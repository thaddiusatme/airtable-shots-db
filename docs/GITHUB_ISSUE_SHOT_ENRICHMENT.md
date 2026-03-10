# GitHub Issue: Shot-Level LLM Enrichment Pipeline

**Title:** Implement Shot-Level LLM Enrichment for Airtable Shot Records  
**Labels:** `enhancement`, `enrichment`, `llm`, `publisher`, `airtable`  
**Priority:** P1 — Core Implemented, Production Wiring Pending  
**Branches:** `feature/shot-package-llm-enrichment`, `feature/airtable-shot-enrichment-schema`, `feature/airtable-shot-enrichment-idempotency`

---

## Status Summary

The core GH-23 enrichment architecture is implemented and test-covered:

- shot package assembly
- prompt payload generation
- publisher integration
- schema alignment for the 4 new multiline enrichment fields
- idempotent re-run behavior that preserves old enrichment

The main follow-up work is production wiring:

- real LLM client adapter
- CLI exposure for enrichment
- optional force re-enrichment / prompt-version-aware re-enrichment

---

## Problem Statement

Shot records in Airtable contain structural metadata (timestamps, labels, scene boundaries) but lack **descriptive analysis** of what each shot contains — camera work, lighting, subject, function, and how to recreate it.

This metadata is essential for:
- Searching and filtering shots by visual characteristics
- Understanding production patterns across videos
- Providing recreation guidance for content production

Manually annotating shots is impractical at scale. An LLM can analyze frame images and transcript context to generate structured shot descriptions automatically.

---

## Solution

Add an **opt-in LLM enrichment pipeline** to the publisher that:

