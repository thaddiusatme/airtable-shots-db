# Create Frames Table Schema in Airtable

## Summary
Add the **Frames table** to the Airtable base schema to support per-second frame record creation for video timeline navigation.

## Problem Statement
The Frames table feature has been fully implemented in the publisher (commits `6539a04`, `582db8e`, `4504887`, `7b6343d`) with 117 passing tests, but the table **does not exist in the Airtable base**. 

Attempting to publish Frames results in:
```
Airtable API error: 403 Forbidden
INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND
```

The publisher is ready to create Frame records, but the schema must be set up first.

## What is the Frames Table?

The Frames table stores **1 frame record per second of video** (configurable via `--frame-sampling`), providing:

- **Granular timeline navigation** - Jump to any second in a video
- **Visual video index** - Browse all frames with R2-hosted images
- **Shot context** - See which frames belong to which shots
- **Timestamp search** - Query frames by time range

### Example Use Cases
1. Find all frames between 1:30 - 2:00 in a video
2. Browse all frames for a specific shot/scene
3. Visual video scrubbing interface in Airtable
4. Frame-by-frame annotation workflows

## Required Schema

### Table Definition
```python
{
    "name": "Frames",
    "description": "Per-second frame captures for video timeline navigation",
    "fields": [{"name": "Frame Key", "type": "singleLineText"}]
}
```

### Fields to Add

| Field Name | Type | Options | Description |
|------------|------|---------|-------------|
| **Frame Key** | singleLineText | - | Unique identifier: `{videoId}_t{timestamp:06d}` |
| **Video** | multipleRecordLinks | linkedTableId: Videos | Parent video record |
| **Shot** | multipleRecordLinks | linkedTableId: Shots | Parent shot/scene record |
| **Timestamp (sec)** | number | precision: 0 | Timestamp in seconds (integer) |
| **Timestamp (hh:mm:ss)** | singleLineText | - | Human-readable timestamp (e.g., "0:01:23") |
| **Frame Image** | multipleAttachment | - | R2-hosted PNG image |
| **Source Filename** | singleLineText | - | Original filename from capture (e.g., `frame_00083_t083.000s.png`) |

### Relationships
```
Videos (1) ----< Frames (many)
Shots (1) ----< Frames (many)
```

Each Frame links to:
- **1 Video** (required) - The source video
- **0-1 Shot** (optional) - The shot/scene containing this frame

## Implementation

### Option 1: Update setup_airtable.py (Recommended)

Add to `build_schema()` function in `setup_airtable.py`:

```python
# Step 1: Add Frames table to initial_tables list (around line 53)
initial_tables = [
    {
        "name": "Channels",
        "description": "Creators/Platforms",
        "fields": [{"name": "Channel Name", "type": "singleLineText"}]
    },
    {
        "name": "Videos",
        "description": "Source Videos",
        "fields": [{"name": "Video Title", "type": "singleLineText"}]
    },
    {
        "name": "Shots",
        "description": "Swipe file for video shots (screenshots)",
        "fields": [{"name": "Shot Label", "type": "singleLineText"}]
    },
    {
        "name": "Frames",
        "description": "Per-second frame captures for video timeline navigation",
        "fields": [{"name": "Frame Key", "type": "singleLineText"}]
    }
]

# Step 2: Get Frames table ID after schema fetch (around line 69)
frames_table_id = next(t.id for t in schema.tables if t.name == "Frames")

# Step 3: Add Frames table fields (after Shots table setup, around line 161)
print("\nStep 5: Adding schema to 'Frames' table...")
# Linking
create_field(base_id, frames_table_id, {
    "name": "Video",
    "type": "multipleRecordLinks",
    "options": {"linkedTableId": videos_table_id}
})
create_field(base_id, frames_table_id, {
    "name": "Shot",
    "type": "multipleRecordLinks",
    "options": {"linkedTableId": shots_table_id}
})

# Timestamps
create_field(base_id, frames_table_id, {
    "name": "Timestamp (sec)",
    "type": "number",
    "options": {"precision": 0}
})
create_field(base_id, frames_table_id, {
    "name": "Timestamp (hh:mm:ss)",
    "type": "singleLineText"
})

# Image + metadata
create_field(base_id, frames_table_id, {
    "name": "Frame Image",
    "type": "multipleAttachment"
})
create_field(base_id, frames_table_id, {
    "name": "Source Filename",
    "type": "singleLineText"
})
```

