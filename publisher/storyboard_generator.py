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
import tempfile
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import requests

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
GenerateFn = Callable[..., str]


def _download_reference_image(url: str) -> np.ndarray:
    """Download and decode a single reference frame."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    image_array = np.frombuffer(response.content, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to decode reference image from {url}")
    return image


def _resize_with_letterbox(image: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    """Fit an image into a fixed-size cell without cropping."""
    source_height, source_width = image.shape[:2]
    scale = min(target_width / source_width, target_height / source_height)
    resized_width = max(1, int(round(source_width * scale)))
    resized_height = max(1, int(round(source_height * scale)))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

    canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    x_offset = (target_width - resized_width) // 2
    y_offset = (target_height - resized_height) // 2
    canvas[y_offset:y_offset + resized_height, x_offset:x_offset + resized_width] = resized
    return canvas


def _build_reference_montage(
    reference_images: list[dict[str, str]],
    output_path: Path,
) -> Path | None:
    """Create a 16:9 montage from 2-4 reference frames for IP-Adapter input."""
    if not reference_images:
        return None

    images = [_download_reference_image(ref["url"]) for ref in reference_images]
    count = len(images)

    if count == 1:
        canvas = _resize_with_letterbox(images[0], 1024, 576)
    else:
        columns = 2
        rows = 1 if count == 2 else 2
        cell_width = 1024 // columns
        cell_height = 576 // rows
        canvas = np.zeros((576, 1024, 3), dtype=np.uint8)

        for index in range(columns * rows):
            row = index // columns
            column = index % columns
            x0 = column * cell_width
            y0 = row * cell_height

            if index < count:
                cell = _resize_with_letterbox(images[index], cell_width, cell_height)
            else:
                cell = np.zeros((cell_height, cell_width, 3), dtype=np.uint8)

            canvas[y0:y0 + cell_height, x0:x0 + cell_width] = cell

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), canvas):
        raise RuntimeError(f"Failed to write reference montage to {output_path}")

    return output_path


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

    reference_image_path: Path | None = None
    reference_images = payload.get("reference_images") or []
    reference_montage_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        if not dry_run and generate_fn is not None and reference_images:
            reference_montage_dir = tempfile.TemporaryDirectory(
                prefix=f"storyboard_refs_{video_id}_{shot_label}_",
            )
            reference_image_path = _build_reference_montage(
                reference_images,
                Path(reference_montage_dir.name) / f"{shot_label}_reference_montage.png",
            )

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
                    "reference_images": reference_images,
                    "conditioning_image": str(reference_image_path) if reference_image_path else "",
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
                    generate_kwargs = {
                        "positive_prompt": positive_prompt,
                        "negative_prompt": negative_prompt,
                        "width": width,
                        "height": height,
                        "output_path": out_path,
                    }
                    if reference_image_path is not None:
                        generate_kwargs["reference_image_path"] = reference_image_path

                    try:
                        generate_fn(**generate_kwargs)
                    except TypeError as exc:
                        if reference_image_path is not None and "reference_image_path" in str(exc):
                            generate_fn(
                                positive_prompt=positive_prompt,
                                negative_prompt=negative_prompt,
                                width=width,
                                height=height,
                                output_path=out_path,
                            )
                        else:
                            raise
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
    finally:
        if reference_montage_dir is not None:
            reference_montage_dir.cleanup()

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
    workflow_path: str | None = None,
    comfyui_url: str = "http://localhost:8188",
    timeout: int = 300,
) -> GenerateFn:
    """Factory returning a generate_fn that calls ComfyUI for image generation.

    Args:
        workflow_path: Path to ComfyUI workflow JSON (API format).
            Defaults to comfyui/workflows/Storyboarder_api.json.
        comfyui_url: Base URL for the ComfyUI API (default: http://localhost:8188).
        timeout: Generation timeout in seconds (default: 300).

    Returns:
        Callable matching the GenerateFn signature.
    """
    from pathlib import Path
    import sys
    
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))
    
    from comfyui.comfyui_client import ComfyUIClient
    
    if workflow_path is None:
        workflow_path = str(repo_root / "comfyui" / "workflows" / "Storyboarder_api.json")
    
    client = ComfyUIClient(base_url=comfyui_url, timeout=timeout)
    workflow_path_obj = Path(workflow_path)
    
    if not workflow_path_obj.exists():
        raise FileNotFoundError(f"ComfyUI workflow not found: {workflow_path}")

    def _generate(
        positive_prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        output_path: str,
        reference_image_path: Path | None = None,
    ) -> str:
        """Call ComfyUI API to generate an image and save to output_path."""
        import hashlib
        
        seed_input = f"{positive_prompt}:{negative_prompt}:{width}:{height}"
        seed = int(hashlib.sha256(seed_input.encode()).hexdigest()[:16], 16)
        
        output_path_obj = Path(output_path)
        
        client.generate_image(
            workflow_path=workflow_path_obj,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            output_path=output_path_obj,
            width=width,
            height=height,
            reference_image_path=reference_image_path,
        )
        
        return output_path

    return _generate
