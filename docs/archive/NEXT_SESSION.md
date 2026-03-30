# Next Session — Recommended Starting Point

**Last Updated:** February 23, 2026  
**Current Branch:** `feature/airtable-publisher`  
**Last Commit:** `768ebb2` (docs: comprehensive documentation cleanup + current state)

---

## Session Summary

**Completed this session:**
- ✅ Phase 3: Airtable Publisher (metadata-only)
- ✅ Phase 3.5: R2 Image Attachments (Scene Start/End thumbnails)
- ✅ Refactored to 1 Shot record per scene (was 2)
- ✅ Added Transcript Start/End fields
- ✅ 130 tests passing (all mocked)
- ✅ Real-data validated: KGHoVptow30, 67 frames → R2, 34 Shot records with thumbnails
- ✅ Documentation cleanup: CURRENT_STATE.md, README.md, issue updates

**Current State:**
- All P0 tasks from ISSUE_SHOT_IMAGE_ATTACHMENTS.md complete
- Pipeline works end-to-end: Capture → Analyze → Publish (with images)
- Ready for production hardening and optimization

---

## Recommended Next Steps (Priority Order)

### Option A: Production Readening (P0 — Must-Have)

**Start here if:** You want to make the pipeline production-ready for regular use.

**Tasks:**
1. **End-to-end integration test** (1-2 hours)
   - Pick a fresh YouTube video (not KGHoVptow30)
   - Run full pipeline: Capture → Analyze → Publish
   - Document any edge cases or failures
   - Validate all 3 phases work together seamlessly
   - **File:** Create `tests/test_integration_e2e.py` (optional, or just manual test + docs)

2. **Populate Video metadata** (30 min)
   - Extract Title, Channel, Duration from `manifest.json`
   - Add to `build_video_fields()` in `publisher/publish.py`
   - Update Airtable Videos table with richer metadata
   - **File:** `publisher/publish.py` (lines 74-89)

3. **Error handling & retry logic** (2-3 hours)
   - Airtable rate limits (5 requests/sec)
   - R2 upload failures (network issues, timeouts)
   - Graceful degradation when Ollama unavailable
   - Add exponential backoff for retries
   - **Files:** `publisher/publish.py`, `publisher/r2_uploader.py`, `analyzer/vlm_describer.py`

**Branch:** Continue on `feature/airtable-publisher` or create `feature/production-hardening`

---

### Option B: Optimization (P1 — Should-Have)

**Start here if:** You want to optimize bandwidth and storage costs.

**Tasks:**
1. **Idempotent R2 uploads** (1 hour)
   - HEAD request before upload to check if file exists
   - Skip upload if same filename already in bucket
   - Saves 13MB bandwidth on re-runs (67 frames × 200KB)
   - **File:** `publisher/r2_uploader.py` (add `check_object_exists()` function)
   - **Tests:** `tests/test_r2_uploader.py` (add HEAD request mocking)

2. **R2 cleanup on re-publish** (1 hour)
   - Delete old frames when Shot records deleted
   - Prevent bucket bloat from repeated testing
   - **File:** `publisher/r2_uploader.py` (add `delete_video_frames()` function)
   - **Integration:** Call before upload in `publish_to_airtable()`

3. **Thumbnail generation** (2 hours)
   - Resize frames to 640px before upload (reduce from ~200KB to ~50KB)
   - Requires `Pillow` dependency
   - Keep originals in `{videoId}/full/` and thumbnails in `{videoId}/thumb/`
   - **File:** `publisher/r2_uploader.py` (add `resize_frame()` function)
   - **Tests:** `tests/test_r2_uploader.py` (mock Pillow)

**Branch:** Create `feature/r2-optimization` from `feature/airtable-publisher`

---

### Option C: Advanced Features (P2 — Nice-to-Have)

**Start here if:** You want to add new capabilities.

**Tasks:**
1. **Batch processing** (2-3 hours)
   - Process multiple videos in one publisher run
   - `--capture-dirs` flag accepting multiple paths
   - Progress bar for multi-video publish
   - **File:** `publisher/cli.py`, `publisher/publish.py`

2. **Shot metadata enrichment** (3-4 hours)
   - Use VLM to extract Camera Angle, Movement, Lighting, etc.
   - Update Ollama prompt to return structured JSON
   - Populate additional Shot fields in Airtable
   - **Files:** `analyzer/vlm_describer.py`, `publisher/publish.py`

3. **Transcript integration** (2-3 hours)
   - Link Chrome extension transcript data to Shot records
   - Match transcript timestamps to scene boundaries
   - Populate "Transcript Line" field
   - **Files:** `publisher/publish.py`, Chrome extension integration

**Branch:** Create feature branches as needed

---

