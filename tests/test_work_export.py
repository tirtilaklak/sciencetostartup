"""CSV URL purpose and source receipt bindings."""
import csv
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from presentation import work_export_rows


class WorkExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = json.loads((ROOT / "data/work-routes.json").read_text())["routes"]

    def csv_rows(self, routes):
        projected = work_export_rows({"routes": routes}, SimpleNamespace(companies={}))
        script = (ROOT / "web/work-core.js").read_text() + """
const rows = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
process.stdout.write(S2SWork.csvFor(rows, {}));
"""
        result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-e", script],
                                input=json.dumps(projected), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return list(csv.DictReader(result.stdout.removeprefix("\ufeff").splitlines()))

    def test_description_only_combined_and_legacy_destinations(self):
        description, application = "https://example.org/role", "https://example.org/apply"
        role = {"id": "sample", "company_id": "sample", "role": "Role", "url": description,
                "sources": [{"id": "description", "url": description}, {"id": "application", "url": application}]}
        description_action = {"purpose": "description", "source_id": "description",
                              "url": description, "label": "Read role"}
        combined_action = dict(description_action, purpose="application", label="Read application instructions")
        separate_action = {"purpose": "application", "source_id": "application",
                           "url": application, "label": "Application access unconfirmed"}
        description_review = {"recorded_url_purpose": "description", "actions": [description_action]}
        cases = {
            "Description with separate current application": (
                dict(role, editorial_review=dict(description_review, actions=[description_action, separate_action])), "", None,
                None, "description"),
            "Combined description and application instructions": (
                dict(role, editorial_review=dict(description_review, actions=[combined_action])), description, description,
                "application", "application"),
            "Description with separate original application": (
                dict(role, editorial_review=description_review,
                     research_record={"route": {"overview_url": description, "application_url": application}}),
                application, application, "application", "description"),
            "Legacy URL": (role, description, None, "description", "description"),
        }
        rows = self.csv_rows([case[0] for case in cases.values()])
        for row, (name, (_, original_column, application_url, legacy_purpose, action_purpose)) in zip(rows, cases.items(), strict=True):
            with self.subTest(name=name):
                self.assertEqual(row["original_application_url"], original_column)
                self.assertEqual(row["current_action_url"], description)
                urls = json.loads(row["original_url_details"])
                self.assertEqual(urls["source_url"], description)
                self.assertEqual(urls["application_url"], application_url)
                self.assertEqual(urls["legacy_url_purpose"], legacy_purpose)
                self.assertEqual(urls["current_action_purpose"], action_purpose)

    def test_work_history_survives_relisting_and_keeps_temporary_source_errors_distinct(self):
        records = {route["id"]: route for route in self.routes}
        exported = {row["route_id"]: row for row in self.csv_rows(self.routes)}
        for rid, route in records.items():
            with self.subTest(route=rid):
                evidence = json.loads(exported[rid]["review_evidence"])
                history = [{key: item[key] for key in ("date", "result", "url", "note", "source_ids") if key in item}
                           for item in route.get("check_history", [])]
                self.assertEqual(evidence.get("check_history", []), history)
                sources = {source.get("id"): source.get("url") for source in route.get("sources", [])}
                checks = [receipt for receipt in (route.get("editorial_review") or {}).get("receipts", [])
                          if receipt.get("scope") == "retrieval" and sources.get(receipt.get("source_id"))
                          and receipt.get("url", sources[receipt["source_id"]]) == sources[receipt["source_id"]]]
                exported_checks = {item["id"]: item for item in evidence.get("source_receipts", [])}
                for check in checks:
                    actual = exported_checks[check["id"]]
                    self.assertEqual(actual["url"], sources[check["source_id"]])
                    for field in ("checked_on", "result", "http_status", "retrieval_reason"):
                        self.assertEqual(actual.get(field), check.get(field))
        security = exported["afterquery.work.senior-software-engineer-security-infrastructure"]
        self.assertEqual(json.loads(security["original_url_details"])["application_check"]["date"], "2026-11-22")

    def test_replaced_listing_keeps_each_bound_source_observation(self):
        description, archived = "https://example.org/role", "https://example.org/original"
        sources = [{"id": "description", "url": description}, {"id": "archive", "url": archived}]
        actions = [{"purpose": "description", "source_id": "description", "url": description, "label": "Read role"},
                   {"purpose": "archived_listing", "source_id": "archive", "url": archived, "label": "Original posting"}]
        first = {"id": "readable", "source_id": "archive", "checked_on": "2026-10-01",
                 "scope": "retrieval", "result": "readable", "http_status": 200}
        second = dict(first, id="removed", checked_on="2026-11-01", result="not_found", http_status=404)
        unrelated = dict(second, id="unbound", source_id="unrelated")
        mismatched = dict(second, id="mismatched", url=description)
        route = {
            "id": "sample", "company_id": "sample", "role": "Role", "url": description, "sources": sources,
            "editorial_review": {"recorded_url_purpose": "description", "actions": actions,
                                 "receipts": [first, second, unrelated, mismatched]},
        }
        row, = self.csv_rows([route])
        self.assertEqual(json.loads(row["original_url_details"])["archived_source_url"], archived)
        self.assertEqual(json.loads(row["review_evidence"])["source_receipts"],
                         [dict(first, url=archived), dict(second, url=archived)])

    def test_release_urls_have_machine_readable_purpose_and_exact_source_bindings(self):
        rows = self.csv_rows(self.routes)
        self.assertEqual([row["route_id"] for row in rows], [route["id"] for route in self.routes])
        self.assertEqual(len(rows[0]), 33)
        career_rows = []
        for row, route in zip(rows, self.routes, strict=True):
            with self.subTest(route=row["route_id"]):
                urls = json.loads(row["original_url_details"])
                sources = {source["id"]: source for source in route["sources"]}
                self.assertEqual(urls["recorded_url"], route["url"])
                self.assertEqual(bool(row["original_application_url"]), bool(urls["legacy_url_purpose"]))
                self.assertEqual(bool(row["current_action_url"]), bool(urls["current_action_purpose"]))
                if urls["legacy_url_purpose"] == "application":
                    self.assertEqual(row["original_application_url"], urls["application_url"])
                for url, key in ((row["current_action_url"], "current_action_source_ids"),
                                 (urls["source_url"], "source_ids"),
                                 (urls["application_url"], "application_source_ids"),
                                 (urls.get("archived_source_url"), "archived_source_ids")):
                    self.assertTrue(all(sources[sid]["url"] == url for sid in urls.get(key, [])))
                for observation in urls.get("source_observations", []):
                    self.assertEqual(observation["accessed_on"], sources[observation["source_id"]]["accessed_on"])
                for check in urls.get("checked_destinations", []):
                    self.assertTrue(check["source_ids"])
                    self.assertTrue(all(sources[sid]["url"] == check["url"] for sid in check["source_ids"]))
                if row["opportunity_kind"] == "career_page" or row["route_id"] == "rws_trainai.work.polaris-asr":
                    career_rows.append(row)
                    self.assertEqual(urls["legacy_url_purpose"], "career_board")
                    self.assertEqual(urls["current_action_purpose"], "career_board")
                    self.assertIsNone(urls["application_url"])
        self.assertEqual(len(career_rows), 24)

    def test_archived_ashby_listings_are_recoverable_apart_from_generic_boards(self):
        earlier_urls = {
            "bespoke_labs.work.devops-sre": "bespokelabs/1548fb45-e179-4c28-aec1-d1f3461028e8",
            "bespoke_labs.work.corporate-finance": "bespokelabs/4402a6fd-0785-49d6-8bd8-d8b033907f0b/",
            "polymath_ai_labs.work.research-resident": "polymath/feac8f33-2e28-4434-bff5-cf26c849f270",
            "elorian.work.model-safety": "elorian-ai-inc/69acef27-d755-4b22-8257-94759edb0efb",
            "elorian.work.rl-infrastructure-engineer": "elorian-ai-inc/7fc67724-f805-4715-a157-fa00e050bf8d",
        }
        checks = {route["id"]: route["last_route_check"]["date"] for route in self.routes if route["id"] in earlier_urls}
        rows = self.csv_rows([route for route in self.routes if route["id"] in earlier_urls])
        self.assertEqual(len(rows), len(earlier_urls))
        for row in rows:
            with self.subTest(route=row["route_id"]):
                urls = json.loads(row["original_url_details"])
                evidence = json.loads(row["review_evidence"])
                earlier = "https://jobs.ashbyhq.com/" + earlier_urls[row["route_id"]]
                self.assertEqual(urls["archived_source_url"], earlier)
                self.assertEqual(urls["source_url"], earlier)
                self.assertTrue(urls["source_observations"])
                self.assertEqual(evidence["page_check"]["url"], earlier)
                self.assertEqual(evidence["page_check"]["date"], checks[row["route_id"]])
                self.assertIsNone(urls["application_url"])
                self.assertEqual(urls["legacy_url_purpose"], "career_board")
                self.assertEqual(urls["current_action_purpose"], "career_board")
                self.assertEqual(row["original_application_url"], row["current_action_url"])
                self.assertNotEqual(row["current_action_url"], earlier)

    def test_historical_forms_keep_prior_render_and_later_unavailable_checks(self):
        observed = {
            "g2i.work.senior-swe-training": "2026-10-23",
            "afterquery.work.research-engineer": "2026-10-14",
            "afterquery.work.research-scientist-frontier-evaluations": "2026-10-14",
            "afterquery.work.people-programs-lead": "2026-10-14",
        }
        rows = self.csv_rows([route for route in self.routes if route["id"] in observed])
        self.assertEqual(len(rows), len(observed))
        for row in rows:
            with self.subTest(route=row["route_id"]):
                urls = json.loads(row["original_url_details"])
                evidence = json.loads(row["review_evidence"])
                exact = row["original_application_url"]
                self.assertEqual(urls["application_url"], exact)
                self.assertEqual(urls["legacy_url_purpose"], "application")
                self.assertEqual(urls["current_action_purpose"], "career_board")
                self.assertNotEqual(row["current_action_url"], exact)
                self.assertEqual(urls["application_check"], {"url": exact, "date": observed[row["route_id"]],
                                 "result": "application_form_available", "verified_in_research": True})
                checks = evidence["archive_disposition"]["checks"]
                self.assertTrue(any(check["url"] == exact and check.get("http_status") == 404
                                    and check["date"] > observed[row["route_id"]] for check in checks))

    def test_reconciled_afterquery_csv_retains_exact_actions_and_pay_fields(self):
        expected = {
            "senior-software-engineer-security-infrastructure":
                ("99afbbe0-5ad1-4f25-a00a-049f14428ac6", "$200,000–$350,000 annual salary", "year"),
            "business-operations-generalist":
                ("30b3dddf-9804-4e80-8fc6-2e2b2a511ca7", "$160,000–$250,000 annual salary", "year"),
            "sales-operations-associate":
                ("d1236ef8-0030-4cbf-bbec-052c6eed971f", "$145,000–$175,000 annual salary", "year"),
            "engagement-manager":
                ("79185014-f08f-4520-923f-e6bb67d31973", "$225,000–$450,000 annual salary field (conflicting)", "conflicting"),
        }
        routes = {r["id"].removeprefix("afterquery.work."): r for r in self.routes if r["company_id"] == "afterquery"}
        rows = self.csv_rows([routes[slug] for slug in expected])
        for row, (slug, (job_id, amount, unit)) in zip(rows, expected.items(), strict=True):
            with self.subTest(route=row["route_id"]):
                exact = "https://jobs.ashbyhq.com/AfterQuery/" + job_id
                application = exact + "/application"
                urls = json.loads(row["original_url_details"])
                check = json.loads(row["review_evidence"])["application_check"]
                self.assertEqual(row["route_id"], "afterquery.work." + slug)
                self.assertEqual((row["advertised_pay"], row["pay_unit"], row["currency"]), (amount, unit, "USD"))
                self.assertEqual((row["current_action_url"], row["current_action_label"]), (exact, "Read role details"))
                self.assertEqual(urls["current_action_purpose"], "description")
                self.assertEqual(row["original_application_url"], application)
                self.assertEqual(urls["application_url"], application)
                self.assertEqual(urls["application_check"], {"date": "2026-11-22", "verified_in_research": True,
                                 "result": "application_form_available", "url": application})
                self.assertEqual((check["url"], check["http_status"], check["retrieval_reason"]),
                                 (application, 200, "application_form_rendered"))
                self.assertTrue({exact, application} <= set(row["source_urls"].split(" | ")))

        engagement = rows[-1]
        self.assertEqual(engagement["availability"], "Pay conflict")
        self.assertIn("$300,000–$450,000", engagement["pay_qualification"])
        self.assertIn("$150,000–$225,000", engagement["pay_qualification"])
        self.assertIn("split 50/50 between base and variable pay", engagement["pay_qualification"])
        self.assertEqual(json.loads(engagement["field_review_metadata"])["pay"], {
            "state": "conflicting", "reviewed_on": "2026-11-22", "basis": "direct_source",
            "source_ids": ["afterquery.work.engagement-manager.board-reconciliation-ashby-2026-11-22"],
        })
        self.assertIn("https://api.ashbyhq.com/posting-api/job-board/AfterQuery?includeCompensation=true",
                      engagement["source_urls"].split(" | "))

        people, = self.csv_rows([routes["people-programs-lead"]])
        exact = "https://jobs.ashbyhq.com/AfterQuery/2ba013e1-d254-4436-afd7-19d0b451424f"
        self.assertEqual(people["current_action_url"], "https://www.afterquery.com/careers")
        self.assertEqual(people["original_application_url"], exact + "/application")
        self.assertEqual(people["availability"], "Past listing · page unavailable")
        checks = json.loads(people["review_evidence"])["archive_disposition"]["checks"]
        self.assertEqual([(c["url"], c["date"], c["http_status"]) for c in checks],
                         [(exact, "2026-11-22", 404), (exact + "/application", "2026-11-22", 404)])

    def test_terac_csv_keeps_sign_in_start_separate_from_archived_rl_listing(self):
        shopping_id = "terac.work.ai-evaluator-shopping-assistant"
        closed_id = "terac.work.rl-environment-creation"
        rows = {r["route_id"]: r for r in self.csv_rows([r for r in self.routes if r["id"] in (shopping_id, closed_id)])}
        shopping = rows[shopping_id]
        self.assertEqual((shopping["availability"], shopping["advertised_pay"], shopping["pay_unit"]),
                         ("Application start available", "$30 / hour", "hour"))
        self.assertEqual(shopping["current_action_url"], "https://terac.com/opportunities/TKd76RUIQxw3wy-x")
        self.assertEqual(shopping["original_application_url"], "")
        urls = json.loads(shopping["original_url_details"])
        start = "https://terac.com/apply/start/58b90b6b-a97d-478e-817c-6666a230e213"
        self.assertEqual([(x["url"], x["purpose"]) for x in urls["checked_destinations"]], [(start, "application")])
        self.assertNotIn("application_check", urls)
        check = json.loads(shopping["review_evidence"])["application_check"]
        self.assertEqual((check["url"], check["http_status"], check["retrieval_reason"]),
                         (start, 200, "application_start_requires_linkedin"))
        self.assertIn("Continue with LinkedIn", check["rendered_observation"])
        closed = rows[closed_id]
        self.assertEqual((closed["availability"], closed["current_action_label"], closed["current_action_url"]),
                         ("Closed", "Read archived listing", "https://terac.com/opportunities/KZwfXOQhfpdjGT8k"))
        self.assertIsNone(json.loads(closed["original_url_details"])["application_url"])

    def test_archived_descriptions_and_checked_form_destinations_keep_distinct_roles(self):
        expected = {
            "appen.work.sage-media": ("archived_listing", "network", "application_migrated",
                                    "https://app.crowdgen.com/apply/signup?p=6RA3aZSrnQdD"),
            "apto.work.ai-data-research-engineer": (None, "career_board", "application_unpublished",
                                                   "https://herp.careers/v1/apto/NyufvNJGg7Td"),
            "terac.work.rl-environment-creation": ("archived_listing", "archived_listing", None, None),
            "quesma.work.route-review": ("source", "source", None, None),
            "apto.work.harbest-experts": ("network", "registration", None, None),
            "ooak.work.data-quality-specialist": (None, "description", None, None),
        }
        rows = {row["route_id"]: row for row in self.csv_rows([route for route in self.routes if route["id"] in expected])}
        self.assertEqual(rows.keys(), expected.keys())
        for route_id, (legacy_purpose, action_purpose, result, application) in expected.items():
            with self.subTest(route=route_id):
                row = rows[route_id]
                urls = json.loads(row["original_url_details"])
                evidence = json.loads(row["review_evidence"])
                self.assertEqual(urls["legacy_url_purpose"], legacy_purpose)
                self.assertEqual(urls["current_action_purpose"], action_purpose)
                self.assertEqual(urls["application_url"], application)
                self.assertNotIn("application_check", urls)
                if result:
                    self.assertNotEqual(urls["source_url"], application)
                    self.assertEqual(evidence["application_check"]["url"], application)
                    self.assertEqual(evidence["application_check"]["retrieval_reason"], result)
                    observed_on = [item["accessed_on"] for item in urls["source_observations"]
                                   if item["source_id"] in urls["source_ids"]]
                    self.assertLess(min(observed_on), evidence["application_check"]["date"])

        harbest = json.loads(rows["apto.work.harbest-experts"]["original_url_details"])
        self.assertEqual(harbest["checked_destinations"][0]["purpose"], "registration")
        terac = json.loads(rows["terac.work.rl-environment-creation"]["original_url_details"])
        self.assertEqual(terac["archived_source_url"], rows["terac.work.rl-environment-creation"]["current_action_url"])
        ooak = json.loads(rows["ooak.work.data-quality-specialist"]["original_url_details"])
        review = json.loads(rows["ooak.work.data-quality-specialist"]["review_evidence"])
        checks = [review["application_check"], *review["application_checks"]]
        self.assertEqual([(check["http_status"], check["retrieval_reason"]) for check in checks],
                         [(404, "http_not_found"), (406, "http_not_acceptable"), (200, "sign_in")])
        self.assertEqual([(check["url"], check["purpose"]) for check in ooak["checked_destinations"]],
                         list(dict.fromkeys((check["url"], "application") for check in checks)))
