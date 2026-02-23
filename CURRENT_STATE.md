# YouTube Shot List Pipeline — Current State

**Last Updated:** February 23, 2026  
**Branch:** `feature/airtable-publisher`  
**Status:** Phase 3 Complete + R2 Image Attachments Working

---

## Overview

Three-phase pipeline for extracting, analyzing, and publishing YouTube video shot lists to Airtable with AI-generated descriptions and frame thumbnails.

**Pipeline Flow:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots with R2-hosted images

---

## ✅ Completed Phases

### Phase 1: Frame Capture (TypeScript)
**Repository:** `/Users/thaddius/repos/2-21/yt-frame-poc`  
**Status:** Feature-complete

- Playwright + system Chrome (YouTube blocks embed URLs in Chromium)
- Captures timestamped PNG frames at configurable intervals
- Outputs: `manifest.json` + `frame_XXXXX_tNNN.NNNs.png`
- 43 tests passing (33 unit + 10 integration)

**Key Files:**
- `src/capture.ts` — Main capture logic
- `src/cli.ts` — CLI entry point
- `tests/` — Jest test suite

---

### Phase 2: Scene Analyzer (Python)
**Status:** Feature-complete on `feature/scene-analyzer` branch

**Pass 1: OpenCV Scene Detection**
- HSV histogram chi-squared distance for boundary detection
- Threshold: 10.0 (calibrated on real video)
- Within-scene: 0–2, scene boundaries: 10–3000+

**Pass 2: Ollama VLM Descriptions**
- `llama3.2-vision:latest` via HTTP API
- ~8.5s per scene on local hardware
- Optional `--skip-vlm` flag for faster testing

**Module Structure:**
- `analyzer/scene_detector.py` — OpenCV histogram analysis
- `analyzer/vlm_describer.py` — Ollama API integration
- `analyzer/analyze.py` — CLI with `--capture-dir`, `--threshold`, `--skip-vlm`, `--verbose`
- `analyzer/__main__.py` — `python -m analyzer` support

**Tests:** 57 passing (29 scene_detector + 8 CLI + 20 VLM, all mocked)

**Real-data validation:** 5 scenes from 10 frames, VLM in 42.3s

---

### Phase 3: Airtable Publisher (Python)
**Status:** Feature-complete with R2 image attachments

**Core Publisher:**
- Reads `analysis.json` from capture directory
- Upserts Video record (by Video ID)
- Creates 1 Shot record per scene (was 2 per scene, refactored)
- Idempotent: deletes existing Shots before re-creating
- Dry-run mode for preview

**R2 Image Upload (NEW):**
- Uploads boundary frame PNGs to Cloudflare R2
- Deduplicates shared frames (67 uploaded for 34 scenes)
- Attaches Scene Start / Scene End thumbnails to Shot records
- Optional `--skip-images` flag for metadata-only publish

**Module Structure:**
- `publisher/publish.py` — Core publisher logic
- `publisher/r2_uploader.py` — Cloudflare R2 S3-compatible uploads
- `publisher/cli.py` — CLI with `--capture-dir`, `--api-key`, `--base-id`, `--dry-run`, `--skip-images`, `--verbose`
- `publisher/__main__.py` — `python -m publisher` support

**Tests:** 130 passing (47 publisher + 8 CLI + 18 r2_uploader + 57 analyzer)

**Real-data validation:** KGHoVptow30, 34 scenes → 67 frames to R2 → 34 Shot records with thumbnails

---

## 📊 Airtable Schema

### Videos Table
| Field | Type | Populated By |
|---|---|---|
| Video ID | Single line text | Publisher |
| Platform | Single select (YouTube) | Publisher |
| Video URL | URL | Publisher |
| Thumbnail URL | URL | Publisher |
| Shots | Linked records → Shots | Auto (reverse link) |

**Not yet populated:** Video Title, Channel, Duration, Total Scenes, Analysis Date, Triage Status, Transcript fields

### Shots Table (1 record per scene)
| Field | Type | Populated By |
|---|---|---|
| Shot Label | Single line text (S01, S02...) | Publisher |
| Video | Linked record → Videos | Publisher |
| Timestamp (sec) | Number | Publisher (scene start) |
| Timestamp (hh:mm:ss) | Single line text | Publisher |
| Transcript Start (sec) | Number | Publisher |
| Transcript End (sec) | Number | Publisher |
| AI Description (Local) | Long text | Publisher (from Ollama) |
| AI Model | Single line text | Publisher |
| AI Status | Single select (Done/Queued) | Publisher |
| Capture Method | Single select (Auto Import) | Publisher |
| Source Device | Single select (Desktop) | Publisher |
| **Scene Start** | **Attachment** | **Publisher (R2 URL)** |
| **Scene End** | **Attachment** | **Publisher (R2 URL)** |

