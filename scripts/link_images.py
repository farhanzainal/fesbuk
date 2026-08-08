# -*- coding: utf-8 -*-
"""Add image column to posts + link images used for live posts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fesbuk import db  # noqa: E402
import sqlite3  # noqa: E402

conn = sqlite3.connect(db.DB_PATH)
conn.row_factory = sqlite3.Row

# add image column if missing
cols = [r["name"] for r in conn.execute("PRAGMA table_info(posts)")]
if "image" not in cols:
    conn.execute("ALTER TABLE posts ADD COLUMN image TEXT")
    print("column image added")

IMAGES = {
    "msg_first.txt": "shah_alam_flood.jpg",
    "msg_p1.txt": "shah_alam_flood.jpg",
    "msg_hafiz.txt": "kl_flood_car.jpg",
    "msg_brand.txt": "tl_brand_final.png",
}
for f, img in IMAGES.items():
    conn.execute("UPDATE posts SET image=? WHERE msg_file=?", (img, f))
    print("linked:", f, "->", img)
conn.commit()

for r in conn.execute("SELECT id, msg_file, status, image FROM posts ORDER BY id"):
    print(f"- {r['id']} {r['msg_file']} {r['status']} img={r['image']}")
conn.close()
