import argparse
import os
import pathlib
import time
from typing import Any, Optional

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pyairtable import Api
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def find_client_secret_file(explicit_path: Optional[str]) -> pathlib.Path:
    if explicit_path:
        p = pathlib.Path(explicit_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"client_secret.json not found at: {p}")
        return p

    candidates = [
        pathlib.Path.cwd() / "client_secret.json",
        pathlib.Path(__file__).resolve().parent / "client_secret.json",
        pathlib.Path(__file__).resolve().parent.parent / "client_secret.json",
    ]
    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        "client_secret.json not found. Set YOUTUBE_CLIENT_SECRET_FILE or place client_secret.json in the repo root."
    )


def get_youtube_service(client_secret_file: pathlib.Path, token_file: pathlib.Path):
    creds: Optional[Credentials] = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), YOUTUBE_SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def get_watch_later_playlist_id(youtube) -> str:
    """Best-effort resolution of the Watch Later playlist ID.

    Some accounts (e.g. certain brand/channel configurations) may not expose
    relatedPlaylists.watchLater. In that case we fall back to the magic ID "WL".
    """

    response = youtube.channels().list(part="contentDetails", mine=True, maxResults=50).execute()
    items = response.get("items", [])
    if not items:
        print("WARNING: channels().list(mine=True) returned no channels; falling back to playlistId=WL")
        return "WL"

    for ch in items:
        related = (ch.get("contentDetails") or {}).get("relatedPlaylists") or {}
        playlist_id = related.get("watchLater")
        if playlist_id:
            return playlist_id

    print(
        "WARNING: relatedPlaylists.watchLater missing for this account; falling back to playlistId=WL. "
        "If this returns 0 items, double-check you authorized the intended Google/YouTube account."
    )
    return "WL"


def get_watch_later_items(youtube, *, playlist_id: str, max_items: Optional[int] = None):
    page_token: Optional[str] = None
    fetched = 0

    while True:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        )
        response = request.execute()

        items = response.get("items", [])
        for it in items:
            yield it
            fetched += 1
            if max_items is not None and fetched >= max_items:
                return

        page_token = response.get("nextPageToken")
        if not page_token:
            return


def debug_print_youtube_identity(youtube) -> None:
    try:
        response = youtube.channels().list(part="snippet,contentDetails", mine=True, maxResults=50).execute()
        items = response.get("items", [])
        print(f"DEBUG: channels(mine=True) count={len(items)}")
        for ch in items:
            snippet = ch.get("snippet") or {}
            related = (ch.get("contentDetails") or {}).get("relatedPlaylists") or {}
            print(
                "DEBUG: channel "
                f"id={ch.get('id')} title={snippet.get('title')} "
                f"relatedPlaylistsKeys={sorted(list(related.keys()))}"
            )
    except Exception as e:
        print(f"DEBUG: failed to list channels(mine=True): {e}")


def debug_watch_later_playlist(youtube) -> None:
    try:
        pl = youtube.playlists().list(part="snippet", id="WL").execute()
        items = pl.get("items", [])
        print(f"DEBUG: playlists().list(id=WL) items={len(items)}")
        if items:
            print(f"DEBUG: WL playlist title={((items[0].get('snippet') or {}).get('title'))}")
    except Exception as e:
        print(f"DEBUG: playlists().list(id=WL) failed: {e}")


def extract_playlist_id(value: str) -> str:
    """Accepts a playlistId or a URL containing ?list=<id>."""
    v = value.strip()
    if "list=" in v:
        # crude parse to avoid extra deps
        after = v.split("list=", 1)[1]
        playlist_id = after.split("&", 1)[0]
        return playlist_id
    return v


def find_playlist_id_by_title(youtube, title: str) -> Optional[str]:
    page_token: Optional[str] = None
    normalized = title.strip().lower()

    while True:
        resp = (
            youtube.playlists()
            .list(part="snippet", mine=True, maxResults=50, pageToken=page_token)
            .execute()
        )
        items = resp.get("items", [])
        for pl in items:
            snippet = pl.get("snippet") or {}
            if (snippet.get("title") or "").strip().lower() == normalized:
                return pl.get("id")

        page_token = resp.get("nextPageToken")
        if not page_token:
            return None


def resolve_source_playlist_id(youtube, *, playlist_id: Optional[str], playlist_title: Optional[str]) -> str:
    if playlist_id:
        return extract_playlist_id(playlist_id)

    if playlist_title:
        found = find_playlist_id_by_title(youtube, playlist_title)
        if not found:
            raise RuntimeError(f"Could not find a playlist with title: {playlist_title}")
        return found

    return get_watch_later_playlist_id(youtube)


def fetch_transcript(video_id: str, languages: list[str]) -> Optional[dict[str, str]]:
    """Fetch transcript for a video. Returns dict with text, language, source or None if unavailable."""
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=languages)
        full_text = " ".join([snippet.text for snippet in fetched.snippets])
        return {
            "text": full_text,
            "language": fetched.language_code,
            "source": "youtube-transcript-api",
        }
    except Exception:
        return None


