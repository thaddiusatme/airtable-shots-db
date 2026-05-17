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
      
      // Try alternative engagement panel selectors (YouTube updated target-id in Feb 2026)
      if (!transcriptPanel) {
        const engagementPanel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-transcript"]') ||
                                document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]') ||
                                document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="PAmodern_transcript_view"]');
        if (engagementPanel) {
          transcriptPanel = engagementPanel.querySelector('ytd-transcript-renderer') || engagementPanel;
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
    
    // Helper function to parse timestamp to seconds
    function parseTimestampToSeconds(timestamp) {
      if (!timestamp) return null;
      const parts = timestamp.split(':').map(Number);
      if (parts.length === 2) {
        // M:SS format
        return parts[0] * 60 + parts[1];
      } else if (parts.length === 3) {
        // H:MM:SS format
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
      }
      return null;
    }
    
    const transcriptSegments = Array.from(segments)
      .map(seg => {
        // Try ALL possible approaches to find timestamp and text
        let timestampStr = null;
        let text = null;
        
        // Approach 1: span.yt-core-attributed-string (Feb 2026 DOM)
        const coreSpans = seg.querySelectorAll('span.yt-core-attributed-string');
        
        // Approach 2: div children with specific roles
        const divChildren = seg.querySelectorAll('div');
        
        // Approach 3: All direct children
        const directChildren = Array.from(seg.children);
        
        // Approach 4: yt-formatted-string elements
        const ytFormatted = seg.querySelectorAll('yt-formatted-string');
        
        // Approach 5: Any element containing a timestamp pattern (M:SS or H:MM:SS)  
        const allEls = seg.querySelectorAll('*');
        for (const el of allEls) {
          const txt = el.textContent.trim();
          // Check if this looks like a timestamp (matches M:SS or H:MM:SS)
          if (!timestampStr && /^\d{1,2}:\d{2}(:\d{2})?$/.test(txt)) {
            timestampStr = txt;
          }
        }
        
        if (coreSpans.length >= 2) {
          if (!timestampStr) timestampStr = coreSpans[0]?.textContent?.trim();
          text = coreSpans[1]?.textContent?.trim();
        } else if (ytFormatted.length >= 2) {
          if (!timestampStr) timestampStr = ytFormatted[0]?.textContent?.trim();
          text = ytFormatted[1]?.textContent?.trim();
        } else if (directChildren.length >= 2) {
          if (!timestampStr) timestampStr = directChildren[0]?.textContent?.trim();
          text = directChildren[1]?.textContent?.trim();
        } else {
          // Last resort: full text content, strip timestamp if found
          const fullText = seg.textContent.trim();
          if (timestampStr && fullText.startsWith(timestampStr)) {
            text = fullText.substring(timestampStr.length).trim();
          } else {
            text = fullText;
          }
        }
        
        const start = parseTimestampToSeconds(timestampStr);
        return { text, start };
      })
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
