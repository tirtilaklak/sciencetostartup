"""Proposed initial-hypothesis, genuine-input source-quality holdout.

No scientific verdict/approval or actual research receipt is created at import.
The actual SUT is unchanged research_graph.public_graph. Audit source truth and
scientific approval are different records. An independent reviewed admission is
always required; arbitrary invocation strings establish no actual execution.
"""
from __future__ import annotations

import json
import math
import copy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import research_graph as rg
from screening_audit_v3 import (
    SHA, _index, _safe_public, _safe_error, _shape, byte_hash, canonical_hash, load_exact, timestamp,
)

VERSION = "reference-audit-v4"
RECEIPT_VERSION = "reference-private-validation-v4"
ADMISSION_VERSION = "reference-audit-admission-v4"
KIND = "source_bound_initial_hypothesis_disposition_holdout"
ENDPOINT = "research_graph.public_graph"
FLOORS = {"reference_sample_size": 200, "reference_precision": .98, "reference_recall": .95}
SEED = "STS-reference-initial-peer-hypothesis-v4-prospective-2026-11-12"
TRUTH_ROLES = {"audit_source_adjudicator", "audit_adversarial_adjudicator"}
CODE_FILES = ("scripts/reference_audit_v4.py", "schema/reference-audit.v4.schema.json",
    "scripts/screening_audit_v3.py", "scripts/research_audit_dispatch.py", "scripts/research_graph.py")
EXPOSURE_PUBLIC_FIELDS = frozenset({"assertion_ids", "scientific_digests", "finding_equivalence_keys",
    "semantic_review_sha256", "source_artifact_pins", "lineage_keys"})
EXPOSURE_PRIVATE_METADATA_FIELDS = frozenset({"all_old_exposure_and_hold_decisions_unchanged",
    "coarse475_are_retained_holds_not_certified_exact_exposures", "derived_on",
    "old_coarse_registry_not_merged_as_false_exact_exposure", "original_eligibility_acceptance_ref",
    "original_exact_scope_identity_supplement", "original_semantic_review_ref", "previous_draft_preserved"})
REQUIRED_ARTIFACTS = {"input_graph", "sut_output", "sut_execution", "frame_curation",
    "exposure_registry", "source_packet", "method_adoption", "exposure_reference250",
    "exposure_reference226", "exposure_citation62", "exposure_semantic_review",
    "exposure_reference200", "exposure_repairs88", "lineage_manifest",
    "population_semantic_review", "metadata_adaptations"}


def public_exposure_registry(registry):
    """Project the six exposure fields, retaining full private originals elsewhere.

    Only known provenance annotations may be omitted. Every scientific exposure
    set and original-scope commitment remains exact; unknown fields fail closed.
    Private authentication and population review still bind all original bytes.
    """
    if (not isinstance(registry, dict) or not EXPOSURE_PUBLIC_FIELDS <= registry.keys()
            or set(registry) - EXPOSURE_PUBLIC_FIELDS - EXPOSURE_PRIVATE_METADATA_FIELDS):
        raise ValueError("Complete known exposure registry fields required")
    return {key: copy.deepcopy(registry[key]) for key in sorted(EXPOSURE_PUBLIC_FIELDS)}


def entity_identity(row):
    return {key: row.get(key) for key in ("id", "kind", "name", "identifiers", "aliases", "parent_id", "family_id")}


POPULATION_RULE = "first_peer_submitted_substantive_hypothesis_per_semantic_lineage"
EXPOSURE_SCOPES = ("reference250", "reference226", "citation62", "reference200", "repairs88")
POPULATION_PINS = {"curation_sha256": "frame_curation", "lineage_manifest_sha256": "lineage_manifest",
    "population_review_sha256": "population_semantic_review", "metadata_adaptations_sha256": "metadata_adaptations"}
FILLER_PREDICATES = {"legacy_description", "version_of", "release_of", "title", "name", "same_as", "identity"}
LIMITATIONS = {"genuine_disposition_stratified_panel", "raw_panel_metrics_not_population_estimates",
    "no_extraction_or_discovery_recall", "supported_prudently_withheld_claim_is_false_negative",
    "withheld_live_bindings_require_complete_current_input", "initial_rule_proposed_after_production_review",
    "corrected_successors_never_additional_cases", "no_final_corrected_output_population_precision",
    "preparatory_source_familiarity_disclosed"}


def _original_entry(value, pointer):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Exact original entry pointer required")
    for part in pointer[1:].split("/"):
        token = part.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _referenced_original(reference, payloads):
    """Authenticate an entry from supplied retained bytes; never open a path."""
    if set(reference) != {"artifact_id", "entry_pointer", "entry_sha256"}:
        raise ValueError("Closed original artifact entry reference required")
    raw = payloads[reference["artifact_id"]]
    value = _original_entry(load_exact(raw), reference["entry_pointer"])
    if canonical_hash(value) != reference["entry_sha256"]:
        raise ValueError("Original provenance entry commitment differs")
    return value


def _pointer_contains(parent, child):
    """Test JSON-pointer token ancestry; /event/1 is not /event/10."""
    def tokens(pointer):
        if pointer == "":
            return []
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("Exact original entry pointer required")
        return [part.replace("~1", "/").replace("~0", "~")
                for part in pointer[1:].split("/")]
    before, after = tokens(parent), tokens(child)
    return after[:len(before)] == before


def _actual_review(entry):
    if (not entry.get("invocation_id") or not entry.get("reviewer")
            or entry.get("actual_execution") is not True or entry.get("fixture") is not False):
        raise ValueError("Actual separately retained non-fixture provenance required")
    return timestamp(entry["reviewed_on"])


