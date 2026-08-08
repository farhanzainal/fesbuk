# -*- coding: utf-8 -*-
"""fesbuk ad spend tracker — pull spend/impressions/clicks from FB Ads API.

Needs a user token with `ads_read` permission:
  GET /me/adaccounts  -> act_XXX
  GET /act_XXX/insights?fields=spend,impressions,clicks,ctr,cpc&date_preset=...
Snapshots are stored in database/fesbuk.db (table `spend`).

Usage:
  python src/fesbuk/fb_spend.py            # pull + store + print summary
  from fesbuk import fb_spend; fb_spend.pull_and_store()
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from fesbuk import config, db
except ImportError:
    import config
    import db


def _graph(path, token, params=None):
    q = {"access_token": token}
    if params:
        q.update(params)
    url = f"{config.GRAPH}/{path}?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # FB balas JSON dgn mesej sebenar (cth "Missing Permissions") — asingkan dari
        # "HTTP Error 403" generik supaya mesej difahami.
        try:
            body = json.loads(e.read().decode())
            msg = body.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(msg) from e


def user_token():
    """Ads token — DB settings (fb_ads_token), separate from page token
    (fb_page_token). Removing the ads token never breaks the dashboard."""
    return config.load_ads_token()


def get_ad_accounts(token):
    """GET /me/adaccounts -> [{id, name, account_status}]. Needs ads_read."""
    data = _graph("me/adaccounts", token, {"fields": "id,name,account_status"})
    return data.get("data", [])


def fetch_insights(act_id, token, date_preset="this_month"):
    """GET /act_XXX/insights -> {spend, impressions, clicks, ctr, cpc}."""
    data = _graph(
        f"{act_id}/insights",
        token,
        {
            "fields": "spend,impressions,clicks,ctr,cpc",
            "date_preset": date_preset,
        },
    )
    if data.get("data"):
        return data["data"][0]
    return {}


def exchange_long_lived(short_token):
    """fb_exchange_token -> long-lived user token (~60 hari). Needs app ID+secret LIVE."""
    vals = {}
    if config.APP_FILE.exists():
        for line in config.APP_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
    app_id, app_secret = vals.get("APP_ID", ""), vals.get("APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("APP_ID / APP_SECRET takde dalam ~/.secrets/fb_app.txt")
    params = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": short_token,
    })
    url = f"{config.GRAPH}/oauth/access_token?{params}"
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
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
        msg = data.get("error", {}).get("message", "Exchange token gagal.")
        raise RuntimeError(msg)
    return tok


def activate_token(raw_token):
    """Aktifkan tracking: exchange -> long-lived, verify ads_read, simpan token, pull spend."""
    raw_token = (raw_token or "").strip()
    if not raw_token:
        return {"ok": False, "error": "Token kosong. Salin token dari Graph API Explorer dulu."}
    try:
        ll = exchange_long_lived(raw_token)
    except Exception as e:
        return {"ok": False, "error": f"Exchange token gagal: {e}"}
    try:
        accts = get_ad_accounts(ll)
    except Exception as e:
        err = str(e)
        if "permission" in err.lower():
            return {"ok": False,
                    "error": "Token ni takde permission ads_read. Dalam Graph API Explorer, "
                             "tambah permission ads_read, generate semula token, cuba lagi."}
        return {"ok": False, "error": err}
    if not accts:
        return {"ok": False,
                "error": "Token OK tapi user takde kaitan dgn mana-mana ad account. "
                         "Sambung user dalam Ads Manager / Business Manager dulu."}
    # Simpan long-lived ads token (60 hari) — DB settings, asing dari
    # fb_page_token (page connection). Buang key ni = buang token ads.
    db.set_token("fb_ads_token", ll)
    act = accts[0]
    results = {}
    for preset in ("last_7d", "this_month"):
        try:
            results[preset] = fetch_insights(act["id"], ll, preset)
        except Exception as e:
            results[preset] = {"error": str(e)}
    db.save_spend(act["id"], act.get("name", ""), results)
    db.set_setting("ads_status", "ready")
    db.set_setting("ads_status_at", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "ad_account": act["id"], "account_name": act.get("name", ""),
            "results": results, "token_expires": "60 hari"}


def ads_status(force=False):
    """Status ads_read token user: 'ready' | 'missing_permission' | 'no_token' | 'no_ad_account' | 'error'.

    1 API call je (/me/adaccounts), cache 1 jam dalam DB supaya dashboard
    tak pukul API setiap kali load. force=True untuk check segar.
    """
    if not force:
        cached = db.get_setting("ads_status")
        at = db.get_setting("ads_status_at")
        if cached and at:
            try:
                t = datetime.fromisoformat(at.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - t).total_seconds() < 3600:
                    return cached
            except Exception:
                pass
    token = user_token()
    if not token:
        status = "no_token"
    else:
        try:
            accts = get_ad_accounts(token)
            status = "ready" if accts else "no_ad_account"
        except Exception as e:
            status = "missing_permission" if "permission" in str(e).lower() else "error"
    db.set_setting("ads_status", status)
    db.set_setting("ads_status_at", datetime.now(timezone.utc).isoformat())
    return status


def pull_and_store():
    """Pull latest spend snapshots + store in DB. Returns summary dict."""
    token = user_token()
    if not token:
        return {"ok": False,
                "error": "Tiada user token. Tampal token di halaman Ads Manager dulu."}
    try:
        accts = get_ad_accounts(token)
    except Exception as e:
        err = str(e)
        if "Missing Permissions" in err or "permission" in err.lower():
            db.set_setting("ads_status", "missing_permission")
            db.set_setting("ads_status_at", datetime.now(timezone.utc).isoformat())
            return {"ok": False,
                    "error": "Token TAKDE permission ads_read. Regenerate token dalam Graph API "
                             "Explorer (tambah permission ads_read), lepas tu tampal token baru "
                             "di halaman Ads Manager."}
        return {"ok": False, "error": err}
    if not accts:
        return {"ok": False,
                "error": "Takde ad account dijumpai untuk token ni. Pastikan user ada "
                         "kaitan dgn mana-mana ad account (Business Manager / Ads Manager)."}
    db.set_setting("ads_status", "ready")
    db.set_setting("ads_status_at", datetime.now(timezone.utc).isoformat())
    act = accts[0]
    results = {}
    for preset in ("last_7d", "this_month"):
        try:
            results[preset] = fetch_insights(act["id"], token, preset)
        except Exception as e:
            results[preset] = {"error": str(e)}
    db.save_spend(act["id"], act.get("name", ""), results)
    return {"ok": True, "ad_account": act["id"], "account_name": act.get("name", ""),
            "results": results}


def main():
    res = pull_and_store()
    if not res.get("ok"):
        print(f"ERROR: {res.get('error')}")
        sys.exit(1)
    print(f"Ad account: {res['ad_account']} ({res['account_name']})")
    for preset, row in res["results"].items():
        if "error" in row:
            print(f"  {preset}: ERROR {row['error']}")
        else:
            print(f"  {preset}: spend=RM{row.get('spend', 0)}, imps={row.get('impressions', 0)}, "
                  f"clicks={row.get('clicks', 0)}, ctr={row.get('ctr', 0)}%, cpc={row.get('cpc', 0)}")
    print("Snapshot disimpan dalam DB (table spend).")


if __name__ == "__main__":
    main()
