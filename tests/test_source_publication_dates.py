"""Publication receipts are exact-ID overlays on the frozen research."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import ValidationError, canonical_bytes, validate_source_updates


class SourcePublicationDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = (ROOT / "data/canonical.json").read_bytes()
        cls.data = json.loads(cls.baseline)
        cls.profiles = json.loads((ROOT / "data/profile-content.json").read_bytes())
        cls.updates = json.loads((ROOT / "data/source-updates.json").read_bytes())
        cls.sources = {row["id"]: row for row in cls.data["sources"]}

    def test_same_article_ids_keep_their_original_source_records(self):
        expected_dates = {
            "afterquery.source.round2-funding": "2026-04-09",
            "afterquery.source.oct14-fd3e4675dd42": "2026-04-09",
            "datacurve.source.oct14-9b179f419da7": "2025-10-09",
            "scale_ai.source.oct14-891cd0d871ee": "2025-07-01",
            "surge_ai.source.oct14-891cd0d871ee": "2025-07-01",
        }
        self.assertEqual(validate_source_updates(self.updates, self.data, self.profiles), self.updates)
        corrections = [row for row in self.updates["evidence_context"]["corrections"] if row["kind"] == "source_publication_date"]
        self.assertEqual({row["target"]["source_id"]: row["publication_date"] for row in corrections}, expected_dates)
        for row in corrections:
            source = self.sources[row["target"]["source_id"]]
            with self.subTest(source=source["id"]):
                self.assertNotIn("published_on", source)
                self.assertEqual(row["historical_snapshot"]["sources"], [source])
                self.assertEqual(row["evidence"]["url"], source["url"])
                self.assertEqual(source["accessed_on"], "2026-10-14")
        self.assertEqual(hashlib.sha256(self.baseline).hexdigest(), "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")
        self.assertEqual(canonical_bytes(self.data), self.baseline)

    def test_rejects_mismatched_date_scope_and_source_roles(self):
        def amendment(sidecar):
            return next(row for row in sidecar["evidence_context"]["corrections"]
                        if row["kind"] == "source_publication_date" and row["company_id"] == "scale_ai")

        changes = [
            ("publication_date", "2025-07-02", "visible dateline"),
            ("checked_at", "2026-11-22T25:00:00Z", "UTC retrieval time"),
            ("reviewer", "", "review assertion"),
            ("publication_date_basis", "article_metadata", "review assertion"),
            ("target", {"source_id": "surge_ai.source.oct14-891cd0d871ee"}, "undated source in that company"),
            ("historical_snapshot", {"dataset_version": "2.5.0", "sources": []}, "historical snapshot"),
            ("evidence.redirects", 0, "redirect receipt"),
            ("evidence.url", "https://www.aol.com/exclusive-scale-ais-bigger-rival-152327362.html", "stored URL"),
            ("evidence.retrieval_scope", "financial_content", "publication-only retrieval receipt"),
            ("evidence.content_sha256", "unchecked", "publication-only retrieval receipt"),
            ("evidence.http_status", 403, "publication-only retrieval receipt"),
        ]
        for field, value, error in changes:
            with self.subTest(field=field):
                sidecar = copy.deepcopy(self.updates)
                row = amendment(sidecar)
                section, _, key = field.rpartition(".")
                (row[section] if section else row)[key] = value
                with self.assertRaisesRegex(ValidationError, error):
                    validate_source_updates(sidecar, self.data, self.profiles)

        sidecar = copy.deepcopy(self.updates)
        sidecar["evidence_context"]["corrections"].append(amendment(sidecar))
        with self.assertRaisesRegex(ValidationError, "duplicate correction"):
            validate_source_updates(sidecar, self.data, self.profiles)

    def test_a_dated_sibling_cannot_receive_the_undated_citations_receipt(self):
        sidecar = copy.deepcopy(self.updates)
        row = next(row for row in sidecar["evidence_context"]["corrections"] if row.get("target") == {"source_id": "afterquery.source.round2-funding"})
        source = self.sources["afterquery.source.b_aq3"]
        row["target"]["source_id"] = source["id"]
        row["id"] = f"{source['id']}.publication-date-{row['reviewed_on']}"
        row["historical_snapshot"]["sources"] = [source]
        with self.assertRaisesRegex(ValidationError, "undated source in that company"):
            validate_source_updates(sidecar, self.data, self.profiles)
