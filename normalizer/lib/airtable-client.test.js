const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  findVideoByVideoId,
  findChannelByHandle,
  listAllRecords,
  listHarvestChannels,
  upsertChannel,
  upsertVideo,
} = require('./airtable-client');

const KEY = 'patFAKE';
const BASE = 'appFAKE';

// The module calls global fetch directly, so stub it. `router` receives a
// decoded call and returns the JSON body to reply with (or undefined to fail
// loudly, which catches an unexpected extra request).
function installFetch(router) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const call = {
      url: decodeURIComponent(String(url)),
      method: options.method || 'GET',
      body: options.body ? JSON.parse(options.body) : null,
    };
    calls.push(call);
    const reply = router(call);
    if (reply === undefined) throw new Error(`no stub for ${call.method} ${call.url}`);
    return { ok: true, status: 200, json: async () => reply };
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}

// --- invariant 2: duplicates must refuse, not silently pick one -------------

test('findVideoByVideoId throws when two records share a Video ID', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recAAA' }, { id: 'recBBB' }] }));
  t.after(f.restore);

  await assert.rejects(
    () => findVideoByVideoId(KEY, BASE, 'oTphk2SVHNc'),
    (err) => {
      assert.match(err.message, /2 records share Video ID 'oTphk2SVHNc'/);
      assert.match(err.message, /recAAA, recBBB/);
      assert.match(err.message, /invariant 2/);
      return true;
    }
  );
});

test('findChannelByHandle throws when two channels share a handle', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recC1' }, { id: 'recC2' }] }));
  t.after(f.restore);
  await assert.rejects(() => findChannelByHandle(KEY, BASE, '@Dup'), /2 records share Channel Handle/);
});

test('a single match is returned normally', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recOnly' }] }));
  t.after(f.restore);
  assert.equal((await findVideoByVideoId(KEY, BASE, 'abc')).id, 'recOnly');
});

// --- channel keying: @handle primary, UC fallback ---------------------------

test('upsertChannel matches on @handle and never queries the UC id', async (t) => {
  const f = installFetch((call) =>
    call.url.includes("{Channel Handle}='@WayneStLedger'") ? { records: [{ id: 'recChan' }] } : undefined
  );
  t.after(f.restore);

  const result = await upsertChannel(KEY, BASE, {
    handleKey: '@WayneStLedger',
    fallbackKey: 'UCxxx',
    channelName: 'Wayne',
  });

  assert.deepEqual(result, { recordId: 'recChan', created: false, matchedOn: 'handle', statsUpdated: false });
  assert.equal(f.calls.length, 1, 'UC fallback should not be queried after a handle hit');
});

test('upsertChannel falls back to the UC id when the handle misses', async (t) => {
  const f = installFetch((call) =>
    call.url.includes("{Channel Handle}='UCxxx'") ? { records: [{ id: 'recLegacy' }] } : { records: [] }
  );
  t.after(f.restore);

  const result = await upsertChannel(KEY, BASE, {
    handleKey: '@Wayne',
    fallbackKey: 'UCxxx',
    channelName: 'Wayne',
  });

  assert.equal(result.recordId, 'recLegacy');
  assert.equal(result.matchedOn, 'channelId');
  assert.equal(f.calls.length, 2);
});

test('upsertChannel creates with the @handle, not the UC id', async (t) => {
  const f = installFetch((call) =>
    call.method === 'POST' ? { id: 'recNew' } : { records: [] }
  );
  t.after(f.restore);

  const result = await upsertChannel(KEY, BASE, {
    handleKey: '@Wayne',
    fallbackKey: 'UCxxx',
    channelName: 'Wayne',
    channelUrl: 'https://www.youtube.com/@Wayne',
  });

  assert.deepEqual(result, { recordId: 'recNew', created: true, statsUpdated: false });
  const post = f.calls.find((c) => c.method === 'POST');
  assert.equal(post.body.fields['Channel Handle'], '@Wayne');
  assert.equal(post.body.fields.Platform, 'YouTube');
});

