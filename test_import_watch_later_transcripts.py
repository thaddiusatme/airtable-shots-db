import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_videos_table():
    return Mock()


@pytest.fixture
def mock_transcript_fetcher():
    with patch("import_watch_later.fetch_transcript") as mock_fetch:
        yield mock_fetch


class TestTranscriptFetch:
    """Test suite for transcript fetching functionality."""

    def test_fetch_transcript_returns_none_when_unavailable(self):
        """When transcript is unavailable, fetch_transcript should return None."""
        from import_watch_later import fetch_transcript
        
        with patch("import_watch_later.YouTubeTranscriptApi") as MockAPI:
            mock_instance = MockAPI.return_value
            mock_instance.fetch.side_effect = Exception("Transcript unavailable")
            
            result = fetch_transcript("video123", languages=["en"])
            assert result is None

    def test_fetch_transcript_returns_data_when_available(self):
        """When transcript exists, fetch_transcript should return transcript data."""
        from import_watch_later import fetch_transcript
        
        mock_segments = [
            {"text": "Hello world", "start": 0.0, "duration": 2.0},
            {"text": "This is a test", "start": 2.0, "duration": 3.0},
        ]
        
        with patch("import_watch_later.YouTubeTranscriptApi") as MockAPI:
            mock_instance = MockAPI.return_value
            mock_fetched = Mock()
            mock_snippet_objs = [Mock(text=s["text"]) for s in mock_segments]
            mock_fetched.snippets = mock_snippet_objs
            mock_fetched.language_code = "en"
            mock_instance.fetch.return_value = mock_fetched
            
            result = fetch_transcript("video123", languages=["en"])
            
            assert result is not None
            assert "text" in result
            assert "language" in result
            assert "source" in result
            assert result["text"] == "Hello world This is a test"
            assert result["language"] == "en"

    def test_fetch_transcript_tries_fallback_languages(self):
        """fetch_transcript should try fallback languages when primary fails."""
        from import_watch_later import fetch_transcript
        
        with patch("import_watch_later.YouTubeTranscriptApi") as MockAPI:
            mock_instance = MockAPI.return_value
            mock_fetched = Mock()
            mock_snippet = Mock(text="Hola mundo")
            mock_fetched.snippets = [mock_snippet]
            mock_fetched.language_code = "es"
            mock_instance.fetch.return_value = mock_fetched
            
            result = fetch_transcript("video123", languages=["en", "es"])
            
            assert result is not None
            assert result["language"] == "es"
            assert "Hola mundo" in result["text"]


