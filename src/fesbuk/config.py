# -*- coding: utf-8 -*-
"""Shared config — fully automatic, cross-platform.

- Page config: reads fesbuk/.env (PAGE_ID etc.)
- Secrets: ~/.secrets (per-user home), created automatically if missing
- venv python: auto-detected per OS (Scripts/python.exe on Windows, bin/python elsewhere)
No machine-specific values are hardcoded anywhere.
"""
import os
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"

# fesbuk repo root — walk up from this file until .env (or pyproject.toml) found
def _find_root():
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / ".env").exists() or (p / "pyproject.toml").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent

ROOT = _find_root()

# Secrets live in ~/.secrets (per-user). Override with FB_SECRETS_DIR if needed.
HOME = Path.home()
SECRETS_DIR = Path(os.environ.get("FB_SECRETS_DIR", str(HOME / ".secrets")))
SECRETS_DIR.mkdir(parents=True, exist_ok=True)  # auto-create

TOKEN_FILE = SECRETS_DIR / "fb_page_token.txt"
APP_FILE = SECRETS_DIR / "fb_app.txt"
API_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"


def venv_python(venv_root):
    """Return the venv python executable for the current OS."""
    root = Path(venv_root)
    if IS_WINDOWS:
        return str(root / "Scripts" / "python.exe")
    return str(root / "bin" / "python")


def _env_values():
    vals = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
    return vals


PAGE_ID = _env_values().get("PAGE_ID", "")
PAGE_NAME = _env_values().get("PAGE_NAME", "")


def load_token() -> str:
    """Page token — single source of truth: DB settings (fb_page_token).
    Fallback ke fail lama (migrasi) kalau DB kosong."""
    try:
        from fesbuk import db
    except ImportError:
        import db
    tok = db.get_token("fb_page_token")
    if tok:
        return tok
    # Migrasi sekali: fail lama -> DB, lepas tu buang fail
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            db.set_token("fb_page_token", tok)
            try:
                TOKEN_FILE.unlink()
            except OSError:
                pass
        return tok
    return ""


def load_user_token() -> str:
    """User token (long-lived preferred) — DB settings, fallback fail lama."""
    try:
        from fesbuk import db
    except ImportError:
        import db
    for key, fname in (("fb_user_token_ll", "fb_user_token_ll.txt"),
                       ("fb_user_token", "fb_user_token.txt")):
        tok = db.get_token(key)
        if tok:
            return tok
        f = SECRETS_DIR / fname
        if f.exists():
            tok = f.read_text(encoding="utf-8").strip()
            if tok:
                db.set_token(key, tok)
                try:
                    f.unlink()
                except OSError:
                    pass
                return tok
    return ""


def load_ads_token() -> str:
    """Ads token — DB settings (fb_ads_token), fallback fail lama."""
    try:
        from fesbuk import db
    except ImportError:
        import db
    tok = db.get_token("fb_ads_token")
    if tok:
        return tok
    f = SECRETS_DIR / "fb_ads_token.txt"
    if f.exists():
        tok = f.read_text(encoding="utf-8").strip()
        if tok:
            db.set_token("fb_ads_token", tok)
            try:
                f.unlink()
            except OSError:
                pass
        return tok
    return ""


def load_app_token() -> str:
    """app_id|app_secret from fb_app.txt."""
    vals = {}
    for line in APP_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            vals[k] = v
    return f"{vals.get('APP_ID', '')}|{vals.get('APP_SECRET', '')}"
