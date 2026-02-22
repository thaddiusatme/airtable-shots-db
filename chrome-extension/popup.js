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
      
      saveResponse = await fetch(updateUrl, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${airtableApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          fields: {
            'Transcript (Full)': currentTranscriptData.transcript,
            'Transcript Language': currentTranscriptData.language,
            'Transcript Source': currentTranscriptData.source
          }
        })
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

// Event listeners
extractBtn.addEventListener('click', extractTranscript);
saveBtn.addEventListener('click', saveToAirtable);
settingsLink.addEventListener('click', (e) => {
  e.preventDefault();
  openSettings();
});

// Initialize - check if on YouTube video page
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const currentTab = tabs[0];
  if (!currentTab.url?.includes('youtube.com/watch')) {
    showStatus('Navigate to a YouTube video page to extract transcripts', 'info');
    extractBtn.disabled = true;
  } else {
    showStatus('Ready! Click "Extract Transcript" to begin', 'info');
  }
});
