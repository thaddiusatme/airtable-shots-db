"""
Tests for frame helper utilities.

Tests timestamp parsing from frame filenames following TDD red-green-refactor cycle.
"""

import pytest
from publisher.frame_helpers import parse_timestamp_from_filename


class TestParseTimestampFromFilename:
    """Test timestamp extraction from frame filenames."""

    def test_parse_basic_timestamp(self):
        """Parse standard frame filename with timestamp."""
        filename = "frame_00001_t001.000s.png"
        assert parse_timestamp_from_filename(filename) == 1

    def test_parse_decimal_timestamp(self):
        """Parse timestamp with decimal seconds (should round/truncate)."""
        filename = "frame_00042_t042.567s.png"
        assert parse_timestamp_from_filename(filename) == 42

    def test_parse_zero_timestamp(self):
        """Parse frame at zero seconds."""
        filename = "frame_00000_t000.000s.png"
        assert parse_timestamp_from_filename(filename) == 0

    def test_parse_large_timestamp(self):
        """Parse timestamp for long video (e.g., 1800 seconds = 30 minutes)."""
        filename = "frame_01800_t1800.000s.png"
        assert parse_timestamp_from_filename(filename) == 1800

    def test_parse_with_path_prefix(self):
        """Parse timestamp from filename with directory path."""
        filename = "/path/to/frames/frame_00123_t123.456s.png"
        assert parse_timestamp_from_filename(filename) == 123

    def test_missing_timestamp_pattern(self):
        """Raise ValueError when timestamp pattern is missing."""
        filename = "frame_00001.png"
        with pytest.raises(ValueError, match="No timestamp found"):
            parse_timestamp_from_filename(filename)

    def test_malformed_timestamp(self):
        """Raise ValueError when timestamp is malformed."""
        filename = "frame_00001_tXYZ.000s.png"
        with pytest.raises(ValueError, match="No timestamp found"):
            parse_timestamp_from_filename(filename)

    def test_missing_s_suffix(self):
        """Raise ValueError when 's' suffix is missing."""
        filename = "frame_00001_t123.456.png"
        with pytest.raises(ValueError, match="No timestamp found"):
            parse_timestamp_from_filename(filename)

    def test_empty_filename(self):
        """Raise ValueError for empty filename."""
        with pytest.raises(ValueError, match="No timestamp found"):
            parse_timestamp_from_filename("")

    def test_none_filename(self):
        """Raise TypeError for None filename."""
        with pytest.raises(TypeError):
            parse_timestamp_from_filename(None)

    def test_parse_single_digit_timestamp(self):
        """Parse timestamp with single digit seconds."""
        filename = "frame_00005_t5.000s.png"
        assert parse_timestamp_from_filename(filename) == 5

    def test_parse_rounds_down(self):
        """Verify decimal seconds are truncated/rounded down to integer."""
        filename = "frame_00010_t10.999s.png"
        assert parse_timestamp_from_filename(filename) == 10
