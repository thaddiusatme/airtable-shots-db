"""Shot package assembly and LLM response parsing.

Builds a complete shot package (frames + transcript) for LLM enrichment,
and parses structured LLM output into Airtable field dicts.

Usage:
    from publisher.shot_package import build_shot_package, collect_shot_frames, parse_llm_response
"""

from __future__ import annotations

import json
import logging
from typing import Any

from publisher.publish import resolve_frame_filename

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field mapping: LLM output keys → Airtable column names
# ---------------------------------------------------------------------------

SHOT_ENRICHMENT_FIELDS: dict[str, str] = {
    "scene_summary": "AI Description (Local)",
    "how_it_is_shot": "How It Is Shot",
    "shot_type": "Shot Type",
    "camera_angle": "Camera Angle",
    "movement": "Movement",
    "lighting": "Lighting",
    "setting": "Setting",
    "subject": "Subject",
    "on_screen_text": "On-screen Text",
    "shot_function": "Shot Function",
    "frame_progression": "Frame Progression",
    "production_patterns": "Production Patterns",
    "recreation_guidance": "Recreation Guidance",
}


# ---------------------------------------------------------------------------
# Frame collection
# ---------------------------------------------------------------------------


def collect_shot_frames(
    scene: dict[str, Any],
    manifest_frame_map: dict[int, str] | None,
    sample_rate: int = 1,
) -> list[dict[str, Any]]:
    """Gather all frames belonging to a single shot in stable timestamp order.

    For each integer timestamp in [startTimestamp, endTimestamp] at the given
    sample_rate, resolves the actual filename via manifest (if available) or
    synthesized naming.

    Args:
        scene: Scene dict with startTimestamp and endTimestamp.
        manifest_frame_map: Optional dict mapping timestamp → actual filename.
            When provided, only timestamps present in the map produce frames.
        sample_rate: Collect frames every N seconds (default: 1).

    Returns:
        List of frame dicts with 'filename' and 'timestamp' keys,
        sorted by timestamp ascending.
    """
    start = int(scene["startTimestamp"])
    end = int(scene["endTimestamp"])

    frames: list[dict[str, Any]] = []
    for ts in range(start, end + 1, sample_rate):
        filename = resolve_frame_filename(ts, manifest_frame_map)
        if filename is None:
            continue
        frames.append({"filename": filename, "timestamp": ts})

    return frames


# ---------------------------------------------------------------------------
# Shot package assembly
# ---------------------------------------------------------------------------


def build_shot_package(
    scene: dict[str, Any],
    frames: list[dict[str, Any]],
    transcript_slice: str,
    video_id: str,
) -> dict[str, Any]:
    """Assemble a complete shot package for LLM consumption.

    Combines scene identity/timing, ordered frame list, and the full
    timestamped transcript slice into a single dict suitable for building
    an LLM prompt payload.

    Args:
        scene: Scene dict with sceneIndex, startTimestamp, endTimestamp.
        frames: Pre-collected list of frame dicts (filename, timestamp),
            expected to be in timestamp order.
        transcript_slice: Full timestamped transcript text for this shot.
        video_id: YouTube video ID for context.

    Returns:
        Shot package dict with keys: shot_label, video_id, scene_index,
        start_timestamp, end_timestamp, frames, transcript.
    """
    idx = scene["sceneIndex"]
    return {
        "shot_label": f"S{idx + 1:02d}",
        "video_id": video_id,
        "scene_index": idx,
        "start_timestamp": scene["startTimestamp"],
        "end_timestamp": scene["endTimestamp"],
        "frames": list(frames),
        "transcript": transcript_slice,
    }


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


def parse_llm_response(raw_response: str) -> dict[str, Any]:
    """Parse structured LLM output into an Airtable field dict.

    Maps LLM JSON keys to Airtable column names using SHOT_ENRICHMENT_FIELDS.
    Stores the full raw JSON in 'AI JSON' for future analysis/migrations.
    On parse failure, returns an 'AI Error' field instead.

    Args:
        raw_response: JSON string from the LLM.

    Returns:
        Dict of Airtable field names → values. Always includes either
        'AI JSON' (on success) or 'AI Error' (on failure).
    """
    if not raw_response or not raw_response.strip():
        return {"AI Error": "Empty LLM response"}

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        return {"AI Error": f"Invalid JSON from LLM: {e}"}

    fields: dict[str, Any] = {}

    # Map each LLM key to its Airtable column, skipping None values
    for llm_key, airtable_col in SHOT_ENRICHMENT_FIELDS.items():
        value = data.get(llm_key)
        if value is not None:
            fields[airtable_col] = value

    # Preserve full raw JSON for future analysis
    fields["AI JSON"] = raw_response

    return fields
