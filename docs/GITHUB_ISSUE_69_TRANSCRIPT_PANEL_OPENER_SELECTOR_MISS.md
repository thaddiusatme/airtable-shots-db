# GH-69: `openTranscriptPanel()` fails silently on videos with a valid transcript, no network request ever fires

## Summary

`extractTranscript()` in `content.js` returns `"Could not find transcript segments"` for videos
that **do** have a transcript and **do** render a working "Show transcript" control — the panel-
opening step (`openTranscriptPanel()`, Strategy 2) never actually triggers YouTube's transcript
fetch. This is a different failure from GH-67 (modern variant segment parsing) and from the
documented GH-68 stale-token 400: no `get_transcript` network request is made at all, on a fresh
page load, with the page fully settled.

## Repro

1. Load `https://www.youtube.com/watch?v=itlpAqVbC3U` fresh (full page load, not SPA nav).
2. Confirm `document.querySelector('ytd-video-description-transcript-section-renderer')` is
   truthy — the description-area transcript section is present in the DOM.
3. Wait 12s+ for the page to fully settle (ruled out as a timing issue — see below).
4. Click `[data-testid="extract-save-btn"]` (or call `extractTranscript()` directly).
5. Panel reaches `data-save-state="error"`, `data-error-msg="Could not find transcript segments.
   Try manually clicking \"Show transcript\" first, then extract again."`
6. `read_network_requests` filtered on `get_transcript` returns **zero matches** for the entire
   click-to-error window.

Confirmed on two consecutive videos in the same playlist (`itlpAqVbC3U`,
`5WB5bcGNib8`) during an unattended `scheduled-playlist-harvest` run on 2026-07-22. A third video
in the same playlist, same run, same environment (`bj04doEDOY4`) succeeded normally (segments
found, saved, verified in Airtable) — so this isn't an environment-wide fault (extension not
loaded, credentials, etc.), it's video/page-state-dependent.

## Root cause (read the code, don't guess)

`openTranscriptPanel()` (`content.js:31-91`) is a five-strategy waterfall. Strategy 2
(`content.js:43-49`) is the one that matters here:

```js
const descriptionButtons = document.querySelectorAll('ytd-video-description-transcript-section-renderer button');
if (descriptionButtons.length > 0) {
  descriptionButtons[0].click();
  await new Promise(resolve => setTimeout(resolve, 1500));
  return true;
}
```

This returns `true` — "opened" — the moment it finds *any* `<button>` inside
`ytd-video-description-transcript-section-renderer` and clicks it, with **no check that the click
actually revealed a transcript panel or produced any segments**. `extractTranscript()`
(`content.js:117-124`) trusts that `true` and moves straight to `waitForSegments`, which polls
`collectSegments(document)` for 5s and gives up.

Two ways this goes wrong, both consistent with the observed symptom (no network call at all):

1. **Wrong button matched.** `ytd-video-description-transcript-section-renderer` can contain more
   than one `<button>` in the current YouTube layout (e.g. an expand/collapse "…more" toggle
   alongside the actual transcript trigger). `descriptionButtons[0]` isn't guaranteed to be the
   transcript control — clicking the wrong one produces no transcript request and no visible
   error, since the click still "succeeds" from `openTranscriptPanel()`'s point of view.
2. **Stale/detached button reference.** Nothing here re-queries after YouTube's own async
   description-section render finishes. If the section renderer exists in the DOM but hasn't
   finished wiring its click handler yet, `.click()` is a no-op — and unlike the GH-68 stale-token
   case, this fails *before* any request is issued, not after a 400.

Either way, the defect is the same: **`openTranscriptPanel()` conflates "found and clicked
something" with "the transcript panel actually opened."** There is no verification step between
the click and the `return true`.

## Why this isn't GH-67 or GH-68

- **Not GH-67** (fixed): that was `SEGMENT_SELECTORS` failing to match the modern
  `transcript-segment-view-model` row markup once segments existed in the DOM. Here, segments
  never arrive at all — `collectSegments()` is never given anything to match against.
