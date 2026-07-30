const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseSrt, timestampToSeconds } = require('./srt-parser');

const FIXTURE = fs.readFileSync(
  path.join(__dirname, '__fixtures__', 'qdRw7oHDXJw.srt.txt'),
  'utf8'
);

test('timestampToSeconds handles standard zero-padded fields', () => {
  assert.equal(timestampToSeconds('00:01:02,500'), 62.5);
});

test('timestampToSeconds handles non-zero-padded seconds (the real feed shape)', () => {
  // 00:04:2,560 -> 4 minutes, 2.56 seconds
  assert.equal(timestampToSeconds('00:04:2,560'), 4 * 60 + 2.56);
});

test('timestampToSeconds handles minute rollover with unpadded seconds', () => {
  // 00:02:1,520 -> 2 minutes, 1.52 seconds
  assert.equal(timestampToSeconds('00:02:1,520'), 2 * 60 + 1.52);
});

test('timestampToSeconds returns null for unparseable input', () => {
  assert.equal(timestampToSeconds('not a timestamp'), null);
});

test('parseSrt drops blank/whitespace-only shadow cues', () => {
  const segments = parseSrt(FIXTURE);
  // Fixture: 4 real+blank pairs, one real+blank pair mid-file (block 125/126),
  // and a trailing pair with reversed blank/text order (block 418/419) —
  // 6 real segments expected, all shadow/blank cues dropped.
  assert.equal(segments.length, 6);
  assert.ok(segments.every((s) => s.text.length > 0));
});

test('parseSrt keeps real cues in chronological order regardless of blank-cue position', () => {
  const segments = parseSrt(FIXTURE);
  const starts = segments.map((s) => s.start);
  const sorted = [...starts].sort((a, b) => a - b);
  assert.deepEqual(starts, sorted);
});

test('parseSrt extracts correct text for the first real cue', () => {
  const segments = parseSrt(FIXTURE);
  assert.equal(segments[0].text, "Everyone's going off the rails here");
  assert.equal(segments[0].start, 0.08);
});

test('parseSrt handles a shadow cue arriving before its real cue (last fixture pair)', () => {
  const segments = parseSrt(FIXTURE);
  const last = segments[segments.length - 1];
  assert.equal(last.text, 'weekend everyone.');
  // 00:07:12,400
  assert.equal(last.start, 7 * 60 + 12.4);
});

test('parseSrt returns [] for empty/non-string input', () => {
  assert.deepEqual(parseSrt(''), []);
  assert.deepEqual(parseSrt(null), []);
  assert.deepEqual(parseSrt(undefined), []);
});
