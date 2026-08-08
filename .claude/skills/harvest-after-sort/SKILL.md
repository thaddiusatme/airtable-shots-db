---
name: harvest-after-sort
description: Run the normalizer's --video-urls harvest for the specific videos a watch-later-sort run just moved into business playlists, then verify the Airtable writes and report per-playlist counts. This is "part 2" of the Watch Later capture pipeline — watch-later-sort routes videos into business playlists; this skill captures them into Airtable Videos as Queued. Use right after a watch-later-sort run reports "Business playlists touched", or when asked to "harvest what we just sorted", "capture the newly sorted videos", or "run the next part" following a sort. Does not run playlist-drain or touch Triage Status — those stay separate, human-gated steps.
---

# Harvest newly-sorted videos into Airtable

Second half of the Watch Later pipeline described in `CLAUDE.md` under "Active work — business-owned
intake playlists": `watch-later-sort` (browser automation, personal account) decides where each
video belongs and moves it; this skill (normalizer, no browser) pulls transcripts and metadata for
whatever landed there into Airtable.

## Use `--video-urls`, not `--playlist-url`

**`--playlist-url` does not work against the business playlists.** Confirmed live 2026-08-06: the
Apify `streamers/youtube-scraper` actor returns `NO_VIDEOS` for `unlisted` playlists, and all six
business intake playlists are unlisted by design (`docs/PLAYLIST-MIGRATION-LIVE-2026-08-04.md`). A
plain unauthenticated fetch of the same playlist URL returns the video data fine — it's specifically
the actor's scrape path that can't see unlisted content. Full writeup:
`docs/NORMALIZER-MANIFEST.md`.

**`--video-urls` is the working path**, added the same day specifically to route around this. It
feeds the individual video watch URLs directly into the actor's `startUrls` — sidestepping the
playlist's privacy status entirely, since the videos themselves aren't unlisted, only the playlist
grouping them is. This isn't a lesser workaround: per `lib/apify-client.js`'s header comment, a
single-video `startUrls` run is the actor's **original, most-verified** input shape (2026-07-29
probe), more so than either channel or playlist mode.

## Inputs this skill needs

From the watch-later-sort report (or by reading the touched playlists' video lists directly if the
report isn't in context): the exact watch URLs (`https://www.youtube.com/watch?v=<ID>`) of the
videos that were just added. Not the playlist URL — the individual video URLs.

## Steps

1. **Collect the watch URLs** for every video the sort just moved, across however many business
   playlists were touched — one `--video-urls` call can span multiple playlists' worth of videos in
   a single actor run, since Channel is derived per dataset item regardless of which playlist (if
   any) a video came from.

2. **Run one harvest** from `normalizer/`:

   ```bash
   cd normalizer && node apify-harvest.js \
     --video-urls "https://www.youtube.com/watch?v=ID1,https://www.youtube.com/watch?v=ID2,..." \
     --max-results <n, equal to the exact URL count> \
     --oldest-post-date <generous date, e.g. 2015-01-01 — not a tight window>
   ```

   `--max-results` and `--oldest-post-date` are mandatory by design (same guardrail as every other
   normalizer mode). For `--video-urls` specifically, `--max-results` must be **at least** the
   number of URLs given — the CLI refuses a lower value itself, because unlike the cost-guardrail
   role it plays elsewhere, here a too-low cap would silently drop one of the exact videos named,
   not just bound cost.

3. **This costs real money** (pay-per-event Apify pricing) — same caveat as `apify-harvest`. A
   `--dry-run` still runs the actor and costs the same; use it only to sanity-check the payload
   shape (e.g. a small canary before a large batch), never as a free check.

4. **Verify every write by `Video ID`** in Airtable — never trust the run's printed summary alone.
   For each newly captured video confirm:
   - Exactly one Videos record matches the `Video ID`.
   - `Transcript (Full)` is nonblank or `Transcript (Timestamped)` parses as a nonempty JSON array.
   - `Channel` is linked to an `@handle`-keyed row, not a forked `channelId`-keyed orphan (see the
     Channels-keying write invariant in `CLAUDE.md`).
   - `Triage Status` is `Queued` (set on create only — never touched on update).

5. **Report per playlist**: videos captured, videos skipped and why (duplicate `Video ID`, missing
   transcript, blank-`Track` channel), and any channel that got created with blank `Track` (flag it,
   don't guess a value — human-owned routing per write invariant #3).

6. **Stop here.** Do not run `playlist-drain` and do not set `Triage Status` on anything. Removing
   now-captured videos from the business playlists is a separate, explicitly human-gated step
   (`npm run drain --prefix playlist-drain`, dry-run first, `--apply` only on a further go-ahead) —
   offer it as the next step rather than rolling it into this one.

## Why this exists as its own skill rather than folding into `apify-harvest`

`apify-harvest` covers `--channel-url` and `--from-airtable` batch mode; `--playlist-url` and
`--video-urls` are newer channel-selection modes (added 2026-07-30 and 2026-08-06 respectively,
specifically to reconnect the Watch-Later-sort capture leg) that aren't wired into `--from-airtable`
and remain manual, one-off invocations per `CLAUDE.md`. This skill exists to make that manual step a
reliable, repeatable procedure keyed to "whatever a sort run just touched," rather than something
reconstructed from memory each time — including remembering which of the two modes actually works.
