"""GH-33 pencil storyboard handoff — thin downstream consumer of GH-32.

Transforms GH-32 assembled prompt dicts into storyboard-generation payloads
with pencil-only style layer, 16:9 defaults, deterministic A/B variant
generation, and enriched-shot Airtable retrieval.

Designed as a thin wrapper: reuses assemble_shot_image_prompt() as the
semantic base and adds only the style/generation/variant layer on top.

Usage:
    from publisher.storyboard_handoff import (
        STORYBOARD_HANDOFF_VERSION,
        build_storyboard_payload,
        build_storyboard_series,
        fetch_enriched_shots_for_storyboard,
    )
"""

from __future__ import annotations

from typing import Any

from publisher.prompt_assembler import ASSEMBLER_VERSION, assemble_shot_image_prompt

STORYBOARD_HANDOFF_VERSION: str = "0.1"
"""Tracks the storyboard handoff contract revision."""

# ---------------------------------------------------------------------------
# Style defaults — pencil-only storyboard preset
# ---------------------------------------------------------------------------

STORYBOARD_STYLE_DEFAULTS: dict[str, Any] = {
    "style_preset": "pencil-only storyboard",
    "positive_style_tokens": (
        "pencil sketch, rough storyboard panel, monochrome line art, "
        "hand-drawn, graphite on paper, cinematic composition"
    ),
    "negative_style_tokens": (
        "color, photorealistic, photograph, saturated, 3d render, "
        "painting, digital art, smooth shading"
    ),
    "aspect_ratio": "16:9",
    "width": 1024,
    "height": 576,
}

# ---------------------------------------------------------------------------
# Variant definitions — deterministic A/B(/C) labels + modifiers
# ---------------------------------------------------------------------------

VARIANT_DEFINITIONS: list[dict[str, str]] = [
    {
        "label": "A",
        "positive_modifier": "clean precise linework, detailed storyboard panel",
    },
    {
        "label": "B",
        "positive_modifier": "loose expressive sketch, gestural storyboard panel",
    },
    {
        "label": "C",
        "positive_modifier": "high contrast ink wash, bold storyboard panel",
    },
]


# ---------------------------------------------------------------------------
# Reference frame selection
# ---------------------------------------------------------------------------


def _evenly_sample(items: list, n: int) -> list:
    """Pick *n* items at evenly-spaced indices from *items*.

    Preserves first and last item when n >= 2.  Returns a new list.
    """
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    if n == 1:
        return [items[0]]
    # Always include first and last; fill the middle evenly
    indices = [0]
    for i in range(1, n - 1):
        idx = round(i * (len(items) - 1) / (n - 1))
        indices.append(idx)
    indices.append(len(items) - 1)
    return [items[i] for i in indices]


def select_reference_frames(
    pool: list[dict[str, str]] | None,
    *,
    max_frames: int = 4,
    min_frames: int = 2,
) -> list[dict[str, str]]:
    """Select 2-4 reference frames in stable order from a frame pool.

    Uses even sampling to spread across the pool (first, middle, last)
    rather than just taking the first N.
    """
    if not pool:
        return []
    target = min(max(min_frames, min(len(pool), max_frames)), len(pool))
    return _evenly_sample(pool, target)


# ---------------------------------------------------------------------------
# Single-shot storyboard payload builder
# ---------------------------------------------------------------------------


