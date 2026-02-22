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
