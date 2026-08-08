#!/usr/bin/env node
// Lane A — business-playlist maintenance orchestrator.
//
// Chains, entirely through the business channel's authenticated YouTube API
// (no browser): full inventory of the six business playlists -> duplicate /
// cross-playlist findings (reported, never auto-resolved) -> bounded harvest
// of whatever's uncaptured -> reconciliation -> a gated drain.
//
// This is Lane A only — see the plan (~/.claude/plans/zany-roaming-sifakis.md)
// for why Watch Later intake (Lane B) is a separate, browser-dependent path
// that cannot be made unattended the same way. Every design decision below
// traces back to a specific stakeholder-review finding, noted inline.

const path = require('node:path');

const { acquireLock, heartbeat, releaseLock } = require('./lock');
const { appendEvent, writeIntent, writeResult, readLedger } = require('./ledger');
const {
  DEFAULT_MAX_WRITES,
  drainPlaylists,
  hasVerifiedTranscript,
  listPlaylistItems,
} = require('../playlist-drain/playlist-manager');
const { sweepChannel } = require('../normalizer/apify-harvest');
const { countQueued, findVideoByVideoId } = require('../normalizer/lib/airtable-client');

const STATE_DIR = path.join(__dirname, 'state');
const LOCK_PATH = path.join(STATE_DIR, 'run.lock');
const LEDGER_PATH = path.join(STATE_DIR, 'ledger.jsonl');

const DEFAULT_QUEUE_CEILING = 30;
const DEFAULT_PER_BATCH_CAP = 10;
const DEFAULT_COST_CAP = 30;
const DEFAULT_OLDEST_POST_DATE = '2015-01-01';

function watchUrl(videoId) {
  return `https://www.youtube.com/watch?v=${videoId}`;
}

// Full inventory across all configured business playlists, plus duplicate /
// cross-playlist detection. Review finding: "Treat cross-playlist duplicates
// in the inherited backlog as findings, not automatically as misplacements.
// Without a prior intended-destination record, code cannot know which
// category is correct." So this only ever REPORTS — it never moves or
// deletes anything based on a duplicate.
async function inventoryBusinessPlaylists({ businessYoutube, config, listPlaylistItemsFn }) {
  const flatItems = [];
  const perPlaylist = [];

  for (const playlistConfig of config.playlists) {
    const { items, unavailable } = await listPlaylistItemsFn(businessYoutube, playlistConfig.destinationPlaylistId);
    perPlaylist.push({
      name: playlistConfig.name,
      destinationPlaylistId: playlistConfig.destinationPlaylistId,
      total: items.length,
      unavailable: unavailable.length,
    });
    for (const item of items) {
      flatItems.push({ playlist: playlistConfig.name, videoId: item.videoId, playlistItemId: item.playlistItemId, position: item.position });
    }
  }

  const byVideoId = new Map();
  for (const item of flatItems) {
    if (!byVideoId.has(item.videoId)) byVideoId.set(item.videoId, []);
    byVideoId.get(item.videoId).push(item);
  }

  const duplicates = [...byVideoId.entries()]
    .filter(([, occurrences]) => occurrences.length > 1)
    .map(([videoId, occurrences]) => ({ videoId, occurrences }));

  return {
    perPlaylist,
    uniqueVideoIds: [...byVideoId.keys()],
    byVideoId,
    duplicates,
    totalItems: flatItems.length,
  };
}

// Classify each unique videoId: already capture-complete (drain-eligible) vs
// still needs harvesting. Reuses the same hasVerifiedTranscript rule the
// tested drain primitive already uses, so this classification and the
// eventual drain dry-run can never disagree about what "captured" means.
async function classifyVideos({ uniqueVideoIds, findVideo }) {
  const needsHarvest = [];
  const alreadyCaptured = [];
  for (const videoId of uniqueVideoIds) {
    const record = await findVideo(videoId);
    if (hasVerifiedTranscript(record)) alreadyCaptured.push(videoId);
    else needsHarvest.push(videoId);
  }
  return { needsHarvest, alreadyCaptured };
}

