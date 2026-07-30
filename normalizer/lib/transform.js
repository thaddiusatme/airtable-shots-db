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

// Channels are keyed on `Channel Handle`, and every one of the 87 rows that
// already exist is in "@handle" form — NOT the UC... id. That's because
// chrome-extension/content.js derives it from the video owner link with
// /\/@([^/?]+)/ and YouTube renders that link as /@handle. Apify, by contrast,
// always reports channelId as UC.... Keying on channelId (as this file
// originally did, and as docs/NORMALIZER-MANIFEST.md still claimed) therefore
// never matches an existing row: every sweep would fork the Channels table and
// link swept videos to a new Track-less orphan, invisible in the AIHS working
// view. Verified against live data 2026-07-29.
//
// So derive the same key the extension does, from the same URL, with the same
// regex — that's the only way to guarantee byte-identical keys.
const HANDLE_FROM_URL = /\/@([^/?]+)/;

function toHandleKey(item) {
  const username = typeof item.channelUsername === 'string' ? item.channelUsername.trim() : '';
  if (username) return username.startsWith('@') ? username : `@${username}`;

  const fromUrl = HANDLE_FROM_URL.exec(item.channelUrl || '');
  if (fromUrl) return `@${fromUrl[1]}`;

  return null;
}

// Apify can return several subtitle tracks. Taking [0] blindly stores a
// non-English transcript under whatever language happened to come first, which
// fails silently — prefer an en* track and fall back only if there isn't one.
function pickSubtitle(subtitles) {
  if (!Array.isArray(subtitles) || subtitles.length === 0) return null;
  const english = subtitles.find(
    (s) => typeof s?.language === 'string' && s.language.toLowerCase().startsWith('en')
  );
  return english || subtitles[0];
}

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

  const subtitle = pickSubtitle(item.subtitles);

  const createOnlyFields = {
    'Video Title': item.title || '',
    'Video ID': item.id,
    Platform: 'YouTube',
    'Video URL': item.url || `https://www.youtube.com/watch?v=${item.id}`,
    'Triage Status': 'Queued',
    'Intake Source': 'Sweep',
  };

  // Always set a thumbnail. chrome-extension/background.js derives this URL
  // unconditionally, so a blank thumbnail is a shape the proven path could
  // never produce — don't let a missing actor field introduce one.
  const thumbnailUrl = item.thumbnailUrl || `https://i.ytimg.com/vi/${item.id}/hqdefault.jpg`;
  createOnlyFields['Thumbnail URL'] = thumbnailUrl;
  createOnlyFields['Thumbnail (Image)'] = [{ url: thumbnailUrl }];

  const updateFields = {
    'Transcript Source': 'apify-youtube-scraper',
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

  const handleKey = toHandleKey(item);
  if (!handleKey && item.channelId) {
    warnings.push(
      `no @handle derivable from channelUsername/channelUrl — Channel will be keyed on the UC id (${item.channelId}), which will NOT match the existing @handle-keyed rows`
    );
  }

  return {
    videoId: item.id,
    createOnlyFields,
    updateFields,
    channel: {
      handleKey,
      fallbackKey: item.channelId || null,
      channelName: item.channelName,
      channelUrl: item.channelUrl,
    },
    warnings,
  };
}

module.exports = { buildVideoFields };
