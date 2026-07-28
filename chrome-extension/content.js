// Content script - runs on YouTube video pages
// Extracts transcript from DOM (like Glasp does)

async function waitForElement(selector, timeout = 5000) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const element = document.querySelector(selector);
    if (element) return element;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return null;
}

// Segment element matching + per-row parsing live in lib/transcript-dom.js so they can
// be unit-tested against captured variant fixtures without a browser (injected before
// this script via manifest.json). TranscriptDom is a global in the content-script world.
const { collectSegments, parseSegment } = TranscriptDom;

// The modern variant lazy-loads its rows behind a spinner after the panel is
// shown, so poll until at least one segment element appears.
async function waitForSegments(root, timeout = 5000) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const segments = collectSegments(root);
    if (segments.length > 0) return segments;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return collectSegments(root);
}

function isTranscriptControl(el) {
  const text = el.textContent?.toLowerCase() || '';
  const ariaLabel = el.getAttribute('aria-label')?.toLowerCase() || '';
  return text.includes('transcript') || ariaLabel.includes('transcript');
}

// 2026-07-27 (playlist-harvest retro): tried preferring the "In this video"
// panel's Transcript tab here, on the theory that YouTube's own client
// silently retries get_transcript once after a 400 when driven through that
// tab (confirmed once via a REAL manual click). Reverted same day: re-tested
// against 2 fresh, never-attempted videos with this code live via the
// extension's own scripted click, and BOTH produced zero get_transcript
// network requests at all — not even a 400. That's the GH-69 signature
// (scripted .click() silently not triggering YouTube's handler) — this tab
// element apparently needs a real trusted click to do anything, unlike the
// description button below, which at least fires a (failing) request under
// a scripted click. So this was a regression, not a fix, for the automated
// path. No Airtable writes happened either way (verified clean). Left as a
// documented dead end — the retry-on-400 problem for automated runs is
// still open; do not re-attempt this exact approach without first getting a
// real (non-scripted) click to reach this element.

// GH-69: pick exactly one plausible trigger, in priority order, rather than
// collecting every match — see openTranscriptPanel for why only one gets
// clicked at all.
function findBestTranscriptButton() {
  const descriptionButton = document.querySelector(
    'ytd-video-description-transcript-section-renderer button'
  );
  if (descriptionButton && isTranscriptControl(descriptionButton)) return descriptionButton;

  const menuItem = Array.from(
    document.querySelectorAll('ytd-menu-service-item-renderer, tp-yt-paper-item')
  ).find(isTranscriptControl);
  if (menuItem) return menuItem;

  const generic = Array.from(
    document.querySelectorAll('button, ytd-button-renderer, a[role="button"]')
  ).find(btn => {
    const text = btn.textContent?.toLowerCase() || '';
    const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
    return text.includes('show transcript') || ariaLabel.includes('show transcript');
  });
  if (generic) return generic;

  const structured = Array.from(
    document.querySelectorAll('ytd-structured-description-content-renderer button')
  ).find(isTranscriptControl);
  return structured || null;
}

// GH-69: a click "succeeding" (element existed, .click() ran) is not the same as
// the transcript panel actually opening — poll for segments before trusting it.
// The wait is long (35s) because live measurement showed real variance in how
// long YouTube takes to populate segments after a genuinely correct click: one
// clean run on a ~20min/1214-segment video took 24s+ to render anything, while
// an identical clean click on the same video another time produced nothing in
// 30s. This isn't a selector problem — it's backend-side variance — so a short
// timeout produces false "not found" negatives on videos that would have
// succeeded with more patience. An unattended harvest run halts after two
// consecutive failures, so a slow true success is much cheaper than a false one.
async function clickAndVerify(el, label, timeout = 35000) {
  console.log(`Clicking ${label}...`);
  el.click();
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (collectSegments(document).length > 0) return true;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  console.log(`${label} click did not reveal transcript segments`);
  return false;
}

