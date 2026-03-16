# Lessons Learned — GH-33 Pencil Storyboard Handoff (Iteration 1)

**Branch:** `feature/gh-33-pencil-storyboard-handoff`  
**Base:** `feature/gh-32-image-prompt-contract-v1`  
**Module:** `publisher/storyboard_handoff.py`  
**Tests:** `tests/test_storyboard_handoff.py`

---

## What was built

- **`publisher/storyboard_handoff.py`** — thin downstream consumer of GH-32's `assemble_shot_image_prompt()`:
  - `STORYBOARD_HANDOFF_VERSION = "0.1"` — contract revision tracking
  - `STORYBOARD_STYLE_DEFAULTS` — pencil-only preset: positive/negative style tokens, 16:9 (1024×576), style_preset label
  - `VARIANT_DEFINITIONS` — 3 deterministic variants (A: clean linework, B: loose sketch, C: ink wash) with unique positive modifiers
  - `select_reference_frames(pool)` — picks 2–4 frames via even sampling (first + last + evenly-spaced middle)
  - `build_storyboard_payload(shot_fields, reference_frames=)` — wraps assembler output with style layer, generation defaults, variant prompts, metadata
  - `build_storyboard_series(shots, reference_frames_by_shot=)` — ordered multi-shot storyboard with `series_index`
  - `fetch_enriched_shots_for_storyboard(shots_table, video_id=, shot_id=)` — Airtable retrieval with enriched-only filter (`AI Prompt Version != ''`)
- **48 tests** in `tests/test_storyboard_handoff.py` across 9 test classes
- **85/85 total** (37 GH-32 + 48 GH-33), 0 regressions

---

## Key lessons

### 1. Thin wrapper > parallel system

The biggest design decision was making GH-33 a **consumer** of GH-32, not a sibling. `build_storyboard_payload()` calls `assemble_shot_image_prompt()` and layers style/generation/variant concerns on top. This means:
- No duplicate prompt logic
- GH-32 improvements automatically flow through
- The storyboard module owns only what's new: style tokens, variants, frame selection, 16:9 defaults

### 2. Style layer is concatenation, not replacement

Storyboard positive prompt = `{base_positive}, {style_tokens}`. Variant prompt = `{storyboard_positive}, {variant_modifier}`. This additive approach:
- Preserves all semantic content from the assembler
- Makes it trivial to A/B test different style layers
- Keeps each layer independently testable

### 3. Even sampling for reference frames

`_evenly_sample()` always includes first and last items, then fills the middle at equal spacing. This gives better temporal coverage than taking the first N frames. Same pattern already exists in `llm_enricher.py` — a future refactor could extract a shared utility.

### 4. Variant definitions as data, not code

`VARIANT_DEFINITIONS` is a plain list of dicts with `label` and `positive_modifier`. Adding a new variant is one dict append — no code changes needed. Tests verify uniqueness and deterministic ordering.

### 5. All 48 tests passed on first GREEN attempt

The contract was well-specified by the RED phase tests. The assembler's output shape was already stable from GH-32, so the wrapper implementation was straightforward. No iteration between RED→GREEN was needed.

### 6. Airtable fetch reuses validate_prompt_assembler.py pattern

`fetch_enriched_shots_for_storyboard()` uses the same `{AI Prompt Version}!=''` + `FIND(video_id, ARRAYJOIN({Video}))` formula pattern from `scripts/validate_prompt_assembler.py`. The `shot_id` narrowing uses `RECORD_ID()='...'` for precise single-shot retrieval.

### 7. RED phase ImportError is the cleanest signal

Since `publisher/storyboard_handoff` didn't exist, `from publisher.storyboard_handoff import ...` immediately failed with `ModuleNotFoundError`. This is an unambiguous RED — every test in the file is blocked, confirming nothing passes accidentally.

---

## Test count progression

| Phase | Count | Notes |
|-------|-------|-------|
| GH-32 baseline | 37 | `test_prompt_assembler.py` |
| GH-33 iteration 1 | 48 | `test_storyboard_handoff.py` |
| **Combined** | **85** | 0 regressions |

---

## Next steps

- **P0:** Wire a manual validation script (similar to `validate_prompt_assembler.py`) that fetches real enriched shots and prints storyboard payloads for manual review
- **P1:** Implement thin ComfyUI/SDXL generation runner consuming the storyboard payload
- **P1:** Add output directory structure for storyboard image series (by video_id / shot_label / variant)
- **P2:** Cross-shot style consistency, reference-frame ranking, richer presets
