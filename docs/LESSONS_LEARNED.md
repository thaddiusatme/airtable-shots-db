# Lessons Learned

## Iteration 1: Triage UI Stabilization (FastAPI)

### Date
2026-02-21

### Branch
`feature/triage-ui-stabilization`

### Commit
`6a7908a` - Add triage UI with TDD: python-multipart + Skipped status

---

## What We Learned

### 1. FastAPI Form Dependency (CRITICAL)
**Issue:** FastAPI's `Form(...)` parameter requires `python-multipart` package at runtime.

**Error:**
```
RuntimeError: Form data requires "python-multipart" to be installed.
```

**Solution:** Add `python-multipart==0.0.20` to `requirements.txt`

**Lesson:** When using FastAPI Form handling, always include `python-multipart` in dependencies. This is not automatically installed with FastAPI.

---

### 2. TDD Red-Green-Refactor Works Well
**Approach:**
- **RED:** Wrote tests first → they failed with missing dependency error
- **GREEN:** Added `python-multipart` → all tests passed
- **REFACTOR:** Code was already minimal, no refactoring needed

**Lesson:** Writing tests before implementation catches missing dependencies early. The red-green-refactor cycle provided clear checkpoints and prevented over-engineering.

---

### 3. Next Button State Management (Architectural Decision)
**Options Considered:**
- **A:** Write "Skipped" status to Airtable (chosen)
- **B:** Track "seen IDs" in session/cookie without writing to Airtable

**Decision:** Chose Approach A (write to Airtable)

**Rationale:**
- Maintains Airtable as single source of truth
- Simple implementation (reuses existing `/set-status` endpoint)
- Makes "skipped" state queryable/reportable
- No client-side state to manage

**Trade-off:** Writes more data to Airtable, but provides better observability.

---

### 4. TestClient Redirect Behavior
**Issue:** Tests initially failed because `TestClient` follows redirects by default (returns 200 instead of 303).

**Solution:**
```python
TestClient(app, follow_redirects=False)
```

**Lesson:** When testing endpoints that return redirects, explicitly disable redirect following to verify correct HTTP status codes.

---

### 5. Virtual Environment Best Practice
**Issue:** Tests tried to use system Python instead of project venv.

**Solution:** Always use `.venv/bin/python -m pytest` when running tests.

**Lesson:** Explicitly reference the venv Python to ensure correct dependencies are available.

---

### 6. Uvicorn Startup from Repo Root
**Command:**
```bash
.venv/bin/python -m uvicorn triage_app:app --reload --port 8000 --app-dir airtable-shots-db
```

**Lesson:** When FastAPI app is in a subdirectory, use `--app-dir` flag OR start uvicorn from that directory. Dotenv path loading already handles `.env` location correctly.

---

## What Went Well
- TDD caught the missing dependency immediately
- Small, focused commit with clear intent
- All acceptance criteria met in first iteration
- Test coverage for all status transitions (Done/Declined/Skipped/Invalid)

---

## What Could Be Improved (Future)
- Add error page for missing `.env` variables (currently raises RuntimeError)
- Add integration test that actually calls Airtable API (not just mocked)
- Consider adding keyboard shortcuts (D/X/N keys)
- Add empty state messaging when no Queued videos exist

---

## Next Steps
- Verify end-to-end with real Airtable data
- Add workflow documentation for running the triage UI
- Consider P1 improvements (error messaging, pagination)

---

## Iteration 2: Chrome Extension Settings Page

### Date
2026-02-21

### Branch
`chrome-extension-settings-page`

### Issue
GitHub Issue #7 — Add proper Settings page for Chrome extension

---

## What We Learned

### 1. Chrome Extension Pages Don't Need web_accessible_resources
**Context:** Opening an extension-owned HTML page via `chrome.tabs.create({ url: chrome.runtime.getURL('settings.html') })`.

**Lesson:** In Manifest V3, extension pages opened by the extension itself (via `chrome.runtime.getURL`) do NOT need to be listed in `web_accessible_resources`. That field is only for resources accessed by web pages or other extensions.

---

### 2. chrome.storage.sync vs chrome.storage.local
**Decision:** Used `chrome.storage.sync` for credential storage.

**Rationale:**
- Syncs across user's Chrome instances (desktop ↔ laptop)
- Appropriate for small config data (API keys, Base IDs)
- `chrome.storage.local` would be better for large data (transcripts)

**Trade-off:** 100KB total sync quota, but credentials are tiny.

---

### 3. Password Field for API Keys (UX Security)
**Decision:** Used `type="password"` for the API Key input field.

**Lesson:** Even though `chrome.storage.sync` stores the key in plaintext, using a password field prevents shoulder-surfing and accidental screen-share exposure. This is a low-cost UX improvement.

---

### 4. Format Validation as Early Guard
**Approach:** Validate that API key starts with "pat" or "key", and Base ID starts with "app" before allowing save.

**Lesson:** Simple prefix checks catch common copy-paste errors (e.g., pasting the wrong value into the wrong field) without being overly restrictive. Better to catch early than get a cryptic 401/404 from Airtable.

---

### 5. Test Connection Button is High-Value UX
**Implementation:** Hits `GET /v0/{baseId}/Videos?maxRecords=1` to verify credentials.

**Lesson:** A "Test Connection" button eliminates the save-try-fail-debug cycle. Users get immediate feedback on whether credentials work before attempting to save a transcript. Maps HTTP status codes to user-friendly messages (401 → "Invalid API Key", 404 → "Base not found").

