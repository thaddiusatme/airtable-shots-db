"""Tests for publisher.llm_enricher — Ollama LLM adapter."""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.llm_enricher import make_ollama_enrich_fn, verify_ollama_model


SAMPLE_PROMPT = {
    "system_prompt": "You are a professional video production analyst.",
    "user_prompt": "Shot: S01\nVideo ID: abc123\nTime range: 0s – 20s\nFrames provided: 2",
    "frame_references": ["frame_00000_t000.000s.png", "frame_00005_t005.000s.png"],
    "prompt_version": "1.0",
}


# ---------------------------------------------------------------------------
# TestMakeOllamaEnrichFn — factory function
# ---------------------------------------------------------------------------


class TestMakeOllamaEnrichFn:
    def test_returns_callable(self, tmp_path: Path):
        fn = make_ollama_enrich_fn(capture_dir=str(tmp_path))
        assert callable(fn)

    def test_accepts_custom_url(self, tmp_path: Path):
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            ollama_url="http://myhost:9999/api/generate",
        )
        assert callable(fn)

    def test_accepts_custom_model(self, tmp_path: Path):
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            model="llava:13b",
        )
        assert callable(fn)

    def test_accepts_timeout(self, tmp_path: Path):
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            timeout=120,
        )
        assert callable(fn)

    def test_accepts_max_frames(self, tmp_path: Path):
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            max_frames=4,
        )
        assert callable(fn)


# ---------------------------------------------------------------------------
# TestOllamaRequestPayload — verify payload shape sent to Ollama
# ---------------------------------------------------------------------------


