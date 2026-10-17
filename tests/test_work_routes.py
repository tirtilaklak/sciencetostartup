"""Protect the reviewed work sidecar without regenerating its historical data."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import observatory
from fixtures import fixture


class WorkRouteValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.work = json.loads((ROOT / "data/work-routes.json").read_text())

    def test_reviewed_sidecar_is_preserved(self):
        work = copy.deepcopy(self.work)
        self.assertIs(observatory.validate_work_routes(work, self.data), work)
        self.assertEqual(work, self.work)
        self.assertEqual(work["source_dataset_version"], "2.3.0")
        self.assertEqual(work["dataset_as_of"], "2026-10-15")
        self.assertTrue(any(not row["claim_ids"] for row in work["routes"]))
        related = next(row for row in work["routes"] if row["id"] == "snorkel_ai.work.terminus-training")
        self.assertIn("laude.claim.worker_opportunities-1", related["claim_ids"])
        self.assertEqual(related["related_company_ids"], ["laude"])

    def test_bad_sidecar_fails_before_destination_is_created(self):
        unknown = copy.deepcopy(self.work)
        unknown["routes"][0]["claim_ids"].append("missing-claim")
        duplicate = copy.deepcopy(self.work)
        duplicate["routes"].append(copy.deepcopy(duplicate["routes"][0]))
        for name, content, message in (
            ("missing", None, "required curated"),
            ("malformed JSON", "{", "not readable JSON"),
            ("wrong root", "[]", "unsupported format"),
            ("invalid reference", json.dumps(unknown), "unknown claim reference"),
            ("duplicate ID", json.dumps(duplicate), "duplicate route ID"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "data").mkdir()
                if content is not None:
                    (root / "data/work-routes.json").write_text(content)
                destination = root / "build-output"
                with patch.object(observatory, "ROOT", root):
                    with self.assertRaisesRegex(observatory.ValidationError, message):
                        observatory.build(self.data, destination)
                self.assertFalse(destination.exists())

    def test_invalid_canonical_references_are_rejected(self):
        mutations = (
            ("company_id", "missing-company", "unknown company reference"),
            ("related_company_ids", ["missing-company"], "unknown related company reference"),
            ("claim_ids", ["missing-claim"], "unknown claim reference"),
            ("source_ids", ["missing-source"], "unknown source reference"),
            ("evidence", [{"id": "missing-claim"}], "unknown evidence reference"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                work = copy.deepcopy(self.work)
                work["routes"][0][field] = value
                with self.assertRaisesRegex(observatory.ValidationError, message):
                    observatory.validate_work_routes(work, self.data)

    def test_structural_errors_are_rejected(self):
        mutations = (
            ("role", " "),
            ("claim_ids", [None]),
            ("source_ids", "a-source"),
            ("requirements", {}),
            ("sources", [{}]),
            ("evidence", [None]),
            ("related_company_ids", [{}]),
            ("numeric_pay", "false"),
            ("url", "javascript:alert(1)"),
            ("url", "https://example.com:bad/"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                work = copy.deepcopy(self.work)
                work["routes"][0][field] = value
                with self.assertRaises(observatory.ValidationError):
                    observatory.validate_work_routes(work, self.data)
        for value in (None, {}, "routes", [None]):
            with self.subTest(routes=value):
                work = copy.deepcopy(self.work)
                work["routes"] = value
                with self.assertRaises(observatory.ValidationError):
                    observatory.validate_work_routes(work, self.data)

    def test_coverage_and_empty_current_routes_are_rejected(self):
        for field in ("route_count", "organizations_total", "organizations_with_reviewed_routes", "canonical_work_claims_preserved"):
            with self.subTest(field=field):
                work = copy.deepcopy(self.work)
                work["coverage"][field] += 1
                with self.assertRaises(observatory.ValidationError):
                    observatory.validate_work_routes(work, self.data)
        work = copy.deepcopy(self.work)
        work["routes"] = []
        work["coverage"] = {key: 0 for key in work["coverage"]}
        with self.assertRaisesRegex(observatory.ValidationError, "reviewed routes missing"):
            observatory.validate_work_routes(work, self.data)
        # Self-consistent counts cannot hide a missing company's reviewed routes.
        work = copy.deepcopy(self.work)
        missing_company = work["routes"][0]["company_id"]
        work["routes"] = [row for row in work["routes"] if row["company_id"] != missing_company]
        work["coverage"]["route_count"] = len(work["routes"])
        work["coverage"]["organizations_with_reviewed_routes"] = len({row["company_id"] for row in work["routes"]})
        work["coverage"]["canonical_work_claims_preserved"] = len({value for row in work["routes"] for value in row["claim_ids"]})
        with self.assertRaisesRegex(observatory.ValidationError, "company coverage incomplete"):
            observatory.validate_work_routes(work, self.data)

    def test_selected_current_version_controls_reference_checks(self):
        work = copy.deepcopy(self.work)
        work["source_dataset_version"] = "0.0.0"
        work["routes"][0]["company_id"] = "missing-company"
        with self.assertRaisesRegex(observatory.ValidationError, "unknown company reference"):
            observatory.validate_work_routes(work, self.data)

    def test_other_selected_versions_keep_structural_checks(self):
        # Older/newer selected data may lack current curated company references.
        # The same structural contract also applies to the existing test fixture.
        for version in ("2.4.0", "2.6.0", "0.0.1"):
            with self.subTest(version=version):
                data = fixture()
                data["dataset_version"] = version
                work = copy.deepcopy(self.work)
                self.assertIs(observatory.validate_work_routes(work, data), work)
                work["routes"][0]["requirements"] = {}
                with self.assertRaisesRegex(observatory.ValidationError, "invalid requirements"):
                    observatory.validate_work_routes(work, data)


if __name__ == "__main__":
    unittest.main()
