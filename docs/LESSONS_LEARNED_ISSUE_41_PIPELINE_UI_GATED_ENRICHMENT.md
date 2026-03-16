# Lessons Learned — Issue #41: Pipeline UI-Gated Enrichment

**Branch:** `fix/pipeline-ui-gated-enrichment`
**Date:** 2026-03-13

## What was built

### P0: UI/job-gated enrichment wiring

- `pipeline-server/orchestrator.js` now derives publish mode from job input instead of always publishing in plain mode.
- Added `getPublishMode(job)` to compute:
  - `enrichShots`
  - `enrichModel`
  - `forceReenrich` gated by `enrichShots`
- Added `buildPublishStatusMessage(hasR2, publishMode)` so publish status text reflects the actual mode:
  - plain publish when enrichment is off
  - enrichment + model when on
  - enrichment + model + force re-enrich when requested
- Added `buildPublisherArgs(captureDir, hasR2, publishMode)` so `python -m publisher` only receives:
  - `--enrich-shots`
  - `--enrich-model <model>`
  - `--force-reenrich`
  when enrichment is explicitly enabled by job input.

### P1: Upstream contract wiring

- `pipeline-server/server.js` now stores `enrichShots`, optional `enrichModel`, and gated `forceReenrich` on `/pipeline/run` jobs.
- Added `applyResumeInputOverrides(job, body)` so `/pipeline/resume/:runId` applies the same publish-mode contract to resumed jobs.
- `chrome-extension/popup.html` now exposes:
  - `enrichShotsCheckbox`
  - `enrichModelInput`
  - `forceReenrichCheckbox`
- `chrome-extension/popup.js` now sends the publish-mode fields on both `/pipeline/run` and `/pipeline/resume/:runId`.

### Regression coverage

- Added `pipeline-server/test/test_orchestrator_enrichment_gating.js` covering:
  - enrichment disabled => no enrichment argv flags
  - enrichment enabled => `--enrich-shots --enrich-model ...`
  - force re-enrich only when enrichment is enabled
  - publish status text matches the selected mode
- Extended `pipeline-server/test/test_resume_api.js` covering:
  - `/pipeline/run` persists gated enrichment fields on new jobs
  - `forceReenrich` is suppressed when `enrichShots=false`
  - `/pipeline/resume/:runId` applies gated publish-mode overrides to failed jobs

## Test results

- Targeted Node suite passed:
  - `node --test test/test_orchestrator_enrichment_gating.js test/test_resume_api.js`
- Result: **15/15 passing**

## Key lessons

### 1. The authoritative switch belongs in job input, not in orchestrator defaults
The orchestrator should not silently decide to enrich. The correct architecture is for the UI or API caller to set an explicit boolean (`enrichShots`) and optional model override, with the orchestrator acting as a pure contract translator into publisher CLI args.

### 2. `forceReenrich` only has meaning when enrichment is enabled
Allowing `forceReenrich=true` while `enrichShots=false` creates an invalid mixed mode. Gating it at every layer (`popup.js`, `server.js`, `orchestrator.js`) keeps the contract simple and prevents misleading status text or argv combinations.

### 3. Status text is part of the production contract
The RCA signal came from dashboard status showing plain publish text with no enrichment/model mention. That means the status string is not just UX copy; it is an operational diagnostic surface and deserves regression coverage alongside argv assertions.

### 4. Small helpers made the refactor safer
Extracting `getPublishMode()`, `buildPublishStatusMessage()`, and `buildPublisherArgs()` kept the publish-step logic readable and made the test target clear. This was the right amount of refactor after GREEN: small, local, and directly justified by duplicated publish-mode branching.

### 5. Resume flows need the same input normalization as fresh runs
It is easy to fix `/pipeline/run` and forget `/pipeline/resume/:runId`. Using a shared `applyResumeInputOverrides()` helper ensures resumed jobs honor the same gating rules and model defaults as new jobs.

### 6. Targeted `node --test` invocation worked; package test script is currently misconfigured
The focused suite passed when invoked directly with explicit test files. In this checkout, `pipeline-server/package.json` still uses `node --test test/`, which Node treats as a module path rather than expanding test files. This appears to be separate from GH-41 and was left unchanged to keep the iteration scoped.

## Files changed

- `chrome-extension/popup.html`
- `chrome-extension/popup.js`
- `pipeline-server/orchestrator.js`
- `pipeline-server/server.js`
- `pipeline-server/test/test_orchestrator_enrichment_gating.js`
- `pipeline-server/test/test_resume_api.js`

## Next steps

- Live-validate a real extension-triggered pipeline run with enrichment disabled and enabled.
- Confirm the dashboard publish message matches the job input mode in both cases.
- Consider adding a follow-up regression test for disk-reconstructed resume flows if that path becomes a frequent operator path.
- Resume GH-31 audit runs once production-path enrichment is validated end-to-end.
