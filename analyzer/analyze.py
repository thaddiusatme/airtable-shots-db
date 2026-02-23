"""CLI entry point for the scene analyzer.

Usage:
    python -m analyzer.analyze --capture-dir ~/Downloads/yt-captures/{videoId}_{datetime}/
    python -m analyzer.analyze --capture-dir ./captures/abc123_2026-02-22 --threshold 0.4
    python -m analyzer.analyze --capture-dir ./captures/abc123_2026-02-22 --skip-vlm
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from analyzer.scene_detector import (
    build_analysis,
    compute_histogram_distance,
    detect_boundaries,
    load_manifest,
    write_analysis,
)
from analyzer.vlm_describer import describe_scenes

logger = logging.getLogger("analyzer")


def configure_logging(verbose: bool = False) -> None:
    """Set up logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def run_pass1(
    capture_dir: str, manifest: dict, threshold: float
) -> tuple[list[int], list[float]]:
    """Run Pass 1: OpenCV histogram-based scene boundary detection.

    Returns:
        Tuple of (boundary frame indices for scene starts, raw distances).
    """
    frames = manifest["frames"]
    num_frames = len(frames)

    if num_frames < 2:
        logger.warning("[Pass 1] Less than 2 frames — no boundaries to detect.")
        return [], []

    logger.info("[Pass 1] Processing %d frames...", num_frames)
    t0 = time.monotonic()

    distances: list[float] = []
    for i in range(num_frames - 1):
        frame_a = f"{capture_dir}/{frames[i]['filename']}"
        frame_b = f"{capture_dir}/{frames[i + 1]['filename']}"
        dist = compute_histogram_distance(frame_a, frame_b)
        distances.append(dist)

        if (i + 1) % 100 == 0 or i == num_frames - 2:
            logger.info("[Pass 1] Processing frame %d/%d...", i + 1, num_frames - 1)

    raw_boundaries = detect_boundaries(distances, threshold=threshold)

    # Convert distance indices to scene-start frame indices:
    # distance[i] is between frame[i] and frame[i+1],
    # so a boundary at distance index i means a new scene starts at frame i+1
    scene_start_indices = [b + 1 for b in raw_boundaries]

    elapsed = time.monotonic() - t0
    logger.info(
        "[Pass 1] Complete in %.1fs — found %d scene boundaries",
        elapsed,
        len(scene_start_indices),
    )

    return scene_start_indices, distances


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the analyzer CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze captured YouTube frames for scene boundaries.",
    )
    parser.add_argument(
        "--capture-dir",
        required=True,
        help="Path to the capture directory containing manifest.json and frame PNGs.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Histogram distance threshold for scene boundary detection (default: 0.5).",
    )
    parser.add_argument(
        "--skip-vlm",
        action="store_true",
        default=False,
        help="Skip Pass 2 (Ollama VLM descriptions). Output analysis with Pass 1 only.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging.",
    )
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    # Load manifest
    try:
        manifest = load_manifest(args.capture_dir)
    except FileNotFoundError as e:
        logger.error("Error: %s", e)
        return 1
    except Exception as e:
        logger.error("Error loading manifest: %s", e)
        return 1

    logger.info(
        'Analyzing "%s" (%d frames, %.1fs interval)',
        manifest.get("videoTitle", manifest["videoId"]),
        len(manifest["frames"]),
        manifest.get("interval", 0),
    )

    # Pass 1: OpenCV scene boundary detection
    scene_starts, distances = run_pass1(
        args.capture_dir, manifest, args.threshold
    )

    # Build analysis structure
    analysis = build_analysis(manifest, scene_starts)

    # Pass 2: Ollama VLM descriptions
    if not args.skip_vlm:
        t1 = time.monotonic()
        analysis = describe_scenes(args.capture_dir, analysis)
        elapsed_vlm = time.monotonic() - t1
        logger.info("[Pass 2] Complete in %.1fs", elapsed_vlm)
    else:
        logger.info("[Pass 2] Skipped (--skip-vlm)")

    # Write output
    write_analysis(args.capture_dir, analysis)
    logger.info(
        "Done — %d scenes written to %s/analysis.json",
        analysis["totalScenes"],
        args.capture_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
