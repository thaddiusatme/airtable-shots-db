// Popup script - handles UI interactions and saves to Airtable

let currentTranscriptData = null;

// DOM elements
const statusMessage = document.getElementById('statusMessage');
const videoInfo = document.getElementById('videoInfo');
const videoTitle = document.getElementById('videoTitle');
const videoId = document.getElementById('videoId');
const transcriptPreview = document.getElementById('transcriptPreview');
const extractBtn = document.getElementById('extractBtn');
const saveBtn = document.getElementById('saveBtn');
const settingsLink = document.getElementById('settingsLink');

function showStatus(message, type = 'info') {
  statusMessage.textContent = message;
  statusMessage.className = `status ${type}`;
}

function showSuccess(message) {
  showStatus(message, 'success');
}

function showError(message) {
  showStatus(message, 'error');
}

async function extractTranscript() {
  showStatus('Extracting transcript...', 'info');
  extractBtn.disabled = true;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab.url?.includes('youtube.com/watch')) {
      showError('Please navigate to a YouTube video page first');
      extractBtn.disabled = false;
      return;
    }

    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { action: 'extractTranscript' });
    } catch (msgError) {
      showError('Content script not loaded. Please reload the YouTube page and try again.');
      extractBtn.disabled = false;
      return;
    }

    if (response.error) {
      showError(response.error);
      extractBtn.disabled = false;
      return;
    }

    currentTranscriptData = response;

    videoTitle.textContent = response.videoTitle;
    videoId.textContent = `ID: ${response.videoId}`;
    videoInfo.classList.remove('hidden');

    const previewText = response.transcript.substring(0, 200) +
                       (response.transcript.length > 200 ? '...' : '');
    transcriptPreview.textContent = previewText;
    transcriptPreview.classList.remove('hidden');

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

async function upsertChannel(apiKey, baseId, channelData) {
  if (!channelData.channelId || !channelData.channelName) {
    console.log('Missing channel info, skipping channel upsert');
    return null;
  }

  try {
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
      return findResult.records[0].id;
    }

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
    return created.id;
  } catch (error) {
    console.error('Channel upsert error:', error);
    return null;
  }
}

async function saveToAirtable() {
  if (!currentTranscriptData) {
    showError('No transcript data to save');
    return;
  }

  showStatus('Saving to Airtable...', 'info');
  saveBtn.disabled = true;

  try {
    const { airtableApiKey, airtableBaseId } = await chrome.storage.sync.get([
      'airtableApiKey',
      'airtableBaseId'
    ]);

    if (!airtableApiKey || !airtableBaseId) {
      showError('Please configure Airtable credentials in settings');
      saveBtn.disabled = false;
      return;
    }

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
      const channelRecordId = await upsertChannel(airtableApiKey, airtableBaseId, {
        channelId: currentTranscriptData.channelId,
        channelName: currentTranscriptData.channelName,
        channelUrl: currentTranscriptData.channelUrl
      });

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

      if (currentTranscriptData.transcriptSegments?.length > 0) {
        createFields['Transcript (Timestamped)'] = JSON.stringify(currentTranscriptData.transcriptSegments);
      }

      if (channelRecordId) {
        createFields['Channel'] = [channelRecordId];
      }

      saveResponse = await fetch(`https://api.airtable.com/v0/${airtableBaseId}/Videos`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${airtableApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ fields: createFields })
      });
    } else {
      const recordId = findResult.records[0].id;
      const updateFields = {
        'Transcript (Full)': currentTranscriptData.transcript,
        'Transcript Language': currentTranscriptData.language,
        'Transcript Source': currentTranscriptData.source
      };

      if (currentTranscriptData.transcriptSegments?.length > 0) {
        updateFields['Transcript (Timestamped)'] = JSON.stringify(currentTranscriptData.transcriptSegments);
      }

      saveResponse = await fetch(`https://api.airtable.com/v0/${airtableBaseId}/Videos/${recordId}`, {
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
    saveBtn.textContent = 'Saved ✓';

  } catch (error) {
    showError(`Error: ${error.message}`);
    saveBtn.disabled = false;
    console.error('Save error:', error);
  }
}

function openSettings() {
  chrome.tabs.create({ url: chrome.runtime.getURL('settings.html') });
}

// Event listeners
extractBtn.addEventListener('click', extractTranscript);
saveBtn.addEventListener('click', saveToAirtable);
settingsLink.addEventListener('click', (e) => {
  e.preventDefault();
  openSettings();
});

// Initialize
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const currentTab = tabs[0];
  if (!currentTab.url?.includes('youtube.com/watch')) {
    showStatus('Navigate to a YouTube video page to extract transcripts', 'info');
    extractBtn.disabled = true;
  } else {
    showStatus('Ready! Click "Extract Transcript" to begin.', 'info');
  }
});
