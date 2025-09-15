# ui/scripts/update_from_psn_titles_v21.py
# PSNAWP 2.1.x compatible
import os
import csv
import argparse
from pathlib import Path
from typing import Optional, Iterable

from psnawp_api import PSNAWP
from psnawp_api.models.trophies import PlatformType


OUT_CSV = Path("ui/data/psn_titles.csv")


def choose_primary_platform(p_set: "frozenset[PlatformType]") -> Optional[PlatformType]:
    """Prefer PS5 > PS4 > PS3 > PSVITA; fall back to any if unknown."""
    if not p_set:
        return None
    for pref in (PlatformType.PS5, PlatformType.PS4, PlatformType.PS3, PlatformType.PS_VITA):
        if pref in p_set:
            return pref
    return next(iter(p_set))


def platform_label(p: Optional[PlatformType]) -> str:
    return p.value if isinstance(p, PlatformType) else ""


def _sum_trophyset_like(obj) -> int:
    """Sum bronze/silver/gold/platinum from TrophySet-like objects or dicts."""
    if obj is None:
        return 0
    # TrophySet object with attributes
    if any(hasattr(obj, k) for k in ("bronze", "silver", "gold", "platinum")):
        total = 0
        for k in ("bronze", "silver", "gold", "platinum"):
            v = getattr(obj, k, 0)
            if isinstance(v, int):
                total += v
        return total
    # dict-like
    if isinstance(obj, dict):
        acc = 0
        for k in ("bronze", "silver", "gold", "platinum"):
            v = obj.get(k)
            if isinstance(v, int):
                acc += v
        if acc:
            return acc
        # fallback: sum every int in dict
        return sum(v for v in obj.values() if isinstance(v, int))
    # last resort: __dict__
    if hasattr(obj, "__dict__"):
        d = {k: v for k, v in obj.__dict__.items() if isinstance(v, int)}
        if d:
            return sum(d.values())
    return 0


def try_groups_total(user, npcomm: str, platform: PlatformType, verbose=False) -> int:
    """
    Prefer getting defined (total) trophies from the groups summary and sum ALL groups (base + DLC).
    Works for both PS4/PS5 quickly and accurately.
    """
    try:
        summary = user.trophy_groups_summary(np_communication_id=npcomm, platform=platform)

        # 1) Many titles expose an overall TrophySet at summary.defined_trophies
        if hasattr(summary, "defined_trophies"):
            overall = getattr(summary, "defined_trophies")
            total = _sum_trophyset_like(overall)
            if total:
                if verbose:
                    print(f"    · trophy_groups_summary[{platform.value}] overall defined -> {total}")
                return total

        # 2) Or they expose a list of group summaries we can sum
        if hasattr(summary, "trophy_groups"):
            groups = getattr(summary, "trophy_groups") or []
            grand = 0
            for g in groups:
                # Each g.defined_trophies is a TrophySet
                if hasattr(g, "defined_trophies"):
                    grand += _sum_trophyset_like(getattr(g, "defined_trophies"))
            if grand:
                if verbose:
                    gids = [getattr(g, "trophy_group_id", "?") for g in groups]
                    print(f"    · trophy_groups_summary[{platform.value}] groups {gids} sum -> {grand}")
                return grand

        # 3) Some summary objects might be dict-shaped
        if isinstance(summary, dict):
            # top-level TrophySet-like
            if "defined_trophies" in summary:
                total = _sum_trophyset_like(summary["defined_trophies"])
                if total:
                    if verbose:
                        print(f"    · trophy_groups_summary[{platform.value}] dict overall -> {total}")
                    return total
            # or a list of groups
            for key in ("trophy_groups", "groups"):
                if key in summary and isinstance(summary[key], list):
                    grand = 0
                    for g in summary[key]:
                        if isinstance(g, dict) and "defined_trophies" in g:
                            grand += _sum_trophyset_like(g["defined_trophies"])
                    if grand:
                        if verbose:
                            print(f"    · trophy_groups_summary[{platform.value}] dict per-group sum -> {grand}")
                        return grand

    except TypeError:
        # signature mismatch; fall back
        pass
    except Exception as e:
        if verbose:
            print(f"    · trophy_groups_summary[{platform.value}] -> ERROR {e}")
    return 0


def _enumerate_group_ids(user, npcomm: str, platform: PlatformType) -> Iterable[str]:
    """Yield group ids ('default', '001', …) if available from summary."""
    try:
        s = user.trophy_groups_summary(np_communication_id=npcomm, platform=platform)
        groups = getattr(s, "trophy_groups", None)
        if isinstance(groups, list) and groups:
            for g in groups:
                gid = getattr(g, "trophy_group_id", None)
                if gid:
                    yield gid
    except Exception:
        return  # silently ignore


