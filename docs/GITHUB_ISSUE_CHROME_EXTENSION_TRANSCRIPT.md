# GitHub Issue: Chrome Extension → Airtable Transcript Integration

**Title:** Implement Chrome Extension-based Transcript Fetching for YouTube Videos

**Labels:** `enhancement`, `transcript-feature`, `chrome-extension`, `integration`

**Priority:** P0 - Critical Path Alternative

---

## Problem Statement

The `youtube-transcript-api` library faces persistent IP blocking (HTTP 429) from YouTube when fetching transcript content, making it unreliable for production use. Proxies are costly ($15-50/month) and add complexity.

**Current blockers:**
- ❌ youtube-transcript-api: 100% IpBlocked during fetch
- ❌ YouTube Data API: Only works for videos you own (incompatible with Watch Later imports)
- ⚠️ Proxy solutions: Recurring costs + setup complexity

## Proposed Solution

**Use a Chrome extension to extract transcripts directly from YouTube's web UI**, leveraging the user's authenticated browser session, then send transcript data to Airtable.

### Architecture Overview

```
┌─────────────────┐
│   YouTube       │
│   Video Page    │
│   (Web UI)      │
└────────┬────────┘
         │
         │ User watches video
         │ Transcript visible in UI
         │
         ▼
┌─────────────────────────┐
│  Chrome Extension       │
│  - Content Script       │
│  - Extract transcript   │
│  - Format data          │
└────────┬────────────────┘
         │
         │ Option A: Direct API call
         │ Option B: Send to local CLI
         │
         ▼
┌─────────────────────────┐
│  Airtable Videos Table  │
│  - Update existing      │
│  - Add transcript data  │
└─────────────────────────┘
```

### Key Benefits

✅ **Bypasses IP blocking** - Uses user's own browser session  
✅ **No proxy costs** - Leverages existing authentication  
✅ **Simple UX** - User is already on YouTube watching videos  
✅ **Reliable** - No scraping detection issues  
✅ **Free** - No recurring service costs

---

## Implementation Details

### Phase 1: Chrome Extension (Manual Trigger)

**User workflow:**
1. User watches YouTube video from Watch Later
2. Transcript panel is visible on page
3. User clicks extension icon → "Save Transcript to Airtable"
4. Extension extracts transcript + metadata
5. Extension sends data to Airtable
6. User sees confirmation notification

**Extension components:**

```javascript
// manifest.json
{
  "manifest_version": 3,
  "name": "YouTube Transcript → Airtable",
  "version": "1.0.0",
  "permissions": [
    "activeTab",
    "storage"
  ],
  "host_permissions": [
    "https://www.youtube.com/*"
  ],
  "content_scripts": [
    {
      "matches": ["https://www.youtube.com/watch*"],
      "js": ["content.js"]
    }
  ],
  "action": {
    "default_popup": "popup.html",
    "default_icon": "icon.png"
  }
}
```

```javascript
// content.js - Extract transcript from YouTube page
function extractTranscript() {
  // YouTube transcript selector (may need updating)
  const transcriptPanel = document.querySelector('ytd-transcript-renderer');
  
  if (!transcriptPanel) {
    return { error: 'Transcript not available' };
  }
  
  // Extract all transcript segments
  const segments = transcriptPanel.querySelectorAll(
    'ytd-transcript-segment-renderer'
  );
  
  const transcriptText = Array.from(segments)
    .map(seg => seg.querySelector('.segment-text')?.textContent)
    .filter(Boolean)
    .join(' ');
  
  // Extract video metadata
  const videoId = new URLSearchParams(window.location.search).get('v');
  const videoTitle = document.querySelector('h1.ytd-video-primary-info-renderer')?.textContent?.trim();
  
  return {
    videoId,
    videoTitle,
    transcript: transcriptText,
    language: 'en', // TODO: detect from UI
    source: 'youtube-web-ui',
    fetchedAt: new Date().toISOString()
  };
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractTranscript') {
    const data = extractTranscript();
    sendResponse(data);
  }
});
```

```javascript
// popup.js - Send to Airtable
async function saveToAirtable(transcriptData) {
  const AIRTABLE_API_KEY = await getStoredApiKey();
  const AIRTABLE_BASE_ID = await getStoredBaseId();
  
  // Find existing video record by Video ID
  const findUrl = `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/Videos?filterByFormula=` +
    encodeURIComponent(`{Video ID}='${transcriptData.videoId}'`);
  
  const findResponse = await fetch(findUrl, {
    headers: {
      'Authorization': `Bearer ${AIRTABLE_API_KEY}`
    }
  });
  
  const findResult = await findResponse.json();
  
  if (findResult.records.length === 0) {
    showError('Video not found in Airtable. Import video first.');
    return;
  }
  
  const recordId = findResult.records[0].id;
  
  // Update record with transcript
  const updateUrl = `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/Videos/${recordId}`;
  
  const updateResponse = await fetch(updateUrl, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${AIRTABLE_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      fields: {
        'Transcript (Full)': transcriptData.transcript,
        'Transcript Language': transcriptData.language,
        'Transcript Source': transcriptData.source
      }
    })
  });
  
  if (updateResponse.ok) {
    showSuccess('Transcript saved to Airtable!');
  } else {
    const error = await updateResponse.json();
    showError(`Failed to save: ${error.error.message}`);
  }
}

// Popup button click handler
document.getElementById('saveBtn').addEventListener('click', async () => {
  // Get data from content script
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  chrome.tabs.sendMessage(tab.id, { action: 'extractTranscript' }, async (response) => {
    if (response.error) {
      showError(response.error);
      return;
    }
    
    await saveToAirtable(response);
  });
});
```

