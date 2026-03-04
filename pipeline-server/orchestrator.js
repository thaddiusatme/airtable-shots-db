const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const {
  savePipelineState,
  loadPipelineState,
  findExistingFrames,
  calculateStartFrame,
  stateFilePath,
} = require('./pipeline-state');
const { retryWithBackoff, classifyError } = require('./retry');

const PROJECT_ROOT = path.resolve(__dirname, '..');

/**
 * Spawn a child process and return a promise that resolves with stdout/stderr.
 */
function runCommand(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const cwd = opts.cwd || PROJECT_ROOT;
    const env = { ...process.env, ...opts.env };

    console.log(`[orchestrator] $ ${cmd} ${args.join(' ')}  (cwd: ${cwd})`);

    const child = spawn(cmd, args, { cwd, env, shell: true });
    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (d) => {
      const chunk = d.toString();
      stdout += chunk;
      if (opts.onStdout) opts.onStdout(chunk);
    });
    child.stderr.on('data', (d) => {
      const chunk = d.toString();
      stderr += chunk;
      if (opts.onStderr) opts.onStderr(chunk);
    });

    child.on('close', (code) => {
      if (code !== 0) {
        const err = new Error(`Command exited with code ${code}`);
        err.stdout = stdout;
        err.stderr = stderr;
        err.code = code;
        return reject(err);
      }
      resolve({ stdout, stderr });
    });

    child.on('error', reject);
  });
}

/**
 * Find the capture subdirectory created by yt-frame-poc inside the base output dir.
 * yt-frame-poc creates: {baseDir}/{videoId}_{slug}_{datetime}/
 * We find the most recently created directory matching the videoId.
 */
function findCaptureDir(baseDir, videoId) {
  if (!fs.existsSync(baseDir)) return null;
  const entries = fs.readdirSync(baseDir, { withFileTypes: true })
    .filter(e => e.isDirectory() && e.name.startsWith(videoId))
    .map(e => ({
      name: e.name,
      path: path.join(baseDir, e.name),
      mtime: fs.statSync(path.join(baseDir, e.name)).mtimeMs,
    }))
    .sort((a, b) => b.mtime - a.mtime);

  return entries.length > 0 ? entries[0].path : null;
}

/**
 * Upsert a Video record in Airtable with transcript + metadata.
 */
