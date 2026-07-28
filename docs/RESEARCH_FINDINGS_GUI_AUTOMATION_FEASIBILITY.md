# Research findings: feasibility of OS-level GUI automation for the transcript harvest loop

Answers the questions posed in `RESEARCH_PROMPT_GUI_AUTOMATION_FEASIBILITY.md`, in response to
`GITHUB_ISSUE_70_CLICK_DELIVERY_UNRELIABLE_CDP_AUTOMATION.md`. Findings below are from an external
AI research pass (2026-07-27) — not independently verified against Chromium source or tested live.
Treat as a strong, sourced starting point, not settled fact.

## Bottom line

The hypothesis (OS-level input avoids whatever CDP input is triggering) is **mechanistically
plausible** but **not proven for this specific case**. Two distinct, real mechanisms could explain
GH-70's failure mode 3 (correct element, correct coordinates, listener never fires):

1. `event.isTrusted` — depends on *which* CDP call was used. `Input.dispatchMouseEvent` (browser-
   layer injection) is documented to produce `isTrusted: true`; a scripted `.click()` or
   `dispatchEvent()` via `Runtime.evaluate` (page-JS layer) is `isTrusted: false` by spec. **This is
   a concrete thing to check against our own click history** — Claude in Chrome's `computer` tool
   should be using the trusted path, but this is worth confirming, not assuming.
2. **CDP-attachment detection, independent of any single event's trust flag** — `navigator.webdriver`,
   a documented `Runtime.enable` console-preview leak (patched partially in V8 as of May 2026, but
   the general class of "enabling a CDP domain changes observable page behavior" isn't closed by
   one patch), and other CDP-domain side effects. If YouTube's page JS branches on any of these
   before our click lands, the *listener's own guard clause* — not the click — is what silently
   swallows it. This fits GH-70's symptom (zero console output from our own handler) better than a
   simple "click missed" explanation.

Nobody has reverse-engineered YouTube's specific detection logic publicly. Both mechanisms are
well-documented for automation-detection generally; neither is confirmed as *the* cause here.

## Recommended next step before any rebuild

**Cheap diagnostic, not a rebuild**: launch Chrome manually with zero CDP/remote-debugging flags
(no Claude in Chrome, no automation attach at all), and use a one-off AppleScript or Quartz test
script to click the Extract & Save button on 5-10 videos, including `ovabeVoWrA0` specifically.
If the failure modes disappear, the hypothesis holds and a rebuild is justified. If they don't,
something else is going on (rate limiting, a race condition in our own extension, backend
flakiness unrelated to automation detection) and the rebuild wouldn't fix the actual problem.

## Implementation recommendation, if the diagnostic confirms the hypothesis

Ranked by the research:

1. **AppleScript System Events targeting Chrome's accessibility tree** (click a named UI element,
   not raw pixel coordinates) — most robust to window movement/resize, lowest maintenance. Requires
   Chrome's accessibility support to be exposing page elements (check `chrome://accessibility/`).
2. **Fallback: native Quartz/CoreGraphics event injection via `pyobjc`**
   (`CGEventCreateMouseEvent`/`CGEventPost`) if AX-tree targeting proves unreliable against Chrome's
   specific tree. Most control over event fields, no abstraction layer between us and the OS input
   pipeline. This is what `pyautogui`/`pynput` wrap anyway — going direct avoids their abstraction.
3. Both require macOS Accessibility permission granted to whichever exact executable/process
   invokes the API (bare Python binary vs. `.app` bundle vs. Terminal all count as different
   grantees — this has tripped people up when the launch method changes).
4. Both need a **real, logged-in, unlocked GUI session** — not headless, not Xvfb. This is an OS
   policy constraint, not a library limitation, and applies identically whether running locally or
   on a VM later.

## VM feasibility

Realistic, with the same "real session" caveat as above:

- **macOS VM**: Apple's Virtualization framework (UTM, Parallels/VMware on Apple Silicon) presents
  a real virtual display + input stack indistinguishable from physical hardware to the guest OS.
  AWS EC2 Mac instances (`mac1`/`mac2`, Dedicated Host only) are the mature "real Mac in the cloud"
  route, with documented VNC/Screen Sharing GUI access — but billed on a 24-hour minimum allocation
  per Apple's licensing terms, which is a real cost for a personal project.
- **Linux VM**: a real Xorg/Wayland session (not Xvfb) accessed via VNC/RDP, with input driven by
  `pynput`/`xdotool` against that real session, should be architecturally equivalent to physical
  hardware from Chrome's perspective — but this exact claim hasn't been independently verified
  against `isTrusted`/bot-detection in the research pass. Treat as reasoned, not proven.
- The distinction that matters is "real windowing/compositing + real input backend exists," not
  "VM vs. physical." Xvfb specifically lacks this and is why CI pipelines are a weaker signal
  environment — don't reach for it here.

## Two things to weigh before committing engineering time

**ToS risk exists independent of the technical fix.** YouTube's API Services Developer Policies
explicitly prohibit scraping and undocumented-API use, regardless of how human the automation
looks. Solving click-reliability doesn't reduce this exposure — it only affects whether the click
technically succeeds. Enforcement against small personal/non-commercial use is inconsistently
reported (some tolerance, some real rate-limiting/blocking), not something to bank on either way.

**A much simpler alternative may sidestep the whole problem**: if the actual goal is "get
transcript text into Airtable" rather than "automate our extension's UI" specifically, calling the
`timedtext`/caption-fetch endpoint directly via HTTP (as `youtube-transcript-api` and similar
libraries do) removes the click-delivery question entirely — there's no click to deliver. This
carries its own version of the undocumented-endpoint ToS exposure noted above, so it's not risk-
free, but it removes the CDP-vs-OS-input problem as a category. Worth evaluating before building
GUI automation of any kind: keep the extension/UI path only as a fallback for cases where a direct
`timedtext` call fails.

## Open items not resolved by this research pass

- Whether the diagnostic test (manual Chrome, zero CDP, real OS click) actually fixes `ovabeVoWrA0`
  — the load-bearing test from `GITHUB_ISSUE_70` is still unrun.
- Whether AX-tree "press" actions on Chrome's accessibility elements produce genuinely OS-level
  trusted input, or whether Chromium's own AXPress handling re-synthesizes a page-layer event that
  could reintroduce the same `isTrusted` question — flagged by the research as an unverified risk
  specific to the AppleScript/AX approach.
- No independently-tested confirmation that a real (non-Xvfb) Linux VM session is treated
  identically to physical hardware by Chrome/YouTube.

## Sources

Not independently verified by us — see the original research response for citation numbers.
Covers: `isTrusted` spec behavior, CDP `Runtime.enable` console-preview leak (V8, patched partially
2026-05), `navigator.webdriver`, Apple Developer documentation on Accessibility-gated `CGEventPost`
(macOS 10.14+), AWS EC2 Mac instance VNC setup docs, YouTube API Services Developer Policies
(scraping prohibition), and general RPA/anti-detect industry context for "real hardware/session"
browser automation.
