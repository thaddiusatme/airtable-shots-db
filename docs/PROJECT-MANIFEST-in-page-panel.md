# Project Manifest — In-Page Transcript Panel

**Project:** Convert "YouTube Transcript → Airtable" from a toolbar popup into an in-page panel driven by an AI agent.
**Repo:** `airtable-shots-db` · **Working dir:** `chrome-extension/`
**Branch:** `feature/transcript-only-extension` (continue on this branch)
**Distribution:** Personal unpacked only — no Chrome Web Store, no icon/store scope
**Status:** Planning → ready to start
**Last updated:** 2026-07-16

---

## 1. Why

The extension currently lives in a toolbar popup. A popup can only be opened by a human clicking the browser chrome — it is invisible to page-level browser automation. We hit this wall directly: an agent (Claude in Chrome) can navigate YouTube and click page elements, but **cannot** click a native extension popup.

Moving the trigger **into the page** flips that. Once the buttons are DOM elements on the watch page, the agent can press them — which turns "capture every transcript in a playlist" into a hands-off loop.

Two goals, in priority order:

1. **Automatability** — the agent presses in-page buttons to run extraction + save. The playlist is the queue; the agent is the loop.
2. **Visibility / UX** — a persistent on-page panel instead of an open/close popup.

---

## 2. Operating model (read this first — it shapes everything)

```
Claude in Chrome (the loop)                 The extension (dumb, per-video)
──────────────────────────                  ───────────────────────────────
open playlist (Watch Later, etc.)
  └─ for each video:
       navigate to watch page  ───────────▶ content script mounts the panel
       find "Extract & Save" button
       click it               ───────────▶ extract transcript from DOM
                                            → service worker → Airtable upsert
       poll data-save-state    ◀──────────  panel sets state: saving → saved/error
       verify "saved", then next video
```

**The extension holds no queue and no orchestration.** It exposes, per watch page: one button that extracts + saves that single video, and a machine-readable status the agent can poll. All iteration, navigation, and retry logic lives with the agent. **The playlist is the queue.**

This is the core design commitment. Do not build a batch queue, a keyboard shortcut, or import-list logic into the extension — that orchestration is the agent's job and duplicating it in the extension is wasted scope.

---

## 3. Goals & non-goals

**Goals**
- In-page panel injected on `youtube.com/watch*`, fixed floating card, always visible.
- A single agent-pressable "Extract & Save" action per video.
- Machine-readable status the agent can poll to confirm each save before advancing.
- Airtable I/O moved to a background service worker (the CORS fix — see §5).
- Reliable panel re-mount on YouTube SPA navigation (video→video without reload).
- Feature parity with today's popup: extract, preview, save, GH-64 truncation handling.

**Non-goals**
- No Chrome Web Store publish; no icon assets; no store review.
- No batch queue / keyboard shortcut / import pipeline inside the extension (agent owns the loop).
- No changes to transcript DOM parsing (`lib/transcript-dom.js`) — it already works across both A/B variants.
- No changes to the credential model (`settings.*`, `chrome.storage.sync`).
- No new Airtable schema. Same Videos/Channels upsert-by-Video-ID behavior.

---

## 4. Architecture

### As-is
- `popup.html/js` — UI + `chrome.tabs.sendMessage` to content script + **`fetch()` to Airtable (runs in extension origin, so CORS is fine)** + reads PAT from storage.
- `content.js` + `lib/transcript-dom.js` — injected on watch pages; `extractTranscript()` / `openTranscriptPanel()` already run in the page (isolated world).
- `settings.*` — PAT + Base ID → `chrome.storage.sync`.
- `manifest.json` — MV3; `action.default_popup`; content script on `watch*`; host perms for youtube + airtable; **no service worker**.

### To-be
- `content.js` — injects a **fixed floating panel** into the watch page; calls `extractTranscript()` **directly** (no message round-trip); sends save requests to the service worker; exposes an agent contract (§6); re-mounts on `yt-navigate-finish`.
- `background.js` **(new)** — service worker owning **all** Airtable I/O. `upsertChannel()` + `saveToAirtable()` move here almost verbatim from `popup.js`. Reads PAT from storage **inside the worker only**. `fetch()` runs in extension origin → no CORS problem, and the PAT never enters the YouTube page world.
- `settings.*` — unchanged.
- `manifest.json` — remove `action.default_popup` (or reduce to a settings launcher); add `background.service_worker`. No new host permissions.

