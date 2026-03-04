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
    raise SystemExit(1)

api = Api(AIRTABLE_API_KEY)


def create_field(base_id: str, table_id: str, field_payload: dict) -> None:
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=field_payload,
        timeout=30,
    )

    if response.status_code == 200:
        print(f"✅ Added field: {field_payload['name']}")
    else:
        print(f"❌ Error adding {field_payload['name']}: {response.status_code} {response.text}")
        response.raise_for_status()

    time.sleep(0.3)


def main() -> None:
    schema = api.base(AIRTABLE_BASE_ID).schema()

    videos_table = next((t for t in schema.tables if t.name == "Videos"), None)
    if not videos_table:
        print("Error: Could not find a table named 'Videos' in this base")
        raise SystemExit(1)

    existing_field_names = {f.name for f in videos_table.fields}
    if "Triage Status" in existing_field_names:
        print("✅ Field already exists: Triage Status")
        return

    create_field(
        AIRTABLE_BASE_ID,
        videos_table.id,
        {
            "name": "Triage Status",
            "type": "singleSelect",
            "options": {
                "choices": [{"name": "Queued"}, {"name": "Declined"}, {"name": "Done"}],
            },
        },
    )


if __name__ == "__main__":
    main()
