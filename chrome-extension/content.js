// Content script - runs on YouTube video pages
// Extracts transcript from DOM (like Glasp does)

async function waitForElement(selector, timeout = 5000) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const element = document.querySelector(selector);
    if (element) return element;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return null;
}

async function openTranscriptPanel() {
  console.log('Attempting to open transcript panel...');
  
  // Strategy 1: Check if panel is already visible but hidden
  const existingPanel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-transcript"]');
  if (existingPanel && existingPanel.getAttribute('visibility') !== 'ENGAGEMENT_PANEL_VISIBILITY_HIDDEN') {
    console.log('Transcript panel already visible');
    return true;
  }
  
  // Strategy 2: Look for the three-dot menu button and transcript option
  // First, try to find "Show transcript" in the description area
  const descriptionButtons = document.querySelectorAll('ytd-video-description-transcript-section-renderer button');
  if (descriptionButtons.length > 0) {
    console.log('Found transcript button in description area, clicking...');
    descriptionButtons[0].click();
    await new Promise(resolve => setTimeout(resolve, 1500));
    return true;
  }
  
  // Strategy 3: Look for menu items (three-dot menu)
  const menuItems = document.querySelectorAll('ytd-menu-service-item-renderer, tp-yt-paper-item');
  for (const item of menuItems) {
    const text = item.textContent?.toLowerCase() || '';
    if (text.includes('transcript') || text.includes('show transcript')) {
      console.log('Found transcript in menu item, clicking...');
      item.click();
      await new Promise(resolve => setTimeout(resolve, 1500));
      return true;
    }
  }
  
  // Strategy 4: Generic button search
  const allButtons = document.querySelectorAll('button, ytd-button-renderer, a[role="button"]');
  for (const btn of allButtons) {
    const text = btn.textContent?.toLowerCase() || '';
    const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
    
    if (text.includes('show transcript') || ariaLabel.includes('show transcript')) {
      console.log('Found generic transcript button, clicking...');
      btn.click();
      await new Promise(resolve => setTimeout(resolve, 1500));
      return true;
    }
  }
  
  // Strategy 5: Try engagement panel sections directly
  const engagementSections = document.querySelectorAll('ytd-structured-description-content-renderer button');
  for (const btn of engagementSections) {
    const text = btn.textContent?.toLowerCase() || '';
    if (text.includes('transcript')) {
      console.log('Found transcript in structured description, clicking...');
      btn.click();
      await new Promise(resolve => setTimeout(resolve, 1500));
      return true;
    }
  }
  
  console.log('Could not find transcript button with any strategy');
  return false;
}

async function extractTranscript() {
  console.log('Attempting to extract transcript...');
  
  // Get video ID from URL
  const urlParams = new URLSearchParams(window.location.search);
  const videoId = urlParams.get('v');
  
  if (!videoId) {
    return { error: 'No video ID found in URL' };
  }
  
  // Get video title
  const videoTitle = document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string')?.textContent?.trim() ||
                     document.querySelector('h1.title')?.textContent?.trim() ||
                     'Unknown Title';
  
  try {
    // First check if transcript panel is already open
    let transcriptPanel = document.querySelector('ytd-transcript-renderer');
    
    // If not open, try to open it
    if (!transcriptPanel) {
      console.log('Transcript panel not open, attempting to open...');
      const opened = await openTranscriptPanel();
      
      if (opened) {
        // Wait for panel to load with multiple attempts
        transcriptPanel = await waitForElement('ytd-transcript-renderer', 5000);
      }
      
      // Try alternative engagement panel selector
      if (!transcriptPanel) {
        const engagementPanel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-transcript"]');
        if (engagementPanel) {
          transcriptPanel = engagementPanel.querySelector('ytd-transcript-renderer');
        }
      }
    }
    
    if (!transcriptPanel) {
      return { 
        error: 'Could not find or open transcript panel. Try manually clicking "Show transcript" first, then extract again.',
        videoId,
        videoTitle
      };
    }
    
    console.log('Transcript panel found, extracting segments...');
    
    // Extract transcript segments from DOM
    const segments = transcriptPanel.querySelectorAll('ytd-transcript-segment-renderer');
    
    if (segments.length === 0) {
      return { 
        error: 'Transcript panel is open but no segments found',
        videoId,
        videoTitle
      };
    }
    
    // Extract text from each segment
    const transcriptText = Array.from(segments)
      .map(seg => {
        // Try multiple selectors for text content
        const textElement = seg.querySelector('.segment-text') ||
                           seg.querySelector('yt-formatted-string') ||
                           seg;
        return textElement?.textContent?.trim();
      })
      .filter(Boolean)
      .join(' ');
    
    // Try to detect language from panel
    let language = 'en';
    const languageButton = transcriptPanel.querySelector('[aria-label*="language"]');
    if (languageButton) {
      const langText = languageButton.textContent?.toLowerCase();
      if (langText?.includes('spanish')) language = 'es';
      else if (langText?.includes('french')) language = 'fr';
      else if (langText?.includes('german')) language = 'de';
    }
    
    console.log(`Extracted ${segments.length} segments, ${transcriptText.length} characters`);
    
    // Extract channel info from DOM
    const channelLink = document.querySelector('ytd-video-owner-renderer ytd-channel-name a') ||
                        document.querySelector('#owner a[href*="/channel/"]') ||
                        document.querySelector('#owner a[href*="/@"]');
    const channelName = document.querySelector('ytd-video-owner-renderer ytd-channel-name yt-formatted-string')?.textContent?.trim() ||
                        document.querySelector('#owner ytd-channel-name')?.textContent?.trim() ||
                        '';
    let channelId = '';
    let channelUrl = '';
    if (channelLink) {
      channelUrl = channelLink.href || '';
      // Extract channel ID or handle from URL
      const channelMatch = channelUrl.match(/\/channel\/(UC[a-zA-Z0-9_-]+)/);
      const handleMatch = channelUrl.match(/\/@([^/?]+)/);
      if (channelMatch) {
        channelId = channelMatch[1];
      } else if (handleMatch) {
        channelId = '@' + handleMatch[1];
      }
    }

    return {
      videoId,
      videoTitle,
      transcript: transcriptText,
      language,
      source: 'youtube-web-ui-dom',
      fetchedAt: new Date().toISOString(),
      segmentCount: segments.length,
      channelName,
      channelId,
      channelUrl
    };
    
  } catch (error) {
    console.error('Transcript extraction error:', error);
    return { 
      error: `Failed to extract transcript: ${error.message}`,
      videoId,
      videoTitle
    };
  }
}