---

## 5. The one hard constraint: who calls Airtable

Today the Airtable `fetch()` works only because it runs in `popup.js` (extension origin). **Moving that same `fetch()` into the content script will break** — content-script fetches in MV3 are subject to the host page's (YouTube's) CORS policy, and `api.airtable.com` will reject them. It looks like it should work; it won't.

**Required pattern:** content script → `chrome.runtime.sendMessage` → **service worker** → `fetch()` to Airtable (extension origin bypasses CORS via `host_permissions`). Bonus: the PAT is read only inside the worker and never lives in a variable on a third-party page.

Phase 0 exists to prove this path before any UI polish.

---

## 6. The Agent Contract (extension ⇄ Claude in Chrome)

This is the interface that makes the extension agent-drivable. Treat it as an API and keep it stable.

**Trigger — the panel root and button must be discoverable and clickable:**
- Panel root: `<div id="yt-transcript-panel" data-save-state="…">`
- Primary action: a real `<button>` with a stable accessible name, e.g. `aria-label="Extract and save transcript"` and `data-testid="extract-save-btn"`.
- Fixed position, always visible — no scroll-into-view required.

**Status — machine-readable, not prose.** `data-save-state` on the panel root is the source of truth the agent polls:

| `data-save-state` | Meaning | Agent action |
|-------------------|---------|--------------|
| `idle` | panel mounted, ready | click the button |
| `extracting` | reading transcript DOM | wait |
| `saving` | service worker calling Airtable | wait |
| `saved` | upsert succeeded | record success, go to next video |
| `error` | extraction or save failed | read `data-error-msg`, decide retry/skip |

- Also surface the outcome in a readable text node (human visibility) — but the agent keys off `data-save-state`, so async timing and lazy-loading never cause a misread.
- Expose `data-video-id` on the panel so the agent can confirm the panel matches the current URL after SPA navigation.

**Idempotency:** save is upsert-by-`Video ID` (already true today), so an accidental re-click or retry updates rather than duplicates.

**Discoverability caveat (spike this):** if the panel is built in a **closed** Shadow DOM, `find`/`read_page` may not see it. Use an **open** shadow root or scoped/prefixed classes instead. Confirm the agent's tools pierce the chosen approach in Phase 0.

---

## 7. Requirements & acceptance criteria

- **R1 — Panel present per video.** On any `youtube.com/watch*` load *and* after in-app navigation to another video, the panel is mounted with `data-save-state="idle"` within ~2s. *Accept:* navigate across 3 playlist videos without reload; `find` locates the button each time.
- **R2 — Agent-pressable.** The button is locatable by accessible name/`data-testid` and clickable without scrolling. *Accept:* Claude in Chrome clicks it via `find` on first try.
- **R3 — Extract parity.** Extraction produces the same segments/fields as the popup does today, both A/B transcript variants. *Accept:* existing `lib/transcript-dom.test.js` still passes; spot-check one classic + one modern video.
- **R4 — Save via worker.** Save round-trips through the service worker to Airtable with no CORS error; creates or updates the Videos record (Triage Status `Queued` on create) and upserts the Channel. *Accept:* record appears/updates in base `appWSbpJAxjCyLfrZ`.
- **R5 — Readable terminal state.** `data-save-state` reaches `saved` or `error` and never hangs on `saving`. *Accept:* agent polls to a terminal state on 5 consecutive videos.
- **R6 — GH-64 preserved.** 100k-char truncation via `lib/transcript-utils.js` still applies; warning surfaced. *Accept:* `lib/transcript-utils.test.js` passes; one >100k transcript saves without failure.
- **R7 — PAT containment.** The Airtable PAT is read only in the service worker; it never appears in content-script/page context. *Accept:* code review.

---

## 8. Phased plan

