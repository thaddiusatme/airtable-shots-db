// Popup script - handles UI interactions and saves to Airtable

let currentTranscriptData = null;
let isCapturing = false;
let captureFolder = '';
let pipelineRunId = null;
let pipelinePollTimer = null;
let pollFailCount = 0;

const PIPELINE_SERVER = 'http://127.0.0.1:3333';

// DOM elements — Transcript
const statusMessage = document.getElementById('statusMessage');
const videoInfo = document.getElementById('videoInfo');
const videoTitle = document.getElementById('videoTitle');
const videoId = document.getElementById('videoId');
const transcriptPreview = document.getElementById('transcriptPreview');
const extractBtn = document.getElementById('extractBtn');
const saveBtn = document.getElementById('saveBtn');
const settingsLink = document.getElementById('settingsLink');

// DOM elements — Pipeline
const runPipelineBtn = document.getElementById('runPipelineBtn');
const pipelineIntervalInput = document.getElementById('pipelineInterval');
const pipelineMaxFramesInput = document.getElementById('pipelineMaxFrames');
const enrichShotsCheckbox = document.getElementById('enrichShotsCheckbox');
const enrichProviderSelect = document.getElementById('enrichProviderSelect');
const enrichModelInput = document.getElementById('enrichModelInput');
const forceReenrichCheckbox = document.getElementById('forceReenrichCheckbox');
const pipelineStatusDiv = document.getElementById('pipelineStatus');
const pipelineStepSpan = document.getElementById('pipelineStep');
const serverOfflineDiv = document.getElementById('serverOffline');
const resumeSection = document.getElementById('resumeSection');
const resumePipelineBtn = document.getElementById('resumePipelineBtn');
const resumeInfo = document.getElementById('resumeInfo');

const DEFAULT_ENRICHMENT_MODELS = {
  ollama: 'qwen2.5-vl:latest',
  gemini: 'gemini-2.5-flash',
};

// DOM elements — Capture (Legacy)
const captureIntervalInput = document.getElementById('captureInterval');
const captureMaxInput = document.getElementById('captureMax');
const captureStatusDiv = document.getElementById('captureStatus');
const captureCountSpan = document.getElementById('captureCount');
const captureTotalSpan = document.getElementById('captureTotal');
const startCaptureBtn = document.getElementById('startCaptureBtn');
const stopCaptureBtn = document.getElementById('stopCaptureBtn');
const openFolderLinkDiv = document.getElementById('openFolderLink');
const openFolderAnchor = document.getElementById('openFolder');

// Show status message
function showStatus(message, type = 'info') {
  statusMessage.textContent = message;
  statusMessage.className = `status ${type}`;
}

// Show success message
function showSuccess(message) {
  showStatus(message, 'success');
}

// Show error message
function showError(message) {
  showStatus(message, 'error');
}

// Extract transcript from current YouTube page
async function extractTranscript() {
  showStatus('Extracting transcript...', 'info');
  extractBtn.disabled = true;
  
  try {
    // Get current active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab.url?.includes('youtube.com/watch')) {
      showError('Please navigate to a YouTube video page first');
      extractBtn.disabled = false;
      return;
    }
    
    // Send message to content script with error handling
    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { action: 'extractTranscript' });
    } catch (msgError) {
      // Content script not loaded yet - try to inject it
      console.log('Content script not ready, reloading page may help');
      showError('Content script not loaded. Please reload the YouTube page and try again.');
      extractBtn.disabled = false;
      return;
    }
    
    if (response.error) {
      showError(response.error);
      extractBtn.disabled = false;
      return;
    }
    
    // Store transcript data
    currentTranscriptData = response;
    
    // Show video info
    videoTitle.textContent = response.videoTitle;
    videoId.textContent = `ID: ${response.videoId}`;
    videoInfo.classList.remove('hidden');
    
    // Show transcript preview (first 200 chars)
    const previewText = response.transcript.substring(0, 200) + 
                       (response.transcript.length > 200 ? '...' : '');
    transcriptPreview.textContent = previewText;
    transcriptPreview.classList.remove('hidden');
    
    // Enable save button
    saveBtn.classList.remove('hidden');
    saveBtn.disabled = false;
    
    showSuccess(`✓ Extracted ${response.segmentCount} segments (${response.transcript.length} characters)`);
    extractBtn.disabled = false;
    
  } catch (error) {
    showError(`Error: ${error.message}`);
    extractBtn.disabled = false;
    console.error('Extract error:', error);
  }
}