test('upsertChannel skips when it has no usable key', async (t) => {
  const f = installFetch(() => undefined);
  t.after(f.restore);
  const result = await upsertChannel(KEY, BASE, { handleKey: null, fallbackKey: null, channelName: 'X' });
  assert.equal(result.skipped, 'missing channel info');
  assert.equal(f.calls.length, 0, 'should not hit the API with no key');
});

// --- channel stats: refresh on match, never touch Track ---------------------

test('upsertChannel PATCHes stats onto an existing row and leaves Track alone', async (t) => {
  const f = installFetch((call) =>
    call.method === 'PATCH' ? { id: 'recChan' } : { records: [{ id: 'recChan' }] }
  );
  t.after(f.restore);

  const result = await upsertChannel(KEY, BASE, {
    handleKey: '@Wayne',
    fallbackKey: 'UCxxx',
    channelName: 'Wayne',
    stats: { Subscribers: 174, 'Total Views': 88652, 'Stats Captured At': '2026-07-30T00:00:00.000Z' },
  });

  assert.equal(result.statsUpdated, true);
  const patch = f.calls.find((c) => c.method === 'PATCH');
  assert.equal(patch.body.fields.Subscribers, 174);
  // Track is human-owned routing — the Channels analogue of invariant 3. A
  // blank/overwritten Track silently drops the channel out of the AIHS view.
  assert.equal('Track' in patch.body.fields, false, 'Track must never be written');
  assert.equal('Channel Handle' in patch.body.fields, false, 'the upsert key must never be rewritten');
});

test('upsertChannel skips the stats PATCH entirely when there are no stats', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recChan' }] }));
  t.after(f.restore);

  const result = await upsertChannel(KEY, BASE, { handleKey: '@Wayne', channelName: 'Wayne', stats: {} });

  assert.equal(result.statsUpdated, false);
  assert.equal(f.calls.every((c) => c.method === 'GET'), true, 'an empty stats object must not trigger a write');
});

test('upsertChannel dry run never PATCHes stats', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recChan' }] }));
  t.after(f.restore);

  const result = await upsertChannel(
    KEY,
    BASE,
    { handleKey: '@Wayne', channelName: 'Wayne', stats: { Subscribers: 174 } },
    { dryRun: true }
  );

  assert.equal(result.statsUpdated, false);
  assert.equal(f.calls.every((c) => c.method === 'GET'), true, 'no writes in dry run');
});

test('a new channel is created with its stats already populated', async (t) => {
  const f = installFetch((call) => (call.method === 'POST' ? { id: 'recNew' } : { records: [] }));
  t.after(f.restore);

  await upsertChannel(KEY, BASE, {
    handleKey: '@Wayne',
    channelName: 'Wayne',
    stats: { Subscribers: 174 },
  });

  const post = f.calls.find((c) => c.method === 'POST');
  assert.equal(post.body.fields.Subscribers, 174);
  assert.equal(post.body.fields['Channel Handle'], '@Wayne');
});

// --- the harvest queue lives in Airtable, not in a repo file ----------------

test('listHarvestChannels returns Harvest?-ticked rows with their Source URL', async (t) => {
  const f = installFetch(() => ({
    records: [
      { id: 'recA', fields: { 'Channel Name': 'A', 'Source URL': 'https://youtube.com/@a' } },
      { id: 'recB', fields: { 'Channel Name': 'B' } },
    ],
  }));
  t.after(f.restore);

  const rows = await listHarvestChannels(KEY, BASE);

  assert.match(f.calls[0].url, /\{Harvest\?\}=1/);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].sourceUrl, 'https://youtube.com/@a');
  // A ticked row with no Source URL is surfaced, not silently dropped here —
  // the CLI warns about it so the misconfiguration is visible.
  assert.equal(rows[1].sourceUrl, null);
});

// --- listAllRecords follows the offset cursor -------------------------------

