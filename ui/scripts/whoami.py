# ui/scripts/whoami.py
import os
from psnawp_api import PSNAWP

npsso = os.getenv("PSN_NPSSO")
if not npsso:
    raise SystemExit("❌ PSN_NPSSO is not set")

psn = PSNAWP(npsso)
me = psn.me()
print("Online ID:", me.online_id)
print("About:", getattr(me, "about_me", None))
print("Country:", getattr(me, "country", None))
