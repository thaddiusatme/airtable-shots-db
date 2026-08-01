# Normalizer Project Manifest — Apify → Airtable

Handoff doc for finishing the Apify capture pivot in a fresh Claude Code session. Read this
first; it links back to `CLAUDE.md` and `docs/archive/FINDINGS-youtube-automation.md` for the
"why" behind decisions already made. This file covers only the normalizer build — capture
architecture and the browser-extension retirement are in the repo `CLAUDE.md`.

**Status as of 2026-07-29 — END TO END PROVEN AGAINST LIVE APIs.** The capture path works
unattended: Apify channel sweep → parsed transcript → Airtable upsert.

Branch `feat/apify-normalizer`. 43 unit tests green. Verified live (not by exit code — by querying
Airtable afterwards, per write invariant 4):

| Check | Result |
|---|---|
| First real write, `--max-results 2` | 2 Videos created, 1 Channel created, 0 errors |
| Records verified by `Video ID` query | 1 record each; `Queued` / `Sweep` / `apify-youtube-scraper` / `en`; both linked to the same Channel |
| Transcripts | 330 and 403 segments, `Transcript (Timestamped)` valid JSON; 11,607 / 15,375 chars — no truncation |
| **Channel key** | exactly **one** `@WayneStLedger` row, keyed `@WayneStLedger`; **zero** UC-keyed rows base-wide — no fork |
| Idempotent re-run | both reported `updated`, not `created`; Videos stayed 91, Channels stayed 88 |
| **Invariant 3** | a hand-set `Declined` **survived** the update; the other stayed `Queued` |
| Duplicates | none, in Videos or Channels |

Three defects were found by checking the live base rather than trusting the inferred contract —
**none were catchable by the 14 unit tests that were passing at the time**:

1. `Transcript Source` had no valid option for Apify, so every write would have 422'd. A dry-run
   cannot catch this (it performs no writes). Now writes `apify-youtube-scraper`.
2. **The channel key was wrong** — see the corrected bullet below. This one fails by *succeeding*.
3. Duplicate keys were resolved by silently taking `records[0]`. Both finders now refuse loudly.

Note for future schema work: **the Airtable API cannot add singleSelect choices.** A
`description`-only PATCH to a field succeeds, the identical PATCH carrying `options.choices` fails
`INVALID_REQUEST_UNKNOWN`. Adding `apify-youtube-scraper` to `Transcript Source` had to be done by
hand in the UI, and it blocked every write until it existed.

## 2026-07-30 — metrics, repurposing fields, and Airtable-driven batch sweeps

Branch `feat/metrics-fields`. 64 unit tests green. The actor returns 45 keys per item and the
normalizer consumed 9; everything metrics- and description-shaped was being paid for and discarded.
That is now mapped, and the harvest config moved into Airtable as originally designed.

**New Videos fields** (all in `updateFields`, so a re-sweep refreshes them — that *is* the metrics
refresh mechanism): `Published At`←`date`, `View Count`←`viewCount`, `Like Count`←`likes`,
`Comment Count`←`commentsCount`, `Duration`←parsed `duration`, `Description`←`text`,
`Description Links`←`descriptionLinks[].url` (deduped, one per line), `Hashtags`←`hashtags`,
`Metrics Captured At`. Plus two Airtable formulas: `Views per Day` (velocity — raw view count only
rewards old videos) and `Engagement Rate %`.

**New Channels fields**: `Subscribers`, `Total Videos`, `Total Views`, `Channel Description`,
`Stats Captured At`, plus the harvest config `Harvest?` / `Source URL` / `Last harvested`.
`upsertChannel` gained an update path so these reach the 88 existing rows, not just new ones.

**`--from-airtable`** sweeps every `Harvest?`-ticked Channel. `--max-results` and
`--oldest-post-date` remain mandatory: batch mode multiplies cost by the channel count, so it needs
*more* bounding, not less.

Verified live by querying Airtable, not by exit codes:

