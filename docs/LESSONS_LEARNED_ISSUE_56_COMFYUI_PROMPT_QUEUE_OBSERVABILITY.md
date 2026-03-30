# Lessons Learned — Issue #56: ComfyUI Prompt Queue Observability

**Branch:** `fix/gh-56-comfyui-prompt-queue-observability`
**Date:** 2026-03-19

## What was built

### P0: Submit-time observability in ComfyUI queue path

- `comfyui/comfyui_client.py` now enriches `/prompt` submission failures in `queue_prompt()` with:
  - endpoint context (`/prompt`)
  - HTTP status code
  - sanitized response body snippet (bounded + truncated marker)
  - optional `prompt_id` when available in error payload
  - safe workflow summary (`workflow_nodes`, node `8` and `12` presence)
- Added explicit malformed-success handling in `queue_prompt()`:
  - non-dict success payload surfaced as malformed response with type
  - dict payload missing `prompt_id` surfaced as distinct missing-id error

### P0: Queue-stage context propagation in generation path

- `generate_image()` now wraps queue failures with explicit stage context:
  - `ComfyUI generate_image failed at queue_prompt: ...`
- This cleanly separates submit-time failures from polling and output extraction failures.

### P0: Targeted queue observability tests

- Added `TestComfyUIClientQueueObservability` in `tests/test_storyboard_generator.py` covering:
  - HTTP 400 includes status + `/prompt` + response snippet
  - malformed queue response shape classification
  - missing `prompt_id` classification
  - truncation behavior for long error bodies
- Added `TestComfyUIClientGenerateImageStageContext` for queue-stage failure propagation in `generate_image()`.

## TDD cycle

### RED

- Added 5 focused tests for queue-submit diagnostics and stage context.
- Initial targeted run failed with baseline behavior:
  - HTTP 400 message lacked endpoint/status/body context
  - malformed/missing prompt-id responses raised raw `TypeError`/`KeyError`
  - generation path did not include explicit queue-stage label

### GREEN

- Implemented minimal queue observability and response-shape checks in `queue_prompt()`.
- Added queue-stage wrapping in `generate_image()`.
- Re-ran targeted suite: **41 passed**.

### REFACTOR

- Kept refactor scoped to small helpers in `ComfyUIClient`:
  - `_sanitize_error_snippet()`
  - `_summarize_workflow()`
  - `_extract_prompt_id_from_http_error()`
- This keeps queue logic readable and avoids duplicated formatting.

## Test results

- Targeted regression run:
  - `.venv/bin/python -m pytest tests/test_storyboard_generator.py -q`
  - Result: **41 passed**

## Runtime validation (single real repro)

Command:

```bash
.venv/bin/python scripts/validate_storyboard_handoff.py \
  --video-id 8uP2IrP3IG8 \
  --shot-label S03 \
  --no-dry-run \
  --comfyui-url http://127.0.0.1:8188 \
  --timeout 120 \
  --output-dir ./storyboard_output_gh56_queue_diag
```

Observed outcome:

- Repro now emits actionable submit-time diagnostics for each variant:
  - `status=400`
  - `response_snippet={"error":{"type":"prompt_outputs_failed_validation",...},"node_errors":{"12":...}}<truncated>`
  - `workflow_nodes=10 node_8=present node_12=present`

Bucket classification:

- **Invalid workflow contract / input validation failure at submit time**
  - specifically, ComfyUI reports prompt validation failure with node-level errors for node `12`

Decision for next slice:

- Prioritize workflow-contract validation and/or compatibility guard around node `12` inputs before submit.

## Key lessons

1. **Submit diagnostics must include response content, not only HTTP exception text.**
   Status + bounded response snippet immediately explains why `/prompt` was rejected.

2. **Malformed success payloads should be treated as first-class error modes.**
   Converting raw `TypeError`/`KeyError` into explicit malformed/missing-id errors gives clean operator signals.

3. **Stage labeling prevents bucket confusion.**
   Prefixing generate failures with `queue_prompt` avoids conflating submit failures with poll-time or output-shape failures.

4. **Safe workflow summaries add high signal with low risk.**
   Node count and key-node presence provide contract context without dumping full workflow JSON.

## Files changed

- `comfyui/comfyui_client.py`
- `tests/test_storyboard_generator.py`
- `docs/LESSONS_LEARNED_ISSUE_56_COMFYUI_PROMPT_QUEUE_OBSERVABILITY.md`