def validate_metadata_adaptations(graph, adaptations, artifact_payloads):
    """Check metadata-only identity preservation, never scientific source approval.

    Creator identity and exact artifact class are independently reviewed facts,
    not inferred from a domain or filename. Independent originals are retained.
    """
    sources = _index(graph["sources"], "id")
    result = {}
    for row in adaptations["records"]:
        sid = row["source_id"]
        if sid in result:
            raise ValueError("Duplicate source metadata adaptation")
        before, after = row["before_record"], row["after_record"]
        kind = row["artifact_kind"]
        target = {"creator_github_readme_or_license": "repository",
            "creator_huggingface_dataset_card": "dataset_card",
            "creator_protocol_report": "provider_documentation"}.get(kind)
        if (target is None or before["source_type"] != "documentation"
                or after["source_type"] != target or after != sources[sid]
                or before["id"] != sid or {**before, "source_type": target} != after):
            raise ValueError("Only exact documentation-to-creator-artifact metadata adaptation is allowed")
        url = urlsplit(after["url"])
        filename = url.path.rstrip("/").rsplit("/", 1)[-1].lower()
        if kind == "creator_github_readme_or_license" and (url.hostname not in {
                "github.com", "raw.githubusercontent.com"} or not (
                filename in {"readme", "license"} or filename.startswith("readme.") or filename.startswith("license."))):
            raise ValueError("Repository adaptation requires the exact creator GitHub README/LICENSE")
        parts = [part for part in url.path.split("/") if part]
        if kind == "creator_huggingface_dataset_card" and (url.hostname != "huggingface.co"
                or not parts or parts[0] != "datasets" or not (
                    len(parts) == 3 or len(parts) >= 6 and parts[3] in {"blob", "raw", "resolve"} and filename == "readme.md")):
            raise ValueError("Dataset-card adaptation requires the exact creator Hugging Face card")
        creator = _referenced_original(row["creator_identity_ref"], artifact_payloads)
        if not creator:
            raise ValueError("Original creator identity evidence required")
        reviews = [_referenced_original(ref, artifact_payloads) for ref in row["review_refs"]]
        if (not reviews or len({r["invocation_id"] for r in reviews}) != len(reviews)
                or not row["author_invocation_id"]
                or row["author_invocation_id"] in {r["invocation_id"] for r in reviews}):
            raise ValueError("Actual independently retained metadata-adaptation review required")
        for review in reviews:
            _actual_review(review)
            expected = {"source_id": sid, "before_record_sha256": canonical_hash(before),
                "after_record_sha256": canonical_hash(after), "artifact_kind": kind,
                "creator_identity_sha256": canonical_hash(creator), "decision": "metadata_only_creator_artifact"}
            if any(review.get(key) != value for key, value in expected.items()):
                raise ValueError("Metadata review does not bind exact before/after/creator originals")
        result[sid] = row
    return result


def _lineage_population(graph, manifest):
    current = {a["id"] for a in graph["assertions"] if a["status"] != "historical"}
    if manifest["population_rule"] != POPULATION_RULE or manifest["input_graph_sha256"] != canonical_hash(graph):
        raise ValueError("Lineage ledger must bind the complete genuine input and uniform initial rule")
    lineages, members = _index(manifest["lineages"], "lineage_sha256"), {}
    for lineage in lineages.values():
        ids = lineage["member_assertion_ids"]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Nonempty distinct lineage members required")
        for aid in ids:
            if aid in members:
                raise ValueError("Every population assertion belongs to exactly one semantic lineage")
            members[aid] = lineage
    if set(members) != current:
        raise ValueError("Complete nonhistorical-input lineage crosswalk required")
    return members


def _grouped_submission(row, payloads):
    """Read an explicitly derived bridge to genuine grouped packet/opening bytes.

    This does not invent an atomic old receiving receipt, invocation or review.
    The original opening may have no invocation identifier; that absence stays
    unknown. Its closed original artifact, packet binding, exact group and prior
    independent opening authentication remain the provenance instead.
    """
    if row["provenance_representation"] != "derived_grouped_packet_v1":
        raise ValueError("Unsupported grouped original-event representation")
    derived = timestamp(row["derived_on"])
    if derived > datetime.now(timezone.utc):
        raise ValueError("Derived provenance projection cannot be future dated")
    assertion = _referenced_original(row["submission_ref"], payloads)
    packet_id = row["submission_ref"]["artifact_id"]
    packet_sha = byte_hash(payloads[packet_id])
    # Every scientific/source entry comes directly from the actual opened packet.
    if any(ref["artifact_id"] != packet_id for ref in row["source_refs"]):
        raise ValueError("Grouped submission sources must be exact entries of the opened packet")
    sources = [_referenced_original(ref, payloads) for ref in row["source_refs"]]
    opening = _referenced_original(row["peer_opening_ref"], payloads)
    original_event = _referenced_original(row["peer_receipt_ref"], payloads)
    group = _referenced_original(row["group_authentication_ref"], payloads)
    role = group["earliest_role"]
    if role not in {"source_verifier", "adversarial"}:
        raise ValueError("Authenticated actual receiving peer role required")
    event_pin = group["verifier_receipt"] if role == "source_verifier" else group["adversary_start_record"]
    expected_opening = min(timestamp(group["verifier_start"]), timestamp(group["adversary_start"]))
    selected_role_start = timestamp(group["verifier_start"] if role == "source_verifier" else group["adversary_start"])
    if (not isinstance(original_event, (dict, list)) or not original_event
            or selected_role_start != expected_opening
            or row["peer_opening_ref"]["artifact_id"] != row["peer_receipt_ref"]["artifact_id"]
            or not _pointer_contains(row["peer_receipt_ref"]["entry_pointer"],
                                     row["peer_opening_ref"]["entry_pointer"])
            or byte_hash(payloads[row["peer_receipt_ref"]["artifact_id"]]) != event_pin["sha256"]
            or group["packet"]["sha256"] != packet_sha
            or timestamp(opening) != expected_opening
            or timestamp(group["first_authenticated_opening"]) != expected_opening
            or timestamp(row["first_peer_submitted_on"]) != expected_opening or derived < expected_opening):
        raise ValueError("Derived group bridge differs from actual earliest opening and exact original packet")
    binding_ref = row["packet_digest_ref"]
    binding_sha = byte_hash(payloads[binding_ref["artifact_id"]])
    allowed_binding = {event_pin["sha256"]}
    if role == "adversarial":
        allowed_binding.add(group["adversary_sealed_index"]["sha256"])
    if binding_sha not in allowed_binding or _referenced_original(binding_ref, payloads) != packet_sha:
        raise ValueError("Original grouped receiving/sealed artifact must bind the exact opened packet bytes")
    if (binding_sha == event_pin["sha256"]
            and not _pointer_contains(row["peer_receipt_ref"]["entry_pointer"], binding_ref["entry_pointer"])):
        raise ValueError("Original receiving entry must contain its same-artifact packet binding")
    # The wrapper below is only a transient reader view, never a historical file.
    return {"assertion": assertion, "sources": sources}, {"received_on": opening}


