# fesbuk - Global Facebook Page Integration Tool

Generic tool for posting to / reading / testing ANY Facebook Page via the Graph API.

## Flow (how this is meant to be used)

1. **User** provides credentials / page info to the **agent** in conversation
   (page ID, tokens, app ID+secret). The user NEVER edits files.
2. **Agent** runs `python src/fb_setup.py --page-id ... --token ... --app-id ... --app-secret ...`
   — this writes `.env` and stores tokens in `~/.secrets/` automatically.
3. **Agent** verifies with `python src/fb_test.py`.
4. **Agent** posts/reads via `fb_post.py` / `fb_read.py`.
5. If `.env` doesn't exist yet, the agent creates it. If it exists, the agent updates it.

## Structure

```
fesbuk/
├── pyproject.toml     ← installable; entry points (fesbuk-test/post/read/setup)
├── README.md          ← read this first (setup, usage, FAQ)
├── AGENTS.md          ← agent operating guide (read by bots)
├── LICENSE            ← MIT
├── .env.example       ← template — copy to .env and fill in (git-safe)
├── .env               ← YOUR page config — agent-written, NEVER commit
├── .gitignore         ← excludes .env, msg*.txt, secrets, __pycache__
├── src/fesbuk/        ← python package
│   ├── __init__.py
│   ├── config.py      ← auto-detect OS/user; loads .env + token paths
│   ├── fb_setup.py    ← agent-side setup (writes .env + secrets)
│   ├── fb_test.py     ← test token + page status
│   ├── fb_post.py     ← post message (text or photo via --image <url>)
│   └── fb_read.py     ← read recent posts + engagement
├── scripts/           ← helper scripts
├── database/          ← ALL PRIVATE DATA (gitignored): fesbuk.db (content/records), images/, docs/
└── tests/             ← pytest
```

All post content, records, images and docs live in `database/` (never committed).
Post via DB: `python src/fesbuk/fb_post.py --db msg_p2.txt` reads the text from the DB.

## Dashboard

Local web dashboard — connected pages (live/offline) + pending/posted posts:

```
http://127.0.0.1:8769/dashboard
```

Start it:
```
./.venv/Scripts/python.exe src/fesbuk/dashboard.py    # project venv ONLY (flask needed)
```

> **PAGE FILTER (user-mandated):** `connected_pages()` in `dashboard.py` filters to
> `config.PAGE_ID` (from `.env`) ONLY. Every screen — dashboard, Post dropdown,
> /pages — shows ONLY the configured page. Other pages on the user token
> (idahamway, Panthera Malaysia, Family Frozen Food, etc.) are dropped completely;
> the `hidden_pages` DB setting is now legacy/unused. Do NOT remove this filter.

- Header: all pages visible to the user token, each marked **LIVE / OFFLINE**
- Pending posts: from `database/fesbuk.db` (auto-seeded from `knowledge/msgs/`)
- Posted posts: marked automatically by `fb_post.py` on success
- API: `http://127.0.0.1:8769/api/posts` (JSON)
- DB + post images live in `database/` (private, never committed)

## Ads Manager (spend tracking)

Sidebar page `http://127.0.0.1:8769/ads` — tracks **total ad spend** from the FB
Ads API (boosted posts). Shows the activation steps when no ads token is connected,
and the stats (bulan ini / 7 hari / impressions / clicks / CTR) once activated.

```
GET /me/adaccounts            → act_XXX
GET /act_XXX/insights?fields=spend,impressions,clicks,ctr&date_preset=last_7d
```

### Enable `ads_read` (one-time, verified steps)

The `ads_read` permission is NOT available in Graph API Explorer until the app has
the **Marketing API** use case. Do this:

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps** → pilih app.
2. **Use Case** → **Add** → pilih **Marketing API**.
3. Kat situ `ads_read` & `ads_management` tersedia.
4. Balik ke **Graph API Explorer** → pilih app → mode **User Token** →
   **Add a permission** → taip `ads_read` → pilih → **Generate Access Token** → benarkan.
5. Salin token (`EAAT...`) → tampal kat `/ads` → **Aktifkan**.

> No business portfolio / Business Verification needed for this path. Do NOT use
> business.facebook.com settings — wrong path.

### How activation works

`fb_spend.activate_token()` (route `/api/ads/activate`) exchanges the pasted token
to a **long-lived token (~60 hari)** with the app's ID+Secret, verifies
`GET /me/adaccounts`, then pulls snapshots into DB table `spend`
(last_7d + this_month). The token is stored in a **dedicated file**:

| Item | Location |
|---|---|
| Ads token (long-lived, dedicated) | `~/.secrets/fb_ads_token.txt` |
| Page token (never expires) | `~/.secrets/fb_page_token.txt` |
| Long-lived user token (page conn) | `~/.secrets/fb_user_token_ll.txt` |
| Short user token (refresh) | `~/.secrets/fb_user_token.txt` |
| App ID + Secret | `~/.secrets/fb_app.txt` |

