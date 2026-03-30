#!/usr/bin/env python3
"""A/B enrichment test harness — compare model quality on a fixed capture.

Runs LLM enrichment on every shot in a capture directory using two (or more)
models, then prints a side-by-side metrics report: valid JSON rate, field
coverage, and top errors.

Usage:
    python scripts/ab_enrichment_test.py \\
        --capture-dir ~/Downloads/yt-captures/U_cDKkDvPAQ_2026-03-10_1422 \\
        --models llava:7b qwen2.5vl:7b \\
        --max-frames 4

Prerequisites:
    - Ollama running locally with both models pulled
    - Capture directory with analysis.json + manifest.json + frame images

Output is a plain-text report suitable for pasting into a GitHub issue.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publisher.llm_enricher import make_gemini_enrich_fn, make_ollama_enrich_fn
from publisher.publish import get_manifest_frame_map, load_analysis
from publisher.shot_package import (
    SHOT_ENRICHMENT_FIELDS,
    build_enrichment_prompt,
    build_shot_package,
    collect_shot_frames,
    parse_llm_response,
)


def _parse_model_spec(model_spec: str) -> tuple[str, str]:
    if model_spec.startswith("ollama:"):
        return "ollama", model_spec.removeprefix("ollama:")
    if model_spec.startswith("gemini:"):
        return "gemini", model_spec.removeprefix("gemini:")
    return "ollama", model_spec


def _build_enrich_fn(
    provider: str,
    model: str,
    *,
    capture_dir: str,
    ollama_url: str,
    gemini_api_key: str,
    gemini_api_url: str,
    timeout: int,
    max_frames: int | None,
):
    if provider == "ollama":
        return make_ollama_enrich_fn(
            capture_dir=capture_dir,
            ollama_url=ollama_url,
            model=model,
            timeout=timeout,
            max_frames=max_frames,
        )
    if provider == "gemini":
        return make_gemini_enrich_fn(
            capture_dir=capture_dir,
            api_key=gemini_api_key,
            api_url=gemini_api_url,
            model=model,
            timeout=timeout,
            max_frames=max_frames,
        )
    raise ValueError(f"Unsupported provider: {provider}")


def run_enrichment_for_model(
    model_spec: str,
    capture_dir: str,
    analysis: dict[str, Any],
    manifest_frame_map: dict[int, str],
    *,
    ollama_url: str,
    gemini_api_key: str,
    gemini_api_url: str,
    timeout: int,
    max_frames: int | None,
    sample_rate: int,
    show_details: bool,
) -> list[dict[str, Any]]:
    """Run enrichment on all shots for a single model, return per-shot results."""
    provider, model = _parse_model_spec(model_spec)
    enrich_fn = _build_enrich_fn(
        provider,
        model,
        capture_dir=capture_dir,
        ollama_url=ollama_url,
        gemini_api_key=gemini_api_key,
        gemini_api_url=gemini_api_url,
        timeout=timeout,
        max_frames=max_frames,
    )

    results: list[dict[str, Any]] = []
    scenes = analysis["scenes"]
    video_id = analysis["videoId"]

    for i, scene in enumerate(scenes):
        shot_label = f"S{scene['sceneIndex'] + 1:02d}"
        print(f"  [{model_spec}] Enriching {shot_label} ({i+1}/{len(scenes)})...", end="", flush=True)

        t0 = time.monotonic()
        try:
            frames = collect_shot_frames(
                scene, manifest_frame_map or None, sample_rate=sample_rate
            )
            package = build_shot_package(scene, frames, "", video_id)
            prompt = build_enrichment_prompt(package)
            raw_response = enrich_fn(prompt)
            elapsed = time.monotonic() - t0
            fields = parse_llm_response(raw_response)
            usage = getattr(enrich_fn, "last_usage", None)

            has_error = "AI Error" in fields
            details: dict[str, Any] = {
                airtable_col: fields.get(airtable_col)
                for airtable_col in SHOT_ENRICHMENT_FIELDS.values()
            }
            covered_fields = [
                col for col in SHOT_ENRICHMENT_FIELDS.values()
                if col in fields and fields[col]
            ]

            results.append({
                "shot_label": shot_label,
                "elapsed_s": round(elapsed, 1),
                "valid_json": not has_error,
                "ai_error": fields.get("AI Error"),
                "field_count": len(covered_fields),
                "covered_fields": covered_fields,
                "details": details if not has_error else None,
                "raw_response": raw_response[:500] if has_error else None,
                "usage": usage,
            })
            usage_suffix = _format_usage_suffix(usage)
            status = (
                f" {'OK' if not has_error else 'PARSE_FAIL'} "
                f"({elapsed:.1f}s, {len(covered_fields)} fields{usage_suffix})"
            )
            print(status)

            if show_details and not has_error:
                print(f"    Details ({shot_label}):")
                if usage:
                    print(
                        "      - Usage: "
                        f"{usage['prompt_tokens']} in, "
                        f"{usage['output_tokens']} out, "
                        f"{usage['total_tokens']} total, "
                        f"est. ${_format_cost(usage.get('estimated_cost_usd'))}"
                    )
                for k, v in details.items():
                    print(f"      - {k}: {v}")

        except Exception as e:
            elapsed = time.monotonic() - t0
            results.append({
                "shot_label": shot_label,
                "elapsed_s": round(elapsed, 1),
                "valid_json": False,
                "ai_error": str(e),
                "field_count": 0,
                "covered_fields": [],
                "details": None,
                "raw_response": None,
                "usage": getattr(enrich_fn, "last_usage", None),
            })
            print(f" ERROR ({elapsed:.1f}s): {e}")

    return results


def print_report(
    model_results: dict[str, list[dict[str, Any]]],
    video_id: str,
) -> None:
    """Print a formatted A/B comparison report."""
    total_fields = len(SHOT_ENRICHMENT_FIELDS)

    print("\n" + "=" * 70)
    print(f"A/B ENRICHMENT REPORT — {video_id}")
    print("=" * 70)

    for model, results in model_results.items():
        total = len(results)
        valid = sum(1 for r in results if r["valid_json"])
        avg_fields = (
            sum(r["field_count"] for r in results if r["valid_json"]) / valid
            if valid > 0 else 0
        )
        avg_time = sum(r["elapsed_s"] for r in results) / total if total else 0
        total_runtime = sum(r["elapsed_s"] for r in results)
        usage_rows = [r["usage"] for r in results if r.get("usage")]
        total_prompt_tokens = sum(u.get("prompt_tokens", 0) for u in usage_rows)
        total_output_tokens = sum(u.get("output_tokens", 0) for u in usage_rows)
        total_tokens = sum(u.get("total_tokens", 0) for u in usage_rows)
        total_estimated_cost = sum(
            u.get("estimated_cost_usd", 0) or 0 for u in usage_rows
        )

        print(f"\n## {model}")
        print(f"  Shots tested:     {total}")
        print(f"  Valid JSON:       {valid}/{total} ({valid/total*100:.0f}%)")
        print(f"  Avg fields/shot:  {avg_fields:.1f}/{total_fields}")
        print(f"  Avg time/shot:    {avg_time:.1f}s")
        print(f"  Total runtime:    {total_runtime:.1f}s")
        if usage_rows:
            print(f"  Prompt tokens:    {total_prompt_tokens}")
            print(f"  Output tokens:    {total_output_tokens}")
            print(f"  Total tokens:     {total_tokens}")
            print(f"  Estimated cost:   ${_format_cost(total_estimated_cost)}")

        # Top errors
        errors = [r for r in results if r["ai_error"]]
        if errors:
            print(f"  Errors ({len(errors)}):")
            for e in errors[:5]:
                err_snippet = (e["ai_error"] or "")[:120]
                print(f"    - {e['shot_label']}: {err_snippet}")

        # Per-field coverage
        field_hits: dict[str, int] = {col: 0 for col in SHOT_ENRICHMENT_FIELDS.values()}
        for r in results:
            for col in r["covered_fields"]:
                if col in field_hits:
                    field_hits[col] += 1
        print(f"  Field coverage ({valid} valid shots):")
        for col, count in field_hits.items():
            pct = count / valid * 100 if valid else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"    {col:<25s} {bar} {count}/{valid} ({pct:.0f}%)")

    # Side-by-side shot comparison
    models = list(model_results.keys())
    if len(models) >= 2:
        print(f"\n{'─' * 70}")
        print("SHOT-BY-SHOT COMPARISON")
        print(f"{'─' * 70}")
        header = f"{'Shot':<6}"
        for m in models:
            header += f" {'Model':>8} {'JSON':>5} {'Fields':>6} {'Time':>6}"
        # Simplified: just show per-shot
        shots_a = {r["shot_label"]: r for r in model_results[models[0]]}
        shots_b = {r["shot_label"]: r for r in model_results[models[1]]}
        all_labels = sorted(set(shots_a) | set(shots_b))

        print(f"{'Shot':<6} | {models[0]:<28} | {models[1]:<28}")
        print(f"{'':─<6}─┼─{'':─<28}─┼─{'':─<28}")
        for label in all_labels:
            ra = shots_a.get(label)
            rb = shots_b.get(label)

            def fmt(r: dict | None) -> str:
                if r is None:
                    return "—"
                ok = "✓" if r["valid_json"] else "✗"
                return f"{ok} {r['field_count']:>2}fld {r['elapsed_s']:>5.1f}s"

            print(f"{label:<6} | {fmt(ra):<28} | {fmt(rb):<28}")

    print("\n" + "=" * 70)


def _format_usage_suffix(usage: dict[str, Any] | None) -> str:
    if not usage:
        return ""
    return (
        f", {usage['prompt_tokens']} in"
        f"/{usage['output_tokens']} out"
        f", ${_format_cost(usage.get('estimated_cost_usd'))}"
    )


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return "n/a"
    return f"{cost:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A/B enrichment test: compare models on a fixed capture"
    )
    parser.add_argument(
        "--capture-dir", required=True,
        help="Path to capture directory with analysis.json"
    )
    parser.add_argument(
        "--models", nargs="+", required=True,
        help="Model specs to compare. Use plain Ollama names or provider-qualified values like ollama:llava:7b gemini:gemini-2.0-flash"
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434/api/generate",
        help="Ollama API generate endpoint"
    )
    parser.add_argument(
        "--gemini-api-key", default="",
        help="Gemini API key for any gemini:* model specs"
    )
    parser.add_argument(
        "--gemini-api-url", default="https://generativelanguage.googleapis.com/v1beta",
        help="Gemini API base URL"
    )
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Per-shot timeout in seconds"
    )
    parser.add_argument(
        "--max-frames", type=int, default=None,
        help="Max frame images per shot (None=all)"
    )
    parser.add_argument(
        "--sample-rate", type=int, default=5,
        help="Frame sample rate in seconds"
    )
    parser.add_argument(
        "--max-shots", type=int, default=None,
        help="Limit number of shots to test (useful for quick runs)"
    )
    parser.add_argument(
        "--output-json", default=None,
        help="Optional: write raw results to JSON file"
    )
    parser.add_argument(
        "--show-details", action="store_true",
        help="Print per-shot enrichment field values to stdout"
    )

    args = parser.parse_args()

    analysis = load_analysis(args.capture_dir)
    video_id = analysis["videoId"]
    manifest_frame_map = get_manifest_frame_map(args.capture_dir)

    if args.max_shots:
        analysis["scenes"] = analysis["scenes"][:args.max_shots]

    print(f"Video: {video_id}")
    print(f"Shots: {len(analysis['scenes'])}")
    print(f"Models: {', '.join(args.models)}")
    print(f"Max frames/shot: {args.max_frames or 'all'}")
    print()

    model_results: dict[str, list[dict[str, Any]]] = {}

    for model in args.models:
        print(f"─── Running model: {model} ───")
        results = run_enrichment_for_model(
            model_spec=model,
            capture_dir=args.capture_dir,
            analysis=analysis,
            manifest_frame_map=manifest_frame_map,
            ollama_url=args.ollama_url,
            gemini_api_key=args.gemini_api_key,
            gemini_api_url=args.gemini_api_url,
            timeout=args.timeout,
            max_frames=args.max_frames,
            sample_rate=args.sample_rate,
            show_details=args.show_details,
        )
        model_results[model] = results
        print()

    print_report(model_results, video_id)

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(model_results, f, indent=2)
        print(f"\nRaw results written to {args.output_json}")


if __name__ == "__main__":
    main()
