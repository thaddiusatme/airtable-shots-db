/**
 * Pipeline state persistence helpers for checkpoint-based resumption.
 * Implements save/load of .pipeline_state.json and frame detection.
 */

const fs = require('fs');
const path = require('path');

const STATE_FILENAME = '.pipeline_state.json';

const INITIAL_PIPELINE_STATE = {
  runId: null,
  videoId: null,
  status: 'running',
  stepStates: {
    upsert_video: { status: 'not_started' },
    capture: { status: 'not_started' },
    analyze: { status: 'not_started' },
    publish: { status: 'not_started' },
  },
  createdAt: null,
  updatedAt: null,
};

function savePipelineState(stateFile, state) {
  state.updatedAt = new Date().toISOString();
  fs.writeFileSync(stateFile, JSON.stringify(state, null, 2));
}

function createInitialState(runId) {
  const now = new Date().toISOString();
  return {
    ...JSON.parse(JSON.stringify(INITIAL_PIPELINE_STATE)),
    runId,
    createdAt: now,
    updatedAt: now,
  };
}

function stateFilePath(captureDir) {
  return path.join(captureDir, STATE_FILENAME);
}

function loadPipelineState(stateFile, runId) {
  if (!fs.existsSync(stateFile)) {
    return createInitialState(runId);
  }

  try {
    const raw = fs.readFileSync(stateFile, 'utf-8');
    return JSON.parse(raw);
  } catch (err) {
    console.warn(`[pipeline-state] Corrupted state file, resetting: ${err.message}`);
    return createInitialState(runId);
  }
}

function findExistingFrames(captureDir) {
  if (!fs.existsSync(captureDir)) return [];
  return fs.readdirSync(captureDir)
    .filter(f => f.endsWith('.png'))
    .sort();
}

function calculateStartFrame(existingFrames) {
  return existingFrames.length;
}

module.exports = {
  STATE_FILENAME,
  INITIAL_PIPELINE_STATE,
  createInitialState,
  stateFilePath,
  savePipelineState,
  loadPipelineState,
  findExistingFrames,
  calculateStartFrame,
};
