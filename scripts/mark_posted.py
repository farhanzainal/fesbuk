# -*- coding: utf-8 -*-
"""Mark already-posted msg files as posted in the dashboard DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fesbuk import db  # noqa: E402

db.seed_from_msgs()
MAPPING = {
    "msg_first.txt": "122094462519440123",
    "msg_brand.txt": "122094478419440123",
    "msg_p1.txt": "122094503703440123",
    "msg_hafiz.txt": "122094511221440123",
}
for f, pid in MAPPING.items():
    db.mark_posted(f, pid)
    print("marked posted:", f, pid)
for p in db.get_posts():
    print(f"- {p['id']} {p['msg_file']} {p['status']}")
