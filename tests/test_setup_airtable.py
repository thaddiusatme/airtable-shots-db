"""Tests for setup_airtable — add_frames_table() and add_enrichment_fields() (TDD).

Tests cover:
- add_frames_table() creates Frames table with correct primary field
- add_frames_table() adds all 6 additional fields via create_field()
- add_frames_table() skips creation if Frames table already exists (idempotent)
- add_frames_table() NEVER calls workspace.create_base() (safety constraint)
- Linked record fields point to correct existing Videos/Shots table IDs
- add_enrichment_fields() adds 4 new LLM enrichment fields to Shots table
- add_enrichment_fields() skips fields that already exist (idempotent)
- add_enrichment_fields() NEVER creates bases or tables (safety constraint)
- Contract: publisher enrichment output fields match schema definitions
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

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_frame_image_uses_correct_attachment_type(self, mock_api, mock_create_field):
        """Frame Image must use multipleAttachments (plural), not multipleAttachment."""
        mock_base = MagicMock()
        mock_base.schema.side_effect = [
            _mock_schema(EXISTING_TABLES),
            _mock_schema(EXISTING_TABLES_WITH_FRAMES),
        ]
        mock_api.base.return_value = mock_base

        from setup_airtable import add_frames_table
        add_frames_table("appTEST123")

        frame_image_calls = [
            c for c in mock_create_field.call_args_list
            if c[0][2].get("name") == "Frame Image"
        ]
        assert len(frame_image_calls) == 1
        payload = frame_image_calls[0][0][2]
        assert payload["type"] == "multipleAttachments"  # plural, not singular


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


# ---------------------------------------------------------------------------
# Fixtures — enrichment field tests (field-level schema mocks)
# ---------------------------------------------------------------------------

def _make_field(name, field_type="singleLineText"):
    """Create a mock field object matching pyairtable schema style."""
    return SimpleNamespace(name=name, type=field_type)


def _make_table_with_fields(name, table_id, field_names=None):
    """Create a mock table with name, id, and field objects."""
    fields = [_make_field(fn) for fn in (field_names or [])]
    return SimpleNamespace(name=name, id=table_id, fields=fields)


# Field names already provisioned by build_schema() for the Shots table
EXISTING_SHOT_FIELD_NAMES = [
    "Shot Label", "Video", "Shot Image", "Timestamp (sec)", "Timestamp (hh:mm:ss)",
    "Shot Function", "Shot Type", "Camera Angle", "Movement", "Lighting",
    "Setting", "Subject", "On-screen Text", "Description (Manual)", "Tags",
    "AI Status", "AI Description (Local)", "AI JSON", "AI Model",
    "AI Prompt Version", "AI Updated At", "AI Error",
    "Transcript Line", "Transcript Start (sec)", "Transcript End (sec)",
    "Captured At", "Rights Note",
]

# Derive enrichment field names from the source constant in setup_airtable.
# This eliminates duplication — if the constant changes, tests follow automatically.
with patch("setup_airtable.api"), patch("setup_airtable.workspace"):
    from setup_airtable import ENRICHMENT_FIELD_DEFINITIONS
NEW_ENRICHMENT_FIELD_NAMES = [fd["name"] for fd in ENRICHMENT_FIELD_DEFINITIONS]


def _enrichment_tables(include_new_fields=False):
    """Build mock tables where Shots has existing fields, optionally with enrichment fields."""
    shot_fields = list(EXISTING_SHOT_FIELD_NAMES)
    if include_new_fields:
        shot_fields.extend(NEW_ENRICHMENT_FIELD_NAMES)
    return [
        _make_table_with_fields("Channels", "tblCHANNELS"),
        _make_table_with_fields("Videos", "tblVIDEOS"),
        _make_table_with_fields("Shots", "tblSHOTS", shot_fields),
        _make_table_with_fields("Frames", "tblFRAMES"),
    ]


# ---------------------------------------------------------------------------
# Test: add_enrichment_fields creates 4 new fields on Shots table
# ---------------------------------------------------------------------------

class TestAddEnrichmentFieldsCreatesFields:
    """add_enrichment_fields() should add 4 LLM enrichment text fields to Shots."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_adds_four_enrichment_fields(self, mock_api, mock_create_field):
        """Should call create_field exactly 4 times."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        assert mock_create_field.call_count == 4

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_field_names_match_spec(self, mock_api, mock_create_field):
        """Field names must be exactly the 4 enrichment fields in order."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        field_names = [c[0][2]["name"] for c in mock_create_field.call_args_list]
        assert field_names == NEW_ENRICHMENT_FIELD_NAMES

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_all_fields_use_multiline_text_type(self, mock_api, mock_create_field):
        """All 4 enrichment fields should be multilineText (LLM narrative output)."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        for call in mock_create_field.call_args_list:
            payload = call[0][2]
            assert payload["type"] == "multilineText", (
                f"{payload['name']} should be multilineText"
            )

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_targets_shots_table(self, mock_api, mock_create_field):
        """All create_field calls must target the Shots table ID."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        for call in mock_create_field.call_args_list:
            assert call[0][1] == "tblSHOTS", "Must target Shots table"


