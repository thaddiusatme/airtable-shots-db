"""CLI entry point for the Airtable publisher.

Usage:
    python -m publisher --capture-dir ~/Downloads/yt-captures/{videoId}_{datetime}/
    python -m publisher --capture-dir ./captures/abc123 --dry-run
    python -m publisher --capture-dir ./captures/abc123 --api-key patXXX --base-id appXXX

Environment variables (alternative to flags):
    AIRTABLE_API_KEY — Airtable personal access token
    AIRTABLE_BASE_ID — Airtable base ID
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from publisher.publish import PublisherError, publish_to_airtable

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
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging.",
    )
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    try:
        result = publish_to_airtable(
            capture_dir=args.capture_dir,
            api_key=args.api_key,
            base_id=args.base_id,
            dry_run=args.dry_run,
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
