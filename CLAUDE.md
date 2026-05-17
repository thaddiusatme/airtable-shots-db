# CLAUDE.md — Project Manifest

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
├── content.js          # Runs on YouTube pages
│                       # - openTranscriptPanel(): 5 DOM strategies to reveal panel
│                       # - extractTranscript(): pulls segments + metadata + channel info
├── popup.html          # Extension popup UI (transcript-only)
├── popup.js            # - extractTranscript(): sends message to content.js
│                       # - upsertChannel(): find-or-create Channels record
│                       # - saveToAirtable(): creates or updates Videos record
├── settings.html       # Credential management page
├── settings.js         # Save/load/test API key + Base ID via chrome.storage.sync
└── icons/              # TODO: create 16x16, 48x48, 128x128 PNGs
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
- Current selectors target Feb 2026 DOM — check `ytd-transcript-segment-renderer`, `.segment-text`
- Icons directory has placeholder only — real PNGs needed for Chrome Web Store
- Issue #8: full transcript extraction (currently may be partial for very long videos)
- Issue #22: upstream frame/publisher contract mismatch (deprioritized — frame pipeline removed)

## Future direction

- Transcript quality improvements (multi-language detection, full extraction for long videos)
- Timestamps UX (show/hide in popup preview)
- Batch mode (save multiple tabs)
- Keyboard shortcut (Ctrl+Shift+T)
- Possible: export transcript as markdown/txt download

## Environment

Credentials live in `.env` (not committed):
- `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`
- Extension uses `chrome.storage.sync` for credentials (entered via Settings page)

No build step. Vanilla JS. Load unpacked at `chrome://extensions/`.