// Upsert channel record in Airtable — returns record ID or null
async function upsertChannel(apiKey, baseId, channelData) {
  if (!channelData.channelId || !channelData.channelName) {
    console.log('Missing channel info, skipping channel upsert');
    return null;
  }

  try {
    // Look up existing channel by handle
    const findUrl = `https://api.airtable.com/v0/${baseId}/Channels?filterByFormula=` +
      encodeURIComponent(`AND({Platform}='YouTube', {Channel Handle}='${channelData.channelId}')`);

    const findResponse = await fetch(findUrl, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });

    if (!findResponse.ok) {
      console.error('Channel lookup failed:', await findResponse.text());
      return null;
    }

    const findResult = await findResponse.json();

    if (findResult.records.length > 0) {
      console.log('Found existing channel:', findResult.records[0].id);
      return findResult.records[0].id;
    }

    // Create new channel record
    const createResponse = await fetch(`https://api.airtable.com/v0/${baseId}/Channels`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        fields: {
          'Channel Name': channelData.channelName,
          'Platform': 'YouTube',
          'Channel Handle': channelData.channelId,
          'Channel URL': channelData.channelUrl || `https://www.youtube.com/channel/${channelData.channelId}`
        }
      })
    });

    if (!createResponse.ok) {
      console.error('Channel create failed:', await createResponse.text());
      return null;
    }

    const created = await createResponse.json();
    console.log('Created new channel:', created.id);
    return created.id;
  } catch (error) {
    console.error('Channel upsert error:', error);
    return null;
  }
}

// Save transcript to Airtable
async function saveToAirtable() {
  if (!currentTranscriptData) {
    showError('No transcript data to save');
    return;
  }
  
  showStatus('Saving to Airtable...', 'info');
  saveBtn.disabled = true;
  
  try {
    // Get stored credentials
    const { airtableApiKey, airtableBaseId } = await chrome.storage.sync.get([
      'airtableApiKey',
      'airtableBaseId'
    ]);
    
    if (!airtableApiKey || !airtableBaseId) {
      showError('Please configure Airtable credentials in settings');
      saveBtn.disabled = false;
      return;
    }
    
    // Find existing video record by Video ID
    const findUrl = `https://api.airtable.com/v0/${airtableBaseId}/Videos?filterByFormula=` +
      encodeURIComponent(`{Video ID}='${currentTranscriptData.videoId}'`);
    
    const findResponse = await fetch(findUrl, {
      headers: {
        'Authorization': `Bearer ${airtableApiKey}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!findResponse.ok) {
      const error = await findResponse.json();
      throw new Error(error.error?.message || 'Failed to query Airtable');
    }
    
    const findResult = await findResponse.json();
    
    let saveResponse;
    
    if (findResult.records.length === 0) {
      // Video not in Airtable yet — create a new record
      const createUrl = `https://api.airtable.com/v0/${airtableBaseId}/Videos`;
      
      // Upsert channel record
      const channelRecordId = await upsertChannel(airtableApiKey, airtableBaseId, {
        channelId: currentTranscriptData.channelId,
        channelName: currentTranscriptData.channelName,
        channelUrl: currentTranscriptData.channelUrl
      });

      // Build fields for new video record
      const thumbnailUrl = `https://i.ytimg.com/vi/${currentTranscriptData.videoId}/hqdefault.jpg`;
      const createFields = {
        'Video Title': currentTranscriptData.videoTitle,
        'Video ID': currentTranscriptData.videoId,
        'Platform': 'YouTube',
        'Video URL': `https://www.youtube.com/watch?v=${currentTranscriptData.videoId}`,
        'Triage Status': 'Queued',
        'Thumbnail URL': thumbnailUrl,
        'Thumbnail (Image)': [{ url: thumbnailUrl }],
        'Transcript (Full)': currentTranscriptData.transcript,
        'Transcript Language': currentTranscriptData.language,
        'Transcript Source': currentTranscriptData.source
      };
      
      // Add timestamped transcript if available
      if (currentTranscriptData.transcriptSegments && currentTranscriptData.transcriptSegments.length > 0) {
        createFields['Transcript (Timestamped)'] = JSON.stringify(currentTranscriptData.transcriptSegments);
      }

      if (channelRecordId) {
        createFields['Channel'] = [channelRecordId];
      }

      saveResponse = await fetch(createUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${airtableApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ fields: createFields })
      });
    } else {
      // Video exists — update with transcript
      const recordId = findResult.records[0].id;
      const updateUrl = `https://api.airtable.com/v0/${airtableBaseId}/Videos/${recordId}`;
      
      const updateFields = {
        'Transcript (Full)': currentTranscriptData.transcript,
        'Transcript Language': currentTranscriptData.language,
        'Transcript Source': currentTranscriptData.source
      };
      
      // Add timestamped transcript if available
      if (currentTranscriptData.transcriptSegments && currentTranscriptData.transcriptSegments.length > 0) {
        updateFields['Transcript (Timestamped)'] = JSON.stringify(currentTranscriptData.transcriptSegments);
      }
      
      saveResponse = await fetch(updateUrl, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${airtableApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ fields: updateFields })
      });
    }
    
    if (!saveResponse.ok) {
      const error = await saveResponse.json();
      throw new Error(error.error?.message || 'Failed to save to Airtable');
    }
    
    const action = findResult.records.length === 0 ? 'created + saved' : 'saved';
    showSuccess(`✓ Transcript ${action} to Airtable successfully!`);
    
    // Keep button disabled to prevent duplicate saves
    saveBtn.textContent = 'Saved ✓';
    
  } catch (error) {
    showError(`Error: ${error.message}`);
    saveBtn.disabled = false;
    console.error('Save error:', error);
  }
}

