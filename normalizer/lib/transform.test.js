const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildVideoFields } = require('./transform');

const SRT_FIXTURE = fs.readFileSync(
  path.join(__dirname, '__fixtures__', 'qdRw7oHDXJw.srt.txt'),
  'utf8'
);

// A real channel-mode dataset item, captured 2026-07-29 from
// streamers/youtube-scraper against @WayneStLedger. Values are trimmed but the
// KEY SET is verbatim — that's the actor output contract this guards. If a
// future actor version changes shape, this is the early warning. Re-verify
// against a fresh capture before widening any assertion to make it pass.
const CHANNEL_ITEM = JSON.parse(
  fs.readFileSync(path.join(__dirname, '__fixtures__', 'channel-item.json'), 'utf8')
);

// Shaped to the ACTUAL channel-mode dataset item observed on 2026-07-29 (see
// __fixtures__/channel-item.json). Two details matter and were previously
// guessed wrong here: Apify reports `channelUrl` in /channel/UC... form (NOT
// @handle, so the URL is useless for deriving the handle key), and there is no
// `hasSubtitles` field at all. `channelUsername` is the only handle source.
function baseItem(overrides = {}) {
  return {
    title: 'Claude Opus 5: When to Use It and When to Skip It',
    id: 'qdRw7oHDXJw',
    url: 'https://www.youtube.com/watch?v=qdRw7oHDXJw',
    date: '2026-07-29T16:14:33.000Z',
    thumbnailUrl: 'https://i.ytimg.com/vi/qdRw7oHDXJw/maxresdefault.jpg',
    channelName: 'Wayne St Ledger | Marketing & AI',
    channelUrl: 'https://www.youtube.com/channel/UCRWNXOT0ZZJFetI_JZWxL2A',
    channelUsername: 'WayneStLedger',
    channelId: 'UCRWNXOT0ZZJFetI_JZWxL2A',
    subtitles: [{ type: 'auto_generated', language: 'en', srt: SRT_FIXTURE }],
    ...overrides,
  };
}

test('buildVideoFields maps the real Apify item shape to Airtable fields', () => {
  const result = buildVideoFields(baseItem());

  assert.equal(result.videoId, 'qdRw7oHDXJw');
  assert.equal(result.createOnlyFields['Video ID'], 'qdRw7oHDXJw');
  assert.equal(result.createOnlyFields.Platform, 'YouTube');
  assert.equal(result.createOnlyFields['Triage Status'], 'Queued');
  assert.equal(result.createOnlyFields['Intake Source'], 'Sweep');
  assert.equal(result.updateFields['Transcript Source'], 'apify-youtube-scraper');
  assert.equal(result.updateFields['Transcript Language'], 'en');
  assert.equal(result.channel.fallbackKey, 'UCRWNXOT0ZZJFetI_JZWxL2A');
  assert.deepEqual(result.warnings, []);
});

// Channel keying — the bug that would have forked the Channels table. Every
// existing row is "@handle"; Apify reports channelId as UC.... See transform.js.
test('channel handleKey comes from channelUsername — the only source Apify gives', () => {
  const result = buildVideoFields(baseItem());
  assert.equal(result.channel.handleKey, '@WayneStLedger');
  assert.equal(result.channel.fallbackKey, 'UCRWNXOT0ZZJFetI_JZWxL2A');
  assert.deepEqual(result.warnings, []);
});

test('channel handleKey does not double-prefix an already-@ username', () => {
  const result = buildVideoFields(baseItem({ channelUsername: '@WayneStLedger' }));
  assert.equal(result.channel.handleKey, '@WayneStLedger');
});

test('channel handleKey falls back to an @-form channelUrl, matching content.js', () => {
  // Not the Apify shape (its channelUrl is /channel/UC...), but it is the shape
  // the extension sees, and the fallback must produce the identical key.
  const result = buildVideoFields(
    baseItem({ channelUsername: undefined, channelUrl: 'https://www.youtube.com/@WayneStLedger' })
  );
  assert.equal(result.channel.handleKey, '@WayneStLedger');
  assert.deepEqual(result.warnings, []);
});

test('channel warns loudly when only a UC id is derivable', () => {
  // The dangerous case: no username and a /channel/UC... URL. Keying on the UC
  // id would fork the Channels table, so this must not pass silently.
  const result = buildVideoFields(baseItem({ channelUsername: undefined }));
  assert.equal(result.channel.handleKey, null);
  assert.equal(result.channel.fallbackKey, 'UCRWNXOT0ZZJFetI_JZWxL2A');
  assert.ok(result.warnings.some((w) => w.includes('will NOT match')));
});