// GH-69 (revised): earlier version tried several *different* transcript-
// trigger buttons in sequence, each with its own long wait, when the first
// one didn't reveal segments in time. Live testing showed that's the wrong
// model: if YouTube's backend is just slow, clicking a second button doesn't
// parallelize a slow response — and clicking while the first request may
// still be in flight risks colliding with it, the same class of bug as the
// GH-68 stale-token 400. So: find the single best candidate, click it once,
// and commit to one patient wait. The only thing worth retrying is the
// *search* itself — the description section's button can take up to ~1s to
// render after the page settles — never the click.
async function openTranscriptPanel() {
  console.log('Attempting to open transcript panel...');

  // Already open from a previous action on this page.
  const existingPanel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-transcript"]');
  if (existingPanel && existingPanel.getAttribute('visibility') !== 'ENGAGEMENT_PANEL_VISIBILITY_HIDDEN') {
    console.log('Transcript panel already visible');
    return { opened: true, attemptedClick: false };
  }

  let btn = null;
  for (let i = 0; i < 5; i++) {
    btn = findBestTranscriptButton();
    if (btn) break;
    await new Promise(resolve => setTimeout(resolve, 400));
  }

  if (!btn) {
    console.log('Could not find transcript button with any strategy');
    return { opened: false, attemptedClick: false };
  }

  const opened = await clickAndVerify(btn, 'transcript button');
  return { opened, attemptedClick: true };
}

async function extractTranscript() {
  console.log('Attempting to extract transcript...');
  
  // Get video ID from URL
  const urlParams = new URLSearchParams(window.location.search);
  const videoId = urlParams.get('v');
  
  if (!videoId) {
    return { error: 'No video ID found in URL' };
  }
  
  // Get video title
  const videoTitle = document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string')?.textContent?.trim() ||
                     document.querySelector('h1.title')?.textContent?.trim() ||
                     'Unknown Title';
  
  try {
    // Search document-wide for segments rather than locking onto a specific panel
    // wrapper: the modern variant renders into an engagement panel whose target-id
    // becomes null once expanded, while a stale hidden "PAmodern_transcript_view"
    // panel (still showing a spinner) also exists — matching by target-id grabs the
    // wrong one. Matching segment elements by tag avoids both traps.
    let segments = collectSegments(document);

    // If none are present yet, open the panel and poll for lazy-loaded rows.
    let attemptedClick = false;
    if (segments.length === 0) {
      console.log('No transcript segments yet, attempting to open panel...');
      const result = await openTranscriptPanel();
      attemptedClick = result.attemptedClick;
      if (result.opened) {
        segments = await waitForSegments(document, 5000);
      }
    }

    if (segments.length === 0) {
      // GH-69: distinguish "no transcript control found" from "found and
      // clicked one, but the panel never revealed segments" — the latter is a
      // DOM-drift/timing bug, not a page genuinely lacking a transcript.
      return {
        error: attemptedClick
          ? 'Found a "Show transcript" control and clicked it, but the transcript panel never revealed any segments. This may be YouTube DOM drift — try reloading the page and extracting again.'
          : 'Could not find transcript segments. Try manually clicking "Show transcript" first, then extract again.',
        videoId,
        videoTitle
      };
    }

    console.log(`Found ${segments.length} transcript segments, extracting...`);

    // Panel reference used later for language detection (variant-agnostic).
    const transcriptPanel = segments[0].closest('ytd-engagement-panel-section-list-renderer') || document;

    // Per-row parsing lives in lib/transcript-dom.js (parseSegment) so it stays testable.
    const transcriptSegments = segments
      .map(parseSegment)
      .filter(item => item.text);
    
    // Build full transcript text from segments (backward compatible)
    const transcriptText = transcriptSegments
      .map(seg => seg.text)
      .filter(Boolean)
      .join(' ');
    
    // Try to detect language from panel
    let language = 'en';
    const languageButton = transcriptPanel.querySelector('[aria-label*="language"]');
    if (languageButton) {
      const langText = languageButton.textContent?.toLowerCase();
      if (langText?.includes('spanish')) language = 'es';
      else if (langText?.includes('french')) language = 'fr';
      else if (langText?.includes('german')) language = 'de';
    }
    
    const timestampedCount = transcriptSegments.filter(s => s.start !== null).length;
    console.log(`Extracted ${segments.length} segments, ${timestampedCount} with timestamps, ${transcriptText.length} characters`);
    if (transcriptSegments.length > 0) {
      console.log('First segment:', JSON.stringify(transcriptSegments[0]));
      console.log('Last segment:', JSON.stringify(transcriptSegments[transcriptSegments.length - 1]));
    }
    
    // Extract channel info from DOM
    const channelLink = document.querySelector('ytd-video-owner-renderer ytd-channel-name a') ||
                        document.querySelector('#owner a[href*="/channel/"]') ||
                        document.querySelector('#owner a[href*="/@"]');
    const channelName = document.querySelector('ytd-video-owner-renderer ytd-channel-name yt-formatted-string')?.textContent?.trim() ||
                        document.querySelector('#owner ytd-channel-name')?.textContent?.trim() ||
                        '';
    let channelId = '';
    let channelUrl = '';
    if (channelLink) {
      channelUrl = channelLink.href || '';
      // Extract channel ID or handle from URL
      const channelMatch = channelUrl.match(/\/channel\/(UC[a-zA-Z0-9_-]+)/);
      const handleMatch = channelUrl.match(/\/@([^/?]+)/);
      if (channelMatch) {
        channelId = channelMatch[1];
      } else if (handleMatch) {
        channelId = '@' + handleMatch[1];
      }
    }

    return {
      videoId,
      videoTitle,
      transcript: transcriptText,
      transcriptSegments,  // NEW: timestamped segments
      language,
      source: 'youtube-web-ui-dom',
      fetchedAt: new Date().toISOString(),
      segmentCount: segments.length,
      channelName,
      channelId,
      channelUrl
    };
    
  } catch (error) {
    console.error('Transcript extraction error:', error);
    return { 
      error: `Failed to extract transcript: ${error.message}`,
      videoId,
      videoTitle
    };
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractTranscript') {
    extractTranscript().then(data => {
      sendResponse(data);
    }).catch(error => {
      sendResponse({ error: error.message });
    });
    return true; // Keep message channel open for async response
  }
  return true;
});

