# CLAUDE.md — Project Manifest

## Current state (as of 2026-07-17)

- **Active branch**: `feature/transcript-only-extension` — **2 commits ahead of remote, NOT pushed**, not merged to master. Working tree clean (only untracked `.claude/settings.local.json`). Continue on this branch.
- **Active initiative**: convert the toolbar popup into an **in-page, agent-drivable panel** (see next section). Design is in `docs/PROJECT-MANIFEST-in-page-panel.md` — Status: **Phase 0 spike committed and verified GO** (2026-07-17).
- **Phase drift**: `background.js` is a complete 210-line implementation, so Phase 1 is essentially done and Phase 2 largely so. Real position: **"Phase 3, one bug from a working loop."**
- **Committed** (commits `8ecf1a4` + `77777b1`): the Phase 0 spike — `content.js` (panel + lifecycle), `manifest.json` (service worker), new `background.js`, `popup.*` trims, plus `docs/` and the `verify-panel` / `harvest-playlist` skills. The old "commit the dirty spike first" note is done.
- **Previous branch** (abandoned): `fix/gh-61-62-storyboard-validate-and-readme-quickstart` — do not continue this work; storyboard is deprioritized
- **2026-07-27, filed GH-70** (`docs/GITHUB_ISSUE_70_CLICK_DELIVERY_UNRELIABLE_CDP_AUTOMATION.md`):
  three independent click-delivery failure modes surfaced in one session (stale-token 400 with no
  retry, GH-69's scripted-click no-op, and a new one — a real `computer` `left_click` on a
  console-verified-correct element that never reaches the button's own listener, tried 6 different
  ways on `ovabeVoWrA0`). Recommends redesigning the click-delivery layer to real OS-level input
  (Python GUI automation) instead of continuing to patch CDP-driven clicks inside `content.js`.
  Not yet built — see the doc's "Open questions" before starting.
  **Research pass done 2026-07-27** (`docs/RESEARCH_FINDINGS_GUI_AUTOMATION_FEASIBILITY.md`,
  prompted via `docs/RESEARCH_PROMPT_GUI_AUTOMATION_FEASIBILITY.md`): hypothesis is plausible
  (CDP-attachment detection / `isTrusted` differences are real, documented mechanisms) but
  unconfirmed for this specific case. **Recommended next step is a cheap diagnostic — not a
  rebuild**: manually launch Chrome with zero CDP/automation attached, click the button on
  `ovabeVoWrA0` + a few others via a one-off AppleScript/Quartz script, see if it actually behaves
  differently. Research also flags a simpler alternative worth evaluating first: calling the
  `timedtext` endpoint directly via HTTP (as `youtube-transcript-api` does) removes the click-
  delivery question entirely, at the cost of its own undocumented-endpoint ToS exposure. Neither
  the diagnostic nor the alternative has been tried yet.
- **Next step**: item #1 of the stale-transcript-panel fix (idle-gating on `watch-flexy` video-id) is
  implemented and verified live (2026-07-22) — see the "Status update" in the Fix direction section
  below. Item #2 (anti-corruption provenance guard) is still open and should land before calling the
  agent loop fully hardened; then finish Phase 3/4.
- **2026-07-23**: investigated GH-69 (`docs/GITHUB_ISSUE_69_...md`) — `content.js`'s
  `openTranscriptPanel()` was reworked (correct button targeting by label, click verification,
  single-candidate patient wait) and is a real improvement, but live testing found the actual
  automated-testing failure mode is that **scripted clicks never trigger YouTube's transcript
  request at all** — a real `computer` click does, reliably. See the GH-69 subsection below; both
  `verify-panel` and `harvest-playlist` skills now mandate real clicks. `content.js` changes not
  yet committed — working tree has this plus the untracked issue doc.
