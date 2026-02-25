const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

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

  const { videoId, videoTitle, videoUrl, transcript } = job.input;

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
    const createRes = await fetch(`https://api.airtable.com/v0/${baseId}/Videos`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fields: {
          'Video Title': videoTitle,
          'Video ID': videoId,
          'Platform': 'YouTube',
          'Video URL': videoUrl,
          'Triage Status': 'Queued',
          'Thumbnail URL': thumbnailUrl,
          'Thumbnail (Image)': [{ url: thumbnailUrl }],
          'Transcript (Full)': transcript,
        },
      }),
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
    const updateRes = await fetch(`https://api.airtable.com/v0/${baseId}/Videos/${recordId}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fields: {
          'Transcript (Full)': transcript,
        },
      }),
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

  // Step 1: Upsert Video transcript
  updateStatus('running', 'Saving transcript to Airtable...', 'upsert_video');
  await upsertVideoTranscript(job);
  job.completedSteps = job.completedSteps || [];
  job.completedSteps.push('upsert_video');

  // Step 2: Capture frames
  updateStatus('running', 'Capturing frames via Playwright...', 'capture');
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

  await runCommand('npx', ['ts-node', ...captureArgs], {
    cwd: ytFramePocPath,
    onStdout: (chunk) => console.log(`[capture] ${chunk.trimEnd()}`),
    onStderr: (chunk) => console.error(`[capture] ${chunk.trimEnd()}`),
  });

  // Find the capture directory
  const captureDir = findCaptureDir(capturesBase, videoId);
  if (!captureDir) {
    throw new Error(`Capture directory not found in ${capturesBase} for ${videoId}`);
  }
  job.captureDir = captureDir;
  job.completedSteps.push('capture');
  console.log(`[orchestrator] Capture dir: ${captureDir}`);

  // Step 3: Analyze scenes
  updateStatus('running', 'Analyzing scenes (OpenCV + VLM)...', 'analyze');
  await runCommand(pythonBin, [
    '-m', 'analyzer',
    '--capture-dir', captureDir,
    '--threshold', '10.0',
    '--verbose',
  ], {
    cwd: PROJECT_ROOT,
    onStdout: (chunk) => console.log(`[analyzer] ${chunk.trimEnd()}`),
    onStderr: (chunk) => console.error(`[analyzer] ${chunk.trimEnd()}`),
  });

  job.completedSteps.push('analyze');

  // Step 4: Publish to Airtable + R2
  updateStatus('running', 'Publishing shots to Airtable + R2...', 'publish');
  await runCommand(pythonBin, [
    '-m', 'publisher',
    '--capture-dir', captureDir,
    '--api-key', process.env.AIRTABLE_API_KEY,
    '--base-id', process.env.AIRTABLE_BASE_ID,
    '--verbose',
  ], {
    cwd: PROJECT_ROOT,
    onStdout: (chunk) => console.log(`[publisher] ${chunk.trimEnd()}`),
    onStderr: (chunk) => console.error(`[publisher] ${chunk.trimEnd()}`),
  });

  return { captureDir };
}

module.exports = { runPipeline };
