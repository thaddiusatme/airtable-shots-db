const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  findVideoByVideoId,
  findChannelByHandle,
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

  assert.deepEqual(result, { recordId: 'recChan', created: false, matchedOn: 'handle' });
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

  assert.deepEqual(result, { recordId: 'recNew', created: true });
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
