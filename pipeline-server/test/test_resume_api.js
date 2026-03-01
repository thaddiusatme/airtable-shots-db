const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const http = require('http');
const { app, jobs } = require('../server');

let server;
let baseUrl;

beforeEach((_, done) => {
  jobs.clear();
  server = app.listen(0, '127.0.0.1', () => {
    const { port } = server.address();
    baseUrl = `http://127.0.0.1:${port}`;
    done();
  });
});

afterEach((_, done) => {
  server.close(done);
});

// Helper: make HTTP request and return parsed JSON
function request(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl);
    const opts = {
      method,
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      headers: { 'Content-Type': 'application/json' },
    };
    const req = http.request(opts, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, body: data });
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// Helper: seed a job into the in-memory store
function seedJob(overrides = {}) {
  const job = {
    runId: overrides.runId || 'test-run-001',
    status: overrides.status || 'error',
    step: overrides.step || 'capture',
    message: overrides.message || 'Failed at capture',
    error: overrides.error || 'Timeout 30000ms exceeded',
    errorDetail: null,
    completedSteps: overrides.completedSteps || ['upsert_video'],
    input: overrides.input || {
      videoUrl: 'https://youtube.com/watch?v=abc123',
      videoId: 'abc123',
      videoTitle: 'Test Video',
      transcript: 'test',
      transcriptSegments: [],
      capture: { interval: 5, maxFrames: 100 },
      skipVlm: true,
    },
    captureDir: overrides.captureDir || '/tmp/captures/abc123_test',
    createdAt: overrides.createdAt || '2026-03-01T12:00:00Z',
    updatedAt: overrides.updatedAt || '2026-03-01T12:42:00Z',
  };
  jobs.set(job.runId, job);
  return job;
}

// ---------------------------------------------------------------------------
// GET /pipeline/resumable
// ---------------------------------------------------------------------------
describe('GET /pipeline/resumable', () => {
  it('returns empty array when no failed jobs exist', async () => {
    const res = await request('GET', '/pipeline/resumable');
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, []);
  });

  it('returns failed jobs with captureDir and completedSteps', async () => {
    seedJob({ runId: 'failed-1', status: 'error', step: 'capture', captureDir: '/tmp/cap1' });

    const res = await request('GET', '/pipeline/resumable');
    assert.equal(res.status, 200);
    assert.equal(res.body.length, 1);
    assert.equal(res.body[0].runId, 'failed-1');
    assert.equal(res.body[0].failedStep, 'capture');
    assert.equal(res.body[0].captureDir, '/tmp/cap1');
    assert.ok(Array.isArray(res.body[0].completedSteps));
  });

  it('excludes non-error jobs from resumable list', async () => {
    seedJob({ runId: 'done-1', status: 'done' });
    seedJob({ runId: 'running-1', status: 'running' });
    seedJob({ runId: 'failed-1', status: 'error' });

    const res = await request('GET', '/pipeline/resumable');
    assert.equal(res.status, 200);
    assert.equal(res.body.length, 1);
    assert.equal(res.body[0].runId, 'failed-1');
  });

  it('includes videoId in resumable response', async () => {
    seedJob({ runId: 'failed-v', status: 'error' });

    const res = await request('GET', '/pipeline/resumable');
    assert.equal(res.body[0].videoId, 'abc123');
  });
});

// ---------------------------------------------------------------------------
// POST /pipeline/resume/:runId
// ---------------------------------------------------------------------------
describe('POST /pipeline/resume/:runId', () => {
  it('returns 404 for non-existent runId', async () => {
    const res = await request('POST', '/pipeline/resume/nonexistent');
    assert.equal(res.status, 404);
    assert.ok(res.body.error);
  });

  it('returns 400 when job is not in error state', async () => {
    seedJob({ runId: 'done-job', status: 'done' });

    const res = await request('POST', '/pipeline/resume/done-job');
    assert.equal(res.status, 400);
    assert.ok(res.body.error.includes('not resumable'));
  });

  it('returns 400 when job is still running', async () => {
    seedJob({ runId: 'running-job', status: 'running' });

    const res = await request('POST', '/pipeline/resume/running-job');
    assert.equal(res.status, 400);
    assert.ok(res.body.error.includes('not resumable'));
  });

  it('resets failed job status to queued and returns resumed: true', async () => {
    seedJob({ runId: 'resume-me', status: 'error', error: 'Timeout' });

    const res = await request('POST', '/pipeline/resume/resume-me');
    assert.equal(res.status, 200);
    assert.equal(res.body.resumed, true);
    assert.equal(res.body.runId, 'resume-me');
  });

  it('clears error fields on the resumed job', async () => {
    seedJob({ runId: 'clear-err', status: 'error', error: 'Timeout' });

    await request('POST', '/pipeline/resume/clear-err');

    const job = jobs.get('clear-err');
    assert.equal(job.error, null);
    assert.equal(job.errorDetail, null);
    // Status should be reset (queued or running)
    assert.notEqual(job.status, 'error');
  });
});
