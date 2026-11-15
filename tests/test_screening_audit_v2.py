"""Synthetic harness controls only: no actual audit/receipt/admission is written.

In-memory simulated trust rows let attacks reach semantic checks without being
rejected merely by stale hashes. Their invocation strings are invented fixture
data and establish no actual execution or scientific source review.
"""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import screening_audit_v2 as sut
from research_audit_dispatch import validate_audit


def blob(value):
    return json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"


def reseal(audit):
    for truth in audit["truths"]:
        digest = sut.canonical_hash({k: v for k, v in truth.items() if k != "review_receipts"})
        for review in truth["review_receipts"]:
            review["decision_sha256"] = digest
    predictions = {row["record_id"]: row for row in audit["predictions"]}
    for check in audit["prediction_source_checks"]:
        check["prediction_sha256"] = sut.canonical_hash(predictions.get(check["record_id"]))
    audit["frame_sha256"] = sut.canonical_hash(audit["frame"])
    audit["method_sha256"] = sut.canonical_hash(audit["method"])
    if "original200" in audit:
        truth_index = {t["record_id"]: t for t in audit["truths"]}
        audit["original200"]["current_canonical_mappings"] = [{"record_id": r["record_id"],
            "current_state": truth_index[r["record_id"]]["state"],
            "logical_id": truth_index[r["record_id"]]["logical_id"],
            "related_logical_ids": truth_index[r["record_id"]]["related_logical_ids"]}
            for r in audit["original200"]["records"]]
    audit["commitments"] = {
        "predictions_sha256": sut.canonical_hash(audit["predictions"]),
        "truth_sha256": sut.canonical_hash(audit["truths"]),
        "prediction_source_checks_sha256": sut.canonical_hash(audit["prediction_source_checks"]),
        "membership_sha256": sut.canonical_hash(audit["selected_record_ids"])}
    return audit