| Check | Result |
|---|---|
| Batch, 5 channels × `--max-results 3` | 12 Videos created, 3 updated, 0 errors |
| New fields on a swept record | `View Count` 11368, `Duration` 836s, `Published At` set, `Views per Day` 11368, `Engagement Rate %` 3.83, hashtags as plain text |
| Channel stats on **existing** rows | all 5 got `Subscribers`/`Total Views`/`Stats Captured At`; `Track` unchanged on every one |
| `Last harvested` | stamped on all 5 (clean sweeps only — a run with errors deliberately leaves it stale) |
| **Queue ceiling in batch** | with `--queue-ceiling 10` against 16 Queued, it halted, named all 5 unswept channels, exit 1, and spent nothing on Apify |
| Duplicates / forks | Videos 94→106, Channels stayed **88**; zero duplicate keys; zero UC-keyed rows |
| **Invariant 3** | `eOebZr3BwSg` stayed `Declined` and `hFlBYtI7q7o` stayed `Done` through metric updates |

Two things worth knowing before touching this again:

- **Formula-field display precision is not settable over the API.** `create_field` returns
  `result.options.precision: 0` and `update_field` accepts only `options.formula`. This is
  *display-only* — verified: the API returns `11.5` and `4.35` for fields formatted to 0 decimals.
  Set the decimals in the Airtable UI if the grid needs them; the stored values are already exact.
- **No actor-supplied value may go into a singleSelect/multipleSelects.** `Hashtags` is the obvious
  trap — it looks like a multi-select, but the values come from the actor, the API cannot add
  choices, and an unseen value 422s the entire record. It is deliberately plain text.

## What exists now

```
normalizer/
├── package.json              — scripts: test, harvest
├── apify-harvest.js           — the CLI entrypoint (single-channel and --from-airtable batch)
├── apify-harvest.test.js
└── lib/
    ├── apify-client.js        — runActorSync() against streamers/youtube-scraper
    ├── airtable-client.js     — countQueued, listHarvestChannels, patchChannel,
    │                            upsertChannel, upsertVideo (find-or-create/upsert)
    ├── airtable-client.test.js
    ├── transform.js           — Apify dataset item -> Airtable fields (+ metrics, channel stats)
    ├── transform.test.js
    ├── srt-parser.js          — parses Apify's non-standard inline SRT into {text, start}
    ├── srt-parser.test.js
    └── __fixtures__/
        ├── qdRw7oHDXJw.srt.txt  — real captured sample, trimmed, used by both test files
        └── channel-item.json    — a real channel-mode dataset item; its KEY SET is the
                                   actor output contract, and the early warning for drift
```

Run `cd normalizer && npm test` — 64 tests, all passing as of 2026-07-30. These are pure unit
tests (fixture-based); they do not touch the network.

`.gitignore` had a blanket `lib/` rule that was silently swallowing `normalizer/lib/` (the same
trap `chrome-extension/lib/` hit once before — see git history). Already fixed: negation lines
added for `normalizer/lib/` alongside the existing `chrome-extension/lib/` ones. Verify with
`git status --porcelain normalizer/` before assuming any new file under `normalizer/lib/` is
tracked-by-default — it will be, but double check if you add a new top-level ignore rule later.

Credentials are in `.env` at repo root (gitignored, not committed): `APIFY_TOKEN`,
`AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`. Already populated — no need to re-request tokens unless
they've since been rotated.

Airtable schema change already applied live (not just in code): `Videos` has a new `Intake
Source` singleSelect field (`fldmKbQYo8YoMWMT4`, options `Watch Later` / `Sweep`) — the guardrail
CLAUDE.md called for, to let triage be stricter on unattended-sweep videos.

## Known base state — don't re-discover these as defects

Confirmed live 2026-07-30 via `node normalizer/audit.js`. The mangled `Video ID` values on the
first two can't collide with a real upsert, so these are documented deliberately, not deleted.

| Record | State |
|---|---|
| `reca4ffDtP8QDoFqt` | tombstone, `Video ID = oTphk2SVHNc-DUP`, `Triage Status = Done` — parked duplicate of `oTphk2SVHNc`, not merged (see CLAUDE.md write invariant 2) |
| `recRYJ0UzWJ3YBrzk` | tombstone, `Video ID = V22VtQ916Y0-DUP-declined`, `Triage Status = Declined` |
| `recLhZak5ARNtgYbE` | completely empty record — no title, no Video ID, no status |
| `recRlmmrTXdGxFNTb` | stub — has `Video ID = 6KktB5aNrjE`, no title, no Triage Status |

