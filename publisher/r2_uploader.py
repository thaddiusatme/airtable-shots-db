"""Cloudflare R2 uploader for scene boundary frame PNGs.

Uploads first/last frame images to R2 (S3-compatible) and returns
public URLs suitable for Airtable attachment fields.

Usage:
    from publisher.r2_uploader import R2Config, create_s3_client, upload_scene_frames
    config = R2Config(account_id="...", access_key_id="...", secret_access_key="...",
                      bucket_name="shot-image", public_url="https://pub-xxx.r2.dev")
    client = create_s3_client(config)
    url_map = upload_scene_frames(client, config, capture_dir, analysis)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3

logger = logging.getLogger(__name__)


class R2UploadError(Exception):
    """Raised when an R2 upload operation fails."""

    pass


@dataclass
class R2Config:
    """Configuration for Cloudflare R2 bucket access."""

    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    public_url: str

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


def create_s3_client(config: R2Config):
    """Create a boto3 S3 client configured for Cloudflare R2.

    Args:
        config: R2 configuration with credentials and endpoint.

    Returns:
        boto3 S3 client instance.
    """
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
    )


def upload_frame(
    s3_client,
    config: R2Config,
    capture_dir: str,
    video_id: str,
    filename: str,
) -> str:
    """Upload a single frame PNG to R2.

    Args:
        s3_client: boto3 S3 client.
        config: R2 configuration.
        capture_dir: Path to the capture directory.
        video_id: YouTube video ID (used as object key prefix).
        filename: Frame filename (e.g., "frame_00000_t000.000s.png").

    Returns:
        Public URL for the uploaded object.

    Raises:
        R2UploadError: If the file is missing or upload fails.
    """
    file_path = Path(capture_dir) / filename
    if not file_path.exists():
        raise R2UploadError(f"Frame file not found: {file_path}")

    object_key = f"{video_id}/{filename}"

    try:
        s3_client.upload_file(
            Filename=str(file_path),
            Bucket=config.bucket_name,
            Key=object_key,
            ExtraArgs={"ContentType": "image/png"},
        )
    except Exception as e:
        raise R2UploadError(
            f"R2 upload failed for {filename}: {e}"
        ) from e

    public_url = f"{config.public_url}/{object_key}"
    logger.debug("Uploaded %s → %s", filename, public_url)
    return public_url


def upload_scene_frames(
    s3_client,
    config: R2Config,
    capture_dir: str,
    analysis: dict[str, Any],
) -> dict[str, str]:
    """Upload all boundary frames (firstFrame + lastFrame) for each scene.

    Deduplicates shared frames (e.g., adjacent scenes sharing a boundary).

    Args:
        s3_client: boto3 S3 client.
        config: R2 configuration.
        capture_dir: Path to the capture directory.
        analysis: Parsed analysis dict with scenes.

    Returns:
        Dict mapping filename → public URL for all uploaded frames.
    """
    video_id = analysis["videoId"]
    scenes = analysis.get("scenes", [])

    # Collect unique filenames
    filenames: set[str] = set()
    for scene in scenes:
        filenames.add(scene["firstFrame"])
        filenames.add(scene["lastFrame"])

    # Upload each unique frame
    url_map: dict[str, str] = {}
    for filename in sorted(filenames):
        url = upload_frame(s3_client, config, capture_dir, video_id, filename)
        url_map[filename] = url

    logger.info("Uploaded %d frames to R2", len(url_map))
    return url_map


def build_attachment_urls(
    analysis: dict[str, Any],
    url_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Build Airtable attachment field values for each scene.

    Args:
        analysis: Parsed analysis dict with scenes.
        url_map: Dict mapping filename → public URL.

    Returns:
        List of dicts (one per scene) with "Scene Start" and/or "Scene End"
        keys containing Airtable attachment format: [{"url": "..."}].
        Keys are omitted if the filename has no URL in the map.
    """
    result: list[dict[str, Any]] = []

    for scene in analysis.get("scenes", []):
        attachments: dict[str, Any] = {}

        first_url = url_map.get(scene["firstFrame"])
        if first_url:
            attachments["Scene Start"] = [{"url": first_url}]

        last_url = url_map.get(scene["lastFrame"])
        if last_url:
            attachments["Scene End"] = [{"url": last_url}]

        result.append(attachments)

    return result
