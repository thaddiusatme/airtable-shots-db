const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { acquireLock, heartbeat, releaseLock, readLock } = require('./lock');

function tmpLockPath() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'maintenance-lock-'));
  return path.join(dir, 'state', 'run.lock');
}

test('acquireLock writes a fresh lock when none exists', () => {
  const lockPath = tmpLockPath();
  const lock = acquireLock(lockPath, { pid: 111, host: 'host-a', now: 1000 });
  assert.deepEqual(lock, { pid: 111, host: 'host-a', acquiredAt: 1000, heartbeatAt: 1000 });
  assert.deepEqual(readLock(lockPath), lock);
});

test('acquireLock refuses when the current owner is alive, even past the stale window', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  assert.throws(
    () => acquireLock(lockPath, {
      pid: 222,
      host: 'host-a',
      now: 1_000_000,
      staleAfterMs: 100,
      checkAlive: () => true,
    }),
    /still alive/i
  );
});

test('acquireLock refuses a same-host lock that is stale but not yet provably dead', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  assert.throws(
    () => acquireLock(lockPath, {
      pid: 222,
      host: 'host-a',
      now: 50, // within staleAfterMs
      staleAfterMs: 100,
      checkAlive: () => false,
    }),
    /Run lock held/i
  );
});

test('acquireLock reclaims only when BOTH stale and the same-host owner is provably dead', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  const reclaimed = acquireLock(lockPath, {
    pid: 222,
    host: 'host-a',
    now: 1000,
    staleAfterMs: 100,
    checkAlive: () => false,
  });
  assert.equal(reclaimed.pid, 222);
  assert.deepEqual(readLock(lockPath), reclaimed);
});

test('acquireLock never reclaims a lock owned by a different host, no matter how stale', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  assert.throws(
    () => acquireLock(lockPath, {
      pid: 222,
      host: 'host-b',
      now: 1_000_000_000, // absurdly stale
      staleAfterMs: 100,
      checkAlive: () => { throw new Error('must not be called for a foreign host'); },
    }),
    /different host/i
  );
});

test('heartbeat refreshes heartbeatAt for the owning pid/host and rejects everyone else', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  heartbeat(lockPath, { pid: 111, host: 'host-a', now: 500 });
  assert.equal(readLock(lockPath).heartbeatAt, 500);

  assert.throws(() => heartbeat(lockPath, { pid: 999, host: 'host-a', now: 600 }), /lost the run lock/i);
});

test('heartbeat on a missing lock file means the lock was lost', () => {
  const lockPath = tmpLockPath();
  assert.throws(() => heartbeat(lockPath, { pid: 111, host: 'host-a' }), /lost the run lock/i);
});

test('releaseLock removes the lock only for its owner, and is a no-op if already gone', () => {
  const lockPath = tmpLockPath();
  acquireLock(lockPath, { pid: 111, host: 'host-a', now: 0 });
  assert.throws(() => releaseLock(lockPath, { pid: 999, host: 'host-a' }), /different process/i);
  assert.equal(fs.existsSync(lockPath), true);

  releaseLock(lockPath, { pid: 111, host: 'host-a' });
  assert.equal(fs.existsSync(lockPath), false);
  assert.doesNotThrow(() => releaseLock(lockPath, { pid: 111, host: 'host-a' }));
});
