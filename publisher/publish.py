"""Airtable publisher for scene analysis results.

Reads analysis.json from a capture directory and publishes
Video and Shot records to Airtable via pyairtable.

Usage:
    from publisher.publish import publish_to_airtable
    result = publish_to_airtable("./captures/abc123", api_key="pat...", base_id="app...")
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pyairtable import Api

from publisher.r2_uploader import (
    R2Config,
    R2UploadError,
    build_attachment_urls,
    create_s3_client,
    upload_all_frames,
    upload_scene_frames,
)
from segmenter.scene_merger import merge_short_scenes
from segmenter.transcript_segmenter import segment_transcript_by_scenes

logger = logging.getLogger(__name__)


class PublisherError(Exception):
    """Raised when the publisher encounters a recoverable error."""

    pass


def is_shot_enriched(fields: dict[str, Any]) -> bool:
    """Check whether a shot record has already been enriched.

    A shot is considered enriched if it has a truthy AI Prompt Version field,
    indicating a previous successful LLM enrichment pass. Shots with only
    AI Error (no AI Prompt Version) are NOT considered enriched and remain
    eligible for retry.

    Args:
        fields: Airtable field dict from a Shot record.

    Returns:
        True if the shot was already successfully enriched.
    """
    return bool(fields.get("AI Prompt Version"))


def load_analysis(capture_dir: str) -> dict[str, Any]:
    """Load and parse analysis.json from a capture directory.

    Args:
        capture_dir: Path to the capture directory containing analysis.json.

    Returns:
        Parsed analysis dict with videoId, scenes, totalScenes, etc.

    Raises:
        FileNotFoundError: If analysis.json does not exist.
        json.JSONDecodeError: If analysis.json is not valid JSON.
        PublisherError: If required fields are missing.
    """
    analysis_path = Path(capture_dir) / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found in {capture_dir}")

    with open(analysis_path) as f:
        analysis = json.load(f)

    if "videoId" not in analysis:
        raise PublisherError("analysis.json missing required field: videoId")
    if "scenes" not in analysis:
        raise PublisherError("analysis.json missing required field: scenes")

    return analysis


def resolve_frame_filename(
    ts: int, manifest_frame_map: dict[int, str] | None
) -> str | None:
    """Resolve the actual frame filename for a given timestamp.

    When manifest_frame_map is provided, looks up the actual captured filename.
    Returns None if the manifest exists but the timestamp was never captured.
    Falls back to synthesized timestamp-based naming when no manifest is available.

    Args:
        ts: Integer timestamp in seconds.
        manifest_frame_map: Optional dict mapping timestamp → actual filename.

    Returns:
        Frame filename string, or None if the timestamp should be skipped.
    """
    if manifest_frame_map and ts in manifest_frame_map:
        return manifest_frame_map[ts]
    elif manifest_frame_map:
        return None
    else:
        return f"frame_{ts:05d}_t{ts:03d}.000s.png"


def get_manifest_frame_map(capture_dir: str) -> dict[int, str]:
    """Load manifest.json and return a mapping of timestamp → actual filename.

    Args:
        capture_dir: Path to the capture directory containing manifest.json.

    Returns:
        Dict mapping integer timestamp (seconds) to actual frame filename.
        Returns empty dict if manifest.json doesn't exist.
    """
    manifest_path = Path(capture_dir) / "manifest.json"
    if not manifest_path.exists():
        return {}

    with open(manifest_path) as f:
        manifest = json.load(f)

    frame_map: dict[int, str] = {}
    for frame in manifest.get("frames", []):
        ts = int(frame["timestamp"])
        frame_map[ts] = frame["filename"]

    return frame_map


def format_timestamp_hms(seconds: float) -> str:
    """Convert seconds to H:MM:SS format.

    Args:
        seconds: Timestamp in seconds (fractional seconds truncated).

    Returns:
        Formatted string like "0:02:05" or "1:01:01".
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours}:{minutes:02d}:{secs:02d}"


