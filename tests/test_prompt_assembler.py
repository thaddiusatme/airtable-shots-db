"""Tests for publisher.prompt_assembler — GH-32 image prompt contract v1.

Golden tests for the per-shot SDXL/ComfyUI prompt assembler. Each test uses
representative enriched shot dicts (Airtable field names) and asserts on the
assembled output structure and content.

TDD RED phase: All tests expected to fail with ImportError (module does not exist).
"""

import json

from publisher.prompt_assembler import (
    ASSEMBLER_VERSION,
    assemble_shot_image_prompt,
)


# ---------------------------------------------------------------------------
# Fixtures — representative enriched shot dicts (Airtable field names)
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

OTHER_HEAVY_SHOT = {
    "Shot Label": "S07",
    "Subject": "laptop screen showing code editor",
    "Setting": "dimly lit home office",
    "Shot Type": "Close-up",
    "Camera Angle": "Other",
    "Lighting": "Other",
    "Movement": ["Static"],
    "How It Is Shot": "Handheld close-up of laptop screen",
    "AI Description (Local)": "Close-up of a laptop screen displaying lines of code.",
    "Shot Function": "Proof",
    "On-screen Text": "VS Code with Python file open",
    "Frame Progression": "No pattern information provided.",
    "Production Patterns": "Not enough information to determine production patterns.",
    "Recreation Guidance": "Point camera directly at laptop screen, ensure code is readable",
}

MINIMAL_SHOT = {
    "Shot Label": "S01",
    "Subject": "speaker at desk",
    "Setting": "studio",
}

REFERENCE_FRAMES = [
    {"url": "https://r2.example.com/captures/vid123/frame_00001.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00005.png", "role": "composition"},
]


# ---------------------------------------------------------------------------
# Test: Clean shot — all fields present, no Other values
# ---------------------------------------------------------------------------


