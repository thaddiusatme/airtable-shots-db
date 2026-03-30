"""Upload generated storyboard images to R2 and create Airtable Storyboards records.

Handles:
- Uploading storyboard variant PNGs to R2
- Creating/updating Storyboards table records
- Linking to Videos and Shots tables
- Attaching R2 URLs to Airtable attachment fields
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyairtable import Table

from publisher.r2_uploader import R2Config

logger = logging.getLogger(__name__)


@dataclass
class StoryboardRecord:
    """Storyboard record data for Airtable."""
    
    video_id: str
    shot_label: str
    variant_label: str
    positive_prompt: str
    negative_prompt: str
    width: int
    height: int
    generator_version: str
    image_url: str
    video_record_id: str | None = None
    shot_record_id: str | None = None


def upload_storyboard_image(
    s3_client,
    config: R2Config,
    image_path: Path,
    video_id: str,
    shot_label: str,
    variant_label: str,
) -> str:
    """Upload a single storyboard image to R2.
    
    Args:
        s3_client: boto3 S3 client
        config: R2 configuration
        image_path: Path to generated PNG
        video_id: Video identifier
        shot_label: Shot label (e.g., "S03")
        variant_label: Variant label (e.g., "A", "B", "C")
        
    Returns:
        Public URL for the uploaded image
        
    Raises:
        Exception: If upload fails
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Storyboard image not found: {image_path}")
    
    object_key = f"storyboards/{video_id}/{shot_label}/{shot_label}_variant_{variant_label}.png"
    
    s3_client.upload_file(
        Filename=str(image_path),
        Bucket=config.bucket_name,
        Key=object_key,
        ExtraArgs={"ContentType": "image/png"},
    )
    
    public_url = f"{config.public_url}/{object_key}"
    logger.info("Uploaded storyboard → %s", public_url)
    
    return public_url


def create_storyboard_record(
    storyboards_table: Table,
    record: StoryboardRecord,
) -> str:
    """Create a Storyboards table record in Airtable.
    
    Args:
        storyboards_table: PyAirtable Table instance for Storyboards
        record: Storyboard record data
        
    Returns:
        Created record ID
    """
    fields: dict[str, Any] = {
        "Shot Label": record.shot_label,
        "Variant": record.variant_label,
        "Positive Prompt": record.positive_prompt,
        "Negative Prompt": record.negative_prompt,
        "Width": record.width,
        "Height": record.height,
        "Generator Version": record.generator_version,
    }
    
    if record.video_record_id:
        fields["Video"] = [record.video_record_id]
    
    if record.shot_record_id:
        fields["Shot"] = [record.shot_record_id]
    
    if record.image_url:
        fields["Image"] = [{"url": record.image_url}]
    
    created = storyboards_table.create(fields)
    logger.info(
        "Created Storyboard record %s for %s variant %s",
        created["id"],
        record.shot_label,
        record.variant_label,
    )
    
    return created["id"]


def upload_and_attach_storyboards(
    s3_client,
    r2_config: R2Config,
    storyboards_table: Table,
    video_id: str,
    shot_label: str,
    variant_outputs: list[str | None],
    variant_labels: list[str],
    payload: dict[str, Any],
    video_record_id: str | None = None,
    shot_record_id: str | None = None,
) -> list[str | None]:
    """Upload storyboard images and create Airtable records for one shot's variants.
    
    Args:
        s3_client: boto3 S3 client
        r2_config: R2 configuration
        storyboards_table: PyAirtable Table for Storyboards
        video_id: Video identifier
        shot_label: Shot label (e.g., "S03")
        variant_outputs: List of output file paths (or None for failed variants)
        variant_labels: List of variant labels matching outputs
        payload: Storyboard payload dict (for metadata)
        video_record_id: Airtable Video record ID (optional)
        shot_record_id: Airtable Shot record ID (optional)
        
    Returns:
        List of created Storyboard record IDs (None for failed variants)
    """
    record_ids: list[str | None] = []
    
    generation = payload["generation"]
    negative_prompt = payload["storyboard_negative"]
    generator_version = payload["metadata"].get("generator_version", "0.1")
    
    for variant_label, output_path in zip(variant_labels, variant_outputs):
        if output_path is None:
            record_ids.append(None)
            continue
        
        try:
            variant_data = next(
                v for v in payload["variants"] if v["label"] == variant_label
            )
            positive_prompt = variant_data["positive_prompt"]
            
            image_url = upload_storyboard_image(
                s3_client,
                r2_config,
                Path(output_path),
                video_id,
                shot_label,
                variant_label,
            )
            
            record = StoryboardRecord(
                video_id=video_id,
                shot_label=shot_label,
                variant_label=variant_label,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                width=generation["width"],
                height=generation["height"],
                generator_version=generator_version,
                image_url=image_url,
                video_record_id=video_record_id,
                shot_record_id=shot_record_id,
            )
            
            record_id = create_storyboard_record(storyboards_table, record)
            record_ids.append(record_id)
            
        except Exception as exc:
            logger.warning(
                "Failed to upload/attach storyboard for %s variant %s: %s",
                shot_label,
                variant_label,
                exc,
            )
            record_ids.append(None)
    
    return record_ids