// Bounded harvest: re-reads the live Queued count before EVERY batch (never
// an in-memory running total) and stops the moment headroom or the run's own
// cost cap is exhausted. Review finding: "--video-urls represents all
// supplied URLs as one pseudo-channel... The Queued ceiling is checked once
// before that whole group, not after each video. A backlog of 90 videos
// could pass when the queue is at 23 and push it far beyond the ceiling."
// This function is what enforces `headroom = min(ceiling - queued, perBatch,
// costCap)` on every batch, upstream of that single-check limitation.
async function boundedHarvest({
  needsHarvest,
  apifyToken,
  airtableKey,
  baseId,
  queueCeiling,
  perBatchCap,
  costCap,
  oldestPostDate,
  countQueuedFn,
  sweepChannelFn,
  findVideo,
  ledgerPath,
  now,
}) {
  const remaining = [...needsHarvest];
  const batches = [];
  let totalRequested = 0;
  let stoppedReason = null;

  while (remaining.length > 0) {
    if (totalRequested >= costCap) {
      stoppedReason = `cost cap reached (${costCap} videos this run)`;
      break;
    }
    const queuedCount = await countQueuedFn();
    const headroom = queueCeiling - queuedCount;
    if (headroom <= 0) {
      stoppedReason = `queue ceiling reached (${queuedCount}/${queueCeiling} Queued — 0 headroom)`;
      break;
    }
    const batchSize = Math.max(0, Math.min(headroom, perBatchCap, remaining.length, costCap - totalRequested));
    if (batchSize <= 0) {
      stoppedReason = `cost cap reached (${costCap} videos this run)`;
      break;
    }

    const batch = remaining.splice(0, batchSize);
    const urls = batch.map(watchUrl);
    totalRequested += batch.length;

    const intentId = writeIntent(ledgerPath, { step: 'harvest-batch', videoIds: batch }, { now: now() });
    let summary;
    try {
      summary = await sweepChannelFn({
        apifyToken,
        airtableKey,
        baseId,
        channel: { recordId: null, channelName: `business-sweep: ${batch.length} url(s)`, sourceUrls: urls },
        args: { maxResults: batch.length, oldestPostDate, dryRun: false },
        capturedAt: new Date(now()).toISOString(),
      });
    } catch (error) {
      writeResult(ledgerPath, intentId, { status: 'error', requested: batch, error: error.message || String(error) }, { now: now() });
      batches.push({ requested: batch, error: error.message || String(error) });
      stoppedReason = `harvest batch threw: ${error.message || error}`;
      break;
    }

    // Reconcile: every requested URL must come back from Apify AND resolve to
    // a verified Airtable row — review finding #6, "the orchestrator must not
    // parse console text" and must fail loudly on a gap rather than silently
    // under-capture.
    const returnedSet = new Set(summary.returnedVideoIds);
    const missingFromDataset = batch.filter((id) => !returnedSet.has(id));
    const verified = [];
    const unverified = [];
    for (const videoId of summary.processedVideoIds) {
      const record = await findVideo(videoId);
      if (hasVerifiedTranscript(record)) verified.push(videoId);
      else unverified.push(videoId);
    }

    const clean = missingFromDataset.length === 0 && unverified.length === 0 && summary.errors === 0;
    writeResult(ledgerPath, intentId, {
      status: clean ? 'ok' : 'partial',
      requested: batch,
      returned: summary.returnedVideoIds,
      processed: summary.processedVideoIds,
      verified,
      missingFromDataset,
      unverified,
      errors: summary.errors,
    }, { now: now() });

    batches.push({ requested: batch, summary, missingFromDataset, verified, unverified });

    if (!clean) {
      stoppedReason = 'reconciliation gap in this batch — stopping rather than compounding it (see ledger for details)';
      break;
    }
  }

  return { batches, remaining, stoppedReason, totalRequested };
}

