# ui/scripts/sync_psn.py
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Iterable, Optional, Tuple, Dict

import pandas as pd
from psnawp_api import PSNAWP
from psnawp_api.models.trophies import PlatformType

# Silence Streamlit warnings when running outside Streamlit
for name in ("streamlit", "streamlit.runtime", "streamlit.runtime.scriptrunner"):
    logging.getLogger(name).setLevel(logging.ERROR)

# ---- paths
ROOT       = Path(__file__).resolve().parents[2]
DATA_DIR   = ROOT / "ui" / "data"
TITLES_CSV = DATA_DIR / "psn_titles.csv"
TROPHY_DIR = DATA_DIR / "trophies"
TROPHY_DIR.mkdir(parents=True, exist_ok=True)

# ---- env
NPSSO     = os.getenv("PSN_NPSSO")
ONLINE_ID = os.getenv("PSN_ONLINE_ID")

# ===================== utilities =====================
def log(msg: str, *, enabled: bool = True) -> None:
    if enabled:
        print(msg, flush=True)

def _require_env():
    if not NPSSO or not ONLINE_ID:
        raise SystemExit("❌ Missing PSN_NPSSO or PSN_ONLINE_ID environment variables.")

def _choose_primary_platform(p_set: "frozenset[PlatformType]") -> Optional[PlatformType]:
    for pref in (PlatformType.PS5, PlatformType.PS4, PlatformType.PS3, PlatformType.PS_VITA):
        if p_set and pref in p_set:
            return pref
    return next(iter(p_set)) if p_set else None

def _platform_label(p: Optional[PlatformType]) -> str:
    return p.value if isinstance(p, PlatformType) else ""

def _platform_from_label(label: str) -> Optional[PlatformType]:
    m = {"PS5": PlatformType.PS5, "PS4": PlatformType.PS4, "PS3": PlatformType.PS3, "PSVITA": PlatformType.PS_VITA}
    return m.get((label or "").strip().upper())

def _sum_trophyset_like(obj) -> int:
    if obj is None:
        return 0
    if any(hasattr(obj, k) for k in ("bronze", "silver", "gold", "platinum")):
        return sum(int(getattr(obj, k, 0) or 0) for k in ("bronze", "silver", "gold", "platinum"))
    if isinstance(obj, dict):
        return sum(v for v in obj.values() if isinstance(v, int))
    if hasattr(obj, "__dict__"):
        return sum(v for v in obj.__dict__.values() if isinstance(v, int))
    return 0

def _groups_total(user, npcomm: str, plat: PlatformType, *, verbose: bool = False) -> int:
    t0 = time.perf_counter()
    try:
        s = user.trophy_groups_summary(np_communication_id=npcomm, platform=plat)
        if hasattr(s, "defined_trophies"):
            t = _sum_trophyset_like(getattr(s, "defined_trophies"))
            if t:
                log(f"      · groups_summary[{plat.value}] overall defined = {t}", enabled=verbose)
                return t
        if hasattr(s, "trophy_groups"):
            total = sum(_sum_trophyset_like(getattr(g, "defined_trophies", None)) for g in (s.trophy_groups or []))
            if total:
                return total
        if isinstance(s, dict):
            if "defined_trophies" in s:
                t = _sum_trophyset_like(s["defined_trophies"])
                if t:
                    return t
            for key in ("trophy_groups", "groups"):
                if key in s and isinstance(s[key], list):
                    total = 0
                    for g in s[key]:
                        if isinstance(g, dict) and "defined_trophies" in g:
                            total += _sum_trophyset_like(g["defined_trophies"])
                    if total:
                        return total
    except Exception as e:
        log(f"      · groups_summary error: {e}", enabled=verbose)
    finally:
        log(f"      · groups_summary time: {time.perf_counter() - t0:.2f}s", enabled=verbose)
    return 0

def _group_ids(user, npcomm: str, plat: PlatformType, *, verbose: bool = False) -> Iterable[str]:
    """Legacy helper: returns just group IDs."""
    try:
        s = user.trophy_groups_summary(np_communication_id=npcomm, platform=plat)
        for g in (getattr(s, "trophy_groups", None) or []):
            gid = getattr(g, "trophy_group_id", None)
            if gid:
                yield gid
        # dict fallback
        if isinstance(s, dict):
            for g in s.get("trophy_groups", []):
                gid = g.get("trophy_group_id") or g.get("trophyGroupId")
                if gid:
                    yield gid
    except Exception as e:
        log(f"      · group_ids error: {e}", enabled=verbose)

