"""Tests for publisher.publish — RED phase (TDD).

Tests cover:
- load_analysis(): Parse analysis.json from capture directory
- format_timestamp_hms(): Convert seconds to HH:MM:SS string
- build_video_fields(): Build Airtable Video record fields from analysis
- build_shot_records(): Build list of Airtable Shot record field dicts
- publish_to_airtable(): Orchestrate pyairtable calls (mocked)
- Error handling: missing analysis.json, API failures
- Dry-run mode: preview without writing to Airtable
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.publish import (
    PublisherError,
    build_frame_records,
    build_shot_records,
    build_video_fields,
    format_timestamp_hms,
    load_analysis,
    publish_to_airtable,
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
            "description": "A man sitting in front of a microphone with headphones",
            "transition": "cut",
        },
        {
            "sceneIndex": 1,
            "startTimestamp": 21.0,
            "endTimestamp": 77.0,
            "firstFrame": "frame_00021_t021.000s.png",
            "lastFrame": "frame_00077_t077.000s.png",
            "description": "Close-up of speaker with purple background lighting",
            "transition": "cut",
        },
        {
            "sceneIndex": 2,
            "startTimestamp": 78.0,
            "endTimestamp": 130.0,
            "firstFrame": "frame_00078_t078.000s.png",
            "lastFrame": "frame_00130_t130.000s.png",
            "description": "Screen recording of a web application landing page",
            "transition": "cut",
        },
    ],
    "totalScenes": 3,
    "analysisDate": "2026-02-23T01:39:22.881311+00:00",
    "analysisModel": "llama3.2-vision:latest",
}


@pytest.fixture
def analysis_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a valid analysis.json."""
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(SAMPLE_ANALYSIS))
    return tmp_path


@pytest.fixture
def analysis() -> dict:
    """Return a copy of the sample analysis dict."""
    return json.loads(json.dumps(SAMPLE_ANALYSIS))


# ---------------------------------------------------------------------------
# load_analysis tests
# ---------------------------------------------------------------------------


