# fesbuk — Agent Operating Guide (AGENTS.md)

This file is for AI agents (including Hermes) assisting the operator with the
fesbuk Facebook integration. Read it before touching this repo.

## What this is

Global tool to post to / read / test ANY Facebook Page via the Graph API.
No page is hardcoded; config lives in `.env` (written by the AGENT, never hand-edited).

## Hard rules (user-mandated)

1. **Never commit secrets/data** — `.env`, `database/` (DB, images, docs), `~/.secrets/*` are gitignored.
   Tokens live in `~/.secrets/` (per-user home; `FB_SECRETS_DIR` override).
2. **Never post without user approval** — show the full post text first, get a GO.
3. **No em-dash "—" in posts** — use "..." instead.
4. **No price in posts** UNLESS the user explicitly says so for that post.
5. **Local tone** — "kat" not "di", "kau/korang", short sentences, storytelling
   (plot + humor + emotion), not corporate/translated BM.
6. **Focus on AREA/neighbourhood** (flood history, traffic, schools, factories),
   not the house itself. Audience = buyers AND renters.
7. **Images**: real photos (Wikimedia Commons, check license) for data posts;
   AI images only when the user asks. Always show the image before posting.
8. **Owner anonymity** — the operator stays unknown; ads/boosts run under the
   Page name, never the personal account.

## Flow

1. User provides credentials/page info in conversation (page ID, tokens, app ID+secret).
2. Agent runs `fesbuk-setup --page-id ... --token ... --app-id ... --app-secret ...`
   (writes `.env` + `~/.secrets/` automatically).
3. Agent verifies with `fesbuk-test`.
4. Agent posts/reads via `fesbuk-post` / `fesbuk-read`.
5. If `.env` is missing the agent creates it; if present the agent updates it.

## Layout

```
fesbuk/
├── pyproject.toml        installable; entry points (fesbuk-test/post/read/setup)
├── README.md             setup, usage, FAQ
├── AGENTS.md             this file
├── LICENSE
├── .env.example          template (git-safe)
├── .env                  page config (agent-written, NEVER commit)
├── .gitignore            excludes .env, knowledge/, secrets, __pycache__
├── src/fesbuk/           python package
│   ├── __init__.py
│   ├── config.py         auto-detect OS/user; loads .env + token paths
│   ├── fb_setup.py       agent-side setup (writes .env + secrets)
│   ├── fb_test.py        test token + page status
│   ├── fb_post.py        post message (text or photo via --image <url>)
│   └── fb_read.py        read recent posts + engagement
├── scripts/              helper scripts
├── database/             ALL PRIVATE DATA (gitignored): fesbuk.db (content/records), images/, docs/
└── tests/                pytest tests
```

All post content lives in the DB (`database/fesbuk.db`); post with
`python src/fesbuk/fb_post.py --db msg_p2.txt`. Images + docs in `database/`.
NEVER put live-post details, images or strategy in README/AGENTS (public docs).

## Dashboard

`http://127.0.0.1:8769/dashboard` — run `./.venv/Scripts/python.exe src/fesbuk/dashboard.py`
(or `fesbuk-dashboard`). **VENV RULE (user-mandated):** fesbuk has its OWN venv
(`.venv/` inside the repo, flask installed) — NEVER borrow another project's venv
(e.g. medsos). If `.venv` is missing: `python -m venv .venv && ./.venv/Scripts/python.exe -m pip install flask`.
Shows connected pages + LIVE/OFFLINE status, pending posts (SQLite in `database/`),
and posted history. All live content/post records/images live in `database/` — NEVER
put live-post details or images in README/AGENTS (they are public repo docs).

**PAGE FILTER (user-mandated):** `connected_pages()` filters to `config.PAGE_ID` ONLY —
every screen shows only the configured page; other pages on the token are dropped.
Do NOT remove this filter.

## Commands

Run from the repo root (any Python 3.11+; after `pip install -e .` the entry
points work anywhere):

```
python src/fesbuk/fb_test.py                 # or: fesbuk-test
python src/fesbuk/fb_post.py msg.txt         # text post from file
python src/fesbuk/fb_post.py --text "..."
python src/fesbuk/fb_post.py --image <url> msg.txt   # photo post
python src/fesbuk/fb_read.py 10              # last 10 posts + engagement
python src/fesbuk/fb_setup.py --page-id ...  # write config from user values
```

## Tokens (FAQ summary — see README for full FAQ)

- Facebook Graph tokens start with `EAAT...` (Threads tokens are graph.threads.net only).
- Flow: Explorer token (pages_show_list, pages_manage_posts, pages_read_engagement)
  → `fb_exchange_token` with the app's ID+Secret (app must be LIVE)
  → long-lived user token (60 days) → `/me/accounts` → page token (never expires).
- App created WITHOUT a business portfolio ("I don't want to connect a business
  portfolio yet") avoids business verification; Privacy Policy URL required for Live.
- Cron: use `.py` wrappers, NEVER `.sh` on Windows (bash mangles backslashes).

## Ads / boost tracking

- To read ad spend via Graph API the token needs `ads_read` permission:
  `GET /me/adaccounts` → `act_XXX`, then
  `GET /act_XXX/insights?fields=spend,impressions,clicks,ctr&date_preset=last_7d`.
- Boost strategy (user): boosted ads, not bought likes; target KL/Selangor/JB/Penang,
  age 25-45, interests property/real estate; goal = engagement during brand exposure.
