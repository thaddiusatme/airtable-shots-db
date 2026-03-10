# Next Chat Prompt Template: YouTube Shot List Pipeline — Phase 2

## The Prompt

Let's create a new branch for the next feature: **Scene Analyzer (OpenCV + Ollama VLM)**. We want to perform TDD framework with red, green, refactor phases, followed by git commit and lessons learned documentation. This equals one iteration.

### Updated Execution Plan (focused P0/P1)

**Brief Context**: Implementing Phase 2 of the YouTube Shot List Pipeline — building a Python scene analyzer that reads captured frames from Phase 1 and detects scene boundaries. Two-pass strategy: Pass 1 uses OpenCV histogram comparison for fast pre-filtering (~2s for 1800 frames), Pass 2 sends only boundary frames to Ollama VLM for descriptions (~5–25 min). Output is `analysis.json` consumed by Phase 3 (Airtable Publisher).

**I'm following the guidance in**: TDD (red-green-refactor), small reviewable commits, and the architecture defined in `ISSUE_SHOT_LIST_PIPELINE.md`.

**Critical path**: Get Pass 1 (OpenCV scene boundary detection) producing correct `analysis.json` before wiring up Pass 2 (Ollama VLM descriptions).

### Current Status

**Completed**:
- Phase 1: Chrome Extension Screenshot Capture (`feature/screenshot-capture` branch, commit `51919ec`)
  - Frames saved to `~/Downloads/yt-captures/{videoId}_{datetime}/` ✅
  - manifest.json generated with correct metadata ✅
  - Existing transcript extraction unaffected ✅
- Architecture planning and GitHub issue specification (`ISSUE_SHOT_LIST_PIPELINE.md`)

**In progress**:
- Phase 2: Scene Analyzer (Python)
  - New module to create: `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/`
  - Python venv exists at `/Users/thaddius/repos/2-20/.venv/` with pyairtable, requests, etc.
  - Needs new deps: `opencv-python`, `ollama` (add to `requirements.txt`)