def _group_name_map(user, npcomm: str, plat: PlatformType, default_title: str, *, verbose: bool = False) -> Dict[str, str]:
    """
    Return {group_id: group_name}. Fallbacks ensure 'default' shows the title.
    """
    name_map: Dict[str, str] = {}
    try:
        s = user.trophy_groups_summary(np_communication_id=npcomm, platform=plat)

        # object-style
        groups = getattr(s, "trophy_groups", None)
        if groups:
            for g in groups:
                gid = getattr(g, "trophy_group_id", None)
                gname = getattr(g, "trophy_group_name", None) or getattr(g, "name", None)
                if gid:
                    if (gid in ("default", "all", "0", "000")) and not gname:
                        gname = default_title or "Base Game"
                    name_map[gid] = gname or gid

        # dict-style
        if not name_map and isinstance(s, dict):
            for g in s.get("trophy_groups", []):
                gid = g.get("trophy_group_id") or g.get("trophyGroupId")
                gname = g.get("trophy_group_name") or g.get("trophyGroupName") or g.get("name")
                if gid:
                    if (gid in ("default", "all", "0", "000")) and not gname:
                        gname = default_title or "Base Game"
                    name_map[gid] = gname or gid
    except Exception as e:
        log(f"      · group_name_map error: {e}", enabled=verbose)

    return name_map

def _group_name_map_with_timeout(user, npcomm: str, plat: PlatformType, default_title: str, timeout: float, *, verbose: bool = False) -> Dict[str, str]:
    def _call():
        return _group_name_map(user, npcomm, plat, default_title, verbose=verbose)
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_call)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout:
            log(f"      · group_name_map timeout after {timeout:.1f}s — continuing without names", enabled=True)
            return {}

def _earned_from_title_obj(t) -> int:
    for cand in [
        getattr(t, "earned_trophies", None),
        getattr(t, "earned", None),
        getattr(t, "user_earned_trophies", None),
        getattr(t, "earned_trophies_count", None),
    ]:
        if cand is None:
            continue
        if any(hasattr(cand, k) for k in ("bronze", "silver", "gold", "platinum")):
            return sum(int(getattr(cand, k, 0) or 0) for k in ("bronze", "silver", "gold", "platinum"))
        if isinstance(cand, dict):
            return sum(v for v in cand.values() if isinstance(v, int))
        if isinstance(cand, (list, tuple)):
            return sum(v for v in cand if isinstance(v, int))
        if isinstance(cand, int):
            return cand
        if hasattr(cand, "__dict__"):
            return sum(v for v in cand.__dict__.values() if isinstance(v, int))
    return 0

def _cache_path(npcomm: str, plat_label: str) -> Path:
    return TROPHY_DIR / f"{npcomm}_{plat_label}.csv"

# ---------- cache completeness checks (so we can skip) ----------
def _cache_status(npcomm: str, plat_label: str, expected_total: int, expected_earned: int) -> str:
    """
    Returns one of: 'missing' | 'incomplete' | 'complete'
      - missing:   no cache file
      - incomplete: exists but looks partial (too few rows, no Earned flags, no GroupName, etc.)
      - complete:  rows >= expected_total (when known) AND Earned column present AND has GroupName
    """
    path = _cache_path(npcomm, plat_label)
    if not path.exists():
        return "missing"
    try:
        tdf = pd.read_csv(path)
    except Exception:
        return "incomplete"

    if tdf.empty:
        return "incomplete"

    # Earned present?
    earned_ok = "Earned" in tdf.columns and tdf["Earned"].notna().any()

    # GroupName present?
    has_group_names = "GroupName" in tdf.columns and tdf["GroupName"].astype(str).str.strip().ne("").any()

    # If we know some are earned but cache shows zero, consider incomplete
    if expected_earned > 0 and ("Earned" not in tdf.columns or int(pd.to_numeric(tdf["Earned"], errors="coerce").fillna(0).sum()) == 0):
        return "incomplete"

    # Enough rows?
    unique_ids = tdf["TrophyID"].nunique() if "TrophyID" in tdf.columns else len(tdf)
    if expected_total and unique_ids < expected_total:
        return "incomplete"

    return "complete" if earned_ok and has_group_names else "incomplete"

