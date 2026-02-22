# YouTube Transcript → Airtable Chrome Extension

Extract YouTube video transcripts and save them directly to your Airtable database.

## Features

- 📝 Extract transcripts directly from YouTube's web UI
- 💾 Save to Airtable with one click
- 🚫 Bypasses IP blocking issues
- 🔒 Uses your authenticated browser session
- ⚡ Fast and lightweight

## Installation

### 1. Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-extension` folder
5. Extension should now appear in your toolbar

### 2. Configure Airtable Credentials

For now, set credentials via Chrome DevTools console:

1. Right-click the extension icon → "Inspect popup"
2. In the Console tab, run:

```javascript
chrome.storage.sync.set({
  airtableApiKey: "YOUR_AIRTABLE_API_KEY",
  airtableBaseId: "YOUR_AIRTABLE_BASE_ID"
});
```

Replace with your actual credentials from `.env` file.

**TODO:** Add proper settings page in future version.

## Usage

### Step 1: Import Video (CLI)

First, make sure the video is already in Airtable:

```bash
cd /path/to/airtable-shots-db
python import_watch_later.py --max-items 1
```

### Step 2: Open Video on YouTube

1. Navigate to the YouTube video
2. Click the **Show transcript** button (three dots menu)
3. Transcript panel should appear on the right side

### Step 3: Extract & Save

1. Click the extension icon in Chrome toolbar
2. Click **"Extract Transcript"**
3. Preview the transcript in the popup
4. Click **"Save to Airtable"**
5. Done! ✓

## Architecture

```
YouTube Video Page
    ↓
Content Script (content.js)
  - Extracts transcript from DOM
  - Gets video metadata
    ↓
Popup (popup.js + popup.html)
  - Shows preview to user
  - Handles save button
    ↓
Airtable API
  - Finds video by Video ID
  - Updates transcript fields
```

## File Structure

```
chrome-extension/
├── manifest.json          # Extension configuration
├── content.js            # Runs on YouTube pages, extracts transcript
├── popup.html            # Extension popup UI
├── popup.js              # Popup logic and Airtable integration
├── icons/                # Extension icons (TODO)
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md             # This file
```

## Troubleshooting

### "Transcript not available"

**Solution:** Make sure the transcript panel is open on YouTube before clicking Extract.
- Look for the "Show transcript" button (three dots menu)
- Some videos don't have transcripts

### "Video not found in Airtable"

**Solution:** Import the video first using the CLI:

```bash
python import_watch_later.py --playlist-id "YOUR_PLAYLIST_ID" --max-items 1
```

### "Please configure Airtable credentials"

**Solution:** Set credentials via DevTools console (see Installation step 2 above).

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

- [ ] Add proper settings page for credentials
- [ ] Create extension icons (16x16, 48x48, 128x128)
- [ ] Auto-detect when transcript panel is opened
- [ ] Support multiple languages detection
- [ ] Preserve timestamps (optional structured format)
- [ ] Batch mode - save multiple videos
- [ ] Keyboard shortcut (Ctrl+Shift+T)
- [ ] Better error messages with recovery suggestions
- [ ] Progress indicator for long transcripts

## Security Notes

- API credentials stored in `chrome.storage.sync` (encrypted by Chrome)
- HTTPS-only connections to Airtable
- No data sent to third parties
- Credentials never logged or transmitted except to Airtable

## Related

- GitHub Issue: [#6 - Implement Chrome Extension-based Transcript Fetching](https://github.com/thaddiusatme/airtable-shots-db/issues/6)
- Root cause analysis: `docs/IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md`
- API investigation: `docs/OPTION_C_YOUTUBE_DATA_API_ANALYSIS.md`

## License

Same as parent project.
