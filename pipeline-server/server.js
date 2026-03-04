require('dotenv').config({ path: require('path').resolve(__dirname, '..', '.env') });

const express = require('express');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const { runPipeline } = require('./orchestrator');
const { scanResumableStates, findExistingFrames } = require('./pipeline-state');

const app = express();
const PORT = process.env.PIPELINE_PORT || 3333;

app.use(cors());
app.use(express.json({ limit: '10mb' }));

const path = require('path');

// Serve dashboard at root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'dashboard.html'));
});

// In-memory job store
const jobs = new Map();

// Shared helper: launch pipeline for a job (used by /run and /resume)
// Wrapped in _internals so tests can override without triggering real pipelines
const _internals = { launchPipeline };
function launchPipeline(job, label = '') {
  const tag = label ? ` (${label})` : '';
  const updateStatus = (status, message, step) => {
    job.status = status;
    job.message = message;
    if (step) job.step = step;
    job.updatedAt = new Date().toISOString();
    console.log(`[job:${job.runId.slice(0, 8)}] ${status}: ${message}${step ? ` (step: ${step})` : ''}`);
  };

  updateStatus('running', `Pipeline started${tag}`);

  runPipeline(job, updateStatus)
    .then((result) => {
      job.status = 'done';
      job.message = `Pipeline complete${tag}`;
      job.captureDir = result.captureDir;
      job.updatedAt = new Date().toISOString();
      console.log(`[job:${job.runId.slice(0, 8)}] done${tag}`);
    })
    .catch((err) => {
      job.status = 'error';
      const detail = err.stderr ? err.stderr.trim().split('\n').pop() : null;
      job.error = detail || err.message;
      job.errorDetail = err.stderr ? err.stderr.slice(0, 2000) : null;
      job.message = `Failed at step '${job.step}': ${job.error}`;
      job.updatedAt = new Date().toISOString();
      console.error(`[job:${job.runId.slice(0, 8)}] error at step '${job.step}':`, err.message);
      if (err.stderr) console.error(`  stderr: ${err.stderr.slice(0, 500)}`);
    });
}

// --- Routes ---

