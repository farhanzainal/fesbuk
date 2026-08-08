# -*- coding: utf-8 -*-
"""Publish due scheduled posts from the DB. Silent when nothing is due.
Cron: every 10 minutes (no_agent)."""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fesbuk import db, fb_post, config  # noqa: E402

due = db.get_due_posts(datetime.now(timezone.utc).isoformat())
if not due:
    raise SystemExit(0)  # senyap — tiada post due

for p in due:
    try:
        page_id = p.get("page_id") or config.PAGE_ID
        if p.get("image"):
            result = fb_post.post_photo_file(str(db.DB_DIR / "images" / p["image"]), p["text"], page_id)
        else:
            result = fb_post.post_message(p["text"], page_id)
        if "id" in result:
            db.mark_posted_by_id(p["id"], result["id"])
            print(f"POSTED #{p['id']} -> https://www.facebook.com/{result['id']}")
        else:
            print(f"FAIL #{p['id']}: {result}")
    except Exception as e:
        print(f"ERROR #{p['id']}: {e}")
