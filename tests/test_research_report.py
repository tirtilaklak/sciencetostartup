"""Publication invariants. All invented evidence is confined to test fixtures."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from research_report import FLOORS, _audit, canonical_hash, load_report, load_edition_snapshots, publication_gate


def empty_graph():
    return {"schema_version": "1.0.0", "release_id": "test-fixture", "as_of": "2026-11-10T00:00:00Z",
            "canonical_dataset_version": "2.5.0", "canonical_sha256": "0" * 64,
            "entities": [], "sources": [], "assertions": [], "reviews": [],
            "coverage": {"frozen_core": {"entity_ids": [], "frozen_on": None, "source_cutoff": None, "sha256": None},
                         "quality_audit": None, "screening_audit": None, "notes": []}}


def test_report():
    return {"title": "Test fixture only", "release_id": "test-fixture", "updated_on": "2026-11-09",
            "status": "prelaunch", "source_cutoff": "2026-11-07T01:00:00Z", "editions": [],
            "sections": [{"id": f"chapter-{index}", "title": str(index), "paragraphs": [
                {"kind": "method", "claim_ids": [], "text": "Test fixture only."}]} for index in range(12)],
            "archive": {"status": "not_published", "doi": None}}


def approved_graph(captured_on="2026-11-06T20:00:00Z", reviewed_on="2026-11-09T20:00:00Z"):
    graph = empty_graph()
    excerpt = "Test fixture capability, never a publication claim."
    digest = hashlib.sha256(excerpt.encode()).hexdigest()
    graph["entities"] = [{"id": "fixture-supplier", "kind": "supplier", "name": "Test fixture only", "status": "approved",
                          "identifiers": {}, "aliases": [], "legacy_id": None, "family_id": None,
                          "disposition": "included", "disposition_reason": "Test fixture only.",
                          "assertion_ids": ["fixture-claim"], "eligible_core": False}]
    # The shared graph contract also carries taxonomy and release-parent fields.
    from research_graph import ENTITY_FIELDS
    if "parent_id" in ENTITY_FIELDS:
        graph["entities"][0]["parent_id"] = None
    if "review_depth" in ENTITY_FIELDS:
        graph["entities"][0]["review_depth"] = "full_source"
    if "taxonomy" in ENTITY_FIELDS:
        graph["entities"][0]["taxonomy"] = {key: [] for key in (
            "domain", "modality", "workflow", "expertise", "origin", "labels", "oversight")}
    graph["sources"] = [{"id": "fixture-source", "url": "https://example.org/test-fixture", "title": "Test fixture only",
                         "publisher": "Example", "source_type": "provider_documentation", "version": "fixture-1",
                         "published_on": "2026-11-01", "captured_on": captured_on, "status": "captured",
                         "response_sha256": "a" * 64, "excerpt": excerpt, "excerpt_sha256": digest,
                         "locator": "test-fixture", "license": None}]
    roles = ("author", "source_verifier", "adversarial")
    graph["assertions"] = [{"id": "fixture-claim", "subject_id": "fixture-supplier", "predicate": "has_capability",
                            "object_id": None, "value": {"type": "text", "value": "Test fixture only"},
                            "evidence": [{"source_id": "fixture-source", "locator": "test-fixture", "excerpt_sha256": digest}],
                            "qualifications": ["Test fixture only"], "status": "approved", "review_ids": list(roles),
                            "as_of": "2026-11-06", "provenance_kind": "first_party"}]
    graph["reviews"] = [{"id": role, "assertion_ids": ["fixture-claim"], "role": role, "reviewer": "Test fixture only",
                         "reviewer_type": "ai", "invocation_id": f"test-only-{role}", "reviewed_on": reviewed_on,
                         "verdict": "pass", "method": "source_content_review", "source_ids": ["fixture-source"],
                         "note": "Test fixture only, never research evidence."} for role in roles]
    from research_graph import assertion_digest
    for review in graph["reviews"]:
        review["assertion_sha256"] = {"fixture-claim": assertion_digest(graph["assertions"][0])}
    return graph


class ReportGateTests(unittest.TestCase):
    def test_committed_edition_snapshot_binds_path_identity_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'data/research/editions/2026-11-09.json'
            path.parent.mkdir(parents=True)
            snapshot = {'graph': empty_graph(), 'report': test_report(), 'policy': {}, 'identity': {}}
            path.write_text(json.dumps(snapshot))
            entry = {'release_id': 'test-fixture', 'snapshot_path': 'editions/2026-11-09.json',
                     'snapshot_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(load_edition_snapshots(root, {'editions': [entry]})['test-fixture'], snapshot)
            path.write_text(json.dumps({**snapshot, 'identity': {'name': 'altered'}}))
            with self.assertRaisesRegex(ValueError, 'digest'):
                load_edition_snapshots(root, {'editions': [entry]})
            entry['snapshot_path'] = '../../../outside.json'
            with self.assertRaisesRegex(ValueError, 'under data/research/editions'):
                load_edition_snapshots(root, {'editions': [entry]})

    def test_final_archive_gate_requires_verified_production_zenodo_receipt(self):
        report = test_report()
        receipt = {"status": "published", "doi": "10.5281/zenodo.12345", "record_url": "https://zenodo.org/records/12345",
                   "api_origin": "https://zenodo.org", "environment": "production", "verified": True,
                   "artifact_sha256": "a" * 64, "release_id": "test-fixture", "confirmed_on": "2026-11-10T01:00:00Z"}
        report["archive"] = receipt
        self.assertFalse(publication_gate(empty_graph(), report)["archive_reasons"])
        for changes in ({"api_origin": "https://sandbox.zenodo.org"}, {"environment": "sandbox"}, {"verified": False},
                        {"record_url": "https://example.org/records/12345"}, {"doi": "10.5281/zenodo.999"},
                        {"confirmed_on": "2026-11-10"}, {"status": "prepared"}):
            report["archive"] = {**receipt, **changes}
            self.assertTrue(publication_gate(empty_graph(), report)["archive_reasons"], changes)

    def test_audit_cannot_borrow_receipts_from_another_assertion_on_same_source(self):
        graph = approved_graph()
        graph["assertions"].append({**copy.deepcopy(graph["assertions"][0]), "id": "other-claim"})
        row = {"id": "holdout-1", "assertion_id": "other-claim", "evidence": graph["assertions"][0]["evidence"],
               "review_ids": ["source_verifier", "adversarial"], "expected_positive": True,
               "observed_positive": True, "critical_false_attribution": False, "stratum": "supplier",
               "adjudication": "Explicitly synthetic wrong-assertion fixture."}
        audit = {"kind": "reference", "status": "completed", "fixture": False,
                 "release_id": graph["release_id"], "graph_sha256": canonical_hash(graph),
                 "frozen_on": "2026-11-09T00:00:00Z", "completed_on": "2026-11-09T23:00:00Z",
                 "items": [row], "holdout_ids_sha256": canonical_hash(["holdout-1"])}
        errors, _ = _audit(audit, "reference", graph, {**FLOORS, "reference_sample_size": 1})
        self.assertTrue(any("exact assertions" in error for error in errors))
        row["assertion_id"] = "fixture-claim"
        audit["completed_on"] = "2026-11-09T19:00:00Z"
        errors, _ = _audit(audit, "reference", graph, {**FLOORS, "reference_sample_size": 1})
        self.assertTrue(any("postdates audit completion" in error for error in errors))

    def test_empty_report_and_unbound_launch_analysis_are_blocked(self):
        report = load_report(ROOT)
        report["sections"][0]["paragraphs"] = []
        self.assertTrue(any("no substantive content" in reason for reason in publication_gate(empty_graph(), report)["reasons"]))
        report["status"] = "archive_pending"
        report["sections"][0]["paragraphs"] = [{"kind": "analysis", "text": "Unbound conclusion", "claim_ids": []}]
        self.assertTrue(any("bind its research inputs" in reason for reason in publication_gate(empty_graph(), report)["reasons"]))

    def test_empty_graph_is_prelaunch(self):
        result = publication_gate(empty_graph(), test_report())
        self.assertFalse(result["ready"])
        self.assertEqual(result["coverage"]["qualifying_suppliers"], 0)
        self.assertTrue(any("Actual reference audit" in reason for reason in result["reasons"]))
        self.assertFalse(result["archival_ready"])
        self.assertTrue(result["archive_reasons"])

    def test_counterfeit_report_counts_do_not_count(self):
        report = test_report()
        report["coverage"] = {key: 10000 for key in FLOORS}
        report["status"] = "published"
        self.assertFalse(publication_gate(empty_graph(), report)["ready"])

    def test_counterfeit_graph_counts_fail_validation(self):
        graph = empty_graph()
        graph["coverage"]["qualifying_suppliers"] = 10000
        result = publication_gate(graph, test_report())
        self.assertFalse(result["ready"])
        self.assertTrue(any("Evidence graph" in reason for reason in result["reasons"]))

    def test_policy_cannot_lower_floors_or_disable_audits(self):
        policy = {"launch_floors": {key: 0 for key in FLOORS}, "archive_required": False,
                  "reference_audit_required": False, "screening_audit_required": False}
        result = publication_gate(empty_graph(), test_report(), policy)
        self.assertEqual(result["thresholds"], FLOORS)
        self.assertFalse(result["ready"])

    def test_nan_cannot_weaken_policy(self):
        result = publication_gate(empty_graph(), test_report(), {"launch_floors": {"reviewed_papers": float("nan")}})
        self.assertEqual(result["thresholds"]["reviewed_papers"], 150)

    def test_summary_only_audit_does_not_pass(self):
        fake = {"kind": "reference", "status": "completed", "fixture": False, "sample_size": 200,
                "precision": 1, "recall": 1, "release_id": "test-fixture"}
        result = publication_gate(empty_graph(), test_report(), {"audits": {"reference": fake}})
        self.assertTrue(any("actual holdout records" in reason for reason in result["reasons"]))
        self.assertFalse(result["ready"])

    def test_fixture_audit_is_rejected(self):
        errors, metrics = _audit({"kind": "reference", "status": "completed", "fixture": True, "items": []},
                                 "reference", empty_graph(), FLOORS)
        self.assertTrue(any("non-fixture" in error for error in errors))

    def test_source_before_cutoff_can_be_reviewed_later(self):
        result = publication_gate(approved_graph(), test_report())
        self.assertEqual(result["coverage"]["qualifying_suppliers"], 1)
        self.assertFalse(any("after the edition cutoff" in reason for reason in result["reasons"]))

    def test_late_source_cannot_use_later_review_to_pass(self):
        result = publication_gate(approved_graph(captured_on="2026-11-07T01:00:01Z"), test_report())
        self.assertTrue(any("after the edition cutoff" in reason for reason in result["reasons"]))

    def test_cutoff_requires_timestamp_not_calendar_date(self):
        report = test_report()
        report["source_cutoff"] = "2026-11-06"
        self.assertTrue(any("timezone-aware" in reason for reason in publication_gate(approved_graph(), report)["reasons"]))

    def test_missing_or_candidate_fact_binding_is_rejected(self):
        report = test_report()
        report["sections"][0]["paragraphs"] = [{"kind": "sourced_fact", "text": "Unverified.", "claim_ids": []}]
        self.assertTrue(any("Unbound factual" in reason for reason in publication_gate(empty_graph(), report)["reasons"]))
        report["sections"][0]["paragraphs"][0]["claim_ids"] = ["missing"]
        self.assertTrue(any("Unknown report assertion" in reason for reason in publication_gate(empty_graph(), report)["reasons"]))

    def test_real_audits_are_absent_and_report_has_twelve_chapters(self):
        self.assertEqual(len(load_report(ROOT)["sections"]), 12)
        for kind in ("reference", "screening"):
            self.assertFalse((ROOT / f"data/research/{kind}-audit.json").exists())
        self.assertEqual(load_report(ROOT)["status"], "prelaunch")


if __name__ == "__main__":
    unittest.main()
