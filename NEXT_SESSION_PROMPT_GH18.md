# Next Session Prompt — GH #18: Frames Table Schema

## The Prompt

Let's create a new branch for the next feature: `frames-table-schema`. We want to perform TDD framework with red, green, refactor phases, followed by git commit and lessons learned documentation. This equals one iteration.

---

## Updated Execution Plan (focused P0/P1)

We need to add the **Frames table** to the existing Airtable base without touching or duplicating the existing Channels/Videos/Shots tables. The publisher code is 100% ready (202 tests passing) — the only blocker is the missing Airtable table (403 Forbidden on publish).

I'm following the TDD discipline in this repo (red → green → refactor → commit) and the additive-only schema constraint documented in GH #18.

**Critical path:** `setup_airtable.py` calls `workspace.create_base(...)` — re-running it creates a brand-new duplicate base. We must write a separate additive function `add_frames_table()` that operates only on the **existing** base ID (`appWSbpJAxjCyLfrZ`) and adds ONLY the Frames table.

---

## Current Status

**Completed:**
- Frames publisher code (TDD iterations 1–4): `parse_timestamp_from_filename()`, `build_frame_records()`, `upload_all_frames()`, full idempotency, `--skip-frames`, `--frame-sampling`, `--max-concurrent-uploads`
- 202 tests passing (190 Python + 12 Node.js)
- 34 frames uploaded to R2 from `bjdBVZa66oU` demo — publisher confirmed working
- GH issues #18 (P0) and #19 (P1 blocked by #18) created

