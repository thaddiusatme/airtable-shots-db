# YouTube Shot List Pipeline — Current State

**Last Updated:** March 3, 2026  
**Branch:** `main`  
**Status:** ✅ Frames Feature COMPLETE (GH-17, GH-18, GH-19) | Pipeline Resumption Complete | Chrome Extension Integrated

---

## Overview

Four-component pipeline for extracting, analyzing, and publishing YouTube video shot lists to Airtable with AI-generated descriptions, frame thumbnails, and per-second frame timeline records.

**Pipeline Flow:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots + Frames with R2-hosted images
4. **Chrome Extension** → One-click pipeline trigger from YouTube page (via pipeline server at :3333)

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
- `analyzer/vlm_describer.py` — Ollama VLM integration
- `analyzer/analyze.py` — CLI with `--capture-dir`, `--threshold`, `--skip-vlm`, `--verbose`
- `analyzer/__main__.py` — `python -m analyzer` support
- `segmenter/transcript_segmenter.py` — Overlap-based transcript segmentation
- `segmenter/scene_merger.py` — Merge short scenes into longer shots

**Tests:** 70 passing (29 scene_detector + 8 CLI + 20 VLM + 13 transcript_segmenter, all mocked)

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
- `publisher/publish.py` — Core publisher (Videos, Shots, Frames + idempotency for all)
- `publisher/r2_uploader.py` — R2 uploads for scene boundaries + all frames (parallel support)
- `publisher/frame_helpers.py` — `parse_timestamp_from_filename()` regex parser
- `publisher/cli.py` — CLI with `--capture-dir`, `--api-key`, `--base-id`, `--dry-run`, `--skip-images`, `--skip-frames`, `--segment-transcripts`, `--merge-scenes`, `--min-scene-duration`, `--max-concurrent-uploads`, `--frame-sampling`, `--verbose`
- `publisher/__main__.py` — `python -m publisher` support

**Tests:** 190 Python passing (see test coverage table)

**Real-data validation:** `bjdBVZa66oU`, 34 shots → 34 frames uploaded to R2 with 4 concurrent workers → Frames table blocked on GH #18

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

**Populated by Chrome extension (transcript extract):** Video Title, Transcript (Full), Transcript (Timestamped), Transcript Language, Transcript Source, Triage Status, Channel

**Not yet populated:** Duration, Total Scenes, Analysis Date

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

### Frames Table ✅ CREATED — [GH #18](https://github.com/thaddiusatme/airtable-shots-db/issues/18) RESOLVED
| Field | Type | Populated By |
|---|---|---|
| Frame Key | Single line text (`{videoId}_t{ts:06d}`) | Publisher |
| Video | Linked record → Videos | Publisher |
| Shot | Linked record → Shots | Publisher |
| Timestamp (sec) | Number (int) | Publisher |
| Timestamp (hh:mm:ss) | Single line text | Publisher |
| **Frame Image** | **Attachment** | **Publisher (R2 URL)** |
| Source Filename | Single line text | Publisher |

**Status:** Table created in Airtable (commits `c359f18`, `564fe7d`). Publisher fully integrated. Chrome extension pipeline uploads all frames automatically.

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
| Segmenter (transcript) | 13 | ✅ Passing |
| Segmenter (scene merger) | 8 | ✅ Passing |
| Publisher (core + frames) | 54 | ✅ Passing |
| Publisher (CLI) | 11 | ✅ Passing |
| Publisher (R2 uploader) | 23 | ✅ Passing |
| Publisher (frame helpers) | 12 | ✅ Passing |
| Pipeline State (Node) | 15 | ✅ Passing |
| Resume API (Node) | 9 | ✅ Passing |
| **Total** | **202** | **✅ All Passing** |

All tests use mocked external APIs (Ollama, Airtable, boto3/R2).  
Pipeline state tests use `node:test` with temp directories (no external deps).  
Resume API tests use `node:test` + `http` with ephemeral Express server (no external deps).

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
│   ├── cli.py              # CLI entry point (all flags)
│   ├── publish.py          # Core publisher: Videos, Shots, Frames
│   ├── r2_uploader.py      # R2 uploads: scene boundaries + all frames (parallel)
│   └── frame_helpers.py    # parse_timestamp_from_filename() regex
├── tests/
│   ├── test_analyze_cli.py
│   ├── test_frame_helpers.py
│   ├── test_publisher.py
│   ├── test_publisher_cli.py
│   ├── test_r2_uploader.py
│   ├── test_scene_detector.py
│   ├── test_scene_merger.py
│   ├── test_transcript_segmenter.py
│   └── test_vlm_describer.py
├── captures/               # Capture directories with frames + analysis.json (gitignored)
├── pipeline-server/
│   ├── orchestrator.js     # Pipeline orchestration + state persistence
│   ├── server.js           # Express API server
│   ├── pipeline-state.js   # Checkpoint state helpers (save/load/find)
│   ├── dashboard.html      # Web dashboard
│   ├── package.json        # Node dependencies + test script
│   └── test/
│       └── test_pipeline_state.js  # 15 unit tests
├── chrome-extension/       # Pipeline trigger + transcript capture
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

