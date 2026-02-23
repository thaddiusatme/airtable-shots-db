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
    return {
        "Video ID": video_id,
        "Platform": "YouTube",
        "Video URL": f"https://www.youtube.com/watch?v={video_id}",
        "Thumbnail URL": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    }


def build_shot_records(
    analysis: dict[str, Any], video_record_id: str
) -> list[dict[str, Any]]:
    """Build list of Shot record field dicts from analysis.

    Each scene produces 2 Shot records: one for the first frame (start)
    and one for the last frame (end).

    Args:
        analysis: Parsed analysis dict.
        video_record_id: Airtable record ID for the parent Video.

    Returns:
        List of field dicts ready for Airtable batch_create.
    """
    shots: list[dict[str, Any]] = []
    model = analysis.get("analysisModel", "")

    for scene in analysis["scenes"]:
        idx = scene["sceneIndex"]
        description = scene.get("description")
        ai_status = "Done" if description else "Queued"

        # First frame (scene start)
        shots.append(
            {
                "Shot Label": f"Scene {idx} — Start",
                "Video": [video_record_id],
                "Timestamp (sec)": scene["startTimestamp"],
                "Timestamp (hh:mm:ss)": format_timestamp_hms(
                    scene["startTimestamp"]
                ),
                "AI Description (Local)": description,
                "AI Model": model,
                "AI Status": ai_status,
                "Capture Method": "Auto Import",
                "Source Device": "Desktop",
            }
        )

        # Last frame (scene end)
        shots.append(
            {
                "Shot Label": f"Scene {idx} — End",
                "Video": [video_record_id],
                "Timestamp (sec)": scene["endTimestamp"],
                "Timestamp (hh:mm:ss)": format_timestamp_hms(
                    scene["endTimestamp"]
                ),
                "AI Description (Local)": description,
                "AI Model": model,
                "AI Status": ai_status,
                "Capture Method": "Auto Import",
                "Source Device": "Desktop",
            }
        )

    return shots


def publish_to_airtable(
    capture_dir: str,
    api_key: str,
    base_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Publish analysis results to Airtable.

    Reads analysis.json, upserts a Video record, and creates Shot records
    for each scene (2 per scene: first frame + last frame).

    Idempotent: re-running deletes existing Shot records for the video
    before creating new ones.

    Args:
        capture_dir: Path to the capture directory containing analysis.json.
        api_key: Airtable personal access token.
        base_id: Airtable base ID (e.g., "appXYZ...").
        dry_run: If True, preview what would be published without writing.

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

    if dry_run:
        shot_records = build_shot_records(analysis, video_record_id="DRY_RUN")
        return {
            "dry_run": True,
            "video_id": video_id,
            "shots_to_create": len(shot_records),
            "video_fields": video_fields,
            "shot_records": shot_records,
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
        else:
            result = videos_table.create(video_fields)
            video_record_id = result["id"]
            logger.info("Created new Video record: %s", video_record_id)

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
        shot_records = build_shot_records(analysis, video_record_id)
        created = shots_table.batch_create(shot_records)
        logger.info("Created %d Shot records", len(created))

        return {
            "video_record_id": video_record_id,
            "video_id": video_id,
            "shots_created": len(created),
        }

    except PublisherError:
        raise
    except Exception as e:
        raise PublisherError(f"Airtable API error: {e}") from e
