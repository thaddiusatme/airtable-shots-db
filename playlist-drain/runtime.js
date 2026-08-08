const fs = require('node:fs');
const path = require('node:path');
const { google } = require('googleapis');

const { parseDotEnv } = require('../normalizer/apify-harvest');
const { DEFAULT_MAX_WRITES } = require('./playlist-manager');

const REPO_ROOT = path.join(__dirname, '..');
const ENV_PATH = path.join(REPO_ROOT, '.env');
const CONFIG_PATH = path.join(__dirname, 'playlists.json');

function loadEnvironment(envPath = ENV_PATH, processValues = process.env) {
  const fileValues = fs.existsSync(envPath) ? parseDotEnv(fs.readFileSync(envPath, 'utf8')) : {};
  return { ...fileValues, ...processValues };
}

function requireEnvironment(env, names) {
  const missing = names.filter((name) => !env[name]);
  if (missing.length > 0) throw new Error(`Missing required environment values: ${missing.join(', ')}`);
}

function parseCommonArgs(argv) {
  const args = { apply: false, maxWrites: DEFAULT_MAX_WRITES, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--apply') args.apply = true;
    else if (arg === '--help' || arg === '-h') args.help = true;
    else if (arg === '--max-writes') args.maxWrites = Number(argv[++index]);
    else if (arg.startsWith('--max-writes=')) args.maxWrites = Number(arg.slice('--max-writes='.length));
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!Number.isInteger(args.maxWrites) || args.maxWrites < 1) {
    throw new Error('--max-writes must be a positive integer');
  }
  return args;
}

function resolveGoogleClientCredentials(env, refreshTokenKey) {
  if (refreshTokenKey === 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN') {
    const hasPersonalId = Boolean(env.GOOGLE_PERSONAL_CLIENT_ID);
    const hasPersonalSecret = Boolean(env.GOOGLE_PERSONAL_CLIENT_SECRET);
    if (hasPersonalId !== hasPersonalSecret) {
      throw new Error('Set both GOOGLE_PERSONAL_CLIENT_ID and GOOGLE_PERSONAL_CLIENT_SECRET, or neither.');
    }
    if (hasPersonalId) {
      return {
        clientId: env.GOOGLE_PERSONAL_CLIENT_ID,
        clientSecret: env.GOOGLE_PERSONAL_CLIENT_SECRET,
      };
    }
  }
  requireEnvironment(env, ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET']);
  return { clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET };
}

function createYoutubeClient(env, refreshTokenKey) {
  requireEnvironment(env, [refreshTokenKey]);
  const credentials = resolveGoogleClientCredentials(env, refreshTokenKey);
  const auth = new google.auth.OAuth2(
    credentials.clientId,
    credentials.clientSecret,
    'http://localhost:3000'
  );
  auth.setCredentials({ refresh_token: env[refreshTokenKey] });
  return google.youtube({ version: 'v3', auth });
}

module.exports = {
  CONFIG_PATH,
  ENV_PATH,
  REPO_ROOT,
  createYoutubeClient,
  loadEnvironment,
  parseCommonArgs,
  requireEnvironment,
  resolveGoogleClientCredentials,
};
