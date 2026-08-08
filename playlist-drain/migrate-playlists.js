#!/usr/bin/env node

const { migratePlaylists, readConfig, writeConfigAtomic } = require('./playlist-manager');
const { CONFIG_PATH, createYoutubeClient, loadEnvironment, parseCommonArgs } = require('./runtime');

function printUsage() {
  console.log(`Usage: node migrate-playlists.js [--apply] [--max-writes N]

Default mode is a read-only preflight. --apply creates/resumes business-owned
playlists. Google write calls stop after 175 operations unless overridden.`);
}

function printSummary(result) {
  console.log(`\nMigration ${result.mode}: ${result.writes} writes; estimated pending quota cost=${result.estimatedQuotaUnits}.`);
  for (const playlist of result.playlists) {
    console.log(
      `- ${playlist.name}: source=${playlist.sourceCount}, destination-before=${playlist.destinationCountBefore}, ` +
      `inserted=${playlist.inserted}, remaining=${playlist.remaining}, unavailable=${playlist.unavailableCount}, ` +
      `validated=${playlist.validated}, destination=${playlist.destinationPlaylistId || '(not created)'}`
    );
    console.log(`  source-sha256=${playlist.sourceHash}`);
    if (playlist.destinationHashAfter) console.log(`  destination-sha256=${playlist.destinationHashAfter}`);
    if (playlist.unavailableCount > 0) console.log(`  unavailable source positions: ${playlist.unavailablePositions.join(', ')}`);
  }
  if (result.quotaExhausted) console.log('YouTube quota was exhausted. Progress is saved; rerun after quota resets.');
  if (!result.complete && result.mode === 'apply') console.log('Migration is incomplete and can be resumed safely.');
}

async function main(argv = process.argv.slice(2)) {
  const args = parseCommonArgs(argv);
  if (args.help) return printUsage();
  const env = loadEnvironment();
  const config = readConfig(CONFIG_PATH);
  const result = await migratePlaylists({
    sourceYoutube: createYoutubeClient(env, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN'),
    businessYoutube: createYoutubeClient(env, 'GOOGLE_REFRESH_TOKEN'),
    config,
    apply: args.apply,
    maxWrites: args.maxWrites,
    persistConfig: (nextConfig) => writeConfigAtomic(CONFIG_PATH, nextConfig),
  });
  printSummary(result);
  if (args.apply && !result.complete) process.exitCode = 2;
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Migration failed: ${error.message || error}`);
    process.exitCode = 1;
  });
}

module.exports = { main, printSummary, printUsage };
