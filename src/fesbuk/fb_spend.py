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


def _graph(path, token, params=None, method="GET", data=None):
    q = {"access_token": token}
    if params:
        q.update(params)
    url = f"{config.GRAPH}/{path}?" + urllib.parse.urlencode(q)
    body = urllib.parse.urlencode(data or {}).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
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


# ---------- per-post breakdown (boosted posts) ----------

_ACTION_TYPES = ("post_likes", "post_comments", "post_shares", "post_reactions")


def _actions_to_dict(actions_list):
    out = {t: 0 for t in _ACTION_TYPES}
    for a in actions_list or []:
        t = a.get("action_type")
        if t in out:
            try:
                out[t] = int(float(a.get("value", 0)))
            except (TypeError, ValueError):
                pass
    return out


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def fetch_ads_list(act_id, token):
    """GET /act_XXX/ads -> [{id, name, status, effective_status, created_time,
    adset{id,name,status,effective_status,start_time,end_time},
    campaign{id,name,status,effective_status},
    creative{object_id,effective_object_story_id}}]."""
    data = _graph(
        f"{act_id}/ads",
        token,
        {
            "fields": "id,name,status,effective_status,created_time,"
                      "adset{id,name,status,effective_status,start_time,end_time},"
                      "campaign{id,name,status,effective_status},"
                      "creative{object_id,effective_object_story_id}",
            "limit": 100,
        },
    )
    return data.get("data", [])


def fetch_ads_daily_breakdown(act_id, token, date_preset="last_7d"):
    """GET /act_XXX/insights level=ad time_increment=1 -> rows per ad per day."""
    data = _graph(
        f"{act_id}/insights",
        token,
        {
            "fields": "ad_id,ad_name,spend,impressions,reach,clicks,ctr,actions,date_start",
            "date_preset": date_preset,
            "time_increment": 1,
            "level": "ad",
            "limit": 500,
        },
    )
    return data.get("data", [])


def build_ads_view(act_id, token, date_preset="last_7d"):
    """Senarai boosted posts + breakdown harian per post.

    Iterate dari SEMUA ads (termasuk yang baru create & belum ada insights —
    status review tetap nampak). Ad tanpa breakdown: days kosong, totals 0.

    Returns: {"ok": True, "ads": [{id, name, status, created_time,
              days_active, first_day, last_day, post_url, days:[...], totals:{...}}]}
    """
    ads = fetch_ads_list(act_id, token)
    rows = fetch_ads_daily_breakdown(act_id, token, date_preset)
    info = {a["id"]: a for a in ads}
    by_ad = {}
    for r in rows:
        by_ad.setdefault(r.get("ad_id"), []).append(r)

    result = []
    for aid in info:  # semua ads, bukan hanya yang ada insights
        rrows = by_ad.get(aid, [])
        inf = info.get(aid, {})
        # Filter: cuma ads yang promote post page TinjauLokasi
        creative = inf.get("creative") or {}
        post_id = creative.get("object_id") or creative.get("effective_object_story_id") or ""
        if not str(post_id).startswith(config.PAGE_ID + "_"):
            continue
        days = []
        for r in sorted(rrows, key=lambda x: x.get("date_start", "")):
            eng = _actions_to_dict(r.get("actions"))
            days.append({
                "date": r.get("date_start", ""),
                "spend": _f(r.get("spend")),
                "impressions": _i(r.get("impressions")),
                "reach": _i(r.get("reach")),
                "clicks": _i(r.get("clicks")),
                "ctr": _f(r.get("ctr")),
                "likes": eng["post_likes"],
                "comments": eng["post_comments"],
                "shares": eng["post_shares"],
                "reactions": eng["post_reactions"],
            })
        totals = {k: sum(d[k] for d in days)
                  for k in ("spend", "impressions", "reach", "clicks",
                            "likes", "comments", "shares", "reactions")}
        totals["ctr"] = round(totals["clicks"] / totals["impressions"] * 100, 2) \
            if totals["impressions"] else 0.0
        dates = [d["date"] for d in days if d.get("date")]
        creative = inf.get("creative") or {}
        post_id = creative.get("object_id") or creative.get("effective_object_story_id") or ""
        adset = inf.get("adset") or {}
        camp = inf.get("campaign") or {}
        result.append({
            "id": aid,
            "name": inf.get("name") or (rrows[0].get("ad_name") if rrows else "") or aid,
            "status": inf.get("effective_status") or inf.get("status") or "",
            "status_raw": inf.get("status") or "",
            "created_time": inf.get("created_time", ""),
            "start_time": adset.get("start_time", ""),
            "end_time": adset.get("end_time", ""),
            "adset_id": adset.get("id", ""),
            "adset_name": adset.get("name", ""),
            "adset_status": adset.get("effective_status") or adset.get("status") or "",
            "campaign_id": camp.get("id", ""),
            "campaign_name": camp.get("name", ""),
            "campaign_status": camp.get("effective_status") or camp.get("status") or "",
            "days_active": len(dates),
            "first_day": min(dates) if dates else "",
            "last_day": max(dates) if dates else "",
            "post_url": f"https://www.facebook.com/{post_id}" if post_id else "",
            "days": days,
            "totals": totals,
        })
    result.sort(key=lambda a: a["created_time"], reverse=True)
    return {"ok": True, "ads": result, "date_preset": date_preset}


