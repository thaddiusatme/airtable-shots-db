# Closing Comment for GitHub Issue #24: `parse_llm_response()` fails on markdown-fenced JSON from Ollama/llava

## ✅ RESOLVED

`publisher/shot_package.py::parse_llm_response()` now handles Ollama-style JSON responses wrapped in markdown code fences, unblocking structured enrichment writes to Airtable.

## Summary

The root cause was parser strictness, not adapter wiring or prompt structure.

Ollama vision models such as `llava:latest` often return a valid JSON object inside markdown fences like:

```text
```json
{ ... }
```
```

The old parser passed the raw response directly to `json.loads()`, which caused valid structured responses to be treated as invalid JSON. As a result, most enrichment fields were not written to Airtable even though the model had returned the expected keys.

This iteration adds a small normalization step before parsing:

- strip leading/trailing whitespace
- strip outer markdown fences with `json` language tag
- strip outer markdown fences without a language tag
- preserve existing clean-JSON behavior
- preserve `AI Error` behavior for truly malformed responses

## Completed Work

### TDD Iteration: `fix/ollama-markdown-json-parsing`

- ✅ Added RED-phase regression tests in `tests/test_shot_package.py`
- ✅ Confirmed the new markdown-fence cases failed before implementation
- ✅ Added `_normalize_llm_json_response()` in `publisher/shot_package.py`
- ✅ Kept `parse_llm_response(raw_response) -> dict[str, Any]` unchanged
- ✅ Preserved original raw response storage in `AI JSON`
- ✅ Re-ran parser-focused and module-level tests successfully

## Tests Added

New regression coverage in `TestParseLlmResponse`:

- ✅ markdown-fenced JSON with `json` language tag
- ✅ markdown-fenced JSON with leading whitespace
- ✅ markdown-fenced JSON without language tag
- ✅ clean JSON still parses as before
- ✅ invalid non-JSON still returns `AI Error`

## Validation

Targeted test results:

- `tests/test_shot_package.py::TestParseLlmResponse` → **18 passed**
- `tests/test_shot_package.py` → **65 passed**

## Implementation Notes

**Files changed:**

- `publisher/shot_package.py`
- `tests/test_shot_package.py`

**Key design choice:**

The normalization lives in the parser layer, not the Ollama adapter. This keeps provider-specific response formatting concerns out of `publish_to_airtable()` and preserves the existing injected-`enrich_fn` architecture.

## Follow-up

- [ ] Finish real end-to-end validation on a live Airtable run and confirm all 13 enrichment fields are written consistently
- [ ] Re-run the same capture to confirm idempotent skip behavior remains unchanged after the parser hardening
- [ ] Consider a future fallback for models that return prose plus a JSON blob instead of fenced JSON only

## Closing Notes

This fix removes the main blocker discovered during the live Ollama demo: the model was often returning the right structured data in the wrong wrapper. By normalizing the wrapper before parsing, the enrichment pipeline can now accept the common Ollama markdown-fenced response format without changing the adapter, prompt contract, or publisher orchestration.