- **2026-07-27 (playlist-harvest retro)**: confirmed `get_transcript` can 400 on the very first
  request even on a genuinely fresh page load (not just after SPA nav as GH-68 assumed) — a real
  gap in the current understanding. Tried a fix: `findBestTranscriptButton()` preferring the "In
  this video" panel's **Transcript tab** over the description-embedded "Show transcript" button, on
  the theory that YouTube's own client silently retries once after a 400 when driven through that
  tab. That theory was confirmed exactly once via a REAL manual click (not the extension's own
  code). **Reverted the same day**: re-tested the fix live, through the extension's own scripted
  click, against 2 fresh never-attempted videos — both produced **zero** `get_transcript` network
  requests, not even a 400. That's the GH-69 signature (scripted `.click()` silently not triggering
  YouTube's handler) — the Transcript tab apparently needs a real trusted click to do anything,
  unlike the description button, which at least fires a failing request under a scripted click. So
  the "fix" was a regression for the automated path, not an improvement. No Airtable writes happened
  in either the broken or reverted state (verified clean both times — the error path still writes
  nothing). **The retry-on-400 problem for automated (non-human-click) runs remains open and
  unsolved.** See the dead-end comment left in `content.js` above `findBestTranscriptButton()` —
  don't re-attempt targeting that tab without first solving the real-click requirement.

- **2026-07-27 (same retro, follow-up) — fresh tab per video looks like a real operational fix,
  separate from any code change.** Thaddius's hypothesis: since the harvest was reusing/re-navigating
  one tab across many videos, maybe a brand-new tab per video avoids whatever accumulates against a
  reused tab. Tested directly against `content.js` reverted to its original (pre-2026-07-27) state —
  no code change involved, purely a change in *how the tab is driven*. **4 for 4 succeeded**,
  including the two videos (`ib74sLgjIBM`, `vmVvpKSSxWE`) that had been stuck failing repeatedly for
  over an hour in a reused tab beforehand — both saved cleanly on the very next attempt in a fresh
  tab. All 4 verified as real records in Airtable with matching titles, not just `data-save-state:
  saved`. Contrast with the same-tab-reused testing earlier in the day: 3 consecutive failures out of
  3 attempts. Sample size is still small (4 successes, no fresh-tab failures yet) and this could
  still be confounded with elapsed time / natural cooldown rather than the tab itself — but it's the
  most promising lead so far and costs nothing to adopt. **Recommend updating `harvest-playlist` and
  `scheduled-playlist-harvest` to open a new tab per video (not just a fresh `navigate()` in the same
  tab) and confirm over a larger batch before fully trusting it.**
  One anomaly noticed during this test, unrelated to the fix: the Airtable record for `vmVvpKSSxWE`
  had `Triage Status = Declined` already set (pre-existing record, created earlier at 00:05:52 in
  that session — before this fix's testing even began, and before another confirmed-empty query for
  that same Video ID later showed zero records). Upsert-by-`Video ID` updated its transcript fields
  but the extension does not touch `Triage Status` on an update, only on create — so a video already
  marked Declined by an earlier/unrelated process (or from a query race) will silently regain a
  transcript without changing its triage state. Worth a human glance rather than assuming Queued.

- **Addendum, separate session, same day — a counterexample to the fresh-tab theory above, plus a
  possibly-cleaner correlation.** Working independently on the "AI (Claude)" playlist
  (`PLVwTAkoVGJsY`), hit the identical 400 on `5WB5bcGNib8` and `ib74sLgjIBM` — 3 consecutive
  failures, real clicks throughout (both the extension's Extract & Save button and, isolating
  further, a real click directly on YouTube's own native "Show transcript" control, bypassing
  `content.js` entirely — still 400). Checked `ytInitialPlayerResponse.captions
  .playerCaptionsTracklistRenderer.captionTracks` on each video: both failing videos have **only** an
  `"asr"` (auto-generated) English track, no manual one. A control video with a manual caption track
  (`dQw4w9WgXcQ`) succeeded instantly, same session, same click method. That's a clean 3-for-3 split
  along caption-track type, independent of click authenticity or 400-vs-zero-request distinction.
  **Directly conflicts with the fresh-tab theory above**: `vmVvpKSSxWE` was tested here in a tab
  created fresh moments earlier (first-ever navigation in it, after a browser-extension
  reconnect) — a real click on YouTube's native transcript control in that brand-new tab still
  400'd. So "fresh tab" did not fix that video in this run, though the other entry reports it did in
  theirs. Didn't check `vmVvpKSSxWE`'s own caption tracks before moving on, which would help settle
  whether ASR-only-caption and fresh-tab are actually two names for the same underlying (e.g.
  time-since-upload / caption-generation-still-settling) cause rather than competing theories — worth
  checking before trusting either fix in isolation. No Airtable writes attempted or made in this
  session; all activity was diagnostic (network requests + `ytInitialPlayerResponse` reads only).

