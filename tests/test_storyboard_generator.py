"""Tests for publisher.storyboard_generator — GH-33 iteration 2.

Thin ComfyUI/SDXL generation runner consuming storyboard payloads from
build_storyboard_payload(). Supports dry-run mode (JSON output) and
real ComfyUI generation with structured output directories.

TDD RED phase: Expected to fail with ImportError (module does not exist).
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from comfyui.comfyui_client import ComfyUIClient
from publisher.storyboard_generator import (
    GENERATOR_VERSION,
    generate_shot_storyboard,
    generate_storyboard_series,
    make_comfyui_generate_fn,
    output_path_for_variant,
)
from publisher.storyboard_handoff import (
    VARIANT_DEFINITIONS,
    build_storyboard_payload,
    build_storyboard_series,
)


# ---------------------------------------------------------------------------
# Fixtures — reuse enriched shot dicts from iteration 1
# ---------------------------------------------------------------------------

CLEAN_SHOT = {
    "Shot Label": "S03",
    "Subject": "person sitting cross-legged in a tent",
    "Setting": "forest clearing at dusk",
    "Shot Type": "Medium",
    "Camera Angle": "Eye-level",
    "Lighting": "Natural-soft",
    "Movement": ["Static"],
    "How It Is Shot": "Tripod-mounted medium shot, shallow depth of field isolating subject from background foliage",
    "AI Description (Local)": "A person sits cross-legged inside a tent with the forest visible behind them.",
    "Shot Function": "B-roll",
    "On-screen Text": "",
    "Frame Progression": "Static composition, subject shifts gaze from camera to horizon",
    "Production Patterns": "Rule of thirds, warm color grading, golden hour tones",
    "Recreation Guidance": "Use a 50mm lens at f/2.8, position subject off-center left, shoot during golden hour",
}

MINIMAL_SHOT = {
    "Shot Label": "S01",
    "Subject": "speaker at desk",
    "Setting": "studio",
}


def _make_payload(shot=None):
    """Build a storyboard payload for testing."""
    return build_storyboard_payload(shot or CLEAN_SHOT)


# ---------------------------------------------------------------------------
# Test: GENERATOR_VERSION constant
# ---------------------------------------------------------------------------


class TestGeneratorVersion:
    """GENERATOR_VERSION tracks the generation runner revision."""

    def test_version_is_string(self):
        assert isinstance(GENERATOR_VERSION, str)

    def test_version_is_nonempty(self):
        assert len(GENERATOR_VERSION) > 0


# ---------------------------------------------------------------------------
# Test: output_path_for_variant — deterministic file naming
# ---------------------------------------------------------------------------


class TestOutputPathForVariant:
    """output_path_for_variant builds deterministic paths for generated images."""

    def test_returns_string_path(self):
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="png",
        )
        assert isinstance(path, str)

    def test_path_includes_video_id_directory(self):
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="png",
        )
        assert "vid123" in path

    def test_path_includes_shot_label_directory(self):
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="png",
        )
        assert "S03" in path

    def test_filename_contains_shot_and_variant(self):
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="png",
        )
        filename = os.path.basename(path)
        assert "S03" in filename
        assert "variant_A" in filename
        assert filename.endswith(".png")

    def test_deterministic_across_calls(self):
        args = dict(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="B",
            ext="png",
        )
        assert output_path_for_variant(**args) == output_path_for_variant(**args)

    def test_json_extension_for_dry_run(self):
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="json",
        )
        assert path.endswith(".json")

    def test_different_variants_produce_different_paths(self):
        base = dict(output_dir="/tmp/out", video_id="vid123", shot_label="S03", ext="png")
        path_a = output_path_for_variant(**base, variant_label="A")
        path_b = output_path_for_variant(**base, variant_label="B")
        assert path_a != path_b

    def test_structured_directory_layout(self):
        """Path should follow: output_dir/video_id/shot_label/filename."""
        path = output_path_for_variant(
            output_dir="/tmp/out",
            video_id="vid123",
            shot_label="S03",
            variant_label="A",
            ext="png",
        )
        parts = path.split(os.sep)
        # Should have video_id and shot_label as directory components
        assert "vid123" in parts
        assert "S03" in parts


# ---------------------------------------------------------------------------
# Test: generate_shot_storyboard — dry-run mode
# ---------------------------------------------------------------------------


class TestGenerateShotStoryboardDryRun:
    """Dry-run mode writes JSON payload files instead of calling ComfyUI."""

    def test_dry_run_returns_list_of_paths(self):
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            assert isinstance(result, list)
            assert len(result) == len(VARIANT_DEFINITIONS)

    def test_dry_run_creates_json_files(self):
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            for p in paths:
                assert os.path.exists(p), f"Expected file at {p}"
                assert p.endswith(".json")

    def test_dry_run_json_is_valid(self):
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            for p in paths:
                with open(p) as f:
                    data = json.load(f)
                assert isinstance(data, dict)

    def test_dry_run_json_contains_variant_prompt(self):
        """Each dry-run JSON should contain the variant's positive_prompt."""
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            with open(paths[0]) as f:
                data = json.load(f)
            assert "positive_prompt" in data
            assert len(data["positive_prompt"]) > 0

    def test_dry_run_json_contains_negative_prompt(self):
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            with open(paths[0]) as f:
                data = json.load(f)
            assert "negative_prompt" in data

    def test_dry_run_json_contains_generation_params(self):
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            with open(paths[0]) as f:
                data = json.load(f)
            assert "generation" in data
            assert data["generation"]["width"] > 0
            assert data["generation"]["height"] > 0

    def test_dry_run_creates_output_directories(self):
        """Should auto-create the video_id/shot_label directory tree."""
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            # Directory structure should exist
            expected_dir = os.path.join(tmpdir, "vid123", "S03")
            assert os.path.isdir(expected_dir)

    def test_dry_run_does_not_call_generate_fn(self):
        """Dry-run should never invoke the generation function."""
        payload = _make_payload()
        mock_fn = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
                generate_fn=mock_fn,
            )
            mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Test: generate_shot_storyboard — with generate_fn
