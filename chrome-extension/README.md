# YouTube Transcript → Airtable Chrome Extension

Extract YouTube video transcripts and save them directly to your Airtable database with one click.

## Features

- Extract transcripts directly from YouTube's web UI (DOM-based, like Glasp)
- Save to Airtable with one click — creates new records or updates existing ones
- Auto-grabs video thumbnail and links to Channel record
- Settings page for credential management (no DevTools needed)
- Test Connection button to verify Airtable credentials
- Bypasses IP blocking issues that affect server-side transcript APIs
- Uses your authenticated browser session
- Fast and lightweight — vanilla JS, no build step

## Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-extension` folder
5. Extension should now appear in your toolbar

## Setup

1. Click the extension icon in your Chrome toolbar
2. Click **"⚙️ Settings"** at the bottom of the popup
3. Enter your **Airtable API Key** (Personal Access Token starting with `pat`)
4. Enter your **Airtable Base ID** (starts with `app`, found in the Airtable URL)
5. Click **"Save Credentials"**
6. Click **"Test Connection"** to verify everything works

**Where to find your credentials:**
- **API Key:** [airtable.com/create/tokens](https://airtable.com/create/tokens) → Create a token with `data.records:read` and `data.records:write` scopes
- **Base ID:** Open your Airtable base → look at the URL: `airtable.com/appXXXXXXXX/...` — the `app...` part is your Base ID

## Usage

1. Navigate to any YouTube video page
2. Click the extension icon in Chrome toolbar
3. Click **"Extract Transcript"** — the extension auto-opens the transcript panel
4. Preview the transcript in the popup
5. Click **"Save to Airtable"**

**What happens on save:**
- If the video already exists in Airtable → updates it with the transcript
- If the video is new → creates a full record with title, URL, thumbnail, channel link, and transcript

## Architecture

```
YouTube Video Page
    ↓
content.js
  - Auto-opens transcript panel (5 detection strategies)
  - Extracts transcript segments from DOM
  - Extracts video metadata (title, ID)
  - Extracts channel info (name, ID, URL)
    ↓
popup.js
  - Shows transcript preview to user
  - Handles save button
    ↓
Airtable API
  - Finds or creates Channel record
  - Finds or creates Video record
  - Saves transcript + thumbnail + channel link

settings.html / settings.js
  - Manages Airtable credentials (chrome.storage.sync)
  - Test Connection button
```

## File Structure

```
chrome-extension/
├── manifest.json          # Manifest V3 — permissions: activeTab, storage
├── content.js             # Runs on YouTube pages, extracts transcript + channel info
├── popup.html             # Extension popup UI
├── popup.js               # Popup logic, Airtable save, channel upsert
├── settings.html          # Settings page for credential management
├── settings.js            # Settings logic (save/load/test/clear credentials)
├── icons/                 # Extension icons (TODO: create PNGs)
└── README.md              # This file
```

## Troubleshooting

### "Could not find or open transcript panel"

Try manually clicking "Show transcript" on the YouTube page first, then click Extract again. Some videos don't have transcripts available. The extension tries 5 different strategies to auto-open the panel.

### "Insufficient permissions to create new select option"

The `Transcript Source` field in Airtable is a Single Select. Add `youtube-web-ui-dom` as an option in the Airtable UI, or add `schema.bases:write` scope to your API token.

### "Please configure Airtable credentials"

Click "⚙️ Settings" in the popup and enter your API Key and Base ID. Use "Test Connection" to verify.

### DOM selectors breaking

YouTube's DOM structure changes frequently. If transcript extraction breaks, update selectors in `content.js`:

```javascript
// Current selectors (as of Feb 2026)
const transcriptPanel = document.querySelector('ytd-transcript-renderer');
const segments = transcriptPanel.querySelectorAll('ytd-transcript-segment-renderer');
```

Check YouTube's HTML inspector to find new selectors.

## Development

1. Make code changes
2. Go to `chrome://extensions/`
3. Click the refresh icon on the extension card
4. Test on a YouTube video page

**Debugging:**
- Content script: open DevTools on YouTube page (F12) → Console tab
- Popup: right-click extension icon → "Inspect popup" → Console tab

## Open issues

- [ ] Create extension icons (16x16, 48x48, 128x128) — icons/ has placeholder only
- [ ] Full transcript extraction for very long videos (#8)
- [ ] Multi-language detection
- [ ] Batch mode — save multiple videos at once
- [ ] Keyboard shortcut (Ctrl+Shift+T)
- [ ] Timestamps UX — show/hide in popup preview
- [ ] Export as markdown/txt download

## Security

- API credentials stored in `chrome.storage.sync` (encrypted by Chrome)
- HTTPS-only connections to Airtable
- No data sent to third parties
- Credentials never logged or transmitted except to Airtable