The audit also surfaces two *real* Videos with no Channel link — `I4kGV5sJEdA` and `ib74sLgjIBM`,
both `Triage Status = Done`. Not junk (real titles, real status), just orphaned from their Channel
link somehow. Not investigated as part of the 2026-07-30 pass; `audit.js` will keep surfacing them
until fixed or explicitly noted here as accepted.

## Verified facts about the Apify actor (streamers/youtube-scraper, h7sDV53CddomktSi5)

Confirmed via two real single-video probe runs (`https://www.youtube.com/watch?v=qdRw7oHDXJw`,
2026-07-29). **Not yet confirmed in channel-sweep mode** — see open items.

- `run-sync-get-dataset-items` endpoint works and returns dataset items directly — no
  run-then-poll-then-fetch-dataset needed for small bounded runs.
- Field mapping used in `transform.js`:
  `id`→Video ID, `title`→Video Title, `url`→Video URL, `thumbnailUrl`→Thumbnail URL/(Image),
  `channelName`→Channel Name, `channelUrl`→Channel URL, `date`→**`Published At`** (as of
  2026-07-30 this is stored, not just used to verify `oldestPostDate` bounding), plus the metrics
  and channel-stats keys listed in the 2026-07-30 section above.

- ⚠️ **CORRECTED 2026-07-29 — this doc previously had the channel key wrong.** It claimed
  `channelId`→Channel Handle (the `UC...` id) was "confirmed against real output" and "matches how
  the existing Chrome extension already keys Channels." **Both halves were false.** The claim was
  read off `background.js`'s `'Channel Handle': channelData.channelId` without checking what that
  variable holds at runtime: `content.js:233-239` prefers a `UC...` id but falls back to
  `'@' + handle`, and YouTube renders the video-owner link as `/@handle`, so **all 87 existing
  Channel rows are `@handle`** — zero are `UC...`. Keying on Apify's `channelId` therefore never
  matches: every sweep would create a *second* row for an existing channel with blank `Track`, and
  link swept videos to that orphan, invisible in the AIHS working view. It fails by *succeeding*.
  The real key is **`'@' + channelUsername`** (`channelUsername` is `"WayneStLedger"`, no `@`).
  `channelId` is kept only as a lookup fallback. Note `channelUrl` is the **`/channel/UC...`
  form**, so it is useless for deriving the handle — only `channelUsername` works.
- Subtitles are delivered **inline** in the dataset item at `subtitles[0]`, not via a KVS file
  URL — `srtUrl` was `null` in both probes because `saveSubsToKVS: false`. This resolves the
  open question in repo `CLAUDE.md` GH-65: no KVS fetch/retention-expiry handling needed, at
  least not for the volumes this normalizer is scoped to. Worth revisiting only if very long
  videos push the inline payload into some undocumented actor-side size limit — not observed yet.
- `subtitlesFormat: "plaintext"` returns one continuous blob with **no per-cue timing** — useless
  for `Transcript (Timestamped)`. Must request `subtitlesFormat: "srt"` (what `apify-harvest.js`
  does).
- The SRT `subtitles[0].srt` field is **not standard SRT**:
  1. Timestamp fields aren't zero-padded (`00:04:2,560`, not `00:04:02,560`). A standard SRT
     parser/regex expecting exactly 2 digits per field will misparse these lines.
  2. Every real caption cue is immediately followed (or, at the very end of the transcript,
     sometimes preceded) by a near-duplicate "shadow" cue whose text is a single space — an
     artifact of YouTube's rolling auto-captions. Naively parsing every SRT block doubles segment
     count with blank entries.

  `srt-parser.js` handles both; `srt-parser.test.js` encodes these as regression tests against
  the real fixture. **If a future Apify actor version changes the SRT shape, these tests are the
  early-warning system — don't just widen them to pass, re-verify against a fresh real sample
  first.**
- Real actor **input** keys, now confirmed against the published input schema and two channel-mode
  runs: `startUrls`, `maxResults`, `maxResultsShorts`, `maxResultStreams`, `downloadSubtitles`,
  `subtitlesFormat`, `subtitlesLanguage`, `preferAutoGeneratedSubtitles` (**not**
  `preferAutoGenerated`, which is what repo `CLAUDE.md` still said), `saveSubsToKVS`,
  `oldestPostDate`, `dateFilter`, `videoType`, `sortVideosBy`, plus boolean content filters
  (`hasCC`, `is360`, `is4K`, `isHD`, …). The earlier note that `oldestPostDate`/`subtitlesLanguage`
  were "not observed" was an artifact of both probes being single-video runs — they are real.

