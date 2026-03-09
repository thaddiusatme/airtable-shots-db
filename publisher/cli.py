"""CLI entry point for the Airtable publisher.

Usage:
    python -m publisher --capture-dir ~/Downloads/yt-captures/{videoId}_{datetime}/
    python -m publisher --capture-dir ./captures/abc123 --dry-run
    python -m publisher --capture-dir ./captures/abc123 --api-key patXXX --base-id appXXX

Environment variables (alternative to flags):
    AIRTABLE_API_KEY — Airtable personal access token
    AIRTABLE_BASE_ID — Airtable base ID
    R2_ACCOUNT_ID — Cloudflare R2 account ID
    R2_ACCESS_KEY_ID — R2 API access key ID
    R2_SECRET_ACCESS_KEY — R2 API secret access key
    R2_BUCKET_NAME — R2 bucket name (default: shot-image)
    R2_PUBLIC_URL — R2 public URL (e.g., https://pub-xxx.r2.dev)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from publisher.publish import PublisherError, publish_to_airtable
from publisher.r2_uploader import R2Config

logger = logging.getLogger("publisher")


def configure_logging(verbose: bool = False) -> None:
    """Set up logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the publisher CLI."""
    parser = argparse.ArgumentParser(
        description="Publish scene analysis results to Airtable.",
    )
    parser.add_argument(
        "--capture-dir",
        required=True,
        help="Path to the capture directory containing analysis.json.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AIRTABLE_API_KEY", ""),
        help="Airtable personal access token (or set AIRTABLE_API_KEY env var).",
    )
    parser.add_argument(
        "--base-id",
        default=os.environ.get("AIRTABLE_BASE_ID", ""),
        help="Airtable base ID (or set AIRTABLE_BASE_ID env var).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would be published without writing to Airtable.",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        default=False,
        help="Skip R2 image uploads (metadata-only publish).",
    )
    parser.add_argument(
        "--skip-frames",
        action="store_true",
        default=False,
        help="Skip Frame record creation (metadata-only publish without per-second frames).",
    )
    parser.add_argument(
        "--max-concurrent-uploads",
        type=int,
        default=1,
        help="Max concurrent frame uploads (default: 1 = sequential). Use 4-8 for faster uploads.",
    )
    parser.add_argument(
        "--frame-sampling",
        type=int,
        default=1,
        help="Create frames every N seconds (default: 1 = every second). Use 5 or 10 to reduce density.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging.",
    )
    parser.add_argument(
        "--segment-transcripts",
        action="store_true",
        default=False,
        help="Segment transcript by scene boundaries (requires timestamped transcript in Videos table).",
    )
    parser.add_argument(
        "--merge-scenes",
        action="store_true",
        default=False,
        help="Merge short adjacent scenes into longer shots before publishing.",
    )
    parser.add_argument(
        "--min-scene-duration",
        type=float,
        default=5.0,
        help="Minimum scene duration in seconds when --merge-scenes is used (default: 5.0).",
    )
    parser.add_argument(
        "--enrich-shots",
        action="store_true",
        default=False,
        help="Run LLM enrichment on each shot after creation.",
    )
    parser.add_argument(
        "--enrich-provider",
        default="ollama",
        help="LLM provider for enrichment (default: ollama).",
    )
    parser.add_argument(
        "--enrich-model",
        default="llava:7b",
        help="Model name for enrichment (stored in AI Model field, default: llava:7b).",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434/api/generate",
        help="Ollama API generate endpoint URL (default: http://localhost:11434/api/generate).",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=600,
        help="Ollama HTTP request timeout in seconds (default: 600).",
    )
    parser.add_argument(
        "--max-enrich-frames",
        type=int,
        default=None,
        help="Max frames to send per shot for enrichment (default: all). Caps image payload size.",
    )
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    # Build R2 config if credentials are available and images not skipped
    r2_config = None
    if not args.skip_images:
        r2_account_id = os.environ.get("R2_ACCOUNT_ID", "")
        r2_access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
        r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
        r2_bucket = os.environ.get("R2_BUCKET_NAME", "shot-image")
        r2_public_url = os.environ.get("R2_PUBLIC_URL", "")

        if r2_account_id and r2_access_key and r2_secret_key and r2_public_url:
            r2_config = R2Config(
                account_id=r2_account_id,
                access_key_id=r2_access_key,
                secret_access_key=r2_secret_key,
                bucket_name=r2_bucket,
                public_url=r2_public_url,
            )
            logger.info("R2 image uploads enabled (bucket: %s)", r2_bucket)
        else:
            logger.info("R2 credentials not set — skipping image uploads")

    enrich_fn = None
    if args.enrich_shots:
        if args.enrich_provider == "ollama":
            from publisher.llm_enricher import make_ollama_enrich_fn

            enrich_fn = make_ollama_enrich_fn(
                capture_dir=args.capture_dir,
                ollama_url=args.ollama_url,
                model=args.enrich_model,
                timeout=args.ollama_timeout,
                max_frames=args.max_enrich_frames,
            )
            logger.info(
                "Enrichment enabled (provider=%s, model=%s, url=%s)",
                args.enrich_provider,
                args.enrich_model,
                args.ollama_url,
            )
        else:
            logger.error("Unsupported enrichment provider: %s", args.enrich_provider)
            return 1

    try:
        result = publish_to_airtable(
            capture_dir=args.capture_dir,
            api_key=args.api_key,
            base_id=args.base_id,
            dry_run=args.dry_run,
            r2_config=r2_config,
            segment_transcripts=args.segment_transcripts,
            merge_scenes=args.merge_scenes,
            min_scene_duration=args.min_scene_duration,
            skip_frames=args.skip_frames,
            max_workers=args.max_concurrent_uploads,
            frame_sample_rate=args.frame_sampling,
            enrich_shots=args.enrich_shots,
            enrich_fn=enrich_fn,
            enrich_model=args.enrich_model,
        )
    except FileNotFoundError as e:
        logger.error("Error: %s", e)
        return 1
    except PublisherError as e:
        logger.error("Publisher error: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return 1

    if args.dry_run:
        logger.info("[Dry run] Would publish to Airtable:")
        logger.info("  Video ID: %s", result["video_id"])
        logger.info("  Video fields: %s", json.dumps(result["video_fields"], indent=2))
        logger.info("  Shots to create: %d", result["shots_to_create"])
        for shot in result["shot_records"]:
            logger.info(
                "    %s @ %s",
                shot["Shot Label"],
                shot["Timestamp (hh:mm:ss)"],
            )
    else:
        logger.info("Published to Airtable:")
        logger.info("  Video ID: %s", result["video_id"])
        logger.info("  Video record: %s", result["video_record_id"])
        logger.info("  Shots created: %d", result["shots_created"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
