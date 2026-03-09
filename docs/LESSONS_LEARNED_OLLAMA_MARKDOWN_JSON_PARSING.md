# Lessons Learned: Ollama Markdown JSON Parsing

## Date
2026-03-09

## Branch
`fix/ollama-markdown-json-parsing`

## Focus
Make `publisher/shot_package.py::parse_llm_response()` robust to markdown-fenced JSON returned by Ollama vision models.

---

## What We Learned

### 1. The parser was the real bottleneck
The live demo confirmed that the Ollama adapter, CLI wiring, and frame transport were already working. The failure mode was downstream: valid structured output was being rejected because it was wrapped in markdown fences.

### 2. Normalize at the parser boundary, not in the adapter
Keeping the fix in `parse_llm_response()` preserves the existing architecture:

- provider adapters focus on API transport
- `publish_to_airtable()` stays provider-agnostic
- the parser owns response-shape normalization before JSON decoding

This is the smallest change that fixes the critical path without leaking Ollama-specific behavior into orchestration code.

### 3. RED was clean once the correct test environment was used
The first test run failed during collection because system Python did not have project dependencies. Re-running with the project venv produced the real RED signal: the three new markdown-fence tests failed while the existing parser tests stayed green.

### 4. A small helper was enough for GREEN + refactor
A single private helper, `_normalize_llm_json_response()`, handled the required cases:

- surrounding whitespace
- fenced JSON with `json` language tag
- fenced JSON without a language tag

This kept `parse_llm_response()` readable and avoided broad parser complexity.

### 5. Preserve original raw responses for auditability
Even though parsing now uses normalized content, `AI JSON` should still store the original raw model output. That preserves the actual provider response for debugging, migrations, and future parser improvements.

### 6. Large live demos can block iteration flow
The real Airtable/R2/Ollama demo run was much slower than the code/test slice because it used a long capture with verbose logging and many uploads. For future iterations, use a shorter capture or less verbose mode when the runtime system is not the primary subject of the fix.

---

## What Went Well

- The bug was isolated with narrow regression tests
- The GREEN fix was minimal and localized
- Existing parser behavior stayed intact
- The interface and architecture did not need to change

---

## What Could Be Improved

- Add a smaller canonical demo capture for operational validation
- Consider future support for prose plus embedded JSON blobs
- Reduce noisy live-demo logging when validating parser-only changes

---

## Next Steps

- Complete live Airtable validation after the long-running demo finishes
- Re-run the same capture to confirm idempotent enrichment skip behavior remains intact
- Consider a future fallback parser for mixed prose + JSON outputs
