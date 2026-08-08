const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const DEFAULT_MAX_WRITES = 175;
const SOURCE_MARKER_PREFIX = 'source-playlist:';

function readConfig(configPath) {
  return JSON.parse(fs.readFileSync(configPath, 'utf8'));
}

function writeConfigAtomic(configPath, config) {
  const tmpPath = `${configPath}.tmp`;
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(tmpPath, `${JSON.stringify(config, null, 2)}\n`);
  fs.renameSync(tmpPath, configPath);
}

function isOrderedPrefix(prefix, full) {
  return prefix.length <= full.length && prefix.every((value, index) => value === full[index]);
}

function orderedVideoHash(videoIds) {
  return crypto.createHash('sha256').update(JSON.stringify(videoIds)).digest('hex');
}

function sourceMarker(sourcePlaylistId) {
  return `${SOURCE_MARKER_PREFIX}${sourcePlaylistId}`;
}

function migrationDescription(description, sourcePlaylistId) {
  const marker = sourceMarker(sourcePlaylistId);
  const clean = String(description || '').trim();
  return clean ? `${clean}\n\n${marker}` : marker;
}

function errorReason(error) {
  return error?.errors?.[0]?.reason || error?.response?.data?.error?.errors?.[0]?.reason || '';
}

function isQuotaError(error) {
  return Number(error?.code) === 403 && ['quotaExceeded', 'dailyLimitExceeded'].includes(errorReason(error));
}

async function assertExpectedChannel(youtube, expectedChannelId) {
  const response = await youtube.channels.list({ part: ['id', 'snippet'], mine: true });
  const channels = response.data.items || [];
  const channel = channels.find((item) => item.id === expectedChannelId);
  if (!channel || channels.length !== 1) {
    const visible = channels.map((item) => `${item.snippet?.title || '(untitled)'} (${item.id})`).join(', ') || 'none';
    throw new Error(
      `Wrong YouTube channel: expected ${expectedChannelId}, but the credential resolves to ${visible}. Refusing to continue.`
    );
  }
  return channel;
}

async function listPlaylistItems(youtube, playlistId) {
  const available = [];
  const unavailable = [];
  let pageToken;

  do {
    const response = await youtube.playlistItems.list({
      part: ['snippet', 'contentDetails'],
      playlistId,
      maxResults: 50,
      pageToken,
    });
    for (const item of response.data.items || []) {
      const position = Number.isFinite(item.snippet?.position) ? item.snippet.position : Number.MAX_SAFE_INTEGER;
      const videoId = item.contentDetails?.videoId || item.snippet?.resourceId?.videoId || null;
      const normalized = {
        playlistItemId: item.id || null,
        videoId,
        position,
      };
      if (videoId) available.push(normalized);
      else unavailable.push(normalized);
    }
    pageToken = response.data.nextPageToken;
  } while (pageToken);

  const byPosition = (a, b) => a.position - b.position;
  available.sort(byPosition);
  unavailable.sort(byPosition);
  return { items: available, unavailable };
}

async function getPlaylistMetadata(youtube, playlistId) {
  const response = await youtube.playlists.list({
    part: ['id', 'snippet', 'status', 'contentDetails'],
    id: [playlistId],
    maxResults: 50,
  });
  const playlist = (response.data.items || []).find((item) => item.id === playlistId);
  if (!playlist) throw new Error(`Playlist ${playlistId} is not visible to the configured credential.`);
  return playlist;
}

async function listOwnedPlaylists(youtube) {
  const playlists = [];
  let pageToken;
  do {
    const response = await youtube.playlists.list({
      part: ['id', 'snippet', 'status', 'contentDetails'],
      mine: true,
      maxResults: 50,
      pageToken,
    });
    playlists.push(...(response.data.items || []));
    pageToken = response.data.nextPageToken;
  } while (pageToken);
  return playlists;
}

