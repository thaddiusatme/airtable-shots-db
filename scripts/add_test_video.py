import os
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

api = Api(AIRTABLE_API_KEY)
base = api.base(AIRTABLE_BASE_ID)
videos_table = base.table("Videos")

# Create a few test videos
test_videos = [
    {
        "Video Title": "Test Video 1 - Introduction to Python",
        "Video ID": "test-001",
        "Platform": "YouTube",
        "Video URL": "https://www.youtube.com/watch?v=kqtD5dpn9C8",
        "Triage Status": "Queued",
    },
    {
        "Video Title": "Test Video 2 - FastAPI Tutorial",
        "Video ID": "test-002",
        "Platform": "YouTube",
        "Video URL": "https://www.youtube.com/watch?v=7t2alSnE2-I",
        "Triage Status": "Queued",
    },
    {
        "Video Title": "Test Video 3 - Airtable API Guide",
        "Video ID": "test-003",
        "Platform": "YouTube",
        "Video URL": "https://www.youtube.com/watch?v=kqtD5dpn9C8",
        "Triage Status": "Queued",
    },
]

for video in test_videos:
    # Check if already exists
    existing = videos_table.first(formula=f"{{Video ID}}='{video['Video ID']}'")
    if existing:
        print(f"SKIP: {video['Video Title']} (already exists)")
    else:
        videos_table.create(video)
        print(f"CREATE: {video['Video Title']}")

print("\nDone! Refresh your Airtable to see the test videos.")
print("Visit http://localhost:8000 to triage them.")
