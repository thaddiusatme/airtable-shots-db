"""Per-shot SDXL/ComfyUI image prompt assembler — GH-32 contract v1.

Transforms enriched shot data (Airtable field names) into a structured
prompt dict suitable for SDXL/ComfyUI image generation pipelines.

Deterministic output: stable key ordering, stable whitespace, no randomness.

Usage:
    from publisher.prompt_assembler import (
        ASSEMBLER_VERSION,
        assemble_shot_image_prompt,
    )
"""

from __future__ import annotations

import re
from typing import Any

ASSEMBLER_VERSION: str = "1.1"
"""Tracks the prompt assembler revision for metadata."""

# ---------------------------------------------------------------------------
# Boilerplate detection
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"no pattern information", re.IGNORECASE),
    re.compile(r"not enough information", re.IGNORECASE),
    re.compile(r"no (?:relevant )?information (?:available|provided)", re.IGNORECASE),
    re.compile(r"cannot be determined", re.IGNORECASE),
    re.compile(r"insufficient (?:data|information)", re.IGNORECASE),
)

_UNINFORMATIVE_NARRATIVES: frozenset[str] = frozenset({
    "other", "yes", "no", "n/a", "na", "none", "static", "unknown",
})
"""Short single-word values that add noise, not signal, to SDXL prompts.

These are typically controlled-vocab leaks into narrative fields
(e.g., How It Is Shot = "Other") or uninformative placeholders.
"""

_BASELINE_NEGATIVE_PROMPT: str = (
    "blurry, deformed, low quality, watermark, text overlay, "
    "out of focus, oversaturated, jpeg artifacts"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_boilerplate(text: str) -> bool:
    """Return True if the text matches a known boilerplate phrase."""
    if not text or not text.strip():
        return True
    return any(pat.search(text) for pat in _BOILERPLATE_PATTERNS)


def _should_omit_controlled(value: str | None) -> bool:
    """Return True if a controlled-vocab field value should be omitted."""
    if not value:
        return True
    return value.strip().lower() == "other"


def _filter_narrative(value: str | None, field_name: str, omissions: list[str]) -> str:
    """Return the narrative text if non-boilerplate, else empty string + track omission."""
    if not value or not value.strip():
        return ""
    stripped = value.strip()
    if _is_boilerplate(stripped):
        omissions.append(f"{field_name}: boilerplate filtered")
        return ""
    if stripped.lower() in _UNINFORMATIVE_NARRATIVES:
        omissions.append(f"{field_name}: uninformative value '{stripped}' filtered")
        return ""
    return stripped


def _build_positive_prompt(sections: dict[str, str]) -> str:
    """Concatenate prompt sections into a single positive prompt string.

    Joins non-empty section values with comma-space separators.
    Ordering is deterministic: subject, setting, composition, camera,
    lighting, style, context, constraints.
    """
    section_order = (
        "subject", "setting", "composition", "camera",
        "lighting", "style", "context", "constraints",
    )
    parts: list[str] = []
    for key in section_order:
        val = sections.get(key, "")
        if val:
            parts.append(val)
    return ", ".join(parts)


def _normalize_reference_frames(
    frames: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Ensure every frame dict has a 'role' key (default: 'composition')."""
    if not frames:
        return []
    result: list[dict[str, str]] = []
    for f in frames:
        result.append({
            "url": f["url"],
            "role": f.get("role", "composition"),
        })
    return result


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------


def assemble_shot_image_prompt(
    shot_fields: dict[str, Any],
    reference_frames: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assemble a structured image-generation prompt from enriched shot data.

    Args:
        shot_fields: Dict with Airtable field names from an enriched shot
            record. Required keys: Shot Label, Subject, Setting.
            Optional: Shot Type, Camera Angle, Lighting, Movement,
            How It Is Shot, AI Description (Local), Shot Function,
            On-screen Text, Frame Progression, Production Patterns,
            Recreation Guidance.
        reference_frames: Optional list of frame dicts with 'url' and
            optional 'role' keys. Role defaults to 'composition'.

    Returns:
        Dict with keys: positive_prompt, negative_prompt, prompt_sections,
        reference_images, metadata.
    """
    omissions: list[str] = []
    sections: dict[str, str] = {}

    # -- Subject (required, but may be empty for unenriched shots) --
    subject = shot_fields.get("Subject", "").strip()
    if subject:
        sections["subject"] = subject

    # -- Setting (required, but may be empty for unenriched shots) --
    setting = shot_fields.get("Setting", "").strip()
    if setting:
        sections["setting"] = setting

    # -- Composition (from How It Is Shot) --
    how_shot = _filter_narrative(
        shot_fields.get("How It Is Shot"), "How It Is Shot", omissions,
    )
    if how_shot:
        sections["composition"] = how_shot

    # -- Camera (Shot Type + Camera Angle, omit Other) --
    camera_parts: list[str] = []
    shot_type = shot_fields.get("Shot Type", "")
    if shot_type and not _should_omit_controlled(shot_type):
        camera_parts.append(f"{shot_type.strip().lower()} shot")

    camera_angle = shot_fields.get("Camera Angle", "")
    if camera_angle and not _should_omit_controlled(camera_angle):
        camera_parts.append(f"{camera_angle.strip().lower()} angle")
    else:
        if camera_angle and camera_angle.strip().lower() == "other":
            omissions.append("Camera Angle: Other (low-signal, omitted)")

    if camera_parts:
        sections["camera"] = ", ".join(camera_parts)

    # -- Lighting (omit Other) --
    lighting = shot_fields.get("Lighting", "")
    if lighting and not _should_omit_controlled(lighting):
        sections["lighting"] = f"{lighting.strip().lower()} lighting"
    else:
        if lighting and lighting.strip().lower() == "other":
            omissions.append("Lighting: Other (low-signal, omitted)")

    # -- Style (from Production Patterns) --
    prod_patterns = _filter_narrative(
        shot_fields.get("Production Patterns"), "Production Patterns", omissions,
    )
    if prod_patterns:
        sections["style"] = prod_patterns

    # -- Context (from Frame Progression + Recreation Guidance) --
    context_parts: list[str] = []
    frame_prog = _filter_narrative(
        shot_fields.get("Frame Progression"), "Frame Progression", omissions,
    )
    if frame_prog:
        context_parts.append(frame_prog)
    rec_guidance = _filter_narrative(
        shot_fields.get("Recreation Guidance"), "Recreation Guidance", omissions,
    )
    if rec_guidance:
        context_parts.append(rec_guidance)
    if context_parts:
        sections["context"] = "; ".join(context_parts)

    # -- Constraints (from On-screen Text, if non-empty) --
    on_screen = (shot_fields.get("On-screen Text") or "").strip()
    if on_screen:
        sections["constraints"] = f"on-screen text: {on_screen}"

    # -- Build prompts --
    positive_prompt = _build_positive_prompt(sections)
    negative_prompt = _BASELINE_NEGATIVE_PROMPT

    # -- Reference images --
    reference_images = _normalize_reference_frames(reference_frames)

    # -- Metadata --
    metadata: dict[str, Any] = {
        "shot_label": shot_fields.get("Shot Label", ""),
        "assembler_version": ASSEMBLER_VERSION,
        "omissions": omissions,
    }

    return {
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "prompt_sections": sections,
        "reference_images": reference_images,
        "metadata": metadata,
    }
