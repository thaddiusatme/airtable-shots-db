const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

const {
  savePipelineState,
  loadPipelineState,
  findExistingFrames,
  calculateStartFrame,
  INITIAL_PIPELINE_STATE,
} = require('../pipeline-state');

// Each test gets a fresh temp directory
let tmpDir;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pipeline-state-test-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// savePipelineState
// ---------------------------------------------------------------------------
describe('savePipelineState', () => {
  it('creates .pipeline_state.json with correct schema', () => {
    const stateFile = path.join(tmpDir, '.pipeline_state.json');
    const state = {
      runId: 'test-run-001',
      videoId: 'abc123',
      status: 'running',
      stepStates: {
        upsert_video: { status: 'not_started' },
        capture: { status: 'not_started' },
        analyze: { status: 'not_started' },
        publish: { status: 'not_started' },
      },
      createdAt: '2026-03-01T12:00:00Z',
      updatedAt: '2026-03-01T12:00:00Z',
    };

    savePipelineState(stateFile, state);

    assert.ok(fs.existsSync(stateFile), 'State file should exist after save');
    const written = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
    assert.equal(written.runId, 'test-run-001');
    assert.equal(written.videoId, 'abc123');
    assert.equal(written.status, 'running');
    assert.equal(written.stepStates.capture.status, 'not_started');
  });

  it('overwrites existing state file on subsequent saves', () => {
    const stateFile = path.join(tmpDir, '.pipeline_state.json');
    const state1 = {
      runId: 'run-1',
      videoId: 'v1',
      status: 'running',
      stepStates: { upsert_video: { status: 'completed' }, capture: { status: 'not_started' }, analyze: { status: 'not_started' }, publish: { status: 'not_started' } },
      createdAt: '2026-03-01T12:00:00Z',
      updatedAt: '2026-03-01T12:00:00Z',
    };
    savePipelineState(stateFile, state1);

    const state2 = { ...state1, status: 'failed' };
    savePipelineState(stateFile, state2);

    const written = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
    assert.equal(written.status, 'failed');
    // updatedAt should be auto-refreshed by savePipelineState, not the original value
    assert.notEqual(written.updatedAt, '2026-03-01T12:00:00Z');
  });

  it('updates updatedAt timestamp on save', () => {
    const stateFile = path.join(tmpDir, '.pipeline_state.json');
    const state = {
      runId: 'run-ts',
      videoId: 'v1',
      status: 'running',
      stepStates: { upsert_video: { status: 'not_started' }, capture: { status: 'not_started' }, analyze: { status: 'not_started' }, publish: { status: 'not_started' } },
      createdAt: '2026-03-01T12:00:00Z',
      updatedAt: '2026-03-01T12:00:00Z',
    };

    savePipelineState(stateFile, state);

    const written = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
    // updatedAt should be refreshed to current time, not the original value
    assert.notEqual(written.updatedAt, '2026-03-01T12:00:00Z');
  });
});

// ---------------------------------------------------------------------------
// loadPipelineState
// ---------------------------------------------------------------------------
describe('loadPipelineState', () => {
  it('returns parsed state from existing file', () => {
    const stateFile = path.join(tmpDir, '.pipeline_state.json');
    const expected = {
      runId: 'existing-run',
      videoId: 'vid1',
      status: 'failed',
      stepStates: {
        upsert_video: { status: 'completed' },
        capture: { status: 'failed', framesCompleted: 672 },
        analyze: { status: 'not_started' },
        publish: { status: 'not_started' },
      },
      createdAt: '2026-03-01T12:00:00Z',
      updatedAt: '2026-03-01T12:42:00Z',
    };
    fs.writeFileSync(stateFile, JSON.stringify(expected));

    const loaded = loadPipelineState(stateFile, 'existing-run');

    assert.equal(loaded.runId, 'existing-run');
    assert.equal(loaded.stepStates.capture.framesCompleted, 672);
  });

  it('returns initial state when file does not exist', () => {
    const stateFile = path.join(tmpDir, 'nonexistent.json');
    const loaded = loadPipelineState(stateFile, 'new-run');

    assert.equal(loaded.runId, 'new-run');
    assert.equal(loaded.status, 'running');
    assert.equal(loaded.stepStates.upsert_video.status, 'not_started');
    assert.equal(loaded.stepStates.capture.status, 'not_started');
    assert.equal(loaded.stepStates.analyze.status, 'not_started');
    assert.equal(loaded.stepStates.publish.status, 'not_started');
  });

  it('returns initial state when file contains invalid JSON', () => {
    const stateFile = path.join(tmpDir, 'corrupt.json');
    fs.writeFileSync(stateFile, '{ broken json!!!');

    const loaded = loadPipelineState(stateFile, 'recovery-run');

    assert.equal(loaded.runId, 'recovery-run');
    assert.equal(loaded.status, 'running');
    assert.equal(loaded.stepStates.upsert_video.status, 'not_started');
  });
});

