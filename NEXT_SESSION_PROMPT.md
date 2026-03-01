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

**In progress:**
- Pipeline resumption feature (not started yet)
- Awaiting implementation of checkpoint system in `pipeline-server/orchestrator.js`

**Lessons from last iteration:**
- Server-side field extraction matters: Missing `skipVlm` in destructuring caused silent failure
- Always verify data flow: Extension → Server → Orchestrator → CLI args
- Test with actual runs: Terminal logs revealed VLM still running despite checkbox
- Small, focused changes work best: 3 files (popup.html, popup.js, server.js, orchestrator.js)

## P0 — Critical/Unblocker (Pipeline Reliability)

**Checkpoint State Persistence:**
- Create `.pipeline_state.json` schema with step status tracking (not_started, running, completed, failed)
- Implement `savePipelineState(stateFile, state)` and `loadPipelineState(stateFile, runId)` helper functions in `orchestrator.js`
- Update state after each step completion (upsert_video, capture, analyze, publish)
- Store error details, timestamps, and progress metrics (framesCompleted, framesTotal)

**Capture Step Resumption:**
- Implement `findExistingFrames(captureDir)` to scan for existing PNGs
- Calculate `startFrame` from existing manifest.json or frame count
- Modify capture command to include `--start-frame N` (may require yt-frame-poc changes)
- Handle partial capture scenario: 672 frames exist, resume from 673

### Acceptance Criteria:
- `.pipeline_state.json` created on first pipeline run with all step states
- State file updated after each step completion with timestamps
- Capture resumes from last frame + 1 if interrupted (tested with manual kill)
- No duplicate frames created when resuming from partial capture

## P1 — Step Skipping and Recovery (User Experience)

**Skip Completed Steps Logic:**
- Check state file on pipeline start: if step status === 'completed', log skip and continue
- Validate step outputs before skipping (e.g., `analysis.json` exists and is valid JSON)
- Add `--force-step <stepName>` CLI flag for manual step re-runs
- Implement step validation: analyze checks for valid analysis.json, publish checks Airtable records

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

- [In progress] Implement checkpoint state schema and persistence helpers
- [Pending] Add capture resumption logic with existing frame detection
- [Pending] Implement step skipping based on state file
- [Pending] Create resume API endpoints (/resumable, /resume/:runId)
- [Pending] Add "Resume Pipeline" button to extension popup
- [Pending] Write integration tests for full resumption flow

## TDD Cycle Plan

### Red Phase:
Write failing tests for checkpoint persistence:
- `test_save_pipeline_state()` — creates `.pipeline_state.json` with correct schema
- `test_load_pipeline_state()` — reads existing state file and returns parsed object
- `test_find_existing_frames()` — scans captureDir and returns array of frame filenames
- `test_calculate_start_frame()` — returns correct start frame based on existing frames

### Green Phase:
Minimal implementation to pass tests:
- Create `savePipelineState()` function with `fs.writeFileSync(stateFile, JSON.stringify(state))`
- Create `loadPipelineState()` function with `fs.existsSync()` check and `JSON.parse()`
- Create `findExistingFrames()` function with `fs.readdirSync()` and filter for `.png` files
- Update `runPipeline()` to call `savePipelineState()` after each step

### Refactor Phase:
- Extract state schema into constant `INITIAL_PIPELINE_STATE`
- Add error handling for corrupted state files (try/catch with fallback to initial state)
- Add state validation function to check schema version compatibility
- Extract step execution into `runStep()` wrapper with automatic state saving

## Next Action (for this session)

1. **Create feature branch:** `git checkout -b feature/pipeline-resumption`
2. **Start with checkpoint persistence tests** in `pipeline-server/test/test_pipeline_state.js`
3. **Implement state helpers** in `pipeline-server/orchestrator.js` (savePipelineState, loadPipelineState)
4. **Update runPipeline()** to save state after each step completion
5. **Manual test:** Start pipeline, kill mid-capture, restart and verify state file exists with correct data

Would you like me to implement the checkpoint state persistence now in small, reviewable commits following TDD red-green-refactor?

---

## Files to Reference

**Core Implementation:**
- `pipeline-server/orchestrator.js` — Main pipeline orchestration, add state persistence here
- `pipeline-server/server.js` — Add resume API endpoints
- `chrome-extension/popup.js` — Add resume button and resumable job polling
- `chrome-extension/popup.html` — Add resume button UI

**Related Docs:**
- `docs/GITHUB_ISSUE_PIPELINE_RESUMPTION.md` — Full implementation spec
- `ISSUE_SHOT_LIST_PIPELINE.md` — Overall pipeline architecture
- `.env.example` — Environment variables

**Testing:**
- Create `pipeline-server/test/test_pipeline_state.js` — New test file for state persistence
- Update `pipeline-server/test/` — Add integration tests for resumption

## Expected Outcomes

After this session:
- ✅ Checkpoint state file created and updated during pipeline runs
- ✅ Pipeline can detect existing partial captures
- ✅ Tests passing for state persistence and frame detection
- ✅ Git commits: "Add checkpoint state persistence", "Implement existing frame detection"
- ✅ Lessons learned documented for next iteration