async function runBusinessSweep({
  businessYoutube,
  config,
  apifyToken,
  airtableKey,
  baseId,
  apply = false,
  queueCeiling = DEFAULT_QUEUE_CEILING,
  perBatchCap = DEFAULT_PER_BATCH_CAP,
  costCap = DEFAULT_COST_CAP,
  oldestPostDate = DEFAULT_OLDEST_POST_DATE,
  maxDrainWrites = DEFAULT_MAX_WRITES,
  lockPath = LOCK_PATH,
  ledgerPath = LEDGER_PATH,
  now = () => Date.now(),
  countQueuedFn = countQueued.bind(null, airtableKey, baseId),
  findVideo = (videoId) => findVideoByVideoId(airtableKey, baseId, videoId),
  sweepChannelFn = sweepChannel,
  drainPlaylistsFn = drainPlaylists,
  listPlaylistItemsFn = listPlaylistItems,
}) {
  acquireLock(lockPath, { now: now() });
  try {
    const inventory = await inventoryBusinessPlaylists({ businessYoutube, config, listPlaylistItemsFn });
    appendEvent(ledgerPath, {
      type: 'inventory',
      at: now(),
      totalItems: inventory.totalItems,
      uniqueVideoIds: inventory.uniqueVideoIds.length,
      duplicates: inventory.duplicates.map((d) => d.videoId),
      perPlaylist: inventory.perPlaylist,
    });

    heartbeat(lockPath, { now: now() });

    const classification = await classifyVideos({ uniqueVideoIds: inventory.uniqueVideoIds, findVideo });

    let harvest = { batches: [], remaining: classification.needsHarvest, stoppedReason: 'apply=false — harvest is a preview only', totalRequested: 0 };
    if (apply) {
      harvest = await boundedHarvest({
        needsHarvest: classification.needsHarvest,
        apifyToken,
        airtableKey,
        baseId,
        queueCeiling,
        perBatchCap,
        costCap,
        oldestPostDate,
        countQueuedFn,
        sweepChannelFn,
        findVideo,
        ledgerPath,
        now,
      });
    }

    heartbeat(lockPath, { now: now() });

    // Fresh dry-run AFTER harvest — authoritative, not a stale snapshot from
    // the classification pass above.
    const drainDryRun = await drainPlaylistsFn({ businessYoutube, config, findVideo, apply: false, maxWrites: maxDrainWrites });

    // Review finding #5: `deferred` is never populated on a dry run (the
    // apply branch that increments it is skipped entirely), so it proves
    // nothing about the write budget. The real gate is computed directly.
    const gate = {
      eligibleWithinBudget: drainDryRun.eligible <= maxDrainWrites,
      noErrors: drainDryRun.errors.length === 0,
      noUnavailable: drainDryRun.unavailable === 0,
    };
    const drainGatePassed = gate.eligibleWithinBudget && gate.noErrors && gate.noUnavailable;

    let drainApply = null;
    if (apply && drainGatePassed && drainDryRun.eligible > 0) {
      const intentId = writeIntent(ledgerPath, { step: 'drain-apply', eligible: drainDryRun.eligible }, { now: now() });
      drainApply = await drainPlaylistsFn({ businessYoutube, config, findVideo, apply: true, maxWrites: maxDrainWrites });
      // `errors` stays a count so existing ledger lines stay readable, but the
      // failures themselves are persisted alongside it. A bare count told the
      // 2026-08-06 run "1 thing broke" and nothing about which item or why,
      // which is unrecoverable once the process exits.
      writeResult(ledgerPath, intentId, {
        status: drainApply.errors.length > 0 ? 'partial' : 'ok',
        deleted: drainApply.deleted,
        alreadyRemoved: drainApply.alreadyRemoved,
        deferred: drainApply.deferred,
        errors: drainApply.errors.length,
        errorDetails: drainApply.errors,
      }, { now: now() });
    }

    return {
      mode: apply ? 'apply' : 'dry-run',
      inventory: { perPlaylist: inventory.perPlaylist, totalItems: inventory.totalItems, uniqueVideoIds: inventory.uniqueVideoIds.length },
      findings: {
        duplicates: inventory.duplicates,
        unavailable: inventory.perPlaylist.reduce((sum, p) => sum + p.unavailable, 0),
      },
      classification: { needsHarvest: classification.needsHarvest.length, alreadyCaptured: classification.alreadyCaptured.length },
      harvest,
      drainDryRun,
      drainGate: { ...gate, passed: drainGatePassed },
      drainApply,
    };
  } finally {
    releaseLock(lockPath);
  }
}

