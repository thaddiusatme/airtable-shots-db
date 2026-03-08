"""Tests for publisher.shot_package — RED phase (TDD Iteration 3).

Tests cover:
- collect_shot_frames(): Gather all frames belonging to a shot in stable order
- build_shot_package(): Assemble a complete shot package for LLM consumption
- parse_llm_response(): Parse structured LLM output into Airtable field dict
- SHOT_ENRICHMENT_FIELDS: Explicit mapping from LLM keys to Airtable columns
"""

import json
from typing import Any

import pytest

from publisher.shot_package import (
    SHOT_ENRICHMENT_FIELDS,
    build_shot_package,
    collect_shot_frames,
    parse_llm_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCENE_A = {
    "sceneIndex": 0,
    "startTimestamp": 0,
    "endTimestamp": 5,
    "firstFrame": "frame_00000_t000.000s.png",
    "lastFrame": "frame_00005_t005.000s.png",
    "description": "Speaker at desk",
    "transition": "cut",
}

SCENE_B = {
    "sceneIndex": 1,
    "startTimestamp": 6,
    "endTimestamp": 15,
    "firstFrame": "frame_00006_t006.000s.png",
    "lastFrame": "frame_00015_t015.000s.png",
    "description": "Close-up of screen recording",
    "transition": "cut",
}

# Manifest simulating 5-second sampled capture (index-based filenames)
SAMPLED_MANIFEST_FRAMES = {
    0: "frame_00000_t000.000s.png",
    5: "frame_00001_t005.000s.png",
    10: "frame_00002_t010.000s.png",
    15: "frame_00003_t015.000s.png",
}

TRANSCRIPT_SLICE_A = "[0:00] Welcome back everyone\n[0:03] Today we're looking at"
TRANSCRIPT_SLICE_B = "[0:06] So if you open the app\n[0:10] You'll see the dashboard"

# Simulated valid LLM JSON response
VALID_LLM_RESPONSE = json.dumps({
    "scene_summary": "Speaker introduces the topic from a studio desk setup.",
    "how_it_is_shot": "Medium shot, single camera, static framing with shallow depth of field.",
    "shot_type": "Medium Shot",
    "camera_angle": "Eye Level",
    "movement": "Static",
    "lighting": "Three-point studio lighting with purple accent",
    "setting": "Home studio / podcast setup",
    "subject": "Male speaker with headphones and microphone",
    "on_screen_text": "None",
    "shot_function": "Introduction / Hook",
    "frame_progression": "Minimal movement; speaker gestures occasionally, background static.",
    "production_patterns": "Standard talking-head podcast setup, consistent framing.",
    "recreation_guidance": "Use medium shot at eye level, three-point lighting with colored accent, shallow DoF.",
})


# ---------------------------------------------------------------------------
# collect_shot_frames tests
# ---------------------------------------------------------------------------


class TestCollectShotFrames:
    """Tests for collect_shot_frames() — gather frames for a single shot."""

    def test_returns_list(self):
        result = collect_shot_frames(SCENE_A, manifest_frame_map=None, sample_rate=1)
        assert isinstance(result, list)

    def test_every_second_capture_includes_all_timestamps(self):
        """1-second capture: every integer second in [start, end] produces a frame."""
        result = collect_shot_frames(SCENE_A, manifest_frame_map=None, sample_rate=1)
        timestamps = [f["timestamp"] for f in result]
        assert timestamps == [0, 1, 2, 3, 4, 5]

    def test_sampled_capture_uses_manifest_filenames(self):
        """With manifest, filenames come from actual capture (index-based)."""
        result = collect_shot_frames(
            SCENE_A, manifest_frame_map=SAMPLED_MANIFEST_FRAMES, sample_rate=5
        )
        filenames = [f["filename"] for f in result]
        # Only t=0 and t=5 fall within scene A [0, 5]
        assert "frame_00000_t000.000s.png" in filenames
        assert "frame_00001_t005.000s.png" in filenames

    def test_sampled_capture_skips_uncaptured_timestamps(self):
        """Timestamps not in the manifest should be skipped."""
        result = collect_shot_frames(
            SCENE_A, manifest_frame_map=SAMPLED_MANIFEST_FRAMES, sample_rate=1
        )
        timestamps = [f["timestamp"] for f in result]
        # Only t=0 and t=5 exist in the manifest within [0, 5]
        assert timestamps == [0, 5]

    def test_frames_sorted_by_timestamp(self):
        """Output frames must be in ascending timestamp order."""
        result = collect_shot_frames(
            SCENE_B, manifest_frame_map=SAMPLED_MANIFEST_FRAMES, sample_rate=5
        )
        timestamps = [f["timestamp"] for f in result]
        assert timestamps == sorted(timestamps)

    def test_frame_dict_has_required_keys(self):
        """Each frame dict must contain filename and timestamp."""
        result = collect_shot_frames(SCENE_A, manifest_frame_map=None, sample_rate=1)
        for frame in result:
            assert "filename" in frame
            assert "timestamp" in frame

    def test_synthesized_filename_format(self):
        """Without manifest, filenames follow frame_XXXXX_tSSS.MMMMs.png pattern."""
        result = collect_shot_frames(SCENE_A, manifest_frame_map=None, sample_rate=1)
        assert result[0]["filename"] == "frame_00000_t000.000s.png"
        assert result[3]["filename"] == "frame_00003_t003.000s.png"

    def test_empty_scene_range(self):
        """Scene where start == end should still produce one frame."""
        scene = {**SCENE_A, "startTimestamp": 5, "endTimestamp": 5}
        result = collect_shot_frames(scene, manifest_frame_map=None, sample_rate=1)
        assert len(result) == 1
        assert result[0]["timestamp"] == 5

    def test_scene_b_sampled_range_starts_at_scene_start(self):
        """Scene B [6, 15] with 5s sampling iterates 6,11 — neither in manifest."""
        result = collect_shot_frames(
            SCENE_B, manifest_frame_map=SAMPLED_MANIFEST_FRAMES, sample_rate=5
        )
        # range(6, 16, 5) = [6, 11]; neither is in manifest {0,5,10,15}
        assert result == []

    def test_scene_b_1s_sampled_includes_manifest_hits(self):
        """Scene B [6, 15] with 1s sampling and manifest includes t=10 and t=15."""
        result = collect_shot_frames(
            SCENE_B, manifest_frame_map=SAMPLED_MANIFEST_FRAMES, sample_rate=1
        )
        timestamps = [f["timestamp"] for f in result]
        assert 10 in timestamps
        assert 15 in timestamps


# ---------------------------------------------------------------------------
# build_shot_package tests
# ---------------------------------------------------------------------------


class TestBuildShotPackage:
    """Tests for build_shot_package() — assemble one complete shot package."""

    @pytest.fixture
    def frames_a(self) -> list[dict[str, Any]]:
        """Pre-collected frames for scene A."""
        return [
            {"filename": "frame_00000_t000.000s.png", "timestamp": 0},
            {"filename": "frame_00001_t001.000s.png", "timestamp": 1},
            {"filename": "frame_00002_t002.000s.png", "timestamp": 2},
            {"filename": "frame_00003_t003.000s.png", "timestamp": 3},
            {"filename": "frame_00004_t004.000s.png", "timestamp": 4},
            {"filename": "frame_00005_t005.000s.png", "timestamp": 5},
        ]

    def test_returns_dict(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert isinstance(result, dict)

    def test_has_required_keys(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        required = {
            "shot_label", "video_id", "scene_index",
            "start_timestamp", "end_timestamp",
            "frames", "transcript",
        }
        assert required.issubset(set(result.keys()))

    def test_shot_label_format(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["shot_label"] == "S01"

    def test_shot_label_scene_b(self, frames_a):
        result = build_shot_package(
            scene=SCENE_B, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_B, video_id="KGHoVptow30",
        )
        assert result["shot_label"] == "S02"

    def test_video_id_propagated(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["video_id"] == "KGHoVptow30"

    def test_timestamps_from_scene(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["start_timestamp"] == 0
        assert result["end_timestamp"] == 5

    def test_all_frames_included(self, frames_a):
        """Every frame passed in should appear in the package."""
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert len(result["frames"]) == 6

    def test_frames_preserve_order(self, frames_a):
        """Frame list in package must maintain input order (timestamp-sorted)."""
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        timestamps = [f["timestamp"] for f in result["frames"]]
        assert timestamps == [0, 1, 2, 3, 4, 5]

    def test_transcript_included_unchanged(self, frames_a):
        """Transcript slice must be included exactly as provided."""
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["transcript"] == TRANSCRIPT_SLICE_A

    def test_empty_transcript_is_valid(self, frames_a):
        """Empty transcript string is acceptable (shot may have no dialogue)."""
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice="", video_id="KGHoVptow30",
        )
        assert result["transcript"] == ""

    def test_empty_frames_is_valid(self):
        """Empty frame list is acceptable (shot may have no captured frames)."""
        result = build_shot_package(
            scene=SCENE_A, frames=[],
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["frames"] == []

    def test_scene_index_propagated(self, frames_a):
        result = build_shot_package(
            scene=SCENE_A, frames=frames_a,
            transcript_slice=TRANSCRIPT_SLICE_A, video_id="KGHoVptow30",
        )
        assert result["scene_index"] == 0


# ---------------------------------------------------------------------------
# parse_llm_response tests
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    """Tests for parse_llm_response() — parse structured LLM output to Airtable fields."""

    def test_returns_dict(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert isinstance(result, dict)

    def test_maps_scene_summary_to_ai_description(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["AI Description (Local)"] == (
            "Speaker introduces the topic from a studio desk setup."
        )

    def test_maps_shot_type(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Shot Type"] == "Medium Shot"

    def test_maps_camera_angle(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Camera Angle"] == "Eye Level"

    def test_maps_movement(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Movement"] == "Static"

    def test_maps_lighting(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Lighting"] == "Three-point studio lighting with purple accent"

    def test_maps_setting(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Setting"] == "Home studio / podcast setup"

    def test_maps_subject(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Subject"] == "Male speaker with headphones and microphone"

    def test_maps_on_screen_text(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["On-screen Text"] == "None"

    def test_maps_shot_function(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Shot Function"] == "Introduction / Hook"

    def test_preserves_raw_json_in_ai_json(self):
        """Full LLM response must be stored in AI JSON for future analysis."""
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert "AI JSON" in result
        # Should be valid JSON when parsed back
        parsed = json.loads(result["AI JSON"])
        assert "scene_summary" in parsed

    def test_invalid_json_returns_ai_error(self):
        """Invalid JSON should not raise — should return AI Error field."""
        result = parse_llm_response("not valid json {{{")
        assert "AI Error" in result
        assert "AI JSON" not in result or result["AI JSON"] is None

    def test_partial_response_populates_available_fields(self):
        """If LLM returns only some fields, populate what's available."""
        partial = json.dumps({"scene_summary": "A quick intro.", "shot_type": "Wide"})
        result = parse_llm_response(partial)
        assert result["AI Description (Local)"] == "A quick intro."
        assert result["Shot Type"] == "Wide"
        # Missing fields should not be present (avoid overwriting existing data)
        assert "Camera Angle" not in result

    def test_empty_string_returns_ai_error(self):
        """Empty response string should return AI Error."""
        result = parse_llm_response("")
        assert "AI Error" in result

    def test_none_values_excluded(self):
        """LLM fields with None/null values should not appear in output."""
        response = json.dumps({"scene_summary": "Intro.", "shot_type": None})
        result = parse_llm_response(response)
        assert "Shot Type" not in result


# ---------------------------------------------------------------------------
# SHOT_ENRICHMENT_FIELDS constant tests
# ---------------------------------------------------------------------------


class TestShotEnrichmentFields:
    """Tests for the explicit field mapping constant."""

    def test_is_dict(self):
        assert isinstance(SHOT_ENRICHMENT_FIELDS, dict)

    def test_maps_llm_keys_to_airtable_columns(self):
        """Each key is an LLM output key, each value is an Airtable column name."""
        assert SHOT_ENRICHMENT_FIELDS["scene_summary"] == "AI Description (Local)"
        assert SHOT_ENRICHMENT_FIELDS["shot_type"] == "Shot Type"
        assert SHOT_ENRICHMENT_FIELDS["camera_angle"] == "Camera Angle"

    def test_includes_all_expected_fields(self):
        expected_keys = {
            "scene_summary", "how_it_is_shot", "shot_type", "camera_angle",
            "movement", "lighting", "setting", "subject", "on_screen_text",
            "shot_function", "frame_progression", "production_patterns",
            "recreation_guidance",
        }
        assert expected_keys.issubset(set(SHOT_ENRICHMENT_FIELDS.keys()))

    def test_no_duplicate_airtable_columns(self):
        """Each Airtable column should map from exactly one LLM key."""
        values = list(SHOT_ENRICHMENT_FIELDS.values())
        assert len(values) == len(set(values))
