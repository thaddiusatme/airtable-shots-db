const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  assertExpectedChannel,
  hasVerifiedTranscript,
  isOrderedPrefix,
  listPlaylistItems,
  migratePlaylists,
  drainPlaylists,
  readConfig,
  waitForExactPlaylist,
  writeConfigAtomic,
} = require('./playlist-manager');

function playlistItem(id, videoId, position) {
  return {
    id,
    snippet: {
      position,
      resourceId: videoId ? { videoId } : {},
    },
    contentDetails: videoId ? { videoId } : {},
  };
}

test('assertExpectedChannel accepts only the configured business channel', async () => {
  const youtube = {
    channels: {
      list: async () => ({ data: { items: [{ id: 'UC-business', snippet: { title: 'Business' } }] } }),
    },
  };
  const channel = await assertExpectedChannel(youtube, 'UC-business');
  assert.equal(channel.id, 'UC-business');
  await assert.rejects(() => assertExpectedChannel(youtube, 'UC-other'), /wrong YouTube channel/i);
});

test('listPlaylistItems paginates, sorts by position, preserves duplicates, and reports unavailable entries', async () => {
  const pages = new Map([
    [undefined, {
      data: {
        items: [playlistItem('pi-2', 'video-b', 2), playlistItem('pi-0', 'video-a', 0)],
        nextPageToken: 'next',
      },
    }],
    ['next', {
      data: {
        items: [playlistItem('pi-3', null, 3), playlistItem('pi-1', 'video-a', 1)],
      },
    }],
  ]);
  const youtube = { playlistItems: { list: async ({ pageToken }) => pages.get(pageToken) } };
  const result = await listPlaylistItems(youtube, 'PL-source');
  assert.deepEqual(result.items.map((item) => item.videoId), ['video-a', 'video-a', 'video-b']);
  assert.deepEqual(result.items.map((item) => item.playlistItemId), ['pi-0', 'pi-1', 'pi-2']);
  assert.equal(result.unavailable.length, 1);
  assert.equal(result.unavailable[0].position, 3);
});

test('listPlaylistItems carries when each item was added to the playlist, not when the video was published', async () => {
  const item = playlistItem('pi-0', 'video-a', 0);
  item.snippet.publishedAt = '2026-09-28T17:03:00Z';
  item.contentDetails.videoPublishedAt = '2024-01-02T00:00:00Z';
  const youtube = { playlistItems: { list: async () => ({ data: { items: [item, playlistItem('pi-1', 'video-b', 1)] } }) } };
  const result = await listPlaylistItems(youtube, 'PL-source');
  assert.deepEqual(result.items.map((entry) => entry.addedAt), ['2026-09-28T17:03:00Z', null]);
});

test('isOrderedPrefix requires exact order and duplicate multiplicity', () => {
  assert.equal(isOrderedPrefix(['a', 'a'], ['a', 'a', 'b']), true);
  assert.equal(isOrderedPrefix(['a', 'b'], ['a', 'a', 'b']), false);
  assert.equal(isOrderedPrefix(['a', 'b', 'c'], ['a', 'b']), false);
});

test('writeConfigAtomic persists destination IDs without corrupting the config', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'playlist-config-'));
  const configPath = path.join(dir, 'playlists.json');
  writeConfigAtomic(configPath, { businessChannelId: 'UC1', playlists: [] });
  assert.deepEqual(readConfig(configPath), { businessChannelId: 'UC1', playlists: [] });
  assert.equal(fs.existsSync(`${configPath}.tmp`), false);
});

test('migratePlaylists resumes from an exact destination prefix and respects max writes', async () => {
  const inserted = [];
  const config = {
    businessChannelId: 'UC-business',
    privacyStatus: 'unlisted',
    playlists: [{
      name: 'AI',
      sourcePlaylistId: 'PL-source',
      destinationPlaylistId: 'PL-destination',
    }],
  };
  const sourceYoutube = {
    playlists: { list: async () => ({ data: { items: [{ id: 'PL-source', snippet: { title: 'AI', description: '' } }] } }) },
    playlistItems: { list: async () => ({ data: { items: [playlistItem('s1', 'a', 0), playlistItem('s2', 'a', 1), playlistItem('s3', 'b', 2)] } }) },
  };
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business', snippet: { title: 'Business' } }] } }) },
    playlists: { list: async () => ({ data: { items: [] } }) },
    playlistItems: {
      list: async () => ({ data: { items: [playlistItem('d1', 'a', 0)] } }),
      insert: async ({ requestBody }) => {
        inserted.push(requestBody.snippet.resourceId.videoId);
        return { data: { id: `new-${inserted.length}` } };
      },
    },
  };
  const result = await migratePlaylists({
    sourceYoutube,
    businessYoutube,
    config,
    apply: true,
    maxWrites: 1,
    persistConfig: () => {},
  });
  assert.deepEqual(inserted, ['a']);
  assert.equal(result.writes, 1);
  assert.equal(result.complete, false);
  assert.equal(result.playlists[0].remaining, 1);
});

