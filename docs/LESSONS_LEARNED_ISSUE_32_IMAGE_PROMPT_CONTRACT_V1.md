# Lessons Learned — GH-32: Image Prompt Contract v1

## TDD Iteration 14 — feature/gh-32-image-prompt-contract-v1

### What was built
- **`publisher/prompt_assembler.py`** — new module with deterministic per-shot SDXL/ComfyUI prompt assembler:
  - `assemble_shot_image_prompt(shot_fields, reference_frames=None) -> dict` — main entry point
  - `ASSEMBLER_VERSION = "1.0"` — version tracking constant
  - `_is_boilerplate(text)` — detects known boilerplate phrases (5 regex patterns)
  - `_should_omit_controlled(value)` — returns True for "Other" or missing controlled-vocab values
  - `_filter_narrative(value, field_name, omissions)` — filters boilerplate, tracks omissions
  - `_build_positive_prompt(sections)` — deterministic section concatenation in stable order
  - `_normalize_reference_frames(frames)` — ensures `role` defaults to "composition"
- **`tests/test_prompt_assembler.py`** — 29 golden tests across 7 test classes:
  - `TestCleanShotAssembly` (11 tests) — fully enriched shot, all fields present
  - `TestOtherHeavyShotOmissions` (6 tests) — Camera Angle + Lighting = Other → omitted
  - `TestBoilerplateFiltering` (4 tests) — narrative boilerplate suppression
  - `TestReferenceFrames` (3 tests) — frames present/absent/default-role
  - `TestMinimalShot` (3 tests) — only required fields (Shot Label, Subject, Setting)
  - `TestDeterministicOutput` (2 tests) — repeated invocations produce identical JSON
- **`docs/IMAGE_PROMPT_CONTRACT_V1.md`** — full contract specification with input/output schema, omission rules, 2 concrete examples, open questions
- **222/222 tests pass** (29 new + 193 existing), 0 regressions

### Key lessons

1. **Assembler consumes Airtable field names, not LLM keys**: The enrichment pipeline stores data in Airtable with column names (e.g., "Camera Angle", "How It Is Shot"). The assembler reads these directly — no need to reverse-map through `SHOT_ENRICHMENT_FIELDS`. This keeps the assembler decoupled from the LLM enrichment internals.

2. **ImportError RED signal is still the cleanest**: Importing `ASSEMBLER_VERSION` and `assemble_shot_image_prompt` from a non-existent module causes immediate `ModuleNotFoundError` at collection time. All 29 tests blocked — unambiguous RED with zero test bodies executed.

3. **All 29 tests passed on first GREEN attempt**: The contract was well-specified enough from the GH-31 audit and execution plan that no iteration was needed between RED → GREEN. Pre-planning with concrete fixture data (clean shot, Other-heavy shot, minimal shot) eliminated ambiguity in what the implementation needed to do.

4. **Omission-over-noise is the right default for SDXL prompts**: Including "Other" in a positive prompt actively degrades SDXL output quality. The assembler omits low-signal controlled vocab and tracks omissions in `metadata.omissions` for operator visibility. This matches the GH-31 audit finding that 6/16 shots had Camera Angle = Other.

5. **Boilerplate detection via compiled regex is cheap and extensible**: Five `re.compile()` patterns catch the common LLM boilerplate phrases ("No pattern information provided.", "Not enough information to determine..."). New patterns can be added to `_BOILERPLATE_PATTERNS` without touching the assembler logic. Pre-compilation avoids re-compiling on each call.

6. **Stable section ordering eliminates non-determinism**: `_build_positive_prompt()` iterates a fixed tuple `("subject", "setting", "composition", "camera", "lighting", "style", "context", "constraints")` rather than dict key order. Combined with no randomness anywhere in the module, the deterministic output tests pass trivially.

7. **Separate module, not extension of shot_package**: The assembler is a distinct concern from LLM enrichment. `shot_package.py` handles LLM ↔ Airtable translation; `prompt_assembler.py` handles Airtable → image-generation translation. Different consumers, different lifecycles, zero import dependency between them.

8. **Reference frames use `{url, role}` for forward compatibility**: The `role` field defaults to `"composition"` but the schema allows future values like `"character"`, `"style"`, `"lighting_reference"`. This was a deliberate forward-compatible design from the execution plan.

9. **Negative prompt is static in v1 — and that's correct**: Shot-derived negative exclusions (e.g., "indoor" when Setting is "outdoor") require more validation data. The baseline `"blurry, deformed, low quality, watermark..."` covers universal SDXL quality issues. Documented as open question for v2.

10. **Contract spec doc serves as both human reference and test oracle**: The two concrete examples in `IMAGE_PROMPT_CONTRACT_V1.md` can be used as manual validation fixtures. The examples were written to match the test fixture data, ensuring consistency between spec and implementation.

### Test count progression
- Previous iteration (GH-43 provider inference): 193 in-scope tests
- This iteration (GH-32 prompt contract): 222 in-scope (29 new), 0 regressions

### Refactor was minimal
- Removed unused `pytest` import from test file
- Implementation was already well-structured from GREEN phase (extracted helpers, clear sections, docstrings)
- No structural refactor needed — the module pattern (constants → helpers → main function) matched existing codebase conventions

### Next steps
- **P1-A**: Apply assembler to 3-5 real audited shots from Airtable, review SDXL usability
- **P1-B**: Refine `metadata.omissions` wording based on live output review
- **P1-C**: Document negative prompt strategy findings
- **P2**: Wire assembler into pipeline (CLI flag or orchestrator step)
- **P2**: Global video style extraction (cross-shot tokens)
- **P2**: Midjourney/ChatGPT single-string contract (GH-45)
