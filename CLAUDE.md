# CLAUDE.md — Project Manifest

## Current state (as of 2026-07-17)

- **Active branch**: `feature/transcript-only-extension` — pushed to remote, not yet merged to master. Continue on this branch.
- **Active initiative**: convert the toolbar popup into an **in-page, agent-drivable panel** (see next section). Design is in `docs/PROJECT-MANIFEST-in-page-panel.md` — Status: **Phase 0 spike built and verified GO** (2026-07-17).
- **Uncommitted**: the whole Phase 0 spike is dirty on disk — `content.js` (panel + lifecycle), `manifest.json` (service worker), new `background.js`, plus `docs/`. **Commit this before starting Phase 1.**
- **Previous branch** (abandoned): `fix/gh-61-62-storyboard-validate-and-readme-quickstart` — do not continue this work; storyboard is deprioritized
- **Next step**: fix the stale-transcript-panel bug (see below) — it blocks the agent loop — then Phase 1.

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

**Fix direction** (untested — do not assume): before extracting, verify the transcript entry point is fresh for
the current `videoId` (re-query the description section after it re-renders; consider gating on the panel's own
`videoId` matching, or retrying on 400) rather than clicking whatever button is present. Retry-after-delay is a
plausible cheap mitigation since the token becomes valid once YouTube finishes the swap.

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

**Phases**: 0 spike (de-risk CORS path + agent discoverability) → 1 service worker → 2 panel UI → 3 SPA lifecycle → 4 agent-contract hardening → 5 cleanup/cut over (retire `default_popup`, bump to v3.0.0). Core 0–3 ≈ 3–4 days.

**Untouched by this work**: `lib/transcript-dom.js` (+ test), `lib/transcript-utils.js` (+ test, now called from the worker), `settings.*`, the Airtable schema. GH-64 truncation logic must be preserved.

## Skills

- **`verify-panel`** (`.claude/skills/verify-panel/`) — acceptance test for the in-page panel with Claude in
  Chrome. Run after any change to `content.js` / `background.js` / `manifest.json`, and at the end of each phase.
  Encodes the method that caught the stale-panel bug (observe before clicking, confirm writes in Airtable,
  isolate before blaming the video).
- **`harvest-playlist`** (`.claude/skills/harvest-playlist/`) — runs the actual agent loop: walk a playlist,
  save every transcript, report. This is where queue/retry logic lives — never in the extension.

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