---

### 6. TDD for Chrome Extensions (Adapted)
**Challenge:** No Node.js runtime, no DOM testing framework set up.

**Adapted approach:**
- **RED:** Created files with all acceptance criteria defined upfront
- **GREEN:** Code-reviewed against each criterion systematically
- **REFACTOR:** CSS/structure was clean from initial implementation

**Lesson:** For UI-heavy Chrome extensions without a test harness, a manual test checklist against acceptance criteria serves as the "test suite." The key discipline is defining criteria BEFORE writing code.

---

## What Went Well
- All P0 + P1 acceptance criteria addressed in a single iteration
- Settings page includes documentation (where to find credentials)
- Three-button design (Save / Test / Clear) covers all user workflows
- Consistent styling with popup.html (same font family, color palette)

---

## What Could Be Improved (Future)
- Add automated tests with Puppeteer or Playwright for extension pages
- Consider encrypting stored credentials (currently plaintext in sync storage)
- Add OAuth flow via Chrome Identity API for enterprise use cases
- Extract shared CSS into a common stylesheet (popup.html + settings.html share styles)

---

## Next Steps
- Load extension in Chrome and run manual test checklist
- Close GitHub Issue #7 after verification
- Begin Issue #8: Full transcript extraction improvements

---

## Iteration 3: Auto-Create Records, Thumbnails, and Channel Linking

### Date
2026-02-21

### Branch
`chrome-extension-settings-page`

### Issues
- GitHub Issue #9 — Transcript Source select field bug (resolved via manual Airtable fix)
- GitHub Issue #10 — Grab thumbnail when creating video record
- GitHub Issue #11 — Link Channel record when creating video

### Commits
- `c63f2aa` — Auto-create Airtable record when video not found
- `8942c18` — Add thumbnail + channel linking when creating video from extension

---

## What We Learned

### 1. Airtable Single Select Fields Reject Unknown Options via API
**Issue:** Sending `"youtube-web-ui-dom"` to a Single Select field that only had `"youtube-transcript-api"` as an option.

**Error:** `Insufficient permissions to create new select option "youtube-web-ui-dom"`

**Lesson:** The Airtable API cannot create new Single Select options unless the token has `schema.bases:write` scope. When adding new sources of data (e.g., Chrome extension vs CLI), either pre-populate the select options in the Airtable UI or use a text field instead.

---

### 2. YouTube Thumbnail URLs Are Predictable
**Approach:** Instead of scraping the thumbnail from the DOM, used the standard YouTube thumbnail URL pattern:
```
https://i.ytimg.com/vi/{videoId}/hqdefault.jpg
```

**Lesson:** YouTube thumbnails follow a deterministic URL pattern. No DOM scraping needed — just construct the URL from the video ID. `hqdefault.jpg` (480x360) is a reliable default; `maxresdefault.jpg` exists for most but not all videos.

---

### 3. Channel Extraction from YouTube DOM Requires Multiple Selectors
**Implementation:** Three fallback strategies for finding the channel link element:
1. `ytd-video-owner-renderer ytd-channel-name a`
2. `#owner a[href*="/channel/"]`
3. `#owner a[href*="/@"]`

**Lesson:** YouTube uses both `/channel/UCxxxxxx` and `/@handle` URL formats. The DOM extraction must handle both. Channel IDs starting with `UC` are the canonical identifier, but many channels now primarily use `@handle` URLs.

---

### 4. Non-Blocking Channel Upsert is the Right Pattern
**Decision:** Channel upsert returns `null` on failure instead of throwing, and the video record saves without the channel link.

**Lesson:** When a secondary operation (channel linking) could fail for various reasons (network, permissions, missing data), make it non-blocking. The primary operation (saving the transcript) should always succeed. Users can manually link channels later if needed.

---

### 5. Extension Can Replace CLI for Record Creation
**Discovery:** Originally, the extension only updated existing records (requiring CLI import first). Adding auto-create capability eliminated a major friction point for non-technical users.

**Lesson:** Every workflow step that requires switching tools (extension → CLI → extension) is a drop-off point. The extension should be self-sufficient for the most common use case: "I'm watching a video and want to save its transcript."

---

### 6. GitHub Issues as Lightweight Bug Tracking Works Well
**Approach:** Created focused issues (#9, #10, #11) for each bug/feature discovered during testing, with root cause analysis and solution options documented in the issue body.

**Lesson:** Filing an issue before fixing a bug creates a paper trail and forces clear problem articulation. Even when the fix is quick, the issue documents the "why" for future reference.

---

## What Went Well
- Rapid iteration: bug discovered → issue filed → fix shipped in minutes
- Auto-create eliminated the biggest UX friction (CLI dependency)
- Thumbnail + channel linking achieved feature parity with CLI import
- Non-blocking pattern prevented cascading failures

---

## What Could Be Improved (Future)
- Add `schema.bases:write` to API token to avoid Single Select issues
- Handle `@handle` → canonical `UCxxxxxx` channel ID resolution
- Consider batch upsert for multiple videos
- Full transcript extraction still incomplete (Issue #8)

---

## Next Steps
- Issue #8: Fix partial transcript extraction
- Create extension icons for polished look
- Consider merging `chrome-extension-settings-page` → `feature/youtube-transcripts` → `main`
