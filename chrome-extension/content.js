// Content script - runs on YouTube video pages
// Extracts transcript from the YouTube web UI

function extractTranscript() {
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
  
  // Try to find transcript panel
  // YouTube's DOM structure may change, this selector may need updating
  const transcriptPanel = document.querySelector('ytd-transcript-renderer') ||
                          document.querySelector('#transcript');
  
  if (!transcriptPanel) {
    return { 
      error: 'Transcript not available. Please open the transcript panel first.',
      videoId,
      videoTitle
    };
  }
  
  // Extract transcript segments
  // YouTube transcript segments have the text in .segment-text or similar
  const segments = transcriptPanel.querySelectorAll(
    'ytd-transcript-segment-renderer, .segment'
  );
  
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
  
  // Try to detect language from UI
  // This is a best guess - may need refinement
  let language = 'en';
  const languageIndicator = transcriptPanel.querySelector('[aria-label*="language"]') ||
                           transcriptPanel.querySelector('.language-name');
  if (languageIndicator) {
    const langText = languageIndicator.textContent?.toLowerCase();
    if (langText?.includes('spanish')) language = 'es';
    else if (langText?.includes('french')) language = 'fr';
    else if (langText?.includes('german')) language = 'de';
    // Add more language detection as needed
  }
  
  return {
    videoId,
    videoTitle,
    transcript: transcriptText,
    language,
    source: 'youtube-web-ui',
    fetchedAt: new Date().toISOString(),
    segmentCount: segments.length
  };
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractTranscript') {
    const data = extractTranscript();
    sendResponse(data);
  }
  return true; // Keep message channel open for async response
});

console.log('YouTube Transcript Extractor content script loaded');
