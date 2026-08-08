# -*- coding: utf-8 -*-
"""fesbuk page-token onboarding — access token untuk MANAGE PAGE (posting).

BERASINGAN dari ads (fb_spend.py): page token guna permission
pages_show_list / pages_manage_posts / pages_read_engagement; ads guna
ads_read. Dua-dua flow setup sendiri-sendiri.

Aliran: user token (Graph API Explorer) -> exchange long-lived (~60 hari)
-> /me/accounts -> page token untuk PAGE_ID (never expires) -> simpan
~/.secrets/fb_page_token.txt + fb_user_token_ll.txt.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from fesbuk import config, db
except ImportError:
    import config
    import db


def _graph(path, token, fields=None):
    url = f"{config.GRAPH}/{path}?" + urllib.parse.urlencode(
        {"access_token": token, **(  {"fields": fields} if fields else {})}
    )
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            msg = body.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(msg) from e


def _app_creds():
    vals = {}
    if config.APP_FILE.exists():
        for line in config.APP_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
    return vals.get("APP_ID", ""), vals.get("APP_SECRET", "")


def exchange_long_lived(short_token):
    """fb_exchange_token -> long-lived user token (~60 hari). App mesti LIVE."""
    app_id, app_secret = _app_creds()
    if not app_id or not app_secret:
        raise RuntimeError("APP_ID / APP_SECRET takde dalam ~/.secrets/fb_app.txt")
    params = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": short_token,
    })
    try:
        with urllib.request.urlopen(f"{config.GRAPH}/oauth/access_token?{params}", timeout=25) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            msg = body.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(msg) from e
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError(data.get("error", {}).get("message", "Exchange token gagal."))
    return tok


def page_token_status(force=False):
    """Status page access token: 'ok' | 'missing' | 'broken'. Cache 1 jam dalam DB.

    'ok'      - token page wujud + boleh baca page
    'missing' - takde token page (belum setup)
    'broken'  - token ada tapi invalid/expired/kurang permission
    """
    if not force:
        cached = db.get_setting("page_status")
        at = db.get_setting("page_status_at")
        if cached and at:
            try:
                t = datetime.fromisoformat(at.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - t).total_seconds() < 3600:
                    return cached
            except Exception:
                pass
    token = ""
    if config.TOKEN_FILE.exists():
        token = config.TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token or not config.PAGE_ID:
        status = "missing"
    else:
        try:
            _graph(config.PAGE_ID, token, "id,name")
            status = "ok"
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ("permission", "invalid", "expired", "session")):
                status = "broken"
            else:
                status = "ok"  # network hiccup — jangan kacau user
    db.set_setting("page_status", status)
    db.set_setting("page_status_at", datetime.now(timezone.utc).isoformat())
    return status


def activate_page_token(raw_token):
    """User token -> long-lived -> page token utk PAGE_ID. Simpan + verify.

    Returns dict: {ok, page_id, page_name} atau {ok: False, error}.
    """
    raw = (raw_token or "").strip()
    if not raw:
        return {"ok": False, "error": "Token kosong. Salin dari Graph API Explorer dulu."}
    try:
        ll = exchange_long_lived(raw)
    except Exception as e:
        return {"ok": False, "error": f"Exchange token gagal: {e}"}
    try:
        data = _graph("me/accounts", ll, "id,name,access_token")
    except Exception as e:
        err = str(e)
        if "permission" in err.lower():
            return {"ok": False,
                    "error": "Token ni takde permission pages_show_list. Dalam Graph API Explorer "
                             "tambah pages_show_list, pages_manage_posts, pages_read_engagement, "
                             "generate semula, cuba lagi."}
        return {"ok": False, "error": err}
    pages = data.get("data", [])
    if config.PAGE_ID:
        match = next((p for p in pages if p["id"] == config.PAGE_ID), None)
        if not match:
            return {"ok": False,
                    "error": f"Page {config.PAGE_ID} takde dalam akaun ni. Pastikan user adalah "
                             "admin page tersebut."}
    elif pages:
        match = pages[0]
        # PAGE_ID kosong -> tulis page pertama ke .env
        env_path = config.ROOT / ".env"
        vals = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip()
        vals["PAGE_ID"] = match["id"]
        env_path.write_text("".join(f"{k}={v}\n" for k, v in vals.items()), encoding="utf-8")
    else:
        return {"ok": False, "error": "Takde page dijumpai untuk token ni."}
    page_token = match.get("access_token", "")
    if not page_token:
        return {"ok": False, "error": "FB tak bagi page token. Cuba lagi."}
    # Simpan page token (never expires) + long-lived user token (60 hari)
    config.TOKEN_FILE.write_text(page_token, encoding="utf-8")
    (config.SECRETS_DIR / "fb_user_token_ll.txt").write_text(ll, encoding="utf-8")
    db.set_setting("page_status", "ok")
    db.set_setting("page_status_at", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "page_id": match["id"], "page_name": match.get("name", "")}


def main():
    """CLI check: python src/fesbuk/fb_page.py"""
    print(f"page_status: {page_token_status(force=True)}")


if __name__ == "__main__":
    main()