# ---------------------------------------------------------------------------


class TestGenerateShotStoryboardWithGenerateFn:
    """When generate_fn is provided and dry_run=False, it generates images."""

    def _make_generate_fn(self):
        """Create a mock generate_fn that writes a dummy PNG."""
        def fake_generate(
            positive_prompt,
            negative_prompt,
            width,
            height,
            output_path,
            reference_image_path=None,
        ):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(b"FAKE_PNG_DATA")
            return output_path
        return MagicMock(side_effect=fake_generate)

    def test_calls_generate_fn_per_variant(self):
        payload = _make_payload()
        mock_fn = self._make_generate_fn()
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=mock_fn,
            )
            assert mock_fn.call_count == len(VARIANT_DEFINITIONS)

    def test_returns_list_of_output_paths(self):
        payload = _make_payload()
        mock_fn = self._make_generate_fn()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=mock_fn,
            )
            assert isinstance(result, list)
            assert len(result) == len(VARIANT_DEFINITIONS)
            for p in result:
                assert os.path.exists(p)

    def test_generate_fn_receives_correct_prompts(self):
        payload = _make_payload()
        mock_fn = self._make_generate_fn()
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=mock_fn,
            )
            # First call should have variant A's prompt
            first_call = mock_fn.call_args_list[0]
            pos_prompt = first_call.kwargs.get("positive_prompt") or first_call[0][0]
            assert isinstance(pos_prompt, str)
            assert len(pos_prompt) > 0

    def test_generate_fn_receives_dimensions(self):
        payload = _make_payload()
        mock_fn = self._make_generate_fn()
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=mock_fn,
            )
            first_call = mock_fn.call_args_list[0]
            kwargs = first_call.kwargs if first_call.kwargs else {}
            # Should pass width and height from generation params
            if kwargs:
                assert "width" in kwargs
                assert "height" in kwargs

    def test_generate_fn_receives_reference_image_path(self):
        payload = _make_payload()
        payload["reference_images"] = [
            {"url": "https://r2.example.com/captures/vid123/frame_00001.png", "role": "composition"},
            {"url": "https://r2.example.com/captures/vid123/frame_00005.png", "role": "composition"},
        ]
        mock_fn = self._make_generate_fn()

        with tempfile.TemporaryDirectory() as tmpdir:
            montage_path = Path(tmpdir) / "montage.png"
            with patch("publisher.storyboard_generator._build_reference_montage", return_value=montage_path) as mock_montage:
                generate_shot_storyboard(
                    payload,
                    video_id="vid123",
                    output_dir=tmpdir,
                    dry_run=False,
                    generate_fn=mock_fn,
                )

            mock_montage.assert_called_once()
            first_call = mock_fn.call_args_list[0]
            kwargs = first_call.kwargs if first_call.kwargs else {}
            assert kwargs.get("reference_image_path") == montage_path