> **Why separate files:** the ads token (`fb_ads_token.txt`) is independent of the
> page-connection user token (`fb_user_token_ll.txt`). Removing ads tracking
> (delete `fb_ads_token.txt` + clear `spend` table) never breaks the dashboard.

### Cron

`scripts/pull_spend.py` — daily 22:00 MY, watchdog pattern (silent on success,
exit 1 + message on failure).

## Setup (one time)

1. **Create a Meta app** with use case "Manage Everything on your page".
   At creation, select **"I don't want to connect a business portfolio yet"**
   (this avoids the Business Verification requirement for Live mode).
2. App Settings → Basic → set **Privacy Policy URL** → Save (required before Go Live).
3. Switch the app to **Live** mode (required for long-lived tokens).
4. **Graph API Explorer** → select the app → Add permissions:
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`
   → Generate Access Token (login as the page admin) → copy token.
5. Exchange to a long-lived token (60 days):
   ```
   GET /v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<USER_TOKEN>
   ```
6. Get the **never-expiring page token**:
   ```
   GET /me/accounts?access_token=<LONG_LIVED_USER_TOKEN>
   ```
   Copy the page token for YOUR page into `~/.secrets/fb_page_token.txt`.
7. Set your page ID: `copy .env.example .env` then edit `.env` (see below).

## .env (page config)

```
PAGE_ID=your_page_id_here
PAGE_NAME=optional_page_name
```

## Usage

Set up the project venv ONCE (self-contained — do NOT depend on other projects'
venvs like medsos; fesbuk is a standalone tool):

```bash
cd fesbuk
python -m venv .venv            # any Python 3.11+; on this machine: /c/Users/clawb/AppData/Local/Python/bin/python
./.venv/Scripts/python.exe -m pip install flask   # Windows; Linux: .venv/bin/python -m pip install flask
```

Run from the fesbuk folder with the project venv python (`./.venv/Scripts/python.exe` on
Windows, `./.venv/bin/python` on Linux — or use `fesbuk-test`/`fesbuk-post`/etc. after
`pip install -e .`):

```bash
python src/fb_test.py            # verify token + page
python src/fb_post.py msg.txt    # post message from UTF-8 file
python src/fb_post.py --text "..."  # post message inline
python src/fb_read.py 10         # last 10 posts + reactions/comments/shares
```

> **IMPORTANT (user-mandated):** fesbuk must never borrow another project's venv
> (e.g. the medsos venv). Use `.venv` inside the fesbuk repo only.

## Credentials (never commit)

Secrets live in `~/.secrets/` (per-user home dir — config.py uses `Path.home()`,
overridable via `FB_SECRETS_DIR` env var).

| Item | Location |
|---|---|
| Page token (never expires) | `~/.secrets/fb_page_token.txt` |
| Long-lived user token (60d) | `~/.secrets/fb_user_token_ll.txt` |
| Short user token (refresh) | `~/.secrets/fb_user_token.txt` |
| Ads token (long-lived, dedicated) | `~/.secrets/fb_ads_token.txt` |
| App ID + Secret | `~/.secrets/fb_app.txt` |

## Cron / automation

- Use `.py` wrappers, NEVER `.sh` on Windows — bash mangles backslash paths
  (`C:\Users\...` → `C:Users...` → "No such file or directory", exit 127).
- Wrapper pattern (auto-detect OS — no manual path config needed):
  ```python
  import os, subprocess, sys
  import config  # fesbuk/src/config.py

  # venv python resolved automatically (Scripts/python.exe vs bin/python)
  venv_python = config.venv_python(r"C:\path\to\venv")  # or any venv root
  r = subprocess.run([venv_python, os.path.join(config.ROOT, "src", "fb_post.py"), msg_file],
                     capture_output=True, text=True, timeout=240)
  print(r.stdout or r.stderr)
  ```

## FAQ (verified steps)

**Q: Why is "Go Live" disabled / why does the app demand Business Verification?**
A: Apps connected to a Business Portfolio require Business Verification before going Live.
FIX: create the app WITHOUT a business portfolio — choose
**"I don't want to connect a business portfolio yet"** at creation. Live then works with no verification.

**Q: "Go Live" still disabled?**
A: App Settings → Basic → set **Privacy Policy URL** → Save. The button enables after that.

**Q: `fb_exchange_token` fails with "Error validating client secret" (code 1)?**
A: The app is still in Development mode (switch to Live first), or the client_id/client_secret
don't match the app that ISSUED the user token. Use that app's own ID+Secret (Settings → Basic).

**Q: "Cannot parse access token" / "Invalid OAuth access token"?**
A: That token belongs to another platform (e.g. a Threads token works only on graph.threads.net).
Facebook Graph user/page tokens start with `EAAT...`.

**Q: Error 101 "Cannot get application info"?**
A: Wrong app secret, or the app is in a broken/old dev state. Use the current app's own ID+Secret.

**Q: 500-character limit?**
A: That is a Threads API limit. Facebook Page posts have no 500-char limit.

**Q: Can the bot post without user approval?**
A: NO — always show the post content and get user approval BEFORE posting.
