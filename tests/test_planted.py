"""Proves the tool catches what we planted. Run:  python -m unittest discover -s tests -v"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_data  # noqa: E402
import underwrite_check  # noqa: E402

DB = os.path.join(tempfile.gettempdir(), "uw_test.db")


def setUpModule():
    generate_data.build(DB)


class PlantedErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = underwrite_check.analyze(DB)
        cls.by_name = {r["name"]: r for r in cls.res["catalogs"]}

    def test_three_underperformers_flagged(self):
        flagged = {r["name"] for r in self.res["catalogs"] if r["status"] == "BELOW_UNDERWRITE"}
        self.assertEqual(flagged, {"Low Tide Club", "Harbor & Vine", "Blue Hour"})

    def test_underperformer_levels(self):
        for name, target in [("Low Tide Club", 70), ("Harbor & Vine", 82), ("Blue Hour", 88)]:
            self.assertAlmostEqual(self.by_name[name]["pct_of_underwrite"], target, delta=1.5)

    def test_watch_catalog(self):
        self.assertEqual(self.by_name["Slow Burn"]["status"], "WATCH")

    def test_no_false_positives(self):
        ok = [r for r in self.res["catalogs"] if r["status"] == "OK"]
        self.assertEqual(len(ok), 11)

    def test_duplicate_row_detected(self):
        dups = self.res["data_quality"]["duplicate_rows_dropped"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["catalog"], "Paper Lanterns")


class CheckerCatchesCorruption(unittest.TestCase):
    def _run(self, claims):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(claims, f)
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "verify.py"), f.name, "--db", DB],
            capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_correct_figures_pass(self):
        res = underwrite_check.analyze(DB)
        r = next(c for c in res["catalogs"] if c["name"] == "Low Tide Club")
        code, _ = self._run([
            {"catalog": "Low Tide Club", "metric": "pct_of_underwrite", "value": r["pct_of_underwrite"]},
            {"catalog": "Low Tide Club", "metric": "dollar_gap", "value": r["dollar_gap"]},
        ])
        self.assertEqual(code, 0)

    def test_corrupted_figure_caught(self):
        code, out = self._run([
            {"catalog": "Low Tide Club", "metric": "pct_of_underwrite", "value": 79.0},  # true ~70
        ])
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH", out)


if __name__ == "__main__":
    unittest.main()
