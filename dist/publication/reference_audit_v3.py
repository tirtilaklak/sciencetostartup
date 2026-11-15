"""Proposed genuine-input, disposition-stratified source-quality holdout.

No scientific verdict/approval or actual research receipt is created at import.
The actual SUT is unchanged research_graph.public_graph. Audit source truth and
scientific approval are different records. An independent reviewed admission is
always required; arbitrary invocation strings establish no actual execution.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import research_graph as rg
from screening_audit_v2 import (
    SHA, _index, _safe_public, _shape, byte_hash, canonical_hash, load_exact, timestamp,
)

VERSION = "reference-audit-v3"
RECEIPT_VERSION = "reference-private-validation-v3"
ADMISSION_VERSION = "reference-audit-admission-v3"
KIND = "source_bound_disposition_stratified_holdout"
ENDPOINT = "research_graph.public_graph"
FLOORS = {"reference_sample_size": 200, "reference_precision": .98, "reference_recall": .95}
SEED = "STS-reference-genuine-input-disposition-holdout-v3-2026-11-11"
TRUTH_ROLES = {"audit_source_adjudicator", "audit_adversarial_adjudicator"}
CODE_FILES = ("scripts/reference_audit_v3.py", "schema/reference-audit.v3.schema.json",
    "scripts/screening_audit_v2.py", "scripts/research_audit_dispatch.py", "scripts/research_graph.py")
REQUIRED_ARTIFACTS = {"input_graph", "sut_output", "sut_execution", "frame_curation",
    "exposure_registry", "source_packet", "method_adoption", "exposure_reference250",
    "exposure_reference226", "exposure_citation62", "exposure_semantic_review"}


def entity_identity(row):
    return {key: row.get(key) for key in ("id", "kind", "name", "identifiers", "aliases", "parent_id", "family_id")}


def build_reference_frame(graph, curation_records, exposure_registry):
    """Neutral frame construction, not new truth or scientific source review.

    Curation must cover every genuine nonhistorical assertion in the real input.
    It marks substantive scope/equivalence and exclusions, never source support.
    Source reading/semantic exposure reconciliation remains an actual review duty.
    """
    assertions = _index(graph["assertions"], "id")
    sources = _index(graph["sources"], "id")
    curated = _index(curation_records, "assertion_id")
    current = {aid for aid, row in assertions.items() if row["status"] != "historical"}
    if set(curated) != current:
        raise ValueError("Complete actual nonhistorical-input curation ledger required")
    frame, groups = [], set()
    for aid in sorted(current):
        assertion, entry = assertions[aid], curated[aid]
        if entry["disposition"] != "include":
            continue
        scientific = rg.assertion_digest(assertion)
        equivalent = entry["finding_equivalence_sha256"]
        if (aid in exposure_registry["assertion_ids"] or scientific in exposure_registry["scientific_digests"]
                or equivalent in exposure_registry["finding_equivalence_keys"]):
            raise ValueError("Exposed finding/equivalent cannot enter the fresh holdout frame")
        if equivalent in groups:
            raise ValueError("Duplicate scientific-finding equivalence unit in holdout frame")
        if (entry["scope_kind"] != "substantive_scientific_finding" or
                assertion["predicate"] in {"legacy_description", "version_of", "release_of"}):
            raise ValueError("Historical/identity-only facts are not substantive holdout findings")
        evidence = assertion.get("evidence", [])
        if not evidence or any(sources.get(e["source_id"], {}).get("status") != "captured"
                or sources[e["source_id"]].get("source_type") == "metadata" for e in evidence):
            raise ValueError("Genuine substantive cases require actual captured primary-source pins")
        groups.add(equivalent)
        frame.append({"assertion_id": aid, "scientific_sha256": scientific,
            "finding_equivalence_sha256": equivalent, "curation_entry_sha256": canonical_hash(entry),
            "disposition_stratum": "included" if assertion["status"] == "approved" else "withheld",
            "predicate": assertion["predicate"], "source_domains": sorted({
                urlsplit(sources[e["source_id"]]["url"]).netloc for e in evidence})})
    return frame


def select_reference_panel(frame, *, seed=SEED):
    """Fixed design: min(100, real withheld availability), fill to200 from output."""
    _index(frame, "assertion_id")
    if len({r["finding_equivalence_sha256"] for r in frame}) != len(frame):
        raise ValueError("Distinct scientific findings required")
    rank = lambda row: (byte_hash((seed + "\n" + row["assertion_id"]).encode()), row["assertion_id"])
    withheld = sorted((r for r in frame if r["disposition_stratum"] == "withheld"), key=rank)
    included = sorted((r for r in frame if r["disposition_stratum"] == "included"), key=rank)
    count = min(100, len(withheld))
    return [r["assertion_id"] for r in withheld[:count] + included[:200-count]]


def sampled_bindings(graph, assertion_ids, output_ids):
    tables = {name: _index(graph[name], "id") for name in ("assertions", "sources", "entities", "reviews")}
    bindings = []
    for aid in assertion_ids:
        assertion = tables["assertions"][aid]
        sids = {e["source_id"] for e in assertion["evidence"]}
        eids = {assertion["subject_id"]} | ({assertion["object_id"]} if assertion.get("object_id") else set())
        bindings.append({"assertion_id": aid, "scientific_sha256": rg.assertion_digest(assertion),
            "original_status": assertion["status"], "observed_positive": aid in output_ids,
            "source_record_sha256": {sid: canonical_hash(tables["sources"][sid]) for sid in sorted(sids)},
            "source_pins": [{"source_id": sid, "response_sha256": tables["sources"][sid]["response_sha256"],
                "captured_on": tables["sources"][sid]["captured_on"]} for sid in sorted(sids)],
            "entity_identity_sha256": {eid: canonical_hash(entity_identity(tables["entities"][eid])) for eid in sorted(eids)},
            "original_review_record_sha256": {rid: canonical_hash(tables["reviews"][rid]) for rid in sorted(assertion["review_ids"])}})
    return bindings


def execute_reference_projection(input_graph_bytes, *, invocation_id, reviewer, fixture):
    """Execute the unchanged SUT and return output/run bytes; no truth/admission.

    This must run only after method/frame/panel freezes during an actual audit.
    Replaying later proves deterministic integrity, not that a past run occurred.
    """
    if not invocation_id or not reviewer or type(fixture) is not bool:
        raise ValueError("Actual invocation identity and explicit fixture status required")
    started = datetime.now(timezone.utc)
    graph = load_exact(input_graph_bytes)
    output = rg.public_graph(graph)
    completed = datetime.now(timezone.utc)
    root = Path(__file__).resolve().parents[1]
    metadata = {"endpoint": ENDPOINT, "invocation_id": invocation_id, "reviewer": reviewer,
        "started_on": started.isoformat(), "completed_on": completed.isoformat(), "fixture": fixture,
        "actual_execution": True, "input_bytes_sha256": byte_hash(input_graph_bytes),
        "input_graph_sha256": canonical_hash(graph), "output_graph_sha256": canonical_hash(output),
        "sut_source_sha256": byte_hash((root / "scripts/research_graph.py").read_bytes())}
    return rg.stable_json(output).encode(), (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode()


def _thresholds(supplied):
    limits = dict(FLOORS)
    for key, floor in FLOORS.items():
        value = (supplied or {}).get(key, floor)
        if type(value) not in (int, float) or not math.isfinite(value) or value < floor:
            raise ValueError(f"Cannot lower {key} below {floor}")
        limits[key] = value
    return limits


def recompute_reference(audit, *, thresholds=None):
    limits = _thresholds(thresholds)
    bindings, truth = _index(audit["bindings"], "assertion_id"), _index(audit["truth"], "assertion_id")
    selected = audit["selected_assertion_ids"]
    if len(set(selected)) != len(selected) or set(bindings) != set(selected) or set(truth) != set(selected):
        raise ValueError("Complete exact selected membership, predictions and truth are required")
    tp = fp = fn = tn = unknown = critical = unresolved = 0
    for aid in selected:
        positive, decision = bindings[aid]["observed_positive"], truth[aid]["decision"]
        tp += positive and decision == "supported"
        fp += positive and decision == "unsupported"
        fn += not positive and decision == "supported"
        tn += not positive and decision == "unsupported"
        unknown += decision == "unknown"
        critical += positive and truth[aid]["critical_if_accepted"] is True
        unresolved += truth[aid]["critical_if_accepted"] is None
    precision = tp/(tp+fp) if tp+fp else 0
    recall = tp/(tp+fn) if tp+fn else 0
    return {"sample_size":len(selected), "true_positive":tp, "false_positive":fp,
        "false_negative":fn, "true_negative":tn, "unknown":unknown, "precision":precision, "recall":recall,
        "precision_denominator":tp+fp, "recall_denominator":tp+fn,
        "observed_included":sum(b["observed_positive"] for b in bindings.values()),
        "observed_withheld":sum(not b["observed_positive"] for b in bindings.values()),
        "critical_false_attributions":critical, "unresolved_critical_attributions":unresolved,
        "thresholds":limits, "numerical_thresholds_met":len(selected)>=limits["reference_sample_size"]
            and not unknown and precision>=limits["reference_precision"] and recall>=limits["reference_recall"],
        "evaluation_kind":KIND, "publication_eligible":False}


def _validate_core(audit, graph, now, thresholds=None):
    root = Path(__file__).resolve().parents[1]
    schema = load_exact((root / "schema/reference-audit.v3.schema.json").read_bytes())
    errors = _shape(audit, schema)
    if errors:
        return errors, {}
    errors.extend(_safe_public(audit))
    try:
        if not audit["actual_execution"] or audit["fixture"]:
            errors.append("Actual non-fixture reference execution required")
        disclosures={"genuine_disposition_stratified_panel","raw_panel_metrics_not_population_estimates",
            "no_extraction_or_discovery_recall","supported_prudently_withheld_claim_is_false_negative",
            "withheld_live_bindings_require_complete_current_input"}
        if len(audit["limitations"])!=5 or set(audit["limitations"])!=disclosures:
            errors.append("All five distinct bounded-scope reference disclosures are required")
        if audit["release_id"] != graph["release_id"]:
            errors.append("Reference release binding differs")
        if audit["method"]["sut_source_sha256"] != byte_hash((root/"scripts/research_graph.py").read_bytes()):
            errors.append("The actual SUT source code differs from the frozen version")
        if audit["method_sha256"] != canonical_hash(audit["method"]) or audit["frame_sha256"] != canonical_hash(audit["frame"]):
            errors.append("Method/frame commitment differs")
        if audit["method"]["seed"] != SEED:
            errors.append("The fixed reviewed sampling seed cannot change")
        expected = select_reference_panel(audit["frame"])
        if audit["selected_assertion_ids"] != expected:
            errors.append("Selected holdout differs from fixed genuine-disposition sampling")
        for field, value in (("bindings_sha256",audit["bindings"]), ("truth_sha256",audit["truth"]),
                             ("membership_sha256",audit["selected_assertion_ids"])):
            if audit["commitments"][field] != canonical_hash(value):
                errors.append(f"{field} differs")
        excluded = audit["exposure_registry"]
        if not excluded["finding_equivalence_keys"] or not excluded["assertion_ids"]:
            errors.append("An empty self-declared exposure registry cannot cover the old250/226/62 findings")
        if audit["artifacts"].get("exposure_semantic_review")!=excluded["semantic_review_sha256"]:
            errors.append("Exact actual semantic exposure-review bytes must be privately authenticated")
        for scope in ("reference250","reference226","citation62"):
            if audit["artifacts"].get("exposure_"+scope)!=excluded["source_artifact_pins"][scope]:
                errors.append("Exposure scope is not bound to the retained original source artifacts")
        for row in audit["frame"]:
            if (row["assertion_id"] in excluded["assertion_ids"] or row["scientific_sha256"] in excluded["scientific_digests"]
                    or row["finding_equivalence_sha256"] in excluded["finding_equivalence_keys"]):
                errors.append("Exposed finding/equivalent present in fresh holdout frame")
            if row["predicate"] in {"legacy_description","version_of","release_of"}:
                errors.append("Pure identity/version facts cannot fill the substantive scientific holdout")
        seq = {key:timestamp(value) for key,value in audit["chronology"].items()}
        ordered = [seq[key] for key in ("method_adopted_on","input_frozen_on","frame_frozen_on","panel_frozen_on",
            "sut_started_on","predictions_sealed_on","truth_started_on","truth_sealed_on","outcomes_opened_on","scored_on")]
        if any(a>=b for a,b in zip(ordered,ordered[1:])) or ordered[-1]>now:
            errors.append("Method/input/frame/panel/SUT/new-truth/score chronology is invalid")
        runs = _index(audit["runs"],"invocation_id")
        sut_runs = [r for r in runs.values() if r["role"]=="sut"]
        if len(sut_runs)!=1:
            errors.append("One exact actual projection SUT invocation required")
        for run in runs.values():
            start,end = timestamp(run["started_on"]),timestamp(run["completed_on"])
            if run["fixture"] or not run["actual_execution"] or not ordered[0]<start<=end<=now:
                errors.append("Invalid actual run provenance/chronology")
            if run["role"]=="sut":
                if not seq["sut_started_on"]<=start<=end<=seq["predictions_sealed_on"]:
                    errors.append("SUT execution is outside its actual pre-truth sealed interval")
                if run["input_projection_sha256"]!=audit["method"]["input_graph_bytes_sha256"]:
                    errors.append("SUT did not consume the exact genuine frozen input graph")
            else:
                obs = timestamp(run["source_observations_frozen_on"])
                if not seq["truth_started_on"]<=start<=obs<end<=seq["truth_sealed_on"]:
                    errors.append("Truth source-only observations must precede sealed decisions")
                if not SHA.fullmatch(str(run["source_observations_sha256"])):
                    errors.append("Frozen source-only observation commitment missing")
                if (run["input_projection_sha256"]!=audit["method"]["source_packet_sha256"]
                        or run["blind_to_predictions_and_status"] is not True):
                    errors.append("New audit truth lacks the exact blinded source-only input projection")
        output = rg.public_graph(graph)
        output_assertions=_index(output["assertions"],"id")
        output_ids = {r["id"] for r in output["assertions"]}
        current = sampled_bindings(graph,audit["selected_assertion_ids"],output_ids)
        for original,new in zip(audit["bindings"],current):
            # Extra review links are permitted; every original review is exact
            # and attached. True claim/status/source/identity changes are holds.
            subset = {rid:new["original_review_record_sha256"].get(rid) for rid in original["original_review_record_sha256"]}
            if {**new,"original_review_record_sha256":subset} != original:
                errors.append("Sampled current scientific/source/identity/status/output/original-review binding changed")
        bindings = _index(audit["bindings"],"assertion_id")
        frame = _index(audit["frame"],"assertion_id")
        sources = _index(graph["sources"],"id")
        old_invocations = {r.get("invocation_id") for r in graph["reviews"] if r["id"] in {
            rid for b in audit["bindings"] for rid in b["original_review_record_sha256"]}}
        for run in runs.values():
            if run["invocation_id"] in old_invocations:
                errors.append("Old scientific review invocation cannot stand in for new audit execution/truth")
        for binding in audit["bindings"]:
            aid=binding["assertion_id"]
            if binding["observed_positive"] and aid in output_assertions and rg.assertion_digest(output_assertions[aid])!=binding["scientific_sha256"]:
                errors.append("An emitted ID alone does not preserve the exact scientific hypothesis")
            if (frame[aid]["scientific_sha256"]!=binding["scientific_sha256"] or
                    (frame[aid]["disposition_stratum"]=="included") is not binding["observed_positive"]):
                errors.append("Selected case differs from frozen genuine disposition frame")
            for pin in binding["source_pins"]:
                if timestamp(pin["captured_on"])>seq["input_frozen_on"]:
                    errors.append("Sampled source capture postdates frozen input/SUT")
                if sources[pin["source_id"]]["status"]!="captured" or sources[pin["source_id"]]["source_type"]=="metadata":
                    errors.append("Sampled source is not captured primary-source evidence")
        for case in audit["truth"]:
            by_role={}
            for receipt in case["review_receipts"]:
                run=runs.get(receipt["invocation_id"],{})
                role=run.get("role")
                if role not in TRUTH_ROLES | {"audit_tie_adjudicator"} or role in by_role:
                    errors.append("Truth requires distinct actual audit source/adversarial/tie roles")
                by_role[role]=receipt
                if receipt["scientific_sha256"]!=bindings[case["assertion_id"]]["scientific_sha256"]:
                    errors.append("Audit truth does not bind exact scoped scientific assertion")
                for pin in receipt["evidence"]:
                    if pin["source_id"] not in bindings[case["assertion_id"]]["source_record_sha256"]:
                        errors.append("Audit truth uses evidence outside the frozen cited-source hypothesis")
                if not receipt["evidence"]:
                    errors.append("Actual audit source reading needs scoped source evidence")
                if receipt["decision"]=="supported" and receipt["critical_if_accepted"] is True:
                    errors.append("Supported exact hypothesis cannot also be critically false attribution")
            if not TRUTH_ROLES<=set(by_role):
                errors.append("Both independent actual audit-truth roles are required")
                continue
            primary=[(by_role[r]["decision"],by_role[r]["critical_if_accepted"]) for r in sorted(TRUTH_ROLES)]
            resolved=primary[0]
            if primary[0]!=primary[1]:
                tie=by_role.get("audit_tie_adjudicator")
                if tie is None:
                    errors.append("Retained source-grounded tie decision required for disagreement")
                    continue
                resolved=(tie["decision"],tie["critical_if_accepted"])
            if (case["decision"],case["critical_if_accepted"])!=resolved:
                errors.append("Consensus truth differs from retained independent decisions")
        metrics=recompute_reference(audit,thresholds=thresholds)
        if metrics["sample_size"]!=200:
            errors.append("Exactly 200 genuine fixed assertion cases required")
        if not metrics["observed_withheld"]:
            errors.append("An all-output panel leaves rejection/false-negative behavior untested")
        if metrics["unknown"]:
            errors.append("Unknown gold remains in the fixed panel and holds completion")
        if metrics["critical_false_attributions"] or metrics["unresolved_critical_attributions"]:
            errors.append("Critical or unresolved attribution adjudication holds completion")
        if not metrics["numerical_thresholds_met"]:
            errors.append("Reference panel misses unchanged 200/98-percent/95-percent floors")
        return list(dict.fromkeys(errors)),metrics
    except (ValueError,KeyError,TypeError,OverflowError) as error:
        return list(dict.fromkeys(errors+[f"Invalid reference audit: {error}"])),{}


def _original_entry(value, pointer):
    if not isinstance(pointer,str) or not pointer.startswith("/"):
        raise ValueError("Exact original truth-entry pointer required")
    for part in pointer[1:].split("/"):
        token=part.replace("~1","/").replace("~0","~")
        value=value[int(token)] if isinstance(value,list) else value[token]
    return value


def validate_private_reference_v3(audit_bytes, current_graph, *, expected_artifact_hashes,
        artifact_payloads, source_payloads, invocation_id, reviewer, fixture):
    """Authenticate originals and preserve all holds; never make an admission.

    Replaying the projection is an integrity check of the sealed actual run.
    It is never treated as a new pre-gold prediction or a scientific review.
    """
    audit=load_exact(audit_bytes)
    now=datetime.now(timezone.utc)
    errors,metrics=_validate_core(audit,current_graph,now)
    if not invocation_id or not reviewer or type(fixture) is not bool:
        raise ValueError("Actual distinct validator identity and explicit fixture flag required")
    if invocation_id in {r["invocation_id"] for r in audit["runs"]}:
        errors.append("Private validation must be a separate actual invocation")
    declared=audit["artifacts"]
    if expected_artifact_hashes!=declared or not REQUIRED_ARTIFACTS<=set(declared):
        errors.append("Independently retained closed original artifact commitments required")
    if set(artifact_payloads)!=set(declared):
        errors.append("Every exact original artifact payload is required")
    authentic={}
    for name,digest in declared.items():
        raw=artifact_payloads.get(name)
        if not isinstance(raw,bytes) or byte_hash(raw)!=digest:
            errors.append(f"Original artifact authentication failed: {name}")
        else:
            authentic[name]=raw
    try:
        frozen=load_exact(authentic["input_graph"])
        output=load_exact(authentic["sut_output"])
        execution=load_exact(authentic["sut_execution"])
        exposure=load_exact(authentic["exposure_registry"])
        curation=load_exact(authentic["frame_curation"])
        frame=build_reference_frame(frozen,curation["records"],exposure)
        if frame!=audit["frame"] or exposure!=audit["exposure_registry"]:
            errors.append("Public neutral frame/exposure projection differs from genuine original inputs")
        if (canonical_hash(frozen)!=audit["method"]["input_graph_sha256"]
                or byte_hash(authentic["input_graph"])!=audit["method"]["input_graph_bytes_sha256"]
                or canonical_hash(output)!=audit["method"]["output_graph_sha256"]
                or canonical_hash(rg.public_graph(frozen))!=canonical_hash(output)):
            errors.append("Sealed unchanged actual SUT input/output replay does not match")
        if (audit["bindings"]!=sampled_bindings(frozen,audit["selected_assertion_ids"],
                {r["id"] for r in output["assertions"]})):
            errors.append("Scientific/current-status predictions do not match exact original frozen SUT")
        run=next(r for r in audit["runs"] if r["role"]=="sut")
        for field in ("invocation_id","reviewer","started_on","completed_on","fixture","actual_execution"):
            if execution.get(field)!=run[field]:
                errors.append("Projected SUT execution metadata differs from exact original run artifact")
        for field in ("input_graph_sha256","input_graph_bytes_sha256","output_graph_sha256","sut_source_sha256"):
            original_key="input_bytes_sha256" if field=="input_graph_bytes_sha256" else field
            if execution.get(original_key)!=audit["method"][field]:
                errors.append("Actual SUT execution input/output/code commitment differs")
        if execution.get("endpoint")!=ENDPOINT:
            errors.append("A different endpoint cannot be substituted for the actual production SUT")
        if (declared["source_packet"]!=audit["method"]["source_packet_sha256"]
                or declared["method_adoption"]!=audit["method"]["adoption_sha256"]):
            errors.append("Actual source-only packet or method-adoption artifact differs")
        runs=_index(audit["runs"],"invocation_id")
        for case in audit["truth"]:
            for receipt in case["review_receipts"]:
                envelope=load_exact(authentic[receipt["artifact_id"]])
                entry=_original_entry(envelope,receipt["entry_pointer"])
                projected={key:receipt[key] for key in ("decision","critical_if_accepted","scientific_sha256","evidence")}
                if (canonical_hash(entry)!=receipt["entry_sha256"] or
                        entry!={"assertion_id":case["assertion_id"],**projected}):
                    errors.append("Audit truth differs from exact original independent decision entry")
                run=runs[receipt["invocation_id"]]
                for key in ("invocation_id","role","reviewer","started_on","completed_on",
                            "source_observations_frozen_on","source_observations_sha256",
                            "input_projection_sha256","blind_to_predictions_and_status","fixture","actual_execution"):
                    if envelope.get(key)!=run[key]:
                        errors.append("Actual independent truth metadata differs from projected provenance")
                notes=authentic.get(run["source_observations_artifact_id"])
                if not isinstance(notes,bytes) or byte_hash(notes)!=run["source_observations_sha256"]:
                    errors.append("Exact independently frozen source-only observations are not authenticated")
    except (KeyError,ValueError,TypeError,IndexError,StopIteration) as error:
        errors.append(f"Original private execution validation incomplete: {error}")
    digests={pin["response_sha256"] for b in audit["bindings"] for pin in b["source_pins"]}
    if set(source_payloads)!=digests or any(not isinstance(source_payloads.get(d),bytes)
            or byte_hash(source_payloads[d])!=d for d in digests):
        errors.append("All distinct sampled raw primary-source response bytes must authenticate")
    root=Path(__file__).resolve().parents[1]
    receipt={"schema_version":RECEIPT_VERSION,"audit_sha256":byte_hash(audit_bytes),
        "method_sha256":audit["method_sha256"],"sample_bindings_sha256":canonical_hash(audit["bindings"]),
        "artifact_commitments_sha256":canonical_hash(expected_artifact_hashes),
        "source_authentication_sha256":canonical_hash(sorted(digests)),
        "validator_code_pins":{name:byte_hash((root/name).read_bytes()) for name in CODE_FILES},
        "validation_run":{"invocation_id":invocation_id,"reviewer":reviewer,"validated_on":now.isoformat(),
                          "fixture":fixture,"actual_execution":True},
        "validation_errors":list(dict.fromkeys(errors))}
    return (json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode()


def validate_public_reference_v3(audit_bytes,current_graph,validation_receipt_bytes,*,trusted_admission,thresholds=None):
    """Live applicability against complete current input, with separate trust.

    A filtered output lacking withheld scientific records cannot reconstruct their
    mutable bindings. Frozen archive receipt verification is a different scope;
    this function does not silently select that mode or discover private files.
    """
    errors,metrics=[],{}
    try:
        audit,receipt=load_exact(audit_bytes),load_exact(validation_receipt_bytes)
        now=datetime.now(timezone.utc)
        errors,metrics=_validate_core(audit,current_graph,now,thresholds)
        receipt_fields={"schema_version","audit_sha256","method_sha256","sample_bindings_sha256",
            "artifact_commitments_sha256","source_authentication_sha256","validator_code_pins",
            "validation_run","validation_errors"}
        if set(receipt)!=receipt_fields or receipt["schema_version"]!=RECEIPT_VERSION or _safe_public(receipt):
            raise ValueError("Unsupported/private reference validation receipt")
        root=Path(__file__).resolve().parents[1]
        pins={name:byte_hash((root/name).read_bytes()) for name in CODE_FILES}
        if receipt["validator_code_pins"]!=pins:
            raise ValueError("Actual reader/schema/SUT capsule differs from independently reviewed validator")
        digests=sorted({p["response_sha256"] for b in audit["bindings"] for p in b["source_pins"]})
        if (receipt["audit_sha256"]!=byte_hash(audit_bytes) or receipt["method_sha256"]!=audit["method_sha256"]
                or receipt["sample_bindings_sha256"]!=canonical_hash(audit["bindings"])
                or receipt["artifact_commitments_sha256"]!=canonical_hash(audit["artifacts"])
                or receipt["source_authentication_sha256"]!=canonical_hash(digests)):
            raise ValueError("Private validation authenticates different exact originals")
        validation=receipt["validation_run"]
        if set(validation)!={"invocation_id","reviewer","validated_on","fixture","actual_execution"}:
            raise ValueError("Actual private validation metadata required")
        run_ids={r["invocation_id"] for r in audit["runs"]}
        if (validation["fixture"] is not False or validation["actual_execution"] is not True
                or not validation["invocation_id"] or not validation["reviewer"] or validation["invocation_id"] in run_ids):
            raise ValueError("Actual distinct non-fixture validation invocation required")
        if not isinstance(receipt["validation_errors"],list) or any(type(e)is not str for e in receipt["validation_errors"]):
            raise ValueError("Complete preserved private validation holds required")
        errors.extend(receipt["validation_errors"])
        a=trusted_admission
        fields={"schema_version","status","audit_sha256","receipt_sha256","validator_capsule_sha256",
            "validation_invocation_id","independent_review_invocation_id","independent_reviewer",
            "independent_review_sha256","reviewed_on","admitted_on","method_adoption_sha256",
            "exposure_review_sha256","completion_authorized"}
        if not isinstance(a,dict) or set(a)!=fields or _safe_public(a):
            raise ValueError("Separately reviewed caller-trusted admission required")
        if a["schema_version"]!=ADMISSION_VERSION or a["status"]!="accepted":
            raise ValueError("Unaccepted reference admission")
        if (a["audit_sha256"]!=byte_hash(audit_bytes) or a["receipt_sha256"]!=byte_hash(validation_receipt_bytes)
                or a["validator_capsule_sha256"]!=canonical_hash(pins)
                or a["validation_invocation_id"]!=validation["invocation_id"]
                or a["method_adoption_sha256"]!=audit["method"]["adoption_sha256"]
                or a["exposure_review_sha256"]!=audit["exposure_registry"]["semantic_review_sha256"]):
            raise ValueError("Admission does not authenticate exact reviewed audit/receipt/method/code")
        if (not a["independent_review_invocation_id"] or not a["independent_reviewer"]
                or a["independent_review_invocation_id"] in run_ids|{validation["invocation_id"]}
                or not SHA.fullmatch(str(a["independent_review_sha256"]))):
            raise ValueError("A distinct actual independent admission review is required")
        if not timestamp(audit["chronology"]["scored_on"])<=timestamp(validation["validated_on"])<=timestamp(a["reviewed_on"])<=timestamp(a["admitted_on"])<=now:
            raise ValueError("Actual validation/review/admission chronology is invalid")
        if type(a["completion_authorized"]) is not bool:
            raise ValueError("Explicit completion authorization required")
        if metrics:
            metrics.update({"integrity_valid":not errors,"execution_admitted":True,
                            "completion_authorized":a["completion_authorized"]})
        if audit["status"]!="completed" or not a["completion_authorized"]:
            errors.append("Formal reference completion is not independently authorized")
        if metrics:
            metrics["publication_eligible"]=not errors
    except (ValueError,KeyError,TypeError,UnicodeError,OverflowError,OSError) as error:
        errors.append(str(error))
    return list(dict.fromkeys(errors)),metrics
