# Integrate Frames Table Feature into Chrome Extension Pipeline

## Summary
Add support for the new **Frames table** feature to the chrome extension's full pipeline workflow. The Frames feature creates 1-per-second frame records in Airtable with R2-hosted images, providing granular video timeline navigation.

## Prerequisites

**CRITICAL:** The Frames table must exist in Airtable before running the pipeline with Frame creation enabled.

**Current Status:** ❌ Frames table does NOT exist in the Airtable base yet.

**Action Required:** Add Frames table creation to `setup_airtable.py` with the following schema:

```python
{
    "name": "Frames",
    "description": "Per-second frame captures for video timeline navigation",
    "fields": [{"name": "Frame Key", "type": "singleLineText"}]
}
```

Then add fields:
- **Frame Key** (singleLineText) - Unique key: `{videoId}_t{timestamp:06d}`
- **Video** (multipleRecordLinks → Videos) - Parent video
- **Shot** (multipleRecordLinks → Shots) - Parent shot/scene
- **Timestamp (sec)** (number, precision: 0) - Timestamp in seconds
- **Timestamp (hh:mm:ss)** (singleLineText) - Human-readable timestamp
- **Frame Image** (multipleAttachment) - R2-hosted PNG image
- **Source Filename** (singleLineText) - Original filename from capture

**Verification:** Run `python setup_airtable.py` to create the schema, or manually create the table in Airtable.

## Background
The Frames table feature was implemented in TDD iterations 1-4 (commits `6539a04`, `582db8e`, `4504887`, `7b6343d`) and provides:
- 1 Frame record per second of video (configurable via `--frame-sampling`)
- R2-hosted frame images with public URLs
- Linked to Video + Shot records in Airtable
- Parallel upload support via `--max-concurrent-uploads`
- Idempotent publishing (deletes existing Frames before creating new ones)

Currently, the chrome extension's "Run Full Pipeline" button does NOT create Frame records — it only creates Shots (scene boundaries).

## Current Pipeline Flow (Chrome Extension)

```
popup.js (user clicks "Run Full Pipeline")
  ↓
pipeline-server/server.js (/pipeline/run endpoint)
  ↓
pipeline-server/orchestrator.js (runPipeline function)
  ↓
  Step 1: Upsert Video transcript to Airtable
  Step 2: Capture frames via yt-frame-poc (Playwright)
  Step 3: Analyze scenes via Python analyzer
  Step 4: Publish Shots to Airtable + R2
          └─> python -m publisher --capture-dir ... --segment-transcripts --merge-scenes
```

**Problem:** Step 4 does NOT pass Frame-related flags, so Frames are never created.

## Proposed Changes

### 1. Update `orchestrator.js` Publisher Command (Required)

**File:** `pipeline-server/orchestrator.js` (lines 366-378)

**Current:**
```javascript
await runCommand(pythonBin, [
  '-m', 'publisher',
  '--capture-dir', captureDir,
  '--api-key', process.env.AIRTABLE_API_KEY,
  '--base-id', process.env.AIRTABLE_BASE_ID,
  '--segment-transcripts',
  '--merge-scenes',
  '--verbose',
], { ... });
```

**Proposed:**
```javascript
const publisherArgs = [
  '-m', 'publisher',
  '--capture-dir', captureDir,
  '--api-key', process.env.AIRTABLE_API_KEY,
  '--base-id', process.env.AIRTABLE_BASE_ID,
  '--segment-transcripts',
  '--merge-scenes',
  '--verbose',
];

// Add Frame creation flags if R2 is configured
if (process.env.R2_ACCOUNT_ID && process.env.R2_ACCESS_KEY_ID) {
  // Enable parallel uploads for better performance
  publisherArgs.push('--max-concurrent-uploads', '8');
  
  // Optional: reduce frame density for faster uploads/smaller DB
  // publisherArgs.push('--frame-sampling', '5');  // 1 frame every 5 seconds
}

await runCommand(pythonBin, publisherArgs, { ... });
```

