# Design: Self-Healing Transcript Selectors

**Status:** Proposed (design only — not yet implemented)
**Author:** Thaddius + Claude
**Date:** 2026-07-13
**Related:** GH-67 (the manual instance of this loop), GH-8

## Problem

Transcript extraction in `chrome-extension/content.js` is DOM-based. YouTube ships
**multiple concurrent A/B panel variants** and periodically renames elements, so the
extractor silently returns **0 segments** whenever it hits a variant it doesn't know.
Each occurrence requires the same manual loop:

1. Notice extraction returns 0 segments despite a visible transcript.
2. Run console snippets against the live panel to find the new segment element and its
   timestamp/text structure.
3. Add the new tag to `SEGMENT_SELECTORS` and a per-row mapping branch.
4. Verify, commit, file an issue.

GH-67 (the `transcript-segment-view-model` / `PAmodern_transcript_view` variant) is the
canonical example. This is repetitive and mechanical — a good automation target.

## Constraint

Claude Code runs in the **terminal** and cannot drive Chrome or observe the live DOM.
Therefore a skill alone cannot self-heal; the **extension must produce the diagnostic
evidence**, and the heal step must be **verifiable without a browser**.

## Architecture

### Layer 1 — Extension self-diagnosis (the enabler)

When `segments.length === 0` after the panel opens, `content.js` currently returns a
dead-end error string. Replace that with a `captureUnknownVariant()` routine that emits a
structured artifact — the same data we gathered by hand for GH-67:

- Every `ytd-engagement-panel-section-list-renderer`: its `target-id`, `visibility`, and
  whether it contains an active spinner.
- Within the visible/expanded panel: a map of custom-element tag names → counts (the
  high-count tag is the candidate segment element — e.g. `transcript-segment-view-model` ×100).
- The `outerHTML` of one candidate row (for timestamp/text class discovery).
- Page context: video ID, URL, timestamp, extension version.

Surface it in the popup as a **"Report unknown variant"** action that copies the JSON to
the clipboard and/or downloads it. Outcome: an opaque failure becomes a structured hand-off.

### Layer 2 — The `/heal-transcript-selectors` skill

A skill in `.claude/skills/` that codifies the GH-67 loop:

1. Read the captured artifact (path pasted by the user, or a fixtures dir the extension writes to).
2. Infer the new segment tag + timestamp/text selectors from the captured `outerHTML`.
3. Patch `content.js`: add the tag to `SEGMENT_SELECTORS` and a per-row mapping branch
   (falling through to existing approaches — always additive, never replacing).
4. Run `node --check content.js` + `npm test`.
5. Draft a GitHub issue and commit referencing it (mirroring GH-67's format).

### Keystone — fixture-driven verification (makes Layer 2 browser-free)

Save each variant's captured segment HTML as a fixture:

```
chrome-extension/test/fixtures/variants/
  classic-ytd-transcript-segment-renderer.html
  modern-transcript-segment-view-model.html
```

Add a jsdom-based test that loads each fixture and asserts the extractor yields ≥1 segment
with non-empty text and a parsed timestamp. Then:

- **Known variants can never silently regress** — a future refactor that drops one fails CI.
- **The skill's job becomes deterministic:** drop the new fixture, extend the extractor until
  its test passes. No browser needed at heal-time.

This requires extracting the per-segment mapping logic out of `extractTranscript()` into a
pure, testable function (e.g. `parseSegment(el) -> {text, start}`) that both the content
script and the fixture test import.

## Build order (recommended)

1. **Refactor** per-segment mapping into a pure `parseSegment()` + `collectSegments(root)`.
2. **Fixture harness** seeded with classic + modern variants (jsdom test).
3. **Layer 1** `captureUnknownVariant()` + popup "Report unknown variant" action.
4. **Layer 2** `/heal-transcript-selectors` skill on top of the above.

Layers 1–3 are fully buildable and testable today without Chrome; the skill stands on them.

## Open questions

- Artifact transport: clipboard paste vs. a `fixtures/incoming/` dir the extension downloads to.
- Should the skill auto-commit/auto-file, or stop at a reviewable diff? (GH-67 was human-approved.)
- Fixture privacy: captured HTML may embed video titles/handles — scrub or keep?
- How to detect "silent partial" variants (some rows extracted, structure changed for others),
  not just the all-or-nothing 0-segment case.
