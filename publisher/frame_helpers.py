"""
Frame helper utilities for timestamp parsing and frame metadata extraction.
"""

import re
from pathlib import Path


_TIMESTAMP_PATTERN = re.compile(r't(\d+(?:\.\d+)?)s')


def parse_timestamp_from_filename(filename: str) -> int:
    """
    Extract integer timestamp (seconds) from frame filename.
    
    Parses filenames following the pattern: frame_XXXXX_tSSSS.MMMMs.png
    where SSSSS.MMMM is the timestamp in seconds with optional decimal.
    
    Args:
        filename: Frame filename (with or without path), e.g., "frame_00042_t042.567s.png"
    
    Returns:
        Integer timestamp in seconds (decimal portion truncated)
    
    Raises:
        ValueError: If no timestamp pattern found in filename
        TypeError: If filename is None
    
    Examples:
        >>> parse_timestamp_from_filename("frame_00001_t001.000s.png")
        1
        >>> parse_timestamp_from_filename("frame_00042_t042.567s.png")
        42
        >>> parse_timestamp_from_filename("/path/to/frame_00123_t123.456s.png")
        123
    """
    if filename is None:
        raise TypeError("filename cannot be None")
    
    if not filename:
        raise ValueError("No timestamp found in filename: empty string")
    
    basename = Path(filename).name
    
    match = _TIMESTAMP_PATTERN.search(basename)
    if not match:
        raise ValueError(f"No timestamp found in filename: {filename}")
    
    timestamp_str = match.group(1)
    timestamp_float = float(timestamp_str)
    
    return int(timestamp_float)
