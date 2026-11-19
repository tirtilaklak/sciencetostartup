"""Editorial truth, provenance and candidate-only monitoring contracts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from editorial_work import (EditorialValidationError, FIELD_NAMES, editorial_counts,
                            load_editorial_release, prepare_editorial_release, validate_editorial_release)
from check_work_sources import check_route, source_summary


class EditorialWorkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = json.loads((ROOT / "data/work-routes.json").read_text())
        cls.release = json.loads((ROOT / "data/editorial-release.json").read_text())
        cls.canonical = json.loads((ROOT / "data/canonical.json").read_text())
        cls.routes = {row["id"]: row for row in cls.work["routes"]}

    def validate(self, work=None, release=None, **kwargs):
        return validate_editorial_release(work or self.work, release or self.release, self.canonical, **kwargs)

    def test_approved_release_binds_unchanged_canonical_and_work_bytes(self):
        release = load_editorial_release(ROOT / "data/editorial-release.json", self.work, self.canonical)
        self.assertEqual(release["canonical_dataset_version"], "2.5.0")
        self.assertEqual(release["canonical_sha256"], "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")
        with self.assertRaisesRegex(EditorialValidationError, "canonical bytes changed"):
            self.validate(canonical_sha256="0" * 64)
        with self.assertRaisesRegex(EditorialValidationError, "sidecar differs"):
            self.validate(work_sha256="0" * 64)

    def test_all_records_have_explicit_states_without_blanket_field_dates(self):
        self.assertEqual(len(self.work["routes"]), 135)
        for row in self.work["routes"]:
            self.assertEqual(set(row["field_reviews"]), FIELD_NAMES, row["id"])
            for field in row["field_reviews"].values():
                if field["state"] == "not_researched":
                    self.assertIsNone(field["reviewed_on"])
                    self.assertEqual(field["basis"], "not_reviewed")
        # The old research establishes a recorded value, not a new field review.
        sample = self.routes["afterquery.work.product-manager"]
        self.assertEqual(sample["field_reviews"]["location"]["state"], "sourced")
        self.assertIsNone(sample["field_reviews"]["location"]["reviewed_on"])
        self.assertEqual(sample["field_reviews"]["pay"]["reviewed_on"], "2026-10-28")

    def test_counts_are_record_types_not_open_job_claims(self):
        counts = editorial_counts(self.work)
        self.assertEqual(counts, self.release["counts"])
        self.assertEqual(counts["work_routes"], counts["named_listings"] + counts["networks_programs"])
        self.assertEqual(counts["records"], counts["work_routes"] + counts["career_pages"] + counts["past_other_records"] + counts["other_company_jobs"])
        self.assertNotIn("open_jobs", counts)
        self.assertEqual(self.routes["surge_ai.work.research-fellowship"]["route_kind"], "named_listing")
        self.assertEqual(self.routes["surge_ai.work.research-fellowship"]["status"], "program")
        for rid in ["scale_ai.work.remotasks", "snorkel_ai.work.terminus-training", "abundant_ai.work.research-product-manager"]:
            self.assertEqual(self.routes[rid]["route_kind"], "other_record")

    def test_five_mixed_arrangements_keep_both_published_possibilities(self):
        for rid in ["bespoke_labs.work.mts-post-training", "aixi.work.research-fellowship",
                    "abundant_ai.work.research-product-manager", "trajectory_labs_pbc.work.safety-careers",
                    "elorian.work.model-safety"]:
            with self.subTest(route=rid):
                self.assertTrue({"remote", "onsite"} <= set(self.routes[rid]["arrangements"]))
        self.assertEqual(self.routes["bespoke_labs.work.fulfillment-operations-associate"]["arrangements"], ["remote"])
        self.assertEqual(self.routes["afterquery.work.product-manager"]["arrangements"], [])

    def test_task_equivalents_and_mixed_pay_are_not_actual_hourly_payment(self):
        for rid in ["toloka.work.mindrift-code", "toloka.work.cad-simulation", "labelbox.work.mechanical-engineering", "terac.work.finance-experts"]:
            self.assertFalse(self.routes[rid]["pay_terms"]["hourly_comparable"], rid)
        self.assertEqual(self.routes["toloka.work.mindrift-code"]["pay_terms"]["unit"], "task")
        self.assertEqual(self.routes["toloka.work.cad-simulation"]["pay_terms"]["unit"], "hour_equivalent")
        self.assertTrue(self.routes["appen.work.sage-media"]["pay_terms"]["hourly_comparable"])
        self.assertEqual(self.routes["afterquery.work.research-scholar"]["engagement_type"], "unknown")
        self.assertEqual(self.routes["afterquery.work.technical-content-writer-contract"]["engagement_type"], "contract")

    def test_sage_has_actual_source_receipt_and_all_binding_conditions(self):
        sage = self.routes["appen.work.sage-media"]
        selected = next(item for item in sage["editorial_review"]["receipts"]
                        if item["id"] == sage["editorial_review"]["approved_terms_receipt_id"])
        self.assertTrue(selected["approved"])
        self.assertEqual(selected["approval_basis"], "source_content_review")
        self.assertEqual(selected["reviewer"], "Codex source review")
        self.assertEqual(selected["checked_on"], "2026-11-08")
        self.assertLessEqual(selected["checked_on"], self.release["as_of"])
        self.assertRegex(selected["response_sha256"], r"^[a-f0-9]{64}$")
        evidence = " ".join(str(item) for item in selected["evidence"])
        for term in ["$15", "United States", "MacBook Pro", "qualification tests", "identity"]:
            self.assertIn(term, evidence)
        self.assertEqual(sage["field_reviews"]["duration"]["state"], "source_not_stated")
        self.assertEqual(sage["terms_checked_on"], "2026-10-28", "retain the original batch receipt")
        self.assertEqual(sage["last_link_check"]["date"], "2026-10-28")

    def test_calibration_receipts_do_not_invent_successful_field_reviews(self):
        self.assertEqual(len(self.release["calibration_route_ids"]), 12)
        row = self.routes["turing.work.expert-network"]
        attempts = row["editorial_review"]["receipts"]
        self.assertEqual(attempts[-1]["result"], "unreadable_shell")
        self.assertFalse(attempts[-1]["approved"])
        self.assertNotIn("approved_terms_receipt_id", row["editorial_review"])
        self.assertEqual(row["status"], "program")
        self.assertEqual(row["last_link_check"]["date"], "2026-10-28")

    def test_invalid_provenance_cannot_pass_as_approved_content(self):
        work = copy.deepcopy(self.work)
        sage = next(row for row in work["routes"] if row["id"] == "appen.work.sage-media")
        approved = next(item for item in sage["editorial_review"]["receipts"] if item.get("approved"))
        approved["approval_basis"] = "automated_retrieval"
        with self.assertRaisesRegex(EditorialValidationError, "retrieval cannot approve facts"):
            self.validate(work=work)
        work = copy.deepcopy(self.work)
        work["routes"][0]["field_reviews"]["duration"] = {
            "state": "not_researched", "reviewed_on": self.release["as_of"], "source_ids": [], "basis": "not_reviewed"}
        with self.assertRaisesRegex(EditorialValidationError, "unresearched field cannot claim"):
            self.validate(work=work)

    def test_monitoring_200_challenge_never_changes_facts_or_claims_closure(self):
        route = copy.deepcopy(self.routes["turing.work.expert-network"])
        before = copy.deepcopy(route)
        body = b'<html><body>Request unsuccessful. Incapsula incident ID</body></html>'
        receipt = check_route(route, "2026-11-08T22:00:00Z", fetcher=lambda url: (200, url, body, False))
        self.assertEqual(receipt["result"], "blocked")
        self.assertFalse(receipt["approved"])
        self.assertTrue(receipt["editorial_review_required"])
        self.assertEqual(route, before)
        self.assertNotIn("closed", receipt.values())
        repeat = check_route(route, "2026-11-09T22:00:00Z", previous=receipt, fetcher=lambda url: (200, url, body, False))
        self.assertEqual(repeat["candidate_reason"], "unchanged_failure")
        self.assertFalse(repeat["approved"])

    def test_monitoring_uses_job_document_instead_of_rotating_chrome(self):
        job = {"@type": "JobPosting", "title": "Engineer", "description": "Review code", "employmentType": "CONTRACTOR"}
        def page(chrome):
            return ('<html><body>' + chrome + '<script type="application/ld+json">' + json.dumps(job) + '</script></body></html>').encode()
        first = source_summary(page("13 hired recently"))
        second = source_summary(page("14 hired recently"))
        self.assertEqual(first["stable_content_sha256"], second["stable_content_sha256"])
        self.assertTrue(first["readable"])
        receipt = check_route({"id": "fixture", "url": "https://example.test/job", "route_kind": "named_listing"},
                              "2026-11-08T22:00:00Z", previous=first,
                              fetcher=lambda url: (200, url, page("14 hired recently"), False))
        self.assertEqual(receipt["candidate_reason"], "unchanged")
        self.assertFalse(receipt["approved"])

    def test_publication_preparation_is_reproducible_and_does_not_refresh_facts(self):
        original_work = copy.deepcopy(self.work)
        original_release = copy.deepcopy(self.release)
        staged_day = (date.fromisoformat(self.release["as_of"]) + timedelta(days=1)).isoformat()
        arguments = {"release_id": staged_day + ".1", "publication_as_of": staged_day + "T12:00:00Z",
                     "canonical_sha256": self.release["canonical_sha256"]}
        first = prepare_editorial_release(self.work, self.release, self.canonical, **arguments)
        second = prepare_editorial_release(self.work, self.release, self.canonical, **arguments)
        self.assertEqual(first, second)
        self.assertEqual(self.work, original_work)
        self.assertEqual(self.release, original_release)
        for before, after in zip(self.work["routes"], first[0]["routes"]):
            self.assertEqual(before["field_reviews"], after["field_reviews"])
            self.assertEqual(before["editorial_review"]["classified_on"], after["editorial_review"]["classified_on"])
            self.assertEqual(before["editorial_review"]["receipts"], after["editorial_review"]["receipts"])
        self.assertEqual(first[1]["canonical_sha256"], self.release["canonical_sha256"])
        with self.assertRaisesRegex(EditorialValidationError, "candidates cannot be promoted"):
            prepare_editorial_release({"status": "candidates_only", "receipts": []}, self.release, self.canonical, **arguments)

    def test_historical_work_checks_remain_a_complete_distinct_batch(self):
        self.assertEqual(self.work["verification"]["checked_on"], "2026-10-28")
        self.assertEqual(self.work["verification"]["routes_link_checked"], 135)
        for row in self.work["routes"]:
            self.assertEqual(row["last_link_check"]["date"], "2026-10-28")

    def test_real_job_security_language_is_not_a_bot_challenge(self):
        body = ('<html><body><h1>Security Engineer</h1>' +
                '<p>Evaluate security challenges, CAPTCHA robustness and human review workflows. ' * 8 +
                '</p></body></html>').encode()
        self.assertTrue(source_summary(body)["readable"])
        self.assertFalse(source_summary(body)["challenge"])

    def test_missing_role_pages_keep_old_terms_and_offer_a_separate_board(self):
        for rid in ["afterquery.work.senior-software-engineer-security-infrastructure", "terac.work.ml-scenarios"]:
            row = self.routes[rid]
            self.assertEqual(row["status"], "historical")
            self.assertEqual(row["editorial_review"]["previous_values"]["status"], "listed")
            self.assertEqual(row["editorial_review"]["disposition"]["state"], "historical_page_unavailable")
            self.assertTrue(any(item.get("http_status") == 404 for item in row["editorial_review"]["receipts"]))
            self.assertTrue(row["pay_label"])
            self.assertEqual(row["last_link_check"]["date"], "2026-10-28")
            self.assertNotEqual(row["url"], row["editorial_review"]["alternative_destination"]["url"])
            self.assertIn("not a claim that the employer stopped hiring", row["availability_note"])
            candidate = check_route(row, "2026-11-09T12:00:00Z", fetcher=lambda url: (404, url, b"Job not found", False))
            self.assertEqual(candidate["priority"], "low", "archived destinations must not displace actionable reviews")

    def test_review_timestamp_cannot_create_a_false_future_promotion(self):
        work = copy.deepcopy(self.work)
        sage = next(row for row in work["routes"] if row["id"] == "appen.work.sage-media")
        receipt = next(item for item in sage["editorial_review"]["receipts"] if item.get("approved"))
        future_day = (date.fromisoformat(self.release["as_of"]) + timedelta(days=1)).isoformat()
        receipt["checked_at"] = future_day + "T12:00:00Z"
        with self.assertRaisesRegex(EditorialValidationError, "timestamp differs"):
            self.validate(work=work)

    def later_pay_review(self):
        """SYNTHETIC future field review; never a source check or published data."""
        work = copy.deepcopy(self.work)
        row = next(r for r in work["routes"] if r["id"] == "mercor.work.expert-network")
        previous = copy.deepcopy(row["editorial_review"]["receipts"])
        old_terms_id = row["editorial_review"]["approved_terms_receipt_id"]
        day = (date.fromisoformat(self.release["as_of"]) + timedelta(days=1)).isoformat()
        source_id = row["id"] + ".synthetic-pay-source"
        row["sources"].append({"id": source_id, "url": "https://example.test/synthetic-pay",
                               "title": "SYNTHETIC test-only source"})
        receipt = {"id": row["id"] + ".synthetic-pay-review", "source_id": source_id,
                   "scope": "field_review", "result": "readable", "checked_on": day,
                   "checked_at": day + "T10:00:00Z", "response_sha256": "a" * 64,
                   "approved": True, "approval_basis": "source_content_review",
                   "reviewer": "SYNTHETIC test reviewer", "reviewed_fields": ["pay"],
                   "evidence": ["SYNTHETIC test-only evidence; no factual source assertion."]}
        row["editorial_review"]["receipts"].append(receipt)
        row["field_reviews"]["pay"] = {"state": "sourced", "basis": "direct_source",
                                       "reviewed_on": day, "source_ids": [source_id]}
        release = copy.deepcopy(self.release)
        release.update(as_of=day, release_id=day + ".1", publication_as_of=day + "T12:00:00Z")
        for route in work["routes"]:
            route["editorial_review"]["release_id"] = release["release_id"]
        return work, release, row, receipt, previous, old_terms_id

    def test_later_field_review_preserves_every_historical_approval_and_terms_clock(self):
        work, release, row, receipt, previous, old_terms_id = self.later_pay_review()
        self.validate(work, release)
        self.assertEqual(row["editorial_review"]["receipts"][:-1], previous)
        self.assertEqual(row["editorial_review"]["approved_terms_receipt_id"], old_terms_id)
        terms = next(r for r in row["editorial_review"]["receipts"] if r["id"] == old_terms_id)
        self.assertEqual(terms["checked_on"], "2026-11-08")
        self.assertEqual(set(terms["reviewed_fields"]), FIELD_NAMES)
        for field in FIELD_NAMES - {"pay"}:
            self.assertEqual(row["field_reviews"][field], self.routes[row["id"]]["field_reviews"][field])

    def test_current_direct_fields_require_exact_approved_source_date_and_field(self):
        def wrong_date(row, receipt):
            row["field_reviews"]["pay"]["reviewed_on"] = "2026-11-07"
        def wrong_source(row, receipt):
            row["field_reviews"]["pay"]["source_ids"] = [row["sources"][0]["id"]]
        def wrong_field(row, receipt):
            receipt["reviewed_fields"] = ["destination"]
        def unapproved(row, receipt):
            receipt["approved"] = False
        def retrieval_only(row, receipt):
            receipt.update(scope="retrieval", approved=False)
        def unreadable(row, receipt):
            receipt.update(result="unreadable_shell", approved=False)
        def extra_unreviewed_source(row, receipt):
            row["field_reviews"]["pay"]["source_ids"].append(row["sources"][0]["id"])
        for change in [wrong_date, wrong_source, wrong_field, unapproved, retrieval_only,
                       unreadable, extra_unreviewed_source]:
            with self.subTest(change=change.__name__):
                work, release, row, receipt, *_ = self.later_pay_review()
                change(row, receipt)
                with self.assertRaisesRegex(EditorialValidationError, "current direct-source field lacks"):
                    self.validate(work, release)

    def test_public_receipts_and_inline_sources_cannot_leak_private_capture_locations(self):
        for private in [{"raw_path": "capture.html"}, {"local_path": "capture.pdf"},
                        {"extracted_text_path": "capture.txt"},
                        {"structured_evidence": {"path": "/workspace/scratch/private/capture.json"}},
                        {"evidence": ["See (/workspace/scratch/private/capture.html) for text."]}]:
            for target in ["receipt", "source"]:
                with self.subTest(private=private, target=target):
                    work, release, row, receipt, *_ = self.later_pay_review()
                    (receipt if target == "receipt" else row["sources"][-1]).update(private)
                    with self.assertRaisesRegex(EditorialValidationError, "private capture"):
                        self.validate(work, release)

    def test_invalid_clock_and_post_publication_receipts_are_rejected(self):
        for value, message in [("T25:00:00Z", "invalid receipt timestamp"),
                               ("T12:00:01Z", "follows publication")]:
            with self.subTest(value=value):
                work, release, row, receipt, *_ = self.later_pay_review()
                receipt["checked_at"] = receipt["checked_on"] + value
                with self.assertRaisesRegex(EditorialValidationError, message):
                    self.validate(work, release)

    def test_capture_time_cannot_be_after_review_or_use_an_ambiguous_format(self):
        for value, message in [("T10:00:01Z", "capture follows review"),
                               ("T10:00:00+00:00", "explicit UTC timestamp"),
                               ("T25:00:00Z", "invalid retrieval timestamp")]:
            with self.subTest(value=value):
                work, release, row, receipt, *_ = self.later_pay_review()
                receipt["retrieved_at"] = receipt["checked_on"] + value
                with self.assertRaisesRegex(EditorialValidationError, message):
                    self.validate(work, release)


if __name__ == "__main__":
    unittest.main()