test('thumbnail falls back to the derived hqdefault URL when the actor omits it', () => {
  const result = buildVideoFields(baseItem({ thumbnailUrl: undefined }));
  const expected = 'https://i.ytimg.com/vi/qdRw7oHDXJw/hqdefault.jpg';
  assert.equal(result.createOnlyFields['Thumbnail URL'], expected);
  assert.deepEqual(result.createOnlyFields['Thumbnail (Image)'], [{ url: expected }]);
});

test('an English subtitle track is preferred over a non-English first track', () => {
  const result = buildVideoFields(
    baseItem({
      subtitles: [
        { type: 'auto_generated', language: 'de', srt: '1\n00:00:0,000 --> 00:00:1,000\nGuten Tag\n' },
        { type: 'auto_generated', language: 'en', srt: SRT_FIXTURE },
      ],
    })
  );
  assert.equal(result.updateFields['Transcript Language'], 'en');
  assert.ok(result.updateFields['Transcript (Full)'].includes('Opus 5'));
  assert.ok(!result.updateFields['Transcript (Full)'].includes('Guten Tag'));
});

test('a non-English track is still used when no English track exists', () => {
  const result = buildVideoFields(
    baseItem({
      subtitles: [{ type: 'auto_generated', language: 'de', srt: '1\n00:00:0,000 --> 00:00:1,000\nGuten Tag\n' }],
    })
  );
  assert.equal(result.updateFields['Transcript Language'], 'de');
  assert.equal(result.updateFields['Transcript (Full)'], 'Guten Tag');
});

test('buildVideoFields produces valid, parseable JSON for Transcript (Timestamped)', () => {
  const result = buildVideoFields(baseItem());
  const parsed = JSON.parse(result.updateFields['Transcript (Timestamped)']);
  assert.ok(Array.isArray(parsed));
  assert.ok(parsed.length > 0);
  assert.ok(parsed.every((s) => typeof s.text === 'string' && typeof s.start === 'number'));
});

test('buildVideoFields warns and skips timestamps when subtitles are plaintext-only', () => {
  const result = buildVideoFields(
    baseItem({ subtitles: [{ type: 'auto_generated', language: 'en', plaintext: 'some text with no timing' }] })
  );
  assert.equal(result.updateFields['Transcript (Timestamped)'], undefined);
  assert.equal(result.updateFields['Transcript (Full)'], 'some text with no timing');
  assert.ok(result.warnings.some((w) => w.includes('plaintext')));
});

test('buildVideoFields warns when there are no subtitles at all', () => {
  const result = buildVideoFields(baseItem({ subtitles: [] }));
  assert.equal(result.updateFields['Transcript (Full)'], undefined);
  assert.ok(result.warnings.some((w) => w.includes('no subtitles')));
});

test('buildVideoFields skips items with no video id', () => {
  const result = buildVideoFields({ title: 'no id here' });
  assert.equal(result.skipped, 'item has no video id');
});

// --- the real captured item, end to end ------------------------------------

test('the real channel-mode item maps cleanly with no warnings', () => {
  const result = buildVideoFields(CHANNEL_ITEM);

  assert.equal(result.videoId, 'eOebZr3BwSg');
  assert.equal(result.createOnlyFields['Video ID'], 'eOebZr3BwSg');
  assert.equal(result.createOnlyFields['Triage Status'], 'Queued');
  assert.equal(result.createOnlyFields['Intake Source'], 'Sweep');
  assert.equal(result.updateFields['Transcript Source'], 'apify-youtube-scraper');
  assert.equal(result.updateFields['Transcript Language'], 'en');

  // The whole point of the fix: an @handle key, never the UC id.
  assert.equal(result.channel.handleKey, '@WayneStLedger');
  assert.equal(result.channel.fallbackKey, 'UCRWNXOT0ZZJFetI_JZWxL2A');

  // No `hasSubtitles` key exists in real output, and subtitles are inline.
  assert.equal('hasSubtitles' in CHANNEL_ITEM, false);
  assert.ok(CHANNEL_ITEM.subtitles[0].srt.length > 0);

  const segments = JSON.parse(result.updateFields['Transcript (Timestamped)']);
  assert.ok(segments.length > 0);
  assert.ok(segments.every((s) => typeof s.text === 'string' && typeof s.start === 'number'));
  assert.deepEqual(result.warnings, []);
});

test('the actor still reports the publish date as `date` in ISO form', () => {
  // --oldest-post-date bounding is only verifiable against this field, and the
  // 2026-07-29 negative control proved the actor honors the bound.
  assert.match(CHANNEL_ITEM.date, /^\d{4}-\d{2}-\d{2}T/);
});
