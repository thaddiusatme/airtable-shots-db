# YouTube Shot List Pipeline: Capture → Analyze → Airtable

## Summary

Implement a three-stage pipeline to create a "shot list" for YouTube videos:
1. **Capture**: Add screenshot capture feature to existing Chrome extension (1fps frames)
2. **Analyze**: Build Python scene analyzer using OpenCV (fast pre-filter) + Ollama VLM (boundary frame descriptions)
3. **Publish**: Write curated scene shots (first + last frame per scene) to Airtable

This enables creating structured shot lists with AI-generated scene descriptions, all within the Free plan's 1,000 record limit (~12–33 videos).

## Context

- **Chrome extension** already exists at `/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/` with working transcript extraction, Airtable upsert patterns, and settings page
- **Airtable base** is set up with normalized schema: Channels → Videos → Shots (26+ fields including AI fields)
- **yt-frame-poc CLI** (`/Users/thaddius/repos/2-21/yt-frame-poc/`) already captures 1fps screenshots and generates manifest.json
- **Ollama** is installed locally with `llama3.2-vision:latest` (7.8 GB) already pulled
- **Python env** at `/Users/thaddius/repos/2-20/.venv/` has pyairtable, FastAPI, requests, etc.

## Architecture

```
CAPTURE                      ANALYZE                       PUBLISH
(extension or CLI)           (Python worker)               (Python → Airtable)

┌──────────────┐  local fs   ┌───────────────────┐         ┌─────────────┐
│ Extension:   │────────────→│ Pass 1: OpenCV    │         │ Airtable    │
│ new "Capture │  PNGs +     │  histogram diff   │         │ Channels    │
│ Shots" tab   │  manifest   │  (~2s / 1800 frm) │         │ Videos      │
│ in popup     │             │                   │         │ Shots       │
├──────────────┤             │ Pass 2: Ollama    │────────→│ (first+last │
│ CLI:         │────────────→│  llama3.2-vision  │         │  per scene) │
│ yt-frame-poc │             │  ~20-50 boundary  │         └─────────────┘
└──────────────┘             │  frames only      │
                             │  (~5-25 min)      │
                             └───────────────────┘
                                  raw frames
                                  deleted after
```

## Phase 1: Chrome Extension — Screenshot Capture ✅

> **Status**: Implemented on branch `feature/screenshot-capture` (commit `51919ec`, 2026-02-22)
> **Manually tested**: Frames saved to Downloads folder successfully.

### Changes to existing files

**manifest.json** ✅
- Added `downloads` permission for saving PNGs locally

**popup.html** ✅
- Added "Capture Shots" section below transcript section
- Interval input (default: 1 sec, min 0.5)
- Max screenshots input (default: 100)
- Start / Stop Capture button
- Status display: `Captured: 0 / 100`
- "Open captures folder" link after capture completes

**popup.js** ✅
- Sends `startCapture` / `stopCapture` messages to content script
- Tracks progress via `chrome.runtime.onMessage` listener
- Downloads frames via `chrome.downloads.download()` API
- UI state management (disable inputs during capture, show/hide buttons)

**content.js** ✅
- On `startCapture`: finds `<video>` element, starts interval timer
- Each tick: `canvas.drawImage(video)` → `canvas.toBlob()` → base64 data URL → sends to popup for download
- On `stopCapture` or max reached: stops timer, generates manifest.json, downloads it
- Filename format: `frame_{index}_t{timestamp}s.png`

### Implementation notes