def airtable_find_first(table, formula: str):
    # pyairtable Table.first returns None if not found
    return table.first(formula=formula)


def upsert_channel(channels_table, *, platform: str, channel_id: str, channel_title: str, dry_run: bool) -> str:
    formula = f"AND({{Platform}}='{platform}', {{Channel Handle}}='{channel_id}')"
    existing = airtable_find_first(channels_table, formula)

    fields = {
        "Channel Name": channel_title,
        "Platform": platform,
        "Channel Handle": channel_id,
        "Channel URL": f"https://www.youtube.com/channel/{channel_id}",
    }

    if existing:
        if dry_run:
            return existing["id"]
        channels_table.update(existing["id"], fields)
        return existing["id"]

    if dry_run:
        return "DRY_RUN_CHANNEL_ID"

    created = channels_table.create(fields)
    return created["id"]


def upsert_video(
    videos_table,
    *,
    platform: str,
    video_id: str,
    video_title: str,
    channel_record_id: str,
    thumbnail_url: Optional[str],
    dry_run: bool,
) -> tuple[str, bool]:
    formula = f"AND({{Platform}}='{platform}', {{Video ID}}='{video_id}')"
    existing = airtable_find_first(videos_table, formula)

    fields: dict[str, Any] = {
        "Video Title": video_title,
        "Video ID": video_id,
        "Platform": platform,
        "Video URL": f"https://www.youtube.com/watch?v={video_id}",
        "Channel": [channel_record_id],
    }
    
    if thumbnail_url:
        fields["Thumbnail URL"] = thumbnail_url
        fields["Thumbnail (Image)"] = [{"url": thumbnail_url}]

    if existing:
        # Do not override triage status if it already exists.
        if existing.get("fields", {}).get("Triage Status"):
            fields.pop("Triage Status", None)

        if dry_run:
            return existing["id"], False

        videos_table.update(existing["id"], fields)
        return existing["id"], False

    fields["Triage Status"] = "Queued"

    if dry_run:
        return "DRY_RUN_VIDEO_ID", True

    created = videos_table.create(fields)
    return created["id"], True


