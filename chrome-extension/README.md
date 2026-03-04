# YouTube Transcript → Airtable Chrome Extension

Extract YouTube video transcripts and save them directly to your Airtable database.

## Features

- 📝 Extract transcripts directly from YouTube's web UI (DOM-based, like Glasp)
- 💾 Save to Airtable with one click — creates new records or updates existing ones
- �️ Auto-grabs video thumbnail and links to Channel record
- ⚙️ Settings page for credential management (no DevTools needed)
- 🔗 Test Connection button to verify Airtable credentials
- �🚫 Bypasses IP blocking issues that affect server-side transcript APIs
- 🔒 Uses your authenticated browser session
- ⚡ Fast and lightweight — vanilla JS, no build step

## Installation

### 1. Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-extension` folder
5. Extension should now appear in your toolbar

### 2. Configure Airtable Credentials

1. Click the extension icon in your Chrome toolbar
2. Click **"⚙️ Settings"** at the bottom of the popup
3. Enter your **Airtable API Key** (Personal Access Token starting with `pat`)
4. Enter your **Airtable Base ID** (starts with `app`, found in the Airtable URL)
5. Click **"Save Credentials"**
6. Click **"Test Connection"** to verify everything works

> **Where to find your credentials:**
> - **API Key:** [airtable.com/create/tokens](https://airtable.com/create/tokens) → Create a token with `data.records:read` and `data.records:write` scopes
> - **Base ID:** Open your Airtable base → look at the URL: `airtable.com/appXXXXXXXX/...` — the `app...` part is your Base ID

## Usage

1. Navigate to any YouTube video page
2. Click the extension icon in Chrome toolbar
3. Click **"Extract Transcript"** — the extension auto-opens the transcript panel
4. Preview the transcript in the popup
5. Click **"Save to Airtable"**
6. Done! ✓

**What happens on save:**
- If the video already exists in Airtable → updates it with the transcript
- If the video is new → creates a full record with title, URL, thumbnail, channel link, and transcript
- Channel records are automatically found or created

## Architecture

```
YouTube Video Page
    ↓
Content Script (content.js)
  - Auto-opens transcript panel (5 detection strategies)
  - Extracts transcript segments from DOM
  - Extracts video metadata (title, ID)
  - Extracts channel info (name, ID, URL)
    ↓
Popup (popup.js + popup.html)
  - Shows transcript preview to user
  - Handles save button
    ↓
Airtable API
  - Finds or creates Channel record
  - Finds or creates Video record
  - Saves transcript + thumbnail + channel link

Settings Page (settings.html + settings.js)
  - Manages Airtable credentials (chrome.storage.sync)
  - Test Connection button
  - Format validation
```

## File Structure

```
chrome-extension/
├── manifest.json          # Manifest V3 configuration
├── content.js            # Runs on YouTube pages, extracts transcript + channel info
├── popup.html            # Extension popup UI
├── popup.js              # Popup logic, Airtable save, channel upsert
├── settings.html         # Settings page for credential management
├── settings.js           # Settings logic (save/load/test/clear credentials)
├── icons/                # Extension icons (TODO)
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md             # This file
```

## Troubleshooting

### "Could not find or open transcript panel"

**Solution:** Try manually clicking "Show transcript" on the YouTube page first, then click Extract again.
- Some videos don't have transcripts available
- The extension tries 5 different strategies to auto-open the panel

### "Insufficient permissions to create new select option"

**Solution:** The `Transcript Source` field in Airtable is a Single Select. Add `youtube-web-ui-dom` as an option in the Airtable UI, or add `schema.bases:write` scope to your API token.

### "Please configure Airtable credentials"

**Solution:** Click "⚙️ Settings" in the popup and enter your API Key and Base ID. Use "Test Connection" to verify.

### Extension icon not showing

**Solution:** Pin the extension:
1. Click the puzzle piece icon in Chrome toolbar
2. Find "YouTube Transcript → Airtable"
3. Click the pin icon

## Development

### Testing Changes

1. Make code changes
2. Go to `chrome://extensions/`
3. Click the refresh icon on the extension card
4. Test on a YouTube video page

### Debugging

**Content Script:**
- Open DevTools on YouTube page (F12)
- Check Console tab for logs from `content.js`

**Popup:**
- Right-click extension icon → "Inspect popup"
- Check Console tab for logs from `popup.js`

### DOM Selectors

YouTube's DOM structure changes frequently. If transcript extraction breaks, update selectors in `content.js`:

```javascript
// Current selectors (as of Feb 2026)
const transcriptPanel = document.querySelector('ytd-transcript-renderer');
const segments = transcriptPanel.querySelectorAll('ytd-transcript-segment-renderer');
const textElement = seg.querySelector('.segment-text');
```

Check YouTube's HTML inspector to find new selectors.

## Future Enhancements

- [x] ~~Add proper settings page for credentials~~ (Done — #7)
- [x] ~~Auto-create video records if not in Airtable~~ (Done)
- [x] ~~Grab thumbnails on record creation~~ (Done — #10)
- [x] ~~Link Channel records on save~~ (Done — #11)
- [ ] Create extension icons (16x16, 48x48, 128x128)
- [ ] Full transcript extraction — currently partial (#8)
- [ ] Support multiple languages detection
- [ ] Preserve timestamps (optional structured format)
- [ ] Batch mode — save multiple videos
- [ ] Keyboard shortcut (Ctrl+Shift+T)
- [ ] Progress indicator for long transcripts
- [ ] OAuth flow via Chrome Identity API

## Security Notes

- API credentials stored in `chrome.storage.sync` (encrypted by Chrome)
- HTTPS-only connections to Airtable
- No data sent to third parties
- Credentials never logged or transmitted except to Airtable

## Related

- GitHub Issues:
  - [#6 — Chrome extension implementation](https://github.com/thaddiusatme/airtable-shots-db/issues/6) (core extraction)
  - [#7 — Settings page](https://github.com/thaddiusatme/airtable-shots-db/issues/7) (credential management)
  - [#8 — Full transcript extraction](https://github.com/thaddiusatme/airtable-shots-db/issues/8) (partial transcript bug)
  - [#9 — Transcript Source select field](https://github.com/thaddiusatme/airtable-shots-db/issues/9) (Airtable schema)
  - [#10 — Thumbnail on record creation](https://github.com/thaddiusatme/airtable-shots-db/issues/10)
  - [#11 — Channel linking on record creation](https://github.com/thaddiusatme/airtable-shots-db/issues/11)
- Root cause analysis: `docs/IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md`
- API investigation: `docs/OPTION_C_YOUTUBE_DATA_API_ANALYSIS.md`

## License

Same as parent project.
