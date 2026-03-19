# Lessons Learned — Issue #56: ComfyUI Polling Observability

**Branch:** `fix/gh-56-comfyui-polling-observability`
**Date:** 2026-03-18

## What was built

### P0: Polling observability in ComfyUI client

- `comfyui/comfyui_client.py` now includes `_summarize_history_state(history, prompt_id)` to classify poll responses as:
  - `history_state=missing`
  - `history_state=incomplete`
  - `history_state=complete`
  - `history_state=malformed`
- `poll_history(prompt_id, ...)` now tracks `last_summary` and emits timeout errors with:
  - `prompt_id`
  - elapsed time
  - last observed history summary
- `poll_history` request failures now include poll context with:
  - `poll_history`
  - `prompt_id`
  - elapsed time when failure occurred

### P0: Downstream output diagnostics in generation path

- `ComfyUIClient.generate_image()` now reports richer failures when history exists but output extraction fails:
  - no outputs includes serialized `history_status`
  - missing SaveImage output includes `available_output_nodes`
  - empty SaveImage images list is surfaced explicitly

### P0: Regression tests for diagnosis categories

- Added `TestComfyUIClientPollingObservability` in `tests/test_storyboard_generator.py` covering:
  - timeout includes prompt id + incomplete history state details
  - timeout includes prompt id + missing history entry state
  - timeout includes prompt id + malformed history shape state
  - request failures include prompt-scoped polling context

## TDD cycle

### RED

- Added 4 focused polling observability tests.
- Initial run failed 4/4 with baseline behavior:
  - timeout message was generic (`ComfyUI generation exceeded ... timeout`)
  - request failures lacked explicit poll-function context

### GREEN

- Implemented minimal targeted changes in `poll_history()` and `generate_image()`.
- New tests passed after implementation.

### REFACTOR

- Kept refactor limited to one helper (`_summarize_history_state`) to avoid duplicated shape parsing and keep polling loop readable.
- Preserved existing polling behavior (still waits for `status.completed == true`), changing only observability surfaces and error specificity.

## Test results

- Focused RED/green test loop:
  - `.venv/bin/python -m pytest tests/test_storyboard_generator.py -q -k "PollingObservability"`
  - Result: **4 passed** (after green)
- Targeted regression run:
  - `.venv/bin/python -m pytest tests/test_storyboard_generator.py -q`
  - Result: **36 passed**

## Runtime validation (single real repro)

Command:

```bash
.venv/bin/python scripts/validate_storyboard_handoff.py \
  --video-id 8uP2IrP3IG8 \
  --shot-label S03 \
  --no-dry-run \
  --comfyui-url http://127.0.0.1:8188 \
  --timeout 120 \
  --output-dir ./storyboard_output_gh56
```

Observed outcome:

- Generation failed for all variants before polling with:
  - `ComfyUI prompt queue failed: 400 Client Error: Bad Request for url: http://127.0.0.1:8188/prompt`

Interpretation:

- This repro did not enter the `poll_history()` timeout path, so the new polling timeout text was not exercised in this specific run.
- It does provide a clearer next bucket than the original GH-56 symptom in this environment: **prompt submission failure** rather than blind poll timeout.

## Key lessons

1. **Poll-loop observability should be stateful, not static.**
   Capturing only elapsed timeout without the last seen history shape hides whether the job is running, absent, malformed, or stalled.

2. **A small classification helper is enough for high signal.**
   A compact state summarizer (`missing`, `incomplete`, `malformed`, `complete`) gives immediate triage direction without changing control flow.

3. **Prompt-scoped errors are essential for operator workflows.**
   Including `prompt_id` and elapsed time in both timeout and request-failure paths makes multi-shot diagnosis practical.

4. **Real repro can reveal a different failure stage than unit tests target.**
   This run failed at `/prompt` (HTTP 400), indicating the next iteration may need queue submission diagnostics in addition to poll-history diagnostics.

## Files changed

- `comfyui/comfyui_client.py`
- `tests/test_storyboard_generator.py`
- `docs/LESSONS_LEARNED_ISSUE_56_COMFYUI_POLLING_OBSERVABILITY.md`

## Suggested next slice

- Add queue-submission observability for `/prompt` 400 responses (include sanitized response body and relevant workflow validation context) so operator output distinguishes submit-time failures from poll-time stalls.
