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
//   - Queue-depth ceiling: stops before any channel while the Triage
//     Status=Queued count in Airtable is at/above --queue-ceiling (default
//     30). Re-checked per channel, not once per run — see main().
//   - --dry-run performs all reads (Apify call + Airtable existence checks)
//     but no writes, and prints exactly what it would have written.
//   - Reuses chrome-extension/lib/transcript-utils.js for GH-64 truncation,
//     and the write invariants from background.js (upsert by Video ID,
//     never touch Triage Status on update, Channel found/created by
//     Channel Handle = '@' + channelUsername).
//
// "oldestPostDate" is HONORED, not merely accepted — proven 2026-07-29 by
// negative control: bounding the same call at a later date returned 1 item
// instead of 2. It also accepts relative values like "7 days".

const fs = require('node:fs');
const path = require('node:path');

const { runActorSync } = require('./lib/apify-client');
const { buildVideoFields } = require('./lib/transform');
const {
  countQueued,
  listHarvestChannels,
  patchChannel,
  upsertChannel,
  upsertVideo,
} = require('./lib/airtable-client');

// Parse .env text into { KEY: value }. Pure, so it is testable without
// touching the real .env sitting one directory up.
function parseDotEnv(text) {
  const values = {};
  for (const line of String(text).split('\n')) {
    const match = /^([A-Z_][A-Z0-9_]*)=(.*)$/.exec(line.trim());
    if (match) values[match[1]] = unquote(match[2]);
  }
  return values;
}

// Strip one MATCHED pair of surrounding quotes, and nothing else. A lone
// leading quote is part of the value, not a quote — eating it would silently
// corrupt a real secret, which is the failure this function exists to avoid.
function unquote(value) {
  const quoted = /^"(.*)"$|^'(.*)'$/s.exec(value);
  if (!quoted) return value;
  return quoted[1] !== undefined ? quoted[1] : quoted[2];
}