Then run:
```bash
python setup_airtable.py
```

### Option 2: Manual Creation in Airtable

1. Go to your Airtable base
2. Click **"+ Add or import"** → **"Create empty table"**
3. Name it **"Frames"**
4. Add fields using the table above
5. Set up relationships to Videos and Shots tables

## Validation

After creating the table, verify the schema:

```bash
# Run a test publish with frame sampling (to limit volume)
python -m publisher \
  --capture-dir captures/bjdBVZa66oU_what-are-skills_2026-03-02_0952 \
  --api-key "$AIRTABLE_API_KEY" \
  --base-id "$AIRTABLE_BASE_ID" \
  --frame-sampling 30 \
  --max-concurrent-uploads 4
```

Expected output:
```
Uploaded 34 frames to R2 (all frames)
Created 34 Frame records
Published to Airtable:
  Video ID: bjdBVZa66oU
  Shots created: 34
  Frames created: 34
```

Check Airtable:
- ✅ Frames table exists
- ✅ 34 Frame records created
- ✅ Frame Image field shows R2 images
- ✅ Video and Shot links populated

## Example Frame Record

```json
{
  "Frame Key": "bjdBVZa66oU_t000060",
  "Video": ["recUefPkqk9EU2MI3"],
  "Shot": ["recJQkqtgxMgC8BFg"],
  "Timestamp (sec)": 60,
  "Timestamp (hh:mm:ss)": "0:01:00",
  "Frame Image": [{
    "url": "https://pub-f300f74e400541688f70ad8bb42b106e.r2.dev/bjdBVZa66oU/frame_00060_t060.000s.png"
  }],
  "Source Filename": "frame_00060_t060.000s.png"
}
```

## Performance Impact

### Database Size Estimates

| Video Length | Frame Sampling | Records Created | Storage Impact |
|--------------|----------------|-----------------|----------------|
| 3 minutes | 1 per second | ~180 records | ~18 KB |
| 10 minutes | 1 per second | ~600 records | ~60 KB |
| 10 minutes | 1 per 5 seconds | ~120 records | ~12 KB |

**Recommendation:** Use default 1-per-second for videos < 5 minutes, use `--frame-sampling 5` for longer videos.

### R2 Storage
- **Average frame size:** 50-400 KB PNG
- **3-minute video @ 1fps:** ~180 frames × 200 KB avg = **~36 MB**
- **10-minute video @ 5fps:** ~120 frames × 200 KB avg = **~24 MB**

## Dependencies

**Required before implementing:**
- ✅ Videos table (exists)
- ✅ Shots table (exists)
- ✅ R2 bucket configured (exists: `shot-image`)
- ✅ Publisher code complete (117 tests passing)

**Blocks:**
- Chrome extension Frame integration (#18)
- End-to-end pipeline testing with Frames

## Success Criteria

- [ ] Frames table exists in Airtable base
- [ ] All 7 fields created with correct types
- [ ] Video and Shot relationships configured
- [ ] Test publish creates Frame records successfully
- [ ] Frame images load from R2 URLs in Airtable
- [ ] No API errors when running publisher with Frames

## Rollback Plan

If issues arise, disable Frame creation:
```bash
python -m publisher --skip-frames ...
```

The `--skip-frames` flag allows the publisher to run without Frame creation, falling back to Shots-only mode.

## Related Issues

- **PR/Commits:** Frames feature implementation (commits `6539a04`, `582db8e`, `4504887`, `7b6343d`)
- **Related:** Chrome Extension Integration (#18) - blocked by this issue
- **Docs:** `docs/GITHUB_ISSUE_FRAMES_CHROME_EXTENSION.md`

## Labels
`schema`, `airtable`, `frames`, `prerequisite`, `backend`

## Assignee
@thaddius

## Priority
**High** - Blocks chrome extension integration and end-to-end testing
