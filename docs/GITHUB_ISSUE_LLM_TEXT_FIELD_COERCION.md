# GitHub Issue: Normalize LLM Narrative Field Shapes Before Airtable Updates

## Summary

Live enrichment validation uncovered a new blocker after the markdown-fenced JSON parser fix and Airtable schema provisioning were resolved.

The publisher can now successfully call Ollama, parse the JSON response, and update several Airtable enrichment fields. However, some LLM responses still fail because fields that should be plain text are occasionally returned as arrays, numbers, or object-shaped values.

This causes Airtable `PATCH` requests to fail with `INVALID_VALUE_FOR_COLUMN` errors.

## Problem Statement

`publisher/shot_package.py::parse_llm_response()` currently normalizes some select-like fields (`Shot Type`, `Camera Angle`, `Movement`, `Lighting`, `Shot Function`) into Airtable-safe values, but narrative/text fields are still passed through too literally.

Observed failures from the live run included:

- `On-screen Text` receiving an object-like JSON value
- `Frame Progression` receiving numeric or array values such as `1`, `[0]`, `[1,2,3]`, or `["No frame progression provided"]`
- `How It Is Shot` receiving array values like `["Screen"]`

These are semantically recoverable values, but Airtable rejects them because the request payload shape does not match the target column type.

## Live Validation Evidence

Examples captured from the real publisher run:

```text
Cannot parse value "{...}" for field On-screen Text
Cannot parse value "1" for field Frame Progression
Cannot parse value "[0]" for field Frame Progression
Cannot parse value "[1,2,3]" for field Frame Progression
Cannot parse value "[\"No frame progression provided\"]" for field Frame Progression
Cannot parse value "[\"Screen\"]" for field How It Is Shot
```

At the same time, the same run showed that the earlier blockers were resolved:

- markdown-fenced Ollama JSON parsing worked
- Airtable enrichment fields existed in the base
- controlled-vocabulary normalization reduced select-field failures
- idempotent skip behavior worked for previously enriched shots
- several shots enriched successfully in the same run

## Root Cause

The LLM is not consistently respecting the intended value shape for free-text narrative fields.

Even with improved prompt instructions, models may still emit:

- arrays instead of strings
- numbers instead of strings
- object-like JSON structures when summarizing on-screen elements

The parser needs a second normalization layer for non-select narrative fields before values are sent to Airtable.

## Proposed Fix

### P0

Add Airtable-safe coercion for narrative/text fields in `publisher/shot_package.py`.

Target fields:

- `AI Description (Local)`
- `How It Is Shot`
- `Frame Progression`
- `Production Patterns`
- `Recreation Guidance`
- `On-screen Text`
- `Setting`
- `Subject`

Recommended coercion rules:

- string → keep as normalized string
- list[str] → join into readable text
- singleton list → unwrap to string
- numeric values → stringify
- dict/object → convert to stable readable text or JSON string
- empty/meaningless structures → omit field or emit safe fallback string

### P0.5

Strengthen prompt instructions so the model knows which fields must always be plain strings rather than arrays or objects.

### P1

Add regression tests covering malformed-but-recoverable narrative payloads from Ollama.

## Acceptance Criteria

- `parse_llm_response()` converts narrative enrichment fields into Airtable-safe string values
- arrays/numbers/objects in text fields no longer cause Airtable `INVALID_VALUE_FOR_COLUMN`
- existing select-field normalization still works
- markdown-fenced JSON parsing still works
- targeted `tests/test_shot_package.py` coverage passes
- a real publisher rerun shows successful enrichment writes without the current text-field shape errors

## Suggested TDD Plan

### Red

Add failing tests in `tests/test_shot_package.py` for:

- object-shaped `on_screen_text`
- numeric `frame_progression`
- array `frame_progression`
- array `how_it_is_shot`
- mixed list/object/string narrative coercion

### Green

Implement minimal coercion helpers in `publisher/shot_package.py` to normalize narrative fields before Airtable mapping.

### Refactor

Keep select-field normalization and narrative-field coercion separate so the parser remains readable and easy to extend.

## Scope Boundary

This issue is not about:

- changing Airtable schema types
- prompt-only mitigation without parser hardening
- altering the injected `enrich_fn` architecture
- broad publisher refactors

## Related Work

- Markdown-fenced Ollama JSON parsing fix
- Airtable enrichment field provisioning via `setup_airtable.py --add-enrichment-fields`
- controlled-vocabulary normalization for select-like enrichment fields
- idempotent enrichment rerun preservation / skip behavior
