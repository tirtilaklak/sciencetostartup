import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_public_snapshot import validate_output_path
from home import promotion_candidates
from presentation import company_graph, retain_runtime_generations


class PresentationTests(unittest.TestCase):
    def test_overview_carries_complete_claims_for_its_evidence_dialog(self):
        manifest = json.loads((ROOT / "dist/manifest.json").read_text())
        summary = json.loads((ROOT / "dist" / manifest["summary"]["href"].lstrip('/')).read_text())
        overview = json.loads((ROOT / "dist" / summary["overview"]["href"].lstrip('/')).read_text())
        canonical = json.loads((ROOT / "data/canonical.json").read_text())
        canonical_claims = {claim["id"]: claim for claim in canonical["claims"]}
        required = {cid for observation in overview["businessHealth"]["observations"] for cid in observation["claim_ids"] if cid in canonical_claims}
        actual = {claim["id"]: claim for claim in overview["data"].get("claims", [])}
        self.assertTrue(required)
        self.assertEqual(set(actual), required)
        self.assertTrue(all(actual[cid] == canonical_claims[cid] for cid in required))
        available_sources = {source["id"] for source in overview["data"].get("sources", [])}
        self.assertTrue({sid for claim in actual.values() for sid in claim["source_ids"]} <= available_sources)

    def test_nested_protected_output_and_symlinks_are_rejected(self):
        for name in ("dist/nested", "web/assets/nested", "data/versions/nested", "scripts/nested", "tests/nested"):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                validate_output_path(ROOT / name)
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / "linked"
            link.symlink_to(ROOT / "data", target_is_directory=True)
            with self.assertRaises(SystemExit):
                validate_output_path(link / "nested")
        self.assertEqual(validate_output_path(ROOT / "build/safe-output"), ROOT / "build/safe-output")

    def test_company_details_have_reference_closure(self):
        data = json.loads((ROOT / "data/canonical.json").read_text())
        for company in data["companies"]:
            graph = company_graph(data, company["id"])
            claims = {c["id"]: c for c in graph["claims"]}
            sources = {s["id"] for s in graph["sources"]}
            for claim in graph["claims"]:
                self.assertTrue(set(claim["source_ids"]) <= sources, claim["id"])
            for table in ("metrics", "products", "funding_rounds", "customer_evidence", "company_people"):
                for row in graph[table]:
                    self.assertIn(row["claim_id"], claims, row["id"])
        self.assertEqual(hashlib.sha256((ROOT / "data/canonical.json").read_bytes()).hexdigest(), "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")

    def test_only_approved_terms_receipts_qualify_and_expiry_is_explicit(self):
        route = {"id": "example", "route_kind": "named_listing", "terms_checked_on": "2026-11-08"}
        work = {"routes": [route]}
        release = {"homepage": {"work_candidate_route_ids": ["example"]}, "publication_policy": {"homepage_work_max_age_days": 3}}
        self.assertEqual(promotion_candidates(work, release), [])
        receipt = {"id": "approved", "approved": True, "scope": "key_terms", "result": "readable", "approval_basis": "source_content_review", "checked_on": "2026-11-08"}
        route["editorial_review"] = {"approved_terms_receipt_id": "approved", "receipts": [receipt]}
        candidates = promotion_candidates(work, release)
        self.assertEqual(candidates[0]["expiresAt"], "2026-11-11T00:00:00Z")
        # A failed new retrieval cannot promote a value or move the approved review date.
        route["editorial_review"]["receipts"].append({**receipt, "id": "blocked", "result": "blocked", "approved": False, "checked_on": "2026-11-10"})
        self.assertEqual(promotion_candidates(work, release), candidates)
        route["editorial_review"]["approved_terms_receipt_id"] = "blocked"
        self.assertEqual(promotion_candidates(work, release), [])

    def test_exactly_two_validated_prior_generations_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            retain_runtime_generations(ROOT, destination)
            manifest = json.loads((ROOT / "release-assets/generations.json").read_text())
            for generation in manifest["generations"]:
                for name, digest in generation["sha256"].items():
                    self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
