# Phase 0 Test Prompt — In-Page Panel Spike

Feed the prompt below to **Claude in Chrome** (or paste it into a Claude Code session with the `claude-in-chrome` tools available) to run the Phase 0 acceptance test end-to-end.

## Before you run it (manual, human does this once)

1. `git checkout feature/transcript-only-extension`
2. At `chrome://extensions/`, **reload** the unpacked `chrome-extension/` (a new service worker was added — the reload icon must be clicked, not just toggled).
3. Confirm the extension **Settings** page holds a valid Airtable PAT + Base ID (`appWSbpJAxjCyLfrZ`).
4. Open a YouTube **playlist** (e.g. Watch Later) and click into the **first watch page** so a `youtube.com/watch?v=…` tab is active.

---

## The prompt

> You are verifying Phase 0 of an in-page Chrome-extension panel on YouTube. The extension injects a fixed floating panel `<div id="yt-transcript-panel">` (bottom-right) with a button `data-testid="extract-save-btn"` (aria-label "Extract and save transcript"). The panel exposes a machine-readable state on `data-save-state`: `idle → extracting → saving → saved | error`, plus `data-video-id` and `data-error-msg`. Saving round-trips through the extension's service worker to Airtable. Do NOT reload the page between videos — SPA remount is exactly what we're testing.
>
> Run these checks and report each as PASS/FAIL with the evidence you observed:
>
> 1. **Panel present.** Call `tabs_context_mcp` and confirm the active tab is a `youtube.com/watch` page. Use `read_page`/`find` to confirm `#yt-transcript-panel` exists with `data-save-state="idle"` and that `data-video-id` matches the `v=` param in the URL.
> 2. **Agent-pressable.** Locate the button by `data-testid="extract-save-btn"` (or its accessible name) and confirm it is clickable **without scrolling**.
> 3. **Extract + save (the CORS path).** Click the button. Poll `data-save-state` on `#yt-transcript-panel` (via `read_page` or `javascript_tool`) until it reaches a **terminal** state (`saved` or `error`). It must pass through `extracting` and `saving` and must **not hang on `saving`**. Report the final state; if `error`, read and report `data-error-msg`. Also check the page console (`read_console_messages`) for any CORS error — there should be **none** (the fetch runs in the service worker, not the page).
> 4. **SPA remount.** Without reloading, navigate to the **next 2 videos** in the playlist (click the next video / use the playlist panel). After each navigation, confirm `#yt-transcript-panel` is present again with `data-save-state="idle"` and that `data-video-id` now matches the **new** URL. Then repeat check 3 (click → poll to terminal state) on at least one of them.
> 5. **Summary.** Report a table: for videos #1–#3 — video id, did the panel remount, terminal `data-save-state`, and any `data-error-msg`. State an overall **GO** (checks 1–4 passed) or **NO-GO** with the blocking reason.
>
> Constraints: do not click any YouTube element that triggers a native confirm/alert dialog. If a browser tool fails 2–3 times, stop and report what you tried rather than looping.

---

## What the human verifies separately (not agent-visible)

- **Airtable write (R4):** after check 3, confirm the Videos record appears/updates in base `appWSbpJAxjCyLfrZ` with `Triage Status = Queued` and a linked Channel. (Ask this Claude Code session to check it via the Airtable MCP tools if you want it automated.)
- **PAT containment (R7):** the Airtable PAT should only ever be read in the service worker. Spot-check the page/content-script context never holds it.

## Go / No-Go

- **GO** → both unknowns retired (CORS path works + agent can drive the panel across SPA nav). Proceed to Phase 1.
- **NO-GO** → if the agent can't read the light-DOM panel, or the worker fetch still CORS-fails, or `data-save-state` hangs on `saving`. Stop and reassess before building real UI.
