const { test } = require('node:test');
const assert = require('node:assert');
const {
  truncateForAirtable,
  fitSegmentsForAirtable,
  AIRTABLE_LONG_TEXT_LIMIT,
  TRUNCATION_NOTICE,
} = require('./transcript-utils');

test('truncateForAirtable: short text passes through unchanged', () => {
  const result = truncateForAirtable('hello world');
  assert.strictEqual(result.value, 'hello world');
  assert.strictEqual(result.truncated, false);
});

test('truncateForAirtable: text exactly at limit is not truncated', () => {
  const text = 'a'.repeat(AIRTABLE_LONG_TEXT_LIMIT);
  const result = truncateForAirtable(text);
  assert.strictEqual(result.truncated, false);
  assert.strictEqual(result.value.length, AIRTABLE_LONG_TEXT_LIMIT);
});

test('truncateForAirtable: over-limit text is truncated and fits the limit', () => {
  const text = 'a'.repeat(AIRTABLE_LONG_TEXT_LIMIT + 5000);
  const result = truncateForAirtable(text);
  assert.strictEqual(result.truncated, true);
  assert.ok(result.value.length <= AIRTABLE_LONG_TEXT_LIMIT);
  assert.ok(result.value.endsWith(TRUNCATION_NOTICE));
});

test('truncateForAirtable: non-string input is returned untouched', () => {
  assert.deepStrictEqual(truncateForAirtable(undefined), { value: undefined, truncated: false });
  assert.deepStrictEqual(truncateForAirtable(null), { value: null, truncated: false });
});

test('fitSegmentsForAirtable: small array serializes fully', () => {
  const segments = [{ text: 'a', start: 0 }, { text: 'b', start: 5 }];
  const result = fitSegmentsForAirtable(segments);
  assert.strictEqual(result.truncated, false);
  assert.strictEqual(result.droppedCount, 0);
  assert.deepStrictEqual(JSON.parse(result.json), segments);
});

test('fitSegmentsForAirtable: large array is trimmed to valid JSON within the limit', () => {
  // Each segment serializes to well over 1 char; 20k of them blows past 100k.
  const segments = Array.from({ length: 20000 }, (_, i) => ({
    text: `segment number ${i} with some descriptive words`,
    start: i * 3,
  }));
  const result = fitSegmentsForAirtable(segments);
  assert.strictEqual(result.truncated, true);
  assert.ok(result.droppedCount > 0);
  assert.ok(result.json.length <= AIRTABLE_LONG_TEXT_LIMIT);
  // Result must still be valid, parseable JSON (the key property vs. raw truncation).
  const parsed = JSON.parse(result.json);
  assert.strictEqual(parsed.length, result.segments.length);
  assert.strictEqual(parsed.length + result.droppedCount, segments.length);
});

test('fitSegmentsForAirtable: non-array input is handled safely', () => {
  const result = fitSegmentsForAirtable(undefined);
  assert.deepStrictEqual(result, { json: null, segments: [], truncated: false, droppedCount: 0 });
});