// Health check (extension uses this to verify server is running)
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Start a pipeline run
app.post('/pipeline/run', (req, res) => {
  const { videoUrl, videoId, videoTitle, transcript, transcriptSegments, capture, skipVlm } = req.body;

  if (!videoUrl || !videoId) {
    return res.status(400).json({ error: 'videoUrl and videoId are required' });
  }

  const runId = uuidv4();

  const job = {
    runId,
    status: 'queued',
    step: null,
    message: null,
    error: null,
    errorDetail: null,
    completedSteps: [],
    input: { videoUrl, videoId, videoTitle, transcript, transcriptSegments, capture, skipVlm: !!skipVlm },
    captureDir: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  jobs.set(runId, job);

  _internals.launchPipeline(job);

  res.json({ runId });
});

// Check pipeline status
app.get('/pipeline/status/:runId', (req, res) => {
  const job = jobs.get(req.params.runId);
  if (!job) {
    return res.status(404).json({ error: 'Run not found' });
  }

  res.json({
    runId: job.runId,
    status: job.status,
    step: job.step,
    message: job.message,
    error: job.error,
    errorDetail: job.errorDetail,
    completedSteps: job.completedSteps,
    captureDir: job.captureDir,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
  });
});

// List recent jobs
app.get('/pipeline/jobs', (req, res) => {
  const list = Array.from(jobs.values())
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .slice(0, 20)
    .map(j => ({
      runId: j.runId,
      videoId: j.input.videoId,
      status: j.status,
      message: j.message,
      createdAt: j.createdAt,
    }));
  res.json(list);
});

// List failed jobs that can be resumed (in-memory + disk state files)
app.get('/pipeline/resumable', (req, res) => {
  const PROJECT_ROOT = path.resolve(__dirname, '..');
  const capturesBase = path.join(PROJECT_ROOT, 'captures');

  // In-memory failed jobs
  const memoryResumable = Array.from(jobs.values())
    .filter(j => j.status === 'error')
    .map(j => ({
      runId: j.runId,
      videoId: j.input.videoId,
      failedStep: j.step,
      completedSteps: j.completedSteps,
      captureDir: j.captureDir,
      error: j.error,
      updatedAt: j.updatedAt,
      source: 'memory',
    }));

  // Disk-based failed states (survive server restart)
  const diskStates = scanResumableStates(capturesBase);
  const memoryVideoIds = new Set(memoryResumable.map(j => j.videoId));
  const diskResumable = diskStates
    .filter(s => !memoryVideoIds.has(s.videoId)) // avoid duplicates
    .map(s => {
      const completedSteps = Object.entries(s.stepStates)
        .filter(([, v]) => v.status === 'completed')
        .map(([k]) => k);
      const failedStep = Object.entries(s.stepStates)
        .find(([, v]) => v.status === 'failed');
      return {
        runId: s.runId,
        videoId: s.videoId,
        failedStep: failedStep ? failedStep[0] : null,
        completedSteps,
        captureDir: null,
        error: failedStep ? failedStep[1].error : null,
        updatedAt: s.updatedAt,
        source: 'disk',
      };
    });

  res.json([...memoryResumable, ...diskResumable]);
});

// Resume a failed pipeline run (from memory or reconstructed from disk)
app.post('/pipeline/resume/:runId', (req, res) => {
  let job = jobs.get(req.params.runId);

  // If not in memory, try to reconstruct from disk state
  if (!job) {
    const PROJECT_ROOT = path.resolve(__dirname, '..');
    const capturesBase = path.join(PROJECT_ROOT, 'captures');
    const diskStates = scanResumableStates(capturesBase);
    const diskState = diskStates.find(s => s.runId === req.params.runId);
    if (!diskState) {
      return res.status(404).json({ error: 'Job not found' });
    }

    // Reconstruct job from disk state
    const completedSteps = Object.entries(diskState.stepStates)
      .filter(([, v]) => v.status === 'completed')
      .map(([k]) => k);

    job = {
      runId: diskState.runId,
      status: 'error',
      step: Object.entries(diskState.stepStates).find(([, v]) => v.status === 'failed')?.[0] || null,
      message: null,
      error: null,
      errorDetail: null,
      completedSteps,
      input: {
        videoUrl: `https://www.youtube.com/watch?v=${diskState.videoId}`,
        videoId: diskState.videoId,
        skipVlm: req.body?.skipVlm || false,
        ...(req.body?.transcript && { transcript: req.body.transcript }),
        ...(req.body?.transcriptSegments && { transcriptSegments: req.body.transcriptSegments }),
        capture: req.body?.capture || {},
      },
      captureDir: null,
      createdAt: diskState.createdAt,
      updatedAt: diskState.updatedAt,
    };
    jobs.set(job.runId, job);
    console.log(`[server] Reconstructed job ${job.runId.slice(0, 8)} from disk state for video ${diskState.videoId}`);
  }

  if (job.status !== 'error') {
    return res.status(400).json({ error: 'Job is not resumable (not in error state)' });
  }

  // Reset job status for resumption
  job.status = 'queued';
  job.error = null;
  job.errorDetail = null;
  job.message = 'Resuming pipeline...';
  job.updatedAt = new Date().toISOString();

  console.log(`[job:${job.runId.slice(0, 8)}] resuming from step '${job.step}'`);

  _internals.launchPipeline(job, 'resumed');

  res.json({ resumed: true, runId: job.runId });
});

// Only start listening when run directly (not when imported by tests)
if (require.main === module) {
  const server = app.listen(PORT, '127.0.0.1', () => {
    console.log(`Pipeline server listening on http://127.0.0.1:${PORT}`);
    console.log(`  YT_FRAME_POC_PATH: ${process.env.YT_FRAME_POC_PATH || '(not set!)'}`);
    console.log(`  AIRTABLE_BASE_ID:  ${process.env.AIRTABLE_BASE_ID || '(not set!)'}`);
  });

  // Graceful shutdown — mark running jobs as interrupted
  function handleShutdown(signal) {
    console.log(`\n[server] Received ${signal}, shutting down...`);
    for (const [runId, job] of jobs) {
      if (job.status === 'running' || job.status === 'queued') {
        job.status = 'error';
        job.error = `Server shutdown (${signal}) while pipeline was at step '${job.step}'`;
        job.message = `Interrupted: ${job.error}`;
        job.updatedAt = new Date().toISOString();
        console.log(`[job:${runId.slice(0, 8)}] marked as interrupted at step '${job.step}'`);
      }
    }
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 5000);
  }
  process.on('SIGINT', () => handleShutdown('SIGINT'));
  process.on('SIGTERM', () => handleShutdown('SIGTERM'));
}

module.exports = { app, jobs, _internals };
