const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { writeIntent, writeResult, readLedger, findOrphanIntents } = require('./ledger');

function tmpLedgerPath() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'maintenance-ledger-'));
  return path.join(dir, 'state', 'ledger.jsonl');
}

test('writeIntent then writeResult appends a paired, readable JSONL log', () => {
  const ledgerPath = tmpLedgerPath();
  const id = writeIntent(ledgerPath, { step: 'drain-delete', videoId: 'AAA' }, { now: 1, id: 'intent-1' });
  writeResult(ledgerPath, id, { status: 'ok' }, { now: 2 });

  const events = readLedger(ledgerPath);
  assert.equal(events.length, 2);
  assert.deepEqual(events[0], { type: 'intent', id: 'intent-1', step: 'drain-delete', videoId: 'AAA', at: 1 });
  assert.deepEqual(events[1], { type: 'result', intentId: 'intent-1', status: 'ok', at: 2 });
});

test('writeResult refuses a result with no intentId', () => {
  const ledgerPath = tmpLedgerPath();
  assert.throws(() => writeResult(ledgerPath, null, { status: 'ok' }), /requires the intentId/i);
  assert.throws(() => writeResult(ledgerPath, undefined, { status: 'ok' }), /requires the intentId/i);
});

test('readLedger returns an empty array when the file does not exist yet', () => {
  const ledgerPath = tmpLedgerPath();
  assert.deepEqual(readLedger(ledgerPath), []);
});

test('appendEvent creates the parent state directory on first write', () => {
  const ledgerPath = tmpLedgerPath();
  assert.equal(fs.existsSync(path.dirname(ledgerPath)), false);
  writeIntent(ledgerPath, { step: 'x' }, { now: 1, id: 'i1' });
  assert.equal(fs.existsSync(ledgerPath), true);
});

test('findOrphanIntents surfaces a crash window: an intent with no matching result', () => {
  const ledgerPath = tmpLedgerPath();
  writeIntent(ledgerPath, { step: 'harvest', videoId: 'AAA' }, { now: 1, id: 'i-complete' });
  writeResult(ledgerPath, 'i-complete', { status: 'ok' }, { now: 2 });
  writeIntent(ledgerPath, { step: 'harvest', videoId: 'BBB' }, { now: 3, id: 'i-crashed' });
  // no matching result for i-crashed — simulates a crash between intent and result

  const orphans = findOrphanIntents(readLedger(ledgerPath));
  assert.equal(orphans.length, 1);
  assert.equal(orphans[0].id, 'i-crashed');
  assert.equal(orphans[0].videoId, 'BBB');
});