test('migratePlaylists aborts rather than appending to a divergent destination', async () => {
  const config = {
    businessChannelId: 'UC-business',
    privacyStatus: 'unlisted',
    playlists: [{ name: 'AI', sourcePlaylistId: 'PL-source', destinationPlaylistId: 'PL-destination' }],
  };
  const sourceYoutube = {
    playlists: { list: async () => ({ data: { items: [{ id: 'PL-source', snippet: { title: 'AI' } }] } }) },
    playlistItems: { list: async () => ({ data: { items: [playlistItem('s1', 'a', 0), playlistItem('s2', 'b', 1)] } }) },
  };
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlists: { list: async () => ({ data: { items: [] } }) },
    playlistItems: { list: async () => ({ data: { items: [playlistItem('d1', 'b', 0)] } }) },
  };
  await assert.rejects(
    () => migratePlaylists({ sourceYoutube, businessYoutube, config, apply: true, persistConfig: () => {} }),
    /diverges/i
  );
});

test('migratePlaylists dry-run never creates or inserts', async () => {
  let writes = 0;
  const config = {
    businessChannelId: 'UC-business',
    privacyStatus: 'unlisted',
    playlists: [{ name: 'AI', sourcePlaylistId: 'PL-source', destinationPlaylistId: null }],
  };
  const sourceYoutube = {
    playlists: { list: async () => ({ data: { items: [{ id: 'PL-source', snippet: { title: 'AI' } }] } }) },
    playlistItems: { list: async () => ({ data: { items: [playlistItem('s1', 'a', 0)] } }) },
  };
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlists: {
      list: async () => ({ data: { items: [] } }),
      insert: async () => { writes += 1; },
    },
    playlistItems: { insert: async () => { writes += 1; } },
  };
  const result = await migratePlaylists({ sourceYoutube, businessYoutube, config });
  assert.equal(writes, 0);
  assert.equal(result.mode, 'dry-run');
  assert.equal(result.playlists[0].requiredWrites, 2);
  assert.equal(config.playlists[0].destinationPlaylistId, null);
});

test('migratePlaylists creates once, persists immediately, copies order, and validates exact IDs', async () => {
  const destinationItems = [];
  const persisted = [];
  const delays = [];
  const config = {
    businessChannelId: 'UC-business',
    privacyStatus: 'unlisted',
    playlists: [{ name: 'AI', sourcePlaylistId: 'PL-source', destinationPlaylistId: null }],
  };
  const sourceYoutube = {
    playlists: { list: async () => ({ data: { items: [{ id: 'PL-source', snippet: { title: 'AI', description: 'source' } }] } }) },
    playlistItems: { list: async () => ({ data: { items: [playlistItem('s1', 'a', 0), playlistItem('s2', 'b', 1)] } }) },
  };
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business', snippet: { title: 'Business' } }] } }) },
    playlists: {
      list: async () => ({ data: { items: [] } }),
      insert: async ({ requestBody }) => {
        assert.equal(requestBody.status.privacyStatus, 'unlisted');
        assert.match(requestBody.snippet.description, /source-playlist:PL-source/);
        return { data: { id: 'PL-destination' } };
      },
    },
    playlistItems: {
      list: async () => ({ data: { items: destinationItems } }),
      insert: async ({ requestBody }) => {
        const videoId = requestBody.snippet.resourceId.videoId;
        destinationItems.push(playlistItem(`d${destinationItems.length}`, videoId, destinationItems.length));
        return { data: { id: destinationItems.at(-1).id } };
      },
    },
  };
  const result = await migratePlaylists({
    sourceYoutube,
    businessYoutube,
    config,
    apply: true,
    persistConfig: (next) => persisted.push(JSON.parse(JSON.stringify(next))),
    sleep: async (milliseconds) => delays.push(milliseconds),
  });
  assert.equal(persisted[0].playlists[0].destinationPlaylistId, 'PL-destination');
  assert.deepEqual(destinationItems.map((item) => item.contentDetails.videoId), ['a', 'b']);
  assert.equal(result.complete, true);
  assert.equal(result.playlists[0].validated, true);
  assert.equal(result.playlists[0].sourceHash, result.playlists[0].destinationHashAfter);
  assert.deepEqual(delays, [1500]);
});

test('waitForExactPlaylist retries a temporarily shorter valid prefix', async () => {
  let reads = 0;
  let sleeps = 0;
  const youtube = {
    playlistItems: {
      list: async () => {
        reads += 1;
        const ids = reads === 1 ? ['a'] : ['a', 'b'];
        return { data: { items: ids.map((id, index) => playlistItem(`d${index}`, id, index)) } };
      },
    },
  };
  const result = await waitForExactPlaylist(youtube, 'PL-destination', ['a', 'b'], {
    attempts: 3,
    delayMs: 1,
    sleep: async () => { sleeps += 1; },
  });
  assert.deepEqual(result.items.map((item) => item.videoId), ['a', 'b']);
  assert.equal(reads, 2);
  assert.equal(sleeps, 1);
});

