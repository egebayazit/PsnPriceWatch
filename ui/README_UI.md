# 🎮 PsnPriceWatch – UI

A Streamlit dashboard to explore your PlayStation trophy progress.  
It connects to PSN via [`psnawp-api`](https://pypi.org/project/psnawp-api/) and shows your games, completion %, and earned trophies with charts and a gallery view.

---

## 🚀 Features
- **Dashboard Overview**  
  - Completion % per game (progress bars).  
  - Earned vs. total trophies.  
  - Metrics (games tracked, completed, avg %).  
- **Filters**  
  - Search by title.  
  - Filter by platform or status.  
- **Tabs & Views**  
  - ✅ Completed games.  
  - 🏆 Near Platinum (≥90% but not 100%).  
  - 📌 In Progress.  
  - 🖼️ Gallery view with cover art grid.  
  - 🧾 Table view.  
- **Visuals**  
  - Altair charts for platform mix and progress distribution.  
  - Uniform gallery cards with game icons (via `ui/data/psn_icons.csv`).

---

## ⚡ Setup

1. Activate your virtual environment:
   ```powershell
   .\.venv\Scripts\activate
Run the dashboard:

streamlit run ui\app\progress_app.py
Ensure environment variables are set:

setx PSN_NPSSO "your-npsso-token"
setx PSN_ONLINE_ID "your-online-id"
📂 Data Files
ui/data/psn_titles.csv → auto-generated via update_from_psn_titles_v21.py (trophies, progress).

ui/data/psn_icons.csv → auto-generated via build_psn_icons.py (cover images).

(Optional) ui/data/progress.csv → if present, overrides with custom status/notes.

🔧 Helper Scripts
update_from_psn_titles_v21.py → fetch trophies & progress from PSN.

build_psn_icons.py → pull per-title icons for gallery.

psn_health_check.py → debug connection & trophy fetching.

whoami.py → verify PSN auth (prints your profile).