- Used base64 data URLs to bridge content script → popup (content scripts can't call `chrome.downloads` directly)
- Reused existing message-passing pattern (`chrome.tabs.sendMessage` / `chrome.runtime.onMessage`)
- Transcript extraction left completely untouched — capture is a separate code path

### Output format

```
~/Downloads/yt-captures/
  {videoId}_{datetime}/
    frame_00000_t000.000s.png
    frame_00001_t001.000s.png
    ...
    manifest.json
```

### What stays unchanged
- Existing transcript extraction
- Settings page and Airtable credential storage
- Channel/Video upsert logic (will be reused in Stage 3)

## Phase 2: Scene Analyzer (Python)

> **Pass 1 Status**: Implemented on branch `feature/scene-analyzer` (commit `1134cad`, 2026-02-22)
> **Tests**: 37 passing (29 unit + 8 CLI integration)
> **Lessons learned**:
> - TDD RED phase: writing tests first that import from non-existent module confirms the test harness works before any implementation
> - Boundary semantics require careful index mapping: `distances[i]` is between `frame[i]` and `frame[i+1]`, so a detected boundary at distance index `i` means a new scene starts at frame `i+1`
> - HSV histogram chi-squared distance on solid-color test frames produces clean 0.0 (identical) vs large positive (different) — good for deterministic test assertions
> - Filename format string `{i:07.3f}` (not `{i:06.3f}`) matches the real Phase 1 output `t000.000s` — fixture format must match manifest format exactly
> - `build_analysis()` takes scene-start frame indices (not raw distance indices) — keeps the API clean and delegates the index+1 conversion to the caller (CLI)
> - Pass 2 VLM is cleanly stubbed: `--skip-vlm` flag, `description: null` / `transition: null` in output — ready for P1 implementation

New module in `airtable-shots-db/analyzer/` with two-pass strategy:

**Pass 1 — OpenCV histogram comparison (~2 seconds for 1800 frames)**
- Load consecutive PNG pairs
- Convert to HSV, compute histogram, chi-squared distance
- Flag frames where distance > threshold (~0.4–0.6) as scene boundaries
- Output: list of candidate boundary timestamps

**Pass 2 — Ollama VLM on boundary frames only (~5–25 min)**
- Send only candidate boundary frames to `llama3.2-vision:latest` via Ollama HTTP API (`localhost:11434`)
- Prompt: describe the scene, classify transition type
- ~20–50 calls × 10–30 sec each

### Time estimates (36GB MacBook Pro Max)

| Video length | Raw frames | CV pass | VLM calls | Total |
|---|---|---|---|---|
| 5 min | 300 | <1s | ~10–15 → 2–5 min | ~3–6 min |
| 15 min | 900 | ~1s | ~15–30 → 5–15 min | ~6–16 min |
| 30 min | 1800 | ~2s | ~25–50 → 8–25 min | ~9–27 min |

### Queue worker

- Uses `watchdog` (Python) to watch captures directory for new `manifest.json` files
- Auto-triggers Pass 1 + Pass 2 when a new capture lands
- Writes: `{capture_dir}/analysis.json`
- Status tracking: `queued` → `analyzing` → `done` / `error`

### Analysis output format

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

## Phase 3: Airtable Publisher (Python)

New module in `airtable-shots-db/publisher/`:
- Reads `analysis.json`
- Looks up or creates Video record by Video ID
- Creates Shot records for each scene boundary (first + last frame)
- Writes fields: Shot Label, Video (linked), Timestamp (sec), Timestamp (hh:mm:ss), AI Status, AI Description (Local), AI Model, Captured At
- Defers Shot Image attachment to later phase (needs cloud storage URL)

### Airtable budget (Free plan, per video)

| Item | Count |
|---|---|
| API calls (Video lookup + Shot batch creates) | ~5–10 |
| Shot records created | ~30–80 |
| Monthly API budget used (per video) | ~1% of 1,000 |

## Phase 4: yt-frame-poc alignment (later)

- Fix `ShotRecord` type + `publishShots()` to match real Airtable schema
- Ensure CLI output lands in same captures directory the analyzer watches

## Phase 5: Cloud storage for Shot Image attachments (later)

- Upload boundary frame PNGs to S3/GCS
- Write URL to `Shot Image` attachment field in Airtable

## Acceptance Criteria

- [x] Phase 1: Chrome extension captures frames at configurable interval, generates manifest.json, downloads to local folder
- [ ] Phase 2: Analyzer detects scene boundaries via OpenCV, generates analysis.json with VLM descriptions
- [ ] Phase 3: Publisher reads analysis.json, creates Shot records in Airtable with linked Video
- [ ] End-to-end test: capture → analyze → publish workflow produces curated shot list in Airtable
- [ ] Free plan budget respected: ~12–33 videos before hitting 1,000 record limit

## Implementation Notes

- Keep repos separate: airtable-shots-db owns extension + analyzer + publisher; yt-frame-poc stays as CLI tool
- Both tools output to same `manifest.json` format
- Default captures directory: `~/yt-captures/` (configurable)
- Add to requirements.txt: `opencv-python`, `ollama`, `watchdog`
