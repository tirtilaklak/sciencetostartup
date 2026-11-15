"""FIXTURE_ONLY: invented in-memory records; never research or real admissions.

Mock provenance intentionally exercises both success and failure branches. All
private validation receipts produced here are fixture=True and remain inadmissible.
No current corpus, candidates, exposure artifacts, source bytes or gold is read.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import reference_audit_v4 as v4
import reference_audit_v3 as historical
import research_graph as rg
from test_reference_audit_v3 import fixture as invented_v3_fixture
from test_research_graph import fixture as tiny_fixture

FIXTURE_ONLY = True


def blob(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def ref(artifact, pointer, value):
    return {"artifact_id": artifact, "entry_pointer": pointer, "entry_sha256": v4.canonical_hash(value)}


def reseal(audit):
    audit["method_sha256"] = v4.canonical_hash(audit["method"])
    audit["frame_sha256"] = v4.canonical_hash(audit["frame"])
    audit["commitments"] = {k: v4.canonical_hash(v) for k, v in (
        ("bindings_sha256", audit["bindings"]), ("truth_sha256", audit["truth"]),
        ("membership_sha256", audit["selected_assertion_ids"]))}
    return audit


def fixture_only():
    assert FIXTURE_ONLY
    audit, graph = invented_v3_fixture()
    audit.update(schema_version=v4.VERSION, evaluation_kind=v4.KIND, limitations=sorted(v4.LIMITATIONS))
    h = v4.canonical_hash("SYNTHETIC v4 fixture only")
    exposure = audit["exposure_registry"]
    exposure["lineage_keys"] = [v4.canonical_hash("SYNTHETIC old exposed lineage")]
    payloads = {"source_packet": b"SYNTHETIC neutral scoped source packet; fixture only",
        "method_adoption": b"SYNTHETIC mock method adoption; never actual authorization",
        "exposure_semantic_review": b"SYNTHETIC mock exposure semantic original"}
    for scope in v4.EXPOSURE_SCOPES:
        payloads["exposure_" + scope] = ("SYNTHETIC preserved " + scope).encode()
        exposure["source_artifact_pins"][scope] = v4.byte_hash(payloads["exposure_" + scope])
    exposure["semantic_review_sha256"] = v4.byte_hash(payloads["exposure_semantic_review"])
    submissions, peers, histories, lineages, curation = [], [], [], [], []
    for i, claim in enumerate(graph["assertions"]):
        original = copy.deepcopy(claim)
        original.update(status="candidate", review_ids=[])
        submission = {"assertion": original, "sources": copy.deepcopy(graph["sources"])}
        submissions.append(submission)
        submission_ref = ref("original_submissions", f"/records/{i}", submission)
        peer = {"assertion_id": claim["id"], "scientific_sha256": rg.assertion_digest(original),
            "submission_entry_sha256": submission_ref["entry_sha256"],
            "source_record_sha256": {s["id"]: v4.canonical_hash(s) for s in graph["sources"]},
            "event": "peer_submission", "received_on": "2026-11-08T12:30:00Z",
            "invocation_id": f"SYNTHETIC.receiving-peer.{i}", "reviewer": "SYNTHETIC receiving peer",
            "actual_execution": True, "fixture": False}
        peers.append(peer)
        history = {"assertion_ids": [claim["id"]], "initial_id": claim["id"],
            "original_event_kind": "SYNTHETIC original production history; fixture only"}
        histories.append(history)
        lineage = v4.canonical_hash("SYNTHETIC lineage " + claim["id"])
        lineages.append({"lineage_sha256": lineage, "first_assertion_id": claim["id"],
            "member_assertion_ids": [claim["id"]], "history_ref": ref("original_histories", f"/records/{i}", history),
            "submissions": [{"assertion_id": claim["id"], "first_peer_submitted_on": peer["received_on"],
                "submission_ref": submission_ref, "peer_receipt_ref": ref("original_peer_receipts", f"/records/{i}", peer)}]})
        curation.append({"assertion_id": claim["id"], "lineage_sha256": lineage,
            "disposition": "include", "scope_kind": "substantive_scientific_finding",
            "finding_equivalence_sha256": v4.canonical_hash(claim["id"]),
            "reason": "SYNTHETIC independent curation fixture only"})
    payloads["original_submissions"] = blob({"records": submissions})
    payloads["original_peer_receipts"] = blob({"records": peers})
    payloads["original_histories"] = blob({"records": histories})
    manifest = {"population_rule": v4.POPULATION_RULE, "input_graph_sha256": v4.canonical_hash(graph), "lineages": lineages}
    adaptations = {"records": []}
    payloads.update(lineage_manifest=blob(manifest), frame_curation=blob({"records": curation}),
        metadata_adaptations=blob(adaptations), exposure_registry=blob(exposure), input_graph=blob(graph),
        sut_output=blob(rg.public_graph(graph)))
    audit["frame"] = v4.build_reference_frame(graph, curation, exposure, manifest,
        artifact_payloads=payloads, metadata_adaptations=adaptations)
    audit["selected_assertion_ids"] = v4.select_reference_panel(audit["frame"])
    output_ids = {a["id"] for a in rg.public_graph(graph)["assertions"]}
    audit["bindings"] = v4.sampled_bindings(graph, audit["selected_assertion_ids"], output_ids)
    truth_by_id = {t["assertion_id"]: t for t in audit["truth"]}
    audit["truth"] = [truth_by_id[aid] for aid in audit["selected_assertion_ids"]]
    method = audit["method"]
    method.update(seed=v4.SEED, population_rule=v4.POPULATION_RULE,
        source_packet_sha256=v4.byte_hash(payloads["source_packet"]), adoption_sha256=v4.byte_hash(payloads["method_adoption"]))
    for run in audit["runs"]:
        is_sut = run["role"] == "sut"
        run.update(requested_model="not_applicable" if is_sut else "gpt-6.1-sol", requested_reasoning="not_applicable" if is_sut else "ultra",
            runtime_model="unknown", runtime_model_attestation_sha256=None, runtime_model_attestation_artifact_id=None,
            source_context_recheck_started_on=None if is_sut else "2026-11-10T07:01:00Z",
            source_context_recheck_completed_on=None if is_sut else "2026-11-10T07:10:00Z",
            hypotheses_opened_on=None if is_sut else "2026-11-10T07:16:00Z",
            decisions_started_on=None if is_sut else "2026-11-10T07:17:00Z",
            source_context_recheck_artifact_id=None if is_sut else run["invocation_id"] + ".context",
            source_context_recheck_sha256=None, preparatory_notes_artifact_id=None,
            preparatory_notes_sha256=None, preparatory_reading_disclosed=True,
            blind_to_other_truth_and_old_judgments=not is_sut)
        if not is_sut:
            run["input_projection_sha256"] = method["source_packet_sha256"]
            scopes = [{"source_id": "source", "response_sha256": graph["sources"][0]["response_sha256"],
                "reading_scope_sha256": h, "locator": "Synthetic source reading only"}]
            notes = {"invocation_id": run["invocation_id"], "frozen_on": run["source_observations_frozen_on"],
                "source_packet_sha256": method["source_packet_sha256"], "records": scopes,
                "supplemental_preparatory_notes_sha256": None}
            payloads[run["source_observations_artifact_id"]] = blob(notes)
            run["source_observations_sha256"] = v4.byte_hash(blob(notes))
            context = {"invocation_id": run["invocation_id"], "started_on": run["source_context_recheck_started_on"],
                "completed_on": run["source_context_recheck_completed_on"], "source_packet_sha256": method["source_packet_sha256"],
                "records": scopes, "supplemental_preparatory_notes_sha256": None, "actual_execution": True, "fixture": False}
            payloads[run["source_context_recheck_artifact_id"]] = blob(context)
            run["source_context_recheck_sha256"] = v4.byte_hash(blob(context))
    sut = next(r for r in audit["runs"] if r["role"] == "sut")
    execution = {k: sut[k] for k in ("invocation_id", "reviewer", "started_on", "completed_on", "fixture", "actual_execution")}
    execution.update(endpoint=v4.ENDPOINT, input_bytes_sha256=method["input_graph_bytes_sha256"],
        **{k: method[k] for k in ("input_graph_sha256", "output_graph_sha256", "sut_source_sha256")})
    payloads["sut_execution"] = blob(execution)
    for run in audit["runs"]:
        if run["role"] == "sut":
            continue
        records = []
        for i, case in enumerate(audit["truth"]):
            receipt = next(r for r in case["review_receipts"] if r["invocation_id"] == run["invocation_id"])
            receipt["evidence"][0]["reading_scope_sha256"] = h
            entry = {"assertion_id": case["assertion_id"], **{k: receipt[k] for k in (
                "decision", "critical_if_accepted", "scientific_sha256", "evidence")}}
            receipt.update(entry_pointer=f"/records/{i}", entry_sha256=v4.canonical_hash(entry))
            records.append(entry)
        artifact = next(r for r in audit["truth"][0]["review_receipts"] if r["invocation_id"] == run["invocation_id"])["artifact_id"]
        payloads[artifact] = blob({**run, "records": records})
    commitments = {"input_graph_sha256": v4.canonical_hash(graph),
        **{k + "_sha256": v4.byte_hash(payloads[k]) for k in (
            "frame_curation", "lineage_manifest", "exposure_registry", "metadata_adaptations", "exposure_semantic_review")},
        "exposure_scopes_sha256": v4.canonical_hash(exposure["source_artifact_pins"])}
    population_review = {"invocation_id": "SYNTHETIC.population-review", "reviewer": "SYNTHETIC independent reviewer",
        "reviewed_on": "2026-11-10T02:30:00Z", "actual_execution": True, "fixture": False,
        "input_commitments": commitments, "records": [{"assertion_id": row["assertion_id"],
            "lineage_sha256": row["lineage_sha256"], "curation_entry_sha256": v4.canonical_hash(row),
            "disposition": row["disposition"], "finding_equivalence_sha256": row["finding_equivalence_sha256"],
            "scope_kind": row["scope_kind"], "lineage_history_sha256": lineages[i]["history_ref"]["entry_sha256"],
            "exposure_decision": "unexposed"} for i, row in enumerate(curation)]}
    payloads["original_population_review"] = blob({"review": population_review})
    payloads["population_semantic_review"] = blob({"author_invocation_id": "SYNTHETIC.curator", "input_commitments": commitments,
        "review_refs": [ref("original_population_review", "/review", population_review)]})
    audit["artifacts"] = {k: v4.byte_hash(v) for k, v in payloads.items()}
    for field, artifact in v4.POPULATION_PINS.items():
        method[field] = audit["artifacts"][artifact]
    rawsource = b"synthetic fixture response"
    return reseal(audit), graph, payloads, {v4.byte_hash(rawsource): rawsource}


def simulated_trust(audit):
    """An invented caller-trust double, never emitted as an actual admission."""
    ab = blob(reseal(audit))
    pins = {name: v4.byte_hash((ROOT / name).read_bytes()) for name in v4.CODE_FILES}
    receipt = {"schema_version": v4.RECEIPT_VERSION, "audit_sha256": v4.byte_hash(ab),
        "method_sha256": audit["method_sha256"], "sample_bindings_sha256": v4.canonical_hash(audit["bindings"]),
        "population_authentication_sha256": v4.canonical_hash({f: audit["method"][f] for f in v4.POPULATION_PINS}),
        "artifact_commitments_sha256": v4.canonical_hash(audit["artifacts"]),
        "source_authentication_sha256": v4.canonical_hash(sorted({p["response_sha256"] for b in audit["bindings"] for p in b["source_pins"]})),
        "validator_code_pins": pins, "validation_errors": [], "validation_run": {
            "invocation_id": "SYNTHETIC.validator", "reviewer": "SYNTHETIC validator", "validated_on": "2026-11-10T11:00:00Z",
            "actual_execution": True, "fixture": False}}
    rb = blob(receipt)
    admission = {"schema_version": v4.ADMISSION_VERSION, "status": "accepted", "audit_sha256": v4.byte_hash(ab),
        "receipt_sha256": v4.byte_hash(rb), "validator_capsule_sha256": v4.canonical_hash(pins),
        "validation_invocation_id": "SYNTHETIC.validator", "independent_review_invocation_id": "SYNTHETIC.admitter",
        "independent_reviewer": "SYNTHETIC admission double", "independent_review_sha256": v4.canonical_hash("SYNTHETIC review"),
        "reviewed_on": "2026-11-10T12:00:00Z", "admitted_on": "2026-11-10T13:00:00Z", "completion_authorized": True,
        "method_adoption_sha256": audit["method"]["adoption_sha256"], "exposure_review_sha256": audit["exposure_registry"]["semantic_review_sha256"],
        "population_rule": v4.POPULATION_RULE, **{f: audit["method"][f] for f in (
            "population_review_sha256", "lineage_manifest_sha256", "metadata_adaptations_sha256")}}
    return ab, rb, admission


class ReferenceV4Controls(unittest.TestCase):
    def setUp(self):
        self.audit, self.graph, self.payloads, self.sources = fixture_only()

    def read(self):
        ab, rb, admission = simulated_trust(self.audit)
        return v4.validate_public_reference_v4(ab, self.graph, rb, trusted_admission=admission)

    def validate_private(self):
        return v4.load_exact(v4.validate_private_reference_v4(blob(reseal(self.audit)), self.graph,
            expected_artifact_hashes=dict(self.audit["artifacts"]), artifact_payloads=self.payloads,
            source_payloads=self.sources, invocation_id="SYNTHETIC.private-validator", reviewer="SYNTHETIC fixture",
            fixture=True))

    def build(self, curation=None, manifest=None, payloads=None):
        return v4.build_reference_frame(self.graph,
            curation if curation is not None else v4.load_exact(self.payloads["frame_curation"])["records"],
            self.audit["exposure_registry"], manifest if manifest is not None else v4.load_exact(self.payloads["lineage_manifest"]),
            artifact_payloads=self.payloads if payloads is None else payloads,
            metadata_adaptations=v4.load_exact(self.payloads["metadata_adaptations"]))

    def test_failed_private_artifact_diagnostics_do_not_echo_unsafe_names(self):
        for key in ('sk-' + 'X' * 24, '文sk-' + 'X' * 24,
                    '/Users/test/private.txt', 'private@example.invalid'):
            with self.subTest(kind=key[:2]):
                audit = copy.deepcopy(self.audit)
                audit['artifacts'][key] = '0' * 64
                receipt = v4.validate_private_reference_v4(blob(reseal(audit)), self.graph,
                    expected_artifact_hashes=dict(audit['artifacts']), artifact_payloads=self.payloads,
                    source_payloads=self.sources, invocation_id='SYNTHETIC.private-key-check',
                    reviewer='SYNTHETIC fixture', fixture=True)
                errors = v4.load_exact(receipt)['validation_errors']
                self.assertTrue(errors)
                self.assertNotIn(key, str(errors))
                self.assertEqual(v4._safe_public(errors), [])

    def change_truth(self, aid, decision, critical=False):
        row = next(t for t in self.audit["truth"] if t["assertion_id"] == aid)
        row.update(decision=decision, critical_if_accepted=critical)
        for receipt in row["review_receipts"]:
            receipt.update(decision=decision, critical_if_accepted=critical)

    def test_fixture_only_integrity_control_and_separate_fixture_receipt(self):
        self.assertTrue(FIXTURE_ONLY)
        self.assertEqual(self.read()[0], [])
        result = self.validate_private()
        self.assertEqual(result["validation_errors"], [])
        self.assertTrue(result["validation_run"]["fixture"])
        ab, _, admission = simulated_trust(self.audit)
        errors, _ = v4.validate_public_reference_v4(ab, self.graph, blob(result), trusted_admission=admission)
        self.assertTrue(errors)

    def test_new_versions_and_distinct_fixed_seed_preserve_same_sut(self):
        self.assertNotEqual(v4.VERSION, historical.VERSION)
        self.assertNotEqual(v4.SEED, historical.SEED)
        self.assertEqual(v4.ENDPOINT, historical.ENDPOINT)
        with self.assertRaisesRegex(ValueError, "seed"):
            v4.select_reference_panel(self.audit["frame"], seed=historical.SEED)
        output, execution = v4.execute_reference_projection(blob(self.graph), invocation_id="SYNTHETIC.actual-projection-test",
            reviewer="SYNTHETIC fixture", fixture=True)
        self.assertEqual(v4.load_exact(output), rg.public_graph(self.graph))
        self.assertTrue(v4.load_exact(execution)["fixture"])

    def test_missing_original_peer_or_history_cannot_be_prose_proof(self):
        payloads = dict(self.payloads)
        del payloads["original_peer_receipts"]
        with self.assertRaises(KeyError): self.build(payloads=payloads)
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["lineages"][0]["history_ref"]["entry_sha256"] = v4.canonical_hash("arbitrary explanation")
        with self.assertRaises(ValueError): self.build(manifest=manifest)

    def test_census_and_lineage_membership_cannot_omit_current_inputs(self):
        curation = v4.load_exact(self.payloads["frame_curation"])["records"]
        with self.assertRaisesRegex(ValueError, "Complete"):
            self.build(curation=curation[:-1])
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["lineages"][0]["member_assertion_ids"].append(manifest["lineages"][1]["first_assertion_id"])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.build(manifest=manifest)

    def test_missing_earliest_input_cannot_promote_corrected_successor(self):
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["lineages"][0]["first_assertion_id"] = "SYNTHETIC.absent.initial"
        with self.assertRaisesRegex(ValueError, "earliest actual input"):
            self.build(manifest=manifest)

    def test_held_rows_preserved_and_never_filled(self):
        curation = v4.load_exact(self.payloads["frame_curation"])["records"]
        curation[0].update(disposition="held", reason="SYNTHETIC missing earliest provenance")
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["lineages"][0]["submissions"] = []
        frame = self.build(curation=curation, manifest=manifest)
        self.assertEqual(len(frame), 199)
        self.assertEqual(len(curation), 200)
        self.assertEqual(len(v4.select_reference_panel(frame)), 199)

    def test_corrected_successor_is_real_output_but_never_a_second_case(self):
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        curation = v4.load_exact(self.payloads["frame_curation"])["records"]
        index = 180  # Genuine synthetic withheld initial hypothesis.
        initial = self.graph["assertions"][index]
        corrected = copy.deepcopy(initial)
        corrected.update(id=initial["id"] + ".corrected", status="approved", review_ids=[])
        corrected["value"]["value"] = "SYNTHETIC corrected proposition; same reviewed lineage, never research."
        for template in self.graph["reviews"][:3]:
            review = copy.deepcopy(template)
            review.update(id=corrected["id"] + "." + review["role"], assertion_ids=[corrected["id"]],
                invocation_id=corrected["id"] + "." + review["role"],
                assertion_sha256={corrected["id"]: rg.assertion_digest(corrected)})
            corrected["review_ids"].append(review["id"])
            self.graph["reviews"].append(review)
        self.graph["assertions"].append(corrected)
        self.graph["entities"][0]["assertion_ids"].append(corrected["id"])
        submission = {"assertion": {**corrected, "status": "candidate", "review_ids": []},
            "sources": copy.deepcopy(self.graph["sources"])}
        submission_ref = ref("correction_submission", "/entry", submission)
        peer = {"assertion_id": corrected["id"], "scientific_sha256": rg.assertion_digest(corrected),
            "submission_entry_sha256": submission_ref["entry_sha256"],
            "source_record_sha256": {s["id"]: v4.canonical_hash(s) for s in self.graph["sources"]},
            "event": "peer_submission", "received_on": "2026-11-08T12:45:00Z",
            "invocation_id": "SYNTHETIC.correction-receiver", "reviewer": "SYNTHETIC peer",
            "actual_execution": True, "fixture": False}
        self.payloads.update(correction_submission=blob({"entry": submission}), correction_peer=blob({"entry": peer}))
        lineage = manifest["lineages"][index]
        lineage["member_assertion_ids"].append(corrected["id"])
        lineage["submissions"].append({"assertion_id": corrected["id"], "first_peer_submitted_on": peer["received_on"],
            "submission_ref": submission_ref, "peer_receipt_ref": ref("correction_peer", "/entry", peer)})
        curation.append({**curation[index], "assertion_id": corrected["id"], "disposition": "exclude",
            "reason": "SYNTHETIC corrected successor remains in census; first hypothesis is the unit"})
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        frame = self.build(curation=curation, manifest=manifest)
        self.assertEqual(len(frame), 200)
        self.assertNotIn(corrected["id"], v4.select_reference_panel(frame))
        output_ids = {a["id"] for a in rg.public_graph(self.graph)["assertions"]}
        self.assertIn(corrected["id"], output_ids)
        self.assertFalse(v4.sampled_bindings(self.graph, [initial["id"]], output_ids)[0]["observed_positive"])
        # A real preserved later chain/opening is enough for a successor; never
        # fabricate an atomic old receiving receipt for its historical format.
        lineage["submissions"].pop()
        event = {"opened_on": peer["received_on"]}
        chain = {"original_assertion_id": initial["id"], "original_scientific_sha256": rg.assertion_digest(initial),
            "original_first_actual_peer_opening": "2026-11-08T12:30:00Z", "successor_assertion_id": corrected["id"],
            "successor_scientific_sha256": rg.assertion_digest(corrected), "initial_time_not_reset": True,
            "successor_actual_opening": {"first_successor_recorded_opening": peer["received_on"],
                "actual_opening_records": [{"opened_on": peer["received_on"], "artifact": {"sha256": v4.byte_hash(blob(event))}}]}}
        self.payloads.update(correction_event=blob(event), original_correction_chain=blob({"chain": chain}))
        lineage["authenticated_successors"] = [{"assertion_id": corrected["id"],
            "chain_ref": ref("original_correction_chain", "/chain", chain),
            "opening_ref": ref("correction_event", "/opened_on", peer["received_on"])}]
        self.assertEqual(len(self.build(curation=curation, manifest=manifest)), 200)
        # A retained successor opening also constrains that successor's peers;
        # its author's earlier legitimate source work is a different event.
        early = copy.deepcopy(next(r for r in self.graph["reviews"] if r["role"] == "source_verifier"))
        early.update(id="SYNTHETIC.successor.early-peer", invocation_id="SYNTHETIC.successor.early-peer",
            assertion_ids=[corrected["id"]], assertion_sha256={corrected["id"]: rg.assertion_digest(corrected)},
            reviewed_on="2026-11-08T12:35:00Z")
        self.graph["reviews"].append(early)
        corrected["review_ids"].append(early["id"])
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        with self.assertRaisesRegex(ValueError, "peer review precedes"):
            self.build(curation=curation, manifest=manifest)
        early["role"] = "author"
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        self.assertEqual(len(self.build(curation=curation, manifest=manifest)), 200)
        corrected["review_ids"].remove(early["id"])
        self.graph["reviews"].remove(early)
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        changed = copy.deepcopy(manifest)
        changed["lineages"][index]["authenticated_successors"][0]["assertion_id"] = initial["id"]
        with self.assertRaisesRegex(ValueError, "successor chain"):
            self.build(curation=curation, manifest=changed)
        curation[-1]["disposition"] = "include"
        with self.assertRaisesRegex(ValueError, "Exactly one initial"):
            self.build(curation=curation, manifest=manifest)

    def test_exposed_old_or_repair_lineage_and_identity_filler_held(self):
        self.audit["exposure_registry"]["lineage_keys"].append(self.audit["frame"][0]["lineage_sha256"])
        with self.assertRaisesRegex(ValueError, "Exposed"): self.build()
        self.audit["exposure_registry"]["lineage_keys"].pop()
        curation = v4.load_exact(self.payloads["frame_curation"])["records"]
        curation[0]["scope_kind"] = "title_metadata"
        with self.assertRaisesRegex(ValueError, "substantive"): self.build(curation=curation)

    def test_support_is_independent_of_actual_production_disposition(self):
        withheld = [b for b in self.audit["bindings"] if not b["observed_positive"]]
        for binding in withheld[:11]: self.change_truth(binding["assertion_id"], "supported")
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["false_negative"], 11)
        self.assertEqual(metrics["supported_withheld"], 11)
        self.assertLess(metrics["recall"], .95)
        self.assertEqual(withheld[0]["original_review_record_sha256"], {})

    def test_unknown_and_critical_errors_preserved(self):
        selected = list(self.audit["selected_assertion_ids"])
        self.change_truth(selected[0], "unknown")
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["unknown"], 1)
        self.assertEqual(selected, self.audit["selected_assertion_ids"])
        self.change_truth(selected[0], "unsupported")
        aid = next(b["assertion_id"] for b in self.audit["bindings"] if b["observed_positive"])
        self.change_truth(aid, "unsupported", True)
        errors, metrics = self.read()
        self.assertTrue(errors)
        self.assertEqual(metrics["critical_false_attributions"], 1)

    def test_unresolved_disagreement_needs_actual_separate_tie(self):
        self.audit["truth"][0]["review_receipts"][0]["decision"] = "unknown"
        errors, _ = self.read()
        self.assertTrue(any("tie" in e for e in errors))

    def test_new_truth_recheck_notes_then_hypotheses_cannot_be_retimestamped_prep(self):
        run = next(r for r in self.audit["runs"] if r["role"] != "sut")
        run["source_context_recheck_started_on"] = "2026-11-10T00:00:00Z"
        errors, _ = self.read()
        self.assertTrue(any("recheck" in e for e in errors))
        run["source_context_recheck_started_on"] = "2026-11-10T07:01:00Z"
        run["hypotheses_opened_on"] = "2026-11-10T07:14:00Z"
        errors, _ = self.read()
        self.assertTrue(any("hypotheses" in e for e in errors))

    def test_honestly_disclosed_pre_method_preparation_can_be_supplemental(self):
        run = next(r for r in self.audit["runs"] if r["role"] != "sut")
        original = blob({"SYNTHETIC": "original neutral preparatory notes, fixture only",
            "frozen_on": "2026-11-09T00:00:00Z"})
        run.update(preparatory_notes_artifact_id="SYNTHETIC.original-preparation", preparatory_notes_sha256=v4.byte_hash(original))
        self.payloads[run["preparatory_notes_artifact_id"]] = original
        for artifact in (run["source_context_recheck_artifact_id"], run["source_observations_artifact_id"]):
            entry = v4.load_exact(self.payloads[artifact])
            entry["supplemental_preparatory_notes_sha256"] = run["preparatory_notes_sha256"]
            self.payloads[artifact] = blob(entry)
        run["source_observations_sha256"] = v4.byte_hash(self.payloads[run["source_observations_artifact_id"]])
        run["source_context_recheck_sha256"] = v4.byte_hash(self.payloads[run["source_context_recheck_artifact_id"]])
        for receipt in self.audit["truth"][0]["review_receipts"]:
            if receipt["invocation_id"] == run["invocation_id"]:
                envelope = v4.load_exact(self.payloads[receipt["artifact_id"]])
                envelope.update(run)
                self.payloads[receipt["artifact_id"]] = blob(envelope)
        self.audit["artifacts"] = {k: v4.byte_hash(v) for k, v in self.payloads.items()}
        result = self.validate_private()
        self.assertEqual(result["validation_errors"], [])
        self.assertEqual(self.payloads[run["preparatory_notes_artifact_id"]], original)

    def test_exact_cited_source_binding_no_sibling_source_rescue(self):
        self.audit["truth"][0]["review_receipts"][0]["evidence"][0]["source_id"] = "SYNTHETIC.sibling.same.body"
        errors, _ = self.read()
        self.assertTrue(any("outside the frozen cited-source" in e for e in errors))

    def test_unrelated_additions_allowed_but_selected_source_changes_held(self):
        extra = copy.deepcopy(self.graph["assertions"][-1])
        extra["id"] = "SYNTHETIC.unrelated.new-finding"
        self.graph["assertions"].append(extra)
        self.graph["entities"][0]["assertion_ids"].append(extra["id"])
        self.assertEqual(self.read()[0], [])
        self.graph["sources"][0]["license"] = "SYNTHETIC changed license"
        errors, _ = self.read()
        self.assertTrue(any("binding changed" in e for e in errors))
        self.graph = rg.public_graph(self.graph)
        self.assertTrue(self.read()[0])

    def test_extra_review_links_preserved_but_earlier_peer_contradiction_held(self):
        review = copy.deepcopy(self.graph["reviews"][0])
        review.update(id="SYNTHETIC.additional-review", invocation_id="SYNTHETIC.additional-review",
            reviewed_on="2026-11-09T00:00:00Z")
        aid = review["assertion_ids"][0]
        self.graph["reviews"].append(review)
        next(a for a in self.graph["assertions"] if a["id"] == aid)["review_ids"].append(review["id"])
        self.assertEqual(self.read()[0], [])
        review["reviewed_on"] = "2026-11-08T12:15:00Z"
        errors, _ = self.read()
        self.assertTrue(any("earliest peer submission" in e for e in errors))

    def test_zero_genuine_withheld_remains_an_explicit_hold(self):
        for binding in self.audit["bindings"]:
            binding["observed_positive"] = True
        errors, metrics = self.read()
        self.assertEqual(metrics["observed_withheld"], 0)
        self.assertTrue(any("all-output panel" in e for e in errors))

    def test_private_authentication_covers_full_population_originals_and_source_bytes(self):
        del self.payloads["original_population_review"]
        result = self.validate_private()
        self.assertTrue(any("original_population_review" in e for e in result["validation_errors"]))
        self.sources.clear()
        result = self.validate_private()
        self.assertTrue(any("raw primary-source" in e for e in result["validation_errors"]))

    def test_private_exact_original_truth_and_fresh_source_notes_cannot_be_resealed(self):
        self.change_truth(self.audit["selected_assertion_ids"][0], "supported")
        result = self.validate_private()
        self.assertTrue(any("exact original independent decision" in e for e in result["validation_errors"]))
        run = next(r for r in self.audit["runs"] if r["role"] != "sut")
        self.payloads[run["source_context_recheck_artifact_id"]] += b" "
        result = self.validate_private()
        self.assertTrue(any("Original artifact authentication failed" in e for e in result["validation_errors"]))

    def test_independent_population_review_is_original_complete_and_pre_frame(self):
        original = v4.load_exact(self.payloads["original_population_review"])
        original["review"]["records"].pop()
        self.payloads["original_population_review"] = blob(original)
        self.audit["artifacts"]["original_population_review"] = v4.byte_hash(blob(original))
        envelope = v4.load_exact(self.payloads["population_semantic_review"])
        envelope["review_refs"][0]["entry_sha256"] = v4.canonical_hash(original["review"])
        self.payloads["population_semantic_review"] = blob(envelope)
        self.audit["artifacts"]["population_semantic_review"] = v4.byte_hash(blob(envelope))
        self.audit["method"]["population_review_sha256"] = self.audit["artifacts"]["population_semantic_review"]
        result = self.validate_private()
        self.assertTrue(any("every genuine nonhistorical" in e for e in result["validation_errors"]))

    def test_separate_admission_and_unchanged_floors_are_required(self):
        ab, rb, admission = simulated_trust(self.audit)
        errors, _ = v4.validate_public_reference_v4(ab, self.graph, rb, trusted_admission=None)
        self.assertTrue(errors)
        errors, _ = v4.validate_public_reference_v4(ab, self.graph, rb, trusted_admission=admission,
            thresholds={"reference_recall": .94})
        self.assertTrue(any("Cannot lower" in e for e in errors))
        admission["population_rule"] = "only convenient revised cases"
        errors, _ = v4.validate_public_reference_v4(ab, self.graph, rb, trusted_admission=admission)
        self.assertTrue(any("initial-hypothesis population" in e for e in errors))

    def test_prospective_privacy_fix_keeps_task_identifier_and_blocks_secrets(self):
        self.assertEqual(v4._safe_public("task-preference-prediction"), [])
        for value in ["sk-" + "X" * 24, "λsk-" + "X" * 24,
            "https://example.org/%73%6b-" + "X" * 24, "https://example.org/?secret=SYNTHETIC"]:
            self.assertTrue(v4._safe_public(value))
        self.assertTrue(historical._safe_public("task-preference-prediction"))

    def test_fixture_flag_never_admitted_as_actual_execution(self):
        self.audit["fixture"] = True
        errors, _ = self.read()
        self.assertTrue(any("non-fixture" in e for e in errors))

    def grouped_fixture_only(self):
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        lineage = manifest["lineages"][0]
        old = v4.load_exact(self.payloads["original_submissions"])["records"][0]
        packet = {"assertions": [old["assertion"]], "sources": old["sources"]}
        packet_raw = blob(packet)
        event = {"opened_on": "2026-11-08T12:30:00Z", "packet_sha256": v4.byte_hash(packet_raw)}
        event_raw = blob(event)
        # No invented per-assertion event, old invocation ID, execution flag or review.
        group = {"packet": {"sha256": v4.byte_hash(packet_raw)},
            "verifier_receipt": {"sha256": v4.byte_hash(event_raw)},
            "verifier_start": event["opened_on"], "adversary_start": "2026-11-08T12:40:00Z",
            "first_authenticated_opening": event["opened_on"], "earliest_role": "source_verifier"}
        self.payloads.update(group_packet=packet_raw, group_event=event_raw, group_auth=blob({"events": [group]}))
        lineage["submissions"] = [{"assertion_id": old["assertion"]["id"],
            "provenance_representation": "derived_grouped_packet_v1", "derived_on": "2026-11-10T00:00:00Z",
            "first_peer_submitted_on": event["opened_on"],
            "submission_ref": ref("group_packet", "/assertions/0", packet["assertions"][0]),
            "source_refs": [ref("group_packet", f"/sources/{i}", source) for i, source in enumerate(packet["sources"])],
            "peer_receipt_ref": ref("group_event", "", event),
            "peer_opening_ref": ref("group_event", "/opened_on", event["opened_on"]),
            "packet_digest_ref": ref("group_event", "/packet_sha256", event["packet_sha256"]),
            "group_authentication_ref": ref("group_auth", "/events/0", group)}]
        return manifest, lineage["submissions"][0]

    def test_genuine_grouped_originals_need_no_fictitious_atomic_receipts(self):
        manifest, row = self.grouped_fixture_only()
        frame = self.build(manifest=manifest)
        self.assertEqual(len(frame), 200)
        self.assertEqual(frame[0]["first_peer_receipt_sha256"], row["peer_receipt_ref"]["entry_sha256"])
        self.assertNotIn("actual_execution", v4.load_exact(self.payloads["group_event"]))
        self.assertNotIn("invocation_id", v4.load_exact(self.payloads["group_event"]))

    def test_grouped_earliest_role_must_really_have_the_earliest_start(self):
        manifest, row = self.grouped_fixture_only()
        group = v4.load_exact(self.payloads["group_auth"])
        group["events"][0].update(verifier_start="2026-11-08T12:40:00Z",
                                   adversary_start="2026-11-08T12:30:00Z")
        self.payloads["group_auth"] = blob(group)
        row["group_authentication_ref"] = ref("group_auth", "/events/0", group["events"][0])
        with self.assertRaisesRegex(ValueError, "earliest opening"):
            self.build(manifest=manifest)

    def test_receiving_entry_must_contain_its_opening_and_same_artifact_binding(self):
        manifest, row = self.grouped_fixture_only()
        event = v4.load_exact(self.payloads["group_event"])
        event["unrelated"] = {"SYNTHETIC": "not the receiving event"}
        self.payloads["group_event"] = blob(event)
        group = v4.load_exact(self.payloads["group_auth"])
        group["events"][0]["verifier_receipt"]["sha256"] = v4.byte_hash(self.payloads["group_event"])
        self.payloads["group_auth"] = blob(group)
        row["group_authentication_ref"] = ref("group_auth", "/events/0", group["events"][0])
        row["peer_receipt_ref"] = ref("group_event", "/unrelated", event["unrelated"])
        with self.assertRaisesRegex(ValueError, "earliest opening"):
            self.build(manifest=manifest)
        self.assertFalse(v4._pointer_contains("/event/1", "/event/10/opened_on"))
        self.assertTrue(v4._pointer_contains("/event/1", "/event/1/opened_on"))
        self.assertTrue(v4._pointer_contains("/event~1name", "/event~1name/opened_on"))
        self.assertTrue(v4._pointer_contains("", "/event/10/opened_on"))
        # A second artifact name for identical bytes cannot bypass token ancestry.
        manifest, row = self.grouped_fixture_only()
        original = v4.load_exact(self.payloads["group_event"])
        event = {"events": [{} for _ in range(11)]}
        event["events"][1] = original
        event["events"][10] = {"packet_sha256": original["packet_sha256"]}
        self.payloads["group_event"] = self.payloads["group_event_alias"] = blob(event)
        group = v4.load_exact(self.payloads["group_auth"])
        group["events"][0]["verifier_receipt"]["sha256"] = v4.byte_hash(self.payloads["group_event"])
        self.payloads["group_auth"] = blob(group)
        row["group_authentication_ref"] = ref("group_auth", "/events/0", group["events"][0])
        row["peer_receipt_ref"] = ref("group_event", "/events/1", original)
        row["peer_opening_ref"] = ref("group_event", "/events/1/opened_on", original["opened_on"])
        row["packet_digest_ref"] = ref("group_event_alias", "/events/10/packet_sha256", original["packet_sha256"])
        with self.assertRaisesRegex(ValueError, "contain.*packet binding"):
            self.build(manifest=manifest)

    def test_derived_representation_must_precede_its_new_ack_and_freezes(self):
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["derived_on"] = "2026-11-11T00:00:00Z"
        self.payloads["lineage_manifest"] = blob(manifest)
        review = v4.load_exact(self.payloads["original_population_review"])
        envelope = v4.load_exact(self.payloads["population_semantic_review"])
        for item in (review["review"]["input_commitments"], envelope["input_commitments"]):
            item["lineage_manifest_sha256"] = v4.byte_hash(self.payloads["lineage_manifest"])
        self.payloads["original_population_review"] = blob(review)
        envelope["review_refs"][0]["entry_sha256"] = v4.canonical_hash(review["review"])
        self.payloads["population_semantic_review"] = blob(envelope)
        curation = v4.load_exact(self.payloads["frame_curation"])
        adaptations = v4.load_exact(self.payloads["metadata_adaptations"])
        with self.assertRaisesRegex(ValueError, "before.*frozen"):
            v4._validate_population_review(self.audit, self.graph, curation, manifest,
                self.audit["exposure_registry"], adaptations, self.payloads)
        self.audit["chronology"].update(input_frozen_on="2026-11-12T00:00:00Z",
                                        frame_frozen_on="2026-11-12T01:00:00Z")
        with self.assertRaisesRegex(ValueError, "Separate actual"):
            v4._validate_population_review(self.audit, self.graph, curation, manifest,
                self.audit["exposure_registry"], adaptations, self.payloads)

    def test_grouped_bridge_rejects_changed_packet_opening_source_or_derived_time(self):
        manifest, row = self.grouped_fixture_only()
        row["first_peer_submitted_on"] = "2026-11-08T12:40:00Z"
        with self.assertRaisesRegex(ValueError, "earliest opening"):
            self.build(manifest=manifest)
        row["first_peer_submitted_on"] = "2026-11-08T12:30:00Z"
        row["derived_on"] = "2026-11-08T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "earliest opening"):
            self.build(manifest=manifest)
        row["derived_on"] = "2026-11-10T00:00:00Z"
        row["source_refs"][0]["artifact_id"] = "original_submissions"
        with self.assertRaisesRegex(ValueError, "opened packet"):
            self.build(manifest=manifest)

    def test_author_completion_before_first_peer_is_legitimate_but_earlier_peer_is_not(self):
        author = next(r for r in self.graph["reviews"] if r["role"] == "author")
        author["reviewed_on"] = "2026-11-08T12:15:00Z"
        manifest = v4.load_exact(self.payloads["lineage_manifest"])
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        self.assertEqual(len(self.build(manifest=manifest)), 200)
        peer = next(r for r in self.graph["reviews"] if r["role"] == "source_verifier")
        peer["reviewed_on"] = "2026-11-08T12:15:00Z"
        manifest["input_graph_sha256"] = v4.canonical_hash(self.graph)
        with self.assertRaisesRegex(ValueError, "peer review precedes"):
            self.build(manifest=manifest)


class MetadataAdaptationControls(unittest.TestCase):
    def fixture_only(self, kind="creator_github_readme_or_license"):
        graph = tiny_fixture()
        before = copy.deepcopy(graph["sources"][0])
        before.update(source_type="documentation", url="https://github.com/SYNTHETIC/fixture/blob/v1/README.md")
        target = {"creator_github_readme_or_license": "repository", "creator_huggingface_dataset_card": "dataset_card",
            "creator_protocol_report": "provider_documentation"}[kind]
        if kind == "creator_huggingface_dataset_card": before["url"] = "https://huggingface.co/datasets/SYNTHETIC/fixture/resolve/pinned-revision/README.md"
        if kind == "creator_protocol_report": before["url"] = "https://example.org/SYNTHETIC/protocol-report"
        after = {**before, "source_type": target}
        graph["sources"] = [after]
        creator = {"SYNTHETIC creator evidence": "fixture only"}
        review = {"source_id": "source", "before_record_sha256": v4.canonical_hash(before),
            "after_record_sha256": v4.canonical_hash(after), "artifact_kind": kind,
            "creator_identity_sha256": v4.canonical_hash(creator), "decision": "metadata_only_creator_artifact",
            "invocation_id": "SYNTHETIC.metadata-independent", "reviewer": "SYNTHETIC independent reviewer",
            "reviewed_on": "2026-11-10T00:00:00Z", "actual_execution": True, "fixture": False}
        payloads = {"creator_original": blob({"entry": creator}), "metadata_review_original": blob({"review": review})}
        adaptations = {"records": [{"source_id": "source", "before_record": before, "after_record": after,
            "artifact_kind": kind, "author_invocation_id": "SYNTHETIC.transform-author",
            "creator_identity_ref": ref("creator_original", "/entry", creator),
            "review_refs": [ref("metadata_review_original", "/review", review)]}]}
        return graph, adaptations, payloads

    def test_three_exact_creator_metadata_transitions_only(self):
        for kind in ("creator_github_readme_or_license", "creator_huggingface_dataset_card", "creator_protocol_report"):
            graph, adaptations, payloads = self.fixture_only(kind)
            self.assertEqual(set(v4.validate_metadata_adaptations(graph, adaptations, payloads)), {"source"})

    def test_metadata_change_never_covers_source_scientific_evidence_or_creator_changes(self):
        graph, adaptations, payloads = self.fixture_only()
        adaptations["records"][0]["before_record"]["license"] = "SYNTHETIC changed original license"
        with self.assertRaisesRegex(ValueError, "Only exact"):
            v4.validate_metadata_adaptations(graph, adaptations, payloads)
        graph, adaptations, payloads = self.fixture_only()
        del payloads["creator_original"]
        with self.assertRaises(KeyError): v4.validate_metadata_adaptations(graph, adaptations, payloads)
        graph, adaptations, payloads = self.fixture_only()
        adaptations["records"][0]["author_invocation_id"] = "SYNTHETIC.metadata-independent"
        with self.assertRaisesRegex(ValueError, "independently"):
            v4.validate_metadata_adaptations(graph, adaptations, payloads)


if __name__ == "__main__":
    unittest.main()
