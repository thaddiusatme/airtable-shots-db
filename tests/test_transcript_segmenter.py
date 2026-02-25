"""Tests for transcript segmentation module."""

import json

from segmenter.transcript_segmenter import (
    format_seconds_to_timestamp,
    segment_transcript_by_scenes,
)


def test_format_seconds_to_timestamp():
    """Test timestamp formatting."""
    assert format_seconds_to_timestamp(0) == "0:00"
    assert format_seconds_to_timestamp(5) == "0:05"
    assert format_seconds_to_timestamp(65) == "1:05"
    assert format_seconds_to_timestamp(3661) == "1:01:01"
    assert format_seconds_to_timestamp(7200) == "2:00:00"


def test_segment_transcript_by_scenes_basic():
    """Test basic transcript segmentation."""
    transcript_data = [
        {"text": "Hello world", "start": 5.0},
        {"text": "This is a test", "start": 8.0},
        {"text": "Another segment", "start": 15.0},
        {"text": "Final words", "start": 18.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
        {"sceneIndex": 1, "startTimestamp": 10, "endTimestamp": 20},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    assert result[0] == "[0:05] Hello world\n[0:08] This is a test"
    # Segment at 8s spans 8-15s, overlaps into scene 1
    assert result[1] == "[0:08] This is a test\n[0:15] Another segment\n[0:18] Final words"


def test_segment_transcript_empty_scene():
    """Test scene before any transcript segments."""
    transcript_data = [
        {"text": "Hello", "start": 5.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 3},
        {"sceneIndex": 1, "startTimestamp": 3, "endTimestamp": 10},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    # Scene 0 ends before segment starts at 5s → empty
    assert result[0] == ""
    # Scene 1 overlaps with segment at 5s (spans 5-15s assumed) → has text
    assert result[1] == "[0:05] Hello"


def test_segment_transcript_missing_transcript():
    """Test with no timestamped transcript."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
    ]
    
    result = segment_transcript_by_scenes(None, scenes)
    
    assert result == {}


def test_segment_transcript_empty_string():
    """Test with empty string transcript."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
    ]
    
    result = segment_transcript_by_scenes("", scenes)
    
    assert result == {}


def test_segment_transcript_invalid_json():
    """Test with invalid JSON transcript."""
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
    ]
    
    result = segment_transcript_by_scenes("not valid json", scenes)
    
    assert result == {}


def test_segment_transcript_not_list():
    """Test with JSON that's not a list."""
    timestamped_transcript = json.dumps({"text": "Hello", "start": 5.0})
    
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    assert result == {}


def test_segment_transcript_malformed_segments():
    """Test with malformed segment objects."""
    transcript_data = [
        {"text": "Valid", "start": 5.0},
        {"text": "Missing start"},
        {"start": 8.0},
        "not a dict",
        {"text": "Also valid", "start": 12.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 15},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    assert result[0] == "[0:05] Valid\n[0:12] Also valid"


def test_segment_transcript_overlap_short_scene():
    """Test that short scenes get transcript from overlapping segments."""
    transcript_data = [
        {"text": "Started talking", "start": 5.0},
        {"text": "Next line", "start": 10.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    # Scene at 7-9s is between segment starts but segment at 5s spans 5-10s
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 7, "endTimestamp": 9},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    assert result[0] == "[0:05] Started talking"


def test_segment_transcript_zero_duration_scene():
    """Test that zero-duration scenes still get transcript."""
    transcript_data = [
        {"text": "Speaking now", "start": 10.0},
        {"text": "Next part", "start": 15.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    # Zero-duration scene at 12s (gets expanded to 12-13s)
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 12, "endTimestamp": 12},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    # Segment at 10s spans 10-15s, overlaps with 12-13s
    assert result[0] == "[0:10] Speaking now"


def test_segment_transcript_boundary_cases():
    """Test segments at exact scene boundaries."""
    transcript_data = [
        {"text": "At start", "start": 0.0},
        {"text": "At boundary", "start": 10.0},
        {"text": "After boundary", "start": 10.1},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    scenes = [
        {"sceneIndex": 0, "startTimestamp": 0, "endTimestamp": 10},
        {"sceneIndex": 1, "startTimestamp": 10, "endTimestamp": 20},
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    # Segment at 0.0 spans 0-10, in scene 0
    assert result[0] == "[0:00] At start"
    # Segments at 10.0 and 10.1 are in scene 1
    assert result[1] == "[0:10] At boundary\n[0:10] After boundary"


def test_segment_transcript_empty_scenes():
    """Test with empty scenes list."""
    transcript_data = [
        {"text": "Hello", "start": 5.0},
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    result = segment_transcript_by_scenes(timestamped_transcript, [])
    
    assert result == {}


def test_segment_transcript_multiple_scenes():
    """Test with many scenes."""
    transcript_data = [
        {"text": f"Segment {i}", "start": float(i * 2)}
        for i in range(10)
    ]
    timestamped_transcript = json.dumps(transcript_data)
    
    scenes = [
        {"sceneIndex": i, "startTimestamp": i * 5, "endTimestamp": (i + 1) * 5}
        for i in range(4)
    ]
    
    result = segment_transcript_by_scenes(timestamped_transcript, scenes)
    
    assert len(result) == 4
    # Segment 2 (start=4) spans 4-6, overlaps scene 0 (0-5) and scene 1 (5-10)
    assert result[0] == "[0:00] Segment 0\n[0:02] Segment 1\n[0:04] Segment 2"
    assert result[1] == "[0:04] Segment 2\n[0:06] Segment 3\n[0:08] Segment 4"
    # Segment 4 (start=8) spans 8-10, scene 2 starts at 10 — no overlap (10 is not > 10)
    assert result[2] == "[0:10] Segment 5\n[0:12] Segment 6\n[0:14] Segment 7"
    # Segment 7 (start=14) spans 14-16, scene 3 starts at 15 — overlaps
    assert result[3] == "[0:14] Segment 7\n[0:16] Segment 8\n[0:18] Segment 9"
