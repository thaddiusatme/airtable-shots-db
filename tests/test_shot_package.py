"""Tests for publisher.shot_package — RED phase (TDD Iterations 3–4).

Tests cover:
- collect_shot_frames(): Gather all frames belonging to a shot in stable order
- build_shot_package(): Assemble a complete shot package for LLM consumption
- parse_llm_response(): Parse structured LLM output into Airtable field dict
- SHOT_ENRICHMENT_FIELDS: Explicit mapping from LLM keys to Airtable columns
- build_enrichment_prompt(): Build multimodal prompt payload for LLM enrichment
- AI_PROMPT_VERSION: Prompt versioning constant
"""

import json
from typing import Any

import pytest

from publisher.shot_package import (
    AI_PROMPT_VERSION,
    SHOT_ENRICHMENT_FIELDS,
    build_enrichment_prompt,
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

    def test_parses_markdown_fenced_json_with_language_tag(self):
        response = f"```json\n{VALID_LLM_RESPONSE}\n```"

        result = parse_llm_response(response)

        assert result["AI Description (Local)"] == (
            "Speaker introduces the topic from a studio desk setup."
        )
        assert result["Shot Type"] == "Medium"
        assert result["AI JSON"] == response

    def test_parses_markdown_fenced_json_with_leading_whitespace(self):
        response = f"\n\n  ```json\n{VALID_LLM_RESPONSE}\n```\n"

        result = parse_llm_response(response)

        assert result["Camera Angle"] == "Eye-level"
        assert result["Movement"] == ["Static"]

    def test_parses_markdown_fenced_json_without_language_tag(self):
        response = f"```\n{VALID_LLM_RESPONSE}\n```"

        result = parse_llm_response(response)

        assert result["Lighting"] == "Studio-soft"
        assert result["Subject"] == "Male speaker with headphones and microphone"

    def test_maps_scene_summary_to_ai_description(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["AI Description (Local)"] == (
            "Speaker introduces the topic from a studio desk setup."
        )

    def test_maps_shot_type(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Shot Type"] == "Medium"

    def test_maps_camera_angle(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Camera Angle"] == "Eye-level"

    def test_maps_movement(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Movement"] == ["Static"]

    def test_maps_lighting(self):
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert result["Lighting"] == "Studio-soft"

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
        assert result["Shot Function"] == "Hook"

    def test_normalizes_still_image_movement_to_static_list(self):
        response = json.dumps({"movement": "Still image"})

        result = parse_llm_response(response)

        assert result["Movement"] == ["Static"]

    def test_normalizes_multiple_movement_values_to_allowed_list(self):
        response = json.dumps({"movement": "pan and tilt"})

        result = parse_llm_response(response)

        assert result["Movement"] == ["Pan", "Tilt"]

    def test_normalizes_unknown_controlled_vocab_to_other(self):
        response = json.dumps(
            {
                "shot_type": "Medium Shot",
                "camera_angle": "Eye Level",
                "lighting": "Moonbeam haze",
                "shot_function": "Context setter",
            }
        )

        result = parse_llm_response(response)

        assert result["Shot Type"] == "Medium"
        assert result["Camera Angle"] == "Eye-level"
        assert result["Lighting"] == "Other"
        assert result["Shot Function"] == "Other"

    def test_normalizes_recognized_controlled_vocab_synonyms(self):
        response = json.dumps(
            {
                "lighting": "Purple cyberpunk glow",
                "shot_function": "Cold open",
            }
        )

        result = parse_llm_response(response)

        assert result["Lighting"] == "Neon"
        assert result["Shot Function"] == "Hook"

    def test_preserves_raw_json_in_ai_json(self):
        """Full LLM response must be stored in AI JSON for future analysis."""
        result = parse_llm_response(VALID_LLM_RESPONSE)
        assert "AI JSON" in result
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
# build_enrichment_prompt tests
# ---------------------------------------------------------------------------

class TestBuildEnrichmentPrompt:
    """Tests for build_enrichment_prompt() — build multimodal prompt payload."""

    @pytest.fixture
    def shot_pkg(self) -> dict[str, Any]:
        """A typical shot package as returned by build_shot_package()."""
        return {
            "shot_label": "S01",
            "video_id": "KGHoVptow30",
            "scene_index": 0,
            "start_timestamp": 0,
            "end_timestamp": 5,
            "frames": [
                {"filename": "frame_00000_t000.000s.png", "timestamp": 0},
                {"filename": "frame_00001_t001.000s.png", "timestamp": 1},
                {"filename": "frame_00002_t002.000s.png", "timestamp": 2},
                {"filename": "frame_00003_t003.000s.png", "timestamp": 3},
                {"filename": "frame_00004_t004.000s.png", "timestamp": 4},
                {"filename": "frame_00005_t005.000s.png", "timestamp": 5},
            ],
            "transcript": TRANSCRIPT_SLICE_A,
        }

    @pytest.fixture
    def empty_pkg(self) -> dict[str, Any]:
        """Shot package with no frames and empty transcript."""
        return {
            "shot_label": "S03",
            "video_id": "KGHoVptow30",
            "scene_index": 2,
            "start_timestamp": 20,
            "end_timestamp": 25,
            "frames": [],
            "transcript": "",
        }

    # -- Structure tests --

    def test_returns_dict(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert isinstance(result, dict)

    def test_has_required_keys(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        required = {"system_prompt", "user_prompt", "frame_references", "prompt_version"}
        assert required.issubset(set(result.keys()))

    # -- System prompt tests --

    def test_system_prompt_is_string(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert isinstance(result["system_prompt"], str)

    def test_system_prompt_requests_json_output(self, shot_pkg):
        """System prompt must instruct the LLM to return JSON."""
        result = build_enrichment_prompt(shot_pkg)
        assert "JSON" in result["system_prompt"]

    def test_system_prompt_references_all_enrichment_field_keys(self, shot_pkg):
        """System prompt must mention every LLM output key from SHOT_ENRICHMENT_FIELDS."""
        result = build_enrichment_prompt(shot_pkg)
        for llm_key in SHOT_ENRICHMENT_FIELDS:
            assert llm_key in result["system_prompt"], (
                f"Missing LLM key '{llm_key}' in system prompt"
            )

    def test_system_prompt_includes_controlled_vocabulary_guidance(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert "shot_type" in result["system_prompt"]
        assert "Wide, Medium, Close-up" in result["system_prompt"]
        assert "camera_angle" in result["system_prompt"]
        assert "Eye-level, High, Low" in result["system_prompt"]
        assert "movement" in result["system_prompt"]
        assert "JSON array" in result["system_prompt"]
        assert "Static, Pan, Tilt" in result["system_prompt"]
        assert 'use "Other"' in result["system_prompt"]

    def test_system_prompt_includes_narrative_field_guidance(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        prompt = result["system_prompt"]
        assert "plain strings" in prompt
        assert "never arrays" in prompt
        assert "scene_summary" in prompt
        assert "how_it_is_shot" in prompt
        assert "frame_progression" in prompt

    # -- User prompt tests --

    def test_user_prompt_is_string(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert isinstance(result["user_prompt"], str)

    def test_user_prompt_includes_transcript(self, shot_pkg):
        """Full transcript slice must appear in the user prompt."""
        result = build_enrichment_prompt(shot_pkg)
        assert TRANSCRIPT_SLICE_A in result["user_prompt"]

    def test_user_prompt_includes_shot_label(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert "S01" in result["user_prompt"]

    def test_user_prompt_includes_timing_context(self, shot_pkg):
        """User prompt should reference the shot's time range."""
        result = build_enrichment_prompt(shot_pkg)
        assert "0" in result["user_prompt"]
        assert "5" in result["user_prompt"]

    def test_user_prompt_includes_video_id(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert "KGHoVptow30" in result["user_prompt"]

    # -- Frame references tests --

    def test_frame_references_is_list(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert isinstance(result["frame_references"], list)

    def test_frame_references_match_package_frames(self, shot_pkg):
        """Every frame filename from the package should appear in frame_references."""
        result = build_enrichment_prompt(shot_pkg)
        expected = [f["filename"] for f in shot_pkg["frames"]]
        assert result["frame_references"] == expected

    def test_frame_references_preserve_order(self, shot_pkg):
        """Frame references must maintain the same order as the shot package frames."""
        result = build_enrichment_prompt(shot_pkg)
        refs = result["frame_references"]
        assert refs[0] == "frame_00000_t000.000s.png"
        assert refs[-1] == "frame_00005_t005.000s.png"

    def test_frame_count_mentioned_in_user_prompt(self, shot_pkg):
        """User prompt should state how many frames are included."""
        result = build_enrichment_prompt(shot_pkg)
        assert "6" in result["user_prompt"]

    # -- Prompt version tests --

    def test_prompt_version_matches_constant(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert result["prompt_version"] == AI_PROMPT_VERSION

    def test_prompt_version_is_string(self, shot_pkg):
        result = build_enrichment_prompt(shot_pkg)
        assert isinstance(result["prompt_version"], str)

    def test_ai_prompt_version_constant_is_nonempty(self):
        """AI_PROMPT_VERSION must be a non-empty string."""
        assert isinstance(AI_PROMPT_VERSION, str)
        assert len(AI_PROMPT_VERSION) > 0

    # -- Edge cases --

    def test_empty_frames_produces_empty_frame_references(self, empty_pkg):
        result = build_enrichment_prompt(empty_pkg)
        assert result["frame_references"] == []

    def test_empty_transcript_still_valid(self, empty_pkg):
        """Empty transcript should not cause errors."""
        result = build_enrichment_prompt(empty_pkg)
        assert isinstance(result["user_prompt"], str)

    def test_user_prompt_notes_no_frames_when_empty(self, empty_pkg):
        """When no frames are available, user prompt should note this."""
        result = build_enrichment_prompt(empty_pkg)
        assert "0" in result["user_prompt"]  # mentions 0 frames

    def test_user_prompt_notes_no_transcript_when_empty(self, empty_pkg):
        """When transcript is empty, user prompt should indicate this."""
        result = build_enrichment_prompt(empty_pkg)
        prompt_lower = result["user_prompt"].lower()
        assert "no transcript" in prompt_lower or "no dialogue" in prompt_lower


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


# ---------------------------------------------------------------------------
# Narrative field coercion tests
# ---------------------------------------------------------------------------

NARRATIVE_FIELDS = (
    "scene_summary",
    "how_it_is_shot",
    "setting",
    "subject",
    "on_screen_text",
    "frame_progression",
    "production_patterns",
    "recreation_guidance",
)


class TestNarrativeFieldCoercion:
    """Tests for coercing non-string LLM narrative values into Airtable-safe strings.

    Live runs showed the LLM sometimes returns lists, dicts, or numbers for
    narrative/text fields. Airtable rejects these with INVALID_VALUE_FOR_COLUMN.
    parse_llm_response() must coerce all narrative fields to plain strings.
    """

    def test_list_how_it_is_shot_coerced_to_string(self):
        response = json.dumps({
            "how_it_is_shot": ["Medium shot", "static framing", "shallow depth of field"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["How It Is Shot"], str)
        assert "Medium shot" in result["How It Is Shot"]
        assert "static framing" in result["How It Is Shot"]
        assert "shallow depth of field" in result["How It Is Shot"]

    def test_list_frame_progression_coerced_to_string(self):
        response = json.dumps({
            "frame_progression": ["Speaker enters frame", "Gestures at screen", "Returns to center"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["Frame Progression"], str)
        assert "Speaker enters frame" in result["Frame Progression"]

    def test_numeric_frame_progression_coerced_to_string(self):
        response = json.dumps({
            "frame_progression": 3,
        })
        result = parse_llm_response(response)
        assert isinstance(result["Frame Progression"], str)
        assert "3" in result["Frame Progression"]

    def test_dict_on_screen_text_coerced_to_string(self):
        response = json.dumps({
            "on_screen_text": {"title": "Welcome Back", "subtitle": "Episode 5"},
        })
        result = parse_llm_response(response)
        assert isinstance(result["On-screen Text"], str)
        assert "Welcome Back" in result["On-screen Text"]
        assert "Episode 5" in result["On-screen Text"]

    def test_list_production_patterns_coerced_to_string(self):
        response = json.dumps({
            "production_patterns": ["Jump cuts", "B-roll inserts", "Lower thirds"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["Production Patterns"], str)
        assert "Jump cuts" in result["Production Patterns"]

    def test_list_recreation_guidance_coerced_to_string(self):
        response = json.dumps({
            "recreation_guidance": ["Use medium shot", "Add three-point lighting", "Place subject center-frame"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["Recreation Guidance"], str)
        assert "Use medium shot" in result["Recreation Guidance"]

    def test_dict_setting_coerced_to_string(self):
        response = json.dumps({
            "setting": {"location": "Home office", "details": "desk with monitors"},
        })
        result = parse_llm_response(response)
        assert isinstance(result["Setting"], str)
        assert "Home office" in result["Setting"]

    def test_list_subject_coerced_to_string(self):
        response = json.dumps({
            "subject": ["Male speaker", "laptop", "whiteboard"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["Subject"], str)
        assert "Male speaker" in result["Subject"]

    def test_list_scene_summary_coerced_to_string(self):
        response = json.dumps({
            "scene_summary": ["Intro segment", "Speaker greets audience"],
        })
        result = parse_llm_response(response)
        assert isinstance(result["AI Description (Local)"], str)
        assert "Intro segment" in result["AI Description (Local)"]

    def test_nested_list_coerced_to_string(self):
        response = json.dumps({
            "how_it_is_shot": [["Medium shot", "static"], ["shallow DoF"]],
        })
        result = parse_llm_response(response)
        assert isinstance(result["How It Is Shot"], str)
        assert "Medium shot" in result["How It Is Shot"]

    def test_mixed_narrative_shapes_all_become_strings(self):
        response = json.dumps({
            "how_it_is_shot": ["Medium shot", "static framing"],
            "frame_progression": 5,
            "on_screen_text": {"text": "Subscribe"},
            "production_patterns": "Standard talking head",
            "recreation_guidance": ["Use wide shot"],
            "setting": {"type": "studio"},
            "subject": ["Speaker"],
            "scene_summary": "Quick intro",
        })
        result = parse_llm_response(response)
        for llm_key in NARRATIVE_FIELDS:
            airtable_col = SHOT_ENRICHMENT_FIELDS[llm_key]
            if airtable_col in result:
                assert isinstance(result[airtable_col], str), (
                    f"{airtable_col} should be a string, got {type(result[airtable_col])}"
                )

    def test_plain_string_narrative_unchanged(self):
        response = json.dumps({
            "how_it_is_shot": "Medium shot, static framing with shallow depth of field.",
        })
        result = parse_llm_response(response)
        assert result["How It Is Shot"] == "Medium shot, static framing with shallow depth of field."

    def test_boolean_narrative_coerced_to_string(self):
        response = json.dumps({
            "on_screen_text": True,
        })
        result = parse_llm_response(response)
        assert isinstance(result["On-screen Text"], str)

    def test_float_narrative_coerced_to_string(self):
        response = json.dumps({
            "frame_progression": 2.5,
        })
        result = parse_llm_response(response)
        assert isinstance(result["Frame Progression"], str)
