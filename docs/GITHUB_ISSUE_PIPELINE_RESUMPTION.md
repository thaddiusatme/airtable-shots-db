# GitHub Issue: Pipeline Resumption and Error Recovery

**Title:** Implement Pipeline Resumption to Resume Failed Runs from Last Successful Step

**Labels:** `enhancement`, `pipeline`, `error-recovery`, `resilience`

**Priority:** P1 - High Impact User Experience

---

## Problem Statement

When the pipeline fails mid-execution (e.g., during frame capture), the entire pipeline must be restarted from the beginning, wasting time and resources. This is particularly problematic for:

1. **Long-running captures** — 100+ frames at 5-second intervals = 8+ minutes of capture time
2. **Playwright timeouts** — `elementHandle.screenshot: Timeout 30000ms exceeded` when Mac sleeps or browser becomes unresponsive
3. **Network failures** — Airtable API errors, R2 upload failures
4. **Resource constraints** — Out of disk space, memory issues

**Current behavior:** Pipeline starts over from step 1 (transcript upsert) even if frames 0-672 were already captured successfully.

**Example failure from user:**
```
[capture] ✓ frame_0672_t072s → frame_00672_t072.000s.png
[capture] Error during capture: elementHandle.screenshot: Timeout 30000ms exceeded.
  - taking element screenshot
  - waiting for fonts to load...
  - fonts loaded
  - attempting scroll into view action
  - waiting for element to be stable
[job:565bc7fa] error at step 'capture': Command exited with code 1
```

**Impact:**
- 672 frames captured successfully (11+ minutes of work)
- Pipeline failed at frame 673
- User must restart from frame 0, re-capturing all 672 frames

---

## Proposed Solution

Implement **stateful pipeline resumption** with checkpoint tracking and step-level recovery.

### Architecture

#### 1. Checkpoint Manifest

Create `{captureDir}/.pipeline_state.json` to track progress:

```json
{
  "runId": "565bc7fa-...",
  "videoId": "abc123",
  "status": "failed",
  "lastSuccessfulStep": "capture",
  "stepStates": {
    "upsert_video": {
      "status": "completed",
      "completedAt": "2026-03-01T12:30:00Z",
      "recordId": "recABC123"
    },
    "capture": {
      "status": "failed",
      "startedAt": "2026-03-01T12:31:00Z",
      "failedAt": "2026-03-01T12:42:15Z",
      "error": "Timeout 30000ms exceeded",
      "framesCompleted": 672,
      "framesTotal": 100,
      "lastFrame": "frame_00672_t072.000s.png"
    },
    "analyze": {
      "status": "not_started"
    },
    "publish": {
      "status": "not_started"
    }
  },
  "createdAt": "2026-03-01T12:30:00Z",
  "updatedAt": "2026-03-01T12:42:15Z"
}
```

#### 2. Step-Level Recovery Logic

**Capture Step (yt-frame-poc):**
- Check for existing frames in `{captureDir}/`
- Read `manifest.json` to get last captured frame index
- Resume from `lastFrameIndex + 1` instead of frame 0
- Pass `--start-frame N` to yt-frame-poc

**Analyze Step (Python analyzer):**
- Check for `{captureDir}/analysis.json`
- If exists and valid → skip to next step
- If partial/corrupted → re-run analysis

**Publish Step (Python publisher):**
- Check which shots already exist in Airtable (query by Video ID + frame index)
- Only publish shots that don't exist yet
- Implement idempotent shot creation

#### 3. Orchestrator Changes

**`orchestrator.js` modifications:**

