# ui/app/progress_app.py
import re
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="PsnPriceWatch – Progress (Gallery v5)", page_icon="🎮", layout="wide")

PROGRESS_CSV = Path("ui/data/progress.csv")
PSN_TITLES_CSV = Path("ui/data/psn_titles.csv")
ICONS_CSV     = Path("ui/data/psn_icons.csv")  # optional cover art (Title/NPCommID → IconURL)

# =============== Global CSS (safe, compact) ===============
st.markdown(
    """
    <style>
      .hero { padding:18px 20px; border-radius:14px; border:1px solid rgba(255,255,255,.10);
              background: linear-gradient(135deg, rgba(40,40,60,.35), rgba(20,20,30,.25)); }
      .hero h1 { margin:0 0 4px 0; font-size:1.8rem; color:rgba(255,255,255,.95); }
      .muted { color:rgba(255,255,255,.80) }

      /* Card */
      .card { background: rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.12);
              border-radius:12px; overflow:hidden; height: 300px; display:flex; flex-direction:column; }
      .card__img { height:160px; width:100%; background:#0f1116; overflow:hidden; }
      .card__img img { width:100%; height:100%; object-fit:cover; display:block; }
      .card__body { padding:10px 12px; display:flex; flex-direction:column; gap:6px; }
      .title { font-weight:700; font-size:.95rem; color:rgba(255,255,255,.98);
               line-height:1.2; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
      .meta  { font-size:.86rem; color:rgba(255,255,255,.85); }
      .tiny  { font-size:.84rem; color:rgba(255,255,255,.80); }

      .progress { position:relative; height:7px; background:rgba(255,255,255,.10); border-radius:999px; overflow:hidden; }
      .progress > span { position:absolute; left:0; top:0; bottom:0; width:0%;
                         background:#2f80ed; border-radius:999px; }

      /* Tabs spacing tweak */
      [data-baseweb="tab-list"] { gap: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============== Helpers ===============
def _normalize_platform(cell: str) -> str:
    if not isinstance(cell, str):
        return ""
    labels = re.findall(r"'(PS[0-9VITA]+)'", cell)
    return "/".join(sorted(set(labels))) if labels else (cell if cell != "None" else "")

def _infer_completed_row(row) -> bool:
    p  = row.get("Percent", np.nan)
    tu = row.get("TrophiesUnlocked", np.nan)
    tt = row.get("TrophiesTotal", np.nan)
    by_percent  = pd.notna(p)  and float(p) >= 100 - 1e-6
    by_trophies = pd.notna(tu) and pd.notna(tt) and int(tt) > 0 and int(tu) >= int(tt)
    return bool(by_percent or by_trophies)

def load_dataframe() -> pd.DataFrame:
    if PROGRESS_CSV.exists():
        df, source = pd.read_csv(PROGRESS_CSV), "progress.csv"
    elif PSN_TITLES_CSV.exists():
        df, source = pd.read_csv(PSN_TITLES_CSV), "psn_titles.csv"
        for col in ["List","Status","LastActivity","Notes"]:
            if col not in df.columns: df[col] = ""
        if "Platform" in df.columns:
            df["Platform"] = df["Platform"].apply(_normalize_platform)
        for c in ["TrophiesUnlocked","TrophiesTotal"]:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        if "Percent" in df.columns:
            df["Percent"] = pd.to_numeric(df["Percent"], errors="coerce").fillna(0.0)
    else:
        st.error("Missing data files. Create ui/data/progress.csv or ui/data/psn_titles.csv.")
        st.stop()

    # Auto-infer Status if blank
    if "Status" not in df.columns:
        df["Status"] = ""
    blank = df["Status"].astype(str).str.strip().eq("")
    if blank.any():
        done = df.apply(_infer_completed_row, axis=1)
        df.loc[blank & done, "Status"] = "Completed"
        df.loc[blank & ~done, "Status"] = "In Progress"

    st.caption(f"Data source: **{source}**")
    return df

def load_icons() -> pd.DataFrame:
    if ICONS_CSV.exists():
        dfi = pd.read_csv(ICONS_CSV)[["NPCommID","IconURL"]].dropna(subset=["NPCommID"])
        dfi["IconURL"] = dfi["IconURL"].fillna("")
        return dfi
    return pd.DataFrame(columns=["NPCommID","IconURL"])

# =============== Load data ===============
df = load_dataframe()
icons = load_icons()
if "Percent" in df.columns:
    df["Percent"] = pd.to_numeric(df["Percent"], errors="coerce").fillna(0).clip(0,100)

if not icons.empty and "NPCommID" in df.columns:
    df = df.merge(icons, on="NPCommID", how="left")
else:
    df["IconURL"] = ""

# =============== Hero ===============
st.markdown(
    """
    <div class="hero">
      <h1>🎮 Personal Progress Dashboard</h1>
      <div class="muted">Uniform cover cards, clean grid, and quick filters.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============== Filters & KPIs ===============
c1, c2, c3 = st.columns([2,1.2,1.2])
q = c1.text_input("🔎 Search title", "")
status_filter   = c2.multiselect("Status", sorted(df["Status"].dropna().unique()))
platform_filter = c3.multiselect("Platform", sorted(df["Platform"].dropna().unique()) if "Platform" in df.columns else [])

f = df.copy()
if q:
    f = f[f["Title"].astype(str).str.contains(q, case=False, na=False)]
if status_filter:
    f = f[f["Status"].isin(status_filter)]
if platform_filter and "Platform" in f.columns:
    f = f[f["Platform"].isin(platform_filter)]

total_games = len(f)
completed   = int((f["Status"] == "Completed").sum())
avg_pct     = int(f["Percent"].mean()) if len(f) else 0
sum_earned  = int(f.get("TrophiesUnlocked", pd.Series(dtype=int)).sum())
sum_total   = int(f.get("TrophiesTotal", pd.Series(dtype=int)).sum())

m1,m2,m3,m4 = st.columns(4)
m1.metric("Games (filtered)", total_games)
m2.metric("Completed", completed)
m3.metric("Avg. %", f"{avg_pct}%")
m4.metric("Trophies (earned/total)", f"{sum_earned:,}/{sum_total:,}")

# =============== Card renderer ===============
PLACEHOLDER = "https://placehold.co/640x320/0f1116/FFFFFF?text=Cover"

def card_html(title: str, platform: str, percent: int, earned: int, total: int, icon_url: str) -> str:
    pct = max(0, min(100, int(percent)))
    img = icon_url.strip() or PLACEHOLDER
    return f"""
    <div class="card">
      <div class="card__img"><img src="{img}" loading="lazy" alt=""></div>
      <div class="card__body">
        <div class="title">{title}</div>
        <div class="meta">{platform} • {pct}%</div>
        <div class="progress"><span style="width:{pct}%"></span></div>
        <div class="tiny">{earned}/{total} trophies</div>
      </div>
    </div>
    """

def render_grid(df_subset: pd.DataFrame, cols_per_row: int = 5, limit: int = 100):
    if df_subset.empty:
        st.info("Nothing to show.")
        return

    show = df_subset[["Title","Platform","Percent","TrophiesUnlocked","TrophiesTotal","IconURL"]].copy()
    show = show.fillna({"IconURL": ""}).head(limit)
    show["Percent"] = pd.to_numeric(show["Percent"], errors="coerce").fillna(0).clip(0,100).astype(int)

    rows = [show[i:i+cols_per_row] for i in range(0, len(show), cols_per_row)]
    for chunk in rows:
        cols = st.columns(cols_per_row, gap="medium")
        # iterate over the columns we created; if chunk shorter than cols_per_row, fill the rest with empty containers
        for idx in range(cols_per_row):
            with cols[idx]:
                if idx < len(chunk):
                    r = chunk.iloc[idx]
                    html = card_html(
                        title=str(r["Title"]),
                        platform=str(r.get("Platform","")),
                        percent=int(r.get("Percent",0)),
                        earned=int(r.get("TrophiesUnlocked",0)),
                        total=int(r.get("TrophiesTotal",0)),
                        icon_url=str(r.get("IconURL","")),
                    )
                    # one single HTML block → no ghost elements
                    st.markdown(html, unsafe_allow_html=True)
                else:
                    # draw an invisible spacer so last row keeps height (optional)
                    st.markdown('<div style="height:300px;"></div>', unsafe_allow_html=True)

# =============== Buckets & Tabs ===============
near_plat = f[(f["Percent"] >= 90) & (f["Percent"] < 100)] if "Percent" in f.columns else f.iloc[0:0]
done      = f[f["Status"] == "Completed"] if "Status" in f.columns else f.iloc[0:0]
todo      = f[f["Status"] != "Completed"] if "Status" in f.columns else f

tab_gallery, tab_done, tab_near, tab_todo, tab_table = st.tabs([
    "🖼️ Gallery",
    f"✅ Completed ({len(done)})",
    f"🏆 Near Platinum ({len(near_plat)})",
    f"📌 In Progress ({len(todo)})",
    "🧾 Table view",
])

with tab_gallery:
    render_grid(f, cols_per_row=5)

with tab_done:
    render_grid(done, cols_per_row=5)

with tab_near:
    render_grid(near_plat, cols_per_row=5)

with tab_todo:
    render_grid(todo, cols_per_row=5)

with tab_table:
    desired = ["Title","Platform","TrophiesUnlocked","TrophiesTotal","Percent"]
    cols_show = [c for c in desired if c in f.columns]
    col_cfg = {}
    if "Percent" in cols_show:
        col_cfg["Percent"] = st.column_config.ProgressColumn("Percent", min_value=0, max_value=100, format="%d%%")
    st.dataframe(f[cols_show], column_config=col_cfg, use_container_width=True, hide_index=True)
