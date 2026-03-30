"""LLM enrichment adapters for shot-level analysis.

Provides factory functions that return an ``enrich_fn(prompt_dict) -> str``
callable compatible with ``publish_to_airtable(enrich_fn=...)``.

Currently supported providers:
- **Ollama** (local): ``make_ollama_enrich_fn(capture_dir, ...)``

Usage:
    from publisher.llm_enricher import make_ollama_enrich_fn

    enrich = make_ollama_enrich_fn(
        capture_dir="/path/to/captures/abc123",
        model="llava:latest",
    )
    raw_json = enrich(prompt_dict)
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_SHOT_ENRICHMENT_FIELD_KEYS = [
    "scene_summary",
    "how_it_is_shot",
    "shot_type",
    "camera_angle",
    "movement",
    "lighting",
    "setting",
    "subject",
    "on_screen_text",
    "shot_function",
    "frame_progression",
    "production_patterns",
    "recreation_guidance",
]

_GEMINI_PRICING_PER_MILLION_TOKENS_USD = {
    "gemini-2.5-flash": {"input": 0.50, "output": 3.00},
    "gemini-2.5-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.50},
}


def verify_ollama_model(
    model: str,
    *,
    ollama_url: str = "http://localhost:11434/api/generate",
) -> None:
    """Verify that the requested model is available in Ollama.

    Calls ``GET /api/tags`` to list installed models and raises
    ``RuntimeError`` if the requested model is not found.

    Args:
        model: Ollama model name to verify (e.g. ``llava:latest``).
        ollama_url: Ollama API generate endpoint URL. The base URL is
            derived by stripping the path and appending ``/api/tags``.
    """
    # Derive base URL from the generate endpoint
    base_url = ollama_url.rsplit("/api/", 1)[0]
    tags_url = base_url + "/api/tags"

    try:
        resp = requests.get(tags_url, timeout=10)
        resp.raise_for_status()
    except requests.ConnectionError as e:
        raise RuntimeError(
            f"Ollama connection failed at {tags_url} — is Ollama running? {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to query Ollama models at {tags_url}: {e}"
        ) from e

    data = resp.json()
    available = [m["name"] for m in data.get("models", [])]

    if model not in available:
        raise RuntimeError(
            f"Model '{model}' not found in Ollama. "
            f"Available models: {', '.join(available)}"
        )


def make_ollama_enrich_fn(
    capture_dir: str,
    *,
    ollama_url: str = "http://localhost:11434/api/generate",
    model: str = "llava:latest",
    timeout: int = 600,
    max_frames: int | None = None,
    verify_model: bool = False,
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
        verify_model: If True, call ``verify_ollama_model()`` before
            returning the enrich_fn. Fails fast if model is not installed.

    Returns:
        Callable that takes a prompt dict and returns a raw JSON string.
    """
    if verify_model:
        verify_ollama_model(model=model, ollama_url=ollama_url)

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
            "format": _build_enrichment_json_schema(),
            "options": {"temperature": 0},
        }

        try:
            resp = requests.post(ollama_url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.ConnectionError as e:
            raise RuntimeError(
                f"Ollama connection failed at {ollama_url} (model={model}) "
                f"— is Ollama running? {e}"
            ) from e
        except requests.Timeout as e:
            raise RuntimeError(
                f"Ollama request timed out after {timeout}s "
                f"(model={model}): {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Ollama request failed (model={model}): {e}"
            ) from e

        data = resp.json()
        return data.get("response", "")

    return _enrich


def make_gemini_enrich_fn(
    capture_dir: str,
    *,
    api_key: str,
    model: str = "gemini-2.0-flash",
    timeout: int = 600,
    max_frames: int | None = None,
    api_url: str = "https://generativelanguage.googleapis.com/v1beta",
) -> callable:
    if not api_key:
        raise RuntimeError("Gemini API key is required")

    capture_path = Path(capture_dir)
    request_url = f"{api_url.rstrip('/')}/models/{model}:generateContent"

    def _enrich(prompt_dict: dict[str, Any]) -> str:
        _enrich.last_usage = None
        frame_refs = list(prompt_dict.get("frame_references", []))
        if max_frames is not None and len(frame_refs) > max_frames:
            frame_refs = _evenly_sample(frame_refs, max_frames)

        parts: list[dict[str, Any]] = [{"text": prompt_dict["user_prompt"]}]
        for filename in frame_refs:
            frame_path = capture_path / filename
            if not frame_path.exists():
                logger.warning("Frame file not found, skipping: %s", frame_path)
                continue
            mime_type = mimetypes.guess_type(frame_path.name)[0] or "image/png"
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(frame_path.read_bytes()).decode("ascii"),
                }
            })

        payload: dict[str, Any] = {
            "systemInstruction": {
                "parts": [{"text": prompt_dict["system_prompt"]}]
            },
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": _build_enrichment_json_schema(),
                "temperature": 0,
            },
        }

        try:
            resp = requests.post(
                request_url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.ConnectionError as e:
            raise RuntimeError(
                f"Gemini connection failed at {request_url} (model={model}): {e}"
            ) from e
        except requests.Timeout as e:
            raise RuntimeError(
                f"Gemini request timed out after {timeout}s (model={model}): {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Gemini request failed (model={model}): {e}"
            ) from e

        data = resp.json()
        _enrich.last_usage = _build_gemini_usage_summary(model, data.get("usageMetadata"))
        candidates = data.get("candidates") or []
        if not candidates:
            prompt_feedback = data.get("promptFeedback") or {}
            block_reason = prompt_feedback.get("blockReason")
            if block_reason:
                raise RuntimeError(
                    f"Gemini returned no candidates (model={model}, blockReason={block_reason})"
                )
            raise RuntimeError(
                f"Gemini returned no candidates (model={model})"
            )

        content = candidates[0].get("content") or {}
        response_parts = content.get("parts") or []
        text_chunks = [
            part.get("text", "")
            for part in response_parts
            if isinstance(part, dict) and part.get("text")
        ]
        if not text_chunks:
            raise RuntimeError(
                f"Gemini returned no text content (model={model})"
            )
        return "".join(text_chunks)

    _enrich.last_usage = None
    return _enrich


def _build_enrichment_json_schema() -> dict[str, Any]:
    """Build a JSON schema for Ollama structured output.

    Returns a JSON Schema object whose properties match the 13
    ``SHOT_ENRICHMENT_FIELDS`` keys. All fields are required. The
    ``movement`` field is typed as ``array`` (multi-select); all others
    are ``string``.
    """
    properties: dict[str, Any] = {}
    for key in _SHOT_ENRICHMENT_FIELD_KEYS:
        if key == "movement":
            properties[key] = {"type": "array", "items": {"type": "string"}}
        else:
            properties[key] = {"type": "string"}

    return {
        "type": "object",
        "properties": properties,
        "required": list(_SHOT_ENRICHMENT_FIELD_KEYS),
    }


def _build_gemini_usage_summary(
    model: str,
    usage_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not usage_metadata:
        return None

    prompt_tokens = int(usage_metadata.get("promptTokenCount") or 0)
    candidate_tokens = int(usage_metadata.get("candidatesTokenCount") or 0)
    thoughts_tokens = int(usage_metadata.get("thoughtsTokenCount") or 0)
    output_tokens = candidate_tokens + thoughts_tokens
    total_tokens = int(
        usage_metadata.get("totalTokenCount")
        or (prompt_tokens + output_tokens)
    )
    estimated_cost_usd = _estimate_gemini_cost_usd(
        model=model,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
    )

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "candidate_tokens": candidate_tokens,
        "thoughts_tokens": thoughts_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _estimate_gemini_cost_usd(
    *,
    model: str,
    prompt_tokens: int,
    output_tokens: int,
) -> float | None:
    pricing = _GEMINI_PRICING_PER_MILLION_TOKENS_USD.get(model)
    if not pricing:
        return None
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 8)


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
