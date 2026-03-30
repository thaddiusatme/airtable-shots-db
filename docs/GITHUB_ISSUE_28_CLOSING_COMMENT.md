# Closing Comment for GitHub Issue #28: Ollama Model Tag Mismatch — `llava:7b` not found

## ✅ RESOLVED

The CLI default model tag has been corrected from `llava:7b` to `llava:latest`, and a pre-flight model availability check now fails fast before entering the publish loop if the requested model is not installed in Ollama.

## Root Cause

Ollama tags models using `model:tag` format. The locally installed model is `llava:latest` (a 7B parameter model), but the CLI default was hardcoded to `llava:7b` — a tag that does not exist. This caused HTTP 404 errors from Ollama on every enrichment request, which were caught per-request but produced an unclear error message (`Ollama request failed (model=llava:7b): 404 Client Error`).

The mismatch went unnoticed during initial wiring because the first live demo used an explicit `--enrich-model` flag, bypassing the bad default.

## Completed Work

### Commit `aae72af` — fix(gh-28): default model tag + pre-flight check

- **`publisher/cli.py`**: Changed `--enrich-model` default from `llava:7b` to `llava:latest`
- **`publisher/llm_enricher.py`**: Added `verify_ollama_model(model, ollama_url)` function
  - Calls `GET /api/tags` to list installed models
  - Raises `RuntimeError` with the bad model name + list of available models if not found
  - Raises `RuntimeError` with connection diagnostic if Ollama is unreachable
- **`publisher/llm_enricher.py`**: Added `verify_model: bool = False` param to `make_ollama_enrich_fn()`
- Default model in factory also updated to `llava:latest`
- 8 new tests (7 in `TestPreflightModelCheck`, 1 CLI default assertion)

### Commit `0f6045b` — feat(gh-28): wire verify_model=True into CLI

- **`publisher/cli.py`**: When `--enrich-shots` is set, passes `verify_model=True` to `make_ollama_enrich_fn()`
- Pre-flight check runs before `publish_to_airtable()` — fails fast with `rc=1` and clear error
- Updated 2 pre-existing CLI tests to mock `requests.get` for the new pre-flight call
- 2 new tests (`test_enrich_shots_passes_verify_model_true`, `test_enrich_shots_fails_fast_on_bad_model`)

## Tests

| Test File | New Tests | Total in File |
|---|---|---|
| `tests/test_llm_enricher.py` | 7 (pre-flight check) | 27 |
| `tests/test_publisher_cli.py` | 3 (default model + verify wiring + fail-fast) | 13 |
| **New total** | **10** | |
| **Full in-scope suite** | | **235 passing** |

## Validation

```
$ .venv/bin/python -m pytest tests/test_llm_enricher.py tests/test_publisher_cli.py tests/test_publisher.py tests/test_shot_package.py -v
============================= 235 passed in 0.44s ==============================
```

## Error Message Improvement

**Before (per-request, unclear):**
```
Ollama request failed (model=llava:7b): 404 Client Error
```

**After (pre-flight, actionable):**
```
Model verification failed: Model 'llava:7b' not found in Ollama. Available models: llava:latest, llama3.2-vision:latest
```

## Files Changed

- `publisher/cli.py` — default model tag + verify_model wiring + try/except for fail-fast
- `publisher/llm_enricher.py` — `verify_ollama_model()` function + `verify_model` param
- `tests/test_llm_enricher.py` — 7 new pre-flight tests
- `tests/test_publisher_cli.py` — 3 new tests + 2 updated with mock

## Follow-up

- [ ] Live re-validation of 16-shot capture with corrected `llava:latest` default
- [ ] Confirm post-`S10` behavior is resolved (may have been caused by the 404 retry loop)