def _first_submission(graph, lineage, payloads, adaptations):
    assertions = _index(graph["assertions"], "id")
    sources = _index(graph["sources"], "id")
    history = _referenced_original(lineage["history_ref"], payloads)
    if not history:
        raise ValueError("Retained original production lineage/correction-history artifact required")
    submissions = lineage["submissions"]
    if not submissions:
        raise ValueError("Missing authenticated earliest genuine peer submission")
    rows = []
    for row in submissions:
        grouped = "provenance_representation" in row
        if grouped:
            original, peer = _grouped_submission(row, payloads)
        else:
            original = _referenced_original(row["submission_ref"], payloads)
            peer = _referenced_original(row["peer_receipt_ref"], payloads)
        assertion = original["assertion"]
        aid = assertion["id"]
        scientific = rg.assertion_digest(assertion)
        if row["assertion_id"] != aid:
            raise ValueError("Original submitted hypothesis identity differs")
        if not grouped and (peer["assertion_id"] != aid
                or peer["scientific_sha256"] != scientific
                or peer["submission_entry_sha256"] != row["submission_ref"]["entry_sha256"]
                or peer["actual_execution"] is not True or peer["fixture"] is not False
                or not peer["invocation_id"] or not peer["reviewer"]):
            raise ValueError("Original first-peer receipt does not authenticate its exact submitted hypothesis")
        submitted = timestamp(peer["received_on"])
        if (not grouped and peer["event"] != "peer_submission") or timestamp(row["first_peer_submitted_on"]) != submitted:
            raise ValueError("First-peer time differs from original received event")
        if aid in assertions and scientific != rg.assertion_digest(assertions[aid]):
            raise ValueError("Scientific/evidence changes cannot be normalized as metadata adaptation")
        original_sources = _index(original["sources"], "id")
        cited = {e["source_id"] for e in assertion["evidence"]}
        if set(original_sources) != cited:
            raise ValueError("Every exact first-submission cited source record is required")
        for sid in cited:
            before = original_sources[sid]
            if sources.get(sid) != before and (sid not in adaptations
                    or before != adaptations[sid]["before_record"]
                    or sources.get(sid) != adaptations[sid]["after_record"]):
                raise ValueError("First-submission source fields changed outside the exact metadata rule")
            if timestamp(before["captured_on"]) > submitted:
                raise ValueError("Source capture cannot postdate the actual first peer submission")
        if not grouped and peer["source_record_sha256"] != {sid: canonical_hash(original_sources[sid]) for sid in sorted(cited)}:
            raise ValueError("First-peer receipt source-record pins differ")
        rows.append((submitted, aid, row, original, peer))
    if len({r[1] for r in rows}) != len(rows):
        raise ValueError("Duplicate submitted hypothesis in semantic lineage")
    first = min(rows, key=lambda row: (row[0], row[1]))
    if sum(row[0] == first[0] for row in rows) != 1:
        raise ValueError("Ambiguous earliest peer submission remains held")
    if (lineage["first_assertion_id"] != first[1] or first[1] not in lineage["member_assertion_ids"]
            or first[1] not in assertions or assertions[first[1]]["status"] == "historical"):
        raise ValueError("Missing earliest actual input hypothesis; corrected successors cannot become cases")
    represented = {r[1] for r in rows}
    peer_openings = {r[1]: r[0] for r in rows}
    for successor in lineage.get("authenticated_successors", []):
        chain = _referenced_original(successor["chain_ref"], payloads)
        aid = successor["assertion_id"]
        opening = _referenced_original(successor["opening_ref"], payloads)
        artifact_sha = byte_hash(payloads[successor["opening_ref"]["artifact_id"]])
        actual = chain["successor_actual_opening"]
        if (aid in represented or aid not in assertions or chain["original_assertion_id"] != first[1]
                or chain["original_scientific_sha256"] != rg.assertion_digest(assertions[first[1]])
                or chain["successor_assertion_id"] != aid
                or chain["successor_scientific_sha256"] != rg.assertion_digest(assertions[aid])
                or chain["initial_time_not_reset"] is not True
                or timestamp(chain["original_first_actual_peer_opening"]) != first[0]
                or timestamp(opening) <= first[0]
                or timestamp(actual["first_successor_recorded_opening"]) != timestamp(opening)
                or not any(pin["artifact"]["sha256"] == artifact_sha and timestamp(pin["opened_on"]) == timestamp(opening)
                    for pin in actual["actual_opening_records"])):
            raise ValueError("Preserved actual successor chain/opening cannot replace or predate the initial hypothesis")
        represented.add(aid)
        peer_openings[aid] = timestamp(opening)
    if set(lineage["member_assertion_ids"]) != represented:
        raise ValueError("All genuine current lineage submissions require original provenance")
    reviews = _index(graph["reviews"], "id")
    for aid, submitted in peer_openings.items():
        if aid in assertions:
            for rid in assertions[aid]["review_ids"]:
                if (reviews[rid]["role"] in {"source_verifier", "adversarial"}
                        and timestamp(reviews[rid]["reviewed_on"]) < submitted):
                    raise ValueError("Production peer review precedes the authenticated first peer submission")
    return first