def fixture():
    graph = {"release_id": "SYNTHETIC-NOT-RESEARCH"}
    h = sut.canonical_hash("synthetic fixture")
    evidence = [{"source_id": "synthetic-source", "locator": "synthetic section",
                 "reading_scope_sha256": h}]
    method = {key: h for key in ("adoption_sha256", "policy_sha256", "sut_instructions_sha256",
        "input_projection_sha256", "implementation_sha256", "exposure_registry_sha256",
        "truth_input_projection_sha256", "prediction_check_input_projection_sha256")}
    frame, truths, predictions, checks = [], [], [], []
    for stratum, count in sut.HISTORICAL_FRAME_COUNTS.items():
        for i in range(count):
            rid = f"SYNTHETIC.{stratum}.{i:03d}"
            frame.append({"record_id": rid, "stratum": stratum})
            truths.append({"record_id": rid, "state": "eligible", "logical_id": rid,
                "route": "D" if stratum == "supplier" else "A", "evidence": copy.deepcopy(evidence),
                "related_logical_ids": [],
                "review_receipts": [{"invocation_id": run, "decision_sha256": h, "receipt_sha256": h}
                                    for run in ("synthetic-truth", "synthetic-adverse")]})
            prediction = {"record_id": rid, "state": "eligible", "mandatory_workload_retained": True,
                "logical_id": rid, "route": "D" if stratum == "supplier" else "A",
                "evidence": copy.deepcopy(evidence), "related_logical_ids": [], "invocation_id": "synthetic-sut"}
            predictions.append(prediction)
            checks.append({"record_id": rid, "prediction_sha256": h, "source_supported": True,
                "critical_false_attribution": False, "invocation_id": "synthetic-check", "receipt_sha256": h})
    runs = []
    for name, role, start, end in [
        ("synthetic-sut", "sut", "02:00:00", "02:30:00"),
        ("synthetic-truth", "source_adjudicator", "04:00:00", "04:30:00"),
        ("synthetic-adverse", "adversarial_adjudicator", "04:00:00", "04:30:00"),
        ("synthetic-check", "prediction_source_verifier", "07:00:00", "07:30:00")]:
        runs.append({"invocation_id": name, "role": role, "reviewer": "synthetic fixture",
            "started_on": f"2020-01-01T{start}+00:00", "completed_on": f"2020-01-01T{end}+00:00",
            "input_projection_sha256": h, "actual_execution": True, "fixture": False,
            "source_observations_frozen_on": "2020-01-01T04:15:00+00:00" if role in {
                "source_adjudicator", "adversarial_adjudicator"} else None,
            "source_observations_sha256": h if role in {
                "source_adjudicator", "adversarial_adjudicator"} else None})
    artifacts = {key: h for key in ("historical_frame_sha256", "historical200_key_sha256",
        "instructions_artifact_sha256", "source_packet_artifact_sha256", "sut_output_artifact_sha256",
        "blind_truth_artifacts_sha256", "prediction_source_checks_artifact_sha256",
        "exposure_registry_artifact_sha256", "identity_mapping_artifact_sha256",
        "private_execution_evidence_sha256")}
    artifacts.update({"historical_frame_sha256": sut.HISTORICAL_FRAME_SHA256,
                      "historical200_key_sha256": sut.HISTORICAL_200_KEY_SHA256})
    audit = {"schema_version": sut.VERSION, "kind": "screening", "evaluation_kind": sut.KIND,
        "status": "completed", "fixture": False, "actual_execution": True,
        "release_id": graph["release_id"], "graph_sha256": sut.canonical_hash(graph),
        "frame_sha256": h, "method_sha256": h, "method": method, "artifact_commitments": artifacts,
        "selection": {"algorithm": "sha256_seed_original_id_first_eligible_canonical_v1",
                      "seed": sut.HISTORICAL_SEED, "quotas": dict(sut.HISTORICAL_QUOTAS)},
        "sources": [{"id": "synthetic-source", "url": "https://example.org/synthetic",
            "version": "synthetic", "captured_on": "2020-01-01T00:00:00+00:00", "response_sha256": h,
            "graph_source_id":None, "graph_source_record_sha256":None}],
        "frame": frame, "predictions": predictions, "truths": truths, "prediction_source_checks": checks,
        "selected_record_ids": sut.select_screening_panel(frame, truths), "runs": runs,
        "chronology": {name: f"2020-01-01T{time}+00:00" for name, time in [
            ("method_frozen_on", "01:00:00"), ("sut_started_on", "02:00:00"),
            ("predictions_sealed_on", "03:00:00"), ("truth_started_on", "04:00:00"),
            ("truth_sealed_on", "05:00:00"), ("membership_sealed_on", "06:00:00"),
            ("source_checks_started_on", "07:00:00"), ("source_checks_sealed_on", "08:00:00"),
            ("outcomes_opened_on", "09:00:00"), ("scored_on", "10:00:00")]},
        "commitments": {}, "limitations": ["exposed_enriched_fixed_frame",
            "post_remediation_not_untouched_holdout", "conditional_recovery_not_discovery_recall",
            "no_population_generalization"]}
    by_id = {r["record_id"]: r for r in frame}
    audit["original200"] = {"key_sha256": sut.HISTORICAL_200_KEY_SHA256,
        "records": [{"id": f"SYNTHETIC.old.case.{i:03d}", "record_id": rid,
            "stratum": by_id[rid]["stratum"], "screening_eligibility": "true" if i < 187 else "unknown"}
            for i, rid in enumerate(audit["selected_record_ids"])], "current_canonical_mappings": []}
    return reseal(audit), graph


def simulated_admitted(audit, graph):
    """Invented in-memory fixture trust; never an actual admission creator."""
    audit_bytes = blob(audit)
    h = sut.canonical_hash("synthetic receipt fixture")
    pins = {name: sut.byte_hash((ROOT / name).read_bytes()) for name in sut.CODE_FILES}
    receipt = {"schema_version": sut.RECEIPT_VERSION, "audit_sha256": sut.byte_hash(audit_bytes),
        "graph_sha256": sut.canonical_hash(graph), "method_sha256": audit["method_sha256"],
        "validator_code_pins": pins, "private_artifact_pins_sha256": sut.canonical_hash(audit["artifact_commitments"]),
        "source_authentication_sha256": sut.canonical_hash(sorted({s["response_sha256"] for s in audit["sources"]})),
        "validation_run": {"invocation_id": "synthetic-validation", "reviewer": "synthetic fixture",
            "validated_on": "2020-01-01T11:00:00+00:00", "actual_execution": True, "fixture": False},
        "validation_errors": []}
    receipt_bytes = blob(receipt)
    admission = {"schema_version": sut.ADMISSION_VERSION, "status": "accepted",
        "audit_sha256": sut.byte_hash(audit_bytes), "receipt_sha256": sut.byte_hash(receipt_bytes),
        "validator_capsule_sha256": sut.canonical_hash(pins), "validation_invocation_id": "synthetic-validation",
        "independent_review_invocation_id": "synthetic-independent-review", "independent_reviewer": "synthetic fixture",
        "independent_review_sha256": h, "reviewed_on": "2020-01-01T12:00:00+00:00",
        "admitted_on": "2020-01-01T13:00:00+00:00", "method_adoption_sha256": audit["method"]["adoption_sha256"],
        "completion_authorized": True}
    return audit_bytes, receipt_bytes, admission


