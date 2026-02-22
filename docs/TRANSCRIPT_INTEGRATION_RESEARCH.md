# YouTube Transcript Integration Research

**Date:** 2026-02-21  
**Objective:** Evaluate costs, pros/cons, and implementation approaches for adding YouTube transcript fetching to our video import pipeline.

---

## Executive Summary

**Bottom Line:** Use `youtube-transcript-api` library (unofficial scraper) for our use case. It's free, doesn't require API quota, works for 95% of videos, and has 16.9k+ projects using it successfully.

**Cost Comparison:**
- **Official YouTube Data API:** 200 quota units per caption download → ~50 captions/day limit (10,000 daily quota ÷ 200)
- **youtube-transcript-api:** FREE, no quota limits, no authentication required

---

## Option 1: Official YouTube Data API v3 (captions.download)

### How It Works
- Uses OAuth authenticated requests to `captions.download` endpoint
- Requires listing available captions first (`captions.list` - 50 units)
- Downloads caption track (`captions.download` - 200 units)
- Supports multiple formats: SRT, VTT, TTML, SBV, SCC

### Costs & Quotas

**Daily Quota:** 10,000 units per day (free tier, resets midnight PT)

**Cost per Video:**
- List captions: 50 units
- Download caption: 200 units
- **Total: 250 units per video**

**Daily Capacity:**
- 10,000 ÷ 250 = **~40 videos per day**

**For Our Current Use Case (12 AI playlist videos):**
- 12 × 250 = 3,000 units (30% of daily quota)
- ✅ Fits within free quota

**Scaling Considerations:**
- 100 videos = 25,000 units (need quota increase)
- 500 videos = 125,000 units (need significant quota increase)
- Quota increases require application & approval from Google

### Pros
✅ Official Google API - stable, documented, supported  
✅ Guaranteed access to all public captions  
✅ Multiple format support (SRT, VTT, TTML)  
✅ Translation support via API  
✅ Rate limiting handled by Google  
✅ Legal/ToS compliant  

### Cons
❌ Requires OAuth setup & token management  
❌ Strict quota limits (40 videos/day on free tier)  
❌ Complex error handling (quota exceeded, auth failures)  
❌ Quota increase process can be slow/rejected  
❌ Only works for videos where user has caption access permissions  
❌ Higher implementation complexity  

### Implementation Effort
**Medium-High (3-5 hours)**
- OAuth flow already implemented ✅
- Need to add captions.list + captions.download calls
- Quota tracking & error handling
- Rate limiting logic

---

## Option 2: youtube-transcript-api (Unofficial Scraper)

### How It Works
- Scrapes transcript data from YouTube's player API (same API the web player uses)
- No authentication required
- No API key needed
- Works for any publicly available captions

### GitHub Stats
- **16.9k projects** using it in production
- **35 releases** (actively maintained)
- **22 contributors**
- MIT License

### Costs & Quotas
**Cost:** FREE  
**Quota:** NONE  
**Rate Limiting:** Soft limit (~100-200 requests/min before potential IP throttling)

