# Shot Image Attachments via Cloudflare R2

## Summary

Add shot frame images to Airtable Shot records by uploading boundary frame PNGs to Cloudflare R2 and writing the public URLs to the `Scene Start` and `Scene End` attachment fields.

Currently, the publisher creates 1 Shot record per scene with metadata (labels, timestamps, AI descriptions) but no images. Viewing the shot list in Airtable requires cross-referencing frame filenames on disk — the shot list should be self-contained with visible thumbnails.

## Context

- **Publisher** (`publisher/publish.py`) creates 1 Shot record per scene from `analysis.json`
- Each scene has `firstFrame` and `lastFrame` filenames in `analysis.json`
- **Shots table** already has two attachment fields: `Scene Start` and `Scene End` (`multipleAttachments`)
- **Airtable attachment fields** require publicly accessible URLs — Airtable downloads and stores its own copy
- **Frame PNGs** exist on disk in the capture directory (e.g., `frame_00000_t000.000s.png`)

## Why Cloudflare R2

- **Zero egress fees** — Airtable downloading images costs nothing
- **S3-compatible API** — use `boto3` (Python), same SDK as AWS S3
- **Generous free tier** — 10GB storage, 10M reads/month
- **Already planned** — `ISSUE_SHOT_LIST_PIPELINE.md` Phase 5 specifies S3/GCS

### Budget estimate

| Video length | Scenes | Boundary frames | Size (~200KB each) |
|---|---|---|---|
| 5 min | ~10 | ~20 | ~4 MB |
| 20 min | ~34 | ~68 | ~14 MB |
| 30 min | ~50 | ~100 | ~20 MB |

100 videos × 14 MB avg = **1.4 GB** (well within 10 GB free tier)

## Implementation Plan

### Prerequisites

- [x] Cloudflare account with R2 enabled
- [x] R2 bucket created: `shot-image`
- [x] R2 API token with read/write access (credentials in `.env`)
- [x] `Scene Start` and `Scene End` attachment fields exist in Shots table
- [x] `boto3>=1.35.0` added to `requirements.txt`

### P0 — Core upload + attach ✅ COMPLETE

**Task 1: R2 upload module** ✅
- ✅ New module: `publisher/r2_uploader.py`
- ✅ `R2Config` dataclass for credentials
- ✅ `create_s3_client(config)` — boto3 S3 client with R2 endpoint
- ✅ `upload_frame(s3_client, config, capture_dir, video_id, filename)` → public URL
- ✅ `upload_scene_frames(s3_client, config, capture_dir, analysis)` → dict[filename, url]
- ✅ `build_attachment_urls(analysis, url_map)` → Airtable attachment format
- ✅ Object key format: `{videoId}/{filename}`
- ✅ ContentType: `image/png`
- ✅ Public URL: `https://pub-f300f74e400541688f70ad8bb42b106e.r2.dev/{videoId}/{filename}`
- ✅ Deduplicates shared boundary frames (67 uploads for 34 scenes)

**Task 2: Integrate into publisher** ✅
- ✅ `publish_to_airtable()` accepts optional `r2_config` parameter
- ✅ `build_shot_records()` accepts optional `attachment_urls` parameter
- ✅ Scene Start / Scene End attachments merged into Shot records before Airtable create
- ✅ Upload happens before Shot record creation
- ✅ `--skip-images` flag added to CLI
- ✅ R2UploadError wrapped into PublisherError

**Task 3: Credential management** ✅
- ✅ Environment variables: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`
- ✅ CLI auto-detects R2 env vars (no flags needed)
- ✅ Graceful fallback: logs "R2 credentials not set" if missing

### P1 — Polish

**Task 4: Idempotent uploads**
- Check if object already exists in R2 before uploading (HEAD request)
- Skip upload if same filename already in bucket (saves bandwidth on re-runs)

**Task 5: Thumbnail generation**
- Optionally resize frames before upload (e.g., 640px wide for Airtable thumbnails)
- Keep originals in R2 under `{videoId}/full/` and thumbnails under `{videoId}/thumb/`
- Requires `Pillow` dependency

**Task 6: Cleanup**
- Delete R2 objects when publisher deletes Shot records (idempotent re-run)
- `delete_shot_frames(bucket, videoId)` before re-upload

## TDD Cycle Plan

**Red Phase:** ✅ COMPLETE
- ✅ `tests/test_r2_uploader.py` — 18 tests, all passing
  - ✅ R2Config dataclass tests
  - ✅ create_s3_client() with correct endpoint/credentials
  - ✅ upload_frame() with correct key, ContentType, public URL
  - ✅ upload_scene_frames() deduplication + boundary frames only
  - ✅ build_attachment_urls() Airtable format
  - ✅ Error handling: missing file, upload failure
- ✅ Mocked `boto3.client` at module level

**Green Phase:** ✅ COMPLETE
- ✅ Implemented `publisher/r2_uploader.py` (177 lines)
- ✅ Integrated into `publish_to_airtable()` with optional r2_config
- ✅ Added `--skip-images` flag to CLI
- ✅ Real-data validated: 67 frames uploaded, 34 Shot records with thumbnails

**Refactor Phase:** ✅ COMPLETE
- ✅ R2Config dataclass for credentials
- ✅ Debug logging for each frame upload
- ✅ Info logging for total frames uploaded
- ⏸️ Idempotent upload (HEAD check) — deferred to P1

## Acceptance Criteria

- [x] Boundary frame PNGs uploaded to R2 bucket under `{videoId}/` prefix
- [x] Shot records in Airtable display frame thumbnails in `Scene Start` and `Scene End` fields
- [x] Re-running publisher replaces Shot records (images re-uploaded, not deduplicated yet)
- [x] `--skip-images` flag skips upload for fast metadata-only publishes
- [x] `--dry-run` reports which images would be uploaded without uploading
- [x] Tests: 18 unit tests with mocked boto3, no real R2 calls in test suite

## Environment Variables

```bash
# Add to .env (actual values in use)
R2_ACCOUNT_ID=7c07e5e41d224c81d5b4e8d9c6a5c97c
R2_ACCESS_KEY_ID=4b8055a16aabe90e19506bc28e406b64
R2_SECRET_ACCESS_KEY=bf987c7b16a96203e4be415211e49c761f360fe70dcc27ed4e8993bed9a5c399
R2_BUCKET_NAME=shot-image
R2_PUBLIC_URL=https://pub-f300f74e400541688f70ad8bb42b106e.r2.dev
```

## Dependencies

```
# Add to requirements.txt
boto3>=1.35.0
```

## Branch Strategy

```bash
git checkout feature/airtable-publisher
git checkout -b feature/shot-image-attachments
```

## References

- [Cloudflare R2 docs](https://developers.cloudflare.com/r2/)
- [boto3 S3 client with R2](https://developers.cloudflare.com/r2/examples/aws/boto3/)
- [Airtable attachment field API](https://airtable.com/developers/web/api/field-model#multipleattachment)
- `ISSUE_SHOT_LIST_PIPELINE.md` — Phase 5 spec
- `publisher/publish.py` — current publisher (attach point for image upload)
