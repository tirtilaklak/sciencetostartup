"""Protect TaskUs reporting periods, service-line boundaries and source receipts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from business_health import load_business_health
from static_pages import selected_business_observation, value_text


class TaskUsQ3SupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads((ROOT / "data/canonical.json").read_text())
        cls.health = json.loads((ROOT / "data/business-health.json").read_text())
        cls.rows = {row["id"]: row for row in cls.health["observations"]}
        cls.checks = json.loads((ROOT / "data/fresh-source-checks.json").read_text())

    def test_quarter_and_year_to_date_stay_distinct_and_latest_selection_is_dated(self):
        quarter = self.rows["refresh.taskus.q3-2026-group-revenue"]
        ytd = self.rows["refresh.taskus.9m-2026-group-revenue"]
        self.assertEqual((quarter["value"], quarter["period"]["type"], quarter["period"]["start"]),
                         (314747000, "quarter", "2026-07-01"))
        self.assertEqual((ytd["value"], ytd["period"]["type"], ytd["period"]["start"]),
                         (929868000, "year_to_date", "2026-01-01"))
        for row in (quarter, ytd):
            self.assertEqual(row["period"]["end"], "2026-09-30")
            self.assertEqual((row["currency"], row["scope"], row["measure"]),
                             ("USD", "company", "period_revenue"))
        self.assertEqual(selected_business_observation(self.health, "taskus")["id"], ytd["id"])
        historical = self.rows["refresh.taskus.h1-2026-group-revenue"]
        self.assertEqual((historical["value"], historical["period"]["end"], historical["evidence_checked_on"]),
                         (615121000, "2026-06-30", "2026-10-28"))

    def test_ai_service_line_growth_and_trailing_revenue_keep_scope_and_lower_bound(self):
        growth = self.rows["refresh.taskus.q3-2026-ai-revenue-growth"]
        ttm = self.rows["refresh.taskus.september-2026-ai-ttm-revenue"]
        self.assertEqual((growth["measure"], growth["value"], growth["unit"], growth["scope"]),
                         ("revenue_growth_yoy", 27.7, "percent", "ai_data"))
        self.assertNotIn("currency", growth)
        self.assertEqual((ttm["measure"], ttm["value"], ttm["qualifier"], ttm["scope"]),
                         ("period_revenue", 250000000, "greater_than", "ai_data"))
        self.assertEqual((ttm["period"]["type"], ttm["period"]["start"], ttm["period"]["end"]),
                         ("trailing_year", "2025-10-01", "2026-09-30"))
        self.assertIn("more than", value_text(ttm).lower())

    def test_new_receipt_is_separate_from_the_original_schedule_receipt(self):
        source_id = "refresh.source.taskus-q3-2026"
        public = next(row for row in self.checks["entries"] if row["source_id"] == source_id)
        embedded = next(row for row in self.health["source_checks"]["entries"] if row["source_id"] == source_id)
        self.assertEqual(public, embedded)
        self.assertEqual((public["status"], public["http_status"], public["checked_on"], public["published_on"]),
                         ("content_checked", 200, "2026-11-16", "2026-11-04"))
        self.assertEqual(public["content_sha256"],
                         "81e9aec198a936e0018551b411ce4e6570184277081dfd821c1a0a882f9dd5f2")
        self.assertEqual(public["approval_basis"], "source_content_review")
        schedule = next(row for row in self.checks["entries"] if row["source_id"] == "taskus.refresh.q3-schedule")
        self.assertEqual(schedule["checked_on"], "2026-10-28")
        self.assertIn("No Q3 financial results are inferred.", schedule["note"])

    def test_loader_binds_new_reporting_periods_and_canonical_bytes_stay_frozen(self):
        self.assertEqual(load_business_health(ROOT / "data/business-health.json", self.canonical), self.health)
        bad = copy.deepcopy(self.health)
        next(row for row in bad["observations"] if row["id"] == "refresh.taskus.9m-2026-group-revenue")["period"]["type"] = "quarter"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad-period.json"
            path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "reporting basis differs"):
                load_business_health(path, self.canonical)
        self.assertEqual(hashlib.sha256((ROOT / "data/canonical.json").read_bytes()).hexdigest(),
                         "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")


if __name__ == "__main__":
    unittest.main()
