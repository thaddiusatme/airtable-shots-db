# Next Chat Prompt Template: YouTube Shot List Pipeline — Phase 1

## The Prompt

Let's create a new branch for the next feature: **Chrome Extension Screenshot Capture**. We want to perform TDD framework with red, green, refactor phases, followed by git commit and lessons learned documentation. This equals one iteration.

### Updated Execution Plan (focused P0/P1)

**Brief Context**: Implementing Phase 1 of the YouTube Shot List Pipeline — adding screenshot capture to the existing Chrome extension. The extension already has working transcript extraction, Airtable integration, and settings page. We're adding a new "Capture Shots" section to the popup UI and frame capture logic to the content script.

**I'm following the guidance in**: TDD (red-green-refactor), small reviewable commits, and the architecture defined in `ISSUE_SHOT_LIST_PIPELINE.md`.

**Critical path**: Get screenshot capture working end-to-end (frames saved to disk + manifest.json generated) before moving to Phase 2 (analyzer).

### Current Status

**Completed**: 
- Architecture planning and GitHub issue specification (`ISSUE_SHOT_LIST_PIPELINE.md`)
- Identified existing extension structure and reusable patterns (transcript extraction, Airtable REST calls, settings page)

**In progress**: 
- Phase 1: Chrome Extension Screenshot Capture
  - Files to modify: `manifest.json`, `popup.html`, `popup.js`, `content.js`
  - Location: `/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/`

**Lessons from last iteration**: 
- The extension already has working patterns for DOM interaction (transcript extraction), message passing (popup ↔ content script), and Airtable REST calls. Reuse these patterns for screenshot capture.
- Keep transcript extraction untouched — add capture as a separate section in the popup.
- Use `chrome.downloads` API for saving PNGs locally (simpler than IndexedDB for this use case).

### P0 — Critical/Unblocker (Phase 1: Screenshot Capture)

**Main Task: Add "Capture Shots" UI and frame capture logic**

1. **Modify `manifest.json`**: Add `downloads` permission to allow saving PNGs locally
2. **Modify `popup.html`**: Add "Capture Shots" section with interval input (default 1s, min 0.5s), max screenshots input, Start/Stop button, and status display (`Captured: 0 / 100`)
3. **Modify `content.js`**: Add frame capture logic — on `startCapture` message, find `<video>` element, start timer, each tick: `canvas.drawImage(video)` → `canvas.toBlob()` → send blob to popup for download, on `stopCapture` or max reached: generate manifest.json and download it
4. **Modify `popup.js`**: Add capture orchestration — send `startCapture` / `stopCapture` messages to content script, track progress via messages, handle downloads, show status updates

**Acceptance Criteria**:
- [ ] Extension loads without errors after manifest.json modification
- [ ] "Capture Shots" section appears in popup UI with interval and max inputs
- [ ] Clicking "Start Capture" begins frame capture at specified interval
- [ ] Frames are saved as `frame_{index}_t{timestamp}s.png` to `~/Downloads/yt-captures/{videoId}_{datetime}/`
- [ ] manifest.json is generated with correct frame metadata (index, timestamp, filename)
- [ ] Clicking "Stop Capture" stops the timer and shows completion status
- [ ] "Open captures folder" link works and opens the captures directory

### P1 — Testing & Validation (Phase 1 validation)

**Task 1: Manual end-to-end test**
- Load extension in Chrome
- Navigate to a YouTube video
- Click extension icon → "Capture Shots" tab
- Set interval to 1 second, max to 10 frames
- Click "Start Capture"
- Verify 10 frames are downloaded to correct folder
- Verify manifest.json contains correct metadata

**Task 2: Verify manifest.json format**
- Check that manifest.json matches the format expected by Phase 2 analyzer
- Fields: `videoId`, `videoTitle`, `frames` (array with `index`, `timestamp`, `filename`)

**Acceptance Criteria**:
- [ ] Manual test produces frames and manifest.json in expected location
- [ ] manifest.json format is compatible with analyzer expectations
- [ ] No console errors in extension popup or content script

