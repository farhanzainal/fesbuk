# -*- coding: utf-8 -*-
"""Cron wrapper — tarik spend dari FB Ads API. SENYAP kalau berjaya
(empty stdout = takde mesej), print + exit 1 kalau gagal (watchdog pattern)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "fesbuk"))

import fb_spend  # noqa: E402

res = fb_spend.pull_and_store()
if not res.get("ok"):
    print(f"[spend] GAGAL: {res.get('error')}")
    sys.exit(1)
