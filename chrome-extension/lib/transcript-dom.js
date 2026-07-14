// Transcript DOM parsing — pure helpers shared by content.js (browser) and tests (node/jsdom).
//
// YouTube serves MULTIPLE CONCURRENT A/B panel variants and periodically renames
// elements, so extraction must match every known variant, not just the current default.
// Keeping the per-segment parsing here (a) makes it unit-testable against captured
// fixtures without a browser, and (b) makes adding the next variant a localized change.
//
// When a new variant appears: capture one segment's outerHTML from the live panel, add a
// fixture under lib/fixtures/variants/, add its tag to SEGMENT_SELECTORS, and add a mapping
// branch in parseSegment(). See docs/self-healing-transcript-selectors.md and GH-67/GH-68.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;            // Node (tests)
  } else {
    root.TranscriptDom = api;        // Browser (content.js global)
  }
})(typeof self !== 'undefined' ? self : this, function () {
  // Segment row element per variant:
  //   - classic Polymer panel:             ytd-transcript-segment-renderer
  //   - modern "PAmodern_transcript_view":  transcript-segment-view-model
  const SEGMENT_SELECTORS = 'ytd-transcript-segment-renderer, transcript-segment-view-model';

  // Find all transcript segment rows within a root (document or panel element),
  // across every known variant. Returns an array (never a live NodeList).
  function collectSegments(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return [];
    return Array.from(root.querySelectorAll(SEGMENT_SELECTORS));
  }

  // Parse a "M:SS" or "H:MM:SS" timestamp to seconds. Returns null if unparseable.
  function parseTimestampToSeconds(timestamp) {
    if (!timestamp) return null;
    const parts = timestamp.split(':').map(Number);
    if (parts.some(Number.isNaN)) return null;
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return null;
  }

  // Extract { text, start } from a single segment element. Tries variant-specific
  // structures in order, falling through to progressively more generic approaches so
  // an unknown-but-similar layout still yields something rather than nothing.
  function parseSegment(seg) {
    let timestampStr = null;
    let text = null;

    // Variant-specific handles:
    const vmTimestamp = seg.querySelector('.ytwTranscriptSegmentViewModelTimestamp'); // modern
    const vmText = seg.querySelector('.ytAttributedStringHost, span[role="text"]');   // modern
    const coreSpans = seg.querySelectorAll('span.yt-core-attributed-string');         // classic Feb-2026
    const ytFormatted = seg.querySelectorAll('yt-formatted-string');
    const directChildren = Array.from(seg.children);

    // Pre-scan: grab the first timestamp-shaped token anywhere in the row.
    for (const el of seg.querySelectorAll('*')) {
      const txt = el.textContent.trim();
      if (!timestampStr && /^\d{1,2}:\d{2}(:\d{2})?$/.test(txt)) {
        timestampStr = txt;
      }
    }

    if (vmText) {
      // Approach 0: modern view-model variant (transcript-segment-view-model)
      if (!timestampStr) timestampStr = vmTimestamp?.textContent?.trim();
      text = vmText.textContent?.trim();
    } else if (coreSpans.length >= 2) {
      // Approach 1: span.yt-core-attributed-string (classic Feb-2026 DOM)
      if (!timestampStr) timestampStr = coreSpans[0]?.textContent?.trim();
      text = coreSpans[1]?.textContent?.trim();
    } else if (ytFormatted.length >= 2) {
      // Approach 2: yt-formatted-string pair
      if (!timestampStr) timestampStr = ytFormatted[0]?.textContent?.trim();
      text = ytFormatted[1]?.textContent?.trim();
    } else if (directChildren.length >= 2) {
      // Approach 3: first two direct children
      if (!timestampStr) timestampStr = directChildren[0]?.textContent?.trim();
      text = directChildren[1]?.textContent?.trim();
    } else {
      // Approach 4: full text, strip a leading timestamp if present
      const fullText = seg.textContent.trim();
      text = (timestampStr && fullText.startsWith(timestampStr))
        ? fullText.substring(timestampStr.length).trim()
        : fullText;
    }

    return { text, start: parseTimestampToSeconds(timestampStr) };
  }

  return {
    SEGMENT_SELECTORS,
    collectSegments,
    parseTimestampToSeconds,
    parseSegment,
  };
});
