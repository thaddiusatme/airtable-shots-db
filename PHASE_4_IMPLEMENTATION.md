# Phase 4: Transcript Segmentation - Implementation Summary

## Overview

Phase 4 adds transcript segmentation to the YouTube Shot List Pipeline, enabling each Shot record in Airtable to contain the transcript text spoken during that scene's timeframe.

## Implementation Status: ✅ COMPLETE

All components implemented and tested. 140 tests passing (including 10 new transcript segmenter tests).

## What Was Built

### 1. Chrome Extension Updates
**Files Modified:**
- `chrome-extension/content.js` - Added timestamp extraction from YouTube DOM
- `chrome-extension/popup.js` - Save timestamped transcript data to Airtable

**Key Features:**
- Extracts both text and timestamps from `ytd-transcript-segment-renderer` elements
- Parses timestamps from "M:SS" or "H:MM:SS" format to seconds
- Stores structured data: `[{text: "...", start: 5.2}, ...]`
- Backward compatible - keeps existing `Transcript (Full)` field

### 2. Segmenter Module
**Files Created:**
- `segmenter/__init__.py`
- `segmenter/transcript_segmenter.py`
- `tests/test_transcript_segmenter.py`

**Core Algorithm:**
```python
def segment_transcript_by_scenes(
    timestamped_transcript: str,  # JSON from Videos table
    scenes: list[dict]             # From analysis.json
) -> dict[int, str]:               # scene_index → transcript_text
```

**Logic:**
- Parse JSON transcript: `[{"text": "...", "start": 5.2}, ...]`
- For each scene, find segments where `start_sec <= seg_start < end_sec`
- Join matching segments into scene transcript text
- Handles edge cases: missing data, invalid JSON, malformed segments

### 3. Publisher Integration
**Files Modified:**
- `publisher/publish.py`
- `publisher/cli.py`

**New Features:**
- Added `segment_transcripts` parameter to `publish_to_airtable()`
- Fetches `Transcript (Timestamped)` from Videos table
- Calls segmenter to align transcript with scenes
- Populates `Transcript Line` field in Shot records
- Backward compatible - only runs when `--segment-transcripts` flag is used

### 4. Airtable Schema
**Files Modified:**
- `setup_airtable.py`

**New Field:**
- Videos table: `Transcript (Timestamped)` (multilineText) - stores JSON array

**Existing Fields Used:**
- Shots table: `Transcript Line` (multilineText) - populated by segmenter
- Shots table: `Transcript Start (sec)`, `Transcript End (sec)` - already populated

## Usage

### Step 1: Extract Transcript with Timestamps (Chrome Extension)
1. Navigate to YouTube video
2. Click extension icon → "Extract Transcript"
3. Extension saves to Airtable Videos table with timestamped data

### Step 2: Capture & Analyze (Existing Pipeline)
```bash
# Capture frames
cd /Users/thaddius/repos/2-21/yt-frame-poc
npm run capture -- <youtube-url> 1.0

# Analyze scenes
cd /Users/thaddius/repos/2-20/airtable-shots-db
.venv/bin/python -m analyzer --capture-dir ./captures/VIDEO_ID_*/
```

### Step 3: Publish with Transcript Segmentation
```bash
cd /Users/thaddius/repos/2-20/airtable-shots-db
set -a && source .env && set +a

.venv/bin/python -m publisher \
  --capture-dir ./captures/VIDEO_ID_*/ \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --segment-transcripts \
  -v
```

## Test Results

```
====================================================================== 140 passed in 0.89s ======================================================================
```

**Test Breakdown:**
- 10 new transcript segmenter tests
- 47 publisher tests (integration verified)
- 8 CLI tests (new flag tested)
- 75 existing tests (analyzer, VLM, R2 uploader)

**Test Coverage:**
- ✅ Basic transcript segmentation
- ✅ Empty scenes (no matching segments)
- ✅ Missing/invalid transcript data
- ✅ Boundary cases (segments at exact scene boundaries)
- ✅ Malformed segment objects
- ✅ Multiple scenes with complex overlaps

## Technical Details

### DOM Extraction (Chrome Extension)
```javascript
// Extract timestamp from YouTube DOM
const timestampEl = seg.querySelector('yt-formatted-string[has-link]') ||
                   seg.querySelector('a.yt-simple-endpoint') ||
                   seg.querySelector('.segment-timestamp');
const timestampStr = timestampEl?.textContent?.trim(); // "1:23"

// Convert to seconds
function parseTimestampToSeconds(timestamp) {
  const parts = timestamp.split(':').map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}
```

### Segmentation Logic (Python)
```python
# Find overlapping segments for each scene
for scene in scenes:
    start_sec = scene['startTimestamp']
    end_sec = scene['endTimestamp']
    
    matching_texts = []
    for seg in segments:
        seg_start = seg.get('start')
        # Include if segment starts within scene timeframe
        if start_sec <= seg_start < end_sec:
            matching_texts.append(seg['text'])
    
    scene_transcripts[scene_idx] = ' '.join(matching_texts)
```

## Edge Cases Handled

1. **No timestamped transcript** - Logs warning, skips segmentation, continues publishing
2. **Invalid JSON** - Catches JSONDecodeError, returns empty dict
3. **Scene with no matching segments** - Sets `Transcript Line` to empty string
4. **Very short scenes (<1s)** - May have no segments (empty string OK)
5. **Timestamp parsing failures** - Returns null for malformed timestamps
6. **DOM structure changes** - Multiple selectors for resilience

## Files Changed

```
chrome-extension/
├── content.js          # MODIFIED: Extract timestamps from DOM
└── popup.js            # MODIFIED: Save timestamped data

segmenter/
├── __init__.py         # NEW
└── transcript_segmenter.py  # NEW: Core segmentation logic

publisher/
├── publish.py          # MODIFIED: Integrate segmenter
└── cli.py              # MODIFIED: Add --segment-transcripts flag

tests/
└── test_transcript_segmenter.py  # NEW: 10 tests

setup_airtable.py       # MODIFIED: Add Transcript (Timestamped) field
```

## Next Steps

To use this feature in production:

1. **Reload Chrome Extension** - The updated extension needs to be reloaded in Chrome
2. **Add Airtable Field** - Manually add `Transcript (Timestamped)` field to existing Videos table (or run setup_airtable.py for new bases)
3. **Extract Transcripts** - Use updated Chrome extension to extract transcripts with timestamps
4. **Run Publisher** - Use `--segment-transcripts` flag when publishing

## Backward Compatibility

✅ **Fully backward compatible:**
- Chrome extension still saves `Transcript (Full)` (plain text)
- Publisher works without `--segment-transcripts` flag
- Existing workflows unchanged
- New feature is opt-in via CLI flag

## Dependencies

**No new dependencies added** - uses existing:
- Chrome extension (DOM extraction)
- pyairtable (already in requirements.txt)
- Standard library (json, typing)

## Performance

- Segmentation is fast: O(n*m) where n=scenes, m=segments
- Typical video: 30 scenes × 200 segments = 6000 comparisons (~1ms)
- No external API calls (uses local JSON data)
- Runs during publisher phase (after R2 uploads)