class TestOllamaRequestPayload:
    @pytest.fixture
    def capture_dir_with_frames(self, tmp_path: Path) -> Path:
        """Create a capture dir with two fake PNG frames."""
        for name in SAMPLE_PROMPT["frame_references"]:
            (tmp_path / name).write_bytes(b"\x89PNG_FAKE_IMAGE_DATA")
        return tmp_path

    @patch("publisher.llm_enricher.requests.post")
    def test_sends_post_to_ollama_url(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(
            capture_dir=str(capture_dir_with_frames),
            ollama_url="http://localhost:11434/api/generate",
        )
        fn(SAMPLE_PROMPT)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:11434/api/generate"

    @patch("publisher.llm_enricher.requests.post")
    def test_payload_contains_model(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(
            capture_dir=str(capture_dir_with_frames),
            model="llava:7b",
        )
        fn(SAMPLE_PROMPT)
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "llava:7b"

    @patch("publisher.llm_enricher.requests.post")
    def test_payload_contains_combined_prompt(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(capture_dir_with_frames))
        fn(SAMPLE_PROMPT)
        payload = mock_post.call_args[1]["json"]
        assert SAMPLE_PROMPT["system_prompt"] in payload["prompt"]
        assert SAMPLE_PROMPT["user_prompt"] in payload["prompt"]

    @patch("publisher.llm_enricher.requests.post")
    def test_payload_contains_base64_images(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(capture_dir_with_frames))
        fn(SAMPLE_PROMPT)
        payload = mock_post.call_args[1]["json"]
        assert "images" in payload
        assert len(payload["images"]) == 2
        # Each image should be valid base64
        for img_b64 in payload["images"]:
            decoded = base64.b64decode(img_b64)
            assert len(decoded) > 0

    @patch("publisher.llm_enricher.requests.post")
    def test_payload_sets_stream_false(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(capture_dir_with_frames))
        fn(SAMPLE_PROMPT)
        payload = mock_post.call_args[1]["json"]
        assert payload["stream"] is False

    @patch("publisher.llm_enricher.requests.post")
    def test_returns_response_text(self, mock_post, capture_dir_with_frames):
        expected = '{"scene_summary": "A wide shot of the city"}'
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": expected}),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(capture_dir_with_frames))
        result = fn(SAMPLE_PROMPT)
        assert result == expected

    @patch("publisher.llm_enricher.requests.post")
    def test_passes_timeout(self, mock_post, capture_dir_with_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": "{}"}),
        )
        fn = make_ollama_enrich_fn(
            capture_dir=str(capture_dir_with_frames),
            timeout=300,
        )
        fn(SAMPLE_PROMPT)
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["timeout"] == 300


# ---------------------------------------------------------------------------
# TestOllamaMaxFrames — cap frames sent per shot
# ---------------------------------------------------------------------------


class TestOllamaMaxFrames:
    @pytest.fixture
    def capture_dir_many_frames(self, tmp_path: Path) -> Path:
        """Create a capture dir with 6 fake frames."""
        for i in range(6):
            name = f"frame_{i:05d}_t{i:03d}.000s.png"
            (tmp_path / name).write_bytes(b"\x89PNG_FAKE")
        return tmp_path

    @patch("publisher.llm_enricher.requests.post")
    def test_max_frames_caps_images(self, mock_post, capture_dir_many_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": "{}"}),
        )
        prompt = {
            **SAMPLE_PROMPT,
            "frame_references": [
                f"frame_{i:05d}_t{i:03d}.000s.png" for i in range(6)
            ],
        }
        fn = make_ollama_enrich_fn(
            capture_dir=str(capture_dir_many_frames),
            max_frames=3,
        )
        fn(prompt)
        payload = mock_post.call_args[1]["json"]
        assert len(payload["images"]) == 3

    @patch("publisher.llm_enricher.requests.post")
    def test_max_frames_none_sends_all(self, mock_post, capture_dir_many_frames):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": "{}"}),
        )
        prompt = {
            **SAMPLE_PROMPT,
            "frame_references": [
                f"frame_{i:05d}_t{i:03d}.000s.png" for i in range(6)
            ],
        }
        fn = make_ollama_enrich_fn(
            capture_dir=str(capture_dir_many_frames),
            max_frames=None,
        )
        fn(prompt)
        payload = mock_post.call_args[1]["json"]
        assert len(payload["images"]) == 6


# ---------------------------------------------------------------------------
# TestOllamaErrorHandling — connection/timeout errors
# ---------------------------------------------------------------------------


class TestOllamaErrorHandling:
    @patch("publisher.llm_enricher.requests.post")
    def test_connection_error_raises_with_message(self, mock_post, tmp_path):
        import requests

        mock_post.side_effect = requests.ConnectionError("Connection refused")
        fn = make_ollama_enrich_fn(capture_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="[Oo]llama"):
            fn(SAMPLE_PROMPT)

    @patch("publisher.llm_enricher.requests.post")
    def test_timeout_error_raises_with_message(self, mock_post, tmp_path):
        import requests

        mock_post.side_effect = requests.Timeout("Read timed out")
        fn = make_ollama_enrich_fn(capture_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="timed out"):
            fn(SAMPLE_PROMPT)

    @patch("publisher.llm_enricher.requests.post")
    def test_http_error_raises_with_status(self, mock_post, tmp_path):
        mock_post.return_value = MagicMock(
            status_code=500,
            text="Internal Server Error",
            raise_for_status=MagicMock(
                side_effect=Exception("500 Server Error")
            ),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(tmp_path))
        with pytest.raises(RuntimeError):
            fn(SAMPLE_PROMPT)

    @patch("publisher.llm_enricher.requests.post")
    def test_timeout_error_includes_model_name(self, mock_post, tmp_path):
        """Timeout RuntimeError should include the model name for diagnosis."""
        import requests

        mock_post.side_effect = requests.Timeout("Read timed out")
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            model="llava:7b",
        )
        with pytest.raises(RuntimeError, match="llava:7b"):
            fn(SAMPLE_PROMPT)

    @patch("publisher.llm_enricher.requests.post")
    def test_connection_error_includes_model_name(self, mock_post, tmp_path):
        """Connection RuntimeError should include the model name for diagnosis."""
        import requests

        mock_post.side_effect = requests.ConnectionError("Connection refused")
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            model="llava:13b",
        )
        with pytest.raises(RuntimeError, match="llava:13b"):
            fn(SAMPLE_PROMPT)

    @patch("publisher.llm_enricher.requests.post")
    def test_missing_frame_file_skipped(self, mock_post, tmp_path):
        """If a referenced frame file doesn't exist, it should be skipped (not crash)."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"response": '{"scene_summary": "test"}'}),
        )
        fn = make_ollama_enrich_fn(capture_dir=str(tmp_path))
        result = fn(SAMPLE_PROMPT)
        # Should still return the response even with no images found
        assert result == '{"scene_summary": "test"}'
        payload = mock_post.call_args[1]["json"]
        assert payload["images"] == []


# ---------------------------------------------------------------------------
# TestPreflightModelCheck — verify_ollama_model + factory integration
# ---------------------------------------------------------------------------


class TestPreflightModelCheck:
    """Tests for pre-flight model availability verification."""

    @patch("publisher.llm_enricher.requests.get")
    def test_verify_succeeds_when_model_exists(self, mock_get):
        """verify_ollama_model should not raise when model is in /api/tags."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "models": [
                    {"name": "llava:latest"},
                    {"name": "llama3.2-vision:latest"},
                ]
            }),
        )
        # Should not raise
        verify_ollama_model(
            model="llava:latest",
            ollama_url="http://localhost:11434/api/generate",
        )

    @patch("publisher.llm_enricher.requests.get")
    def test_verify_fails_when_model_missing(self, mock_get):
        """verify_ollama_model should raise RuntimeError for missing model."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "models": [
                    {"name": "llava:latest"},
                    {"name": "llama3.2-vision:latest"},
                ]
            }),
        )
        with pytest.raises(RuntimeError, match="llava:7b"):
            verify_ollama_model(
                model="llava:7b",
                ollama_url="http://localhost:11434/api/generate",
            )

    @patch("publisher.llm_enricher.requests.get")
    def test_verify_error_lists_available_models(self, mock_get):
        """Error message should list available models for diagnosis."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "models": [
                    {"name": "llava:latest"},
                    {"name": "llama3.2-vision:latest"},
                ]
            }),
        )
        with pytest.raises(RuntimeError, match="llava:latest") as exc_info:
            verify_ollama_model(
                model="llava:7b",
                ollama_url="http://localhost:11434/api/generate",
            )
        assert "llama3.2-vision:latest" in str(exc_info.value)

    @patch("publisher.llm_enricher.requests.get")
    def test_verify_connection_error_raises(self, mock_get):
        """Connection failure during pre-flight should raise RuntimeError."""
        import requests
        mock_get.side_effect = requests.ConnectionError("Connection refused")
        with pytest.raises(RuntimeError, match="[Cc]onnect"):
            verify_ollama_model(
                model="llava:latest",
                ollama_url="http://localhost:11434/api/generate",
            )

    @patch("publisher.llm_enricher.requests.get")
    def test_factory_with_verify_model_calls_check(self, mock_get, tmp_path):
        """make_ollama_enrich_fn(verify_model=True) should call verify_ollama_model."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "models": [{"name": "llava:latest"}]
            }),
        )
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            model="llava:latest",
            verify_model=True,
        )
        assert callable(fn)
        mock_get.assert_called_once()

    @patch("publisher.llm_enricher.requests.get")
    def test_factory_with_verify_model_fails_fast(self, mock_get, tmp_path):
        """make_ollama_enrich_fn(verify_model=True) should fail fast if model missing."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "models": [{"name": "llava:latest"}]
            }),
        )
        with pytest.raises(RuntimeError, match="nonexistent-model"):
            make_ollama_enrich_fn(
                capture_dir=str(tmp_path),
                model="nonexistent-model",
                verify_model=True,
            )

    def test_factory_without_verify_model_skips_check(self, tmp_path):
        """make_ollama_enrich_fn without verify_model should not call /api/tags."""
        # No mock on requests.get — if it were called, it would hit real network
        # and likely fail. The fact this doesn't raise proves no GET was made.
        fn = make_ollama_enrich_fn(
            capture_dir=str(tmp_path),
            model="nonexistent-model",
        )
        assert callable(fn)
