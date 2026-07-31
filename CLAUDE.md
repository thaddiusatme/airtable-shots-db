# CLAUDE.md — YouTube Transcript → Airtable

## What this project is

Capture YouTube transcripts and metadata into Airtable, so the **AIHS content refinery** (separate
project, `~/claude/Youtube Transcripts`) can turn them into teardowns, digests and content ideas.

This repo owns **capture only**. Triage, treatment, and everything downstream lives in the refinery.

## Current state — 2026-07-30

**The pivot from browser automation to a hosted scraper is complete.** Five months of work proved
that the transcript can be *extracted* reliably but not *delivered* reliably without a human
clicking. The decision record and the full evidence are in
`docs/archive/FINDINGS-youtube-automation.md` — **read §1 before proposing any change to the capture
mechanism.**

Capture is no longer the constraint. Unattended batch sweeps run on one command, and the binding
limit is now the **human review gate** downstream in the refinery. Read that as: the useful work
left in this repo is mostly *not* "capture more," it's making what's captured easier to triage.

| Path | Status |
|------|--------|
| Apify `streamers/youtube-scraper` (`h7sDV53CddomktSi5`) | **Primary — working end to end**, verified live 2026-07-29, extended to metrics + batch sweeps 2026-07-30 (branch `feat/metrics-fields`) |
| Chrome extension (`chrome-extension/`) | **Frozen fallback** — works, no further investment |
| YouTube Data API v3 | Permanently closed — ownership dealbreaker |
| Direct HTTP / `timedtext` from our own IP | Permanently closed — 429 `IpBlocked` |

**Why a paid scraper and not a fix.** `IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md` established back in the
spring that direct transcript fetching returns 429 `IpBlocked` 100% of the time from our IP, and that
**only rotating residential proxies work.** A hosted scraping platform is that mitigation, bought
rather than built. This is not a lateral move to a new tool — it is the only version of the
direct-fetch approach that can function. Apify is "Fork C" in the GH-70 decision; Forks A (OS-level
GUI automation) and B (direct HTTP) are closed.

**The extension stays loaded and working.** It's the right tool for "this one video, right now, no
cost." It is not the right tool for unattended volume, and it should not be developed further.

## Active work — Apify → Airtable normalizer `[working; proven live 2026-07-30]`

Run it, one channel:

```
cd normalizer && node apify-harvest.js --channel-url <url> --max-results <n> \
  --oldest-post-date <YYYY-MM-DD> [--dry-run] [--save-raw <path>]
```

Or sweep every Channel with `Harvest?` ticked, using its `Source URL`:

```
cd normalizer && node apify-harvest.js --from-airtable --max-results <n> --oldest-post-date "30 days"
```

`--max-results` and `--oldest-post-date` are mandatory by design **in both modes** — batch
multiplies the cost by the channel count, so it needs more bounding, not less. Details and the live
verification tables: `docs/NORMALIZER-MANIFEST.md`.

```
Airtable Channels (Harvest? · Source URL · Last harvested · Track)
        ↓ read config, re-check Queued-count ceiling BEFORE EACH CHANNEL
Apify run: startUrls + oldestPostDate + maxResults + downloadSubtitles
        ↓ dataset
Normalizer (this repo, Node — reuses chrome-extension/lib/transcript-utils.js)
   parse subtitles → {text,start} · find-or-create Channel · upsert by Video ID
   metrics + description + links → updateFields · channel stats → Channels
        ↓
Videos: Triage Status=Queued · Intake Source=Sweep · Track via Channel link
        ↓ unchanged
AIHS refinery: triage → teardown/digest → Ideas → human review gate
```

The ceiling is re-checked **per channel**, not once per run: a single up-front check would let one
verdict wave ten channels through, which is a guardrail that stops guarding exactly when volume
arrives.

Decisions already made (2026-07-29):

