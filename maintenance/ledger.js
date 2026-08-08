// Write-ahead ledger for the business-playlist maintenance orchestrator.
//
// A stakeholder review rejected a single completed-step-only log line: "A
// completed-step-only event still loses the exact crash window it is
// intended to protect." This is the fix — every mutation gets an `intent`
// event written BEFORE it's attempted and a `result` event written after. A
// crash between the two leaves a legible orphaned intent instead of silence,
// so a later run (or a human) can tell exactly where a video's processing
// stopped rather than finding nothing.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function ensureDir(ledgerPath) {
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true });
}

function appendEvent(ledgerPath, event) {
  ensureDir(ledgerPath);
  fs.appendFileSync(ledgerPath, `${JSON.stringify(event)}\n`);
}

// Returns the intent's id so the caller can pass it to writeResult — pairing
// is explicit, never inferred from ordering or timing.
function writeIntent(ledgerPath, { step, ...details }, { now = Date.now(), id = crypto.randomUUID() } = {}) {
  const event = { type: 'intent', id, step, at: now, ...details };
  appendEvent(ledgerPath, event);
  return id;
}

function writeResult(ledgerPath, intentId, { status, ...details }, { now = Date.now() } = {}) {
  if (!intentId) {
    throw new Error(
      'writeResult requires the intentId returned by writeIntent — a result with no matching intent ' +
      'is exactly the silent gap this ledger exists to prevent.'
    );
  }
  const event = { type: 'result', intentId, status, at: now, ...details };
  appendEvent(ledgerPath, event);
  return event;
}

function readLedger(ledgerPath) {
  if (!fs.existsSync(ledgerPath)) return [];
  return fs.readFileSync(ledgerPath, 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

// Intents with no matching result — the exact crash window the write-ahead
// design exists to make legible. Meant for post-run/post-crash reporting.
function findOrphanIntents(events) {
  const resultIntentIds = new Set(events.filter((event) => event.type === 'result').map((event) => event.intentId));
  return events.filter((event) => event.type === 'intent' && !resultIntentIds.has(event.id));
}

module.exports = { appendEvent, writeIntent, writeResult, readLedger, findOrphanIntents };
