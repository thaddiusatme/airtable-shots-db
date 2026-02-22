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
    
    if (findResult.records.length === 0) {
      showError('Video not found in Airtable. Please import the video first using the CLI.');
      saveBtn.disabled = false;
      return;
    }
    
    const recordId = findResult.records[0].id;
    
    // Update record with transcript
    const updateUrl = `https://api.airtable.com/v0/${airtableBaseId}/Videos/${recordId}`;
    
    const updateResponse = await fetch(updateUrl, {
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
    
    if (!updateResponse.ok) {
      const error = await updateResponse.json();
      throw new Error(error.error?.message || 'Failed to update Airtable');
    }
    
    showSuccess('✓ Transcript saved to Airtable successfully!');
    
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
