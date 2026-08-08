#!/usr/bin/env node

const { findVideoByVideoId } = require('../normalizer/lib/airtable-client');
const { drainPlaylists, readConfig } = require('./playlist-manager');
const {
  CONFIG_PATH,
  createYoutubeClient,
  loadEnvironment,
  parseCommonArgs,
  requireEnvironment,
} = require('./runtime');

function printUsage() {
  console.log(`Usage: node drain-playlists.js [--apply] [--max-writes N]

Default mode is read-only. --apply removes only business playlist items whose
Video ID has exactly one Airtable record with a verified nonempty transcript.`);
}

function printSummary(result) {
  console.log(
    `\nDrain ${result.mode}: eligible=${result.eligible}, deleted=${result.deleted}, ` +
    `already-removed=${result.alreadyRemoved}, retained=${result.retained}, deferred=${result.deferred}, ` +
    `unavailable=${result.unavailable}, errors=${result.errors.length}`
  );
  for (const playlist of result.playlists) {
    console.log(
      `- ${playlist.name}: total=${playlist.total}, eligible=${playlist.eligible}, ` +
      `deleted=${playlist.deleted}, retained=${playlist.retained}, unavailable=${playlist.unavailable}, errors=${playlist.errors}`
    );
  }
  for (const error of result.errors) {
    console.error(`  [error] ${error.playlist}${error.videoId ? ` video=${error.videoId}` : ''}: ${error.error}`);
  }
}

async function main(argv = process.argv.slice(2)) {
  const args = parseCommonArgs(argv);
  if (args.help) return printUsage();
  const env = loadEnvironment();
  requireEnvironment(env, ['AIRTABLE_API_KEY', 'AIRTABLE_BASE_ID']);
  const config = readConfig(CONFIG_PATH);
  const result = await drainPlaylists({
    businessYoutube: createYoutubeClient(env, 'GOOGLE_REFRESH_TOKEN'),
    config,
    apply: args.apply,
    maxWrites: args.maxWrites,
    findVideo: (videoId) => findVideoByVideoId(env.AIRTABLE_API_KEY, env.AIRTABLE_BASE_ID, videoId),
  });
  printSummary(result);
  if (result.errors.length > 0) process.exitCode = 1;
  else if (args.apply && result.deferred > 0) process.exitCode = 2;
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Drain failed: ${error.message || error}`);
    process.exitCode = 1;
  });
}

module.exports = { main, printSummary, printUsage };
