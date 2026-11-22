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
                dict(role, editorial_review=dict(description_review, actions=[description_action, separate_action])), "", None),
            "Combined description and application instructions": (
                dict(role, editorial_review=dict(description_review, actions=[combined_action])), description, description),
            "Description with separate original application": (
                dict(role, editorial_review=description_review,
                     research_record={"route": {"overview_url": description, "application_url": application}}),
                application, application),
            "Legacy URL": (role, description, None),
        }
        rows = self.csv_rows([route for route, _, _ in cases.values()])
        for row, (name, (_, original_column, application_url)) in zip(rows, cases.items(), strict=True):
            with self.subTest(name=name):
                self.assertEqual(row["original_application_url"], original_column)
                self.assertEqual(row["current_action_url"], description)
                urls = json.loads(row["original_url_details"])
                self.assertEqual(urls["source_url"], description)
                self.assertEqual(urls["application_url"], application_url)

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
