# YouTube Shot List Pipeline

Automated pipeline for extracting, analyzing, publishing, and storyboarding YouTube video shot lists — Airtable as the data store, AI enrichment via Ollama/Gemini, and ComfyUI for pencil storyboard panel generation.

**Status:** Frames ✅ | LLM Enrichment ✅ | Gemini Provider ✅ | Storyboard Generation ✅ | IPAdapterAdvanced Wiring ✅
**Tests:** ~590 passing (539 Python + 51 Node.js)
**Current Focus:** Live ComfyUI end-to-end storyboard run; GH-40 GitHub post; GH-53 branch merge

## Quick Start

```bash
# 1. Start pipeline server (serves Chrome extension)
cd pipeline-server && node server.js

# 2. Or run manually — Capture frames (TypeScript - separate repo)
cd /Users/thaddius/repos/2-21/yt-frame-poc
npx ts-node src/index.ts "https://youtube.com/watch?v=VIDEO_ID" 1.0 --output ../airtable-shots-db/captures/

# 3. Analyze scenes (Python)
cd /path/to/airtable-shots-db
set -a && source .env && set +a
python -m analyzer --capture-dir captures/VIDEO_ID_*/ --verbose

# 4. Publish to Airtable + R2 (with Frames)
python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --segment-transcripts \
  --merge-scenes \
  --max-concurrent-uploads 8 \
  --verbose

# 5. Optional: publish with shot enrichment
python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --skip-frames \
  --enrich-shots \
  --enrich-model llava:latest \
  --verbose

# 6. Optional: enrich with Gemini instead of Ollama
python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --skip-frames \
  --enrich-shots \
  --enrich-provider gemini \
  --enrich-model gemini-2.5-flash \
  --gemini-api-key "$GEMINI_API_KEY" \
  --verbose

# 7. A/B test model comparison (Ollama vs Gemini)
python scripts/ab_enrichment_test.py \
  --capture-dir captures/VIDEO_ID_*/ \
  --models llava:latest gemini:gemini-2.5-flash \
  --max-frames 4 \
  --show-details

# 8. Generate storyboard panels (dry-run)
python scripts/validate_storyboard_handoff.py \
  --video-id VIDEO_ID --shot-label S01 --dry-run
```

## Pipeline Overview

**Five-component system:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots + Frames with R2-hosted images + optional LLM enrichment (Ollama or Gemini)
4. **Chrome Extension** → One-click pipeline trigger from YouTube page (via pipeline server at :3333)
5. **Storyboard Generation** (Python/ComfyUI) → Per-shot SDXL pencil panel generation with IPAdapterAdvanced frame conditioning, R2 upload, Airtable attachment

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frame capture + pipeline server)
- Airtable account with API access (base ID: `appWSbpJAxjCyLfrZ`)
- Cloudflare R2 bucket (bucket: `shot-image`)
- Ollama with `llava:latest` (optional — use `--skip-vlm` to bypass)
- ComfyUI at `http://127.0.0.1:8188` with `ip-adapter-plus_sdxl_vit-h.safetensors` (for storyboard generation)

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

# Gemini (optional — for Gemini enrichment provider)
GEMINI_API_KEY=your_gemini_api_key

# yt-frame-poc path (for pipeline server)
YT_FRAME_POC_PATH=/path/to/yt-frame-poc
```

> **Note:** Use `set -a && source .env && set +a` to export env vars for Python subprocesses.

### 3. Pipeline Server (Chrome Extension Backend)

```bash
cd pipeline-server
npm install
node server.js  # Runs on http://127.0.0.1:3333
```

### 4. Ollama Setup (optional)

```bash
# Install Ollama: https://ollama.ai
ollama pull llava:latest
ollama serve  # Runs on localhost:11434
# Use --skip-vlm flag to bypass if Ollama is not running
```

## Usage

### Analyze Scenes

```bash
python -m analyzer \
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
set -a && source .env && set +a
python -m publisher \
  --capture-dir captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --segment-transcripts \
  --merge-scenes \
  --max-concurrent-uploads 8 \
  --verbose
```

**Key Options:**
- `--dry-run` — Preview without writing to Airtable
- `--skip-images` — Skip all R2 image uploads
- `--skip-frames` — Skip Frame record creation (Shots only)
- `--enrich-shots` — Run shot-level LLM enrichment after creating Shots
- `--enrich-provider ollama|gemini` — Enrichment provider (default: `ollama`)
- `--enrich-model NAME` — Model for enrichment (default: `llava:latest`)
- `--gemini-api-key KEY` — Gemini API key (or `GEMINI_API_KEY` env var)
- `--force-reenrich` — Re-enrich all shots even if already enriched
- `--max-concurrent-uploads N` — Parallel R2 upload workers (default: 1, recommended: 8)

## Testing

```bash
# All Python tests
python -m pytest tests/ -v

# Node.js pipeline server tests
cd pipeline-server && npm test

# Specific module
python -m pytest tests/test_storyboard_handoff.py -v

