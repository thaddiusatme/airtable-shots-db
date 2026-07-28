# Research prompt: feasibility of OS-level GUI automation for the YouTube transcript harvest loop

Copy everything below the line into your AI assistant of choice.

---

## Context

I run a Chrome extension (Manifest V3, unpacked/personal build) that extracts YouTube video
transcripts and saves them to Airtable. It exposes an in-page floating button
("Extract & Save") on each YouTube watch page. Today this loop is driven by an AI agent
(Claude, via a Chrome-DevTools-Protocol-based browser automation tool) that navigates to each
video and clicks the button.

I've hit a wall: clicks delivered through Chrome DevTools Protocol (CDP) — whether dispatched as
a scripted `.click()` call or as a CDP-level synthetic mouse event meant to emulate a real click —
are **not reliably equivalent to a genuine OS-level mouse click**, and the gap shows up as several
different failure modes:

1. Sometimes the click fires a request to YouTube's backend (`get_transcript`) that comes back
   with an error, with no automatic retry.
2. Sometimes the click "runs" (the button's own JS handler never even logs that it fired) but
   produces zero network activity — as if the click never happened from the page's perspective.
3. In one confirmed case, a CDP-issued click landed on the exact correct DOM element (verified via
   `document.elementFromPoint()` immediately before clicking, and via `getBoundingClientRect()`
   confirming coordinates), was retried 6 different ways (plain click x5, double-click, click via
   an accessibility-tree element reference), and **never once triggered the element's own
   registered click listener** — confirmed by the complete absence of that listener's own
   `console.log` output, even with console tracking enabled from before the click.

I suspect this is either (a) Chrome exposing to the page/extension that it's under automation
control (e.g. via `navigator.webdriver` or similar signals) even when input is injected through
CDP, and something downstream (YouTube, or Chrome's own input pipeline) treating CDP-origin input
differently from OS-origin input, or (b) some other automation-detection mechanism I don't yet
understand. I have not confirmed the exact mechanism.

**My working hypothesis**: if I replace CDP-driven clicking with a Python script that drives the
**actual OS input stack** (real mouse events at the operating-system level — e.g. via `pyautogui`,
`pynput`, or platform-native input injection APIs — clicking real, unambiguous screen coordinates
on a real, focused, visible browser window), the click will be indistinguishable from a human's,
and all three failure modes above should disappear, because the thing that's different about CDP
input (whatever it is) won't be present.

**Eventual goal**: run this unattended on a VM. But the automation must still act on **the
machine's real display and real input devices** (a real virtual display with real synthetic input
at the OS level), not a headless browser or a virtual framebuffer (Xvfb) — because the entire
premise is that something distinguishes CDP-mediated input from OS-level input, and I don't know
whether a headless/Xvfb setup would preserve or destroy that distinction.

**Environment**: macOS (Sequoia-era), Chrome, an unpacked Manifest V3 extension already built and
working when driven by a real human click. Eventually intended to also run on a VM (platform not
yet decided — could be macOS, Linux, or Windows).

## What I need researched

Please research and report back on the following, with sources/citations where possible
(official docs, security research, GitHub issues, blog posts from people who've hit this exact
class of problem — not just general knowledge):

1. **Does OS-level input injection (pyautogui/pynput/native APIs) actually bypass whatever is
   distinguishing CDP input from real input in Chrome?** Is there documented behavior (from
   Chromium source, security research, or bot-detection vendors) showing that Chrome or a page can
   detect *how* an input event originated (CDP `Input.dispatchMouseEvent` vs. a real OS-level
   click), and that pages/sites act differently based on that distinction? I want to know if my
   hypothesis is even mechanistically plausible before betting a rebuild on it.
2. **What exactly can a webpage or Chrome extension detect about automation?** Cover
   `navigator.webdriver`, CDP-connection detection, Chrome's "automation controlled" banner/flags,
   and any other known signals — and clarify which of these would differ between "Claude in
   Chrome"-style CDP automation and a Python script clicking real screen pixels on the same browser
   with no CDP connection at all.
3. **Practical implementation options for OS-level GUI automation on macOS**, compared on
   reliability, permissions required (Accessibility/Screen Recording permissions on macOS),
   maintenance burden, and whether they can run unattended/headless-ish on a Mac (e.g. via a
   dedicated user session, `launchd`, VNC, or similar) versus requiring an actual logged-in GUI
   session with the screen unlocked:
   - `pyautogui`
   - `pynput`
   - macOS-native (`Quartz`/`CoreGraphics` event injection, e.g. via `pyobjc`)
   - Any other Python or scripting approaches worth considering (e.g. AppleScript driving System
     Events, or a hybrid).
4. **VM feasibility**: for whichever OS-level approach looks best, what's required to run it
   inside a VM such that the input is still "real" from the browser/page's perspective — i.e. a
   real virtual display + real synthetic input at the OS level, not headless Chrome and not
   Xvfb-only. Cover:
   - macOS VMs (e.g. via Apple's Virtualization framework, Parallels, VMware, UTM) — can they
     present a real display and accept real synthetic input the same way physical hardware does?
   - Linux VMs with a real X11/Wayland session (not Xvfb) — does synthetic input via `pynput`/
     `pyautogui` on a real X session read as "real" to Chrome the same way it would on physical
     hardware, or does running inside a VM/remote-display context introduce its own tells?
   - Whether cloud VM providers commonly used for this kind of workload (e.g. AWS, GCP,
     Hetzner, a dedicated Mac-mini-in-the-cloud provider) support a real GUI session suitable for
     this, and any known gotchas.
5. **Detection risk / ToS considerations**: is YouTube (or Google broadly) known to detect and
   penalize accounts that use OS-level automation for transcript scraping specifically, separate
   from the CDP-detection question above? I'd rather know this going in than find out later. I'm
   not asking for legal advice — just what's publicly documented or commonly reported by people
   doing similar YouTube automation.
6. **Prior art**: are there existing open-source tools or writeups of people building "click real
   pixels via OS input, driven by a script, to work around CDP-detectable automation" for browser
   automation generally (not necessarily YouTube-specific)? I'd like to avoid rebuilding something
   that already has known pitfalls documented elsewhere.

## What a good answer looks like

- Directly addresses whether the core hypothesis (OS-level input avoids whatever is happening with
  CDP input) is plausible, with the best evidence you can find either way — including if the
  answer is "no one knows" or "this is undocumented."
- A clear recommendation on which OS-level automation approach (of those in question 3) is most
  reliable and least effort for a solo developer to build and maintain, for macOS first.
- A clear statement on whether the VM goal is realistic with a real display + real synthetic input,
  and what the simplest viable setup would be.
- Flags anything that would make you personally hesitant to build this (fragility, ToS risk,
  maintenance burden, a much simpler alternative I haven't considered) rather than just answering
  the literal questions.

## What NOT to do

Don't write the implementation yet — this is a feasibility research pass only. I'll take the
findings and decide whether to proceed to an actual build.
