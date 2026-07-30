#!/usr/bin/env node
// Apify -> Airtable normalizer CLI.
//
//   node apify-harvest.js --channel-url <url> --max-results 5 --oldest-post-date 2026-07-01 [--dry-run]
//
// Design decisions this implements (see repo CLAUDE.md "Active work" for the
// full rationale — this comment only covers what's enforced in code):
//
//   - --max-results and --oldest-post-date are MANDATORY on every run,
//     dry-run or not. No unbounded channel pulls. (Guardrail.)
//   - Queue-depth ceiling: refuses to run while Triage Status=Queued count
//     in Airtable is already at/above --queue-ceiling (default 30).
//   - --dry-run performs all reads (Apify call + Airtable existence checks)
//     but no writes, and prints exactly what it would have written.
//   - Reuses chrome-extension/lib/transcript-utils.js for GH-64 truncation,
//     and the write invariants from background.js (upsert by Video ID,
//     never touch Triage Status on update, Channel found/created by
//     Channel Handle = channelId).
//
// KNOWN GAP (2026-07-29): "oldestPostDate" is confirmed to be a REAL actor
// input key (documented as "only posts uploaded after or on this date"; it
// also accepts a relative value like "7 days"). What is NOT yet confirmed is
// that the actor actually HONORS it in channel-sweep mode — an accepted-but-
// ignored field looks identical to a working one until --max-results is
// raised, at which point a "bounded" sweep walks the whole channel history.
// Prove it with --save-raw: check the captured publish dates against the
// bound, then re-run with a recent date and confirm the item set changes.
// Until that negative control passes, --max-results is the only real bound.

const fs = require('node:fs');
const path = require('node:path');

const { runActorSync } = require('./lib/apify-client');
const { buildVideoFields } = require('./lib/transform');
const { countQueued, upsertChannel, upsertVideo } = require('./lib/airtable-client');

function loadDotEnv() {
  const envPath = path.join(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const match = /^([A-Z_][A-Z0-9_]*)=(.*)$/.exec(line.trim());
    if (match && !process.env[match[1]]) process.env[match[1]] = match[2];
  }
}

const USAGE = `Usage:
  node apify-harvest.js --channel-url <url> --max-results <n> --oldest-post-date <YYYY-MM-DD> [options]

Required (guardrail: no unbounded channel pulls):
  --channel-url <url>          Channel to harvest, e.g. https://www.youtube.com/@Someone
  --max-results <n>            Max regular videos to pull
  --oldest-post-date <date>    Only videos on/after this date (ISO, or relative like "7 days")

Options:
  --queue-ceiling <n>          Refuse to run if Queued count >= n (default 30)
  --dry-run                    Do every read, print intended writes, write nothing
  --save-raw <path>            Dump the raw Apify dataset to <path> for inspection
  --help                       Show this message
`;