test('hasVerifiedTranscript accepts nonblank full text or a nonempty timestamped array', () => {
  assert.equal(hasVerifiedTranscript({ fields: { 'Transcript (Full)': ' words ' } }), true);
  assert.equal(hasVerifiedTranscript({ fields: { 'Transcript (Timestamped)': '[{"text":"x","start":0}]' } }), true);
  assert.equal(hasVerifiedTranscript({ fields: { 'Transcript (Timestamped)': '[]' } }), false);
  assert.equal(hasVerifiedTranscript({ fields: { 'Transcript (Timestamped)': 'not-json' } }), false);
  assert.equal(hasVerifiedTranscript(null), false);
});

test('drainPlaylists deletes by playlist item ID, treats 404 as idempotent, and verifies removal', async () => {
  let destinationItems = [playlistItem('pi-1', 'captured', 0), playlistItem('pi-2', 'pending', 1)];
  const deleted = [];
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlistItems: {
      list: async () => ({ data: { items: destinationItems } }),
      delete: async ({ id }) => {
        deleted.push(id);
        destinationItems = destinationItems.filter((item) => item.id !== id);
        if (id === 'already-gone') {
          const error = new Error('not found');
          error.code = 404;
          throw error;
        }
      },
    },
  };
  const records = new Map([
    ['captured', { id: 'rec-1', fields: { 'Transcript (Full)': 'done' } }],
    ['pending', { id: 'rec-2', fields: { 'Transcript (Full)': '' } }],
  ]);
  const result = await drainPlaylists({
    businessYoutube,
    config: {
      businessChannelId: 'UC-business',
      playlists: [{ name: 'AI', destinationPlaylistId: 'PL-destination' }],
    },
    findVideo: async (videoId) => records.get(videoId) || null,
    apply: true,
  });
  assert.deepEqual(deleted, ['pi-1']);
  assert.equal(result.deleted, 1);
  assert.equal(result.retained, 1);
  assert.equal(result.errors.length, 0);
});

test('drainPlaylists isolates duplicate Airtable lookup errors and never deletes that item', async () => {
  const deleted = [];
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlistItems: {
      list: async () => ({ data: { items: [playlistItem('pi-1', 'duplicate', 0)] } }),
      delete: async ({ id }) => deleted.push(id),
    },
  };
  const result = await drainPlaylists({
    businessYoutube,
    config: { businessChannelId: 'UC-business', playlists: [{ name: 'AI', destinationPlaylistId: 'PL-destination' }] },
    findVideo: async () => { throw new Error('2 records share Video ID'); },
    apply: true,
  });
  assert.deepEqual(deleted, []);
  assert.equal(result.errors.length, 1);
});

test('drainPlaylists surfaces unavailable entries instead of silently dropping them', async () => {
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlistItems: {
      list: async () => ({
        data: {
          items: [
            playlistItem('pi-1', 'video-a', 0),
            playlistItem('pi-gone', null, 1), // no videoId -> unavailable
          ],
        },
      }),
      delete: async () => {},
    },
  };
  const result = await drainPlaylists({
    businessYoutube,
    config: { businessChannelId: 'UC-business', playlists: [{ name: 'AI', destinationPlaylistId: 'PL-destination' }] },
    findVideo: async () => null,
    apply: false,
  });
  assert.equal(result.unavailable, 1);
  assert.equal(result.playlists[0].unavailable, 1);
  // The unavailable entry never reaches findVideo/eligible/retained at all —
  // it has no videoId to check.
  assert.equal(result.playlists[0].total, 1);
});

test('drainPlaylists counts a 404 delete attempt against max writes and treats it as already removed', async () => {
  let items = [playlistItem('pi-gone', 'captured', 0), playlistItem('pi-deferred', 'captured-2', 1)];
  const attempted = [];
  const businessYoutube = {
    channels: { list: async () => ({ data: { items: [{ id: 'UC-business' }] } }) },
    playlistItems: {
      list: async () => ({ data: { items } }),
      delete: async ({ id }) => {
        attempted.push(id);
        items = items.filter((item) => item.id !== id);
        const error = new Error('gone');
        error.code = 404;
        throw error;
      },
    },
  };
  const result = await drainPlaylists({
    businessYoutube,
    config: { businessChannelId: 'UC-business', playlists: [{ name: 'AI', destinationPlaylistId: 'PL-destination' }] },
    findVideo: async () => ({ fields: { 'Transcript (Full)': 'yes' } }),
    apply: true,
    maxWrites: 1,
  });
  assert.deepEqual(attempted, ['pi-gone']);
  assert.equal(result.writes, 1);
  assert.equal(result.alreadyRemoved, 1);
  assert.equal(result.deferred, 1);
});