// Open settings page in a new tab
function openSettings() {
  chrome.tabs.create({ url: chrome.runtime.getURL('settings.html') });
}

// --- Pipeline Server Integration ---

const POLL_INTERVAL_MS = 3000;

async function checkServerHealth() {
  try {
    const res = await fetch(`${PIPELINE_SERVER}/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      serverOfflineDiv.classList.add('hidden');
      return true;
    }
  } catch (e) {
    // Server not reachable
  }
  serverOfflineDiv.classList.remove('hidden');
  return false;
}

function getSelectedEnrichmentProvider() {
  return enrichProviderSelect.value || 'ollama';
}

function getDefaultModelForProvider(provider) {
  return DEFAULT_ENRICHMENT_MODELS[provider] || DEFAULT_ENRICHMENT_MODELS.ollama;
}

function getSelectedEnrichmentModel() {
  const provider = getSelectedEnrichmentProvider();
  return (enrichModelInput.value || '').trim() || getDefaultModelForProvider(provider);
}

function syncModelInputForProvider() {
  const provider = getSelectedEnrichmentProvider();
  enrichModelInput.placeholder = getDefaultModelForProvider(provider);
  if (!(enrichModelInput.value || '').trim()) {
    enrichModelInput.value = getDefaultModelForProvider(provider);
  }
}

async function runFullPipeline() {
  runPipelineBtn.disabled = true;
  runPipelineBtn.textContent = 'Running...';
  pipelineStatusDiv.classList.remove('hidden');
  pipelineStepSpan.textContent = 'Extracting transcript...';

  try {
    // Step 1: Check server health
    const serverUp = await checkServerHealth();
    if (!serverUp) {
      showError('Pipeline server is not running. Please start it first.');
      resetPipelineUI();
      return;
    }

    // Step 2: Extract transcript from YouTube DOM
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab.url?.includes('youtube.com/watch')) {
      showError('Navigate to a YouTube video page first');
      resetPipelineUI();
      return;
    }

    let transcriptData;
    try {
      transcriptData = await chrome.tabs.sendMessage(tab.id, { action: 'extractTranscript' });
    } catch (msgError) {
      showError('Content script not loaded. Reload the YouTube page and try again.');
      resetPipelineUI();
      return;
    }

    if (transcriptData.error) {
      showError(transcriptData.error);
      resetPipelineUI();
      return;
    }

    // Store for UI display
    currentTranscriptData = transcriptData;
    videoTitle.textContent = transcriptData.videoTitle;
    videoId.textContent = `ID: ${transcriptData.videoId}`;
    videoInfo.classList.remove('hidden');

    // Step 3: POST to pipeline server
    pipelineStepSpan.textContent = 'Sending to pipeline server...';

    const interval = parseFloat(pipelineIntervalInput.value) || 5;
    const maxFrames = parseInt(pipelineMaxFramesInput.value) || 100;
    const skipVlm = document.getElementById('skipVlmCheckbox').checked;
    const enrichShots = enrichShotsCheckbox.checked;
    const enrichProvider = getSelectedEnrichmentProvider();
    const enrichModel = getSelectedEnrichmentModel();
    const forceReenrich = enrichShots && forceReenrichCheckbox.checked;

    const res = await fetch(`${PIPELINE_SERVER}/pipeline/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        videoUrl: `https://www.youtube.com/watch?v=${transcriptData.videoId}`,
        videoId: transcriptData.videoId,
        videoTitle: transcriptData.videoTitle,
        transcript: transcriptData.transcript,
        transcriptSegments: transcriptData.transcriptSegments,
        capture: { interval, maxFrames },
        skipVlm,
        enrichShots,
        enrichProvider,
        enrichModel,
        forceReenrich,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Server returned an error');
    }

    const { runId } = await res.json();
    pipelineRunId = runId;
    pipelineStepSpan.textContent = 'Pipeline started — polling for status...';
    showStatus(`Pipeline running (${runId.slice(0, 8)}...)`, 'info');

    // Step 4: Start polling
    startPipelinePolling(runId);

  } catch (error) {
    showError(`Pipeline error: ${error.message}`);
    resetPipelineUI();
    console.error('Pipeline error:', error);
  }
}

