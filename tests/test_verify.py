"""Unit tests for verify.py portfolio and data quality metrics."""
import json
import os
import sqlite3
import tempfile
import unittest
import sys

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from verify import truth_portfolio, truth_data_quality, truth_catalog


class TestPortfolioMetrics(unittest.TestCase):
    def setUp(self):
        """Create a minimal test database."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.con = sqlite3.connect(self.db_path)
        self.con.execute("""
            CREATE TABLE catalogs (
                catalog_id INTEGER PRIMARY KEY,
                name TEXT,
                acquired_month TEXT,
                r0 REAL,
                decay REAL
            )
        """)
        self.con.execute("""
            CREATE TABLE underwrite (
                catalog_id INTEGER,
                month TEXT,
                projected REAL
            )
        """)
        self.con.execute("""
            CREATE TABLE actuals (
                catalog_id INTEGER,
                month TEXT,
                revenue REAL
            )
        """)
        self.con.commit()

    def tearDown(self):
        self.con.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_n_catalogs(self):
        """Test n_catalogs count."""
        self.con.execute("INSERT INTO catalogs VALUES (1, 'Cat A', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO catalogs VALUES (2, 'Cat B', '2024-02', 100, 0.1)")
        self.con.commit()

        metrics = truth_portfolio(self.con)
        self.assertEqual(metrics["n_catalogs"], 2)

    def test_n_below_underwrite(self):
        """Test n_below_underwrite flags catalogs with cumulative % < 90%."""
        # Catalog 1: 100 actual / 200 underwritten = 50% -> BELOW
        self.con.execute("INSERT INTO catalogs VALUES (1, 'Below Cat', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO underwrite VALUES (1, '2024-01', 100)")
        self.con.execute("INSERT INTO underwrite VALUES (1, '2024-02', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 50)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-02', 50)")

        # Catalog 2: 950 actual / 1000 underwritten = 95% -> OK
        self.con.execute("INSERT INTO catalogs VALUES (2, 'OK Cat', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO underwrite VALUES (2, '2024-01', 500)")
        self.con.execute("INSERT INTO underwrite VALUES (2, '2024-02', 500)")
        self.con.execute("INSERT INTO actuals VALUES (2, '2024-01', 475)")
        self.con.execute("INSERT INTO actuals VALUES (2, '2024-02', 475)")
        self.con.commit()

        metrics = truth_portfolio(self.con)
        self.assertEqual(metrics["n_below_underwrite"], 1)

    def test_n_watch(self):
        """Test n_watch flags catalogs with cumulative >= 90% but trailing 3M < 85%."""
        # Catalog 1: Cumulative 95%, trailing 3M 50% -> WATCH
        self.con.execute("INSERT INTO catalogs VALUES (1, 'Watch Cat', '2024-01', 100, 0.1)")
        # 3 months early strong, 3 months recent weak
        # Early: 300 actual / 300 underwritten
        # Recent: 150 actual / 300 underwritten (trailing 3M = 150/300 = 50%)
        # Total: 450 actual / 600 underwritten = 75% cumulative
        # Need cumulative >= 90%, so adjust:
        for i in range(1, 10):
            month = f'2024-{i:02d}'
            self.con.execute("INSERT INTO underwrite VALUES (1, ?, 100)", (month,))
        # Early months (1-6): 90 actual each = 540 actual
        # Recent months (7-9): 30 actual each = 90 actual
        # Total: 630/900 = 70% cumulative (still not 90%)
        # Let me use: early months higher underwrite, recent months lower
        # Month 1-3: 100 actual, 100 underwritten each = 300/300
        # Month 4-6: 150 actual, 100 underwritten each = 450/300
        # Month 7-9: 50 actual, 100 underwritten each = 150/300
        # Total: 900/900 = 100% cumulative, trailing 3M = 150/300 = 50% < 85%
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-02', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-03', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-04', 150)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-05', 150)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-06', 150)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-07', 50)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-08', 50)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-09', 50)")

        # Catalog 2: Cumulative 50% -> Should not be flagged for watch
        self.con.execute("INSERT INTO catalogs VALUES (2, 'Below Cat', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO underwrite VALUES (2, '2024-01', 200)")
        self.con.execute("INSERT INTO underwrite VALUES (2, '2024-02', 200)")
        self.con.execute("INSERT INTO actuals VALUES (2, '2024-01', 50)")
        self.con.execute("INSERT INTO actuals VALUES (2, '2024-02', 50)")
        self.con.commit()

        metrics = truth_portfolio(self.con)
        self.assertEqual(metrics["n_watch"], 1)

    def test_total_dollar_gap(self):
        """Test total_dollar_gap sum across all catalogs."""
        # Catalog 1: $100 actual - $200 underwritten = -$100
        self.con.execute("INSERT INTO catalogs VALUES (1, 'Below', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO underwrite VALUES (1, '2024-01', 200)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 100)")

        # Catalog 2: $300 actual - $200 underwritten = +$100
        self.con.execute("INSERT INTO catalogs VALUES (2, 'Above', '2024-01', 100, 0.1)")
        self.con.execute("INSERT INTO underwrite VALUES (2, '2024-01', 200)")
        self.con.execute("INSERT INTO actuals VALUES (2, '2024-01', 300)")
        self.con.commit()

        metrics = truth_portfolio(self.con)
        self.assertEqual(metrics["total_dollar_gap"], 0)  # -100 + 100 = 0

    def test_duplicate_rows_dropped(self):
        """Test duplicate_rows_dropped counts duplicates correctly."""
        # Insert 5 rows: 3 unique, 2 duplicates
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 100)")  # Exact duplicate
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-02', 200)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-02', 200)")  # Exact duplicate
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-03', 300)")
        self.con.commit()

        metrics = truth_data_quality(self.con)
        self.assertEqual(metrics["duplicate_rows_dropped"], 2)

    def test_no_duplicates(self):
        """Test duplicate_rows_dropped is 0 when all rows are unique."""
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-01', 100)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-02', 200)")
        self.con.execute("INSERT INTO actuals VALUES (1, '2024-03', 300)")
        self.con.commit()

        metrics = truth_data_quality(self.con)
        self.assertEqual(metrics["duplicate_rows_dropped"], 0)


if __name__ == "__main__":
    unittest.main()
