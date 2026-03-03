# Next Session Prompt — March 3, 2026

## What Was Accomplished This Session

### Frames Feature (TDD Iterations 1–4) — ✅ COMPLETE

Publisher code is fully implemented and tested. 4 commits landed today:

| Commit | Description |
|--------|-------------|
| `6539a04` | TDD Iter 1: `parse_timestamp_from_filename()` in `publisher/frame_helpers.py` |
| `582db8e` | TDD Iter 2: `build_frame_records()` + `upload_all_frames()` |
| `4504887` | TDD Iter 3: Full publisher integration + idempotency + `--skip-frames` flag |
| `7b6343d` | TDD Iter 4: Parallel uploads (`--max-concurrent-uploads`) + frame sampling (`--frame-sampling`) |

**Demo verified:** 34 frames uploaded to R2 with 4 concurrent workers from `bjdBVZa66oU` capture.

**Test count:** 202 total passing (190 Python + 24 Node.js → run with `pytest tests/ -q` and `cd pipeline-server && npm test`)

### GitHub Issues Created — ✅ COMPLETE

| Issue | Title | Status |
|-------|-------|--------|
| [#18](https://github.com/thaddiusatme/airtable-shots-db/issues/18) | Create Frames Table Schema in Airtable | Open — **P0 NEXT** |
| [#19](https://github.com/thaddiusatme/airtable-shots-db/issues/19) | Integrate Frames into Chrome Extension Pipeline | Open — blocked by #18 |

---

## P0 — Next Session Priority

### 1. Create Frames Table in Airtable ([GH #18](https://github.com/thaddiusatme/airtable-shots-db/issues/18))

**Why:** Publisher code is done but hits 403 Forbidden because the Frames table doesn't exist.

**Option A — Update `setup_airtable.py`** (recommended):

Add to `initial_tables` list (line ~38):
```python
{
    "name": "Frames",
    "description": "Per-second frame captures for video timeline navigation",
    "fields": [{"name": "Frame Key", "type": "singleLineText"}]
}
```

Then get the table ID and add fields in a new Step 5 block:
```python
frames_table_id = next(t.id for t in schema.tables if t.name == "Frames")

create_field(base_id, frames_table_id, {"name": "Video", "type": "multipleRecordLinks", "options": {"linkedTableId": videos_table_id}})
create_field(base_id, frames_table_id, {"name": "Shot", "type": "multipleRecordLinks", "options": {"linkedTableId": shots_table_id}})
create_field(base_id, frames_table_id, {"name": "Timestamp (sec)", "type": "number", "options": {"precision": 0}})
create_field(base_id, frames_table_id, {"name": "Timestamp (hh:mm:ss)", "type": "singleLineText"})
create_field(base_id, frames_table_id, {"name": "Frame Image", "type": "multipleAttachment"})
create_field(base_id, frames_table_id, {"name": "Source Filename", "type": "singleLineText"})
```

**Option B — Create manually in Airtable UI** (faster for now):
- Add table named "Frames" with the 7 fields listed above

**Verify with test run:**
```bash
export $(cat .env | xargs)
.venv/bin/python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --frame-sampling 30 \
  --max-concurrent-uploads 4
```

Expected: `Created 34 Frame records` in output.

---

### 2. Chrome Extension Integration ([GH #19](https://github.com/thaddiusatme/airtable-shots-db/issues/19))

**Blocked by #18.** After Frames table exists, this is a 1-line change in `orchestrator.js`:

In the publish step command args, add:
```javascript
'--max-concurrent-uploads', '8',
```

Full integration plan in `docs/GITHUB_ISSUE_FRAMES_CHROME_EXTENSION.md`.

---

## P1 — Remaining Pipeline Items

- **Step output validation** — Check `analysis.json` exists before skipping analyze step in orchestrator
- **`--force-step` flag** — Allow re-running specific pipeline steps on demand
- **Idempotent R2 uploads** — HEAD check before upload (skip if already exists in R2)
- **End-to-end test** — Capture → Analyze → Publish → Frames on a fresh short video

---

## Key Files

**Frames feature (publisher):**
- `publisher/frame_helpers.py` — `parse_timestamp_from_filename()`
- `publisher/publish.py` — `build_frame_records()`, `publish_to_airtable()` with Frames integration
- `publisher/r2_uploader.py` — `upload_all_frames()` with parallel support
- `publisher/cli.py` — `--skip-frames`, `--max-concurrent-uploads`, `--frame-sampling`

**Pipeline server:**
- `pipeline-server/orchestrator.js` — Add `--max-concurrent-uploads` flag here (GH #19)
- `pipeline-server/server.js` — REST API + resume endpoints
- `pipeline-server/pipeline-state.js` — Checkpoint helpers

**Chrome extension:**
- `chrome-extension/popup.html` / `popup.js` — Phase 2: Add frame controls (GH #19)

**Schema:**
- `setup_airtable.py` — Add Frames table creation (GH #18)
- `docs/GITHUB_ISSUE_FRAMES_TABLE_SCHEMA.md` — Detailed schema spec

**Tests:**
- `tests/test_frame_helpers.py` — 12 tests for timestamp parsing
- `tests/test_publisher.py` — 54 tests including `TestBuildFrameRecords` class
- `tests/test_r2_uploader.py` — 23 tests including `upload_all_frames`
- `tests/test_publisher_cli.py` — 11 tests including `--skip-frames`, `--frame-sampling`, `--max-concurrent-uploads`

---

## Lessons Learned (March 3, 2026)

- **Frame Key deduplication:** `build_frame_records` uses `frames_by_key` dict to handle overlapping scene boundaries — scenes can share endpoint timestamps
- **Filename format:** `frame_{ts:05d}_t{ts:03d}.000s.png` — both numbers are the same integer timestamp
- **Parallel uploads with ThreadPoolExecutor:** `max_workers=1` falls back to sequential (safe default). `as_completed()` handles result collection
- **Frame sample rate applies at filename generation:** Both `frame_filenames` list and `build_frame_records` must use same `sample_rate` to stay in sync
- **Airtable 403 = table doesn't exist:** Not a permissions error on existing table — the Frames table needs to be created first
- **R2 credentials:** Use `export $(cat .env | xargs)` NOT `source .env` for Python subprocesses

---

## Quick Commands

```bash
# Run all Python tests
.venv/bin/python -m pytest tests/ -q

# Run Node.js tests
cd pipeline-server && npm test

# Demo frames upload (frame-sampling 30 = 1 per 30s, fast)
export $(cat .env | xargs)
.venv/bin/python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --frame-sampling 30 --max-concurrent-uploads 4

# Start pipeline server
cd pipeline-server && node server.js
```

---

## Open GitHub Issues Summary

| # | Title | Priority | Status |
|---|-------|----------|--------|
| [#18](https://github.com/thaddiusatme/airtable-shots-db/issues/18) | Create Frames Table Schema | **P0** | Open |
| [#19](https://github.com/thaddiusatme/airtable-shots-db/issues/19) | Chrome Extension Frames Integration | P1 | Blocked by #18 |
| [#17](https://github.com/thaddiusatme/airtable-shots-db/issues/17) | Publish 1fps Frames to Airtable | — | ✅ Code complete |
| [#16](https://github.com/thaddiusatme/airtable-shots-db/issues/16) | Pipeline Resumption | — | ✅ Complete |
| [#15](https://github.com/thaddiusatme/airtable-shots-db/issues/15) | Azure Cloud VLM | Future | Open |
| [#12](https://github.com/thaddiusatme/airtable-shots-db/issues/12) | Simplify end-to-end CLI | Future | Open |
