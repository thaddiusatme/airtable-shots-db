# Pipeline Resumption Implementation - Session Prompt

Let's create a new branch for the next feature: **pipeline-resumption**. We want to perform TDD framework with red, green, refactor phases, followed by git commit and lessons learned documentation. This equals one iteration.

## Updated Execution Plan (focused P0/P1)

Implementing stateful pipeline resumption to recover from mid-execution failures without restarting from frame 0. Following GitHub Issue #16 implementation phases.

I'm following the guidance in `docs/GITHUB_ISSUE_PIPELINE_RESUMPTION.md` and TDD best practices (critical path: checkpoint state persistence and capture resumption logic).

## Current Status

**Completed:**
- VLM bypass option implemented (checkbox in extension, flag passed through to analyzer)
- server.js fixed to extract `skipVlm` from request body and pass to orchestrator
- GitHub Issue #16 created with comprehensive implementation spec
- Pipeline successfully runs with `--skip-vlm` flag, reducing runtime from minutes to seconds
- ✅ **TDD Iteration 1 complete** — Checkpoint state persistence + capture resumption
- ✅ `pipeline-state.js` module: `savePipelineState`, `loadPipelineState`, `findExistingFrames`, `calculateStartFrame`, `createInitialState`, `stateFilePath`, `INITIAL_PIPELINE_STATE`
- ✅ 15 unit tests passing (`node:test` + `node:assert/strict`, ~84ms)
- ✅ `orchestrator.js` integrated: state load/save per step, skip completed steps, partial capture tracking on failure
- ✅ Commits: `1065e8f` (feat: checkpoint state persistence), `7eaa9f7` (docs: lessons learned)

**In progress:**
- TDD Iteration 2 — Resume API endpoints and extension UI

**Lessons from TDD Iteration 1 (March 1, 2026):**
- `savePipelineState` auto-updates `updatedAt` — tests must assert `notEqual` to original, not a hardcoded value
- Deep-clone `INITIAL_PIPELINE_STATE` via `JSON.parse(JSON.stringify(...))` to prevent shared-state mutation
- Corrupted JSON graceful recovery: `loadPipelineState` falls back to initial state on parse errors
- Capture failure saves partial progress: catch block counts existing frames before re-throwing
- `node:test` is zero-dep and sufficient for unit tests (no Jest/Mocha needed)
- State file location: `stateFilePath(capturesBase)` allows tracking before capture directory is created

**Lessons from previous iteration:**
- Server-side field extraction matters: Missing `skipVlm` in destructuring caused silent failure
- Always verify data flow: Extension → Server → Orchestrator → CLI args
- Test with actual runs: Terminal logs revealed VLM still running despite checkbox
- Small, focused changes work best: 3 files (popup.html, popup.js, server.js, orchestrator.js)

## P0 — Critical/Unblocker (Pipeline Reliability)

**Checkpoint State Persistence:** ✅ DONE
- ✅ `.pipeline_state.json` schema with step status tracking (not_started, running, completed, failed)
- ✅ `savePipelineState(stateFile, state)` and `loadPipelineState(stateFile, runId)` in `pipeline-state.js`
- ✅ State saved after each step completion (upsert_video, capture, analyze, publish)
- ✅ Error details, timestamps, and progress metrics (framesCompleted, lastFrame)

**Capture Step Resumption:** ✅ DONE
- ✅ `findExistingFrames(captureDir)` scans for existing PNGs (sorted)
- ✅ `calculateStartFrame(existingFrames)` returns frame count as next index
- ✅ Capture command includes `--start-frame N` when resuming
- ✅ Partial capture: failed step records `framesCompleted` + `lastFrame` in state

### Acceptance Criteria:
- ✅ `.pipeline_state.json` created on first pipeline run with all step states
- ✅ State file updated after each step completion with timestamps
- ✅ Capture resumes from last frame + 1 if interrupted
- ⬜ No duplicate frames created when resuming (needs manual test with yt-frame-poc `--start-frame` support)

## P1 — Step Skipping and Recovery (User Experience)

**Skip Completed Steps Logic:** ✅ PARTIALLY DONE
- ✅ Check state file on pipeline start: if step status === 'completed', log skip and continue
- ⬜ Validate step outputs before skipping (e.g., `analysis.json` exists and is valid JSON)
- ⬜ Add `--force-step <stepName>` CLI flag for manual step re-runs
- ⬜ Implement step validation: analyze checks for valid analysis.json, publish checks Airtable records

**Server API for Resumption:**
- `GET /pipeline/resumable` — returns list of failed jobs with captureDir and completedSteps
- `POST /pipeline/resume/:runId` — resets job status and calls runPipeline with state loading
- Extension popup shows "Resume Last Failed Pipeline" if resumable jobs exist
- Poll resumable endpoint on popup open, display resume button conditionally

### Acceptance Criteria:
- Completed steps are skipped on pipeline restart (logged: "Skipping analyze (already completed)")
- Failed pipeline can be resumed via API endpoint with correct runId
- Extension popup detects resumable jobs and shows resume button
- Resume button triggers pipeline from last successful checkpoint

