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
--      — this script clicks a physical point on your display):
--        - Open Digital Color Meter (Cmd+Space, type "Digital Color Meter" —
--          it ships with macOS, in /Applications/Utilities/).
--        - Hover your mouse over the CENTER of the "Extract & Save" button
--          (don't click).
--        - Read the x, y values shown in that app's window.
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
