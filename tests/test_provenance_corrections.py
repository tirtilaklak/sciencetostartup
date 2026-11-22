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

AFTERQUERY_CAREERS = "https://www.afterquery.com/careers"
AFTERQUERY_BOARD = "https://api.ashbyhq.com/posting-api/job-board/AfterQuery?includeCompensation=true"
RECONCILIATION = "board-reconciliation-correction-2026-11-22"


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
        self.assertEqual(self.release["release_id"], "2026-11-22.8")
        self.assertEqual(self.release["as_of"], "2026-11-22")
        self.assertEqual(self.release["publication_as_of"], "2026-11-22T14:08:49Z")
        self.assertEqual(self.release["work_routes_sha256"],
                         hashlib.sha256((ROOT / "data/work-routes.json").read_bytes()).hexdigest())
        validate_editorial_release(self.work, self.release, self.canonical)
        counts = editorial_counts(self.work)
        self.assertEqual(counts["records"], 135)
        self.assertEqual(counts["work_routes"], 72)
        self.assertEqual(counts["named_listings"], 51)
        self.assertEqual(counts["past_other_records"], 30)
        self.assertEqual(counts["other_company_jobs"], 10)

    def test_security_and_people_keep_exact_retrievals_and_prior_forms_separate(self):
        exact_roles = {
            "senior-software-engineer-security-infrastructure": ("99afbbe0-5ad1-4f25-a00a-049f14428ac6", 200),
            "people-programs-lead": ("2ba013e1-d254-4436-afd7-19d0b451424f", 404),
        }
        for role, (job_id, status) in exact_roles.items():
            with self.subTest(role=role):
                row = self.routes[f"afterquery.work.{role}"]
                review = row["editorial_review"]
                sources = {s["id"]: s for s in row["sources"]}
                exact = f"https://jobs.ashbyhq.com/AfterQuery/{job_id}"
                application = exact + "/application"
                self.assertEqual(row["url"], application)
                prior_form = sources["afterquery.source.round2-form-" + job_id]
                self.assertEqual((prior_form["url"], prior_form["accessed_on"]), (application, "2026-10-14"))
                self.assertIn("10 inputs and a visible Submit Application control", prior_form["notes"])
                self.assertFalse(row["application_submitted"])

                for url in (exact, application):
                    checks = [r for r in review["receipts"] if r.get("url") == url and r["scope"] == "retrieval"
                              and r["checked_on"] == "2026-11-22"]
                    self.assertEqual([(r["http_status"], r["result"], r["approved"]) for r in checks],
                                     [(503, "blocked", False), (status, "readable" if status == 200 else "not_found", False)])
                    self.assertEqual(checks[0]["retrieval_reason"], "environment_proxy_failure")
                    for receipt in checks:
                        self.assertEqual(sources[receipt["source_id"]]["url"], url)
                    self.assertLess(checks[0]["checked_at"], checks[1]["checked_at"])

                destination = row["field_reviews"]["destination"]
                self.assertEqual(destination["reviewed_on"], "2026-11-22")
                self.assertEqual([sources[sid]["url"] for sid in destination["source_ids"]],
                                 [AFTERQUERY_BOARD, AFTERQUERY_CAREERS])
                board_receipts = [r for r in review["receipts"] if r["source_id"] in destination["source_ids"]]
                self.assertEqual({r["source_id"] for r in board_receipts}, set(destination["source_ids"]))
                self.assertTrue(all(r["approved"] and "destination" in r["reviewed_fields"] for r in board_receipts))
                self.assertTrue(all(job_id in " ".join(r["evidence"]) for r in board_receipts))

        security = self.routes["afterquery.work.senior-software-engineer-security-infrastructure"]
        old_security = prior_values(security, RECONCILIATION)
        self.assertEqual(old_security["status"], "historical")
        self.assertEqual(old_security["disposition"]["state"], "historical_page_unavailable")
        self.assertEqual(old_security["disposition"]["reviewed_on"], "2026-11-08")
        old_checks = [r for r in security["editorial_review"]["receipts"]
                      if r["source_id"] in old_security["disposition"]["source_ids"]]
        self.assertEqual([r["http_status"] for r in old_checks], [404, 404, 200])
        self.assertEqual(old_security["alternative_destination"]["url"], "https://jobs.ashbyhq.com/AfterQuery")
        self.assertEqual((security["status"], security["availability_label"]), ("listed", "Listed again"))
        self.assertTrue(security["listed_on_current_company_board"])
        self.assertTrue(security["form_available"])
        new_board = next(r for r in security["editorial_review"]["receipts"] if r.get("url") == AFTERQUERY_BOARD)
        self.assertIn("publishedAt 2026-11-09T17:22:34.994+00:00", " ".join(new_board["evidence"]))
        new_form = security["last_route_check"]["application_check"]
        self.assertEqual((new_form["url"], new_form["retrieval_reason"], new_form["rendered_checked_at"]),
                         (security["url"], "application_form_rendered", "2026-11-22T13:59:23Z"))
        self.assertIn("labeled fields and a Submit Application control", new_form["rendered_observation"])
        self.assertIn("Application acceptance remains unconfirmed", security["availability_note"])

        people = self.routes["afterquery.work.people-programs-lead"]
        old_people = prior_values(people, RECONCILIATION)
        self.assertEqual((old_people["status"], old_people["form_available"]), ("listed", True))
        self.assertEqual(people["status"], "historical")
        self.assertFalse(people["listed_on_current_company_board"])
        self.assertEqual(people["pay_label"], "$160K–$230K salary band + equity")
        self.assertNotIn("pay", old_people["field_reviews"])
        self.assertEqual(people["field_reviews"]["pay"], {
            "state": "sourced", "reviewed_on": "2026-10-28", "basis": "stored_evidence",
            "source_ids": [people["id"] + ".review-2026-10-28"],
        })
        archived = people["editorial_review"]["disposition"]
        self.assertEqual((archived["state"], archived["reviewed_on"]), ("historical_page_unavailable", "2026-11-22"))
        latest = people["last_route_check"]
        self.assertEqual((latest["url"], latest["http_status"], latest["retrieval_reason"]),
                         (people["url"], 404, "http_not_found"))
        self.assertIn("Job not found", latest["rendered_observation"])
        self.assertIn("Employer closure remains unconfirmed", people["availability_note"])

    def test_changed_afterquery_quotes_keep_equity_bonus_and_ote_separate(self):
        roles = [
            ("business-operations-generalist", "Business Operations Generalist", "$150K–$250K salary band + equity",
             "$160K – $250K • Offers Equity", {"Equity": "Offered"}),
            ("sales-operations-associate", "Associate", "$130K–$150K salary band + equity; bonus offered",
             "$145K – $175K • Offers Equity • Offers Bonus", {"Equity": "Offered", "Bonus": "Offered"}),
            ("engagement-manager", "Engagement Manager", "$150K–$225K salary band + equity; bonus offered",
             "$225K – $450K • Offers Equity • Offers Bonus • Annual Target Compensation: "
             "$300-450k OTE (50% base / 50% variable) depending on experience.",
             {"Equity": "Offered", "Bonus": "Offered", "Annual salary field": "$225,000–$450,000",
              "Annual on-target earnings": "$300,000–$450,000", "Annual base implied by the 50/50 split": "$150,000–$225,000"}),
        ]
        for role, title, previous_label, quote, observations in roles:
            with self.subTest(role=role):
                row = self.routes[f"afterquery.work.{role}"]
                self.assertEqual(row["role"], title)
                self.assertEqual(prior_values(row, RECONCILIATION)["pay_label"], previous_label)
                self.assertEqual(row["source_quote"], quote)
                self.assertEqual({o["label"]: o["value"] for o in row["pay_observations"]}, observations)
        self.assertEqual(self.routes["afterquery.work.engagement-manager"]["status"], "pay_conflict")

    def test_terac_shopping_sign_in_and_separate_rl_closure(self):
        shopping = self.routes["terac.work.ai-evaluator-shopping-assistant"]
        description = "https://terac.com/opportunities/TKd76RUIQxw3wy-x"
        start = "https://terac.com/apply/start/58b90b6b-a97d-478e-817c-6666a230e213"
        self.assertEqual((shopping["status"], shopping["url"], shopping["pay_label"], shopping["hours"]),
                         ("listed", description, "$30 / hour", "20+ hours/week"))
        self.assertEqual(shopping["arrangements"], ["remote"])
        self.assertEqual(shopping["engagement_type"], "contract")
        self.assertEqual(shopping["pay_terms"], {"unit": "hour", "hourly_comparable": True, "basis": "hour", "currency": "USD"})
        previous = prior_values(shopping, RECONCILIATION)
        self.assertEqual((previous["status"], previous["last_route_check"]["date"], previous["last_route_check"]["result"]),
                         ("closed", "2026-10-28", "official_listing_closed"))
        review = shopping["editorial_review"]
        pay_receipt = next(r for r in review["receipts"] if r["source_id"] in shopping["field_reviews"]["pay"]["source_ids"])
        self.assertEqual((pay_receipt["url"], pay_receipt["checked_on"], pay_receipt["approved"]),
                         (description, "2026-11-22", True))
        self.assertIn("pay", pay_receipt["reviewed_fields"])
        check = shopping["last_route_check"]["application_check"]
        self.assertEqual((check["url"], check["http_status"], check["retrieval_reason"]),
                         (start, 200, "application_start_requires_linkedin"))
        self.assertIn("Continue with LinkedIn", check["rendered_observation"])
        self.assertIn("Screening and submission were unverified", check["note"])

        closed = self.routes["terac.work.rl-environment-creation"]
        self.assertEqual((closed["status"], closed["url"], closed["pay_label"]),
                         ("closed", "https://terac.com/opportunities/KZwfXOQhfpdjGT8k", "$90 / hour"))
        self.assertEqual(closed["last_route_check"]["review_signals"], ["explicitly_closed"])
        self.assertIn("This listing has closed", closed["availability_note"])

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
        self.assertEqual(row["route_kind"], "named_listing")
        self.assertTrue(row["listed_on_current_company_board"])
        self.assertEqual(row["availability_label"], "Application link returned 404")
        self.assertIn("OOAK still lists this role", row["availability_note"])
        self.assertIn("Application access remains unconfirmed", row["availability_note"])
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
        self.assertNotIn("disposition", review)
        self.assertNotIn("status_review", review)
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
        self.assertEqual(row["last_route_check"]["checked_at"], "2026-11-22T12:26:53Z")
        application = row["last_route_check"]["application_check"]
        self.assertEqual((application["url"], application["http_status"], application["result"]),
                         ("https://www.workatastartup.com/jobs/114405", 404, "not_found"))
        self.assertEqual(application["checked_at"], "2026-11-22T12:56:45Z")
        self.assertEqual(application["response_sha256"], "56d3c2c604c259de804e820a8c43bb17f32feed21dd35c0e76612b7539c2af2d")
        self.assertEqual(application["rendered_observation"]["http_status"], 404)
        self.assertEqual(application["rendered_observation"]["visible_text_sha256"],
                         "920306a984462aa8b3dc6652ac996c8deb9218a86eaa5c1024b0e43101838b3e")
        default_headers, sign_in = row["last_route_check"]["application_checks"]
        self.assertEqual((default_headers["url"], default_headers["http_status"], default_headers["result"]),
                         (application["url"], 406, "unavailable"))
        self.assertEqual(default_headers["response_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertNotEqual(sign_in["url"], application["url"])
        self.assertEqual(sign_in["retrieval_reason"], "sign_in")
        self.assertEqual(sign_in["rendered_observation"]["url"], "https://account.ycombinator.com/")
        previous = prior_values(row, "application-link-404-2026-11-22.correction")
        old_application = previous["last_route_check"]["application_check"]
        self.assertEqual(old_application["http_status"], 406)
        self.assertEqual(old_application["rendered_observation"]["http_status"], 503)
        self.assertEqual(previous["last_route_check"]["application_checks"], [sign_in])
        for check in (application, default_headers, sign_in, old_application):
            receipt = next(item for item in review["receipts"] if item.get("url") == check["url"]
                           and item["checked_at"] == check["checked_at"])
            self.assertEqual(receipt["scope"], "retrieval")
            self.assertFalse(receipt["approved"])
            self.assertEqual(sources[receipt["source_id"]]["url"], check["url"])
            for key in ("http_status", "retrieval_reason", "response_sha256", "rendered_observation"):
                self.assertEqual(receipt.get(key), check.get(key))

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
