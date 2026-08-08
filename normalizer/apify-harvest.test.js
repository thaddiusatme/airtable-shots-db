const { test } = require('node:test');
const assert = require('node:assert/strict');

const { parseArgs, parseDotEnv, validateArgs, elideTranscripts, emptySummary, mergeSummary, blankTrackWarning } = require('./apify-harvest');

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
  assert.throws(() => validateArgs(parseArgs([])), /one of --channel-url, --playlist-url, or --from-airtable is required/);
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

// --- playlist mode -----------------------------------------------------------
//
// The Watch Later -> playlist -> Airtable leg went dark when the browser-
// extension playlist harvest was retired in favor of the channel-only
// normalizer. The actor's own docs show startUrls accepts a playlist link
// (https://www.youtube.com/playlist?list=...) the same way it accepts a
// channel link, and transform.js already derives Channel per dataset item
// (not from the input URL), so a playlist is just a third channel-selection
// mode, not a new data path.

test('parseArgs reads --playlist-url', () => {
  const args = parseArgs([
    '--playlist-url', 'https://www.youtube.com/playlist?list=PL123',
    '--max-results', '5',
    '--oldest-post-date', '2026-01-01',
  ]);
  assert.equal(args.playlistUrl, 'https://www.youtube.com/playlist?list=PL123');
});

test('validateArgs accepts --playlist-url alone as the channel source', () => {
  assert.doesNotThrow(() =>
    validateArgs(parseArgs([
      '--playlist-url', 'https://www.youtube.com/playlist?list=PL123',
      '--max-results', '5',
      '--oldest-post-date', '2026-01-01',
    ]))
  );
});

test('validateArgs rejects --playlist-url combined with --channel-url', () => {
  const args = parseArgs([...REQUIRED, '--playlist-url', 'https://www.youtube.com/playlist?list=PL123']);
  assert.throws(() => validateArgs(args), /mutually exclusive/);
});

test('validateArgs rejects --playlist-url combined with --from-airtable', () => {
  const args = parseArgs([
    '--playlist-url', 'https://www.youtube.com/playlist?list=PL123',
    '--from-airtable',
    '--max-results', '5',
    '--oldest-post-date', '2026-01-01',
  ]);
  assert.throws(() => validateArgs(args), /mutually exclusive/);
});

test('validateArgs still requires a channel source when none of the three is given', () => {
  assert.throws(
    () => validateArgs(parseArgs([])),
    /one of --channel-url, --playlist-url, or --from-airtable is required/
  );
});

// --- video-urls mode ---------------------------------------------------------
//
// Discovered 2026-08-06: the Apify streamers/youtube-scraper actor cannot read
// UNLISTED playlists (NO_VIDEOS, confirmed live against two real playlists,
// while an identical call against a public playlist worked). The individual
// videos in those playlists are not themselves unlisted, so feeding their
// watch URLs straight into startUrls sidesteps the blocker entirely — and per
// lib/apify-client.js's header comment, a single-video startUrls run is the
// ORIGINAL, most-verified shape this actor was probed with (2026-07-29),
// more so than channel or playlist mode.

test('parseArgs reads --video-urls', () => {
  const args = parseArgs([
    '--video-urls', 'https://www.youtube.com/watch?v=AAA,https://www.youtube.com/watch?v=BBB',
    '--max-results', '5',
    '--oldest-post-date', '2026-01-01',
  ]);
  assert.equal(args.videoUrls, 'https://www.youtube.com/watch?v=AAA,https://www.youtube.com/watch?v=BBB');
});

test('validateArgs accepts --video-urls alone as the channel source', () => {
  assert.doesNotThrow(() =>
    validateArgs(parseArgs([
      '--video-urls', 'https://www.youtube.com/watch?v=AAA',
      '--max-results', '5',
      '--oldest-post-date', '2026-01-01',
    ]))
  );
});

test('validateArgs rejects --video-urls combined with --channel-url', () => {
  const args = parseArgs([...REQUIRED, '--video-urls', 'https://www.youtube.com/watch?v=AAA']);
  assert.throws(() => validateArgs(args), /mutually exclusive/);
});

test('validateArgs rejects --video-urls combined with --playlist-url', () => {
  const args = parseArgs([
    '--video-urls', 'https://www.youtube.com/watch?v=AAA',
    '--playlist-url', 'https://www.youtube.com/playlist?list=PL123',
    '--max-results', '5',
    '--oldest-post-date', '2026-01-01',
  ]);
  assert.throws(() => validateArgs(args), /mutually exclusive/);
});

test('validateArgs rejects a blank --video-urls', () => {
  const args = parseArgs(['--video-urls', '  , ,  ', '--max-results', '5', '--oldest-post-date', '2026-01-01']);
  assert.throws(() => validateArgs(args), /--video-urls must contain at least one URL/);
});

// Silently dropping a video the user explicitly named is worse than a loud
// refusal — --max-results is a per-channel COST guardrail everywhere else,
// but here a too-low value would truncate the exact list asked for.
test('validateArgs rejects --max-results lower than the --video-urls count', () => {
  const args = parseArgs([
    '--video-urls', 'https://www.youtube.com/watch?v=AAA,https://www.youtube.com/watch?v=BBB,https://www.youtube.com/watch?v=CCC',
    '--max-results', '2',
    '--oldest-post-date', '2026-01-01',
  ]);
  assert.throws(() => validateArgs(args), /--max-results \(2\) is less than the 3 URL\(s\)/);
});

