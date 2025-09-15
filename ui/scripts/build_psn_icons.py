# ui/scripts/build_psn_icons.py
# Pulls per-title icon URLs and saves to ui/data/psn_icons.csv

import os
import csv
from pathlib import Path
from psnawp_api import PSNAWP

OUT = Path("ui/data/psn_icons.csv")
OUT.parent.mkdir(parents=True, exist_ok=True)

NPSSO = os.getenv("PSN_NPSSO")
ONLINE_ID = os.getenv("PSN_ONLINE_ID")
if not NPSSO or not ONLINE_ID:
    raise SystemExit("❌ Missing PSN_NPSSO or PSN_ONLINE_ID environment variables.")

psn = PSNAWP(NPSSO)
user = psn.user(online_id=ONLINE_ID)

rows = []
seen = set()

for t in user.trophy_titles():
    npcomm = getattr(t, "np_communication_id", None)
    title  = getattr(t, "title_name", "")
    # Try to get an icon URL from the title object first
    icon = getattr(t, "title_icon_url", None)
    # If not present, ask the groups summary (often has trophy_title_icon_url)
    if not icon:
        try:
            plat = next(iter(getattr(t, "title_platform", []) or []), None)
            if plat:
                s = user.trophy_groups_summary(np_communication_id=npcomm, platform=plat)
                icon = getattr(s, "trophy_title_icon_url", None) or getattr(s, "title_icon_url", None)
        except Exception:
            pass

    if npcomm and npcomm not in seen:
        rows.append({"NPCommID": npcomm, "Title": title, "IconURL": icon or ""})
        seen.add(npcomm)

with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["NPCommID", "Title", "IconURL"])
    w.writeheader()
    w.writerows(rows)

print(f"✅ Wrote {len(rows)} icon rows to {OUT}")
