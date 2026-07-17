// Service worker - owns ALL Airtable I/O for the in-page panel.
//
// Why this exists (the CORS constraint): a fetch() to api.airtable.com from a
// content script runs in the YouTube page's origin and is rejected by CORS.
// The same fetch() from this service worker runs in the extension origin and is
// allowed via host_permissions. The content script therefore posts the extracted
// transcript here via chrome.runtime.sendMessage and we do the save.
// Bonus: the Airtable PAT is read ONLY inside this worker, never in the page world.

// TranscriptUtils (GH-64 truncation shim) is a UMD module; in a worker `self` is
// the global scope, so importScripts attaches self.TranscriptUtils.
importScripts('lib/transcript-utils.js');

// Build the transcript-related Airtable fields, guarding against the 100k-char
// Long Text limit (GH-64). Returns the fields plus a human-readable warning
// string (or null) describing any truncation that occurred.
// (Ported verbatim from popup.js buildTranscriptFields.)
function buildTranscriptFields(data) {
  const fields = {
    'Transcript Language': data.language,
    'Transcript Source': data.source
  };

  const fullText = TranscriptUtils.truncateForAirtable(data.transcript);
  fields['Transcript (Full)'] = fullText.value;

  const warnings = [];
  if (fullText.truncated) {
    warnings.push('full transcript truncated to 100k chars');
  }

  if (data.transcriptSegments?.length > 0) {
    const fitted = TranscriptUtils.fitSegmentsForAirtable(data.transcriptSegments);
    fields['Transcript (Timestamped)'] = fitted.json;
    if (fitted.truncated) {
      warnings.push(`${fitted.droppedCount} timestamped segment(s) dropped to fit 100k chars`);
    }
  }

  return { fields, warning: warnings.length ? `⚠ Saved with limits: ${warnings.join('; ')}` : null };
}

// Find-or-create a Channels record by Channel Handle. Swallows all failures ->
// null so a channel problem never blocks the video save. (Ported from popup.js.)
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

// Upsert a Videos record by Video ID from an extractTranscript() result.
// Resolves to { action: 'created' | 'saved', warning } or throws with a readable
// message. (Ported from popup.js saveToAirtable, DOM stripped; reads the PAT +
// Base ID from chrome.storage.sync inside the worker only.)
async function saveTranscript(data) {
  if (!data || !data.videoId) {
    throw new Error('No transcript data to save');
  }

  const { airtableApiKey, airtableBaseId } = await chrome.storage.sync.get([
    'airtableApiKey',
    'airtableBaseId'
  ]);

  if (!airtableApiKey || !airtableBaseId) {
    throw new Error('Please configure Airtable credentials in settings');
  }

  const findUrl = `https://api.airtable.com/v0/${airtableBaseId}/Videos?filterByFormula=` +
    encodeURIComponent(`{Video ID}='${data.videoId}'`);

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
  let truncationWarning = null;

  if (findResult.records.length === 0) {
    const channelRecordId = await upsertChannel(airtableApiKey, airtableBaseId, {
      channelId: data.channelId,
      channelName: data.channelName,
      channelUrl: data.channelUrl
    });

    const thumbnailUrl = `https://i.ytimg.com/vi/${data.videoId}/hqdefault.jpg`;
    const { fields: transcriptFields, warning } = buildTranscriptFields(data);
    truncationWarning = warning;
    const createFields = {
      'Video Title': data.videoTitle,
      'Video ID': data.videoId,
      'Platform': 'YouTube',
      'Video URL': `https://www.youtube.com/watch?v=${data.videoId}`,
      'Triage Status': 'Queued',
      'Thumbnail URL': thumbnailUrl,
      'Thumbnail (Image)': [{ url: thumbnailUrl }],
      ...transcriptFields
    };

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
    const { fields: transcriptFields, warning } = buildTranscriptFields(data);
    truncationWarning = warning;

    saveResponse = await fetch(`https://api.airtable.com/v0/${airtableBaseId}/Videos/${recordId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${airtableApiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ fields: transcriptFields })
    });
  }

  if (!saveResponse.ok) {
    const error = await saveResponse.json();
    throw new Error(error.error?.message || 'Failed to save to Airtable');
  }

  return {
    action: findResult.records.length === 0 ? 'created' : 'saved',
    warning: truncationWarning
  };
}

// Message handler: content script -> worker -> Airtable.
// { action: 'saveTranscript', data: <extractTranscript() result> }
//   -> { ok: true, action: 'created'|'saved', warning } | { ok: false, error }
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'saveTranscript') {
    saveTranscript(msg.data)
      .then(r => sendResponse({ ok: true, ...r }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true; // keep the channel open for the async response
  }
  return false;
});