- Normalizer is a **local Node script in this repo**, reusing `lib/transcript-utils.js` so the GH-64
  truncation logic isn't reimplemented. Not an Airtable automation, not a webhook, not in-session MCP.
- Harvest config lives in **Airtable Channels**, not a repo JSON file — `Track` already lives there,
  and adding a channel shouldn't need a commit.
- Ship a `--dry-run` that prints intended writes and touches nothing, **before** it ever writes.

Guardrails, because removing capture friction removes the accidental throttle on intake (the
refinery's real bottleneck is a human review gate). All shipped except the last:

- ✅ `maxResults` **and** a date filter mandatory on every run, both modes. No unbounded pulls.
- ✅ `Intake Source` on Videos — hand-curated (`Watch Later`) vs swept (`Sweep`), so triage can be
  stricter on sweeps. Everything triaged before 2026-07-30 was hand-picked; that's no longer true.
- ✅ Queue-depth ceiling, **re-checked before each channel** in batch mode.
- ⬜ A **Track-unset** view on Channels. Bulk ingest creates Channels with blank `Track`, and the
  refinery's working view filters `Track = AIHS OR Tooling-watch` — so blank-Track videos vanish
  *silently* rather than failing loudly. **4 of 88 Channels** are currently blank
  (`@Jasper_Tech`, `@BulbDigital`, `@3.7Million`, `@WizardsandWarriors`). Manual UI step — the
  Airtable MCP has no create-view tool.

### Where things stand, and what's actually next

Live counts as of 2026-07-30: **106 Videos** (16 `Queued`, ceiling 30), **88 Channels**, 5 with
`Harvest?` ticked (`@WayneStLedger`, `@M365CopilotConnection`, `@MicrosoftCommunityLearning`,
`@KevinStratvert`, `@your365coach`).

1. **Triage the 16 Queued** before sweeping more — the ceiling will halt a batch partway at 30, by
   design. This is the bottleneck; adding capture volume against it is the one move that makes
   things worse.
2. **Commit `feat/metrics-fields`** — the metrics/batch work is verified live but was left
   uncommitted.
3. Build the Track-unset view (above).
4. Decide unattended invocation — cron, a scheduled task, or stay manual. `--from-airtable` makes
   this a single command with no channel list baked into the repo, so nothing blocks it technically.
   The question is whether *capture* should be automated while triage isn't.

Actor input keys (verified 2026-07-29 against the published schema and two live channel-mode runs):
`startUrls`, `maxResults`, `maxResultsShorts`, `maxResultStreams`, `oldestPostDate`, `dateFilter`,
`videoType`, `sortVideosBy`, `downloadSubtitles`, `subtitlesLanguage`, `subtitlesFormat`,
`preferAutoGeneratedSubtitles` (**not** `preferAutoGenerated`), `saveSubsToKVS`. Pricing is
pay-per-event, $0.004/video on free tier down to $0.001 at higher plan tiers.

**`oldestPostDate` is honored, not merely accepted** — proven by negative control: bounding the same
call at `2026-07-29` returned 1 item instead of 2. It also accepts relative values (`"7 days"`).

**Channels are keyed on `'@' + channelUsername`, never Apify's `channelId`.** All 87 existing rows
are `@handle` (written by `content.js`, which parses the `/@handle` owner link); Apify's `channelId`
is `UC...` and its `channelUrl` is the `/channel/UC...` form. Keying on the UC id forks the Channels
table — a new blank-`Track` row per sweep, with swept videos linked to the invisible orphan. This
fails by *succeeding*, so nothing surfaces it. See `docs/NORMALIZER-MANIFEST.md` for the full
correction.

## Airtable

- Base `appWSbpJAxjCyLfrZ`
- **Videos** `tblpwqMfiMsRsYuMY` — `Video Title`, `Video ID`, `Platform`, `Video URL`,
  `Triage Status` (default Queued), `Thumbnail URL`, `Thumbnail (Image)`, `Transcript (Full)`,
  `Transcript (Timestamped)` (JSON array of `{text, start}`), `Transcript Language`,
  `Transcript Source`, `Channel` (link)
  - **Metrics/repurposing (added 2026-07-30)** — `Published At`, `View Count`, `Like Count`,
    `Comment Count`, `Duration`, `Description`, `Description Links`, `Hashtags`,
    `Metrics Captured At`, plus formulas `Views per Day` and `Engagement Rate %`. All written to
    `updateFields`, so **a re-sweep is the metrics-refresh mechanism** — there is no other one.
    Metrics are overwritten in place; only `Metrics Captured At` keeps them honest. No history.
- **Channels** `tblaTYkbXc072XEsT` — find-or-create by `Channel Handle`
  - Harvest config: `Harvest?` (checkbox), `Source URL`, `Last harvested` (stamped only after a
    sweep with zero errors, so a failure stays visibly stale)
  - Stats: `Subscribers`, `Total Videos`, `Total Views`, `Channel Description`, `Stats Captured At`

### Write invariants — non-negotiable, inherited by the normalizer

1. **Upsert by `Video ID`.** Never blind create.
2. **Two records sharing one `Video ID` break the upsert.** Check before creating anything by hand;
   when recovering a "failed" run, adopt the existing record. The normalizer now *enforces* this —
   both finders throw and name the colliding ids rather than silently writing to `records[0]`, which
   is what both it and `background.js` used to do. (`Video ID oTphk2SVHNc` was in exactly this state
   until 2026-07-29; the two records held identical transcripts but disjoint links — 25 Shots on one,
   the Channel link and provenance on the other — so they were merged, not parked.)
3. **Never touch `Triage Status` on update.** Set `Queued` on create only. The Channels analogue is
   **`Track`**: `upsertChannel` now PATCHes stats onto existing rows, and it must never write
   `Track`. Both are human-owned routing, and both fail silently — a clobbered `Track` drops the
   channel out of the working view without erroring. The protection is structural, not a rule to
   remember: `transform.js` builds the stats object and `Track` is simply never in it.
4. **Verify the write by querying `Video ID`.** Never trust a status flag — a reported `error` can be
   a false negative after a successful save. Acting on one caused a duplicate record on 2026-07-26.
5. **Truncate transcripts over 100k chars** via `lib/transcript-utils.js` (GH-64), keeping
   `Transcript (Timestamped)` valid JSON. Log truncation loudly — unattended runs have no human to see
   a warning.
6. **Pull transcripts one record at a time by recordId.** A full-column pull returned ~2.7M chars.
7. **A singleSelect write fails the whole record.** `Transcript Source`, `Triage Status`,
   `Intake Source` and `Platform` are all singleSelects, and Airtable 422s the entire create if a
   value isn't an existing option (no `typecast` is used, deliberately — it would silently invent
   options on a typo). Check the option exists before adding a new provenance value. A `--dry-run`
   **cannot** catch this, because it performs no writes. Machine-written values follow a slug
   convention: `youtube-web-ui-dom` (extension), `apify-youtube-scraper` (normalizer).
   Note the Airtable API cannot add choices — that is a manual UI step.

   **Corollary: no actor-supplied value may go into a singleSelect/multipleSelects.** We control
   the provenance slugs, so those are safe as selects. We do not control what YouTube returns, so a
   field like `Hashtags` — which looks exactly like a multi-select — must be plain text, or the
   first unseen tag 422s the whole record. Selects are for our vocabulary, never theirs.