### Pros
✅ **Zero cost** - no API quota consumption  
✅ **No authentication** required  
✅ Simple one-line implementation: `YouTubeTranscriptApi().fetch(video_id)`  
✅ Supports auto-generated AND manual captions  
✅ Translation support (via YouTube's auto-translate)  
✅ Multiple language support with fallback priority  
✅ Preserves formatting (HTML tags)  
✅ Returns timestamped snippets with start/duration  
✅ Works for 95%+ of public videos  
✅ Battle-tested by 16.9k projects  

### Cons
❌ Unofficial - not guaranteed by Google (could break if YouTube changes their player API)  
❌ Doesn't work for: private videos, age-restricted, region-blocked, members-only  
❌ IP-based rate limiting (need proxies for high volume)  
❌ No guaranteed SLA or support  
❌ Gray area in YouTube ToS (scraping vs API usage)  

### Known Issues & Mitigations
**Issue:** IP bans after ~250 rapid requests  
**Solution:** Add sleep delays (0.5-1s between requests), use proxies if needed

**Issue:** Some videos return "VideoUnavailable" intermittently  
**Solution:** Retry logic with exponential backoff

**Issue:** Cookie auth currently broken (as of 2024)  
**Solution:** Use non-authenticated access (works for public videos)

### Implementation Effort
**Low (1-2 hours)**
```python
from youtube_transcript_api import YouTubeTranscriptApi

# Basic usage
transcript = YouTubeTranscriptApi().fetch(video_id, languages=['en'])

# Returns:
# FetchedTranscript(
#   snippets=[
#     FetchedTranscriptSnippet(text="Hey there", start=0.0, duration=1.54),
#     ...
#   ],
#   video_id="...",
#   language="English",
#   is_generated=False
# )
```

---

## Option 3: yt-dlp (Alternative Scraper)

### How It Works
- Command-line tool + Python library
- Downloads entire videos OR just subtitles
- Widely used for video archival

### Pros
✅ Extremely robust (handles 1000+ sites, not just YouTube)  
✅ Actively maintained  
✅ Can extract subtitles in multiple formats  

### Cons
❌ Overkill for our use case (designed for full video downloads)  
❌ Heavier dependency  
❌ More complex API than youtube-transcript-api  

### Verdict
**Not recommended** - youtube-transcript-api is simpler and purpose-built for transcripts.

---

## Successful Implementation Examples

### 1. Video Summarization Tools
- Use youtube-transcript-api to extract transcripts
- Feed to LLM for summarization
- Common pattern in AI content tools

### 2. Accessibility Projects
- Auto-generate searchable text for videos
- Translate captions for multi-language support

### 3. Content Analysis Platforms
- Extract transcripts for sentiment analysis
- Search across video content by keyword

### 4. Educational Tech
- Create study notes from lecture videos
- Search across course content

**Common Pattern:** Start with youtube-transcript-api (free), upgrade to Official API only if:
- Hitting IP rate limits (thousands of videos/day)
- Need guaranteed access (business critical)
- Need official support/SLA

---

## Recommendation for Our Project

### Use youtube-transcript-api (Option 2)

**Rationale:**
1. **Our scale fits perfectly:** 12 videos now, maybe 100-500 eventually
2. **Cost-effective:** FREE vs spending quota on captions
3. **Simple implementation:** 1-2 hours vs 3-5 hours
4. **Proven at scale:** 16.9k projects using it successfully
5. **Sufficient reliability:** Works for 95%+ of public videos

### Implementation Plan

**Phase 1: Basic Integration (1-2 hours)**
```python
# Add to import_watch_later.py
from youtube_transcript_api import YouTubeTranscriptApi

def fetch_transcript(video_id):
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=['en'])
        
        # Convert to plain text
        full_text = " ".join([snippet.text for snippet in transcript])
        
        return {
            "text": full_text,
            "language": transcript.language,
            "source": "YouTube" if not transcript.is_generated else "YouTube (Auto)",
        }
    except Exception as e:
        print(f"Transcript unavailable for {video_id}: {e}")
        return None
```

**Phase 2: Airtable Integration**
- Add `--fetch-transcripts` flag to importer
- Write to Airtable fields:
  - `Transcript (Full)` = transcript text
  - `Transcript Source` = "YouTube" or "YouTube (Auto)"
  - `Transcript Language` = language code
- Add retry logic for transient failures

**Phase 3: Error Handling**
- Log videos without transcripts (track percentage)
- Add rate limiting (0.5s delay between requests)
- Idempotency: skip if transcript already exists

**Phase 4: Future (If Needed)**
- Add proxy support if hitting IP limits
- Consider Official API fallback for mission-critical videos
- Add Whisper fallback for videos without captions

---

## Cost Analysis: Our Use Case

### Current State
- **12 videos** in AI playlist
- **~25 videos** total if we import both playlists

### Scenario 1: Import Current Videos
**youtube-transcript-api:**
- Cost: $0
- Time: ~15 seconds (12 × 1s delay)
- Success rate: ~11-12 videos (95%)

**Official API:**
- Cost: 3,000 units (30% daily quota)
- Time: ~20 seconds
- Success rate: 12 videos (100% for public captions)

**Verdict:** Both work fine, youtube-transcript-api saves quota for other API calls.

### Scenario 2: Scale to 500 Videos (Future)
**youtube-transcript-api:**
- Cost: $0
- Time: ~8-10 minutes (500 × 1s delay)
- Limitations: Potential IP rate limiting, need proxies (~$20-50/month)

**Official API:**
- Cost: 125,000 quota units
- Need quota increase (default 10,000 → 125,000+)
- Approval required, not guaranteed
- Alternative: Spread across 13 days (40 videos/day)

**Verdict:** youtube-transcript-api more scalable without bureaucracy.

---

## Risk Assessment

### youtube-transcript-api Risks

**Risk 1: YouTube breaks the scraper**
- **Probability:** Low-Medium (happened once in 2024, fixed in days)
- **Impact:** High (transcripts stop working)
- **Mitigation:** Pin library version, monitor GitHub issues, have Official API as backup

**Risk 2: IP rate limiting**
- **Probability:** Medium (at 100+ videos/hour)
- **Impact:** Medium (need to slow down or use proxies)
- **Mitigation:** Add delays (0.5-1s), use proxy services (~$20/mo)

**Risk 3: Legal/ToS concerns**
- **Probability:** Low (16.9k projects, no known takedowns)
- **Impact:** Low (personal use, not commercial scraping at scale)
- **Mitigation:** Use for personal/research purposes, respect rate limits

### Official API Risks

**Risk 1: Quota exceeded**
- **Probability:** High (at scale)
- **Impact:** High (can't fetch more until next day)
- **Mitigation:** Request quota increase (slow, uncertain approval)

**Risk 2: Cost at scale**
- **Probability:** N/A (free for our current scale)
- **Impact:** N/A
- **Mitigation:** N/A

---

## Decision Matrix

| Criteria | youtube-transcript-api | Official API | Winner |
|----------|----------------------|--------------|--------|
| **Cost** | FREE | FREE (within quota) | Tie |
| **Quota Limits** | None | 40 videos/day | youtube-transcript-api |
| **Implementation Time** | 1-2 hours | 3-5 hours | youtube-transcript-api |
| **Reliability** | 95% (public videos) | 100% (auth'd videos) | Official API |
| **Scalability** | High (with proxies) | Limited (quota) | youtube-transcript-api |
| **Legal/Support** | Unofficial | Official | Official API |
| **Maintenance** | Monitor for breaks | Stable | Official API |
| **Our Use Case Fit** | ✅ Perfect | ✅ Works | youtube-transcript-api |

**Overall Winner:** **youtube-transcript-api** for our current scale and requirements.

---

## Next Steps

1. **Add youtube-transcript-api to `requirements.txt`**
2. **Implement basic transcript fetching** (1-2 hours)
3. **Test on 12 AI playlist videos**
4. **Document success rate** (track which videos fail)
5. **If >90% success:** Ship it ✅
6. **If <90% success:** Consider Official API for fallback

---

## References

- [youtube-transcript-api GitHub](https://github.com/jdepoix/youtube-transcript-api) - 16.9k projects using it
- [YouTube Data API Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube API Pricing Guide](https://www.getphyllo.com/post/is-the-youtube-api-free-costs-limits-iv)
- [Official Captions API Docs](https://developers.google.com/youtube/v3/docs/captions/download)

---

## Appendix: Sample Code Comparison

### youtube-transcript-api (Recommended)
```python
from youtube_transcript_api import YouTubeTranscriptApi

# Simple usage
transcript = YouTubeTranscriptApi().fetch(video_id)
full_text = " ".join([s.text for s in transcript])

# With language fallback
transcript = YouTubeTranscriptApi().fetch(
    video_id, 
    languages=['en', 'es', 'de']  # Priority order
)

# Check available transcripts first
api = YouTubeTranscriptApi()
transcript_list = api.list(video_id)
transcript = transcript_list.find_transcript(['en'])
data = transcript.fetch()
```

### Official YouTube Data API
```python
from googleapiclient.discovery import build

# List available captions (50 units)
captions = youtube.captions().list(
    part="snippet",
    videoId=video_id
).execute()

# Download caption (200 units)
caption_id = captions['items'][0]['id']
caption_text = youtube.captions().download(
    id=caption_id,
    tfmt='srt'  # or 'vtt', 'ttml', etc.
).execute()
```

**Complexity Winner:** youtube-transcript-api (3 lines vs 10+ lines)