def _should_refresh_cache(prev_titles: pd.DataFrame, row: pd.Series) -> bool:
    npcomm, plat = str(row["NPCommID"]), str(row["Platform"])
    # 1) If cache missing or incomplete → refresh
    status = _cache_status(npcomm, plat, int(row.get("TrophiesTotal", 0) or 0), int(row.get("TrophiesUnlocked", 0) or 0))
    if status in ("missing", "incomplete"):
        return True

    # 2) Otherwise, only refresh if the title's numbers changed vs previous snapshot
    if prev_titles is None or prev_titles.empty:
        return False
    prev = prev_titles[
        (prev_titles["NPCommID"].astype(str) == npcomm) &
        (prev_titles["Platform"].astype(str) == plat)
    ]
    if prev.empty:
        return True  # new title we haven't seen before
    p = prev.iloc[0]
    for k in ("TrophiesUnlocked", "TrophiesTotal", "Percent"):
        if int(row.get(k, 0) or 0) != int(p.get(k, 0) or 0):
            return True
    return False

def _write_titles(rows: list[Tuple[str, str, str, int, int, int]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TITLES_CSV.with_suffix(".tmp.csv")
    bak = TITLES_CSV.with_suffix(".prev.csv")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Title", "NPCommID", "Platform", "TrophiesUnlocked", "TrophiesTotal", "Percent"])
            w.writerows(rows)
        if TITLES_CSV.exists():
            if bak.exists():
                try: bak.unlink()
                except Exception: pass
            TITLES_CSV.replace(bak)
        tmp.replace(TITLES_CSV)
    finally:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass

# ---- Core: list trophies with per-trophy progress ----
def _list_trophies_with_timeout(user, npcomm, plat, gid, timeout: float) -> list:
    """
    Try modern signature with include_progress=True; fall back to older forms.
    """
    def _call():
        try:
            return list(
                user.trophies(
                    np_communication_id=npcomm,
                    platform=plat,
                    include_progress=True,
                    trophy_group_id=gid,
                )
            )
        except TypeError:
            try:
                # Older psnawp versions (positional include_progress)
                return list(user.trophies(npcomm, plat, True, gid))
            except TypeError:
                # Ancient: no progress support
                return list(user.trophies(npcomm, plat, gid))
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_call)
        return fut.result(timeout=timeout)

def _norm_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}

def _cache_trophies_for(
    user,
    title: str,
    npcomm: str,
    plat_label: str,
    *,
    verbose: bool = False,
    group_timeout: float = 8.0,
    summary_timeout: float = 6.0,
    max_groups: int = 50,
    throttle: float = 0.0,
) -> int:
    plat = _platform_from_label(plat_label)
    if not plat:
        return 0
    out = _cache_path(npcomm, plat_label)
    rows, seen = [], set()

    # Build group name map (with timeout), then list groups
    gmap = _group_name_map_with_timeout(user, npcomm, plat, title, timeout=summary_timeout, verbose=verbose)
    gids = list(gmap.keys())
    if not gids:
        # fallback to enumerating ids; finally, at least try "default"
        gids = list(_group_ids(user, npcomm, plat, verbose=verbose)) or ["default"]

    # de-dup keep order
    uniq, seen_g = [], set()
    for g in gids:
        if g not in seen_g:
            uniq.append(g); seen_g.add(g)
    # max_groups: 0 or negative → unlimited
    gids = uniq if max_groups <= 0 else uniq[:max_groups]

    log(f"      · caching trophies → groups={gids[:8]}{'…' if len(gids)>8 else ''} (max {max_groups if max_groups>0 else '∞'})", enabled=verbose)

    for gi, gid in enumerate(gids, start=1):
        t0 = time.perf_counter()
        try:
            items = _list_trophies_with_timeout(user, npcomm, plat, gid, timeout=group_timeout)
        except FuturesTimeout:
            log(f"        ⚠ timeout after {group_timeout:.1f}s on group '{gid}' — skipping", enabled=verbose)
            try:
                items = _list_trophies_with_timeout(user, npcomm, plat, gid, timeout=max(3.0, group_timeout / 2))
            except Exception:
                items = []
        except Exception as e:
            log(f"        ⚠ error on group '{gid}': {e} — skipping", enabled=verbose)
            items = []

        if throttle > 0:
            time.sleep(throttle)

        log(f"        · group {gi}/{len(gids)} '{gid}': {len(items)} items in {time.perf_counter()-t0:.2f}s", enabled=verbose)

        group_name = gmap.get(gid) or (title if gid in ("default", "all", "0", "000") else gid)

        for t in items:
            tid = getattr(t, "trophy_id", None)
            if tid is None or (gid, tid) in seen:
                continue
            seen.add((gid, tid))

            # Pull progress if available
            earned_attr = getattr(t, "earned", None)
            if earned_attr is None:
                cu = getattr(t, "compared_user", None)
                earned_attr = getattr(cu, "earned", None) if cu is not None else None

            earn_rate = (
                getattr(t, "trophy_earn_rate", None)
                or getattr(t, "trophy_rare_rate", None)
                or getattr(getattr(t, "trophy_rarity", None), "rate", None)
            )

            rows.append({
                "GroupID":    gid,
                "GroupName":  group_name,
                "TrophyID":   tid,
                "Name":       getattr(t, "trophy_name", "") or getattr(t, "name", ""),
                "Detail":     getattr(t, "trophy_detail", "") or getattr(t, "detail", ""),
                "Grade":      getattr(t, "trophy_type", "") or getattr(t, "type", ""),
                "Earned":     _norm_bool(False if earned_attr is None else earned_attr),
                "EarnedRate": earn_rate,
                "IconURL":    getattr(t, "trophy_icon_url", "") or getattr(t, "icon_url", ""),
            })

    if rows:
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    return len(rows)