// ---------------------------------------------------------------------------
// In-page panel (Phase 0 spike) — an agent-drivable "Extract & Save" button.
//
// Design: scoped light-DOM (unique id + prefixed .ytx-* classes + inline styles)
// so Claude in Chrome's find/read_page can see it without piercing a shadow root.
// The agent keys off data-save-state on #yt-transcript-panel; the button carries
// a stable data-testid + aria-label. Save round-trips through the service worker
// (background.js) so the Airtable fetch() runs in the extension origin (no CORS)
// and the PAT never enters this page world.
// ---------------------------------------------------------------------------

const PANEL_ID = 'yt-transcript-panel';

function getCurrentVideoId() {
  return new URLSearchParams(window.location.search).get('v') || '';
}

// Single source of truth the agent polls. Also mirrors a human-readable label.
function setPanelState(panel, state, { errorMsg = '', statusText } = {}) {
  panel.dataset.saveState = state;
  panel.dataset.errorMsg = errorMsg;
  const status = panel.querySelector('.ytx-status');
  if (status) status.textContent = statusText || state;
}

async function onExtractSaveClick(panel) {
  if (panel.dataset.saveState === 'waiting') {
    // SPA swap hasn't landed yet per GH-68 — refuse rather than risk the
    // stale-continuation-token 400. The agent should poll data-save-state
    // and retry once it flips to 'idle'.
    return;
  }
  const btn = panel.querySelector('.ytx-btn');
  btn.disabled = true;
  try {
    setPanelState(panel, 'extracting', { statusText: 'Extracting…' });
    const data = await extractTranscript();
    if (data.error) {
      setPanelState(panel, 'error', { errorMsg: data.error, statusText: `Error: ${data.error}` });
      return;
    }

    setPanelState(panel, 'saving', { statusText: 'Saving…' });
    const res = await chrome.runtime.sendMessage({ action: 'saveTranscript', data });

    if (res && res.ok) {
      const label = res.warning
        ? `${res.action === 'created' ? 'Created' : 'Saved'} · ${res.warning}`
        : (res.action === 'created' ? 'Created + saved ✓' : 'Saved ✓');
      setPanelState(panel, 'saved', { statusText: label });
    } else {
      const msg = (res && res.error) || 'Save failed';
      setPanelState(panel, 'error', { errorMsg: msg, statusText: `Error: ${msg}` });
    }
  } catch (error) {
    setPanelState(panel, 'error', { errorMsg: error.message, statusText: `Error: ${error.message}` });
  } finally {
    btn.disabled = false;
  }
}

