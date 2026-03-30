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
    fetch_shot_frame_urls,
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
    parser.add_argument("--dry-run", action="store_true", help="Generate dry-run JSON files (default: True)")
    parser.add_argument("--no-dry-run", action="store_true", help="Run real ComfyUI generation (requires --comfyui-url)")
    parser.add_argument("--output-dir", type=str, default="./storyboard_output", help="Output directory for generated files")
    parser.add_argument("--comfyui-url", type=str, default="http://127.0.0.1:8188", help="ComfyUI server URL")
    parser.add_argument("--timeout", type=int, default=300, help="ComfyUI generation timeout in seconds")
    parser.add_argument("--upload-to-r2", action="store_true", help="Upload generated PNGs to R2 and create Airtable Storyboards records")
    parser.add_argument("--shot-label", type=str, default=None, help="Limit to single shot by label (e.g., S01)")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")

    if not api_key or not base_id:
        print("ERROR: Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in .env", file=sys.stderr)
        sys.exit(1)

    # Validate flags
    if args.no_dry_run and args.dry_run:
        print("ERROR: Cannot specify both --dry-run and --no-dry-run", file=sys.stderr)
        sys.exit(1)
    
    if args.upload_to_r2 and not args.no_dry_run:
        print("ERROR: --upload-to-r2 requires --no-dry-run (can't upload dry-run JSON files)", file=sys.stderr)
        sys.exit(1)
    
    # R2 config for uploads
    r2_config = None
    s3_client = None
    if args.upload_to_r2:
        from publisher.r2_uploader import R2Config, create_s3_client
        
        r2_account_id = os.getenv("R2_ACCOUNT_ID")
        r2_access_key = os.getenv("R2_ACCESS_KEY_ID")
        r2_secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        r2_bucket = os.getenv("R2_BUCKET_NAME", "shot-image")
        r2_public_url = os.getenv("R2_PUBLIC_URL")
        
        if not all([r2_account_id, r2_access_key, r2_secret_key, r2_public_url]):
            print("ERROR: R2 upload requires R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_PUBLIC_URL in .env", file=sys.stderr)
            sys.exit(1)
        
        r2_config = R2Config(
            account_id=r2_account_id,
            access_key_id=r2_access_key,
            secret_access_key=r2_secret_key,
            bucket_name=r2_bucket,
            public_url=r2_public_url,
        )
        s3_client = create_s3_client(r2_config)

    api = Api(api_key)
    videos_table = api.base(base_id).table("Videos")
    shots_table = api.base(base_id).table("Shots")
    storyboards_table = api.base(base_id).table("Storyboards") if args.upload_to_r2 else None

    print(f"Fetching enriched shots for video: {args.video_id}")
    print(f"  Assembler version: {ASSEMBLER_VERSION}")
    print(f"  Handoff version: {STORYBOARD_HANDOFF_VERSION}")
    print(f"  Generator version: {GENERATOR_VERSION}")
    print(f"  Style preset: {STORYBOARD_STYLE_DEFAULTS['style_preset']}")
    print(f"  Variants: {len(VARIANT_DEFINITIONS)} ({', '.join(v['label'] for v in VARIANT_DEFINITIONS)})")

    # Airtable schema note: Shots.{Video} is a linked-record field to Videos.
    # The linked value is the Video record ID (rec...), not the Videos.{Video ID}
    # text field. So for a YouTube video_id like "l5ggH-YhuAw", we resolve the
    # corresponding Videos record ID and filter shots by that record ID.
    video_record_id = None
    if args.video_id.startswith("rec"):
        video_record_id = args.video_id
    else:
        matching_videos = videos_table.all(
            formula=f"{{Video ID}}='{args.video_id}'",
            max_records=1,
        )
        if matching_videos:
            video_record_id = matching_videos[0]["id"]

    if video_record_id:
        print(f"Resolved Videos record: {video_record_id}")
        # Airtable formulas against linked-record fields can be brittle (they may
        # evaluate as display values rather than record IDs). To avoid false
        # negatives, fetch enriched shots and filter client-side by linked video.
        enriched_records = shots_table.all(formula="{AI Prompt Version}!=''")
        records = [
            r for r in enriched_records
            if video_record_id in (r.get("fields", {}).get("Video", []) or [])
        ]
        if args.shot_id:
            records = [r for r in records if r.get("id") == args.shot_id]
    
    # Filter by shot label if specified
    if args.shot_label:
        records = [
            r for r in records
            if r.get("fields", {}).get("Shot Label") == args.shot_label
        ]
    else:
        # Backward-compatible fallback: attempt the original filter.
        records = fetch_enriched_shots_for_storyboard(
            shots_table,
            video_id=args.video_id,
            shot_id=args.shot_id,
        )

    if not records:
        print("\nNo enriched shots found. Run enrichment first.")
        sys.exit(0)

    print(f"\nFound {len(records)} enriched shots.")

    # Extract frame URLs from shot records for IPAdapter conditioning
    reference_frames_by_shot: dict[str, list[dict[str, str]]] = {}
    for record in records:
        shot_label = record["fields"].get("Shot Label", "")
        frame_urls = fetch_shot_frame_urls(record["fields"])
        if frame_urls:
            reference_frames_by_shot[shot_label] = frame_urls
            print(f"  {shot_label}: {len(frame_urls)} frame URLs")
        else:
            print(f"  {shot_label}: no frame attachments")

    # Build payloads with reference frames
    shots_fields = [r["fields"] for r in records]
    series = build_storyboard_series(shots_fields, reference_frames_by_shot=reference_frames_by_shot)

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
        print("  SUMMARY")
        print(f"{'='*72}")
        print(f"  Shots processed: {len(records)}")
        print(f"  Total variants generated: {total_variants}")
        print(f"  Avg storyboard_positive length: {total_positive_len // max(len(records), 1)} chars")
        print(f"  Total base prompt omissions: {total_omissions}")
        print(f"  Style preset: {STORYBOARD_STYLE_DEFAULTS['style_preset']}")
        print(f"  Aspect ratio: {STORYBOARD_STYLE_DEFAULTS['aspect_ratio']}")
        print(f"  Dimensions: {STORYBOARD_STYLE_DEFAULTS['width']}x{STORYBOARD_STYLE_DEFAULTS['height']}")

    # Generation (dry-run or real)
    if args.dry_run or args.no_dry_run:
        is_dry_run = not args.no_dry_run
        mode = "Dry-Run" if is_dry_run else "Real ComfyUI"
        print(f"\n--- {mode} Generation ---")
        print(f"  Output directory: {args.output_dir}")
        
        generate_fn = None
        if not is_dry_run:
            from publisher.storyboard_generator import make_comfyui_generate_fn
            print(f"  ComfyUI URL: {args.comfyui_url}")
            print(f"  Timeout: {args.timeout}s")
            try:
                generate_fn = make_comfyui_generate_fn(
                    comfyui_url=args.comfyui_url,
                    timeout=args.timeout,
                )
            except FileNotFoundError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(1)
        
        gen_results = generate_storyboard_series(
            series,
            video_id=args.video_id,
            output_dir=args.output_dir,
            dry_run=is_dry_run,
            generate_fn=generate_fn,
        )

        total_files = sum(len(r) for r in gen_results)
        print(f"  Files generated: {total_files}")
        for shot_idx, shot_results in enumerate(gen_results):
            for path in shot_results:
                if path:
                    print(f"    {path}")
        
        # Upload to R2 and create Airtable records
        if args.upload_to_r2 and not is_dry_run:
            from publisher.storyboard_uploader import upload_and_attach_storyboards
            
            print("\n--- R2 Upload + Airtable Storyboards ---")
            variant_labels = [v["label"] for v in VARIANT_DEFINITIONS]
            
            for shot_idx, (record, payload, shot_outputs) in enumerate(zip(records, series, gen_results)):
                shot_label = record["fields"].get("Shot Label", "???")
                shot_record_id = record["id"]
                
                print(f"  Processing {shot_label}...")
                
                storyboard_record_ids = upload_and_attach_storyboards(
                    s3_client=s3_client,
                    r2_config=r2_config,
                    storyboards_table=storyboards_table,
                    video_id=args.video_id,
                    shot_label=shot_label,
                    variant_outputs=shot_outputs,
                    variant_labels=variant_labels,
                    payload=payload,
                    video_record_id=video_record_id,
                    shot_record_id=shot_record_id,
                )
                
                successful = sum(1 for rid in storyboard_record_ids if rid is not None)
                print(f"    Created {successful}/{len(storyboard_record_ids)} Storyboard records")
            
            print("  Upload complete.")
        
        print()


if __name__ == "__main__":
    main()
