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

function stateFilePath(baseDir, videoId) {
  return path.join(baseDir, `.pipeline_state_${videoId}.json`);
}

/**
 * Scan a directory for per-video state files and return any that are in 'failed' status.
 * Used on server startup to reconstruct resumable jobs from disk.
 */
function scanResumableStates(baseDir) {
  if (!fs.existsSync(baseDir)) return [];
  return fs.readdirSync(baseDir)
    .filter(f => f.startsWith('.pipeline_state_') && f.endsWith('.json'))
    .map(f => {
      try {
        const raw = fs.readFileSync(path.join(baseDir, f), 'utf-8');
        return JSON.parse(raw);
      } catch { return null; }
    })
    .filter(s => {
      if (!s || s.status !== 'failed') return false;
      // Skip states with invalid video IDs (real YouTube IDs are 11 chars)
      if (!s.videoId || s.videoId.length < 8) return false;
      // Skip states older than 7 days
      if (s.updatedAt) {
        const age = Date.now() - new Date(s.updatedAt).getTime();
        if (age > 7 * 24 * 60 * 60 * 1000) return false;
      }
      return true;
    });
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
  scanResumableStates,
};