def pull_ads(token=None, date_preset="last_7d"):
    """Tarik senarai boosted posts + breakdown, simpan JSON dalam DB settings
    (key `ads_data` + `ads_data_at`). Returns {"ok", count, ads}."""
    if token is None:
        token = user_token()
    if not token:
        return {"ok": False,
                "error": "Tiada user token. Tampal token di halaman Ads Manager dulu."}
    try:
        accts = get_ad_accounts(token)
    except Exception as e:
        err = str(e)
        if "permission" in err.lower():
            return {"ok": False,
                    "error": "Token ni takde permission ads_read. Regenerate token dalam "
                             "Graph API Explorer (tambah permission ads_read), lepas tu "
                             "tampal token baru di halaman Ads Manager."}
        return {"ok": False, "error": err}
    if not accts:
        return {"ok": False,
                "error": "Takde ad account dijumpai untuk token ni. Pastikan user ada "
                         "kaitan dgn mana-mana ad account (Business Manager / Ads Manager)."}
    try:
        view = build_ads_view(accts[0]["id"], token, date_preset)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    db.set_setting("ads_data", json.dumps(view.get("ads", [])))
    db.set_setting("ads_data_at", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "count": len(view.get("ads", [])), "ads": view.get("ads", [])}


def load_ads_view():
    """Ads snapshot dari DB (kalau ada). Returns {"ads": [...], "fetched_at": ...}."""
    raw = db.get_setting("ads_data")
    at = db.get_setting("ads_data_at")
    try:
        ads = json.loads(raw) if raw else []
    except Exception:
        ads = []
    return {"ads": ads, "fetched_at": at or ""}


# ---------- create campaign (boost a post) ----------

# Target kawasan (user-mandated): KL, Selangor, JB, Penang
# Format FB: regions/cities sebagai list of {key: "..."}
GEO_TARGETS = {
    "KL & Selangor": {"regions": [{"key": "2549"}, {"key": "2547"}]},
    "Johor Bahru": {"cities": [{"key": "1562288"}]},
    "Penang": {"regions": [{"key": "2545"}]},
    "Semua (KL/Sel/JB/Penang)": {"regions": [{"key": "2549"}, {"key": "2547"}, {"key": "2545"}],
                                  "cities": [{"key": "1562288"}]},
}
# Pilihan interest (id -> label)
INTEREST_OPTIONS = {
    "Real Estate": 6002979192120,
    "Property (industry)": 6003578086487,
    "First-time buyer (property)": 6003174415534,
    "Property investing": 6003446239080,
    "Mortgage loans": 6003141785766,
    "Apartment block (property)": 6003435139283,
    "Tiada (broad)": None,
}
AGE_OPTIONS = {
    "18-24": (18, 24),
    "25-34": (25, 34),
    "25-45": (25, 45),
    "35-44": (35, 44),
    "45-54": (45, 54),
    "55+": (55, 65),
    "Semua (18-65)": (18, 65),
}
DEFAULT_INTEREST = "Real Estate"
DEFAULT_AGE = "25-45"

# Pilihan objective + optimization_goal yang sepadan
# VERIFIED (Aug 2026): FB tolak ENGAGEMENT/LEADS optimization bila promoted_object
# page_id (error "Performance goal isn't available" 2490408). TRAFFIC + AWARENESS
# berfungsi penuh (campaign -> adset -> creative -> ad, semua step lulus).
OBJECTIVE_OPTIONS = {
    "Traffic (klik link)": {"objective": "OUTCOME_TRAFFIC", "optimization": "LINK_CLICKS"},
    "Reach (jangkauan)": {"objective": "OUTCOME_AWARENESS", "optimization": "REACH"},
}
DEFAULT_OBJECTIVE = "Traffic (klik link)"


def _post_label(post_id: str, token: str, max_len: int = 42) -> str:
    """Nama cantik untuk campaign/adset/ad: 'Boost: <message post>'.

    Tarik message post dari FB — guna user token, fallback ke page token
    (page post message perlu page token / pages_read_engagement). Fallback
    akhir: 'Boost <post_id>'.
    """
    candidates = [token]
    try:
        pt = db.get_token("fb_page_token")
        if pt and pt != token:
            candidates.append(pt)
    except Exception:
        pass
    for tok in candidates:
        try:
            d = _graph(f"{post_id}", tok, params={"fields": "message"}, method="GET")
            msg = (d.get("message") or d.get("name") or "").strip().replace("\n", " ")
            if msg:
                return f"Boost: {msg[:max_len]}{'…' if len(msg) > max_len else ''}"
        except Exception:
            continue
    return f"Boost {post_id}"


