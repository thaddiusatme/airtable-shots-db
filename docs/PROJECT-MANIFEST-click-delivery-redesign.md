# Project Manifest — Click-Delivery Layer Redesign (Change Request)

**Project:** Redesign how the transcript harvest loop triggers extraction — replace CDP-driven
clicks with something that doesn't depend on emulating a real user click through the DevTools
Protocol.
**Repo:** `airtable-shots-db` · **Working dir:** `chrome-extension/` (Fork A) or a new
`scripts/`/service (Fork B)
**Triggered by:** `docs/GITHUB_ISSUE_70_CLICK_DELIVERY_UNRELIABLE_CDP_AUTOMATION.md`
**Informed by:** `docs/RESEARCH_PROMPT_GUI_AUTOMATION_FEASIBILITY.md` +
`docs/RESEARCH_FINDINGS_GUI_AUTOMATION_FEASIBILITY.md`
**Status:** Fork A chosen (D2 decided) — Phase 0 diagnostic script ready, awaiting a run
**Last updated:** 2026-07-27

---

## 1. Why

GH-70 documented three independent click-delivery failure modes in one harvest session, all
converging on the same root uncertainty: **CDP-mediated input (however issued — scripted `.click()`
or Claude in Chrome's `computer` tool) is not reliably equivalent to a genuine OS-level click**, and
the gap shows up unpredictably — sometimes a request fires and 400s with no retry (GH-68), sometimes
the click "runs" but nothing downstream fires (GH-69), and in one confirmed case (`ovabeVoWrA0`) a
real `computer` click on a console-verified-correct element never reached the button's own listener
at all, across six different delivery attempts.

The external research pass (`RESEARCH_FINDINGS_GUI_AUTOMATION_FEASIBILITY.md`) confirms the
underlying mechanisms are real and documented (CDP-attachment detection via `navigator.webdriver`,
a `Runtime.enable` console-preview leak, `isTrusted` differences by dispatch method) but **does not
confirm** they're what's actually happening to us. It also surfaces a second, simpler option we
hadn't scoped: skip the click entirely by calling YouTube's caption/`timedtext` endpoint directly
over HTTP.

This manifest exists to make that a real decision instead of defaulting into a rebuild, and to
scope whichever path we take.

---

## 2. The fork

Two candidate directions, not mutually exclusive long-term (Fork B could become the primary path
with Fork A / the existing extension as a fallback), but they need to be evaluated and built
separately:

### Fork A — OS-level GUI automation

Keep the existing extension and its Extract & Save button entirely as-is. Replace *how the click is
delivered* with a Python (or AppleScript) script driving real OS-level input — no CDP, no Claude in
Chrome, no browser automation library — against a real, logged-in, unlocked GUI session, locally
first and on a VM later.

**Keeps:** the extension's panel contract (`data-save-state`, `data-video-id`, upsert-by-Video-ID),
all Airtable I/O, the playlist-as-queue model, the verification-by-query discipline.
**Changes:** only the input-delivery mechanism and the "agent" that drives navigation (a Python
script instead of Claude in Chrome).

### Fork B — Direct `timedtext` HTTP fetch

Bypass the browser, the extension, and the click entirely. Call YouTube's caption/`timedtext`
endpoint directly over HTTP (the same approach `youtube-transcript-api` and similar libraries use),
parse the response, and write to Airtable directly from a script — no page load, no button, no
click-delivery question at all.

**Keeps:** the Airtable schema, upsert-by-Video-ID logic, the playlist-as-queue model conceptually.
**Changes:** removes the browser/extension from the harvest path entirely for the common case; the
extension becomes a fallback for videos where the direct fetch fails (if that ever happens) or is
retired outright if it doesn't.

---

## 3. Phase 0 — the diagnostic (shared prerequisite, cheap, decisive)

Before committing real effort to either fork, run the diagnostic already identified in GH-70 and
the research findings:

**Test:** Launch Chrome manually with zero CDP/remote-debugging attached (no Claude in Chrome, no
automation flags at all). Use a one-off AppleScript or Quartz script to click the Extract & Save
button on 5-10 videos, **including `ovabeVoWrA0` specifically** (the video that failed 6/6 CDP
delivery attempts).

**What this answers:**
- If `ovabeVoWrA0` and the others succeed cleanly under zero-CDP OS-level clicking → the core
  hypothesis holds, Fork A is justified, proceed to §5.
- If they still fail the same way → CDP-attachment is *not* the cause (rate limiting, a race
  condition in our own extension, or backend flakiness unrelated to automation detection is more
  likely), and Fork A would not fix the actual problem. Re-scope toward Fork B or further
  diagnosis before building anything.

**This is a ~1-hour spike, not a build.** Do not proceed to Phase 1 of either fork until this runs
and the result is recorded here.

**Script ready**: `scripts/phase0_diagnostic_click.applescript` — an AppleScript that posts a real
OS-level click (via macOS System Events, zero dependencies) at given screen coordinates. Read the
header comment for full setup/usage. **This has to be run by a human, not Claude** — it requires
disconnecting Claude in Chrome entirely (the CDP session itself is the variable under test) and
acting on the real display, which is outside what Claude's sandboxed environment or its
browser/desktop tools can do. See the script's own comments for exact steps.

Run it against **both** `ovabeVoWrA0` (known-failing, 6/6 CDP attempts failed) and a known-good
control video (e.g. `J_jswzXhYJA`, which saved cleanly earlier), so there's a baseline to compare
against.

**Result:** *(not yet run — fill in before proceeding)*

---

## 4. Decision gate

| Phase 0 result | Recommended path |
|---|---|
| Zero-CDP OS clicks succeed where CDP clicks failed | Proceed with **Fork A**, Phase 1 below. Fork B still worth evaluating in parallel as a lower-maintenance long-term option, but not urgent. |
| Zero-CDP OS clicks fail the same way | Fork A is not worth building. Re-diagnose the actual cause first (rate limiting? our own extension's state machine? something YouTube-side unrelated to automation?). Fork B becomes the more attractive default *if* the failures are backend-side rather than click-delivery-side, since it removes the browser from the path entirely. |
| Mixed / inconclusive | Widen the diagnostic (more videos, longer observation) before deciding either way. |

---

## 5. Fork A — Goals, architecture, phased plan (if Phase 0 confirms the hypothesis)

### Goals
- Real OS-level input (no CDP) triggers the existing extension's Extract & Save button reliably.
- Runs locally first, against a real logged-in macOS session.
- Eventually runs unattended on a VM with a real display + real input — not headless, not Xvfb.

### Non-goals (for this fork)
- No changes to `content.js`'s extraction/save logic, the Airtable schema, or the agent contract
  (`data-save-state` etc.) — those are proven and untouched.
- No CDP involvement anywhere in the click path once this ships.

### Architecture

**As-is:** Claude in Chrome (CDP) → finds button via accessibility tree or coordinates → dispatches
click via CDP `Input.dispatchMouseEvent` or `javascript_tool` → extension's `onExtractSaveClick`
fires (or doesn't) → panel state machine → service worker → Airtable.

**To-be:** A Python script (or AppleScript) → drives navigation (new tab, load URL) and clicking via
real OS input (Quartz/CoreGraphics event injection via `pyobjc`, ranked above AppleScript AX-tree
targeting per the research — see `RESEARCH_FINDINGS...md` §"Implementation recommendation") → same
extension, same panel, same Airtable path, unchanged.

### Phased plan

| Phase | Goal | Tasks | Effort |
|---|---|---|---|
| **0 — Diagnostic** | Confirm the hypothesis before building anything | See §3 above | ~1 hour |
| **1 — Minimal script spike** | Prove a Python/AppleScript script can navigate + click reliably on ≥1 known-good and the known-bad (`ovabeVoWrA0`) video | Write the smallest possible script: open URL, wait for panel `idle`, click via Quartz/AX, poll `data-save-state` to terminal, verify Airtable | 0.5–1 day |
| **2 — Queue + retry logic** | Port the agent's loop responsibilities into the script | Playlist enumeration, per-video navigation, verify-by-Airtable-query discipline, consecutive-failure halt policy — same rules `harvest-playlist`/`scheduled-playlist-harvest` already encode, just executed by Python instead of an agent | 1 day |
| **3 — Permissions + reliability hardening** | Make it runnable outside an interactive session babysat by a human | macOS Accessibility permission granted to the exact invoking executable; handle window focus/frontmost requirements; jitter/timing to avoid behavioral (non-CDP) detection per the research's caveat | 0.5–1 day |
| **4 — VM port** | Run unattended | Real GUI session (auto-login, screen lock disabled, real display via Virtualization framework or a cloud Mac instance) — see research findings §"VM feasibility" for provider tradeoffs | TBD, likely the largest single chunk of effort/cost |

### Risks
- AX-tree "press" actions might re-synthesize a page-layer (non-OS-trusted) event depending on how
  Chromium handles `AXPress` — flagged as unverified in the research. Test this specifically in
  Phase 1 before committing to the AX approach over raw Quartz coordinates.
- Coordinate-based clicking is fragile to window movement/resize/OS scaling — prefer AX-tree
  targeting if it proves reliable; fall back to Quartz coordinates only if it doesn't.
- VM unattended operation requires actively fighting the OS's idle/lock behavior — real ongoing
  maintenance surface, not a one-time setup cost.
- ToS exposure (YouTube's scraping prohibition) is unchanged by this fork — solving click
  reliability doesn't reduce that risk.

---

## 6. Fork B — Goals, architecture, phased plan (evaluate regardless of Phase 0 result)

### Goals
- Fetch transcript text for a video without a browser, an extension, or a click, by calling the
  `timedtext` endpoint (or equivalent) directly over HTTP from a script.
- Write directly to Airtable, preserving upsert-by-Video-ID and the existing schema.

### Non-goals
- Not required to preserve the extension's exact DOM-parsing behavior (GH-64 truncation logic
  would need to be re-implemented or reused as a library import if kept).

### Architecture

**To-be:** Python script → enumerate playlist (via `youtube-transcript-api`-style caption listing or
the YouTube Data API if going fully official) → fetch captions directly via HTTP → transform to the
existing `{text, start}` timestamped-segment shape → write to Airtable via the same
upsert-by-Video-ID pattern the extension uses today (reimplemented in Python, or by calling the
existing `background.js` logic isn't possible outside the extension — this would be a fresh,
parallel implementation).

### Phased plan

| Phase | Goal | Tasks | Effort |
|---|---|---|---|
| **1 — Spike** | Confirm direct fetch works for a handful of videos, including ones the extension has struggled with | Use `youtube-transcript-api` (or hand-rolled `timedtext` HTTP calls) against `ovabeVoWrA0` and 4-5 others; compare output to what the extension would have produced | 0.5 day |
| **2 — Airtable write path** | Reimplement upsert-by-Video-ID outside the extension | Python Airtable client, same field IDs/schema as `background.js` uses today, same Triage Status default (`Queued`) on create | 0.5–1 day |
| **3 — Queue/playlist logic** | Port the playlist-as-queue + drain-on-verify model | Reuse the same rules as `harvest-playlist`/`scheduled-playlist-harvest` skills, executed by the script | 0.5–1 day |
| **4 — Fallback decision** | Decide whether to keep the extension at all | If Fork B's success rate is high enough, the extension/click path could be retired to "manual/rare-fallback only" status, or kept purely for videos where direct fetch 403s/fails | TBD, depends on Phase 1 results |

### Risks
- Undocumented-endpoint exposure carries its own version of the ToS/reliability risk the research
  flagged — YouTube could change or gate `timedtext` access independent of anything CDP-related.
- Loses the "verified against the actual rendered page" property the extension has today (DOM
  parsing sees exactly what a human would see); a direct API call trusts YouTube's caption data
  as-is.
- GH-64's truncation handling (`lib/transcript-utils.js`) would need to be ported or reused as a
  library, not assumed to carry over automatically.

---

## 7. Open decisions

- **D1 — Run Phase 0 diagnostic before anything else.** Not optional; both forks' priority depends
  on this result.
- **D2 — Fork A vs Fork B vs both. DECIDED 2026-07-27: Fork A.** Focus here first. Fork B stays
  documented above as a future option, not being pursued right now.
- **D3 — If Fork A proceeds, AX-tree targeting vs raw Quartz coordinates** — decide in Fork A Phase
  1 based on which the diagnostic/spike shows to be reliable against Chrome's actual accessibility
  tree exposure.
- **D4 — VM platform** (macOS via Virtualization framework/AWS EC2 Mac vs Linux with a real X
  session) — deferred to Fork A Phase 4; not needed for local-first validation.

---

## 8. Getting started (first session)

1. Run the **Phase 0 diagnostic** (§3) — this is the only thing that should happen before anything
   else in this manifest. Record the result in §3.
2. Based on the decision gate (§4), pick Fork A, Fork B, or both-in-parallel.
3. If Fork A: start with Phase 1 (minimal script spike) — smallest possible script, one known-good
   video + `ovabeVoWrA0`, prove the click lands and the extension's own state machine advances.
4. If Fork B: start with Phase 1 (spike) — confirm direct fetch works and compare output quality
   against what the extension produces today, especially for videos the extension has struggled
   with.
5. Update this manifest's Status line as phases complete, same convention as
   `PROJECT-MANIFEST-in-page-panel.md`.
