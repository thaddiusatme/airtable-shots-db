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

// The actor reports runtime as a "HH:MM:SS" (or "MM:SS") string; Airtable's
// duration field wants seconds. Returns null on anything unparseable rather
// than throwing — buildVideoFields is total by contract, and a weird duration
// is not worth losing a whole video over.
function parseDuration(value) {
  if (typeof value !== 'string') return null;
  const parts = value.trim().split(':');
  if (parts.length < 2 || parts.length > 3) return null;

  let seconds = 0;
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    seconds = seconds * 60 + Number(part);
  }
  return seconds;
}

// The publish date is the field that makes every view count interpretable, so
// only accept it in the ISO shape the actor was observed to emit — a surprise
// format is better left blank than silently stored as an unparseable string.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}T/;

// Assign only when the value is genuinely a finite number.
//
// This is deliberately a typeof check and not `if (value)`: `likes: 0` is a
// real value in the observed fixture, and a truthiness guard would drop every
// zero-like and zero-comment video — precisely the videos where the zero is
// the informative part. Same reasoning for a missing metric: absent must stay
// absent rather than becoming a fabricated 0.
function assignNumber(fields, name, value) {
  if (typeof value === 'number' && Number.isFinite(value)) fields[name] = value;
}

// Long text goes through the same GH-64 shim the transcripts use (invariant 5)
// rather than being written raw — a 100k-char description would 422 the record.
function assignLongText(fields, name, value, warnings, label) {
  if (typeof value !== 'string' || value === '') return;
  const fitted = TranscriptUtils.truncateForAirtable(value);
  fields[name] = fitted.value;
  if (fitted.truncated) warnings.push(`${label} truncated to 100k chars (GH-64)`);
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

// Channel-level stats, keyed by Airtable field name. Returned as its own
// object so airtable-client can PATCH it onto an existing Channel row without
// having to know which fields are stats and which are human-owned — `Track`
// is never in here, so it is structurally impossible to clobber.
function buildChannelStats(item, capturedAt) {
  const stats = {};
  assignNumber(stats, 'Subscribers', item.numberOfSubscribers);
  assignNumber(stats, 'Total Videos', item.channelTotalVideos);
  assignNumber(stats, 'Total Views', item.channelTotalViews);

  if (typeof item.channelDescription === 'string' && item.channelDescription !== '') {
    stats['Channel Description'] = TranscriptUtils.truncateForAirtable(item.channelDescription).value;
  }

  // Only stamp when something was actually captured — an empty stats object
  // means "nothing to write", and a lone timestamp would claim otherwise.
  if (capturedAt && Object.keys(stats).length > 0) stats['Stats Captured At'] = capturedAt;

  return stats;
}

// Build { createOnlyFields, updateFields, channel, warnings } from one Apify
// dataset item. Never throws — items missing subtitles still produce a
// Video row (just without transcript fields), since Triage can't happen
// without the video existing at all, and a missing transcript is visible
// and fixable later rather than silently dropping the video.
//
// `capturedAt` is an ISO string computed once per run by the CLI, so every
// record in one sweep shares a single timestamp.
function buildVideoFields(item, { capturedAt } = {}) {
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

  // --- metrics and repurposing material --------------------------------------
  //
  // These live in updateFields, not createOnlyFields, and that is the whole
  // refresh mechanism: they are machine-owned and time-varying, so re-sweeping
  // a channel updates them in place for free. Nothing here is ever hand-edited,
  // so unlike Triage Status (invariant 3) there is no human value to clobber.
  //
  // Metrics are a snapshot with no history — `Metrics Captured At` is what
  // keeps a stored view count honest once it's a week old.
  assignNumber(updateFields, 'View Count', item.viewCount);
  assignNumber(updateFields, 'Like Count', item.likes);
  assignNumber(updateFields, 'Comment Count', item.commentsCount);
  assignNumber(updateFields, 'Duration', parseDuration(item.duration));

  if (typeof item.date === 'string' && ISO_DATE.test(item.date)) {
    updateFields['Published At'] = item.date;
  }

  // `text` is the video description: hooks, CTAs, chapter lists, offer framing.
  assignLongText(updateFields, 'Description', item.text, warnings, 'description');

  // Creators repeat the same link several times in a description, so dedupe
  // while preserving order — the useful signal is which offers exist, not how
  // many times each was mentioned.
  if (Array.isArray(item.descriptionLinks)) {
    const urls = [
      ...new Set(
        item.descriptionLinks
          .map((link) => link?.url)
          .filter((url) => typeof url === 'string' && url !== '')
      ),
    ];
    assignLongText(updateFields, 'Description Links', urls.join('\n'), warnings, 'description links');
  }

  // Plain text, never a multi-select: these values come from the actor rather
  // than from us, and a value that isn't an existing choice 422s the entire
  // record (invariant 7). See the field description in Airtable.
  if (Array.isArray(item.hashtags)) {
    const tags = item.hashtags.filter((tag) => typeof tag === 'string' && tag !== '');
    if (tags.length > 0) updateFields.Hashtags = tags.join(' ');
  }

  if (capturedAt) updateFields['Metrics Captured At'] = capturedAt;

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
      stats: buildChannelStats(item, capturedAt),
    },
    warnings,
  };
}

module.exports = { buildVideoFields, parseDuration, buildChannelStats };
