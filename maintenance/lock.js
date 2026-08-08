// Run lock for the business-playlist maintenance orchestrator.
//
// A stakeholder review of the original design rejected an age-only stale-lock
// break: "Don't break a stale lock based only on age. Record PID/host/
// heartbeat and reclaim only when the owner is demonstrably dead." This module
// implements that — reclaim requires BOTH a stale heartbeat AND a same-host
// PID that is no longer running. A lock held by a different host can never be
// proven dead from here, so it is never auto-reclaimed, regardless of age —
// that requires a human to remove the lock file by hand.

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const DEFAULT_STALE_AFTER_MS = 15 * 60 * 1000; // 15 minutes with no heartbeat

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM means the process exists but is owned by someone else — still alive.
    return error.code === 'EPERM';
  }
}

function readLock(lockPath) {
  if (!fs.existsSync(lockPath)) return null;
  return JSON.parse(fs.readFileSync(lockPath, 'utf8'));
}

function writeLockAtomic(lockPath, lock) {
  const tmpPath = `${lockPath}.tmp`;
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  fs.writeFileSync(tmpPath, `${JSON.stringify(lock, null, 2)}\n`);
  fs.renameSync(tmpPath, lockPath);
}

function isStale(lock, { now, staleAfterMs }) {
  return now - lock.heartbeatAt > staleAfterMs;
}

// A lock can only be proven dead when we can check the PID ourselves, which
// requires the recorded host to match the host doing the checking.
function isOwnerDemonstrablyDead(lock, { host, checkAlive }) {
  if (lock.host !== host) return false;
  return !checkAlive(lock.pid);
}

function describeHeldLock(existing, { host, stale, dead }) {
  const base = `Run lock held by pid=${existing.pid} host=${existing.host} since ` +
    `${new Date(existing.acquiredAt).toISOString()} (heartbeat ${new Date(existing.heartbeatAt).toISOString()}).`;
  if (existing.host !== host) {
    return `${base} Owner is on a different host; refusing to guess liveness — remove the lock file by hand if it is truly dead.`;
  }
  if (!stale) return `${base} Heartbeat is current.`;
  if (!dead) return `${base} Heartbeat is stale but the owning process is still alive.`;
  return base;
}

function acquireLock(lockPath, {
  pid = process.pid,
  host = os.hostname(),
  now = Date.now(),
  staleAfterMs = DEFAULT_STALE_AFTER_MS,
  checkAlive = isProcessAlive,
} = {}) {
  const existing = readLock(lockPath);
  if (existing) {
    const stale = isStale(existing, { now, staleAfterMs });
    const dead = isOwnerDemonstrablyDead(existing, { host, checkAlive });
    if (!(stale && dead)) {
      throw new Error(describeHeldLock(existing, { host, stale, dead }));
    }
  }
  const lock = { pid, host, acquiredAt: now, heartbeatAt: now };
  writeLockAtomic(lockPath, lock);
  return lock;
}

function heartbeat(lockPath, { pid = process.pid, host = os.hostname(), now = Date.now() } = {}) {
  const existing = readLock(lockPath);
  if (!existing || existing.pid !== pid || existing.host !== host) {
    throw new Error('Lost the run lock — another process holds it now. Aborting rather than continuing unsafely.');
  }
  writeLockAtomic(lockPath, { ...existing, heartbeatAt: now });
}

function releaseLock(lockPath, { pid = process.pid, host = os.hostname() } = {}) {
  const existing = readLock(lockPath);
  if (!existing) return;
  if (existing.pid !== pid || existing.host !== host) {
    throw new Error('Refusing to release a run lock owned by a different process.');
  }
  fs.unlinkSync(lockPath);
}

module.exports = {
  DEFAULT_STALE_AFTER_MS,
  acquireLock,
  heartbeat,
  releaseLock,
  readLock,
  isProcessAlive,
  isOwnerDemonstrablyDead,
  isStale,
};