def build_reference_frame(graph, curation_records, exposure_registry, lineage_manifest, *,
        artifact_payloads, metadata_adaptations):
    """Mechanically authenticate uniform first-hypothesis selection on a census.

    Semantic equivalence, substantive units, exposure completeness and creator
    identity remain actual independent reviewer duties. Strings do not prove them.
    Excluded/held rows stay in the complete curation and lineage artifacts.
    """
    assertions = _index(graph["assertions"], "id")
    sources = _index(graph["sources"], "id")
    curated = _index(curation_records, "assertion_id")
    population = _lineage_population(graph, lineage_manifest)
    if set(curated) != set(population):
        raise ValueError("Complete actual nonhistorical-input curation ledger required")
    adaptations = validate_metadata_adaptations(graph, metadata_adaptations, artifact_payloads)
    frame, groups, counted_lineages = [], set(), set()
    for aid in sorted(population):
        assertion, entry, lineage = assertions[aid], curated[aid], population[aid]
        if entry["lineage_sha256"] != lineage["lineage_sha256"]:
            raise ValueError("Curation differs from the complete semantic-lineage crosswalk")
        if entry["disposition"] not in {"include", "exclude", "held"} or not entry["reason"]:
            raise ValueError("Retained neutral inclusion/exclusion/hold reasons required")
        if entry["disposition"] != "include":
            continue
        first = _first_submission(graph, lineage, artifact_payloads, adaptations)
        _, initial_id, submission, _, _ = first
        if aid != initial_id or lineage["lineage_sha256"] in counted_lineages:
            raise ValueError("Exactly one initial genuine peer-submitted hypothesis per lineage required")
        scientific, equivalent = rg.assertion_digest(assertion), entry["finding_equivalence_sha256"]
        if (aid in exposure_registry["assertion_ids"] or scientific in exposure_registry["scientific_digests"]
                or equivalent in exposure_registry["finding_equivalence_keys"]
                or lineage["lineage_sha256"] in exposure_registry["lineage_keys"]
                or any(member in exposure_registry["assertion_ids"] for member in lineage["member_assertion_ids"])):
            raise ValueError("Exposed finding/equivalent/repair lineage cannot enter the fresh holdout frame")
        if equivalent in groups:
            raise ValueError("Duplicate scientific-finding equivalence unit in holdout frame")
        if entry["scope_kind"] != "substantive_scientific_finding" or assertion["predicate"] in FILLER_PREDICATES:
            raise ValueError("Historical/identity-only facts are not substantive holdout findings")
        evidence = assertion.get("evidence", [])
        if not evidence or any(sources.get(e["source_id"], {}).get("status") != "captured"
                or sources[e["source_id"]].get("source_type") in {"metadata", "legacy", "documentation"}
                for e in evidence):
            raise ValueError("Genuine substantive cases require actual captured primary-source pins")
        groups.add(equivalent)
        counted_lineages.add(lineage["lineage_sha256"])
        frame.append({"assertion_id": aid, "scientific_sha256": scientific,
            "finding_equivalence_sha256": equivalent, "curation_entry_sha256": canonical_hash(entry),
            "lineage_sha256": lineage["lineage_sha256"],
            "lineage_history_sha256": lineage["history_ref"]["entry_sha256"],
            "first_submission_sha256": submission["submission_ref"]["entry_sha256"],
            "first_peer_receipt_sha256": submission["peer_receipt_ref"]["entry_sha256"],
            "first_peer_submitted_on": submission["first_peer_submitted_on"],
            "disposition_stratum": "included" if assertion["status"] == "approved" else "withheld",
            "predicate": assertion["predicate"], "source_domains": sorted({
                urlsplit(sources[e["source_id"]]["url"]).netloc for e in evidence})})
    return frame


