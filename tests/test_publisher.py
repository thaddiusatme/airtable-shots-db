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
    is_shot_enriched,
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


# Sampled capture data — reproduces GH-22 scenario (5s interval, index-based filenames)
SAMPLED_ANALYSIS_5S = {
    "videoId": "Lwh_e2gJCN0",
    "scenes": [
        {
            "sceneIndex": 0,
            "startTimestamp": 0,
            "endTimestamp": 10,
            "firstFrame": "frame_00000_t000.000s.png",
            "lastFrame": "frame_00002_t010.000s.png",
            "description": None,
            "transition": None,
        },
        {
            "sceneIndex": 1,
            "startTimestamp": 15,
            "endTimestamp": 25,
            "firstFrame": "frame_00003_t015.000s.png",
            "lastFrame": "frame_00005_t025.000s.png",
            "description": None,
            "transition": None,
        },
    ],
    "totalScenes": 2,
    "analysisDate": "2026-03-08T15:35:55+00:00",
}

SAMPLED_MANIFEST_5S = {
    "videoId": "Lwh_e2gJCN0",
    "videoTitle": "Test Sampled Video",
    "captureDate": "2026-02-24T22:55:22.294Z",
    "options": {"interval": 5, "maxFrames": 100},
    "frames": [
        {"index": 0, "timestamp": 0, "filename": "frame_00000_t000.000s.png"},
        {"index": 1, "timestamp": 5, "filename": "frame_00001_t005.000s.png"},
        {"index": 2, "timestamp": 10, "filename": "frame_00002_t010.000s.png"},
        {"index": 3, "timestamp": 15, "filename": "frame_00003_t015.000s.png"},
        {"index": 4, "timestamp": 20, "filename": "frame_00004_t020.000s.png"},
        {"index": 5, "timestamp": 25, "filename": "frame_00005_t025.000s.png"},
    ],
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


@pytest.fixture
def sampled_capture_dir(tmp_path: Path) -> Path:
    """Create a capture directory simulating Chrome extension 5s-interval output.

    Reproduces the GH-22 scenario: index-based filenames with 5s sampling.
    """
    (tmp_path / "analysis.json").write_text(json.dumps(SAMPLED_ANALYSIS_5S))
    (tmp_path / "manifest.json").write_text(json.dumps(SAMPLED_MANIFEST_5S))
    for frame in SAMPLED_MANIFEST_5S["frames"]:
        (tmp_path / frame["filename"]).write_bytes(b"\x89PNG dummy")
    return tmp_path


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
        """Scene lasting exactly 1 second should produce 1 frame."""
        analysis["scenes"] = [
            {
                "sceneIndex": 0,
                "startTimestamp": 5.0,
                "endTimestamp": 5.0,
                "firstFrame": "frame_00005_t005.000s.png",
                "lastFrame": "frame_00005_t005.000s.png",
            }
        ]

        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS[:1], self.R2_URL_MAP
        )

        assert len(result) == 1
        assert result[0]["Frame Key"] == "KGHoVptow30_t000005"

    def test_frame_sampling_every_2_seconds(self, analysis: dict):
        """With sample_rate=2, should create frames for even seconds only."""
        result = build_frame_records(
            analysis,
            "recVID1",
            self.SHOT_RECORDS,
            self.R2_URL_MAP,
            sample_rate=2,
        )

        # Scene 0: 0-20s → 0,2,4,6,8,10,12,14,16,18,20 = 11 frames
        # Scene 1: 21-100s → 21,23,25,...,99 = 40 frames
        # Scene 2: 100-130s → 100,102,104,...,130 = 16 frames
        # Total: 11 + 40 + 16 = 67 frames
        assert len(result) == 67

        # Check first few timestamps follow sample_rate=2
        assert result[0]["Timestamp (sec)"] == 0
        assert result[1]["Timestamp (sec)"] == 2
        assert result[2]["Timestamp (sec)"] == 4

    def test_frame_sampling_every_5_seconds(self, analysis: dict):
        """With sample_rate=5, should create frames every 5 seconds."""
        result = build_frame_records(
            analysis,
            "recVID1",
            self.SHOT_RECORDS,
            self.R2_URL_MAP,
            sample_rate=5,
        )

        # Scene 0: 0-20s → 0,5,10,15,20 = 5 frames
        # Scene 1: 21-100s → 21,26,31,...,96 = 16 frames
        # Scene 2: 100-130s → 100,105,110,115,120,125,130 = 7 frames
        # Total: 5 + 16 + 7 = 28 frames
        assert len(result) == 28

    def test_default_sample_rate_is_1(self, analysis: dict):
        """Without sample_rate param, should default to every second."""
        result = build_frame_records(
            analysis, "recVID1", self.SHOT_RECORDS, self.R2_URL_MAP
        )

        # Default should be same as sample_rate=1
        assert len(result) == 131