### Phase 0 verification result (2026-07-17, live run against a 76-video playlist)

**Verdict: GO.** Both hard constraints validated on real YouTube + real Airtable writes.

- **CORS path works.** content script → `sendMessage` → service worker → `fetch()` wrote real records
  (`rec06KMarqFXMaRPq`, `recCMZX3SsiUeRFcD`, `recoYXkJNQIykIckl`) with Channel links + language. **Zero CORS errors.**
- **Agent discoverability works.** `find` returns exactly 1 hit for the button; fixed-position, in-viewport, no scroll.
  Open shadow root / prefixed classes were not a problem.
- **SPA remount works.** Panel resets to `idle` with the new `data-video-id` on `yt-navigate-finish`, no reload.
  Note: it is a **reset-in-place**, not destroy/recreate — no nodes are removed/added, only attributes flip.
  Fine for the contract, but don't expect `panel-added` mutations if you write tests against it.
- **State machine never hangs.** Errors terminate at `error` with a message on `data-error-msg` (6.6s worst case).
- **Upsert is genuinely idempotent** — 3 saves of the same video → 1 record. Error path writes *nothing* (no junk rows).

### BLOCKER: stale transcript panel survives SPA navigation

**Symptom**: extract on video N succeeds → SPA-navigate to N+1 → extract on N+1 fails with
"Could not find transcript segments", 0 segments under both known selectors, transcript engagement panel
stuck on a live spinner + pending `ytd-continuation-item-renderer` indefinitely (observed 26s+).

**This is exactly the agent loop** (extract → next → extract), so a naive agent marks every second video failed.

**Isolated by controlled comparison** (same video, `elBPgLSVGk0`, which has 610 segments):
| Scenario | Result |
|---|---|
| Fresh full page load → extract | `saved`, 610 segments |
| SPA nav to it, **no** prior extract on #1 | `saved`, 610 segments |
| SPA nav to it, **after** extracting #1 | **`error`**, 0 segments, stuck spinner |

So the trigger is **the prior extraction**, not SPA nav and not the video.

**The cause is a 400 from YouTube's transcript API — see "ROOT CAUSE FOUND" below.** The table above is real
but its conclusion ("the trigger is the prior extraction") is **misleading**: the true variable is *elapsed time
since navigation*, which the prior extraction only correlates with. Read the root cause before theorising.

**DO NOT "fix" this by closing the transcript panel.** Tried 2026-07-17, three attempts, all failed —
and the last one **silently corrupted data**. Details below; read before attempting a fix.

### Failed fix attempts (2026-07-17) — read before touching this

**Attempt 1** — close the panel on `yt-navigate-finish`, then re-open. Failed: still 0 segments.
**Attempt 2** — close the panel on the success path of `extractTranscript()` (leave each video with it shut).
Appeared to fail — but see below, it was never actually tested.
**Attempt 3** — fixed `closeTranscriptPanel()` itself, then **corrupted an Airtable record**. Reverted.

**Why attempts 1–2 "failed"**: `closeTranscriptPanel()` was broken. It matched
`button[aria-label="Close transcript"]` document-wide, which resolves to a **0x0 button inside a HIDDEN
legacy panel** — clicking it is a silent no-op. The console logged "Closing open transcript panel" while
closing nothing. **The theory was never tested; the code just didn't work.**

**Live DOM facts** (probed, not inferred — these break the obvious approaches):
- The actually-open transcript panel reports **`target-id="null"`** (same trap as `SEGMENT_SELECTORS`).
  Filtering panels by `/transcript/i` on `target-id` **misses the real one**.
