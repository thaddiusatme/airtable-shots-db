---
name: verify-panel
description: Verify the in-page YouTube transcript panel end-to-end with Claude in Chrome — panel presence, agent discoverability, the service-worker CORS path, SPA remount, and real Airtable writes. Use after any change to content.js, background.js, or manifest.json, and as the acceptance test at the end of each phase (0-5) of the in-page panel initiative. Triggers on "verify the panel", "run the panel acceptance test", "test the agent loop", "does the extension still work".
---

# Verify the in-page transcript panel

Acceptance test for the agent-drivable panel (`docs/PROJECT-MANIFEST-in-page-panel.md`). Runs against live YouTube and writes real records to Airtable base `appWSbpJAxjCyLfrZ`.

The contract under test (from CLAUDE.md — treat as stable API):
- Panel root `<div id="yt-transcript-panel" data-save-state data-video-id data-error-msg>`
- Button `<button data-testid="extract-save-btn" aria-label="Extract and save transcript">`, fixed position
- States: `idle → extracting → saving → saved | error`. Must never hang on `saving`.

## Preconditions (ask the human to confirm — do not guess)

1. Unpacked `chrome-extension/` **reloaded** at `chrome://extensions/` and matching the working tree. A stale load fails check 1 for a boring reason that looks like a real failure.
2. Settings page holds a valid Airtable PAT + Base ID.
3. **A playlist URL with 3+ videos.** Ask for it; never pick one yourself — every run writes real records into the user's Videos table.

The toolbar popup still existing is expected until Phase 5 and is NOT under test. If the user describes "Settings and Extract buttons", they clicked the toolbar icon — redirect them to the floating button in the page.

## Method — the parts that catch real bugs

**Install a MutationObserver before clicking.** A successful save completes in ~2.7s, faster than one tool round-trip, so polling after the click reads `saved` and teaches you nothing. Observe `document.documentElement` with `subtree:true, attributes:true, attributeFilter:['data-save-state','data-video-id','data-error-msg']`, stash to `window.__phase0log`, then click. Without this you cannot claim the state machine passed *through* `extracting→saving`.

**Navigate by clicking the playlist sidebar. Never use `navigate`.** `navigate` does a full page load and silently voids the SPA-remount test — the exact thing being verified.

**Observer survival proves no reload.** If `window.__phase0log` still exists after navigating, it was genuinely SPA nav. Free, and more reliable than reading the URL.

**Never trust `data-save-state: saved`. Confirm the record in Airtable** (Videos `tblpwqMfiMsRsYuMY`, filter `Video ID`) via the Airtable MCP tools. This is what separates "the UI claims success" from evidence. It also gets you two properties for free: upsert idempotency (N saves → 1 record) and that the error path writes no junk rows.

**Check the transcript's CONTENT, not just that it saved.** A `saved` whose `extracting → saving` took ~2ms with no fetch means stale segments from the *previous* video were harvested and written under this video's ID — silent corruption that reports success. Compare length and opening words against the actual video. Treat a sub-100ms extract as guilty until proven innocent.

**A real Airtable write is strong evidence; absence of console CORS errors is weak.** Console tracking only starts when `read_console_messages` is first called — call it early with `clear:true`, but lean on the write.

**`javascript_tool` output is blocked if it contains the page URL/query string.** Read `v=` from `location.search` internally; never return `location.href` in the JSON.

## Checks

1. **Panel present** — `#yt-transcript-panel` exists, `data-save-state="idle"`, `data-video-id` matches `v=`.
2. **Agent-pressable** — `find` returns the button; real `<button>`, in-viewport without scrolling. (Guards the closed-shadow-root risk.)
3. **Extract + save** — observer installed, click, poll to terminal. Must transition `extracting → saving → saved`, never hang. On `error`, report `data-error-msg`. Confirm the Airtable record.
4. **SPA remount** — via sidebar, to the next 2 videos. After each: panel back at `idle`, `data-video-id` matches the new URL, observer survived. Repeat check 3 on **every** video, not just one — see the trap below.
5. **Summary** — table of video id / remounted / terminal state / error msg, plus GO / NO-GO.

**When extraction fails, read the NETWORK before theorising about the DOM.** A permanent spinner means a request failed, not that the DOM is confused. `read_network_requests` with `urlPattern: "transcript"` shows `POST /youtubei/v1/get_transcript` and its status — a **400** there is the known root-cause signature (stale continuation token after SPA nav). Network tracking only starts when the tool is first called, so call it *before* the click you want to observe. Three DOM-level fixes were written against this bug before anyone checked the request; all three failed and one corrupted data.

**`data-save-state: idle` does not mean ready.** The panel remounts on `yt-navigate-finish` while YouTube is still mid-swap: the page title, the description's transcript entry point, and even the previous video's segments can still be stale. Before clicking, also require the page to have settled (e.g. `document.title` reflects the new video). Clicking the instant the panel says `idle` is how you get either the 400 or stale-data corruption.

**Abort, don't click, when preconditions fail.** If the wait for `idle` + matching `data-video-id` times out, report and stop. A script that clicks anyway produced a bogus `saved` that was really the *previous* video re-saved.

## The trap this test exists to catch

**Extract on video N → SPA nav to N+1 → extract fails.** A prior successful extraction leaves YouTube's transcript engagement panel expanded; the extension sees the stale panel, believes it's already open, and never loads segments for the new video. It hangs on a spinner with a pending `ytd-continuation-item-renderer` and reports "Could not find transcript segments".

This only reproduces in the exact sequence the agent runs (extract → next → extract), so **extract on every video, never every other one.** Testing a subset hides it.

**When a video fails, isolate before blaming the video.** Run the 3-way comparison:

| Scenario | Meaning if it passes |
|---|---|
| Fresh full page load → extract | The video is fine; the bug is in the nav path |
| SPA nav, **no** prior extract | SPA nav is fine; the bug is the prior extraction |
| SPA nav, **after** a prior extract | (the failing case) |

Concluding "this video has no transcript" without this comparison is how the bug gets missed. Do the reload-based diagnostics only **after** the remount checks are done, so they don't void the test.

## GO / NO-GO

- **GO** — checks 1–4 pass with Airtable writes confirmed.
- **NO-GO** — agent can't read the panel, worker fetch CORS-fails, `data-save-state` hangs, or a save reports `saved` with no record in Airtable.

Distinguish *architecture* failures (NO-GO: the design is wrong) from *defects* (GO with a must-fix: the design holds, the code has a bug). A stale-panel-style bug is a defect, not an architecture failure — but it still blocks the agent loop, so report it as blocking.
