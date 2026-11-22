"""Pay, eligibility and court-status corrections keep their precise evidence scope."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from editorial_work import editorial_counts, validate_editorial_release
from observatory import validate_company_events
from presentation import work_uncertain


def prior_values(route, correction_id):
    return next(correction["previous_values"] for correction in route["editorial_review"]["correction_history"]
                if correction["id"] == f"{route['id']}.{correction_id}")


class ProvenanceCorrectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = json.loads((ROOT / "data/work-routes.json").read_text())
        cls.routes = {row["id"]: row for row in cls.work["routes"]}
        cls.events = json.loads((ROOT / "data/company-events.json").read_text())
        cls.release = json.loads((ROOT / "data/editorial-release.json").read_text())
        cls.canonical = json.loads((ROOT / "data/canonical.json").read_text())

    def test_release_binds_exact_work_bytes_and_unchanged_frozen_canonical(self):
        self.assertEqual(hashlib.sha256((ROOT / "data/canonical.json").read_bytes()).hexdigest(),
                         "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")
        self.assertEqual(self.release["release_id"], "2026-11-22.6")
        self.assertEqual(self.release["as_of"], "2026-11-22")
        self.assertEqual(self.release["work_routes_sha256"],
                         hashlib.sha256((ROOT / "data/work-routes.json").read_bytes()).hexdigest())
        validate_editorial_release(self.work, self.release, self.canonical)
        counts = editorial_counts(self.work)
        self.assertEqual(counts["records"], 135)
        self.assertEqual(counts["work_routes"], 70)

    def test_surge_fellowship_application_and_unstated_location_have_exact_source(self):
        row = self.routes["surge_ai.work.research-fellowship"]
        self.assertEqual(row["geography"], "Location not published")
        self.assertEqual(row["arrangements"], [])
        self.assertEqual(row["route_kind"], "named_listing")
        self.assertEqual(row["status"], "program")
        self.assertEqual(row["pay_label"], "Hourly; rate not published")
        self.assertFalse(row["numeric_pay"])
        self.assertFalse(row["pay_terms"]["hourly_comparable"])
        directions = "Email a CV or relevant work samples using the address on the official fellowship page."
        self.assertEqual(row["availability_note"], directions)
        review = row["editorial_review"]
        self.assertNotIn("approved_terms_receipt_id", review)
        receipt_id = f"{row['id']}.application-location-2026-11-22.review"
        receipt = next(item for item in review["receipts"] if item["id"] == receipt_id)
        self.assertTrue(receipt["approved"])
        self.assertEqual(receipt["scope"], "field_review")
        self.assertEqual(set(receipt["reviewed_fields"]), {"destination", "location"})
        self.assertEqual(receipt["approval_basis"], "source_content_review")
        self.assertEqual(receipt["response_sha256"], "afa14a64527ff4377159d5941c13cedcce818a33df4287f194640e8060b31926")
        source = next(item for item in row["sources"] if item["id"] == receipt["source_id"])
        self.assertEqual(source["url"], "https://surgehq.ai/fellowship")
        self.assertEqual(source["accessed_on"], receipt["checked_on"])
        self.assertEqual(review["actions"], [{
            "label": "Read application instructions",
            "url": source["url"],
            "source_id": source["id"],
            "purpose": "application",
        }])
        for field, state in (("destination", "sourced"), ("location", "source_not_stated")):
            binding = row["field_reviews"][field]
            self.assertEqual(binding["state"], state)
            self.assertEqual(binding["basis"], "direct_source")
            self.assertEqual(binding["source_ids"], [source["id"]])
            self.assertEqual(binding["reviewed_on"], receipt["checked_on"])
        self.assertEqual(prior_values(row, "application-location-2026-11-22.correction")["geography"], "Project-specific")
        self.assertNotRegex(json.dumps(row), r"mailto:|[\w.+-]+@surgehq\.ai")

    def test_retained_quote_normalization_is_not_a_new_source_check(self):
        for rid, currency in [("bespoke_labs.work.mts-post-training", "USD"),
                              ("scale_ai.work.outlier-statistics", "USD"),
                              ("bespoke_labs.work.fulfillment-operations-associate", "USD")]:
            with self.subTest(route=rid):
                row = self.routes[rid]
                self.assertIn(currency, row["source_quote"])
                self.assertEqual(row["pay_terms"]["currency"], currency)
                self.assertEqual(row["field_reviews"]["pay"]["basis"], "stored_evidence")
                self.assertEqual(row["field_reviews"]["pay"]["reviewed_on"], "2026-10-28")
                self.assertEqual(row["terms_checked_on"], "2026-10-28")
                self.assertTrue(all(r["checked_on"] != "2026-11-18"
                                    for r in row["editorial_review"]["receipts"]))
        mts = self.routes["bespoke_labs.work.mts-post-training"]
        self.assertEqual(mts["pay_terms"]["unit"], "year")
        self.assertEqual(mts["pay_basis"], mts["pay_terms"]["basis"])
        self.assertFalse(mts["pay_terms"]["hourly_comparable"])
        ooak = self.routes["ooak.work.data-quality-specialist"]
        previous = prior_values(ooak, "employer-listing-2026-11-22.correction")
        self.assertIn("EUR", previous["source_quote"])
        self.assertEqual(previous["pay_terms"]["currency"], "EUR")
        self.assertEqual(previous["field_reviews"]["pay"]["basis"], "stored_evidence")
        self.assertEqual(previous["field_reviews"]["pay"]["reviewed_on"], "2026-10-28")
        self.assertEqual(ooak["terms_checked_on"], "2026-10-28")

    def test_ooak_exact_employer_listing_preserves_the_original_and_application_checks(self):
        row = self.routes["ooak.work.data-quality-specialist"]
        employer_url = "https://ooakdata.com/careers?job_id=114405#job"
        original_url = "https://www.ycombinator.com/companies/ooak-data/jobs/Gr7Gc1x-data-quality-specialist"
        self.assertEqual(row["status"], "listed")
        self.assertTrue(row["listed_on_current_company_board"])
        self.assertEqual(row["availability_label"], "Application access unconfirmed")
        self.assertTrue(work_uncertain(row))
        self.assertEqual(row["url"], employer_url)
        self.assertEqual(row["research_record"]["route"]["url"], original_url)
        self.assertEqual(row["pay_label"], "€65K–€80K / year")
        self.assertIn("earlier YC listing", row["pay_terms"]["note"])
        self.assertEqual(row["source_quote"], "€65–80K")
        self.assertEqual(row["arrangements"], ["hybrid"])
        self.assertIn("1–2 days working from home", row["geography"])
        self.assertEqual(row["duration"], "Permanent contract (CDI)")
        self.assertIn("6+ years", row["requirements"][0])
        self.assertIn("4+ years", row["requirements"][0])
        self.assertEqual(row["field_reviews"]["requirements"]["state"], "conflicting")
        self.assertIn("audit of an anonymized dataset", row["assessment"])

        review = row["editorial_review"]
        sources = {source["id"]: source for source in row["sources"]}
        employer_action, original_action = review["actions"]
        self.assertEqual((employer_action["label"], employer_action["url"], employer_action["purpose"]),
                         ("Read employer listing", employer_url, "description"))
        self.assertEqual((original_action["url"], original_action["purpose"]), (original_url, "archived_listing"))
        receipts = {item["source_id"]: item for item in review["receipts"]}
        employer_receipt = receipts[employer_action["source_id"]]
        self.assertTrue(employer_receipt["approved"])
        self.assertEqual(employer_receipt["scope"], "field_review")
        self.assertNotIn("approved_terms_receipt_id", review)
        for field, binding in row["field_reviews"].items():
            self.assertIn(field, employer_receipt["reviewed_fields"])
            self.assertEqual(binding["basis"], "direct_source")
            self.assertEqual(binding["reviewed_on"], employer_receipt["checked_on"])
            self.assertEqual([sources[sid]["url"] for sid in binding["source_ids"]], [employer_url])
        self.assertEqual(receipts[original_action["source_id"]]["http_status"], 404)
        self.assertFalse(receipts[original_action["source_id"]]["approved"])
        archived = prior_values(row, "employer-listing-2026-11-22.correction")
        self.assertEqual(archived["disposition"]["state"], "historical_page_unavailable")
        self.assertEqual(archived["last_route_check"]["url"], original_url)
        self.assertEqual(archived["last_route_check"]["http_status"], 404)
        self.assertEqual(row["last_route_check"]["url"], employer_url)
        self.assertEqual(row["last_route_check"]["http_status"], 200)
        application = row["last_route_check"]["application_check"]
        self.assertEqual((application["url"], application["http_status"], application["result"]),
                         ("https://www.workatastartup.com/jobs/114405", 406, "unavailable"))
        sign_in, = row["last_route_check"]["application_checks"]
        self.assertEqual(sign_in["retrieval_reason"], "sign_in")
        self.assertEqual(sign_in["rendered_observation"]["url"], "https://account.ycombinator.com/")
        for check in (application, sign_in):
            receipt = next(item for item in review["receipts"] if item.get("url") == check["url"])
            self.assertEqual(receipt["scope"], "retrieval")
            self.assertFalse(receipt["approved"])
            self.assertEqual(sources[receipt["source_id"]]["url"], check["url"])

    def test_five_scoped_reviews_leave_full_terms_and_other_field_clocks_alone(self):
        reviewed = {"mercor.work.expert-network": "pay", "proximal.work.frontierswe-fellowship": "pay",
                    "rws_trainai.work.polaris-asr": "destination", "invisible.work.full-stack-trainer": "destination",
                    "aixi.work.machine-learning-research-scientist": "pay"}
        for rid, field in reviewed.items():
            with self.subTest(route=rid):
                row = self.routes[rid]
                fresh = [r for r in row["editorial_review"]["receipts"] if r["checked_on"] == "2026-11-18"]
                self.assertEqual(len(fresh), 1)
                receipt = fresh[0]
                self.assertEqual(receipt["scope"], "field_review")
                self.assertEqual(receipt["reviewed_fields"], [field])
                self.assertEqual(receipt["approval_basis"], "source_content_review")
                self.assertEqual(receipt["reviewer"], "Codex source review")
                self.assertLessEqual(receipt["retrieved_at"], receipt["checked_at"])
                field_review = row["field_reviews"][field]
                if rid == "mercor.work.expert-network":
                    field_review = prior_values(row, "w1-correction-2026-11-22")["field_reviews"][field]
                self.assertEqual(field_review["reviewed_on"], "2026-11-18")
                self.assertEqual(field_review["source_ids"], [receipt["source_id"]])
                self.assertEqual(row["last_link_check"]["date"], "2026-10-28")
                if rid != "mercor.work.expert-network":
                    self.assertNotIn("approved_terms_receipt_id", row["editorial_review"])
                for name, review in row["field_reviews"].items():
                    if name != field:
                        self.assertNotEqual(review["reviewed_on"], "2026-11-18")
        mercor = self.routes["mercor.work.expert-network"]
        self.assertEqual(mercor["editorial_review"]["approved_terms_receipt_id"], "mercor.work.expert-network.key-terms-2026-11-08")
        self.assertFalse(mercor["numeric_pay"])
        self.assertFalse(mercor["pay_terms"]["hourly_comparable"])
        previous = prior_values(mercor, "w1-correction-2026-11-22")
        self.assertIn("$91/hour", previous["pay_context"])
        self.assertIn("Network context", previous["pay_context"])
        self.assertIn("$94/hour average contracted rate on 22 November 2026", mercor["pay_context"])
        current = mercor["field_reviews"]["pay"]
        self.assertEqual(current["reviewed_on"], "2026-11-22")
        self.assertEqual(current["source_ids"], ["mercor.work.expert-network.w1-expert-network-2026-11-22"])
        self.assertTrue(any("$90" in h["note"] for h in mercor["check_history"]))
        self.assertTrue(any("$97" in h["note"] for h in mercor["check_history"]))
        self.assertEqual(self.routes["proximal.work.frontierswe-fellowship"]["pay_terms"]["unit"], "undisclosed")

    def test_turing_withdrawal_does_not_turn_a_block_into_fresh_eligibility(self):
        row = self.routes["turing.work.machine-learning"]
        self.assertEqual(row["geography"], "Country eligibility unverified")
        self.assertEqual(row["status"], "information")
        self.assertEqual(prior_values(row, "w1-correction-2026-11-22")["status"], "unverified")
        self.assertEqual(row["field_reviews"]["location"]["state"], "not_researched")
        self.assertIsNone(row["field_reviews"]["location"]["reviewed_on"])
        self.assertEqual(row["field_reviews"]["location"]["basis"], "not_reviewed")
        receipt = next(item for item in row["editorial_review"]["receipts"]
                       if item["id"] == "turing.work.machine-learning.retained-country-correction-2026-11-18")
        self.assertFalse(receipt["approved"])
        self.assertEqual(receipt["result"], "blocked")
        self.assertEqual(receipt["scope"], "retrieval")
        self.assertEqual(receipt["correction_basis"], "retained_record_review")
        old = prior_values(row, "correction-2026-11-18")
        self.assertEqual(old["geography"], "Pakistan / Turkey listing")
        self.assertEqual(old["field_reviews"]["location"]["state"], "sourced")
        claim = next(c for c in self.canonical["claims"] if c["id"] == "turing.claim.worker_opportunities")
        self.assertEqual(claim["status"], "unverified")
        self.assertEqual(claim["confidence"], "U")

    def test_availability_corrections_do_not_claim_specific_closure_or_placement(self):
        rws = self.routes["rws_trainai.work.polaris-asr"]
        self.assertEqual(rws["status"], "historical")
        self.assertNotIn("disposition", rws["editorial_review"])
        self.assertEqual(rws["pay_label"], "$16 / hour")
        self.assertIsNone(rws["field_reviews"]["pay"]["reviewed_on"])
        self.assertIn("does not establish that Polaris closed", rws["availability_note"])
        invisible = self.routes["invisible.work.full-stack-trainer"]
        self.assertIn("were not tested", invisible["availability_note"])
        self.assertEqual(invisible["field_reviews"]["pay"]["reviewed_on"], "2026-10-28")
        old = prior_values(invisible, "correction-2026-11-18")
        self.assertIn("could not be loaded", old["availability_note"])

    def test_aixi_currency_and_amount_change_does_not_rewrite_original_evidence(self):
        row = self.routes["aixi.work.machine-learning-research-scientist"]
        self.assertEqual(row["pay_terms"]["currency"], "USD")
        self.assertEqual(row["pay_terms"]["unit"], "year")
        self.assertFalse(row["pay_terms"]["hourly_comparable"])
        self.assertEqual(row["geography"], "London / Berkeley")
        self.assertEqual(row["research_record"]["route"]["pay"]["currency"], "GBP")
        old = prior_values(row, "correction-2026-11-18")
        self.assertEqual(old["source_quote"], "£120,000 – £160,000 / year")
        self.assertEqual(row["terms_checked_on"], "2026-10-28")

    def test_prolific_participant_policy_and_program_signup_keep_distinct_scope(self):
        participant = self.routes["prolific.work.study-participant"]
        expert = self.routes["prolific.work.expert-network"]
        self.assertEqual(participant["requirements"], ["Over 18."])
        self.assertIn("with occasional exceptions", participant["geography"])
        old = prior_values(participant, "eligibility-copy-correction-2026-11-22")
        self.assertIn("Age 18+", old["assessment"])
        self.assertEqual(participant["field_reviews"]["assessment"]["reviewed_on"], "2026-10-14")
        self.assertEqual(expert["field_reviews"]["requirements"]["state"], "not_researched")
        for route in (participant, expert):
            with self.subTest(route=route["id"]):
                self.assertEqual(route["availability_note"], "Join the waitlist, accept an invitation, then verify your account.")
                receipt = next(item for item in route["editorial_review"]["receipts"]
                               if item["id"] == f"{route['id']}.w1-waitlist-recheck-2026-11-22.retrieval")
                self.assertEqual(receipt["url"], route["url"])
                self.assertFalse(receipt["approved"])
        policy_id = participant["field_reviews"]["requirements"]["source_ids"][0]
        policy = next(item for item in participant["editorial_review"]["receipts"] if item["source_id"] == policy_id)
        self.assertEqual(policy["reviewed_fields"], ["requirements", "location"])
        self.assertEqual(policy["checked_on"], "2026-11-22")
        self.assertIn("over 18 years old", policy["evidence"][0]["quote"])

    def test_events_preserve_filing_dates_and_qualify_procedural_outcomes(self):
        validate_company_events(self.events, self.canonical)
        rows = {e["id"]: e for e in self.events["events"]}
        scale = rows["scale_ai.event.mckinney-misclassification-suit"]
        self.assertEqual(scale["date"], "2024-12-10")
        self.assertEqual(scale["status"], "Settlement granted final approval")
        self.assertIn("Scale denies the claims", scale["detail"])
        self.assertIn("September 13, 2027", scale["detail"])
        self.assertTrue(any(s["url"].endswith("/ORDER_GRANTING_FINAL_APPROVAL") and s["published_on"] == "2026-10-30" for s in scale["sources"]))
        boggs = rows["handshake_ai.event.boggs-misclassification-suit"]
        self.assertEqual(boggs["date"], "2026-07-20")
        self.assertEqual(boggs["status"], "Stayed pending mediation")
        self.assertIn("alleges", boggs["detail"])
        self.assertIn("Arbitration rights remain reserved", boggs["detail"])
        self.assertIn("no merits or settlement ruling is made", boggs["detail"])
        for row in (scale, boggs):
            self.assertEqual(row["kind"], "lawsuit")
            self.assertEqual(row["date_basis"], "filed")
            self.assertEqual(row["status_checked_on"], "2026-11-18")
            self.assertLessEqual(len(row["detail"]), 320)
            self.assertLessEqual(len(row["status"]), 40)
        for row in self.events["events"]:
            if row not in (scale, boggs):
                self.assertLess(row["status_checked_on"], "2026-11-18")

    def test_new_public_evidence_is_bounded_and_contains_no_private_capture_paths(self):
        text = (ROOT / "data/work-routes.json").read_text()
        self.assertNotIn("/workspace/", text)
        self.assertNotIn("libfile_", text)
        for row in self.work["routes"]:
            for receipt in row["editorial_review"]["receipts"]:
                if receipt["checked_on"] == "2026-11-18" and receipt.get("approved"):
                    words = sum(len(e.get("quote", "").split()) for e in receipt["evidence"])
                    if row["id"] == "aixi.work.machine-learning-research-scientist":
                        words += len(row["source_quote"].split())
                    self.assertLessEqual(words, 25)


if __name__ == "__main__":
    unittest.main()