test('listAllRecords pages through offset until it runs out', async (t) => {
  const pages = [
    { records: [{ id: 'rec1' }, { id: 'rec2' }], offset: 'cursor1' },
    { records: [{ id: 'rec3' }], offset: undefined },
  ];
  let call = 0;
  const f = installFetch(() => pages[call++]);
  t.after(f.restore);

  const records = await listAllRecords(KEY, BASE, 'Videos', { fields: ['Video ID'] });

  assert.deepEqual(records.map((r) => r.id), ['rec1', 'rec2', 'rec3']);
  assert.equal(f.calls.length, 2);
  assert.doesNotMatch(f.calls[0].url, /offset=/);
  assert.match(f.calls[1].url, /offset=cursor1/);
  assert.match(f.calls[0].url, /fields\[\]=Video ID/);
});

test('listAllRecords returns everything on a single page', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recOnly' }] }));
  t.after(f.restore);

  const records = await listAllRecords(KEY, BASE, 'Channels');

  assert.equal(records.length, 1);
  assert.equal(f.calls.length, 1);
});

// --- invariant 3: never touch Triage Status on update ----------------------

test('update PATCHes only updateFields — Triage Status cannot be clobbered', async (t) => {
  const f = installFetch((call) =>
    call.method === 'PATCH' ? { id: 'recExisting' } : { records: [{ id: 'recExisting' }] }
  );
  t.after(f.restore);

  const result = await upsertVideo(KEY, BASE, {
    videoId: 'abc',
    channelRecordId: 'recChan',
    createOnlyFields: { 'Triage Status': 'Queued', 'Intake Source': 'Sweep', 'Video Title': 'T' },
    updateFields: { 'Transcript Source': 'apify-youtube-scraper' },
  });

  assert.equal(result.action, 'updated');
  const patch = f.calls.find((c) => c.method === 'PATCH');
  assert.deepEqual(patch.body.fields, { 'Transcript Source': 'apify-youtube-scraper' });
  assert.equal('Triage Status' in patch.body.fields, false);
  assert.equal('Channel' in patch.body.fields, false, 'Channel link is create-only');
});

test('create merges both field sets and links the Channel', async (t) => {
  const f = installFetch((call) => (call.method === 'POST' ? { id: 'recMade' } : { records: [] }));
  t.after(f.restore);

  const result = await upsertVideo(KEY, BASE, {
    videoId: 'abc',
    channelRecordId: 'recChan',
    createOnlyFields: { 'Triage Status': 'Queued' },
    updateFields: { 'Transcript Source': 'apify-youtube-scraper' },
  });

  assert.equal(result.action, 'created');
  const post = f.calls.find((c) => c.method === 'POST');
  assert.equal(post.body.fields['Triage Status'], 'Queued');
  assert.deepEqual(post.body.fields.Channel, ['recChan']);
});

// --- dry run writes nothing ------------------------------------------------

test('dry run performs the lookup but never writes, and returns the payload', async (t) => {
  const f = installFetch(() => ({ records: [] }));
  t.after(f.restore);

  const result = await upsertVideo(
    KEY,
    BASE,
    {
      videoId: 'abc',
      channelRecordId: '<dry-run: would create>',
      createOnlyFields: { 'Triage Status': 'Queued' },
      updateFields: { 'Transcript Source': 'apify-youtube-scraper' },
    },
    { dryRun: true }
  );

  assert.equal(result.action, 'would-create');
  assert.ok(result.fields, 'dry run must expose the payload so the CLI can print it');
  assert.equal(
    'Channel' in result.fields,
    false,
    'the <dry-run sentinel must never be written into a Channel link'
  );
  assert.equal(f.calls.every((c) => c.method === 'GET'), true, 'no writes in dry run');
});

test('dry run on an existing record returns the PATCH payload it would send', async (t) => {
  const f = installFetch(() => ({ records: [{ id: 'recExisting' }] }));
  t.after(f.restore);

  const result = await upsertVideo(
    KEY,
    BASE,
    {
      videoId: 'abc',
      channelRecordId: 'recChan',
      createOnlyFields: { 'Triage Status': 'Queued' },
      updateFields: { 'Transcript Source': 'apify-youtube-scraper' },
    },
    { dryRun: true }
  );

  assert.equal(result.action, 'would-update');
  assert.deepEqual(result.fields, { 'Transcript Source': 'apify-youtube-scraper' });
});