def _enumerate_and_count(user, npcomm: str, plat: PlatformType, *, verbose: bool = False) -> int:
    total = 0
    gids = list(_group_ids(user, npcomm, plat, verbose=verbose)) or ["all"]
    for gid in gids:
        try:
            try:
                items = list(user.trophies(np_communication_id=npcomm, platform=plat, trophy_group_id=gid))
            except TypeError:
                items = list(user.trophies(npcomm, plat, gid))
            subtotal = len(items); total += subtotal
            log(f"      · trophies[{plat.value}][{gid}] → {subtotal}", enabled=verbose)
        except Exception as e:
            log(f"      · trophies[{plat.value}][{gid}] error: {e}", enabled=verbose)
    return total

# ===================== main sync =====================
def sync(
    limit: int = 0,
    refresh: str = "changed",   # changed | all | none
    throttle: float = 0.0,
    verbose: bool = False,
    group_timeout: float = 6.0,
    summary_timeout: float = 6.0,
    max_groups: int = 50,
    title_timeout: float = 45.0,  # hard per-title cap so we always move on
    log_unchanged_titles: bool = False,
) -> str:
    """
    - Titles CSV is always refreshed.
    - Trophy caches are refreshed based on `refresh`:
        * none     → never refresh
        * changed  → refresh if cache missing/incomplete OR the title's numbers changed vs .prev
        * all      → refresh all, but still respect per-title timeout so we never get stuck
    """
    _require_env()
    t_start = time.perf_counter()

    psn = PSNAWP(NPSSO)
    user = psn.user(online_id=ONLINE_ID)

    prev_df = pd.read_csv(TITLES_CSV) if TITLES_CSV.exists() else pd.DataFrame()

    # ---------------- titles pass ----------------
    log("📥 Fetching trophy titles…", enabled=verbose)
    titles = list(user.trophy_titles())
    if limit:
        titles = titles[:limit]
        log(f"🔎 Limiting to first {len(titles)} titles.", enabled=verbose)

    rows = []
    for idx, t in enumerate(titles, start=1):
        t0 = time.perf_counter()

        title = getattr(t, "title_name", "") or getattr(t, "name", "")
        npcomm = getattr(t, "np_communication_id", "") or ""
        pset = getattr(t, "title_platform", None) or getattr(t, "platform", frozenset())
        primary = _choose_primary_platform(pset)
        label = _platform_label(primary)

        percent = getattr(t, "progress", None) or getattr(t, "progress_percent", 0) or 0
        try: percent = int(percent)
        except Exception: percent = 0
        earned_now = _earned_from_title_obj(t)

        # Totals: reuse old totals if title unchanged, else recompute
        total = 0
        prev_row = None
        if not prev_df.empty:
            cand = prev_df[
                (prev_df["NPCommID"].astype(str) == npcomm) &
                (prev_df["Platform"].astype(str) == label)
            ]
            if not cand.empty:
                prev_row = cand.iloc[0]

        recompute_totals = True
        if prev_row is not None:
            prev_earned = int(prev_row.get("TrophiesUnlocked", 0) or 0)
            prev_percent = int(prev_row.get("Percent", 0) or 0)
            if earned_now == prev_earned and percent == prev_percent:
                total = int(prev_row.get("TrophiesTotal", 0) or 0)
                recompute_totals = False
                log(f"[{idx}/{len(titles)}] {title} ({label or '-'}) • NPCommID={npcomm} • {percent}%  ↪︎ unchanged, reuse totals={total}",
                    enabled=verbose and log_unchanged_titles)
            else:
                log(f"[{idx}/{len(titles)}] {title} ({label or '-'}) • NPCommID={npcomm} • {percent}%  (changed)", enabled=verbose)
        else:
            log(f"[{idx}/{len(titles)}] {title} ({label or '-'}) • NPCommID={npcomm} • {percent}%  (new)", enabled=verbose)

        if primary and recompute_totals:
            total = _groups_total(user, npcomm, primary, verbose=verbose)
            if not total:
                total = _enumerate_and_count(user, npcomm, primary, verbose=verbose)
        elif not primary:
            total = 0

        rows.append((title, npcomm, label, int(earned_now), int(total), int(percent)))

        if throttle > 0: time.sleep(throttle)
        log(f"   • title time = {time.perf_counter() - t0:.2f}s", enabled=verbose and (recompute_totals or log_unchanged_titles))

    # write titles + keep .prev
    log("💾 Writing psn_titles.csv…", enabled=verbose)
    _write_titles(rows)

    # ---------------- trophies caches ----------------
    new_prev = pd.read_csv(TITLES_CSV.with_suffix(".prev.csv")) if TITLES_CSV.with_suffix(".prev.csv").exists() else pd.DataFrame()
    df = pd.DataFrame(rows, columns=["Title","NPCommID","Platform","TrophiesUnlocked","TrophiesTotal","Percent"])

    refreshed = 0
    skipped   = 0
    log(f"🗃️ Refresh mode: {refresh}", enabled=True)

    for _, r in df.iterrows():
        title = r['Title']; plat = r['Platform']; npcomm = r['NPCommID']

        if refresh == "none":
            log(f"↪︎ Skip (refresh=none): {title} [{plat}]", enabled=True)
            skipped += 1
            continue

        need = True
        if refresh == "changed":
            need = _should_refresh_cache(new_prev, r)

        if not need:
            log(f"↪︎ Skip (unchanged & cache complete): {title} [{plat}]", enabled=True)
            skipped += 1
            continue

        def _do_cache():
            return _cache_trophies_for(
                user, title, npcomm, plat,
                verbose=False,
                group_timeout=group_timeout,
                summary_timeout=summary_timeout,
                max_groups=max_groups,
                throttle=throttle
            )

        t1 = time.perf_counter()
        if 0.0 < title_timeout:
            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(_do_cache)
                    n = fut.result(timeout=title_timeout)
            except FuturesTimeout:
                log(f"⏭️  Skip '{title}' after {title_timeout:.1f}s (per-title timeout)", enabled=True)
                n = 0
        else:
            n = _do_cache()

        if n:
            refreshed += 1
            log(f"✔ Updated trophies: {title} [{plat}] → {n} items ({time.perf_counter()-t1:.2f}s)", enabled=True)
        else:
            log(f"➖ No update (timeout or empty): {title} [{plat}]", enabled=True)

        if throttle > 0:
            time.sleep(throttle)

    duration = time.perf_counter() - t_start
    return f"Updated titles: {len(rows)} • refreshed caches: {refreshed} • skipped: {skipped} • {duration:.1f}s"