# With coverage
python -m pytest tests/ --cov=publisher --cov=analyzer --cov=segmenter
```

**Test Coverage: ~590 tests passing**

| Module | Count |
|--------|-------|
| `tests/test_publisher.py` | 114 |
| `tests/test_storyboard_handoff.py` | 59 |
| `tests/test_shot_package.py` | 85 |
| `tests/test_storyboard_generator.py` | 45 |
| `tests/test_llm_enricher.py` | 41 |
| `tests/test_prompt_assembler.py` | 37 |
| `tests/test_r2_uploader.py` | 25 |
| `tests/test_publisher_cli.py` | 24 |
| `tests/test_setup_airtable.py` | 19 |
| `tests/test_scene_detector.py` | 29 |
| `tests/test_frame_helpers.py` | 12 |
| `tests/test_transcript_segmenter.py` | 13 |
| `tests/test_vlm_describer.py` | 20 |
| `tests/test_scene_merger.py` | 8 |
| `tests/test_analyze_cli.py` | 8 |
| Node.js (pipeline-server/test/) | 51 |
| **Total** | **~590** |

## Project Structure

```
airtable-shots-db/
├── analyzer/               # Scene detection + AI descriptions
│   ├── scene_detector.py   # OpenCV histogram analysis
│   └── vlm_describer.py    # Ollama VLM integration
├── publisher/              # Airtable + R2 + enrichment + storyboard
│   ├── publish.py          # Core publisher (Videos, Shots, Frames, enrichment)
│   ├── shot_package.py     # Shot packaging, prompt builder, response parser
│   ├── llm_enricher.py     # Ollama + Gemini enrichment adapters
│   ├── r2_uploader.py      # R2 uploads (scenes + all frames, parallel)
│   ├── frame_helpers.py    # Timestamp parsing from filenames
│   ├── prompt_assembler.py # GH-32: SDXL/ComfyUI per-shot image prompt builder
│   ├── storyboard_handoff.py  # GH-33/53: pencil-style payload + frame URL extraction
│   ├── storyboard_generator.py # GH-33/51: ComfyUI generation runner
│   ├── storyboard_uploader.py  # GH-51: R2 + Airtable for storyboard images
│   └── cli.py              # CLI entry point
├── comfyui/                # ComfyUI client + workflows
│   ├── comfyui_client.py   # REST API client (queue + poll + fetch)
│   └── workflows/
│       ├── Storyboarder_api.json  # API workflow (IPAdapterAdvanced)
│       └── Storyboarder 4.json   # GUI workflow counterpart
├── segmenter/              # Transcript + scene processing
│   ├── transcript_segmenter.py
│   └── scene_merger.py
├── pipeline-server/        # Express orchestrator (Chrome extension backend)
│   ├── server.js           # REST API (:3333)
│   ├── orchestrator.js     # Pipeline steps + state persistence
│   └── pipeline-state.js   # Checkpoint save/load/resume
├── chrome-extension/       # Browser extension for one-click pipeline trigger
├── scripts/                # Validation + A/B testing utilities
│   ├── ab_enrichment_test.py          # Model comparison harness
│   └── validate_storyboard_handoff.py # Storyboard payload spot-check
├── captures/               # Capture directories (gitignored)
├── tests/                  # Python unit tests (all external APIs mocked)
├── docs/                   # Issue docs, lessons learned, implementation notes
│   └── lessons-learned/    # Per-iteration lessons learned files
├── .env                    # Credentials (gitignored)
├── requirements.txt        # Python dependencies
├── CURRENT_STATE.md        # Detailed status, schema, test coverage, roadmap
└── NEXT_SESSION.md         # Current handoff and next-phase priorities
```

## Documentation

- **[CURRENT_STATE.md](./CURRENT_STATE.md)** — Full project status, schema, test coverage, roadmap
- **[NEXT_SESSION.md](./NEXT_SESSION.md)** — Current handoff and next-phase priorities
- **[docs/lessons-learned/](./docs/lessons-learned/)** — Per-iteration lessons learned
- **[docs/IMAGE_PROMPT_CONTRACT_V1.md](./docs/IMAGE_PROMPT_CONTRACT_V1.md)** — GH-32 SDXL prompt contract spec
- **[docs/LESSONS_LEARNED_ISSUE_53_AIRTABLE_FRAME_IPADAPTER_WIRING.md](./docs/LESSONS_LEARNED_ISSUE_53_AIRTABLE_FRAME_IPADAPTER_WIRING.md)** — GH-53 IPAdapter wiring
- **[docs/LESSONS_LEARNED_ISSUE_38_STRUCTURED_OUTPUTS.md](./docs/LESSONS_LEARNED_ISSUE_38_STRUCTURED_OUTPUTS.md)** — GH-38 structured outputs fix
- **[docs/HOWTO_COMFYUI_AUTOGEN_WORKFLOW.md](./docs/HOWTO_COMFYUI_AUTOGEN_WORKFLOW.md)** — ComfyUI workflow generation guide

## Airtable Schema

### Videos Table
- Video ID, Platform, Video URL, Thumbnail URL
- Transcript (Full), Transcript (Timestamped), Transcript Language, Transcript Source
- Triage Status, Channel (linked)

### Shots Table (1 record per scene)
- Shot Label (S01, S02...), Video (linked)
- Timestamp (sec), Timestamp (hh:mm:ss)
- Transcript Line, Transcript Start/End (sec)
- AI Description (Local), AI Model, AI Status, AI Prompt Version
- **Scene Start** (attachment), **Scene End** (attachment) ← R2-hosted images
- How It Is Shot, Frame Progression, Production Patterns, Recreation Guidance (LLM enrichment)
- Shot Function, Shot Type, Camera Angle, Movement, Lighting, Setting, Subject (LLM enrichment)

### Frames Table
- Frame Key (`{videoId}_t{timestamp:06d}`), Video (linked), Shot (linked)
- Timestamp (sec), Timestamp (hh:mm:ss)
- **Frame Image** (attachment) ← R2-hosted PNG

## Real-Data Validation

- ✅ `gemini-2.5-flash` on `U_cDKkDvPAQ`: 4/4 valid JSON, 13/13 fields, ~6.2s avg latency
- ✅ `llava:latest` on `6KktB5aNrjE`: 5/5 valid JSON, 13/13 fields, ~7.0s avg (with structured outputs)
- ✅ IPAdapterAdvanced storyboard wiring on `8uP2IrP3IG8` shot `S03`: 2 frame URLs extracted, 3 variants generated

## License

MIT
