// Tests for transcript-dom.js — parse captured YouTube variant fixtures via jsdom.
//
// The "every fixture yields usable segments" block is the regression guard from the
// self-healing design (GH-68): each known variant has a fixture, and no refactor may
// silently drop one. Adding a new variant = drop its captured HTML in fixtures/variants/
// and extend parseSegment() until this passes — no browser required.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const { collectSegments, parseSegment, parseTimestampToSeconds } = require('./transcript-dom');

const VARIANTS_DIR = path.join(__dirname, 'fixtures', 'variants');

function loadFixture(name) {
  const html = fs.readFileSync(path.join(VARIANTS_DIR, name), 'utf8');
  return new JSDOM(html).window.document;
}

const fixtureFiles = fs.readdirSync(VARIANTS_DIR).filter(f => f.endsWith('.html'));

// --- Regression guard: every known variant must remain extractable ---------------
test('at least one variant fixture exists', () => {
  assert.ok(fixtureFiles.length >= 1, 'expected fixtures under fixtures/variants/');
});

for (const file of fixtureFiles) {
  test(`variant "${file}" yields usable segments`, () => {
    const document = loadFixture(file);
    const segments = collectSegments(document);
    assert.ok(segments.length >= 1, `${file}: no segments matched`);

    const parsed = segments.map(parseSegment).filter(s => s.text);
    assert.strictEqual(parsed.length, segments.length, `${file}: some rows produced empty text`);

    for (const { text, start } of parsed) {
      assert.ok(typeof text === 'string' && text.length > 0, `${file}: empty segment text`);
      assert.ok(start === null || Number.isFinite(start), `${file}: bad start ${start}`);
    }
  });
}

// --- Variant-specific structure assertions ---------------------------------------
test('modern variant: timestamp + text mapped correctly', () => {
  const document = loadFixture('modern-transcript-segment-view-model.html');
  const parsed = collectSegments(document).map(parseSegment);
  assert.strictEqual(parsed.length, 3);
  assert.match(parsed[0].text, /^I made this entire Vox/);
  assert.strictEqual(parsed[0].start, 0);
  assert.strictEqual(parsed[1].start, 7);
  assert.strictEqual(parsed[2].start, 3723); // 1:02:03
});

test('classic variant: timestamp + text mapped correctly', () => {
  const document = loadFixture('classic-ytd-transcript-segment-renderer.html');
  const parsed = collectSegments(document).map(parseSegment);
  assert.strictEqual(parsed.length, 3);
  assert.strictEqual(parsed[0].text, 'Welcome to the classic transcript panel.');
  assert.strictEqual(parsed[0].start, 0);
  assert.strictEqual(parsed[2].start, 3723);
});

// --- collectSegments contract ----------------------------------------------------
test('collectSegments handles null / non-DOM input safely', () => {
  assert.deepStrictEqual(collectSegments(null), []);
  assert.deepStrictEqual(collectSegments({}), []);
});

// --- parseTimestampToSeconds -----------------------------------------------------
test('parseTimestampToSeconds parses M:SS and H:MM:SS, rejects junk', () => {
  assert.strictEqual(parseTimestampToSeconds('0:00'), 0);
  assert.strictEqual(parseTimestampToSeconds('1:23'), 83);
  assert.strictEqual(parseTimestampToSeconds('1:02:03'), 3723);
  assert.strictEqual(parseTimestampToSeconds(null), null);
  assert.strictEqual(parseTimestampToSeconds(''), null);
  assert.strictEqual(parseTimestampToSeconds('abc'), null);
});