class TestTranscriptIntegration:
    """Test suite for transcript integration into import workflow."""

    def test_upsert_video_with_transcript_when_flag_enabled(self, mock_videos_table):
        """When fetch_transcripts=True and transcript exists, update Airtable with transcript fields."""
        mock_videos_table.first.return_value = None
        mock_videos_table.create.return_value = {"id": "recNEW123"}
        
        transcript_data = {
            "text": "Full transcript text here",
            "language": "en",
            "source": "youtube-transcript-api"
        }
        
        with patch("import_watch_later.fetch_transcript") as mock_fetch:
            mock_fetch.return_value = transcript_data
            
            from import_watch_later import upsert_video_with_transcript
            
            record_id, created, t_stats = upsert_video_with_transcript(
                mock_videos_table,
                platform="YouTube",
                video_id="vid123",
                video_title="Test Video",
                channel_record_id="recCH1",
                thumbnail_url=None,
                dry_run=False,
                fetch_transcripts=True,
                force_transcripts=False,
            )
            
            assert created is True
            assert record_id == "recNEW123"
            assert t_stats["fetched"] == 1
            assert t_stats["unavailable"] == 0
            assert t_stats["skipped"] == 0
            
            create_call = mock_videos_table.create.call_args
            fields = create_call[0][0]
            
            assert fields["Transcript (Full)"] == "Full transcript text here"
            assert fields["Transcript Source"] == "youtube-transcript-api"
            assert fields["Transcript Language"] == "en"

    def test_upsert_video_skips_transcript_when_flag_disabled(self, mock_videos_table):
        """When fetch_transcripts=False, should not fetch or write transcript."""
        mock_videos_table.first.return_value = None
        mock_videos_table.create.return_value = {"id": "recNEW456"}
        
        with patch("import_watch_later.fetch_transcript") as mock_fetch:
            from import_watch_later import upsert_video_with_transcript
            
            record_id, created, t_stats = upsert_video_with_transcript(
                mock_videos_table,
                platform="YouTube",
                video_id="vid456",
                video_title="Test Video 2",
                channel_record_id="recCH2",
                thumbnail_url=None,
                dry_run=False,
                fetch_transcripts=False,
                force_transcripts=False,
            )
            
            mock_fetch.assert_not_called()
            assert t_stats["fetched"] == 0
            assert t_stats["unavailable"] == 0
            assert t_stats["skipped"] == 0
            
            create_call = mock_videos_table.create.call_args
            fields = create_call[0][0]
            
            assert "Transcript (Full)" not in fields
            assert "Transcript Source" not in fields
            assert "Transcript Language" not in fields

    def test_upsert_video_skips_existing_transcript_unless_forced(self, mock_videos_table):
        """When video has existing transcript and force=False, should skip refetch."""
        existing_record = {
            "id": "recEXIST789",
            "fields": {
                "Video ID": "vid789",
                "Transcript (Full)": "Existing transcript",
                "Transcript Language": "en",
            }
        }
        mock_videos_table.first.return_value = existing_record
        
        with patch("import_watch_later.fetch_transcript") as mock_fetch:
            from import_watch_later import upsert_video_with_transcript
            
            record_id, created, t_stats = upsert_video_with_transcript(
                mock_videos_table,
                platform="YouTube",
                video_id="vid789",
                video_title="Existing Video",
                channel_record_id="recCH3",
                thumbnail_url=None,
                dry_run=False,
                fetch_transcripts=True,
                force_transcripts=False,
            )
            
            mock_fetch.assert_not_called()
            assert created is False
            assert t_stats["skipped"] == 1
            assert t_stats["fetched"] == 0
            assert t_stats["unavailable"] == 0

    def test_upsert_video_refetches_when_forced(self, mock_videos_table):
        """When force_transcripts=True, should refetch even if transcript exists."""
        existing_record = {
            "id": "recEXIST999",
            "fields": {
                "Video ID": "vid999",
                "Transcript (Full)": "Old transcript",
                "Transcript Language": "en",
            }
        }
        mock_videos_table.first.return_value = existing_record
        
        new_transcript = {
            "text": "Updated transcript",
            "language": "en",
            "source": "youtube-transcript-api"
        }
        
        with patch("import_watch_later.fetch_transcript") as mock_fetch:
            mock_fetch.return_value = new_transcript
            
            from import_watch_later import upsert_video_with_transcript
            
            record_id, created, t_stats = upsert_video_with_transcript(
                mock_videos_table,
                platform="YouTube",
                video_id="vid999",
                video_title="Existing Video",
                channel_record_id="recCH4",
                thumbnail_url=None,
                dry_run=False,
                fetch_transcripts=True,
                force_transcripts=True,
            )
            
            mock_fetch.assert_called_once_with("vid999", languages=["en"])
            assert t_stats["fetched"] == 1
            assert t_stats["skipped"] == 0
            assert t_stats["unavailable"] == 0
            
            update_call = mock_videos_table.update.call_args
            fields = update_call[0][1]
            
            assert fields["Transcript (Full)"] == "Updated transcript"

    def test_upsert_video_handles_transcript_fetch_failure_gracefully(self, mock_videos_table):
        """When transcript fetch fails, should still create/update video without transcript."""
        mock_videos_table.first.return_value = None
        mock_videos_table.create.return_value = {"id": "recNEW111"}
        
        with patch("import_watch_later.fetch_transcript") as mock_fetch:
            mock_fetch.return_value = None
            
            from import_watch_later import upsert_video_with_transcript
            
            record_id, created, t_stats = upsert_video_with_transcript(
                mock_videos_table,
                platform="YouTube",
                video_id="vid111",
                video_title="No Transcript Video",
                channel_record_id="recCH5",
                thumbnail_url=None,
                dry_run=False,
                fetch_transcripts=True,
                force_transcripts=False,
            )
            
            assert created is True
            assert record_id == "recNEW111"
            assert t_stats["unavailable"] == 1
            assert t_stats["fetched"] == 0
            assert t_stats["skipped"] == 0
            
            create_call = mock_videos_table.create.call_args
            fields = create_call[0][0]
            
            assert "Transcript (Full)" not in fields
