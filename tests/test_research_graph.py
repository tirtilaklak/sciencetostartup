"""Evidence failure cases. Synthetic review receipts exist only in these fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_graph as rg


def entity(identifier, kind="paper", **overrides):
    return {"id": identifier, "kind": kind, "name": identifier, "status": "approved",
            "identifiers": {"arxiv": "2203.02155"} if kind == "paper" else {},
            "aliases": [], "legacy_id": None, "family_id": None, "parent_id": None,
            "taxonomy": {facet: [] for facet in rg.FACETS}, "review_depth": "full_source",
            "disposition": "included", "disposition_reason": "Synthetic test scope only.",
            "assertion_ids": ["claim"], "eligible_core": False, **overrides}


def fixture():
    quote = "Synthetic fixture source evidence."
    source = {"id": "source", "url": "https://example.org/paper/v1", "title": "Synthetic fixture",
              "publisher": "Test fixture", "source_type": "paper", "version": "v1",
              "published_on": "2026-11-01", "captured_on": "2026-11-08T12:00:00Z",
              "status": "captured", "response_sha256": rg.digest(b"synthetic fixture response"),
              "excerpt": quote, "excerpt_sha256": rg.digest(quote), "locator": "Methods / paragraph 1", "license": None}
    claim = {"id": "claim", "subject_id": "paper", "predicate": "paper_method", "object_id": None,
             "value": {"type": "text", "value": "Synthetic test observation."},
             "evidence": [{"source_id": "source", "locator": source["locator"], "excerpt_sha256": rg.digest(quote)}],
             "qualifications": ["Synthetic fixture, never publish as research."], "status": "approved",
             "review_ids": sorted(rg.REVIEW_ROLES), "as_of": "2026-11-08", "provenance_kind": "first_party"}
    reviews = [{"id": role, "assertion_ids": ["claim"], "role": role, "reviewer": "Synthetic test role",
                "reviewer_type": "ai", "invocation_id": "test-only-invocation-" + role,
                "reviewed_on": "2026-11-08T13:00:00Z", "verdict": "pass", "method": "source_content_review",
                "source_ids": ["source"], "note": "Synthetic test fixture only."} for role in sorted(rg.REVIEW_ROLES)]
    graph = {"schema_version": "1.0.0", "release_id": "test-only", "as_of": "2026-11-09T00:00:00Z",
            "canonical_dataset_version": "2.5.0", "canonical_sha256": "a" * 64,
            "entities": [entity("paper")], "sources": [source], "assertions": [claim], "reviews": reviews,
            "coverage": {"frozen_core": {"entity_ids": [], "frozen_on": None, "source_cutoff": None, "sha256": None},
                         "quality_audit": None, "screening_audit": None, "notes": []}}
    for review in graph["reviews"]:
        review["assertion_sha256"] = {"claim": rg.assertion_digest(claim)}
    return graph


class ResearchGraphTests(unittest.TestCase):
    def assert_invalid(self, graph, message=None):
        with self.assertRaises(rg.GraphValidationError) as caught:
            rg.validate_graph(graph)
        if message:
            self.assertIn(message, str(caught.exception))

    def test_actual_graph_is_canonical_bound_and_honestly_prelaunch(self):
        graph = rg.load_graph(ROOT)
        summary = rg.coverage_summary(graph)
        self.assertEqual(summary["legacy_organizations"], 39)
        self.assertFalse(summary["coverage_floors_met"])
        self.assertEqual(summary["launch_floors"]["reviewed_papers"], 150)
        self.assertEqual(summary["launch_floors"]["qualifying_suppliers"], 60)
        self.assertEqual(summary["launch_floors"]["dataset_families"], 60)
        self.assertEqual(summary["launch_floors"]["benchmark_families"], 20)
        self.assertGreaterEqual(summary["captured_sources"], 9)

    def test_canonical_byte_drift_fails(self):
        graph = rg.load_graph(ROOT)
        with self.assertRaisesRegex(rg.GraphValidationError, "canonical bytes"):
            rg.validate_graph(graph, (ROOT / "data/canonical.json").read_bytes() + b"\n")

    def test_duplicate_or_missing_legacy_organization_fails(self):
        graph = rg.load_graph(ROOT)
        graph["entities"] = [e for e in graph["entities"] if e["legacy_id"] != "mercor"]
        with self.assertRaisesRegex(rg.GraphValidationError, "canonical 39"):
            rg.validate_graph(graph, (ROOT / "data/canonical.json").read_bytes())

    def test_minimum_source_bound_three_role_fixture(self):
        graph = fixture()
        rg.validate_graph(graph)
        self.assertEqual(rg.coverage_summary(graph)["reviewed_papers"], 1)

    def test_abstracts_do_not_count_as_deeply_reviewed_papers(self):
        graph = fixture()
        graph["entities"][0]["review_depth"] = "abstract"
        self.assertEqual(rg.coverage_summary(graph)["reviewed_papers"], 0)

    def test_family_rollup_counts_reviewed_manifestations_once_with_reviewed_parent(self):
        graph = fixture()
        graph['entities'] = [entity('family', kind='dataset_family', identifiers={}, family_id='test-family', assertion_ids=[]),
                             entity('release', kind='dataset_release', identifiers={}, family_id='test-family', parent_id='family')]
        graph['assertions'][0]['subject_id'] = 'release'
        for review in graph['reviews']:
            review['assertion_sha256'] = {'claim': rg.assertion_digest(graph['assertions'][0])}
        self.assertEqual(rg.coverage_summary(graph)['dataset_families'], 1)
        graph['entities'].append(entity('second-release', kind='dataset_release', identifiers={}, family_id='test-family',
                                        parent_id='family', assertion_ids=[]))
        self.assertEqual(rg.coverage_summary(graph)['dataset_families'], 1)
        graph['entities'][0]['review_depth'] = 'abstract'
        self.assertEqual(rg.coverage_summary(graph)['dataset_families'], 0)
        graph['entities'][0]['review_depth'] = 'full_source'
        graph['entities'][1]['status'] = 'candidate'
        self.assertEqual(rg.coverage_summary(graph)['dataset_families'], 0)

    def test_candidate_never_counts_even_with_three_test_receipts(self):
        graph = fixture()
        graph["assertions"][0]["status"] = "candidate"
        summary = rg.coverage_summary(graph)
        self.assertEqual(summary["approved_assertions"], 0)
        self.assertEqual(summary["reviewed_papers"], 0)
        exported = rg.public_graph(graph)
        self.assertEqual(exported["assertions"], [])
        self.assertEqual(exported["reviews"], [])
        self.assertNotIn("Synthetic test observation", rg.stable_json(exported))

    def test_single_invocation_cannot_impersonate_reviewers(self):
        graph = fixture()
        for review in graph["reviews"]:
            review["invocation_id"] = "one-test-invocation"
        self.assert_invalid(graph, "separate invocations")

    def test_missing_role_and_unresolved_review_block_approval(self):
        for change in ("missing", "negative", "metadata", "wrong_source"):
            graph = fixture()
            if change == "missing":
                graph["reviews"][0]["role"] = "author"
            elif change == "negative":
                graph["reviews"][0]["verdict"] = "revise"
            elif change == "metadata":
                graph["reviews"][0]["method"] = "metadata_review"
            else:
                graph["reviews"][0]["source_ids"] = []
            with self.subTest(change=change):
                self.assert_invalid(graph)

    def test_excerpt_tampering_and_missing_locator_fail(self):
        graph = fixture()
        graph["sources"][0]["excerpt"] += " Tampered."
        self.assert_invalid(graph, "digest mismatch")
        graph = fixture()
        graph["assertions"][0]["evidence"][0]["locator"] = ""
        self.assert_invalid(graph, "precise locator")

    def test_approved_metadata_and_historical_sources_fail(self):
        for status, kind in (("metadata_only", "metadata"), ("historical_reference", "legacy")):
            graph = fixture()
            graph["sources"][0].update(status=status, source_type=kind)
            self.assert_invalid(graph)

    def test_review_cannot_precede_capture_or_follow_graph_date(self):
        for timestamp in ("2026-11-01T00:00:00Z", "2026-11-10T00:00:00Z"):
            graph = fixture()
            graph["reviews"][0]["reviewed_on"] = timestamp
            self.assert_invalid(graph)

    def test_recips_must_be_reciprocal(self):
        graph = fixture()
        graph["assertions"][0]["review_ids"].pop()
        self.assert_invalid(graph, "reciprocal")

    def test_typed_values_and_unambiguous_object_fail_closed(self):
        for replacement in ({"type": "number", "value": True}, {"type": "date", "value": "2026-02-31"}, {"type": "number", "value": float("nan")}):
            graph = fixture()
            graph["assertions"][0]["value"] = replacement
            self.assert_invalid(graph)
        graph = fixture()
        graph["assertions"][0]["object_id"] = "paper"
        self.assert_invalid(graph, "exactly one")

    def test_work_versions_are_not_distinct_papers(self):
        graph = fixture()
        version = entity("paper.v2", "paper_version", parent_id="paper", identifiers={"arxiv": "2203.02155v2"}, assertion_ids=[])
        graph["entities"].append(version)
        self.assertEqual(rg.coverage_summary(graph)["reviewed_papers"], 1)
        duplicate = entity("paper.duplicate", identifiers={"arxiv": "https://arxiv.org/abs/2203.02155v7"}, assertion_ids=[])
        graph["entities"].append(duplicate)
        self.assert_invalid(graph, "duplicate paper work")

    def test_pmlr_published_work_needs_no_invented_arxiv_or_doi_and_deduplicates_urls(self):
        graph = fixture()
        graph['entities'][0]['identifiers'] = {'pmlr': 'v70/shi17a'}
        rg.validate_graph(graph)
        self.assertEqual(rg.coverage_summary(graph)['reviewed_papers'], 1)
        for identifier in ('https://proceedings.mlr.press/v70/shi17a.html',
                           'https://proceedings.mlr.press/v70/shi17a/shi17a.pdf'):
            with self.subTest(identifier=identifier):
                duplicate = entity('paper.duplicate', identifiers={'pmlr': identifier}, assertion_ids=[])
                self.assert_invalid({**graph, 'entities': graph['entities'] + [duplicate]}, 'duplicate paper work')
        graph['entities'][0]['identifiers']['pmlr'] = 'v70/../unverified'
        self.assert_invalid(graph, 'PMLR volume/publication key')

    def test_dataset_versions_do_not_inflate_family_counts(self):
        graph = fixture()
        graph["entities"] = [entity("paper", "dataset", family_id="family", identifiers={})]
        graph["entities"].append(entity("dataset.v2", "dataset_release", family_id="family", parent_id="paper", assertion_ids=[]))
        self.assertEqual(rg.coverage_summary(graph)["dataset_families"], 1)
        graph["entities"].append(entity("dataset.duplicate", "dataset_family", family_id="family", assertion_ids=[]))
        self.assert_invalid(graph, "duplicate dataset/benchmark family")

    def test_unknown_fields_and_invalid_types_fail_closed(self):
        graph = fixture()
        graph["entities"][0]["unreviewed_note"] = "unknown"
        self.assert_invalid(graph, "fields must be exactly")
        graph = fixture()
        graph["assertions"][0]["subject_id"] = []
        self.assert_invalid(graph)

    def test_no_inferred_supplier_coverage_from_contribution_alone(self):
        graph = fixture()
        graph["entities"][0]["kind"] = "supplier"
        self.assertEqual(rg.coverage_summary(graph)["qualifying_suppliers"], 0)
        graph["assertions"][0]["predicate"] = "has_capability"
        for review in graph["reviews"]:
            review["assertion_sha256"] = {"claim": rg.assertion_digest(graph["assertions"][0])}
        self.assertEqual(rg.coverage_summary(graph)["qualifying_suppliers"], 1)

    def test_review_receipts_cannot_be_reused_after_assertion_wording_changes(self):
        graph = fixture()
        graph["assertions"][0]["value"]["value"] = "A different unsupported observation."
        self.assert_invalid(graph, "reviewed assertion content changed")

    def test_frozen_core_requires_exact_hash_and_identities(self):
        graph = fixture()
        graph["entities"][0]["eligible_core"] = True
        self.assert_invalid(graph, "exactly match frozen")
        graph["coverage"]["frozen_core"] = {"entity_ids": ["paper"], "frozen_on": "2026-11-01T00:00:00Z", "source_cutoff": "2026-11-06T17:00:00Z", "sha256": rg.digest(rg.stable_json(["paper"]))}
        self.assertEqual(rg.coverage_summary(graph)["core_disposition_rate"], 1.0)
        graph["coverage"]["frozen_core"]["sha256"] = "a" * 64
        self.assert_invalid(graph, "core hash mismatch")

    def test_core_work_disposition_uses_reviewed_exact_version_without_copying_claims(self):
        graph = fixture()
        graph['entities'][0].update(kind='paper_work', assertion_ids=[], eligible_core=True)
        graph['entities'].append(entity('paper.v1', kind='paper_version', parent_id='paper',
                                        identifiers={'arxiv': '2203.02155v1'}))
        graph['assertions'][0]['subject_id'] = 'paper.v1'
        for review in graph['reviews']:
            review['assertion_sha256'] = {'claim': rg.assertion_digest(graph['assertions'][0])}
        graph['coverage']['frozen_core'] = {'entity_ids': ['paper'], 'frozen_on': '2026-11-08T00:00:00Z',
            'source_cutoff': '2026-11-07T17:00:00Z', 'sha256': rg.digest(rg.stable_json(['paper']))}
        self.assertEqual(rg.coverage_summary(graph)['core_disposition_rate'], 1.0)
        self.assertEqual(graph['entities'][0]['assertion_ids'], [])
        baseline = copy.deepcopy(graph)
        for entity_index in (0, 1):
            for field, value in (('review_depth', 'abstract'), ('status', 'candidate'), ('disposition', 'pending')):
                altered = copy.deepcopy(baseline)
                altered['entities'][entity_index][field] = value
                self.assertEqual(rg.coverage_summary(altered)['core_dispositioned'], 0, (entity_index, field))
        graph['assertions'][0]['status'] = 'candidate'
        self.assertEqual(rg.coverage_summary(graph)['core_dispositioned'], 0)

    def test_frozen_core_cannot_inflate_units_with_paper_versions(self):
        graph = fixture()
        graph['entities'].append(entity('paper.v2', kind='paper_version', identifiers={'arxiv':'2203.02155v2'},
                                        parent_id='paper', assertion_ids=[], eligible_core=True))
        graph['coverage']['frozen_core'] = {'entity_ids': ['paper.v2'], 'frozen_on': '2026-11-08T00:00:00Z',
            'source_cutoff': '2026-11-07T17:00:00Z', 'sha256': rg.digest(rg.stable_json(['paper.v2']))}
        self.assert_invalid(graph, 'versions and releases cannot inflate disposition')

    def test_core_disposition_requires_substantive_review_and_preserves_supported_exclusions(self):
        graph = fixture()
        graph['entities'][0]['eligible_core'] = True
        graph['coverage']['frozen_core'] = {'entity_ids': ['paper'], 'frozen_on': '2026-11-08T00:00:00Z',
            'source_cutoff': '2026-11-07T17:00:00Z', 'sha256': rg.digest(rg.stable_json(['paper']))}
        baseline = copy.deepcopy(graph)
        for field, value in (('review_depth', 'abstract'), ('status', 'candidate'), ('disposition', 'pending')):
            altered = copy.deepcopy(baseline)
            altered['entities'][0][field] = value
            self.assertEqual(rg.coverage_summary(altered)['core_dispositioned'], 0, field)
        graph['entities'][0].update(status='excluded', disposition='excluded')
        summary = rg.coverage_summary(graph)
        self.assertEqual(summary['core_dispositioned'], 1)
        self.assertEqual(summary['reviewed_papers'], 0)
        graph['assertions'][0]['status'] = 'candidate'
        self.assertEqual(rg.coverage_summary(graph)['core_dispositioned'], 0)

    def test_private_extensions_are_removed_and_free_text_email_redacted(self):
        graph = fixture()
        graph["entities"][0]["private_email"] = "person@example.org"
        graph["entities"][0]["disposition_reason"] += " Contact person@example.org."
        graph["raw_body"] = "person@example.org"
        projected = rg.public_graph(graph)
        self.assertNotIn("person@example.org", rg.stable_json(projected))
        self.assertNotIn("private_email", projected["entities"][0])
        self.assertNotIn("raw_body", projected)

    def test_graph_rejects_emails_and_credentials_in_any_public_text(self):
        for value in ("person@example.org", "sk-proj-" + "a" * 30):
            graph = fixture()
            graph["coverage"]["notes"] = [value]
            self.assert_invalid(graph)

    def test_credential_bearing_source_url_rejected(self):
        graph = fixture()
        graph["sources"][0]["url"] = "https://example.org/?api_key=secret"
        self.assert_invalid(graph, "credential-free HTTPS")

    def test_export_is_deterministic_private_filtered_and_queryable(self):
        graph = fixture()
        graph["entities"][0]["email"] = "person@example.org"
        graph["entities"][0]["name"] = "=IMPORTDATA(unsafe)"
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory) / "left", Path(directory) / "right"
            first, second = rg.write_exports(graph, left), rg.write_exports(graph, right)
            self.assertEqual(first, second)
            for name in first:
                self.assertEqual((left / name).read_bytes(), (right / name).read_bytes(), name)
                self.assertNotIn(b"person@example.org", (left / name).read_bytes())
            self.assertIn("'=IMPORTDATA", (left / "research-entities.csv").read_text())
            with sqlite3.connect(left / "research-graph.sqlite") as db:
                self.assertEqual(db.execute("SELECT count(*) FROM assertion_evidence").fetchone()[0], 1)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            manifest = json.loads((left / "research-exports-manifest.json").read_text())
            for name, expected in manifest["files"].items():
                self.assertEqual(hashlib.sha256((left / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
