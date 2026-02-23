"""Tests for analyzer.scene_detector — RED phase (TDD).

Tests cover:
- load_manifest(): Parse manifest.json and return structured data
- compute_histogram_distance(): Chi-squared distance between two frames
- detect_boundaries(): Threshold-based boundary detection from distances
- build_analysis(): Construct analysis.json structure from manifest + boundaries
- write_analysis(): Write analysis.json to disk
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from analyzer.scene_detector import (
    build_analysis,
    compute_histogram_distance,
    detect_boundaries,
    load_manifest,
    write_analysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MANIFEST = {
    "videoId": "dQw4w9WgXcQ",
    "videoTitle": "Rick Astley - Never Gonna Give You Up",
    "captureDate": "2026-02-22T15:30:00Z",
    "interval": 1.0,
    "frames": [
        {"index": i, "timestamp": float(i), "filename": f"frame_{i:05d}_t{i:07.3f}s.png"}
        for i in range(20)
    ],
}


def _make_solid_png(path: str, color_bgr: tuple[int, int, int]) -> None:
    """Create a 64x64 solid-color PNG for testing."""
    img = np.full((64, 64, 3), color_bgr, dtype=np.uint8)
    cv2.imwrite(path, img)


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    """Create a temporary capture directory with manifest.json and dummy frames."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(SAMPLE_MANIFEST))

    # Create 20 frames: frames 0-9 are blue, frames 10-19 are red (scene change at 10)
    for i in range(20):
        fname = f"frame_{i:05d}_t{i:07.3f}s.png"
        color = (255, 0, 0) if i < 10 else (0, 0, 255)  # BGR: blue then red
        _make_solid_png(str(tmp_path / fname), color)

    return tmp_path


@pytest.fixture
def identical_frames(tmp_path: Path) -> tuple[str, str]:
    """Two identical blue frames."""
    a = str(tmp_path / "a.png")
    b = str(tmp_path / "b.png")
    _make_solid_png(a, (255, 0, 0))
    _make_solid_png(b, (255, 0, 0))
    return a, b


@pytest.fixture
def different_frames(tmp_path: Path) -> tuple[str, str]:
    """Two very different frames (blue vs red)."""
    a = str(tmp_path / "a.png")
    b = str(tmp_path / "b.png")
    _make_solid_png(a, (255, 0, 0))
    _make_solid_png(b, (0, 0, 255))
    return a, b


