const { test } = require('node:test');
const assert = require('node:assert/strict');

const { parseArgs, validateArgs, elideTranscripts } = require('./apify-harvest');

const REQUIRED = ['--channel-url', 'https://www.youtube.com/@X', '--max-results', '2', '--oldest-post-date', '2026-01-01'];

test('parseArgs reads the required args and applies defaults', () => {
  const args = parseArgs(REQUIRED);
  assert.equal(args.channelUrl, 'https://www.youtube.com/@X');
  assert.equal(args.maxResults, 2);
  assert.equal(args.oldestPostDate, '2026-01-01');
  assert.equal(args.queueCeiling, 30);
  assert.equal(args.dryRun, false);
  assert.equal(args.saveRaw, undefined);
});

test('parseArgs accepts --flag=value form', () => {
  const args = parseArgs([
    '--channel-url=https://www.youtube.com/@X',
    '--max-results=5',
    '--oldest-post-date=2026-01-01',
    '--save-raw=/tmp/raw.json',
  ]);
  assert.equal(args.channelUrl, 'https://www.youtube.com/@X');
  assert.equal(args.maxResults, 5);
  assert.equal(args.saveRaw, '/tmp/raw.json');
});

test('parseArgs handles flags and --save-raw', () => {
  const args = parseArgs([...REQUIRED, '--dry-run', '--save-raw', '/tmp/x.json', '--queue-ceiling', '5']);
  assert.equal(args.dryRun, true);
  assert.equal(args.saveRaw, '/tmp/x.json');
  assert.equal(args.queueCeiling, 5);
});

test('parseArgs rejects an unknown flag and shows usage', () => {
  assert.throws(() => parseArgs(['--nope']), /Unknown argument: --nope/);
  assert.throws(() => parseArgs(['--nope']), /Usage:/);
});

test('--help short-circuits without needing the mandatory args', () => {
  assert.equal(parseArgs(['--help']).help, true);
  assert.equal(parseArgs(['-h']).help, true);
});

// The mandatory bounds are the guardrail against an unbounded channel pull,
// so they must fail closed — dry run or not.
test('validateArgs requires a channel source and all bounds', () => {
  assert.throws(() => validateArgs(parseArgs([])), /one of --channel-url or --from-airtable is required/);
  assert.throws(() => validateArgs(parseArgs([])), /--max-results is required/);
  assert.throws(() => validateArgs(parseArgs([])), /--oldest-post-date is required/);
});

test('validateArgs rejects both channel sources at once', () => {
  // Two sources of truth for "which channels" is precisely what moving the
  // config into Airtable exists to avoid, so refuse rather than pick one.
  const args = parseArgs([...REQUIRED, '--from-airtable']);
  assert.throws(() => validateArgs(args), /mutually exclusive/);
});

// --from-airtable multiplies the cost by the number of ticked channels, so it
// needs the per-channel bounds MORE than a single-channel run does.
test('--from-airtable still requires the per-channel bounds', () => {
  assert.throws(() => validateArgs(parseArgs(['--from-airtable'])), /--max-results is required/);
  assert.throws(() => validateArgs(parseArgs(['--from-airtable'])), /--oldest-post-date is required/);
  assert.doesNotThrow(() =>
    validateArgs(parseArgs(['--from-airtable', '--max-results', '5', '--oldest-post-date', '30 days']))
  );
});

test('parseArgs defaults --from-airtable to false', () => {
  assert.equal(parseArgs(REQUIRED).fromAirtable, false);
  assert.equal(parseArgs(['--from-airtable']).fromAirtable, true);
});

test('validateArgs rejects a zero, negative, or non-numeric --max-results', () => {
  for (const bad of ['0', '-1', 'abc']) {
    const args = parseArgs(['--channel-url', 'u', '--max-results', bad, '--oldest-post-date', '2026-01-01']);
    assert.throws(() => validateArgs(args), /--max-results/, `expected ${bad} to be rejected`);
  }
});

test('validateArgs passes on a complete arg set', () => {
  assert.doesNotThrow(() => validateArgs(parseArgs(REQUIRED)));
});

test('elideTranscripts summarises long values but keeps short ones intact', () => {
  const out = elideTranscripts({
    'Video Title': 'Short title',
    'Transcript (Full)': 'x'.repeat(5000),
    'Thumbnail (Image)': [{ url: 'https://example.com/a.jpg' }],
  });
  assert.equal(out['Video Title'], 'Short title');
  assert.equal(out['Transcript (Full)'], '<5000 chars>');
  assert.deepEqual(out['Thumbnail (Image)'], [{ url: 'https://example.com/a.jpg' }]);
});
