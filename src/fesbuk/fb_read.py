# -*- coding: utf-8 -*-
"""Read recent posts from the configured Facebook Page + engagement.
Usage: python src/fb_read.py [limit]   (default 10)
"""
import sys
import json
import urllib.request
import urllib.parse
try:
    from fesbuk import config
except ImportError:
    import config


def api(path, params):
    token = config.load_token()
    url = f"{config.GRAPH}/{path}?" + urllib.parse.urlencode({**params, "access_token": token})
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    if not config.PAGE_ID:
        print("ERROR: PAGE_ID kosong — set dalam fesbuk/.env")
        sys.exit(1)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    posts = api(f"{config.PAGE_ID}/posts",
                {"fields": "id,message,created_time", "limit": limit}).get("data", [])
    print(f"=== POSTS TERKINI ({len(posts)}) ===")
    for p in posts:
        pid = p["id"]
        msg = (p.get("message") or "").replace("\n", " ")[:70]
        try:
            eng = api(pid, {"fields": "reactions.summary(true),comments.summary(true),shares"})
            r = eng.get("reactions", {}).get("summary", {}).get("total_count", 0)
            c = eng.get("comments", {}).get("summary", {}).get("total_count", 0)
            s = (eng.get("shares") or {}).get("count", 0)
        except Exception:
            r = c = s = "?"
        print(f"- {p.get('created_time')[:10]} | react={r} komen={c} share={s} | {msg}")
        print(f"  https://www.facebook.com/{pid}")


if __name__ == "__main__":
    main()
