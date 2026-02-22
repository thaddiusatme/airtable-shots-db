"""
update_notion.py
Updates the "Swiped Shot List Library" Notion page with the v2 Airtable schema.

Requirements:
  1. NOTION_TOKEN in .env (Internal Integration Secret from notion.so/my-integrations)
  2. The integration must be invited to the page (Share → Invite → select integration)

Usage:
  python update_notion.py
"""

import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
if not NOTION_TOKEN:
    print("❌ NOTION_TOKEN not set in .env")
    print("   1. Go to https://www.notion.so/my-integrations")
    print("   2. Create an integration and copy the token")
    print("   3. Share the Notion page with that integration")
    print("   4. Add NOTION_TOKEN=secret_... to .env")
    exit(1)

PAGE_ID = "30d51d439135812caedafdad7866919e"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_blocks(block_id):
    """Return all children of a block (handles pagination)."""
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    results = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        results.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
        time.sleep(0.2)
    return results

def delete_block(block_id):
    r = requests.delete(f"https://api.notion.com/v1/blocks/{block_id}", headers=HEADERS)
    r.raise_for_status()
    time.sleep(0.15)

def append_blocks(parent_id, children):
    """Append blocks to a parent, chunked to 100 per request."""
    url = f"https://api.notion.com/v1/blocks/{parent_id}/children"
    for i in range(0, len(children), 100):
        chunk = children[i:i+100]
        r = requests.patch(url, headers=HEADERS, json={"children": chunk})
        if not r.ok:
            print(f"  ❌ append_blocks error: {r.status_code} {r.text[:300]}")
            r.raise_for_status()
        time.sleep(0.3)

def rich(text, bold=False, code=False):
    """Build a simple rich_text array."""
    obj = {"type": "text", "text": {"content": text}}
    if bold or code:
        obj["annotations"] = {}
        if bold:
            obj["annotations"]["bold"] = True
        if code:
            obj["annotations"]["code"] = True
    return [obj]

def h4(text):
    return {"object": "block", "type": "heading_4",
            "heading_4": {"rich_text": rich(text)}}

def para(text, bold=False):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": rich(text, bold=bold)}}

def bullet(text, bold_prefix=None):
    """Bullet with optional bold prefix like 'Field Name — ' rest normal."""
    if bold_prefix:
        rt = [
            {"type": "text", "text": {"content": bold_prefix},
             "annotations": {"bold": True}},
            {"type": "text", "text": {"content": text}},
        ]
    else:
        rt = rich(text)
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rt}}

def todo(text, checked=False):
    return {"object": "block", "type": "to_do",
            "to_do": {"rich_text": rich(text), "checked": checked}}

def divider():
    return {"object": "block", "type": "divider", "divider": {}}

def find_block_by_text(blocks, needle, block_type=None):
    """Find first block whose plain text contains needle."""
    for b in blocks:
        if block_type and b["type"] != block_type:
            continue
        btype = b["type"]
        rt = b.get(btype, {}).get("rich_text", [])
        text = "".join(t.get("plain_text", "") for t in rt)
        if needle in text:
            return b
    return None

# ---------------------------------------------------------------------------
# New content blocks
# ---------------------------------------------------------------------------

