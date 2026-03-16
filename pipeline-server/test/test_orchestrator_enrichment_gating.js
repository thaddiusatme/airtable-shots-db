const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const childProcess = require('child_process');
const fs = require('fs');
const pipelineState = require('../pipeline-state');
const retry = require('../retry');

const originalSpawn = childProcess.spawn;
const originalExistsSync = fs.existsSync;
const originalMkdirSync = fs.mkdirSync;
const originalLoadPipelineState = pipelineState.loadPipelineState;
const originalSavePipelineState = pipelineState.savePipelineState;
const originalStateFilePath = pipelineState.stateFilePath;
const originalFindExistingFrames = pipelineState.findExistingFrames;
const originalRetryWithBackoff = retry.retryWithBackoff;
const originalClassifyError = retry.classifyError;
const originalFetch = global.fetch;

let spawnCalls;
let savedStates;
let statusUpdates;

function makeCompletedStepState(runId, videoId) {
  return {
    runId,
    videoId,
    status: 'running',
    stepStates: {
      upsert_video: { status: 'completed' },
      capture: { status: 'completed' },
      analyze: { status: 'completed' },
      publish: { status: 'not_started' },
    },
    createdAt: '2026-03-13T00:00:00.000Z',
    updatedAt: '2026-03-13T00:00:00.000Z',
  };
}

function makeJob(inputOverrides = {}) {
  return {
    runId: 'run-123',
    completedSteps: ['upsert_video', 'capture', 'analyze'],
    captureDir: '/tmp/capture-dir',
    input: {
      videoUrl: 'https://www.youtube.com/watch?v=abc123xyz00',
      videoId: 'abc123xyz00',
      capture: { interval: 5, maxFrames: 100 },
      ...inputOverrides,
    },
  };
}

beforeEach(() => {
  spawnCalls = [];
  savedStates = [];
  statusUpdates = [];

  process.env.YT_FRAME_POC_PATH = '/tmp/yt-frame-poc';
  process.env.AIRTABLE_API_KEY = 'key123';
  process.env.AIRTABLE_BASE_ID = 'base123';
  delete process.env.R2_ACCOUNT_ID;
  delete process.env.R2_ACCESS_KEY_ID;

  childProcess.spawn = (cmd, args) => {
    spawnCalls.push({ cmd, args });
    const handlers = {};
    const stream = { on: () => {} };
    const child = {
      stdout: stream,
      stderr: stream,
      on: (event, handler) => {
        handlers[event] = handler;
        if (event === 'close') {
          process.nextTick(() => handler(0));
        }
      },
    };
    return child;
  };

  fs.existsSync = () => true;
  fs.mkdirSync = () => {};

  pipelineState.loadPipelineState = (stateFile, runId) => makeCompletedStepState(runId, 'abc123xyz00');
  pipelineState.savePipelineState = (stateFile, state) => {
    savedStates.push(JSON.parse(JSON.stringify(state)));
  };
  pipelineState.stateFilePath = () => '/tmp/pipeline-state.json';
  pipelineState.findExistingFrames = () => ['frame_0001.png'];

  retry.retryWithBackoff = async (fn) => fn();
  retry.classifyError = () => 'unknown';

  global.fetch = async () => {
    throw new Error('fetch should not be called in publish-step tests');
  };

  delete require.cache[require.resolve('../orchestrator')];
});

afterEach(() => {
  childProcess.spawn = originalSpawn;
  fs.existsSync = originalExistsSync;
  fs.mkdirSync = originalMkdirSync;
  pipelineState.loadPipelineState = originalLoadPipelineState;
  pipelineState.savePipelineState = originalSavePipelineState;
  pipelineState.stateFilePath = originalStateFilePath;
  pipelineState.findExistingFrames = originalFindExistingFrames;
  retry.retryWithBackoff = originalRetryWithBackoff;
  retry.classifyError = originalClassifyError;
  global.fetch = originalFetch;
  delete require.cache[require.resolve('../orchestrator')];
});

