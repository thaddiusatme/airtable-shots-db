# Lessons Learned — Issue #38: Structured Outputs + Success Criteria Fix

**Branch:** `fix/gh-38-structured-outputs-success-criteria`
**Commit:** `5bb4f8e`
**Date:** 2025-07-15

## What was built

### P0-A: Ollama Structured Output (JSON Schema)
- **`_build_enrichment_json_schema()`** in `publisher/llm_enricher.py` — generates a JSON Schema from `SHOT_ENRICHMENT_FIELDS` keys
  - All 13 fields listed as `required`
  - `movement` typed as `array` (multi-select); all others `string`
- Ollama request payload now includes:
  - `"format": <json_schema>` — enforces structured JSON output
  - `"options": {"temperature": 0}` — deterministic output

### P0-B: Enrichment Success Criteria Fix
- **`publish.py` enrichment loop** now branches on `"AI Error" in fields`:
  - **Parse failure path:** writes only `AI Error` to Airtable, logs warning, does NOT set `AI Prompt Version` / `AI Updated At` / `AI Model`, does NOT increment `shots_enriched_count`
  - **Success path:** sets all metadata fields, increments count (unchanged behavior)
- This fixes the root cause: failed parses were getting `AI Prompt Version` stamped, marking them as "enriched" and preventing retry

### P1: A/B Test Harness
- **`scripts/ab_enrichment_test.py`** — standalone script comparing model quality:
  - Runs enrichment on all shots in a capture with N models
  - Reports: valid JSON rate, avg fields/shot, avg time, per-field coverage bars, shot-by-shot comparison
  - Supports `--max-shots` for quick runs, `--output-json` for raw data export

### Prompt Version Bump
- `AI_PROMPT_VERSION` bumped `1.1` → `1.2` (structured output contract change triggers automatic re-enrichment of stale shots)

## Test counts
- 6 new in `TestStructuredOutputPayload` (test_llm_enricher.py)
- 6 new in `TestEnrichmentSuccessCriteria` (test_publisher.py)
- **232/232 in-scope pass**, 0 regressions
- 5 pre-existing CLI test isolation flakes unchanged

## Key lessons

### 1. The success criteria bug was a single missing branch
The entire P0-B fix is one `if "AI Error" in fields:` guard. The original code unconditionally stamped `AI Prompt Version` after `parse_llm_response()`, regardless of whether the parse succeeded. This single missing branch caused failed enrichments to be marked as complete, preventing retry on subsequent runs.

### 2. Structured output is an adapter-layer concern, not a parser concern
The `format` JSON schema belongs in `llm_enricher.py` (the Ollama adapter), not in `shot_package.py` (the parser). The parser must still handle malformed responses defensively — structured output reduces but doesn't eliminate parse failures (e.g., Ollama version incompatibility, model not supporting format parameter).

### 3. Deferred import avoids circular dependency
`_build_enrichment_json_schema()` uses `from publisher.shot_package import SHOT_ENRICHMENT_FIELDS` inside the function body, not at module level. This is consistent with the existing pattern in `publish.py` and prevents circular imports between `llm_enricher.py` → `shot_package.py` → `publish.py`.

### 4. Temperature=0 goes in `options`, not top-level
Ollama's `/api/generate` API puts model parameters inside an `options` dict, not at the top level of the payload. The test correctly asserts `payload["options"]["temperature"] == 0`.

### 5. RED phase cleanly separated bug-detection from regression guards
- **6 FAIL in structured output tests** — all `KeyError: 'format'` (payload missing the key)
- **4 FAIL + 2 PASS in success criteria tests** — the 2 passing tests (`test_parse_failure_writes_ai_error`, `test_successful_parse_still_sets_ai_prompt_version`) are backward-compat guards that correctly pass with the old code. The 4 failures catch the actual bug.

### 6. Movement field needs special schema typing
`movement` is the only multi-select field in `SHOT_ENRICHMENT_FIELDS` (the Airtable column accepts arrays). The JSON schema types it as `{"type": "array", "items": {"type": "string"}}` while all other fields are `{"type": "string"}`. This distinction is important for the LLM to produce correctly-typed values.

### 7. A/B harness reuses existing pipeline functions
The harness imports `make_ollama_enrich_fn`, `load_analysis`, `collect_shot_frames`, `build_shot_package`, `build_enrichment_prompt`, and `parse_llm_response` directly. No new abstractions needed — the existing function boundaries are clean enough for reuse.

## Files changed
- `publisher/llm_enricher.py` — `format` + `temperature` in payload, `_build_enrichment_json_schema()`
- `publisher/publish.py` — success criteria branching in enrichment loop
- `publisher/shot_package.py` — `AI_PROMPT_VERSION` bump to `1.2`
- `tests/test_llm_enricher.py` — `TestStructuredOutputPayload` (6 tests)
- `tests/test_publisher.py` — `TestEnrichmentSuccessCriteria` (6 tests)
- `scripts/ab_enrichment_test.py` — A/B test harness (new file)

## Next steps
- Run A/B harness on a real capture: `python scripts/ab_enrichment_test.py --capture-dir <path> --models llava:7b qwen2.5vl:7b --max-frames 4`
- Post results to Issue #38 as an update
- Verify previously-failed enrichments now retry correctly on re-run (AI Prompt Version no longer blocks retry)
- Consider adding `--structured-output` flag to CLI for opt-in/opt-out during model compatibility testing