# ---------------------------------------------------------------------------
# Test: generate_shot_storyboard — error handling
# ---------------------------------------------------------------------------


class TestGenerateShotStoryboardErrorHandling:
    """Generation errors are isolated per-variant and reported gracefully."""

    def test_generate_fn_error_does_not_crash(self):
        """If generate_fn raises for one variant, others should still proceed."""
        payload = _make_payload()
        call_count = 0

        def flaky_generate(positive_prompt, negative_prompt, width, height, output_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("ComfyUI not reachable")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(b"FAKE_PNG_DATA")
            return output_path

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=flaky_generate,
            )
            # Should return paths for successful variants, None for failed
            assert isinstance(result, list)
            assert len(result) == len(VARIANT_DEFINITIONS)
            # First variant failed
            assert result[0] is None
            # Remaining variants succeeded
            assert all(r is not None for r in result[1:])

    def test_no_generate_fn_without_dry_run_returns_empty(self):
        """If dry_run=False but no generate_fn, should return empty/skip."""
        payload = _make_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_shot_storyboard(
                payload,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=False,
                generate_fn=None,
            )
            assert isinstance(result, list)
            # All None since no generator available
            assert all(r is None for r in result)


# ---------------------------------------------------------------------------
# Test: generate_storyboard_series — multi-shot
# ---------------------------------------------------------------------------


