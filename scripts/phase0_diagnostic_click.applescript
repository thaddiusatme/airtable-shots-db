-- Phase 0 diagnostic click (GH-70 / click-delivery redesign, Fork A)
--
-- PURPOSE
-- Test whether a REAL OS-level click — via macOS's own System Events, with
-- ZERO Chrome DevTools Protocol / Claude in Chrome / any automation attached
-- to the browser — succeeds on the extension's "Extract & Save" button where
-- 6 different CDP-driven "real" clicks failed against ovabeVoWrA0.
-- See docs/GITHUB_ISSUE_70_CLICK_DELIVERY_UNRELIABLE_CDP_AUTOMATION.md and
-- docs/PROJECT-MANIFEST-click-delivery-redesign.md (Section 3, Phase 0) for
-- the full context. This script IS that diagnostic — nothing more.
--
-- WHY THIS HAS TO BE RUN BY YOU, NOT BY CLAUDE
-- Claude cannot run this itself: browser automation must go through the
-- Claude in Chrome tools (which are CDP-based — the exact thing this test
-- needs to be absent), and Claude's separate "computer use" desktop-control
-- tools are policy-restricted from operating a browser at all. There's also
-- no path from Claude's sandboxed environment to your actual screen. This is
-- a genuine "human runs the diagnostic, reports back" step.
--
-- REQUIRES
-- The application actually running this script (Terminal, if you invoke it
-- via `osascript`; or Script Editor if you run it from there) must have
-- Accessibility permission: System Settings > Privacy & Security >
-- Accessibility > enable Terminal (or Script Editor).
--
-- BEFORE RUNNING
--   1. Fully quit/disconnect Claude in Chrome so Chrome has ZERO CDP or
--      remote-debugging attached. Check chrome://inspect shows nothing
--      connected. This is the whole point of the test — if CDP is still
--      attached, the result doesn't tell us anything.
--   2. In a normal Chrome window (not one Claude has ever driven this
--      session), navigate to the target video, e.g.:
--        https://www.youtube.com/watch?v=ovabeVoWrA0
--      Wait for the floating "Extract & Save" panel (bottom-right) to show
--      "Idle".
--   3. Find the button's actual SCREEN coordinates (not page/DOM coordinates
--      — this script clicks a physical point on your display). NOTE: Digital
--      Color Meter does NOT show x/y coordinates (it only reads pixel color);
--      an earlier version of this comment was wrong about that. Instead, the
--      most reliable way is to compute it from the page, in the DevTools
--      console on the target tab:
--        var el = document.querySelector('[data-testid="extract-save-btn"]');
--        var r = el.getBoundingClientRect();
--        JSON.stringify({
--          x: Math.round(window.screenX + r.x + r.width/2),
--          y: Math.round(window.screenY
--               + (window.outerHeight - window.innerHeight)
--               + r.y + r.height/2)
--        })
--      WINDOW HYGIENE (these cost a whole session on 2026-07-27):
--        - Docking/undocking DevTools CHANGES the window bounds, which
--          invalidates coordinates computed before the change. Compute the
--          coordinates in the exact window layout you will click in.
--        - An UNDOCKED DevTools window becomes Chrome's `front window` for
--          AppleScript. Verify with:
--            osascript -e 'tell application "Google Chrome" to get bounds of front window'
--          and make sure it matches the browser window, not a DevTools panel.
--
-- USAGE
--   osascript phase0_diagnostic_click.applescript <x> <y>
--
-- EXAMPLE
--   osascript phase0_diagnostic_click.applescript 1308 819
--
-- AFTER RUNNING
-- Check the result one of two ways:
--   (a) Look at the panel on screen — did it change from "Idle" to
--       "Extracting..." / "Saving..." / "Saved"?
--   (b) Open DevTools Console (this doesn't attach CDP the way Claude in
--       Chrome does — it's the same as any human opening DevTools) and run:
--         document.getElementById('yt-transcript-panel').dataset.saveState
--
-- Run this against BOTH ovabeVoWrA0 (the known-failing video) and at least
-- one video that worked fine before (e.g. J_jswzXhYJA), so we have a
-- control. Record both results in
-- docs/PROJECT-MANIFEST-click-delivery-redesign.md Section 3.
--
-- ============================================================================
-- KNOWN LIMITATION — READ BEFORE RUNNING (found 2026-07-27)
-- ============================================================================
-- This script's `click at` DOES NOT WORK against Chrome. It was run against
-- ovabeVoWrA0 with verified-correct coordinates and confirmed Accessibility
-- permission, and produced ZERO click events on the page — verified with a
-- capture-phase click listener that successfully logged a real physical click
-- (isTrusted:true) moments earlier. The same `click at` drives TextEdit
-- correctly, so the permission and coordinate space are fine; the events just
-- don't reach Chrome's render surface.
--
-- Therefore this script CANNOT currently answer the GH-70 question, and a
-- null result from it means nothing about YouTube or CDP. Next attempt should
-- use Quartz/CoreGraphics injection via pyobjc (CGEventCreateMouseEvent +
-- CGEventPost), which the research findings already ranked higher.
--
-- Verification rig that DOES work, and is worth reusing (CDP-free):
--   Install a listener (persist to localStorage — JS globals do NOT survive
--   between separate `execute javascript` calls):
--     osascript -e 'tell application "Google Chrome" to execute active tab of front window javascript "localStorage.setItem(\"clickLog\", JSON.stringify([])); document.addEventListener(\"click\", function(e){ var l = JSON.parse(localStorage.getItem(\"clickLog\")||\"[]\"); l.push({x:e.clientX,y:e.clientY,target:e.target.tagName,trusted:e.isTrusted}); localStorage.setItem(\"clickLog\", JSON.stringify(l)); }, true); \"ok\""'
--   Read it back after a click attempt:
--     osascript -e 'tell application "Google Chrome" to execute active tab of front window javascript "localStorage.getItem(\"clickLog\")"'
--   Requires: Chrome > View > Developer > Allow JavaScript from Apple Events.
--   An empty array means the click never arrived at the page at all.
-- ============================================================================

on run argv
	if (count of argv) is not 2 then
		error "Usage: osascript phase0_diagnostic_click.applescript <x> <y>"
	end if
	set xCoord to (item 1 of argv) as integer
	set yCoord to (item 2 of argv) as integer

	tell application "Google Chrome" to activate
	delay 1

	tell application "System Events"
		-- "click at" posts a real OS-level mouse event at the given screen
		-- coordinates. This goes through the same input pipeline a physical
		-- click would (CoreGraphics/Quartz event injection under the hood) —
		-- no CDP, no browser automation layer, no Claude in Chrome involved
		-- at any point in this call.
		click at {xCoord, yCoord}
	end tell

	return "Clicked at " & xCoord & ", " & yCoord & ". Now check the panel's state (see AFTER RUNNING above)."
end run