# ---------------------------------------------------------------------------
# GH-22 regression: sampled capture frame contract
# ---------------------------------------------------------------------------


class TestSampledCaptureFrameContract:
    """GH-22 regression: publisher must handle sampled capture output correctly.

    Chrome extension captures frames at configurable intervals (default 5s).
    Capture output uses index-based filenames:
        frame_00000_t000.000s.png  (index=0, t=0s)
        frame_00001_t005.000s.png  (index=1, t=5s)
        frame_00002_t010.000s.png  (index=2, t=10s)

    Publisher must use actual captured filenames from manifest.json,
    not synthesize timestamp-based filenames like frame_00005_t005.000s.png.
    """

    SHOT_RECORDS = [
        {"id": "recSHOT1", "fields": {"Shot Label": "S01"}},
        {"id": "recSHOT2", "fields": {"Shot Label": "S02"}},
    ]

    MANIFEST_FRAME_MAP = {
        int(f["timestamp"]): f["filename"]
        for f in SAMPLED_MANIFEST_5S["frames"]
    }

    def test_source_filename_uses_actual_capture_name(self):
        """Frame at t=5s should use actual capture filename (index-based),
        not synthesized timestamp-based name."""
        result = build_frame_records(
            SAMPLED_ANALYSIS_5S, "recVID1", self.SHOT_RECORDS, {},
            sample_rate=5,
            manifest_frame_map=self.MANIFEST_FRAME_MAP,
        )

        frame_at_5 = [f for f in result if f["Timestamp (sec)"] == 5][0]
        # Actual capture file at t=5 is frame_00001 (index 1), not frame_00005
        assert frame_at_5["Source Filename"] == "frame_00001_t005.000s.png"

    def test_all_frame_filenames_exist_on_disk(self, sampled_capture_dir: Path):
        """Every Source Filename in frame records should correspond to
        an actual file in the capture directory."""
        result = build_frame_records(
            SAMPLED_ANALYSIS_5S, "recVID1", self.SHOT_RECORDS, {},
            sample_rate=5,
            manifest_frame_map=self.MANIFEST_FRAME_MAP,
        )

        for frame in result:
            filename = frame["Source Filename"]
            assert (sampled_capture_dir / filename).exists(), \
                f"Frame record references non-existent file: {filename}"

    @patch("publisher.publish.upload_all_frames")
    @patch("publisher.publish.upload_scene_frames")
    @patch("publisher.publish.create_s3_client")
    @patch("publisher.publish.Api")
    def test_publish_passes_actual_filenames_to_upload(
        self, mock_api_cls, mock_create_s3, mock_scene_upload,
        mock_upload_all, sampled_capture_dir: Path,
    ):
        """publish_to_airtable should pass manifest-derived filenames
        to upload_all_frames, not synthesized ones."""
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
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recVID1", "fields": {}}
        mock_shots.batch_create.return_value = [
            {"id": "recSHOT1", "fields": {}},
            {"id": "recSHOT2", "fields": {}},
        ]
        mock_frames.batch_create.return_value = []
        mock_scene_upload.return_value = {}
        mock_upload_all.return_value = {}

        r2_config = MagicMock()
        publish_to_airtable(
            str(sampled_capture_dir),
            api_key="fake_key",
            base_id="appXYZ",
            r2_config=r2_config,
        )

        mock_upload_all.assert_called_once()
        call_kwargs = mock_upload_all.call_args
        frame_filenames = call_kwargs[1]["frame_filenames"]

        # Should contain actual manifest filenames (index-based naming)
        assert "frame_00001_t005.000s.png" in frame_filenames
        # Should NOT contain synthesized timestamp-based filenames
        assert "frame_00005_t005.000s.png" not in frame_filenames


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


# ---------------------------------------------------------------------------
# Enrichment integration tests (publish_to_airtable + enrich_shots)
# ---------------------------------------------------------------------------


