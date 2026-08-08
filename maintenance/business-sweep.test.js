const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { listPlaylistItems, drainPlaylists, DEFAULT_MAX_WRITES } = require('../playlist-drain/playlist-manager');
const { runBusinessSweep, boundedHarvest, watchUrl, readLedger, parseArgs } = require('./business-sweep');

function tmpStatePaths() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'business-sweep-'));
  return { lockPath: path.join(dir, 'run.lock'), ledgerPath: path.join(dir, 'ledger.jsonl') };
}

function playlistItem(id, videoId, position) {
  return { id, snippet: { position, resourceId: videoId ? { videoId } : {} }, contentDetails: videoId ? { videoId } : {} };
}

// A single in-memory YouTube fake shared by both the inventory read and the
// drain step, so they can never disagree about state the way two independent
// mocks might. Mirrors how the real API would behave.
function makeBusinessYoutube(initialState, businessChannelId = 'UC-business') {
  const state = new Map(Object.entries(initialState).map(([playlistId, items]) => [playlistId, [...items]]));
  return {
    state,
    channels: { list: async () => ({ data: { items: [{ id: businessChannelId, snippet: { title: 'Business' } }] } }) },
    playlistItems: {
      list: async ({ playlistId }) => ({ data: { items: state.get(playlistId) || [] } }),
      delete: async ({ id }) => {
        for (const [playlistId, items] of state) {
          const next = items.filter((item) => item.id !== id);
          if (next.length !== items.length) {
            state.set(playlistId, next);
            return;
          }
        }
        const error = new Error('not found');
        error.code = 404;
        throw error;
      },
    },
  };
}

function makeConfig(playlists) {
  return { businessChannelId: 'UC-business', playlists };
}

test('watchUrl builds a standard watch URL', () => {
  assert.equal(watchUrl('abc123'), 'https://www.youtube.com/watch?v=abc123');
});

test('parseArgs defaults to a safe read-only dry run', () => {
  const args = parseArgs([]);
  assert.equal(args.apply, false);
  assert.equal(args.queueCeiling, 30);
  assert.equal(args.batchCap, 10);
  assert.equal(args.costCap, 30);
});

test('parseArgs reads --apply and the numeric overrides', () => {
  const args = parseArgs(['--apply', '--max-writes', '5', '--queue-ceiling', '20', '--batch-cap', '3', '--cost-cap', '7']);
  assert.equal(args.apply, true);
  assert.equal(args.maxWrites, 5);
  assert.equal(args.queueCeiling, 20);
  assert.equal(args.batchCap, 3);
  assert.equal(args.costCap, 7);
});

test('parseArgs rejects an unknown flag', () => {
  assert.throws(() => parseArgs(['--nope']), /Unknown argument: --nope/);
});

test('dry-run reports inventory, duplicate findings, and the drain gate without spending or mutating', async () => {
  const { lockPath, ledgerPath } = tmpStatePaths();
  const businessYoutube = makeBusinessYoutube({
    'PL-a': [playlistItem('i1', 'vid-captured', 0), playlistItem('i2', 'vid-dup', 1)],
    'PL-b': [playlistItem('i3', 'vid-dup', 0), playlistItem('i4', 'vid-needs-harvest', 1)],
  });
  const config = makeConfig([
    { name: 'AI (Claude)', destinationPlaylistId: 'PL-a' },
    { name: 'Tech & Development', destinationPlaylistId: 'PL-b' },
  ]);
  const records = new Map([['vid-captured', { id: 'rec1', fields: { 'Transcript (Full)': 'yes' } }]]);
  const findVideo = async (videoId) => records.get(videoId) || null;

  let sweepChannelCalls = 0;
  const report = await runBusinessSweep({
    businessYoutube,
    config,
    apply: false,
    lockPath,
    ledgerPath,
    now: () => 1000,
    findVideo,
    sweepChannelFn: async () => { sweepChannelCalls += 1; throw new Error('must not be called in dry-run mode'); },
    countQueuedFn: async () => { throw new Error('must not be called in dry-run mode'); },
    drainPlaylistsFn: drainPlaylists,
    listPlaylistItemsFn: listPlaylistItems,
  });

  assert.equal(sweepChannelCalls, 0);
  assert.equal(report.mode, 'dry-run');
  assert.equal(report.inventory.totalItems, 4);
  assert.equal(report.inventory.uniqueVideoIds, 3);
  assert.equal(report.findings.duplicates.length, 1);
  assert.equal(report.findings.duplicates[0].videoId, 'vid-dup');
  assert.equal(report.findings.duplicates[0].occurrences.length, 2);
  assert.equal(report.classification.needsHarvest, 2);
  assert.equal(report.classification.alreadyCaptured, 1);
  assert.equal(report.harvest.totalRequested, 0);
  assert.equal(report.harvest.remaining.length, 2);
  assert.equal(report.drainDryRun.eligible, 1);
  assert.equal(report.drainGate.passed, true);
  assert.equal(report.drainApply, null);

  // Nothing was mutated: both playlists still hold everything they started with.
  assert.equal(businessYoutube.state.get('PL-a').length, 2);
  assert.equal(businessYoutube.state.get('PL-b').length, 2);

  // Lock was released, and the inventory snapshot made it into the ledger.
  assert.equal(fs.existsSync(lockPath), false);
  const events = readLedger(ledgerPath);
  assert.ok(events.some((e) => e.type === 'inventory'));
});

