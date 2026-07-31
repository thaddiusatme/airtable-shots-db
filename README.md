# YouTube Transcript → Airtable

Captures YouTube transcripts and video metadata into Airtable, feeding the AIHS content refinery.

**Status (2026-07-30):** the pivot from browser automation to a hosted scraper is complete. The Apify
normalizer is the primary capture path, proven end to end 2026-07-29 and extended to metrics and
batch sweeps 2026-07-30. The Chrome extension still works and is kept as a manual fallback; it is no
longer being developed.

> Formerly a shot-list / storyboard pipeline (ComfyUI, frame capture, scene analysis). All of that was
> removed on 2026-07-29 and is recoverable from git history. See `CLAUDE.md`.

## Layout

```
normalizer/          Apify → Airtable normalizer (Node, no deps) — the primary capture path
chrome-extension/    Manifest V3 extension — the manual fallback capture path
docs/TDD-CONTRACT.md One command, four lines of evidence — read before changing anything
docs/NORMALIZER-MANIFEST.md  normalizer design + live verification tables
docs/archive/        FINDINGS-youtube-automation.md — why capture works the way it does
.github/workflows/   check.yml — runs `npm run check`, no credentials
.claude/skills/      apify-harvest, diagnose-stuck-automation
```

## Development

One command, from the repo root:

```bash
npm run setup
```

```bash
npm run check
```

`setup` runs once per clone (it installs `jsdom`, the extension suite's only dependency). `check`
runs both suites — `chrome-extension` then `normalizer` — and is what GitHub re-runs on every pull
request.

Every change reports **RED / GREEN / REGRESSION / LIVE** evidence in its pull request. See
[docs/TDD-CONTRACT.md](docs/TDD-CONTRACT.md) for what each means, when LIVE is legitimately "not
applicable", and why there is deliberately no pre-commit hook.

## Apify capture (primary)

Actor: `streamers/youtube-scraper` (`h7sDV53CddomktSi5`), pay-per-event at ~$0.004/video. The Node
normalizer maps dataset items to Airtable, reusing `chrome-extension/lib/transcript-utils.js` for
GH-64 truncation.

One channel:

```bash
cd normalizer && node apify-harvest.js --channel-url https://www.youtube.com/@SomeChannel --max-results 5 --oldest-post-date 2026-07-01 --dry-run
```

Every channel with `Harvest?` ticked in Airtable, using each row's `Source URL`:

```bash
cd normalizer && node apify-harvest.js --from-airtable --max-results 5 --oldest-post-date "30 days"
```

`--max-results` and `--oldest-post-date` are **mandatory in both modes**, dry-run or not — batch
multiplies the cost by the channel count. Note a `--dry-run` still runs the actor and still costs the
same; it is for checking the payload, not for saving money.

Design, guardrails, the write invariants it must honour, and the live verification tables:
`CLAUDE.md` and [docs/NORMALIZER-MANIFEST.md](docs/NORMALIZER-MANIFEST.md).

## Chrome extension (manual fallback)

1. Load unpacked at `chrome://extensions/` → point it at `chrome-extension/`.
2. Open its Settings page and enter your Airtable API key + Base ID (stored in
   `chrome.storage.sync`).
3. Open a YouTube video, click **Extract & Save** in the in-page panel.
4. **Verify the write in Airtable by `Video ID`.** The panel's status is not authoritative — a
   reported error can be a false negative after a successful save.

No build step, vanilla JS.

## Before changing how transcripts are captured

Read `docs/archive/FINDINGS-youtube-automation.md` §1. The YouTube Data API cannot download other
creators' captions, and direct HTTP transcript fetching returns 429 `IpBlocked` from our IP — both
were established empirically here, and the second was accidentally re-proposed months later.

## Environment

`.env` (not committed): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `APIFY_TOKEN`. CI needs none of
these and is never given them.