**In progress:** Create Frames table in existing Airtable base — `setup_airtable.py::add_frames_table()` (GH #18)

**Lessons from last iteration:**
- `setup_airtable.py::build_schema()` calls `workspace.create_base()` — never re-run it; it creates a duplicate base, not an additive change
- Airtable 403 = table doesn't exist (not a permissions issue on an existing table)
- Frame Key deduplication: `build_frame_records()` uses a `frames_by_key` dict — scenes can share boundary timestamps
- `export $(cat .env | xargs)` NOT `source .env` for Python subprocess env vars

---

## P0 — Frames Table Schema Creation (GH #18)

**`add_frames_table()` in `setup_airtable.py`:** Additive-only function targeting the EXISTING base

1. Accept `base_id` as parameter (default: `appWSbpJAxjCyLfrZ` from env or arg)
2. Fetch current schema → get `videos_table_id` and `shots_table_id` from existing tables
3. Call `api.base(base_id).create_table("Frames", ...)` (NOT `workspace.create_base`)
4. Add all 6 additional fields via `create_field()`: Video (link), Shot (link), Timestamp (sec), Timestamp (hh:mm:ss), Frame Image, Source Filename
5. Guard: if Frames table already exists, skip creation and print a warning (idempotent)

**Safety constraint:** Function must NOT call `workspace.create_base()` or modify existing tables. Only adds.

**Validation run (after table creation):**

```bash
set -a && source .env && set +a
.venv/bin/python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --frame-sampling 30 \
  --max-concurrent-uploads 4
```

Expected: `Created 34 Frame records` — no 403 errors.

**Acceptance Criteria:**
- `add_frames_table()` runs without error against existing base
- Frames table exists in Airtable UI with all 7 fields (Frame Key + 6 added)
- Video and Shot linked record fields point to correct existing tables
- Validation publish creates 34 Frame records with R2 image attachments
- `--skip-frames` still works (no regression to existing Shots/Videos flow)
- Existing Channels/Videos/Shots tables are untouched

---

## P1 — Chrome Extension Frames Integration (GH #19) — blocked by P0

**`pipeline-server/orchestrator.js`:** Add `--max-concurrent-uploads` to publish step

```javascript
'--max-concurrent-uploads', '8',
```

**`chrome-extension/popup.js` / `popup.html`:** Expose frame controls (frame sampling slider or checkbox)

**Migration strategy:** No data migration needed — Frames table starts empty; publisher fills it on next run.

**`setup_airtable.py` update:** Add `add_frames_table()` to `__main__` block so it can be called standalone:

```bash
python setup_airtable.py --add-frames-only
```

**Acceptance Criteria:**
- Chrome extension triggers pipeline including frame upload step
- Frame sampling rate configurable from extension UI
- No regression to existing shot pipeline flow

---

## P2 — Polish & Pipeline Hardening

- **Step output validation** — Check `analysis.json` exists before skipping analyze step in orchestrator
- **`--force-step` flag** — Re-run specific pipeline steps on demand
- **Idempotent R2 uploads** — HEAD check before upload (skip existing objects)
- **End-to-end integration test** — Fresh short video: Capture → Analyze → Publish → Frames

---

## Task Tracker

- [In progress] GH-18: Create Frames table in existing Airtable base (additive)
- [Pending] GH-18: Validate with real publish (34 Frame records expected)
- [Pending] GH-19: Add `--max-concurrent-uploads` to orchestrator.js
- [Pending] GH-19: Chrome extension frame controls
- [Pending] P1: Step output validation in orchestrator
- [Pending] P1: `--force-step` CLI flag

---

## TDD Cycle Plan

**Red Phase:**
Write `tests/test_setup_airtable.py` with:
- `test_add_frames_table_creates_table_with_correct_fields()` — mocks `api.base().create_table()` and `create_field()`, asserts called with correct payloads
- `test_add_frames_table_skips_if_already_exists()` — mocks schema fetch returning existing Frames table, asserts `create_table` not called
- `test_add_frames_table_does_not_call_create_base()` — asserts `workspace.create_base` is never called

**Green Phase:**
Add `add_frames_table(base_id)` to `setup_airtable.py`:
- Fetch schema
- Guard: return early if "Frames" in `[t.name for t in schema.tables]`
- `api.base(base_id).create_table("Frames", [{"name": "Frame Key", "type": "singleLineText"}])`
- Re-fetch schema, get `frames_table_id`, `videos_table_id`, `shots_table_id`
- 6x `create_field()` calls per GH #18 spec

**Refactor Phase:**
- Extract `get_table_id(schema, name)` helper (already used inline 3 times)
- Add `--add-frames-only` CLI flag to `__main__` block
- Update docstring/comment block in `build_schema()` noting it creates a NEW base

---

## Key Files

| File | Role |
|------|------|
| `setup_airtable.py` | Add `add_frames_table()` here — DO NOT re-run `build_schema()` |
| `publisher/publish.py` | `build_frame_records()`, Frames integration — already complete |
| `publisher/cli.py` | `--skip-frames`, `--frame-sampling`, `--max-concurrent-uploads` — already complete |
| `pipeline-server/orchestrator.js` | Add `--max-concurrent-uploads` flag (GH #19, after P0) |
| `chrome-extension/popup.js` | Frame controls (GH #19, after P0) |
| `tests/test_setup_airtable.py` | NEW — red phase TDD tests for `add_frames_table()` |
| `docs/GITHUB_ISSUE_FRAMES_TABLE_SCHEMA.md` | Full schema spec for GH #18 |

---

## Existing Airtable Base (DO NOT RECREATE)

```
Base ID:   appWSbpJAxjCyLfrZ
Tables:    Channels, Videos, Shots  ← already populated with real data
Missing:   Frames                   ← add this only
```

---

## Quick Commands

```bash
# Run all Python tests (must stay green before and after P0)
.venv/bin/python -m pytest tests/ -q

# Run Node.js tests
cd pipeline-server && npm test

# After add_frames_table() implemented — run it
set -a && source .env && set +a
.venv/bin/python setup_airtable.py --add-frames-only

# Validation publish (frame-sampling 30 = 1 per 30s, low volume)
.venv/bin/python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --frame-sampling 30 --max-concurrent-uploads 4

# Regression check — shots-only publish (must still work)
.venv/bin/python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --skip-frames
```

---

Would you like me to implement `add_frames_table()` now in `setup_airtable.py` with a TDD-first approach (write the failing test first, then the implementation)?
