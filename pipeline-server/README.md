# Pipeline Server

Local orchestration server that bridges the Chrome extension with the full shot-list pipeline (capture → analyze → publish).

## Setup

```bash
cd pipeline-server
npm install
```

### Required Environment Variables

These are read from `../.env` (the project root). Make sure your `.env` includes:

```bash
# Airtable
AIRTABLE_API_KEY=patXXXXXXXXXXXXXX
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX

# Cloudflare R2
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# Path to yt-frame-poc repo (absolute)
YT_FRAME_POC_PATH=/Users/you/repos/yt-frame-poc
```

Optional:

```bash
PIPELINE_PORT=3333  # default
```

### Prerequisites

- `yt-frame-poc` repo with `npm install` + `npx playwright install` done
- Python venv at `../.venv/` with analyzer + publisher deps installed
- Ollama running (`ollama serve`) with `llama3.2-vision:latest`

## Running

```bash
# From pipeline-server/
npm start

# Or with auto-reload during development
npm run dev
```

Server listens on `http://127.0.0.1:3333`.

## API

### `GET /health`

Returns `{ "status": "ok", "timestamp": "..." }`.

### `POST /pipeline/run`

Starts a full pipeline run. Request body:

```json
{
  "videoUrl": "https://www.youtube.com/watch?v=VIDEO_ID",
  "videoId": "VIDEO_ID",
  "videoTitle": "Video Title",
  "transcript": "Full transcript text...",
  "capture": {
    "interval": 5,
    "maxFrames": 100
  }
}
```

Returns: `{ "runId": "uuid" }`

Pipeline steps (executed sequentially):
1. Upsert Video record in Airtable (with transcript)
2. Capture frames via `yt-frame-poc` Playwright CLI
3. Analyze scenes via Python `analyzer` (OpenCV + Ollama VLM)
4. Publish shots via Python `publisher` (Airtable + R2)

### `GET /pipeline/status/:runId`

Returns job status:

```json
{
  "runId": "uuid",
  "status": "queued|running|done|error",
  "message": "Current step description",
  "error": null,
  "captureDir": "/path/to/captures/...",
  "createdAt": "...",
  "updatedAt": "..."
}
```

### `GET /pipeline/jobs`

Lists the 20 most recent jobs.

## Chrome Extension Integration

The Chrome extension calls this server when the user clicks **"Run Full Pipeline"**:

1. Extension extracts transcript from YouTube DOM
2. Extension POSTs transcript + capture options to `/pipeline/run`
3. Extension polls `/pipeline/status/:runId` every 3 seconds
4. Extension shows progress and completion status

The extension checks `/health` on popup open and shows an offline message if the server is not running.