def _validate_population_review(audit, graph, curation, manifest, exposure, adaptations, payloads):
    """Authenticate complete review originals; semantic judgment is external work."""
    envelope = load_exact(payloads["population_semantic_review"])
    expected = {"input_graph_sha256": canonical_hash(graph),
        "frame_curation_sha256": byte_hash(payloads["frame_curation"]),
        "lineage_manifest_sha256": byte_hash(payloads["lineage_manifest"]),
        "exposure_registry_sha256": byte_hash(payloads["exposure_registry"]),
        "metadata_adaptations_sha256": byte_hash(payloads["metadata_adaptations"]),
        "exposure_semantic_review_sha256": byte_hash(payloads["exposure_semantic_review"]),
        "exposure_scopes_sha256": canonical_hash(exposure["source_artifact_pins"])}
    if envelope["input_commitments"] != expected:
        raise ValueError("Population review does not bind every exact curation/lineage/exposure/adaptation original")
    rows = _index(curation["records"], "assertion_id")
    population = _lineage_population(graph, manifest)
    if set(rows) != set(population):
        raise ValueError("Full population curation crosswalk required")
    refs = envelope["review_refs"]
    if not refs or not envelope["author_invocation_id"]:
        raise ValueError("Actual independent full-population semantic review original required")
    used = set()
    production = {r["invocation_id"] for r in graph["reviews"]}
    run_ids = {r["invocation_id"] for r in audit["runs"]}
    known_submitted = [timestamp(row["first_peer_submitted_on"])
        for lineage in manifest["lineages"] for row in lineage["submissions"]]
    derived = ([timestamp(manifest["derived_on"])] if manifest.get("derived_on") else [])
    derived += [timestamp(row["derived_on"]) for lineage in manifest["lineages"]
                for row in lineage["submissions"] if row.get("provenance_representation")]
    frozen_before = min(timestamp(audit["chronology"]["input_frozen_on"]),
                        timestamp(audit["chronology"]["frame_frozen_on"]))
    if any(value > frozen_before for value in derived):
        raise ValueError("Derived provenance must exist before its actual frozen input and frame")
    for ref in refs:
        review = _referenced_original(ref, payloads)
        reviewed = _actual_review(review)
        rid = review["invocation_id"]
        if (rid in used | production | run_ids | {envelope["author_invocation_id"]}
                or reviewed >= timestamp(audit["chronology"]["frame_frozen_on"])
                or known_submitted and reviewed < max(known_submitted)
                or derived and reviewed < max(derived)
                or review["input_commitments"] != expected):
            raise ValueError("Separate actual pre-frame population/exposure review provenance required")
        used.add(rid)
        decisions = _index(review["records"], "assertion_id")
        if set(decisions) != set(rows):
            raise ValueError("Independent review must cover every genuine nonhistorical input")
        for aid, row in rows.items():
            decision = decisions[aid]
            expected_row = {"assertion_id": aid, "lineage_sha256": population[aid]["lineage_sha256"],
                "curation_entry_sha256": canonical_hash(row), "disposition": row["disposition"],
                "finding_equivalence_sha256": row["finding_equivalence_sha256"],
                "scope_kind": row["scope_kind"], "lineage_history_sha256": (
                    population[aid]["history_ref"]["entry_sha256"] if population[aid].get("history_ref") else None)}
            if (any(decision.get(k) != v for k, v in expected_row.items())
                    or decision["exposure_decision"] not in {"unexposed", "exposed", "unresolved"}
                    or row["disposition"] == "include" and decision["exposure_decision"] != "unexposed"):
                raise ValueError("Independent semantic/exposure review differs from complete frozen curation")
    for adaptation in adaptations["records"]:
        for ref in adaptation["review_refs"]:
            if _actual_review(_referenced_original(ref, payloads)) >= timestamp(audit["chronology"]["input_frozen_on"]):
                raise ValueError("Metadata adaptation review must precede frozen input")


def _validate_source_context(run, authentic, truth, sources):
    """Require real post-start context-check/notes originals before hypotheses.

    This authenticates recorded work and exact scoped pins. It does not pretend
    that a timestamp or a note hash proves a scientific full-source read.
    """
    if run["role"] == "sut":
        return
    notes = load_exact(authentic[run["source_observations_artifact_id"]])
    context = load_exact(authentic[run["source_context_recheck_artifact_id"]])
    if (byte_hash(authentic[run["source_context_recheck_artifact_id"]]) != run["source_context_recheck_sha256"]
            or notes["invocation_id"] != run["invocation_id"]
            or notes["frozen_on"] != run["source_observations_frozen_on"]
            or context["invocation_id"] != run["invocation_id"]
            or context["started_on"] != run["source_context_recheck_started_on"]
            or context["completed_on"] != run["source_context_recheck_completed_on"]
            or context["source_packet_sha256"] != run["input_projection_sha256"]
            or notes["source_packet_sha256"] != run["input_projection_sha256"]
            or context["actual_execution"] is not True or context["fixture"] is not False):
        raise ValueError("Actual post-start source-context recheck/notes originals differ")
    scope_key = lambda row: (row["source_id"], row["locator"], row["reading_scope_sha256"])
    context_rows, note_rows = {scope_key(r) for r in context["records"]}, {scope_key(r) for r in notes["records"]}
    for row in context["records"] + notes["records"]:
        if (row["response_sha256"] != sources[row["source_id"]]["response_sha256"]
                or not SHA.fullmatch(str(row["reading_scope_sha256"])) or not row["locator"]):
            raise ValueError("Source-context recheck/notes lack exact actual primary-response pins")
    for case in truth:
        for receipt in case["review_receipts"]:
            if receipt["invocation_id"] == run["invocation_id"]:
                for evidence in receipt["evidence"]:
                    if scope_key(evidence) not in context_rows & note_rows:
                        raise ValueError("Exact adjudication scope lacks a fresh actual source-context recheck and frozen note")
    prep_id, prep_sha = run["preparatory_notes_artifact_id"], run["preparatory_notes_sha256"]
    if (prep_id is None) != (prep_sha is None):
        raise ValueError("Supplemental preparatory reading must be honestly paired and disclosed")
    if prep_id is not None and byte_hash(authentic[prep_id]) != prep_sha:
        raise ValueError("Original supplemental preparatory notes must authenticate without retimestamping")
    if (notes["supplemental_preparatory_notes_sha256"] != prep_sha
            or context["supplemental_preparatory_notes_sha256"] != prep_sha):
        raise ValueError("Preparatory notes cannot masquerade as fresh post-start source observations")


