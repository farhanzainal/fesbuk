# -*- coding: utf-8 -*-
"""Agent-side setup helper. The AGENT runs this with values the USER provided in
conversation — the user never edits files. Writes .env + secrets automatically.

Usage:
  python src/fb_setup.py --page-id <PAGE_ID> --page-name <NAMA_PAGE>
  python src/fb_setup.py --page-id ... --token <page-token> --app-id ... --app-secret ...
  python src/fb_setup.py --token <token>            # update token only
"""
import argparse
try:
    from fesbuk import config, db
except ImportError:
    import config
    import db


def main():
    p = argparse.ArgumentParser(description="Write fesbuk config from user-provided values")
    p.add_argument("--page-id", help="Facebook Page ID")
    p.add_argument("--page-name", help="Optional page name (display)")
    p.add_argument("--token", help="Page access token (never-expires) -> DB settings (fb_page_token)")
    p.add_argument("--app-id", help="Meta app ID")
    p.add_argument("--app-secret", help="Meta app secret")
    args = p.parse_args()

    if not any([args.page_id, args.page_name, args.token, args.app_id, args.app_secret]):
        p.print_help()
        raise SystemExit(1)

    # .env (agent-written; created/updated here, never hand-edited)
    env_path = config.ROOT / ".env"
    vals = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
    if args.page_id:
        vals["PAGE_ID"] = args.page_id
    if args.page_name:
        vals["PAGE_NAME"] = args.page_name
    if vals:
        env_path.write_text("".join(f"{k}={v}\n" for k, v in vals.items()), encoding="utf-8")
        print(f"[ok] .env written -> {env_path}")

    # secrets — DB settings (single source of truth)
    if args.token:
        db.set_token("fb_page_token", args.token.strip())
        print("[ok] page token -> DB settings (fb_page_token)")
    if args.app_id and args.app_secret:
        config.APP_FILE.write_text(f"APP_ID={args.app_id}\nAPP_SECRET={args.app_secret}\n",
                                   encoding="utf-8")
        print(f"[ok] app creds -> {config.APP_FILE}")

    print("Setup done. Verify with: python src/fb_test.py")


if __name__ == "__main__":
    main()