---

### Phase 2: CLI Integration (Optional)

**Alternative architecture:** Extension → Local CLI → Airtable

**Benefits:**
- Reuses existing Python codebase
- Better error handling
- Logging and monitoring
- Batch operations

**Implementation:**

```bash
# CLI command to receive transcript from extension
python import_watch_later.py transcript-from-extension \
  --video-id "VIDEO_ID" \
  --transcript-file /tmp/transcript.json
```

```python
# import_watch_later.py - Add new command
def handle_transcript_from_extension(video_id: str, transcript_file: str):
    """
    Handle transcript data sent from Chrome extension.
    """
    import json
    
    with open(transcript_file, 'r') as f:
        data = json.load(f)
    
    # Find existing video record
    existing = airtable_find_first(
        videos_table,
        f"AND({{Platform}}='YouTube', {{Video ID}}='{video_id}')"
    )
    
    if not existing:
        print(f"Error: Video {video_id} not found in Airtable")
        return 1
    
    # Update with transcript
    videos_table.update(
        existing['id'],
        {
            'Transcript (Full)': data['transcript'],
            'Transcript Language': data.get('language', 'en'),
            'Transcript Source': 'chrome-extension-web-ui'
        }
    )
    
    print(f"✓ Updated transcript for {video_id}")
    return 0
```

**Extension modification:**

```javascript
// popup.js - Call local CLI instead of direct API
async function saveViaLocalCLI(transcriptData) {
  // Write transcript to temp file
  const tempFile = '/tmp/transcript_' + transcriptData.videoId + '.json';
  
  // Use Native Messaging to call CLI
  const response = await chrome.runtime.sendNativeMessage(
    'com.yourapp.transcript_importer',
    {
      command: 'save_transcript',
      videoId: transcriptData.videoId,
      data: transcriptData
    }
  );
  
  if (response.success) {
    showSuccess('Transcript saved via CLI!');
  } else {
    showError(response.error);
  }
}
```

---

### Phase 3: Automation (Future Enhancement)

**Auto-detect and save transcripts:**
- Extension monitors YouTube tab
- When video is watched, automatically extract transcript
- Queue for background sync to Airtable
- Reduce manual clicks