```javascript
async function runPipeline(job, updateStatus) {
  const stateFile = path.join(job.captureDir || capturesBase, '.pipeline_state.json');
  
  // Load existing state if resuming
  let state = loadPipelineState(stateFile, job.runId);
  
  // Step 1: Upsert Video
  if (state.stepStates.upsert_video.status !== 'completed') {
    await runUpsertVideo(job, updateStatus, state);
    savePipelineState(stateFile, state);
  } else {
    console.log('[orchestrator] Skipping upsert_video (already completed)');
  }
  
  // Step 2: Capture frames
  if (state.stepStates.capture.status !== 'completed') {
    await runCapture(job, updateStatus, state);
    savePipelineState(stateFile, state);
  } else {
    console.log('[orchestrator] Skipping capture (already completed)');
  }
  
  // ... same pattern for analyze and publish
}

async function runCapture(job, updateStatus, state) {
  // Check for existing frames
  const existingFrames = findExistingFrames(job.captureDir);
  const startFrame = existingFrames.length > 0 ? existingFrames.length : 0;
  
  if (startFrame > 0) {
    console.log(`[orchestrator] Resuming capture from frame ${startFrame}`);
    updateStatus('running', `Resuming capture from frame ${startFrame}...`, 'capture');
  }
  
  const captureArgs = [
    'src/index.ts',
    `"${job.input.videoUrl}"`,
    String(job.input.capture.interval),
    '--output', capturesBase,
    '--start-frame', String(startFrame), // NEW FLAG
  ];
  
  // ... run capture with recovery
}
```

#### 4. User-Facing Resume Command

**Chrome Extension:**
- Add "Resume Last Failed Pipeline" button
- Query pipeline server for failed jobs with same videoId
- Show resumable jobs with progress indicator

**Server API:**
```javascript
// GET /pipeline/resumable
app.get('/pipeline/resumable', (req, res) => {
  const resumable = Array.from(jobs.values())
    .filter(j => j.status === 'error' && j.captureDir)
    .map(j => ({
      runId: j.runId,
      videoId: j.input.videoId,
      failedStep: j.step,
      completedSteps: j.completedSteps,
      captureDir: j.captureDir,
    }));
  res.json(resumable);
});

// POST /pipeline/resume/:runId
app.post('/pipeline/resume/:runId', (req, res) => {
  const job = jobs.get(req.params.runId);
  if (!job || job.status !== 'error') {
    return res.status(400).json({ error: 'Job not resumable' });
  }
  
  // Reset job status and resume from last checkpoint
  job.status = 'queued';
  job.error = null;
  runPipeline(job, updateStatus); // Will read .pipeline_state.json
  
  res.json({ resumed: true, runId: job.runId });
});
```

---

## Implementation Phases

### Phase 1: Basic Checkpointing (P0)
- [ ] Create `.pipeline_state.json` tracking
- [ ] Save state after each step completion
- [ ] Log existing state on pipeline start
- **Deliverable:** State tracking infrastructure in place

### Phase 2: Capture Resumption (P0)
- [ ] Add `--start-frame` flag to yt-frame-poc CLI
- [ ] Detect existing frames in `captureDir`
- [ ] Resume from last captured frame + 1
- **Deliverable:** Capture step resumes from partial progress

### Phase 3: Step Skipping Logic (P1)
- [ ] Skip completed steps (upsert_video, analyze, publish)
- [ ] Validate step outputs before skipping (e.g., check `analysis.json` validity)
- [ ] Add `--force-step <stepName>` flag to re-run specific steps
- **Deliverable:** Full pipeline resumption from any step

### Phase 4: UI Integration (P1)
- [ ] "Resume Last Failed Pipeline" button in extension popup
- [ ] Show resumable jobs with progress (e.g., "672/1000 frames captured")
- [ ] `/pipeline/resumable` and `/pipeline/resume/:runId` API endpoints
- **Deliverable:** User can resume failed pipelines from UI

### Phase 5: Idempotent Publishing (P2)
- [ ] Check Airtable for existing shots before creating new ones
- [ ] Update existing shots instead of creating duplicates
- [ ] Add shot deduplication logic (Video ID + frame index)
- **Deliverable:** Publish step can be safely re-run

---

## Testing Strategy

### Unit Tests
- `test_pipeline_state.js` — Load/save state, state validation
- `test_capture_resume.js` — Find existing frames, calculate start frame
- `test_step_skipping.js` — Skip completed steps, validate outputs

### Integration Tests
1. **Happy path:** Full pipeline runs, state saved after each step
2. **Capture failure:** Fail at frame 50, resume from frame 51
3. **Analyze failure:** Fail during analysis, resume skips capture
4. **Publish failure:** Fail during publishing, re-run publishes missing shots only
5. **Manual resume:** User clicks "Resume" button, pipeline continues from checkpoint