function startPipelinePolling(runId) {
  if (pipelinePollTimer) clearInterval(pipelinePollTimer);
  pollFailCount = 0;

  pipelinePollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${PIPELINE_SERVER}/pipeline/status/${runId}`);
      if (!res.ok) {
        console.error('Poll failed:', res.status);
        return;
      }
      pollFailCount = 0;

      const job = await res.json();
      const stepInfo = job.step ? ` [${job.step}]` : '';
      const completedInfo = job.completedSteps?.length ? ` (${job.completedSteps.length}/4 steps done)` : '';
      pipelineStepSpan.textContent = (job.message || job.status) + completedInfo;

      if (job.status === 'done') {
        clearInterval(pipelinePollTimer);
        pipelinePollTimer = null;
        showSuccess('✓ Pipeline complete! Shots published to Airtable.');
        runPipelineBtn.textContent = 'Pipeline Complete ✓';
        pipelineStepSpan.textContent = 'Done — shots published to Airtable + R2';
      } else if (job.status === 'error') {
        clearInterval(pipelinePollTimer);
        pipelinePollTimer = null;
        showError(`Pipeline failed at step '${job.step}': ${job.error}`);
        resetPipelineUI();
      }
    } catch (e) {
      pollFailCount++;
      console.error(`Poll error (${pollFailCount}):`, e);
      if (pollFailCount >= 3) {
        clearInterval(pipelinePollTimer);
        pipelinePollTimer = null;
        showError('Lost connection to pipeline server. Check if the server is still running.');
        resetPipelineUI();
      }
    }
  }, POLL_INTERVAL_MS);
}

function resetPipelineUI() {
  runPipelineBtn.disabled = false;
  runPipelineBtn.textContent = 'Run Full Pipeline';
  if (pipelinePollTimer) {
    clearInterval(pipelinePollTimer);
    pipelinePollTimer = null;
  }
}

// --- Resume Pipeline ---

let resumableJob = null;

async function checkResumable() {
  try {
    const res = await fetch(`${PIPELINE_SERVER}/pipeline/resumable`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return;
    const list = await res.json();
    if (list.length > 0) {
      resumableJob = list[0];
      resumeSection.classList.remove('hidden');
      resumeInfo.textContent = `Video: ${resumableJob.videoId} — failed at '${resumableJob.failedStep}' (${resumableJob.completedSteps.length}/4 steps done)`;
    } else {
      resumableJob = null;
      resumeSection.classList.add('hidden');
    }
  } catch (e) {
    // Server not reachable — hide resume section
    resumeSection.classList.add('hidden');
  }
}

async function resumePipeline() {
  if (!resumableJob) return;

  resumePipelineBtn.disabled = true;
  resumePipelineBtn.textContent = 'Resuming...';
  pipelineStatusDiv.classList.remove('hidden');
  pipelineStepSpan.textContent = 'Resuming pipeline...';

  try {
    const res = await fetch(`${PIPELINE_SERVER}/pipeline/resume/${resumableJob.runId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enrichShots: enrichShotsCheckbox.checked,
        enrichProvider: getSelectedEnrichmentProvider(),
        enrichModel: getSelectedEnrichmentModel(),
        forceReenrich: enrichShotsCheckbox.checked && forceReenrichCheckbox.checked,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Resume failed');
    }

    const { runId } = await res.json();
    pipelineRunId = runId;
    showStatus(`Pipeline resuming (${runId.slice(0, 8)}...)`, 'info');
    resumeSection.classList.add('hidden');
    runPipelineBtn.disabled = true;
    runPipelineBtn.textContent = 'Running...';

    startPipelinePolling(runId);
  } catch (error) {
    showError(`Resume error: ${error.message}`);
    resumePipelineBtn.disabled = false;
    resumePipelineBtn.textContent = '🔄 Resume Failed Pipeline';
    console.error('Resume error:', error);
  }
}

