const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const {
  isTransientError,
  classifyError,
  retryWithBackoff,
} = require('../retry');

// ---------------------------------------------------------------------------
// isTransientError
// ---------------------------------------------------------------------------
describe('isTransientError', () => {
  it('returns true for waitForFunction timeout', () => {
    const err = new Error('page.waitForFunction: Timeout 30000ms exceeded.');
    assert.equal(isTransientError(err), true);
  });

  it('returns true for elementHandle.screenshot timeout', () => {
    const err = new Error('elementHandle.screenshot: Timeout 30000ms exceeded.');
    assert.equal(isTransientError(err), true);
  });

  it('returns true for net::ERR_NETWORK_CHANGED', () => {
    const err = new Error('net::ERR_NETWORK_CHANGED');
    assert.equal(isTransientError(err), true);
  });

  it('returns true for net::ERR_INTERNET_DISCONNECTED', () => {
    const err = new Error('net::ERR_INTERNET_DISCONNECTED');
    assert.equal(isTransientError(err), true);
  });

  it('returns true for Target closed', () => {
    const err = new Error('Target closed');
    assert.equal(isTransientError(err), true);
  });

  it('returns true for Navigation timeout', () => {
    const err = new Error('page.goto: Timeout 20000ms exceeded.');
    assert.equal(isTransientError(err), true);
  });

  it('returns true when transient pattern is in stderr', () => {
    const err = new Error('Command exited with code 1');
    err.stderr = 'Error during capture: page.waitForFunction: Timeout 30000ms exceeded.';
    assert.equal(isTransientError(err), true);
  });

  it('returns false for Invalid YouTube URL', () => {
    const err = new Error('Invalid YouTube URL: could not extract video ID');
    assert.equal(isTransientError(err), false);
  });

  it('returns false for exceeds video duration', () => {
    const err = new Error('Timestamp 999s exceeds video duration 60s');
    assert.equal(isTransientError(err), false);
  });

  it('returns false for generic unknown errors', () => {
    const err = new Error('Something completely unexpected');
    assert.equal(isTransientError(err), false);
  });
});

// ---------------------------------------------------------------------------
// classifyError
// ---------------------------------------------------------------------------
describe('classifyError', () => {
  it('returns "transient" for timeout errors', () => {
    const err = new Error('Timeout 30000ms exceeded');
    assert.equal(classifyError(err), 'transient');
  });

  it('returns "permanent" for invalid URL errors', () => {
    const err = new Error('Invalid YouTube URL');
    assert.equal(classifyError(err), 'permanent');
  });

  it('returns "unknown" for unrecognized errors', () => {
    const err = new Error('Something weird happened');
    assert.equal(classifyError(err), 'unknown');
  });
});

// ---------------------------------------------------------------------------
// retryWithBackoff
// ---------------------------------------------------------------------------
describe('retryWithBackoff', () => {
  it('returns result on first success', async () => {
    let calls = 0;
    const result = await retryWithBackoff(async () => {
      calls++;
      return 'ok';
    }, { maxRetries: 3, baseDelayMs: 1 });

    assert.equal(result, 'ok');
    assert.equal(calls, 1);
  });

  it('retries on transient error and succeeds', async () => {
    let calls = 0;
    const result = await retryWithBackoff(async () => {
      calls++;
      if (calls < 3) throw new Error('Timeout 30000ms exceeded');
      return 'recovered';
    }, { maxRetries: 3, baseDelayMs: 1 });

    assert.equal(result, 'recovered');
    assert.equal(calls, 3);
  });

  it('does NOT retry on permanent error', async () => {
    let calls = 0;
    await assert.rejects(
      () => retryWithBackoff(async () => {
        calls++;
        throw new Error('Invalid YouTube URL: could not extract video ID');
      }, { maxRetries: 3, baseDelayMs: 1 }),
      (err) => err.message.includes('Invalid YouTube URL')
    );
    assert.equal(calls, 1);
  });

  it('throws after exhausting all retries', async () => {
    let calls = 0;
    await assert.rejects(
      () => retryWithBackoff(async () => {
        calls++;
        throw new Error('Timeout 30000ms exceeded');
      }, { maxRetries: 2, baseDelayMs: 1 }),
      (err) => err.message.includes('Timeout')
    );
    assert.equal(calls, 3); // 1 initial + 2 retries
  });

  it('calls onRetry callback before each retry', async () => {
    const retryLog = [];
    let calls = 0;
    await assert.rejects(
      () => retryWithBackoff(async () => {
        calls++;
        throw new Error('Timeout 30000ms exceeded');
      }, {
        maxRetries: 2,
        baseDelayMs: 1,
        onRetry: (attempt, err, delayMs) => {
          retryLog.push({ attempt, message: err.message, delayMs });
        },
      }),
    );

    assert.equal(retryLog.length, 2);
    assert.equal(retryLog[0].attempt, 1);
    assert.equal(retryLog[1].attempt, 2);
    assert.ok(retryLog[0].message.includes('Timeout'));
  });

  it('applies exponential backoff delays', async () => {
    const delays = [];
    let calls = 0;
    await assert.rejects(
      () => retryWithBackoff(async () => {
        calls++;
        throw new Error('Timeout 30000ms exceeded');
      }, {
        maxRetries: 3,
        baseDelayMs: 100,
        onRetry: (attempt, err, delayMs) => {
          delays.push(delayMs);
        },
      }),
    );

    // Delays should increase: 100, 200, 400 (exponential)
    assert.ok(delays[0] >= 100 && delays[0] <= 200, `delay[0]=${delays[0]}`);
    assert.ok(delays[1] >= 200 && delays[1] <= 400, `delay[1]=${delays[1]}`);
    assert.ok(delays[2] >= 400 && delays[2] <= 800, `delay[2]=${delays[2]}`);
  });

  it('respects maxDelayMs cap', async () => {
    const delays = [];
    let calls = 0;
    await assert.rejects(
      () => retryWithBackoff(async () => {
        calls++;
        throw new Error('Timeout 30000ms exceeded');
      }, {
        maxRetries: 5,
        baseDelayMs: 1000,
        maxDelayMs: 2000,
        onRetry: (attempt, err, delayMs) => {
          delays.push(delayMs);
        },
      }),
    );

    // All delays should be capped at 2000ms
    for (const d of delays) {
      assert.ok(d <= 2000, `delay ${d} exceeded maxDelayMs 2000`);
    }
  });
});
