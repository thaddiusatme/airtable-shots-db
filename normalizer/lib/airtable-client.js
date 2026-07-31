// Airtable I/O for the normalizer. Deliberately mirrors the invariants and
// field names already proven out in chrome-extension/background.js
// (saveTranscript/upsertChannel) rather than inventing a new shape:
//
//   1. Upsert Videos by Video ID. Never blind-create.
//   2. Never touch Triage Status on update — only set on create.
//   3. Find-or-create Channels by Channel Handle = the "@handle", which is
//      what every existing row uses. NOT the UC... channelId — see the note
//      in transform.js; keying on the UC id forks the Channels table.
//   4. Verify writes by re-querying rather than trusting a status flag
//      (that's an extension-specific lesson from the panel-state retro, but
//      the write path itself already returns the created/updated record
//      here, so there's nothing to "trust" blindly in the first place).
//
// See CLAUDE.md "Write invariants — non-negotiable, inherited by the
// normalizer" for the source of these rules and the incidents behind them.

const AIRTABLE_API = 'https://api.airtable.com/v0';

// Escape single quotes for Airtable filterByFormula string literals.
function escapeFormulaString(value) {
  return String(value).replace(/'/g, "\\'");
}

async function airtableRequest(apiKey, path, options = {}) {
  const response = await fetch(`${AIRTABLE_API}/${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body?.error?.message || `Airtable request failed (${response.status})`;
    throw new Error(message);
  }
  return body;
}

async function countQueued(apiKey, baseId) {
  const formula = encodeURIComponent(`{Triage Status}='Queued'`);
  const result = await airtableRequest(
    apiKey,
    `${baseId}/Videos?filterByFormula=${formula}&fields%5B%5D=Video%20ID&pageSize=100`
  );
  // Only counts the first page (100) — good enough for a ceiling check; if
  // there are >100 Queued we're already well past any sane threshold.
  return result.records?.length ?? 0;
}

// Invariant 2: two records sharing one key break the upsert. Returning
// records[0] silently sends the write to whichever row Airtable happened to
// return first — the base had exactly this condition (Video ID oTphk2SVHNc on
// two records) until it was merged on 2026-07-29. Refuse loudly instead; the
// CLI isolates per-item errors so one bad key doesn't kill the sweep.
function exactlyOneOrNull(records, label, value) {
  if (!records || records.length === 0) return null;
  if (records.length > 1) {
    const ids = records.map((r) => r.id).join(', ');
    throw new Error(
      `${records.length} records share ${label} '${value}' (${ids}) — this breaks upsert-by-key. Merge or park the extras before harvesting (see CLAUDE.md write invariant 2).`
    );
  }
  return records[0];
}

async function findVideoByVideoId(apiKey, baseId, videoId) {
  const formula = encodeURIComponent(`{Video ID}='${escapeFormulaString(videoId)}'`);
  const result = await airtableRequest(apiKey, `${baseId}/Videos?filterByFormula=${formula}`);
  return exactlyOneOrNull(result.records, 'Video ID', videoId);
}

async function findChannelByHandle(apiKey, baseId, channelHandle) {
  const formula = encodeURIComponent(
    `AND({Platform}='YouTube', {Channel Handle}='${escapeFormulaString(channelHandle)}')`
  );
  const result = await airtableRequest(apiKey, `${baseId}/Channels?filterByFormula=${formula}`);
  return exactlyOneOrNull(result.records, 'Channel Handle', channelHandle);
}

// PATCH arbitrary fields onto one Channel row. Callers are responsible for
// what they put in `fields` — see the invariant note on upsertChannel about
// what must never appear there.
async function patchChannel(apiKey, baseId, recordId, fields) {
  return airtableRequest(apiKey, `${baseId}/Channels/${recordId}`, {
    method: 'PATCH',
    body: JSON.stringify({ fields }),
  });
}

// The harvest queue: every Channel with Harvest? ticked. This is why the
// config lives in Airtable rather than a repo JSON file — adding a channel to
// the sweep is a checkbox, not a commit.
async function listHarvestChannels(apiKey, baseId) {
  const formula = encodeURIComponent('{Harvest?}=1');
  const result = await airtableRequest(
    apiKey,
    `${baseId}/Channels?filterByFormula=${formula}&pageSize=100`
  );
  return (result.records || []).map((record) => ({
    recordId: record.id,
    channelName: record.fields['Channel Name'] || '(unnamed)',
    sourceUrl: record.fields['Source URL'] || null,
    lastHarvested: record.fields['Last harvested'] || null,
  }));
}

// Find-or-create a Channel by Channel Handle.
//
// Looks up `handleKey` (@handle — what all existing rows use, see
// transform.js) first, then `fallbackKey` (the UC... id) so a row created by
// some other path is still found rather than forked. Creates with handleKey
// when we have one. Returns { recordId, created, matchedOn, statsUpdated }.
//
// `created: true` means this Channel has no Track set yet — per CLAUDE.md a
// blank-Track Channel silently vanishes from the AIHS working view
// (Track = AIHS OR Tooling-watch). Callers should surface `created` loudly.
//
// INVARIANT: on an existing row this writes `stats` and nothing else. `Track`
// is human-owned routing — the exact same category as Triage Status on Videos
// (invariant 3), and clobbering it would silently drop a channel out of the
// refinery's working view. transform.js builds `stats` and never puts Track in
// it, so the protection is structural rather than a rule to remember here.
async function upsertChannel(
  apiKey,
  baseId,
  { handleKey, fallbackKey, channelName, channelUrl, stats },
  { dryRun } = {}
) {
  const writeKey = handleKey || fallbackKey;
  if (!writeKey || !channelName) return { recordId: null, created: false, skipped: 'missing channel info' };

  const statsFields = stats && Object.keys(stats).length > 0 ? stats : null;

  for (const [label, key] of [['handle', handleKey], ['channelId', fallbackKey]]) {
    if (!key) continue;
    const existing = await findChannelByHandle(apiKey, baseId, key);
    if (!existing) continue;

    if (statsFields && !dryRun) await patchChannel(apiKey, baseId, existing.id, statsFields);
    return {
      recordId: existing.id,
      created: false,
      matchedOn: label,
      statsUpdated: Boolean(statsFields) && !dryRun,
    };
  }

  if (dryRun) return { recordId: '<dry-run: would create>', created: true, statsUpdated: false };

  const created = await airtableRequest(apiKey, `${baseId}/Channels`, {
    method: 'POST',
    body: JSON.stringify({
      fields: {
        'Channel Name': channelName,
        Platform: 'YouTube',
        'Channel Handle': writeKey,
        'Channel URL': channelUrl || `https://www.youtube.com/channel/${fallbackKey || ''}`,
        ...(statsFields || {}),
      },
    }),
  });

  return { recordId: created.id, created: true, statsUpdated: Boolean(statsFields) };
}