// ---------------------------------------------------------------------------
// findExistingFrames
// ---------------------------------------------------------------------------
describe('findExistingFrames', () => {
  it('returns array of PNG filenames in captureDir', () => {
    // Create fake frame files
    fs.writeFileSync(path.join(tmpDir, 'frame_00000_t000.000s.png'), '');
    fs.writeFileSync(path.join(tmpDir, 'frame_00001_t001.000s.png'), '');
    fs.writeFileSync(path.join(tmpDir, 'frame_00002_t002.000s.png'), '');
    // Non-frame files should be excluded
    fs.writeFileSync(path.join(tmpDir, 'manifest.json'), '{}');
    fs.writeFileSync(path.join(tmpDir, '.pipeline_state.json'), '{}');

    const frames = findExistingFrames(tmpDir);

    assert.equal(frames.length, 3);
    assert.ok(frames.every(f => f.endsWith('.png')));
    assert.ok(frames.includes('frame_00000_t000.000s.png'));
    assert.ok(frames.includes('frame_00002_t002.000s.png'));
  });

  it('returns empty array for empty directory', () => {
    const frames = findExistingFrames(tmpDir);
    assert.deepEqual(frames, []);
  });

  it('returns empty array for non-existent directory', () => {
    const frames = findExistingFrames(path.join(tmpDir, 'does-not-exist'));
    assert.deepEqual(frames, []);
  });

  it('returns sorted array of frame filenames', () => {
    fs.writeFileSync(path.join(tmpDir, 'frame_00002_t002.000s.png'), '');
    fs.writeFileSync(path.join(tmpDir, 'frame_00000_t000.000s.png'), '');
    fs.writeFileSync(path.join(tmpDir, 'frame_00001_t001.000s.png'), '');

    const frames = findExistingFrames(tmpDir);

    assert.equal(frames[0], 'frame_00000_t000.000s.png');
    assert.equal(frames[1], 'frame_00001_t001.000s.png');
    assert.equal(frames[2], 'frame_00002_t002.000s.png');
  });
});

// ---------------------------------------------------------------------------
// calculateStartFrame
// ---------------------------------------------------------------------------
describe('calculateStartFrame', () => {
  it('returns 0 when no existing frames', () => {
    const start = calculateStartFrame([]);
    assert.equal(start, 0);
  });

  it('returns count of existing frames (next frame index)', () => {
    const frames = [
      'frame_00000_t000.000s.png',
      'frame_00001_t001.000s.png',
      'frame_00002_t002.000s.png',
    ];
    const start = calculateStartFrame(frames);
    assert.equal(start, 3);
  });

  it('handles large frame counts correctly', () => {
    // Simulate 672 existing frames
    const frames = Array.from({ length: 672 }, (_, i) => {
      const idx = String(i).padStart(5, '0');
      return `frame_${idx}_t${idx}.000s.png`;
    });
    const start = calculateStartFrame(frames);
    assert.equal(start, 672);
  });
});

// ---------------------------------------------------------------------------
// INITIAL_PIPELINE_STATE
// ---------------------------------------------------------------------------
describe('INITIAL_PIPELINE_STATE', () => {
  it('has all required step keys', () => {
    assert.ok(INITIAL_PIPELINE_STATE.stepStates);
    assert.ok('upsert_video' in INITIAL_PIPELINE_STATE.stepStates);
    assert.ok('capture' in INITIAL_PIPELINE_STATE.stepStates);
    assert.ok('analyze' in INITIAL_PIPELINE_STATE.stepStates);
    assert.ok('publish' in INITIAL_PIPELINE_STATE.stepStates);
  });

  it('all steps start as not_started', () => {
    for (const step of Object.values(INITIAL_PIPELINE_STATE.stepStates)) {
      assert.equal(step.status, 'not_started');
    }
  });
});