test('validateArgs accepts --max-results equal to the --video-urls count', () => {
  assert.doesNotThrow(() =>
    validateArgs(parseArgs([
      '--video-urls', 'https://www.youtube.com/watch?v=AAA,https://www.youtube.com/watch?v=BBB',
      '--max-results', '2',
      '--oldest-post-date', '2026-01-01',
    ]))
  );
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

// --- .env parsing -----------------------------------------------------------
//
// Quoting a value in .env is ordinary — most .env documentation shows it, and
// anything pasted from a shell export arrives quoted. A parser that keeps the
// quotes hands Airtable `"patXXX"` and gets a 401, which reads as a bad token
// rather than a bad parse. That is a long way to walk for a stray character.

test('parseDotEnv reads a bare KEY=value line', () => {
  assert.deepEqual(parseDotEnv('AIRTABLE_BASE_ID=appWSbpJAxjCyLfrZ'), {
    AIRTABLE_BASE_ID: 'appWSbpJAxjCyLfrZ',
  });
});

test('parseDotEnv strips surrounding double quotes', () => {
  assert.deepEqual(parseDotEnv('AIRTABLE_API_KEY="patXXX"'), { AIRTABLE_API_KEY: 'patXXX' });
});

test('parseDotEnv strips surrounding single quotes', () => {
  assert.deepEqual(parseDotEnv("APIFY_TOKEN='apify_api_XXX'"), { APIFY_TOKEN: 'apify_api_XXX' });
});

test('parseDotEnv leaves an unmatched quote alone rather than guessing', () => {
  // Only a matched pair is a quote. `"oops` is a value that starts with a
  // quote character, and silently eating it would corrupt a real secret.
  assert.deepEqual(parseDotEnv('APIFY_TOKEN="oops'), { APIFY_TOKEN: '"oops' });
  assert.deepEqual(parseDotEnv('APIFY_TOKEN=\'mixed"'), { APIFY_TOKEN: '\'mixed"' });
});

test('parseDotEnv keeps quotes that are inside the value', () => {
  assert.deepEqual(parseDotEnv('APIFY_TOKEN=a"b"c'), { APIFY_TOKEN: 'a"b"c' });
});

test('parseDotEnv keeps an "=" that appears inside the value', () => {
  assert.deepEqual(parseDotEnv('AIRTABLE_API_KEY=pat.a=b=c'), { AIRTABLE_API_KEY: 'pat.a=b=c' });
});

test('parseDotEnv ignores comments, blank lines, and lowercase keys', () => {
  const text = ['# a comment', '', '   ', 'lowercase=ignored', 'APIFY_TOKEN=t'].join('\n');
  assert.deepEqual(parseDotEnv(text), { APIFY_TOKEN: 't' });
});

test('parseDotEnv reads an empty value as an empty string', () => {
  assert.deepEqual(parseDotEnv('APIFY_TOKEN='), { APIFY_TOKEN: '' });
});

// --- structured summary (reconciliation for the maintenance orchestrator) ---
//
// A caller that named exact videos (e.g. business-sweep.js's bounded harvest)
// must be able to tell "asked for" apart from "actually landed" without
// parsing console text — see maintenance/business-sweep.js.

test('emptySummary starts every videoId list empty', () => {
  assert.deepEqual(emptySummary(), {
    created: 0,
    updated: 0,
    wouldCreate: 0,
    wouldUpdate: 0,
    skipped: 0,
    channelsCreated: 0,
    errors: 0,
    returnedVideoIds: [],
    processedVideoIds: [],
    skippedVideoIds: [],
  });
});

test('mergeSummary concatenates videoId lists instead of adding them as numbers', () => {
  const total = emptySummary();
  mergeSummary(total, {
    ...emptySummary(),
    created: 2,
    returnedVideoIds: ['AAA', 'BBB'],
    processedVideoIds: ['AAA'],
    skippedVideoIds: ['BBB'],
  });
  mergeSummary(total, {
    ...emptySummary(),
    created: 1,
    returnedVideoIds: ['CCC'],
    processedVideoIds: ['CCC'],
    skippedVideoIds: [],
  });
  assert.equal(total.created, 3);
  assert.deepEqual(total.returnedVideoIds, ['AAA', 'BBB', 'CCC']);
  assert.deepEqual(total.processedVideoIds, ['AAA', 'CCC']);
  assert.deepEqual(total.skippedVideoIds, ['BBB']);
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

// CLAUDE.md: Track stopped gating the working view 2026-08-06 — every Queued
// video reaches triage regardless of Track now. The warning used to claim
// otherwise (a live 2026-08-06 run still logged the pre-cutover "silently
// vanish... Track = AIHS OR Tooling-watch" text), which is simply false today.
test('blankTrackWarning does not claim Track still gates the working view', () => {
  const warning = blankTrackWarning('Ali Abdaal', '@aliabdaal');
  assert.match(warning, /Ali Abdaal/);
  assert.match(warning, /@aliabdaal/);
  assert.doesNotMatch(warning, /silently vanish/);
  assert.doesNotMatch(warning, /Track = AIHS OR Tooling-watch/);
});
