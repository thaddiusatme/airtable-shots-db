# Phase 3: Airtable Publisher — Next Session Prompt

Let's create a new branch for the next feature: **Phase 3 Airtable Publisher**. We want to perform TDD framework with red, green, refactor phases, followed by git commit and lessons learned documentation. This equals one iteration.

## Updated Execution Plan (focused P0/P1)

**Brief Context of Current Priorities:**
Phase 2 (Scene Analyzer) is complete and validated on real data. The analyzer produces `analysis.json` with scene boundaries and VLM descriptions. Now we need Phase 3 to read `analysis.json` and publish Shot records to Airtable.

**I'm following the guidance in:**
- `ISSUE_SHOT_LIST_PIPELINE.md` (critical path: Phase 3 Airtable Publisher)
- Existing Airtable schema: Channels → Videos → Shots (26+ fields)
- Existing Chrome extension patterns for Airtable upsert (`chrome-extension/background.js`)

## Current Status

**Completed:**
- Phase 1: Frame capture (Chrome extension + yt-frame-poc CLI) — both working, manifest.json format compatible
- Phase 2: Scene Analyzer (OpenCV + Ollama VLM) — 57 tests passing, validated on real data
  - `analyzer/scene_detector.py`: Pass 1 (histogram chi-squared distance, threshold 10.0)
  - `analyzer/vlm_describer.py`: Pass 2 (Ollama HTTP API, llama3.2-vision)
  - `analyzer/analyze.py`: CLI with --capture-dir, --threshold, --skip-vlm, --verbose
- Real-data validation: 5-minute segment analyzed → 9 scenes with VLM descriptions in ~12 minutes

**In progress:**
- Full video capture + analysis running (KGHoVptow30, ~1192 frames at 1fps)

**Lessons from last iteration:**
- Chi-squared histogram distances on real video: 0–2 (within-scene), 10–3000+ (boundaries). Default threshold 0.5 → 10.0 was critical.
- Mocking `requests.post` isolates VLM tests from running Ollama — all 20 tests run in <0.5s
- Per-scene error handling prevents one bad frame from aborting the entire VLM pass
- Verbose distance logging (`-v`) is essential for threshold tuning on new content
- yt-frame-poc manifest format is compatible with analyzer (minor: `interval` is under `options.interval` not top-level, only affects log message)

## P0 — Critical/Unblocker (Phase 3 Publisher)

**Main P0 Task: Build Airtable Publisher module**
- Read `analysis.json` from capture directory
- Upsert Channel record (if needed) using `videoId` → channel lookup
- Upsert Video record with `videoId`, `videoTitle`, `duration`, `analysisDate`, `totalScenes`
- Create Shot records for each scene:
  - `sceneIndex`, `startTimestamp`, `endTimestamp`
  - `firstFrame`, `lastFrame` (filenames)
  - `description` (VLM output), `transition` (default "cut")
  - Link to parent Video record
- Follow existing pyairtable patterns from Chrome extension background.js

**Secondary P0 Task: CLI integration**
- Add `publisher/publish.py` module with `publish_to_airtable(capture_dir, analysis)` function
- Wire into `analyzer/analyze.py` or create standalone `python -m publisher` CLI
- Support `--api-key` and `--base-id` flags (or read from env vars)
- Add `--dry-run` flag to preview what would be published without writing to Airtable

**Acceptance Criteria:**
- Publisher can read `analysis.json` and create all records in Airtable
- Shot records correctly link to parent Video record
- Idempotent: re-running publisher on same analysis doesn't create duplicates
- CLI returns exit code 0 on success, non-zero on errors
- Tests: unit tests for record building, integration test with mocked Airtable API

## P1 — Publisher Features (Post-MVP)

**P1 Task 1: Image attachment support**
- Upload `firstFrame` and `lastFrame` PNGs as Airtable attachments
- Store in Shot record's `shotImage` field (or similar)
- Consider cloud storage (S3/Cloudflare R2) for large video libraries

**P1 Task 2: Batch operations**
- Process multiple capture directories in one run
- Support glob patterns: `python -m publisher --captures "./frames/**/"`
- Progress reporting for multi-video batches

**P1 Task 3: Update existing records**
- Support `--update` flag to re-analyze and update existing Video/Shot records
- Preserve manual edits to certain fields (e.g., user-curated descriptions)
- Add `lastAnalyzedDate` field to track re-analysis

