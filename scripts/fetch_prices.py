#!/usr/bin/env python3
import os, json, pathlib, sys
from datetime import datetime
from hashlib import md5

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
WATCHLIST = REPORTS / "watchlist.json"
OUTFILE = REPORTS / "prices_current.json"

PLAT_URL = os.getenv("PLAT_API_URL")  # e.g. https://platprices.com/api.php (if applicable)
PLAT_KEY = os.getenv("PLAT_KEY")
REGION   = os.getenv("REGION", "TR")

def mock_price_for(title):
    # deterministic pseudo-price for stable diffs in CI without secrets
    h = int(md5(title.encode("utf-8")).hexdigest(), 16)
    base = 99 + (h % 251)  # 99–349 TL
    discount = 0 if (h % 3) else (10 * ((h // 3) % 5))  # 0,10,20,30,40%
    return {"price": base, "discount_pct": discount, "currency": "TRY", "live": False}

def fetch_live(title, store_id=None, plat_id=None):
    if not (PLAT_URL and PLAT_KEY):
        return mock_price_for(title)
    try:
        import requests
        # This is a generic pattern; adjust params to your actual endpoint spec.
        params = {
            "key": PLAT_KEY,
            "q": title,
            "region": REGION
        }
        r = requests.get(PLAT_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        # Map to a normalized shape; tweak selectors per your API response
        # Fallbacks if fields aren’t present
        price = data.get("price") or data.get("current_price") or 0
        discount = data.get("discount_pct") or data.get("discount") or 0
        currency = data.get("currency") or "TRY"
        return {"price": price, "discount_pct": discount, "currency": currency, "live": True, "raw": data}
    except Exception as e:
        print(f"[fetch_prices] live fetch failed for '{title}': {e}", file=sys.stderr)
        return mock_price_for(title)

def main():
    if not WATCHLIST.exists():
        print(f"[fetch_prices] {WATCHLIST} missing; run apify_resolve first.", file=sys.stderr)
        sys.exit(1)
    wl = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    items = wl.get("items", [])
    out = []
    for it in items:
        title = it.get("title","").strip()
        if not title: continue
        price = fetch_live(title, it.get("store_id"), it.get("platprices_id"))
        out.append({
            "title": title,
            "store_id": it.get("store_id"),
            "platprices_id": it.get("platprices_id"),
            "region": REGION,
            **price
        })
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "region": REGION,
        "count": len(out),
        "items": sorted(out, key=lambda x: x["title"].lower())
    }
    OUTFILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[fetch_prices] wrote {OUTFILE} with {len(out)} items (live={any(i.get('live') for i in out)})")

if __name__ == "__main__":
    main()