def build_video_fields(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build Airtable Video record fields from analysis data.

    Args:
        analysis: Parsed analysis dict.

    Returns:
        Dict of Airtable field names to values for the Videos table.
    """
    video_id = analysis["videoId"]
    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return {
        "Video ID": video_id,
        "Platform": "YouTube",
        "Video URL": f"https://www.youtube.com/watch?v={video_id}",
        "Thumbnail URL": thumbnail_url,
        "Thumbnail (Image)": [{"url": thumbnail_url}],
    }


def build_shot_records(
    analysis: dict[str, Any],
    video_record_id: str,
    attachment_urls: list[dict[str, Any]] | None = None,
    scene_transcripts: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Build list of Shot record field dicts from analysis.

    Each scene produces 1 Shot record. If attachment_urls is provided,
    Scene Start / Scene End attachment fields are merged in.

    Args:
        analysis: Parsed analysis dict.
        video_record_id: Airtable record ID for the parent Video.
        attachment_urls: Optional list of dicts (one per scene) with
            Scene Start/End Airtable attachment values from R2 upload.

    Returns:
        List of field dicts ready for Airtable batch_create.
    """
    shots: list[dict[str, Any]] = []
    model = analysis.get("analysisModel", "")

    for scene in analysis["scenes"]:
        idx = scene["sceneIndex"]
        description = scene.get("description")
        ai_status = "Done" if description else "Queued"

        record = {
            "Shot Label": f"S{idx + 1:02d}",
            "Video": [video_record_id],
            "Timestamp (sec)": scene["startTimestamp"],
            "Timestamp (hh:mm:ss)": format_timestamp_hms(
                scene["startTimestamp"]
            ),
            "Transcript Start (sec)": scene["startTimestamp"],
            "Transcript End (sec)": scene["endTimestamp"],
            "AI Description (Local)": description,
            "AI Model": model,
            "AI Status": ai_status,
            "Capture Method": "Auto Import",
            "Source Device": "Desktop",
        }

        # Merge image attachments if available
        if attachment_urls and idx < len(attachment_urls):
            record.update(attachment_urls[idx])
        
        # Add transcript line if available
        if scene_transcripts and idx in scene_transcripts:
            record["Transcript Line"] = scene_transcripts[idx]

        shots.append(record)

    return shots


def build_frame_records(
    analysis: dict[str, Any],
    video_record_id: str,
    shot_records: list[dict[str, Any]],
    r2_url_map: dict[str, str],
    sample_rate: int = 1,
    manifest_frame_map: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Build list of Frame record field dicts from analysis.

    For each shot's time range [startTimestamp, endTimestamp], generates one
    Frame record per sample_rate seconds. Each frame is linked to its parent Shot
    and Video records.

    When manifest_frame_map is provided, uses actual captured filenames from
    the manifest instead of synthesizing timestamp-based names. Timestamps
    not found in the manifest are skipped (they were never captured).

    Args:
        analysis: Parsed analysis dict with scenes.
        video_record_id: Airtable record ID for the parent Video.
        shot_records: List of created Shot record dicts (with "id" keys),
            in the same order as analysis["scenes"].
        r2_url_map: Dict mapping frame filename → R2 public URL.
        sample_rate: Create frames every N seconds (default: 1 = every second).
        manifest_frame_map: Optional dict mapping timestamp (int) → actual
            filename from manifest.json. When provided, only timestamps
            present in the map produce Frame records.

    Returns:
        List of field dicts ready for Airtable batch_create on the Frames table.
    """
    video_id = analysis["videoId"]
    scenes = analysis.get("scenes", [])
    frames_by_key: dict[str, dict[str, Any]] = {}

    for i, scene in enumerate(scenes):
        shot_record_id = shot_records[i]["id"] if i < len(shot_records) else None
        start = int(scene["startTimestamp"])
        end = int(scene["endTimestamp"])

        for ts in range(start, end + 1, sample_rate):
            frame_key = f"{video_id}_t{ts:06d}"
            
            # Skip if already created (handles overlapping scene boundaries)
            if frame_key in frames_by_key:
                continue
                
            filename = resolve_frame_filename(ts, manifest_frame_map)
            if filename is None:
                continue

            record: dict[str, Any] = {
                "Frame Key": frame_key,
                "Video": [video_record_id],
                "Timestamp (sec)": ts,
                "Timestamp (hh:mm:ss)": format_timestamp_hms(ts),
                "Source Filename": filename,
            }

            if shot_record_id:
                record["Shot"] = [shot_record_id]

            url = r2_url_map.get(filename)
            if url:
                record["Frame Image"] = [{"url": url}]

            frames_by_key[frame_key] = record

    return list(frames_by_key.values())


def publish_to_airtable(
    capture_dir: str,
    api_key: str,
    base_id: str,
    dry_run: bool = False,
    r2_config: R2Config | None = None,
    segment_transcripts: bool = False,
    merge_scenes: bool = False,
    min_scene_duration: float = 5.0,
    skip_frames: bool = False,
    max_workers: int = 1,
    frame_sample_rate: int = 1,
    enrich_shots: bool = False,
    enrich_fn: Callable[[dict[str, Any]], str] | None = None,
    enrich_model: str = "",
    force_reenrich: bool = False,
) -> dict[str, Any]:
    """Publish analysis results to Airtable.

    Reads analysis.json, upserts a Video record, and creates Shot records
    (one per scene). If r2_config is provided, uploads boundary frame
    images to R2 and attaches them as Scene Start / Scene End.

    When enrich_shots is True and enrich_fn is provided, each shot is
    packaged with its frames and transcript, sent to the LLM via enrich_fn,
    and the parsed response is written back to the shot record.

    Idempotent: re-running deletes existing Shot records for the video
    before creating new ones.

    Args:
        capture_dir: Path to the capture directory containing analysis.json.
        api_key: Airtable personal access token.
        base_id: Airtable base ID (e.g., "appXYZ...").
        dry_run: If True, preview what would be published without writing.
        r2_config: Optional R2 configuration for image uploads.
        enrich_shots: If True, run LLM enrichment on each shot after creation.
        enrich_fn: Callable that takes a prompt payload dict and returns a
            raw LLM response string. Required when enrich_shots is True.
        enrich_model: Model name for AI Model field tracking.
        force_reenrich: If True, re-enrich all shots regardless of existing
            enrichment state. Overrides prompt-version-aware skip logic.

    Returns:
        Summary dict with video_record_id, shots_created, video_id,
        frames_created, and shots_enriched (when enrichment is enabled).

    Raises:
        PublisherError: On validation errors or Airtable API failures.
        FileNotFoundError: If analysis.json is missing.
    """
    if not api_key:
        raise PublisherError("api_key is required")
    if not base_id:
        raise PublisherError("base_id is required")

    analysis = load_analysis(capture_dir)
    video_id = analysis["videoId"]
    video_fields = build_video_fields(analysis)

    # Merge short scenes if requested
    if merge_scenes:
        original_count = len(analysis["scenes"])
        analysis["scenes"] = merge_short_scenes(
            analysis["scenes"], min_duration=min_scene_duration
        )
        logger.info(
            "Merged %d scenes into %d (min_duration=%.1fs)",
            original_count,
            len(analysis["scenes"]),
            min_scene_duration,
        )

    # Upload images to R2 if configured
    s3_client = None
    attachment_urls: list[dict[str, Any]] | None = None
    if r2_config:
        try:
            s3_client = create_s3_client(r2_config)
            url_map = upload_scene_frames(
                s3_client, r2_config, capture_dir, analysis
            )
            attachment_urls = build_attachment_urls(analysis, url_map)
        except R2UploadError as e:
            raise PublisherError(f"Image upload failed: {e}") from e
    
    # Segment transcripts if requested (requires existing Video record)
    scene_transcripts: dict[int, str] = {}
    if segment_transcripts:
        logger.info("Transcript segmentation requested, will fetch after Video lookup")

    if dry_run:
        shot_records = build_shot_records(
            analysis, video_record_id="DRY_RUN",
            attachment_urls=attachment_urls,
            scene_transcripts=scene_transcripts,
        )
        return {
            "dry_run": True,
            "video_id": video_id,
            "shots_to_create": len(shot_records),
            "video_fields": video_fields,
            "shot_records": shot_records,
            "images_uploaded": len(url_map) if r2_config else 0,
        }

    try:
        api = Api(api_key)
        videos_table = api.table(base_id, "Videos")
        shots_table = api.table(base_id, "Shots")

        # Look up existing Video by Video ID
        existing_videos = videos_table.all(
            formula=f"{{Video ID}}='{video_id}'"
        )

        if existing_videos:
            video_record_id = existing_videos[0]["id"]
            videos_table.update(video_record_id, video_fields)
            logger.info("Updated existing Video record: %s", video_record_id)
            
            # Fetch timestamped transcript for segmentation if enabled
            if segment_transcripts:
                timestamped_transcript = existing_videos[0]["fields"].get("Transcript (Timestamped)")
                if timestamped_transcript:
                    scene_transcripts = segment_transcript_by_scenes(
                        timestamped_transcript,
                        analysis["scenes"]
                    )
                    logger.info("Segmented transcript into %d scenes", len(scene_transcripts))
                else:
                    logger.warning("Transcript segmentation requested but no timestamped transcript found")
        else:
            result = videos_table.create(video_fields)
            video_record_id = result["id"]
            logger.info("Created new Video record: %s", video_record_id)
            
            if segment_transcripts:
                logger.warning("Cannot segment transcripts for newly created Video (no transcript data yet)")

        # Delete existing shots for idempotency.
        # Linked record fields can't be queried by record ID in formulas,
        # so read the reverse-link "Shots" field from the Video record.
        # Before deleting, read old shot records to preserve enrichment state.
        old_enrichment_by_label: dict[str, dict[str, Any]] = {}
        if existing_videos:
            existing_shot_ids = existing_videos[0]["fields"].get("Shots", [])
            if existing_shot_ids:
                if enrich_shots and enrich_fn:
                    for shot_id in existing_shot_ids:
                        old_record = shots_table.get(shot_id)
                        old_fields = old_record.get("fields", {})
                        label = old_fields.get("Shot Label", "")
                        if label:
                            old_enrichment_by_label[label] = old_fields
                    logger.info(
                        "Read %d old shot records for enrichment state",
                        len(old_enrichment_by_label),
                    )
                shots_table.batch_delete(existing_shot_ids)
                logger.info(
                    "Deleted %d existing Shot records", len(existing_shot_ids)
                )

        # Create new Shot records
        shot_records = build_shot_records(
            analysis, video_record_id,
            attachment_urls=attachment_urls,
            scene_transcripts=scene_transcripts,
        )
        created = shots_table.batch_create(shot_records)
        logger.info("Created %d Shot records", len(created))

        # Create Frame records if R2 is configured and frames not skipped
        frames_created_count = 0
        if r2_config and not skip_frames:
            frames_table = api.table(base_id, "Frames")

            # Delete existing frames for idempotency
            if existing_videos:
                existing_frame_ids = existing_videos[0]["fields"].get("Frames", [])
                if existing_frame_ids:
                    frames_table.batch_delete(existing_frame_ids)
                    logger.info(
                        "Deleted %d existing Frame records", len(existing_frame_ids)
                    )

            # Load manifest for actual frame filenames
            manifest_frame_map = get_manifest_frame_map(capture_dir)

            # Generate frame filenames (manifest-driven when available)
            frame_filenames = []
            for scene in analysis["scenes"]:
                start = int(scene["startTimestamp"])
                end = int(scene["endTimestamp"])
                for ts in range(start, end + 1, frame_sample_rate):
                    filename = resolve_frame_filename(ts, manifest_frame_map)
                    if filename is not None:
                        frame_filenames.append(filename)

            # Upload all frames to R2 (reuse s3_client from scene uploads)
            frame_url_map = upload_all_frames(
                s3_client=s3_client,
                config=r2_config,
                capture_dir=capture_dir,
                video_id=video_id,
                frame_filenames=frame_filenames,
                max_workers=max_workers,
            )

            # Build and create Frame records
            frame_records = build_frame_records(
                analysis, video_record_id, created, frame_url_map,
                sample_rate=frame_sample_rate,
                manifest_frame_map=manifest_frame_map or None,
            )
            created_frames = frames_table.batch_create(frame_records)
            frames_created_count = len(created_frames)
            logger.info("Created %d Frame records", frames_created_count)

        # Enrich shots with LLM analysis if requested
        shots_enriched_count = 0
        shots_skipped_count = 0
        if enrich_shots and enrich_fn:
            from publisher.shot_package import (
                AI_PROMPT_VERSION,
                SHOT_ENRICHMENT_FIELDS,
                build_enrichment_prompt,
                build_shot_package,
                collect_shot_frames,
                parse_llm_response,
            )

            # Field names that should be preserved from old enrichment
            enrichment_preserve_fields = set(SHOT_ENRICHMENT_FIELDS.values()) | {
                "AI Prompt Version", "AI Updated At", "AI Model", "AI JSON",
            }

            manifest_frame_map_enrich = get_manifest_frame_map(capture_dir)

            total_shots = len(created)
            for i, shot_record in enumerate(created):
                scene = analysis["scenes"][i]
                shot_label = f"S{scene['sceneIndex'] + 1:02d}"

                # Check if old shot was already enriched
                old_fields = old_enrichment_by_label.get(shot_label, {})

                if not force_reenrich and is_shot_enriched(old_fields):
                    # Check prompt version — re-enrich if stale
                    old_version = old_fields.get("AI Prompt Version", "")
                    if old_version == AI_PROMPT_VERSION:
                        # Copy old enrichment fields to new shot record
                        preserved = {
                            k: v for k, v in old_fields.items()
                            if k in enrichment_preserve_fields and v is not None
                        }
                        if preserved:
                            shots_table.update(shot_record["id"], preserved)
                        shots_skipped_count += 1
                        logger.info(
                            "Skipped enrichment for shot %s (%s) — already enriched (v%s)",
                            shot_record["id"],
                            shot_label,
                            old_version,
                        )
                        continue
                    logger.info(
                        "Re-enriching %s — prompt version changed (%s → %s)",
                        shot_label,
                        old_version,
                        AI_PROMPT_VERSION,
                    )

                logger.info(
                    "Enriching %s (%d/%d) — requesting LLM analysis",
                    shot_label,
                    i + 1,
                    total_shots,
                )
                shot_start = time.monotonic()
                try:
                    frames = collect_shot_frames(
                        scene,
                        manifest_frame_map_enrich or None,
                        sample_rate=frame_sample_rate,
                    )
                    transcript = scene_transcripts.get(i, "")
                    package = build_shot_package(
                        scene, frames, transcript, video_id
                    )
                    prompt = build_enrichment_prompt(package)
                    raw_response = enrich_fn(prompt)
                    elapsed = time.monotonic() - shot_start
                    fields = parse_llm_response(raw_response)
                    fields["AI Prompt Version"] = AI_PROMPT_VERSION
                    fields["AI Updated At"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    if enrich_model:
                        fields["AI Model"] = enrich_model
                    shots_table.update(shot_record["id"], fields)
                    shots_enriched_count += 1
                    logger.info(
                        "Enriched %s (%d/%d) in %.1fs",
                        shot_label,
                        i + 1,
                        total_shots,
                        elapsed,
                    )
                except Exception as e:
                    elapsed = time.monotonic() - shot_start
                    logger.warning(
                        "Enrichment failed for %s (%d/%d) after %.1fs: %s",
                        shot_label,
                        i + 1,
                        total_shots,
                        elapsed,
                        e,
                    )
                    shots_table.update(
                        shot_record["id"],
                        {"AI Error": f"Enrichment failed for {shot_label}: {e}"},
                    )

        return {
            "video_record_id": video_record_id,
            "video_id": video_id,
            "shots_created": len(created),
            "frames_created": frames_created_count,
            "shots_enriched": shots_enriched_count,
            "shots_skipped_enrichment": shots_skipped_count,
        }

    except PublisherError:
        raise
    except Exception as e:
        raise PublisherError(f"Airtable API error: {e}") from e
