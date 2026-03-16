"""Tests for publisher.storyboard_handoff — GH-33 pencil storyboard contract.

Thin downstream consumer of GH-32's assemble_shot_image_prompt().
Adds storyboard style layer, 16:9 defaults, deterministic variant generation,
and enriched-shot Airtable retrieval.

TDD RED phase: All tests expected to fail with ImportError (module does not exist).
"""

import json
from unittest.mock import MagicMock

from publisher.prompt_assembler import ASSEMBLER_VERSION, assemble_shot_image_prompt
from publisher.storyboard_handoff import (
    STORYBOARD_HANDOFF_VERSION,
    STORYBOARD_STYLE_DEFAULTS,
    VARIANT_DEFINITIONS,
    build_storyboard_payload,
    build_storyboard_series,
    fetch_enriched_shots_for_storyboard,
    select_reference_frames,
)


# ---------------------------------------------------------------------------
# Fixtures — reuse GH-32 enriched shot dicts
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

REFERENCE_FRAMES_POOL = [
    {"url": "https://r2.example.com/captures/vid123/frame_00001.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00003.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00005.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00007.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00009.png", "role": "composition"},
    {"url": "https://r2.example.com/captures/vid123/frame_00011.png", "role": "composition"},
]


# ---------------------------------------------------------------------------
# Test: Storyboard style defaults constant
# ---------------------------------------------------------------------------


class TestStoryboardStyleDefaults:
    """STORYBOARD_STYLE_DEFAULTS constant provides pencil-only presets."""

    def test_style_defaults_is_dict(self):
        assert isinstance(STORYBOARD_STYLE_DEFAULTS, dict)

    def test_style_preset_is_pencil(self):
        assert "style_preset" in STORYBOARD_STYLE_DEFAULTS
        preset = STORYBOARD_STYLE_DEFAULTS["style_preset"]
        assert "pencil" in preset.lower()

    def test_style_has_positive_modifier(self):
        """Storyboard style adds tokens to the positive prompt."""
        assert "positive_style_tokens" in STORYBOARD_STYLE_DEFAULTS
        tokens = STORYBOARD_STYLE_DEFAULTS["positive_style_tokens"]
        assert isinstance(tokens, str)
        assert len(tokens) > 0
        # Should mention pencil/sketch/storyboard characteristics
        lower = tokens.lower()
        assert any(kw in lower for kw in ("pencil", "sketch", "line art", "storyboard"))

    def test_style_has_negative_modifier(self):
        """Storyboard style adds tokens to the negative prompt."""
        assert "negative_style_tokens" in STORYBOARD_STYLE_DEFAULTS
        tokens = STORYBOARD_STYLE_DEFAULTS["negative_style_tokens"]
        assert isinstance(tokens, str)
        assert len(tokens) > 0
        # Should suppress color/photorealism for pencil-only
        lower = tokens.lower()
        assert any(kw in lower for kw in ("color", "photorealistic", "photograph"))

    def test_aspect_ratio_is_16_9(self):
        assert "aspect_ratio" in STORYBOARD_STYLE_DEFAULTS
        assert STORYBOARD_STYLE_DEFAULTS["aspect_ratio"] == "16:9"

    def test_width_and_height_are_16_9(self):
        """Pixel dimensions should match 16:9 aspect ratio."""
        assert "width" in STORYBOARD_STYLE_DEFAULTS
        assert "height" in STORYBOARD_STYLE_DEFAULTS
        w = STORYBOARD_STYLE_DEFAULTS["width"]
        h = STORYBOARD_STYLE_DEFAULTS["height"]
        assert isinstance(w, int)
        assert isinstance(h, int)
        # 16:9 ratio within rounding tolerance
        assert abs(w / h - 16 / 9) < 0.01


# ---------------------------------------------------------------------------
# Test: Variant definitions constant
# ---------------------------------------------------------------------------


