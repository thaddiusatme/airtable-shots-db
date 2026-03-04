"""Ollama VLM integration for scene description (Pass 2).

Sends boundary frames to a local Ollama vision model and returns
natural-language scene descriptions.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2-vision:latest"
DEFAULT_API_URL = "http://localhost:11434/api/generate"
DEFAULT_PROMPT = "Describe this video frame in one sentence. What is the scene showing?"
DEFAULT_TIMEOUT = 120  # seconds


class OllamaError(Exception):
    """Raised when Ollama API communication fails."""


def encode_frame_base64(frame_path: str) -> str:
    """Read a PNG file and return its contents as a base64-encoded string.

    Args:
        frame_path: Path to the frame image file.

    Returns:
        Base64-encoded string of the file contents.

    Raises:
        FileNotFoundError: If the frame file does not exist.
    """
    path = Path(frame_path)
    if not path.exists():
        raise FileNotFoundError(f"Frame not found: {frame_path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def describe_frame(
    frame_path: str,
    *,
    model: str = DEFAULT_MODEL,
    prompt: str = DEFAULT_PROMPT,
    api_url: str = DEFAULT_API_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a single frame to Ollama VLM and return the description.

    Args:
        frame_path: Path to the frame PNG.
        model: Ollama model name.
        prompt: Text prompt to send with the image.
        api_url: Ollama API endpoint URL.
        timeout: Request timeout in seconds.

    Returns:
        Description string from the model (whitespace-stripped).

    Raises:
        OllamaError: On connection error, timeout, or bad response.
    """
    image_b64 = encode_frame_base64(frame_path)

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }

    try:
        resp = requests.post(api_url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.ConnectionError as e:
        raise OllamaError(f"Connection refused: {e}") from e
    except requests.Timeout as e:
        raise OllamaError(f"Request timed out: {e}") from e
    except Exception as e:
        raise OllamaError(f"Ollama API error: {e}") from e

    data = resp.json()
    description = data.get("response", "").strip()
    return description


def describe_scenes(
    capture_dir: str,
    analysis: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Add VLM descriptions to all scenes in an analysis dict.

    Sends the firstFrame of each scene to the Ollama VLM for description.
    Errors are caught per-scene so one failure doesn't abort the whole pass.

    Args:
        capture_dir: Path to the capture directory containing frame PNGs.
        analysis: Analysis dict (modified in place and returned).
        model: Ollama model name.
        api_url: Ollama API endpoint URL.
        timeout: Request timeout in seconds per request.

    Returns:
        The analysis dict with description and transition fields populated.
    """
    scenes = analysis.get("scenes", [])
    total = len(scenes)

    if total == 0:
        logger.info("[Pass 2] No scenes to describe.")
        return analysis

    logger.info("[Pass 2] Describing %d scenes with %s...", total, model)

    for i, scene in enumerate(scenes):
        frame_path = f"{capture_dir}/{scene['firstFrame']}"
        logger.info(
            "[Pass 2] Describing scene %d/%d (%s)...",
            i + 1,
            total,
            scene["firstFrame"],
        )

        try:
            description = describe_frame(
                frame_path, model=model, api_url=api_url, timeout=timeout
            )
            scene["description"] = description
            scene["transition"] = "cut"
        except OllamaError as e:
            logger.warning(
                "[Pass 2] Error describing scene %d: %s", i, e
            )
            scene["description"] = f"[Error: {e}]"
            scene["transition"] = "cut"

    analysis["analysisModel"] = model
    logger.info("[Pass 2] Complete — described %d scenes.", total)

    return analysis
