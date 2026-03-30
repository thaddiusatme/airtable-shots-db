"""Shot package assembly, prompt building, and LLM response parsing.

Builds a complete shot package (frames + transcript) for LLM enrichment,
constructs the multimodal prompt payload, and parses structured LLM output
into Airtable field dicts.

Usage:
    from publisher.shot_package import (
        build_shot_package, collect_shot_frames,
        build_enrichment_prompt, parse_llm_response,
        AI_PROMPT_VERSION, SHOT_ENRICHMENT_FIELDS,
    )
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from publisher.publish import resolve_frame_filename

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AI_PROMPT_VERSION: str = "1.2"
"""Tracks the prompt template revision for AI Model / AI Prompt Version fields."""

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

CONTROLLED_VOCAB_GUIDANCE: str = (
    "Use these Airtable-safe value rules for controlled fields:\n"
    "- shot_type: choose exactly one of Wide, Medium, Close-up, POV, OTS, Insert, Establishing, Screen, Drone, Other.\n"
    "- camera_angle: choose exactly one of Eye-level, High, Low, Top-down, Dutch, Other.\n"
    "- movement: return a JSON array of zero or more values chosen from Static, Pan, Tilt, Push-in, Pull-out, Handheld, Gimbal, Zoom, Whip-pan, Other. If there is no visible camera motion, use [\"Static\"].\n"
    "- lighting: choose exactly one of Natural-soft, Natural-hard, Studio-soft, Backlit, Mixed, Neon, Other.\n"
    "- shot_function: choose exactly one of Hook, Proof, Payoff, B-roll, Transition, CTA, Other.\n"
    "If unsure for any controlled field, use \"Other\"."
)

NARRATIVE_FIELD_GUIDANCE: str = (
    "The following fields MUST always be plain strings (never arrays, objects, or numbers):\n"
    "scene_summary, how_it_is_shot, setting, subject, on_screen_text, "
    "frame_progression, production_patterns, recreation_guidance.\n"
    "If a field has multiple items, combine them into a single comma-separated string."
)

_SINGLE_SELECT_NORMALIZERS: dict[str, tuple[str, ...]] = {
    "shot_type": ("Wide", "Medium", "Close-up", "POV", "OTS", "Insert", "Establishing", "Screen", "Drone", "Other"),
    "camera_angle": ("Eye-level", "High", "Low", "Top-down", "Dutch", "Other"),
    "lighting": ("Natural-soft", "Natural-hard", "Studio-soft", "Backlit", "Mixed", "Neon", "Other"),
    "shot_function": ("Hook", "Proof", "Payoff", "B-roll", "Transition", "CTA", "Other"),
}

_MOVEMENT_CHOICES: tuple[str, ...] = (
    "Static", "Pan", "Tilt", "Push-in", "Pull-out", "Handheld", "Gimbal", "Zoom", "Whip-pan", "Other"
)

_NARRATIVE_FIELDS: frozenset[str] = frozenset({
    "scene_summary",
    "how_it_is_shot",
    "setting",
    "subject",
    "on_screen_text",
    "frame_progression",
    "production_patterns",
    "recreation_guidance",
})


# ---------------------------------------------------------------------------
# Prompt payload builder
# ---------------------------------------------------------------------------


def build_enrichment_prompt(shot_package: dict[str, Any]) -> dict[str, Any]:
    """Build the multimodal prompt payload for LLM shot enrichment.

    Produces a structured dict containing the system prompt (with JSON output
    instructions referencing all SHOT_ENRICHMENT_FIELDS keys), a user prompt
    (with shot context, timing, frame count, and transcript), an ordered list
    of frame filename references, and the prompt version for tracking.

    Args:
        shot_package: Dict from build_shot_package() with keys: shot_label,
            video_id, scene_index, start_timestamp, end_timestamp, frames,
            transcript.

    Returns:
        Dict with keys: system_prompt, user_prompt, frame_references,
        prompt_version.
    """
    # -- System prompt: instruct LLM to return structured JSON --
    field_keys = list(SHOT_ENRICHMENT_FIELDS.keys())
    field_list = "\n".join(f"- {key}" for key in field_keys)
    system_prompt = (
        "You are a professional video production analyst. "
        "Analyze the provided video shot (frames and transcript) and return "
        "a single JSON object with the following keys:\n\n"
        f"{field_list}\n\n"
        f"{CONTROLLED_VOCAB_GUIDANCE}\n\n"
        f"{NARRATIVE_FIELD_GUIDANCE}\n\n"
        "Return ONLY valid JSON. Do not include markdown fencing, commentary, "
        "or any text outside the JSON object. Every key must be present; use "
        "null for fields that cannot be determined from the provided material."
    )

    # -- User prompt: shot context + transcript --
    frames = shot_package.get("frames", [])
    transcript = shot_package.get("transcript", "")
    frame_count = len(frames)

    transcript_section = (
        f"Transcript:\n{transcript}"
        if transcript
        else "Transcript:\nNo transcript available (no dialogue in this shot)."
    )

    user_prompt = (
        f"Shot: {shot_package['shot_label']}\n"
        f"Video ID: {shot_package['video_id']}\n"
        f"Time range: {shot_package['start_timestamp']}s – {shot_package['end_timestamp']}s\n"
        f"Frames provided: {frame_count}\n\n"
        f"{transcript_section}"
    )

    # -- Frame references: ordered filenames for multimodal attachment --
    frame_references = [f["filename"] for f in frames]

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "frame_references": frame_references,
        "prompt_version": AI_PROMPT_VERSION,
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


def _normalize_llm_json_response(raw_response: str) -> str:
    """Normalize LLM JSON responses before parsing."""
    normalized = raw_response.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", normalized, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return normalized


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _normalize_shot_type(value: Any) -> str:
    text = _normalize_text(value)
    lower = text.lower()
    if not lower:
        return ""
    if "medium" in lower:
        return "Medium"
    if "close" in lower:
        return "Close-up"
    if "wide" in lower:
        return "Wide"
    if "over the shoulder" in lower or lower == "ots" or " o.t.s" in lower:
        return "OTS"
    if "pov" in lower or "point of view" in lower:
        return "POV"
    if "insert" in lower:
        return "Insert"
    if "establish" in lower:
        return "Establishing"
    if "screen" in lower:
        return "Screen"
    if "drone" in lower or "aerial" in lower:
        return "Drone"
    return "Other"


def _normalize_camera_angle(value: Any) -> str:
    text = _normalize_text(value)
    lower = text.lower()
    if not lower:
        return ""
    if "eye" in lower and "level" in lower:
        return "Eye-level"
    if "top" in lower and "down" in lower:
        return "Top-down"
    if "high" in lower:
        return "High"
    if "low" in lower:
        return "Low"
    if "dutch" in lower or "canted" in lower or "tilted horizon" in lower:
        return "Dutch"
    return "Other"


def _normalize_lighting(value: Any) -> str:
    text = _normalize_text(value)
    lower = text.lower()
    if not lower:
        return ""
    if "studio" in lower or "three-point" in lower or "softbox" in lower:
        return "Studio-soft"
    if "backlit" in lower or "silhouette" in lower:
        return "Backlit"
    if "mixed" in lower or ("natural" in lower and "practical" in lower):
        return "Mixed"
    if "neon" in lower or "rgb" in lower or "cyberpunk" in lower:
        return "Neon"
    if "natural" in lower:
        if "hard" in lower or "harsh" in lower or "direct sun" in lower:
            return "Natural-hard"
        return "Natural-soft"
    return "Other"


def _normalize_shot_function(value: Any) -> str:
    text = _normalize_text(value)
    lower = text.lower()
    if not lower:
        return ""
    if "hook" in lower or "cold open" in lower or "intro" in lower or "opening" in lower:
        return "Hook"
    if "proof" in lower or "demo" in lower or "example" in lower or "explanation" in lower:
        return "Proof"
    if "payoff" in lower or "result" in lower or "reveal" in lower or "conclusion" in lower:
        return "Payoff"
    if "b-roll" in lower or "b roll" in lower or "cutaway" in lower:
        return "B-roll"
    if "transition" in lower or "bridge" in lower:
        return "Transition"
    if "cta" in lower or "call to action" in lower or "subscribe" in lower:
        return "CTA"
    return "Other"


def _normalize_movement(value: Any) -> list[str]:
    if isinstance(value, list):
        text = " ".join(_normalize_text(item) for item in value if _normalize_text(item))
    else:
        text = _normalize_text(value)
    lower = text.lower()
    if not lower:
        return []

    movement_values: list[str] = []

    def add(choice: str) -> None:
        if choice not in movement_values:
            movement_values.append(choice)

    if any(token in lower for token in ("still image", "still frame", "no movement", "static", "locked off", "locked-off")):
        add("Static")
    if "whip-pan" in lower or "whip pan" in lower:
        add("Whip-pan")
    if "push-in" in lower or "push in" in lower or "dolly in" in lower:
        add("Push-in")
    if "pull-out" in lower or "pull out" in lower or "dolly out" in lower:
        add("Pull-out")
    if "handheld" in lower:
        add("Handheld")
    if "gimbal" in lower or "stabilized" in lower or "stabilised" in lower:
        add("Gimbal")
    if "zoom" in lower:
        add("Zoom")
    if re.search(r"\bpan(?:ning)?\b", lower):
        add("Pan")
    if re.search(r"\btilt(?:ing)?\b", lower):
        add("Tilt")

    if movement_values:
        return movement_values
    return ["Other"]


def _coerce_to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, list):
                parts.extend(str(sub) for sub in item)
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(value, dict):
        return ", ".join(str(v) for v in value.values())
    return str(value)


def _normalize_controlled_value(llm_key: str, value: Any) -> Any:
    if llm_key == "shot_type":
        return _normalize_shot_type(value)
    if llm_key == "camera_angle":
        return _normalize_camera_angle(value)
    if llm_key == "lighting":
        return _normalize_lighting(value)
    if llm_key == "shot_function":
        return _normalize_shot_function(value)
    if llm_key == "movement":
        return _normalize_movement(value)
    if llm_key in _NARRATIVE_FIELDS:
        return _coerce_to_string(value)
    return value


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
        data = json.loads(_normalize_llm_json_response(raw_response))
    except json.JSONDecodeError as e:
        return {"AI Error": f"Invalid JSON from LLM: {e}"}

    fields: dict[str, Any] = {}

    # Map each LLM key to its Airtable column, skipping None values
    for llm_key, airtable_col in SHOT_ENRICHMENT_FIELDS.items():
        value = data.get(llm_key)
        if value is not None:
            value = _normalize_controlled_value(llm_key, value)
        if value not in (None, "", []):
            fields[airtable_col] = value

    # Preserve full raw JSON for future analysis
    fields["AI JSON"] = raw_response

    return fields