class TestCleanShotAssembly:
    """Assembler with a fully-enriched shot (no Other, no boilerplate)."""

    def test_returns_dict_with_required_keys(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert isinstance(result, dict)
        for key in ("positive_prompt", "negative_prompt", "prompt_sections", "reference_images", "metadata"):
            assert key in result, f"Missing top-level key: {key}"

    def test_positive_prompt_contains_subject_and_setting(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        pp = result["positive_prompt"]
        assert "person sitting cross-legged in a tent" in pp
        assert "forest clearing at dusk" in pp

    def test_positive_prompt_contains_composition_modifiers(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        pp = result["positive_prompt"].lower()
        assert "medium shot" in pp
        assert "eye-level" in pp.replace("eye-level", "eye-level")  # case-insensitive
        assert "natural" in pp and "soft" in pp

    def test_prompt_sections_has_subject_and_setting(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        sections = result["prompt_sections"]
        assert sections["subject"] == "person sitting cross-legged in a tent"
        assert sections["setting"] == "forest clearing at dusk"

    def test_prompt_sections_includes_composition(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        sections = result["prompt_sections"]
        assert "composition" in sections
        assert "shallow depth of field" in sections["composition"].lower()

    def test_prompt_sections_includes_camera(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        sections = result["prompt_sections"]
        assert "camera" in sections

    def test_prompt_sections_includes_lighting(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        sections = result["prompt_sections"]
        assert "lighting" in sections
        assert "natural-soft" in sections["lighting"].lower()

    def test_metadata_shot_label(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert result["metadata"]["shot_label"] == "S03"

    def test_metadata_assembler_version(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert result["metadata"]["assembler_version"] == ASSEMBLER_VERSION

    def test_metadata_omissions_empty_for_clean_shot(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert result["metadata"]["omissions"] == []

    def test_negative_prompt_is_string(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert isinstance(result["negative_prompt"], str)
        assert len(result["negative_prompt"]) > 0


# ---------------------------------------------------------------------------
# Test: Other-heavy shot — Camera Angle + Lighting are Other → omitted
# ---------------------------------------------------------------------------


class TestOtherHeavyShotOmissions:
    """Assembler gracefully omits low-signal controlled vocab (Other)."""

    def test_positive_prompt_omits_other_camera_angle(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        pp = result["positive_prompt"].lower()
        assert "other" not in pp

    def test_positive_prompt_still_contains_subject(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        pp = result["positive_prompt"]
        assert "laptop screen showing code editor" in pp

    def test_prompt_sections_no_camera_key_when_other(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        sections = result["prompt_sections"]
        # Camera section should be absent or empty when Camera Angle is Other
        if "camera" in sections:
            assert "other" not in sections["camera"].lower()

    def test_prompt_sections_no_lighting_key_when_other(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        sections = result["prompt_sections"]
        if "lighting" in sections:
            assert "other" not in sections["lighting"].lower()

    def test_metadata_omissions_lists_camera_angle(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        omissions = result["metadata"]["omissions"]
        assert any("Camera Angle" in o for o in omissions)

    def test_metadata_omissions_lists_lighting(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        omissions = result["metadata"]["omissions"]
        assert any("Lighting" in o for o in omissions)


# ---------------------------------------------------------------------------
# Test: Boilerplate narrative suppression
# ---------------------------------------------------------------------------


class TestBoilerplateFiltering:
    """Assembler filters known boilerplate phrases from narrative fields."""

    def test_frame_progression_boilerplate_omitted(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        pp = result["positive_prompt"]
        assert "No pattern information" not in pp

    def test_production_patterns_boilerplate_omitted(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        pp = result["positive_prompt"]
        assert "Not enough information" not in pp

    def test_boilerplate_tracked_in_omissions(self):
        result = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        omissions = result["metadata"]["omissions"]
        assert any("boilerplate" in o.lower() for o in omissions)

    def test_clean_narrative_passes_through(self):
        """Non-boilerplate narrative content should appear in prompt sections."""
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        sections = result["prompt_sections"]
        # Production Patterns has real content → should appear in style or context
        found = any(
            "rule of thirds" in str(v).lower()
            for v in sections.values()
        )
        assert found, "Real production patterns content should appear in prompt sections"


# ---------------------------------------------------------------------------
# Test: Reference frames present vs absent
# ---------------------------------------------------------------------------


class TestReferenceFrames:
    """Assembler handles reference_frames parameter."""

    def test_frames_included_in_output(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES)
        assert len(result["reference_images"]) == 2
        assert result["reference_images"][0]["url"] == REFERENCE_FRAMES[0]["url"]
        assert result["reference_images"][0]["role"] == "composition"

    def test_no_frames_gives_empty_list(self):
        result = assemble_shot_image_prompt(CLEAN_SHOT)
        assert result["reference_images"] == []

    def test_frames_without_role_default_to_composition(self):
        frames_no_role = [
            {"url": "https://r2.example.com/frame.png"},
        ]
        result = assemble_shot_image_prompt(CLEAN_SHOT, reference_frames=frames_no_role)
        assert result["reference_images"][0]["role"] == "composition"


# ---------------------------------------------------------------------------
# Test: Minimal shot (only required fields)
# ---------------------------------------------------------------------------


class TestMinimalShot:
    """Assembler works with only the required fields (Shot Label, Subject, Setting)."""

    def test_assembles_with_minimal_fields(self):
        result = assemble_shot_image_prompt(MINIMAL_SHOT)
        assert "speaker at desk" in result["positive_prompt"]
        assert "studio" in result["positive_prompt"]

    def test_prompt_sections_populated_for_minimal(self):
        result = assemble_shot_image_prompt(MINIMAL_SHOT)
        assert result["prompt_sections"]["subject"] == "speaker at desk"
        assert result["prompt_sections"]["setting"] == "studio"

    def test_metadata_complete_for_minimal(self):
        result = assemble_shot_image_prompt(MINIMAL_SHOT)
        assert result["metadata"]["shot_label"] == "S01"
        assert result["metadata"]["assembler_version"] == ASSEMBLER_VERSION


# ---------------------------------------------------------------------------
# Test: Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Assembler produces identical output on repeated invocations."""

    def test_identical_json_on_repeated_calls(self):
        r1 = assemble_shot_image_prompt(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES)
        r2 = assemble_shot_image_prompt(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES)
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)

    def test_identical_json_for_other_heavy(self):
        r1 = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        r2 = assemble_shot_image_prompt(OTHER_HEAVY_SHOT)
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
