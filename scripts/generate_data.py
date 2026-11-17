"""Generate a SYNTHETIC catalog portfolio database (SQLite).

All data is fabricated for demonstration. Nothing here reflects any real company.

Planted for testing (see tests/test_planted.py):
  - 3 catalogs well below underwrite (70%, 82%, 88% of underwrite, flat)
  - 1 "watch" catalog: fine overall, but the last 3 months drop sharply
  - 1 exact duplicate row in the actuals table (data-quality issue)
"""
import os
import random
import sqlite3
import sys

SEED = 42
END_YEAR, END_MONTH = 2026, 10  # data runs through 2026-10

# (name, months_of_history, r0 monthly revenue at acquisition, monthly decay, factor)
# factor = actual / underwritten, held flat unless noted.
CATALOGS = [
    ("Neon Harbor", 24, 42000, 0.008, 1.04),
    ("Gold Line", 22, 30000, 0.010, 0.98),
    ("Midtown Static", 20, 55000, 0.006, 1.07),
    ("Paper Lanterns", 24, 18000, 0.012, 0.96),
    ("Velvet Static", 18, 25000, 0.009, 1.02),
    ("Low Tide Club", 16, 61000, 0.007, 0.70),   # PLANTED: 70%
    ("Crown Heights Vol. 2", 15, 33000, 0.010, 1.10),
    ("Sunday Drive", 23, 14000, 0.011, 0.99),
    ("Harbor & Vine", 12, 47000, 0.008, 0.82),   # PLANTED: 82%
    ("Ghost Notes", 21, 22000, 0.009, 1.01),
    ("Blue Hour", 19, 38000, 0.007, 0.88),       # PLANTED: 88%
    ("Parallel Lines", 14, 29000, 0.010, 1.03),
    ("Slow Burn", 17, 52000, 0.008, 0.97),       # PLANTED "watch": drops in last 3 months
    ("Marigold", 13, 16000, 0.012, 1.06),
    ("Static Bloom", 22, 27000, 0.009, 0.95),
]
WATCH_NAME = "Slow Burn"


def month_label(offset_from_end):
    """offset_from_end=0 -> END month; 1 -> the month before; ..."""
    idx = END_YEAR * 12 + (END_MONTH - 1) - offset_from_end
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def build(path):
    rng = random.Random(SEED)
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE catalogs (
            catalog_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            acquired_month TEXT NOT NULL,
            r0 REAL NOT NULL,          -- underwritten monthly revenue in month 0
            decay REAL NOT NULL        -- underwritten monthly decay rate
        );
        CREATE TABLE underwrite (
            catalog_id INTEGER NOT NULL,
            month TEXT NOT NULL,       -- 'YYYY-MM'
            projected REAL NOT NULL
        );
        CREATE TABLE actuals (         -- intentionally NO unique constraint
            catalog_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            revenue REAL NOT NULL
        );
        """
    )
    first_actual_row = None
    for i, (name, n_months, r0, decay, factor) in enumerate(CATALOGS, start=1):
        start_offset = n_months - 1
        cur.execute(
            "INSERT INTO catalogs VALUES (?,?,?,?,?)",
            (i, name, month_label(start_offset), r0, decay),
        )
        for t in range(n_months):
            offset = start_offset - t
            month = month_label(offset)
            projected = round(r0 * (1 - decay) ** t, 2)
            f = factor
            if name == WATCH_NAME and offset <= 2:
                f = 0.72  # sharp recent drop
            noise = rng.gauss(0, 0.015)
            actual = round(projected * f * (1 + noise), 2)
            cur.execute("INSERT INTO underwrite VALUES (?,?,?)", (i, month, projected))
            cur.execute("INSERT INTO actuals VALUES (?,?,?)", (i, month, actual))
            if i == 4 and t == 6:
                first_actual_row = (i, month, actual)
    # PLANTED data-quality issue: exact duplicate row for Paper Lanterns
    cur.execute("INSERT INTO actuals VALUES (?,?,?)", first_actual_row)
    con.commit()
    con.close()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "data", "portfolio.db"
    )
    build(out)
    print(f"Wrote {os.path.abspath(out)}")