## 🎯 Recent Commits

| Hash | Description |
|---|---|
| `TBD` | feat(GH-19): integrate frames into chrome extension pipeline (orchestrator.js) |
| `564fe7d` | fix(GH-18): correct attachment field type multipleAttachments (plural) |
| `c359f18` | feat(GH-18): add_frames_table() — additive Frames table creation (TDD iteration 1) |
| `7b6343d` | feat(GH-17): add parallel uploads and frame sampling (TDD iteration 4) |
| `4504887` | feat(GH-17): integrate Frame records into publisher with idempotency + --skip-frames (TDD iteration 3) |
| `582db8e` | feat(GH-17): add frame record builder and R2 all-frames uploader (TDD iteration 2) |
| `6539a04` | feat(GH-17): add timestamp parsing from frame filenames (TDD iteration 1) |
| `238694a` | feat: add resume API endpoints and extension resume button |

---

## 📋 Known Issues & Gotchas

### Pipeline Resumption (TDD Iterations 1–2 — March 1, 2026)

- **`savePipelineState` auto-updates `updatedAt`:** Tests that assert a hardcoded `updatedAt` value will fail because the save function always stamps current time. Assert `notEqual` to the original value instead.
- **Deep-clone INITIAL_PIPELINE_STATE:** Using `JSON.parse(JSON.stringify(...))` prevents mutation of the shared constant across multiple `createInitialState` calls.
- **Corrupted JSON graceful recovery:** `loadPipelineState` falls back to initial state on parse errors — critical for production resilience when process is killed mid-write.
- **Capture failure saves partial progress:** The catch block in the capture step counts existing frames via `findExistingFrames` before re-throwing, so the state file accurately records `framesCompleted` even on crash.
- **`node:test` is zero-dep and sufficient:** No need for Jest/Mocha for simple unit tests. Built-in `node:test` + `node:assert/strict` with temp dirs covers all pipeline state scenarios in 84ms.
- **State file location matters:** Using `stateFilePath(capturesBase)` (the captures root) rather than per-video captureDir allows state tracking before the capture directory is created.
- **`require.main === module` guard for testability:** Prevents `app.listen()` from running when server.js is imported by tests. Export `app` and `jobs` for direct test manipulation.
- **`launchPipeline` helper eliminates duplication:** Both `/pipeline/run` and `/pipeline/resume/:runId` share identical updateStatus/error-handling logic — extracted to single function with label param.
- **Resume filter requires `captureDir`:** Jobs that fail before capture starts have no `captureDir` and are excluded from resumable list (nothing to resume from).

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

### P0 — Core Functionality ✅ COMPLETE
- [x] Phase 3: Airtable Publisher (metadata)
- [x] R2 Image Uploads (Scene Start/End attachments)
- [x] Pipeline Server (Express orchestrator + Chrome extension trigger)
- [x] VLM Bypass (`--skip-vlm` flag end-to-end)
- [x] Checkpoint state persistence (`.pipeline_state.json` save/load)
- [x] Step skipping on resume (completed steps logged and skipped)
- [x] Resume API endpoints (`GET /pipeline/resumable`, `POST /pipeline/resume/:runId`)
- [x] Extension resume button (detect resumable jobs, show "Resume Failed Pipeline")
- [x] **Frames feature — publisher code complete** ([GH #17](https://github.com/thaddiusatme/airtable-shots-db/issues/17)) — TDD iterations 1–4, 117 tests
- [x] **Parallel frame uploads** (`--max-concurrent-uploads N`, ThreadPoolExecutor)
- [x] **Frame sampling** (`--frame-sampling N`, deduplication by Frame Key)
- [x] **Create Frames table in Airtable** ([GH #18](https://github.com/thaddiusatme/airtable-shots-db/issues/18)) — Commits `c359f18`, `564fe7d`
- [x] **Integrate Frames into Chrome Extension** ([GH #19](https://github.com/thaddiusatme/airtable-shots-db/issues/19)) — March 3, 2026

### P1 — Polish & Optimization
- [ ] **Step output validation** (check `analysis.json` exists before skipping analyze)
- [ ] **`--force-step` CLI flag** (re-run specific steps on demand)
- [ ] **Idempotent R2 uploads** (HEAD request before upload, skip if exists)
- [ ] **Thumbnail generation** (resize frames to 640px before upload, save bandwidth)
- [ ] **Logging improvements** (structured JSON logs, log levels)
- [ ] **End-to-end integration test** (Capture → Analyze → Publish → Frames on fresh video)
- [ ] **`setup_airtable.py` update** (add Frames table creation to schema script)

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
