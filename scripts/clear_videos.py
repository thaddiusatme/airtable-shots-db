import os
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

api = Api(AIRTABLE_API_KEY)
base = api.base(AIRTABLE_BASE_ID)
videos_table = base.table("Videos")

print("Fetching all videos...")
all_videos = videos_table.all()
print(f"Found {len(all_videos)} videos to delete")

if len(all_videos) == 0:
    print("No videos to delete")
    exit(0)

confirm = input(f"\n⚠️  Delete ALL {len(all_videos)} videos? Type 'yes' to confirm: ")

if confirm.lower() != 'yes':
    print("Cancelled")
    exit(0)

print("\nDeleting videos...")
for video in all_videos:
    video_id = video['id']
    title = video.get('fields', {}).get('Video Title', 'N/A')
    videos_table.delete(video_id)
    print(f"  ✅ Deleted: {title}")

print(f"\n✅ Deleted {len(all_videos)} videos")