1. Packages each shot's frames, transcript, and metadata into a structured prompt
2. Calls an injected LLM function to generate structured JSON analysis
3. Parses the response into 13 Airtable-ready fields
4. Writes enrichment fields + AI metadata to each Shot record
5. Skips already-enriched shots on re-run (idempotent)
6. Isolates failures per-shot (one failure doesn't block others)

---

## Airtable Enrichment Fields

### LLM Output Fields (13)

| Airtable Column | LLM Key | Schema Note | Description |
|---|---|---|---|
| AI Description (Local) | `scene_summary` | Existing field | Brief description of the shot |
| How It Is Shot | `how_it_is_shot` | Added by GH-23 helper (`multilineText`) | Camera technique narrative |
| Shot Type | `shot_type` | Existing field in `Shots` schema | e.g., Medium Shot, Close-Up |
| Camera Angle | `camera_angle` | Existing field in `Shots` schema | e.g., Eye Level, High Angle |
| Movement | `movement` | Existing field in `Shots` schema | e.g., Static, Pan, Dolly |
| Lighting | `lighting` | Existing field in `Shots` schema | e.g., Studio, Natural |
| Setting | `setting` | Existing field in `Shots` schema | e.g., Home studio, Outdoors |
| Subject | `subject` | Existing field in `Shots` schema | e.g., Speaker, Product |
| On-screen Text | `on_screen_text` | Existing field in `Shots` schema | Visible text in frames |
| Shot Function | `shot_function` | Existing field in `Shots` schema | e.g., Introduction, B-Roll |
| Frame Progression | `frame_progression` | Added by GH-23 helper (`multilineText`) | How frames evolve over time |
| Production Patterns | `production_patterns` | Added by GH-23 helper (`multilineText`) | Repeatable production techniques |
| Recreation Guidance | `recreation_guidance` | Added by GH-23 helper (`multilineText`) | How to recreate this shot |

### AI Metadata Fields (4)

| Airtable Column | Populated By | Purpose |
|---|---|---|
| AI Prompt Version | Publisher | Tracks prompt template revision (currently `"1.0"`) |
| AI Updated At | Publisher | ISO 8601 timestamp of last enrichment |
| AI Model | Publisher | LLM model identifier (e.g., `gpt-4o`) |
| AI Error | Publisher | Error message if enrichment failed |

---

## Implementation — Completed Slices

### Slice 1: Shot Package Contract ✅
**Commit:** `0719744` | **Branch:** `feature/shot-package-llm-enrichment`

- `publisher/shot_package.py` — new module
- `collect_shot_frames()` — gather frames for a shot in stable order
- `build_shot_package()` — assemble scene + frames + transcript for LLM
- `parse_llm_response()` — map structured LLM JSON → Airtable fields
- `SHOT_ENRICHMENT_FIELDS` — explicit LLM key → Airtable column mapping
- 41 new tests in `tests/test_shot_package.py`

### Slice 2: Prompt Payload Builder ✅
**Commit:** `bb1aaf9` | **Branch:** `feature/shot-package-llm-enrichment`

- `AI_PROMPT_VERSION = "1.0"` constant
- `build_enrichment_prompt(shot_package)` → `{system_prompt, user_prompt, frame_references, prompt_version}`
- API-agnostic prompt dict (no OpenAI/Anthropic coupling)
- System prompt instructs JSON output with all 13 enrichment keys
- Handles empty frames/transcript edge cases
- 21 new tests in `TestBuildEnrichmentPrompt`

### Slice 3: Publisher Integration ✅
**Commit:** `9c31802` | **Branch:** `feature/shot-package-llm-enrichment`

- `publish_to_airtable()` gains `enrich_shots`, `enrich_fn`, `enrich_model` params
- Per-shot enrichment loop after shot creation
- Dependency-injected `enrich_fn` callable (no hardcoded LLM client)
- Per-shot error isolation — failures write `AI Error`, don't block other shots
- `shots_enriched` count in return summary
- 10 new tests in `TestEnrichmentIntegration`

### Slice 4: Airtable Schema Alignment ✅
**Commit:** `45bc4f2` | **Branch:** `feature/airtable-shot-enrichment-schema`

- `ENRICHMENT_FIELD_DEFINITIONS` constant in `setup_airtable.py`
- `add_enrichment_fields(base_id)` — adds the 4 new GH-23 multiline fields that were not already present in the base:
  - How It Is Shot, Frame Progression, Production Patterns, Recreation Guidance
- Field-level idempotency (skips fields that already exist)
- `--add-enrichment-fields` CLI flag
- Contract tests verifying all enrichment fields are provisioned
- 11 new tests in `test_setup_airtable.py`

### Slice 5: Idempotent Re-run ✅
**Commit:** `d89c759` | **Branch:** `feature/airtable-shot-enrichment-idempotency`

- `is_shot_enriched(fields)` — pure helper; returns True if `AI Prompt Version` is truthy
- Read old shot records before deletion to capture enrichment state
- `old_enrichment_by_label` mapping (Shot Label → fields dict)
- Enriched shots: old fields copied to new records, LLM call skipped
- AI Error-only shots (no AI Prompt Version): eligible for retry
- `shots_skipped_enrichment` count in return summary
- 8 integration + 6 unit tests (14 new)

---

## Test Coverage

| Test File | Enrichment Tests | Total |
|---|---|---|
| `tests/test_shot_package.py` | 62 | 62 |
| `tests/test_publisher.py` | 24 (10 integration + 8 idempotency + 6 unit) | 96 |
| `tests/test_setup_airtable.py` | 11 (schema + contract) | 19 |
| **Total enrichment-related** | **97** | |
| **Total project** | | **297** |

---

## Architecture

```
publish_to_airtable(enrich_shots=True, enrich_fn=my_llm_fn)
  │
  ├─ Read old shot records (if existing video)
  │   └─ Build old_enrichment_by_label mapping
  │
  ├─ Delete old shots → Create new shots
  │
  └─ Enrichment loop (per shot):
      │
      ├─ is_shot_enriched(old_fields)?
      │   ├─ YES → Copy old fields to new record, skip LLM
      │   └─ NO  → Continue to LLM enrichment
      │
      ├─ collect_shot_frames(scene, manifest)
      ├─ build_shot_package(scene, frames, transcript, video_id)
      ├─ build_enrichment_prompt(package)
      ├─ enrich_fn(prompt)  ← injected callable
      ├─ parse_llm_response(raw_response)
      └─ shots_table.update(record_id, fields)
```

### Key Design Decisions

- **Dependency injection** — `enrich_fn` callable, not a hardcoded LLM client
- **Opt-in** — `enrich_shots=False` by default; existing publish flows unaffected
- **Per-shot isolation** — one failed enrichment doesn't block others
- **Whitelist field copying** — only enrichment fields preserved on re-run
- **AI Prompt Version as enrichment signal** — single-field check, clean contract

---

## CLI Usage

The schema helper is available from the command line today. The publisher enrichment path is currently available through `publish_to_airtable()` parameters, but a production-ready CLI LLM adapter is still pending.

```bash
# Add missing enrichment fields to Airtable schema
AIRTABLE_BASE_ID="$AIRTABLE_BASE_ID" \
.venv/bin/python setup_airtable.py --add-enrichment-fields
```

---

## Remaining Work

### Not Yet Implemented

- [ ] **`--force-reenrich` CLI flag** — bypass skip logic, re-enrich all shots
- [ ] **Prompt version-aware re-enrichment** — auto re-enrich when `AI_PROMPT_VERSION` changes
- [ ] **End-to-end validation** — test with real LLM API (OpenAI / Anthropic / local Ollama)
- [ ] **CLI wiring for enrichment** — `publish_to_airtable()` supports enrichment params, but `publisher/cli.py` does not yet expose a production-ready LLM adapter path
- [ ] **Chrome extension integration** — trigger enrichment from extension pipeline
- [ ] **Cost/rate limiting** — track token usage, add configurable rate limits
- [ ] **Batch enrichment** — enrich shots from multiple videos in one run

### Known Limitations

- Shot matching uses Shot Label (e.g., "S01") which is deterministic from `sceneIndex`. If scene ordering changes between analysis runs, label matching could mismatch.
- `enrich_fn` is injected but no production LLM client adapter exists yet. Tests use mocks.
- No prompt version migration path — changing `AI_PROMPT_VERSION` currently doesn't trigger re-enrichment.

---

## Acceptance Criteria

- [x] Shot records can be enriched with 13 structured LLM output fields
- [x] Enrichment is opt-in and backward-compatible
- [x] Per-shot error isolation prevents one failure from blocking others
- [x] Re-running with enrichment enabled skips already-enriched shots
- [x] Failed shots (AI Error only) are automatically retried on re-run
- [x] Old enrichment data is preserved when shots are recreated
- [x] Airtable schema includes all required enrichment fields
- [x] `shots_enriched` and `shots_skipped_enrichment` counts in summary
- [ ] At least one real LLM client adapter works end-to-end
- [ ] `--force-reenrich` flag available for manual override
- [ ] Prompt version changes trigger selective re-enrichment

---

## Commits (Chronological)

| Commit | Date | Description | Tests Added |
|---|---|---|---|
| `0719744` | Mar 8, 2026 | Shot package contract + LLM response parser | 41 |
| `bb1aaf9` | Mar 8, 2026 | Prompt payload builder + AI_PROMPT_VERSION | 21 |
| `9c31802` | Mar 8, 2026 | Publisher enrichment integration | 10 |
| `45bc4f2` | Mar 8, 2026 | Schema alignment (4 missing fields) | 11 |
| `d89c759` | Mar 8, 2026 | Idempotent re-run (skip enriched shots) | 14 |
| **Total** | | | **97** |

---

## Related

- `CURRENT_STATE.md` — Current project state (updated to reflect GH-23 core completion and remaining follow-up work)
- `docs/ISSUE_SHOT_LIST_PIPELINE.md` — Original shot list pipeline spec
- `docs/GITHUB_ISSUE_CI_DEVELOPER_EXPERIENCE.md` — CI/DX framework (separate track)
