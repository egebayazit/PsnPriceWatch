#!/usr/bin/env python3
import json, pathlib, shutil
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CUR = REPORTS / "prices_current.json"
PREV = REPORTS / "prices_previous.json"

def load(path):
    if not path.exists():
        return {"items": []}
    return json.loads(path.read_text(encoding="utf-8"))

def keymap(items):  # normalize by title
    return {(it["title"].strip().lower()): it for it in items if it.get("title")}

def fmt_price_block(it):
    if not it:
        return "—"
    price = it.get("price")
    disc = it.get("discount_pct", 0) or 0
    cur = it.get("currency", "")
    if price is None:
        return "—"
    return f"{price} {cur} ({disc}% off)" if disc else f"{price} {cur}"

def mkrow_change(change):
    t = change["title"]
    old = change["old"]
    new = change["new"]
    return f"| {t} | {fmt_price_block(old)} | {fmt_price_block(new)} |"

def top_discounts(items, top_n=10):
    # Pick items with a discount > 0 and sort by discount desc, then title
    discounted = [it for it in items if (it.get("discount_pct") or 0) > 0]
    discounted.sort(key=lambda x: (x.get("discount_pct", 0), -float(x.get("price", 0) or 0)), reverse=True)
    return discounted[:top_n]

def mkrow_discount(it):
    title = it.get("title", "—")
    price = it.get("price")
    disc = it.get("discount_pct", 0) or 0
    cur = it.get("currency", "")
    p = "—" if price is None else f"{price} {cur}"
    return f"| {title} | {p} | {disc}% |"

def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().date().isoformat()
    md_path = REPORTS / f"{today}.md"

    cur = load(CUR)
    prev = load(PREV)
    km_prev = keymap(prev.get("items", []))
    km_cur = keymap(cur.get("items", []))

    # Build change list (price or discount changed, or new item)
    changes = []
    for title, new in km_cur.items():
        old = km_prev.get(title)
        if not old or (old.get("price") != new.get("price") or (old.get("discount_pct") or 0) != (new.get("discount_pct") or 0)):
            changes.append({"title": new["title"], "old": old, "new": new})

    # Header & meta
    header = f"# PsnPriceWatch — Price Diff Report ({today})\n\n"
    meta = (
        f"- Region: **{cur.get('region','TR')}**  \n"
        f"- Items: **{cur.get('count',0)}**  \n"
        f"- Live fetch: **{'yes' if any(i.get('live') for i in cur.get('items',[])) else 'no (mock)'}**\n\n"
    )

    # Top Discounts Today
    top = top_discounts(cur.get("items", []), top_n=10)
    if top:
        top_md = "## Top Discounts Today\n\n| Title | Current Price | Discount |\n|---|---:|---:|\n" + "\n".join(mkrow_discount(it) for it in top) + "\n\n"
    else:
        top_md = "## Top Discounts Today\n\n_No discounts today._\n\n"

    # Changes section
    if not changes:
        changes_md = "## Changes vs Previous Snapshot\n\n_No changes since previous run._\n"
    else:
        changes_md = (
            "## Changes vs Previous Snapshot\n\n"
            "| Title | Previous | Current |\n|---|---|---|\n" +
            "\n".join(mkrow_change(c) for c in sorted(changes, key=lambda x: x['title'].lower())) + "\n"
        )

    # Write report
    md_path.write_text(header + meta + top_md + changes_md, encoding="utf-8")

    # Roll current -> previous for next run
    if CUR.exists():
        shutil.copyfile(CUR, PREV)

    print(f"[diff_report] wrote {md_path} ({len(changes)} change(s); top_discounts={len(top)})")

if __name__ == "__main__":
    main()
