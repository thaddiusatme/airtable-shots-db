# GH-70: Browser-automation click delivery is unreliable enough to justify redesigning the harvest loop

## Summary

Across a single harvest session against playlist `PLVwTAkoVGJsY` ("AI (Claude)"), driving the
extension's Extract & Save button via Claude in Chrome (Chrome DevTools Protocol automation)
showed three distinct, independent failure modes — not one bug, three — all rooted in the same
underlying problem: **a CDP-driven click is not equivalent to a real user click, and YouTube (or
Chrome itself) appears to treat them differently in ways that are inconsistent and not fully
diagnosable from inside the extension.** One operational workaround (fresh tab per video) recovered
most of the batch, but a fundamentally different failure (click delivered to the correct element,
handler never fires, zero downstream effect) surfaced on a video that workaround didn't fix. This
doc recommends treating that as the signal to stop patching around CDP automation and move the
click-delivery layer to real OS-level input (a Python GUI-automation script), while keeping
everything upstream (queue logic, Airtable I/O, verification) as-is.

## Failure mode 1 (known, GH-68): stale-token 400 on a claimed-fresh load

Already documented in `CLAUDE.md` — `get_transcript` returns a 400 that the extension has no
retry for. Confirmed again this session via `read_network_requests`, including on genuinely fresh
full-page loads (not just post-SPA-nav), which the existing GH-68 writeup didn't establish as
occurring.

**Attempted fix**: prefer YouTube's native "In this video → Transcript" tab
(`findTranscriptTab()`), on the theory that its client-side code silently retries once after a 400
— confirmed exactly once via a real manual click. **Reverted the same day**: re-tested live through
the extension's own scripted click against 2 fresh, never-attempted videos, and both produced
**zero** `get_transcript` requests at all — worse than the bug being fixed. See the dead-end
comment left in `content.js` above `findBestTranscriptButton()`. Root cause: the tab element
apparently requires a real trusted click to do anything; the description button at least fires a
(failing) request under a scripted click. This is failure mode 2, encountered while trying to fix
failure mode 1.

## Failure mode 2 (GH-69, reconfirmed): scripted click never reaches YouTube's handler

Already documented in GH-69. Reconfirmed this session on the reverted `findTranscriptTab()` code:
2/2 fresh videos, real extension code path, zero network requests — not even a 400. Consistent with
GH-69's finding that some UI elements need a real trusted click to do anything at all, and that a
CDP/`javascript_tool`-issued click can silently no-op on them.

## Failure mode 3 (new): a real `computer` `left_click`, on the verified-correct element, does not
trigger the button's own listener

This is the one that motivates the redesign, because it defeats the mitigation GH-69 already
prescribes (use a real `computer` click, not a scripted one).

**Video**: `ovabeVoWrA0` — "Claude Design 2 HOUR COURSE (Beginner to Pro)".

**Repro**:
1. Close all tabs, open one fresh tab, navigate directly to the video (full page load).
2. Wait for `#yt-transcript-panel` to reach `data-video-id` matching the URL and
   `data-save-state="idle"`.
3. Confirm via `document.elementFromPoint(x, y)` that the coordinates about to be clicked resolve
   to exactly `button[data-testid="extract-save-btn"]` — not an overlay, not a different element.
4. Issue a real `computer` `left_click` at those exact coordinates.
5. `data-save-state` remains `idle`. No state transition at all.
6. Repeat step 4 four more times (verifying coordinates fresh each time — the button's
   `getBoundingClientRect()` was rechecked before every click and never moved), plus one
   `double_click`, plus one click via the `find`-tool's element reference instead of raw
   coordinates. **All six attempts produced identical no-op behavior.**
7. Enabled console tracking from before the click. Content script's own `console.log` calls
   (`"Clicking transcript button..."` etc., emitted from inside `onExtractSaveClick`) **never
   appear** — meaning the click event is not reaching the button's registered listener at all, not
   that the listener ran and did nothing. The one console message that did appear
   (`ApolloError: Response not successful: Received status code 403`) is from a *different*,
   unrelated Chrome extension (`bnebanooamokkihfjepphafoekheipfh`) sharing the browser profile —
   noise, not signal.
