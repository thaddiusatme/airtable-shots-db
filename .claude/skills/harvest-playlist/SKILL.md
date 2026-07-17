---
name: harvest-playlist
description: Walk a YouTube playlist with Claude in Chrome and save every video's transcript to Airtable via the in-page panel — SPA navigation, click Extract & Save, poll to terminal state, retry, and report. Use when asked to capture/harvest/save transcripts for a playlist, backfill a playlist into Airtable, or run the agent loop over a list of videos.
---

# Harvest a playlist into Airtable

The hands-off agent loop the in-page panel exists to enable (`docs/PROJECT-MANIFEST-in-page-panel.md`). **You own iteration, navigation, and retry — the playlist is the queue.** The extension is deliberately dumb and per-video: one button, one status attribute. Do not ask it to batch; that duplicates your job.

To verify the panel itself works, use `verify-panel` instead. This skill assumes it does.

## Before starting

- **Get the playlist URL from the user.** Never pick one — every run writes real records to their Videos table.
- Extension loaded unpacked and Settings hold a valid Airtable PAT + Base ID.
- Playlists can be long (76+ videos). Tell the user the count and confirm scope before walking all of it.

## The contract you drive

- Panel `#yt-transcript-panel` → `data-save-state`: `idle → extracting → saving → saved | error`, plus `data-video-id`, `data-error-msg`.
- Button `[data-testid="extract-save-btn"]`.
- Saves are **upsert-by-`Video ID`** — idempotent. Re-running is safe; a retry updates, never duplicates.

## Loop

1. **Enumerate the queue once, up front.** From the playlist sidebar:
   `document.querySelectorAll('ytd-playlist-panel-video-renderer a')` → dedupe the `v=` param. Keep the ordered list of ids + titles; that's the work list.
2. **Optionally skip already-saved.** Query Airtable (Videos `tblpwqMfiMsRsYuMY`, base `appWSbpJAxjCyLfrZ`) for existing `Video ID`s and skip them. Worth it on a re-run; skip this on first pass. Ask the user if unsure.
3. **For each video:**
   - Navigate by **clicking its sidebar entry** — never `navigate`, never reload. Full loads are slow and defeat the design.
   - Wait for `data-video-id` to equal the new `v=` **and** `data-save-state` to be `idle`. Don't click before both hold, or you'll fire at the previous video's panel.
   - **`idle` is necessary but NOT sufficient — the panel lies.** It remounts on `yt-navigate-finish` while YouTube is still mid-swap. Also wait for the page to settle (`document.title` reflects the new video) and for the previous video's segments to clear. Clicking too early either 400s YouTube's transcript API (permanent spinner → `error`) or harvests the previous video's leftover segments and saves them under this video's ID (**silent corruption**). A couple of seconds of patience per video prevents both.
   - Click the button, then poll `data-save-state` until `saved` or `error` (cap ~60s).
   - Record: id, title, terminal state, `data-error-msg`.
4. **Report a table** at the end: id / title / state / error, plus counts and a list of anything needing a human.

Prefer one `javascript_tool` call that clicks and polls to terminal in a single round-trip — a save takes ~2.7s, so a call per poll is pure overhead. `javascript_tool` output is **blocked if it contains the page URL/query string**: read `location.search` internally, never return `location.href`.

## Errors

**`error` is normal and expected sometimes** — plenty of videos genuinely have no transcript. Do not treat it as failure of the run. Record it and move on.

**Retry once**, in place, before recording a failure — the panel is idempotent so a retry is free.

**Watch for the known 400 signature**: "Could not find transcript segments" with the transcript panel stuck on a spinner, on a video reached by SPA nav. This is an **open, unfixed bug** (see CLAUDE.md "ROOT CAUSE FOUND"): clicking too soon after navigation POSTs a stale continuation token and `POST /youtubei/v1/get_transcript` returns **400**. Confirm with `read_network_requests` (`urlPattern: "transcript"`) rather than guessing from the DOM. Waiting longer before clicking, or retrying, may clear it — the token becomes valid once YouTube finishes the swap.

**Never write a DOM-level fix for a spinner without checking the request first.** Three such fixes were attempted and all failed; one silently corrupted a record.

Distinguish the two before reporting: a video with no transcript has no "Show transcript" control; a stale-panel failure has one, plus an expanded panel that never populates. If several consecutive videos fail, stop and reassess rather than continuing — that's a systemic signal, not bad luck.

**If a browser tool fails 2–3 times, stop and report.** Don't loop.

## Don't

- Don't reload between videos. Don't use `navigate` to move through the queue.
- Don't delete or edit records to "clean up" a failed save — the error path writes nothing, so there's nothing to clean.
- Don't build queue/retry logic into the extension. It lives here, with you.
