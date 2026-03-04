"""Transcript segmentation module.

Segments timestamped transcripts by scene boundaries for the YouTube Shot List Pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def format_seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to a human-readable timestamp string.
    
    Returns M:SS for times under 1 hour, H:MM:SS for 1 hour+.
    """
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def segment_transcript_by_scenes(
    timestamped_transcript: Optional[str],
    scenes: list[dict[str, Any]]
) -> dict[int, str]:
    """Segment transcript text by scene boundaries.
    
    Each transcript line is prefixed with its timestamp so the output
    shows exactly when each line was spoken.
    
    Args:
        timestamped_transcript: JSON string from Videos table containing
            list of {text: str, start: float} objects.
        scenes: List of scene dicts with startTimestamp, endTimestamp, sceneIndex.
    
    Returns:
        Dict mapping scene_index → timestamped transcript text for each scene.
        Empty dict if no transcript available or parsing fails.
    
    Example:
        >>> transcript = '[{"text": "Hello", "start": 5.0}, {"text": "world", "start": 8.0}]'
        >>> scenes = [{"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10}]
        >>> segment_transcript_by_scenes(transcript, scenes)
        {0: '[0:05] Hello\n[0:08] world'}
    """
    if not timestamped_transcript:
        logger.debug("No timestamped transcript provided")
        return {}
    
    # Parse JSON: [{"text": "...", "start": 5.2}, ...]
    try:
        segments = json.loads(timestamped_transcript)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse timestamped transcript JSON: {e}")
        return {}
    
    if not isinstance(segments, list):
        logger.warning("Timestamped transcript is not a list")
        return {}
    
    # Pre-process: build list of valid segments with computed end times.
    # Each segment spans from its start until the next segment begins.
    valid_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        seg_start = seg.get('start')
        seg_text = seg.get('text')
        if seg_start is None or not seg_text:
            continue
        valid_segments.append({'start': seg_start, 'text': seg_text})
    
    # Sort by start time and compute each segment's end time
    valid_segments.sort(key=lambda s: s['start'])
    for i, seg in enumerate(valid_segments):
        if i + 1 < len(valid_segments):
            seg['end'] = valid_segments[i + 1]['start']
        else:
            seg['end'] = seg['start'] + 10  # last segment: assume 10s duration
    
    scene_transcripts = {}
    
    for scene in scenes:
        start_sec = scene.get('startTimestamp', 0)
        end_sec = scene.get('endTimestamp', 0)
        scene_idx = scene.get('sceneIndex', 0)
        
        # For zero-duration scenes, treat as a 1-second window
        if end_sec <= start_sec:
            end_sec = start_sec + 1
        
        # Find transcript segments that overlap with this scene.
        # Overlap: segment starts before scene ends AND segment ends after scene starts.
        matching_lines = []
        for seg in valid_segments:
            if seg['start'] < end_sec and seg['end'] > start_sec:
                ts = format_seconds_to_timestamp(seg['start'])
                matching_lines.append(f"[{ts}] {seg['text']}")
        
        # Join with newlines so each timestamped line is on its own row
        scene_transcripts[scene_idx] = '\n'.join(matching_lines)
    
    logger.info(f"Segmented transcript into {len(scene_transcripts)} scenes")
    return scene_transcripts
