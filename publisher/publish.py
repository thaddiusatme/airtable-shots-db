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
from pathlib import Path
from typing import Any

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
) -> list[dict[str, Any]]:
    """Build list of Frame record field dicts from analysis.

    For each shot's time range [startTimestamp, endTimestamp], generates one
    Frame record per sample_rate seconds. Each frame is linked to its parent Shot
    and Video records.

    Args:
        analysis: Parsed analysis dict with scenes.
        video_record_id: Airtable record ID for the parent Video.
        shot_records: List of created Shot record dicts (with "id" keys),
            in the same order as analysis["scenes"].
        r2_url_map: Dict mapping frame filename → R2 public URL.
        sample_rate: Create frames every N seconds (default: 1 = every second).

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
                
            filename = f"frame_{ts:05d}_t{ts:03d}.000s.png"

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
) -> dict[str, Any]:
    """Publish analysis results to Airtable.

    Reads analysis.json, upserts a Video record, and creates Shot records
    (one per scene). If r2_config is provided, uploads boundary frame
    images to R2 and attaches them as Scene Start / Scene End.

    Idempotent: re-running deletes existing Shot records for the video
    before creating new ones.

    Args:
        capture_dir: Path to the capture directory containing analysis.json.
        api_key: Airtable personal access token.
        base_id: Airtable base ID (e.g., "appXYZ...").
        dry_run: If True, preview what would be published without writing.
        r2_config: Optional R2 configuration for image uploads.

    Returns:
        Summary dict with video_record_id, shots_created, video_id.

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
        if existing_videos:
            existing_shot_ids = existing_videos[0]["fields"].get("Shots", [])
            if existing_shot_ids:
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

            # Generate frame filenames (respecting sample rate)
            frame_filenames = []
            for scene in analysis["scenes"]:
                start = int(scene["startTimestamp"])
                end = int(scene["endTimestamp"])
                for ts in range(start, end + 1, frame_sample_rate):
                    frame_filenames.append(f"frame_{ts:05d}_t{ts:03d}.000s.png")

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
                analysis, video_record_id, created, frame_url_map, sample_rate=frame_sample_rate
            )
            created_frames = frames_table.batch_create(frame_records)
            frames_created_count = len(created_frames)
            logger.info("Created %d Frame records", frames_created_count)

        return {
            "video_record_id": video_record_id,
            "video_id": video_id,
            "shots_created": len(created),
            "frames_created": frames_created_count,
        }

    except PublisherError:
        raise
    except Exception as e:
        raise PublisherError(f"Airtable API error: {e}") from e