function parseArgs(argv) {
  const args = { dryRun: false, queueCeiling: 30, help: false };
  for (let i = 0; i < argv.length; i++) {
    // Accept both "--flag value" and "--flag=value".
    const raw = argv[i];
    const eq = raw.indexOf('=');
    const arg = eq > 1 ? raw.slice(0, eq) : raw;
    const inlineValue = eq > 1 ? raw.slice(eq + 1) : null;
    const takeValue = () => (inlineValue !== null ? inlineValue : argv[++i]);

    switch (arg) {
      case '--channel-url':
        args.channelUrl = takeValue();
        break;
      case '--max-results':
        args.maxResults = Number(takeValue());
        break;
      case '--oldest-post-date':
        args.oldestPostDate = takeValue();
        break;
      case '--queue-ceiling':
        args.queueCeiling = Number(takeValue());
        break;
      case '--save-raw':
        args.saveRaw = takeValue();
        break;
      case '--dry-run':
        args.dryRun = true;
        break;
      case '--help':
      case '-h':
        args.help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}\n\n${USAGE}`);
    }
  }
  return args;
}

// Replace long transcript bodies with a size summary so dry-run output stays
// readable while still proving the fields are populated.
function elideTranscripts(fields) {
  const out = {};
  for (const [key, value] of Object.entries(fields)) {
    out[key] = typeof value === 'string' && value.length > 200
      ? `<${value.length} chars>`
      : value;
  }
  return out;
}

function validateArgs(args) {
  const errors = [];
  if (!args.channelUrl) errors.push('--channel-url is required');
  if (!args.maxResults || args.maxResults <= 0) errors.push('--max-results is required and must be > 0 (guardrail: no unbounded pulls)');
  if (!args.oldestPostDate) errors.push('--oldest-post-date is required (guardrail: no unbounded pulls) — format YYYY-MM-DD');
  if (errors.length) {
    throw new Error(`Invalid arguments:\n  - ${errors.join('\n  - ')}`);
  }
}

async function main() {
  loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(USAGE);
    return;
  }
  validateArgs(args);

  const apifyToken = process.env.APIFY_TOKEN;
  const airtableKey = process.env.AIRTABLE_API_KEY;
  const baseId = process.env.AIRTABLE_BASE_ID;

  if (!apifyToken) throw new Error('APIFY_TOKEN not set (.env)');
  if (!airtableKey || !baseId) throw new Error('AIRTABLE_API_KEY / AIRTABLE_BASE_ID not set (.env)');

  console.log(`[queue check] querying Triage Status=Queued count...`);
  const queuedCount = await countQueued(airtableKey, baseId);
  console.log(`[queue check] ${queuedCount} currently Queued (ceiling: ${args.queueCeiling})`);
  if (queuedCount >= args.queueCeiling) {
    console.error(`Refusing to harvest: Queued count (${queuedCount}) is at/above the ceiling (${args.queueCeiling}). The refinery's bottleneck is the human review gate, not capture — clear the queue before sweeping more in.`);
    process.exitCode = 1;
    return;
  }

  const input = {
    startUrls: [{ url: args.channelUrl }],
    maxResults: args.maxResults,
    oldestPostDate: args.oldestPostDate,
    downloadSubtitles: true,
    subtitlesFormat: 'srt',
    subtitlesLanguage: 'en',
    preferAutoGeneratedSubtitles: true,
    saveSubsToKVS: false, // inline delivery confirmed sufficient — see srt-parser.js
  };

  console.log(`[apify] running actor with input:`, JSON.stringify(input, null, 2));
  const items = await runActorSync({ token: apifyToken, input });
  console.log(`[apify] dataset returned ${items.length} item(s)`);

  // Write the raw capture before any processing, so a later failure still
  // leaves the observed output on disk to inspect and turn into a fixture.
  if (args.saveRaw) {
    fs.writeFileSync(args.saveRaw, JSON.stringify(items, null, 2));
    console.log(`[apify] raw dataset written to ${args.saveRaw}`);
  }

  const summary = { created: 0, updated: 0, wouldCreate: 0, wouldUpdate: 0, skipped: 0, channelsCreated: 0, errors: 0 };

  for (const item of items) {
    const built = buildVideoFields(item);
    if (built.skipped) {
      console.warn(`[skip] ${item?.id || '(no id)'}: ${built.skipped}`);
      summary.skipped++;
      continue;
    }

    for (const warning of built.warnings) {
      console.warn(`[warn] ${built.videoId}: ${warning}`);
    }

    // Each item's write is independent, so one failure shouldn't abandon the
    // rest of the sweep — record it, keep going, and exit non-zero at the end.
    try {
      const channelResult = await upsertChannel(airtableKey, baseId, built.channel, { dryRun: args.dryRun });
      if (channelResult.created) {
        summary.channelsCreated++;
        console.warn(`[channel] created "${built.channel.channelName}" (${built.channel.handleKey || built.channel.fallbackKey}) with NO Track set — it will silently vanish from the working view (Track = AIHS OR Tooling-watch) until someone sets Track by hand.`);
      } else if (channelResult.matchedOn) {
        console.log(`[channel] matched existing "${built.channel.channelName}" on ${channelResult.matchedOn}`);
      } else if (channelResult.skipped) {
        console.warn(`[channel] ${built.videoId}: ${channelResult.skipped} — video will have no Channel link`);
      }

      const videoResult = await upsertVideo(
        airtableKey,
        baseId,
        {
          videoId: built.videoId,
          channelRecordId: channelResult.recordId,
          createOnlyFields: built.createOnlyFields,
          updateFields: built.updateFields,
        },
        { dryRun: args.dryRun }
      );

      console.log(`[video] ${built.videoId} (${built.createOnlyFields['Video Title']}): ${videoResult.action}`);
      if (videoResult.action === 'created') summary.created++;
      else if (videoResult.action === 'updated') summary.updated++;
      else if (videoResult.action === 'would-create') summary.wouldCreate++;
      else if (videoResult.action === 'would-update') summary.wouldUpdate++;

      // Dry-run's whole purpose is to show the payload, so print it. Transcript
      // bodies are elided — they're up to 100k chars and would bury the rest.
      if (args.dryRun && videoResult.fields) {
        console.log(`         would write: ${JSON.stringify(elideTranscripts(videoResult.fields), null, 2).replace(/\n/g, '\n         ')}`);
      }
    } catch (error) {
      summary.errors++;
      console.error(`[error] ${built.videoId}: ${error.message}`);
    }
  }

  console.log('\n[summary]', JSON.stringify(summary, null, 2));
  if (args.dryRun) console.log('\nDry run — nothing was written to Airtable.');
  if (summary.errors > 0) {
    console.error(`\n${summary.errors} item(s) failed — see [error] lines above.`);
    process.exitCode = 1;
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`\nError: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = { parseArgs, validateArgs, elideTranscripts, USAGE };
