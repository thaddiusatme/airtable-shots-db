require('dotenv').config({ path: require('path').resolve(__dirname, '..', '.env') });

const express = require('express');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const { runPipeline } = require('./orchestrator');

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

// --- Routes ---

// Health check (extension uses this to verify server is running)
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Start a pipeline run
app.post('/pipeline/run', (req, res) => {
  const { videoUrl, videoId, videoTitle, transcript, capture } = req.body;

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
    input: { videoUrl, videoId, videoTitle, transcript, capture },
    captureDir: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  jobs.set(runId, job);

  // Run pipeline asynchronously
  const updateStatus = (status, message, step) => {
    job.status = status;
    job.message = message;
    if (step) job.step = step;
    job.updatedAt = new Date().toISOString();
    console.log(`[job:${runId.slice(0, 8)}] ${status}: ${message}${step ? ` (step: ${step})` : ''}`);
  };

  updateStatus('running', 'Pipeline started');

  runPipeline(job, updateStatus)
    .then((result) => {
      job.status = 'done';
      job.message = 'Pipeline complete';
      job.captureDir = result.captureDir;
      job.updatedAt = new Date().toISOString();
      console.log(`[job:${runId.slice(0, 8)}] done`);
    })
    .catch((err) => {
      job.status = 'error';
      const detail = err.stderr ? err.stderr.trim().split('\n').pop() : null;
      job.error = detail || err.message;
      job.errorDetail = err.stderr ? err.stderr.slice(0, 2000) : null;
      job.message = `Failed at step '${job.step}': ${job.error}`;
      job.updatedAt = new Date().toISOString();
      console.error(`[job:${runId.slice(0, 8)}] error at step '${job.step}':`, err.message);
      if (err.stderr) console.error(`  stderr: ${err.stderr.slice(0, 500)}`);
    });

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
