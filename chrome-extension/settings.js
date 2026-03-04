// Settings page script - manages Airtable credential storage

const apiKeyInput = document.getElementById('apiKey');
const baseIdInput = document.getElementById('baseId');
const saveBtn = document.getElementById('saveBtn');
const testBtn = document.getElementById('testBtn');
const clearBtn = document.getElementById('clearBtn');
const statusMessage = document.getElementById('statusMessage');
const lastSavedEl = document.getElementById('lastSaved');
const backLink = document.getElementById('backLink');

// Show status message
function showStatus(message, type = 'info') {
  statusMessage.textContent = message;
  statusMessage.className = `status ${type}`;
}

// Hide status message
function hideStatus() {
  statusMessage.className = 'status hidden';
}

// Load existing credentials from chrome.storage.sync
async function loadCredentials() {
  try {
    const { airtableApiKey, airtableBaseId, airtableSettingsSavedAt } =
      await chrome.storage.sync.get(['airtableApiKey', 'airtableBaseId', 'airtableSettingsSavedAt']);

    if (airtableApiKey) {
      apiKeyInput.value = airtableApiKey;
    }
    if (airtableBaseId) {
      baseIdInput.value = airtableBaseId;
    }
    if (airtableSettingsSavedAt) {
      lastSavedEl.textContent = `Last saved: ${new Date(airtableSettingsSavedAt).toLocaleString()}`;
    }
  } catch (error) {
    console.error('Failed to load credentials:', error);
    showStatus('Failed to load saved credentials.', 'error');
  }
}

// Validate input fields — returns error message or null if valid
function validateInputs() {
  const apiKey = apiKeyInput.value.trim();
  const baseId = baseIdInput.value.trim();

  if (!apiKey && !baseId) {
    return 'Please enter both API Key and Base ID.';
  }
  if (!apiKey) {
    return 'Please enter your Airtable API Key.';
  }
  if (!baseId) {
    return 'Please enter your Airtable Base ID.';
  }

  // Format validation (P1)
  if (!apiKey.startsWith('pat') && !apiKey.startsWith('key')) {
    return 'API Key should start with "pat" (Personal Access Token) or "key" (legacy).';
  }
  if (!baseId.startsWith('app')) {
    return 'Base ID should start with "app".';
  }

  return null;
}

// Save credentials to chrome.storage.sync
async function saveCredentials() {
  const error = validateInputs();
  if (error) {
    showStatus(error, 'error');
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';

  try {
    const now = new Date().toISOString();
    await chrome.storage.sync.set({
      airtableApiKey: apiKeyInput.value.trim(),
      airtableBaseId: baseIdInput.value.trim(),
      airtableSettingsSavedAt: now
    });

    showStatus('✓ Credentials saved successfully!', 'success');
    lastSavedEl.textContent = `Last saved: ${new Date(now).toLocaleString()}`;
  } catch (error) {
    console.error('Failed to save credentials:', error);
    showStatus('Failed to save credentials. Please try again.', 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save Credentials';
  }
}

// Test connection to Airtable
async function testConnection() {
  const error = validateInputs();
  if (error) {
    showStatus(error, 'error');
    return;
  }

  testBtn.disabled = true;
  testBtn.textContent = 'Testing...';

  try {
    const apiKey = apiKeyInput.value.trim();
    const baseId = baseIdInput.value.trim();

    // Try to list records from the Videos table (limit 1)
    const url = `https://api.airtable.com/v0/${baseId}/Videos?maxRecords=1`;
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });

    if (response.ok) {
      showStatus('✓ Connection successful! Credentials are valid.', 'success');
    } else if (response.status === 401) {
      showStatus('✗ Invalid API Key. Please check your token.', 'error');
    } else if (response.status === 404) {
      showStatus('✗ Base not found. Please check your Base ID.', 'error');
    } else {
      const data = await response.json();
      showStatus(`✗ Error: ${data.error?.message || response.statusText}`, 'error');
    }
  } catch (error) {
    console.error('Test connection error:', error);
    showStatus('✗ Connection failed. Check your network and try again.', 'error');
  } finally {
    testBtn.disabled = false;
    testBtn.textContent = 'Test Connection';
  }
}

// Clear all stored credentials
async function clearCredentials() {
  if (!confirm('Are you sure you want to clear your saved credentials?')) {
    return;
  }

  try {
    await chrome.storage.sync.remove(['airtableApiKey', 'airtableBaseId', 'airtableSettingsSavedAt']);
    apiKeyInput.value = '';
    baseIdInput.value = '';
    lastSavedEl.textContent = '';
    showStatus('Credentials cleared.', 'info');
  } catch (error) {
    console.error('Failed to clear credentials:', error);
    showStatus('Failed to clear credentials.', 'error');
  }
}

// Back link — close this tab
backLink.addEventListener('click', (e) => {
  e.preventDefault();
  window.close();
});

// Event listeners
saveBtn.addEventListener('click', saveCredentials);
testBtn.addEventListener('click', testConnection);
clearBtn.addEventListener('click', clearCredentials);

// Load credentials on page load
loadCredentials();
