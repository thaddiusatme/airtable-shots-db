"""LLM enrichment adapters for shot-level analysis.

Provides factory functions that return an ``enrich_fn(prompt_dict) -> str``
callable compatible with ``publish_to_airtable(enrich_fn=...)``.

Currently supported providers:
- **Ollama** (local): ``make_ollama_enrich_fn(capture_dir, ...)``

Usage:
    from publisher.llm_enricher import make_ollama_enrich_fn

    enrich = make_ollama_enrich_fn(
        capture_dir="/path/to/captures/abc123",
        model="llava:7b",
    )
    raw_json = enrich(prompt_dict)
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def make_ollama_enrich_fn(
    capture_dir: str,
    *,
    ollama_url: str = "http://localhost:11434/api/generate",
    model: str = "llava:7b",
    timeout: int = 600,
    max_frames: int | None = None,
) -> callable:
    """Create an Ollama-backed enrich_fn callable.

    The returned function accepts a prompt dict (from
    ``build_enrichment_prompt()``) and returns the raw LLM response string.

    Args:
        capture_dir: Path to the capture directory containing frame images.
        ollama_url: Ollama API generate endpoint URL.
        model: Ollama model name (must support vision for multimodal).
        timeout: HTTP request timeout in seconds.
        max_frames: Maximum number of frame images to send. ``None`` means
            send all referenced frames. When set, frames are evenly sampled.

    Returns:
        Callable that takes a prompt dict and returns a raw JSON string.
    """
    capture_path = Path(capture_dir)

    def _enrich(prompt_dict: dict[str, Any]) -> str:
        prompt_text = (
            prompt_dict["system_prompt"] + "\n\n" + prompt_dict["user_prompt"]
        )

        frame_refs = list(prompt_dict.get("frame_references", []))
        if max_frames is not None and len(frame_refs) > max_frames:
            frame_refs = _evenly_sample(frame_refs, max_frames)

        images = _encode_frames(capture_path, frame_refs)

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt_text,
            "images": images,
            "stream": False,
        }

        try:
            resp = requests.post(ollama_url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.ConnectionError as e:
            raise RuntimeError(
                f"Ollama connection failed at {ollama_url} — is Ollama running? {e}"
            ) from e
        except requests.Timeout as e:
            raise RuntimeError(
                f"Ollama request timed out after {timeout}s: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Ollama request failed: {e}"
            ) from e

        data = resp.json()
        return data.get("response", "")

    return _enrich


def _encode_frames(
    capture_path: Path, frame_refs: list[str]
) -> list[str]:
    """Base64-encode frame images from the capture directory.

    Missing files are skipped with a warning rather than raising.
    """
    images: list[str] = []
    for filename in frame_refs:
        frame_path = capture_path / filename
        if not frame_path.exists():
            logger.warning("Frame file not found, skipping: %s", frame_path)
            continue
        raw = frame_path.read_bytes()
        images.append(base64.b64encode(raw).decode("ascii"))
    return images


def _evenly_sample(items: list, n: int) -> list:
    """Select n items evenly spaced from the list."""
    if n <= 0:
        return []
    if n >= len(items):
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]
