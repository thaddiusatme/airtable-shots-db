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
        ])
        assert rc == 0

    def test_dry_run_does_not_call_api(self, analysis_dir: Path):
        with patch("publisher.publish.Api") as mock_api_cls:
            main([
                "--capture-dir", str(analysis_dir),
                "--api-key", "patFAKE",
                "--base-id", "appFAKE",
                "--dry-run",
            ])
            mock_api_cls.assert_not_called()

    @patch("publisher.publish.Api")
    def test_publish_returns_zero_on_success(self, mock_api_cls, analysis_dir: Path):
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
