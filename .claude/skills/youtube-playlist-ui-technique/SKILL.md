---
name: youtube-playlist-ui-technique
description: Browser-automation technique reference for reliably driving YouTube's video-page "Save to..." panel and a Watch Later row's action menu — the low-level clicking mechanics, not classification logic. Use alongside the watch-later-sort skill (which owns what to classify a video as) whenever actually executing a sort: a Save-to-playlist click that appears to do nothing, a Watch Later row's three-dot menu not opening on the first click, or needing to verify a playlist checkbox is really selected. Also applies to any other task that adds a video to a playlist and/or removes one from Watch Later via the browser.
---

# YouTube Save-panel and Watch Later row technique

Learned from a live 21-video watch-later-sort run (2026-08-05) that moved 15 videos into three
business playlists. The classification skill (`watch-later-sort`) gets the destination right; this
skill is about the mechanical reliability of actually clicking it, which failed in several
non-obvious ways during that run.

## Opening the Save panel

- The **Save** button's y-coordinate on a video watch page is not fixed — it shifts depending on
  whether the channel shows a **Join** button next to **Subscribe** (channels with memberships).
  Screenshot after the page settles and locate Save precisely each time; don't hardcode a coordinate
  across videos.
- The watch page needs roughly 2-3 seconds after navigation to finish hydrating. A click issued too
  early can land on the video player itself (visible in the screenshot as a stray click dot mid-frame)
  and silently do nothing. Wait, then screenshot, then click — don't chain navigate+click in one
  batch without a wait in between.

## Selecting the right playlist row

- The panel lists the **business-owned** destination and the **personal source** playlist under the
  *identical visible title*. Disambiguate by the subtitle: the business copy reads `Unlisted •
  Collaborative`; the personal copy reads `Unlisted` alone. This confirms the guidance already in
  `watch-later-sort` — but note it also holds when the panel re-sorts recently-touched rows to the
  top after a click, so re-read the subtitle every time rather than trusting row position.
- It's normal to see a video's *personal*-playlist checkbox already filled in when you open the
  panel — the same video can independently already belong to a personal category playlist. Leave
  those alone; only ever click the business row.
- **Don't trust `find`'s reported "Selected"/"Not selected" state.** It was observed stale multiple
  times this session — reporting "Not selected" on a row immediately after a click that, per a
  visual check, had actually succeeded. Verify by `zoom`-screenshotting the panel region instead and
  checking whether the row's bookmark icon is solid/filled (selected) versus an outline (not
  selected). Treat the accessibility-tree label as a hint at best, the icon fill as ground truth.
- **Never press Escape to close the panel.** It silently reverts the checkbox you just set — a
  click-then-Escape sequence can look successful (the panel closes) while the selection never
  persisted. Close the panel by clicking the **Save** button again at the same coordinates (it
  toggles closed), not by hitting Escape or clicking elsewhere.

## Removing a video from Watch Later

- On the Watch Later list page, the row's three-dot "Action menu" button frequently needs **two**
  clicks at the same coordinate: the first only paints the hover-state icon without opening the
  menu, the second actually opens it. Always screenshot after the click to confirm the menu (with
  "Remove from Watch later" visible) is open before clicking a menu item.
- If you skip that confirmation and the menu wasn't actually open, the click meant for "Remove from
  Watch later" can land on the video title link underneath instead and navigate to the video's watch
  page. This isn't destructive, but it wastes a round trip and can be mistaken for a completed
  removal if you don't check the resulting URL/title. `navigate` back to `list=WL` and retry.

## Verifying state, not assuming it

- After any add or remove, re-navigate fresh to the playlist URL (`list=WL` or the destination
  playlist) and re-fetch rather than trusting the in-page state right after the click — the "N
  videos" header count can lag the actual DOM update by one render cycle if read immediately.
- **Correction, 2026-08-06 — the "duplicate item at the end of the list" pattern is NOT reliably a
  rendering artifact.** An earlier draft of this skill claimed `get_page_text` appending a duplicate
  of the last item or two was cosmetic virtualization noise, safe to ignore. That was wrong, and
  believing it delayed catching a real bug: cross-checking against the actual YouTube Data API
  (`playlistItems.list`, ground truth — not scraped HTML) after a 15-video sort found that **12 of
  13 adds to one playlist were genuinely double-added** (two distinct `playlistItemId`s, same
  `videoId`), and one video had been accidentally added to the *wrong* playlist entirely during
  early trial-and-error on the technique. The header's "N videos" count does **not** by itself tell
  you whether a specific video got added once or twice — it just tells you the total changed by
  roughly the right amount, which a double-add plus a missed add can coincidentally still satisfy.
  If a queue is large enough to matter, don't stop at eyeballing `get_page_text` or trusting the
  header count arithmetic — do a real per-`videoId` duplicate check against the API (group playlist
  items by `videoId`, look for any group with more than one entry) before treating a batch as clean.
  In this repo that's cheap: `playlist-drain/playlist-manager.js`'s `listPlaylistItems()` returns raw
  items including `playlistItemId`, so a short one-off script grouping by `videoId` answers this
  directly, read-only, no browser involved.
- The practical mitigation, not just detection: after clicking a business-playlist checkbox in the
  Save panel, the panel can re-render/reorder its rows (observed happening after some clicks). A
  second stray click intended for something else (e.g. re-opening the panel to verify, or a retry
  after an earlier click seemed not to register) can land on a checkbox that's already selected,
  which YouTube may treat as "add again" rather than a no-op toggle for a multi-add panel. Prefer
  fewer, more deliberate clicks over "click a few times to be sure" — each click on an
  already-selected row is a live risk, not a free retry.

## Checkpoint discipline

For a queue of more than a handful of videos, verify the destination playlist's total count against
arithmetic expectation every 3-5 videos (not just at the end) — catching a missed click after 3
videos is a much smaller cleanup than after 15.
