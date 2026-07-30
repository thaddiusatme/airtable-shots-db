# Archived findings — YouTube transcript automation (Mar–Jul 2026)

Consolidated 2026-07-29, when transcript capture pivoted to a hosted scraper (Apify) and the
browser-automation line of work was frozen. This file is the **memory** of that work: the facts that
cost real time to establish, separated from the theories they killed.

Nothing here is a live instruction. For current state see `CLAUDE.md`. Read this before proposing
*any* change to how transcripts get captured — several dead ends in here were proposed twice.

---

## 1. Transcript sources: four attempts, and why three failed

This is the most important section. The capture problem was attacked from four directions over five
months. **Three are permanently ruled out, and one of them was re-proposed after already being
disproven in this same repo.**

### 1a. Official YouTube Data API v3 (`captions.download`) — DEALBREAKER

Analyzed in the (now deleted) `OPTION_C_YOUTUBE_DATA_API_ANALYSIS.md`. The API only permits caption
download **for videos you own**. Per Google's own documentation and support answers: *"Only owners of
a video can download its captions."* Quotas were never the issue — ownership is. The Data API is
built for channel owners managing their own content, not for reading other creators' transcripts.

**Status: permanently closed.** No amount of quota, key, or OAuth scope changes this.

### 1b. Direct HTTP to the transcript endpoint (`youtube-transcript-api` / `timedtext`) — IP BLOCKED

Analyzed in the (now deleted) `IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md`. Empirically tested, not
theorized:

| Call | Result |
|------|--------|
| `.list()` (metadata / available tracks) | ✅ 100% success |
| `.fetch()` (actual transcript content) | ❌ 100% failure — HTTP 429 `IpBlocked` |

Tested across popular, obscure, old and new videos (`nVnxG10D5W0`, `dQw4w9WgXcQ`, `jNQXAC9IVRw`,
`0VH1Lim8gL8`, `O5xeyoRL95U`) — all blocked. Mitigations attempted and **all failed**: browser
user-agent spoofing, 30-second cooldowns between requests, multiple language codes, different videos.

YouTube rate-limits the *content* endpoint specifically while leaving the listing endpoint open. The
analysis concluded: **only rotating residential proxies work reliably.**

**Status: closed for direct self-hosted use.** The code was never the problem; the IP was.

### 1c. Browser DOM extraction (the Chrome extension) — WORKS, BUT DELIVERY IS UNRELIABLE

This is what actually shipped and what still works today. It sidesteps both problems above by
reading the transcript out of the logged-in browser's own DOM, so there's no API ownership check and
no separate IP to block. Its weakness is not extraction but **click delivery** — see §3.

**Status: frozen fallback.** Works for one-off manual captures. Not viable unattended.

### 1d. Hosted scraper (Apify `streamers/youtube-scraper`) — CURRENT DIRECTION

**The critical connection: §1b's finding is exactly why this is the right answer, not a lateral
move.** The one mitigation that IP-blocking analysis identified as working — rotating residential
proxies plus a maintained scraper — is precisely what a hosted scraping platform sells. Apify is not
"another option"; it is the only form of §1b that can actually function.

### ⚠️ The loop to not repeat

On 2026-07-27, `RESEARCH_FINDINGS_GUI_AUTOMATION_FEASIBILITY.md` recommended, as a simpler
alternative worth evaluating first, *"calling the `timedtext` endpoint directly via HTTP (as
`youtube-transcript-api` does)"* — i.e. **it re-proposed §1b, which this repo had already disproven
empirically.** The earlier analysis existed but wasn't consulted.

**If a future session proposes direct HTTP transcript fetching, that is the third occurrence. The
answer is 429 `IpBlocked` unless residential proxies are in the path.**

---

## 2. The Chrome extension — what it is and its agent contract

Manifest V3, vanilla JS, no build step, loaded unpacked. Chrome Web Store publish is a non-goal.

- `content.js` — runs on YouTube watch pages; injects an in-page panel, handles SPA re-mount,
  extracts segments, messages the service worker.
