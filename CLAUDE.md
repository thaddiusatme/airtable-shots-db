# CLAUDE.md — YouTube Transcript → Airtable

## What this project is

Capture YouTube transcripts and metadata into Airtable, so the **AIHS content refinery** (separate
project, `~/repos/aihs-refinery`) can turn them into teardowns, digests and content ideas.

This repo owns **capture only**. Triage, treatment, and everything downstream lives in the refinery.

## Capture mechanism (decided 2026-07-29)

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
| Apify `streamers/youtube-scraper` (`h7sDV53CddomktSi5`) | **Primary — working end to end**, verified live 2026-07-29, extended to metrics + batch sweeps 2026-07-30, merged to `master` via PR #69 |
| Chrome extension (`chrome-extension/`) | **Frozen fallback** — works, no further investment |
| YouTube Data API v3 transcripts | Permanently closed — caption ownership dealbreaker |
| YouTube Data API v3 playlists (`playlist-drain/`) | **Live — business-owned migration + transcript-verified drain, verified 2026-08-04** |
| Direct HTTP / `timedtext` from our own IP | Permanently closed — 429 `IpBlocked` |

**Why a paid scraper and not a fix.** `IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md` established back in the
spring that direct transcript fetching returns 429 `IpBlocked` 100% of the time from our IP, and that
**only rotating residential proxies work.** A hosted scraping platform is that mitigation, bought
rather than built. This is not a lateral move to a new tool — it is the only version of the
direct-fetch approach that can function. Apify is "Fork C" in the GH-70 decision; Forks A (OS-level
GUI automation) and B (direct HTTP) are closed.

**The extension stays loaded and working.** It's the right tool for "this one video, right now, no
cost." It is not the right tool for unattended volume, and it should not be developed further.

## Active work — business-owned intake playlists `[working; proven live 2026-08-04]`

The six personal playlists were copied once into unlisted playlists owned by **The AI Humble
Servant** (`UCQa5rETk8YLryqNlJzWJ2PA`). Their source and destination IDs live in
`playlist-drain/playlists.json`; destination URLs and ordered source hashes are recorded in
`docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md`.

**The migration is complete and is not a routine command.** Do not rerun `npm run migrate` after
draining: the business playlists intentionally stop matching the original personal playlists as
captured entries are removed. The personal playlists are preservation/reference copies now — never
delete from, reorder, rename, or use them as the live processing queue.

Routine operation is:

1. Save new intake videos into the matching **business-owned** playlist. If YouTube shows the
   personal playlists instead, switch to the business channel before saving.
