# Lessons Learned — GH-32 Slice 2: Live Validation + Assembler Refinement

## TDD Iteration 15 — feature/gh-32-image-prompt-contract-v1 (Slice 2)

### What was built

- **`scripts/validate_prompt_assembler.py`** — one-time validation harness:
  - Pulls enriched shots from Airtable via pyairtable (formula: `AI Prompt Version != ''`)
  - Runs `assemble_shot_image_prompt()` on each, prints structured output + full JSON
  - Shot classification: clean / other-heavy / minimal / partial
  - Summary with omission frequency counts
  - CLI flags: `--limit`, `--video-id`, `--json-only`

- **`publisher/prompt_assembler.py` v1.1** — two output-affecting fixes:
  - `_UNINFORMATIVE_NARRATIVES` frozenset: filters `"other"`, `"yes"`, `"no"`, `"n/a"`, `"na"`, `"none"`, `"static"`, `"unknown"` from narrative fields
  - Empty `subject`/`setting` excluded from `prompt_sections` (previously always present as empty strings)
  - `ASSEMBLER_VERSION` bumped `1.0` → `1.1`

- **8 new golden tests** in `tests/test_prompt_assembler.py`:
  - `TestShortUninformativeNarratives` (5 tests): Other/Yes/Static in narrative fields, real guidance passthrough, positive prompt exclusion
  - `TestEmptySectionsCleanup` (3 tests): empty subject/setting excluded, no leading commas

- **`docs/IMAGE_PROMPT_CONTRACT_V1.md`** updated to v1.1:
  - New "Short uninformative narratives" omission rule section
  - Negative prompt strategy documented (deferred to v2 with rationale)
  - `prompt_sections` note updated for empty field exclusion
  - All version references bumped

- **37/37 prompt assembler tests pass**, **230/230 in-scope cross-module pass**, 0 regressions

### Key findings from live validation

1. **75% of shots had Lighting = "Other"** — omission tracking works correctly, but this suggests Lighting enrichment quality is low for screen-recording content. The assembler's omission-over-noise rule is validated.

2. **Many "enriched" shots had ALL empty fields** — `llava:latest` model produced empty parse results but still got `AI Prompt Version` stamped (the pre-fix/gh-38 success criteria bug). These shots have `AI Prompt Version: "1.0"` or `"1.1"` but zero enrichment content. The assembler handles this gracefully (produces empty prompt), but it means the Airtable data has a data quality issue upstream.

3. **Controlled-vocab values leak into narrative fields** — `How It Is Shot: "Other"`, `Production Patterns: "Static"`. The LLM sometimes copies controlled-vocab terms into free-text fields. The `_UNINFORMATIVE_NARRATIVES` filter catches these at the assembler layer.

4. **`Frame Progression: "Yes"` is a real pattern** — The LLM answers the implicit question "Is there frame progression?" with "Yes" instead of describing what changes. This is a prompt engineering issue upstream but the assembler now filters it.

5. **Prompt lengths vary wildly**: 0 chars (empty shots) to 1394 chars (verbose qwen2.5-vl output). SDXL works best at ~300-600 chars. Prompt truncation or summarization may be needed in v2.

6. **Negative prompt from shot context is not viable in v1** — Setting values like "Digital interface" or "Computer screen" don't map cleanly to exclusion terms. Documented as deferred.

### Key lessons

1. **Live validation before pipeline wiring is the correct gate**: Running the assembler against 10+ real shots revealed 3 edge cases that synthetic golden tests missed. The 30-minute validation investment prevented shipping broken prompts into the generation pipeline.

2. **Uninformative narrative filter is a third defense layer**: Layer 1 = controlled-vocab normalization in `parse_llm_response()`. Layer 2 = boilerplate regex in assembler. Layer 3 = uninformative single-word filter. Each layer catches a different failure mode.

3. **`frozenset` membership test is the right pattern for short-value filtering**: O(1) lookup, immutable, clear intent. The 8-value set covers all observed cases from live data. New values can be added without touching filter logic.

4. **Empty required fields should be conditional, not always-present**: The v1.0 decision to always include `subject` and `setting` in `prompt_sections` created empty strings in the output dict. For downstream consumers iterating over sections, empty strings are a footgun. Conditional inclusion is cleaner.

5. **Validation script as a one-time harness, not a test**: The script hits real Airtable — it can't run in CI. But it's reusable for future validation passes when enrichment quality improves or new edge cases appear.

6. **RED phase had 6 FAIL, 2 PASS**: The 2 passing tests were backward-compat guards (`test_real_recreation_guidance_passes_through` and `test_positive_prompt_still_works_without_subject_setting`). Expected — real content should always pass through unchanged.

### Test count progression

- Slice 1 (v1.0 contract): 29 tests, 222 in-scope
- Slice 2 (v1.1 live validation): 37 tests (+8 new), 230 in-scope, 0 regressions

### Next steps

- **P1**: Re-run validation script after enrichment quality improvements (better model, prompt tuning)
- **P2-A**: Wire assembler into publisher CLI (`--assemble-prompts` flag)
- **P2-B**: Global video style extraction (cross-shot tokens)
- **P2-C**: Prompt length awareness / truncation strategy for SDXL token limits
- **P2-D**: Midjourney/ChatGPT single-string contract (GH-45)