**Impact:** With default settings (sample rate=1, max workers=1), a 3-minute video will create ~180 Frame records. With `--frame-sampling 5`, only ~36 frames.

### 2. Add UI Controls for Frame Settings (Optional - Phase 2)

**File:** `chrome-extension/popup.html`

Add optional controls to the pipeline section:

```html
<!-- After existing pipeline controls -->
<div class="input-group">
  <label>
    <input type="checkbox" id="skipFramesCheckbox" />
    Skip Frame creation (faster, Shots only)
  </label>
</div>

<div class="input-group" id="frameSamplingGroup">
  <label for="frameSampling">Frame Sampling (seconds):</label>
  <input 
    type="number" 
    id="frameSampling" 
    min="1" 
    max="30" 
    value="1" 
    style="width: 60px;"
  />
  <small>1 = every second, 5 = every 5 seconds</small>
</div>
```

**File:** `chrome-extension/popup.js`

Pass through to server:

```javascript
// In runFullPipeline() function, around line 386
const skipFrames = document.getElementById('skipFramesCheckbox').checked;
const frameSampling = parseInt(document.getElementById('frameSampling').value) || 1;

const res = await fetch(`${PIPELINE_SERVER}/pipeline/run`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    videoUrl: `https://www.youtube.com/watch?v=${transcriptData.videoId}`,
    videoId: transcriptData.videoId,
    videoTitle: transcriptData.videoTitle,
    transcript: transcriptData.transcript,
    transcriptSegments: transcriptData.transcriptSegments,
    capture: { interval, maxFrames },
    skipVlm,
    skipFrames,          // NEW
    frameSampling,       // NEW
  }),
});
```

**File:** `pipeline-server/orchestrator.js`

Use the flags:

```javascript
// In runPipeline(), around line 366
if (process.env.R2_ACCOUNT_ID && process.env.R2_ACCESS_KEY_ID && !job.input.skipFrames) {
  publisherArgs.push('--max-concurrent-uploads', '8');
  if (job.input.frameSampling && job.input.frameSampling > 1) {
    publisherArgs.push('--frame-sampling', String(job.input.frameSampling));
  }
}
```

### 3. Update Pipeline Status Messages

**File:** `pipeline-server/orchestrator.js` (line 359)

**Current:**
```javascript
updateStatus('running', 'Publishing shots to Airtable + R2...', 'publish');
```

**Proposed:**
```javascript
const hasR2 = process.env.R2_ACCOUNT_ID && process.env.R2_ACCESS_KEY_ID;
const skipFrames = job.input.skipFrames;
let msg = 'Publishing shots to Airtable';
if (hasR2 && !skipFrames) {
  msg += ' + frames to R2';
} else if (hasR2) {
  msg += ' (R2 images)';
}
updateStatus('running', msg + '...', 'publish');
```

## Implementation Plan

### Phase 0: Schema Setup (REQUIRED FIRST)
**Goal:** Create Frames table in Airtable

- [ ] Add Frames table creation to `setup_airtable.py`
- [ ] Run setup script or manually create Frames table
- [ ] Verify table exists with correct fields

**Estimated time:** 15 minutes  
**Risk:** None - one-time setup

### Phase 1: Minimal Integration (Required)
**Goal:** Enable Frames creation in pipeline with sensible defaults

- [ ] Update `orchestrator.js` publisher command to add `--max-concurrent-uploads 8`
- [ ] Add conditional Frame creation only when R2 is configured
- [ ] Update status messages to reflect Frame creation
- [ ] Test full pipeline end-to-end with a short video (< 1 min)
- [ ] Verify Frames appear in Airtable with R2 image URLs

**Estimated time:** 30 minutes  
**Risk:** Low - only adds CLI flags to existing working pipeline

### Phase 2: User Controls (Optional Enhancement)
**Goal:** Let users customize Frame behavior via popup UI

- [ ] Add `skipFrames` checkbox to popup.html
- [ ] Add `frameSampling` input to popup.html
- [ ] Wire through popup.js → server → orchestrator
- [ ] Add CSS styling for new controls
- [ ] Update popup instructions/tooltips

**Estimated time:** 1-2 hours  
**Risk:** Low - purely additive UI changes

## Testing Checklist

- [ ] **PREREQUISITE:** Verify Frames table exists in Airtable base
- [ ] Run pipeline on short video (30-60s) with R2 configured
- [ ] Verify Frames table populated (expected: ~30-60 records)
- [ ] Verify Frame images load from R2 URLs
- [ ] Verify Frame → Shot → Video links work in Airtable
- [ ] Test with `--skip-frames` flag (should create 0 Frames)
- [ ] Test with `--frame-sampling 5` (should create ~6-12 Frames for 60s video)
- [ ] Test idempotency (re-run pipeline, check old Frames deleted)
- [ ] Test without R2 config (should skip Frames gracefully)

## Performance Considerations

**Frame Upload Time Estimates:**
- 1-minute video @ 1fps + 1 worker = ~60 uploads × ~200ms each = **~12 seconds**
- 1-minute video @ 1fps + 8 workers = ~60 uploads ÷ 8 = **~2 seconds**
- 10-minute video @ 1fps + 8 workers = ~600 uploads ÷ 8 = **~15 seconds**
- 10-minute video @ 5fps (sampling) + 8 workers = ~120 uploads ÷ 8 = **~3 seconds**

**Recommendation:** Default to `--max-concurrent-uploads 8` for good UX.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Long videos (>10 min) create too many Frames | Use `--frame-sampling 5` or `10` by default |
| Upload failures interrupt pipeline | Frames upload uses retry logic (already implemented) |
| R2 costs increase | Monitor R2 storage; frames are small PNGs (~50-400KB each) |
| Airtable API rate limits | pyairtable handles rate limiting automatically |

## Success Criteria

✅ Users can run "Full Pipeline" and Frames are created automatically  
✅ Frame images load correctly in Airtable (R2 URLs work)  
✅ Pipeline completes without errors for typical videos (< 5 minutes)  
✅ Frame creation adds < 30 seconds to pipeline for 5-minute video

## Related Work

- **GitHub Issue #17:** Frames table implementation (TDD iterations 1-4) ✅ DONE
- **Commit `7b6343d`:** Parallel uploads + frame sampling
- **Commit `4504887`:** Publisher integration + idempotency
- **Publisher CLI docs:** See `publisher/cli.py` for all Frame-related flags

## Questions / Decisions Needed

1. **Default frame sampling rate?**
   - Option A: 1 (every second) - max granularity, slower uploads
   - Option B: 5 (every 5 seconds) - faster uploads, still useful
   - **Recommendation:** Start with 1, add UI toggle in Phase 2

2. **Should Frame creation be opt-in or opt-out?**
   - Option A: Opt-in (default OFF, user must check "Create Frames")
   - Option B: Opt-out (default ON, user can check "Skip Frames")
   - **Recommendation:** Opt-out (Phase 1), then add toggle (Phase 2)

3. **Max concurrent uploads default?**
   - **Recommendation:** 8 workers (good balance of speed vs. R2 load)

## Implementation Notes

- All Frame-related logic is already implemented in `publisher/` module
- No Airtable schema changes needed (Frames table exists)
- R2 bucket already configured and working for Shot images
- Extension already has R2 env vars in pipeline server

## Next Steps

1. Implement Phase 1 (minimal integration)
2. Test with existing capture directory (`bjdBVZa66oU`)
3. Run end-to-end pipeline test with fresh video
4. If successful, optionally implement Phase 2 (UI controls)
5. Update chrome extension README with Frames feature documentation
