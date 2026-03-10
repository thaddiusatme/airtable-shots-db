# Phase 2 Completion Summary

## What Was Accomplished

### Phase 2: Scene Analyzer — COMPLETE ✅

**Branch:** `feature/scene-analyzer` at `/Users/thaddius/repos/2-20/airtable-shots-db`

**Commits (6 total):**
1. `1134cad` — Pass 1 (OpenCV scene detection)
2. `65cdccc` — Pass 1 docs
3. `117bfcc` — Pass 2 (Ollama VLM descriptions)
4. `b041f99` — Pass 2 docs
5. `abb241b` — Threshold fix (0.5 → 10.0 for real video)
6. `4073081` — Real-data validation docs

**Test Coverage:** 57 tests passing
- 29 scene_detector tests (unit + integration)
- 8 CLI tests
- 20 VLM tests (all mocked, no live Ollama required)

**Modules Created:**
- `analyzer/__init__.py` — Package init
- `analyzer/__main__.py` — `python -m analyzer` support
- `analyzer/scene_detector.py` — Pass 1: OpenCV HSV histogram chi-squared distance
- `analyzer/vlm_describer.py` — Pass 2: Ollama HTTP API integration
- `analyzer/analyze.py` — CLI entry point

**CLI Usage:**
```bash
# Pass 1 only (fast, no Ollama)
python -m analyzer --capture-dir /path/to/frames/ --skip-vlm -v

# Full pipeline (Pass 1 + Pass 2)
python -m analyzer --capture-dir /path/to/frames/ -v

# Custom threshold
python -m analyzer --capture-dir /path/to/frames/ --threshold 5.0
```

**Output:** `analysis.json` with:
- `videoId`, `totalScenes`, `analysisDate`, `analysisModel`
- `scenes[]` array with `sceneIndex`, `startTimestamp`, `endTimestamp`, `firstFrame`, `lastFrame`, `description`, `transition`

### Real-Data Validation

**Video:** "Autonomous AI Agents Have Gone Too Far!" (KGHoVptow30, 19:52 duration)

**5-Minute Test (300 frames):**
- Pass 1: 11.7s — found 8 scene boundaries
- Pass 2: 711.7s (9 scenes × ~79s/scene)
- Total: ~12 minutes
- VLM descriptions accurately identified UI elements, products (Moltbook AI), Twitter screenshots, and host appearance

**Key Findings:**
- Chi-squared distances on real video: 0–2 (within-scene motion), 10–3000+ (actual cuts)
- Default threshold 0.5 (calibrated for synthetic test frames) → 10.0 (for real video)
- Verbose logging (`-v`) essential for threshold tuning
- VLM quality is high: correctly identified "FUTURE TOOLS" cap, "Moltbook AI chatbot", Twitter feed, purple glow effects

### Integration with yt-frame-poc

**Manifest Compatibility:** ✅ Works end-to-end

The yt-frame-poc CLI (`/Users/thaddius/repos/2-21/yt-frame-poc`) outputs `manifest.json` that the analyzer can read directly. Minor difference: `interval` is under `options.interval` instead of top-level (only affects log message, not analysis).

**Workflow:**
```bash
# Step 1: Capture frames
cd /Users/thaddius/repos/2-21/yt-frame-poc
npx ts-node src/index.ts "YOUTUBE_URL" 1 --max-frames 300

# Step 2: Analyze
cd /Users/thaddius/repos/2-20/airtable-shots-db
/Users/thaddius/repos/2-20/.venv/bin/python -m analyzer \
  --capture-dir /Users/thaddius/repos/2-21/yt-frame-poc/frames/{OUTPUT_DIR} \
  -v
```

## Critical Lessons Learned

### Technical

1. **Threshold Calibration:** Synthetic test frames (solid colors) produce chi-squared distances 0–1. Real video produces 0–3000+. Always validate on real data.

2. **Mocking Strategy:** `@patch("analyzer.vlm_describer.requests.post")` at module level cleanly isolates VLM tests from Ollama server. All 20 tests run in <0.5s.

3. **Error Handling:** Per-scene try/except in `describe_scenes()` prevents one bad frame from aborting the entire run. Failed scenes get `[Error: ...]` descriptions.

4. **Custom Exceptions:** `OllamaError` wraps `ConnectionError`, `Timeout`, and HTTP errors into one type for clean caller code.

5. **Module Separation:** Keeping `scene_detector.py` (OpenCV) and `vlm_describer.py` (HTTP/Ollama) separate preserves single-responsibility. No cross-dependencies.

### Process

1. **TDD RED Phase:** Writing tests that import non-existent modules confirms test harness works before implementation.

2. **Boundary Semantics:** `distances[i]` is between `frame[i]` and `frame[i+1]`, so boundary at distance index `i` means new scene starts at frame `i+1`. Index mapping must be explicit.

3. **Filename Format:** Test fixtures must match real capture format exactly: `frame_00000_t000.000s.png` not `frame_00000_t00.000s.png`.

4. **Venv State:** `requests` was in `requirements.txt` but not installed in venv. Always verify venv matches requirements before running tests.

## What's Next: Phase 3

**Goal:** Airtable Publisher — read `analysis.json` and create Shot records in Airtable

**See:** `PHASE_3_PROMPT.md` for full next-session prompt

**Key Tasks:**
1. Create `publisher/publish.py` module
2. Build functions: `build_channel_record()`, `build_video_record()`, `build_shot_records()`
3. Implement `publish_to_airtable()` using pyairtable
4. Wire into CLI with `--publish` flag or standalone `python -m publisher`
5. Write tests (mocked Airtable API)
6. Follow TDD: RED → GREEN → REFACTOR → commit → docs

**Branch Strategy:**
```bash
git checkout feature/scene-analyzer
git checkout -b feature/airtable-publisher
```

## Current Running Task

**Full Video Capture (In Progress):**
- Video: KGHoVptow30 (~1192 frames at 1fps)
- Command: `npx ts-node src/index.ts "https://www.youtube.com/watch?v=KGHoVptow30" 1`
- Status: Running (at frame 465+ as of last check)
- Next: Run analyzer on full capture once complete
- Output will be in: `/Users/thaddius/repos/2-21/yt-frame-poc/frames/KGHoVptow30_autonomous-ai-agents-have-gone-too-far_2026-02-22_17XX/`

## Environment

- **Python venv:** `/Users/thaddius/repos/2-20/.venv/`
- **Dependencies:** opencv-python, numpy, requests, pytest (all installed)
- **Ollama:** localhost:11434, llama3.2-vision:latest available
- **Node/TypeScript:** yt-frame-poc uses Playwright + system Chrome

## Files to Reference for Phase 3

- `ISSUE_SHOT_LIST_PIPELINE.md` — Phase 3 spec, Airtable schema
- `chrome-extension/background.js` — Existing Airtable upsert patterns
- `analyzer/analyze.py` — CLI structure to mirror
- `tests/test_scene_detector.py` — Test structure example
- Real analysis.json: `/Users/thaddius/repos/2-21/yt-frame-poc/frames/KGHoVptow30_autonomous-ai-agents-have-gone-too-far_2026-02-22_1736/analysis.json`
