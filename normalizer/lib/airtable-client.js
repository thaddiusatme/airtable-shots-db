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

// Find-or-create a Channel by Channel Handle.
//
// Looks up `handleKey` (@handle — what all existing rows use, see
// transform.js) first, then `fallbackKey` (the UC... id) so a row created by
// some other path is still found rather than forked. Creates with handleKey
// when we have one. Returns { recordId, created, matchedOn }.
//
// `created: true` means this Channel has no Track set yet — per CLAUDE.md a
// blank-Track Channel silently vanishes from the AIHS working view
// (Track = AIHS OR Tooling-watch). Callers should surface `created` loudly.
async function upsertChannel(apiKey, baseId, { handleKey, fallbackKey, channelName, channelUrl }, { dryRun } = {}) {
  const writeKey = handleKey || fallbackKey;
  if (!writeKey || !channelName) return { recordId: null, created: false, skipped: 'missing channel info' };

  for (const [label, key] of [['handle', handleKey], ['channelId', fallbackKey]]) {
    if (!key) continue;
    const existing = await findChannelByHandle(apiKey, baseId, key);
    if (existing) return { recordId: existing.id, created: false, matchedOn: label };
  }

  if (dryRun) return { recordId: '<dry-run: would create>', created: true };

  const created = await airtableRequest(apiKey, `${baseId}/Channels`, {
    method: 'POST',
    body: JSON.stringify({
      fields: {
        'Channel Name': channelName,
        Platform: 'YouTube',
        'Channel Handle': writeKey,
        'Channel URL': channelUrl || `https://www.youtube.com/channel/${fallbackKey || ''}`,
      },
    }),
  });

  return { recordId: created.id, created: true };
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
  upsertChannel,
  upsertVideo,
};