- **Not the GH-68 stale-token 400**: that bug requires a `get_transcript` POST to actually fire
  and come back 400, and only reproduces after SPA navigation with a stale continuation token.
  This repro is a **fresh full page load** (the documented mitigation for GH-68) and **no request
  fires at all** — confirmed via `read_network_requests` with tracking enabled from before the
  click. Longer settle time (12s vs. the skill's normal wait) made no difference, which also rules
  out a simple render-race explanation on its own — Strategy 2's blind `descriptionButtons[0]`
  assumption fits the evidence better than timing.

## Impact

- Silent-ish data-completeness gap: affected videos report a clean, specific error
  (`data-save-state="error"`) rather than corrupting data — the existing corruption guard (GH-68
  provenance / fast-`saved` tripwire) is not implicated here. But per `scheduled-playlist-harvest`
  policy, **two consecutive identical errors correctly halted an unattended run**, which is the
  designed behavior — this issue is why that tripped, not a flaw in the tripwire.
- Any video where YouTube renders more than one `<button>` inside
  `ytd-video-description-transcript-section-renderer`, or where that section's click handler isn't
  wired by the time Strategy 2 runs, will hit this.

## Suggested fix direction (not yet attempted — flagging per project policy against live DOM fixes)

1. **Verify, don't assume, after the click.** After Strategy 2 clicks `descriptionButtons[0]`,
   poll (like `waitForSegments` already does) for either segments appearing *or* a
   `get_transcript` network request being observed, before returning `true`. If neither happens
   within a short timeout, fall through to Strategy 3/4/5 instead of stopping.
2. **Disambiguate the button** inside `ytd-video-description-transcript-section-renderer` by
   `aria-label`/text content (`"show transcript"`) rather than blindly taking index `[0]`, so an
   unrelated button in that section doesn't get clicked instead.
3. Consider surfacing the distinction between "no button found" (page genuinely has no transcript)
   and "button found + clicked but panel never opened" (this bug) in the error message /
   `data-error-msg`, so future triage doesn't have to re-derive it from network logs by hand.

**Do not** attempt a same-session DOM patch without following `verify-panel` afterward — the
project's own history (`CLAUDE.md`, "Failed fix attempts 2026-07-17") shows a broken
`closeTranscriptPanel()` fix silently overwrote a real Airtable record (`recoYXkJNQIykIckl`) by
harvesting stale document-wide segments. Any fix here should be verified against a live run before
trusting `saved` states again.

## Evidence log

- Repro session: unattended harvest of playlist `PLVwTAkoVGJsY` ("AI (Claude)"), 2026-07-22.
- `itlpAqVbC3U` — "The New Workflows Agent Deserves More Than a Two-Star Rating": error both on
  first attempt and on a same-video retry with a full reload + 12s extra settle time. Zero
  `get_transcript` requests observed either time.
- `5WB5bcGNib8` — "Anthropic Just Published the Playbook for Loops That Run Themselves": error on
  first attempt (retry not separately isolated before the run was halted per the
  consecutive-failure policy).
- `bj04doEDOY4` — "Claude Just Changed Completely: Here's How It Works (In 2026)": succeeded
  cleanly in the same run, same environment — 3.7s extract+save, verified in Airtable, drained
  from the playlist. Rules out an environment-wide cause.
- Both failing videos confirmed to have `ytd-video-description-transcript-section-renderer`
  present in the DOM (`hasTranscriptSection: true`), so this is not the "video has no transcript"
  case the current error message assumes.

## Additional repro (2026-07-23) — third playlist, confirms not a one-off

Reproduced again during an unattended `scheduled-playlist-harvest` run against playlist
`PLZ8PtMY63lo86BcUEo__5Y2bT6fr_iIhd` ("Business & Productivity"), a different playlist from the
original GH-69 repro (`PLVwTAkoVGJsY`, "AI (Claude)") and a day later — rules out both
"one bad playlist" and "one bad session."

- `1D7RsOVC-lE` — "Business is a video game. Here's how to win." — `error`, same
  `data-error-msg`, on both the first attempt and a same-video full-reload retry.
- `eY9gpdaXW7w` — "Business is Hard Until You Build These Systems" — `error`, same message, on
  both the first attempt and a same-video full-reload retry. Confirmed via `find` that a
  "Show transcript" button genuinely exists on this page (two matches, likely the same
  index-`[0]`-vs-real-control ambiguity Strategy 2 already suspects) — so this is the same
  "button found, panel never opened" failure mode, not a no-transcript video.
- Two consecutive identical failures correctly halted the unattended run per
  `scheduled-playlist-harvest` policy before reaching the remaining 3 videos in the playlist
  (`_ahTP_Zn7nU`, `xBD73v3fXNQ`, `N6Mf0cutEeI` — untouched, transcript status unknown). Playlist
  left undrained, nothing saved or removed.
- Network tracking was not enabled from before the click on this run, so no fresh
  `get_transcript`-absence confirmation was gathered this time — the DOM evidence (button present,
  segments never found) is consistent with the original finding but this run doesn't independently
  re-confirm the "zero network requests" detail.

Net: this remains reproducible across playlists and days. Priority for a fix (see "Suggested fix
direction" above) should go up accordingly — it's not a rare edge case tied to one video or one run.

## ACTUAL ROOT CAUSE FOUND (2026-07-23, via live Claude-in-Chrome testing)

The "Suggested fix direction" above (disambiguate the button, verify after click) was implemented
in `content.js` — correct button targeting by label instead of blind `descriptionButtons[0]`, a
poll that verifies segments actually appear before trusting a click, and a single-candidate
patient-wait design (35s) instead of fanning out across multiple different buttons. All of that is
a real improvement and stayed in the code. **But it was not the actual fix**, and extensive live
retesting exposed why.

**The real defect: a scripted click never triggers YouTube's transcript request at all — a real
trusted click does, every time.** Live testing (Claude in Chrome) produced dozens of clean,
correctly-targeted attempts via `javascript_tool`'s `.click()` (or any synthetic DOM method) on the
verified-correct "Show transcript" button, across multiple unrelated videos, with timeouts pushed
as high as 90s+. Every one failed the same way: `read_network_requests` (`urlPattern:
"get_transcript"`) showed **zero requests**, ever — not a 400, not a slow response, nothing. The
button's own click handler visibly ran (DOM state changed as expected), but nothing downstream of
it fired.

The moment the *identical* button, on the *identical* video, in the *identical* browser
session/cookies, was clicked with a **real, trusted mouse event** — either the user clicking it by
hand, or Claude in Chrome's `computer` `left_click` tool — it worked immediately and reliably.
Confirmed on `1D7RsOVC-lE` (1214 real segments, saved cleanly) and `eY9gpdaXW7w` (982 segments,
truncation-warned save) — both videos that had failed **every single scripted-click attempt** made
against them earlier the same session.

This is consistent with an anti-automation gate tied to genuine browser user activation (YouTube
declining to serve `get_transcript` unless triggered by what it can tell is a real user gesture),
not a DOM, selector, or timing bug. It explains the entire GH-69 symptom set retroactively: the
original `scheduled-playlist-harvest` repro runs (2026-07-22, 2026-07-23) that motivated this doc
were unattended automation — if that automation triggered the button via a scripted method rather
than a real input event, every video would show exactly the observed signature ("found and clicked
a valid control, zero segments, zero network requests"), regardless of which video, which
selector, or how long it waited. No amount of retry/timeout tuning in `content.js` could have
fixed this, because the defect was never in the extension's DOM code — it was in *how the click was
delivered*.

**Fix**: `harvest-playlist` and `verify-panel` (both under `.claude/skills/`) now mandate a real
`computer` `left_click` to trigger the Extract & Save button (and playlist sidebar navigation) —
never `javascript_tool` or any scripted `.click()`/`dispatchEvent` call. `javascript_tool` remains
correct and preferred for everything read-only (polling `data-save-state`, reading
`data-error-msg`, checking Airtable). This is a **procedural fix for agents driving the panel**, not
a code change — `content.js` cannot detect or work around this from the inside, since the gate
appears to live in YouTube's own request-handling, outside anything the extension's content script
controls.

**Open question**: whether this is truly a deliberate anti-bot gate, some transient/environmental
effect of the very high volume of repeated test traffic against these specific videos in one day,
or something else entirely. Not resolved — flagging as unconfirmed. What's confirmed is the
practical mitigation (use real clicks) and that it reproduces reliably in the failing direction
(scripted click → silent no-op) and the working direction (real click → success) on the same
video/session.

## Not filed to GitHub

This is a local markdown writeup only, matching the existing `docs/GITHUB_ISSUE_*` convention in
this repo (see `GITHUB_ISSUE_CHROME_EXTENSION_TRANSCRIPT.md` et al.) — no GitHub issue has actually
been opened. File it as GH-69 if/when triaged.
