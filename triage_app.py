import os
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pyairtable import Api
from starlette.requests import Request

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=ENV_FILE)

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
    raise RuntimeError("Please set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in your .env file")

api = Api(AIRTABLE_API_KEY)
base = api.base(AIRTABLE_BASE_ID)
videos_table = base.table("Videos")

app = FastAPI()

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def airtable_find_first(table, formula: str):
    return table.first(formula=formula)


def get_next_queued_video() -> Optional[dict[str, Any]]:
    # Airtable formula: only videos queued for triage.
    record = airtable_find_first(videos_table, "{Triage Status}='Queued'")
    return record


def get_video_id_from_record(record: dict[str, Any]) -> Optional[str]:
    fields = record.get("fields", {})
    video_id = fields.get("Video ID")
    if isinstance(video_id, str) and video_id.strip():
        return video_id.strip()
    return None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    record = get_next_queued_video()
    if not record:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "empty": True,
            },
        )

    fields = record.get("fields", {})
    video_id = get_video_id_from_record(record)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "empty": False,
            "record_id": record.get("id"),
            "video_id": video_id,
            "title": fields.get("Video Title"),
            "url": fields.get("Video URL"),
            "triage_status": fields.get("Triage Status"),
        },
    )


@app.post("/set-status")
def set_status(record_id: str = Form(...), status: str = Form(...)):
    if status not in {"Queued", "Declined", "Done", "Skipped"}:
        return RedirectResponse(url="/", status_code=303)

    videos_table.update(record_id, {"Triage Status": status})
    return RedirectResponse(url="/", status_code=303)
