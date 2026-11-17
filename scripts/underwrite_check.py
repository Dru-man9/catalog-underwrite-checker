"""Compute actual vs. underwritten performance per catalog. Prints JSON (or a table).

This script does ALL the math. The agent interprets; it never computes.

Rules (see assumptions.md):
  - exact duplicate (catalog_id, month, revenue) rows are dropped and reported
  - status = BELOW_UNDERWRITE if cumulative % of underwrite < threshold
  - status = WATCH if cumulative is fine but trailing-3-month % < watch threshold
"""
import argparse
import json
import os
import sqlite3
from collections import defaultdict

BELOW_THRESHOLD = 90.0   # cumulative % of underwrite
WATCH_THRESHOLD = 85.0   # trailing 3-month % of underwrite


def load(db):
    con = sqlite3.connect(db)
    cats = {r[0]: r[1] for r in con.execute("SELECT catalog_id, name FROM catalogs")}
    proj = defaultdict(dict)
    for cid, month, p in con.execute("SELECT catalog_id, month, projected FROM underwrite"):
        proj[cid][month] = p
    seen, actual, dups = set(), defaultdict(dict), []
    for cid, month, rev in con.execute("SELECT catalog_id, month, revenue FROM actuals ORDER BY rowid"):
        key = (cid, month, rev)
        if key in seen:
            dups.append({"catalog_id": cid, "catalog": cats[cid], "month": month, "revenue": rev})
            continue
        seen.add(key)
        actual[cid][month] = actual[cid].get(month, 0.0) + rev
    con.close()
    return cats, proj, actual, dups


def analyze(db):
    cats, proj, actual, dups = load(db)
    rows = []
    for cid, name in cats.items():
        months = sorted(proj[cid])
        act_total = sum(actual[cid].get(m, 0.0) for m in months)
        und_total = sum(proj[cid][m] for m in months)
        last3 = months[-3:]
        a3 = sum(actual[cid].get(m, 0.0) for m in last3)
        u3 = sum(proj[cid][m] for m in last3)
        pct = 100.0 * act_total / und_total
        pct3 = 100.0 * a3 / u3
        if pct < BELOW_THRESHOLD:
            status = "BELOW_UNDERWRITE"
        elif pct3 < WATCH_THRESHOLD:
            status = "WATCH"
        else:
            status = "OK"
        rows.append({
            "catalog_id": cid, "name": name, "months": len(months),
            "actual_total": round(act_total), "underwritten_total": round(und_total),
            "pct_of_underwrite": round(pct, 1), "trailing3_pct": round(pct3, 1),
            "dollar_gap": round(act_total - und_total), "status": status,
        })
    rows.sort(key=lambda r: r["dollar_gap"])
    return {
        "as_of": max(max(m) for m in (proj[c] for c in proj)),
        "thresholds": {"below_underwrite_pct": BELOW_THRESHOLD, "watch_trailing3_pct": WATCH_THRESHOLD},
        "data_quality": {"duplicate_rows_dropped": dups},
        "catalogs": rows,
        "summary": {
            "n_catalogs": len(rows),
            "n_below_underwrite": sum(r["status"] == "BELOW_UNDERWRITE" for r in rows),
            "n_watch": sum(r["status"] == "WATCH" for r in rows),
            "total_dollar_gap": sum(r["dollar_gap"] for r in rows),
        },
    }


def table(res):
    lines = ["| Catalog | Months | % of UW | Trailing 3M % | $ Gap | Status |", "|---|---|---|---|---|---|"]
    for r in res["catalogs"]:
        lines.append(f"| {r['name']} | {r['months']} | {r['pct_of_underwrite']} | {r['trailing3_pct']} | {r['dollar_gap']:,} | {r['status']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(here, "..", "data", "portfolio.db"))
    ap.add_argument("--table", action="store_true", help="print a markdown table instead of JSON")
    args = ap.parse_args()
    res = analyze(args.db)
    print(table(res) if args.table else json.dumps(res, indent=2))
