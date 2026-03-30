# YouTube Shot List Pipeline — Current State

**Last Updated:** March 30, 2026
**Branch:** `feature/gh-53-airtable-frame-ipadapter-wiring`
**Status:** ✅ Frames (GH-17/18/19) | ✅ Shot LLM Enrichment (GH-23/28/30) | ✅ Structured Outputs (GH-38) | ✅ Gemini Provider (GH-40) | ✅ Image Prompt Assembler (GH-32) | ✅ Storyboard Generation (GH-33/51) | ✅ ComfyUI Queue Observability (GH-56) | ✅ Dynamic IPAdapter Stripping (GH-57) | ✅ Airtable Frame IPAdapter Wiring (GH-53)

---

## Overview

Four-component pipeline for extracting, analyzing, and publishing YouTube video shot lists to Airtable with AI-generated descriptions, frame thumbnails, per-second frame timeline records, and optional shot-level LLM enrichment.

**Pipeline Flow:**
1. **Capture** (TypeScript/Playwright) → Frame PNGs + manifest.json
2. **Analyze** (Python/OpenCV/Ollama) → Scene boundaries + AI descriptions → analysis.json
3. **Publish** (Python/pyairtable/boto3) → Airtable Videos + Shots + Frames with R2-hosted images + optional shot enrichment
4. **Chrome Extension** → One-click pipeline trigger from YouTube page (via pipeline server at :3333), now routed through orchestrator-driven shot enrichment during publish
5. **Storyboard Generation** (Python/ComfyUI) → Per-shot SDXL image prompts + pencil storyboard panel generation via ComfyUI IPAdapterAdvanced + R2 upload + Airtable attachment

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
**Status:** Feature-complete with R2 image attachments and shot-enrichment core

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

**Shot-Level LLM Enrichment (GH-23, GH-38, GH-40):**

- `publisher/shot_package.py` assembles full shot packages (all frames + transcript slice)
- Structured prompt payload builder with `AI_PROMPT_VERSION = "1.2"` (bumped for structured output contract)
- Response parser maps 13 LLM keys into Airtable `Shots` fields + `AI JSON`
- `publish_to_airtable()` supports `enrich_shots`, `enrich_fn`, and `enrich_model`
- Idempotent re-runs preserve old enrichment and skip already-enriched shots
- Schema helper adds missing enrichment fields to existing bases
- **NEW (GH-38):** Ollama structured outputs via `format` JSON schema + `temperature=0` for deterministic, valid JSON
- **NEW (GH-38):** Success criteria fix — `AI Prompt Version` only set on successful parse (no `AI Error`)
- **NEW (GH-40):** Gemini enrichment provider support via `--enrich-provider gemini`, `--gemini-api-key`, and `--gemini-api-url`
- **NEW (GH-40):** A/B harness supports provider-qualified model specs such as `gemini:gemini-2.5-flash`
- **NEW (GH-40):** Gemini responses now expose usage metadata for token counts and estimated cost reporting in the A/B harness

**Module Structure:**

- `publisher/publish.py` — Core publisher (Videos, Shots, Frames + enrichment + idempotency)
- `publisher/shot_package.py` — Shot package assembly, prompt builder, response parser
- `publisher/r2_uploader.py` — R2 uploads for scene boundaries + all frames (parallel support)
- `publisher/frame_helpers.py` — `parse_timestamp_from_filename()` regex parser
- `publisher/llm_enricher.py` — Ollama + Gemini enrichment adapters, structured-output schema, and Gemini usage/cost metadata capture
- `publisher/cli.py` — CLI with publish/frames/transcript/enrichment flags, including Gemini provider/api-key routing; Ollama pre-flight model check enabled when `--enrich-shots` is set
- `publisher/__main__.py` — `python -m publisher` support

**Tests:** 41 focused Gemini/Ollama adapter tests currently validated for the latest GH-40 slice; broader enrichment suite remains in place from prior work

