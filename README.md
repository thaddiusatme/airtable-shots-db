# Airtable Video Shots Swipe File Script

This repository contains a simple initialization script to stand up a normalized Airtable Base for a Video/Shots Swipe File. 

The created schema separates the base intro three primary tables:
- **Channels**: The creators/platforms.
- **Videos**: The source videos.
- **Shots**: The individual swipes, containing all the visual classifications, tags, AI operation flags, and transcript notes.

This normalized setup exists so that your local AI system (e.g., Vision Language Models) does not have to repeatedly process or manage duplicated Video Metadata/Transcripts for multiple shots from the same video.

## Prerequisites
- Python 3.9+
- An Airtable account
- An Airtable Personal Access Token (PAT) with the `schema.bases:write` scope.

## Setup

1. Clone the repository and navigate into the directory.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory:
   ```bash
   touch .env
   ```
5. Add your credentials to `.env`:
   ```env
   AIRTABLE_API_KEY=patYOUR_PERSONAL_ACCESS_TOKEN
   AIRTABLE_WORKSPACE_ID=wspYOUR_WORKSPACE_ID
   ```
   *Note: You can find your Workspace ID in the URL when viewing your workspace on the Airtable home screen (it starts with `wsp...`).*

## Running the Script

Run the initializer script:

```bash
python setup_airtable.py
```

The script will:
1. Create a brand new Base named "Video Swipe File".
2. Create the `Channels`, `Videos`, and `Shots` tables.
3. Rapidly add all 26+ columns utilizing the Airtable Schema API.

### ⚠️ Manual Step Required

Due to a limitation in the Airtable API (which frequently blocks attachment field creation from scratch), the script **will not** create the `Shot Image` attachment field.

After running the script:
1. Open your new Airtable Base.
2. Navigate to the **Shots** table.
3. Manually add a field named **Shot Image** with the type **Attachment**. 

This allows your local VLM to push screenshots directly into that field.
