---
name: apify-harvest
description: Run a bounded YouTube channel sweep into Airtable via the Apify normalizer, and verify the writes actually landed. Use when asked to harvest, sweep, capture, or backfill transcripts for a channel — "harvest @SomeChannel", "sweep the last N videos", "capture new videos from that channel into Airtable", "backfill transcripts". Also use when a harvest run reported errors and needs diagnosing. Replaces the retired harvest-playlist / verify-panel / youtube-panel-triage skills (the browser-automation capture line is dead — see docs/archive/FINDINGS-youtube-automation.md §1).
---

# Harvest a YouTube channel into Airtable

Runs `normalizer/apify-harvest.js` (Apify `streamers/youtube-scraper` → Airtable Videos). Proven end
to end 2026-07-29; the verification table is in `docs/NORMALIZER-MANIFEST.md`.

**Costs real money** — pay-per-event, roughly $0.004/video. Always dry-run first.

## Run it

```bash
cd normalizer && npm test && node apify-harvest.js \
  --channel-url https://www.youtube.com/@SomeChannel \
  --max-results 5 --oldest-post-date 2026-07-01 --dry-run
```

Drop `--dry-run` only after the printed payload looks right. `--save-raw <path>` dumps the raw
dataset — use it whenever the output shape matters.

`--max-results` and `--oldest-post-date` are **mandatory by design**, dry-run or not. Do not add a
bypass. `oldestPostDate` is verified honored (negative control 2026-07-29), and it accepts relative
values like `"7 days"`.

## Non-negotiables

1. **Never trust the summary — verify by querying.** `created: 2, errors: 0` is not proof. Query
   Videos by `Video ID` and confirm one record each, plus `Triage Status`, `Intake Source`,
   `Transcript Source`, the `Channel` link, and that `Transcript (Timestamped)` parses as JSON.
   Invariant 4 exists because a misread status flag caused a duplicate record on 2026-07-26.
2. **Check Channels didn't fork.** After a run, confirm the channel has exactly **one** row and that
   its `Channel Handle` is `@handle` form. A `UC...`-keyed row means the channel-key logic regressed
   — that bug creates a blank-`Track` orphan and every swept video links to it, invisible in the
   working view. It fails by *succeeding*, so only an explicit check catches it.
3. **A new Channel has blank `Track`.** The CLI warns loudly. Set it by hand — `AIHS`,
   `Tooling-watch`, or `Personal`. **Never guess it**, and never infer it from the channel name.
4. **Never touch `Triage Status` on an existing record.** The CLI already enforces this
   structurally; don't "fix" it by adding the field to `updateFields`. Expect a `Declined` video to
   silently gain a fresh transcript on a re-sweep — that's correct, and worth a human glance.
5. **Adding a new `Transcript Source` value needs an Airtable UI edit.** The API cannot add
   singleSelect choices, and a mismatched value 422s the *entire* record. A dry-run cannot catch it
   — it performs no writes.

## When a run reports errors

Per-item failures are isolated: the run continues and exits non-zero. Read the `[error]` lines.

- **`N records share Video ID '...'`** — a duplicate breaks upsert-by-key. Don't delete anything
  blindly: pull both records and compare, because they may hold *different* data. The 2026-07-29
  case had identical transcripts but disjoint links (25 Shots on one, the Channel link on the
  other), so it was merged and the loser parked as `<id>-DUP`, not deleted.
- **`INVALID_MULTIPLE_CHOICE_OPTIONS`** — a singleSelect value isn't an existing option. Add the
  choice in the UI; do not reach for `typecast`, which silently invents options on a typo.
- **429 / rate limit** — there is no retry/backoff (deliberate, documented non-goal). Airtable caps
  at 5 req/s. Re-run; the upsert is idempotent, so it will update rather than duplicate.
- **Queue ceiling refusal** — working as intended. The bottleneck is the human review gate, not
  capture. Clear the queue instead of raising `--queue-ceiling`.

## Don't

- Don't propose direct HTTP `timedtext` fetching or the YouTube Data API. Both are permanently
  closed; `FINDINGS-youtube-automation.md` §1 records this being re-proposed twice already.
- Don't develop the Chrome extension further. It's a frozen fallback for one-off manual captures.
- Don't widen a failing fixture assertion to make it pass. `__fixtures__/channel-item.json` and the
  SRT tests are the early-warning system for actor output drift — re-verify against a fresh
  `--save-raw` capture first.