2. Harvest the videos that landed there. **`--playlist-url` does not work here** — confirmed live
   2026-08-06, the Apify actor returns `NO_VIDEOS` for every business playlist because they are
   `unlisted` by design, and the actor cannot read unlisted playlists (a plain unauthenticated fetch
   of the same URL works fine; the actor's own scrape path is what fails). Use **`--video-urls`**
   instead — list the specific video watch URLs that were just added (from the sort report or by
   reading the playlist page) and feed them directly:

   ```bash
   cd normalizer && node apify-harvest.js \
     --video-urls "https://www.youtube.com/watch?v=ID1,https://www.youtube.com/watch?v=ID2,..." \
     --max-results <n, equal to the URL count — a lower value silently drops one> \
     --oldest-post-date <generous date>
   ```

   This is not a workaround bolted on top — per-video `startUrls` is the actor's **original,
   most-verified** input shape (2026-07-29 probe), more so than channel or playlist mode.
3. Verify the Airtable write by `Video ID`; never trust only the command summary.
4. Preview the drain, review the counts, then apply it:

   ```bash
   npm run drain --prefix playlist-drain
   npm run drain --prefix playlist-drain -- --apply
   ```

Drain eligibility is **capture completion**, not triage completion: exactly one Airtable Videos row
must match `Video ID`, and `Transcript (Full)` must be nonblank or `Transcript (Timestamped)` must be
a nonempty valid JSON array. `Triage Status` is irrelevant. Missing transcripts and duplicate
Airtable matches stay in the playlist. Deletion always uses the business playlist-item ID, treats a
later 404 as already removed, and verifies the item is absent afterward.

Both commands default to read-only. There is deliberately no scheduler; `--apply` is always an
explicit human invocation. The personal OAuth credential is read-only, the business credential is
write-enabled, and every mutation rechecks the expected business channel before acting.

## Active work — Apify → Airtable normalizer `[working; proven live 2026-07-30]`

Run it, one channel:

```
cd normalizer && node apify-harvest.js --channel-url <url> --max-results <n> \
  --oldest-post-date <YYYY-MM-DD> [--dry-run] [--save-raw <path>]
```

Or one playlist (added 2026-07-30 — **only works for public playlists**, see below):

```
cd normalizer && node apify-harvest.js --playlist-url <url> --max-results <n> \
  --oldest-post-date <YYYY-MM-DD> [--dry-run] [--save-raw <path>]
```

Or specific videos (added 2026-08-06 — the working path for the *unlisted* business playlists):

```
cd normalizer && node apify-harvest.js --video-urls <url1,url2,...> --max-results <n, ≥ url count> \
  --oldest-post-date <YYYY-MM-DD> [--dry-run] [--save-raw <path>]
```

Or sweep every Channel with `Harvest?` ticked, using its `Source URL`:

```
cd normalizer && node apify-harvest.js --from-airtable --max-results <n> --oldest-post-date "30 days"
```

`--max-results` and `--oldest-post-date` are mandatory by design **in all four modes** — batch
multiplies the cost by the channel count, so it needs more bounding, not less. `--channel-url`,
`--playlist-url`, `--video-urls`, and `--from-airtable` are mutually exclusive channel-selection
inputs. Details and the live verification tables: `docs/NORMALIZER-MANIFEST.md`.

**`--playlist-url` reconnects a leg that broke in the 2026-07-29 pivot, but only for *public*
playlists.** `watch-later-sort` routes videos into the six business playlists on the assumption that
a playlist harvester picks them up — but that harvester was the Chrome-extension per-video panel,
retired the same day this normalizer went live, and the normalizer that replaced it only took
`--channel-url`/`--from-airtable`. `--playlist-url` was meant to close that gap: the Apify actor's
`startUrls` accepts a playlist link exactly like a channel link (confirmed against the published
input schema), and `transform.js` already derives each video's Channel from the dataset item's own
`channelUsername`/`channelUrl` rather than from the input URL. **LIVE — run 2026-08-06: it does not
work against our actual business playlists.** The Apify actor cannot read `unlisted` playlists —
`NO_VIDEOS` against two real business playlists, reproduced twice, while the identical call against
a known-public playlist worked. All six business intake playlists are unlisted by design
(`docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md`), so this mode currently cannot serve the queue it was
built for. Full writeup: `docs/NORMALIZER-MANIFEST.md`.

**`--video-urls` is the mode that actually closes the gap (added 2026-08-06).** Same "third
channel-selection input, not a new data path" shape as playlist mode, but passes N individual video
watch URLs as N `startUrls` entries in one actor call — and per `lib/apify-client.js`'s header
comment, a single-video `startUrls` run is the actor's **original, most-verified** input shape
(2026-07-29 probe), more so than channel or playlist mode ever was. `--max-results` must be ≥ the
number of URLs given — unlike the cost-guardrail role it plays elsewhere, here a too-low value would
silently drop one of the exact videos named. **LIVE verified 2026-08-06** (15 videos, zero errors;
record IDs in the manifest). New Channels get blank `Track` for a human to set — do not guess it.
Not yet wired into `--from-airtable` (same reason as playlist mode: these aren't Channels-table
rows). Full writeup: `docs/NORMALIZER-MANIFEST.md`.

```
Airtable Channels (Harvest? · Source URL · Last harvested · Track)
        ↓ read config, re-check untriaged-count ceiling BEFORE EACH CHANNEL
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

**What the ceiling counts (changed 2026-10-07): untriaged videos** — `Triage Status = Queued` with a
blank `Triaged At` (`countUntriaged` in `normalizer/lib/airtable-client.js`). It used to count every
`Queued` video, which made videos a human had already kept, and that were only waiting on
extraction, block capture: on 2026-10-05 a harvest stopped at 30/30 with nothing left to triage.
`Triaged At` is a date field on Videos written only by the refinery's `triage-confirm.js --apply`,
on every video kept at triage. **This repo never writes it** — a video the normalizer creates has
it blank, which is exactly what makes a new video count as untriaged. The formula is shared with
`aihs-refinery/refine/lib/required-fields.js` and both repos pin it in a test.

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
- ✅ Queue-depth ceiling, **re-checked before each channel** in batch mode. Counts untriaged videos
  since 2026-10-07 (see above).
- ✅ A blank-`Track` audit. Bulk ingest may create Channels with blank `Track`; Track stopped gating
  the refinery working view on 2026-08-06, so this is incomplete metadata rather than a hidden-video
  defect. Kept as a repo-side audit command, `normalizer/audit.js`, rather
  than a manual Airtable view (the Airtable MCP has no create-view tool, so a view would need
  manual UI upkeep with nothing to catch drift). Run `cd normalizer && node audit.js` — it also
  checks for `Harvest?`-ticked channels with no `Source URL`, Videos with no Channel link,
  duplicate `Video ID`s, and Videos missing `Metrics Captured At`. The blank-`Track` warning is
  informational.

### Operating rules

Live counts drift; query Airtable or run `node normalizer/audit.js` instead of trusting a number here.

1. **Triage before sweeping more** — the ceiling will halt a batch partway at 30 untriaged, by
   design. This is the bottleneck; adding capture volume against it is the one move that makes
   things worse.
2. Run `node normalizer/audit.js` (above) periodically to catch drift — it's read-only and cheap.
3. **Unattended invocation stays manual (decided 2026-07-30).** `--from-airtable` makes it
   technically a single command with no channel list baked into the repo, but capture is not the
   real constraint — the AIHS refinery has spawned Ideas from only 5 of 106 captured videos, and
   published 0 of 27 Ideas ever created. Automating the cheap, working end of the pipe while the
   downstream review gate stays a bottleneck just piles up unreviewed ore faster. See the pipeline
   redesign doc, `~/claude/Youtube Transcripts/_meta/SPEC-pipeline-redesign-2026-07-30.md`
   (pointer: `docs/PIPELINE-REDESIGN.md`), before revisiting this.

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

`aihs-refinery/CLAUDE.md` cites rules 4, 6, 7 and 8 by number. Renumber them only together with
that file.

1. **Upsert by `Video ID`.** Never blind create.
2. **Two records sharing one `Video ID` break the upsert.** Check before creating anything by hand;
   when recovering a "failed" run, adopt the existing record. The normalizer now *enforces* this —
   both finders throw and name the colliding ids rather than silently writing to `records[0]`, which
   is what both it and `background.js` used to do. (`Video ID oTphk2SVHNc` was in exactly this state
   until 2026-07-29; the two records held identical transcripts but disjoint links — 25 Shots on one,
   the Channel link and provenance on the other. **Corrected 2026-07-30**: live state shows it was
   *parked*, not merged — `reca4ffDtP8QDoFqt` still exists with `Video ID` mangled to
   `oTphk2SVHNc-DUP` so it can't re-collide. See "known base state" in
   `docs/NORMALIZER-MANIFEST.md` for the full list of parked/junk records.)
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
   Note the Airtable API cannot add choices — that is a manual UI step (see the
   `airtable-ui-fallback` skill).

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
normalizer/                # the primary path — Apify -> Airtable, Node, no deps
├── apify-harvest.js       #   CLI: arg guardrails, per-channel ceiling re-check, dry-run
├── audit.js               #   read-only base health check — blank Track, orphans, dupes, stale metrics
├── lib/apify-client.js    #   actor run + dataset fetch
├── lib/srt-parser.js      #   subtitles -> {text, start}
├── lib/transform.js       #   dataset item -> {createOnlyFields, updateFields, channel}
└── lib/airtable-client.js #   upsert by Video ID, find-or-create Channel, listAll* for audit.js
playlist-drain/            # personal -> business playlists + Airtable-verified drain
├── migrate-playlists.js   #   resumable ordered copy; dry-run unless --apply
├── drain-playlists.js     #   removes only transcript-verified business playlist items
├── get-refresh-token.js   #   separate business-write / personal-read OAuth targets
└── playlists.json         #   six source IDs + persisted business destination IDs
docs/TDD-CONTRACT.md       # the one command + the four evidence lines — READ THIS FIRST
docs/NORMALIZER-MANIFEST.md# normalizer design + live verification tables
docs/archive/              # FINDINGS-youtube-automation.md — five months of hard-won facts
.github/workflows/check.yml# CI: runs `npm run check`, no credentials, ever
.claude/skills/            # apify-harvest, diagnose-stuck-automation
```

Playlist migration and the first transcript-verified drain completed live
2026-08-04. Destination IDs, ordered source hashes, source-preservation checks,
and post-drain counts are in `docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md`.

## How work gets done here

One command, from the repo root:

```bash
npm run setup   # once per clone
npm run check   # all suites — chrome-extension, normalizer, then playlist-drain
```

Every change reports four lines of evidence — **RED**, **GREEN**, **REGRESSION**, **LIVE** (or an
explicit "not applicable"). The contract, what LIVE actually requires, and why there is deliberately
no pre-commit hook: `docs/TDD-CONTRACT.md`. GitHub re-runs `npm run check` on every pull request,
with no credentials — so it verifies the first three and never the fourth.

## Skills

- **`diagnose-stuck-automation`** — general Claude-in-Chrome checklist for "the click seems to do
  nothing": coordinate scaling, real-vs-scripted click as a variable, network requests as ground
  truth, tab-throttling and tool-timeout artifacts. Not project-specific; kept.
- **`apify-harvest`** — run a bounded channel sweep through the normalizer and verify the writes
  landed. Encodes the non-negotiables (verify by querying, check Channels didn't fork, never guess
  `Track`, never touch `Triage Status`) and the error playbook.
- **`airtable-ui-fallback`** — drives the Airtable web UI (via browser tools) for the one thing
  the MCP server can't do: adding choices to an existing select field. Use when `update_field`'s
  lack of a `choices` param blocks a write invariant #7 fix. Uses the record-detail modal, not the
  grid, since the grid's canvas rendering is unreliable for precise clicks in an unsupported-browser
  session.
- **`youtube-playlist-ui-technique`** — low-level clicking mechanics for YouTube's video-page "Save
  to..." panel and a Watch Later row's action menu: Save button position, why Escape reverts a
  checkbox instead of just closing the panel, why `find`'s "Selected" state can't be trusted (verify
  via a `zoom` screenshot of the bookmark icon instead), and why the Watch Later action menu often
  needs two clicks. Companion to the (plugin-provided) `watch-later-sort` skill, which owns
  classification/routing, not the mechanics of driving the UI. Learned live 2026-08-05 sorting 21
  Watch Later videos into three business playlists.
- **`harvest-after-sort`** — part 2 of the Watch Later pipeline: runs the normalizer's
  `--video-urls` mode against whichever videos a `watch-later-sort` run just moved into business
  playlists, verifies the Airtable writes by `Video ID`, and reports. Uses `--video-urls`, not
  `--playlist-url` — the latter can't read the business playlists (`unlisted`, confirmed live
  2026-08-06, see `docs/NORMALIZER-MANIFEST.md`). Stops before `playlist-drain` — that stays a
  separate, human-gated step.
