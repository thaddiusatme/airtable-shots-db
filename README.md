# YouTube Shot List Pipeline

Automated pipeline for extracting, analyzing, and publishing YouTube video shot lists to Airtable with AI-generated descriptions and frame thumbnails.

**Status:** Phase 3 Complete + R2 Image Attachments Working  
**Branch:** `feature/airtable-publisher`

## Quick Start

```bash
# 1. Capture frames (TypeScript - separate repo)
cd /path/to/yt-frame-poc
npm run capture -- --video-id VIDEO_ID --interval 1.0

# 2. Analyze scenes (Python)
cd /path/to/airtable-shots-db
set -a && source .env && set +a
.venv/bin/python -m analyzer --capture-dir /path/to/frames/VIDEO_ID_*/

# 3. Publish to Airtable + R2 (Python)
.venv/bin/python -m publisher \
  --capture-dir /path/to/frames/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  -v
```

## Pipeline Overview

**Three-phase system:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots with R2-hosted images

## Prerequisites

- Python 3.14+ (or 3.9+)
- Node.js 18+ (for frame capture)
- Airtable account with API access
- Cloudflare R2 bucket (for image hosting)
- Ollama with `llama3.2-vision:latest` (for AI descriptions)

## Setup

### 1. Python Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create `.env` in the project root:

```bash
# Airtable
AIRTABLE_API_KEY=patYOUR_PERSONAL_ACCESS_TOKEN
AIRTABLE_BASE_ID=appYOUR_BASE_ID

# Cloudflare R2 (optional, for image uploads)
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-xxx.r2.dev
```

### 3. Ollama Setup

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2-vision:latest
ollama serve  # Runs on localhost:11434
```

## Usage

### Analyze Scenes

```bash
.venv/bin/python -m analyzer \
  --capture-dir /path/to/capture/directory \
  --threshold 10.0 \
  --verbose
```

**Options:**
- `--capture-dir` — Path to directory with manifest.json and frame PNGs
- `--threshold` — Scene boundary detection threshold (default: 10.0)
- `--skip-vlm` — Skip AI descriptions (faster testing)
- `--verbose` — Debug logging

### Publish to Airtable

```bash
set -a && source .env && set +a  # Export env vars
.venv/bin/python -m publisher \
  --capture-dir /path/to/capture/directory \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --verbose
```

**Options:**
- `--capture-dir` — Path to directory with analysis.json
- `--api-key` — Airtable API key (or set `AIRTABLE_API_KEY` env var)
- `--base-id` — Airtable base ID (or set `AIRTABLE_BASE_ID` env var)
- `--dry-run` — Preview without writing to Airtable
- `--skip-images` — Skip R2 image uploads (metadata only)
- `--verbose` — Debug logging

## Testing

```bash
# All tests
.venv/bin/python -m pytest tests/ -v

# Specific module
.venv/bin/python -m pytest tests/test_r2_uploader.py -v

# With coverage
.venv/bin/python -m pytest tests/ --cov=publisher --cov=analyzer
```

**Test Coverage:** 130 tests passing (47 publisher + 8 CLI + 18 r2_uploader + 57 analyzer)

## Project Structure

```
airtable-shots-db/
├── analyzer/           # Scene detection + AI descriptions
├── publisher/          # Airtable + R2 integration
├── tests/              # 130 unit tests (all mocked)
├── .env                # Credentials (gitignored)
├── requirements.txt    # Python dependencies
├── CURRENT_STATE.md    # Detailed status + architecture
└── README.md           # This file
```

## Documentation

- **[CURRENT_STATE.md](./CURRENT_STATE.md)** — Comprehensive project status, architecture, and next steps
- **[ISSUE_SHOT_LIST_PIPELINE.md](./ISSUE_SHOT_LIST_PIPELINE.md)** — Original spec + Phase 1-3 details
- **[ISSUE_SHOT_IMAGE_ATTACHMENTS.md](./ISSUE_SHOT_IMAGE_ATTACHMENTS.md)** — R2 upload implementation

## Airtable Schema

### Videos Table
- Video ID, Platform, Video URL, Thumbnail URL
- Linked to Shots (reverse link)

### Shots Table (1 record per scene)
- Shot Label (S01, S02...), Video (linked)
- Timestamp (sec), Timestamp (hh:mm:ss)
- Transcript Start/End (sec)
- AI Description (Local), AI Model, AI Status
- **Scene Start** (attachment), **Scene End** (attachment) ← R2-hosted images
- Capture Method, Source Device

## Real-Data Validation

**Test Video:** KGHoVptow30 (20 min, 34 scenes)
- ✅ 67 frames uploaded to R2 (1 deduplicated)
- ✅ 34 Shot records created with Scene Start/End thumbnails
- ✅ Idempotent re-runs work correctly

## Next Steps

See **[CURRENT_STATE.md](./CURRENT_STATE.md)** for detailed roadmap. Priority items:

**P0:**
- [ ] End-to-end integration test on fresh video
- [ ] Populate Video metadata (Title, Channel, Duration)
- [ ] Error handling & retry logic

**P1:**
- [ ] Idempotent R2 uploads (HEAD check before upload)
- [ ] R2 cleanup on re-publish
- [ ] Thumbnail generation (resize to 640px)

## License

MIT
