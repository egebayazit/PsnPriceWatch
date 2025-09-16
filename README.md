# 🎮 PsnPriceWatch

A two-part project for PlayStation users:

1. **Price Watcher (automation)**
   - Tracks discounts and price drops for your chosen games on the **PlayStation Store Turkey**.
   - Uses:
     - **Apify** → fetch DLC/add-ons per title (TR store).
     - **PlatPrices API** → get current prices & discount info for `region=TR`.
     - **GitHub Actions** → scheduled daily run, diff reports, optional Discord alerts.
   - Input lists:
     - `lists/new_games.txt` → games + DLC you plan to buy.
     - `lists/backlog.txt` → games already owned (track DLC only).

2. **Progress Dashboard (UI)**
   - A Streamlit web app to view your **PlayStation trophies, completion %, and platform mix**.
   - Uses:
     - [`psnawp-api`](https://pypi.org/project/psnawp-api/) → fetch trophy/title data from PSN.
     - Custom scripts in `ui/scripts/` for health checks, syncing, and fetching icons.
     - Visual dashboard (`ui/app/`) with filters, charts, and a gallery view of your collection.

---

## ⚡ Quickstart

### Price Watcher
```bash
# Install deps
pip install -r requirements.txt

# Build watchlist via Apify
APIFY_TOKEN=... python scripts/apify_resolve.py

# Fetch prices
PLAT_KEY=... REGION=TR python scripts/fetch_prices.py

# Generate diff report
DISCORD_WEBHOOK=... python scripts/diff_report.py
Daily runs are automated with GitHub Actions:
See .github/workflows/psn-price-watch.yml.

Progress Dashboard

# From repo root
.\.venv\Scripts\activate
streamlit run ui\app\progress_app.py
Log in with your PSN_NPSSO and PSN_ONLINE_ID environment variables set.

Data gets cached in ui/data/psn_titles.csv and ui/data/psn_icons.csv.

📂 Repo structure

.github/workflows/   → GitHub Actions (daily automation)
lists/               → Your tracked games (new & backlog)
scripts/             → Price fetching & reporting
ui/app/              → Streamlit UI apps
ui/scripts/          → Trophy/PSN helpers (icons, health check, update)
ui/data/             → CSV cache (titles, icons, progress)