// Not overriding an already-set variable is the wrapper's job, not the
// parser's: a real environment beats a file on disk.
function loadDotEnv() {
  const envPath = path.join(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return;
  for (const [key, value] of Object.entries(parseDotEnv(fs.readFileSync(envPath, 'utf8')))) {
    if (!process.env[key]) process.env[key] = value;
  }
}

const USAGE = `Usage:
  node apify-harvest.js --channel-url <url> --max-results <n> --oldest-post-date <YYYY-MM-DD> [options]
  node apify-harvest.js --playlist-url <url> --max-results <n> --oldest-post-date <YYYY-MM-DD> [options]
  node apify-harvest.js --from-airtable  --max-results <n> --oldest-post-date <YYYY-MM-DD> [options]

Channel selection (exactly one):
  --channel-url <url>          One channel, e.g. https://www.youtube.com/@Someone
  --playlist-url <url>         One playlist, e.g. https://www.youtube.com/playlist?list=PL...
                                Videos can span multiple channels; each is upserted using its
                                own channelUsername from the dataset item, same as channel mode.
  --from-airtable               Every Channel row with Harvest? ticked, using its Source URL

Required in both modes (guardrail: no unbounded channel pulls):
  --max-results <n>            Max regular videos to pull, PER CHANNEL
  --oldest-post-date <date>    Only videos on/after this date (ISO, or relative like "7 days")

Options:
  --queue-ceiling <n>          Stop before any channel whose Queued count >= n (default 30)
  --dry-run                    Do every read, print intended writes, write nothing
  --save-raw <path>            Dump the raw Apify dataset to <path> (one file per channel in batch mode)
  --help                       Show this message
`;

function parseArgs(argv) {
  const args = { dryRun: false, fromAirtable: false, queueCeiling: 30, help: false };
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
      case '--playlist-url':
        args.playlistUrl = takeValue();
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
      case '--from-airtable':
        args.fromAirtable = true;
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
  // Exactly one channel source. Accepting more than one would silently ignore
  // the others, and the harvest config living in two places is the failure
  // mode the Airtable-driven design exists to avoid.
  const sourceCount = [args.channelUrl, args.playlistUrl, args.fromAirtable].filter(Boolean).length;
  if (sourceCount === 0) {
    errors.push('one of --channel-url, --playlist-url, or --from-airtable is required');
  } else if (sourceCount > 1) {
    errors.push('--channel-url, --playlist-url, and --from-airtable are mutually exclusive');
  }
  // Per-channel bounds stay mandatory in batch mode: --from-airtable multiplies
  // the cost by the number of ticked channels, so it needs MORE bounding, not less.
  if (!args.maxResults || args.maxResults <= 0) errors.push('--max-results is required and must be > 0 (guardrail: no unbounded pulls)');
  if (!args.oldestPostDate) errors.push('--oldest-post-date is required (guardrail: no unbounded pulls) — format YYYY-MM-DD');
  if (errors.length) {
    throw new Error(`Invalid arguments:\n  - ${errors.join('\n  - ')}`);
  }
}

function emptySummary() {
  return { created: 0, updated: 0, wouldCreate: 0, wouldUpdate: 0, skipped: 0, channelsCreated: 0, errors: 0 };
}

function mergeSummary(total, part) {
  for (const key of Object.keys(total)) total[key] += part[key];
}

// In batch mode one --save-raw path would have each channel overwrite the last,
// so give each its own file. Single-channel runs keep the exact path given.
function rawPathFor(basePath, channel, index, isBatch) {
  if (!isBatch) return basePath;
  const slug = String(channel.channelName).replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
  const ext = path.extname(basePath);
  return path.join(
    path.dirname(basePath),
    `${path.basename(basePath, ext)}.${String(index + 1).padStart(2, '0')}-${slug}${ext}`
  );
}

// Harvest one channel. Returns its own summary so the caller can decide
// whether the sweep was clean enough to stamp Last harvested.
async function sweepChannel({ apifyToken, airtableKey, baseId, channel, args, capturedAt, rawPath }) {
  const summary = emptySummary();

  const input = {
    startUrls: [{ url: channel.sourceUrl }],
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
  if (rawPath) {
    fs.writeFileSync(rawPath, JSON.stringify(items, null, 2));
    console.log(`[apify] raw dataset written to ${rawPath}`);
  }

  // A channel sweep is all one channel, so resolve it once. Without this every
  // video re-queries Channels — wasted requests against Airtable's 5 req/s cap
  // (there's no retry/backoff), and in --dry-run it also reports the same
  // channel as "created" once per video, since nothing is ever really created.
  const channelCache = new Map();

  for (const item of items) {
    const built = buildVideoFields(item, { capturedAt });
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
      const channelKey = built.channel.handleKey || built.channel.fallbackKey;
      let channelResult = channelKey ? channelCache.get(channelKey) : undefined;
      if (!channelResult) {
        channelResult = await upsertChannel(airtableKey, baseId, built.channel, { dryRun: args.dryRun });
        if (channelKey) channelCache.set(channelKey, channelResult);

        if (channelResult.created) {
          summary.channelsCreated++;
          console.warn(`[channel] created "${built.channel.channelName}" (${channelKey}) with NO Track set — it will silently vanish from the working view (Track = AIHS OR Tooling-watch) until someone sets Track by hand.`);
        } else if (channelResult.matchedOn) {
          const stats = channelResult.statsUpdated ? ', stats refreshed' : '';
          console.log(`[channel] matched existing "${built.channel.channelName}" on ${channelResult.matchedOn}${stats}`);
        } else if (channelResult.skipped) {
          console.warn(`[channel] ${built.videoId}: ${channelResult.skipped} — video will have no Channel link`);
        }
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

  return summary;
}

// Resolve the channels to sweep: either the single --channel-url, or every
// Harvest?-ticked row in Airtable. A ticked row with no Source URL is a
// configuration mistake, so warn rather than guessing a URL from the handle.
async function resolveChannels(args, airtableKey, baseId) {
  // Playlist mode is a third channel-selection input, not a new data path:
  // the actor's startUrls accepts a playlist link the same way it accepts a
  // channel link (confirmed against the published input schema), and
  // transform.js already derives each video's Channel from the dataset
  // item's own channelUsername/channelUrl rather than from the input URL —
  // so a playlist spanning several channels upserts each one correctly with
  // no changes below this point. `recordId: null` means no Channels row gets
  // `Last harvested` stamped, same as a one-off --channel-url run.
  if (args.playlistUrl) {
    return [{ recordId: null, channelName: `playlist: ${args.playlistUrl}`, sourceUrl: args.playlistUrl }];
  }

  if (!args.fromAirtable) {
    return [{ recordId: null, channelName: args.channelUrl, sourceUrl: args.channelUrl }];
  }

  const rows = await listHarvestChannels(airtableKey, baseId);
  console.log(`[config] ${rows.length} channel(s) with Harvest? ticked`);

  const usable = [];
  for (const row of rows) {
    if (!row.sourceUrl) {
      console.warn(`[config] skipping "${row.channelName}" — Harvest? is ticked but Source URL is blank`);
      continue;
    }
    usable.push(row);
  }
  return usable;
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

  // One timestamp for the whole run, so every record swept together carries
  // the same Metrics Captured At and the snapshot is comparable across rows.
  const capturedAt = new Date().toISOString();

  const channels = await resolveChannels(args, airtableKey, baseId);
  if (channels.length === 0) {
    console.error('Nothing to harvest: no channel had both Harvest? ticked and a Source URL set.');
    process.exitCode = 1;
    return;
  }

  const isBatch = channels.length > 1;
  const total = emptySummary();
  let stopped = null;

  for (const [index, channel] of channels.entries()) {
    // Re-check the ceiling before EVERY channel, not once per run. Checking
    // once and then sweeping ten channels through that single verdict is how a
    // guardrail stops guarding at exactly the moment volume arrives — the
    // refinery's bottleneck is the human review gate, and this is what keeps
    // capture from outrunning it.
    const queuedCount = await countQueued(airtableKey, baseId);
    if (queuedCount >= args.queueCeiling) {
      stopped = { queuedCount, remaining: channels.slice(index) };
      break;
    }

    console.log(`\n=== [${index + 1}/${channels.length}] ${channel.channelName} — ${queuedCount} Queued (ceiling: ${args.queueCeiling}) ===`);

    // One bad channel must not abandon the rest of the batch.
    try {
      const summary = await sweepChannel({
        apifyToken,
        airtableKey,
        baseId,
        channel,
        args,
        capturedAt,
        rawPath: args.saveRaw ? rawPathFor(args.saveRaw, channel, index, isBatch) : null,
      });
      mergeSummary(total, summary);
      console.log(`[channel summary] ${channel.channelName}:`, JSON.stringify(summary));

      // Stamp Last harvested only on a clean sweep. A run with errors
      // deliberately leaves it stale so the gap stays visible in the base.
      if (channel.recordId && summary.errors === 0 && !args.dryRun) {
        await patchChannel(airtableKey, baseId, channel.recordId, { 'Last harvested': capturedAt });
        console.log(`[config] stamped Last harvested on "${channel.channelName}"`);
      } else if (channel.recordId && summary.errors > 0) {
        console.warn(`[config] NOT stamping Last harvested on "${channel.channelName}" — ${summary.errors} error(s), so it stays visibly stale.`);
      }
    } catch (error) {
      total.errors++;
      console.error(`[error] channel "${channel.channelName}": ${error.message}`);
    }
  }

  console.log('\n[summary]', JSON.stringify(total, null, 2));

  if (stopped) {
    console.error(
      `\nStopped before ${stopped.remaining.length} remaining channel(s): Queued count (${stopped.queuedCount}) reached the ceiling (${args.queueCeiling}). The refinery's bottleneck is the human review gate, not capture — clear the queue, then re-run.\n  Not swept: ${stopped.remaining.map((c) => c.channelName).join(', ')}`
    );
    process.exitCode = 1;
  }

  if (args.dryRun) console.log('\nDry run — nothing was written to Airtable.');
  if (total.errors > 0) {
    console.error(`\n${total.errors} item(s) failed — see [error] lines above.`);
    process.exitCode = 1;
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`\nError: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = { parseArgs, parseDotEnv, validateArgs, elideTranscripts, USAGE };
