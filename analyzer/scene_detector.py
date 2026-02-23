"""Scene boundary detection using OpenCV histogram comparison.

Pass 1 of the scene analyzer pipeline:
- Load manifest.json from a capture directory
- Compute HSV histogram chi-squared distance between consecutive frames
- Flag frames where distance exceeds threshold as scene boundaries
- Build analysis.json structure for downstream consumption
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

logger = logging.getLogger(__name__)


def load_manifest(capture_dir: str) -> dict[str, Any]:
    """Load and parse manifest.json from a capture directory.

    Args:
        capture_dir: Path to the capture directory containing manifest.json.

    Returns:
        Parsed manifest dict with videoId, frames, interval, etc.

    Raises:
        FileNotFoundError: If manifest.json does not exist.
        json.JSONDecodeError: If manifest.json is not valid JSON.
    """
    manifest_path = Path(capture_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {capture_dir}")
    with open(manifest_path) as f:
        return json.load(f)


def compute_histogram_distance(frame_a_path: str, frame_b_path: str) -> float:
    """Compute chi-squared histogram distance between two frame images.

    Converts frames to HSV, computes histograms over H and S channels,
    and returns the chi-squared distance.

    Args:
        frame_a_path: Path to the first frame PNG.
        frame_b_path: Path to the second frame PNG.

    Returns:
        Chi-squared distance as a float (0.0 = identical).

    Raises:
        FileNotFoundError: If either frame file does not exist.
    """
    for p in (frame_a_path, frame_b_path):
        if not Path(p).exists():
            raise FileNotFoundError(f"Frame not found: {p}")

    img_a = cv2.imread(frame_a_path)
    img_b = cv2.imread(frame_b_path)

    hsv_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2HSV)
    hsv_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2HSV)

    # Histogram over H (0-180) and S (0-256) channels
    h_bins, s_bins = 50, 60
    hist_size = [h_bins, s_bins]
    h_ranges = [0, 180]
    s_ranges = [0, 256]
    ranges = h_ranges + s_ranges
    channels = [0, 1]

    hist_a = cv2.calcHist([hsv_a], channels, None, hist_size, ranges)
    hist_b = cv2.calcHist([hsv_b], channels, None, hist_size, ranges)

    cv2.normalize(hist_a, hist_a, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hist_b, hist_b, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    distance = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CHISQR)
    return float(distance)


def detect_boundaries(
    distances: list[float], threshold: float = 0.5
) -> list[int]:
    """Detect scene boundaries from a list of frame-to-frame distances.

    Args:
        distances: List of histogram distances between consecutive frames.
            distances[i] is the distance between frame i and frame i+1.
        threshold: Distance above which a boundary is flagged (strict >).

    Returns:
        List of indices where distance exceeds threshold.
    """
    return [i for i, d in enumerate(distances) if d > threshold]


def build_analysis(
    manifest: dict[str, Any],
    boundaries: list[int],
) -> dict[str, Any]:
    """Build analysis.json structure from manifest and detected boundaries.

    Boundaries are frame indices where new scenes start. For example,
    if boundaries=[10], scene 0 is frames 0-9 and scene 1 is frames 10-end.

    Args:
        manifest: Parsed manifest dict.
        boundaries: Sorted list of frame indices where new scenes begin.

    Returns:
        Analysis dict matching the analysis.json schema.
    """
    frames = manifest["frames"]
    if not frames:
        return {
            "videoId": manifest["videoId"],
            "scenes": [],
            "totalScenes": 0,
            "analysisDate": datetime.now(timezone.utc).isoformat(),
        }

    # Build scene start indices: [0] + boundaries (deduplicated, sorted)
    scene_starts = sorted(set([0] + boundaries))

    scenes = []
    for idx, start in enumerate(scene_starts):
        # End is one before the next scene start, or the last frame
        if idx + 1 < len(scene_starts):
            end = scene_starts[idx + 1] - 1
        else:
            end = len(frames) - 1

        scene = {
            "sceneIndex": idx,
            "startTimestamp": frames[start]["timestamp"],
            "endTimestamp": frames[end]["timestamp"],
            "firstFrame": frames[start]["filename"],
            "lastFrame": frames[end]["filename"],
            "description": None,
            "transition": None,
        }
        scenes.append(scene)

    return {
        "videoId": manifest["videoId"],
        "scenes": scenes,
        "totalScenes": len(scenes),
        "analysisDate": datetime.now(timezone.utc).isoformat(),
    }


def write_analysis(capture_dir: str, analysis: dict[str, Any]) -> None:
    """Write analysis dict to analysis.json in the capture directory.

    Args:
        capture_dir: Path to the capture directory.
        analysis: Analysis dict to serialize.
    """
    output_path = Path(capture_dir) / "analysis.json"
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2)
    logger.info("Wrote analysis to %s", output_path)