**Acceptance Criteria:**
- Image attachments visible in Airtable UI
- Batch mode processes 5+ videos without manual intervention
- Update mode preserves user edits while refreshing AI fields

## P2 — Future Improvements (Nice-to-Have)

**P2 Task 1: Chrome extension integration**
- Add "Publish to Airtable" button to extension popup
- Reuse existing Airtable credential storage from settings page
- Trigger Python publisher via local HTTP server or message passing

**P2 Task 2: Scene transition detection**
- Enhance VLM prompt to detect transition types: cut, fade, dissolve, wipe
- Update `transition` field with detected type instead of hardcoded "cut"

**P2 Task 3: Confidence scoring**
- Add `boundaryConfidence` field based on histogram distance magnitude
- Add `descriptionConfidence` if VLM API supports it
- Filter low-confidence scenes for manual review

## Task Tracker

- [In progress] P0.1 — Write failing tests for Airtable publisher (RED phase)
- [Pending] P0.2 — Implement `publisher/publish.py` core functions (GREEN phase)
- [Pending] P0.3 — Wire publisher into CLI (GREEN phase)
- [Pending] P0.4 — Run all tests and fix failures (GREEN phase)
- [Pending] P0.5 — Refactor error handling and logging (REFACTOR phase)
- [Pending] P0.6 — Git commit with descriptive message
- [Pending] P0.7 — Document lessons learned in ISSUE_SHOT_LIST_PIPELINE.md

## TDD Cycle Plan

**Red Phase:**
- Write `tests/test_publisher.py` with tests for:
  - `build_channel_record(analysis)` → returns dict matching Airtable schema
  - `build_video_record(analysis)` → returns dict with all required fields
  - `build_shot_records(analysis)` → returns list of Shot dicts
  - `publish_to_airtable(capture_dir, api_key, base_id)` → mocked pyairtable calls
  - Error handling: missing analysis.json, invalid API key, network errors
- Run tests → expect ModuleNotFoundError (publisher module doesn't exist yet)

**Green Phase:**
- Implement `publisher/publish.py`:
  - `build_channel_record()`, `build_video_record()`, `build_shot_records()`
  - `publish_to_airtable()` using pyairtable Table.create() and Table.update()
  - Error handling with custom `PublisherError` exception
- Wire into CLI: add `--publish` flag to `analyzer/analyze.py` or create `publisher/__main__.py`
- Run all tests → expect 100% passing

**Refactor Phase:**
- Extract Airtable field mapping to constants/config
- Add progress logging for multi-scene publishes
- Add `--dry-run` mode for testing without writing to Airtable
- Update requirements.txt if new dependencies needed

## Next Action (for this session)

**Specific Actionable Task:**
1. Create `publisher/__init__.py` (empty package init)
2. Create `tests/test_publisher.py` with RED phase tests covering:
   - Record building functions (channel, video, shots)
   - Airtable API interaction (mocked with `@patch("publisher.publish.Table")`)
   - Error scenarios (missing files, API failures)
3. Run tests to confirm RED phase (ModuleNotFoundError expected)
4. Review existing Airtable schema in `chrome-extension/background.js` to match field names exactly
5. Check `requirements.txt` for pyairtable version (should already be installed from Chrome extension work)

**Would you like me to implement the RED phase (failing tests) now in small, reviewable commits?**

---

## Context Files to Reference

- `/Users/thaddius/repos/2-20/airtable-shots-db/ISSUE_SHOT_LIST_PIPELINE.md` — Phase 3 spec and Airtable schema
- `/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/background.js` — Existing Airtable upsert patterns
- `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/analyze.py` — CLI structure to mirror
- `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/scene_detector.py` — Example of clean module structure
- `/Users/thaddius/repos/2-20/airtable-shots-db/tests/test_scene_detector.py` — Example test structure to follow
- Real analysis.json example: `/Users/thaddius/repos/2-21/yt-frame-poc/frames/KGHoVptow30_autonomous-ai-agents-have-gone-too-far_2026-02-22_1736/analysis.json`

## Branch Strategy

```bash
# Create new branch from feature/scene-analyzer
git checkout feature/scene-analyzer
git checkout -b feature/airtable-publisher
```

## Environment Setup

- Python venv: `/Users/thaddius/repos/2-20/.venv/`
- Dependencies: pyairtable (already in requirements.txt), pytest
- Airtable credentials: stored in Chrome extension settings (can reuse or pass via CLI flags)
