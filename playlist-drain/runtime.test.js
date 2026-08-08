const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { authRequestOptions, getOAuthTarget, writeEnvValue } = require('./get-refresh-token');
const { loadEnvironment, parseCommonArgs, resolveGoogleClientCredentials } = require('./runtime');

test('OAuth targets keep the personal read token separate from the business write token', () => {
  const personal = getOAuthTarget('personal-read');
  assert.equal(personal.envKey, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN');
  assert.deepEqual(personal.scopes, ['https://www.googleapis.com/auth/youtube.readonly']);

  const business = getOAuthTarget('business');
  assert.equal(business.envKey, 'GOOGLE_REFRESH_TOKEN');
  assert.deepEqual(business.scopes, ['https://www.googleapis.com/auth/youtube.force-ssl']);
  assert.throws(() => getOAuthTarget('personal'), /target/i);
});

test('OAuth forces account selection so an existing business grant cannot silently win', () => {
  const options = authRequestOptions(getOAuthTarget('personal-read'), 'csrf');
  assert.equal(options.prompt, 'select_account consent');
  assert.equal(options.state, 'csrf');
});

test('writeEnvValue replaces only the requested key and never duplicates it', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'playlist-env-'));
  const envPath = path.join(dir, '.env');
  fs.writeFileSync(envPath, 'GOOGLE_REFRESH_TOKEN=business\nOTHER=value\n');
  writeEnvValue(envPath, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN', 'personal');
  writeEnvValue(envPath, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN', 'replacement');
  const text = fs.readFileSync(envPath, 'utf8');
  assert.match(text, /^GOOGLE_REFRESH_TOKEN=business$/m);
  assert.match(text, /^GOOGLE_PERSONAL_READ_REFRESH_TOKEN=replacement$/m);
  assert.equal((text.match(/^GOOGLE_PERSONAL_READ_REFRESH_TOKEN=/gm) || []).length, 1);
});

test('loadEnvironment gives process values precedence over .env without exposing secrets', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'playlist-runtime-'));
  const envPath = path.join(dir, '.env');
  fs.writeFileSync(envPath, 'A=file\nB="quoted"\n');
  const env = loadEnvironment(envPath, { A: 'process' });
  assert.deepEqual(env, { A: 'process', B: 'quoted' });
});

test('parseCommonArgs defaults to dry-run and validates max writes', () => {
  assert.deepEqual(parseCommonArgs([]), { apply: false, maxWrites: 175, help: false });
  assert.deepEqual(parseCommonArgs(['--apply', '--max-writes', '12']), { apply: true, maxWrites: 12, help: false });
  assert.deepEqual(parseCommonArgs(['--max-writes=7']), { apply: false, maxWrites: 7, help: false });
  assert.throws(() => parseCommonArgs(['--max-writes', '0']), /positive integer/i);
  assert.throws(() => parseCommonArgs(['--wat']), /unknown argument/i);
});

test('personal OAuth can use a separate client without changing business credentials', () => {
  const env = {
    GOOGLE_CLIENT_ID: 'business-id',
    GOOGLE_CLIENT_SECRET: 'business-secret',
    GOOGLE_PERSONAL_CLIENT_ID: 'personal-id',
    GOOGLE_PERSONAL_CLIENT_SECRET: 'personal-secret',
  };
  assert.deepEqual(resolveGoogleClientCredentials(env, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN'), {
    clientId: 'personal-id',
    clientSecret: 'personal-secret',
  });
  assert.deepEqual(resolveGoogleClientCredentials(env, 'GOOGLE_REFRESH_TOKEN'), {
    clientId: 'business-id',
    clientSecret: 'business-secret',
  });
  assert.throws(
    () => resolveGoogleClientCredentials({ ...env, GOOGLE_PERSONAL_CLIENT_SECRET: '' }, 'GOOGLE_PERSONAL_READ_REFRESH_TOKEN'),
    /both GOOGLE_PERSONAL_CLIENT_ID and GOOGLE_PERSONAL_CLIENT_SECRET/i
  );
});
