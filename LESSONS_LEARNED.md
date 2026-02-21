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