- Its close button is labelled **`"Close"`**, not `"Close transcript"`. The `"Close transcript"` button
  belongs to a *hidden* `engagement-panel-searchable-transcript` that lingers.
- Detect open transcript panels by **content + visibility** (`offsetWidth||offsetHeight` AND contains
  segment elements), never by `target-id` or by the presence of a close button.

**Why attempt 3 was WORSE than the bug** (the important part):
Closing the panel **does not remove segment nodes from the DOM**. `extractTranscript()` begins with a
document-wide `collectSegments(document)`, so on video N+1 it instantly harvested video N's leftover rows
(2ms, no fetch) and saved **video N's transcript under video N+1's ID** — reporting `saved`. Record
`recoYXkJNQIykIckl` (Targaryens doc) was overwritten with video #1's Dan Harmon transcript.
The original bug is *safer*: YouTube clears the segments and leaves a spinner, so extraction fails **loudly**.

**Constraint for any future fix**: it is not enough to make extraction *succeed* — it must be impossible to
extract **stale** segments. Prove the segments belong to the current video before saving (e.g. remove/ignore
stale nodes on navigation, or gate on "panel was opened *after* the current `yt-navigate-finish`"), and
verify the saved transcript's **content**, not just that the state reached `saved`. A passing `saved` with a
suspiciously fast `extracting→saving` (< ~100ms, no fetch) is the corruption signature.

### ROOT CAUSE FOUND (2026-07-17, via `read_network_requests`)

```
POST https://www.youtube.com/youtubei/v1/get_transcript?prettyPrint=false  ->  400
```

**The panel is not "stuck loading" — YouTube's transcript API rejects the request with a 400.** The spinner
spins forever because the fetch failed; nothing in the DOM surfaces this. Every DOM-level theory (stale panel,
close buttons, user activation, window focus) was downstream noise. `hasFocus` was true; a real dispatched
`computer left_click` fails identically to a scripted `.click()`, so it is **not** a user-activation issue.

**Why 400**: the "Show transcript" control in the description (`ytd-video-description-transcript-section-renderer`,
Strategy 2) carries a continuation token bound to the video it rendered for. After SPA nav the extension clicks
that button while it still holds the **previous video's token** -> YouTube rejects it -> permanent spinner.

Consistent with every observation:
- A **human click seconds later succeeds** (description section has re-rendered with the new token).
- An **agent click immediately after `data-save-state=idle` fails** (button still stale).
- A **fresh page load always succeeds** (token never stale).