// Upsert a Videos record by Video ID. `fields` should already be built
// (Video Title, Transcript (Full), Transcript (Timestamped), etc.) — this
// function only adds the create-only fields (Video ID, Platform, Video URL,
// Triage Status, Intake Source, Thumbnail) and the Channel link.
async function upsertVideo(apiKey, baseId, { videoId, channelRecordId, createOnlyFields, updateFields }, { dryRun } = {}) {
  const existing = await findVideoByVideoId(apiKey, baseId, videoId);

  if (existing) {
    if (dryRun) return { action: 'would-update', recordId: existing.id, fields: updateFields };
    const updated = await airtableRequest(apiKey, `${baseId}/Videos/${existing.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ fields: updateFields }),
    });
    return { action: 'updated', recordId: updated.id };
  }

  const fields = { ...createOnlyFields, ...updateFields };
  if (channelRecordId && typeof channelRecordId === 'string' && !channelRecordId.startsWith('<dry-run')) {
    fields.Channel = [channelRecordId];
  }

  if (dryRun) return { action: 'would-create', recordId: null, fields };

  const created = await airtableRequest(apiKey, `${baseId}/Videos`, {
    method: 'POST',
    body: JSON.stringify({ fields }),
  });
  return { action: 'created', recordId: created.id };
}

module.exports = {
  countQueued,
  findVideoByVideoId,
  findChannelByHandle,
  listHarvestChannels,
  patchChannel,
  upsertChannel,
  upsertVideo,
};