def create_boost(post_id: str, daily_budget_rm: float, days: int,
                 area: str = "Semua (KL/Sel/JB/Penang)",
                 age_range: str = DEFAULT_AGE,
                 interest: str = DEFAULT_INTEREST,
                 objective: str = DEFAULT_OBJECTIVE,
                 status: str = "ACTIVE",
                 token=None):
    """Create a boosted-post campaign: campaign -> adset -> creative -> ad.

    status="PAUSED" untuk dry-run (test tanpa keluar duit).
    Returns {"ok": True, "campaign_id", "adset_id", "ad_id", "post_id"}.
    """
    if token is None:
        token = user_token()
    if not token:
        return {"ok": False,
                "error": "Tiada user token. Tampal token di halaman Ads Manager dulu."}
    try:
        accts = get_ad_accounts(token)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not accts:
        return {"ok": False,
                "error": "Takde ad account dijumpai untuk token ni. Sambung user dalam "
                         "Ads Manager / Business Manager dulu."}
    act_id = accts[0]["id"]

    geo = GEO_TARGETS.get(area, GEO_TARGETS["Semua (KL/Sel/JB/Penang)"])
    age_min, age_max = AGE_OPTIONS.get(age_range, AGE_OPTIONS[DEFAULT_AGE])
    # interest: nama preset ATAU id FB terus (angka) — flexible
    interest_raw = (interest or "").strip()
    interest_id = None
    if interest_raw and interest_raw != "Tiada (broad)":
        if interest_raw.isdigit():
            interest_id = interest_raw
        else:
            interest_id = INTEREST_OPTIONS.get(interest_raw)
            if interest_id is None:
                # bukan preset — cuba cari id via search (fallback)
                return {"ok": False,
                        "error": f"Interest '{interest_raw}' tak dikenali. Pilih dari senarai "
                                 "atau taip dan cari interest dulu."}
    targeting = {
        "geo_locations": geo,
        "age_min": age_min,
        "age_max": age_max,
        "targeting_automation": {"advantage_audience": 0},
    }
    if interest_id:
        targeting["interests"] = [{"id": str(interest_id)}]
    budget = max(int(round(daily_budget_rm * 100)), 100)  # FB guna sen (min RM1)
    name_base = _post_label(post_id, token)  # "Boost: <message>" — bukan id mentah
    obj = OBJECTIVE_OPTIONS.get(objective, OBJECTIVE_OPTIONS[DEFAULT_OBJECTIVE])

    try:
        # 1) Campaign
        camp = _graph(act_id + "/campaigns", token, params={
            "name": name_base,
            "objective": obj["objective"],
            "status": status,
            "special_ad_categories": "[]",
            "is_adset_budget_sharing_enabled": "false",
        }, method="POST")
        camp_id = camp.get("id")
        if not camp_id:
            return {"ok": False, "error": f"Campaign gagal: {camp}"}
        # 2) AdSet — promoted_object page_id (boost page post; perlu pages_manage_ads)
        adset = _graph(act_id + "/adsets", token, params={
            "name": name_base + " set",
            "campaign_id": camp_id,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": obj["optimization"],
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "daily_budget": str(budget),
            "targeting": json.dumps(targeting),
            "status": status,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "promoted_object": json.dumps({"page_id": config.PAGE_ID}),
        }, method="POST")
        adset_id = adset.get("id")
        if not adset_id:
            return {"ok": False, "error": f"AdSet gagal: {adset}", "campaign_id": camp_id}
        # 3) Creative (boost page post)
        creative = _graph(act_id + "/adcreatives", token, params={
            "name": name_base + " creative",
            "object_story_id": post_id,
        }, method="POST")
        creative_id = creative.get("id")
        if not creative_id:
            return {"ok": False, "error": f"Creative gagal: {creative}",
                    "campaign_id": camp_id, "adset_id": adset_id}
        # 4) Ad
        ad = _graph(act_id + "/ads", token, params={
            "name": name_base + " ad",
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": status,
        }, method="POST")
        ad_id = ad.get("id")
        if not ad_id:
            return {"ok": False, "error": f"Ad gagal: {ad}",
                    "campaign_id": camp_id, "adset_id": adset_id}
        # Simpan rekod campaign dalam DB
        camps = json.loads(db.get_setting("ad_campaigns", "[]") or "[]")
        camps.append({
            "campaign_id": camp_id, "adset_id": adset_id, "ad_id": ad_id,
            "post_id": post_id, "area": area, "age_range": age_range,
            "interest": interest, "objective": objective,
            "daily_budget_rm": daily_budget_rm, "days": days,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db.set_setting("ad_campaigns", json.dumps(camps))
        return {"ok": True, "campaign_id": camp_id, "adset_id": adset_id,
                "ad_id": ad_id, "post_id": post_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