# ===================== CLI =====================
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Sync PSN titles & cache per-title trophies (resume-friendly).")
    p.add_argument("--limit", type=int, default=0, help="Process only first N titles")
    p.add_argument("--refresh", choices=["changed", "all", "none"], default="changed",
                   help="Refresh policy: changed=only missing/incomplete or changed; all=force all; none=never")
    p.add_argument("--throttle", type=float, default=0.0,
                   help="Sleep this many seconds between network calls")
    p.add_argument("--verbose", action="store_true", help="Verbose logging for titles summary")
    p.add_argument("--group-timeout", type=float, default=6.0,
                   help="Seconds to wait per trophy group before skipping")
    p.add_argument("--summary-timeout", type=float, default=6.0,
                   help="Seconds to wait for group names summary before continuing")
    p.add_argument("--max-groups", type=int, default=50,
                   help="Maximum trophy groups to process per title (0 = unlimited)")
    p.add_argument("--title-timeout", type=float, default=45.0,
                   help="Maximum seconds to spend caching trophies per title (0=no limit)")
    p.add_argument("--log-unchanged-titles", action="store_true",
                   help="When --verbose, also log unchanged titles during the titles pass")
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    try:
        msg = sync(
            limit=args.limit,
            refresh=args.refresh,
            throttle=args.throttle,
            verbose=args.verbose,
            group_timeout=args.group_timeout,
            summary_timeout=args.summary_timeout,
            max_groups=args.max_groups,
            title_timeout=args.title_timeout,
            log_unchanged_titles=args.log_unchanged_titles,
        )
        print("✅", msg, flush=True)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user.", flush=True)
        sys.exit(130)

if __name__ == "__main__":
    main()