- **`oldestPostDate` is honored, not merely accepted** (verified 2026-07-29). Documented as "only
  posts uploaded after or on this date"; also accepts a relative value like `"7 days"`. Negative
  control: the same call bounded at `2026-07-29` returned **1** item instead of 2, excluding the
  `2026-07-28` video. This is the class of control the archived findings doc records as having been
  skipped once before, so it was run deliberately. An accepted-but-ignored field is
  indistinguishable from a working one until `maxResults` is raised.

- Observed **output** shape (channel mode, 45 keys — pinned verbatim in
  `normalizer/lib/__fixtures__/channel-item.json`): publish date is **`date`** (ISO 8601);
  `channelUsername` is the bare handle (`"WayneStLedger"`); `channelUrl` is the **`/channel/UC...`
  form**; **there is no `hasSubtitles` key at all**; subtitles arrive inline at `subtitles[0].srt`
  (35k–44k chars observed) with `srtUrl` unused.

## What `apify-harvest.js` already enforces

- `--max-results` and `--oldest-post-date` are both mandatory CLI args, dry-run or not (guardrail:
  no unbounded channel pulls).
- Queue-depth ceiling: queries live `Triage Status = Queued` count before running anything;
  refuses to proceed if at/above `--queue-ceiling` (default 30). Rationale is in repo
  `CLAUDE.md` — the refinery's bottleneck is the human review gate, not capture, so an unbounded
  automated feed just piles up unreviewed ore.
- `--dry-run` performs every read (Apify call, Airtable existence lookups) but zero writes, and
  prints the exact fields it would have written.
- Upsert-by-Video-ID, Channel find-or-create by `Channel Handle` (= `'@' + channelUsername`, with
  the `UC...` id tried as a fallback), and "never touch Triage Status on update" are all lifted
  directly from `chrome-extension/background.js` — intentionally the same invariants, not reinvented.
- **Duplicate-key refusal**: both finders throw and name the colliding record ids rather than
  silently writing to `records[0]` (write invariant 2). The base had exactly this condition on
  `Video ID oTphk2SVHNc` until it was merged on 2026-07-29.
- **Per-item error isolation**: one failed video logs `[error]` and the sweep continues, with a
  non-zero exit at the end. Previously one Airtable hiccup abandoned the run mid-way with earlier
  items already written.
- **Channel lookup is cached per run** — a sweep is one channel, so re-querying it per video just
  burned requests against Airtable's 5 req/s cap (there is still no retry/backoff).