class TestEnrichmentIntegration:
    """Tests for LLM enrichment within publish_to_airtable(enrich_shots=True)."""

    VALID_LLM_RESPONSE = json.dumps({
        "scene_summary": "Speaker at desk",
        "how_it_is_shot": "Medium shot, static",
        "shot_type": "Medium Shot",
        "camera_angle": "Eye Level",
        "movement": "Static",
        "lighting": "Studio",
        "setting": "Home studio",
        "subject": "Speaker",
        "on_screen_text": "None",
        "shot_function": "Introduction",
        "frame_progression": "Minimal movement",
        "production_patterns": "Standard talking head",
        "recreation_guidance": "Use medium shot at eye level",
    })

    def _setup_mocks(self, mock_api_cls):
        """Helper: set up mock Api with Videos and Shots tables."""
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

        # Default: new video, 3 shots created
        mock_videos.all.return_value = []
        mock_videos.create.return_value = {"id": "recVID1", "fields": {}}
        mock_shots.batch_create.return_value = [
            {"id": "recSHOT1", "fields": {"Shot Label": "S01"}},
            {"id": "recSHOT2", "fields": {"Shot Label": "S02"}},
            {"id": "recSHOT3", "fields": {"Shot Label": "S03"}},
        ]

        return mock_api, mock_videos, mock_shots

    # -- Backward compatibility --

    @patch("publisher.publish.Api")
    def test_default_enrich_shots_false_no_updates(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Default enrich_shots=False should not update shot records after creation."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)

        publish_to_airtable(str(analysis_dir), api_key="fake_key", base_id="appXYZ")

        mock_shots.update.assert_not_called()

    # -- Enrichment flow --

    @patch("publisher.publish.Api")
    def test_enrich_shots_updates_each_shot(
        self, mock_api_cls, analysis_dir: Path
    ):
        """With enrich_shots=True, each shot record should be updated."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert mock_shots.update.call_count == 3

    @patch("publisher.publish.Api")
    def test_enrich_fn_called_per_shot(
        self, mock_api_cls, analysis_dir: Path
    ):
        """enrich_fn should be called once per shot."""
        self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert enrich_fn.call_count == 3

    @patch("publisher.publish.Api")
    def test_enrichment_fields_written_to_shot(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Updated shot should include parsed LLM fields."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        # Check first update call
        first_update = mock_shots.update.call_args_list[0]
        record_id, fields = first_update[0]
        assert record_id == "recSHOT1"
        assert fields["AI Description (Local)"] == "Speaker at desk"
        assert fields["Shot Type"] == "Medium Shot"

    @patch("publisher.publish.Api")
    def test_enrichment_includes_ai_metadata(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Updated shot should include AI Model, Prompt Version, Updated At."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
            enrich_model="gpt-4o",
        )

        first_update = mock_shots.update.call_args_list[0]
        _, fields = first_update[0]
        assert "AI Prompt Version" in fields
        assert "AI Updated At" in fields
        assert fields["AI Model"] == "gpt-4o"

    # -- Error isolation --

    @patch("publisher.publish.Api")
    def test_enrichment_failure_isolated_per_shot(
        self, mock_api_cls, analysis_dir: Path
    ):
        """LLM failure on one shot should not prevent others from being enriched."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(side_effect=[
            self.VALID_LLM_RESPONSE,
            Exception("LLM timeout"),
            self.VALID_LLM_RESPONSE,
        ])

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        # All 3 shots should still be updated (2 success + 1 error)
        assert mock_shots.update.call_count == 3

    @patch("publisher.publish.Api")
    def test_enrichment_failure_stores_ai_error(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Failed enrichment should store error in AI Error field."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(side_effect=Exception("LLM timeout"))

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        first_update = mock_shots.update.call_args_list[0]
        _, fields = first_update[0]
        assert "AI Error" in fields
        assert "LLM timeout" in fields["AI Error"]

    # -- Edge cases --

    @patch("publisher.publish.Api")
    def test_enrich_shots_true_without_enrich_fn_skips(
        self, mock_api_cls, analysis_dir: Path
    ):
        """enrich_shots=True without enrich_fn should skip enrichment gracefully."""
        _, _, mock_shots = self._setup_mocks(mock_api_cls)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True,
        )

        mock_shots.update.assert_not_called()

    # -- Summary --

    @patch("publisher.publish.Api")
    def test_summary_includes_shots_enriched(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Return dict should include shots_enriched count."""
        self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert "shots_enriched" in result
        assert result["shots_enriched"] == 3

    @patch("publisher.publish.Api")
    def test_summary_counts_only_successful_enrichments(
        self, mock_api_cls, analysis_dir: Path
    ):
        """shots_enriched should only count successful enrichments."""
        self._setup_mocks(mock_api_cls)
        enrich_fn = MagicMock(side_effect=[
            self.VALID_LLM_RESPONSE,
            Exception("LLM timeout"),
            self.VALID_LLM_RESPONSE,
        ])

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert result["shots_enriched"] == 2


# ---------------------------------------------------------------------------
# Enrichment idempotency tests (skip already-enriched shots on re-run)
# ---------------------------------------------------------------------------


class TestEnrichmentIdempotency:
    """Tests for idempotent enrichment: skip already-enriched shots on re-run.

    When publish_to_airtable re-runs on a video whose shots were already
    enriched, it should:
      - Read old shot records before deleting them
      - Detect which shots are already enriched (AI Prompt Version present)
      - Skip the LLM call for those shots
      - Copy old enrichment fields to the new shot records
      - Still enrich shots that were not previously enriched
      - Treat AI Error-only shots (no AI Prompt Version) as eligible for retry
    """

    VALID_LLM_RESPONSE = json.dumps({
        "scene_summary": "Speaker at desk",
        "how_it_is_shot": "Medium shot, static",
        "shot_type": "Medium Shot",
        "camera_angle": "Eye Level",
        "movement": "Static",
        "lighting": "Studio",
        "setting": "Home studio",
        "subject": "Speaker",
        "on_screen_text": "None",
        "shot_function": "Introduction",
        "frame_progression": "Minimal movement",
        "production_patterns": "Standard talking head",
        "recreation_guidance": "Use medium shot at eye level",
    })

    # Fields that signal a shot was successfully enriched
    ENRICHED_FIELDS = {
        "AI Prompt Version": "1.0",
        "AI Updated At": "2026-03-01T00:00:00+00:00",
        "AI Model": "gpt-4o",
        "Shot Type": "Medium Shot",
        "Camera Angle": "Eye Level",
        "How It Is Shot": "Medium shot, static camera",
        "AI JSON": '{"shot_type": "Medium Shot"}',
    }

    def _setup_mocks_with_existing_enriched_shots(
        self, mock_api_cls, old_shot_fields_list
    ):
        """Set up mock Api with an existing video and old shot records.

        Args:
            mock_api_cls: Patched Api class.
            old_shot_fields_list: List of field dicts for old shot records
                (one per shot, matched by index to analysis scenes).

        Returns:
            Tuple of (mock_api, mock_videos, mock_shots).
        """
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

        # Build old shot records with enrichment data
        old_shot_ids = [f"recOLD{i+1}" for i in range(len(old_shot_fields_list))]
        old_records = {
            old_shot_ids[i]: {
                "id": old_shot_ids[i],
                "fields": old_shot_fields_list[i],
            }
            for i in range(len(old_shot_fields_list))
        }

        # Existing video with reverse-link to old shots
        mock_videos.all.return_value = [{
            "id": "recVID1",
            "fields": {
                "Video ID": "KGHoVptow30",
                "Shots": old_shot_ids,
            },
        }]

        # Old shot records readable via get()
        mock_shots.get.side_effect = lambda rid: old_records[rid]

        # New shots created after deletion
        mock_shots.batch_create.return_value = [
            {"id": f"recNEW{i+1}", "fields": {"Shot Label": f"S{i+1:02d}"}}
            for i in range(3)
        ]

        return mock_api, mock_videos, mock_shots

    # -- Skip already-enriched shots --

    @patch("publisher.publish.Api")
    def test_skips_enrichment_for_already_enriched_shots(
        self, mock_api_cls, analysis_dir: Path
    ):
        """enrich_fn should NOT be called when all shots are already enriched."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": f"S{i+1:02d}"}
            for i in range(3)
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        enrich_fn.assert_not_called()

    @patch("publisher.publish.Api")
    def test_mixed_batch_only_enriches_unenriched(
        self, mock_api_cls, analysis_dir: Path
    ):
        """In a mixed batch, enrich_fn should only be called for unenriched shots."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": "S01"},  # enriched
            {"Shot Label": "S02"},                            # NOT enriched
            {**self.ENRICHED_FIELDS, "Shot Label": "S03"},  # enriched
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert enrich_fn.call_count == 1

    # -- AI Error eligible for retry --

    @patch("publisher.publish.Api")
    def test_ai_error_shot_eligible_for_retry(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Shots with AI Error but no AI Prompt Version should be re-enriched."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": "S01"},                   # enriched
            {"Shot Label": "S02", "AI Error": "Enrichment failed: timeout"}, # failed → retry
            {**self.ENRICHED_FIELDS, "Shot Label": "S03"},                   # enriched
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        # Only the failed shot (S02) should be re-enriched
        assert enrich_fn.call_count == 1

    # -- Preserve old enrichment on new records --

    @patch("publisher.publish.Api")
    def test_preserves_old_enrichment_on_new_shot(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Enrichment fields from old shots should be copied to new shot records."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": f"S{i+1:02d}"}
            for i in range(3)
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        # Each new shot should be updated with old enrichment fields
        assert mock_shots.update.call_count == 3
        first_update = mock_shots.update.call_args_list[0]
        record_id, fields = first_update[0]
        assert record_id == "recNEW1"
        assert fields.get("Shot Type") == "Medium Shot"
        assert fields.get("AI Prompt Version") == "1.0"

    # -- Summary reporting --

    @patch("publisher.publish.Api")
    def test_summary_includes_shots_skipped(
        self, mock_api_cls, analysis_dir: Path
    ):
        """Result summary should include shots_skipped_enrichment count."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": "S01"},  # enriched → skip
            {**self.ENRICHED_FIELDS, "Shot Label": "S02"},  # enriched → skip
            {"Shot Label": "S03"},                            # NOT enriched → enrich
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert "shots_skipped_enrichment" in result
        assert result["shots_skipped_enrichment"] == 2

    @patch("publisher.publish.Api")
    def test_summary_enriched_plus_skipped_equals_total(
        self, mock_api_cls, analysis_dir: Path
    ):
        """shots_enriched + shots_skipped_enrichment should equal total shots."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": "S01"},  # skip
            {"Shot Label": "S02"},                            # enrich
            {**self.ENRICHED_FIELDS, "Shot Label": "S03"},  # skip
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )
        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        total = result["shots_enriched"] + result["shots_skipped_enrichment"]
        assert total == 3

    # -- Backward compatibility guards (should PASS in RED phase) --

    @patch("publisher.publish.Api")
    def test_new_video_enriches_all_shots(
        self, mock_api_cls, analysis_dir: Path
    ):
        """New video (no existing shots) should enrich all shots normally."""
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
        mock_videos.create.return_value = {"id": "recVID1", "fields": {}}
        mock_shots.batch_create.return_value = [
            {"id": f"recSHOT{i+1}", "fields": {"Shot Label": f"S{i+1:02d}"}}
            for i in range(3)
        ]

        enrich_fn = MagicMock(return_value=self.VALID_LLM_RESPONSE)

        publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=True, enrich_fn=enrich_fn,
        )

        assert enrich_fn.call_count == 3

    @patch("publisher.publish.Api")
    def test_enrich_disabled_ignores_old_enrichment_state(
        self, mock_api_cls, analysis_dir: Path
    ):
        """enrich_shots=False should work normally regardless of old shot state."""
        old_fields = [
            {**self.ENRICHED_FIELDS, "Shot Label": f"S{i+1:02d}"}
            for i in range(3)
        ]
        _, _, mock_shots = self._setup_mocks_with_existing_enriched_shots(
            mock_api_cls, old_fields
        )

        result = publish_to_airtable(
            str(analysis_dir), api_key="fake_key", base_id="appXYZ",
            enrich_shots=False,
        )

        mock_shots.update.assert_not_called()
        assert result["shots_created"] == 3


# ---------------------------------------------------------------------------
# is_shot_enriched unit tests
# ---------------------------------------------------------------------------


class TestIsAlreadyEnriched:
    """Unit tests for is_shot_enriched() — the skip decision helper."""

    def test_enriched_with_prompt_version(self):
        assert is_shot_enriched({"AI Prompt Version": "1.0"}) is True

    def test_not_enriched_empty_fields(self):
        assert is_shot_enriched({}) is False

    def test_not_enriched_with_ai_error_only(self):
        """AI Error without AI Prompt Version means failed — eligible for retry."""
        assert is_shot_enriched({"AI Error": "timeout"}) is False

    def test_enriched_with_both_prompt_version_and_error(self):
        """AI Prompt Version takes precedence — shot is considered enriched."""
        assert is_shot_enriched({
            "AI Prompt Version": "1.0",
            "AI Error": "partial response",
        }) is True

    def test_not_enriched_with_empty_prompt_version(self):
        """Empty string AI Prompt Version is falsy — not enriched."""
        assert is_shot_enriched({"AI Prompt Version": ""}) is False

    def test_not_enriched_with_none_prompt_version(self):
        """None AI Prompt Version is falsy — not enriched."""
        assert is_shot_enriched({"AI Prompt Version": None}) is False