def build_storyboard_payload(
    shot_fields: dict[str, Any],
    *,
    reference_frames: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a storyboard-generation payload for one shot.

    Wraps assemble_shot_image_prompt() with pencil-only style layer,
    16:9 generation defaults, and deterministic prompt variants.

    Args:
        shot_fields: Enriched shot dict (Airtable field names).
        reference_frames: Optional pool of frame dicts. Will be
            trimmed to 2-4 via select_reference_frames().

    Returns:
        Dict with keys: base_prompt, storyboard_positive,
        storyboard_negative, style, generation, reference_images,
        variants, metadata.
    """
    # -- Base prompt from GH-32 assembler --
    selected_refs = select_reference_frames(reference_frames)
    base = assemble_shot_image_prompt(shot_fields, reference_frames=selected_refs)

    # -- Storyboard positive = base positive + style tokens --
    style_tokens = STORYBOARD_STYLE_DEFAULTS["positive_style_tokens"]
    storyboard_positive = f"{base['positive_prompt']}, {style_tokens}"

    # -- Storyboard negative = base negative + style negative tokens --
    neg_tokens = STORYBOARD_STYLE_DEFAULTS["negative_style_tokens"]
    storyboard_negative = f"{base['negative_prompt']}, {neg_tokens}"

    # -- Style block --
    style = {
        "style_preset": STORYBOARD_STYLE_DEFAULTS["style_preset"],
    }

    # -- Generation defaults --
    generation = {
        "aspect_ratio": STORYBOARD_STYLE_DEFAULTS["aspect_ratio"],
        "width": STORYBOARD_STYLE_DEFAULTS["width"],
        "height": STORYBOARD_STYLE_DEFAULTS["height"],
    }

    # -- Variants --
    variants: list[dict[str, str]] = []
    for vdef in VARIANT_DEFINITIONS:
        variants.append({
            "label": vdef["label"],
            "positive_prompt": f"{storyboard_positive}, {vdef['positive_modifier']}",
        })

    # -- Metadata --
    metadata: dict[str, Any] = {
        "shot_label": base["metadata"]["shot_label"],
        "assembler_version": ASSEMBLER_VERSION,
        "handoff_version": STORYBOARD_HANDOFF_VERSION,
        "variant_count": len(VARIANT_DEFINITIONS),
    }

    return {
        "base_prompt": base,
        "storyboard_positive": storyboard_positive,
        "storyboard_negative": storyboard_negative,
        "style": style,
        "generation": generation,
        "reference_images": selected_refs,
        "variants": variants,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Multi-shot storyboard series
# ---------------------------------------------------------------------------


def build_storyboard_series(
    shots: list[dict[str, Any]],
    *,
    reference_frames_by_shot: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, Any]]:
    """Build an ordered storyboard series from multiple enriched shots.

    Args:
        shots: List of enriched shot field dicts.
        reference_frames_by_shot: Optional mapping of shot label →
            frame pool.  Falls back to empty pool when absent.

    Returns:
        Ordered list of storyboard payloads with series_index in metadata.
    """
    if not shots:
        return []
    ref_map = reference_frames_by_shot or {}
    series: list[dict[str, Any]] = []
    for idx, shot_fields in enumerate(shots):
        label = shot_fields.get("Shot Label", "")
        refs = ref_map.get(label)
        payload = build_storyboard_payload(shot_fields, reference_frames=refs)
        payload["metadata"]["series_index"] = idx
        series.append(payload)
    return series


# ---------------------------------------------------------------------------
# Airtable retrieval — enriched shots for storyboard
# ---------------------------------------------------------------------------


def fetch_enriched_shots_for_storyboard(
    shots_table,
    *,
    video_id: str,
    shot_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch enriched shot records from an Airtable Shots table.

    Follows the same filtering pattern as validate_prompt_assembler.py:
    enriched = AI Prompt Version is non-empty.

    Args:
        shots_table: pyairtable Table object for the Shots table.
        video_id: Video ID to filter by.
        shot_id: Optional record ID or shot label to narrow results.

    Returns:
        List of Airtable record dicts (each with 'id' and 'fields').
    """
    formula_parts = ["{AI Prompt Version}!=''"]
    formula_parts.append(f"FIND('{video_id}', ARRAYJOIN({{Video}}))")

    if shot_id:
        formula_parts.append(f"RECORD_ID()='{shot_id}'")

    formula = f"AND({', '.join(formula_parts)})"
    records = shots_table.all(formula=formula)
    return records
