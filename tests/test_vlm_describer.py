"""Tests for analyzer.vlm_describer — RED phase (TDD).

Tests cover:
- encode_frame_base64(): Convert a PNG file to base64 string
- describe_frame(): Send a single frame to Ollama and get description
- describe_scenes(): Add descriptions to all scenes in an analysis dict
- Error handling: connection refused, timeout, model not found, bad response
"""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from analyzer.vlm_describer import (
    OllamaError,
    describe_frame,
    describe_scenes,
    encode_frame_base64,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_solid_png(path: str, color_bgr: tuple[int, int, int]) -> None:
    """Create a 64x64 solid-color PNG for testing."""
    img = np.full((64, 64, 3), color_bgr, dtype=np.uint8)
    cv2.imwrite(path, img)


@pytest.fixture
def sample_frame(tmp_path: Path) -> str:
    """Create a single test frame and return its path."""
    path = str(tmp_path / "frame.png")
    _make_solid_png(path, (255, 0, 0))
    return path


@pytest.fixture
def sample_analysis(tmp_path: Path) -> tuple[str, dict]:
    """Create a capture dir with frames and a minimal analysis dict."""
    # Create frame files
    for i in range(4):
        fname = f"frame_{i:05d}_t{i:07.3f}s.png"
        color = (255, 0, 0) if i < 2 else (0, 0, 255)
        _make_solid_png(str(tmp_path / fname), color)

    analysis = {
        "videoId": "test123",
        "scenes": [
            {
                "sceneIndex": 0,
                "startTimestamp": 0.0,
                "endTimestamp": 1.0,
                "firstFrame": "frame_00000_t000.000s.png",
                "lastFrame": "frame_00001_t001.000s.png",
                "description": None,
                "transition": None,
            },
            {
                "sceneIndex": 1,
                "startTimestamp": 2.0,
                "endTimestamp": 3.0,
                "firstFrame": "frame_00002_t002.000s.png",
                "lastFrame": "frame_00003_t003.000s.png",
                "description": None,
                "transition": None,
            },
        ],
        "totalScenes": 2,
        "analysisDate": "2026-02-22T15:30:00Z",
    }
    return str(tmp_path), analysis


# ---------------------------------------------------------------------------
# encode_frame_base64 tests
# ---------------------------------------------------------------------------


class TestEncodeFrameBase64:
    def test_returns_string(self, sample_frame: str):
        result = encode_frame_base64(sample_frame)
        assert isinstance(result, str)

    def test_is_valid_base64(self, sample_frame: str):
        result = encode_frame_base64(sample_frame)
        # Should not raise
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_raises_on_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            encode_frame_base64(str(tmp_path / "nonexistent.png"))


# ---------------------------------------------------------------------------
# describe_frame tests (mocked Ollama API)
# ---------------------------------------------------------------------------


def _mock_ollama_response(description: str) -> MagicMock:
    """Create a mock requests.Response with Ollama-like JSON."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": description}
    return mock_resp


class TestDescribeFrame:
    @patch("analyzer.vlm_describer.requests.post")
    def test_returns_description_string(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("A blue image")
        result = describe_frame(sample_frame)
        assert result == "A blue image"

    @patch("analyzer.vlm_describer.requests.post")
    def test_sends_correct_model(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("desc")
        describe_frame(sample_frame, model="llama3.2-vision:latest")
        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert body["model"] == "llama3.2-vision:latest"

    @patch("analyzer.vlm_describer.requests.post")
    def test_sends_base64_image(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("desc")
        describe_frame(sample_frame)
        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"]
        assert "images" in body
        assert len(body["images"]) == 1
        # Verify it's valid base64
        base64.b64decode(body["images"][0])

    @patch("analyzer.vlm_describer.requests.post")
    def test_sends_stream_false(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("desc")
        describe_frame(sample_frame)
        body = mock_post.call_args[1]["json"]
        assert body["stream"] is False

    @patch("analyzer.vlm_describer.requests.post")
    def test_strips_whitespace_from_response(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("  A blue image  \n")
        result = describe_frame(sample_frame)
        assert result == "A blue image"

    @patch("analyzer.vlm_describer.requests.post")
    def test_raises_ollama_error_on_connection_error(self, mock_post, sample_frame):
        import requests as req
        mock_post.side_effect = req.ConnectionError("Connection refused")
        with pytest.raises(OllamaError, match="Connection refused"):
            describe_frame(sample_frame)

    @patch("analyzer.vlm_describer.requests.post")
    def test_raises_ollama_error_on_timeout(self, mock_post, sample_frame):
        import requests as req
        mock_post.side_effect = req.Timeout("Request timed out")
        with pytest.raises(OllamaError, match="timed out"):
            describe_frame(sample_frame)

    @patch("analyzer.vlm_describer.requests.post")
    def test_raises_ollama_error_on_http_error(self, mock_post, sample_frame):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "model not found"
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_post.return_value = mock_resp
        with pytest.raises(OllamaError):
            describe_frame(sample_frame)

    @patch("analyzer.vlm_describer.requests.post")
    def test_custom_prompt(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("custom desc")
        describe_frame(sample_frame, prompt="Custom prompt here")
        body = mock_post.call_args[1]["json"]
        assert body["prompt"] == "Custom prompt here"

    @patch("analyzer.vlm_describer.requests.post")
    def test_custom_api_url(self, mock_post, sample_frame):
        mock_post.return_value = _mock_ollama_response("desc")
        describe_frame(sample_frame, api_url="http://myhost:1234/api/generate")
        assert mock_post.call_args[0][0] == "http://myhost:1234/api/generate"


# ---------------------------------------------------------------------------
# describe_scenes tests (mocked)
# ---------------------------------------------------------------------------


class TestDescribeScenes:
    @patch("analyzer.vlm_describer.describe_frame")
    def test_fills_descriptions_for_all_scenes(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.return_value = "A test description"
        result = describe_scenes(capture_dir, analysis)
        for scene in result["scenes"]:
            assert scene["description"] is not None
            assert "test description" in scene["description"].lower()

    @patch("analyzer.vlm_describer.describe_frame")
    def test_calls_describe_for_first_frame_of_each_scene(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.return_value = "desc"
        describe_scenes(capture_dir, analysis)
        # Should be called once per scene (using firstFrame)
        assert mock_desc.call_count == 2

    @patch("analyzer.vlm_describer.describe_frame")
    def test_sets_transition_to_cut_by_default(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.return_value = "desc"
        result = describe_scenes(capture_dir, analysis)
        for scene in result["scenes"]:
            assert scene["transition"] == "cut"

    @patch("analyzer.vlm_describer.describe_frame")
    def test_adds_analysis_model_field(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.return_value = "desc"
        result = describe_scenes(capture_dir, analysis)
        assert "analysisModel" in result
        assert "llama3.2-vision" in result["analysisModel"]

    @patch("analyzer.vlm_describer.describe_frame")
    def test_handles_ollama_error_gracefully(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.side_effect = OllamaError("Connection refused")
        # Should not raise — should set description to error message or None
        result = describe_scenes(capture_dir, analysis)
        for scene in result["scenes"]:
            assert scene["description"] is not None
            assert "error" in scene["description"].lower() or "failed" in scene["description"].lower()

    @patch("analyzer.vlm_describer.describe_frame")
    def test_does_not_mutate_original_analysis(self, mock_desc, sample_analysis):
        capture_dir, analysis = sample_analysis
        mock_desc.return_value = "new desc"
        result = describe_scenes(capture_dir, analysis)
        # Result should be the same dict (mutated in place is OK per our API)
        assert result["scenes"][0]["description"] == "new desc"

    @patch("analyzer.vlm_describer.describe_frame")
    def test_empty_scenes_list(self, mock_desc):
        analysis = {"videoId": "x", "scenes": [], "totalScenes": 0}
        result = describe_scenes("/tmp", analysis)
        assert mock_desc.call_count == 0
        assert result["scenes"] == []
