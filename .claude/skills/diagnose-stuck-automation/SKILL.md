---
name: diagnose-stuck-automation
description: Systematic checklist for when a Claude-in-Chrome action (click, form fill, etc.) appears to do nothing — the element is found and "clicked" but nothing observable happens, or a spinner never resolves. Use before writing a DOM-level fix or tuning retries/timeouts. Triggers on "click doesn't do anything", "automation isn't working", "stuck spinner", "the button click seems to be a no-op", "not sure why this action isn't registering", or repeated identical failures across multiple attempts/targets.
---

# Diagnose a stuck browser automation

Born from a real multi-hour debugging session (GH-69, `youtube-panel-triage`) where the actual
defect (scripted clicks lack real user activation) was buried under an hour of chasing selector and
timing theories that were never the problem. Run this checklist **before** touching selectors,
retries, or timeouts — most of that tuning is wasted effort if the real issue is one of the four
below.

## The four things to check, in order

### 1. Is the click landing where you think it is?

Screenshot pixel coordinates are **not** guaranteed to equal the page's CSS pixel coordinates —
`window.innerWidth`/`innerHeight` and `devicePixelRatio` can put a real scale factor between them.
Don't eyeball a screenshot and click raw coordinates on a precision target. Instead:

- Prefer `find` (returns a `ref`) and click by ref, or `read_page` for a ref — both sidestep the
  coordinate math entirely.
- If you must use coordinates, verify first: get the element's `getBoundingClientRect()` via
  `javascript_tool`, compute its center, and confirm `document.elementFromPoint(cx, cy)` actually
  returns the element you expect. If the screenshot is a different pixel size than
  `window.innerWidth`/`innerHeight`, scale: `screenshot_coord = css_coord * (screenshot_width /
  window.innerWidth)`.
- A click that produces *zero* observable effect, repeatedly, on an element you've confirmed exists
  and is visible, is a strong sign the coordinates are off — not that the target is broken.

### 2. Is a scripted click actually equivalent to a real one, for this target?

Some components (anti-bot gates, gesture-recognizer UI libraries, autoplay-style APIs) behave
differently for a synthetic `.click()`/`dispatchEvent` than for a genuinely trusted input event —
even though the DOM handler visibly runs in both cases. If a scripted click "succeeds" (no error,
handler fires) but nothing downstream happens, **isolate trust as a variable**:

- Try the identical element with a real `computer` `left_click` instead of `javascript_tool`'s
  `.click()`.
- If the real click works and the scripted one doesn't, on the *same* element/page/session, that's
  your answer — stop tuning the scripted approach (more retries, longer timeouts, different
  selectors won't fix a trust gate) and switch to real clicks for anything that must actually work.
- This is easy to miss because the DOM looks identical either way — the handler runs, state may
  even update — but whatever the handler *triggers downstream* (a network request, in most real
  cases) silently never fires.

### 3. Use network requests as ground truth, not DOM/spinner state

A stuck spinner or a state that never leaves "loading" tells you nothing about *why* on its own —
guessing from DOM state alone produces plausible-sounding but wrong theories. Before the action you
want to observe, call `read_network_requests` (tracking only starts once the tool is first called,
so call it early) filtered to the relevant endpoint. Three outcomes, three different fixes:

- **Zero requests fired** → the click never triggered the underlying action at all. Check #1 and #2
  above — this is almost never a server-side or timing problem.
- **A request fired and failed** (4xx/5xx) → a real server-side rejection. Read the status and
  response; this might be stale auth/state, rate limiting, or a genuine bug — but it's a different
  class of problem from #1/#2, and no amount of client-side retrying the same broken request fixes
  it.
- **A request fired and is just slow** → a genuine timing/patience issue. This is the *only* one of
  the three where "wait longer" is the correct fix.

Don't skip this step and write a DOM-level workaround for a spinner — confirm which of the three
you're actually looking at first.

### 4. Watch for tool/environment artifacts that distort your own measurements

- **Background-tab timer throttling**: Chrome throttles `setTimeout`/`setInterval` in tabs that
  lose focus. If you're interleaving many separate tool calls with idle waits, a page-side loop
  coded to time out at N seconds can take dramatically longer in wall-clock time, inconsistently —
  this looks like flaky behavior but is a measurement artifact, not a real defect. If a coded
  timeout is being blown past by 2-3x unpredictably, suspect this before suspecting your logic.
- **The automation tool's own execution ceiling**: a single `javascript_tool` call has its own cap
  (commonly well under a minute) independent of any `await`/timeout logic inside the script you
  wrote. A legitimately long-running in-page operation can hit the *tool's* ceiling and error out
  even though the page itself is working fine — check state with a fresh, short follow-up call
  rather than treating a tool-level timeout as proof the page is broken.
- **Session/traffic contamination**: if you've hammered the same target dozens of times in one
  session (heavy manual + scripted testing), a sudden run of consistent failures across *multiple*
  unrelated targets may be self-inflicted rate limiting rather than a fix regression. Test against a
  target you haven't touched yet before concluding a fix doesn't work.

## When several consecutive attempts fail identically

Stop and reassess rather than continuing to tweak the same approach — that's a systemic signal
(one of the four things above), not bad luck on this particular element/page/video. Re-run the
checklist from #1 before trying another variant of the same fix.