8. **A new field must exist in Airtable before anything writes to it.** An unknown field name 422s
   the entire record, and `--dry-run` cannot catch that either, for the same reason. Schema first.

Rationale and the incidents behind each: `docs/archive/FINDINGS-youtube-automation.md` §4–5.

## Codebase

```
chrome-extension/          # the frozen fallback — Manifest V3, vanilla JS, no build step
├── manifest.json          #   permissions: activeTab, storage; hosts: youtube.com, api.airtable.com
├── content.js             #   in-page panel, SPA lifecycle, extraction
├── background.js          #   service worker — ALL Airtable I/O (CORS requires this; PAT read here only)
├── lib/transcript-dom.js  #   DOM parsing, both A/B variants (+ fixture tests)
├── lib/transcript-utils.js#   GH-64 truncation shim — REUSE THIS in the normalizer
├── popup.*  settings.*    #   manual UI + credential entry
└── icons/                 #   placeholders only; no store publish
docs/archive/              # FINDINGS-youtube-automation.md — five months of hard-won facts
.claude/skills/            # diagnose-stuck-automation (general-purpose, kept)
```

Tests: `cd chrome-extension && npm test`.

## Skills

- **`diagnose-stuck-automation`** — general Claude-in-Chrome checklist for "the click seems to do
  nothing": coordinate scaling, real-vs-scripted click as a variable, network requests as ground
  truth, tab-throttling and tool-timeout artifacts. Not project-specific; kept.
