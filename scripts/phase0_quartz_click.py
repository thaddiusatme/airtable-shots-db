#!/usr/bin/env python3
"""GH-70 Phase 0 diagnostic — CDP-free click injection via Quartz/CoreGraphics.

Replaces scripts/phase0_diagnostic_click.applescript, whose `click at {x,y}`
delivered NO events to Chrome at all (see docs/PROJECT-MANIFEST-click-delivery-
redesign.md §3). This posts real CGEvents on the HID event tap — the same path a
physical mouse takes — using ctypes against ApplicationServices. No pyobjc, no
pip install: pyobjc is only a wrapper around these same C functions.

WHAT THIS IS FOR
    Testing whether a click delivered with ZERO CDP/automation attached to Chrome
    behaves differently from the 6 CDP-driven clicks that failed on `ovabeVoWrA0`.
    The read-back channel is Chrome's `execute javascript` over Apple Events,
    which inspects the page WITHOUT attaching the very thing under test.

PREREQUISITES
    1. Chrome > View > Developer > Allow JavaScript from Apple Events  (must be on)
    2. Accessibility permission for whatever process runs this script.
       Per-process: a grant to Terminal.app does NOT cover another terminal.
       Check with:  ./scripts/phase0_quartz_click.py trusted

THE LADDER (run in this order — do not skip step 1)
    ./scripts/phase0_quartz_click.py trusted          # is Accessibility granted?
    ./scripts/phase0_quartz_click.py probe            # install the click listener
    ./scripts/phase0_quartz_click.py coords 'h1'      # screen coords of an element
    ./scripts/phase0_quartz_click.py click X Y        # inject the click
    ./scripts/phase0_quartz_click.py read             # what did the page see?
    ./scripts/phase0_quartz_click.py perf             # was get_transcript requested?

    Step 1 is plain page content, far from any button: does a Quartz click
    register in the page AT ALL? If it does not, the tool is broken again and the
    result says NOTHING about YouTube — fix the tool, do not touch the manifest's
    §4 decision gate. Only if a Quartz click registers on plain content AND THEN
    fails to trigger get_transcript at the Extract & Save button does §4 go live.

COORDINATE SPACE
    CGEvent global coords are in POINTS, origin top-left of the main display.
    `window.screenX/screenY` are the same space, so the math in `coords` is a
    direct sum — no devicePixelRatio scaling on Retina. Two things break it:
      - Page zoom != 100% (getBoundingClientRect returns CSS px, which stop
        matching points). `coords` refuses to run if zoom is not 1.
      - Docking/undocking DevTools changes the window bounds. Recompute coords
        AFTER any DevTools change; an undocked DevTools window also becomes
        Chrome's `front window` for Apple Events.

NOTE ON STATE
    JS globals do NOT survive between separate `execute javascript` calls — each
    call is its own evaluation. The listener therefore records into localStorage
    under LOG_KEY, which is why `probe` and `read` are separate commands.
"""

import ctypes
import ctypes.util
import json
import subprocess
import sys
import time

LOG_KEY = "gh70ClickLog"

# --- CoreGraphics / ApplicationServices bindings -----------------------------

_AS_PATH = ctypes.util.find_library("ApplicationServices")
if not _AS_PATH:
    sys.exit("could not locate ApplicationServices framework")
AS = ctypes.cdll.LoadLibrary(_AS_PATH)


class CGPoint(ctypes.Structure):
    # CGFloat is double on 64-bit; passed by value, so argtypes must be exact.
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


AS.AXIsProcessTrusted.restype = ctypes.c_bool

AS.CGEventCreateMouseEvent.restype = ctypes.c_void_p
AS.CGEventCreateMouseEvent.argtypes = [
    ctypes.c_void_p,  # CGEventSourceRef (NULL = default)
    ctypes.c_uint32,  # CGEventType
    CGPoint,          # location
    ctypes.c_uint32,  # CGMouseButton
]

AS.CGEventPost.restype = None
AS.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

AS.CGEventCreate.restype = ctypes.c_void_p
AS.CGEventCreate.argtypes = [ctypes.c_void_p]

