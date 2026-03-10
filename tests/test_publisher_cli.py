"""Tests for publisher.cli entry point."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.cli import main


SAMPLE_ANALYSIS = {
    "videoId": "KGHoVptow30",
    "scenes": [
        {
            "sceneIndex": 0,
            "startTimestamp": 0.0,
            "endTimestamp": 20.0,
            "firstFrame": "frame_00000_t000.000s.png",
            "lastFrame": "frame_00020_t020.000s.png",
            "description": "A man with headphones",
            "transition": "cut",
        },
    ],
    "totalScenes": 1,
    "analysisDate": "2026-02-23T01:39:22.881311+00:00",
    "analysisModel": "llama3.2-vision:latest",
}


@pytest.fixture
def analysis_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a valid analysis.json."""
    (tmp_path / "analysis.json").write_text(json.dumps(SAMPLE_ANALYSIS))
    return tmp_path


class TestPublisherCLI:
    def test_returns_error_on_missing_dir(self, tmp_path: Path):
        rc = main([
            "--capture-dir", str(tmp_path / "nonexistent"),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
        ])
        assert rc == 1

    def test_returns_error_on_missing_analysis(self, tmp_path: Path):
        rc = main([
            "--capture-dir", str(tmp_path),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
        ])
        assert rc == 1

    def test_returns_error_on_empty_api_key(self, analysis_dir: Path):
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "",
            "--base-id", "appFAKE",
        ])
        assert rc == 1

    def test_returns_error_on_empty_base_id(self, analysis_dir: Path):
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "",
        ])
        assert rc == 1

    def test_dry_run_returns_zero(self, analysis_dir: Path):
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--dry-run",
            "--skip-frames",
        ])
        assert rc == 0

    def test_dry_run_does_not_call_api(self, analysis_dir: Path):
        with patch("publisher.publish.Api") as mock_api_cls:
            main([
                "--capture-dir", str(analysis_dir),
                "--api-key", "patFAKE",
                "--base-id", "appFAKE",
                "--dry-run",
                "--skip-frames",
            ])
            mock_api_cls.assert_not_called()

    @patch("publisher.publish.Api")
    def test_publish_returns_zero_on_success(self, mock_api_cls, analysis_dir: Path):
        """CLI should return 0 when publish succeeds."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            return MagicMock()

        mock_api.table.side_effect = table_router
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recNEW", "fields": {}}
        mock_shots.batch_create.return_value = [{"id": "recS1"}, {"id": "recS2"}]

        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
        ])
        assert rc == 0

    @patch("publisher.publish.Api")
    def test_api_failure_returns_nonzero(self, mock_api_cls, analysis_dir: Path):
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.table.return_value = MagicMock(
            all=MagicMock(side_effect=Exception("Network error"))
        )

        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
        ])
        assert rc == 1

    @patch("publisher.publish.Api")
    def test_skip_frames_flag_accepted(self, mock_api_cls, analysis_dir: Path):
        """CLI should accept --skip-frames flag without error."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            return MagicMock()

        mock_api.table.side_effect = table_router
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recNEW", "fields": {}}
        mock_shots.batch_create.return_value = [{"id": "recS1"}]

        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
        ])
        assert rc == 0

    @patch("publisher.publish.Api")
    def test_max_concurrent_uploads_flag_accepted(self, mock_api_cls, analysis_dir: Path):
        """CLI should accept --max-concurrent-uploads flag."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            return MagicMock()

        mock_api.table.side_effect = table_router
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recNEW", "fields": {}}
        mock_shots.batch_create.return_value = [{"id": "recS1"}]

        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--max-concurrent-uploads", "8",
            "--skip-frames",
        ])
        assert rc == 0

    @patch("publisher.publish.Api")
    def test_frame_sampling_flag_accepted(self, mock_api_cls, analysis_dir: Path):
        """CLI should accept --frame-sampling flag."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            return MagicMock()

        mock_api.table.side_effect = table_router
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recNEW", "fields": {}}
        mock_shots.batch_create.return_value = [{"id": "recS1"}]

        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--frame-sampling", "5",
            "--skip-frames",
        ])
        assert rc == 0