function findMarkedDestination(ownedPlaylists, sourcePlaylistId) {
  const marker = sourceMarker(sourcePlaylistId);
  const matches = ownedPlaylists.filter((item) => String(item.snippet?.description || '').includes(marker));
  if (matches.length > 1) {
    throw new Error(`Multiple business playlists contain ${marker}; refusing to guess which destination to adopt.`);
  }
  return matches[0] || null;
}

async function insertPlaylistItem(youtube, destinationPlaylistId, videoId) {
  return youtube.playlistItems.insert({
    part: ['snippet'],
    requestBody: {
      snippet: {
        playlistId: destinationPlaylistId,
        resourceId: { kind: 'youtube#video', videoId },
      },
    },
  });
}

function sleepMs(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForExactPlaylist(
  youtube,
  playlistId,
  expectedVideoIds,
  { attempts = 6, delayMs = 500, sleep = sleepMs } = {}
) {
  let lastCount = 0;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const current = await listPlaylistItems(youtube, playlistId);
    const currentIds = current.items.map((item) => item.videoId);
    lastCount = currentIds.length;
    if (current.unavailable.length > 0) {
      throw new Error(`Validation failed for ${playlistId}: destination contains unavailable entries.`);
    }
    if (currentIds.length === expectedVideoIds.length && isOrderedPrefix(currentIds, expectedVideoIds)) {
      return current;
    }
    if (!isOrderedPrefix(currentIds, expectedVideoIds)) {
      throw new Error(`Validation failed for ${playlistId}: destination order diverges from the source.`);
    }
    if (attempt < attempts - 1) {
      await sleep(Math.min(delayMs * (2 ** attempt), 4000));
    }
  }
  throw new Error(
    `Validation failed for ${playlistId}: destination remained a shorter prefix (${lastCount}/${expectedVideoIds.length}) after ${attempts} reads.`
  );
}