describe('runPipeline publish enrichment gating', () => {
  it('does not append enrichment flags or enrichment status text when enrichShots is disabled', async () => {
    const { runPipeline } = require('../orchestrator');
    const job = makeJob({ enrichShots: false, enrichModel: 'qwen2.5-vl:latest', forceReenrich: true });

    await runPipeline(job, (status, message, step) => {
      statusUpdates.push({ status, message, step });
    });

    const publishCall = spawnCalls.at(-1);
    assert.deepEqual(publishCall.args, [
      '-m', 'publisher',
      '--capture-dir', '/tmp/capture-dir',
      '--api-key', 'key123',
      '--base-id', 'base123',
      '--segment-transcripts',
      '--merge-scenes',
      '--verbose',
    ]);

    const publishStatus = statusUpdates.find((update) => update.step === 'publish');
    assert.equal(publishStatus.message, 'Publishing shots to Airtable...');
  });

  it('appends enrich flags and enrichment status text when enrichShots is enabled', async () => {
    const { runPipeline } = require('../orchestrator');
    const job = makeJob({ enrichShots: true, enrichModel: 'qwen2.5-vl:latest' });

    await runPipeline(job, (status, message, step) => {
      statusUpdates.push({ status, message, step });
    });

    const publishCall = spawnCalls.at(-1);
    assert.deepEqual(publishCall.args, [
      '-m', 'publisher',
      '--capture-dir', '/tmp/capture-dir',
      '--api-key', 'key123',
      '--base-id', 'base123',
      '--segment-transcripts',
      '--merge-scenes',
      '--verbose',
      '--enrich-shots',
      '--enrich-provider', 'ollama',
      '--enrich-model', 'qwen2.5-vl:latest',
    ]);

    const publishStatus = statusUpdates.find((update) => update.step === 'publish');
    assert.equal(publishStatus.message, 'Publishing shots to Airtable with AI enrichment (ollama/qwen2.5-vl:latest)...');
  });

  it('adds force re-enrich only when enrichment is enabled', async () => {
    const { runPipeline } = require('../orchestrator');
    const job = makeJob({ enrichShots: true, enrichModel: 'qwen2.5-vl:latest', forceReenrich: true });

    await runPipeline(job, (status, message, step) => {
      statusUpdates.push({ status, message, step });
    });

    const publishCall = spawnCalls.at(-1);
    assert.deepEqual(publishCall.args.slice(-6), [
      '--enrich-shots',
      '--enrich-provider', 'ollama',
      '--enrich-model', 'qwen2.5-vl:latest',
      '--force-reenrich',
    ]);

    const publishStatus = statusUpdates.find((update) => update.step === 'publish');
    assert.equal(publishStatus.message, 'Publishing shots to Airtable with AI enrichment (ollama/qwen2.5-vl:latest, force re-enrich)...');
  });

  it('passes gemini provider through to publisher args and status text', async () => {
    const { runPipeline } = require('../orchestrator');
    const job = makeJob({
      enrichShots: true,
      enrichProvider: 'gemini',
      enrichModel: 'gemini-2.5-flash',
    });

    await runPipeline(job, (status, message, step) => {
      statusUpdates.push({ status, message, step });
    });

    const publishCall = spawnCalls.at(-1);
    assert.deepEqual(publishCall.args, [
      '-m', 'publisher',
      '--capture-dir', '/tmp/capture-dir',
      '--api-key', 'key123',
      '--base-id', 'base123',
      '--segment-transcripts',
      '--merge-scenes',
      '--verbose',
      '--enrich-shots',
      '--enrich-provider', 'gemini',
      '--enrich-model', 'gemini-2.5-flash',
    ]);

    const publishStatus = statusUpdates.find((update) => update.step === 'publish');
    assert.equal(publishStatus.message, 'Publishing shots to Airtable with AI enrichment (gemini/gemini-2.5-flash)...');
  });
});
