# Project Manifest — Click-Delivery Layer Redesign (Change Request)

**Project:** Redesign how the transcript harvest loop triggers extraction — replace CDP-driven
clicks with something that doesn't depend on emulating a real user click through the DevTools
Protocol.
**Repo:** `airtable-shots-db` · **Working dir:** `chrome-extension/` (Fork A) or a new
`scripts/`/service (Fork B)
**Triggered by:** `docs/GITHUB_ISSUE_70_CLICK_DELIVERY_UNRELIABLE_CDP_AUTOMATION.md`
**Informed by:** `docs/RESEARCH_PROMPT_GUI_AUTOMATION_FEASIBILITY.md` +
`docs/RESEARCH_FINDINGS_GUI_AUTOMATION_FEASIBILITY.md`
**Status:** Fork A chosen (D2 decided) — Phase 0 diagnostic **RUN 2026-07-27, positive leg complete**:
a zero-CDP OS-level click (Quartz/CoreGraphics via ctypes) succeeded end-to-end on `ovabeVoWrA0`,
the video that failed 6/6 CDP delivery attempts. One control is still outstanding before the gate
is fully settled — see §3.1.
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

**Result (2026-07-27, first attempt): INCONCLUSIVE — blocked by the delivery tool itself, not by
YouTube.** The diagnostic never got far enough to test the hypothesis. AppleScript's
`System Events` → `click at {x, y}` **does not deliver click events to Chrome at all** in this
setup, so there was nothing to observe at the button.

What was established, in order:

1. **Accessibility permission is correctly granted** to `osascript` when run from native Terminal.app
   (first run errored `-25211 not allowed assistive access`, subsequent runs returned cleanly). Note
   Claude Code's *embedded* terminal is a different process and does not inherit this grant.
2. **`click at` genuinely works at the OS level.** Self-verifying control test: opened a TextEdit
   document, clicked its center via `click at`, typed a marker string, and read the document's text
   back via AppleScript — marker present. So the mechanism, permission, and coordinate space are all
   functional against a native app.
3. **Coordinates were verified correct, repeatedly.** Digital Color Meter does *not* show x/y (the
   script header is wrong about this — use the `Cmd+Shift+4` crosshair readout or a JXA
   `NSEvent.mouseLocation` poll instead). Final coordinates were computed from the page itself
   (`getBoundingClientRect()` + `window.screenX/screenY` + browser-chrome offset) and cross-checked
   against `bounds of front window`.
4. **Two window-hygiene traps cost most of the session** and must be avoided on any retry: an
   **undocked DevTools window** becomes Chrome's `front window` for AppleScript (returned a 640×640
   window instead of the browser), and window bounds *change* when DevTools docks/undocks, silently
   invalidating previously-computed coordinates.
5. **Chrome's `execute javascript` (View > Developer > Allow JavaScript from Apple Events) works**
   and is the right read-back channel — but **JS globals (`window.__x`) do not persist between
   separate `execute javascript` calls** (each appears to run in a fresh context; a global set in
   one call read back `undefined` in the next). Use `localStorage` for any cross-call state.
6. **Ground truth, via a `localStorage`-backed capture-phase `click` listener on `document`:**
   - A **real physical click** → logged, `{"x":550,"y":460,"target":"SPAN","trusted":true}`. The
     listener demonstrably works.
   - A **`click at` synthetic click on the Extract & Save button** (`1018,1073`) → **empty log**,
     panel stayed `idle`.
   - A **`click at` synthetic click on plain page content** (`821,575`, center of page, nowhere near
     any extension UI) → **empty log**, panel stayed `idle`.

**So: zero click events reach the page's document from `click at`, anywhere on the page, while the
same mechanism drives TextEdit fine and a real click on the same page logs normally.** This is a
property of AppleScript `click at` vs. Chrome's render surface — *not* evidence for or against the
GH-70 hypothesis, which remains untested.

**Next step is to re-run the diagnostic with a different OS-input mechanism before drawing any
conclusion about CDP.** The research findings already ranked **Quartz/CoreGraphics event injection
via `pyobjc`** (`CGEventCreateMouseEvent` + `CGEventPost`) *above* AppleScript AX targeting — this
result is a concrete argument for going there directly. Reuse the verification rig built here as-is:
the `localStorage` click listener is the ground truth (an empty log means the click never arrived;
`trusted:true`/`false` distinguishes real from synthetic), and `execute javascript` via AppleScript
is a working CDP-free read-back channel. Only if a Quartz-injected click *does* register on plain
page content, but *doesn't* trigger `get_transcript` at the button, does the decision gate in §4
actually come into play.

### 3.1 Second attempt (2026-07-27, same day): Quartz injection — POSITIVE