class TestCLIEnrichmentFlags:
    """Tests for --enrich-shots and related enrichment CLI flags."""

    @patch("publisher.publish.Api")
    def test_enrich_shots_passes_true(self, mock_api_cls, analysis_dir: Path):
        """--enrich-shots flag sets enrich_shots=True in publish_to_airtable call."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            return MagicMock()

        mock_api.table.side_effect = table_router
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recNEW", "fields": {}}
        mock_shots.batch_create.return_value = [{"id": "recS1"}]

        with patch("publisher.cli.publish_to_airtable") as mock_publish:
            mock_publish.return_value = {
                "video_record_id": "recNEW",
                "video_id": "KGHoVptow30",
                "shots_created": 1,
                "frames_created": 0,
                "shots_enriched": 0,
                "shots_skipped_enrichment": 0,
            }
            rc = main([
                "--capture-dir", str(analysis_dir),
                "--api-key", "patFAKE",
                "--base-id", "appFAKE",
                "--skip-frames",
                "--enrich-shots",
            ])
            assert rc == 0
            call_kwargs = mock_publish.call_args[1]
            assert call_kwargs["enrich_shots"] is True

    @patch("publisher.cli.publish_to_airtable")
    def test_enrich_model_propagates(self, mock_publish, analysis_dir: Path):
        """--enrich-model value is passed through to publish_to_airtable."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
            "--enrich-model", "llava:7b",
        ])
        assert rc == 0
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["enrich_model"] == "llava:7b"

    @patch("publisher.llm_enricher.requests.post")
    @patch("publisher.cli.publish_to_airtable")
    def test_enrich_fn_is_callable_for_ollama(self, mock_publish, mock_post, analysis_dir: Path):
        """When --enrich-shots with ollama provider, enrich_fn should be a callable."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
            "--enrich-provider", "ollama",
        ])
        assert rc == 0
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["enrich_fn"] is not None
        assert callable(call_kwargs["enrich_fn"])

    @patch("publisher.cli.publish_to_airtable")
    def test_default_provider_is_ollama(self, mock_publish, analysis_dir: Path):
        """Default enrichment provider should be ollama (no --enrich-provider needed)."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
        ])
        assert rc == 0
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["enrich_fn"] is not None

    @patch("publisher.cli.publish_to_airtable")
    def test_no_enrich_shots_means_no_enrich_fn(self, mock_publish, analysis_dir: Path):
        """Without --enrich-shots, enrich_fn should not be passed (or be None)."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
        ])
        assert rc == 0
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs.get("enrich_shots") is not True or call_kwargs.get("enrich_fn") is None

    @patch("publisher.cli.publish_to_airtable")
    def test_ollama_url_propagates(self, mock_publish, analysis_dir: Path):
        """--ollama-url should configure the adapter's target URL."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
            "--ollama-url", "http://myhost:9999/api/generate",
        ])
        assert rc == 0

    @patch("publisher.cli.publish_to_airtable")
    def test_default_enrich_model_is_llava_latest(self, mock_publish, analysis_dir: Path):
        """CLI default --enrich-model should be llava:latest (matches common local install)."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
        ])
        assert rc == 0
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["enrich_model"] == "llava:latest"

    @patch("publisher.cli.publish_to_airtable")
    def test_max_enrich_frames_flag(self, mock_publish, analysis_dir: Path):
        """--max-enrich-frames should be accepted as a CLI flag."""
        mock_publish.return_value = {
            "video_record_id": "recNEW",
            "video_id": "KGHoVptow30",
            "shots_created": 1,
            "frames_created": 0,
            "shots_enriched": 0,
            "shots_skipped_enrichment": 0,
        }
        rc = main([
            "--capture-dir", str(analysis_dir),
            "--api-key", "patFAKE",
            "--base-id", "appFAKE",
            "--skip-frames",
            "--enrich-shots",
            "--max-enrich-frames", "4",
        ])
        assert rc == 0