## Quick Commands Reference

### Run Full Pipeline (Manual)

```bash
# 1. Capture frames (TypeScript - separate repo)
cd /Users/thaddius/repos/2-21/yt-frame-poc
npm run capture -- --video-id NEW_VIDEO_ID --interval 1.0 --duration 120

# 2. Analyze scenes (Python)
cd /Users/thaddius/repos/2-20/airtable-shots-db
set -a && source .env && set +a
.venv/bin/python -m analyzer \
  --capture-dir /Users/thaddius/repos/2-21/yt-frame-poc/frames/NEW_VIDEO_ID_*/ \
  --threshold 10.0 \
  -v

# 3. Publish to Airtable + R2 (Python)
.venv/bin/python -m publisher \
  --capture-dir /Users/thaddius/repos/2-21/yt-frame-poc/frames/NEW_VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  -v
```

### Run Tests

```bash
# All tests
.venv/bin/python -m pytest tests/ -v

# Specific module
.venv/bin/python -m pytest tests/test_r2_uploader.py -v

# With coverage
.venv/bin/python -m pytest tests/ --cov=publisher --cov=analyzer
```

### Git Workflow

```bash
# Check current status
git status
git log --oneline -10

# Create new feature branch
git checkout -b feature/production-hardening

# Commit workflow
git add <files>
git commit -m "feat: description"
git push origin feature/production-hardening
```

---

## Known Issues & Gotchas

### Airtable
- **Rate limits:** 5 requests/sec — add delays between batch operations if publishing many videos
- **singleSelect validation:** Must use exact choices (Done/Queued/Processing/Error)
- **Linked record formulas:** Don't work with record IDs — use reverse-link fields

### R2
- **Env var export:** `source .env` doesn't export — use `set -a && source .env && set +a`
- **No deduplication yet:** Re-runs re-upload all frames (13MB for 34 scenes)
- **No cleanup yet:** Old frames accumulate in bucket on re-publish

### OpenCV Scene Detection
- **Threshold calibration:** Default 10.0 works for talking-head videos
- **May need adjustment:** Action scenes, montages, or rapid cuts may need higher threshold

### Ollama VLM
- **Local only:** Requires Ollama running on localhost:11434
- **Slow:** ~8.5s per scene on local hardware
- **No retry logic yet:** Network failures abort the run

---

## Files to Review Before Starting

1. **[CURRENT_STATE.md](./CURRENT_STATE.md)** — Complete project status
2. **[README.md](./README.md)** — Quick-start guide
3. **[ISSUE_SHOT_LIST_PIPELINE.md](./ISSUE_SHOT_LIST_PIPELINE.md)** — Original spec + all phases
4. **[publisher/publish.py](./publisher/publish.py)** — Core publisher logic
5. **[publisher/r2_uploader.py](./publisher/r2_uploader.py)** — R2 upload module

---

## Test Coverage Status

| Module | Tests | Coverage |
|---|---|---|
| analyzer/scene_detector.py | 29 | ✅ High |
| analyzer/vlm_describer.py | 20 | ✅ High |
| analyzer/analyze.py (CLI) | 8 | ✅ High |
| publisher/publish.py | 47 | ✅ High |
| publisher/r2_uploader.py | 18 | ✅ High |
| publisher/cli.py | 8 | ✅ High |
| **Total** | **130** | **All Passing** |

All tests use mocked external APIs (Ollama, Airtable, boto3/R2) — no real API calls in test suite.

---

## Environment Setup Checklist

Before starting work, verify:

- [ ] Python venv activated: `source .venv/bin/activate`
- [ ] `.env` file has all credentials (Airtable + R2)
- [ ] Ollama running: `ollama serve` (if using VLM)
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Tests passing: `.venv/bin/python -m pytest tests/ -v`
- [ ] On correct branch: `git branch` shows `feature/airtable-publisher`

---

## Recommended Session Flow

1. **Review docs** (10 min)
   - Read CURRENT_STATE.md for full context
   - Review this file for recommended tasks

2. **Pick a task** (5 min)
   - Choose Option A, B, or C based on priorities
   - Create feature branch if needed

3. **TDD cycle** (iterative)
   - RED: Write failing tests first
   - GREEN: Implement minimal code to pass
   - REFACTOR: Clean up, extract functions
   - COMMIT: `git commit -m "feat: description"`

4. **Real-data validation** (30 min)
   - Run on fresh video (not KGHoVptow30)
   - Document any issues or edge cases
   - Update CURRENT_STATE.md with findings

5. **Documentation** (15 min)
   - Update CURRENT_STATE.md with new status
   - Update this file for next session
   - Commit docs: `git commit -m "docs: update status"`

---

**Good luck! 🚀**