test('apply mode harvests a bounded batch, reconciles it, then drains what is now eligible', async () => {
  const { lockPath, ledgerPath } = tmpStatePaths();
  const businessYoutube = makeBusinessYoutube({
    'PL-a': [playlistItem('i1', 'vid-a', 0), playlistItem('i2', 'vid-b', 1)],
  });
  const config = makeConfig([{ name: 'AI (Claude)', destinationPlaylistId: 'PL-a' }]);

  const harvested = new Set();
  const alreadyCaptured = new Set(['vid-b']);
  const findVideo = async (videoId) => {
    if (alreadyCaptured.has(videoId) || harvested.has(videoId)) {
      return { id: `rec-${videoId}`, fields: { 'Transcript (Full)': 'text' } };
    }
    return null;
  };

  const sweepChannelCalls = [];
  const sweepChannelFn = async ({ channel }) => {
    sweepChannelCalls.push(channel.sourceUrls);
    const ids = channel.sourceUrls.map((url) => new URL(url).searchParams.get('v'));
    for (const id of ids) harvested.add(id);
    return {
      created: ids.length, updated: 0, wouldCreate: 0, wouldUpdate: 0, skipped: 0, channelsCreated: 0, errors: 0,
      returnedVideoIds: ids, processedVideoIds: ids, skippedVideoIds: [],
    };
  };

  const report = await runBusinessSweep({
    businessYoutube,
    config,
    apply: true,
    lockPath,
    ledgerPath,
    now: () => 2000,
    queueCeiling: 30,
    perBatchCap: 10,
    costCap: 30,
    findVideo,
    countQueuedFn: async () => 25, // headroom = 5, plenty for the 1 video that needs harvesting
    sweepChannelFn,
    drainPlaylistsFn: drainPlaylists,
    listPlaylistItemsFn: listPlaylistItems,
  });

  assert.equal(sweepChannelCalls.length, 1);
  assert.deepEqual(sweepChannelCalls[0], ['https://www.youtube.com/watch?v=vid-a']);
  assert.equal(report.harvest.totalRequested, 1);
  assert.equal(report.harvest.remaining.length, 0);
  assert.deepEqual(report.harvest.batches[0].missingFromDataset, []);
  assert.deepEqual(report.harvest.batches[0].verified, ['vid-a']);

  assert.equal(report.drainDryRun.eligible, 2);
  assert.equal(report.drainGate.passed, true);
  assert.ok(report.drainApply);
  assert.equal(report.drainApply.deleted, 2);
  assert.equal(businessYoutube.state.get('PL-a').length, 0);

  const events = readLedger(ledgerPath);
  const harvestIntent = events.find((e) => e.type === 'intent' && e.step === 'harvest-batch');
  const harvestResult = events.find((e) => e.type === 'result' && e.intentId === harvestIntent.id);
  assert.equal(harvestResult.status, 'ok');
  const drainIntent = events.find((e) => e.type === 'intent' && e.step === 'drain-apply');
  const drainResult = events.find((e) => e.type === 'result' && e.intentId === drainIntent.id);
  assert.equal(drainResult.status, 'ok');
  assert.equal(fs.existsSync(lockPath), false);
});

test('boundedHarvest stops at zero headroom without ever calling sweepChannel', async () => {
  let calls = 0;
  const result = await boundedHarvest({
    needsHarvest: ['v1', 'v2', 'v3'],
    queueCeiling: 30,
    perBatchCap: 10,
    costCap: 30,
    oldestPostDate: '2015-01-01',
    countQueuedFn: async () => 30, // headroom = 0
    sweepChannelFn: async () => { calls += 1; return {}; },
    findVideo: async () => null,
    ledgerPath: tmpStatePaths().ledgerPath,
    now: () => 1,
  });
  assert.equal(calls, 0);
  assert.deepEqual(result.remaining, ['v1', 'v2', 'v3']);
  assert.match(result.stoppedReason, /ceiling/i);
});

test('boundedHarvest stops on a reconciliation gap instead of compounding it into the next batch', async () => {
  const { ledgerPath } = tmpStatePaths();
  let calls = 0;
  const result = await boundedHarvest({
    needsHarvest: ['v1', 'v2'],
    queueCeiling: 30,
    perBatchCap: 1, // forces two separate batches if it kept going
    costCap: 30,
    oldestPostDate: '2015-01-01',
    countQueuedFn: async () => 0, // plenty of headroom
    sweepChannelFn: async () => {
      calls += 1;
      // Simulate Apify not returning the requested video at all.
      return { created: 0, updated: 0, wouldCreate: 0, wouldUpdate: 0, skipped: 0, channelsCreated: 0, errors: 0, returnedVideoIds: [], processedVideoIds: [], skippedVideoIds: [] };
    },
    findVideo: async () => null,
    ledgerPath,
    now: () => 1,
  });
  assert.equal(calls, 1, 'must not attempt the second batch after a reconciliation gap in the first');
  assert.deepEqual(result.remaining, ['v2']);
  assert.match(result.stoppedReason, /reconciliation gap/i);
});