**Real-data validation:** Frames pipeline validated end-to-end; shot enrichment core is implemented and test-covered with live Ollama adapter and pre-flight model check. Issue #30 live validation confirmed that orchestrator-triggered publish now passes `--enrich-shots` / `--enrich-model`, shows enrichment in job status, and performs per-shot enrichment in the real one-click path. GH-40 live validation confirmed that `gemini-2.5-flash` works on real multimodal shot packages from `U_cDKkDvPAQ`, with a 4-shot sample producing 4/4 valid JSON, 13.0/13 field coverage, and ~6.2s average latency. The original `gemini-2.0-flash` target is not available to this project key and should be treated as superseded for current usage.

---

### Phase 4: Pipeline Server + Chrome Extension Orchestration

**Status:** Orchestrator enrichment wiring complete on `feature/issue-30-orchestrator-enrichment`

- `pipeline-server/orchestrator.js` now always passes `--enrich-shots` and `--enrich-model` to the Python publisher
- Orchestrator publish status explicitly shows enrichment and selected model (`llava:latest` by default)
- `pipeline-server/test/test_orchestrator_postgres_cold_layer.js` includes a regression test asserting the publisher argv contract
- Live validation on short existing capture `IuQBOpDCsKQ_*` reached full pipeline completion including `persist_postgres`
- Live extension-triggered run `20c83926-2999-4c7c-8a7a-e67b357c782b` for `KcLG9QoSPFM` reached enriched publish and began `Enriching S01 (1/10)` after frame upload/Frame record creation

**Important local validation note:** The successful end-to-end `persist_postgres` run required:

- starting `pipeline-server` with `POSTGRES_URL=postgres://pipeline:pipeline@127.0.0.1:5432/airtable_shots`
- bootstrapping the host Postgres instance (role/db/table/permissions) because host Postgres was occupying `127.0.0.1:5432` instead of the Docker Postgres container

---

### Phase 5: Storyboard Generation (Python/ComfyUI)
**Status:** Feature-complete on `feature/gh-53-airtable-frame-ipadapter-wiring`