class TestGenerateStoryboardSeries:
    """generate_storyboard_series processes a full storyboard series."""

    def test_processes_all_shots_dry_run(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        series = build_storyboard_series(shots)
        with tempfile.TemporaryDirectory() as tmpdir:
            results = generate_storyboard_series(
                series,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            assert isinstance(results, list)
            assert len(results) == 2
            # Each entry is a list of variant paths
            for shot_result in results:
                assert isinstance(shot_result, list)
                assert len(shot_result) == len(VARIANT_DEFINITIONS)

    def test_creates_per_shot_directories(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        series = build_storyboard_series(shots)
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_storyboard_series(
                series,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            assert os.path.isdir(os.path.join(tmpdir, "vid123", "S03"))
            assert os.path.isdir(os.path.join(tmpdir, "vid123", "S01"))

    def test_empty_series_returns_empty(self):
        results = generate_storyboard_series(
            [],
            video_id="vid123",
            output_dir="/tmp/unused",
            dry_run=True,
        )
        assert results == []

    def test_returns_summary_stats(self):
        """Results should include enough info for summary reporting."""
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        series = build_storyboard_series(shots)
        with tempfile.TemporaryDirectory() as tmpdir:
            results = generate_storyboard_series(
                series,
                video_id="vid123",
                output_dir=tmpdir,
                dry_run=True,
            )
            # Flatten and count total outputs
            total = sum(len(r) for r in results)
            assert total == 2 * len(VARIANT_DEFINITIONS)


# ---------------------------------------------------------------------------
# Test: make_comfyui_generate_fn — factory
# ---------------------------------------------------------------------------


class TestMakeComfyuiGenerateFn:
    """make_comfyui_generate_fn returns a callable for ComfyUI generation."""

    def test_returns_callable(self):
        fn = make_comfyui_generate_fn(comfyui_url="http://localhost:8188")
        assert callable(fn)

    def test_connection_error_raises_runtime_error(self):
        """When ComfyUI is unreachable, should raise RuntimeError."""
        fn = make_comfyui_generate_fn(comfyui_url="http://127.0.0.1:19999")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.png")
            with pytest.raises(RuntimeError, match="ComfyUI"):
                fn(
                    positive_prompt="test prompt",
                    negative_prompt="bad stuff",
                    width=1024,
                    height=576,
                    output_path=output_path,
                )


# ---------------------------------------------------------------------------
# Test: ComfyUIClient reference-image injection
# ---------------------------------------------------------------------------


class TestComfyUIClientReferenceInjection:
    """ComfyUI workflow injection should explicitly mark uploaded inputs."""

    def test_reference_image_sets_upload_input(self):
        client = ComfyUIClient()
        workflow = {
            "12": {
                "inputs": {
                    "image": "reference_montage.png",
                },
                "class_type": "LoadImage",
            },
            "4": {"inputs": {"text": ""}},
            "5": {"inputs": {"text": ""}},
            "1": {"inputs": {"seed": 0}},
            "6": {"inputs": {"width": 1024, "height": 576}},
            "8": {"inputs": {"filename_prefix": "ComfyUI"}},
        }

        updated = client.inject_prompt(
            workflow,
            positive_prompt="test",
            negative_prompt="bad",
            seed=123,
            width=1024,
            height=576,
            filename_prefix="test",
            reference_image="montage.png",
        )

        assert updated["12"]["inputs"]["image"] == "montage.png"
        assert updated["12"]["inputs"]["upload"] == "input"


# ---------------------------------------------------------------------------
# Test: ComfyUIClient polling observability (GH-56)
# ---------------------------------------------------------------------------


class TestComfyUIClientPollingObservability:
    """Polling errors should include actionable history state diagnostics."""

    @staticmethod
    def _response_with_json(payload):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_timeout_includes_prompt_id_and_incomplete_history_state(self):
        client = ComfyUIClient(timeout=1)
        prompt_id = "prompt-123"
        incomplete_history = {
            prompt_id: {
                "status": {
                    "completed": False,
                    "status_str": "running",
                },
                "outputs": {},
            }
        }

        with (
            patch("comfyui.comfyui_client.requests.get", return_value=self._response_with_json(incomplete_history)),
            patch("comfyui.comfyui_client.time.sleep", return_value=None),
            patch("comfyui.comfyui_client.time.time", side_effect=[0.0, 0.0, 1.1]),
        ):
            with pytest.raises(TimeoutError) as exc_info:
                client.poll_history(prompt_id, poll_interval=0.01)

        message = str(exc_info.value)
        assert "prompt_id=prompt-123" in message
        assert "history_state=incomplete" in message
        assert "status.completed=False" in message

    def test_timeout_includes_no_history_entry_state(self):
        client = ComfyUIClient(timeout=1)
        prompt_id = "prompt-456"

        with (
            patch("comfyui.comfyui_client.requests.get", return_value=self._response_with_json({})),
            patch("comfyui.comfyui_client.time.sleep", return_value=None),
            patch("comfyui.comfyui_client.time.time", side_effect=[0.0, 0.0, 1.1]),
        ):
            with pytest.raises(TimeoutError) as exc_info:
                client.poll_history(prompt_id, poll_interval=0.01)

        message = str(exc_info.value)
        assert "prompt_id=prompt-456" in message
        assert "history_state=missing" in message

    def test_timeout_includes_malformed_history_shape_state(self):
        client = ComfyUIClient(timeout=1)
        prompt_id = "prompt-789"

        with (
            patch("comfyui.comfyui_client.requests.get", return_value=self._response_with_json(["unexpected"])),
            patch("comfyui.comfyui_client.time.sleep", return_value=None),
            patch("comfyui.comfyui_client.time.time", side_effect=[0.0, 0.0, 1.1]),
        ):
            with pytest.raises(TimeoutError) as exc_info:
                client.poll_history(prompt_id, poll_interval=0.01)

        message = str(exc_info.value)
        assert "prompt_id=prompt-789" in message
        assert "history_state=malformed" in message

    def test_request_failure_includes_prompt_id_and_poll_context(self):
        client = ComfyUIClient(timeout=5)

        with patch(
            "comfyui.comfyui_client.requests.get",
            side_effect=requests.RequestException("connection reset"),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                client.poll_history("prompt-500", poll_interval=0.01)

        message = str(exc_info.value)
        assert "prompt_id=prompt-500" in message
        assert "poll_history" in message


class TestComfyUIClientQueueObservability:
    """Queue submission errors should include actionable /prompt diagnostics."""

    @staticmethod
    def _response_with_http_error(status_code: int, body: str):
        response = MagicMock()
        response.status_code = status_code
        response.text = body
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} Client Error",
            response=response,
        )
        return response

    @staticmethod
    def _response_with_json(payload):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_queue_http_400_includes_status_endpoint_and_body_snippet(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")
        workflow = {"8": {"inputs": {"filename_prefix": "test"}}}
        response = self._response_with_http_error(
            400,
            "invalid prompt: required input 'model' for node 12 is missing",
        )

        with patch("comfyui.comfyui_client.requests.post", return_value=response):
            with pytest.raises(RuntimeError) as exc_info:
                client.queue_prompt(workflow)

        message = str(exc_info.value)
        assert "/prompt" in message
        assert "status=400" in message
        assert "response_snippet=" in message
        assert "required input 'model'" in message

    def test_queue_malformed_response_shape_is_distinct(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")

        with patch(
            "comfyui.comfyui_client.requests.post",
            return_value=self._response_with_json(["unexpected"]),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                client.queue_prompt({"8": {"inputs": {"filename_prefix": "test"}}})

        message = str(exc_info.value)
        assert "malformed" in message
        assert "response_type=list" in message

    def test_queue_missing_prompt_id_is_distinct(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")

        with patch(
            "comfyui.comfyui_client.requests.post",
            return_value=self._response_with_json({"status": "ok"}),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                client.queue_prompt({"8": {"inputs": {"filename_prefix": "test"}}})

        message = str(exc_info.value)
        assert "missing prompt_id" in message
        assert "/prompt" in message

    def test_queue_http_error_response_snippet_is_truncated(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")
        long_body = "x" * 500
        response = self._response_with_http_error(400, long_body)

        with patch("comfyui.comfyui_client.requests.post", return_value=response):
            with pytest.raises(RuntimeError) as exc_info:
                client.queue_prompt({"8": {"inputs": {"filename_prefix": "test"}}})

        message = str(exc_info.value)
        assert "response_snippet=" in message
        assert "<truncated>" in message


class TestComfyUIClientGenerateImageStageContext:
    """generate_image should preserve queue stage context on submit failure."""

    def test_generate_image_queue_failure_mentions_queue_stage(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")
        workflow = {
            "1": {"inputs": {"seed": 0}},
            "4": {"inputs": {"text": ""}},
            "5": {"inputs": {"text": ""}},
            "6": {"inputs": {"width": 1024, "height": 576}},
            "8": {"inputs": {"filename_prefix": "ComfyUI"}},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"

            with (
                patch.object(client, "load_workflow", return_value=workflow),
                patch.object(client, "queue_prompt", side_effect=RuntimeError("ComfyUI prompt queue failed: boom")),
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    client.generate_image(
                        workflow_path=Path("unused.json"),
                        positive_prompt="good",
                        negative_prompt="bad",
                        seed=123,
                        output_path=output_path,
                    )

        message = str(exc_info.value)
        assert "queue_prompt" in message
        assert "prompt queue failed" in message


# ---------------------------------------------------------------------------
# Test: ComfyUIClient IPAdapter dynamic stripping (GH-57)
# ---------------------------------------------------------------------------


def _full_workflow():
    """Return a workflow dict matching Storyboarder_api.json node topology."""
    return {
        "1": {
            "inputs": {
                "seed": 0, "steps": 4, "cfg": 8,
                "sampler_name": "euler", "scheduler": "simple", "denoise": 1,
                "model": ["10", 0],
                "positive": ["4", 0], "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
            "class_type": "KSampler",
        },
        "3": {"inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}, "class_type": "CheckpointLoaderSimple"},
        "4": {"inputs": {"text": "", "clip": ["3", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"text": "", "clip": ["3", 1]}, "class_type": "CLIPTextEncode"},
        "6": {"inputs": {"width": 1024, "height": 576, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "7": {"inputs": {"samples": ["1", 0], "vae": ["3", 2]}, "class_type": "VAEDecode"},
        "8": {"inputs": {"filename_prefix": "ComfyUI", "images": ["7", 0]}, "class_type": "SaveImage"},
        "10": {
            "inputs": {
                "weight": 1, "start_at": 0, "end_at": 1, "weight_type": "standard",
                "model": ["14", 0], "ipadapter": ["14", 1], "image": ["12", 0],
            },
            "class_type": "IPAdapter",
        },
        "12": {"inputs": {"image": "reference_montage.png", "upload": "input"}, "class_type": "LoadImage"},
        "14": {"inputs": {"model": ["3", 0], "preset": "STANDARD (medium strength)"}, "class_type": "IPAdapterUnifiedLoader"},
    }


class TestIPAdapterDynamicStripping:
    """GH-57: When no reference image, strip IPAdapter nodes and rewire KSampler."""

    def test_strips_ipadapter_nodes_when_no_reference(self):
        client = ComfyUIClient()
        workflow = _full_workflow()

        result = client.inject_prompt(
            workflow,
            positive_prompt="test",
            negative_prompt="bad",
            seed=42,
            reference_image=None,
        )

        assert "10" not in result, "IPAdapter node should be removed"
        assert "12" not in result, "LoadImage node should be removed"
        assert "14" not in result, "IPAdapterUnifiedLoader node should be removed"

    def test_rewires_ksampler_to_base_model_when_no_reference(self):
        client = ComfyUIClient()
        workflow = _full_workflow()

        result = client.inject_prompt(
            workflow,
            positive_prompt="test",
            negative_prompt="bad",
            seed=42,
            reference_image=None,
        )

        assert result["1"]["inputs"]["model"] == ["3", 0], (
            "KSampler model input should point to CheckpointLoaderSimple (node 3)"
        )

    def test_preserves_ipadapter_nodes_with_reference(self):
        client = ComfyUIClient()
        workflow = _full_workflow()

        result = client.inject_prompt(
            workflow,
            positive_prompt="test",
            negative_prompt="bad",
            seed=42,
            reference_image="montage.png",
        )

        assert "10" in result, "IPAdapter node should be preserved"
        assert "12" in result, "LoadImage node should be preserved"
        assert "14" in result, "IPAdapterUnifiedLoader node should be preserved"
        assert result["1"]["inputs"]["model"] == ["10", 0], (
            "KSampler model input should still point to IPAdapter (node 10)"
        )

    def test_generate_image_succeeds_without_reference(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:8188")
        workflow = _full_workflow()

        history_entry = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "8": {
                    "images": [{"filename": "test_00001_.png", "subfolder": "", "type": "output"}]
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"
            mock_queue = MagicMock(return_value="prompt-abc")

            with (
                patch.object(client, "load_workflow", return_value=workflow),
                patch.object(client, "queue_prompt", mock_queue),
                patch.object(client, "poll_history", return_value=history_entry),
                patch.object(client, "fetch_image", return_value=b"FAKE_PNG"),
            ):
                result = client.generate_image(
                    workflow_path=Path("unused.json"),
                    positive_prompt="pencil sketch",
                    negative_prompt="bad",
                    seed=42,
                    output_path=output_path,
                    reference_image_path=None,
                )

            assert result == output_path
            assert output_path.read_bytes() == b"FAKE_PNG"
            mock_queue.assert_called_once()
            queued_workflow = mock_queue.call_args[0][0]
            assert "10" not in queued_workflow
            assert "12" not in queued_workflow
            assert "14" not in queued_workflow
            assert queued_workflow["1"]["inputs"]["model"] == ["3", 0]