**Lessons from last iteration**:
- Used base64 data URLs to bridge content script → popup for `chrome.downloads` (content scripts can't call `chrome.downloads` directly).
- Reusing existing patterns (message passing, DOM interaction) kept the implementation clean and avoided breaking transcript extraction.
- manifest.json format is: `{ videoId, videoTitle, captureDate, interval, frames: [{ index, timestamp, filename }] }` — the analyzer must read this format.
- Keep each phase's output as a standalone JSON file so phases are loosely coupled (manifest.json → analysis.json → Airtable).

### P0 — Critical/Unblocker (Phase 2: Scene Analyzer — Pass 1)

**Main Task: Build OpenCV histogram-based scene boundary detection**

1. **Create `analyzer/` module**: New directory at `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/` with `__init__.py`, `scene_detector.py`, `analyze.py` (CLI entry point)
2. **Implement `scene_detector.py`**: Load consecutive PNG pairs from a capture directory, convert to HSV, compute histograms, calculate chi-squared distance between consecutive frames, flag frames where distance > threshold (~0.4–0.6) as scene boundaries
3. **Implement `analyze.py` CLI**: Accept `--capture-dir` argument (path to a `{videoId}_{datetime}/` folder), read `manifest.json`, run Pass 1, output `analysis.json` to the same directory
4. **Add dependencies**: Add `opencv-python` to `requirements.txt`
5. **Write tests**: Unit tests for histogram comparison, boundary detection, and manifest parsing

**Acceptance Criteria**:
- [ ] `python -m analyzer.analyze --capture-dir ~/Downloads/yt-captures/{videoId}_{datetime}/` runs without errors
- [ ] Reads `manifest.json` from the capture directory and loads frame PNGs
- [ ] Detects scene boundaries using OpenCV histogram chi-squared distance
- [ ] Outputs `analysis.json` with correct scene boundary data (sceneIndex, startTimestamp, endTimestamp, firstFrame, lastFrame)
- [ ] Configurable threshold via `--threshold` flag (default 0.5)
- [ ] Unit tests pass for histogram comparison, boundary detection, and manifest parsing

### P1 — Pass 2: Ollama VLM Descriptions (Phase 2 completion)

**Task 1: Add Ollama VLM integration**
- Send only boundary frames (first + last per scene) to `llama3.2-vision:latest` via Ollama HTTP API (`localhost:11434/api/generate`)
- Prompt: "Describe this video frame in one sentence. What is the scene showing?"
- Parse response, write `description` and `transition` fields into each scene in `analysis.json`

**Task 2: Add `--skip-vlm` flag**
- Allow running Pass 1 only (fast, no Ollama dependency) for testing
- Default behavior: run both passes

**Task 3: Add progress logging**
- Log Pass 1 progress: `[Pass 1] Processing frame 150/1800...`
- Log Pass 2 progress: `[Pass 2] Describing boundary 5/30 (frame_00045_t045.000s.png)...`
- Log timing: `[Pass 1] Complete in 1.8s — found 28 scene boundaries`

**Acceptance Criteria**:
- [ ] `analysis.json` includes `description` field for each scene (from Ollama VLM)
- [ ] `--skip-vlm` flag produces `analysis.json` without descriptions (Pass 1 only)
- [ ] Ollama errors are handled gracefully (timeout, connection refused, model not found)
- [ ] Progress logging shows frame-by-frame and boundary-by-boundary status

### P2 — Future Improvements (deferred to later iterations)

**Task 1**: Queue worker using `watchdog` to auto-trigger analysis on new captures
**Task 2**: Configurable VLM model (not hardcoded to `llama3.2-vision:latest`)
**Task 3**: Batch VLM requests for better throughput
**Task 4**: Add `--cleanup` flag to delete raw frames after analysis

### Task Tracker

- [ ] **In progress**: Create `analyzer/` module with Pass 1 (OpenCV scene detection)
- [ ] **Pending**: Write unit tests for histogram comparison and boundary detection
- [ ] **Pending**: Add Pass 2 (Ollama VLM descriptions)
- [ ] **Pending**: Test end-to-end with real captured frames from Phase 1
- [ ] **Pending**: Git commit with lessons learned
- [ ] **Pending**: Phase 3 (Airtable Publisher) — publish shots to Airtable
- [ ] **Pending**: Phase 4 (yt-frame-poc alignment) — fix CLI publisher schema
- [ ] **Pending**: Phase 5 (Cloud storage) — upload Shot Image attachments

### TDD Cycle Plan

**Red Phase**:
- Write test that loads a `manifest.json` and returns parsed frame list
- Write test that computes histogram distance between two PNG frames and returns a float
- Write test that given a list of distances and a threshold, returns correct boundary indices
- Write test that `analysis.json` output matches expected schema

**Green Phase**:
- Implement `load_manifest(capture_dir)` → parsed dict with frame list
- Implement `compute_histogram_distance(frame_a_path, frame_b_path)` → float
- Implement `detect_boundaries(distances, threshold)` → list of boundary indices
- Implement `build_analysis(manifest, boundaries)` → analysis dict
- Implement `write_analysis(capture_dir, analysis)` → writes `analysis.json`

**Refactor Phase**:
- Extract histogram computation into reusable helper
- Add type hints and dataclasses for Manifest, Frame, Scene, Analysis
- Add error handling for missing frames, corrupt PNGs, empty capture directories
- Add logging with configurable verbosity

### Next Action (for this session)

**Specific actionable task with file references**:

1. Create `analyzer/__init__.py` (`/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/__init__.py`): Empty init
2. Create `analyzer/scene_detector.py` (`/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/scene_detector.py`): Core functions — `load_manifest()`, `compute_histogram_distance()`, `detect_boundaries()`, `build_analysis()`
3. Create `analyzer/analyze.py` (`/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/analyze.py`): CLI entry point with `--capture-dir`, `--threshold`, `--skip-vlm` flags
4. Create `tests/test_scene_detector.py` (`/Users/thaddius/repos/2-20/airtable-shots-db/tests/test_scene_detector.py`): Unit tests for all core functions
5. Update `requirements.txt` (`/Users/thaddius/repos/2-20/airtable-shots-db/requirements.txt`): Add `opencv-python`

Would you like me to implement these changes now in small, reviewable commits?

---

## Reference Information

**Repo paths**:
- Analyzer (this phase): `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/` (to be created)
- Extension (Phase 1, done): `/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/`
- Publisher (Phase 3): `/Users/thaddius/repos/2-20/airtable-shots-db/publisher/` (to be created)
- CLI capture: `/Users/thaddius/repos/2-21/yt-frame-poc/`
- Python venv: `/Users/thaddius/repos/2-20/.venv/`

**Key files**:
- Issue spec: `/Users/thaddius/repos/2-20/airtable-shots-db/ISSUE_SHOT_LIST_PIPELINE.md`
- Existing requirements: `/Users/thaddius/repos/2-20/airtable-shots-db/requirements.txt`
- Phase 1 branch: `feature/screenshot-capture` (commit `51919ec`)

**Input format** (from Phase 1 capture):

```
~/Downloads/yt-captures/
  {videoId}_{datetime}/
    frame_00000_t000.000s.png
    frame_00001_t001.000s.png
    ...
    manifest.json
```

**manifest.json format** (input to analyzer):

```json
{
  "videoId": "dQw4w9WgXcQ",
  "videoTitle": "Rick Astley - Never Gonna Give You Up",
  "captureDate": "2026-02-22T15:30:00Z",
  "interval": 1.0,
  "frames": [
    {
      "index": 0,
      "timestamp": 0.0,
      "filename": "frame_00000_t000.000s.png"
    },
    {
      "index": 1,
      "timestamp": 1.0,
      "filename": "frame_00001_t001.000s.png"
    }
  ]
}
```

**analysis.json format** (output from analyzer, input to Phase 3 publisher):

```json
{
  "videoId": "dQw4w9WgXcQ",
  "scenes": [
    {
      "sceneIndex": 0,
      "startTimestamp": 0.0,
      "endTimestamp": 12.0,
      "firstFrame": "frame_00000_t000.000s.png",
      "lastFrame": "frame_00012_t012.000s.png",
      "description": "Wide establishing shot of a brick building exterior",
      "transition": "cut"
    }
  ],
  "totalScenes": 15,
  "analysisModel": "llama3.2-vision:latest",
  "analysisDate": "2026-02-22T14:30:00Z"
}
```

**Existing Python environment** (`/Users/thaddius/repos/2-20/.venv/`):
- pyairtable 3.3.0, requests 2.32.5, pydantic 2.12.5, python-dotenv 1.2.1
- Needs: `opencv-python`, `ollama` (for Pass 2)

**Ollama setup** (already installed):
- Model: `llama3.2-vision:latest` (7.8 GB, already pulled)
- API: `http://localhost:11434/api/generate`
- Accepts base64-encoded images in the `images` field
