"""Independent verifier. Re-derives each cited figure straight from SQL.

Deliberately does NOT import underwrite_check.py, so a bug there cannot hide itself.

Usage:  python scripts/verify.py out/claims.json [--db data/portfolio.db]
claims.json: [{"catalog": "Low Tide Club", "metric": "pct_of_underwrite", "value": 70.1}, ...]
Metrics: pct_of_underwrite, trailing3_pct, dollar_gap, actual_total, underwritten_total,
         n_catalogs, n_below_underwrite, n_watch, total_dollar_gap, duplicate_rows_dropped
Exit code 0 = all PASS, 1 = at least one MISMATCH / unknown.
"""
import argparse
import json
import os
import sqlite3
import sys

TOL = {"pct_of_underwrite": 0.1, "trailing3_pct": 0.1,
       "dollar_gap": 1.0, "actual_total": 1.0, "underwritten_total": 1.0,
       "n_catalogs": 0.5, "n_below_underwrite": 0.5, "n_watch": 0.5,
       "total_dollar_gap": 1.0, "duplicate_rows_dropped": 0.5}


def truth_catalog(con, name):
    """Derive metrics for a specific catalog."""
    cid = con.execute("SELECT catalog_id FROM catalogs WHERE name=?", (name,)).fetchone()
    if not cid:
        return None
    cid = cid[0]
    # DISTINCT removes exact duplicate rows
    act = con.execute(
        "SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals WHERE catalog_id=?)",
        (cid,)).fetchone()[0]
    und = con.execute("SELECT SUM(projected) FROM underwrite WHERE catalog_id=?", (cid,)).fetchone()[0]
    last3 = [r[0] for r in con.execute(
        "SELECT month FROM underwrite WHERE catalog_id=? ORDER BY month DESC LIMIT 3", (cid,))]
    q = ",".join("?" * len(last3))
    a3 = con.execute(
        f"SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals "
        f"WHERE catalog_id=? AND month IN ({q}))", (cid, *last3)).fetchone()[0]
    u3 = con.execute(
        f"SELECT SUM(projected) FROM underwrite WHERE catalog_id=? AND month IN ({q})",
        (cid, *last3)).fetchone()[0]
    return {
        "actual_total": act, "underwritten_total": und,
        "pct_of_underwrite": 100 * act / und, "trailing3_pct": 100 * a3 / u3,
        "dollar_gap": act - und,
    }


def truth_portfolio(con):
    """Derive portfolio-level metrics using thresholds from assumptions.md."""
    # n_catalogs: count rows in catalogs table
    n_catalogs = con.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0]

    # n_below_underwrite: cumulative % < 90%
    n_below = 0
    for cid, in con.execute("SELECT catalog_id FROM catalogs"):
        act = con.execute(
            "SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals WHERE catalog_id=?)",
            (cid,)).fetchone()[0]
        und = con.execute("SELECT SUM(projected) FROM underwrite WHERE catalog_id=?", (cid,)).fetchone()[0]
        if act and und:
            pct = 100 * act / und
            if pct < 90:
                n_below += 1

    # n_watch: trailing 3-month % < 85% AND cumulative >= 90%
    n_watch = 0
    for cid, in con.execute("SELECT catalog_id FROM catalogs"):
        act = con.execute(
            "SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals WHERE catalog_id=?)",
            (cid,)).fetchone()[0]
        und = con.execute("SELECT SUM(projected) FROM underwrite WHERE catalog_id=?", (cid,)).fetchone()[0]
        if act and und:
            pct = 100 * act / und
            if pct >= 90:  # Only consider if cumulative >= 90%
                last3 = [r[0] for r in con.execute(
                    "SELECT month FROM underwrite WHERE catalog_id=? ORDER BY month DESC LIMIT 3", (cid,))]
                if last3:
                    q = ",".join("?" * len(last3))
                    a3 = con.execute(
                        f"SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals "
                        f"WHERE catalog_id=? AND month IN ({q}))", (cid, *last3)).fetchone()[0]
                    u3 = con.execute(
                        f"SELECT SUM(projected) FROM underwrite WHERE catalog_id=? AND month IN ({q})",
                        (cid, *last3)).fetchone()[0]
                    if a3 and u3:
                        t3_pct = 100 * a3 / u3
                        if t3_pct < 85:
                            n_watch += 1

    # total_dollar_gap: sum of (actual - underwritten) for all catalogs
    total_gap = con.execute(
        """SELECT SUM(act - und) FROM (
            SELECT catalog_id,
                   (SELECT SUM(revenue) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals a WHERE a.catalog_id = c.catalog_id)) as act,
                   (SELECT SUM(projected) FROM underwrite u WHERE u.catalog_id = c.catalog_id) as und
            FROM catalogs c
        )"""
    ).fetchone()[0]
    if total_gap is None:
        total_gap = 0

    return {
        "n_catalogs": n_catalogs,
        "n_below_underwrite": n_below,
        "n_watch": n_watch,
        "total_dollar_gap": total_gap,
    }


def truth_data_quality(con):
    """Derive data quality metrics."""
    # Count total rows in actuals
    total_rows = con.execute("SELECT COUNT(*) FROM actuals").fetchone()[0]
    # Count distinct (catalog_id, month, revenue) rows
    distinct_rows = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT catalog_id, month, revenue FROM actuals)"
    ).fetchone()[0]
    # Duplicates dropped = total - distinct
    duplicates = total_rows - distinct_rows

    return {"duplicate_rows_dropped": duplicates}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("claims")
    ap.add_argument("--db", default=os.path.join(here, "..", "data", "portfolio.db"))
    args = ap.parse_args()
    claims = json.load(open(args.claims))
    con = sqlite3.connect(args.db)
    bad = 0
    for c in claims:
        # Check metric is known
        if c["metric"] not in TOL:
            print(f"UNKNOWN   {c}")
            bad += 1
            continue

        # Get truth value based on catalog
        if c["catalog"] == "Portfolio":
            t = truth_portfolio(con)
        elif c["catalog"] == "Data Quality":
            t = truth_data_quality(con)
        else:
            t = truth_catalog(con, c["catalog"])

        if t is None:
            print(f"UNKNOWN   {c}")
            bad += 1
            continue

        if c["metric"] not in t:
            print(f"UNKNOWN   {c}")
            bad += 1
            continue

        actual = t[c["metric"]]
        ok = abs(actual - c["value"]) <= TOL[c["metric"]]
        tag = "PASS    " if ok else "MISMATCH"
        print(f"{tag}  {c['catalog']:<22} {c['metric']:<20} claimed={c['value']:<12} verified={actual:.1f}")
        bad += (not ok)
    print(f"\n{len(claims) - bad}/{len(claims)} figures verified")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