- New-Channel creation logs a loud warning (`[channel] created "..." with NO Track set...`)
  because a Track-less Channel silently disappears from the AIHS working view
  (`Track = AIHS OR Tooling-watch`). The CLI surfaces this; it does not (and shouldn't) guess a
  Track value.

## 2026-07-30 — `--playlist-url` mode

Added to reconnect the Watch Later → playlist → Airtable leg documented as broken in `CLAUDE.md`
"Active work": the browser-extension playlist harvest (`harvest-playlist`, `scheduled-playlist-harvest`)
was the thing that actually drained `AI (Claude)` / `AI` / `Business & Productivity` into Airtable, and
it went dark when the extension was frozen 2026-07-29 in favor of this (channel-only) normalizer.

No new data path — a playlist is a third value for the same "channel selection" input already in
`resolveChannels()`/`sweepChannel()`. Two facts made this a small change rather than a redesign:

- The actor's `startUrls` field accepts a playlist URL
  (`https://www.youtube.com/playlist?list=...`) exactly like a channel URL — confirmed against the
  published input schema at `apify.com/streamers/youtube-scraper/input-schema`, 2026-07-30. Not
  previously probed against a live playlist run (see LIVE gap below).
- `transform.js`'s `buildVideoFields()` already derives each item's Channel from the dataset item's
  own `channelUsername`/`channelUrl` (`toHandleKey()`), never from the input URL. A playlist can span
  many channels; `sweepChannel()`'s per-run `channelCache` already keys by that derived handle, so
  each distinct channel in a playlist's results resolves/creates correctly with zero changes below
  `resolveChannels()`.

`--channel-url`, `--playlist-url`, and `--from-airtable` are now mutually exclusive
channel-selection inputs (`validateArgs` in `apify-harvest.js`), each requiring the same
`--max-results`/`--oldest-post-date` bounds. Playlist mode always has `recordId: null` (there's no
Channels-table row for a playlist), so it never stamps `Last harvested` — same behavior as a one-off
`--channel-url` run.

**Not yet wired into `--from-airtable`.** The three AIHS-relevant playlists aren't Channels rows, so
batch mode can't pick them up automatically yet — this is a manual one-off command for now, the same
tier as `--channel-url`. If the cadence turns out to want it automated, the natural next step is a
separate "Harvest playlists" config surface (a new small table, or an `Intake Source = Watch Later`
convention read from somewhere), not folding playlists into the Channels table.

**LIVE — not applicable.** Playlist mode is unit-tested (`validateArgs`'s three-way mutual exclusion,
`resolveChannels()` with `recordId: null`, and the reasoning that `transform.js` derives Channel per
dataset item) but has not been run against a live playlist. No Apify run ID or Airtable record ID
exists to cite for it. Run it live before claiming otherwise.

## Next step, in order

The original steps 1–3 are **done** — dry-run smoke test, channel-mode probe, first real write, and
the idempotency/invariant-3 re-run all ran live on 2026-07-29. Findings are folded in above.
What remains:

1. ~~Set `Track` on `@WayneStLedger`~~ — **done**, it is `Tooling-watch` as of 2026-07-30.

2. **Track-unset view** — a Channels grid view filtered to blank `Track`. Manual UI step (the
   Airtable MCP has no create-view tool). Now **4 of 88 Channels** have blank `Track`
   (`@Jasper_Tech`, `@BulbDigital`, `@3.7Million`, `@WizardsandWarriors`) — down from 29, but the
   view is still worth having, because a blank-`Track` channel fails by vanishing silently.

3. Decide how this runs unattended — cron on an always-on machine? A Claude scheduled task? Manual?
   Nothing in `apify-harvest.js` assumes an invocation method, and `--from-airtable` now makes an
   unattended invocation a single command with no channel list baked into it. Note the real
   constraint is not capture any more: it's the human review gate downstream (see the queue
   ceiling, and item 5).

4. ~~Merge `feat/apify-normalizer`~~ — **done** (`3a878d1`). ~~Merge `feat/metrics-fields`~~ — **done**
   (PR #69, `ce91b57`). Work since the merge lives on `feat/tdd-ci`: a TDD contract + CI check
   (`349c84b`) and the `normalizer/audit.js` command (2026-07-30, this session).

5. Not this normalizer's job, but adjacent and worth remembering: the receiving-end refinery
   (`~/claude/Youtube Transcripts`) still has its own gate closed — "Still gated until treatment
   quality is proven." Getting capture working doesn't change that; if anything it raises the
   volume hitting an already-throttled human review step. Don't let capture velocity outrun triage
   capacity — that queue-ceiling check in step 2 above is the mechanical version of that same
   discipline.

## Non-goals / explicitly deferred

- Retry/backoff on transient Apify or Airtable failures — none implemented. A failed run today
  just exits non-zero; whatever partially wrote, wrote (each item's write is independent, so
  partial progress isn't corrupt, just incomplete).
- Shorts/streams (`maxResultsShorts`, `maxResultStreams`) — not wired up. Only `maxResults`
  (regular videos) is passed today.
- ~~Per-channel config stored in Airtable~~ — **shipped 2026-07-30.** `Harvest?`, `Source URL` and
  `Last harvested` exist on Channels and drive `--from-airtable`. `--channel-url` remains for
  one-off runs.
- **Metrics history.** Metrics are overwritten in place with a `Metrics Captured At` stamp, so
  trend data is not recoverable after the fact — you can see what a video's velocity is *now*, not
  what it was last week. A snapshot table is the upgrade path if "is this angle gaining?" ever
  becomes a question worth answering; it was deliberately not built.
- **Backfilling the extension-captured videos.** Videos captured before the sweep window stay
  metric-less. Note this partially self-heals: a re-swept channel updates any of its videos that
  still fall inside `--oldest-post-date`, which is how `hFlBYtI7q7o` (a `Done` record from
  2026-07-11) gained metrics without being re-created.