class TestVariantDefinitions:
    """VARIANT_DEFINITIONS provides deterministic variant labels and modifiers."""

    def test_variant_definitions_is_list(self):
        assert isinstance(VARIANT_DEFINITIONS, list)

    def test_at_least_two_variants(self):
        """A/B testing requires at least 2 variants."""
        assert len(VARIANT_DEFINITIONS) >= 2

    def test_each_variant_has_label_and_modifier(self):
        for v in VARIANT_DEFINITIONS:
            assert "label" in v, f"Variant missing 'label': {v}"
            assert "positive_modifier" in v, f"Variant missing 'positive_modifier': {v}"
            assert isinstance(v["label"], str)
            assert isinstance(v["positive_modifier"], str)

    def test_variant_labels_are_unique(self):
        labels = [v["label"] for v in VARIANT_DEFINITIONS]
        assert len(labels) == len(set(labels)), f"Duplicate variant labels: {labels}"

    def test_variant_labels_are_deterministic(self):
        """Labels should be stable identifiers like 'A', 'B', 'C'."""
        labels = [v["label"] for v in VARIANT_DEFINITIONS]
        assert labels[0] == "A"
        assert labels[1] == "B"


# ---------------------------------------------------------------------------
# Test: Reference frame selection
# ---------------------------------------------------------------------------


class TestSelectReferenceFrames:
    """select_reference_frames picks 2-4 frames in stable order from a pool."""

    def test_returns_list(self):
        result = select_reference_frames(REFERENCE_FRAMES_POOL)
        assert isinstance(result, list)

    def test_max_four_frames(self):
        result = select_reference_frames(REFERENCE_FRAMES_POOL)
        assert len(result) <= 4

    def test_min_two_frames_when_available(self):
        """At least 2 frames when the pool has >= 2."""
        result = select_reference_frames(REFERENCE_FRAMES_POOL)
        assert len(result) >= 2

    def test_single_frame_pool_returns_one(self):
        result = select_reference_frames(REFERENCE_FRAMES_POOL[:1])
        assert len(result) == 1

    def test_empty_pool_returns_empty(self):
        result = select_reference_frames([])
        assert result == []

    def test_none_pool_returns_empty(self):
        result = select_reference_frames(None)
        assert result == []

    def test_stable_ordering(self):
        """Same pool produces same selection on repeated calls."""
        r1 = select_reference_frames(REFERENCE_FRAMES_POOL)
        r2 = select_reference_frames(REFERENCE_FRAMES_POOL)
        assert r1 == r2

    def test_evenly_samples_from_pool(self):
        """Should spread across the pool, not just take first N."""
        result = select_reference_frames(REFERENCE_FRAMES_POOL)
        urls = [f["url"] for f in result]
        # First and last from pool should be represented
        assert REFERENCE_FRAMES_POOL[0]["url"] in urls
        assert REFERENCE_FRAMES_POOL[-1]["url"] in urls

    def test_preserves_frame_dict_structure(self):
        result = select_reference_frames(REFERENCE_FRAMES_POOL)
        for f in result:
            assert "url" in f
            assert "role" in f


# ---------------------------------------------------------------------------
# Test: build_storyboard_payload — single shot
# ---------------------------------------------------------------------------