// --- Frame Capture Logic ---

let captureTimer = null;
let captureIndex = 0;
let captureMax = 100;
let captureInterval = 1000; // ms
let captureFolder = '';

function getVideoElement() {
  return document.querySelector('video.html5-main-video') || document.querySelector('video');
}

function getVideoId() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('v') || 'unknown';
}

function getVideoTitleText() {
  return document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string')?.textContent?.trim() ||
         document.querySelector('h1.title')?.textContent?.trim() ||
         document.querySelector('yt-formatted-string.style-scope.ytd-watch-metadata')?.textContent?.trim() ||
         'Unknown Title';
}

function formatTimestamp(seconds) {
  return seconds.toFixed(3).padStart(7, '0');
}

function formatIndex(index) {
  return String(index).padStart(5, '0');
}

function captureFrame(video) {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/png');
  });
}

function buildManifest(frameList) {
  return {
    videoId: getVideoId(),
    videoTitle: getVideoTitleText(),
    captureDate: new Date().toISOString(),
    interval: captureInterval / 1000,
    frames: frameList
  };
}

async function startCapture(options) {
  const video = getVideoElement();
  if (!video) {
    chrome.runtime.sendMessage({ type: 'captureError', error: 'No <video> element found on page' });
    return;
  }

  captureIndex = 0;
  captureMax = options.maxFrames || 100;
  captureInterval = (options.interval || 1) * 1000;
  const now = new Date();
  const datetime = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
  captureFolder = `yt-captures/${getVideoId()}_${datetime}`;
  const frameList = [];

  console.log(`[Capture] Starting: interval=${captureInterval}ms, max=${captureMax}, folder=${captureFolder}`);

  captureTimer = setInterval(async () => {
    if (captureIndex >= captureMax) {
      stopCapture(frameList);
      return;
    }

    try {
      const timestamp = video.currentTime;
      const blob = await captureFrame(video);
      const filename = `frame_${formatIndex(captureIndex)}_t${formatTimestamp(timestamp)}s.png`;

      frameList.push({ index: captureIndex, timestamp, filename });

      // Convert blob to base64 data URL for download via popup
      const reader = new FileReader();
      reader.onloadend = () => {
        chrome.runtime.sendMessage({
          type: 'frameReady',
          dataUrl: reader.result,
          filename,
          folder: captureFolder,
          index: captureIndex,
          timestamp,
          total: captureMax
        });
      };
      reader.readAsDataURL(blob);

      captureIndex++;
    } catch (err) {
      console.error('[Capture] Frame error:', err);
    }
  }, captureInterval);

  chrome.runtime.sendMessage({ type: 'captureStarted', folder: captureFolder });
}

function stopCapture(frameList) {
  if (captureTimer) {
    clearInterval(captureTimer);
    captureTimer = null;
  }

  // Generate manifest.json
  if (frameList && frameList.length > 0) {
    const manifest = buildManifest(frameList);
    const manifestBlob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
    const reader = new FileReader();
    reader.onloadend = () => {
      chrome.runtime.sendMessage({
        type: 'manifestReady',
        dataUrl: reader.result,
        filename: 'manifest.json',
        folder: captureFolder,
        manifest
      });
    };
    reader.readAsDataURL(manifestBlob);
  }

  chrome.runtime.sendMessage({ type: 'captureStopped', count: captureIndex, folder: captureFolder });
  console.log(`[Capture] Stopped at frame ${captureIndex}`);
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractTranscript') {
    // extractTranscript is now async
    extractTranscript().then(data => {
      sendResponse(data);
    }).catch(error => {
      sendResponse({ error: error.message });
    });
    return true; // Keep message channel open for async response
  }

  if (request.action === 'startCapture') {
    startCapture(request.options || {});
    sendResponse({ status: 'started' });
    return true;
  }

  if (request.action === 'stopCapture') {
    stopCapture(null);
    sendResponse({ status: 'stopped' });
    return true;
  }

  return true;
});

console.log('YouTube Transcript Extractor content script loaded');