// --- Capture Orchestration (Legacy) ---

async function startCapture() {
  const interval = parseFloat(captureIntervalInput.value) || 1;
  const maxFrames = parseInt(captureMaxInput.value) || 100;

  if (interval < 0.5) {
    showError('Minimum interval is 0.5 seconds');
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab.url?.includes('youtube.com/watch')) {
    showError('Navigate to a YouTube video page first');
    return;
  }

  isCapturing = true;
  captureCountSpan.textContent = '0';
  captureTotalSpan.textContent = String(maxFrames);
  captureStatusDiv.classList.remove('hidden');
  startCaptureBtn.classList.add('hidden');
  stopCaptureBtn.classList.remove('hidden');
  openFolderLinkDiv.classList.add('hidden');
  captureIntervalInput.disabled = true;
  captureMaxInput.disabled = true;

  try {
    await chrome.tabs.sendMessage(tab.id, {
      action: 'startCapture',
      options: { interval, maxFrames }
    });
  } catch (err) {
    showError('Content script not loaded. Reload the YouTube page and try again.');
    resetCaptureUI();
  }
}

async function stopCapture() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    await chrome.tabs.sendMessage(tab.id, { action: 'stopCapture' });
  } catch (err) {
    console.error('Stop capture error:', err);
  }
  resetCaptureUI();
}

function resetCaptureUI() {
  isCapturing = false;
  startCaptureBtn.classList.remove('hidden');
  stopCaptureBtn.classList.add('hidden');
  captureIntervalInput.disabled = false;
  captureMaxInput.disabled = false;
}

// Listen for messages from content script (frame data, status updates)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'frameReady') {
    // Download the frame PNG
    chrome.downloads.download({
      url: message.dataUrl,
      filename: `${message.folder}/${message.filename}`,
      saveAs: false,
      conflictAction: 'uniquify'
    });
    captureCountSpan.textContent = String(message.index + 1);
  }

  if (message.type === 'manifestReady') {
    // Download manifest.json
    chrome.downloads.download({
      url: message.dataUrl,
      filename: `${message.folder}/${message.filename}`,
      saveAs: false,
      conflictAction: 'uniquify'
    });
    captureFolder = message.folder;
  }

  if (message.type === 'captureStarted') {
    captureFolder = message.folder;
    console.log('[Popup] Capture started, folder:', captureFolder);
  }

  if (message.type === 'captureStopped') {
    const count = message.count || 0;
    captureCountSpan.textContent = String(count);
    showSuccess(`✓ Captured ${count} frames`);
    resetCaptureUI();
    if (captureFolder) {
      openFolderLinkDiv.classList.remove('hidden');
    }
  }

  if (message.type === 'captureError') {
    showError(message.error);
    resetCaptureUI();
  }
});

// Event listeners
extractBtn.addEventListener('click', extractTranscript);
saveBtn.addEventListener('click', saveToAirtable);
settingsLink.addEventListener('click', (e) => {
  e.preventDefault();
  openSettings();
});
runPipelineBtn.addEventListener('click', runFullPipeline);
resumePipelineBtn.addEventListener('click', resumePipeline);
startCaptureBtn.addEventListener('click', startCapture);
stopCaptureBtn.addEventListener('click', stopCapture);
enrichProviderSelect.addEventListener('change', syncModelInputForProvider);
openFolderAnchor.addEventListener('click', (e) => {
  e.preventDefault();
  // Open the Downloads folder — chrome.downloads.showDefaultFolder() opens the default download location
  chrome.downloads.showDefaultFolder();
});

// Initialize - check if on YouTube video page
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  syncModelInputForProvider();
  const currentTab = tabs[0];
  if (!currentTab.url?.includes('youtube.com/watch')) {
    showStatus('Navigate to a YouTube video page to extract transcripts', 'info');
    extractBtn.disabled = true;
    startCaptureBtn.disabled = true;
    runPipelineBtn.disabled = true;
  } else {
    showStatus('Ready! Click "Extract Transcript" or "Run Full Pipeline"', 'info');
    startCaptureBtn.disabled = false;
    // Check server health to enable/disable pipeline button, then check for resumable jobs
    checkServerHealth().then((ok) => {
      runPipelineBtn.disabled = !ok;
      if (ok) checkResumable();
    });
  }
});
