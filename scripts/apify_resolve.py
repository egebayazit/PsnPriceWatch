#!/usr/bin/env python3
import os, json, sys, pathlib, re
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
LISTS = ROOT / "lists"
OUTDIR = ROOT / "reports"
OUTDIR.mkdir(parents=True, exist_ok=True)
OUTFILE = OUTDIR / "watchlist.json"

# Lines that should be ignored entirely (section headers, etc.)
HEADER_PATTERNS = [
    r"^to[- ]?do platinum",           # To-Do Platinum New Games...
    r"^backlog\b",                    # Backlog – Already Played...
]
HEADER_RE = re.compile("|".join(HEADER_PATTERNS), flags=re.IGNORECASE)

# Strip leading numbering like "12. " or "12) " or "12 - " and extra spaces
LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[\.\-\)]\s*")

def read_list(path: pathlib.Path):
    if not path.exists():
        return []
    raw = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    cleaned = []
    for ln in raw:
        if not ln:
            continue
        if HEADER_RE.search(ln):
            continue
        # remove leading numbering if present
        ln = LEADING_NUMBER_RE.sub("", ln)
        # collapse internal whitespace
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            cleaned.append(ln)
    return cleaned

def maybe_call_apify(titles):
    token = os.getenv("APIFY_TOKEN")
    actor = os.getenv("APIFY_ACTOR_ID")  # optional; e.g. your custom PS Store resolver
    if not token or not actor:
        # fallback: titles only
        return [{"title": t} for t in titles]

    try:
        import requests, time
        run_url = f"https://api.apify.com/v2/acts/{actor}/runs?token={token}"
        payload = {"titles": titles}
        run = requests.post(run_url, json=payload, timeout=30).json()
        run_id = run["data"]["id"]
        # poll until finished
        while True:
            r = requests.get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}", timeout=15).json()
            status = r["data"]["status"]
            if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                break
            time.sleep(3)
        if status != "SUCCEEDED":
            return [{"title": t} for t in titles]
        # fetch dataset items
        dataset_id = r["data"]["defaultDatasetId"]
        items = requests.get(f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}", timeout=30).json()
        result = []
        for it in items:
            result.append({
                "title": it.get("title") or it.get("name") or "",
                "store_id": it.get("id") or it.get("npTitleId"),
                "platprices_id": it.get("platpricesId")
            })
        return result
    except Exception as e:
        print(f"[apify_resolve] Apify call failed: {e}", file=sys.stderr)
        return [{"title": t} for t in titles]

def main():
    new_games = read_list(LISTS / "new_games.txt")
    backlog   = read_list(LISTS / "backlog.txt")
    # dedupe case-insensitively
    seen = set()
    titles = []
    for t in new_games + backlog:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            titles.append(t)

    resolved = maybe_call_apify(titles)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(resolved),
        "items": resolved
    }
    OUTFILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[apify_resolve] wrote {OUTFILE} with {len(resolved)} items (from {len(new_games)+len(backlog)} raw)")

if __name__ == "__main__":
    main()