- `background.js` — service worker owning **all** Airtable I/O. This split is load-bearing: a
  content-script `fetch()` to `api.airtable.com` is subject to YouTube's CORS policy and gets
  rejected. Required path is content script → `chrome.runtime.sendMessage` → worker → `fetch()`.
  Bonus: the Airtable PAT is only ever read inside the worker, never in the page world.
- `lib/transcript-dom.js` — DOM parsing for both A/B variants, with a fixture test harness.
- `lib/transcript-utils.js` — the GH-64 truncation shim. **Reusable by any future writer.**

Agent contract (was treated as a stable API):

- Panel root `<div id="yt-transcript-panel" data-save-state data-video-id data-error-msg>`
- Button: real `<button aria-label="Extract and save transcript" data-testid="extract-save-btn">`,
  fixed position, always visible.
- `data-save-state`: `waiting → idle → extracting → saving → saved | error`. Never hangs on `saving`.
- **Open** shadow root or prefixed classes — a *closed* shadow root hides the panel from agent `find`.
- SPA remount is a **reset-in-place** on `yt-navigate-finish`: attributes flip, no nodes are
  added/removed. Don't write tests expecting `panel-added` mutations.

Verified working on a real 76-video playlist run (2026-07-17): CORS path wrote real records, agent
`find` returned exactly one hit, state machine never hung (6.6s worst case to `error`), and
upsert-by-`Video ID` was genuinely idempotent — 3 saves of one video produced 1 record, and the error
path wrote **nothing** (no junk rows).

---

## 3. The click-delivery saga — established vs. theorized

Five months of investigation across GH-67, GH-68, GH-69, GH-70. Separated deliberately, because the
chronological notes contradicted each other and the contradictions were load-bearing.

### Established by evidence

**Stale continuation token → HTTP 400 (GH-68).** `POST /youtubei/v1/get_transcript` returns 400 when
the description-embedded "Show transcript" button is clicked while still holding the *previous*
video's continuation token after SPA navigation. The panel then spins forever because the fetch
failed and nothing in the DOM surfaces it. Found via `read_network_requests` — every DOM-level theory
before that (stale panel, close buttons, user activation, window focus) was downstream noise.

**`idle` was lying (GH-68 fix, implemented + verified 2026-07-22).** `mountPanel()` fired on
`yt-navigate-finish` and advertised `idle` + the new `data-video-id` while YouTube was still
mid-swap. Measured live: at `yt-navigate-finish` the URL already named the new video but
`ytd-watch-flexy[video-id]` still reported the **previous** one for **~1.4–2s**. Fix: hold a new
`waiting` state until `watch-flexy[video-id] === urlVideoId`, poll 50ms, 4s fail-open;
`onExtractSaveClick()` refuses to run while `waiting`. Verified with a clean attributed write
(`receRO6SOSsBmx9Ck`).

**Scripted clicks can silently never fire the request (GH-69, 2026-07-23).** Dozens of
correctly-targeted `javascript_tool` `.click()` attempts, multiple videos, timeouts to 90s+, on fresh
page loads (so no stale token) → **zero** `get_transcript` network requests, confirmed via
`read_network_requests` rather than inferred from DOM. The same button, same video, same session,
clicked with a genuine trusted event worked immediately.

**A real OS-level click works where CDP clicks didn't (GH-70 Phase 0, 2026-07-27).** Quartz
`CGEventCreateMouseEvent` + `CGEventPost` via **ctypes** (pyobjc has no wheel for Python 3.14 and
only wraps the same C functions). On `ovabeVoWrA0` with zero CDP attached: `isTrusted:true`, native
Show transcript fired `get_transcript` in 308ms → **2342 segments**, extension went
`idle → saving → saved` in 16s, verified in Airtable as `rec5uUvvw2CTFBeyI`.

**Truncation is real and active.** That same record's transcript was cut at exactly 100k by the
GH-64 shim.

### Theories that were killed