# ---------------------------------------------------------------------------
# Test: idempotent — skips fields that already exist
# ---------------------------------------------------------------------------

class TestAddEnrichmentFieldsIdempotent:
    """add_enrichment_fields() must be safe to re-run."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_skips_if_all_enrichment_fields_exist(self, mock_api, mock_create_field):
        """If all 4 enrichment fields already exist, create_field must NOT be called."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=True)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        mock_create_field.assert_not_called()

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_adds_only_missing_fields(self, mock_api, mock_create_field):
        """If some enrichment fields exist, only add the missing ones."""
        partial_fields = EXISTING_SHOT_FIELD_NAMES + [
            "How It Is Shot", "Frame Progression",
        ]
        tables = [
            _make_table_with_fields("Channels", "tblCHANNELS"),
            _make_table_with_fields("Videos", "tblVIDEOS"),
            _make_table_with_fields("Shots", "tblSHOTS", partial_fields),
            _make_table_with_fields("Frames", "tblFRAMES"),
        ]
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(tables)
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        assert mock_create_field.call_count == 2
        added_names = [c[0][2]["name"] for c in mock_create_field.call_args_list]
        assert "Production Patterns" in added_names
        assert "Recreation Guidance" in added_names


# ---------------------------------------------------------------------------
# Test: safety — no table or base creation
# ---------------------------------------------------------------------------

class TestAddEnrichmentFieldsSafety:
    """add_enrichment_fields() must NEVER create bases or tables."""

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.workspace")
    @patch("setup_airtable.api")
    def test_does_not_call_create_base(self, mock_api, mock_workspace, mock_create_field):
        """workspace.create_base() must never be called."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        mock_workspace.create_base.assert_not_called()

    @patch("setup_airtable.create_field")
    @patch("setup_airtable.api")
    def test_does_not_create_table(self, mock_api, mock_create_field):
        """base.create_table() must never be called."""
        mock_base = MagicMock()
        mock_base.schema.return_value = _mock_schema(
            _enrichment_tables(include_new_fields=False)
        )
        mock_api.base.return_value = mock_base

        from setup_airtable import add_enrichment_fields
        add_enrichment_fields("appTEST123")

        mock_base.create_table.assert_not_called()


# ---------------------------------------------------------------------------
# Test: contract — publisher enrichment fields match schema definitions
# ---------------------------------------------------------------------------

class TestEnrichmentFieldContract:
    """Field names written by publisher enrichment must match schema definitions."""

    def test_all_enrichment_output_fields_have_schema_support(self):
        """Every SHOT_ENRICHMENT_FIELDS Airtable column must be provisioned by schema."""
        from publisher.shot_package import SHOT_ENRICHMENT_FIELDS

        enrichment_airtable_cols = set(SHOT_ENRICHMENT_FIELDS.values())
        schema_shot_fields = set(EXISTING_SHOT_FIELD_NAMES) | set(NEW_ENRICHMENT_FIELD_NAMES)

        missing = enrichment_airtable_cols - schema_shot_fields
        assert not missing, f"Enrichment fields not in schema: {missing}"

    def test_enrichment_metadata_fields_in_schema(self):
        """AI Prompt Version, AI Updated At, AI Error, AI Model, AI JSON must be in schema."""
        metadata_fields = {
            "AI Prompt Version", "AI Updated At", "AI Error", "AI Model", "AI JSON",
        }
        schema_shot_fields = set(EXISTING_SHOT_FIELD_NAMES) | set(NEW_ENRICHMENT_FIELD_NAMES)

        missing = metadata_fields - schema_shot_fields
        assert not missing, f"Metadata fields not in schema: {missing}"

    def test_no_duplicate_airtable_columns_in_enrichment(self):
        """SHOT_ENRICHMENT_FIELDS must not map multiple LLM keys to same Airtable column."""
        from publisher.shot_package import SHOT_ENRICHMENT_FIELDS

        airtable_cols = list(SHOT_ENRICHMENT_FIELDS.values())
        assert len(airtable_cols) == len(set(airtable_cols)), "Duplicate Airtable column names"