- **`apify-harvest`** — run a bounded channel sweep through the normalizer and verify the writes
  landed. Encodes the non-negotiables (verify by querying, check Channels didn't fork, never guess
  `Track`, never touch `Triage Status`) and the error playbook.
- Retired 2026-07-29 along with the browser-automation line: `harvest-playlist`, `verify-panel`,
  `youtube-panel-triage`. `apify-harvest` replaces them.

## Environment

Credentials in `.env` (not committed): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`. The normalizer will
also need `APIFY_TOKEN`. The extension reads credentials from `chrome.storage.sync`, entered via its
Settings page.

No build step. Vanilla JS. Load unpacked at `chrome://extensions/`.

## Open issues

- **GH-65 (open, low priority)** — lossless full-transcript storage, which would remove the GH-64
  truncation shim. Apify's `saveSubsToKVS` may resolve this nearly free by giving a hosted file URL.
  **Verify retention first** — unnamed Apify key-value stores expire (roughly 7 days on lower plans),
  so a stored pointer could rot. Named store, or copy the file out. Note observed transcripts run
  11k–44k chars against a 100k limit, so nothing has actually truncated yet — this is a latent
  problem, not a live one.
- **GH-64 (fixed)** — truncation shim in place, but it now runs unattended with nobody reading the
  warning.
- **No metrics history.** `View Count` and friends are overwritten on each sweep with only
  `Metrics Captured At` to date them, so you can see a video's velocity *now* but not its trend. A
  snapshot table is the upgrade path if "is this angle gaining?" becomes worth answering; it was
  deliberately not built (2026-07-30 decision).
- **Formula display precision is a UI-only setting.** `Views per Day` and `Engagement Rate %` are
  formatted to 0 decimals because the API can't set it (`update_field` accepts only
  `options.formula`). Display only — the stored values are exact. Fix in the Airtable UI if the grid
  needs decimals.
- **GH-69, GH-70 (to close)** — click-delivery investigations, superseded by the Apify pivot. Findings
  preserved in the archive doc.
- Provenance guard (GH-68 fix item #2) never implemented. Only matters if the extension is revived,
  but the *principle* — verify provenance, never trust that state reached `saved` — carries over to
  the normalizer.

## Dead — do not resurrect

Storyboard generation (ComfyUI, SDXL, IPAdapter), frame capture, `pipeline-server/`, shot list /
scene analysis, and the Python pipeline (`analyzer/`, `publisher/`, `segmenter/`, `comfyui/`,
`templates/`, `tests/`) — all deleted 2026-07-29, recoverable from git history. Also closed: batch
queue logic inside the extension (the harvest config is the queue), the Ctrl+Shift+T shortcut, and
Chrome Web Store publish.

Full list with reasoning: `docs/archive/FINDINGS-youtube-automation.md` §8.
