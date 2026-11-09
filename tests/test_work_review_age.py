"""Review age changes labels, never source facts, availability or review dates."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from static_pages import Research, work_freshness, work_review_label, work_terms_age


def listing(day="2026-10-25"):
    return {"id": "example.work.named", "company_id": "example", "route_kind": "named_listing", "status": "listed",
            "terms_checked_on": "2026-11-07", "last_link_check": {"date": "2026-11-08", "result": "reachable"},
            "editorial_review": {"approved_terms_receipt_id": "approved", "receipts": [{
                "id": "approved", "checked_on": day, "scope": "key_terms", "approved": True,
                "result": "readable", "approval_basis": "source_content_review"}]}}


class WorkReviewAgeTests(unittest.TestCase):
    def test_exact_fourteen_day_deadline_uses_approved_key_terms_only(self):
        route = listing()
        self.assertEqual(work_terms_age(route, "2026-11-07")["state"], "current")
        boundary = work_terms_age(route, "2026-11-08T23:59:59Z")
        self.assertEqual(boundary, {"state": "needs_recheck", "reviewed_on": "2026-10-25", "as_of": "2026-11-08", "age_days": 14, "label": "Needs recheck"})
        self.assertEqual(work_terms_age(route, "2026-11-09")["age_days"], 15)

    def test_failed_checks_and_new_pay_dates_do_not_refresh_full_terms(self):
        route = listing()
        route["last_link_check"] = {"date": "2026-11-08", "result": "blocked"}
        route["terms_checked_on"] = "2026-11-08"
        route["editorial_review"]["receipts"].append({"id": "failed-later", "checked_on": "2026-11-08", "scope": "key_terms", "approved": False, "result": "blocked", "approval_basis": "source_content_review"})
        before = copy.deepcopy(route)
        self.assertEqual(work_terms_age(route, "2026-11-08")["reviewed_on"], "2026-10-25")
        self.assertEqual(work_terms_age(route, "2026-11-08")["label"], "Needs recheck")
        self.assertEqual(route, before)
        self.assertEqual(work_freshness(route), "Terms checked 25 Oct 2026")

    def test_pay_only_and_page_review_are_not_claimed_as_a_full_terms_review(self):
        route = listing()
        route["editorial_review"]["receipts"][0]["scope"] = "field_review"
        self.assertEqual(work_terms_age(route, "2026-11-08")["label"], "Full terms review not recorded")
        self.assertEqual(work_terms_age(route, "2026-11-08")["reviewed_on"], None)
        self.assertEqual(work_freshness(route), "Pay terms reviewed 7 Nov 2026")
        route["editorial_review"] = {}
        self.assertEqual(work_terms_age(route, "2026-11-08")["state"], "not_reviewed")

    def test_programs_and_past_or_outside_records_are_not_aged_as_active_named_listings(self):
        for changed in ({"route_kind": "network_program"}, {"status": "historical"}, {"ai_data_work": False}, {"route_kind": "career_page"}):
            route = {**listing(), **changed}
            with self.subTest(changed=changed):
                self.assertEqual(work_terms_age(route, "2026-12-08")["state"], "not_applicable")
                self.assertEqual(work_terms_age(route, "2026-12-08")["label"], "")

    def test_publication_date_is_explicit_and_utc_normalized(self):
        self.assertEqual(work_terms_age(listing(), "2026-11-07T23:30:00-02:00")["as_of"], "2026-11-08")
        for value in (None, "", "2026-11-08T12:00:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                work_terms_age(listing(), value)
        self.assertEqual(work_terms_age(listing("2026-11-09"), "2026-11-08")["state"], "not_reviewed")

    def test_static_label_prints_its_snapshot_date_without_altering_the_record(self):
        data = json.loads((ROOT / "data/canonical.json").read_text())
        research = Research(data, publication_as_of="2026-11-08T23:00:00Z")
        route = listing()
        before = copy.deepcopy(route)
        self.assertEqual(work_review_label(research, route), "Terms checked 25 Oct 2026 · Needs recheck (as of 8 Nov 2026)")
        self.assertEqual(route, before)


if __name__ == "__main__":
    unittest.main()