class TestLoadAnalysis:
    def test_returns_dict_with_expected_keys(self, analysis_dir: Path):
        result = load_analysis(str(analysis_dir))
        assert "videoId" in result
        assert "scenes" in result
        assert "totalScenes" in result
        assert "analysisDate" in result

    def test_video_id_matches(self, analysis_dir: Path):
        result = load_analysis(str(analysis_dir))
        assert result["videoId"] == "KGHoVptow30"

    def test_scenes_list_length(self, analysis_dir: Path):
        result = load_analysis(str(analysis_dir))
        assert len(result["scenes"]) == 3

    def test_scene_has_required_fields(self, analysis_dir: Path):
        result = load_analysis(str(analysis_dir))
        scene = result["scenes"][0]
        assert "sceneIndex" in scene
        assert "startTimestamp" in scene
        assert "endTimestamp" in scene
        assert "firstFrame" in scene
        assert "lastFrame" in scene
        assert "description" in scene

    def test_raises_on_missing_analysis(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_analysis(str(tmp_path))

    def test_raises_on_invalid_json(self, tmp_path: Path):
        (tmp_path / "analysis.json").write_text("not valid json{{{")
        with pytest.raises(json.JSONDecodeError):
            load_analysis(str(tmp_path))

    def test_raises_publisher_error_on_missing_video_id(self, tmp_path: Path):
        bad_analysis = {"scenes": [], "totalScenes": 0}
        (tmp_path / "analysis.json").write_text(json.dumps(bad_analysis))
        with pytest.raises(PublisherError, match="videoId"):
            load_analysis(str(tmp_path))

    def test_raises_publisher_error_on_missing_scenes(self, tmp_path: Path):
        bad_analysis = {"videoId": "abc", "totalScenes": 0}
        (tmp_path / "analysis.json").write_text(json.dumps(bad_analysis))
        with pytest.raises(PublisherError, match="scenes"):
            load_analysis(str(tmp_path))


# ---------------------------------------------------------------------------
# format_timestamp_hms tests
# ---------------------------------------------------------------------------


class TestFormatTimestampHms:
    def test_zero_seconds(self):
        assert format_timestamp_hms(0.0) == "0:00:00"

    def test_seconds_only(self):
        assert format_timestamp_hms(45.0) == "0:00:45"

    def test_minutes_and_seconds(self):
        assert format_timestamp_hms(125.0) == "0:02:05"

    def test_hours_minutes_seconds(self):
        assert format_timestamp_hms(3661.0) == "1:01:01"

    def test_large_timestamp(self):
        assert format_timestamp_hms(7200.0) == "2:00:00"

    def test_fractional_seconds_truncated(self):
        # Fractional seconds should be truncated to whole seconds
        assert format_timestamp_hms(65.7) == "0:01:05"

    def test_returns_string(self):
        assert isinstance(format_timestamp_hms(10.0), str)


# ---------------------------------------------------------------------------
# build_video_fields tests
# ---------------------------------------------------------------------------


class TestBuildVideoFields:
    def test_returns_dict(self, analysis: dict):
        result = build_video_fields(analysis)
        assert isinstance(result, dict)

    def test_contains_video_id(self, analysis: dict):
        result = build_video_fields(analysis)
        assert result["Video ID"] == "KGHoVptow30"

    def test_contains_platform(self, analysis: dict):
        result = build_video_fields(analysis)
        assert result["Platform"] == "YouTube"

    def test_contains_video_url(self, analysis: dict):
        result = build_video_fields(analysis)
        assert result["Video URL"] == "https://www.youtube.com/watch?v=KGHoVptow30"

    def test_contains_thumbnail_url(self, analysis: dict):
        result = build_video_fields(analysis)
        expected = "https://i.ytimg.com/vi/KGHoVptow30/hqdefault.jpg"
        assert result["Thumbnail URL"] == expected


# ---------------------------------------------------------------------------
# build_shot_records tests
# ---------------------------------------------------------------------------


class TestBuildShotRecords:
    def test_returns_list(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert isinstance(result, list)

    def test_one_record_per_scene(self, analysis: dict):
        """Each scene produces 1 Shot record."""
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert len(result) == 3  # 3 scenes × 1 record each

    def test_shot_has_required_fields(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        shot = result[0]
        assert "Shot Label" in shot
        assert "Video" in shot
        assert "Timestamp (sec)" in shot
        assert "Timestamp (hh:mm:ss)" in shot
        assert "AI Description (Local)" in shot
        assert "AI Model" in shot
        assert "AI Status" in shot

    def test_video_linked_record(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        for shot in result:
            assert shot["Video"] == ["recABC123"]

    def test_shot_label_format(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["Shot Label"] == "S01"
        assert result[1]["Shot Label"] == "S02"
        assert result[2]["Shot Label"] == "S03"

    def test_timestamp_uses_scene_start(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["Timestamp (sec)"] == 0.0
        assert result[0]["Timestamp (hh:mm:ss)"] == "0:00:00"
        assert result[1]["Timestamp (sec)"] == 21.0
        assert result[1]["Timestamp (hh:mm:ss)"] == "0:00:21"

    def test_transcript_start_end(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["Transcript Start (sec)"] == 0.0
        assert result[0]["Transcript End (sec)"] == 20.0
        assert result[1]["Transcript Start (sec)"] == 21.0
        assert result[1]["Transcript End (sec)"] == 77.0

    def test_description_propagated(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        expected = "A man sitting in front of a microphone with headphones"
        assert result[0]["AI Description (Local)"] == expected

    def test_ai_status_done_when_description_present(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["AI Status"] == "Done"

    def test_ai_status_queued_when_description_none(self, analysis: dict):
        analysis["scenes"][0]["description"] = None
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["AI Status"] == "Queued"

    def test_ai_model_propagated(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["AI Model"] == "llama3.2-vision:latest"

    def test_capture_method_set(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["Capture Method"] == "Auto Import"

    def test_source_device_set(self, analysis: dict):
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result[0]["Source Device"] == "Desktop"

    def test_empty_scenes_returns_empty_list(self, analysis: dict):
        analysis["scenes"] = []
        result = build_shot_records(analysis, video_record_id="recABC123")
        assert result == []

    def test_no_unknown_fields(self, analysis: dict):
        """Shot records should only contain fields that exist in Airtable."""
        result = build_shot_records(analysis, video_record_id="recABC123")
        valid_fields = {
            "Shot Label", "Video", "Timestamp (sec)", "Timestamp (hh:mm:ss)",
            "Transcript Start (sec)", "Transcript End (sec)",
            "AI Description (Local)", "AI Model", "AI Status",
            "Capture Method", "Source Device",
        }
        for shot in result:
            assert set(shot.keys()) == valid_fields


# ---------------------------------------------------------------------------
# build_frame_records tests
# ---------------------------------------------------------------------------


class TestBuildFrameRecords:
    """Tests for build_frame_records() — generates Frame record dicts."""

    SHOT_RECORDS = [
        {"id": "recSHOT1", "fields": {"Shot Label": "S01"}},
        {"id": "recSHOT2", "fields": {"Shot Label": "S02"}},
        {"id": "recSHOT3", "fields": {"Shot Label": "S03"}},
    ]

    R2_URL_MAP = {
        "frame_00000_t000.000s.png": "https://r2.dev/vid/frame_00000_t000.000s.png",
        "frame_00001_t001.000s.png": "https://r2.dev/vid/frame_00001_t001.000s.png",
        "frame_00002_t002.000s.png": "https://r2.dev/vid/frame_00002_t002.000s.png",
        "frame_00019_t019.000s.png": "https://r2.dev/vid/frame_00019_t019.000s.png",
        "frame_00020_t020.000s.png": "https://r2.dev/vid/frame_00020_t020.000s.png",
        "frame_00021_t021.000s.png": "https://r2.dev/vid/frame_00021_t021.000s.png",
        "frame_00076_t076.000s.png": "https://r2.dev/vid/frame_00076_t076.000s.png",
        "frame_00077_t077.000s.png": "https://r2.dev/vid/frame_00077_t077.000s.png",
        "frame_00078_t078.000s.png": "https://r2.dev/vid/frame_00078_t078.000s.png",
        "frame_00129_t129.000s.png": "https://r2.dev/vid/frame_00129_t129.000s.png",
        "frame_00130_t130.000s.png": "https://r2.dev/vid/frame_00130_t130.000s.png",
    }

    def test_returns_list(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        assert isinstance(result, list)

    def test_frame_count_matches_time_ranges(self, analysis: dict):
        """Each integer second in a shot's range produces one frame record."""
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        # Scene 0: 0-20 = 21 seconds, Scene 1: 21-77 = 57 seconds, Scene 2: 78-130 = 53 seconds
        # Total: 131 frames (0 through 130 inclusive)
        assert len(result) == 131

    def test_frame_key_format(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        first = result[0]
        assert first["Frame Key"] == "KGHoVptow30_t000000"

    def test_frame_key_increments(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        assert result[0]["Frame Key"] == "KGHoVptow30_t000000"
        assert result[1]["Frame Key"] == "KGHoVptow30_t000001"
        assert result[20]["Frame Key"] == "KGHoVptow30_t000020"

    def test_video_linked(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        for frame in result:
            assert frame["Video"] == ["recVID1"]

    def test_shot_linked_to_correct_record(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        # Frame at t=0 belongs to Shot 1 (scene 0)
        assert result[0]["Shot"] == ["recSHOT1"]
        # Frame at t=21 belongs to Shot 2 (scene 1)
        assert result[21]["Shot"] == ["recSHOT2"]
        # Frame at t=78 belongs to Shot 3 (scene 2)
        assert result[78]["Shot"] == ["recSHOT3"]

    def test_timestamp_sec_field(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        assert result[0]["Timestamp (sec)"] == 0
        assert result[5]["Timestamp (sec)"] == 5
        assert result[130]["Timestamp (sec)"] == 130

    def test_timestamp_hms_field(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        assert result[0]["Timestamp (hh:mm:ss)"] == "0:00:00"
        assert result[65]["Timestamp (hh:mm:ss)"] == "0:01:05"
        assert result[130]["Timestamp (hh:mm:ss)"] == "0:02:10"

    def test_frame_image_attachment_when_url_exists(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        # Frame at t=0 has a URL in the map
        assert result[0]["Frame Image"] == [
            {"url": "https://r2.dev/vid/frame_00000_t000.000s.png"}
        ]

    def test_frame_image_empty_when_url_missing(self, analysis: dict):
        """Frames without R2 URLs should have no Frame Image attachment."""
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        # Frame at t=5 is NOT in the R2 url map
        assert "Frame Image" not in result[5] or result[5]["Frame Image"] is None

    def test_source_filename_field(self, analysis: dict):
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )
        # Source filename follows the pattern frame_XXXXX_tSSS.MMMMs.png
        assert result[0]["Source Filename"] == "frame_00000_t000.000s.png"

    def test_empty_scenes_returns_empty(self, analysis: dict):
        analysis["scenes"] = []
        result = build_frame_records(analysis, "recVID1", [], {})
        assert result == []

    def test_single_second_scene(self, analysis: dict):
        """A scene spanning 1 second (start==end) produces 1 frame."""
        analysis["scenes"] = [
            {
                "sceneIndex": 0,
                "startTimestamp": 5.0,
                "endTimestamp": 5.0,
                "firstFrame": "frame_00005_t005.000s.png",
                "lastFrame": "frame_00005_t005.000s.png",
                "description": "Single frame scene",
                "transition": "cut",
            }
        ]
        shot_records = [{"id": "recS1", "fields": {"Shot Label": "S01"}}]
        result = build_frame_records(analysis, "recVID1", shot_records, {})
        assert len(result) == 1
        assert result[0]["Timestamp (sec)"] == 5


# ---------------------------------------------------------------------------
# publish_to_airtable tests (mocked pyairtable)
# ---------------------------------------------------------------------------


class TestPublishToAirtable:
    @patch("publisher.publish.Api")
    def test_looks_up_existing_video(self, mock_api_cls, analysis_dir: Path):
        """Should query Videos table by Video ID before creating."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        # Video already exists
        mock_videos_table.all.return_value = [
            {"id": "recEXIST", "fields": {"Video ID": "KGHoVptow30"}}
        ]
        mock_shots_table.batch_create.return_value = []

        publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        mock_videos_table.all.assert_called_once()
        # Should NOT create a new video since it exists
        mock_videos_table.create.assert_not_called()

    @patch("publisher.publish.Api")
    def test_creates_video_when_not_found(self, mock_api_cls, analysis_dir: Path):
        """Should create Video record if lookup returns empty."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        # No existing video
        mock_videos_table.all.return_value = []
        mock_videos_table.create.return_value = {
            "id": "recNEW",
            "fields": {"Video ID": "KGHoVptow30"},
        }
        mock_shots_table.batch_create.return_value = []

        publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        mock_videos_table.create.assert_called_once()

    @patch("publisher.publish.Api")
    def test_creates_shot_records(self, mock_api_cls, analysis_dir: Path):
        """Should create Shot records linked to the Video record."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        mock_videos_table.all.return_value = [
            {"id": "recVID1", "fields": {"Video ID": "KGHoVptow30"}}
        ]
        mock_shots_table.batch_create.return_value = []

        publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        mock_shots_table.batch_create.assert_called_once()
        shot_records = mock_shots_table.batch_create.call_args[0][0]
        # 3 scenes × 1 record each = 3
        assert len(shot_records) == 3

    @patch("publisher.publish.Api")
    def test_returns_summary_dict(self, mock_api_cls, analysis_dir: Path):
        """Should return a summary of what was published."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        mock_videos_table.all.return_value = [
            {"id": "recVID1", "fields": {"Video ID": "KGHoVptow30"}}
        ]
        mock_shots_table.batch_create.return_value = [
            {"id": f"recSHOT{i}"} for i in range(3)
        ]

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ"
        )

        assert isinstance(result, dict)
        assert result["video_record_id"] == "recVID1"
        assert result["shots_created"] == 3
        assert result["video_id"] == "KGHoVptow30"

    @patch("publisher.publish.Api")
    def test_updates_video_fields_when_existing(self, mock_api_cls, analysis_dir: Path):
        """Should update the existing Video record with analysis fields."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        mock_videos_table.all.return_value = [
            {"id": "recEXIST", "fields": {"Video ID": "KGHoVptow30"}}
        ]
        mock_shots_table.batch_create.return_value = []

        publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        # Should update the existing record with analysis metadata
        mock_videos_table.update.assert_called_once()
        update_args = mock_videos_table.update.call_args
        assert update_args[0][0] == "recEXIST"  # record ID

    @patch("publisher.publish.Api")
    def test_idempotent_clears_existing_shots(self, mock_api_cls, analysis_dir: Path):
        """Re-running publisher should delete existing shots before creating new ones."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_shots_table = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos_table
            if table_name == "Shots":
                return mock_shots_table
            return MagicMock()

        mock_api.table.side_effect = table_router

        # Video record includes reverse-link "Shots" field with existing shot IDs
        mock_videos_table.all.return_value = [
            {
                "id": "recVID1",
                "fields": {
                    "Video ID": "KGHoVptow30",
                    "Shots": ["recOLD1", "recOLD2"],
                },
            }
        ]
        mock_shots_table.batch_create.return_value = []

        result = publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        # Should delete old shots before creating new ones
        mock_shots_table.batch_delete.assert_called_once_with(["recOLD1", "recOLD2"])


# ---------------------------------------------------------------------------
# Frames integration tests (publish_to_airtable + Frames table)
# ---------------------------------------------------------------------------


class TestPublishFrameIntegration:
    """Tests for Frame record creation within publish_to_airtable()."""

    def _setup_mocks(self, mock_api_cls):
        """Helper: set up mock Api with Videos, Shots, and Frames tables."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos = MagicMock()
        mock_shots = MagicMock()
        mock_frames = MagicMock()

        def table_router(base_id, table_name):
            if table_name == "Videos":
                return mock_videos
            if table_name == "Shots":
                return mock_shots
            if table_name == "Frames":
                return mock_frames
            return MagicMock()

        mock_api.table.side_effect = table_router

        # Default: new video, shots created successfully
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recVID1", "fields": {}}
        mock_shots.batch_create.return_value = [
            {"id": "recSHOT1", "fields": {"Shot Label": "S01"}},
            {"id": "recSHOT2", "fields": {"Shot Label": "S02"}},
            {"id": "recSHOT3", "fields": {"Shot Label": "S03"}},
        ]
        mock_frames.batch_create.return_value = [
            {"id": f"recFRAME{i}"} for i in range(131)
        ]

        return mock_api, mock_videos, mock_shots, mock_frames

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_creates_frame_records_with_r2_config(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, analysis_dir: Path,
    ):
        """When r2_config is provided, should create Frame records."""
        _, _, _, mock_frames = self._setup_mocks(mock_api_cls)
        mock_scene_upload.return_value = {}
        mock_upload_all.return_value = {}

        r2_config = MagicMock()
        publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
        )

        mock_frames.batch_create.assert_called_once()

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_skip_frames_skips_frame_creation(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, analysis_dir: Path,
    ):
        """When skip_frames=True, should NOT create Frame records."""
        _, _, _, mock_frames = self._setup_mocks(mock_api_cls)
        mock_scene_upload.return_value = {}

        r2_config = MagicMock()
        publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
            skip_frames=True,
        )

        mock_frames.batch_create.assert_not_called()
        mock_upload_all.assert_not_called()

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.Api")
    def test_no_r2_config_skips_frame_creation(
        self, mock_api_cls, mock_upload_all, analysis_dir: Path
    ):
        """Without r2_config, should NOT create Frame records."""
        _, _, _, mock_frames = self._setup_mocks(mock_api_cls)

        publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
        )

        mock_frames.batch_create.assert_not_called()
        mock_upload_all.assert_not_called()

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_summary_includes_frames_created(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, analysis_dir: Path,
    ):
        """Return dict should include frames_created count."""
        _, _, _, mock_frames = self._setup_mocks(mock_api_cls)
        mock_scene_upload.return_value = {}
        mock_upload_all.return_value = {}
        mock_frames.batch_create.return_value = [
            {"id": f"recF{i}"} for i in range(10)
        ]

        r2_config = MagicMock()
        result = publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
        )

        assert "frames_created" in result
        assert result["frames_created"] == 10

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_idempotent_deletes_existing_frames(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, analysis_dir: Path,
    ):
        """Re-running should delete existing Frames before creating new ones."""
        _, mock_videos, _, mock_frames = self._setup_mocks(mock_api_cls)
        mock_scene_upload.return_value = {}
        mock_upload_all.return_value = {}

        # Existing video with reverse-link Frames field
        mock_videos.all.return_value = [
            {
                "id": "recVID1",
                "fields": {
                    "Video ID": "KGHoVptow30",
                    "Shots": [],
                    "Frames": ["recOLDF1", "recOLDF2", "recOLDF3"],
                },
            }
        ]

        r2_config = MagicMock()
        publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
        )

        mock_frames.batch_delete.assert_called_once_with(
            ["recOLDF1", "recOLDF2", "recOLDF3"]
        )

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_calls_upload_all_frames(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, analysis_dir: Path,
    ):
        """Should call upload_all_frames with correct video_id."""
        self._setup_mocks(mock_api_cls)
        mock_scene_upload.return_value = {}
        mock_upload_all.return_value = {"frame.png": "https://r2.dev/frame.png"}

        r2_config = MagicMock()
        publish_to_airtable(
            str(analysis_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
        )

        mock_upload_all.assert_called_once()
        call_kwargs = mock_upload_all.call_args
        assert call_kwargs[1]["video_id"] == "KGHoVptow30"


# ---------------------------------------------------------------------------
# Dry-run mode tests
# ---------------------------------------------------------------------------


class TestDryRun:
    @patch("publisher.publish.Api")
    def test_dry_run_does_not_create_records(self, mock_api_cls, analysis_dir: Path):
        """Dry-run should NOT call any create/update/delete methods."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ", dry_run=True
        )

        # Api should NOT even be instantiated in dry-run mode
        mock_api_cls.assert_not_called()

    def test_dry_run_returns_preview(self, analysis_dir: Path):
        """Dry-run should return a preview of what would be published."""
        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ", dry_run=True
        )

        assert isinstance(result, dict)
        assert result["dry_run"] is True
        assert result["video_id"] == "KGHoVptow30"
        assert result["shots_to_create"] == 3
        assert "video_fields" in result
        assert "shot_records" in result


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_analysis_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            publish_to_airtable(
                str(tmp_path), api_key="fake_key", base_id="appXYZ"
            )

    @patch("publisher.publish.Api")
    def test_api_error_raises_publisher_error(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Network/API errors should be wrapped in PublisherError."""
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_videos_table = MagicMock()
        mock_api.table.return_value = mock_videos_table

        mock_videos_table.all.side_effect = Exception("401 Unauthorized")

        with pytest.raises(PublisherError, match="Airtable API error"):
            publish_to_airtable(
                str(analysis_dir), api_key="bad_key", base_id="appXYZ"
            )

    def test_empty_api_key_raises_publisher_error(self, analysis_dir: Path):
        with pytest.raises(PublisherError, match="api_key"):
            publish_to_airtable(
                str(analysis_dir), api_key="", base_id="appXYZ"
            )

    def test_empty_base_id_raises_publisher_error(self, analysis_dir: Path):
        with pytest.raises(PublisherError, match="base_id"):
            publish_to_airtable(
                str(analysis_dir), api_key="fake_key", base_id=""
            )
