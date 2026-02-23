"""Tests for publisher.r2_uploader — TDD RED phase.

Tests cover:
- create_s3_client(): Build boto3 S3 client with R2 endpoint
- upload_frame(): Upload a single PNG to R2, return public URL
- upload_scene_frames(): Upload boundary frames for all scenes
- build_attachment_urls(): Map scene frames to Airtable attachment format
- Error handling: missing files, upload failures
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.r2_uploader import (
    R2Config,
    R2UploadError,
    create_s3_client,
    upload_frame,
    upload_scene_frames,
    build_attachment_urls,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ANALYSIS = {
    "videoId": "KGHoVptow30",
    "scenes": [
        {
            "sceneIndex": 0,
            "startTimestamp": 0.0,
            "endTimestamp": 20.0,
            "firstFrame": "frame_00000_t000.000s.png",
            "lastFrame": "frame_00020_t020.000s.png",
            "description": "A man sitting in front of a microphone",
            "transition": "cut",
        },
        {
            "sceneIndex": 1,
            "startTimestamp": 21.0,
            "endTimestamp": 77.0,
            "firstFrame": "frame_00021_t021.000s.png",
            "lastFrame": "frame_00077_t077.000s.png",
            "description": "Close-up of speaker",
            "transition": "cut",
        },
    ],
    "totalScenes": 2,
    "analysisModel": "llama3.2-vision:latest",
}


@pytest.fixture
def r2_config() -> R2Config:
    """Return a sample R2 configuration."""
    return R2Config(
        account_id="test_account_id",
        access_key_id="test_access_key",
        secret_access_key="test_secret",
        bucket_name="shot-image",
        public_url="https://pub-abc123.r2.dev",
    )


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    """Create a capture directory with fake frame PNGs and analysis.json."""
    (tmp_path / "analysis.json").write_text(json.dumps(SAMPLE_ANALYSIS))
    # Create fake PNG files (1x1 pixel isn't needed for upload tests)
    for scene in SAMPLE_ANALYSIS["scenes"]:
        (tmp_path / scene["firstFrame"]).write_bytes(b"fake-png-data-start")
        (tmp_path / scene["lastFrame"]).write_bytes(b"fake-png-data-end")
    return tmp_path


@pytest.fixture
def analysis() -> dict:
    """Return a copy of the sample analysis dict."""
    return json.loads(json.dumps(SAMPLE_ANALYSIS))


# ---------------------------------------------------------------------------
# R2Config tests
# ---------------------------------------------------------------------------


class TestR2Config:
    def test_endpoint_url(self, r2_config: R2Config):
        expected = "https://test_account_id.r2.cloudflarestorage.com"
        assert r2_config.endpoint_url == expected

    def test_public_url_stored(self, r2_config: R2Config):
        assert r2_config.public_url == "https://pub-abc123.r2.dev"

    def test_bucket_name_stored(self, r2_config: R2Config):
        assert r2_config.bucket_name == "shot-image"


# ---------------------------------------------------------------------------
# create_s3_client tests
# ---------------------------------------------------------------------------


class TestCreateS3Client:
    @patch("publisher.r2_uploader.boto3")
    def test_creates_client_with_r2_endpoint(self, mock_boto3, r2_config: R2Config):
        create_s3_client(r2_config)
        mock_boto3.client.assert_called_once_with(
            "s3",
            endpoint_url="https://test_account_id.r2.cloudflarestorage.com",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret",
            region_name="auto",
        )

    @patch("publisher.r2_uploader.boto3")
    def test_returns_client(self, mock_boto3, r2_config: R2Config):
        result = create_s3_client(r2_config)
        assert result == mock_boto3.client.return_value


# ---------------------------------------------------------------------------
# upload_frame tests
# ---------------------------------------------------------------------------


class TestUploadFrame:
    @patch("publisher.r2_uploader.boto3")
    def test_uploads_file_with_correct_key(
        self, mock_boto3, r2_config: R2Config, capture_dir: Path
    ):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        upload_frame(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            video_id="KGHoVptow30",
            filename="frame_00000_t000.000s.png",
        )

        mock_client.upload_file.assert_called_once()
        call_kwargs = mock_client.upload_file.call_args
        # Object key should be videoId/filename
        assert call_kwargs[1]["Key"] == "KGHoVptow30/frame_00000_t000.000s.png"
        assert call_kwargs[1]["Bucket"] == "shot-image"

    @patch("publisher.r2_uploader.boto3")
    def test_sets_content_type_png(
        self, mock_boto3, r2_config: R2Config, capture_dir: Path
    ):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        upload_frame(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            video_id="KGHoVptow30",
            filename="frame_00000_t000.000s.png",
        )

        call_kwargs = mock_client.upload_file.call_args
        assert call_kwargs[1]["ExtraArgs"]["ContentType"] == "image/png"

    @patch("publisher.r2_uploader.boto3")
    def test_returns_public_url(
        self, mock_boto3, r2_config: R2Config, capture_dir: Path
    ):
        mock_client = MagicMock()

        url = upload_frame(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            video_id="KGHoVptow30",
            filename="frame_00000_t000.000s.png",
        )

        expected = "https://pub-abc123.r2.dev/KGHoVptow30/frame_00000_t000.000s.png"
        assert url == expected

    def test_raises_on_missing_file(self, r2_config: R2Config, tmp_path: Path):
        mock_client = MagicMock()

        with pytest.raises(R2UploadError, match="not found"):
            upload_frame(
                s3_client=mock_client,
                config=r2_config,
                capture_dir=str(tmp_path),
                video_id="KGHoVptow30",
                filename="nonexistent.png",
            )

    @patch("publisher.r2_uploader.boto3")
    def test_wraps_upload_error(
        self, mock_boto3, r2_config: R2Config, capture_dir: Path
    ):
        mock_client = MagicMock()
        mock_client.upload_file.side_effect = Exception("Connection refused")

        with pytest.raises(R2UploadError, match="upload failed"):
            upload_frame(
                s3_client=mock_client,
                config=r2_config,
                capture_dir=str(capture_dir),
                video_id="KGHoVptow30",
                filename="frame_00000_t000.000s.png",
            )


# ---------------------------------------------------------------------------
# upload_scene_frames tests
# ---------------------------------------------------------------------------


class TestUploadSceneFrames:
    @patch("publisher.r2_uploader.upload_frame")
    def test_uploads_all_boundary_frames(
        self, mock_upload, r2_config: R2Config, analysis: dict, capture_dir: Path
    ):
        mock_upload.return_value = "https://pub-abc123.r2.dev/fake.png"
        mock_client = MagicMock()

        upload_scene_frames(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            analysis=analysis,
        )

        # 2 scenes × 2 frames (first + last) = 4 uploads
        assert mock_upload.call_count == 4

    @patch("publisher.r2_uploader.upload_frame")
    def test_returns_url_mapping(
        self, mock_upload, r2_config: R2Config, analysis: dict, capture_dir: Path
    ):
        def fake_upload(s3_client, config, capture_dir, video_id, filename):
            return f"https://pub-abc123.r2.dev/{video_id}/{filename}"

        mock_upload.side_effect = fake_upload
        mock_client = MagicMock()

        result = upload_scene_frames(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            analysis=analysis,
        )

        assert isinstance(result, dict)
        assert "frame_00000_t000.000s.png" in result
        assert "frame_00020_t020.000s.png" in result
        assert "frame_00021_t021.000s.png" in result
        assert "frame_00077_t077.000s.png" in result
        assert result["frame_00000_t000.000s.png"] == (
            "https://pub-abc123.r2.dev/KGHoVptow30/frame_00000_t000.000s.png"
        )

    @patch("publisher.r2_uploader.upload_frame")
    def test_deduplicates_shared_frames(
        self, mock_upload, r2_config: R2Config, analysis: dict, capture_dir: Path
    ):
        """If two scenes share the same boundary frame, upload only once."""
        # Make scene 1's firstFrame the same as scene 0's lastFrame
        analysis["scenes"][1]["firstFrame"] = "frame_00020_t020.000s.png"
        mock_upload.return_value = "https://pub-abc123.r2.dev/fake.png"
        mock_client = MagicMock()

        upload_scene_frames(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            analysis=analysis,
        )

        # 3 unique frames, not 4
        assert mock_upload.call_count == 3

    @patch("publisher.r2_uploader.upload_frame")
    def test_empty_scenes_returns_empty_dict(
        self, mock_upload, r2_config: R2Config, analysis: dict, capture_dir: Path
    ):
        analysis["scenes"] = []
        mock_client = MagicMock()

        result = upload_scene_frames(
            s3_client=mock_client,
            config=r2_config,
            capture_dir=str(capture_dir),
            analysis=analysis,
        )

        assert result == {}
        mock_upload.assert_not_called()


# ---------------------------------------------------------------------------
# build_attachment_urls tests
# ---------------------------------------------------------------------------


class TestBuildAttachmentUrls:
    def test_returns_scene_start_and_end(self, analysis: dict):
        url_map = {
            "frame_00000_t000.000s.png": "https://r2.dev/KGHoVptow30/frame_00000_t000.000s.png",
            "frame_00020_t020.000s.png": "https://r2.dev/KGHoVptow30/frame_00020_t020.000s.png",
            "frame_00021_t021.000s.png": "https://r2.dev/KGHoVptow30/frame_00021_t021.000s.png",
            "frame_00077_t077.000s.png": "https://r2.dev/KGHoVptow30/frame_00077_t077.000s.png",
        }

        result = build_attachment_urls(analysis, url_map)

        assert len(result) == 2
        # Scene 0
        assert result[0]["Scene Start"] == [
            {"url": "https://r2.dev/KGHoVptow30/frame_00000_t000.000s.png"}
        ]
        assert result[0]["Scene End"] == [
            {"url": "https://r2.dev/KGHoVptow30/frame_00020_t020.000s.png"}
        ]
        # Scene 1
        assert result[1]["Scene Start"] == [
            {"url": "https://r2.dev/KGHoVptow30/frame_00021_t021.000s.png"}
        ]
        assert result[1]["Scene End"] == [
            {"url": "https://r2.dev/KGHoVptow30/frame_00077_t077.000s.png"}
        ]

    def test_empty_url_map_omits_attachments(self, analysis: dict):
        result = build_attachment_urls(analysis, {})
        for scene_attachments in result:
            assert "Scene Start" not in scene_attachments
            assert "Scene End" not in scene_attachments

    def test_partial_url_map(self, analysis: dict):
        """If only firstFrame has a URL, only Scene Start is set."""
        url_map = {
            "frame_00000_t000.000s.png": "https://r2.dev/KGHoVptow30/frame_00000_t000.000s.png",
        }

        result = build_attachment_urls(analysis, url_map)

        assert "Scene Start" in result[0]
        assert "Scene End" not in result[0]
        assert "Scene Start" not in result[1]

    def test_empty_scenes_returns_empty(self, analysis: dict):
        analysis["scenes"] = []
        result = build_attachment_urls(analysis, {})
        assert result == []
