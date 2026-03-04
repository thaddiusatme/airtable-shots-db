# YouTube Shot List Pipeline

Automated pipeline for extracting, analyzing, and publishing YouTube video shot lists to Airtable with AI-generated descriptions, frame thumbnails, and per-second frame timeline records.

**Status:** Frames Feature Complete (TDD iterations 1–4) | Pipeline Resumption Complete  
**Tests:** 195 passing (190 Python + 24 Node.js)  
**Open Issues:** [#18 Frames Table Schema](https://github.com/thaddiusatme/airtable-shots-db/issues/18) | [#19 Chrome Extension Integration](https://github.com/thaddiusatme/airtable-shots-db/issues/19)

## Quick Start

```bash
# 1. Start pipeline server (serves Chrome extension)
cd pipeline-server && node server.js

# 2. Or run manually — Capture frames (TypeScript - separate repo)
cd /Users/thaddius/repos/2-21/yt-frame-poc
npx ts-node src/index.ts "https://youtube.com/watch?v=VIDEO_ID" 1.0 --output ../airtable-shots-db/captures/

# 3. Analyze scenes (Python)
cd /path/to/airtable-shots-db
export $(cat .env | xargs)
.venv/bin/python -m analyzer --capture-dir captures/VIDEO_ID_*/ --verbose

# 4. Publish to Airtable + R2 (with Frames)
.venv/bin/python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --segment-transcripts \
  --merge-scenes \
  --max-concurrent-uploads 8 \
  --verbose
```

## Pipeline Overview

**Four-component system:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots + Frames with R2-hosted images
4. **Chrome Extension** → One-click pipeline trigger from YouTube page (via pipeline server)

## Prerequisites

- Python 3.14+
- Node.js 18+ (for frame capture + pipeline server)
- Airtable account with API access (base ID: `appWSbpJAxjCyLfrZ`)
- Cloudflare R2 bucket (bucket: `shot-image`)
- Ollama with `llama3.2-vision:latest` (optional — use `--skip-vlm` to bypass)

## Setup

### 1. Python Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create `.env` in the project root:

```bash
# Airtable
AIRTABLE_API_KEY=patYOUR_PERSONAL_ACCESS_TOKEN
AIRTABLE_BASE_ID=appYOUR_BASE_ID
AIRTABLE_WORKSPACE_ID=wspYOUR_WORKSPACE_ID

# Cloudflare R2 (required for Shot + Frame image uploads)
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# yt-frame-poc path (for pipeline server)
YT_FRAME_POC_PATH=/path/to/yt-frame-poc
```

> **Note:** Use `export $(cat .env | xargs)` to export env vars for Python subprocesses.

### 3. Pipeline Server (Chrome Extension Backend)

```bash
cd pipeline-server
npm install
node server.js  # Runs on http://127.0.0.1:3333
```

### 4. Ollama Setup (optional)

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2-vision:latest
ollama serve  # Runs on localhost:11434
# Use --skip-vlm flag to bypass if Ollama is not running
```

## Usage

### Analyze Scenes

```bash
.venv/bin/python -m analyzer \
  --capture-dir captures/VIDEO_ID_*/ \
  --threshold 10.0 \
  --verbose
```

**Options:**
- `--capture-dir` — Directory with manifest.json and frame PNGs
- `--threshold` — Scene boundary detection threshold (default: 10.0)
- `--skip-vlm` — Skip AI descriptions (faster, no Ollama required)
- `--verbose` — Debug logging

### Publish to Airtable + R2

```bash
export $(cat .env | xargs)
.venv/bin/python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --segment-transcripts \
  --merge-scenes \
  --max-concurrent-uploads 8 \
  --verbose
```

**All Options:**
- `--capture-dir` — Directory with analysis.json
- `--api-key` — Airtable API key (or `AIRTABLE_API_KEY` env var)
- `--base-id` — Airtable base ID (or `AIRTABLE_BASE_ID` env var)
- `--dry-run` — Preview without writing to Airtable
- `--skip-images` — Skip all R2 image uploads
- `--skip-frames` — Skip Frame record creation (Shots only)
- `--segment-transcripts` — Link transcript lines to Shots by timestamp
- `--merge-scenes` — Merge short adjacent scenes into longer shots
- `--min-scene-duration N` — Minimum scene duration in seconds (default: 5.0)
- `--max-concurrent-uploads N` — Parallel R2 upload workers (default: 1, recommended: 8)
- `--frame-sampling N` — Create 1 Frame per N seconds (default: 1)
- `--verbose` / `-v` — Debug logging

## Testing

```bash
# All Python tests
.venv/bin/python -m pytest tests/ -v

# Node.js pipeline server tests
cd pipeline-server && npm test

# Specific Python module
.venv/bin/python -m pytest tests/test_publisher.py -v

# With coverage
.venv/bin/python -m pytest tests/ --cov=publisher --cov=analyzer --cov=segmenter
```

**Test Coverage:** 195 tests (190 Python + 24 Node.js), all passing

| Module | Count |
|--------|-------|
| Publisher (core + frames) | 54 |
| Publisher (CLI) | 11 |
| Publisher (R2 uploader) | 23 |
| Publisher (frame helpers) | 12 |
| Analyzer (scene detector) | 29 |
| Analyzer (CLI) | 8 |
| Analyzer (VLM) | 20 |
| Segmenter (transcript) | 13 |
| Segmenter (scene merger) | 8 + 8 |
| Pipeline State (Node) | 15 |
| Resume API (Node) | 9 |

## Project Structure

```
airtable-shots-db/
├── analyzer/               # Scene detection + AI descriptions
│   ├── scene_detector.py   # OpenCV histogram analysis
│   └── vlm_describer.py    # Ollama VLM integration
├── publisher/              # Airtable + R2 integration
│   ├── publish.py          # Core publisher (Videos, Shots, Frames)
│   ├── r2_uploader.py      # R2 uploads (scenes + all frames, parallel)
│   ├── frame_helpers.py    # Timestamp parsing from filenames
│   └── cli.py              # CLI entry point
├── segmenter/              # Transcript + scene processing
│   ├── transcript_segmenter.py
│   └── scene_merger.py
├── pipeline-server/        # Express orchestrator (Chrome extension backend)
│   ├── server.js           # REST API (:3333)
│   ├── orchestrator.js     # Pipeline steps + state persistence
│   └── pipeline-state.js   # Checkpoint save/load/resume
├── chrome-extension/       # Browser extension for pipeline trigger
├── captures/               # Capture directories (gitignored)
├── tests/                  # 190 Python unit tests (all mocked)
├── .env                    # Credentials (gitignored)
├── requirements.txt        # Python dependencies
└── CURRENT_STATE.md        # Detailed status, architecture, roadmap
```

## Documentation

- **[CURRENT_STATE.md](./CURRENT_STATE.md)** — Full project status, schema, test coverage, roadmap
- **[docs/GITHUB_ISSUE_FRAMES_TABLE_SCHEMA.md](./docs/GITHUB_ISSUE_FRAMES_TABLE_SCHEMA.md)** — Frames table schema spec (GH #18)
- **[docs/GITHUB_ISSUE_FRAMES_CHROME_EXTENSION.md](./docs/GITHUB_ISSUE_FRAMES_CHROME_EXTENSION.md)** — Chrome extension integration (GH #19)
- **[docs/GITHUB_ISSUE_PIPELINE_RESUMPTION.md](./docs/GITHUB_ISSUE_PIPELINE_RESUMPTION.md)** — Pipeline resumption spec (GH #16)

## Airtable Schema

### Videos Table
- Video ID, Platform, Video URL, Thumbnail URL, Thumbnail (Image)
- Transcript (Full), Transcript (Timestamped), Transcript Language, Transcript Source
- Triage Status, Channel (linked)

### Shots Table (1 record per scene)
- Shot Label (S01, S02...), Video (linked)
- Timestamp (sec), Timestamp (hh:mm:ss)
- Transcript Line, Transcript Start/End (sec)
- AI Description (Local), AI Model, AI Status
- **Scene Start** (attachment), **Scene End** (attachment) ← R2-hosted images

### Frames Table ⚠️ PENDING CREATION — [GH #18](https://github.com/thaddiusatme/airtable-shots-db/issues/18)
- Frame Key (`{videoId}_t{timestamp:06d}`), Video (linked), Shot (linked)
- Timestamp (sec), Timestamp (hh:mm:ss)
- **Frame Image** (attachment) ← R2-hosted PNG

## Real-Data Validation

**Test Video:** `bjdBVZa66oU` ("What are Skills?", ~3 min)
- ✅ 34 Shot records created with Scene Start/End thumbnails
- ✅ 34 frames uploaded to R2 with 4 concurrent workers
- ✅ Idempotent re-runs work (existing Shots/Frames deleted before recreating)
- ⚠️ Frame records blocked on Airtable Frames table creation (GH #18)

## Open GitHub Issues

| # | Title | Priority |
|---|-------|----------|
| [#18](https://github.com/thaddiusatme/airtable-shots-db/issues/18) | Create Frames Table Schema in Airtable | **P0 — Blocks Frames feature** |
| [#19](https://github.com/thaddiusatme/airtable-shots-db/issues/19) | Integrate Frames into Chrome Extension Pipeline | P1 — Blocked by #18 |
| [#17](https://github.com/thaddiusatme/airtable-shots-db/issues/17) | Feature: Publish 1fps Frames to Airtable | ✅ Code complete |
| [#16](https://github.com/thaddiusatme/airtable-shots-db/issues/16) | Implement Pipeline Resumption | ✅ Complete |
| [#12](https://github.com/thaddiusatme/airtable-shots-db/issues/12) | Simplify end-to-end CLI | Future |
| [#15](https://github.com/thaddiusatme/airtable-shots-db/issues/15) | Azure cloud VLM pipeline | Future |

## License

MIT