def try_list_total(user, npcomm: str, platform: PlatformType, verbose=False) -> int:
    """
    Fallback: enumerate trophies and count length for TOTAL.
    We try per-group enumeration to include DLC, then generic calls if needed.
    """
    # 1) Try per-group enumeration (default + DLC) if we can discover group ids
    group_ids = list(_enumerate_group_ids(user, npcomm, platform))
    if group_ids:
        total = 0
        for gid in group_ids:
            try:
                items = list(user.trophies(np_communication_id=npcomm, platform=platform, trophy_group_id=gid))
                subtotal = len(items)
                total += subtotal
                if verbose:
                    print(f"    · trophies[{platform.value}][group={gid}] -> {subtotal}")
            except Exception as e:
                if verbose:
                    print(f"    · trophies[{platform.value}][group={gid}] -> ERROR {e}")
        if total:
            if verbose:
                print(f"    · trophies[{platform.value}] per-group total -> {total}")
            return total

    # 2) Generic calls (may only return base list)
    calls = [
        lambda: user.trophies(np_communication_id=npcomm, platform=platform, trophy_group_id="all"),
        lambda: user.trophies(npcomm, platform, "all"),
        lambda: user.trophies(np_communication_id=npcomm, platform=platform),
        lambda: user.trophies(npcomm, platform),
    ]
    last_err = None
    for i, fn in enumerate(calls, 1):
        try:
            items = list(fn())
            total = len(items)
            if verbose:
                print(f"    · trophies[{platform.value}] -> list length {total} (call#{i})")
            if total:
                return total
        except TypeError as te:
            last_err = te
            continue
        except Exception as e:
            last_err = e
            continue
    if verbose and last_err:
        print(f"    · trophies[{platform.value}] -> ERROR {last_err}")
    return 0


def extract_earned_from_title_obj(title_obj) -> int:
    """
    Pull user's earned count from the trophy title object across PSNAWP 2.1.x.
    Handles TrophySet, dict, tuple-like and int.
    """
    candidates = [
        getattr(title_obj, "earned_trophies", None),
        getattr(title_obj, "earned", None),
        getattr(title_obj, "user_earned_trophies", None),
        getattr(title_obj, "earned_trophies_count", None),
    ]

    for val in candidates:
        if val is None:
            continue

        if any(hasattr(val, k) for k in ("bronze", "silver", "gold", "platinum")):
            total = 0
            for k in ("bronze", "silver", "gold", "platinum"):
                v = getattr(val, k, 0)
                if isinstance(v, int):
                    total += v
            if total:
                return total

        if isinstance(val, dict):
            s = sum(v for v in val.values() if isinstance(v, int))
            if s:
                return s

        if isinstance(val, (list, tuple)):
            s = sum(x for x in val if isinstance(x, int))
            if s:
                return s

        if isinstance(val, int):
            return val

        if hasattr(val, "__dict__"):
            d = {k: v for k, v in val.__dict__.items() if isinstance(v, int)}
            if d:
                s = sum(d.values())
                if s:
                    return s

    return 0


def main():
    parser = argparse.ArgumentParser(description="Update PSN titles (totals include DLC via groups).")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of titles processed")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    NPSSO = os.environ.get("PSN_NPSSO")
    ONLINE_ID = os.environ.get("PSN_ONLINE_ID")
    if not NPSSO or not ONLINE_ID:
        raise SystemExit("Missing PSN_NPSSO or PSN_ONLINE_ID environment variables.")

    psn = PSNAWP(NPSSO)
    user = psn.user(online_id=ONLINE_ID)

    titles = list(user.trophy_titles())
    print(f"Fetched {len(titles)} titles from PSN…")

    rows = []
    count = 0

    for t in titles:
        if args.limit and count >= args.limit:
            break

        title_name = getattr(t, "title_name", None) or getattr(t, "name", "")
        npcomm = getattr(t, "np_communication_id", None) or getattr(t, "np_communication_id_", "")
        pset = getattr(t, "title_platform", None) or getattr(t, "platform", frozenset())
        percent = getattr(t, "progress", None)
        if percent is None:
            percent = getattr(t, "progress_percent", None)
        try:
            percent = int(percent) if percent is not None else 0
        except Exception:
            percent = 0

        primary = choose_primary_platform(pset)
        label = platform_label(primary) if primary else ""

        if args.verbose:
            plat_text = "/".join(sorted([p.value for p in pset])) if pset else ""
            print(f"[{count+1}] {title_name} | {npcomm} | {plat_text or label} | {percent}%")

        # TOTAL trophies (prefer groups summary sum; fallback to per-group enumeration)
        total_defined = 0
        if primary:
            total_defined = try_groups_total(user, npcomm, primary, verbose=args.verbose)
            if total_defined == 0:
                total_defined = try_list_total(user, npcomm, primary, verbose=args.verbose)

        # EARNED trophies (from the title object)
        earned = extract_earned_from_title_obj(t)
        if args.verbose:
            print(f"    · earned_from_title_obj -> {earned}")

        rows.append((title_name, npcomm, label, earned, total_defined, percent))
        count += 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Title", "NPCommID", "Platform", "TrophiesUnlocked", "TrophiesTotal", "Percent"])
        for r in rows:
            w.writerow(r)

    if rows:
        print("Sample rows:")
        for r in rows[:5]:
            print(f"   {r}")
    print(f"✅ Wrote {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
