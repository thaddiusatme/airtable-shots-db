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

## What exists now

```
normalizer/
├── package.json              — scripts: test, harvest
├── apify-harvest.js           — the CLI entrypoint
└── lib/
    ├── apify-client.js        — runActorSync() against streamers/youtube-scraper
    ├── airtable-client.js     — countQueued, upsertChannel, upsertVideo (find-or-create/upsert)
    ├── transform.js           — Apify dataset item -> Airtable fields
    ├── transform.test.js
    ├── srt-parser.js          — parses Apify's non-standard inline SRT into {text, start}
    ├── srt-parser.test.js
    └── __fixtures__/
        └── qdRw7oHDXJw.srt.txt  — real captured sample, trimmed, used by both test files
```

Run `cd normalizer && npm test` — 14 tests, all passing as of last run. These are pure unit
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

## Verified facts about the Apify actor (streamers/youtube-scraper, h7sDV53CddomktSi5)

Confirmed via two real single-video probe runs (`https://www.youtube.com/watch?v=qdRw7oHDXJw`,
2026-07-29). **Not yet confirmed in channel-sweep mode** — see open items.

- `run-sync-get-dataset-items` endpoint works and returns dataset items directly — no
  run-then-poll-then-fetch-dataset needed for small bounded runs.
- Field mapping used in `transform.js`:
  `id`→Video ID, `title`→Video Title, `url`→Video URL, `thumbnailUrl`→Thumbnail URL/(Image),
  `channelName`→Channel Name, `channelUrl`→Channel URL, `date`→(publish date, not stored;
  used only to verify `oldestPostDate` bounding).

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

## Next step, in order

The original steps 1–3 are **done** — dry-run smoke test, channel-mode probe, first real write, and
the idempotency/invariant-3 re-run all ran live on 2026-07-29. Findings are folded in above.
What remains:

1. **Set `Track` on the new `@WayneStLedger` Channel** (`rec4cdSg0ws368gtK`) — currently blank, so
   its two videos are invisible in the AIHS working view. Needs a human call: `AIHS`,
   `Tooling-watch`, or `Personal`. Neither the CLI nor a future session should guess it.

2. **Track-unset view** — a Channels grid view filtered to blank `Track`. Manual UI step (the
   Airtable MCP has no create-view tool). **29 of 88 Channels have blank `Track`**, so this is
   fixing a live hole, not just guarding future sweeps.

3. Decide how this runs unattended — cron on an always-on machine? A Claude scheduled task? Manual?
   Nothing in `apify-harvest.js` assumes an invocation method. Note the real constraint is not
   capture any more: it's the human review gate downstream (see the queue ceiling, and item 5).

4. Merge `feat/apify-normalizer` into `master`.

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
- Any per-channel config stored in Airtable (`Harvest?`, `Source URL`, `Last harvested` on
  Channels) — the original design doc mentions these but they don't exist yet and
  `apify-harvest.js` takes `--channel-url` on the command line instead. Worth revisiting once
  you're running this against more than one channel at a time.
