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

// Segment element matching + per-row parsing live in lib/transcript-dom.js so they can
// be unit-tested against captured variant fixtures without a browser (injected before
// this script via manifest.json). TranscriptDom is a global in the content-script world.
const { collectSegments, parseSegment } = TranscriptDom;

// The modern variant lazy-loads its rows behind a spinner after the panel is
// shown, so poll until at least one segment element appears.
async function waitForSegments(root, timeout = 5000) {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    const segments = collectSegments(root);
    if (segments.length > 0) return segments;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return collectSegments(root);
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
    // Search document-wide for segments rather than locking onto a specific panel
    // wrapper: the modern variant renders into an engagement panel whose target-id
    // becomes null once expanded, while a stale hidden "PAmodern_transcript_view"
    // panel (still showing a spinner) also exists — matching by target-id grabs the
    // wrong one. Matching segment elements by tag avoids both traps.
    let segments = collectSegments(document);

    // If none are present yet, open the panel and poll for lazy-loaded rows.
    if (segments.length === 0) {
      console.log('No transcript segments yet, attempting to open panel...');
      const opened = await openTranscriptPanel();
      if (opened) {
        segments = await waitForSegments(document, 5000);
      }
    }

    if (segments.length === 0) {
      return {
        error: 'Could not find transcript segments. Try manually clicking "Show transcript" first, then extract again.',
        videoId,
        videoTitle
      };
    }

    console.log(`Found ${segments.length} transcript segments, extracting...`);

    // Panel reference used later for language detection (variant-agnostic).
    const transcriptPanel = segments[0].closest('ytd-engagement-panel-section-list-renderer') || document;

    // Per-row parsing lives in lib/transcript-dom.js (parseSegment) so it stays testable.
    const transcriptSegments = segments
      .map(parseSegment)
      .filter(item => item.text);
    
    // Build full transcript text from segments (backward compatible)
    const transcriptText = transcriptSegments
      .map(seg => seg.text)
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
    
    const timestampedCount = transcriptSegments.filter(s => s.start !== null).length;
    console.log(`Extracted ${segments.length} segments, ${timestampedCount} with timestamps, ${transcriptText.length} characters`);
    if (transcriptSegments.length > 0) {
      console.log('First segment:', JSON.stringify(transcriptSegments[0]));
      console.log('Last segment:', JSON.stringify(transcriptSegments[transcriptSegments.length - 1]));
    }
    
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
      transcriptSegments,  // NEW: timestamped segments
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

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractTranscript') {
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