class TestBuildStoryboardPayload:
    """build_storyboard_payload wraps assemble_shot_image_prompt with style layer."""

    def test_returns_dict_with_required_keys(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        assert isinstance(result, dict)
        for key in (
            "base_prompt", "storyboard_positive", "storyboard_negative",
            "style", "generation", "reference_images", "variants", "metadata",
        ):
            assert key in result, f"Missing top-level key: {key}"

    def test_base_prompt_is_assembler_output(self):
        """base_prompt should be the unmodified GH-32 assembler output."""
        result = build_storyboard_payload(CLEAN_SHOT)
        expected = assemble_shot_image_prompt(CLEAN_SHOT)
        assert result["base_prompt"]["positive_prompt"] == expected["positive_prompt"]
        assert result["base_prompt"]["negative_prompt"] == expected["negative_prompt"]
        assert result["base_prompt"]["prompt_sections"] == expected["prompt_sections"]

    def test_storyboard_positive_includes_base_and_style(self):
        """storyboard_positive merges base positive prompt + style tokens."""
        result = build_storyboard_payload(CLEAN_SHOT)
        sp = result["storyboard_positive"]
        assert isinstance(sp, str)
        # Contains base content
        assert "person sitting cross-legged in a tent" in sp
        # Contains style tokens
        lower = sp.lower()
        assert any(kw in lower for kw in ("pencil", "sketch", "storyboard", "line art"))

    def test_storyboard_negative_includes_base_and_style(self):
        """storyboard_negative merges base negative prompt + style negative tokens."""
        result = build_storyboard_payload(CLEAN_SHOT)
        sn = result["storyboard_negative"]
        assert isinstance(sn, str)
        # Contains base negative
        assert "blurry" in sn
        # Contains style suppression tokens
        lower = sn.lower()
        assert any(kw in lower for kw in ("color", "photorealistic", "photograph"))

    def test_style_key_contains_preset(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        assert "style_preset" in result["style"]
        assert "pencil" in result["style"]["style_preset"].lower()

    def test_generation_key_has_16_9_defaults(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        gen = result["generation"]
        assert gen["aspect_ratio"] == "16:9"
        assert "width" in gen
        assert "height" in gen
        assert abs(gen["width"] / gen["height"] - 16 / 9) < 0.01

    def test_variants_list_matches_definitions(self):
        """Each variant gets a labeled prompt string derived from the base."""
        result = build_storyboard_payload(CLEAN_SHOT)
        variants = result["variants"]
        assert isinstance(variants, list)
        assert len(variants) == len(VARIANT_DEFINITIONS)
        for v in variants:
            assert "label" in v
            assert "positive_prompt" in v
            assert isinstance(v["positive_prompt"], str)
            assert len(v["positive_prompt"]) > 0

    def test_variant_labels_match_definitions(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        expected_labels = [vd["label"] for vd in VARIANT_DEFINITIONS]
        actual_labels = [v["label"] for v in result["variants"]]
        assert actual_labels == expected_labels

    def test_variant_prompts_differ(self):
        """Different variants should produce different positive prompts."""
        result = build_storyboard_payload(CLEAN_SHOT)
        prompts = [v["positive_prompt"] for v in result["variants"]]
        assert len(set(prompts)) == len(prompts), "Variant prompts should be distinct"

    def test_reference_images_passed_through(self):
        result = build_storyboard_payload(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES_POOL[:4])
        assert len(result["reference_images"]) <= 4
        assert len(result["reference_images"]) > 0

    def test_reference_images_auto_selected_from_pool(self):
        """When given >4 frames, select_reference_frames should pick 2-4."""
        result = build_storyboard_payload(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES_POOL)
        assert 2 <= len(result["reference_images"]) <= 4

    def test_no_reference_frames_gives_empty_list(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        assert result["reference_images"] == []

    def test_metadata_includes_handoff_version(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        meta = result["metadata"]
        assert meta["handoff_version"] == STORYBOARD_HANDOFF_VERSION
        assert meta["assembler_version"] == ASSEMBLER_VERSION
        assert meta["shot_label"] == "S03"

    def test_metadata_includes_variant_count(self):
        result = build_storyboard_payload(CLEAN_SHOT)
        assert result["metadata"]["variant_count"] == len(VARIANT_DEFINITIONS)


# ---------------------------------------------------------------------------
# Test: build_storyboard_payload — minimal shot
# ---------------------------------------------------------------------------


class TestBuildStoryboardPayloadMinimalShot:
    """Storyboard payload works with minimal shots (only required fields)."""

    def test_minimal_shot_assembles(self):
        result = build_storyboard_payload(MINIMAL_SHOT)
        assert "speaker at desk" in result["storyboard_positive"]

    def test_minimal_shot_has_all_variants(self):
        result = build_storyboard_payload(MINIMAL_SHOT)
        assert len(result["variants"]) == len(VARIANT_DEFINITIONS)

    def test_minimal_shot_has_style(self):
        result = build_storyboard_payload(MINIMAL_SHOT)
        assert "pencil" in result["style"]["style_preset"].lower()


# ---------------------------------------------------------------------------
# Test: Deterministic output
# ---------------------------------------------------------------------------


class TestStoryboardDeterminism:
    """Storyboard payload is deterministic across calls."""

    def test_identical_json_on_repeated_calls(self):
        r1 = build_storyboard_payload(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES_POOL[:4])
        r2 = build_storyboard_payload(CLEAN_SHOT, reference_frames=REFERENCE_FRAMES_POOL[:4])
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ---------------------------------------------------------------------------
# Test: build_storyboard_series — multi-shot
# ---------------------------------------------------------------------------


class TestBuildStoryboardSeries:
    """build_storyboard_series processes multiple shots into an ordered series."""

    def test_returns_list_of_payloads(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        result = build_storyboard_series(shots)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_each_item_is_valid_payload(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        result = build_storyboard_series(shots)
        for payload in result:
            assert "base_prompt" in payload
            assert "storyboard_positive" in payload
            assert "variants" in payload

    def test_shot_order_preserved(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        result = build_storyboard_series(shots)
        assert result[0]["metadata"]["shot_label"] == "S03"
        assert result[1]["metadata"]["shot_label"] == "S01"

    def test_series_index_in_metadata(self):
        shots = [CLEAN_SHOT, MINIMAL_SHOT]
        result = build_storyboard_series(shots)
        assert result[0]["metadata"]["series_index"] == 0
        assert result[1]["metadata"]["series_index"] == 1

    def test_empty_shots_returns_empty(self):
        result = build_storyboard_series([])
        assert result == []


# ---------------------------------------------------------------------------
# Test: fetch_enriched_shots_for_storyboard — Airtable retrieval
# ---------------------------------------------------------------------------


class TestFetchEnrichedShotsForStoryboard:
    """Airtable retrieval follows enriched-shot filtering pattern."""

    def _make_mock_table(self, records):
        table = MagicMock()
        table.all.return_value = records
        return table

    def _make_record(self, shot_label, video_id="vid123", enriched=True):
        fields = {
            "Shot Label": shot_label,
            "Subject": f"subject for {shot_label}",
            "Setting": f"setting for {shot_label}",
        }
        if enriched:
            fields["AI Prompt Version"] = "1.2"
            fields["AI Model"] = "gemini-2.0-flash"
        return {"id": f"rec{shot_label}", "fields": fields}

    def test_fetches_by_video_id(self):
        records = [self._make_record("S01"), self._make_record("S02")]
        table = self._make_mock_table(records)
        result = fetch_enriched_shots_for_storyboard(table, video_id="vid123")
        assert result is not None
        # Should call table.all with a formula filtering by video_id + enriched
        table.all.assert_called_once()
        call_kwargs = table.all.call_args
        formula = call_kwargs.kwargs.get("formula") or call_kwargs[1].get("formula", "")
        assert "vid123" in formula
        assert "AI Prompt Version" in formula

    def test_returns_field_dicts(self):
        records = [self._make_record("S01"), self._make_record("S02")]
        table = self._make_mock_table(records)
        result = fetch_enriched_shots_for_storyboard(table, video_id="vid123")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_optional_shot_id_narrows_filter(self):
        records = [self._make_record("S02")]
        table = self._make_mock_table(records)
        result = fetch_enriched_shots_for_storyboard(
            table, video_id="vid123", shot_id="recS02",
        )
        assert result is not None
        table.all.assert_called_once()
        # Formula should include shot_id filtering
        call_kwargs = table.all.call_args
        formula = call_kwargs.kwargs.get("formula") or call_kwargs[1].get("formula", "")
        assert "recS02" in formula or "S02" in formula

    def test_empty_result_returns_empty_list(self):
        table = self._make_mock_table([])
        result = fetch_enriched_shots_for_storyboard(table, video_id="vid_none")
        assert result == []

    def test_only_enriched_shots_returned(self):
        """Filter formula must require AI Prompt Version."""
        records = [self._make_record("S01", enriched=True)]
        table = self._make_mock_table(records)
        result = fetch_enriched_shots_for_storyboard(table, video_id="vid123")
        assert result is not None
        call_kwargs = table.all.call_args
        formula = call_kwargs.kwargs.get("formula") or call_kwargs[1].get("formula", "")
        assert "AI Prompt Version" in formula