AS.CGEventGetLocation.restype = CGPoint
AS.CGEventGetLocation.argtypes = [ctypes.c_void_p]

_CF_PATH = ctypes.util.find_library("CoreFoundation")
CF = ctypes.cdll.LoadLibrary(_CF_PATH)
CF.CFRelease.restype = None
CF.CFRelease.argtypes = [ctypes.c_void_p]

kCGHIDEventTap = 0
kCGEventMouseMoved = 5
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGMouseButtonLeft = 0


def cursor_position():
    ev = AS.CGEventCreate(None)
    pt = AS.CGEventGetLocation(ev)
    CF.CFRelease(ev)
    return pt.x, pt.y


def post(event_type, x, y):
    ev = AS.CGEventCreateMouseEvent(None, event_type, CGPoint(x, y), kCGMouseButtonLeft)
    if not ev:
        sys.exit("CGEventCreateMouseEvent returned NULL")
    AS.CGEventPost(kCGHIDEventTap, ev)
    CF.CFRelease(ev)


def click(x, y, restore=True):
    """Move, then press and release. The move matters: some handlers ignore a
    down/up that arrives with no preceding motion to the target."""
    start = cursor_position()
    post(kCGEventMouseMoved, x, y)
    time.sleep(0.08)
    post(kCGEventLeftMouseDown, x, y)
    time.sleep(0.05)
    post(kCGEventLeftMouseUp, x, y)
    if restore:
        time.sleep(0.15)
        post(kCGEventMouseMoved, *start)
    return start


# --- Chrome read-back over Apple Events (CDP-free) ---------------------------

def chrome_js(script):
    """Evaluate JS in Chrome's front window's active tab. Returns stdout text.

    Deliberately NOT CDP: attaching a debugger is the variable under test."""
    osa = (
        'tell application "Google Chrome" to execute '
        "front window's active tab javascript %s" % json.dumps(script)
    )
    r = subprocess.run(["osascript", "-e", osa], capture_output=True, text=True)
    if r.returncode != 0:
        err = r.stderr.strip()
        if "Allow JavaScript from Apple Events" in err or "-2700" in err:
            err += "\n\nEnable Chrome > View > Developer > Allow JavaScript from Apple Events."
        sys.exit("chrome_js failed:\n" + err)
    return r.stdout.strip()


def cmd_trusted():
    ok = AS.AXIsProcessTrusted()
    print("AXIsProcessTrusted:", ok)
    if not ok:
        print(
            "\nGrant Accessibility to THIS process (System Settings > Privacy &\n"
            "Security > Accessibility). The grant is per-process: Terminal.app's\n"
            "grant does not cover another terminal or a wrapper process."
        )
    return 0 if ok else 1


def cmd_probe():
    """Install a capture-phase click listener that records to localStorage."""
    script = """(function(){
      localStorage.removeItem(%s);
      if (window.__gh70Installed) return 'already-installed (log cleared)';
      window.__gh70Installed = true;
      document.addEventListener('click', function(e){
        var log = JSON.parse(localStorage.getItem(%s) || '[]');
        log.push({
          t: Date.now(),
          isTrusted: e.isTrusted,
          x: e.clientX, y: e.clientY,
          target: (e.target.tagName || '?') + (e.target.id ? '#' + e.target.id : ''),
          label: (e.target.getAttribute && e.target.getAttribute('aria-label')) || null
        });
        localStorage.setItem(%s, JSON.stringify(log));
      }, true);
      return 'installed on ' + location.href;
    })()""" % (json.dumps(LOG_KEY), json.dumps(LOG_KEY), json.dumps(LOG_KEY))
    print(chrome_js(script))
    print("\nListener is capture-phase on document: it sees the click even if a\n"
          "handler downstream stops propagation. An empty log after a click means\n"
          "the event never reached the page at all.")
    return 0


def cmd_read():
    raw = chrome_js("localStorage.getItem(%s) || '[]'" % json.dumps(LOG_KEY))
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        print("unparseable log:", raw)
        return 1
    if not entries:
        print("LOG EMPTY — the page saw no clicks.")
        print("If this follows a click on plain page content, the injection tool\n"
              "is not working. That is a tool failure, not a YouTube finding.")
        return 1
    for e in entries:
        print("isTrusted=%-5s (%4d,%4d) %s%s" % (
            e.get("isTrusted"), e.get("x", -1), e.get("y", -1),
            e.get("target"), " aria-label=%r" % e["label"] if e.get("label") else ""))
    return 0


