#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const readline = require('node:readline/promises');
const { spawn } = require('node:child_process');
const { URL } = require('node:url');
const { google } = require('googleapis');

const { parseDotEnv } = require('../normalizer/apify-harvest');
const { resolveGoogleClientCredentials } = require('./runtime');

const PORT = 3000;
const REDIRECT_URI = `http://localhost:${PORT}`;
const ENV_PATH = path.join(__dirname, '..', '.env');

function getOAuthTarget(target) {
  if (target === 'personal-read') {
    return {
      name: 'personal source channel',
      envKey: 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN',
      scopes: ['https://www.googleapis.com/auth/youtube.readonly'],
    };
  }
  if (target === 'business') {
    return {
      name: 'business destination channel',
      envKey: 'GOOGLE_REFRESH_TOKEN',
      scopes: ['https://www.googleapis.com/auth/youtube.force-ssl'],
    };
  }
  throw new Error('A target is required: --target personal-read or --target business');
}

function authRequestOptions(target, state) {
  return {
    access_type: 'offline',
    prompt: 'select_account consent',
    scope: target.scopes,
    state,
  };
}

function parseTargetArg(argv) {
  let target;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--target') target = argv[++index];
    else if (arg.startsWith('--target=')) target = arg.slice('--target='.length);
    else if (arg === '--help' || arg === '-h') return { help: true };
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return { help: false, target: getOAuthTarget(target), targetName: target };
}

function loadDotEnv(envPath = ENV_PATH) {
  const values = fs.existsSync(envPath) ? parseDotEnv(fs.readFileSync(envPath, 'utf8')) : {};
  return { ...values, ...process.env };
}

function writeEnvValue(envPath, key, value) {
  const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
  const lines = existing.split('\n');
  const matcher = new RegExp(`^${key}=`);
  const index = lines.findIndex((line) => matcher.test(line.trim()));
  const replacement = `${key}=${value}`;

  if (index === -1) {
    const prefix = existing === '' || existing.endsWith('\n') ? existing : `${existing}\n`;
    fs.writeFileSync(envPath, `${prefix}${replacement}\n`);
  } else {
    lines[index] = replacement;
    fs.writeFileSync(envPath, lines.join('\n'));
  }
}

function openInBrowser(url) {
  const cmd = process.platform === 'darwin' ? 'open'
    : process.platform === 'win32' ? 'start'
    : 'xdg-open';
  try {
    spawn(cmd, [url], { stdio: 'ignore', detached: true, shell: process.platform === 'win32' })
      .on('error', () => {})
      .unref();
  } catch {
    // The printed URL remains the fallback.
  }
}

function waitForAuthCode(expectedState) {
  return new Promise((resolve, reject) => {
    const sockets = new Set();
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, REDIRECT_URI);
      if (url.pathname !== '/') {
        res.writeHead(204).end();
        return;
      }

      const code = url.searchParams.get('code');
      const error = url.searchParams.get('error');
      const returnedState = url.searchParams.get('state');
      if (error) {
        res.end(`Authorization failed: ${error}. You can close this tab.`);
        finish(() => reject(new Error(error)));
        return;
      }
      if (code && returnedState !== expectedState) {
        res.end('State mismatch. You can close this tab.');
        finish(() => reject(new Error('OAuth state mismatch')));
        return;
      }
      if (code) {
        res.end('Authorization successful. Return to the terminal to confirm the channel.');
        finish(() => resolve(code));
        return;
      }
      res.end('Waiting for the OAuth callback.');
    });

    let settled = false;
    function finish(action) {
      if (settled) return;
      settled = true;
      server.close();
      for (const socket of sockets) socket.destroy();
      action();
    }

    server.on('connection', (socket) => {
      sockets.add(socket);
      socket.on('close', () => sockets.delete(socket));
    });
    server.on('error', (error) => {
      if (error.code === 'EADDRINUSE') {
        finish(() => reject(new Error(`Port ${PORT} is already in use; stop that listener and retry.`)));
      } else {
        finish(() => reject(error));
      }
    });
    server.listen(PORT);
  });
}

async function confirmChannel(channel, target) {
  const title = channel.snippet?.title || '(untitled)';
  console.log(`\nAuthorized ${target.name}: ${title} (${channel.id})`);
  const prompt = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    const answer = await prompt.question(`Store this credential in ${target.envKey}? Type yes to confirm: `);
    return answer.trim().toLowerCase() === 'yes';
  } finally {
    prompt.close();
  }
}

async function main(argv = process.argv.slice(2)) {
  const parsed = parseTargetArg(argv);
  if (parsed.help) {
    console.log('Usage: node get-refresh-token.js --target personal-read|business');
    return;
  }
  const target = parsed.target;
  const env = loadDotEnv();
  const clientCredentials = resolveGoogleClientCredentials(env, target.envKey);

  const oauth2Client = new google.auth.OAuth2(clientCredentials.clientId, clientCredentials.clientSecret, REDIRECT_URI);
  const state = crypto.randomBytes(16).toString('hex');
  const authUrl = oauth2Client.generateAuthUrl(authRequestOptions(target, state));

  console.log(`\nAuthorize the ${target.name} using this URL:\n\n${authUrl}\n`);
  console.log(`Requested scope: ${target.scopes.join(', ')}`);
  openInBrowser(authUrl);
  console.log(`Waiting for approval on ${REDIRECT_URI} (Ctrl-C to abort)...`);

  const code = await waitForAuthCode(state);
  const { tokens } = await oauth2Client.getToken(code);
  if (!tokens.refresh_token) {
    throw new Error('Google returned no refresh token. Revoke this app grant, then retry with consent.');
  }

  oauth2Client.setCredentials({ refresh_token: tokens.refresh_token });
  const youtube = google.youtube({ version: 'v3', auth: oauth2Client });
  const response = await youtube.channels.list({ part: ['id', 'snippet'], mine: true });
  const channels = response.data.items || [];
  if (channels.length !== 1) throw new Error(`Expected one authorized YouTube channel; received ${channels.length}`);

  if (!await confirmChannel(channels[0], target)) {
    console.log('Credential was not saved.');
    return;
  }
  writeEnvValue(ENV_PATH, target.envKey, tokens.refresh_token);
  console.log(`Saved ${target.envKey} to the repo-root .env without printing the token.`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Fatal error: ${error.message || error}`);
    process.exitCode = 1;
  });
}

module.exports = {
  authRequestOptions,
  confirmChannel,
  getOAuthTarget,
  loadDotEnv,
  main,
  parseTargetArg,
  waitForAuthCode,
  writeEnvValue,
};