| Phase | Goal | Tasks | Effort |
|------|------|-------|--------|
| **0 — Spike (de-risk)** | Prove the two unknowns before building UI | (a) minimal `background.js` that does the Airtable save on a message; (b) hardcoded floating button injected by `content.js` that extracts + saves current video; (c) confirm Claude in Chrome can `find`+click it and read `data-save-state` through the chosen shadow-DOM/scoped-class approach | 0.5 day |
| **1 — Service worker** | All Airtable I/O in the worker | Move `upsertChannel` + `saveToAirtable` from `popup.js` → `background.js`; define message schema `{action:'extractAndSave', …}` / response; PAT read only in worker; keep GH-64 logic | 0.5–1 day |
| **2 — Panel UI** | Floating card at popup parity | Build fixed panel (status, video info, preview, Extract & Save); port popup CSS into scoped/shadow styles; wire button → extract → worker; set `data-save-state` transitions | 1–1.5 days |
| **3 — SPA lifecycle** | Rock-solid per-video remount | Handle `yt-navigate-finish` (+ MutationObserver fallback); reset panel state and `data-video-id` per video; teardown stale panel | 0.5–1 day |
| **4 — Agent contract hardening** | Make the loop reliable | Finalize `data-*` attributes, `aria-label`/`data-testid`, `data-error-msg`; document the contract; dry-run a full playlist with Claude in Chrome | 0.5–1 day |
| **5 — Cleanup / cut over** | Ship personal build | Remove `default_popup` (or reduce to settings launcher); update manifest, README; re-run `npm test`; bump to v3.0.0; load-unpacked verify | 0.5 day |

**Core (0–3): ~3–4 days. Full incl. agent hardening: ~4–5 days.**

---

## 9. File change map

| File | Change |
|------|--------|
| `manifest.json` | Add `background.service_worker`; remove/repurpose `action.default_popup`; (no new host perms) |
| `background.js` | **New.** Airtable upsert logic + message handler; PAT read here only |
| `content.js` | Add panel injection, SPA-remount lifecycle, direct `extractTranscript()` call, worker messaging, agent `data-*` contract |
| `popup.html` / `popup.js` | Retire (or shrink `popup.html` to a settings launcher). Save/channel logic relocates to `background.js` |
| `lib/transcript-dom.js` + tests | **Untouched** |
| `lib/transcript-utils.js` + tests | **Untouched** (called from worker now) |
| `settings.html` / `settings.js` | **Untouched** |

---

## 10. Risks & open decisions

**Risks**
- **YouTube DOM churn** — standing risk (selector breakage); the panel anchor adds one selector to maintain. Not worsened by this change.
- **Shadow-DOM discoverability** — closed shadow root could hide the panel from the agent. Mitigation: open shadow root / scoped classes; validated in Phase 0.
- **SPA remount is load-bearing** — if the panel doesn't remount on `yt-navigate-finish`, the agent's `find` fails on video #2. This is the highest-value thing to get right (Phase 3, spiked in Phase 0).
- **Service-worker lifecycle** — MV3 workers sleep; ensure each save message spins it up cleanly (it does by default, just don't hold state across messages).

**Open decisions for the team**
- **D1 — Shadow DOM vs scoped classes** for style isolation. Recommendation: whichever Phase 0 proves the agent can read; default to open shadow root.
- **D2 — Retire popup entirely vs keep a minimal settings launcher.** Recommendation: keep a tiny popup that only opens Settings, so credential setup stays reachable.
- **D3 — Error-retry policy** owned by the agent (retry N times then skip vs stop). Doesn't affect the extension; document in the agent runbook.

**Decided**
- Distribution: personal unpacked only. · Panel: fixed floating card. · Branch: `feature/transcript-only-extension`. · Queue: the playlist; loop: the agent.

---

## 11. Getting started (first session)

1. `git checkout feature/transcript-only-extension`
2. Load `chrome-extension/` unpacked at `chrome://extensions/`; confirm Settings still holds the Airtable PAT + Base ID.
3. Build the **Phase 0 spike**: floating button + minimal `background.js` save path on one video.
4. With Claude in Chrome, verify it can `find` the button, click it, and read `data-save-state` to `saved`.
5. If both hold, proceed to Phase 1. If shadow-DOM hides the panel, switch to scoped classes and re-verify — decide D1 here.
