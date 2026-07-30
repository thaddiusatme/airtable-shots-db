const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildVideoFields } = require('./transform');

const SRT_FIXTURE = fs.readFileSync(
  path.join(__dirname, '__fixtures__', 'qdRw7oHDXJw.srt.txt'),
  'utf8'
);

function baseItem(overrides = {}) {
  return {
    title: 'Claude Opus 5: When to Use It and When to Skip It',
    id: 'qdRw7oHDXJw',
    url: 'https://www.youtube.com/watch?v=qdRw7oHDXJw',
    thumbnailUrl: 'https://i.ytimg.com/vi/qdRw7oHDXJw/maxresdefault.jpg',
    channelName: 'Wayne St Ledger | Marketing & AI',
    channelUrl: 'https://www.youtube.com/@WayneStLedger',
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
  assert.equal(result.updateFields['Transcript Source'], 'Apify');
  assert.equal(result.updateFields['Transcript Language'], 'en');
  assert.equal(result.channel.channelId, 'UCRWNXOT0ZZJFetI_JZWxL2A');
  assert.deepEqual(result.warnings, []);
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