**GH-32: Image Prompt Assembler**  
**Description:** Implemented a deterministic prompt assembler that converts enriched Airtable shot fields into structured SDXL/ComfyUI-compatible prompt dictionaries for automated storyboard image generation.  
**Primary Files/Components:** `publisher/prompt_assembler.py`, `scripts/validate_prompt_assembler.py`  
**User-Facing/Operational Impact:** Enables automated creation of high-quality storyboard panels from shot descriptions, eliminating manual prompt engineering and improving visual storytelling consistency.  
**Reference:** [GH-32](https://github.com/thaddiusatme/airtable-shots-db/issues/32)

**GH-33/51: Storyboard Generation**  
**Description:** Built end-to-end storyboard generation pipeline using ComfyUI to create pencil-style SDXL panels from assembled prompts, with R2 upload and Airtable attachment integration.  
**Primary Files/Components:** `publisher/storyboard_handoff.py`, `publisher/storyboard_generator.py`, `publisher/storyboard_uploader.py`, `comfyui/comfyui_client.py`, `comfyui/workflows/Storyboarder_api.json`  
**User-Facing/Operational Impact:** Users can generate visual storyboards directly from video analysis, enhancing project planning and presentation with automated visual assets.  
**Reference:** [GH-33](https://github.com/thaddiusatme/airtable-shots-db/issues/33) / [GH-51](https://github.com/thaddiusatme/airtable-shots-db/issues/51)

**GH-56: ComfyUI Queue Observability**  
**Description:** Added polling diagnostics and error surfacing for ComfyUI job status, queue position, and generation failures during storyboard creation.  
**Primary Files/Components:** `comfyui/comfyui_client.py`, `publisher/storyboard_generator.py`  
**User-Facing/Operational Impact:** Operators gain real-time visibility into generation progress and can quickly diagnose issues, improving reliability and reducing downtime in storyboard workflows.  
**Reference:** [GH-56](https://github.com/thaddiusatme/airtable-shots-db/issues/56)

**GH-57: Dynamic IPAdapter Stripping**  
**Description:** Implemented runtime stripping of IPAdapter workflow nodes when no reference images are provided, enabling graceful degradation for shots without frame attachments.  
**Primary Files/Components:** `comfyui/workflows/Storyboarder_api.json`, `publisher/storyboard_generator.py`  
**User-Facing/Operational Impact:** Ensures storyboard generation succeeds for all shots regardless of frame availability, preventing workflow failures and maintaining consistent output.  
**Reference:** [GH-57](https://github.com/thaddiusatme/airtable-shots-db/issues/57)

**GH-53: Airtable Frame IPAdapter Wiring**  
**Description:** Integrated Airtable frame URLs into ComfyUI IPAdapter conditioning, upgrading to IPAdapterAdvanced for reference-image based storyboard generation.  
**Primary Files/Components:** `publisher/storyboard_handoff.py` (`fetch_shot_frame_urls()`), `comfyui/workflows/Storyboarder_api.json` (IPAdapterAdvanced upgrade)  
**User-Facing/Operational Impact:** Storyboard panels now incorporate actual video frames for more accurate and contextually relevant visual representations.  
**Reference:** [GH-53](https://github.com/thaddiusatme/airtable-shots-db/issues/53)

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
| Transcript Line | Long text | Publisher (when transcript segmentation enabled) |
| Transcript Start (sec) | Number | Publisher |
| Transcript End (sec) | Number | Publisher |
| AI Description (Local) | Long text | Publisher (from Ollama) |
| How It Is Shot | Long text | Publisher enrichment |
| Frame Progression | Long text | Publisher enrichment |
| Production Patterns | Long text | Publisher enrichment |
| Recreation Guidance | Long text | Publisher enrichment |
| Shot Function | Single/multi select or text | Publisher enrichment / Airtable schema |
| Shot Type | Single/multi select or text | Publisher enrichment / Airtable schema |
| Camera Angle | Single/multi select or text | Publisher enrichment / Airtable schema |
| Movement | Single/multi select or text | Publisher enrichment / Airtable schema |
| Lighting | Single/multi select or text | Publisher enrichment / Airtable schema |
| Setting | Single line text | Publisher enrichment |
| Subject | Single line text | Publisher enrichment |
| On-screen Text | Text | Publisher enrichment |
| AI JSON | Long text | Publisher enrichment |
| AI Prompt Version | Single line text | Publisher enrichment |
| AI Updated At | Date/time | Publisher enrichment |
| AI Model | Single line text | Publisher |
| AI Error | Long text | Publisher enrichment |
| AI Status | Single select (Done/Queued) | Publisher |
| Capture Method | Single select (Auto Import) | Publisher |
| Source Device | Single select (Desktop) | Publisher |
| **Scene Start** | **Attachment** | **Publisher (R2 URL)** |
| **Scene End** | **Attachment** | **Publisher (R2 URL)** |

**Notes:** Enrichment fields are populated when `publish_to_airtable()` is called with enrichment enabled and an injected LLM function. Existing bases may need `setup_airtable.py --add-enrichment-fields` to provision the 4 new multiline fields added in GH-23.

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
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-xxx.r2.dev
```

**boto3 Configuration:**
- Endpoint: `https://{account_id}.r2.cloudflarestorage.com`
- Region: `auto`
- ContentType: `image/png`

**Important:** Use `set -a && source .env && set +a` to export env vars for Python subprocess.

---

## 🧪 Test Coverage

- **Python test suite:** 539 tests
  - `tests/test_publisher.py` — 114 (publish/enrichment/idempotency/observability)
  - `tests/test_storyboard_handoff.py` — 59 (handoff contract + frame URL extraction)
  - `tests/test_shot_package.py` — 85 (shot package assembly + prompt builder)
  - `tests/test_storyboard_generator.py` — 45 (ComfyUI runner + dry-run)
  - `tests/test_llm_enricher.py` — 41 (Ollama + Gemini adapters)
  - `tests/test_prompt_assembler.py` — 37 (SDXL prompt assembly + filtering)
  - `tests/test_r2_uploader.py` — 25 (R2 parallel uploads)
  - `tests/test_publisher_cli.py` — 24 (CLI flags including Gemini routing)
  - `tests/test_setup_airtable.py` — 19 (schema/contract tests)
  - `tests/test_scene_detector.py` — 29
  - `tests/test_frame_helpers.py` — 12
  - `tests/test_transcript_segmenter.py` — 13
  - `tests/test_scene_merger.py` — 8
  - `tests/test_analyze_cli.py` — 8
  - `tests/test_vlm_describer.py` — 20
- **Node.js pipeline-server suite:** 51 tests
  - `test_pipeline_state.js` — 15
  - `test_resume_api.js` — 12
  - `test_retry.js` — 20
  - `test_orchestrator_enrichment_gating.js` — 4
- **Total:** ~590 tests passing

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
│   ├── publish.py          # Core publisher: Videos, Shots, Frames, enrichment
│   ├── shot_package.py     # Shot package assembly + prompt + parser
│   ├── r2_uploader.py      # R2 uploads: scene boundaries + all frames (parallel)
│   ├── frame_helpers.py    # parse_timestamp_from_filename() regex
│   ├── prompt_assembler.py # GH-32: SDXL/ComfyUI per-shot image prompt builder
│   ├── storyboard_handoff.py  # GH-33/53: pencil-style payload + fetch_shot_frame_urls()
│   ├── storyboard_generator.py # GH-33/51: ComfyUI generation runner
│   └── storyboard_uploader.py # GH-51: R2 + Airtable attachment for storyboard images
├── comfyui/
│   ├── comfyui_client.py   # ComfyUI REST API client (queue + poll + fetch)
│   └── workflows/
│       ├── Storyboarder_api.json  # API workflow (IPAdapterAdvanced)
│       └── Storyboarder 4.json   # GUI workflow counterpart
├── tests/
│   ├── test_analyze_cli.py
│   ├── test_frame_helpers.py
│   ├── test_publisher.py
│   ├── test_publisher_cli.py
│   ├── test_r2_uploader.py
│   ├── test_scene_detector.py
│   ├── test_scene_merger.py
│   ├── test_setup_airtable.py
│   ├── test_shot_package.py
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
├── setup_airtable.py       # Airtable schema helpers (Frames + enrichment fields)
├── jest.config.js
├── pytest.ini
├── CURRENT_STATE.md        # This file
└── docs/
    ├── ISSUE_SHOT_LIST_PIPELINE.md
    ├── ISSUE_SHOT_IMAGE_ATTACHMENTS.md
    └── archive/            # Historical session prompts / phase handoff docs

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
| `bc4ff30` | fix: update gitignore for storyboard outputs + upgrade IPAdapterAdvanced |
| `4052d80` | Add lessons learned documentation for GH-53 iteration |
| `1c9e67b` | Implement fetch_shot_frame_urls() for GH-53 Airtable frame IPAdapter wiring |
| `3c7099a` | Fix storyboard quality: increase steps + simplify prompts |
| `65fffe8` | docs: add lessons learned for GH-57 dynamic workflow stripping |
| `3966ce8` | GH-57: dynamic IPAdapter stripping when no reference image |
| `ce92e40` | GH-56: add ComfyUI prompt queue observability |
| `4974550` | fix(gh-56): add comfyui polling observability diagnostics |
| `8bbc37c` | Docs: ComfyUI autogen workflow + ignore storyboard outputs |
| `5a3141b` | GH-51: ComfyUI storyboard generation + R2/Airtable integration |
| `c24c9ec` | feat(GH-33): storyboard generation runner + validation script — TDD iteration 2 |
| `33692e3` | GH-33: storyboard handoff contract — TDD iteration 1 |
| `5ee24d3` | feat(GH-32): v1.1 live validation — uninformative narrative filter + empty section cleanup |
| `201f8d2` | feat(GH-32): image prompt contract v1 — deterministic SDXL/ComfyUI per-shot prompt assembler |
| `3d04ecb` | merge: bring pipeline UI-gated enrichment + provider selection onto master |

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

### Shot Enrichment (GH-23)
- **Manifest remains source of truth:** Shot frame collection should use manifest-driven filename resolution when available, especially for sampled captures.
- **`AI Prompt Version` is the enrichment signal:** Shots with this field set are considered enriched and are skipped on re-run unless explicit re-enrichment logic is added.
- **Error-only shots retry automatically:** If an old shot has `AI Error` but no `AI Prompt Version`, it is eligible for re-enrichment on the next run.
- **`Shot Label` matching assumes stable scene ordering:** If scene boundaries change between runs, preserved enrichment could attach to the wrong recreated shot.
- **CLI wiring exists for Ollama:** `publisher/cli.py` now exposes `--enrich-shots`, provider/model/timeout flags, and wires through `make_ollama_enrich_fn()`.
- **GH-28 model tag fix:** Default model changed from `llava:7b` to `llava:latest`. Pre-flight model availability check via `GET /api/tags` runs before the publish loop when `--enrich-shots` is set. Fails fast with `rc=1` if model not found.
- **GH-27 observability landed:** The publisher logs shot label + progress before each request, records per-shot elapsed time, and writes shot-labeled `AI Error` values for failed enrichments.
- **Late-shot root cause may be resolved:** The post-`S10` stall may have been caused by the `llava:7b` 404 retry loop. Needs live re-validation with the corrected default.
- **`--force-reenrich` flag available:** Bypasses all skip logic to re-enrich all shots regardless of existing enrichment state.
- **Prompt-version-aware re-enrichment:** When `AI_PROMPT_VERSION` changes, stale shots are automatically re-enriched on the next run without needing `--force-reenrich`.

### R2 Upload
- **`source .env` doesn't export vars:** Use `set -a && source .env && set +a` for subprocess.
- **Deduplication:** Adjacent scenes may share boundary frames — 67 uploads for 34 scenes.

### OpenCV Scene Detection
- **Threshold calibration:** Default 10.0 works for talking-head videos. May need adjustment for action/montage content.
- **Chi-squared distance range:** 0–2 (same scene), 10–3000+ (boundary).

---

## Next Steps (Priority Order)

### P0 — Core Functionality 
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
- [x] **Shot-level LLM enrichment core** ([GH #23](https://github.com/thaddiusatme/airtable-shots-db/issues/23)) — shot package assembly, prompt payloads, schema alignment, idempotent re-run

### P1 — Polish & Optimization
- [ ] **Step output validation** (check `analysis.json` exists before skipping analyze)
- [ ] **`--force-step` CLI flag** (re-run specific steps on demand)
- [ ] **Idempotent R2 uploads** (HEAD request before upload, skip if exists)
- [ ] **Thumbnail generation** (resize frames to 640px before upload, save bandwidth)
- [ ] **Logging improvements** (structured JSON logs, log levels beyond current GH-27 enrichment observability)
- [ ] **End-to-end integration test** (Capture → Analyze → Publish → Frames on fresh video)
- [ ] **Late-shot runtime diagnosis / live re-run** (re-run the 16-shot Ollama capture with GH-27 observability enabled)
- [x] **`--force-reenrich` flag** (manual override for already-enriched shots) — **GH-34 complete**
- [x] **Prompt version-aware re-enrichment** (selective re-run when `AI_PROMPT_VERSION` changes) — **GH-23 complete**

### P2 — Advanced Features
- [ ] **Batch processing** (publish multiple videos in one run)
- [ ] **Incremental updates** (only re-analyze changed scenes)
- [x] **Chrome extension enrichment integration** — **GH-34 complete** (force-reenrich checkbox wired through extension → pipeline → orchestrator)
- [ ] **Cost/rate limiting for enrichment** (token tracking + configurable rate limits)
- [ ] **Prompt-size optimization / batching** (large shot packages with many frames)
- [ ] **Web UI** for shot list review/editing
- [x] **Image prompt assembler** (GH-32) — deterministic SDXL prompts from enriched shots
- [x] **Storyboard generation** (GH-33/51) — ComfyUI pencil panel generation, R2 upload, Airtable attachment
- [x] **ComfyUI queue observability** (GH-56) — polling diagnostics + error surfacing
- [x] **Dynamic IPAdapter stripping** (GH-57) — graceful degradation when no reference images
- [x] **Airtable frame IPAdapter wiring** (GH-53) — fetch_shot_frame_urls() + IPAdapterAdvanced upgrade
- [ ] **Retry/backoff for Gemini 429 responses** (GH-40 follow-up)
- [ ] **Gemini vs qwen2.5vl:7b benchmark** (10+ shots, latency/field coverage/cost comparison)
- [ ] **Full extension-driven end-to-end with provider=gemini**
- [ ] **Real ComfyUI storyboard generation end-to-end** (--no-dry-run with live ComfyUI service)

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

## ✅ Issue #38: Structured Outputs + Success Criteria Fix

**Branch:** `fix/gh-38-structured-outputs-success-criteria`  
**Commits:** `5bb4f8e` (P0-A/P0-B), `6346cb9` (lessons), `c7f1fcb` (A/B harness)  
**Status:** Complete — ready for merge

### What was fixed
**P0-A: Ollama Structured Outputs**
- Added `format: <json_schema>` to Ollama request payload (enforces valid JSON structure)
- Added `options: {temperature: 0}` for deterministic output
- Schema built dynamically from `SHOT_ENRICHMENT_FIELDS` (13 required properties)
- `movement` field typed as `array`, all others `string`

**P0-B: Enrichment Success Criteria**
- Fixed bug where `AI Prompt Version` was set even on parse failure
- Now gates success metadata (`AI Prompt Version`, `AI Updated At`, `AI Model`) on `"AI Error" not in fields`
- Parse failures write only `AI Error`, do NOT increment `shots_enriched` count
- This prevents failed enrichments from being marked as complete

**P1: A/B Test Harness**
- Added `scripts/ab_enrichment_test.py` for model comparison
- Supports `--models llava:latest qwen2.5vl:7b` (or any Ollama models)
- Outputs: valid JSON rate, avg fields/shot, avg time, field coverage bars, shot-by-shot comparison
- `--show-details` flag prints per-shot enrichment values
- `--output-json` exports full results for offline analysis

### A/B Test Results (llava:latest vs qwen2.5vl:7b)
**Video:** `6KktB5aNrjE` (5 shots)  
**Config:** `--max-frames 4`, `--timeout 600s`

| Model | Valid JSON | Avg Fields | Avg Time | Notes |
|-------|------------|------------|----------|-------|
| `llava:latest` | 5/5 (100%) | 13.0/13 | ~7.0s/shot | 4x faster |
| `qwen2.5vl:7b` | 5/5 (100%) | 13.0/13 | ~29.7s/shot | Richer detail |

**Key finding:** With structured outputs, **both models achieve 100% valid JSON and 100% field coverage**. The difference is speed (llava 4x faster) and semantic quality (qwen2.5vl more detailed descriptions).

### Version bump
- `AI_PROMPT_VERSION` bumped `1.1` → `1.2` (triggers auto re-enrichment of stale shots)

### Tests
- 12 new (6 structured output payload, 6 success criteria)
- 232/232 in-scope pass, 0 regressions

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
- [docs/ISSUE_SHOT_LIST_PIPELINE.md](./docs/ISSUE_SHOT_LIST_PIPELINE.md) — Original spec + Phase 1-3 details
- [docs/ISSUE_SHOT_IMAGE_ATTACHMENTS.md](./docs/ISSUE_SHOT_IMAGE_ATTACHMENTS.md) — R2 upload spec
- [docs/GITHUB_ISSUE_SHOT_ENRICHMENT.md](./docs/GITHUB_ISSUE_SHOT_ENRICHMENT.md) — GH-23 implementation summary and remaining work

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