**"ASR-only captions cause the failures."** A clean-looking 3-for-3 split had failing videos with
only an `"asr"` track and a control (`dQw4w9WgXcQ`) with a manual track succeeding. **Killed** by
`ovabeVoWrA0`, which has a single `"asr"` track and no manual one, and extracted cleanly. Caption
type alone does not explain the failures.

**"The prior extraction is the trigger."** A controlled comparison table said so (fresh load → 610
segments; SPA nav with no prior extract → 610 segments; SPA nav after extracting #1 → error, 0
segments, stuck spinner). The table is real but the conclusion misleads: the true variable is
**elapsed time since navigation**, which the prior extraction merely correlates with.

**"Scripted always fails, real click is the fix."** Over-read from GH-69. On 2026-07-26 an agent
`computer` click *did* trigger a successful save (`recti9Qu1mpKGx717`) — and the panel still read
`error` afterward. The finding holds only for the **no-request signature**.

### Never resolved

**Retry-on-400 for automated runs.** `get_transcript` can 400 on the very first request even on a
genuinely fresh page load — not only after SPA nav as GH-68 assumed. Attempted fix: prefer the "In
this video" panel's **Transcript tab** over the description button, on the theory that YouTube's own
client silently retries once after a 400 through that tab. Confirmed exactly once via a *real manual*
click; **reverted the same day** after re-testing through the extension's scripted click against two
fresh videos produced **zero** `get_transcript` requests — not even a 400. The Transcript tab needs a
real trusted click to do anything at all, unlike the description button which at least fires a
failing request. The "fix" was a regression for the automated path. A dead-end comment was left in
`content.js` above `findBestTranscriptButton()`.

**Fresh tab per video.** Hypothesis: a brand-new tab per video avoids whatever accumulates against a
reused tab. Tested with `content.js` reverted to pre-2026-07-27 state, so purely operational — **4
for 4 succeeded**, including `ib74sLgjIBM` and `vmVvpKSSxWE` which had failed repeatedly for over an
hour in a reused tab. All 4 verified as real Airtable records, not just `data-save-state: saved`.
Contrast: 3 consecutive failures out of 3 in a reused tab earlier the same day.

**But a same-day counterexample directly conflicts:** working the "AI (Claude)" playlist
(`PLVwTAkoVGJsY`), `vmVvpKSSxWE` was tested in a tab created fresh moments earlier — first-ever
navigation in it — and a real click on YouTube's native transcript control still 400'd. Sample size
is tiny and both results may be confounded with elapsed time / caption-generation settling rather
than the tab itself.

**The missing negative control.** A *CDP-driven* click was never re-run on `ovabeVoWrA0` in the same
session to watch it fail. So "OS click works" and "CDP click fails" are separated by hours and by the
focus confound in §6. GH-70 Fork A's premise was supported but **never proven.**

---

## 4. The silent-corruption path — the most important safety finding

**Read this before writing any transcript-to-Airtable code, including the Apify normalizer.**

Three attempts were made to fix the stuck-panel bug by closing the transcript panel. The third one
**corrupted an Airtable record.**

Closing the panel **does not remove segment nodes from the DOM.** `extractTranscript()` began with a
document-wide `collectSegments(document)`, so on video N+1 it instantly harvested video N's leftover
rows — 2ms, no fetch — and saved **video N's transcript under video N+1's ID**, reporting `saved`.
Record `recoYXkJNQIykIckl` (a Targaryens documentary) was overwritten with video #1's Dan Harmon
transcript.

**The original bug was safer than the fix.** YouTube clears the segments and leaves a spinner, so
extraction fails *loudly*. The "fix" made it fail *silently and wrongly*.

Why attempts 1–2 appeared to fail: `closeTranscriptPanel()` was itself broken. It matched
`button[aria-label="Close transcript"]` document-wide, which resolves to a **0x0 button inside a
hidden legacy panel** — clicking it is a silent no-op. The console logged "Closing open transcript
panel" while closing nothing. The theory was never actually tested.

**Constraints for any future implementation:**

