# Lessons Learned — GH-33 Pencil Storyboard Handoff

**Branch:** `feature/gh-33-pencil-storyboard-handoff`  
**Base:** `feature/gh-32-image-prompt-contract-v1`  
**Modules:** `publisher/storyboard_handoff.py`, `publisher/storyboard_generator.py`  
**Tests:** `tests/test_storyboard_handoff.py`, `tests/test_storyboard_generator.py`  
**Scripts:** `scripts/validate_storyboard_handoff.py`

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

## Iteration 2 — Generation runner + validation script

### What was built

- **`publisher/storyboard_generator.py`** — thin ComfyUI/SDXL generation runner:
  - `GENERATOR_VERSION = "0.1"` — runner revision tracking
  - `output_path_for_variant(output_dir, video_id, shot_label, variant_label, ext)` — deterministic path builder: `{output_dir}/{video_id}/{shot_label}/{shot_label}_variant_{A|B|C}.{ext}`
  - `generate_shot_storyboard(payload, video_id=, output_dir=, dry_run=, generate_fn=)` — per-shot generation with dry-run JSON or real image output, per-variant error isolation
  - `generate_storyboard_series(series, video_id=, output_dir=, dry_run=, generate_fn=)` — multi-shot orchestrator
  - `make_comfyui_generate_fn(comfyui_url=, timeout=)` — closure-based factory returning a `generate_fn` callable for ComfyUI API
  - `GenerateFn` type alias for the generation callable signature
- **`scripts/validate_storyboard_handoff.py`** — manual validation harness:
  - Fetches enriched shots by video_id from Airtable, builds storyboard series, prints structured output
  - `--dry-run --output-dir` mode writes JSON payloads to structured directories
  - `--json-only` mode for programmatic consumption
  - Summary stats: shots processed, variants generated, avg prompt length, omission count
- **30 tests** in `tests/test_storyboard_generator.py` across 7 test classes
- **115/115 total** (30 generator + 48 storyboard + 37 prompt assembler), 0 regressions

### Key lessons

#### 1. Dependency injection via generate_fn (same pattern as enrich_fn)

`generate_shot_storyboard()` accepts an optional `generate_fn` callable, matching the `enrich_fn` injection pattern from `publish_to_airtable()`. Tests pass a `MagicMock` with `side_effect` that writes dummy files. Production code will pass `make_comfyui_generate_fn()`. No patching of module-level functions needed.

#### 2. Dry-run as the default development path

`dry_run=True` is the default. This means the validation script and tests work without ComfyUI running. The dry-run JSON files contain the full generation payload (positive/negative prompts, dimensions, style, variant label) — enough to manually review or pipe into any generation backend.

#### 3. Per-variant error isolation mirrors per-shot enrichment isolation

The same try/except pattern from `publish_to_airtable()`'s enrichment loop is reused: if `generate_fn` raises for variant A, variants B and C still proceed. Failed variants return `None` in the results list. This is critical for A/B testing — one flaky generation shouldn't block the whole series.

#### 4. Port 99999 is invalid, not unreachable

Initial test used `http://localhost:99999` expecting `ConnectionError`, but `requests` raises `InvalidURL` (port out of range). Fixed to `http://127.0.0.1:19999` — a valid but unlistened port that triggers the correct `ConnectionError` → `RuntimeError` path. Lesson: test infrastructure failures at the right layer.

#### 5. Closure-based factory for ComfyUI adapter

`make_comfyui_generate_fn()` captures `comfyui_url` and `timeout` in closure scope, consistent with `make_ollama_enrich_fn()` in `llm_enricher.py`. Deferred `import requests` inside the factory avoids loading the dependency when generation is off.

#### 6. All 30 tests passed on first GREEN attempt (after port fix)

29/30 passed immediately; the single failure was an infrastructure issue (invalid port), not a logic bug. After fixing the test to use a valid port, all 30 passed without any implementation changes. The contract was well-specified by iteration 1's payload shape.

#### 7. Validation script follows established pattern

`scripts/validate_storyboard_handoff.py` mirrors `scripts/validate_prompt_assembler.py` in structure: argparse CLI, dotenv for Airtable creds, fetch → process → print loop, summary stats. The storyboard version adds `--dry-run` for generation output and prints variant-level detail.

---

## Test count progression

| Phase | Count | Notes |
| ----- | ----- | ----- |
| GH-32 baseline | 37 | `test_prompt_assembler.py` |
| GH-33 iteration 1 | 48 | `test_storyboard_handoff.py` |
| GH-33 iteration 2 | 30 | `test_storyboard_generator.py` |
| **Combined** | **115** | 0 regressions |

---

## Next steps

- **P0:** Run validation script against a real enriched video to confirm end-to-end payload usability
- **P1:** Wire CLI entry point: `python -m publisher.storyboard --video-id VIDEO_ID [--dry-run] [--output-dir DIR]`
- **P1:** Test with real ComfyUI instance — replace placeholder workflow JSON with actual SDXL workflow nodes
- **P2:** Cross-shot style consistency, reference-frame ranking, richer presets
- **P2:** Extract shared `_evenly_sample()` utility from `storyboard_handoff.py` and `llm_enricher.py`
