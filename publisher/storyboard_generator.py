"""GH-33 storyboard generation runner — iteration 2.

Thin ComfyUI/SDXL generation runner that consumes storyboard payloads
from build_storyboard_payload() and produces ordered storyboard images
(or dry-run JSON files) in a structured output directory.

Output directory layout:
    {output_dir}/{video_id}/{shot_label}/{shot_label}_variant_{A|B|C}.{ext}

Supports dependency injection via generate_fn for swappable backends
(ComfyUI, SDXL API, etc.) and --dry-run mode for development.

Usage:
    from publisher.storyboard_generator import (
        GENERATOR_VERSION,
        generate_shot_storyboard,
        generate_storyboard_series,
        make_comfyui_generate_fn,
        output_path_for_variant,
    )
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

GENERATOR_VERSION: str = "0.1"
"""Tracks the storyboard generation runner revision."""


# ---------------------------------------------------------------------------
# Deterministic output path helper
# ---------------------------------------------------------------------------


def output_path_for_variant(
    output_dir: str,
    video_id: str,
    shot_label: str,
    variant_label: str,
    ext: str = "png",
) -> str:
    """Build a deterministic output file path for a storyboard variant.

    Layout: {output_dir}/{video_id}/{shot_label}/{shot_label}_variant_{label}.{ext}

    Args:
        output_dir: Root output directory.
        video_id: Video identifier for directory grouping.
        shot_label: Shot label (e.g., "S03") for directory and filename.
        variant_label: Variant label (e.g., "A", "B", "C").
        ext: File extension without dot (default: "png").

    Returns:
        Absolute file path string.
    """
    filename = f"{shot_label}_variant_{variant_label}.{ext}"
    return os.path.join(output_dir, video_id, shot_label, filename)


# ---------------------------------------------------------------------------
# Single-shot generation
# ---------------------------------------------------------------------------

# Type alias for generate_fn signature
GenerateFn = Callable[[str, str, int, int, str], str]


def generate_shot_storyboard(
    payload: dict[str, Any],
    *,
    video_id: str,
    output_dir: str,
    dry_run: bool = True,
    generate_fn: GenerateFn | None = None,
) -> list[str | None]:
    """Generate storyboard images (or dry-run JSON) for one shot's variants.

    Args:
        payload: Storyboard payload dict from build_storyboard_payload().
        video_id: Video identifier for output directory grouping.
        output_dir: Root output directory.
        dry_run: If True, write JSON payload files instead of generating.
        generate_fn: Callable(positive_prompt, negative_prompt, width, height,
            output_path) -> output_path. Required when dry_run=False.

    Returns:
        List of output file paths (one per variant). None entries indicate
        failed variants (error isolated, others still proceed).
    """
    shot_label = payload["metadata"]["shot_label"]
    generation = payload["generation"]
    width = generation["width"]
    height = generation["height"]
    negative_prompt = payload["storyboard_negative"]

    results: list[str | None] = []

    for variant in payload["variants"]:
        variant_label = variant["label"]
        positive_prompt = variant["positive_prompt"]

        if dry_run:
            out_path = output_path_for_variant(
                output_dir, video_id, shot_label, variant_label, ext="json",
            )
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            dry_run_payload = {
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "generation": {
                    "width": width,
                    "height": height,
                    "aspect_ratio": generation.get("aspect_ratio", ""),
                },
                "variant_label": variant_label,
                "shot_label": shot_label,
                "video_id": video_id,
                "style": payload.get("style", {}),
                "generator_version": GENERATOR_VERSION,
            }

            with open(out_path, "w") as f:
                json.dump(dry_run_payload, f, indent=2)

            results.append(out_path)
            logger.info("Dry-run wrote %s", out_path)

        elif generate_fn is not None:
            out_path = output_path_for_variant(
                output_dir, video_id, shot_label, variant_label, ext="png",
            )
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            try:
                generate_fn(
                    positive_prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    output_path=out_path,
                )
                results.append(out_path)
                logger.info("Generated %s", out_path)
            except Exception as exc:
                logger.warning(
                    "Generation failed for %s variant %s: %s",
                    shot_label, variant_label, exc,
                )
                results.append(None)
        else:
            # No generate_fn and not dry_run — skip
            results.append(None)

    return results


# ---------------------------------------------------------------------------
# Multi-shot series generation
# ---------------------------------------------------------------------------


def generate_storyboard_series(
    series: list[dict[str, Any]],
    *,
    video_id: str,
    output_dir: str,
    dry_run: bool = True,
    generate_fn: GenerateFn | None = None,
) -> list[list[str | None]]:
    """Generate storyboard images for a full series of shots.

    Args:
        series: List of storyboard payload dicts from build_storyboard_series().
        video_id: Video identifier for output directory grouping.
        output_dir: Root output directory.
        dry_run: If True, write JSON payload files.
        generate_fn: Optional generation callable.

    Returns:
        List of per-shot results (each a list of variant output paths).
    """
    if not series:
        return []

    results: list[list[str | None]] = []
    for payload in series:
        shot_result = generate_shot_storyboard(
            payload,
            video_id=video_id,
            output_dir=output_dir,
            dry_run=dry_run,
            generate_fn=generate_fn,
        )
        results.append(shot_result)

    return results


# ---------------------------------------------------------------------------
# ComfyUI generate_fn factory
# ---------------------------------------------------------------------------


def make_comfyui_generate_fn(
    *,
    comfyui_url: str = "http://localhost:8188",
    timeout: int = 120,
) -> GenerateFn:
    """Factory returning a generate_fn that calls ComfyUI for image generation.

    Args:
        comfyui_url: Base URL for the ComfyUI API.
        timeout: Request timeout in seconds.

    Returns:
        Callable matching the GenerateFn signature.
    """
    import requests

    def _generate(
        positive_prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        output_path: str,
    ) -> str:
        """Call ComfyUI API to generate an image and save to output_path."""
        try:
            # Minimal ComfyUI /prompt API payload
            # This is a placeholder workflow — real ComfyUI workflows
            # will need a proper workflow JSON with node IDs
            api_payload = {
                "prompt": {
                    "positive": positive_prompt,
                    "negative": negative_prompt,
                    "width": width,
                    "height": height,
                },
            }

            response = requests.post(
                f"{comfyui_url}/prompt",
                json=api_payload,
                timeout=timeout,
            )
            response.raise_for_status()

            # For now, save the response content as the output
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)

            return output_path

        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"ComfyUI connection failed at {comfyui_url}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"ComfyUI request timed out after {timeout}s: {exc}"
            ) from exc
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"ComfyUI request failed ({exc.response.status_code}): {exc}"
            ) from exc

    return _generate
