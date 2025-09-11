# PSN TR Price Watch

Daily price checker for **PlayStation Store Turkey** (games + DLC).  
- **Apify**: enumerate DLC/add-ons per title (TR store).  
- **PlatPrices**: fetch prices & discount info for `region=TR`.  
- **GitHub Actions**: run daily, create a diff report, optional alerts.

## Quickstart
1. Put your titles into:
   - `lists/new_games.txt`  (track **game + DLC**)  
   - `lists/backlog.txt`    (**DLC only** for already-started games)  
2. Build watchlist (Apify) → fetch prices (PlatPrices) → generate diff.