def select_reference_panel(frame, *, seed=SEED):
    """Fixed design: min(100, real withheld availability), fill to200 from output."""
    _index(frame, "assertion_id")
    if seed != SEED:
        raise ValueError("The new prospective fixed seed cannot be substituted")
    if (len({r["finding_equivalence_sha256"] for r in frame}) != len(frame)
            or len({r["lineage_sha256"] for r in frame}) != len(frame)):
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
        "supported_withheld":fn, "unsupported_withheld":tn,
        "all_supported_panel_recall_if_all_withheld_supported": (
            sum(b["observed_positive"] for b in bindings.values()) / len(selected) if selected else 0),
        "critical_false_attributions":critical, "unresolved_critical_attributions":unresolved,
        "thresholds":limits, "numerical_thresholds_met":len(selected)>=limits["reference_sample_size"]
            and not unknown and precision>=limits["reference_precision"] and recall>=limits["reference_recall"],
        "evaluation_kind":KIND, "publication_eligible":False}


def _validate_core(audit, graph, now, thresholds=None):
    root = Path(__file__).resolve().parents[1]
    schema = load_exact((root / "schema/reference-audit.v4.schema.json").read_bytes())
    errors = _shape(audit, schema)
    if errors:
        return errors, {}
    errors.extend(_safe_public(audit))
    try:
        if not audit["actual_execution"] or audit["fixture"]:
            errors.append("Actual non-fixture reference execution required")
        if len(audit["limitations"]) != len(LIMITATIONS) or set(audit["limitations"]) != LIMITATIONS:
            errors.append("All distinct initial-hypothesis bounded-scope reference disclosures are required")
        if audit["release_id"] != graph["release_id"]:
            errors.append("Reference release binding differs")
        if audit["method"]["sut_source_sha256"] != byte_hash((root/"scripts/research_graph.py").read_bytes()):
            errors.append("The actual SUT source code differs from the frozen version")
        if audit["method_sha256"] != canonical_hash(audit["method"]) or audit["frame_sha256"] != canonical_hash(audit["frame"]):
            errors.append("Method/frame commitment differs")
        if audit["method"]["seed"] != SEED:
            errors.append("The fixed reviewed sampling seed cannot change")
        if audit["method"]["population_rule"] != POPULATION_RULE:
            errors.append("Uniform actual first-peer initial-hypothesis population rule required")
        if not REQUIRED_ARTIFACTS <= set(audit["artifacts"]):
            errors.append("Complete original lineage/population/exposure/adaptation artifacts required")
        for field, artifact in POPULATION_PINS.items():
            if audit["method"][field] != audit["artifacts"].get(artifact):
                errors.append("Population/lineage/metadata commitments differ from authenticated originals")
        expected = select_reference_panel(audit["frame"])
        if audit["selected_assertion_ids"] != expected:
            errors.append("Selected holdout differs from fixed genuine-disposition sampling")
        for field, value in (("bindings_sha256",audit["bindings"]), ("truth_sha256",audit["truth"]),
                             ("membership_sha256",audit["selected_assertion_ids"])):
            if audit["commitments"][field] != canonical_hash(value):
                errors.append(f"{field} differs")
        excluded = audit["exposure_registry"]
        if not excluded["finding_equivalence_keys"] or not excluded["assertion_ids"] or not excluded["lineage_keys"]:
            errors.append("An empty self-declared exposure registry cannot cover old250/226/62/200/88-repair lineages")
        if audit["artifacts"].get("exposure_semantic_review")!=excluded["semantic_review_sha256"]:
            errors.append("Exact actual semantic exposure-review bytes must be privately authenticated")
        for scope in EXPOSURE_SCOPES:
            if audit["artifacts"].get("exposure_"+scope)!=excluded["source_artifact_pins"][scope]:
                errors.append("Exposure scope is not bound to the retained original source artifacts")
        for row in audit["frame"]:
            if (row["assertion_id"] in excluded["assertion_ids"] or row["scientific_sha256"] in excluded["scientific_digests"]
                    or row["finding_equivalence_sha256"] in excluded["finding_equivalence_keys"]
                    or row["lineage_sha256"] in excluded["lineage_keys"]):
                errors.append("Exposed finding/equivalent present in fresh holdout frame")
            if row["predicate"] in FILLER_PREDICATES:
                errors.append("Pure identity/version facts cannot fill the substantive scientific holdout")
        seq = {key:timestamp(value) for key,value in audit["chronology"].items()}
        ordered = [seq[key] for key in ("method_adopted_on","input_frozen_on","frame_frozen_on","panel_frozen_on",
            "sut_started_on","predictions_sealed_on","truth_started_on","truth_sealed_on","outcomes_opened_on","scored_on")]
        if any(a>=b for a,b in zip(ordered,ordered[1:])) or ordered[-1]>now:
            errors.append("Method/input/frame/panel/SUT/new-truth/score chronology is invalid")
        if any(timestamp(row["first_peer_submitted_on"]) >= seq["input_frozen_on"] for row in audit["frame"]):
            errors.append("Actual original first-peer submission must predate the frozen genuine input")
        if len({row["lineage_sha256"] for row in audit["frame"]}) != len(audit["frame"]):
            errors.append("Corrected successors cannot provide additional frame cases")
        runs = _index(audit["runs"],"invocation_id")
        sut_runs = [r for r in runs.values() if r["role"]=="sut"]
        if len(sut_runs)!=1:
            errors.append("One exact actual projection SUT invocation required")
        for run in runs.values():
            start,end = timestamp(run["started_on"]),timestamp(run["completed_on"])
            if run["fixture"] or not run["actual_execution"] or not ordered[0]<start<=end<=now:
                errors.append("Invalid actual run provenance/chronology")
            if (not run["requested_model"] or not run["requested_reasoning"]
                    or run["runtime_model"] != "unknown" and not SHA.fullmatch(str(run["runtime_model_attestation_sha256"]))
                    or run["runtime_model"] == "unknown" and (run["runtime_model_attestation_sha256"] is not None
                        or run["runtime_model_attestation_artifact_id"] is not None)
                    or run["runtime_model"] != "unknown" and not run["runtime_model_attestation_artifact_id"]):
                errors.append("Requested model/reasoning and honest attested-or-unknown runtime model required")
            if run["role"]=="sut":
                if not seq["sut_started_on"]<=start<=end<=seq["predictions_sealed_on"]:
                    errors.append("SUT execution is outside its actual pre-truth sealed interval")
                if run["input_projection_sha256"]!=audit["method"]["input_graph_bytes_sha256"]:
                    errors.append("SUT did not consume the exact genuine frozen input graph")
            else:
                obs = timestamp(run["source_observations_frozen_on"])
                recheck_start, recheck_end = timestamp(run["source_context_recheck_started_on"]), timestamp(run["source_context_recheck_completed_on"])
                hypotheses, decisions = timestamp(run["hypotheses_opened_on"]), timestamp(run["decisions_started_on"])
                if not seq["truth_started_on"] <= start <= recheck_start < recheck_end <= obs < hypotheses <= decisions < end <= seq["truth_sealed_on"]:
                    errors.append("Fresh post-SUT truth context recheck and notes freeze must precede hypotheses and decisions")
                if not SHA.fullmatch(str(run["source_observations_sha256"])):
                    errors.append("Frozen source-only observation commitment missing")
                if not SHA.fullmatch(str(run["source_context_recheck_sha256"])):
                    errors.append("Actual fresh source-context recheck commitment missing")
                if run["preparatory_reading_disclosed"] is not True:
                    errors.append("Prior blind preparatory source familiarity must be honestly disclosed")
                if (run["input_projection_sha256"]!=audit["method"]["source_packet_sha256"]
                        or run["blind_to_predictions_and_status"] is not True
                        or run["blind_to_other_truth_and_old_judgments"] is not True):
                    errors.append("New audit truth lacks the exact blinded source-only input projection")
        output = rg.public_graph(graph)
        output_assertions=_index(output["assertions"],"id")
        output_ids = {r["id"] for r in output["assertions"]}
        current = sampled_bindings(graph,audit["selected_assertion_ids"],output_ids)
        originals = _index(audit["bindings"], "assertion_id")
        for new in current:
            original = originals[new["assertion_id"]]
            # Extra review links are permitted; every original review is exact
            # and attached. True claim/status/source/identity changes are holds.
            subset = {rid:new["original_review_record_sha256"].get(rid) for rid in original["original_review_record_sha256"]}
            if {**new,"original_review_record_sha256":subset} != original:
                errors.append("Sampled current scientific/source/identity/status/output/original-review binding changed")
        bindings = _index(audit["bindings"],"assertion_id")
        frame = _index(audit["frame"],"assertion_id")
        sources = _index(graph["sources"],"id")
        old_invocations = {r.get("invocation_id") for r in graph["reviews"]}
        for run in runs.values():
            if run["invocation_id"] in old_invocations:
                errors.append("Old scientific review invocation cannot stand in for new audit execution/truth")
        for binding in audit["bindings"]:
            aid=binding["assertion_id"]
            current_assertion = _index(graph["assertions"], "id")[aid]
            current_reviews = _index(graph["reviews"], "id")
            if any(current_reviews[rid]["role"] in {"source_verifier", "adversarial"}
                    and timestamp(current_reviews[rid]["reviewed_on"]) < timestamp(frame[aid]["first_peer_submitted_on"])
                    for rid in current_assertion["review_ids"]):
                errors.append("Current selected-case review history contradicts the admitted earliest peer submission")
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
        return list(dict.fromkeys(errors+["Invalid reference audit: " + _safe_error(error)])),{}



