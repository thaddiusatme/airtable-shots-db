import os
import pathlib
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

client_secret_file = pathlib.Path(__file__).resolve().parent / "client_secret.json"
token_file = pathlib.Path(__file__).resolve().parent / "token.json"

creds = None
if token_file.exists():
    creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())

if not creds or not creds.valid:
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")

youtube = build("youtube", "v3", credentials=creds)

# List all playlists for this account
print("Fetching your YouTube playlists...\n")
page_token = None
playlist_count = 0

while True:
    response = youtube.playlists().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50,
        pageToken=page_token
    ).execute()
    
    items = response.get("items", [])
    
    for pl in items:
        playlist_count += 1
        snippet = pl.get("snippet", {})
        content_details = pl.get("contentDetails", {})
        
        print(f"#{playlist_count}")
        print(f"  Title: {snippet.get('title')}")
        print(f"  ID: {pl.get('id')}")
        print(f"  Privacy: {snippet.get('privacyStatus', 'unknown')}")
        print(f"  Items: {content_details.get('itemCount', 0)}")
        print()
    
    page_token = response.get("nextPageToken")
    if not page_token:
        break

print(f"\nTotal playlists: {playlist_count}")
print("\nTo import a playlist, use:")
print('  .venv/bin/python import_watch_later.py --playlist-id "PLAYLIST_ID_HERE"')