- Retired 2026-07-29 along with the browser-automation line: `harvest-playlist`, `verify-panel`,
  `youtube-panel-triage`. `apify-harvest` replaces them.

## Environment

Credentials in `.env` (not committed): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `APIFY_TOKEN`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` (business write), and
`GOOGLE_PERSONAL_READ_REFRESH_TOKEN` (personal read-only). Optional `GOOGLE_PERSONAL_CLIENT_ID` and
`GOOGLE_PERSONAL_CLIENT_SECRET` isolate the personal grant when the shared OAuth client is pinned to
the business channel. The extension reads Airtable credentials
from `chrome.storage.sync`, entered via its Settings page.

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
- **Shared base now has `Ideas` (`tblAE0Rsadl6E1plB`) and `Posts` (`tblf2fmwBUMZZY2LL`) tables**,
  owned by the AIHS refinery / Threads pipeline project (2026-08-03). `docs/NORMALIZER-MANIFEST.md`
  and `normalizer/audit.js` predate both and don't know they exist — don't mistake either table for
  dead schema during exploration, and don't extend `audit.js` to cover them without checking with
  the refinery project first, since their write invariants (draft-only Metricool pushes, never
  auto-publish) live there, not here.

## Dead — do not resurrect

Storyboard generation (ComfyUI, SDXL, IPAdapter), frame capture, `pipeline-server/`, shot list /
scene analysis, and the Python pipeline (`analyzer/`, `publisher/`, `segmenter/`, `comfyui/`,
`templates/`, `tests/`) — all deleted 2026-07-29, recoverable from git history. Also closed: batch
queue logic inside the extension (the harvest config is the queue), the Ctrl+Shift+T shortcut, and
Chrome Web Store publish.

Full list with reasoning: `docs/archive/FINDINGS-youtube-automation.md` §8.