**The deeper defect — the agent contract lies.** `mountPanel()` fires on `yt-navigate-finish` and reports
`idle` + the new `data-video-id` while YouTube is still mid-swap (page title and description section still show
the previous video; the previous video's segments are briefly still in the DOM). **`idle` does not mean ready.**
This is a **Phase 4 (agent-contract)** problem as much as Phase 3: the panel must not advertise readiness until
the current video's transcript entry point actually belongs to the current video.

**Fix direction** (refined 2026-07-16, still untested — do not assume). Both symptoms are one defect: nothing ties
*what gets saved* to *the video the URL currently names*. `extractTranscript()` reads `videoId` fresh from the URL
(correct) but then harvests `collectSegments(document)` document-wide, trusting whatever rows are in the DOM; and
`mountPanel()` stamps `data-video-id` + flips to `idle` on `yt-navigate-finish` while YouTube is still mid-swap.
So: old segments cleared → stale-token "Show transcript" click → 400 → loud failure; old segments *not yet* cleared
→ harvest video N under N+1's URL → silent corruption. **A fix that only chases the 400 leaves the corruption path
open.** Constraint stands: make stale extraction *impossible*, and verify provenance, not just that state reached
`saved`.

Layered plan, cheapest / highest-value first:

1. **Stop `idle` from lying (contract fix, biggest lever).** Don't advertise `idle` until the page has actually
   finished swapping. Candidate free signal: `ytd-watch-flexy`'s `video-id` attribute, which flips only when the
   swap completes — gate `idle` on `watch-flexy[video-id] === urlVideoId`; hold a non-ready state (e.g. `waiting`)
   until they match. This makes the token fresh by click time and dissolves the 400 without a retry hack. **Verify
   live first** that `watch-flexy[video-id]` genuinely lags the URL during the swap (don't theorize — check the DOM),
   and that gating `idle` doesn't strand the agent's `find` (button still mounts, just not "ready").
2. **Bind segments to the current video before saving (anti-corruption guard).** Refuse to harvest unless segments
   were populated *after* the current nav settled — a generation counter bumped on each `yt-navigate-finish`, plus
   the corruption-signature tripwire (`extracting→saving` in <~100ms with no fetch → treat as stale, error loudly,
   never save). Note: true *content* verification is hard — the transcript is just text+timestamps with no intrinsic
   videoId — so verify *provenance* (opened after this video's swap), not content.
3. **Retry-on-400 / retry-on-empty as cheap insurance,** not the primary mechanism — should rarely fire once #1 holds.

**Status update (2026-07-22): item #1 implemented and verified live.** `mountPanel()` no longer
flips straight to `idle`; it now checks `ytd-watch-flexy`'s own `video-id` attribute against the
URL and holds a new `waiting` state (button still mounts, `data-save-state="waiting"`) until they
match, polling every 50ms up to a 4s fail-open timeout. `onExtractSaveClick()` also refuses to run
while `data-save-state === 'waiting'`, so a fast agent click can't slip through mid-swap.

Live-measured before fixing (Claude in Chrome, real SPA nav via a related-video click): at
`yt-navigate-finish`, URL already named the new video but `watch-flexy[video-id]` still reported
the *previous* one for **~1.4–2s** before catching up — confirming the "idle lies" theory with real
numbers, not a guess. After the fix, the same nav sequence correctly held `waiting` until the swap
landed, then flipped to `idle`, and a subsequent extract+save produced a clean, correctly-attributed
Airtable write (`receRO6SOSsBmx9Ck`, Stratholme video, created 2026-07-23) — no stale-token 400, no
cross-video contamination.

Item #2 (anti-corruption provenance guard / generation counter) is **still not implemented** — this
fix addresses the 400 failure mode, not the silent-corruption path documented above. Don't treat
the loop as fully hardened until #2 lands too. Item #3 (retry) remains unneeded so far.

Not yet committed — see `git log` / working tree for current status; commit message will reference
this section.

### GH-69 (2026-07-23): scripted clicks silently never trigger `get_transcript` — real clicks always do

**This contradicts the 2026-07-17 claim above** ("a real dispatched `computer left_click` fails
identically to a scripted `.click()`, so it is not a user-activation issue") — flagging the
contradiction explicitly rather than quietly overwriting it, since the earlier claim is still in
this file a few paragraphs up. That test appears to have been confounded by the (also real, also
verified) stale-continuation-token 400 described above — with both problems live at once on
2026-07-17, a real click could plausibly have failed too, for the *different* reason of hitting a
stale token, masking any user-activation effect in that particular test.

The 2026-07-23 evidence is more extensive and isolates the variable more cleanly: dozens of
correctly-targeted scripted-click attempts (`javascript_tool` `.click()`), across multiple unrelated
videos, with timeouts pushed as high as 90s+, on a fresh page load (GH-68's token can't be stale
here) — **zero** ever produced a `get_transcript` network request (confirmed via
`read_network_requests`, not inferred from the DOM). The identical button, on the identical video,
in the identical session, clicked with a genuine trusted mouse event (a human, or Claude in
Chrome's `computer` `left_click` tool) worked immediately and reliably every time it was tried,
including on two videos that had just failed every scripted attempt made against them. Full
writeup: `docs/GITHUB_ISSUE_69_TRANSCRIPT_PANEL_OPENER_SELECTOR_MISS.md`.

**Practical fix, and it's procedural, not code**: `.claude/skills/harvest-playlist/SKILL.md` and
`.claude/skills/verify-panel/SKILL.md` now mandate a real `computer` `left_click` to trigger the
Extract & Save button (and playlist navigation) — never `javascript_tool` or any scripted
`.click()`/`dispatchEvent`. `content.js` itself cannot detect or route around this from the inside;
whatever gates the request appears to live in YouTube's own handling, outside the content script's
control. The `content.js` changes made investigating this (correct button targeting by label
instead of blind index `[0]`, verifying segments appear before trusting a click, a single-candidate
patient 35s wait instead of fanning out across multiple different buttons) are real, defensible
improvements and were kept — but they were not the actual fix for what looked like GH-69's symptom
in automated testing.

**Not confirmed**: whether this is a deliberate YouTube anti-bot gate on real user activation, some
effect of very high same-day repeated test traffic against these specific videos, or something
else. What's reproduced reliably is the practical shape of it — scripted click → silent no-op,
real click → success — on the same videos/session, both directions.

**Nuance added 2026-07-26 (panel-state retro) — don't over-read this section as "scripted always
fails / real click is the fix".** In that later incident the agent's `computer` click via the Chrome
MCP *did* trigger a successful `get_transcript` + save — real record `recti9Qu1mpKGx717` landed
correctly. The `error` observed afterward came from a **follow-up run**, not from that first extract:
the panel read `error` even though the write had already succeeded, a second run was fired, and it
created a duplicate that then broke the upsert. So the durable takeaway is **"confirm the write in
Airtable (or the network request) before declaring failure,"** not "scripted clicks always fail." The
click-mechanism finding above still holds for the *no-request* signature; it just isn't a licence to
trust `error` at face value — `data-save-state` gives false negatives, and acting on one is what
caused the duplicate.

## Active change request: click-delivery layer redesign

**Full design: `docs/PROJECT-MANIFEST-click-delivery-redesign.md`.** Triggered by GH-70. Forks into
two candidate directions — (A) OS-level GUI automation replacing CDP-driven clicks against the
existing extension, or (B) bypassing the browser/extension entirely via a direct `timedtext` HTTP
fetch. **Both are gated on a shared Phase 0 diagnostic (not yet run)**: click `ovabeVoWrA0` via a
zero-CDP OS-level click and see if it succeeds where 6 CDP-driven attempts didn't. Do not start
building either fork before that diagnostic runs — see the manifest's decision gate (§4).

## Active initiative: in-page agent-drivable panel

**Full design: `docs/PROJECT-MANIFEST-in-page-panel.md`.** Read it before working on this.

**Why**: a toolbar popup can only be opened by a human clicking browser chrome — it is invisible to page-level browser automation (Claude in Chrome can't click a native popup). Moving the trigger into the page turns "capture every transcript in a playlist" into a hands-off agent loop.

**Operating model**: the extension is dumb and per-video — it exposes one "Extract & Save" button per watch page plus a machine-readable status. **All iteration, navigation, and retry logic lives with the agent; the playlist is the queue.** Do NOT build a batch queue, keyboard shortcut, or import-list logic into the extension — that duplicates the agent's job.

**Two hard constraints** (don't get these wrong):
1. **Airtable I/O must move to a service worker (`background.js`).** Today's `fetch()` works only because it runs in `popup.js` (extension origin). A content-script `fetch()` to `api.airtable.com` is subject to YouTube's CORS policy and will be rejected. Required path: content script → `chrome.runtime.sendMessage` → service worker → `fetch()`. Bonus: the Airtable PAT is then read only inside the worker, never in the YouTube page world.
2. **SPA remount is load-bearing.** The panel must re-mount on `yt-navigate-finish` (+ MutationObserver fallback) so the agent's `find` succeeds on video #2, #3, … without a reload.

**Agent contract (treat as a stable API):**
- Panel root: `<div id="yt-transcript-panel" data-save-state="…" data-video-id="…" data-error-msg="…">`
- Button: real `<button>` with `aria-label="Extract and save transcript"` + `data-testid="extract-save-btn"`, fixed position, always visible.
- `data-save-state` is the source of truth the agent polls: `idle → extracting → saving → saved | error`. Must never hang on `saving`.
- Use an **open** shadow root or scoped/prefixed classes — a *closed* shadow root can hide the panel from the agent's `find`/`read_page`. Validate in Phase 0.
- Save stays upsert-by-`Video ID` (idempotent; re-click/retry updates, never duplicates).
- **Trigger the button with a real `computer` `left_click`, never `javascript_tool`/scripted `.click()`** — see GH-69 (2026-07-23) above. A scripted click silently never fires YouTube's `get_transcript` request; a real trusted click works reliably. `javascript_tool` remains correct for all read-only polling.

**Phases**: 0 spike (de-risk CORS path + agent discoverability) → 1 service worker → 2 panel UI → 3 SPA lifecycle → 4 agent-contract hardening → 5 cleanup/cut over (retire `default_popup`, bump to v3.0.0). Core 0–3 ≈ 3–4 days.

**Untouched by this work**: `lib/transcript-dom.js` (+ test), `lib/transcript-utils.js` (+ test, now called from the worker), `settings.*`, the Airtable schema. GH-64 truncation logic must be preserved.

## Skills

- **`verify-panel`** (`.claude/skills/verify-panel/`) — acceptance test for the in-page panel with Claude in
  Chrome. Run after any change to `content.js` / `background.js` / `manifest.json`, and at the end of each phase.
  Encodes the method that caught the stale-panel bug (observe before clicking, confirm writes in Airtable,
  isolate before blaming the video). Mandates real `computer` clicks (see GH-69 above).
- **`harvest-playlist`** (`.claude/skills/harvest-playlist/`) — runs the actual agent loop: walk a playlist,
  save every transcript, report. This is where queue/retry logic lives — never in the extension. Mandates
  real `computer` clicks (see GH-69 above) — `javascript_tool` is read-only in this loop.
- **`youtube-panel-triage`** (`.claude/skills/youtube-panel-triage/`) — added 2026-07-23. When extraction
  fails or looks wrong, distinguishes the three known failure modes (GH-68 stale-token 400, GH-69
  scripted-click no-op, stale-panel cross-video corruption) via network requests, so a fix isn't attempted
  against the wrong theory. Run this before writing any panel-related fix.
- **`diagnose-stuck-automation`** (`.claude/skills/diagnose-stuck-automation/`) — added 2026-07-23.
  General Claude-in-Chrome checklist (not project-specific) for "click seems to do nothing": coordinate
  scaling, real-vs-scripted click as a variable, network requests as ground truth, tab-throttling and
  tool-timeout artifacts. `youtube-panel-triage` defers to this for non-panel-specific click issues.

## What this project is

**YouTube Transcript → Airtable** — a Chrome extension that extracts transcripts from YouTube's web UI and saves them to an Airtable database. One-click operation: open a YouTube video, click the extension, extract, save.

## What this project is NOT (deprecated)

The following features were removed in May 2026 and should not be resurrected:

- **Storyboard generation** (ComfyUI, SDXL, IPAdapterAdvanced) — unfinished, no longer interesting
- **Frame capture pipeline** (TypeScript/Playwright, canvas capture) — removed from extension
- **Pipeline server** (`pipeline-server/` directory, `:3333` local server) — no longer used by extension
- **Shot list / scene analysis** — not the focus

Do not suggest work on these areas. If issues reference storyboard, ComfyUI, or the pipeline server, they are deprioritized.

## Active codebase: `chrome-extension/`

Everything worth touching lives here:

```
chrome-extension/
├── manifest.json       # Manifest V3; permissions: activeTab, storage
│                       # hosts: youtube.com, api.airtable.com
│                       # In-page work: add background.service_worker; retire/repurpose action.default_popup
├── content.js          # Runs on YouTube pages
│                       # - openTranscriptPanel(): 5 DOM strategies to reveal panel
│                       # - extractTranscript(): pulls segments + metadata + channel info
│                       # In-page work: injects the floating panel, SPA-remount lifecycle,
│                       #   direct extractTranscript() call, sendMessage to background.js, data-* contract
├── background.js       # NEW (in-page work): service worker owning ALL Airtable I/O.
│                       #   upsertChannel() + saveToAirtable() move here from popup.js; PAT read here only
├── popup.html          # Extension popup UI (transcript-only)
├── popup.js            # - extractTranscript(): sends message to content.js
│                       # - upsertChannel(): find-or-create Channels record
│                       # - saveToAirtable(): creates or updates Videos record
│                       # In-page work: retire, or shrink to a Settings launcher; save logic → background.js
├── lib/transcript-dom.js    # DOM parsing (both A/B variants) — untouched by in-page work
├── lib/transcript-utils.js  # GH-64 truncation shim — untouched; called from worker after move
├── settings.html       # Credential management page — untouched
├── settings.js         # Save/load/test API key + Base ID via chrome.storage.sync — untouched
└── icons/              # Placeholder only — no real PNGs needed (personal unpacked; no Web Store)
```

## Airtable schema

- **Base ID**: `appWSbpJAxjCyLfrZ`
- **Videos table** (`tblpwqMfiMsRsYuMY`) — fields written by extension:
  - `Video Title`, `Video ID`, `Platform` (YouTube), `Video URL`
  - `Triage Status` (default: Queued)
  - `Thumbnail URL`, `Thumbnail (Image)`
  - `Transcript (Full)` — plain text
  - `Transcript (Timestamped)` — JSON array of `{text, start}` objects
  - `Transcript Language`, `Transcript Source` (youtube-web-ui-dom)
  - `Channel` (linked record → Channels table)
- **Channels table** (`tblaTYkbXc072XEsT`) — find-or-create by `Channel Handle`

## Known issues / open work

- Transcript extraction is DOM-based; YouTube selector changes break it (update selectors in `content.js`)
- YouTube runs **multiple concurrent A/B panel variants** — extraction must match all of them,
  not just the current default. Known segment elements (`content.js` `SEGMENT_SELECTORS`):
  - Classic Polymer: `ytd-transcript-segment-renderer` (timestamp/text in `span.yt-core-attributed-string`)
  - Modern view-model (`PAmodern_transcript_view`): `transcript-segment-view-model`
    (timestamp in `.ytwTranscriptSegmentViewModelTimestamp`, text in `.ytAttributedStringHost`);
    lazy-loads behind a spinner and renders into the expanded panel whose `target-id` is `null`
- Issue #67 (FIXED): modern A/B variant returned 0 segments — now matched document-wide across both
  tags with lazy-load polling. When a new variant appears, capture one segment's `outerHTML` from the
  live panel and add its tag + timestamp/text classes to `SEGMENT_SELECTORS` / the per-row mapping.
- Icons directory has placeholder only — real PNGs no longer needed (personal unpacked build; Chrome Web Store publish is a non-goal)
- Issue #8: full transcript extraction (currently may be partial for very long videos)
- Issue #22: upstream frame/publisher contract mismatch (deprioritized — frame pipeline removed)
- Issue #64 (FIXED): transcripts >100k chars no longer fail the save. `lib/transcript-utils.js`
  truncates `Transcript (Full)` and trims `Transcript (Timestamped)` to valid JSON under the
  limit; the popup shows a warning when truncation occurs. Tests: `cd chrome-extension && npm test`.
- Issue #65 (open): lossless full-transcript storage (attachment / R2 / chunk table) — the proper
  follow-up that would remove the truncation shim.

## Future direction

- **In-page agent-drivable panel** (current initiative — see section above and `docs/PROJECT-MANIFEST-in-page-panel.md`)
- Transcript quality improvements (multi-language detection, full extraction for long videos)
- Timestamps UX (show/hide in panel preview)
- Possible: export transcript as markdown/txt download

**Explicit non-goals** (do not build — the agent owns the loop, personal build only):
- Batch queue / import-list logic inside the extension (the playlist is the queue; the agent iterates)
- Keyboard shortcut (Ctrl+Shift+T) — was a prior idea, dropped; agent triggers the in-page button
- Chrome Web Store publish, icon/store assets, store review

## Environment

Credentials live in `.env` (not committed):
- `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`
- Extension uses `chrome.storage.sync` for credentials (entered via Settings page)

No build step. Vanilla JS. Load unpacked at `chrome://extensions/`.