async function migratePlaylists({
  sourceYoutube,
  businessYoutube,
  config,
  apply = false,
  maxWrites = DEFAULT_MAX_WRITES,
  persistConfig = () => {},
  sleep = sleepMs,
  newPlaylistDelayMs = 1500,
}) {
  if (!Number.isInteger(maxWrites) || maxWrites < 1) throw new Error('--max-writes must be a positive integer');
  await assertExpectedChannel(businessYoutube, config.businessChannelId);

  const result = {
    mode: apply ? 'apply' : 'dry-run',
    writes: 0,
    estimatedQuotaUnits: 0,
    complete: true,
    quotaExhausted: false,
    playlists: [],
  };
  let ownedPlaylists;

  for (const playlistConfig of config.playlists) {
    const sourceMetadata = await getPlaylistMetadata(sourceYoutube, playlistConfig.sourcePlaylistId);
    const source = await listPlaylistItems(sourceYoutube, playlistConfig.sourcePlaylistId);
    const sourceVideoIds = source.items.map((item) => item.videoId);
    let destinationPlaylistId = playlistConfig.destinationPlaylistId || null;
    let recoveredDestination = false;
    let createdDestination = false;

    if (!destinationPlaylistId) {
      ownedPlaylists ||= await listOwnedPlaylists(businessYoutube);
      const marked = findMarkedDestination(ownedPlaylists, playlistConfig.sourcePlaylistId);
      if (marked) {
        destinationPlaylistId = marked.id;
        recoveredDestination = true;
        if (apply) {
          playlistConfig.destinationPlaylistId = destinationPlaylistId;
          persistConfig(config);
        }
      }
    }

    let destination = { items: [], unavailable: [] };
    if (destinationPlaylistId) {
      destination = await listPlaylistItems(businessYoutube, destinationPlaylistId);
      const destinationVideoIds = destination.items.map((item) => item.videoId);
      if (!isOrderedPrefix(destinationVideoIds, sourceVideoIds)) {
        throw new Error(
          `Destination for ${playlistConfig.name} diverges from the source sequence; refusing to append or repair automatically.`
        );
      }
    }

    const createsNeeded = destinationPlaylistId ? 0 : 1;
    const insertsNeeded = sourceVideoIds.length - destination.items.length;
    result.estimatedQuotaUnits += (createsNeeded + insertsNeeded) * 50;

    const report = {
      name: playlistConfig.name,
      sourcePlaylistId: playlistConfig.sourcePlaylistId,
      destinationPlaylistId,
      sourceCount: sourceVideoIds.length,
      sourceHash: orderedVideoHash(sourceVideoIds),
      destinationCountBefore: destination.items.length,
      destinationHashBefore: orderedVideoHash(destination.items.map((item) => item.videoId)),
      unavailableCount: source.unavailable.length,
      unavailablePositions: source.unavailable.map((item) => item.position),
      requiredWrites: createsNeeded + insertsNeeded,
      recoveredDestination,
      createdDestination,
      inserted: 0,
      remaining: createsNeeded + insertsNeeded,
      validated: false,
      destinationHashAfter: null,
      partial: source.unavailable.length > 0,
    };
    result.playlists.push(report);

    if (!apply) {
      report.validated = Boolean(destinationPlaylistId) && insertsNeeded === 0 && source.unavailable.length === 0;
      if (!report.validated) result.complete = false;
      continue;
    }

    if (!destinationPlaylistId) {
      if (result.writes >= maxWrites) {
        result.complete = false;
        continue;
      }
      try {
        const created = await businessYoutube.playlists.insert({
          part: ['snippet', 'status'],
          requestBody: {
            snippet: {
              title: sourceMetadata.snippet?.title || playlistConfig.name,
              description: migrationDescription(sourceMetadata.snippet?.description, playlistConfig.sourcePlaylistId),
            },
            status: { privacyStatus: playlistConfig.privacyStatus || config.privacyStatus || 'unlisted' },
          },
        });
        destinationPlaylistId = created.data.id;
        if (!destinationPlaylistId) throw new Error(`YouTube did not return an id when creating ${playlistConfig.name}`);
        playlistConfig.destinationPlaylistId = destinationPlaylistId;
        persistConfig(config);
        report.destinationPlaylistId = destinationPlaylistId;
        report.createdDestination = true;
        report.remaining -= 1;
        result.writes += 1;
        await sleep(newPlaylistDelayMs);
      } catch (error) {
        if (isQuotaError(error)) {
          result.quotaExhausted = true;
          result.complete = false;
          break;
        }
        throw error;
      }
    }

    for (const videoId of sourceVideoIds.slice(destination.items.length)) {
      if (result.writes >= maxWrites) {
        result.complete = false;
        break;
      }
      try {
        await insertPlaylistItem(businessYoutube, destinationPlaylistId, videoId);
        report.inserted += 1;
        report.remaining -= 1;
        result.writes += 1;
      } catch (error) {
        if (isQuotaError(error)) {
          result.quotaExhausted = true;
          result.complete = false;
          break;
        }
        throw error;
      }
    }

    if (result.quotaExhausted) break;
    if (report.remaining > 0 || report.partial) {
      result.complete = false;
      continue;
    }

    const verified = await waitForExactPlaylist(businessYoutube, destinationPlaylistId, sourceVideoIds, { sleep });
    const verifiedIds = verified.items.map((item) => item.videoId);
    report.validated = true;
    report.destinationHashAfter = orderedVideoHash(verifiedIds);
  }

  if (result.playlists.length !== config.playlists.length) result.complete = false;
  return result;
}

function hasVerifiedTranscript(record) {
  if (!record?.fields) return false;
  const full = record.fields['Transcript (Full)'];
  if (typeof full === 'string' && full.trim()) return true;

  const timestamped = record.fields['Transcript (Timestamped)'];
  if (Array.isArray(timestamped)) return timestamped.length > 0;
  if (typeof timestamped !== 'string' || !timestamped.trim()) return false;
  try {
    const parsed = JSON.parse(timestamped);
    return Array.isArray(parsed) && parsed.length > 0;
  } catch {
    return false;
  }
}