**Not yet populated:** Shot Function, Shot Type, Camera Angle, Movement, Lighting, Setting, Subject, On-screen Text, Description (Manual), Tags, AI JSON, Needs Review, Captured At, Rights Note

---

## 🪣 Cloudflare R2 Setup

**Bucket:** `shot-image`  
**Public URL:** `https://pub-f300f74e400541688f70ad8bb42b106e.r2.dev`  
**Account ID:** `7c07e5e41d224c81d5b4e8d9c6a5c97c`

**Object Key Format:** `{videoId}/{filename}`  
Example: `KGHoVptow30/frame_00000_t000.000s.png`

**Environment Variables (.env):**
```bash
R2_ACCOUNT_ID=7c07e5e41d224c81d5b4e8d9c6a5c97c
R2_ACCESS_KEY_ID=4b8055a16aabe90e19506bc28e406b64
R2_SECRET_ACCESS_KEY=bf987c7b16a96203e4be415211e49c761f360fe70dcc27ed4e8993bed9a5c399
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-f300f74e400541688f70ad8bb42b106e.r2.dev
```

**boto3 Configuration:**
- Endpoint: `https://{account_id}.r2.cloudflarestorage.com`
- Region: `auto`
- ContentType: `image/png`

**Important:** Use `set -a && source .env && set +a` to export env vars for Python subprocess.

---

## 🧪 Test Coverage

| Module | Tests | Status |
|---|---|---|
| Analyzer (scene_detector) | 29 | ✅ Passing |
| Analyzer (CLI) | 8 | ✅ Passing |
| Analyzer (VLM) | 20 | ✅ Passing |
| Publisher (core) | 47 | ✅ Passing |
| Publisher (CLI) | 8 | ✅ Passing |
| Publisher (R2 uploader) | 18 | ✅ Passing |
| **Total** | **130** | **✅ All Passing** |

All tests use mocked external APIs (Ollama, Airtable, boto3/R2).

---

## 📁 Project Structure

```
airtable-shots-db/
├── analyzer/
│   ├── __init__.py
│   ├── __main__.py
│   ├── analyze.py          # CLI entry point
│   ├── scene_detector.py   # OpenCV histogram analysis
│   └── vlm_describer.py    # Ollama VLM integration
├── publisher/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # CLI entry point
│   ├── publish.py          # Core publisher + Airtable API
│   └── r2_uploader.py      # Cloudflare R2 S3 uploads
├── tests/
│   ├── test_analyze_cli.py
│   ├── test_publisher.py
│   ├── test_publisher_cli.py
│   ├── test_r2_uploader.py
│   ├── test_scene_detector.py
│   └── test_vlm_describer.py
├── chrome-extension/       # Manual transcript capture (legacy)
├── .env                    # Credentials (gitignored)
├── requirements.txt        # Python dependencies
├── jest.config.js
├── pytest.ini
├── ISSUE_SHOT_LIST_PIPELINE.md
├── ISSUE_SHOT_IMAGE_ATTACHMENTS.md
└── CURRENT_STATE.md        # This file
```

---

## 🔑 Dependencies

**Python (requirements.txt):**
- `pyairtable==3.3.0` — Airtable API client
- `boto3>=1.35.0` — AWS S3 / Cloudflare R2 client
- `opencv-python==4.13.0.92` — Scene detection
- `numpy==2.4.2` — OpenCV dependency
- `requests==2.32.5` — Ollama HTTP API
- `python-dotenv==1.2.1` — .env file loading
- `pytest` — Test framework

**TypeScript (yt-frame-poc):**
- `playwright` — Browser automation
- `jest`, `ts-jest` — Testing

**External Services:**
- Ollama (localhost:11434) — `llama3.2-vision:latest`
- Airtable API — Base ID: `appWSbpJAxjCyLfrZ`
- Cloudflare R2 — Bucket: `shot-image`

---

## 🎯 Recent Commits (feature/airtable-publisher)

| Hash | Description |
|---|---|
| `89c8f32` | Refactor to 1 Shot record per scene + Transcript fields |
| `40bc593` | Update image issue for 1-record-per-scene model |
| `fcd6eb7` | Add R2 image uploader + integrate into publisher |
| `0470b65` | Revert accidental paste in issue file |

---

## 📋 Known Issues & Gotchas

### Airtable API
- **Linked record formulas don't work with record IDs:** `{Video}='recXXX'` returns empty. Use reverse-link field instead.
- **singleSelect fields reject unknown values:** Must use exact choices (e.g., "Done" not "done").
- **batch_create/batch_delete auto-chunk:** Max 10 records per request.

### R2 Upload
- **`source .env` doesn't export vars:** Use `set -a && source .env && set +a` for subprocess.
- **Deduplication:** Adjacent scenes may share boundary frames — 67 uploads for 34 scenes.