- It is not enough to make extraction *succeed* — it must be **impossible to extract stale data**.
- **Verify provenance, not content.** A transcript is just text and timestamps with no intrinsic
  video ID, so content verification is not available. Prove the data was populated *after* the
  current video's swap settled (a generation counter bumped on each navigation).
- **Corruption signature:** `extracting → saving` in under ~100ms with no network fetch. Treat as
  stale, error loudly, never save.
- Verify the saved transcript's **content**, not merely that state reached `saved`.

**This guard (item #2 of the GH-68 fix plan) was never implemented.** The `waiting`-state fix
addresses the 400 failure mode only. The silent-corruption path was open when this line of work was
frozen.

---

## 5. Airtable write invariants — any future writer must preserve these

Earned the hard way. The Apify normalizer inherits every one of them.

1. **Upsert by `Video ID`, never blind create.** Verified idempotent in the extension: 3 saves → 1
   record.
2. **Two records sharing one `Video ID` break the upsert** — it fails on multiple matches. Never
   hand-create a Video or Channel record without first checking by `Video ID`. When recovering a
   "failed" harvest, **adopt the existing record**; don't create a second.
3. **Never touch `Triage Status` on update. Set `Queued` on create only.** Observed consequence of
   getting this right-but-surprising: `vmVvpKSSxWE` already had `Triage Status = Declined`; the upsert
   updated its transcript fields and left triage alone, so a video marked Declined silently regained a
   transcript without changing triage state. Worth a human glance rather than assuming `Queued`.
4. **`data-save-state` is not ground truth — verify the write.** `error` (or a poll timing out
   mid-`extracting`/`saving`) can be a **false negative** after a save has already landed. Query
   Videos by `Video ID` before treating a run as failed. **A single misread of this caused the
   2026-07-26 duplicate-record incident**: the write had succeeded, the panel said `error`, a second
   run was fired, the duplicate broke the upsert per invariant 2. Cheapest recovery is check Airtable
   → reload → retry, never synthesizing a record by hand.
5. **Transcripts over 100k chars must be truncated** (GH-64, `lib/transcript-utils.js`): truncates
   `Transcript (Full)` and trims `Transcript (Timestamped)` to still-valid JSON under the limit.
   Lossless storage is **GH-65, still open** — a hosted scraper's key-value store may resolve it.
6. **Pull transcripts one record at a time by recordId.** A full-table pull of the transcript column
   returned ~2.7M chars and blew the token limit.
7. **Truncation used to warn a human.** The popup surfaced it. Any unattended writer has no such
   surface — log it loudly or solve GH-65.

Schema: base `appWSbpJAxjCyLfrZ`; Videos `tblpwqMfiMsRsYuMY`; Channels `tblaTYkbXc072XEsT`
(find-or-create by `Channel Handle`).

---

## 6. Environment gotchas — macOS, Chrome, CDP automation

Expensive to rediscover. Mostly not project-specific.

**macOS click-to-focus will fake a "site ignored the click" null result.** Mid-run, clicks silently
stopped arriving with a textbook signature: no listener entry, no network request, panel unchanged.
It was an artifact. `document.hasFocus()` was `false` while `AXFrontmost=true`, `AXMain=true`, no
sheets, and after `activate`. **The first mouse-down after a window loses focus is consumed
activating that window and never reaches page content.** The discriminator: mouse *motion* still
reached the page while clicks did not — motion routes by cursor location, button events need a key
window. `phase0_quartz_click.py click` gained an `ensure_focus()` that refuses to click without
verified focus. **This may well have contaminated the earlier AppleScript attempt, and it is the
focus confound that leaves §3's negative control missing.**

**Screen→client coordinate mapping is affine, not a translation.** `window.screenY + (outerHeight -
innerHeight)` went **negative**: `outerHeight` is physical points, `innerHeight` is CSS px. At 90%
page zoom the scale was 1.111, so a single-point offset was 77px off and drifted across the viewport.
Solve scale *and* origin from two separated measured points; refuse to click uncalibrated.

**Apple Events `execute javascript` runs in an ISOLATED world.** `ytInitialPlayerResponse`, `ytcfg`
and `ytd` are all `undefined`, though `document`, `localStorage` and `performance` work fine. Page
globals are never visible at all — caption-track type has to be scraped from inline `<script>` text.

**`performance.getEntriesByType('resource')` is a CDP-free substitute for reading network requests** —
detects whether a request happened without attaching the debugger under test. No status code, so a
hit proves the request occurred, not that it succeeded.

**Check accessibility permission, don't assume it.** `AXIsProcessTrusted` returned **true** for
Claude Code's own process, contradicting an earlier note that Terminal.app's grant doesn't extend to
it.

**`javascript_tool` caps output at ~1000 chars.** `get_page_text` on injected DOM is the
large-payload escape hatch. Manual DOM harvest is a last resort and must **upsert, not create**.

**Digital Color Meter does not show x/y coordinates.** Docking/undocking DevTools changes window
bounds, and an undocked DevTools window becomes Chrome's `front window` for AppleScript.

---

## 7. YouTube DOM facts — only if the extension is ever revived

**Multiple concurrent A/B panel variants exist.** Extraction must match all of them, not just the
current default (`SEGMENT_SELECTORS`):

- Classic Polymer: `ytd-transcript-segment-renderer`, timestamp/text in
  `span.yt-core-attributed-string`.
- Modern view-model (`PAmodern_transcript_view`): `transcript-segment-view-model`, timestamp in
  `.ytwTranscriptSegmentViewModelTimestamp`, text in `.ytAttributedStringHost`. Lazy-loads behind a
  spinner into the expanded panel whose `target-id` is `null`.

When a new variant appears: capture one segment's `outerHTML` from the live panel and add its tag
plus timestamp/text classes to `SEGMENT_SELECTORS` and the per-row mapping. (GH-67 was exactly this.)

**Traps that break the obvious approaches:**

- The actually-open transcript panel reports **`target-id="null"`**. Filtering panels by
  `/transcript/i` on `target-id` **misses the real one**.
- Its close button is labelled **`"Close"`**, not `"Close transcript"`. The `"Close transcript"`
  button belongs to a *hidden* `engagement-panel-searchable-transcript` that lingers.
- Detect open transcript panels by **content + visibility** (`offsetWidth || offsetHeight` AND
  contains segment elements) — never by `target-id`, never by presence of a close button.

---

## 8. Dead — do not resurrect

**Removed 2026-07-29** (recoverable from git history before that commit):

- **Storyboard generation** (ComfyUI, SDXL, IPAdapterAdvanced) — unfinished, no longer interesting.
- **Frame capture pipeline** (TypeScript/Playwright, canvas capture).
- **Pipeline server** (`pipeline-server/`, local `:3333`) — no longer used by the extension.
- **Shot list / scene analysis**, `analyzer/`, `publisher/`, `segmenter/`, `comfyui/`, `templates/`,
  the Python test suite, and the Airtable schema-migration scripts.

These had been documented as "removed in May 2026" while still fully present in the tree for two
months. If issues reference storyboard, ComfyUI, or the pipeline server, they are dead.

**Also closed as capture strategies:**

- YouTube Data API v3 for transcripts (§1a — ownership dealbreaker).
- Direct HTTP / `timedtext` / `youtube-transcript-api` from our own IP (§1b — 429 `IpBlocked`).
- **GH-70 Fork A** — rebuilding click delivery on OS-level GUI automation. Phase 0 showed it *can*
  work but never ran the negative control, and it solves click delivery only, leaving §4's
  corruption path and the unattended-reliability problem untouched.
- **GH-70 Fork B** — direct `timedtext` HTTP. Identical to §1b. See the loop warning there.
- Batch queue / import-list logic **inside** the extension, and the Ctrl+Shift+T keyboard shortcut.
- Chrome Web Store publish, icons, store assets, store review.

**Superseded by Fork C — buy the proxy pool** (Apify hosted scraper). See `CLAUDE.md`.