SCHEMA_BLOCKS = [
    h4("Architecture: Three Normalized Tables (v2)"),
    para("Channels → Videos → Shots, linked via record links. Formula-based UID fields provide stable dedup keys for AI reprocessing."),

    h4("Channels"),
    bullet("Channel Name — primary field"),
    bullet("Channel URL — url"),
    bullet("Platform — singleSelect (YouTube, TikTok, Instagram, X, Other)"),
    bullet("Channel Handle — singleLineText"),
    bullet("Channel UID — formula: LOWER(SUBSTITUTE({Channel Name},\" \",\"\")) & \"|\" & {Platform}"),

    h4("Videos"),
    bullet("Video Title — primary field"),
    bullet("Video URL — url"),
    bullet("Video ID — singleLineText (platform-native)"),
    bullet("Platform — singleSelect (YouTube, TikTok, Instagram, X, Other)"),
    bullet("Channel — link → Channels"),
    bullet("Video UID — formula: {Platform} & \"|\" & {Video ID}"),
    bullet("Transcript (Full) — multilineText"),
    bullet("Transcript Source — singleSelect (YouTube, Whisper, Other)"),
    bullet("Transcript Language — singleLineText"),

    h4("Shots — Core & Visuals"),
    bullet("Shot Label — primary field"),
    bullet("Video — link → Videos"),
    bullet("Shot Image — attachment"),
    bullet("Timestamp (sec) — number"),
    bullet("Timestamp (hh:mm:ss) — singleLineText"),
    bullet("Shot UID — formula: {Video UID} & \"|\" & ROUND({Timestamp (sec)}, 0)"),

    h4("Shots — Categorization"),
    bullet("Shot Function — singleSelect: Hook, Proof, Payoff, B-roll, Transition, CTA, Other"),
    bullet("Shot Type — singleSelect: Talking-head, Wide, Medium, Close-up, POV, OTS, Insert, Establishing, Screen, Drone, Other"),
    bullet("Camera Angle — singleSelect: Eye-level, High, Low, Top-down, Dutch, Other"),
    bullet("Movement — multiSelect: Static, Pan, Tilt, Push-in, Pull-out, Handheld, Gimbal, Zoom, Whip-pan, Other"),
    bullet("Lighting — singleSelect: Natural-soft, Natural-hard, Studio-soft, Backlit, Mixed, Neon, Practical, Other"),
    bullet("Setting, Subject, On-screen Text — text fields"),

    h4("Shots — Tags"),
    bullet("Tags (Controlled) — multiSelect: talking-head, b-roll, text-overlay, transition, screen-recording"),
    bullet("Tags (Raw) — singleLineText (AI freeform dump; map to controlled via automation)"),

    h4("Shots — AI Operations"),
    bullet("AI Status — singleSelect: Queued, Processing, Done, Error"),
    bullet("AI Description (Local) — multilineText"),
    bullet("AI JSON — multilineText (latest canonical output)"),
    bullet("AI Model — singleLineText"),
    bullet("AI Prompt Version — singleLineText"),
    bullet("AI Updated At — dateTime"),
    bullet("AI Error — multilineText"),
    bullet("AI Run ID — singleLineText (stable per-run tracking)"),
    bullet("AI Input Hash — singleLineText (hash of prompt + image URLs + metadata)"),

    h4("Shots — Transcript & Operational"),
    bullet("Transcript Line — multilineText (shot-level excerpt)"),
    bullet("Transcript Start / End (sec) — number"),
    bullet("Capture Method — singleSelect: Manual, Screenshot Swipe, Auto Import"),
    bullet("Source Device — singleSelect: S23 Ultra, Desktop, Other"),
    bullet("Needs Review — checkbox"),
    bullet("Captured At — dateTime"),
    bullet("Rights Note — multilineText"),
]

