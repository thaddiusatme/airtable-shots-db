import os
import time
import requests
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
    print("Error: Please set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in your .env file")
    exit(1)

api = Api(AIRTABLE_API_KEY)
schema = api.base(AIRTABLE_BASE_ID).schema()

videos_table_id = next(t.id for t in schema.tables if t.name == "Videos")

print(f"Adding Thumbnail URL field to Videos table...")

url = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables/{videos_table_id}/fields"
response = requests.post(
    url,
    headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"},
    json={"name": "Thumbnail URL", "type": "url"}
)

if response.status_code == 200:
    print(f"✅ Added Thumbnail URL field to Videos table")
else:
    print(f"❌ Error: {response.text}")
