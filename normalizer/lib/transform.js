// Turn one Apify streamers/youtube-scraper dataset item into the Airtable
// fields the normalizer needs to write, reusing:
//   - srt-parser.js for the timestamped-segment shape { text, start }
//   - chrome-extension/lib/transcript-utils.js for the GH-64 100k-char
//     truncation shim, so that logic is never reimplemented (per CLAUDE.md).

const path = require('node:path');
const TranscriptUtils = require(
  path.join(__dirname, '..', '..', 'chrome-extension', 'lib', 'transcript-utils.js')
);
const { parseSrt } = require('./srt-parser');

// Build { createOnlyFields, updateFields, channel, warnings } from one Apify
// dataset item. Never throws — items missing subtitles still produce a
// Video row (just without transcript fields), since Triage can't happen
// without the video existing at all, and a missing transcript is visible
// and fixable later rather than silently dropping the video.
function buildVideoFields(item) {
  const warnings = [];

  if (!item || !item.id) {
    return { skipped: 'item has no video id', item };
  }

  const subtitle = Array.isArray(item.subtitles) ? item.subtitles[0] : null;

  const createOnlyFields = {
    'Video Title': item.title || '',
    'Video ID': item.id,
    Platform: 'YouTube',
    'Video URL': item.url || `https://www.youtube.com/watch?v=${item.id}`,
    'Triage Status': 'Queued',
    'Intake Source': 'Sweep',
  };

  if (item.thumbnailUrl) {
    createOnlyFields['Thumbnail URL'] = item.thumbnailUrl;
    createOnlyFields['Thumbnail (Image)'] = [{ url: item.thumbnailUrl }];
  }

  const updateFields = {
    'Transcript Source': 'Apify',
  };

  if (subtitle?.language) {
    updateFields['Transcript Language'] = subtitle.language;
  }

  // subtitle.srt is populated when subtitlesFormat: "srt" was requested;
  // subtitle.plaintext when subtitlesFormat: "plaintext" was requested (no
  // usable per-cue timing in that case — see srt-parser.js header comment).
  let segments = [];
  if (subtitle?.srt) {
    segments = parseSrt(subtitle.srt);
    if (segments.length === 0) {
      warnings.push('subtitles.srt present but parsed to 0 segments — check actor output shape');
    }
  } else if (subtitle?.plaintext) {
    warnings.push('subtitles delivered as plaintext, not srt — no per-cue timestamps available; Transcript (Timestamped) will be empty. Re-run with subtitlesFormat: "srt".');
  } else if (item.hasSubtitles !== false) {
    warnings.push('no subtitles in dataset item — video created without transcript');
  }

  const fullText = segments.length > 0
    ? segments.map((s) => s.text).join(' ')
    : subtitle?.plaintext || '';

  if (fullText) {
    const fitted = TranscriptUtils.truncateForAirtable(fullText);
    updateFields['Transcript (Full)'] = fitted.value;
    if (fitted.truncated) warnings.push('full transcript truncated to 100k chars (GH-64)');
  }

  if (segments.length > 0) {
    const fitted = TranscriptUtils.fitSegmentsForAirtable(segments);
    updateFields['Transcript (Timestamped)'] = fitted.json;
    if (fitted.truncated) {
      warnings.push(`${fitted.droppedCount} timestamped segment(s) dropped to fit 100k chars (GH-64)`);
    }
  }

  return {
    videoId: item.id,
    createOnlyFields,
    updateFields,
    channel: {
      channelId: item.channelId,
      channelName: item.channelName,
      channelUrl: item.channelUrl,
    },
    warnings,
  };
}

module.exports = { buildVideoFields };
