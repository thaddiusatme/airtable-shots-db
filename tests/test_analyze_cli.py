"""Tests for analyzer.analyze CLI entry point."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from analyzer.analyze import main


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
    img = np.full((64, 64, 3), color_bgr, dtype=np.uint8)
    cv2.imwrite(path, img)


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    """Capture directory with a scene change at frame 10 (blue → red)."""
    (tmp_path / "manifest.json").write_text(json.dumps(SAMPLE_MANIFEST))
    for i in range(20):
        fname = f"frame_{i:05d}_t{i:07.3f}s.png"
        color = (255, 0, 0) if i < 10 else (0, 0, 255)
        _make_solid_png(str(tmp_path / fname), color)
    return tmp_path


class TestCLI:
    def test_returns_zero_on_success(self, capture_dir: Path):
        rc = main(["--capture-dir", str(capture_dir), "--skip-vlm"])
        assert rc == 0

    def test_produces_analysis_json(self, capture_dir: Path):
        main(["--capture-dir", str(capture_dir), "--skip-vlm"])
        assert (capture_dir / "analysis.json").exists()

    def test_analysis_json_valid_schema(self, capture_dir: Path):
        main(["--capture-dir", str(capture_dir), "--skip-vlm"])
        with open(capture_dir / "analysis.json") as f:
            analysis = json.load(f)
        assert analysis["videoId"] == "dQw4w9WgXcQ"
        assert "scenes" in analysis
        assert "totalScenes" in analysis
        assert "analysisDate" in analysis

    def test_detects_scene_boundary(self, capture_dir: Path):
        main(["--capture-dir", str(capture_dir), "--skip-vlm", "--threshold", "0.3"])
        with open(capture_dir / "analysis.json") as f:
            analysis = json.load(f)
        assert analysis["totalScenes"] >= 2

    def test_custom_threshold(self, capture_dir: Path):
        # Very high threshold → no boundaries → 1 scene
        main(["--capture-dir", str(capture_dir), "--skip-vlm", "--threshold", "999"])
        with open(capture_dir / "analysis.json") as f:
            analysis = json.load(f)
        assert analysis["totalScenes"] == 1

    def test_returns_error_on_missing_dir(self, tmp_path: Path):
        rc = main(["--capture-dir", str(tmp_path / "nonexistent")])
        assert rc == 1

    def test_returns_error_on_missing_manifest(self, tmp_path: Path):
        rc = main(["--capture-dir", str(tmp_path)])
        assert rc == 1

    def test_descriptions_none_with_skip_vlm(self, capture_dir: Path):
        main(["--capture-dir", str(capture_dir), "--skip-vlm"])
        with open(capture_dir / "analysis.json") as f:
            analysis = json.load(f)
        for scene in analysis["scenes"]:
            assert scene["description"] is None
            assert scene["transition"] is None