### Manual Testing
1. Start pipeline, kill process mid-capture
2. Restart pipeline with same videoId
3. Verify frames 0-N are not re-captured
4. Verify capture resumes from frame N+1

---

## Success Metrics

- **Time saved:** Resuming from frame 672 → saves 11+ minutes of re-capture
- **User experience:** No manual intervention required to resume
- **Reliability:** Pipeline can survive Mac sleep, browser crashes, network issues
- **Idempotency:** Running pipeline twice produces same result (no duplicates)

---

## Related Issues & Docs

- `ISSUE_SHOT_LIST_PIPELINE.md` — Overall pipeline architecture
- Chrome Extension: `chrome-extension/popup.js` — Current pipeline UI
- Pipeline Server: `pipeline-server/orchestrator.js` — Step orchestration
- yt-frame-poc: External dependency (may need --start-frame PR)

---

## Open Questions

1. **Stale checkpoints:** Should we auto-expire checkpoints after N days?
2. **Checkpoint cleanup:** Delete `.pipeline_state.json` after successful run?
3. **Partial frames:** What if frame 672 was partially written (corrupted PNG)?
4. **Version compatibility:** What if pipeline code changes between runs?
5. **Multi-user:** Can two users resume the same failed job?

---

## Workaround (Current)

Until resumption is implemented:
1. **Use smaller `maxFrames`** — 50 frames instead of 100 reduces blast radius
2. **Keep Mac awake** — Use Amphetamine or `caffeinate` during capture
3. **Monitor progress** — Watch terminal logs, stop before timeout
4. **Manual cleanup** — Delete partial `captureDir` before retrying

---

## Update — 2026-03-02: New Capture Timeout Error

**Error:** `page.waitForFunction: Timeout 30000ms exceeded` during `YouTubePlayer.initialize()` — the video metadata never loaded.

```
[orchestrator] $ npx ts-node src/index.ts "https://www.youtube.com/watch?v=2mBZeQ90HT0" 1 --output captures --max-frames 1000
[capture] Navigating to: https://www.youtube.com/watch?v=2mBZeQ90HT0
[capture] Waiting for video element and metadata...
Error during capture: page.waitForFunction: Timeout 30000ms exceeded.
[job:bff76b45] error at step 'capture': Command exited with code 1
```

**Root cause:** yt-frame-poc's `YouTubePlayer.initialize()` waits for `video.readyState >= 1 && video.duration > 0` with a 20s timeout. YouTube can be slow to load depending on network conditions, ad state, or consent dialogs.

**Classification:** This is a **transient** failure — retrying typically succeeds.

### Known Transient Capture Errors
| Pattern | Cause | Retryable |
|---|---|---|
| `Timeout 30000ms exceeded` during `waitForFunction` | Video metadata didn't load in time | ✅ Yes |
| `Timeout 30000ms exceeded` during `elementHandle.screenshot` | Mac sleep / browser unresponsive | ✅ Yes |
| `net::ERR_NETWORK_CHANGED` | Network disconnected | ✅ Yes |
| `net::ERR_INTERNET_DISCONNECTED` | No internet | ✅ Yes (with delay) |
| `Target closed` | Browser crashed | ✅ Yes (restart browser) |
| `Invalid YouTube URL` | Bad video ID | ❌ No — permanent |
| `exceeds video duration` | Seek past end | ❌ No — permanent |

### Implementation Status (2026-03-02)

- [x] Phase 1: Basic Checkpointing — per-video `.pipeline_state_{videoId}.json`
- [x] Phase 2: Capture Resumption — reuse existing capture dir with frames
- [x] Phase 3: Step Skipping — skip completed steps on resume
- [x] Phase 4: UI Integration — Resume button in Chrome extension, `/pipeline/resumable` + `/pipeline/resume` APIs
- [x] Phase 4b: Disk Persistence — resume survives server restart via disk state scanning
- [ ] **Phase 6: Capture Retry Logic** — auto-retry transient errors with exponential backoff

---

**Assignee:** TBD  
**Milestone:** v2.0 - Production Readiness  
**Created:** 2026-03-01  
**Updated:** 2026-03-02
