# In-Page Transcript Extension — Feasibility & Project Plan

**Date:** 2026-07-16
**Author:** working notes for Thaddius
**Goal:** Convert the "YouTube Transcript → Airtable" extension from a toolbar-popup UI into an **in-page panel injected directly into the YouTube watch page** (like the "YouTube Summary" panel that renders in the right rail), optimized for two things Thaddius named:

1. **Visibility / UX** — a persistent on-page panel instead of a popup you open and close.
2. **Automatability** — a design where extraction can be triggered programmatically (batch across Watch Later, or driven by an automation agent), which a popup fundamentally blocks.

---

## Verdict: Highly feasible. Mostly a refactor.

The hard part — reading YouTube's transcript DOM across both A/B panel variants — **already lives in the content script** (`content.js` + `lib/transcript-dom.js`) and already runs in the page context. The popup does almost nothing that's hard to move:

- renders a small UI (2 buttons, a status line, a preview),
- messages the content script to run extraction,
- calls the Airtable REST API to upsert Channel + Video.

Roughly **60–70% of the code is reusable as-is**. The net-new work is (a) drawing the UI into the page instead of a popup window, (b) adding a background service worker to make the Airtable calls (the one genuine architectural change — see CORS below), and (c) a small trigger/message layer that unlocks automation.

---

## Current architecture (as-is)

```
┌─ popup.html / popup.js  (extension origin)
│    • UI: Extract + Save buttons, status, preview
│    • chrome.tabs.sendMessage → content script
│    • fetch() → api.airtable.com   ← works because popup runs in EXTENSION origin
│    • credentials from chrome.storage.sync
│
├─ content.js + lib/transcript-dom.js  (injected into youtube.com/watch, ISOLATED world)
│    • openTranscriptPanel() — 5 DOM strategies
│    • extractTranscript() — collectSegments/parseSegment, lazy-load polling
│    • returns {videoId, title, segments, channel...} over sendMessage
│
├─ settings.html / settings.js — Airtable PAT + Base ID → chrome.storage.sync
│
└─ manifest.json (MV3)
     • action.default_popup = popup.html
     • content_scripts on https://www.youtube.com/watch*
     • host_permissions: youtube.com, api.airtable.com
     • NO background service worker
```

The popup is the *only* thing that has to disappear. Extraction is already where we want it.

---

## Target architecture (to-be)

```
┌─ content.js (page)  ── injects an in-page PANEL into the watch page DOM
│    • panel = shadow-root UI (extract/save/status/preview + auto-save toggle)
│    • re-mounts on YouTube SPA navigation (yt-navigate-finish)
│    • extractTranscript() called DIRECTLY — no cross-context round trip
│    • save request → chrome.runtime.sendMessage → service worker
│    • listens for programmatic triggers (see Automatability)
│
├─ background.js (service worker, NEW)  ── owns ALL Airtable I/O
│    • upsertChannel() + saveToAirtable()  (moved verbatim from popup.js)
│    • reads PAT from chrome.storage.sync — PAT never enters the page world
│    • fetch to api.airtable.com runs in EXTENSION origin → no CORS problem
│    • optional: chrome.commands keyboard shortcut, batch queue
│
├─ settings.html / settings.js — unchanged
│
└─ manifest.json
     • REMOVE action.default_popup (or keep a tiny popup that just opens settings)
     • ADD background.service_worker
     • ADD web_accessible_resources if panel loads its own CSS/HTML fragment
     • (optional) commands for a keyboard shortcut
```

---

## The one real gotcha: CORS / who makes the Airtable call

This is the single most important technical fact and the reason a background service worker is required.

Today the Airtable `fetch()` happens in **popup.js**, which runs in the **extension origin** — so `host_permissions` grants it a CORS bypass and it just works.

If you naively move that same `fetch()` into the **content script**, it runs in **YouTube's page origin**. In Manifest V3, content-script fetches are subject to the *host page's* CORS policy, so `api.airtable.com` would reject it. It would look like it should work and won't.

**Fix (standard MV3 pattern):** the content script never calls Airtable directly. It sends a message to a **background service worker**, which makes the call from the extension origin (bypassing CORS via `host_permissions`). This is a clean move — the `upsertChannel` and `saveToAirtable` functions transplant almost verbatim from `popup.js` into `background.js`.

**Bonus security win:** routing through the service worker means your Airtable PAT is read from `chrome.storage.sync` **inside the service worker only** and never lives in a variable on a third-party page (YouTube). Content scripts run in an isolated world, but keeping the credential out of the page context entirely is the right call.

---

## Secondary technical challenges (all solved patterns, low risk)

1. **YouTube is a SPA.** Navigating between videos doesn't reload the page, so a panel injected once can go stale or detach. Listen for `yt-navigate-finish` (YouTube's own event) or use a MutationObserver on the watch container to (re)mount the panel and reset state per video. `content.js` already assumes fresh URL params per extraction, so this is mostly mount lifecycle.

2. **Style isolation.** Injecting UI into YouTube's DOM means YouTube's CSS can bleed into your panel and vice-versa. Mount the panel inside a **Shadow DOM root** so styles are encapsulated. The existing popup CSS drops straight into the shadow root's `<style>`.