## P2 — Production Hardening (Future Improvements)

**Idempotent Publishing:**
- Query Airtable for existing shots before creating (filterByFormula: Video ID + frame index)
- Update existing shots instead of creating duplicates
- Add shot deduplication in publisher.py

**Checkpoint Cleanup:**
- Auto-expire checkpoints older than 7 days
- Delete `.pipeline_state.json` after successful completion
- Add `--keep-checkpoint` flag to preserve state for debugging

**yt-frame-poc Integration:**
- Submit PR to yt-frame-poc for `--start-frame` flag support
- Handle case where yt-frame-poc doesn't support resumption (graceful fallback)

## Task Tracker

- [Done] Implement checkpoint state schema and persistence helpers
- [Done] Add capture resumption logic with existing frame detection
- [Done] Implement step skipping based on state file (basic: skip completed steps)
- [Pending] Create resume API endpoints (/resumable, /resume/:runId)
- [Pending] Add "Resume Pipeline" button to extension popup
- [Pending] Step output validation before skipping (analysis.json, Airtable records)
- [Pending] Write integration tests for full resumption flow

## TDD Cycle Plan

### Iteration 1: Checkpoint Persistence ✅ COMPLETE

**Red Phase:** 14 failing tests → **Green Phase:** 15 passing → **Refactor:** `createInitialState` helper, `stateFilePath`, `STATE_FILENAME`, corrupted file warning log

**Tests written (15 total in `pipeline-server/test/test_pipeline_state.js`):**
- `savePipelineState` — creates file with schema, overwrites on save, auto-updates `updatedAt`
- `loadPipelineState` — parses existing file, returns initial state when missing, recovers from corrupt JSON
- `findExistingFrames` — returns sorted PNGs, empty for empty/missing dirs
- `calculateStartFrame` — returns 0 for empty, frame count for existing, handles 672 frames
- `INITIAL_PIPELINE_STATE` — has all step keys, all start as `not_started`

### Iteration 2: Resume API + Extension UI (NEXT)

**Red Phase:**
- `test_resumable_endpoint()` — GET /pipeline/resumable returns failed jobs with captureDir
- `test_resume_endpoint()` — POST /pipeline/resume/:runId resets job and triggers pipeline
- `test_resume_non_existent_job()` — returns 400 for unknown runId
- `test_resume_non_failed_job()` — returns 400 for jobs not in error state

**Green Phase:**
- Add `GET /pipeline/resumable` route to `server.js`
- Add `POST /pipeline/resume/:runId` route to `server.js`
- Wire resume to `runPipeline()` with state file loading

**Refactor Phase:**
- Extract job filtering logic
- Add resume status tracking in job object

## Next Action (for next session)

1. **TDD Iteration 2 — Resume API endpoints** in `pipeline-server/server.js`
2. **Write failing tests** for `GET /pipeline/resumable` and `POST /pipeline/resume/:runId`
3. **Implement endpoints** with job filtering and state file loading
4. **Extension UI** — Add "Resume Pipeline" button to `chrome-extension/popup.html` + `popup.js`
5. **Manual test:** Start pipeline, kill mid-capture, use resume endpoint to continue

---

## Files to Reference

**Core Implementation:**
- `pipeline-server/pipeline-state.js` — ✅ State persistence helpers (save/load/find/calculate)
- `pipeline-server/orchestrator.js` — ✅ Pipeline orchestration with state persistence integrated
- `pipeline-server/server.js` — Add resume API endpoints (next iteration)
- `chrome-extension/popup.js` — Add resume button and resumable job polling (next iteration)
- `chrome-extension/popup.html` — Add resume button UI (next iteration)

**Related Docs:**
- `docs/GITHUB_ISSUE_PIPELINE_RESUMPTION.md` — Full implementation spec
- `ISSUE_SHOT_LIST_PIPELINE.md` — Overall pipeline architecture
- `CURRENT_STATE.md` — Updated with progress, test counts, lessons learned

**Testing:**
- `pipeline-server/test/test_pipeline_state.js` — ✅ 15 unit tests for state persistence
- `pipeline-server/test/` — Add integration tests for resume API (next iteration)

## Session Outcomes

**TDD Iteration 1 (March 1, 2026) — COMPLETE:**
- ✅ Checkpoint state file created and updated during pipeline runs
- ✅ Pipeline can detect existing partial captures
- ✅ 15 tests passing for state persistence and frame detection
- ✅ Git commits: `1065e8f` (checkpoint state persistence), `7eaa9f7` (docs + lessons)
- ✅ Lessons learned documented in `CURRENT_STATE.md`
- ✅ Step skipping implemented (completed steps logged and skipped on resume)
- ✅ Partial capture failure records `framesCompleted` + `lastFrame` for recovery

**Expected outcomes for next session (TDD Iteration 2):**
- Resume API endpoints functional (`/pipeline/resumable`, `/pipeline/resume/:runId`)
- Extension popup shows "Resume Pipeline" button for failed jobs
- Integration tests for resume flow
- Git commit + lessons learned