### OpenCV Scene Detection
- **Threshold calibration:** Default 10.0 works for talking-head videos. May need adjustment for action/montage content.
- **Chi-squared distance range:** 0–2 (same scene), 10–3000+ (boundary).

---

## 🚀 Next Steps (Priority Order)

### P0 — Core Functionality
- [x] Phase 3: Airtable Publisher (metadata)
- [x] R2 Image Uploads (Scene Start/End attachments)
- [ ] **End-to-end integration test** (Capture → Analyze → Publish on fresh video)
- [ ] **Populate Video metadata** (Title, Channel, Duration from manifest.json)
- [ ] **Error handling & retry logic** (Airtable rate limits, R2 upload failures)

### P1 — Polish & Optimization
- [ ] **Idempotent R2 uploads** (HEAD request before upload, skip if exists)
- [ ] **R2 cleanup on re-publish** (delete old frames when Shot records deleted)
- [ ] **Thumbnail generation** (resize frames to 640px before upload, save bandwidth)
- [ ] **Progress bars** for multi-frame uploads (tqdm)
- [ ] **Logging improvements** (structured JSON logs, log levels)

### P2 — Advanced Features
- [ ] **Batch processing** (publish multiple videos in one run)
- [ ] **Incremental updates** (only re-analyze changed scenes)
- [ ] **Shot metadata enrichment** (Shot Function, Camera Angle, etc. via VLM)
- [ ] **Transcript integration** (Chrome extension → Airtable → link to Shots)
- [ ] **Web UI** for shot list review/editing

### P3 — Production Readiness
- [ ] **CI/CD pipeline** (GitHub Actions for tests)
- [ ] **Docker containerization** (reproducible environment)
- [ ] **Configuration management** (YAML config files, not just .env)
- [ ] **Monitoring & alerting** (failed publishes, R2 quota)
- [ ] **Documentation** (API docs, architecture diagrams, runbook)

---

## 📝 Usage Examples

### Full Pipeline (Manual Steps)

```bash
# 1. Capture frames (TypeScript)
cd /Users/thaddius/repos/2-21/yt-frame-poc
npm run capture -- --video-id KGHoVptow30 --interval 1.0 --duration 60

# 2. Analyze scenes (Python)
cd /Users/thaddius/repos/2-20/airtable-shots-db
set -a && source .env && set +a
.venv/bin/python -m analyzer \
  --capture-dir /Users/thaddius/repos/2-21/yt-frame-poc/frames/KGHoVptow30_*/

# 3. Publish to Airtable + R2 (Python)
.venv/bin/python -m publisher \
  --capture-dir /Users/thaddius/repos/2-21/yt-frame-poc/frames/KGHoVptow30_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  -v
```

### Publisher Options

```bash
# Dry-run (preview without writing)
.venv/bin/python -m publisher --capture-dir ./captures/abc123 --dry-run

# Skip image uploads (metadata only)
.venv/bin/python -m publisher --capture-dir ./captures/abc123 --skip-images

# Verbose logging
.venv/bin/python -m publisher --capture-dir ./captures/abc123 -v
```

---

## 🔬 Development Workflow

### Running Tests
```bash
# All tests
.venv/bin/python -m pytest tests/ -v

# Specific module
.venv/bin/python -m pytest tests/test_r2_uploader.py -v

# With coverage
.venv/bin/python -m pytest tests/ --cov=publisher --cov=analyzer
```

### TDD Cycle
1. **RED:** Write failing test in `tests/test_*.py`
2. **GREEN:** Implement minimal code to pass
3. **REFACTOR:** Clean up, extract functions, improve naming
4. **COMMIT:** `git commit -m "feat: description"`

### Branch Strategy
- `main` — Stable releases only
- `feature/scene-analyzer` — Phase 2 (merged to main)
- `feature/airtable-publisher` — Phase 3 + R2 (current work)
- `feature/*` — New features

---

## 📞 Support & References

**Documentation:**
- [ISSUE_SHOT_LIST_PIPELINE.md](./ISSUE_SHOT_LIST_PIPELINE.md) — Original spec + Phase 1-3 details
- [ISSUE_SHOT_IMAGE_ATTACHMENTS.md](./ISSUE_SHOT_IMAGE_ATTACHMENTS.md) — R2 upload spec

**External APIs:**
- [Airtable API Docs](https://airtable.com/developers/web/api/introduction)
- [pyairtable Docs](https://pyairtable.readthedocs.io/)
- [Cloudflare R2 Docs](https://developers.cloudflare.com/r2/)
- [boto3 S3 Docs](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [Ollama API Docs](https://github.com/ollama/ollama/blob/main/docs/api.md)

**Python venv:** `/Users/thaddius/repos/2-20/.venv/`  
**Ollama:** `localhost:11434` (llama3.2-vision:latest)

---

**End of Current State Document**
