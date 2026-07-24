---
name: youtube-panel-triage
description: Triage a misbehaving in-page transcript panel (stuck spinner, "Could not find transcript segments" error, or a suspiciously-fast "saved") against the three known failure modes — GH-68 stale-token 400, GH-69 scripted-click no-op, and stale-panel cross-video corruption — using network requests as the deciding evidence rather than re-deriving from the DOM each time. Use whenever extraction fails or looks wrong on a real video, before writing any fix. Triggers on "transcript panel stuck", "extraction failed", "panel spinner", "Could not find transcript segments", "GH-68", "GH-69", "extract and save error".
---

# Triage the transcript panel

Three distinct, previously-confirmed failure modes produce overlapping symptoms on this panel.
Guessing from DOM state alone (a spinner, an error message) cannot tell them apart — this skill
exists because that guessing already produced two wasted fix attempts and one **data-corrupting**
one (see `CLAUDE.md` "Failed fix attempts"). Always work through the checks below before writing
any code; general click/automation issues (coordinate scaling, scripted-vs-real click, tool-level
timeouts) are covered by `diagnose-stuck-automation` — read that first if the click itself seems
not to register at all.

**Never write a DOM-level fix for a stuck spinner without doing step 1 first.** All three prior
DOM-only fix attempts on this panel failed; one silently overwrote a real Airtable record.

## Step 1: read the network, not the DOM

Call `read_network_requests` (`urlPattern: "get_transcript"`) — start tracking *before* the click
you want to observe (tracking only begins once the tool is first called in a tab). Look at what
came back:

| Observation | Failure mode | Go to |
|---|---|---|
| **Zero requests**, however long you wait | GH-69: click never triggered the request | Step 2 |
| **A request fired and returned 400** | GH-68: stale continuation token after SPA nav | Step 3 |
| **`saved` in well under ~100ms with no fetch observed at all** | Stale-panel corruption | Step 4 |
| A request fired and is legitimately still pending | Not a bug — wait longer (a real extraction on a long video can take 30s+) | — |

## Step 2: GH-69 — zero requests, ever

**Signature**: `data-error-msg` says "Could not find transcript segments…", the button was
genuinely found and clicked (check `content.js` console logs for "Clicking transcript button..."),
and `read_network_requests` shows no `get_transcript` call at all, no matter the timeout.

**Cause**: a scripted click (`javascript_tool`'s `.click()`, or any `dispatchEvent` sequence) does
not carry real browser user activation, and YouTube's transcript-loading path silently never fires
in response — confirmed on 2026-07-23 across dozens of attempts, multiple videos, timeouts to 90s+.
A real trusted click (a human, or Claude in Chrome's `computer` `left_click`) on the identical
button/video/session works immediately. Full writeup:
`docs/GITHUB_ISSUE_69_TRANSCRIPT_PANEL_OPENER_SELECTOR_MISS.md`.

**Fix**: re-trigger with a real `computer` `left_click`, not `javascript_tool`. If you're running
`harvest-playlist` or `verify-panel`, they already mandate this — if you're seeing this failure
mode from one of those skills, something upstream is falling back to a scripted click; fix the
calling code, not this panel. Do **not** respond to this signature by adding more retries/timeouts
in `content.js` — the defect isn't in the extension, and no amount of client-side patience fixes a
request that never gets sent.

## Step 3: GH-68 — a request fired and got a 400

**Signature**: `read_network_requests` shows `POST /youtubei/v1/get_transcript` with **status
400**. Usually reached via SPA nav (clicking a playlist sidebar entry), rarely on a fresh full page
load.

**Cause**: the "Show transcript" control in the description carries a continuation token bound to
the video it rendered for. If clicked too soon after a SPA nav (`yt-navigate-finish` fires while
YouTube is still mid-swap), it still holds the *previous* video's token → 400 → permanent spinner.
Full root-cause writeup: `CLAUDE.md` → "ROOT CAUSE FOUND (2026-07-17...)".

**Mitigation already implemented**: `mountPanel()` holds a `waiting` state (not `idle`) until
`ytd-watch-flexy`'s own `video-id` attribute matches the URL, which is when the token becomes
fresh — implemented and verified live 2026-07-22 (see `CLAUDE.md` "Status update"). If you're
seeing a fresh 400 despite that gate holding, that's a **new regression** worth its own writeup, not
an instance of the already-fixed issue — don't assume it's the same bug without checking whether
`data-save-state` genuinely reached `idle` (not `waiting`) before the click that produced the 400.

**Anti-corruption note (item #2, still open per `CLAUDE.md`)**: the provenance guard for this path
(refuse to harvest segments not populated after the current nav) is **not yet implemented**. Don't
treat the loop as fully hardened against this even with the `waiting`-state gate in place.

## Step 4: stale-panel cross-video corruption

**Signature**: `data-save-state` reaches `saved` suspiciously fast — `extracting → saving` in
under ~100ms, with no `get_transcript` fetch observed in that window at all.

**Cause**: `extractTranscript()` calls `collectSegments(document)` document-wide before trying to
open anything. If the previous video's transcript panel is still expanded (closing it does **not**
remove its segment nodes from the DOM), this instantly harvests the previous video's leftover
segments and saves them under the *current* video's ID — a genuine data-corruption bug, not a
failure. It reports `saved`, not `error`, which is what makes it dangerous.

**This is the single most important thing to check before trusting any `saved` state**: compare
the saved transcript's opening words / length against the actual current video, not just that the
UI says `saved`. A passing `saved` with a suspiciously fast `extracting→saving` and no fetch is
**guilty until proven innocent**.

**Do not attempt to fix this by closing the transcript panel on navigation.** Three attempts at
exactly that were made 2026-07-17; the DOM facts that break the obvious approaches (the real open
panel reports `target-id="null"`, its close button is labelled `"Close"` not `"Close transcript"`)
are documented in `CLAUDE.md` → "Failed fix attempts". The third attempt silently overwrote a real
Airtable record. If you think you've found a fix here, verify against real content in Airtable
before trusting a `saved` result, and re-read that section first.

## Reference map

- `CLAUDE.md` — GH-68 root cause, the `waiting`-state fix, the three failed fix attempts, GH-69
  finding.
- `docs/GITHUB_ISSUE_69_TRANSCRIPT_PANEL_OPENER_SELECTOR_MISS.md` — GH-69 full writeup and evidence
  log.
- `docs/PROJECT-MANIFEST-in-page-panel.md` — overall panel design and agent contract.
- `diagnose-stuck-automation` — general click/automation debugging, for issues not specific to this
  panel.
