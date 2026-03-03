"""Tests for setup_airtable.add_frames_table() — RED phase (TDD).

Tests cover:
- add_frames_table() creates Frames table with correct primary field
- add_frames_table() adds all 6 additional fields via create_field()
- add_frames_table() skips creation if Frames table already exists (idempotent)
- add_frames_table() NEVER calls workspace.create_base() (safety constraint)
- Linked record fields point to correct existing Videos/Shots table IDs
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures — mock Airtable schema objects
# ---------------------------------------------------------------------------

def _make_table(name, table_id):
    """Create a mock table object matching pyairtable schema style."""
    return SimpleNamespace(name=name, id=table_id)


EXISTING_TABLES = [
    _make_table("Channels", "tblCHANNELS"),
    _make_table("Videos", "tblVIDEOS"),
    _make_table("Shots", "tblSHOTS"),
]

EXISTING_TABLES_WITH_FRAMES = EXISTING_TABLES + [
    _make_table("Frames", "tblFRAMES"),
]


def _mock_schema(tables):
    """Return a mock schema object with a .tables attribute."""
    return SimpleNamespace(tables=tables)


# ---------------------------------------------------------------------------
# Test: creates Frames table with correct fields
# ---------------------------------------------------------------------------

class TestAddFramesTableCreatesTable:
    """add_frames_table() should create the Frames table and add 6 fields."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_creates_table_with_frame_key_primary_field(self, mock_api, mock_create_field):
        """Should call create_table('Frames', ...) with Frame Key as primary field."""
        # First schema() call returns existing tables (no Frames)
        # Second schema() call returns tables including new Frames table
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        mock_base.create_table.assert_called_once()
        args, kwargs = mock_base.create_table.call_args
        assert args[0] == "Frames"
        # Primary field should be Frame Key (singleLineText)
        fields = args[1]
        assert len(fields) == 1
        assert fields[0]["name"] == "Frame Key"
        assert fields[0]["type"] == "singleLineText"

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_adds_six_additional_fields(self, mock_api, mock_create_field):
        """Should call create_field() exactly 6 times for the additional fields."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        assert mock_create_field.call_count == 6

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_video_link_field_points_to_videos_table(self, mock_api, mock_create_field):
        """Video linked record field must reference tblVIDEOS."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        # Find the Video link field call
        video_link_calls = [
            c for c in mock_create_field.call_args_list
            if c[0][2].get("name") == "Video"
        ]
        assert len(video_link_calls) == 1
        payload = video_link_calls[0][0][2]
        assert payload["type"] == "multipleRecordLinks"
        assert payload["options"]["linkedTableId"] == "tblVIDEOS"

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_shot_link_field_points_to_shots_table(self, mock_api, mock_create_field):
        """Shot linked record field must reference tblSHOTS."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        shot_link_calls = [
            c for c in mock_create_field.call_args_list
            if c[0][2].get("name") == "Shot"
        ]
        assert len(shot_link_calls) == 1
        payload = shot_link_calls[0][0][2]
        assert payload["type"] == "multipleRecordLinks"
        assert payload["options"]["linkedTableId"] == "tblSHOTS"

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_all_field_names_match_spec(self, mock_api, mock_create_field):
        """All 6 additional field names must match the GH #18 spec exactly."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        field_names = [c[0][2]["name"] for c in mock_create_field.call_args_list]
        expected = [
            "Video",
            "Shot",
            "Timestamp (sec)",
            "Timestamp (hh:mm:ss)",
            "Frame Image",
            "Source Filename",
        ]
        assert field_names == expected


# ---------------------------------------------------------------------------
# Test: skips creation if Frames table already exists (idempotent)
# ---------------------------------------------------------------------------

class TestAddFramesTableIdempotent:
    """add_frames_table() must be safe to re-run."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_skips_if_frames_already_exists(self, mock_api, mock_create_field):
        """If Frames table already exists, create_table must NOT be called."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(EXISTING_TABLES_WITH_FRAMES)
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        mock_base.create_table.assert_not_called()
        mock_create_field.assert_not_called()


# ---------------------------------------------------------------------------
# Test: NEVER calls workspace.create_base() (safety constraint)
# ---------------------------------------------------------------------------

class TestAddFramesTableSafety:
    """add_frames_table() must NEVER create a new base."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.workspace")
    @patch("setup_airtable.api")
    def test_does_not_call_create_base(self, mock_api, mock_workspace, mock_create_field):
        """workspace.create_base() must never be called."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        mock_workspace.create_base.assert_not_called()