async function upsertVideoTranscript(job) {
  const apiKey = process.env.AIRTABLE_API_KEY;
  const baseId = process.env.AIRTABLE_BASE_ID;

  if (!apiKey || !baseId) {
    throw new Error('Missing AIRTABLE_API_KEY or AIRTABLE_BASE_ID in env');
  }

  const { videoId, videoTitle, videoUrl, transcript, transcriptSegments } = job.input;

  // Search for existing video
  const findUrl = `https://api.airtable.com/v0/${baseId}/Videos?filterByFormula=` +
    encodeURIComponent(`{Video ID}='${videoId}'`);

  const findRes = await fetch(findUrl, {
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
  });

  if (!findRes.ok) {
    throw new Error(`Airtable lookup failed: ${await findRes.text()}`);
  }

  const findResult = await findRes.json();

  const thumbnailUrl = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;

  if (findResult.records.length === 0) {
    // Create new video record
    const fields = {
      'Video Title': videoTitle,
      'Video ID': videoId,
      'Platform': 'YouTube',
      'Video URL': videoUrl,
      'Triage Status': 'Queued',
      'Thumbnail URL': thumbnailUrl,
      'Thumbnail (Image)': [{ url: thumbnailUrl }],
      'Transcript (Full)': transcript,
    };
    
    // Add timestamped transcript if available
    if (transcriptSegments && transcriptSegments.length > 0) {
      fields['Transcript (Timestamped)'] = JSON.stringify(transcriptSegments);
    }
    
    const createRes = await fetch(`https://api.airtable.com/v0/${baseId}/Videos`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields }),
    });

    if (!createRes.ok) {
      throw new Error(`Airtable create failed: ${await createRes.text()}`);
    }
    const created = await createRes.json();
    console.log(`[orchestrator] Created Video record: ${created.id}`);
    return created.id;
  } else {
    // Update existing record with transcript
    const recordId = findResult.records[0].id;
    const fields = {
      'Transcript (Full)': transcript,
    };
    
    // Add timestamped transcript if available
    if (transcriptSegments && transcriptSegments.length > 0) {
      fields['Transcript (Timestamped)'] = JSON.stringify(transcriptSegments);
    }
    
    const updateRes = await fetch(`https://api.airtable.com/v0/${baseId}/Videos/${recordId}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields }),
    });

    if (!updateRes.ok) {
      throw new Error(`Airtable update failed: ${await updateRes.text()}`);
    }
    console.log(`[orchestrator] Updated Video record: ${recordId}`);
    return recordId;
  }
}

/**
 * Run the full pipeline:
 *   1. Upsert Video transcript in Airtable
 *   2. Capture frames via yt-frame-poc
 *   3. Analyze scenes via Python analyzer
 *   4. Publish shots via Python publisher
 */
async function runPipeline(job, updateStatus) {
  const { videoUrl, videoId, capture } = job.input;
  const ytFramePocPath = process.env.YT_FRAME_POC_PATH;
  const capturesBase = path.join(PROJECT_ROOT, 'captures');
  const pythonBin = path.join(PROJECT_ROOT, '.venv', 'bin', 'python');

  if (!ytFramePocPath) {
    throw new Error('YT_FRAME_POC_PATH env var not set');
  }

  if (!fs.existsSync(ytFramePocPath)) {
    throw new Error(`yt-frame-poc not found at: ${ytFramePocPath}`);
  }

  fs.mkdirSync(capturesBase, { recursive: true });

  // Load or create pipeline state for resumption (per-video state file)
  const stateFile = stateFilePath(capturesBase, videoId);
  const state = loadPipelineState(stateFile, job.runId);
  state.videoId = videoId;
  job.completedSteps = job.completedSteps || [];

  console.log(`[orchestrator] Pipeline state loaded (status: ${state.status}, runId: ${state.runId})`);

  // --- Step 1: Upsert Video transcript ---
  if (state.stepStates.upsert_video.status === 'completed') {
    console.log('[orchestrator] Skipping upsert_video (already completed)');
    if (!job.completedSteps.includes('upsert_video')) job.completedSteps.push('upsert_video');
  } else {
    updateStatus('running', 'Saving transcript to Airtable...', 'upsert_video');
    state.stepStates.upsert_video.status = 'running';
    state.stepStates.upsert_video.startedAt = new Date().toISOString();
    savePipelineState(stateFile, state);

    try {
      await upsertVideoTranscript(job);
      state.stepStates.upsert_video.status = 'completed';
      state.stepStates.upsert_video.completedAt = new Date().toISOString();
      savePipelineState(stateFile, state);
      job.completedSteps.push('upsert_video');
    } catch (err) {
      state.stepStates.upsert_video.status = 'failed';
      state.stepStates.upsert_video.error = err.message;
      state.status = 'failed';
      savePipelineState(stateFile, state);
      throw err;
    }
  }

  // --- Step 2: Capture frames ---
  let captureDir;
  if (state.stepStates.capture.status === 'completed') {
    console.log('[orchestrator] Skipping capture (already completed)');
    captureDir = job.captureDir || findCaptureDir(capturesBase, videoId);
    if (!job.completedSteps.includes('capture')) job.completedSteps.push('capture');
  } else {
    // Check for existing frames from a previous (possibly failed) run
    const existingCaptureDir = findCaptureDir(capturesBase, videoId);
    const existingFrames = existingCaptureDir ? findExistingFrames(existingCaptureDir) : [];

    if (existingFrames.length > 0) {
      // Reuse existing capture directory — yt-frame-poc doesn't support --start-frame
      // and always creates a new timestamped dir, so we skip re-capture entirely
      captureDir = existingCaptureDir;
      job.captureDir = captureDir;
      console.log(`[orchestrator] Reusing existing capture dir with ${existingFrames.length} frames: ${captureDir}`);
      updateStatus('running', `Reusing ${existingFrames.length} existing frames (skipping capture)`, 'capture');

      state.stepStates.capture.status = 'completed';
      state.stepStates.capture.completedAt = new Date().toISOString();
      state.stepStates.capture.framesCompleted = existingFrames.length;
      state.stepStates.capture.lastFrame = existingFrames[existingFrames.length - 1] || null;
      state.stepStates.capture.reused = true;
      savePipelineState(stateFile, state);
      job.completedSteps.push('capture');
    } else {
      // No existing frames — run fresh capture
      updateStatus('running', 'Capturing frames via Playwright...', 'capture');

      state.stepStates.capture.status = 'running';
      state.stepStates.capture.startedAt = new Date().toISOString();
      savePipelineState(stateFile, state);

      const interval = capture?.interval || 1;
      const captureArgs = [
        'src/index.ts',
        `"${videoUrl}"`,
        String(interval),
        '--output', capturesBase,
      ];
      if (capture?.start !== undefined) captureArgs.push('--start', String(capture.start));
      if (capture?.end !== undefined) captureArgs.push('--end', String(capture.end));
      if (capture?.maxFrames !== undefined) captureArgs.push('--max-frames', String(capture.maxFrames));

      try {
        await retryWithBackoff(
          () => runCommand('npx', ['ts-node', ...captureArgs], {
            cwd: ytFramePocPath,
            onStdout: (chunk) => console.log(`[capture] ${chunk.trimEnd()}`),
            onStderr: (chunk) => console.error(`[capture] ${chunk.trimEnd()}`),
          }),
          {
            maxRetries: 2,
            baseDelayMs: 5000,
            maxDelayMs: 30000,
            onRetry: (attempt, err, delayMs) => {
              const kind = classifyError(err);
              console.log(`[orchestrator] Capture attempt failed (${kind}): ${err.message}`);
              console.log(`[orchestrator] Retrying in ${(delayMs / 1000).toFixed(0)}s (attempt ${attempt}/2)...`);
              updateStatus('running', `Capture failed (${kind}), retrying in ${(delayMs / 1000).toFixed(0)}s... (attempt ${attempt + 1}/3)`, 'capture');
            },
          }
        );
      } catch (err) {
        // Save partial progress before re-throwing
        const partialDir = findCaptureDir(capturesBase, videoId);
        const partialFrames = partialDir ? findExistingFrames(partialDir) : [];
        state.stepStates.capture.status = 'failed';
        state.stepStates.capture.failedAt = new Date().toISOString();
        state.stepStates.capture.error = err.message;
        state.stepStates.capture.errorType = classifyError(err);
        state.stepStates.capture.framesCompleted = partialFrames.length;
        state.stepStates.capture.lastFrame = partialFrames[partialFrames.length - 1] || null;
        state.status = 'failed';
        savePipelineState(stateFile, state);
        throw err;
      }

      captureDir = findCaptureDir(capturesBase, videoId);
      if (!captureDir) {
        throw new Error(`Capture directory not found in ${capturesBase} for ${videoId}`);
      }
      job.captureDir = captureDir;

      const finalFrames = findExistingFrames(captureDir);
      state.stepStates.capture.status = 'completed';
      state.stepStates.capture.completedAt = new Date().toISOString();
      state.stepStates.capture.framesCompleted = finalFrames.length;
      state.stepStates.capture.lastFrame = finalFrames[finalFrames.length - 1] || null;
      savePipelineState(stateFile, state);
      job.completedSteps.push('capture');
      console.log(`[orchestrator] Capture dir: ${captureDir} (${finalFrames.length} frames)`);
    }
  }

  // --- Step 3: Analyze scenes ---
  if (state.stepStates.analyze.status === 'completed') {
    console.log('[orchestrator] Skipping analyze (already completed)');
    if (!job.completedSteps.includes('analyze')) job.completedSteps.push('analyze');
  } else {
    const analyzerArgs = [
      '-m', 'analyzer',
      '--capture-dir', captureDir,
      '--threshold', '10.0',
      '--verbose',
    ];
    
    if (job.input.skipVlm) {
      analyzerArgs.push('--skip-vlm');
      updateStatus('running', 'Analyzing scenes (OpenCV only, VLM skipped)...', 'analyze');
    } else {
      updateStatus('running', 'Analyzing scenes (OpenCV + VLM)...', 'analyze');
    }

    state.stepStates.analyze.status = 'running';
    state.stepStates.analyze.startedAt = new Date().toISOString();
    savePipelineState(stateFile, state);

    try {
      await runCommand(pythonBin, analyzerArgs, {
        cwd: PROJECT_ROOT,
        onStdout: (chunk) => console.log(`[analyzer] ${chunk.trimEnd()}`),
        onStderr: (chunk) => console.error(`[analyzer] ${chunk.trimEnd()}`),
      });
      state.stepStates.analyze.status = 'completed';
      state.stepStates.analyze.completedAt = new Date().toISOString();
      savePipelineState(stateFile, state);
      job.completedSteps.push('analyze');
    } catch (err) {
      state.stepStates.analyze.status = 'failed';
      state.stepStates.analyze.error = err.message;
      state.status = 'failed';
      savePipelineState(stateFile, state);
      throw err;
    }
  }

  // --- Step 4: Publish to Airtable + R2 ---
  if (state.stepStates.publish.status === 'completed') {
    console.log('[orchestrator] Skipping publish (already completed)');
    if (!job.completedSteps.includes('publish')) job.completedSteps.push('publish');
  } else {
    const hasR2 = process.env.R2_ACCOUNT_ID && process.env.R2_ACCESS_KEY_ID;
    const statusMsg = hasR2 
      ? 'Publishing shots + frames to Airtable + R2...' 
      : 'Publishing shots to Airtable...';
    updateStatus('running', statusMsg, 'publish');

    state.stepStates.publish.status = 'running';
    state.stepStates.publish.startedAt = new Date().toISOString();
    savePipelineState(stateFile, state);

    try {
      const publisherArgs = [
        '-m', 'publisher',
        '--capture-dir', captureDir,
        '--api-key', process.env.AIRTABLE_API_KEY,
        '--base-id', process.env.AIRTABLE_BASE_ID,
        '--segment-transcripts',
        '--merge-scenes',
        '--verbose',
      ];

      // Enable parallel frame uploads if R2 is configured
      if (hasR2) {
        publisherArgs.push('--max-concurrent-uploads', '8');
      }

      await runCommand(pythonBin, publisherArgs, {
        cwd: PROJECT_ROOT,
        onStdout: (chunk) => console.log(`[publisher] ${chunk.trimEnd()}`),
        onStderr: (chunk) => console.error(`[publisher] ${chunk.trimEnd()}`),
      });
      state.stepStates.publish.status = 'completed';
      state.stepStates.publish.completedAt = new Date().toISOString();
      savePipelineState(stateFile, state);
      job.completedSteps.push('publish');
    } catch (err) {
      state.stepStates.publish.status = 'failed';
      state.stepStates.publish.error = err.message;
      state.status = 'failed';
      savePipelineState(stateFile, state);
      throw err;
    }
  }

  // Mark overall pipeline as completed
  state.status = 'completed';
  savePipelineState(stateFile, state);

  return { captureDir };
}

module.exports = { runPipeline };
