from psnawp_api import PSNAWP
from pathlib import Path
import os, sys

NPSSO = os.getenv("PSN_NPSSO")
ONLINE_ID = os.getenv("PSN_ONLINE_ID")
if not NPSSO or not ONLINE_ID:
    print("Missing PSN_NPSSO or PSN_ONLINE_ID env vars.")
    sys.exit(1)

psn = PSNAWP(NPSSO)
user = psn.user(online_id=ONLINE_ID)

# 1) Quick overall counts (should NOT be zero if privacy is correct)
try:
    summary = user.trophy_summary()
    print("Overall (PS4):", summary.ps4.earned, "/", summary.ps4.defined)
    print("Overall (PS5):", summary.ps5.earned, "/", summary.ps5.defined)
except Exception as e:
    print("Could not read overall summary:", e)

# 2) Per-title check using your library’s built-in title list
titles = list(user.trophy_titles(limit=20))
print(f"Fetched {len(titles)} titles from account")

# Pick a very common one for testing:
PREFERRED = {"Marvel's Spider-Man", "God of War", "RESIDENT EVIL 2", "ELDEN RING™"}
target = None
for t in titles:
    if t.title_name in PREFERRED:
        target = t
        break
if target is None and titles:
    target = titles[0]

if not target:
    print("No titles returned at all.")
    sys.exit(0)

print(f"Testing title: {target.title_name} | NPCommID={target.np_communication_id} | Platforms={target.title_platform}")

# 3) Try detailed trophies for the first (or only) platform
platform = next(iter(target.title_platform))  # e.g. PlatformType.PS4 or PS5
try:
    # Newer psnawp exposes per-title trophy list via the title object:
    groups = target.trophy_groups(platform=platform)
    defined = earned = 0
    for g in groups:
        defined += g.defined_trophies.total
        earned  += g.earned_trophies.total
    print(f"Detailed: earned {earned} / {defined} on {platform}")
except AttributeError:
    print("Your psnawp-api version may be old; try upgrading (pip install -U psnawp-api)")
except Exception as e:
    print("Detailed call failed:", e)
