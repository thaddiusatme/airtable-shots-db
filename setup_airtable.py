import os
import time
import requests
from dotenv import load_dotenv
from pyairtable import Api

# Load environment variables from .env file
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_WORKSPACE_ID = os.getenv("AIRTABLE_WORKSPACE_ID")

if not AIRTABLE_API_KEY or not AIRTABLE_WORKSPACE_ID:
    print("Error: Please set AIRTABLE_API_KEY and AIRTABLE_WORKSPACE_ID in your .env file")
    exit(1)

api = Api(AIRTABLE_API_KEY)
workspace = api.workspace(AIRTABLE_WORKSPACE_ID)

def create_field(base_id, table_id, field_payload):
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"},
        json=field_payload
    )
    if response.status_code == 200:
        print(f"    ✅ Added field: {field_payload['name']}")
    else:
        print(f"    ❌ Error adding {field_payload['name']}: {response.text}")
    # Small sleep to respect rate limits
    time.sleep(0.3)

def build_schema():
    print(f"Step 1: Creating a new Base in Workspace: {AIRTABLE_WORKSPACE_ID}...")

    # Step 1: Create the empty base with just the primary fields
    initial_tables = [
        {
            "name": "Channels",
            "description": "Creators/Platforms",
            "fields": [{"name": "Channel Name", "type": "singleLineText"}]
        },
        {
            "name": "Videos",
            "description": "Source Videos",
            "fields": [{"name": "Video Title", "type": "singleLineText"}]
        },
        {
            "name": "Shots",
            "description": "Swipe file for video shots (screenshots)",
            "fields": [{"name": "Shot Label", "type": "singleLineText"}]
        }
    ]

    try:
        new_base = workspace.create_base("Video Swipe File", initial_tables)
        base_id = new_base.id
        print(f"✅ Created Base! ID: {base_id}")
    except Exception as e:
         print(f"❌ Error creating the Base: {e}")
         return

    # To add fields we need the actual table IDs. Let's fetch the base schema.
    schema = api.base(base_id).schema()
    
    channels_table_id = next(t.id for t in schema.tables if t.name == "Channels")
    videos_table_id = next(t.id for t in schema.tables if t.name == "Videos")
    shots_table_id = next(t.id for t in schema.tables if t.name == "Shots")

    print("\nStep 2: Adding schema to 'Channels' table...")
    create_field(base_id, channels_table_id, {"name": "Channel URL", "type": "url"})
    create_field(base_id, channels_table_id, {"name": "Platform", "type": "singleSelect", "options": {"choices": [
        {"name": "YouTube"}, {"name": "TikTok"}, {"name": "Instagram"}, {"name": "X"}, {"name": "Other"}
    ]}})

    print("\nStep 3: Adding schema to 'Videos' table...")
    create_field(base_id, videos_table_id, {"name": "Video URL", "type": "url"})
    create_field(base_id, videos_table_id, {"name": "Video ID", "type": "singleLineText"})
    create_field(base_id, videos_table_id, {"name": "Channel", "type": "multipleRecordLinks", "options": {
        "linkedTableId": channels_table_id
    }})
    create_field(base_id, videos_table_id, {"name": "Platform", "type": "singleLineText"})
    create_field(base_id, videos_table_id, {"name": "Thumbnail URL", "type": "url"})
    create_field(base_id, videos_table_id, {"name": "Transcript (Full)", "type": "multilineText"})
    create_field(base_id, videos_table_id, {"name": "Transcript (Timestamped)", "type": "multilineText"})
    create_field(base_id, videos_table_id, {"name": "Transcript Language", "type": "singleLineText"})
    create_field(base_id, videos_table_id, {"name": "Transcript Source", "type": "singleLineText"})


    print("\nStep 4: Adding schema to 'Shots' table...")
    # Linking
    create_field(base_id, shots_table_id, {"name": "Video", "type": "multipleRecordLinks", "options": {"linkedTableId": videos_table_id}})
    create_field(base_id, shots_table_id, {"name": "Shot Image", "type": "multipleAttachment"})

    # Timestamps
    create_field(base_id, shots_table_id, {"name": "Timestamp (sec)", "type": "number", "options": {"precision": 0}})
    create_field(base_id, shots_table_id, {"name": "Timestamp (hh:mm:ss)", "type": "singleLineText"})

    # Categorization
    create_field(base_id, shots_table_id, {"name": "Shot Function", "type": "singleSelect", "options": {"choices": [
        {"name": "Hook"}, {"name": "Proof"}, {"name": "Payoff"}, {"name": "B-roll"},
        {"name": "Transition"}, {"name": "CTA"}, {"name": "Other"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "Shot Type", "type": "singleSelect", "options": {"choices": [
        {"name": "Wide"}, {"name": "Medium"}, {"name": "Close-up"}, {"name": "POV"},
        {"name": "OTS"}, {"name": "Insert"}, {"name": "Establishing"}, {"name": "Screen"},
        {"name": "Drone"}, {"name": "Other"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "Camera Angle", "type": "singleSelect", "options": {"choices": [
        {"name": "Eye-level"}, {"name": "High"}, {"name": "Low"}, {"name": "Top-down"},
        {"name": "Dutch"}, {"name": "Other"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "Movement", "type": "multipleSelects", "options": {"choices": [
        {"name": "Static"}, {"name": "Pan"}, {"name": "Tilt"}, {"name": "Push-in"},
        {"name": "Pull-out"}, {"name": "Handheld"}, {"name": "Gimbal"}, {"name": "Zoom"},
        {"name": "Whip-pan"}, {"name": "Other"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "Lighting", "type": "singleSelect", "options": {"choices": [
        {"name": "Natural-soft"}, {"name": "Natural-hard"}, {"name": "Studio-soft"},
        {"name": "Backlit"}, {"name": "Mixed"}, {"name": "Neon"}, {"name": "Other"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "Setting", "type": "singleLineText"})
    create_field(base_id, shots_table_id, {"name": "Subject", "type": "singleLineText"})
    create_field(base_id, shots_table_id, {"name": "On-screen Text", "type": "multilineText"})

    # Notes & Tags
    create_field(base_id, shots_table_id, {"name": "Description (Manual)", "type": "multilineText"})
    create_field(base_id, shots_table_id, {"name": "Tags", "type": "multipleSelects", "options": {"choices": [
        {"name": "talking-head"}, {"name": "b-roll"}, {"name": "text-overlay"},
        {"name": "transition"}, {"name": "screen-recording"}
    ]}})

    # AI Ops
    create_field(base_id, shots_table_id, {"name": "AI Status", "type": "singleSelect", "options": {"choices": [
        {"name": "Queued"}, {"name": "Processing"}, {"name": "Done"}, {"name": "Error"}
    ]}})
    create_field(base_id, shots_table_id, {"name": "AI Description (Local)", "type": "multilineText"})
    create_field(base_id, shots_table_id, {"name": "AI JSON", "type": "multilineText"})
    create_field(base_id, shots_table_id, {"name": "AI Model", "type": "singleLineText"})
    create_field(base_id, shots_table_id, {"name": "AI Prompt Version", "type": "singleLineText"})
    create_field(base_id, shots_table_id, {"name": "AI Updated At", "type": "dateTime", "options": {
        "dateFormat": {"name": "local"},
        "timeFormat": {"name": "12hour"},
        "timeZone": "client"
    }})
    create_field(base_id, shots_table_id, {"name": "AI Error", "type": "multilineText"})

    # Transcript
    create_field(base_id, shots_table_id, {"name": "Transcript Line", "type": "multilineText"})
    create_field(base_id, shots_table_id, {"name": "Transcript Start (sec)", "type": "number", "options": {"precision": 0}})
    create_field(base_id, shots_table_id, {"name": "Transcript End (sec)", "type": "number", "options": {"precision": 0}})

    # Housekeeping
    create_field(base_id, shots_table_id, {"name": "Captured At", "type": "dateTime", "options": {
         "dateFormat": {"name": "local"},
         "timeFormat": {"name": "12hour"},
         "timeZone": "client"
    }})
    create_field(base_id, shots_table_id, {"name": "Rights Note", "type": "multilineText"})

    print("\n✅ API Schema creation complete!")
    print(f"You can now visit Airtable to see your new base: https://airtable.com/{base_id}")

if __name__ == "__main__":
    build_schema()
