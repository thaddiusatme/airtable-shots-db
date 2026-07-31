#!/usr/bin/env node
// Read-only base audit. Separate from apify-harvest.js because that CLI makes
// --max-results/--oldest-post-date mandatory as a capture guardrail, and
// those are meaningless for a check that performs zero writes.
//
//   node audit.js
//
// Exits non-zero if any check finds something. Every finding is printed with
// enough detail to act on directly (handle, record id, video id) — see
// CLAUDE.md "Active work" item 3 for why this replaces a manual Airtable view.

const fs = require('node:fs');
const path = require('node:path');

const { listAllChannels, listAllVideos } = require('./lib/airtable-client');

function loadDotEnv() {
  const envPath = path.join(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const match = /^([A-Z_][A-Z0-9_]*)=(.*)$/.exec(line.trim());
    if (match && !process.env[match[1]]) process.env[match[1]] = match[2];
  }
}

// Each check takes the already-fetched channels/videos and returns an array
// of finding strings (empty = clean). Pure functions so they're testable
// without touching the network.

function findBlankTrackChannels(channels) {
  return channels
    .filter((c) => !c.track)
    .map((c) => `${c.handle || '(no handle)'} — "${c.channelName}" (${c.recordId})`);
}

function findMisconfiguredHarvestChannels(channels) {
  return channels
    .filter((c) => c.harvest && !c.sourceUrl)
    .map((c) => `${c.handle || '(no handle)'} — "${c.channelName}" (${c.recordId})`);
}

function findVideosWithNoChannel(videos) {
  return videos
    .filter((v) => !v.channelLinks || v.channelLinks.length === 0)
    .map((v) => `${v.videoId || '(no Video ID)'} — "${v.title}" (${v.recordId})`);
}

function findDuplicateVideoIds(videos) {
  const byId = new Map();
  for (const v of videos) {
    if (!v.videoId) continue;
    if (!byId.has(v.videoId)) byId.set(v.videoId, []);
    byId.get(v.videoId).push(v.recordId);
  }
  const dupes = [];
  for (const [videoId, recordIds] of byId) {
    if (recordIds.length > 1) dupes.push(`${videoId} — ${recordIds.join(', ')}`);
  }
  return dupes;
}

// Metrics only ever land via a sweep (see updateFields in transform.js), so a
// Queued video whose channel isn't Harvest?-ticked is stuck metrics-less
// until someone ticks it — this is expected, not a bug, but worth surfacing.
function findVideosMissingMetrics(videos) {
  return videos
    .filter((v) => !v.metricsCapturedAt)
    .map((v) => `${v.videoId || '(no Video ID)'} — "${v.title}" (${v.triageStatus || 'no status'})`);
}

const CHECKS = [
  {
    label: 'Blank Track Channels',
    hint: 'silently vanish from the working view (Track = AIHS OR Tooling-watch)',
    run: (data) => findBlankTrackChannels(data.channels),
  },
  {
    label: 'Harvest? ticked with no Source URL',
    hint: 'skipped by --from-airtable at sweep time; fix the row before the next sweep',
    run: (data) => findMisconfiguredHarvestChannels(data.channels),
  },
  {
    label: 'Videos with no Channel link',
    hint: 'orphaned records — Channel-Track lookups and Track routing can\'t reach them',
    run: (data) => findVideosWithNoChannel(data.videos),
  },
  {
    label: 'Duplicate Video ID values',
    hint: 'breaks upsert-by-key — merge or park the extras (write invariant 2)',
    run: (data) => findDuplicateVideoIds(data.videos),
  },
  {
    label: 'Videos missing Metrics Captured At',
    hint: 're-sweep is the only metrics-refresh mechanism — expected for videos whose channel isn\'t Harvest?-ticked',
    run: (data) => findVideosMissingMetrics(data.videos),
  },
];

async function runAudit(apiKey, baseId) {
  const [channels, videos] = await Promise.all([
    listAllChannels(apiKey, baseId),
    listAllVideos(apiKey, baseId),
  ]);

  const results = CHECKS.map((check) => ({
    label: check.label,
    hint: check.hint,
    findings: check.run({ channels, videos }),
  }));

  return { channelCount: channels.length, videoCount: videos.length, results };
}

async function main() {
  loadDotEnv();

  const airtableKey = process.env.AIRTABLE_API_KEY;
  const baseId = process.env.AIRTABLE_BASE_ID;
  if (!airtableKey || !baseId) throw new Error('AIRTABLE_API_KEY / AIRTABLE_BASE_ID not set (.env)');

  const { channelCount, videoCount, results } = await runAudit(airtableKey, baseId);
  console.log(`[audit] ${channelCount} Channels, ${videoCount} Videos — read-only, no writes performed\n`);

  let totalFindings = 0;
  for (const { label, hint, findings } of results) {
    totalFindings += findings.length;
    if (findings.length === 0) {
      console.log(`[ok] ${label}: none`);
      continue;
    }
    console.warn(`[warn] ${label}: ${findings.length} — ${hint}`);
    for (const finding of findings) console.warn(`         ${finding}`);
  }

  console.log(`\n[summary] ${totalFindings} finding(s) across ${results.length} check(s)`);
  if (totalFindings > 0) process.exitCode = 1;
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`\nError: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = {
  runAudit,
  findBlankTrackChannels,
  findMisconfiguredHarvestChannels,
  findVideosWithNoChannel,
  findDuplicateVideoIds,
  findVideosMissingMetrics,
};
