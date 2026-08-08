# -*- coding: utf-8 -*-
"""Test FB setup: token validity + page info. Usage: python src/fb_test.py"""
import json
import sys
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
    page_id = config.PAGE_ID
    if not page_id:
        print("ERROR: PAGE_ID kosong — set dalam fesbuk/.env")
        sys.exit(1)
    token = config.load_token()
    if not token:
        print("ERROR: Tiada page token dalam DB (fb_page_token).")
        print("Sambung page dulu: dashboard → 'Sambung Facebook Page' atau")
        print("python src/fb_setup.py --token <page-token>")
        sys.exit(1)
    print("=== FB TEST ===")
    info = api(page_id, {"fields": "id,name,fan_count,link,about"})
    print(f"Page : {info.get('name')} ({info.get('id')})")
    print(f"Fans : {info.get('fan_count')}")
    print(f"Link : {info.get('link')}")
    print(f"About: {info.get('about', '-')}")

    try:
        app_tok = config.load_app_token()
        url = f"{config.GRAPH}/debug_token?input_token={config.load_token()}&access_token={app_tok}"
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode()).get("data", {})
        print(f"Token: type={d.get('type')} valid={d.get('is_valid')} expires_at={d.get('expires_at')} "
              f"(0 = never)")
        print("Scopes:", [s for s in d.get("scopes", []) if "page" in s])
    except Exception as e:
        print(f"Token debug: SKIP ({e})")
    print("\nSTATUS: OK")


if __name__ == "__main__":
    main()