**The retry above was run and it worked.** Tool: `scripts/phase0_quartz_click.py` — Quartz/
CoreGraphics (`CGEventCreateMouseEvent` + `CGEventPost` on `kCGHIDEventTap`) bound through
**ctypes**, not `pyobjc`. pyobjc has no wheel for the Python 3.14 here and `--target` installs fight
PEP 668; ctypes needs no install at all, and pyobjc is only a wrapper over these same C functions.

**Result on `ovabeVoWrA0` — the 6/6-CDP-failure video — with zero CDP attached:**

| Step | Outcome |
|---|---|
| Quartz click on plain page content | logged, `isTrusted:true` — **the tool works** (AppleScript logged nothing here) |
| Quartz click on description expander | landed exactly on `TP-YT-PAPER-BUTTON#expand`, description expanded |
| Quartz click on YouTube's native **Show transcript** | **`get_transcript` fired** (308ms) → **2342 segments** |
| Quartz click on the extension's **Extract & Save** | `idle → saving → saved` in 16s |
| Airtable verification | `rec5uUvvw2CTFBeyI`, **one** record, correct title/channel/language, transcript truncated at exactly 100k by the GH-64 shim |

So a real OS-level click succeeds end-to-end on the video that resisted six CDP-driven attempts.

**Two prior theories die here:**
- **ASR-only captions are NOT a sufficient cause of failure.** `ovabeVoWrA0` has a single `"kind":"asr"`
  English track and no manual track — the exact profile CLAUDE.md's 2026-07-27 addendum blamed for a
  clean 3-for-3 failure split — and it extracted 2342 segments without complaint. Whatever that
  correlation was, caption-track type alone does not explain it.
- **The AppleScript "no events reach Chrome" conclusion needs a caveat** — see the focus trap below.
  `click at` may have been defeated by the same thing, not by anything intrinsic to AppleScript.

#### The confound that nearly produced a false positive — macOS click-to-focus

Mid-run, clicks silently stopped arriving: a click on **Show transcript** produced no listener entry,
no `get_transcript`, and no panel change — a *textbook* "site ignored the click" signature. It was
wrong. `document.hasFocus()` was `false` while `AXFrontmost=true`, `AXMain=true`, no sheets, and
`osascript activate` had been called. **The first mouse-down after the window loses focus is consumed
activating it and never reaches page content.** Three repeat clicks then logged normally.

Discriminator that isolated it: **mouse *motion* still reached the page while clicks did not** —
`calibrate` (which posts `kCGEventMouseMoved` only) kept working throughout. Motion routes by cursor
location; button events need a key window.

This is now guarded in the tool — `click` calls `ensure_focus()` first, verifies `document.hasFocus()`,
and if absent spends a throwaway click on a point where `elementFromPoint` hits nothing interactive,
then re-verifies. **Any future null result from this diagnostic is meaningless unless focus was
verified at click time.** It is entirely plausible this trap contaminated earlier manual/AppleScript
attempts, including §3's.

#### Coordinate mapping is affine, not a translation

`window.screenY + (outerHeight - innerHeight)` is wrong and went **negative** (−24) on a real window.
Cause: `outerHeight` is in physical points, `innerHeight` in CSS px — a unit mismatch, not a bug.
The tab was at **90% zoom**, making screen→client a scale of **1.111**, so a single-point offset was
77px off at the calibration point and drifted further across the viewport — easily enough to hit a
neighbouring control and misread it as a failed click.

`calibrate` therefore measures **two** widely-separated points by mouse motion and solves for scale
*and* origin; `coords` refuses to run without it rather than guessing.

#### Apple Events JS runs in an ISOLATED world

`document`, `localStorage` and `performance` all work, but **page globals do not exist**:
`ytInitialPlayerResponse`, `ytcfg` and `ytd` were all `undefined` while `document.querySelector`
happily found `ytd-watch-flexy`. Caption-track type must be scraped out of the inline `<script>`
text instead. This is a stronger statement than §3's "globals don't persist between calls" — the
page's own globals are never visible at all.

Corollary win: **Resource Timing (`performance.getEntriesByType('resource')`) is a CDP-free
substitute for `read_network_requests`** — it detects whether `get_transcript` was requested without
attaching the debugger that is the variable under test. It carries no status code, so a hit proves
the request happened, not that it succeeded.

#### What is still outstanding

The positive leg is done; the **negative control is not**. We did not re-run a CDP-driven click on
`ovabeVoWrA0` in this same session to watch it fail. Without that, "OS click works" and "CDP click
fails" are separated by hours and by the focus confound above, so the causal attribution to CDP is
supported but not proven. Run that control before treating Fork A's premise as established.

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