async function drainPlaylists({
  businessYoutube,
  config,
  findVideo,
  apply = false,
  maxWrites = DEFAULT_MAX_WRITES,
}) {
  if (!Number.isInteger(maxWrites) || maxWrites < 1) throw new Error('--max-writes must be a positive integer');
  await assertExpectedChannel(businessYoutube, config.businessChannelId);

  const result = {
    mode: apply ? 'apply' : 'dry-run',
    eligible: 0,
    deleted: 0,
    alreadyRemoved: 0,
    retained: 0,
    deferred: 0,
    writes: 0,
    unavailable: 0,
    errors: [],
    playlists: [],
  };

  for (const playlistConfig of config.playlists) {
    if (!playlistConfig.destinationPlaylistId) {
      result.errors.push({ playlist: playlistConfig.name, error: 'destination playlist is not configured' });
      continue;
    }
    const before = await listPlaylistItems(businessYoutube, playlistConfig.destinationPlaylistId);
    const deletedIds = [];
    // `before.unavailable` entries have no videoId to check against Airtable,
    // so they're never eligible for drain — but silently dropping them (as
    // this used to do) hid a signal worth surfacing: a business playlist
    // holding an unavailable/private/deleted video is itself a finding.
    const playlistReport = {
      name: playlistConfig.name,
      destinationPlaylistId: playlistConfig.destinationPlaylistId,
      total: before.items.length,
      eligible: 0,
      deleted: 0,
      retained: 0,
      errors: 0,
      unavailable: before.unavailable.length,
    };
    result.unavailable += before.unavailable.length;
    result.playlists.push(playlistReport);

    for (const item of before.items) {
      let record;
      try {
        record = await findVideo(item.videoId);
      } catch (error) {
        result.errors.push({ playlist: playlistConfig.name, videoId: item.videoId, error: error.message || String(error) });
        result.retained += 1;
        playlistReport.retained += 1;
        playlistReport.errors += 1;
        continue;
      }

      if (!hasVerifiedTranscript(record)) {
        result.retained += 1;
        playlistReport.retained += 1;
        continue;
      }

      result.eligible += 1;
      playlistReport.eligible += 1;
      if (!apply) continue;
      if (result.writes >= maxWrites) {
        result.deferred += 1;
        continue;
      }

      result.writes += 1;
      try {
        await businessYoutube.playlistItems.delete({ id: item.playlistItemId });
        result.deleted += 1;
        playlistReport.deleted += 1;
        deletedIds.push(item.playlistItemId);
      } catch (error) {
        if (Number(error?.code) === 404) {
          result.alreadyRemoved += 1;
          deletedIds.push(item.playlistItemId);
          continue;
        }
        result.errors.push({ playlist: playlistConfig.name, videoId: item.videoId, error: error.message || String(error) });
        playlistReport.errors += 1;
      }
    }

    if (apply && deletedIds.length > 0) {
      const after = await listPlaylistItems(businessYoutube, playlistConfig.destinationPlaylistId);
      const remainingIds = new Set(after.items.map((item) => item.playlistItemId));
      for (const id of deletedIds) {
        if (remainingIds.has(id)) {
          result.errors.push({ playlist: playlistConfig.name, playlistItemId: id, error: 'delete verification failed' });
          playlistReport.errors += 1;
        }
      }
    }
  }

  return result;
}

module.exports = {
  DEFAULT_MAX_WRITES,
  assertExpectedChannel,
  drainPlaylists,
  findMarkedDestination,
  getPlaylistMetadata,
  hasVerifiedTranscript,
  isOrderedPrefix,
  listOwnedPlaylists,
  listPlaylistItems,
  migratePlaylists,
  migrationDescription,
  orderedVideoHash,
  readConfig,
  sourceMarker,
  waitForExactPlaylist,
  writeConfigAtomic,
};