def validate_private_reference_v4(audit_bytes, current_graph, *, expected_artifact_hashes,
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
    for position,(name,digest) in enumerate(declared.items()):
        raw=artifact_payloads.get(name)
        if not isinstance(raw,bytes) or byte_hash(raw)!=digest:
            errors.append(f"Original artifact authentication failed at position {position}")
        else:
            authentic[name]=raw
    try:
        frozen=load_exact(authentic["input_graph"])
        output=load_exact(authentic["sut_output"])
        execution=load_exact(authentic["sut_execution"])
        exposure=load_exact(authentic["exposure_registry"])
        curation=load_exact(authentic["frame_curation"])
        lineage=load_exact(authentic["lineage_manifest"])
        adaptations=load_exact(authentic["metadata_adaptations"])
        frame=build_reference_frame(frozen,curation["records"],exposure,lineage,
            artifact_payloads=authentic,metadata_adaptations=adaptations)
        _validate_population_review(audit,frozen,curation,lineage,exposure,adaptations,authentic)
        if frame!=audit["frame"] or public_exposure_registry(exposure)!=audit["exposure_registry"]:
            errors.append("Public neutral frame/exposure projection differs from genuine original inputs")
        if (canonical_hash(frozen)!=audit["method"]["input_graph_sha256"]
                or byte_hash(authentic["input_graph"])!=audit["method"]["input_graph_bytes_sha256"]
                or canonical_hash(output)!=audit["method"]["output_graph_sha256"]
                or canonical_hash(rg.public_graph(frozen))!=canonical_hash(output)):
            errors.append("Sealed unchanged actual SUT input/output replay does not match")
        if (_index(audit["bindings"],"assertion_id")!=_index(sampled_bindings(frozen,audit["selected_assertion_ids"],
                {r["id"] for r in output["assertions"]}),"assertion_id")):
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
        for run in runs.values():
            _validate_source_context(run,authentic,audit["truth"],_index(frozen["sources"],"id"))
            attestation_id = run["runtime_model_attestation_artifact_id"]
            if run["runtime_model"] != "unknown":
                raw = authentic[attestation_id]
                attestation = load_exact(raw)
                if (byte_hash(raw) != run["runtime_model_attestation_sha256"]
                        or attestation["invocation_id"] != run["invocation_id"]
                        or attestation["runtime_model"] != run["runtime_model"]):
                    errors.append("Runtime model does not bind an exact retained runtime attestation")
        for case in audit["truth"]:
            for receipt in case["review_receipts"]:
                envelope=load_exact(authentic[receipt["artifact_id"]])
                entry=_original_entry(envelope,receipt["entry_pointer"])
                projected={key:receipt[key] for key in ("decision","critical_if_accepted","scientific_sha256","evidence")}
                if (canonical_hash(entry)!=receipt["entry_sha256"] or
                        entry!={"assertion_id":case["assertion_id"],**projected}):
                    errors.append("Audit truth differs from exact original independent decision entry")
                run=runs[receipt["invocation_id"]]
                for key in run:
                    if envelope.get(key)!=run[key]:
                        errors.append("Actual independent truth metadata differs from projected provenance")
                notes=authentic.get(run["source_observations_artifact_id"])
                if not isinstance(notes,bytes) or byte_hash(notes)!=run["source_observations_sha256"]:
                    errors.append("Exact independently frozen source-only observations are not authenticated")
    except (KeyError,ValueError,TypeError,IndexError,StopIteration) as error:
        errors.append("Original private execution validation incomplete: " + _safe_error(error))
    digests={pin["response_sha256"] for b in audit["bindings"] for pin in b["source_pins"]}
    if set(source_payloads)!=digests or any(not isinstance(source_payloads.get(d),bytes)
            or byte_hash(source_payloads[d])!=d for d in digests):
        errors.append("All distinct sampled raw primary-source response bytes must authenticate")
    root=Path(__file__).resolve().parents[1]
    receipt={"schema_version":RECEIPT_VERSION,"audit_sha256":byte_hash(audit_bytes),
        "method_sha256":audit["method_sha256"],"sample_bindings_sha256":canonical_hash(audit["bindings"]),
        "population_authentication_sha256":canonical_hash({f:audit["method"][f] for f in POPULATION_PINS}),
        "artifact_commitments_sha256":canonical_hash(expected_artifact_hashes),
        "source_authentication_sha256":canonical_hash(sorted(digests)),
        "validator_code_pins":{name:byte_hash((root/name).read_bytes()) for name in CODE_FILES},
        "validation_run":{"invocation_id":invocation_id,"reviewer":reviewer,"validated_on":now.isoformat(),
                          "fixture":fixture,"actual_execution":True},
        "validation_errors":list(dict.fromkeys(errors))}
    return (json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode()


def validate_public_reference_v4(audit_bytes,current_graph,validation_receipt_bytes,*,trusted_admission,thresholds=None):
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
            "validation_run","validation_errors","population_authentication_sha256"}
        if set(receipt)!=receipt_fields or receipt["schema_version"]!=RECEIPT_VERSION or _safe_public(receipt):
            raise ValueError("Unsupported/private reference validation receipt")
        root=Path(__file__).resolve().parents[1]
        pins={name:byte_hash((root/name).read_bytes()) for name in CODE_FILES}
        if receipt["validator_code_pins"]!=pins:
            raise ValueError("Actual reader/schema/SUT capsule differs from independently reviewed validator")
        digests=sorted({p["response_sha256"] for b in audit["bindings"] for p in b["source_pins"]})
        if (receipt["audit_sha256"]!=byte_hash(audit_bytes) or receipt["method_sha256"]!=audit["method_sha256"]
                or receipt["sample_bindings_sha256"]!=canonical_hash(audit["bindings"])
                or receipt["population_authentication_sha256"]!=canonical_hash({f:audit["method"][f] for f in POPULATION_PINS})
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
            "exposure_review_sha256","completion_authorized","population_review_sha256",
            "lineage_manifest_sha256","metadata_adaptations_sha256","population_rule"}
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
        if (a["population_rule"] != POPULATION_RULE or any(a[f]!=audit["method"][f] for f in (
                "population_review_sha256","lineage_manifest_sha256","metadata_adaptations_sha256"))):
            raise ValueError("Independent admission must accept the exact uniform initial-hypothesis population and reviews")
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
        errors.append(_safe_error(error))
    return list(dict.fromkeys(errors)),metrics
