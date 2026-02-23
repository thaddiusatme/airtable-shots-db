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

- [ ] Cloudflare account with R2 enabled
- [ ] R2 bucket created (e.g., `yt-shots`)
- [ ] R2 API token with read/write access (Account ID, Access Key ID, Secret Access Key)
- [ ] `Scene Start` and `Scene End` attachment fields already exist in Shots table — no Airtable changes needed
- [ ] Add `boto3` to `requirements.txt`

### P0 — Core upload + attach

**Task 1: R2 upload module**
- New module: `publisher/r2_uploader.py`
- `upload_frame(bucket, capture_dir, filename) → public_url`
- `upload_shot_frames(bucket, capture_dir, analysis) → dict[filename, url]`
- Use `boto3` S3 client with R2 endpoint (`https://<account_id>.r2.cloudflarestorage.com`)
- Object key format: `{videoId}/{filename}` (e.g., `KGHoVptow30/frame_00000_t000.000s.png`)
- Set `ContentType: image/png` on upload
- Return public URL from R2 custom domain or `r2.dev` subdomain

**Task 2: Integrate into publisher**
- After `build_shot_records()`, enrich each Shot record with two attachment fields:
  - `"Scene Start": [{"url": "https://...r2.dev/KGHoVptow30/frame_00000_t000.000s.png"}]`
  - `"Scene End": [{"url": "https://...r2.dev/KGHoVptow30/frame_00020_t020.000s.png"}]`
- Upload only boundary frames (firstFrame + lastFrame per scene), not all captured frames
- For a 34-scene video: 68 uploads total (34 start + 34 end), but only 34 Shot records
- Add `--skip-images` flag to publisher CLI (skip upload for faster testing)

**Task 3: Credential management**
- Environment variables: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- CLI flags: `--r2-bucket`, `--r2-account-id` (or read from env)
- Validate credentials before upload attempt

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

**Red Phase:**
- `tests/test_r2_uploader.py`:
  - `upload_frame()` calls `s3_client.upload_file()` with correct key and content type
  - `upload_shot_frames()` uploads only boundary frames referenced in analysis
  - Returns correct public URL format
  - Error handling: missing file, upload failure, invalid credentials
- Mock `boto3.client` at module level

**Green Phase:**
- Implement `publisher/r2_uploader.py`
- Wire into `publish_to_airtable()` — upload frames, add URLs to shot records
- Add `--skip-images` flag to CLI

**Refactor Phase:**
- Extract R2 config to constants
- Add progress logging for multi-frame uploads
- Idempotent upload (HEAD check before PUT)

## Acceptance Criteria

- [ ] Boundary frame PNGs uploaded to R2 bucket under `{videoId}/` prefix
- [ ] Shot records in Airtable display frame thumbnails in `Shot Image` field
- [ ] Re-running publisher replaces images (idempotent)
- [ ] `--skip-images` flag skips upload for fast metadata-only publishes
- [ ] `--dry-run` reports which images would be uploaded without uploading
- [ ] Tests: unit tests with mocked boto3, no real R2 calls in test suite

## Environment Variables

```bash
# Add to .env
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET_NAME=yt-shots
R2_PUBLIC_URL=https://yt-shots.your-domain.workers.dev
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