class ScreeningAuditControls(unittest.TestCase):
    def setUp(self):
        self.audit, self.graph = fixture()

    def read(self, *, audit=None, mutate_admission=None, thresholds=None):
        a = reseal(audit or self.audit)
        ab, rb, admission = simulated_admitted(a, self.graph)
        if mutate_admission:
            mutate_admission(admission)
        return sut.validate_public_screening_audit(ab, self.graph, rb,
            trusted_admission=admission, thresholds=thresholds)

    def test_synthetic_positive_control_only(self):
        errors, metrics = self.read()
        self.assertEqual(errors, [])
        self.assertEqual(metrics["recovered"], 200)
        self.assertTrue(metrics["publication_eligible"])

    def test_no_prediction_input_to_selection(self):
        self.assertNotIn("predictions", inspect.signature(sut.select_screening_panel).parameters)
        original = self.audit["selected_record_ids"]
        for p in self.audit["predictions"]:
            p["state"] = "unknown"
        self.assertEqual(original, sut.select_screening_panel(self.audit["frame"], self.audit["truths"]))
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["recovered"], 0)

    def test_identifier_only_is_not_recovery(self):
        for p in self.audit["predictions"]:
            p["evidence"] = []
        errors, metrics = self.read()
        self.assertTrue(any("source proof" in e for e in errors))
        self.assertEqual(metrics["recovered"], 0)

    def test_all_eligible_without_independent_source_support(self):
        for check in self.audit["prediction_source_checks"]:
            check["source_supported"] = False
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["recovered"], 0)

    def test_wrong_logical_identity_misses_recovery(self):
        chosen = set(self.audit["selected_record_ids"][:11])
        for p in self.audit["predictions"]:
            if p["record_id"] in chosen:
                p["logical_id"] = "SYNTHETIC.WRONG"
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["recovered"], 189)

    def test_major_stratum_floor_is_independent_of_190_total(self):
        chosen = {rid for rid in self.audit["selected_record_ids"] if ".benchmark." in rid}
        for p in [p for p in self.audit["predictions"] if p["record_id"] in chosen][:3]:
            p["state"] = "unknown"
        errors, metrics = self.read()
        self.assertEqual(metrics["recovered"], 197)
        self.assertEqual(metrics["strata"]["benchmark"]["recall"], .88)
        self.assertTrue(errors)

    def test_no_quota_transfer_after_canonical_collapse(self):
        for t in self.audit["truths"]:
            if ".dataset." in t["record_id"]:
                t["logical_id"] = "SYNTHETIC.ONE.FAMILY"
        self.audit["selected_record_ids"] = sut.select_screening_panel(self.audit["frame"], self.audit["truths"])
        errors, metrics = self.read()
        self.assertEqual(metrics["strata"]["dataset"]["eligible"], 1)
        self.assertLess(metrics["sample_size"], 200)
        self.assertTrue(errors)

    def test_nonunit_and_unknown_full_frame_rows_remain(self):
        unselected = [t for t in self.audit["truths"] if t["record_id"] not in self.audit["selected_record_ids"]]
        unselected[0].update(state="not_logical_unit", logical_id=None)
        unselected[1].update(state="unknown", logical_id=None)
        errors, metrics = self.read()
        self.assertEqual(errors, [])
        self.assertEqual(metrics["frame_size"], 269)
        self.assertEqual(metrics["frame_truth_states"]["unknown"], 1)
        self.assertEqual(metrics["frame_eligible_predictions_by_truth_state"]["not_logical_unit"], 1)

    def test_original200_unknown_is_preserved_when_new_truth_resolves_nonunits(self):
        original_rows = copy.deepcopy(self.audit["original200"]["records"])
        changed = {r["record_id"] for r in original_rows[-2:]}
        for truth in self.audit["truths"]:
            if truth["record_id"] in changed:
                truth.update(state="not_logical_unit", logical_id=None)
        self.audit["selected_record_ids"] = sut.select_screening_panel(self.audit["frame"], self.audit["truths"])
        errors, metrics = self.read()
        self.assertEqual(errors, [])
        self.assertEqual(self.audit["original200"]["records"], original_rows)
        sensitivity = metrics["original200_sensitivity"]
        self.assertEqual(sensitivity["preserved_original_eligibility"], {"true":187,"false":0,"unknown":13})
        self.assertEqual(sensitivity["current_distinct_eligible_logical_units"], 198)
        self.assertFalse(sensitivity["completes_contract"])
        self.assertEqual(metrics["sample_size"], 200)

    def test_missing_complete_frame_output(self):
        self.audit["predictions"].pop()
        errors, _ = self.read()
        self.assertTrue(errors)

    def test_membership_cannot_be_swapped_after_predictions(self):
        self.audit["selected_record_ids"][0] = "SYNTHETIC.supplier.083"
        errors, _ = self.read()
        self.assertTrue(any("membership" in e for e in errors))

    def test_seed_change_fails_even_when_all_hashes_resealed(self):
        self.audit["selection"]["seed"] = "score-optimized seed"
        self.audit["selected_record_ids"] = sut.select_screening_panel(self.audit["frame"], self.audit["truths"], seed="score-optimized seed")
        errors, _ = self.read()
        self.assertTrue(any("seed/rank" in e for e in errors))

    def test_truth_before_prediction_seal(self):
        self.audit["chronology"]["truth_started_on"] = "2020-01-01T02:01:00+00:00"
        errors, _ = self.read()
        self.assertTrue(any("chronology" in e for e in errors))

    def test_late_captured_source(self):
        self.audit["sources"][0]["captured_on"] = "2020-01-01T01:30:00+00:00"
        errors, _ = self.read()
        self.assertTrue(any("captured after" in e for e in errors))

    def test_bound_graph_source_cannot_hide_different_capture_date(self):
        original = {k:v for k,v in self.audit["sources"][0].items() if not k.startswith("graph_")}
        original["captured_on"] = "2030-01-01T00:00:00+00:00"
        self.graph["sources"] = [original]
        self.audit["graph_sha256"] = sut.canonical_hash(self.graph)
        self.audit["sources"][0].update(graph_source_id=original["id"],
            graph_source_record_sha256=sut.canonical_hash(original))
        errors, _ = self.read()
        self.assertTrue(any("original graph record" in e for e in errors))

    def test_shared_truth_and_sut_invocation(self):
        self.audit["truths"][0]["review_receipts"][0]["invocation_id"] = "synthetic-sut"
        errors, _ = self.read()
        self.assertTrue(any("independent" in e for e in errors))

    def test_source_only_notes_must_precede_truth_key(self):
        self.audit["runs"][1]["source_observations_frozen_on"] = self.audit["runs"][1]["completed_on"]
        errors, _ = self.read()
        self.assertTrue(any("source-only" in e for e in errors))

    def test_fixture_run_rejected(self):
        self.audit["runs"][0]["fixture"] = True
        errors, _ = self.read()
        self.assertTrue(any("non-fixture" in e for e in errors))

    def test_changed_projection_rejected(self):
        self.audit["runs"][0]["input_projection_sha256"] = "a" * 64
        errors, _ = self.read()
        self.assertTrue(any("projection" in e for e in errors))

    def test_critical_true_and_unknown_rejected(self):
        rid = self.audit["selected_record_ids"][0]
        check = next(c for c in self.audit["prediction_source_checks"] if c["record_id"] == rid)
        for value in (True, None):
            check["critical_false_attribution"] = value
            errors, metrics = self.read()
            self.assertTrue(metrics["numerical_thresholds_met"])
            self.assertTrue(errors)
            self.assertFalse(metrics["publication_eligible"])

    def test_no_self_admission_or_completion_from_numeric_success(self):
        errors, metrics = self.read(mutate_admission=lambda a: a.update(completion_authorized=False))
        self.assertTrue(metrics["numerical_thresholds_met"])
        self.assertFalse(metrics["publication_eligible"])
        ab, rb, _ = simulated_admitted(self.audit, self.graph)
        errors, _ = sut.validate_public_screening_audit(ab, self.graph, rb, trusted_admission=None)
        self.assertTrue(errors)

    def test_unknown_schema_cannot_fall_back(self):
        self.audit["schema_version"] = "invented-version"
        errors, _ = self.read()
        self.assertTrue(errors)

    def test_lower_threshold_rejected(self):
        errors, _ = self.read(thresholds={"screening_recovered": 189})
        self.assertTrue(any("Cannot lower" in e for e in errors))

    def test_duplicate_and_nonfinite_json_rejected(self):
        for value in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                sut.load_exact(value)

    def test_credential_query_and_local_path_rejected(self):
        for value in ("https://example.org/?%74oken=secret", "/Users/synthetic/cache"):
            self.audit["sources"][0]["url"] = value
            errors, _ = self.read()
            self.assertTrue(errors)

    def test_dispatch_keeps_legacy_reader_and_never_retries_unknown_version(self):
        calls = []
        def legacy(audit, kind, graph, thresholds):
            calls.append(kind)
            return ["explicit synthetic legacy result"], {}
        errors, _ = validate_audit("screening", blob({"kind":"screening"}), self.graph,
                                    sut.FLOORS, legacy_reader=legacy)
        self.assertEqual(calls, ["screening"])
        self.assertEqual(errors, ["explicit synthetic legacy result"])
        errors, _ = validate_audit("screening", blob({"kind":"screening", "schema_version":"invented"}),
                                  self.graph, sut.FLOORS, legacy_reader=legacy)
        self.assertTrue(errors)
        self.assertEqual(calls, ["screening"])
        errors, _ = validate_audit("screening", blob({"kind":"screening", "schema_version":None}),
                                  self.graph, sut.FLOORS, legacy_reader=legacy)
        self.assertTrue(errors)
        self.assertEqual(calls, ["screening"])

    def test_wrong_current_graph_is_not_retargeted(self):
        ab, rb, admission = simulated_admitted(self.audit, self.graph)
        errors, metrics = sut.validate_public_screening_audit(ab, {**self.graph,"unrelated":"addition"}, rb,
                                                              trusted_admission=admission)
        self.assertTrue(errors)
        self.assertFalse(metrics["publication_eligible"])

    def test_private_held_authentication_cannot_become_clean_public_result(self):
        ab = blob(self.audit)
        receipt_bytes = sut.validate_private_screening_execution(ab, self.graph,
            expected_artifact_hashes=dict(self.audit["artifact_commitments"]), artifact_payloads={},
            source_payloads={}, invocation_id="synthetic-private-validation", reviewer="synthetic fixture", fixture=True)
        receipt = sut.load_exact(receipt_bytes)
        self.assertTrue(any("Original artifact authentication failed" in e for e in receipt["validation_errors"]))
        self.assertTrue(any("original authenticated bytes" in e for e in receipt["validation_errors"]))
        errors, _ = sut.validate_public_screening_audit(ab, self.graph, receipt_bytes, trusted_admission=None)
        self.assertTrue(errors)

    def test_private_validation_holds_are_preserved_even_under_simulated_admission(self):
        ab, rb, admission = simulated_admitted(self.audit, self.graph)
        receipt = sut.load_exact(rb)
        receipt["validation_errors"] = ["SYNTHETIC PRESERVED HOLD"]
        rb = blob(receipt)
        admission["receipt_sha256"] = sut.byte_hash(rb)
        errors, metrics = sut.validate_public_screening_audit(ab, self.graph, rb, trusted_admission=admission)
        self.assertIn("SYNTHETIC PRESERVED HOLD", errors)
        self.assertTrue(metrics["numerical_thresholds_met"])
        self.assertFalse(metrics["publication_eligible"])

    def test_old_issuer_capsule_cannot_validate_new_reader(self):
        ab, rb, admission = simulated_admitted(self.audit, self.graph)
        receipt = sut.load_exact(rb)
        receipt["validator_code_pins"]["scripts/screening_audit_v2.py"] = "a"*64
        rb = blob(receipt)
        admission.update(receipt_sha256=sut.byte_hash(rb),
                         validator_capsule_sha256=sut.canonical_hash(receipt["validator_code_pins"]))
        errors, _ = sut.validate_public_screening_audit(ab, self.graph, rb, trusted_admission=admission)
        self.assertTrue(any("capsule" in e for e in errors))

    def test_dispatch_screening_v2_requires_separate_receipt_and_admission(self):
        ab, rb, admission = simulated_admitted(self.audit, self.graph)
        errors, _ = validate_audit("screening", ab, self.graph, sut.FLOORS)
        self.assertTrue(errors)
        errors, metrics = validate_audit("screening", ab, self.graph, sut.FLOORS,
            validation_receipt_bytes=rb, trusted_admission=admission)
        self.assertEqual(errors, [])
        self.assertTrue(metrics["publication_eligible"])

    def test_dispatch_reference_v2_only_to_explicit_public_reader(self):
        calls = []
        def reference(*args, **kwargs):
            calls.append(kwargs)
            return ["synthetic held reference"], {"publication_eligible":False}
        errors, metrics = validate_audit("reference", blob({"kind":"reference", "schema_version":"reference-audit-v2"}),
            self.graph, sut.FLOORS, validation_receipt_bytes=b"{}", trusted_admission={"synthetic":True},
            reference_reader=reference)
        self.assertEqual(errors, ["synthetic held reference"])
        self.assertFalse(metrics["publication_eligible"])
        self.assertEqual(calls[0]["trusted_admission"], {"synthetic":True})


if __name__ == "__main__":
    unittest.main()