test('drain gate blocks apply when eligible exceeds the write budget, even though a dry run always reports deferred=0', async () => {
  const { lockPath, ledgerPath } = tmpStatePaths();
  const businessYoutube = makeBusinessYoutube({
    'PL-a': [playlistItem('i1', 'vid-a', 0), playlistItem('i2', 'vid-b', 1)],
  });
  const config = makeConfig([{ name: 'AI (Claude)', destinationPlaylistId: 'PL-a' }]);
  const findVideo = async () => ({ id: 'rec', fields: { 'Transcript (Full)': 'text' } }); // both eligible

  const report = await runBusinessSweep({
    businessYoutube,
    config,
    apply: true,
    lockPath,
    ledgerPath,
    now: () => 3000,
    maxDrainWrites: 1, // budget of 1, but 2 items are eligible
    findVideo,
    countQueuedFn: async () => 30,
    sweepChannelFn: async () => { throw new Error('must not be called — nothing needs harvest'); },
    drainPlaylistsFn: drainPlaylists,
    listPlaylistItemsFn: listPlaylistItems,
  });

  assert.equal(report.drainDryRun.eligible, 2);
  assert.equal(report.drainDryRun.deferred, 0, 'dry-run never populates deferred — this is the known gap the gate must not trust');
  assert.equal(report.drainGate.eligibleWithinBudget, false);
  assert.equal(report.drainGate.passed, false);
  assert.equal(report.drainApply, null);
  assert.equal(businessYoutube.state.get('PL-a').length, 2, 'nothing should have been deleted');
});

// The 2026-08-06 live run logged `"status":"partial","errors":1` and nothing
// else, so the one thing that actually failed was unrecoverable after the
// fact. A count is not a diagnosis: this asserts the ledger keeps WHICH item
// failed and why, which is the whole point of a write-ahead log.
test('a partial drain records what failed in the ledger, not just how many', async () => {
  const { lockPath, ledgerPath } = tmpStatePaths();
  const businessYoutube = makeBusinessYoutube({
    'PL-a': [playlistItem('i1', 'vid-a', 0), playlistItem('i2', 'vid-b', 1)],
  });
  const config = makeConfig([{ name: 'AI (Claude)', destinationPlaylistId: 'PL-a' }]);

  // vid-b's delete fails with a non-404 — the real "errors: 1" shape.
  const realDelete = businessYoutube.playlistItems.delete;
  businessYoutube.playlistItems.delete = async ({ id }) => {
    if (id === 'i2') throw new Error('backendError: playlist item delete rejected');
    return realDelete({ id });
  };

  const report = await runBusinessSweep({
    businessYoutube,
    config,
    apply: true,
    lockPath,
    ledgerPath,
    now: () => 5000,
    findVideo: async (videoId) => ({ id: `rec-${videoId}`, fields: { 'Transcript (Full)': 'text' } }),
    countQueuedFn: async () => 30, // no headroom — this test is about the drain, not the harvest
    sweepChannelFn: async () => { throw new Error('harvest must not run in this test'); },
    drainPlaylistsFn: drainPlaylists,
    listPlaylistItemsFn: listPlaylistItems,
  });

  assert.equal(report.drainApply.deleted, 1);
  assert.equal(report.drainApply.errors.length, 1);

  const events = readLedger(ledgerPath);
  const drainIntent = events.find((e) => e.type === 'intent' && e.step === 'drain-apply');
  const drainResult = events.find((e) => e.type === 'result' && e.intentId === drainIntent.id);
  assert.equal(drainResult.status, 'partial');
  assert.equal(drainResult.errors, 1, 'the existing count field stays a count');
  assert.ok(Array.isArray(drainResult.errorDetails), 'the ledger must persist the failures themselves');
  assert.equal(drainResult.errorDetails.length, 1);
  assert.equal(drainResult.errorDetails[0].videoId, 'vid-b');
  assert.equal(drainResult.errorDetails[0].playlist, 'AI (Claude)');
  assert.match(drainResult.errorDetails[0].error, /backendError/);
});

test('runBusinessSweep releases the lock even when a step throws', async () => {
  const { lockPath, ledgerPath } = tmpStatePaths();
  const businessYoutube = makeBusinessYoutube({ 'PL-a': [playlistItem('i1', 'vid-a', 0)] });
  const config = makeConfig([{ name: 'AI (Claude)', destinationPlaylistId: 'PL-a' }]);

  await assert.rejects(() =>
    runBusinessSweep({
      businessYoutube,
      config,
      apply: false,
      lockPath,
      ledgerPath,
      now: () => 4000,
      findVideo: async () => { throw new Error('boom'); },
      drainPlaylistsFn: drainPlaylists,
      listPlaylistItemsFn: listPlaylistItems,
    })
  );
  assert.equal(fs.existsSync(lockPath), false);
});
