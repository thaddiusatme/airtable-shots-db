# YouTube Transcript → Airtable

Captures YouTube transcripts and video metadata into Airtable, feeding the AIHS content refinery.

**Status (2026-07-29):** capture is pivoting from browser automation to a hosted scraper (Apify).
The Chrome extension still works and is kept as a manual fallback; it is no longer being developed.

> Formerly a shot-list / storyboard pipeline (ComfyUI, frame capture, scene analysis). All of that was
> removed on 2026-07-29 and is recoverable from git history. See `CLAUDE.md`.

## Layout

```
chrome-extension/    Manifest V3 extension — the manual fallback capture path
docs/archive/        FINDINGS-youtube-automation.md — why capture works the way it does
.claude/skills/      diagnose-stuck-automation
```

## Chrome extension (manual capture)

1. Load unpacked at `chrome://extensions/` → point it at `chrome-extension/`.
2. Open its Settings page and enter your Airtable API key + Base ID (stored in
   `chrome.storage.sync`).
3. Open a YouTube video, click **Extract & Save** in the in-page panel.
4. **Verify the write in Airtable by `Video ID`.** The panel's status is not authoritative — a
   reported error can be a false negative after a successful save.

No build step, vanilla JS. Tests:

```bash
cd chrome-extension && npm test
```

## Apify capture (in progress)

Not built yet. Actor: `streamers/youtube-scraper` (`h7sDV53CddomktSi5`), pay-per-event at
~$0.004/video. A Node normalizer in this repo will map dataset items to Airtable, reusing
`chrome-extension/lib/transcript-utils.js` for GH-64 truncation. Design, guardrails and the write
invariants it must honour are in `CLAUDE.md`.

## Before changing how transcripts are captured

Read `docs/archive/FINDINGS-youtube-automation.md` §1. The YouTube Data API cannot download other
creators' captions, and direct HTTP transcript fetching returns 429 `IpBlocked` from our IP — both
were established empirically here, and the second was accidentally re-proposed months later.

## Environment

`.env` (not committed): `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, and `APIFY_TOKEN` once the normalizer
lands.
