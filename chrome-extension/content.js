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
  
  // Look for the "Show transcript" button
  // YouTube structure: button with aria-label or text containing "transcript"
  const buttons = Array.from(document.querySelectorAll('button, ytd-button-renderer'));
  
  const transcriptButton = buttons.find(btn => {
    const text = btn.textContent?.toLowerCase() || '';
    const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
    return text.includes('transcript') || ariaLabel.includes('transcript');
  });
  
  if (transcriptButton) {
    console.log('Found transcript button, clicking...');
    transcriptButton.click();
    // Wait a bit for panel to appear
    await new Promise(resolve => setTimeout(resolve, 1000));
    return true;
  }
  
  // Alternative: look for the engagement panel button
  const engagementPanels = document.querySelectorAll('ytd-engagement-panel-title-header-renderer button');
  for (const btn of engagementPanels) {
    if (btn.textContent?.toLowerCase().includes('transcript')) {
      console.log('Found engagement panel transcript button, clicking...');
      btn.click();
      await new Promise(resolve => setTimeout(resolve, 1000));
      return true;
    }
  }
  
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
        // Wait for panel to load
        transcriptPanel = await waitForElement('ytd-transcript-renderer', 3000);
      }
    }
    
    if (!transcriptPanel) {
      return { 
        error: 'Could not find or open transcript panel. This video may not have captions available.',
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
    
    return {
      videoId,
      videoTitle,
      transcript: transcriptText,
      language,
      source: 'youtube-web-ui-dom',
      fetchedAt: new Date().toISOString(),
      segmentCount: segments.length
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
  return true;
});

console.log('YouTube Transcript Extractor content script loaded');