# ---------------------------------------------------------------------------
# load_manifest tests
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_returns_dict_with_expected_keys(self, capture_dir: Path):
        manifest = load_manifest(str(capture_dir))
        assert "videoId" in manifest
        assert "frames" in manifest
        assert "interval" in manifest

    def test_video_id_matches(self, capture_dir: Path):
        manifest = load_manifest(str(capture_dir))
        assert manifest["videoId"] == "dQw4w9WgXcQ"

    def test_frames_list_length(self, capture_dir: Path):
        manifest = load_manifest(str(capture_dir))
        assert len(manifest["frames"]) == 20

    def test_frame_has_required_fields(self, capture_dir: Path):
        manifest = load_manifest(str(capture_dir))
        frame = manifest["frames"][0]
        assert "index" in frame
        assert "timestamp" in frame
        assert "filename" in frame

    def test_raises_on_missing_manifest(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_manifest(str(tmp_path))

    def test_raises_on_invalid_json(self, tmp_path: Path):
        (tmp_path / "manifest.json").write_text("not json{{{")
        with pytest.raises(json.JSONDecodeError):
            load_manifest(str(tmp_path))


# ---------------------------------------------------------------------------
# compute_histogram_distance tests
# ---------------------------------------------------------------------------


class TestComputeHistogramDistance:
    def test_identical_frames_returns_zero(self, identical_frames):
        a, b = identical_frames
        dist = compute_histogram_distance(a, b)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_different_frames_returns_positive(self, different_frames):
        a, b = different_frames
        dist = compute_histogram_distance(a, b)
        assert dist > 0.1

    def test_returns_float(self, identical_frames):
        a, b = identical_frames
        dist = compute_histogram_distance(a, b)
        assert isinstance(dist, float)

    def test_symmetric(self, different_frames):
        a, b = different_frames
        assert compute_histogram_distance(a, b) == pytest.approx(
            compute_histogram_distance(b, a), abs=0.001
        )

    def test_raises_on_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            compute_histogram_distance(
                str(tmp_path / "nope.png"), str(tmp_path / "nope2.png")
            )


# ---------------------------------------------------------------------------
# detect_boundaries tests
# ---------------------------------------------------------------------------


class TestDetectBoundaries:
    def test_no_boundaries_below_threshold(self):
        distances = [0.01, 0.02, 0.01, 0.03, 0.02]
        result = detect_boundaries(distances, threshold=0.5)
        assert result == []

    def test_single_boundary(self):
        distances = [0.01, 0.01, 0.01, 0.9, 0.01, 0.01]
        result = detect_boundaries(distances, threshold=0.5)
        # Index 3 means the boundary is between frame 3 and frame 4
        assert result == [3]

    def test_multiple_boundaries(self):
        distances = [0.01, 0.8, 0.01, 0.01, 0.7, 0.02]
        result = detect_boundaries(distances, threshold=0.5)
        assert result == [1, 4]

    def test_all_above_threshold(self):
        distances = [0.9, 0.8, 0.7, 0.6]
        result = detect_boundaries(distances, threshold=0.5)
        assert result == [0, 1, 2, 3]

    def test_empty_distances(self):
        result = detect_boundaries([], threshold=0.5)
        assert result == []

    def test_threshold_at_exact_value_excluded(self):
        # Distance exactly at threshold should NOT be a boundary (strict >)
        distances = [0.5, 0.51]
        result = detect_boundaries(distances, threshold=0.5)
        assert result == [1]


# ---------------------------------------------------------------------------
# build_analysis tests
# ---------------------------------------------------------------------------


class TestBuildAnalysis:
    def test_output_has_required_keys(self):
        manifest = SAMPLE_MANIFEST.copy()
        boundaries = [10]  # Scene change at frame 10
        analysis = build_analysis(manifest, boundaries)
        assert "videoId" in analysis
        assert "scenes" in analysis
        assert "totalScenes" in analysis
        assert "analysisDate" in analysis

    def test_video_id_propagated(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [10])
        assert analysis["videoId"] == "dQw4w9WgXcQ"

    def test_single_boundary_produces_two_scenes(self):
        # Boundary at index 10 → scene 0 (frames 0-9), scene 1 (frames 10-19)
        analysis = build_analysis(SAMPLE_MANIFEST, [10])
        assert analysis["totalScenes"] == 2
        assert len(analysis["scenes"]) == 2

    def test_no_boundaries_produces_one_scene(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [])
        assert analysis["totalScenes"] == 1
        assert len(analysis["scenes"]) == 1

    def test_scene_timestamps_correct(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [10])
        scene0 = analysis["scenes"][0]
        scene1 = analysis["scenes"][1]

        assert scene0["startTimestamp"] == 0.0
        assert scene0["endTimestamp"] == 9.0
        assert scene0["firstFrame"] == "frame_00000_t000.000s.png"
        assert scene0["lastFrame"] == "frame_00009_t009.000s.png"

        assert scene1["startTimestamp"] == 10.0
        assert scene1["endTimestamp"] == 19.0
        assert scene1["firstFrame"] == "frame_00010_t010.000s.png"
        assert scene1["lastFrame"] == "frame_00019_t019.000s.png"

    def test_scene_index_sequential(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [5, 10, 15])
        for i, scene in enumerate(analysis["scenes"]):
            assert scene["sceneIndex"] == i

    def test_multiple_boundaries(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [5, 10, 15])
        assert analysis["totalScenes"] == 4

    def test_description_is_none_without_vlm(self):
        analysis = build_analysis(SAMPLE_MANIFEST, [10])
        for scene in analysis["scenes"]:
            assert scene["description"] is None
            assert scene["transition"] is None


# ---------------------------------------------------------------------------
# write_analysis tests
# ---------------------------------------------------------------------------


class TestWriteAnalysis:
    def test_writes_json_file(self, tmp_path: Path):
        analysis = {"videoId": "test", "scenes": [], "totalScenes": 0}
        write_analysis(str(tmp_path), analysis)
        output_path = tmp_path / "analysis.json"
        assert output_path.exists()

    def test_written_json_is_valid(self, tmp_path: Path):
        analysis = {"videoId": "test", "scenes": [], "totalScenes": 0}
        write_analysis(str(tmp_path), analysis)
        with open(tmp_path / "analysis.json") as f:
            loaded = json.load(f)
        assert loaded["videoId"] == "test"

    def test_overwrites_existing(self, tmp_path: Path):
        analysis1 = {"videoId": "v1", "scenes": [], "totalScenes": 0}
        analysis2 = {"videoId": "v2", "scenes": [], "totalScenes": 0}
        write_analysis(str(tmp_path), analysis1)
        write_analysis(str(tmp_path), analysis2)
        with open(tmp_path / "analysis.json") as f:
            loaded = json.load(f)
        assert loaded["videoId"] == "v2"


# ---------------------------------------------------------------------------
# Integration: end-to-end with real frames
# ---------------------------------------------------------------------------


class TestIntegrationEndToEnd:
    def test_full_pipeline_with_scene_change(self, capture_dir: Path):
        """Load manifest, compute distances, detect boundaries, build analysis."""
        manifest = load_manifest(str(capture_dir))

        # Compute distances for consecutive frames
        distances = []
        for i in range(len(manifest["frames"]) - 1):
            frame_a = str(capture_dir / manifest["frames"][i]["filename"])
            frame_b = str(capture_dir / manifest["frames"][i + 1]["filename"])
            dist = compute_histogram_distance(frame_a, frame_b)
            distances.append(dist)

        # Detect boundaries
        boundaries = detect_boundaries(distances, threshold=0.3)

        # Should detect the blue→red transition at frame 10
        assert len(boundaries) >= 1
        # The boundary index in distances corresponds to the transition
        # between frame[idx] and frame[idx+1], so boundary frame index = idx + 1
        boundary_frame_indices = [b + 1 for b in boundaries]
        assert 10 in boundary_frame_indices

        # Build analysis
        # For build_analysis, boundaries represent the start of new scenes
        scene_start_indices = [b + 1 for b in boundaries]
        analysis = build_analysis(manifest, scene_start_indices)
        assert analysis["totalScenes"] >= 2

        # Write analysis
        write_analysis(str(capture_dir), analysis)
        assert (capture_dir / "analysis.json").exists()

        with open(capture_dir / "analysis.json") as f:
            saved = json.load(f)
        assert saved["videoId"] == "dQw4w9WgXcQ"
        assert saved["totalScenes"] >= 2