def cmd_perf(needle="get_transcript"):
    """Did the page issue a matching request? Ground truth WITHOUT CDP.

    Resource Timing sees fetch/XHR, so a get_transcript POST shows up here. This
    is the CDP-free substitute for read_network_requests — which would attach a
    debugger, i.e. the exact variable this diagnostic is trying to hold at zero.

    Caveat: timing entries carry no status code, so a 400 and a 200 look alike.
    A hit means "the request was made" (rules out GH-69's silent no-op); it does
    not mean the request succeeded. Distinguish those by what the panel does next.
    """
    script = """(function(){
      var hits = performance.getEntriesByType('resource')
        .filter(function(e){ return e.name.indexOf(%s) !== -1; })
        .map(function(e){ return {t: Math.round(e.startTime), dur: Math.round(e.duration), name: e.name.split('?')[0]}; });
      return JSON.stringify(hits);
    })()""" % json.dumps(needle)
    hits = json.loads(chrome_js(script))
    if not hits:
        print("NO %r REQUEST — the click did not trigger it." % needle)
        print("This is the GH-69 signature: click delivered, request never made.")
        return 1
    for h in hits:
        print("t=%-7d dur=%-6d %s" % (h["t"], h["dur"], h["name"]))
    print("\n%d request(s). Timing entries carry no status: this proves the request\n"
          "happened, NOT that it succeeded (a 400 looks identical here)." % len(hits))
    return 0


def cmd_coords(selector):
    """Screen-space center point of the first element matching `selector`."""
    script = """(function(){
      // Rough zoom guard. outerWidth/innerWidth is not exact (scrollbars, window
      // chrome), so this only catches a clearly-wrong zoom; the ratio is reported
      // either way so a near-miss is visible rather than silently skewing coords.
      var zoomRatio = window.outerWidth / window.innerWidth;
      if (Math.abs(zoomRatio - 1) > 0.1) {
        return JSON.stringify({error: 'page zoom looks wrong (ratio ' + zoomRatio.toFixed(3) + ') - coords would be off'});
      }
      var el = document.querySelector(%s);
      if (!el) return JSON.stringify({error: 'no element matches selector'});
      var r = el.getBoundingClientRect();
      if (!r.width && !r.height) return JSON.stringify({error: 'element has zero size'});
      var chromeH = window.outerHeight - window.innerHeight;
      return JSON.stringify({
        x: Math.round(window.screenX + r.left + r.width / 2),
        y: Math.round(window.screenY + chromeH + r.top + r.height / 2),
        w: Math.round(r.width), h: Math.round(r.height),
        tag: el.tagName, label: el.getAttribute('aria-label'),
        zoomRatio: Number(zoomRatio.toFixed(3))
      });
    })()""" % json.dumps(selector)
    out = json.loads(chrome_js(script))
    if "error" in out:
        print("ERROR:", out["error"])
        return 1
    print(json.dumps(out, indent=2))
    print("\nclick with:  ./scripts/phase0_quartz_click.py click %d %d" % (out["x"], out["y"]))
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "trusted":
        return cmd_trusted()
    if cmd == "probe":
        return cmd_probe()
    if cmd == "read":
        return cmd_read()
    if cmd == "perf":
        return cmd_perf(argv[2] if len(argv) > 2 else "get_transcript")
    if cmd == "coords":
        if len(argv) < 3:
            print("usage: coords <css-selector>")
            return 2
        return cmd_coords(argv[2])
    if cmd == "click":
        if len(argv) < 4:
            print("usage: click <x> <y>")
            return 2
        x, y = float(argv[2]), float(argv[3])
        start = click(x, y)
        print("posted move+down+up at (%g, %g); cursor restored to (%g, %g)" % (x, y, *start))
        print("now run:  ./scripts/phase0_quartz_click.py read")
        return 0
    print("unknown command: %s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