// GH-68 fix (contract fix, "stop idle from lying"): ytd-watch-flexy's own
// video-id attribute flips only once YouTube has actually finished swapping
// the page for a SPA nav — confirmed live (2026-07-22): at yt-navigate-finish
// the URL already names the new video but watch-flexy still reports the
// previous one for ~1.4-2s before it catches up. Clicking "Show transcript"
// before that swap completes hits the *previous* video's continuation token
// and YouTube's get_transcript endpoint 400s (silent, permanent spinner).
// So: hold a non-ready 'waiting' state until watch-flexy's video-id matches
// the URL, THEN flip to 'idle'. The button still mounts immediately (agent's
// find() still succeeds) — only the advertised readiness is delayed.
function getFlexyVideoId() {
  const el = document.querySelector('ytd-watch-flexy');
  return el ? el.getAttribute('video-id') : null;
}

// Poll (cheap, short-lived) rather than MutationObserver: the watch-flexy
// attribute swap is a single flip, not a stream of mutations worth wiring
// an observer for, and polling is trivial to reason about / bound in time.
function waitForVideoSwap(panel, videoId, { timeout = 4000, interval = 50 } = {}) {
  const start = Date.now();
  const tick = () => {
    // Bail if the panel moved on to a *different* video while we were waiting
    // (rapid nav-nav-nav) — don't stomp a newer wait with a stale one.
    if (panel.dataset.videoId !== videoId) return;

    if (getFlexyVideoId() === videoId) {
      setPanelState(panel, 'idle', { statusText: 'Idle' });
      return;
    }
    if (Date.now() - start >= timeout) {
      // Fail open: don't strand the panel forever if watch-flexy's attribute
      // never matches for some reason (unknown YouTube layout, etc.) — better
      // to risk the old 400 than to brick the agent loop on every video.
      console.log('waitForVideoSwap: timed out waiting for watch-flexy video-id to match, flipping idle anyway');
      setPanelState(panel, 'idle', { statusText: 'Idle' });
      return;
    }
    setTimeout(tick, interval);
  };
  tick();
}

// Idempotent: builds the panel once. Refreshes data-video-id and resets to a
// non-ready 'waiting' state so a remount on the next video starts clean and
// doesn't advertise idle until the SPA swap has actually landed.
function mountPanel() {
  let panel = document.getElementById(PANEL_ID);
  if (!panel) {
    panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.className = 'ytx-panel';
    panel.style.cssText =
      'position:fixed;bottom:16px;right:16px;z-index:9999;background:#212121;color:#fff;' +
      'padding:12px 14px;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.4);' +
      'font-family:Roboto,Arial,sans-serif;font-size:13px;display:flex;align-items:center;gap:10px;';

    const btn = document.createElement('button');
    btn.className = 'ytx-btn';
    btn.setAttribute('data-testid', 'extract-save-btn');
    btn.setAttribute('aria-label', 'Extract and save transcript');
    btn.textContent = 'Extract & Save';
    btn.style.cssText =
      'background:#3ea6ff;color:#0f0f0f;border:none;border-radius:8px;padding:8px 12px;' +
      'font-weight:600;font-size:13px;cursor:pointer;';
    btn.addEventListener('click', () => onExtractSaveClick(panel));

    const status = document.createElement('span');
    status.className = 'ytx-status';

    panel.appendChild(btn);
    panel.appendChild(status);
    document.body.appendChild(panel);
  }

  const videoId = getCurrentVideoId();
  panel.dataset.videoId = videoId;

  if (getFlexyVideoId() === videoId) {
    // Fresh full page load, or watch-flexy already caught up — no need to wait.
    setPanelState(panel, 'idle', { statusText: 'Idle' });
  } else {
    setPanelState(panel, 'waiting', { statusText: 'Loading…' });
    waitForVideoSwap(panel, videoId);
  }
  return panel;
}

// YouTube is a SPA: navigating video->video does not re-run this content script.
// Re-mount on yt-navigate-finish so the agent's find() succeeds on video #2, #3…
window.addEventListener('yt-navigate-finish', () => {
  if (!location.pathname.startsWith('/watch')) return;
  mountPanel();
});

// Mount on initial load (script runs at document_idle).
mountPanel();

console.log('YouTube Transcript Extractor content script loaded');
