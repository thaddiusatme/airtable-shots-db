#!/usr/bin/env python3
"""Validate storyboard handoff against real enriched shots from Airtable.

Manual validation harness for GH-33 — fetch enriched shots, run
build_storyboard_payload() on each, optionally dry-run generate outputs,
print structured output for manual review.

Follows the same pattern as scripts/validate_prompt_assembler.py.

Usage:
    .venv/bin/python scripts/validate_storyboard_handoff.py --video-id VIDEO_ID
    .venv/bin/python scripts/validate_storyboard_handoff.py --video-id VIDEO_ID --dry-run --output-dir ./output
    .venv/bin/python scripts/validate_storyboard_handoff.py --video-id VIDEO_ID --shot-id recXXXXX
    .venv/bin/python scripts/validate_storyboard_handoff.py --video-id VIDEO_ID --json-only

Requires: AIRTABLE_API_KEY and AIRTABLE_BASE_ID in .env
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from pyairtable import Api

# Add project root to path so we can import publisher modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publisher.prompt_assembler import ASSEMBLER_VERSION
from publisher.storyboard_generator import (
    GENERATOR_VERSION,
    generate_storyboard_series,
)
from publisher.storyboard_handoff import (
    STORYBOARD_HANDOFF_VERSION,
    STORYBOARD_STYLE_DEFAULTS,
    VARIANT_DEFINITIONS,
    build_storyboard_series,
    fetch_enriched_shots_for_storyboard,
)


def print_payload_result(idx: int, record: dict, payload: dict):
    """Pretty-print a single shot's storyboard payload."""
    fields = record["fields"]
    label = fields.get("Shot Label", "???")
    meta = payload["metadata"]

    print(f"\n{'='*72}")
    print(f"  Shot {idx+1}: {label}")
    print(f"  Record ID: {record['id']}")
    print(f"  AI Model: {fields.get('AI Model', 'N/A')}")
    print(f"  AI Prompt Version: {fields.get('AI Prompt Version', 'N/A')}")
    print(f"{'='*72}")

    # Storyboard prompts
    print("\n--- Storyboard Positive Prompt ---")
    sp = payload["storyboard_positive"]
    print(f"  ({len(sp)} chars)")
    print(f"  {sp}")

    print("\n--- Storyboard Negative Prompt ---")
    sn = payload["storyboard_negative"]
    print(f"  ({len(sn)} chars)")
    print(f"  {sn}")

    # Style
    print("\n--- Style ---")
    print(f"  preset: {payload['style']['style_preset']}")
    print(f"  aspect: {payload['generation']['aspect_ratio']}")
    print(f"  dimensions: {payload['generation']['width']}x{payload['generation']['height']}")

    # Variants
    print(f"\n--- Variants ({len(payload['variants'])}) ---")
    for v in payload["variants"]:
        vp = v["positive_prompt"]
        print(f"\n  Variant {v['label']}:")
        print(f"    ({len(vp)} chars)")
        print(f"    {vp[:200]}{'...' if len(vp) > 200 else ''}")

    # Reference images
    refs = payload["reference_images"]
    print(f"\n--- Reference Images: {len(refs)} ---")
    for r in refs:
        print(f"  {r['url']} [{r.get('role', 'N/A')}]")

    # Metadata
    print("\n--- Metadata ---")
    print(f"  shot_label: {meta['shot_label']}")
    print(f"  assembler_version: {meta['assembler_version']}")
    print(f"  handoff_version: {meta['handoff_version']}")
    print(f"  variant_count: {meta['variant_count']}")

    # Base prompt omissions
    base_omissions = payload["base_prompt"]["metadata"].get("omissions", [])
    if base_omissions:
        print(f"\n--- Base Prompt Omissions ({len(base_omissions)}) ---")
        for o in base_omissions:
            print(f"  - {o}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate storyboard handoff on real Airtable shots"
    )
    parser.add_argument("--video-id", type=str, required=True, help="Video ID to fetch shots for")
    parser.add_argument("--shot-id", type=str, default=None, help="Optional: single shot record ID")
    parser.add_argument("--json-only", action="store_true", help="Output only JSON (no pretty-print)")
    parser.add_argument("--dry-run", action="store_true", help="Generate dry-run JSON files")
    parser.add_argument("--output-dir", type=str, default="./storyboard_output", help="Output directory for dry-run files")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")

    if not api_key or not base_id:
        print("ERROR: Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in .env", file=sys.stderr)
        sys.exit(1)

    api = Api(api_key)
    shots_table = api.base(base_id).table("Shots")

    print(f"Fetching enriched shots for video: {args.video_id}")
    print(f"  Assembler version: {ASSEMBLER_VERSION}")
    print(f"  Handoff version: {STORYBOARD_HANDOFF_VERSION}")
    print(f"  Generator version: {GENERATOR_VERSION}")
    print(f"  Style preset: {STORYBOARD_STYLE_DEFAULTS['style_preset']}")
    print(f"  Variants: {len(VARIANT_DEFINITIONS)} ({', '.join(v['label'] for v in VARIANT_DEFINITIONS)})")

    records = fetch_enriched_shots_for_storyboard(
        shots_table,
        video_id=args.video_id,
        shot_id=args.shot_id,
    )

    if not records:
        print("\nNo enriched shots found. Run enrichment first.")
        sys.exit(0)

    print(f"\nFound {len(records)} enriched shots.")

    # Build payloads
    shots_fields = [r["fields"] for r in records]
    series = build_storyboard_series(shots_fields)

    # Aggregate stats
    total_positive_len = 0
    total_variants = 0
    total_omissions = 0
    results_json: list[dict] = []

    for idx, (record, payload) in enumerate(zip(records, series)):
        total_positive_len += len(payload["storyboard_positive"])
        total_variants += len(payload["variants"])
        total_omissions += len(payload["base_prompt"]["metadata"].get("omissions", []))

        if args.json_only:
            results_json.append({
                "record_id": record["id"],
                "shot_label": record["fields"].get("Shot Label", ""),
                "payload": payload,
            })
        else:
            print_payload_result(idx, record, payload)

    if args.json_only:
        print(json.dumps(results_json, indent=2))
    else:
        # Summary
        print(f"\n{'='*72}")
        print(f"  SUMMARY")
        print(f"{'='*72}")
        print(f"  Shots processed: {len(records)}")
        print(f"  Total variants generated: {total_variants}")
        print(f"  Avg storyboard_positive length: {total_positive_len // max(len(records), 1)} chars")
        print(f"  Total base prompt omissions: {total_omissions}")
        print(f"  Style preset: {STORYBOARD_STYLE_DEFAULTS['style_preset']}")
        print(f"  Aspect ratio: {STORYBOARD_STYLE_DEFAULTS['aspect_ratio']}")
        print(f"  Dimensions: {STORYBOARD_STYLE_DEFAULTS['width']}x{STORYBOARD_STYLE_DEFAULTS['height']}")

    # Dry-run generation
    if args.dry_run:
        print("\n--- Dry-Run Generation ---")
        print(f"  Output directory: {args.output_dir}")

        gen_results = generate_storyboard_series(
            series,
            video_id=args.video_id,
            output_dir=args.output_dir,
            dry_run=True,
        )

        total_files = sum(len(r) for r in gen_results)
        print(f"  Files written: {total_files}")
        for shot_idx, shot_results in enumerate(gen_results):
            for path in shot_results:
                if path:
                    print(f"    {path}")
        print()


if __name__ == "__main__":
    main()