### P2 — Future Improvements (deferred to later iterations)

**Task 1**: Add progress bar to popup UI (currently just text counter)
**Task 2**: Add pause/resume functionality (currently only start/stop)
**Task 3**: Add keyboard shortcut (Ctrl+Shift+C) to toggle capture
**Task 4**: Store capture settings (interval, max) in chrome.storage.sync for persistence

### Task Tracker

- [ ] **In progress**: Modify manifest.json, popup.html, popup.js, content.js for screenshot capture
- [ ] **Pending**: Manual end-to-end test on YouTube video
- [ ] **Pending**: Verify manifest.json format
- [ ] **Pending**: Git commit with lessons learned
- [ ] **Pending**: Phase 2 (Scene Analyzer) — OpenCV histogram comparison
- [ ] **Pending**: Phase 3 (Airtable Publisher) — publish shots to Airtable
- [ ] **Pending**: Phase 4 (yt-frame-poc alignment) — fix CLI publisher schema
- [ ] **Pending**: Phase 5 (Cloud storage) — upload Shot Image attachments

### TDD Cycle Plan

**Red Phase**: 
- Write test that verifies frames are captured and saved to disk with correct filenames
- Test that manifest.json is generated with correct metadata
- Test that content script receives and responds to `startCapture` / `stopCapture` messages

**Green Phase**:
- Implement minimal frame capture logic in content.js (canvas.drawImage + toBlob)
- Implement minimal message passing in popup.js and content.js
- Implement minimal manifest.json generation

**Refactor Phase**:
- Extract frame capture logic into helper functions
- Add error handling for missing `<video>` element
- Add logging for debugging
- Clean up message passing patterns

### Next Action (for this session)

**Specific actionable task with file references**:

1. Start with `manifest.json` (`/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/manifest.json`): Add `downloads` permission to the permissions array
2. Update `popup.html` (`/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/popup.html`): Add "Capture Shots" section with UI controls
3. Update `popup.js` (`/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/popup.js`): Add capture orchestration logic
4. Update `content.js` (`/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/content.js`): Add frame capture logic

Would you like me to implement these changes now in small, reviewable commits?

---

## Reference Information

**Repo paths**:
- Extension: `/Users/thaddius/repos/2-20/airtable-shots-db/chrome-extension/`
- Analyzer (Phase 2): `/Users/thaddius/repos/2-20/airtable-shots-db/analyzer/` (to be created)
- Publisher (Phase 3): `/Users/thaddius/repos/2-20/airtable-shots-db/publisher/` (to be created)
- CLI capture: `/Users/thaddius/repos/2-21/yt-frame-poc/`

**Key files**:
- Issue spec: `/Users/thaddius/repos/2-20/airtable-shots-db/ISSUE_SHOT_LIST_PIPELINE.md`
- Architecture plan: `/Users/thaddius/.windsurf/plans/connector-options-68f0fb.md`

**Expected output format** (for Phase 2 compatibility):
```
~/Downloads/yt-captures/
  {videoId}_{datetime}/
    frame_00000_t000.000s.png
    frame_00001_t001.000s.png
    ...
    manifest.json
```

**manifest.json format** (expected by analyzer):
```json
{
  "videoId": "dQw4w9WgXcQ",
  "videoTitle": "Rick Astley - Never Gonna Give You Up",
  "captureDate": "2026-02-22T15:30:00Z",
  "interval": 1.0,
  "frames": [
    {
      "index": 0,
      "timestamp": 0.0,
      "filename": "frame_00000_t000.000s.png"
    },
    {
      "index": 1,
      "timestamp": 1.0,
      "filename": "frame_00001_t001.000s.png"
    }
  ]
}
```

**Existing extension patterns to reuse**:
- Message passing: `chrome.tabs.sendMessage()` (popup → content) and `chrome.runtime.onMessage.addListener()` (content script)
- DOM interaction: `document.querySelector()` for finding elements
- Airtable REST: fetch API with Bearer token auth (in popup.js)
- Settings storage: `chrome.storage.sync.get()` / `chrome.storage.sync.set()`
