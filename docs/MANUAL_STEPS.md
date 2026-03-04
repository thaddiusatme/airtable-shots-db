# Manual Steps Required

## Base Created Successfully! 🎉

**Base ID**: `appWSbpJAxjCyLfrZ`  
**Base URL**: https://airtable.com/appWSbpJAxjCyLfrZ

---

## ⚠️ Manual Steps Required (API Limitations)

The Airtable API has limitations that prevent automatic creation of certain field types. You'll need to manually add the following fields:

### 1. Formula Fields (3 fields)

#### Channels Table
- **Field Name**: `Channel UID`
- **Type**: Formula
- **Formula**: `LOWER(SUBSTITUTE({Channel Name}," ","")) & "|" & {Platform}`
- **Purpose**: Unique deduplication ID for channels

#### Videos Table
- **Field Name**: `Video UID`
- **Type**: Formula
- **Formula**: `{Platform} & "|" & {Video ID}`
- **Purpose**: Unique deduplication ID for videos

#### Shots Table
- **Field Name**: `Shot UID`
- **Type**: Formula
- **Formula**: `{Video UID} & "|" & ROUND({Timestamp (sec)}, 0)`
- **Purpose**: Unique deduplication ID for shots

### 2. Attachment Field (1 field)

#### Shots Table
- **Field Name**: `Shot Image`
- **Type**: Attachment (Multiple attachments)
- **Purpose**: Store screenshot images of video shots

---

## How to Add These Fields

1. Open your base: https://airtable.com/appWSbpJAxjCyLfrZ
2. Navigate to each table mentioned above
3. Click the **+** button to add a new field
4. For formula fields:
   - Select "Formula" as the field type
   - Copy/paste the formula exactly as shown above
5. For the attachment field:
   - Select "Attachment" as the field type
   - Enable "Allow multiple attachments"

---

## ✅ What Was Successfully Created

- **3 Tables**: Channels, Videos, Shots
- **30+ Fields** across all tables including:
  - Linking fields between tables
  - Categorization fields (Shot Function, Type, Camera Angle, etc.)
  - AI workflow fields (AI Status, AI Description, AI JSON, etc.)
  - Transcript management fields
  - Timestamp and metadata fields
  - Operational fields (Capture Method, Source Device, etc.)

---

## Next Steps

1. Complete the manual field additions above
2. Your base will be ready for AI VLM integration
3. Start adding video shots and let your local AI process them!
