#!/usr/bin/env python3
"""Validate prompt assembler against real enriched shots from Airtable.

One-time validation harness for GH-32 — pull enriched shots, run
assemble_shot_image_prompt() on each, print structured output for
manual SDXL/ComfyUI usability review.

Usage:
    .venv/bin/python scripts/validate_prompt_assembler.py
    .venv/bin/python scripts/validate_prompt_assembler.py --limit 5
    .venv/bin/python scripts/validate_prompt_assembler.py --video-id abc123

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

from publisher.prompt_assembler import ASSEMBLER_VERSION, assemble_shot_image_prompt
from publisher.shot_package import SHOT_ENRICHMENT_FIELDS


def fetch_enriched_shots(
    shots_table,
    *,
    limit: int = 5,
    video_id: str | None = None,
) -> list[dict]:
    """Fetch enriched shot records from Airtable.

    Enriched = has truthy AI Prompt Version field.
    """
    formula_parts = ["{AI Prompt Version}!=''"]
    if video_id:
        formula_parts.append(f"FIND('{video_id}', ARRAYJOIN({{Video}}))")

    formula = (
        f"AND({', '.join(formula_parts)})" if len(formula_parts) > 1
        else formula_parts[0]
    )

    records = shots_table.all(formula=formula, max_records=limit)
    return records


def classify_shot(fields: dict) -> str:
    """Classify a shot for reporting: clean, other-heavy, minimal, or partial."""
    controlled_fields = ["Shot Type", "Camera Angle", "Lighting"]
    other_count = sum(
        1 for f in controlled_fields
        if (fields.get(f) or "").strip().lower() == "other"
    )
    enrichment_count = sum(
        1 for col in SHOT_ENRICHMENT_FIELDS.values()
        if fields.get(col)
    )

    if other_count >= 2:
        return "other-heavy"
    if enrichment_count <= 4:
        return "minimal"
    if enrichment_count <= 8:
        return "partial"
    return "clean"


def print_shot_result(idx: int, record: dict, result: dict, classification: str):
    """Pretty-print a single shot's assembler output."""
    fields = record["fields"]
    label = fields.get("Shot Label", "???")

    print(f"\n{'='*72}")
    print(f"  Shot {idx+1}: {label} [{classification}]")
    print(f"  Record ID: {record['id']}")
    print(f"  AI Model: {fields.get('AI Model', 'N/A')}")
    print(f"  AI Prompt Version: {fields.get('AI Prompt Version', 'N/A')}")
    print(f"{'='*72}")

    # Input fields summary
    print("\n--- Input Fields (from Airtable) ---")
    for llm_key, col_name in SHOT_ENRICHMENT_FIELDS.items():
        val = fields.get(col_name, "")
        if val:
            display = str(val)[:100] + ("..." if len(str(val)) > 100 else "")
            print(f"  {col_name}: {display}")
        else:
            print(f"  {col_name}: (empty)")

    # Assembler output
    print("\n--- Assembler Output ---")
    print(f"  positive_prompt ({len(result['positive_prompt'])} chars):")
    print(f"    {result['positive_prompt']}")
    print(f"\n  negative_prompt:")
    print(f"    {result['negative_prompt']}")

    print(f"\n  prompt_sections ({len(result['prompt_sections'])} keys):")
    for key, val in result["prompt_sections"].items():
        display = val[:80] + ("..." if len(val) > 80 else "")
        print(f"    {key}: {display}")

    print(f"\n  reference_images: {len(result['reference_images'])} frames")

    print(f"\n  metadata:")
    print(f"    shot_label: {result['metadata']['shot_label']}")
    print(f"    assembler_version: {result['metadata']['assembler_version']}")
    if result["metadata"]["omissions"]:
        print(f"    omissions ({len(result['metadata']['omissions'])}):")
        for o in result["metadata"]["omissions"]:
            print(f"      - {o}")
    else:
        print(f"    omissions: (none)")

    # Full JSON for copy-paste
    print(f"\n--- Full JSON ---")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Validate prompt assembler on real Airtable shots")
    parser.add_argument("--limit", type=int, default=5, help="Max shots to fetch (default: 5)")
    parser.add_argument("--video-id", type=str, default=None, help="Filter by Video ID")
    parser.add_argument("--json-only", action="store_true", help="Output only JSON (no pretty-print)")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")

    if not api_key or not base_id:
        print("ERROR: Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in .env", file=sys.stderr)
        sys.exit(1)

    api = Api(api_key)
    shots_table = api.base(base_id).table("Shots")

    print(f"Fetching up to {args.limit} enriched shots from Airtable...")
    if args.video_id:
        print(f"  Filtering by Video ID: {args.video_id}")

    records = fetch_enriched_shots(shots_table, limit=args.limit, video_id=args.video_id)
    if not records:
        print("No enriched shots found. Run enrichment first.")
        sys.exit(0)

    print(f"Found {len(records)} enriched shots.")
    print(f"Assembler version: {ASSEMBLER_VERSION}")

    # Aggregate stats
    classifications = {"clean": 0, "other-heavy": 0, "minimal": 0, "partial": 0}
    all_omissions: list[str] = []
    total_prompt_len = 0
    results_json: list[dict] = []

    for idx, record in enumerate(records):
        fields = record["fields"]
        classification = classify_shot(fields)
        classifications[classification] += 1

        result = assemble_shot_image_prompt(fields)
        all_omissions.extend(result["metadata"]["omissions"])
        total_prompt_len += len(result["positive_prompt"])

        if args.json_only:
            results_json.append({
                "record_id": record["id"],
                "shot_label": fields.get("Shot Label", ""),
                "classification": classification,
                "result": result,
            })
        else:
            print_shot_result(idx, record, result, classification)

    if args.json_only:
        print(json.dumps(results_json, indent=2))
        return

    # Summary
    print(f"\n{'='*72}")
    print(f"  SUMMARY")
    print(f"{'='*72}")
    print(f"  Shots processed: {len(records)}")
    print(f"  Classifications: {json.dumps(classifications)}")
    print(f"  Avg positive_prompt length: {total_prompt_len // max(len(records), 1)} chars")
    if all_omissions:
        # Group omissions by type
        omission_counts: dict[str, int] = {}
        for o in all_omissions:
            key = o.split(":")[0] if ":" in o else o
            omission_counts[key] = omission_counts.get(key, 0) + 1
        print(f"  Total omissions: {len(all_omissions)}")
        for key, count in sorted(omission_counts.items(), key=lambda x: -x[1]):
            print(f"    {key}: {count}x")
    else:
        print(f"  Total omissions: 0")
    print()


if __name__ == "__main__":
    main()