function printReport(report) {
  console.log(`\nBusiness-playlist maintenance (${report.mode})`);
  console.log(`Inventory: ${report.inventory.totalItems} item(s), ${report.inventory.uniqueVideoIds} unique video(s) across ${report.inventory.perPlaylist.length} playlist(s)`);
  for (const playlist of report.inventory.perPlaylist) {
    console.log(`  - ${playlist.name}: total=${playlist.total}, unavailable=${playlist.unavailable}`);
  }
  if (report.findings.duplicates.length > 0) {
    console.log(`\nFINDINGS — ${report.findings.duplicates.length} duplicate video ID(s), not auto-resolved:`);
    for (const dup of report.findings.duplicates) {
      console.log(`  - ${dup.videoId}: ${dup.occurrences.map((o) => `${o.playlist}#${o.position}`).join(', ')}`);
    }
  }
  console.log(`\nClassification: ${report.classification.needsHarvest} need harvest, ${report.classification.alreadyCaptured} already captured`);
  console.log(`Harvest: requested=${report.harvest.totalRequested}, remaining=${report.harvest.remaining.length}${report.harvest.stoppedReason ? `, stopped: ${report.harvest.stoppedReason}` : ''}`);
  console.log(`\nDrain dry-run: eligible=${report.drainDryRun.eligible}, unavailable=${report.drainDryRun.unavailable}, errors=${report.drainDryRun.errors.length}`);
  console.log(`Drain gate: ${report.drainGate.passed ? 'PASSED' : 'BLOCKED'} (withinBudget=${report.drainGate.eligibleWithinBudget}, noErrors=${report.drainGate.noErrors}, noUnavailable=${report.drainGate.noUnavailable})`);
  if (report.drainApply) {
    console.log(`Drain apply: deleted=${report.drainApply.deleted}, alreadyRemoved=${report.drainApply.alreadyRemoved}, deferred=${report.drainApply.deferred}, errors=${report.drainApply.errors.length}`);
    for (const error of report.drainApply.errors) {
      const subject = error.videoId ? ` video=${error.videoId}` : error.playlistItemId ? ` item=${error.playlistItemId}` : '';
      console.error(`  [error] ${error.playlist}${subject}: ${error.error}`);
    }
  }
}

function printUsage() {
  console.log(`Usage: node business-sweep.js [--apply] [--max-writes N] [--queue-ceiling N]
                              [--batch-cap N] [--cost-cap N]

Default mode is read-only: inventories the six business playlists, reports
duplicate/cross-playlist findings, previews the harvest backlog, and runs a
drain dry-run. Nothing is written to YouTube, Airtable, or Apify.

--apply actually harvests a bounded batch of uncaptured videos (this costs
real Apify money) and, only if the drain gate passes, deletes the
now-capture-complete items from the business playlists.`);
}

function parseArgs(argv) {
  const args = {
    apply: false,
    maxWrites: DEFAULT_MAX_WRITES,
    queueCeiling: DEFAULT_QUEUE_CEILING,
    batchCap: DEFAULT_PER_BATCH_CAP,
    costCap: DEFAULT_COST_CAP,
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--apply') args.apply = true;
    else if (arg === '--help' || arg === '-h') args.help = true;
    else if (arg === '--max-writes') args.maxWrites = Number(argv[++i]);
    else if (arg === '--queue-ceiling') args.queueCeiling = Number(argv[++i]);
    else if (arg === '--batch-cap') args.batchCap = Number(argv[++i]);
    else if (arg === '--cost-cap') args.costCap = Number(argv[++i]);
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return args;
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) return printUsage();

  // Reuses playlist-drain's env/credential plumbing rather than reinventing
  // it — same .env, same config file, same business-channel credential.
  const { loadEnvironment, requireEnvironment, createYoutubeClient, CONFIG_PATH } = require('../playlist-drain/runtime');
  const { readConfig } = require('../playlist-drain/playlist-manager');

  const env = loadEnvironment();
  requireEnvironment(env, ['AIRTABLE_API_KEY', 'AIRTABLE_BASE_ID']);
  if (args.apply) requireEnvironment(env, ['APIFY_TOKEN']);

  const config = readConfig(CONFIG_PATH);
  const report = await runBusinessSweep({
    businessYoutube: createYoutubeClient(env, 'GOOGLE_REFRESH_TOKEN'),
    config,
    apifyToken: env.APIFY_TOKEN,
    airtableKey: env.AIRTABLE_API_KEY,
    baseId: env.AIRTABLE_BASE_ID,
    apply: args.apply,
    queueCeiling: args.queueCeiling,
    perBatchCap: args.batchCap,
    costCap: args.costCap,
    maxDrainWrites: args.maxWrites,
  });
  printReport(report);

  if (report.findings.duplicates.length > 0) {
    console.log(`\n${report.findings.duplicates.length} duplicate finding(s) need a human decision — see above. Not auto-resolved.`);
  }
  if (!report.drainGate.passed) process.exitCode = 2;
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Business sweep failed: ${error.message || error}`);
    process.exitCode = 1;
  });
}

module.exports = {
  DEFAULT_QUEUE_CEILING,
  DEFAULT_PER_BATCH_CAP,
  DEFAULT_COST_CAP,
  DEFAULT_OLDEST_POST_DATE,
  LOCK_PATH,
  LEDGER_PATH,
  watchUrl,
  inventoryBusinessPlaylists,
  classifyVideos,
  boundedHarvest,
  runBusinessSweep,
  printReport,
  printUsage,
  parseArgs,
  main,
  readLedger,
};
