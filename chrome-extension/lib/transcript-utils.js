// Transcript utilities — pure helpers shared by popup.js (browser) and tests (node).
//
// Airtable Long Text fields have a hard 100,000-character limit. Saving a longer
// value makes the whole record write fail ("Field ... cannot accept the provided
// value"), so long videos (guides, lectures, full playthroughs) would silently fail
// to save. These helpers keep values under the limit without losing JSON validity.
//
// See GH-64 (truncation workaround) and GH-65 (lossless full-transcript storage).

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;            // Node (tests)
  } else {
    root.TranscriptUtils = api;      // Browser (popup.js global)
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const AIRTABLE_LONG_TEXT_LIMIT = 100000;
  const TRUNCATION_NOTICE = '\n\n[TRUNCATED — full transcript exceeds Airtable 100k char limit]';

  // Truncate a plain-text value to fit an Airtable Long Text field.
  // Returns { value, truncated }. Never throws on non-string input.
  function truncateForAirtable(text, limit = AIRTABLE_LONG_TEXT_LIMIT) {
    if (typeof text !== 'string') return { value: text, truncated: false };
    if (text.length <= limit) return { value: text, truncated: false };
    const sliceLength = Math.max(0, limit - TRUNCATION_NOTICE.length);
    return { value: text.slice(0, sliceLength) + TRUNCATION_NOTICE, truncated: true };
  }

  // Fit a segment array into an Airtable Long Text field as JSON.
  // A naively-truncated JSON string would be invalid, so instead we keep the
  // largest leading run of segments whose serialized form stays under the limit.
  // Returns { json, segments, truncated, droppedCount }.
  function fitSegmentsForAirtable(segments, limit = AIRTABLE_LONG_TEXT_LIMIT) {
    if (!Array.isArray(segments)) {
      return { json: null, segments: [], truncated: false, droppedCount: 0 };
    }

    let json = JSON.stringify(segments);
    if (json.length <= limit) {
      return { json, segments, truncated: false, droppedCount: 0 };
    }

    // Binary-search the largest prefix length that serializes within the limit.
    let lo = 0;
    let hi = segments.length;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (JSON.stringify(segments.slice(0, mid)).length <= limit) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }

    const kept = segments.slice(0, lo);
    json = JSON.stringify(kept);
    return {
      json,
      segments: kept,
      truncated: true,
      droppedCount: segments.length - kept.length,
    };
  }

  return {
    AIRTABLE_LONG_TEXT_LIMIT,
    TRUNCATION_NOTICE,
    truncateForAirtable,
    fitSegmentsForAirtable,
  };
});
