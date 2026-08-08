# -*- coding: utf-8 -*-
"""Post message to the configured Facebook Page.
Usage:
  python src/fb_post.py msg.txt                 # text post from UTF-8 file
  python src/fb_post.py --text "..."            # inline text post
  python src/fb_post.py --image <url> msg.txt   # photo post (image URL + message)
"""
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from fesbuk import config
except ImportError:
    import config


def _token_for(page_id=None):
    """Page token for the given page (or the configured page)."""
    if page_id and page_id != config.PAGE_ID:
        return get_page_token(page_id)
    return config.load_token()


def get_page_token(page_id: str) -> str:
    """Fetch the access token for a specific page via the long-lived user token."""
    import requests
    utoken = config.load_user_token()
    if not utoken:
        raise RuntimeError("User token tiada dalam DB")
    resp = requests.get(
        f"{config.GRAPH}/me/accounts",
        params={"access_token": utoken, "fields": "id,name,access_token"},
        timeout=30,
    )
    data = resp.json()
    for p in data.get("data", []):
        if p["id"] == str(page_id) and p.get("access_token"):
            return p["access_token"]
    raise RuntimeError(f"Page {page_id} tak jumpa / takde token")


def post_message(message: str, page_id: str = None) -> dict:
    token = _token_for(page_id)
    url = f"{config.GRAPH}/{page_id or config.PAGE_ID}/feed"
    data = urllib.parse.urlencode({
        "message": message,
        "access_token": token,
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def post_photo(image_url: str, message: str, page_id: str = None) -> dict:
    token = _token_for(page_id)
    url = f"{config.GRAPH}/{page_id or config.PAGE_ID}/photos"
    data = urllib.parse.urlencode({
        "url": image_url,
        "message": message,
        "access_token": token,
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def post_photo_file(image_path, message: str, page_id: str = None) -> dict:
    """Upload a LOCAL image file as a photo post (multipart, via requests)."""
    import requests
    token = _token_for(page_id)
    url = f"{config.GRAPH}/{page_id or config.PAGE_ID}/photos"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data={"message": message, "access_token": token},
            files={"source": f},
            timeout=120,
        )
    return resp.json()


def main():
    if not config.PAGE_ID:
        print("ERROR: PAGE_ID kosong — set dalam fesbuk/.env")
        sys.exit(1)
    args = sys.argv[1:]
    if not args:
        print('Guna: python src/fb_post.py msg.txt | --text "..." | --image <url> msg.txt')
        sys.exit(1)
    if args[0] == "--text":
        text = " ".join(args[1:])
        result = post_message(text)
    elif args[0] == "--db":
        # read text from the dashboard DB (all content lives in database/fesbuk.db)
        msg_file = args[1]
        try:
            from fesbuk import db as _db
        except ImportError:
            import db as _db
        row = _db.get_post_by_file(msg_file)
        if not row:
            print("ERROR: tiada rekod dalam DB untuk:", msg_file)
            sys.exit(1)
        result = post_message(row["text"])
        _db.mark_posted(msg_file, result["id"])
    elif args[0] == "--image":
        image_url = args[1]
        text = open(args[2], encoding="utf-8").read().strip() if len(args) > 2 else ""
        result = post_photo(image_url, text)
    else:
        text = open(args[0], encoding="utf-8").read().strip()
        result = post_message(text)
    print(json.dumps(result, ensure_ascii=False))
    if "id" in result:
        print("LIVE: https://www.facebook.com/" + result["id"])
        # record into dashboard DB (if the message came from knowledge/msgs/)
        try:
            import db as _db
            src = args[2] if args and args[0] == "--image" and len(args) > 2 else (args[0] if args else "")
            if src and "knowledge" in str(src):
                _db.seed_from_msgs()
                _db.mark_posted(Path(src).name, result["id"])
                print("[db] marked posted:", Path(src).name)
        except Exception as e:
            print(f"[db] skip ({e})")
    else:
        print("ERROR:", result)
        sys.exit(2)


if __name__ == "__main__":
    main()