3. **Where to anchor the panel.** Options: (a) the right-rail secondary column (`#secondary`) above recommendations — matches the "YouTube Summary" placement Thaddius likes; (b) a fixed floating card; (c) a collapsible button under the video. Recommend (a) for the visibility goal, with a collapse toggle.

4. **web_accessible_resources.** Only needed if the panel pulls in a separate HTML/CSS asset or icons by URL. If the UI is built with inline DOM + inline styles in the shadow root, this may not be needed at all.

5. **No build step to preserve.** The repo is vanilla JS, no bundler (per CLAUDE.md). Keep it that way — all of this is doable with plain DOM APIs, no framework.

---

## Automatability design (the second goal — this is what a popup can never do)

A popup can only run when a human clicks the toolbar icon. Once the UI lives in the page and the network layer lives in a service worker, several trigger paths open up. In rough order of effort:

- **Keyboard shortcut** — `chrome.commands` in the manifest (e.g. `Ctrl+Shift+T`) fires a message that runs extract+save on the current video. Zero UI clicks. (Already listed as a "future direction" in CLAUDE.md.)
- **Auto-save toggle** — a checkbox in the panel; on `yt-navigate-finish`, auto-extract and save. Walk Watch Later, let it capture each video as it plays/opens.
- **Batch queue** — feed the service worker a list of video IDs/URLs; it opens each, extracts, and upserts. This is the natural home for a "process my whole Watch Later" button. (Also aligns with the existing `import_watch_later.py` intent.)
- **Agent-drivable trigger** — because an automation agent (me, in Cowork/Chrome) *can* interact with in-page DOM but *cannot* click a native toolbar popup, moving the trigger into the page is precisely what makes the extension automatable by an agent. A single in-page "Extract & Save" button in the DOM is clickable by browser automation; the toolbar popup is not. This directly resolves the wall we hit earlier today.

**Design note:** keep the trigger surface small and explicit (one message type like `{action:'extractAndSave', videoId}`). That single message is the seam that both the keyboard shortcut, the batch queue, and an external agent all push on.

---

## Phased plan

| Phase | Scope | Deliverable | Rough effort |
|------|-------|-------------|--------------|
| **0 — Spike** | Prove the service-worker Airtable path works end-to-end with a hardcoded button injected into `#secondary`. Validates the CORS fix before any UI polish. | Injected button that extracts + saves one video | 0.5 day |
| **1 — Panel UI** | Port popup.html UI into a shadow-root panel: status, video info, preview, Extract + Save. Mount/unmount on SPA nav. | In-page panel at feature parity with popup | 1 day |
| **2 — Service worker** | Move `upsertChannel` + `saveToAirtable` into `background.js`; content script messages it; PAT read only in worker. Keep truncation/GH-64 logic intact. | All Airtable I/O via worker, CORS-clean | 0.5–1 day |
| **3 — Automatability** | `chrome.commands` shortcut + auto-save toggle + single `extractAndSave` message seam. | One-key / hands-free capture | 1 day |
| **4 — Batch (optional)** | Queue in the worker to walk a list of videos (Watch Later). | "Process these N videos" | 1–2 days |
| **5 — Cleanup** | Remove `default_popup` (or reduce to a settings launcher), update README/manifest, re-run `npm test` (transcript-dom/utils tests are unaffected). | Shipped v3.0.0 | 0.5 day |

**Core conversion (Phases 0–2): ~2–3 focused days.** Automation (Phase 3) another day. Batch is optional gravy.

---

## What you keep for free

- `lib/transcript-dom.js` (segment matching, both A/B variants, fixtures + tests) — **untouched**.
- `lib/transcript-utils.js` (100k-char truncation / GH-64 shim) — **untouched**, just called from the worker instead of the popup.
- `settings.html/js` and the `chrome.storage.sync` credential model — **untouched**.
- The `extractTranscript()` / `openTranscriptPanel()` logic — reused; it actually gets *simpler* (no sendMessage round trip, since the UI and extractor now share the content-script world).

---

## Risks & open questions

- **YouTube DOM churn.** Same standing risk you already carry (selectors break on YouTube redesigns) — not worsened by this change, but the panel anchor (`#secondary`) is one more selector to maintain.
- **Manifest permissions.** No *new* host permissions needed (youtube + airtable already present). Adding `commands` and `background` is additive and low-risk.
- **PAT exposure discipline.** The plan deliberately keeps the PAT out of the page context. Don't shortcut this by fetching Airtable from the content script "just to ship faster" — that both breaks on CORS and puts the key in the page world.
- **Chrome Web Store vs. unpacked.** If this stays a personal unpacked extension ("just for me," per the ask), you can skip store-review concerns entirely — no icons/store-listing blockers. Worth confirming this is personal-only.
- **Open question:** anchor placement — right rail (matches YouTube Summary) vs. floating card vs. under-video collapsible? Affects Phase 1 only.

---

## Recommendation

Do it. The risky part (transcript DOM extraction) is already built, tested, and in the right execution context. The conversion is a well-trodden MV3 pattern: **in-page shadow-root panel + background service worker for network I/O + a small message seam for triggers.** Start with the Phase 0 spike to de-risk the CORS/service-worker path in half a day; if that lands, the rest is mechanical. The automatability payoff is real and specifically fixes the "an agent can't click your toolbar popup" wall — an in-page button is something browser automation *can* drive.
