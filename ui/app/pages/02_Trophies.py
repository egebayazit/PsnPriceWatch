# ui/app/pages/02_Trophies.py
from pathlib import Path
from urllib.parse import quote as _urlq
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="PsnPriceWatch – Trophies",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hard-hide sidebar/nav everywhere (prevents flash + removes on this page)
st.markdown(
    """
    <style>
      [data-testid="stSidebar"],
      [data-testid="stSidebarNav"],
      [data-testid="stSidebarCollapsedControl"],
      section[data-testid="stSidebar"] {
        display: none !important;
      }
      .block-container { padding-left: 1rem; padding-right: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

PSN_TITLES_CSV = Path("ui/data/psn_titles.csv")
ICONS_CSV      = Path("ui/data/psn_icons.csv")
TROPHIES_DIR   = Path("ui/data/trophies")
PLACEHOLDER    = "https://placehold.co/640x320/0f1116/FFFFFF?text=Cover"

# ---------- helpers ----------
def qp_get(key: str, default: str = "") -> str:
    try:
        return str(st.query_params.get(key, default))
    except AttributeError:
        return default

def qp_set(**kwargs):
    try:
        st.query_params.update(kwargs)
    except AttributeError:
        pass

def show_image(url: str):
    try:
        st.image(url, use_container_width=True)
    except TypeError:
        st.image(url, use_column_width=True)

def as_int(val, default=0):
    try:
        if pd.isna(val):
            return default
    except Exception:
        pass
    try:
        return int(val)
    except Exception:
        try:
            return int(float(val))
        except Exception:
            return default

def coerce_bool_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype=bool)
    m = {
        "true": True, "1": True, "yes": True, "y": True, "t": True,
        "false": False, "0": False, "no": False, "n": False, "f": False,
    }
    return (
        s.astype(str)
         .str.strip()
         .str.lower()
         .map(m)
         .fillna(False)
         .astype(bool)
    )

def clean_grade(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype="object")
    g = (
        s.astype(str)
         .str.replace(r"(?i)^trophytype\.", "", regex=True)
         .str.replace(r"(?i)^trophytype_", "", regex=True)
         .str.replace(r"(?i)^trophy\.", "", regex=True)
         .str.strip()
         .str.title()
    )
    return g.replace({
        "Trophytype.Bronze": "Bronze",
        "Trophytype.Silver": "Silver",
        "Trophytype.Gold": "Gold",
        "Trophytype.Platinum": "Platinum",
    })

# Tiny fallbacks (used only when an icon URL is missing)
def _fallback_trophy_svg(grade: str) -> str:
    color_map = {"Bronze": "#C07A2C", "Silver": "#C0C0C8", "Gold": "#F4C542", "Platinum": "#7DB7FF"}
    color = color_map.get((grade or "").title(), "#C0C0C8")
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>
      <path fill='{color}' d='M19 3h-3V2H8v1H5a1 1 0 0 0-1 1v2a5 5 0 0 0 5 5c.64.32 1.32.54 2 .66c.68-.12 1.36-.34 2-.66a5 5 0 0 0 5-5V4a1 1 0 0 0-1-1Zm-1 3a3 3 0 0 1-3 3c-.65.35-1.35.58-2 .68c-.65-.1-1.35-.33-2-.68a3 3 0 0 1-3-3V5h10ZM7 14.17A8.06 8.06 0 0 0 12 16c1.83 0 3.54-.62 5-1.83V16a2 2 0 0 1-2 2h-2v2.5h3V22H8v-1.5h3V18H9a2 2 0 0 1-2-2z'/>
    </svg>
    """.strip()
    return "data:image/svg+xml;utf8," + _urlq(svg)

def _green_check_svg() -> str:
    svg = """
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>
      <path fill='#22c55e' d='M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z'/>
    </svg>
    """.strip()
    return "data:image/svg+xml;utf8," + _urlq(svg)

def load_trophies(npcomm: str, plat_label: str) -> pd.DataFrame | None:
    path = TROPHIES_DIR / f"{npcomm}_{plat_label}.csv"
    if not path.exists():
        return None
    try:
        tdf = pd.read_csv(path)
    except Exception as e:
        st.error(f"Couldn't read trophies file: {path.name} ({e})")
        return None

    # expected columns (plus GroupName if present from the sync cache)
    for col in ["Name","Detail","Grade","Earned","EarnedRate","IconURL","GroupID","GroupName","TrophyID"]:
        if col not in tdf.columns:
            tdf[col] = "" if col not in ("Earned",) else False

    # normalize
    tdf["Earned"]      = coerce_bool_series(tdf.get("Earned"))
    tdf["Grade"]       = clean_grade(tdf.get("Grade"))
    tdf["EarnedRate"]  = pd.to_numeric(tdf.get("EarnedRate"), errors="coerce")

    # Natural numeric ID for proper sorting
    tdf["TrophyIDNum"] = pd.to_numeric(tdf.get("TrophyID"), errors="coerce")

    # default sort: missing first, then by numeric ID
    tdf = tdf.sort_values(by=["Earned", "TrophyIDNum"], ascending=[True, True], ignore_index=True)

    return tdf

# ---------- get selection ----------
npcomm   = qp_get("npcomm")   or st.session_state.get("sel_npcomm", "")
platform = qp_get("platform") or st.session_state.get("sel_platform", "")
title    = qp_get("title")    or st.session_state.get("sel_title", "Selected Game")

# ---------- header/metrics ----------
row, icon_url = None, ""
try:
    df = pd.read_csv(PSN_TITLES_CSV)
    if ICONS_CSV.exists():
        df = df.merge(pd.read_csv(ICONS_CSV), on="NPCommID", how="left")
    row = df[(df["NPCommID"].astype(str) == npcomm) & (df["Platform"].astype(str) == platform)]
    if row.empty:
        row = df[df["NPCommID"].astype(str) == npcomm]
    row = row.iloc[0] if not row.empty else None
    if row is not None:
        icon_url = str(row.get("IconURL","")) if pd.notna(row.get("IconURL","")) else ""
except Exception:
    pass

st.markdown(f"# 🏆 {title}")
st.caption(f"NPCommID: **{npcomm or '—'}** • Platform: **{platform or '—'}**")

c1, c2 = st.columns([1,3])
with c1:
    show_image(icon_url or PLACEHOLDER)
    if st.button("← Back to gallery", use_container_width=True):
        qp_set()
        for k in ("sel_npcomm","sel_platform","sel_title"):
            st.session_state.pop(k, None)
        try:
            st.switch_page("progress_app.py")
        except Exception:
            st.rerun()

with c2:
    if row is not None:
        p  = as_int(row.get("Percent", 0))
        tu = as_int(row.get("TrophiesUnlocked", 0))
        tt = as_int(row.get("TrophiesTotal", 0))
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Platform", str(row.get("Platform","")))
        cc2.metric("Completion", f"{p}%")
        cc3.metric("Trophies", f"{tu}/{tt}")
    else:
        st.caption("No aggregated metrics available for this selection.")

# ---------- tabs ----------
tab_overview, tab_trophies, tab_notes = st.tabs(["Overview", "Trophies", "Notes"])

with tab_overview:
    st.write("Overview content (future: playtime, sessions, rarity chart).")

def _group_display(title_: str, gid: str, gname: str) -> str:
    gid = (gid or "").strip()
    gname = (gname or "").strip()
    if gname:
        return gname
    return title_ if gid.lower() == "default" or gid == "" else gid

def _render_table(view_df: pd.DataFrame, show_group_col: bool):
    """Render the trophies table with icons, green tick (ID is hidden)."""
    # Use PSN icon if present; fallback tiny SVG otherwise
    def _icon_cell(row_):
        url = str(row_.get("IconURL", "") or "").strip()
        return url if url else _fallback_trophy_svg(row_.get("Grade", ""))

    green_tick = _green_check_svg()

    df_show = view_df.copy()
    df_show["IconPNG"]    = df_show.apply(_icon_cell, axis=1)
    df_show["EarnedMark"] = df_show["Earned"].map(lambda b: green_tick if bool(b) else "")
    # keep TrophyIDNum for initial sort order; do NOT display

    cc = st.column_config
    TextColumn   = getattr(cc, "TextColumn", None)
    NumberColumn = getattr(cc, "NumberColumn", None)
    ImageColumn  = getattr(cc, "ImageColumn", None)

    col_cfg = {}
    if ImageColumn:
        col_cfg["IconPNG"]    = ImageColumn("", width="small")
        col_cfg["EarnedMark"] = ImageColumn("Earned", width="small")
    if NumberColumn and "EarnedRate" in df_show:
        col_cfg["EarnedRate"] = NumberColumn("Rarity %")
    if TextColumn:
        col_cfg["Name"]   = TextColumn("Name", width="medium")
        col_cfg["Grade"]  = TextColumn("Grade", width="small")
        col_cfg["Detail"] = TextColumn("Description", width="large")
        if show_group_col and "GroupDisplay" in df_show.columns:
            col_cfg["GroupDisplay"] = TextColumn("Group", width="medium")

    # ID column removed from display
    show_cols = ["IconPNG","Name","Grade","EarnedMark","Detail","EarnedRate"]
    if show_group_col and "GroupDisplay" in df_show.columns:
        show_cols.append("GroupDisplay")
    show_cols = [c for c in show_cols if c in df_show.columns]

    st.dataframe(
        df_show[show_cols],
        column_config=col_cfg,
        use_container_width=True,
        hide_index=True
    )

with tab_trophies:
    if not (npcomm and platform):
        st.info("Open this page from the gallery so I know which game's trophies to load.")
    else:
        tdf = load_trophies(npcomm, platform)
        if tdf is None or tdf.empty:
            st.info("No cached trophy list found for this title. Run a sync to generate per-game trophy caches.")
        else:
            # If the cache has no earned flags but the summary says some are earned, hint to refresh
            expected_earned = as_int(row.get("TrophiesUnlocked", 0)) if row is not None else 0
            have_earned = int(tdf["Earned"].sum()) if "Earned" in tdf.columns else 0
            if expected_earned > 0 and have_earned == 0:
                st.warning(
                    "This trophy cache doesn’t include per-trophy 'earned' flags. "
                    "Try running a sync that refreshes trophies for this title (e.g., **Refresh: all**)."
                )

            # Compute human-friendly group display names
            tdf["GroupDisplay"] = tdf.apply(
                lambda r: _group_display(title, str(r.get("GroupID","")), str(r.get("GroupName",""))),
                axis=1
            )

            # Search & quick filter (applies to all tabs)
            left, right = st.columns([2,1])
            with left:
                search = st.text_input("Search trophy name/description", "")
            with right:
                view = st.selectbox("View", ["All", "Missing only", "Earned only"], index=0)

            base_df = tdf.copy()
            if search:
                s = search.strip().lower()
                base_df = base_df[
                    base_df["Name"].astype(str).str.lower().str.contains(s) |
                    base_df["Detail"].astype(str).str.lower().str.contains(s)
                ]
            if view == "Missing only":
                base_df = base_df[~base_df["Earned"]]
            elif view == "Earned only":
                base_df = base_df[base_df["Earned"]]

            # Build group stats + order: default first, then numeric IDs, then alpha
            id_sample = (
                base_df.groupby("GroupDisplay")["GroupID"]
                       .agg(lambda s: str(next((x for x in s if pd.notna(x)), "")))
                       .reset_index()
            )

            def _sort_key(gid: str):
                g = (gid or "").strip().lower()
                if g == "default" or g == "":
                    return (-1, 0, "")
                try:
                    return (0, int(g), "")
                except Exception:
                    return (1, 0, g)

            stats = []
            for gname, gdf in base_df.groupby("GroupDisplay"):
                total = len(gdf)
                earned = int(gdf["Earned"].sum())
                pct = int(round(earned * 100 / total)) if total else 0
                gid = id_sample[id_sample["GroupDisplay"] == gname]["GroupID"].iloc[0] if not id_sample.empty else ""
                stats.append({
                    "GroupDisplay": gname,
                    "GroupID": gid,
                    "total": total,
                    "earned": earned,
                    "pct": pct,
                    "sort": _sort_key(str(gid)),
                })

            stats = sorted(stats, key=lambda x: x["sort"])

            # Build tabs: All + per-group with completion in the label
            tab_labels = ["All"] + [f"{s['GroupDisplay']} ({s['earned']}/{s['total']} • {s['pct']}%)" for s in stats]
            containers = st.tabs(tab_labels)

            # --- All tab ---
            with containers[0]:
                _render_table(base_df, show_group_col=True)

            # --- Per-group tabs ---
            for i, s in enumerate(stats, start=1):
                with containers[i]:
                    gdf = base_df[base_df["GroupDisplay"] == s["GroupDisplay"]]
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Group", s["GroupDisplay"])
                    m2.metric("Completion", f"{s['pct']}%")
                    m3.metric("Trophies", f"{s['earned']}/{s['total']}")
                    _render_table(gdf, show_group_col=False)

with tab_notes:
    st.write("Add your personal notes here (future enhancement: write-back to CSV).")