def upsert_video_with_transcript(
    videos_table,
    *,
    platform: str,
    video_id: str,
    video_title: str,
    channel_record_id: str,
    thumbnail_url: Optional[str],
    dry_run: bool,
    fetch_transcripts: bool,
    force_transcripts: bool,
    transcript_languages: Optional[list[str]] = None,
) -> tuple[str, bool, dict[str, int]]:
    """Upsert video with optional transcript fetching.
    
    Returns: (record_id, was_created, transcript_stats)
    where transcript_stats = {"fetched": 0/1, "skipped": 0/1, "unavailable": 0/1}
    """
    if transcript_languages is None:
        transcript_languages = ["en"]

    transcript_stats = {"fetched": 0, "skipped": 0, "unavailable": 0}

    formula = f"AND({{Platform}}='{platform}', {{Video ID}}='{video_id}')"
    existing = airtable_find_first(videos_table, formula)

    fields: dict[str, Any] = {
        "Video Title": video_title,
        "Video ID": video_id,
        "Platform": platform,
        "Video URL": f"https://www.youtube.com/watch?v={video_id}",
        "Channel": [channel_record_id],
    }
    
    if thumbnail_url:
        fields["Thumbnail URL"] = thumbnail_url
        fields["Thumbnail (Image)"] = [{"url": thumbnail_url}]

    should_fetch_transcript = False
    if fetch_transcripts:
        if existing:
            existing_fields = existing.get("fields", {})
            has_transcript = bool(existing_fields.get("Transcript (Full)"))
            if force_transcripts or not has_transcript:
                should_fetch_transcript = True
            elif has_transcript:
                transcript_stats["skipped"] = 1
        else:
            should_fetch_transcript = True

    if should_fetch_transcript:
        transcript_data = fetch_transcript(video_id, languages=transcript_languages)
        if transcript_data:
            fields["Transcript (Full)"] = transcript_data["text"]
            fields["Transcript Source"] = transcript_data["source"]
            fields["Transcript Language"] = transcript_data["language"]
            transcript_stats["fetched"] = 1
        else:
            transcript_stats["unavailable"] = 1

    if existing:
        if existing.get("fields", {}).get("Triage Status"):
            fields.pop("Triage Status", None)

        if dry_run:
            return existing["id"], False, transcript_stats

        videos_table.update(existing["id"], fields)
        return existing["id"], False, transcript_stats

    fields["Triage Status"] = "Queued"

    if dry_run:
        return "DRY_RUN_VIDEO_ID", True, transcript_stats

    created = videos_table.create(fields)
    return created["id"], True, transcript_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import YouTube Watch Later into Airtable (Channels + Videos).")
    parser.add_argument("--max-items", type=int, default=None, help="Limit number of items for testing")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print actions without writing to Airtable")
    parser.add_argument(
        "--playlist-id",
        type=str,
        default=None,
        help="Playlist ID or URL containing ?list=<id> (optional; overrides Watch Later)",
    )
    parser.add_argument(
        "--playlist-title",
        type=str,
        default=None,
        help="Playlist title to import from (optional; overrides Watch Later)",
    )
    parser.add_argument(
        "--debug-youtube",
        action="store_true",
        help="Print debug info about the authenticated YouTube identity and playlist access",
    )
    parser.add_argument(
        "--fetch-transcripts",
        action="store_true",
        help="Fetch and store video transcripts (default: off)",
    )
    parser.add_argument(
        "--force-transcripts",
        action="store_true",
        help="Re-fetch transcripts even if they already exist (requires --fetch-transcripts)",
    )
    parser.add_argument(
        "--transcript-language",
        type=str,
        default="en",
        help="Primary transcript language to fetch (default: en)",
    )
    args = parser.parse_args()

    airtable_api_key = os.getenv("AIRTABLE_API_KEY")
    airtable_base_id = os.getenv("AIRTABLE_BASE_ID")

    if not airtable_api_key or not airtable_base_id:
        print("Error: Please set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in your .env file")
        raise SystemExit(1)

    client_secret_file = find_client_secret_file(os.getenv("YOUTUBE_CLIENT_SECRET_FILE"))
    token_file = pathlib.Path(__file__).resolve().parent / "token.json"

    youtube = get_youtube_service(client_secret_file, token_file)

    if args.debug_youtube:
        debug_print_youtube_identity(youtube)

    watch_later_playlist_id = resolve_source_playlist_id(
        youtube,
        playlist_id=args.playlist_id,
        playlist_title=args.playlist_title,
    )
    if args.debug_youtube:
        print(f"DEBUG: resolved watchLater playlist_id={watch_later_playlist_id}")

    api = Api(airtable_api_key)
    base = api.base(airtable_base_id)
    channels_table = base.table("Channels")
    videos_table = base.table("Videos")

    created_videos = 0
    updated_videos = 0
    created_channels = 0
    updated_channels = 0
    skipped_missing_channel = 0
    raw_items_seen = 0
    transcripts_fetched = 0
    transcripts_unavailable = 0
    transcripts_skipped_existing = 0

    for it in get_watch_later_items(youtube, playlist_id=watch_later_playlist_id, max_items=args.max_items):
        raw_items_seen += 1
        snippet = it.get("snippet", {})
        content_details = it.get("contentDetails", {})

        video_id = content_details.get("videoId")
        if not video_id:
            continue

        video_title = snippet.get("title") or "(untitled)"

        channel_id = snippet.get("videoOwnerChannelId") or snippet.get("channelId") or ""
        channel_title = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or ""
        
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("maxres", {}).get("url") or
            thumbnails.get("high", {}).get("url") or
            thumbnails.get("medium", {}).get("url") or
            thumbnails.get("default", {}).get("url") or
            None
        )

        if not channel_id:
            # Skip videos with missing channel metadata.
            skipped_missing_channel += 1
            continue

        platform = "YouTube"

        existing_channel = airtable_find_first(
            channels_table,
            f"AND({{Platform}}='{platform}', {{Channel Handle}}='{channel_id}')",
        )
        channel_record_id = upsert_channel(
            channels_table,
            platform=platform,
            channel_id=channel_id,
            channel_title=channel_title,
            dry_run=args.dry_run,
        )
        if existing_channel:
            updated_channels += 1
        else:
            created_channels += 1
        
        if args.fetch_transcripts:
            _, created, t_stats = upsert_video_with_transcript(
                videos_table,
                platform=platform,
                video_id=video_id,
                video_title=video_title,
                channel_record_id=channel_record_id,
                thumbnail_url=thumbnail_url,
                dry_run=args.dry_run,
                fetch_transcripts=args.fetch_transcripts,
                force_transcripts=args.force_transcripts,
                transcript_languages=[args.transcript_language],
            )
            transcripts_fetched += t_stats["fetched"]
            transcripts_skipped_existing += t_stats["skipped"]
            transcripts_unavailable += t_stats["unavailable"]
        else:
            _, created = upsert_video(
                videos_table,
                platform=platform,
                video_id=video_id,
                video_title=video_title,
                channel_record_id=channel_record_id,
                thumbnail_url=thumbnail_url,
                dry_run=args.dry_run,
            )

        if created:
            created_videos += 1
            action = "CREATE"
        else:
            updated_videos += 1
            action = "UPDATE"

        print(f"{action} {video_id} | {video_title}")

        time.sleep(0.12)

    print("\nDone.")
    if raw_items_seen == 0:
        print("WARNING: 0 Watch Later items returned from the API. Is your Watch Later list empty?")
        print(f"Resolved playlist id used: {watch_later_playlist_id}")
        if args.debug_youtube and watch_later_playlist_id == "WL":
            debug_watch_later_playlist(youtube)
    if skipped_missing_channel:
        print(f"Skipped items due to missing channel metadata: {skipped_missing_channel}")
    print(f"Channels: created={created_channels} updated={updated_channels}")
    print(f"Videos: created={created_videos} updated={updated_videos}")
    if args.fetch_transcripts:
        print(f"Transcripts: fetched={transcripts_fetched} skipped_existing={transcripts_skipped_existing} unavailable={transcripts_unavailable}")


if __name__ == "__main__":
    main()