8. `document.hasFocus()` was `true` throughout; `document.activeElement` stayed `BODY` even
   immediately after each click, which is itself abnormal — a real click on a `<button>` should
   normally focus it.

**This is distinct from GH-69.** GH-69 is "the click fires, the handler runs, but YouTube's own
downstream request never gets triggered." This is "the click never reaches the handler in the
first place," on an element independently confirmed to be the right one, at the right coordinates,
not covered by anything, not disabled. Six different click deliveries, zero effect. No plausible
DOM-level explanation was found; no console error, no network request, no focus change.

## Operational workaround found this session (works for failure modes 1 & 2, not 3)

**Close the previous tab, then open a brand-new tab per video** (not just a fresh `navigate()` in
a reused tab) recovered 5 of 6 videos attempted, including two (`ib74sLgjIBM`, `vmVvpKSSxWE`) that
had been failing repeatedly for over an hour in a reused tab. Already logged in `CLAUDE.md` under
the 2026-07-27 retro with the appropriate caveats (small sample, possible confound with elapsed
time). This workaround did **not** help `ovabeVoWrA0` — tried in a freshly-closed-then-reopened tab
with the same six-click battery above, same result.

## Why this is a redesign trigger, not just another bug to patch

Three different, independent failure modes, in one session, all clustering around "the click
didn't do what a real click would do" — with the mitigations for each (retry logic, real clicks
instead of scripted ones, fresh tabs) each fixing some cases and not others, and with failure mode 3
defeating the most reliable mitigation found so far. Continuing to chase this by adding more retry
layers and more heuristics inside `content.js` treats the symptom, not the cause: **CDP-mediated
input (however it's issued — `javascript_tool`, or Claude in Chrome's `computer` tool) is not
guaranteed equivalent to a real OS-level click, and the gap between them is exactly where all three
failure modes live.**

## Proposed direction (not yet built — for discussion)

Move the click-delivery layer out of CDP entirely: a Python script driving the actual OS input
stack (e.g. `pyautogui`, or platform-native input injection) to click real screen coordinates on a
real, focused browser window, rather than dispatching input through the DevTools Protocol. Keep
everything else as-is — the extension's panel/contract (`data-save-state`, `data-video-id`,
upsert-by-Video-ID), the Airtable I/O, the verification-by-query discipline, and the
playlist-as-queue model. This is a swap of *how a click is delivered*, not a redesign of the
pipeline's architecture.

Longer-term: run this on a VM, but — per the stated requirement — the clicking must still act on
**the machine's actual screen**, not a headless/virtual display, since the whole premise is that
real OS-level input is what YouTube/Chrome are treating differently from CDP input. A VM with a
real virtual display and real (not synthetic) input events should preserve this property; a
headless or Xvfb-style setup likely would not, and should be treated as suspect until proven
otherwise against the same kind of test this doc used for `ovabeVoWrA0` (real click on a
console-verified correct element, checked for both the content script's own log line and the
downstream network request).

**Open questions for the redesign, not yet answered:**
- Does a real OS-level click (outside CDP entirely) succeed on `ovabeVoWrA0` where six CDP-issued
  real clicks did not? This is the load-bearing assumption behind the whole redesign and should be
  the first thing tested, on this exact video, before building anything further.
- What triggers the gate, if there is one — Chrome's own automation-controlled flag (visible to
  the page via `navigator.webdriver` or similar even when input is injected via CDP's `Input.*`
  domain), something YouTube checks, or something else? Worth a quick check of
  `navigator.webdriver` in the failing tab before assuming.
- Does the fresh-tab workaround (which fixed 5/6 this session) still matter once click delivery is
  handled by real OS input, or was it only ever compensating for CDP-specific flakiness?

## Not filed to GitHub

Local markdown writeup only, matching the existing `docs/GITHUB_ISSUE_*` convention (see GH-69 for
the closest-related prior art). File as GH-70 if/when triaged.
