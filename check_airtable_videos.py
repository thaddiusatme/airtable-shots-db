import os
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

print(f"Using Base ID: {AIRTABLE_BASE_ID}")

api = Api(AIRTABLE_API_KEY)
base = api.base(AIRTABLE_BASE_ID)
videos_table = base.table("Videos")

print("\nFetching all videos from Airtable...")
all_videos = videos_table.all()

print(f"\nTotal records: {len(all_videos)}\n")

for video in all_videos:
    fields = video.get("fields", {})
    print(f"ID: {video['id']}")
    print(f"  Title: {fields.get('Video Title', 'N/A')}")
    print(f"  Video ID: {fields.get('Video ID', 'N/A')}")
    print(f"  Status: {fields.get('Triage Status', 'N/A')}")
    print(f"  Platform: {fields.get('Platform', 'N/A')}")
    
    transcript_full = fields.get('Transcript (Full)', '')
    if transcript_full:
        print(f"  Transcript: {transcript_full[:100]}..." if len(transcript_full) > 100 else f"  Transcript: {transcript_full}")
        print(f"  Transcript Language: {fields.get('Transcript Language', 'N/A')}")
        print(f"  Transcript Source: {fields.get('Transcript Source', 'N/A')}")
    else:
        print("  Transcript: (none)")
    print()