TECH_STACK_NEW_ROWS = [
    {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [
                rich("Schema Setup"),
                rich("Python (setup_airtable.py)"),
                rich("Programmatic base provisioning via Airtable REST API"),
            ]
        }
    },
    {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [
                rich("AI Processing (Phase 2)"),
                rich("Local Worker Script"),
                rich("Queue-based AI image description with dedup via Shot UID + AI Input Hash"),
            ]
        }
    },
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Fetching blocks from page {PAGE_ID}...")
    top_blocks = get_blocks(PAGE_ID)
    print(f"  Found {len(top_blocks)} top-level blocks.")

    # -----------------------------------------------------------------------
    # 1. Update Tech Stack table
    # -----------------------------------------------------------------------
    print("\n1️⃣  Updating Tech Stack table...")
    tech_block = find_block_by_text(top_blocks, "Tech Stack", "heading_3")
    if not tech_block:
        print("  ⚠️  Could not find '🏗️ Tech Stack' heading. Skipping.")
    else:
        # The table is a sibling block right after the heading
        tech_idx = top_blocks.index(tech_block)
        table_block = None
        for b in top_blocks[tech_idx:tech_idx + 5]:
            if b["type"] == "table":
                table_block = b
                break
        if not table_block:
            print("  ⚠️  Could not find table block under Tech Stack. Skipping.")
        else:
            append_blocks(table_block["id"], TECH_STACK_NEW_ROWS)
            print("  ✅ Appended 2 new rows to Tech Stack table.")

    # -----------------------------------------------------------------------
    # 2. Replace Airtable Schema Design section
    # -----------------------------------------------------------------------
    print("\n2️⃣  Replacing Airtable Schema Design section...")
    schema_block = find_block_by_text(top_blocks, "Airtable Schema Design", "heading_3")
    if not schema_block:
        print("  ⚠️  Could not find 'Airtable Schema Design' heading. Skipping.")
    else:
        # Fetch its children and delete them all
        schema_children = get_blocks(schema_block["id"])
        print(f"  Deleting {len(schema_children)} existing schema child blocks...")
        for child in schema_children:
            # Also delete grandchildren (subheading children)
            grandchildren = get_blocks(child["id"])
            for gc in grandchildren:
                delete_block(gc["id"])
            delete_block(child["id"])
        # Append new blocks
        append_blocks(schema_block["id"], SCHEMA_BLOCKS)
        print(f"  ✅ Schema section replaced with {len(SCHEMA_BLOCKS)} new blocks.")

    # -----------------------------------------------------------------------
    # 3. Update Phase 1 checklist — add completed item at top
    # -----------------------------------------------------------------------
    print("\n3️⃣  Updating Phase 1 checklist...")
    phase1_block = find_block_by_text(top_blocks, "Phase 1", "heading_4")
    if not phase1_block:
        print("  ⚠️  Could not find 'Phase 1' heading. Skipping.")
    else:
        phase1_children = get_blocks(phase1_block["id"])
        # Find the first to_do item and prepend before it by appending then relying on order
        # Notion API doesn't support prepend natively, so we insert at the block level
        # We'll append and note to user it'll appear at the bottom of phase 1
        new_item = todo("Provision Airtable base with v2 three-table schema via setup_airtable.py", checked=True)
        # Prepend by appending before existing items: not directly possible via API.
        # Best workaround: delete all, re-add with new item first.
        existing_todos = [b for b in phase1_children]
        print(f"  Re-ordering {len(existing_todos)} Phase 1 items to prepend new item...")
        for b in existing_todos:
            delete_block(b["id"])
        rebuilt = [new_item] + [
            {
                "object": "block",
                "type": b["type"],
                b["type"]: b[b["type"]]
            }
            for b in existing_todos
        ]
        append_blocks(phase1_block["id"], rebuilt)
        print("  ✅ Phase 1: added checked item at top.")

    # -----------------------------------------------------------------------
    # 4. Update Phase 3 — mark transcript item as done
    # -----------------------------------------------------------------------
    print("\n4️⃣  Updating Phase 3 transcript item...")
    phase3_block = find_block_by_text(top_blocks, "Phase 3", "heading_4")
    if not phase3_block:
        print("  ⚠️  Could not find 'Phase 3' heading. Skipping.")
    else:
        phase3_children = get_blocks(phase3_block["id"])
        for b in phase3_children:
            btype = b["type"]
            rt = b.get(btype, {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rt)
            if "Timestamp and Transcript" in text or "transcript" in text.lower():
                # Update this block to checked + new text
                r = requests.patch(
                    f"https://api.notion.com/v1/blocks/{b['id']}",
                    headers=HEADERS,
                    json={
                        "to_do": {
                            "rich_text": rich("Transcript fields added to v2 schema — Video-level (Full + Source + Language) and Shot-level excerpt. DONE ✅"),
                            "checked": True,
                        }
                    }
                )
                if r.ok:
                    print("  ✅ Phase 3 transcript item marked complete.")
                else:
                    print(f"  ⚠️  Could not update Phase 3 item: {r.text[:200]}")
                break

    print("\n✅ Notion page update complete!")
    print(f"   View: https://www.notion.so/{PAGE_ID.replace('-', '')}")

if __name__ == "__main__":
    main()