**Implementation considerations:**
- Rate limiting (don't spam Airtable API)
- User preference (opt-in/opt-out)
- Conflict resolution (don't overwrite existing transcripts)

---

## Data Flow

### Extension → Airtable Direct

```
1. User on YouTube video page
2. User clicks extension icon
3. Extension content script:
   - Queries DOM for transcript panel
   - Extracts transcript segments
   - Combines into full text
   - Gets video ID from URL
4. Extension popup:
   - Displays preview
   - User confirms "Save"
5. Extension background:
   - Finds Airtable record by Video ID
   - PATCH request to update transcript fields
6. User sees success notification
```

### Extension → CLI → Airtable

```
1. User on YouTube video page
2. User clicks extension icon
3. Extension extracts transcript
4. Extension writes JSON to temp file
5. Extension calls native CLI via Chrome Native Messaging
6. CLI reads JSON file
7. CLI uses existing airtable logic to update
8. CLI returns success/error to extension
9. Extension shows notification
```

---

## Required Changes to Existing Codebase

### New CLI Command

```python
# import_watch_later.py

def main():
    parser = argparse.ArgumentParser(...)
    subparsers = parser.add_subparsers(dest='command')
    
    # Existing: import videos from YouTube
    import_parser = subparsers.add_parser('import')
    import_parser.add_argument('--max-items', ...)
    # ... existing args
    
    # NEW: Handle transcript from extension
    transcript_parser = subparsers.add_parser('transcript-from-extension')
    transcript_parser.add_argument('--video-id', required=True)
    transcript_parser.add_argument('--transcript', required=True, 
                                    help='Transcript text')
    transcript_parser.add_argument('--language', default='en')
    
    args = parser.parse_args()
    
    if args.command == 'transcript-from-extension':
        return handle_transcript_from_extension(
            video_id=args.video_id,
            transcript=args.transcript,
            language=args.language
        )
    else:
        # Existing import logic
        ...
```

### New Helper Function

```python
def handle_transcript_from_extension(
    video_id: str,
    transcript: str,
    language: str = 'en'
) -> int:
    """
    Update Airtable video record with transcript from Chrome extension.
    
    Returns:
        0 on success, 1 on error
    """
    airtable_api_key = os.getenv("AIRTABLE_API_KEY")
    airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
    
    if not airtable_api_key or not airtable_base_id:
        print("Error: AIRTABLE_API_KEY and AIRTABLE_BASE_ID required")
        return 1
    
    api = Api(airtable_api_key)
    base = api.base(airtable_base_id)
    videos_table = base.table("Videos")
    
    # Find video by Video ID
    existing = airtable_find_first(
        videos_table,
        f"AND({{Platform}}='YouTube', {{Video ID}}='{video_id}')"
    )
    
    if not existing:
        print(f"Error: Video {video_id} not found in Airtable")
        print("Please import the video first using: python import_watch_later.py")
        return 1
    
    # Update with transcript
    try:
        videos_table.update(
            existing['id'],
            {
                'Transcript (Full)': transcript,
                'Transcript Language': language,
                'Transcript Source': 'chrome-extension-web-ui'
            }
        )
        print(f"✓ Successfully updated transcript for: {existing['fields'].get('Video Title', video_id)}")
        return 0
    except Exception as e:
        print(f"Error updating Airtable: {e}")
        return 1
```

---

## Testing Plan

### Manual Testing

1. **Extension Installation**
   - Load unpacked extension in Chrome
   - Verify permissions requested
   - Configure Airtable API credentials in extension settings

2. **Transcript Extraction**
   - Navigate to YouTube video with transcript
   - Open transcript panel
   - Click extension icon
   - Verify transcript preview shows correctly

3. **Airtable Integration**
   - First import video via existing CLI: `python import_watch_later.py --max-items 1`
   - Navigate to that video on YouTube
   - Use extension to save transcript
   - Verify Airtable record updated with transcript fields

4. **Error Handling**
   - Video without transcript → Should show error
   - Video not in Airtable → Should show helpful message
   - Invalid API credentials → Should show auth error

### Integration Testing

```bash
# Test CLI transcript command
python import_watch_later.py transcript-from-extension \
  --video-id "dQw4w9WgXcQ" \
  --transcript "Never gonna give you up, never gonna let you down..." \
  --language "en"

# Verify in Airtable
python check_airtable_videos.py | grep "dQw4w9WgXcQ"
```

---

## Rollout Plan

### Week 1: Extension MVP
- [ ] Build basic Chrome extension structure
- [ ] Implement transcript extraction from YouTube DOM
- [ ] Test on multiple video types (auto-generated, manual, different languages)
- [ ] Handle edge cases (no transcript, private video, etc.)

### Week 2: Airtable Integration
- [ ] Add direct Airtable API calls to extension
- [ ] Implement credential storage (chrome.storage.sync)
- [ ] Add error handling and user notifications
- [ ] Test with real Airtable data

### Week 3: CLI Bridge (Optional)
- [ ] Add transcript-from-extension command to CLI
- [ ] Set up Chrome Native Messaging
- [ ] Test extension → CLI → Airtable flow
- [ ] Document setup instructions

### Week 4: Polish & Documentation
- [ ] Add extension settings page
- [ ] Improve UI/UX
- [ ] Write user documentation
- [ ] Create demo video

---

## Open Questions

1. **Extension distribution:**
   - Keep as unpacked extension (manual install)?
   - Publish to Chrome Web Store?

2. **Architecture choice:**
   - Direct API calls from extension (simpler)?
   - Native messaging to CLI (more robust)?

3. **Automation level:**
   - Manual button click per video?
   - Auto-save when transcript viewed?
   - Batch processing?

4. **Transcript format:**
   - Plain text (current)?
   - Preserve timestamps?
   - Store as structured JSON?

5. **Multi-language support:**
   - Auto-detect language from UI?
   - Allow manual language selection?
   - Support translated transcripts?

---

## Success Metrics

- ✅ Extension successfully extracts transcripts from 95%+ of videos
- ✅ Airtable updates complete in < 2 seconds
- ✅ Zero IP blocking issues (using authenticated browser)
- ✅ User can save 20+ transcripts without issues
- ✅ No recurring service costs

---

## Related Issues/PRs

- #[transcript-feature] - Original transcript import implementation
- IP_BLOCKING_ROOT_CAUSE_ANALYSIS.md - Why youtube-transcript-api doesn't work
- OPTION_C_YOUTUBE_DATA_API_ANALYSIS.md - Why official API doesn't work

---

## References

- Chrome Extension Manifest V3: https://developer.chrome.com/docs/extensions/mv3/
- Chrome Native Messaging: https://developer.chrome.com/docs/apps/nativeMessaging/
- Airtable REST API: https://airtable.com/developers/web/api/introduction
- YouTube DOM structure (subject to change)
