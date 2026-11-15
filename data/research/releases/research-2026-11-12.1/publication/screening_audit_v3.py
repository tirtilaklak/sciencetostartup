#!/usr/bin/env python3
"""Unadopted frozen-reference repeat proposal; no adoption or admission side effects.

All external truth/execution claims still require an actual separately reviewed
admission. These pure helpers do not read sources, manufacture scientific reviews,
run a SUT, write receipts, change a graph, or make the central gate dispatch here.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

VERSION = "screening-audit-v3"
RECEIPT_VERSION = "screening-private-validation-v2"
ADMISSION_VERSION = "screening-audit-admission-v2"
KIND = "frozen_reference_post_remediation_repeat"
STRATA = {"supplier", "paper", "dataset", "benchmark"}
STATES = {"eligible", "unknown", "not_logical_unit", "excluded"}
FLOORS = {"screening_sample_size": 200, "screening_recovered": 190,
          "screening_stratum_recall": .90}
HISTORICAL_SEED = "STS-eligible-screening-reservoir-v1-269-protected-2026-11-10"
HISTORICAL_QUOTAS = {"supplier": 50, "paper": 65, "dataset": 60, "benchmark": 25}
HISTORICAL_FRAME_COUNTS = {"supplier": 84, "paper": 82, "dataset": 68, "benchmark": 35}
HISTORICAL_FRAME_SHA256 = "d605540d1102647335b35a9b409c8eab6314bfe81be1118b427d90325b4ec836"
HISTORICAL_200_KEY_SHA256 = "c542d3087db0c28ff15963695bb182e85a9842df04b6f2b57c4742605c94f0ec"
CODE_FILES = ("scripts/screening_audit_v3.py", "schema/screening-audit.v3.schema.json",
              "scripts/research_audit_dispatch.py")
SHA = re.compile(r"^[0-9a-f]{64}$")
HTTP_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def byte_hash(value):
    return hashlib.sha256(value).hexdigest()


def load_exact(blob):
    if not isinstance(blob, bytes):
        raise ValueError("Exact UTF-8 document bytes are required")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Nonfinite JSON number")

    result = json.loads(blob.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    canonical_hash(result)
    return result


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Recorded UTC timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Explicit UTC required")
    return parsed


def _shape(value, schema, path="$"):
    """The deliberately small structural subset used by this checked-in schema."""
    errors = []
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "boolean": isinstance(value, bool),
             "integer": isinstance(value, int) and not isinstance(value, bool),
             "null": value is None, None: True}
    if not any(valid.get(k, False) for k in kinds):
        return [f"{path}: invalid structural type"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value outside declared enum")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: wrong contract constant")
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        props = schema.get("properties", {})
        if required - set(value):
            errors.append(f"{path}: missing required fields {sorted(required - set(value))}")
        if schema.get("additionalProperties") is False and set(value) - set(props):
            errors.append(f"{path}: {len(set(value) - set(props))} unknown fields")
        for position, (key, item) in enumerate(value.items()):
            child = props.get(key, schema.get("additionalProperties", {}))
            if isinstance(child, dict):
                # Dynamic names are untrusted data too. Keep rejected secrets
                # and paths out of diagnostics, including malformed values.
                label = key if key in props else f"<field-{position}>"
                errors.extend(_shape(item, child, f"{path}/{label}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            errors.append(f"{path}: array size violates contract")
        for i, item in enumerate(value):
            errors.extend(_shape(item, schema.get("items", {}), f"{path}/{i}"))
    if isinstance(value, str):
        if not value or ("pattern" in schema and not re.search(schema["pattern"], value)):
            errors.append(f"{path}: invalid string")
    return errors


def _index(rows, field):
    index = {row[field]: row for row in rows}
    if len(index) != len(rows):
        raise ValueError(f"Duplicate {field}")
    return index


def _safe_public(value):
    errors = []
    if isinstance(value, dict):
        for key, item in value.items():
            errors.extend(_safe_public(key))
            if key in {"excerpt", "raw_file", "text_file", "credentials", "access_token", "private_cache_path"}:
                errors.append("Private field in public audit")
            errors.extend(_safe_public(item))
    elif isinstance(value, list):
        for item in value:
            errors.extend(_safe_public(item))
    elif isinstance(value, str):
        # Public schema has no free-form rationale/source-body fields. This is
        # an explicit known-channel boundary, not general-purpose text DLP.
        plain = unquote(HTTP_URL.sub("", value))
        if re.search(r"(?:file://|/Users/|/home/|/private/|/tmp/|/var/folders/|[A-Za-z]:[\\/]|\\\\)", plain):
            errors.append("Local path in public audit")
        if re.search(r"(?<![A-Za-z0-9_-])(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN .*PRIVATE KEY-----)", unquote(value)):
            errors.append("Credential pattern in public audit")
        if re.search(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", unquote(value)):
            errors.append("Contact address in public audit")
        for match in HTTP_URL.finditer(value):
            url = urlsplit(match.group())
            if url.username or url.password or any(unquote(k).lower() in {
                    "token", "access_token", "secret", "api_key", "api-key", "signature", "password"}
                    for k, _ in parse_qsl(url.query)):
                errors.append("Credential-bearing public URL")
    return errors


def _safe_error(error):
    """Keep diagnostic text useful without echoing rejected private input."""
    try:
        message = str(error)
        return "Rejected private validation input" if _safe_public(message) else message
    except (ValueError, TypeError, UnicodeError):
        return "Malformed validation input"


def select_screening_panel(frame, truths, *, seed=HISTORICAL_SEED, quotas=None):
    """Select by original identity rank and canonical truth, never predictions.

    Every frame row remains in the full audit; an alias consumes no extra place.
    Quotas cannot be transferred. This helper cannot decide eligibility itself.
    """
    quotas = HISTORICAL_QUOTAS if quotas is None else quotas
    if set(quotas) != STRATA or any(type(n) is not int or n <= 0 for n in quotas.values()):
        raise ValueError("Four positive fixed integer quotas required")
    if sum(quotas.values()) != 200:
        raise ValueError("The declared panel must contain exactly 200 records")
    frames, truth = _index(frame, "record_id"), _index(truths, "record_id")
    if set(frames) != set(truth):
        raise ValueError("Complete exact-frame truth ledger required")
    selected, seen = [], set()
    for stratum in sorted(STRATA):
        rows = sorted((r for r in frame if r["stratum"] == stratum), key=lambda r:
            (byte_hash((seed + "\n" + r["record_id"]).encode()), r["record_id"]))
        count = 0
        for row in rows:
            decision = truth[row["record_id"]]
            if decision["state"] != "eligible":
                continue
            logical = decision["logical_id"]
            if not logical:
                raise ValueError("Eligible truth requires exact logical identity")
            if logical in seen:
                continue
            if count < quotas[stratum]:
                selected.append(row["record_id"])
                seen.add(logical)
                count += 1
    return selected


def _limits(thresholds):
    out = dict(FLOORS)
    for key, floor in FLOORS.items():
        value = (thresholds or {}).get(key, floor)
        if type(value) not in (float, int) or not math.isfinite(value) or value < floor:
            raise ValueError(f"Cannot lower {key} below {floor}")
        out[key] = value
    return out


def _recovered(prediction, truth, check):
    return (prediction["state"] == "eligible" and prediction["mandatory_workload_retained"] is True
            and prediction["logical_id"] == truth["logical_id"]
            and bool(prediction["evidence"]) and check["source_supported"] is True
            and check["prediction_sha256"] == canonical_hash(prediction))


def original200_sensitivity(audit):
    """Retain old three-valued rows and separately evaluate current mappings.

    Old raw-retention diagnostics are not the source-screening endpoint and
    cannot complete the contract. Old Unknown never becomes false/nonunit here.
    """
    original = audit["original200"]
    if original["key_sha256"] != HISTORICAL_200_KEY_SHA256 or len(original["records"]) != 200:
        raise ValueError("Exact preserved original-200 key projection required")
    rows = _index(original["records"], "record_id")
    _index(original["records"], "id")
    mappings = _index(original["current_canonical_mappings"], "record_id")
    frame = _index(audit["frame"], "record_id")
    truth = _index(audit["truths"], "record_id")
    predictions = _index(audit["predictions"], "record_id")
    checks = _index(audit["prediction_source_checks"], "record_id")
    if not set(rows) == set(mappings) or not set(rows) <= set(frame):
        raise ValueError("Original-200 membership/mapping projection is incomplete or outside fixed269")
    for rid, row in rows.items():
        if row["stratum"] != frame[rid]["stratum"]:
            raise ValueError("Original-200 stratum mapping changed")
        expected = {"record_id": rid, "current_state": truth[rid]["state"],
            "logical_id": truth[rid]["logical_id"], "related_logical_ids": truth[rid]["related_logical_ids"]}
        if mappings[rid] != expected:
            raise ValueError("Original-200 mapping differs from complete sealed current blind truth")
    old_positive = [rid for rid, row in rows.items() if row["screening_eligibility"] == "true"]
    current_positive = [rid for rid in rows if truth[rid]["state"] == "eligible"]
    return {"fixed_record_count": 200,
        "preserved_original_eligibility": {state: sum(r["screening_eligibility"] == state for r in rows.values())
                                           for state in ("true", "false", "unknown")},
        "raw_retained_original_positive_records": sum(predictions[rid]["state"] == "eligible"
            and predictions[rid]["mandatory_workload_retained"] is True for rid in old_positive),
        "current_blind_truth_states": {state: sum(truth[rid]["state"] == state for rid in rows)
                                       for state in sorted(STATES)},
        "current_distinct_eligible_logical_units": len({truth[rid]["logical_id"] for rid in current_positive}),
        "current_source_supported_recovered_records": sum(_recovered(predictions[rid], truth[rid], checks[rid])
                                                          for rid in current_positive),
        "completes_contract": False}


def recompute_screening(audit, *, thresholds=None):
    limits = _limits(thresholds)
    frame = _index(audit["frame"], "record_id")
    truth = _index(audit["truths"], "record_id")
    predictions = _index(audit["predictions"], "record_id")
    checks = _index(audit["prediction_source_checks"], "record_id")
    if not set(frame) == set(truth) == set(predictions) == set(checks):
        raise ValueError("Frame, predictions, truth and source-check ledgers must match exactly")
    selection = audit["selection"]
    panel = select_screening_panel(audit["frame"], audit["truths"],
                                  seed=selection["seed"], quotas=selection["quotas"])
    if panel != audit["selected_record_ids"]:
        raise ValueError("Submitted membership differs from deterministic eligible selection")
    recovered = {rid: _recovered(predictions[rid], truth[rid], checks[rid]) for rid in panel}
    strata = {}
    for name in sorted(STRATA):
        subset = [rid for rid in panel if frame[rid]["stratum"] == name]
        count = sum(recovered[rid] for rid in subset)
        strata[name] = {"eligible": len(subset), "recovered": count,
                        "recall": count / len(subset) if subset else 0}
    critical = sum(checks[rid]["critical_false_attribution"] is True for rid in panel)
    unresolved_critical = sum(checks[rid]["critical_false_attribution"] is None for rid in panel)
    frame_critical = sum(row["critical_false_attribution"] is True for row in checks.values())
    frame_conclusive_unresolved = sum(row["critical_false_attribution"] is None
        and predictions[rid]["state"] != "unknown" for rid, row in checks.items())
    numeric = (len(panel) >= limits["screening_sample_size"]
               and sum(recovered.values()) >= limits["screening_recovered"]
               and all(row["recall"] >= limits["screening_stratum_recall"] for row in strata.values()))
    return {"sample_size": len(panel), "recovered": sum(recovered.values()), "strata": strata,
            "frame_size": len(frame), "frame_truth_states": {state:
                sum(row["state"] == state for row in truth.values()) for state in sorted(STATES)},
            "frame_eligible_predictions_by_truth_state": {state: sum(
                p["state"] == "eligible" and truth[rid]["state"] == state
                for rid, p in predictions.items()) for state in sorted(STATES)},
            "critical_false_attributions": critical, "unresolved_critical_attributions": unresolved_critical,
            "frame_critical_false_attributions": frame_critical,
            "frame_unresolved_conclusive_attributions": frame_conclusive_unresolved,
            "original200_sensitivity": original200_sensitivity(audit),
            "numerical_thresholds_met": numeric, "thresholds": limits,
            "evaluation_kind": KIND, "publication_eligible": False}


def _audit_errors(audit, graph, now):
    schema = load_exact((Path(__file__).resolve().parents[1] / CODE_FILES[1]).read_bytes())
    errors = _shape(audit, schema)
    if errors:
        return errors, {}
    errors.extend(_safe_public(audit))
    if audit["fixture"] is not False or audit["actual_execution"] is not True:
        errors.append("An actual non-fixture execution is required")
    if set(audit["limitations"]) != {"exposed_enriched_fixed_frame", "post_remediation_not_untouched_holdout",
            "conditional_recovery_not_discovery_recall", "no_population_generalization",
            "reuses_previously_scored_frozen_reference", "sut_has_no_truth_or_prior_predictions"}:
        errors.append("All six bounded-scope disclosures are required")
    if audit["release_id"] != graph.get("release_id") or audit["graph_sha256"] != canonical_hash(graph):
        errors.append("Current exact graph and release binding differs")
    if len(audit["frame"]) != 269:
        errors.append("This method version requires the entire historical 269-frame")
    if {name: sum(row["stratum"] == name for row in audit["frame"]) for name in STRATA} != HISTORICAL_FRAME_COUNTS:
        errors.append("Historical frame stratum counts differ")
    if audit["selection"]["seed"] != HISTORICAL_SEED or audit["selection"]["quotas"] != HISTORICAL_QUOTAS:
        errors.append("Historical seed/rank and quotas are immutable in this version")
    if audit["frame_sha256"] != canonical_hash(audit["frame"]):
        errors.append("Frame commitment differs")
    if audit["method_sha256"] != canonical_hash(audit["method"]):
        errors.append("Method commitment differs")
    if (audit["artifact_commitments"]["historical_frame_sha256"] != HISTORICAL_FRAME_SHA256
            or audit["artifact_commitments"]["historical200_key_sha256"] != HISTORICAL_200_KEY_SHA256):
        errors.append("Historical frame/key commitments differ from preserved originals")
    reference = audit["frozen_reference"]
    if (reference["truth_projection_sha256"] != audit["artifact_commitments"]["frozen_reference_truth_projection_sha256"]
            or reference["membership_projection_sha256"] != audit["artifact_commitments"]["frozen_reference_membership_projection_sha256"]
            or reference["source_packet_sha256"] != audit["artifact_commitments"]["source_packet_artifact_sha256"]
            or reference["policy_sha256"] != audit["method"]["policy_sha256"]
            or reference["prior_scored_run_sha256"] != audit["artifact_commitments"]["prior_scored_repeat_sha256"]):
        errors.append("Frozen reference truth/membership/source/policy commitments differ")
    for name, field in (("predictions", "predictions"), ("truth", "truths"),
                        ("prediction_source_checks", "prediction_source_checks")):
        if audit["commitments"][name + "_sha256"] != canonical_hash(audit[field]):
            errors.append(f"{name} commitment differs")
    if audit["commitments"]["membership_sha256"] != canonical_hash(audit["selected_record_ids"]):
        errors.append("Membership commitment differs")
    try:
        seq = {key: timestamp(value) for key, value in audit["chronology"].items()}
        chain = [seq[k] for k in ("truth_started_on", "truth_sealed_on", "membership_sealed_on",
            "reference_frozen_on", "method_frozen_on", "sut_started_on", "predictions_sealed_on",
            "source_checks_sealed_on", "outcomes_opened_on", "scored_on")]
        if chain != sorted(chain) or any(a >= b for a, b in zip(chain, chain[1:])) or chain[-1] > now:
            errors.append("Actual frozen-reference/method/fresh-prediction/check/score chronology is invalid")
        if not seq["method_frozen_on"] < seq["source_checks_started_on"] < seq["source_checks_sealed_on"]:
            errors.append("Fresh source-check work must follow the method freeze")
        sources = _index(audit["sources"], "id")
        graph_sources = _index(graph.get("sources", []), "id")
        runs = _index(audit["runs"], "invocation_id")
        for source in sources.values():
            url = urlsplit(source["url"])
            if url.scheme != "https" or not url.netloc or any(c.isspace() for c in source["url"]):
                errors.append("Pinned source needs a public HTTPS URL")
            if timestamp(source["captured_on"]) > seq["reference_frozen_on"]:
                errors.append("A shared source was captured after the fixed reference/source packet freeze")
            gid = source["graph_source_id"]
            if gid is None:
                if source["graph_source_record_sha256"] is not None:
                    errors.append("Standalone audit source cannot claim an unattached graph record hash")
            else:
                original = graph_sources.get(gid)
                if (original is None or canonical_hash(original) != source["graph_source_record_sha256"]
                        or any(source[key] != original.get(key) for key in (
                            "url", "version", "captured_on", "response_sha256"))):
                    errors.append("Audit source differs from its exact original graph record or capture chronology")
        for run in runs.values():
            start, end = timestamp(run["started_on"]), timestamp(run["completed_on"])
            if run["fixture"] is not False or run["actual_execution"] is not True:
                errors.append("Every operational/truth/check run must be actual and non-fixture")
            role = run["role"]
            is_reference_role = role in {"source_adjudicator", "adversarial_adjudicator", "tie_adjudicator"}
            lower_bound = seq["truth_started_on"] if is_reference_role else seq["method_frozen_on"]
            if not lower_bound <= start <= end <= now:
                errors.append("Run timestamps are missing, future or reordered")
            projection = ("input_projection_sha256" if role == "sut" else
                "prediction_check_input_projection_sha256" if role == "prediction_source_verifier" else
                "truth_input_projection_sha256")
            if run["input_projection_sha256"] != audit["method"][projection]:
                errors.append("Run input differs from its exact frozen role projection")
            if role == "sut" and not seq["sut_started_on"] <= start <= end <= seq["predictions_sealed_on"]:
                errors.append("SUT run falls outside its sealed interval")
            if role in {"source_adjudicator", "adversarial_adjudicator", "tie_adjudicator"} and not (
                    seq["truth_started_on"] <= start <= end <= seq["truth_sealed_on"]):
                errors.append("Preserved reference truth run falls outside its actual original interval")
            if role in {"source_adjudicator", "adversarial_adjudicator", "tie_adjudicator"}:
                if not start <= timestamp(run["source_observations_frozen_on"]) < end:
                    errors.append("Truth source-only observations must freeze before decisions/key completion")
                if not SHA.fullmatch(str(run["source_observations_sha256"])):
                    errors.append("Exact frozen source-only observation commitment required")
            if role == "prediction_source_verifier":
                if not seq["source_checks_started_on"] <= start <= end <= seq["source_checks_sealed_on"]:
                    errors.append("Prediction source check falls outside its sealed interval")
                observed = timestamp(run["source_observations_frozen_on"])
                opened = timestamp(run["predictions_opened_on"])
                if not (start <= observed < opened <= end and seq["predictions_sealed_on"] <= opened):
                    errors.append("Fresh checker must freeze own source observations before opening sealed predictions")
                if not SHA.fullmatch(str(run["source_observations_sha256"])):
                    errors.append("Exact actual checker source-observation commitment required")
            elif run["predictions_opened_on"] is not None:
                errors.append("Prediction-opening timestamp belongs only to the fresh source checker")

        def evidence(pins):
            for pin in pins:
                if pin["source_id"] not in sources:
                    errors.append("Unbound source evidence")

        for prediction in audit["predictions"]:
            if runs.get(prediction["invocation_id"], {}).get("role") != "sut":
                errors.append("Prediction lacks a distinct actual SUT invocation")
            if prediction["state"] == "eligible" and (not prediction["logical_id"] or not prediction["evidence"] or not prediction["route"]):
                errors.append("Eligible prediction lacks scoped source proof or exact logical identity")
            required_roles = {
                "A": {"official_supplier_link", "primary_workflow"},
                "B": {"creator_family_documentation", "primary_workflow"},
                "C": {"primary_workflow", "independent_field_designation"},
                "D": {"commercial_supply", "entity_identity"},
            }
            bindings = prediction["proof_bindings"]
            named_roles = [row["role"] for row in bindings]
            evidence_ids = {row["source_id"] for row in prediction["evidence"]}
            if len(named_roles) != len(set(named_roles)):
                errors.append("Duplicate prediction proof role")
            if prediction["state"] == "eligible" and not required_roles.get(prediction["route"], set()) <= set(named_roles):
                errors.append("Eligible prediction omits a mandatory route proof role")
            for binding in bindings:
                if (not binding["source_ids"] or len(binding["source_ids"]) != len(set(binding["source_ids"]))
                        or not set(binding["source_ids"]) <= evidence_ids):
                    errors.append("Prediction proof role does not bind its exact nonempty evidence sources")
            evidence(prediction["evidence"])
        for truth in audit["truths"]:
            receipts = truth["review_receipts"]
            invocations = {r["invocation_id"] for r in receipts}
            roles = {runs.get(r["invocation_id"], {}).get("role") for r in receipts}
            if len(invocations) != len(receipts) or not {
                    "source_adjudicator", "adversarial_adjudicator"} <= roles:
                errors.append("Truth lacks distinct independent source/adversarial invocations")
            for receipt in receipts:
                if receipt["decision_sha256"] != canonical_hash({k: v for k, v in truth.items() if k != "review_receipts"}):
                    errors.append("Truth receipt does not bind the exact canonical decision")
            if truth["state"] == "eligible" and (not truth["logical_id"] or not truth["evidence"] or not truth["route"]):
                errors.append("Eligible truth lacks source proof, route or canonical identity")
            if truth["state"] in {"not_logical_unit", "excluded"} and not truth["evidence"]:
                errors.append("A conclusive nonunit/exclusion requires scoped source proof")
            evidence(truth["evidence"])
        predictions = _index(audit["predictions"], "record_id")
        for check in audit["prediction_source_checks"]:
            if runs.get(check["invocation_id"], {}).get("role") != "prediction_source_verifier":
                errors.append("Prediction support lacks a separate actual source-check invocation")
            if check["prediction_sha256"] != canonical_hash(predictions.get(check["record_id"])):
                errors.append("Source check does not bind the exact evaluated prediction")
        metrics = recompute_screening(audit)
    except (KeyError, ValueError, TypeError, OverflowError) as error:
        return errors + ["Invalid screening execution: " + _safe_error(error)], {}
    if metrics["sample_size"] != 200:
        errors.append("Fixed frame did not supply the 200 eligible canonical records under fixed quotas")
    if metrics["critical_false_attributions"] or metrics["unresolved_critical_attributions"]:
        errors.append("Selected panel has critical or unresolved attribution adjudications")
    if metrics["frame_critical_false_attributions"] or metrics["frame_unresolved_conclusive_attributions"]:
        errors.append("Full269 frame has critical or unresolved conclusive attributions; recheck affected cohort")
    return list(dict.fromkeys(errors)), metrics


def validate_private_screening_execution(audit_bytes, graph, *, expected_artifact_hashes,
        artifact_payloads, source_payloads, invocation_id, reviewer, fixture):
    """Authenticate actual supplied originals and return a held-or-clean receipt.

    Expected hashes are independently retained caller inputs, never obtained from
    submitted data. No function creates an admission. This function performs
    byte/provenance validation, not scientific source reading or SUT execution.
    """
    now = datetime.now(timezone.utc)
    audit = load_exact(audit_bytes)
    errors, metrics = _audit_errors(audit, graph, now)
    if not invocation_id or not reviewer or type(fixture) is not bool:
        raise ValueError("Actual distinct validation identity and explicit fixture status required")
    if invocation_id in {run["invocation_id"] for run in audit.get("runs", [])}:
        errors.append("Validation invocation must be distinct from evaluated/truth/check invocations")
    declared = audit["artifact_commitments"]
    if not isinstance(expected_artifact_hashes, dict) or expected_artifact_hashes != declared:
        errors.append("Original artifacts do not match independently retained commitments")
    if set(artifact_payloads) != set(declared):
        errors.append("Complete exact original artifact payloads required")
    for position, (name, digest) in enumerate(declared.items()):
        payload = artifact_payloads.get(name)
        if not isinstance(payload, bytes) or byte_hash(payload) != digest:
            errors.append(f"Original artifact authentication failed at position {position}")
    historical = artifact_payloads.get("historical_frame_sha256")
    if isinstance(historical, bytes) and byte_hash(historical) == HISTORICAL_FRAME_SHA256:
        original = load_exact(historical)
        expected = sorted(({"record_id": row["record_id"], "stratum": row["stratum"]}
                           for row in original["items"]), key=lambda row: row["record_id"])
        if sorted(audit["frame"], key=lambda row: row["record_id"]) != expected:
            errors.append("Public frame differs from immutable historical 269 identities/strata")
    reference_truth = artifact_payloads.get("frozen_reference_truth_projection_sha256")
    reference_membership = artifact_payloads.get("frozen_reference_membership_projection_sha256")
    try:
        if load_exact(reference_truth) != audit["truths"]:
            errors.append("Truth differs from authenticated frozen reference projection")
        if load_exact(reference_membership) != audit["selected_record_ids"]:
            errors.append("Membership differs from authenticated frozen reference projection")
    except (ValueError, TypeError, UnicodeError):
        errors.append("Exact frozen reference truth and membership projection bytes required")
    original200 = artifact_payloads.get("historical200_key_sha256")
    if isinstance(original200, bytes) and byte_hash(original200) == HISTORICAL_200_KEY_SHA256:
        # This is a projection checker, not a new source adjudication. The old
        # format has no canonical logical-ID field. Never infer or rewrite one.
        preserved = load_exact(original200)
        projected = [{key: row[key] for key in ("id", "record_id", "stratum", "screening_eligibility")}
                     for row in preserved["records"]]
        if audit["original200"]["records"] != projected:
            errors.append("Original-200 public projection differs from exact original three-valued key")
    source_digests = {s["response_sha256"] for s in audit["sources"]}
    if set(source_payloads) != source_digests or any(not isinstance(source_payloads.get(d), bytes)
            or byte_hash(source_payloads[d]) != d for d in source_digests):
        errors.append("Every distinct captured source response requires original authenticated bytes")
    if metrics and not metrics["numerical_thresholds_met"]:
        errors.append("Screening audit misses unchanged numerical floors")
    root = Path(__file__).resolve().parents[1]
    receipt = {"schema_version": RECEIPT_VERSION, "audit_sha256": byte_hash(audit_bytes),
        "graph_sha256": canonical_hash(graph), "method_sha256": audit["method_sha256"],
        "validator_code_pins": {name: byte_hash((root / name).read_bytes()) for name in CODE_FILES},
        "private_artifact_pins_sha256": canonical_hash(expected_artifact_hashes),
        "source_authentication_sha256": canonical_hash(sorted(source_digests)),
        "validation_run": {"invocation_id": invocation_id, "reviewer": reviewer,
            "validated_on": now.isoformat(), "actual_execution": True, "fixture": fixture},
        "validation_errors": list(dict.fromkeys(errors))}
    return json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def validate_public_screening_audit(audit_bytes, graph, validation_receipt_bytes, *,
                                    trusted_admission, thresholds=None):
    """Offline validation using a caller-supplied independently reviewed trust row.

    There is no API that creates accepted admission rows. Test fixture rows in
    unit tests do not establish actual execution or constitute research evidence.
    """
    errors, metrics = [], {}
    try:
        audit, receipt = load_exact(audit_bytes), load_exact(validation_receipt_bytes)
        now = datetime.now(timezone.utc)
        errors, metrics = _audit_errors(audit, graph, now)
        if metrics:
            metrics.update(recompute_screening(audit, thresholds=thresholds))
        required_receipt = {"schema_version", "audit_sha256", "graph_sha256", "method_sha256",
            "validator_code_pins", "private_artifact_pins_sha256", "source_authentication_sha256",
            "validation_run", "validation_errors"}
        if set(receipt) != required_receipt or receipt["schema_version"] != RECEIPT_VERSION:
            raise ValueError("Unsupported private validation receipt shape")
        if _safe_public(receipt):
            raise ValueError("Private channels in validation receipt")
        if (receipt["audit_sha256"] != byte_hash(audit_bytes) or receipt["graph_sha256"] != canonical_hash(graph)
                or receipt["method_sha256"] != audit["method_sha256"]):
            raise ValueError("Private validation receipt binds different inputs")
        pins = receipt["validator_code_pins"]
        if set(pins) != set(CODE_FILES) or any(not SHA.fullmatch(str(value)) for value in pins.values()):
            raise ValueError("Exact reviewed validator capsule pins required")
        code_root = Path(__file__).resolve().parents[1]
        if pins != {name: byte_hash((code_root / name).read_bytes()) for name in CODE_FILES}:
            raise ValueError("Current reader/schema differs from the independently reviewed validator capsule")
        validation = receipt["validation_run"]
        if set(validation) != {"invocation_id", "reviewer", "validated_on", "actual_execution", "fixture"}:
            raise ValueError("Actual validation invocation metadata required")
        if validation["fixture"] is not False or validation["actual_execution"] is not True:
            raise ValueError("Fixture validation cannot authorize actual research")
        audit_runs = {r["invocation_id"] for r in audit["runs"]}
        if not validation["invocation_id"] or not validation["reviewer"] or validation["invocation_id"] in audit_runs:
            raise ValueError("Validation must be a distinct actual invocation")
        if not isinstance(receipt["validation_errors"], list) or any(not isinstance(e, str) for e in receipt["validation_errors"]):
            raise ValueError("Complete preserved private validation errors required")
        errors.extend(receipt["validation_errors"])
        admission = trusted_admission
        required_admission = {"schema_version", "status", "audit_sha256", "receipt_sha256",
            "validator_capsule_sha256", "validation_invocation_id", "independent_review_invocation_id",
            "independent_reviewer", "independent_review_sha256", "reviewed_on", "admitted_on",
            "method_adoption_sha256", "completion_authorized"}
        if not isinstance(admission, dict) or set(admission) != required_admission:
            raise ValueError("A separately reviewed caller trust admission is required")
        if admission["schema_version"] != ADMISSION_VERSION or admission["status"] != "accepted":
            raise ValueError("Unaccepted admission")
        if _safe_public(admission):
            raise ValueError("Private channels in public admission")
        if (admission["audit_sha256"] != byte_hash(audit_bytes)
                or admission["receipt_sha256"] != byte_hash(validation_receipt_bytes)
                or admission["validator_capsule_sha256"] != canonical_hash(pins)
                or admission["validation_invocation_id"] != validation["invocation_id"]
                or admission["method_adoption_sha256"] != audit["method"]["adoption_sha256"]):
            raise ValueError("Admission does not authenticate the exact independently reviewed inputs")
        reviewer = admission["independent_review_invocation_id"]
        if not reviewer or reviewer in audit_runs | {validation["invocation_id"]} or not admission["independent_reviewer"]:
            raise ValueError("Admission review must use a separate actual invocation")
        for key in ("private_artifact_pins_sha256", "source_authentication_sha256"):
            if not SHA.fullmatch(str(receipt[key])):
                raise ValueError("Original artifact/source validation commitments required")
        if (receipt["private_artifact_pins_sha256"] != canonical_hash(audit["artifact_commitments"])
                or receipt["source_authentication_sha256"] != canonical_hash(sorted({
                    s["response_sha256"] for s in audit["sources"]}))):
            raise ValueError("Validated original artifact/source commitments differ")
        if not SHA.fullmatch(str(admission["independent_review_sha256"])):
            raise ValueError("Exact independent review record required")
        scored, validated = timestamp(audit["chronology"]["scored_on"]), timestamp(validation["validated_on"])
        reviewed, admitted = timestamp(admission["reviewed_on"]), timestamp(admission["admitted_on"])
        if not scored <= validated <= reviewed <= admitted <= now:
            raise ValueError("Validation/review/admission chronology is invalid")
        if type(admission["completion_authorized"]) is not bool:
            raise ValueError("Explicit completion authorization required")
        if metrics:
            metrics.update({"integrity_valid": not errors, "execution_admitted": True,
                            "completion_authorized": admission["completion_authorized"]})
        if audit["status"] != "completed" or not admission["completion_authorized"]:
            errors.append("Formal completion is not independently authorized")
        if metrics and not metrics["numerical_thresholds_met"]:
            errors.append("Screening audit misses the unchanged recovery/stratum floors")
        if metrics:
            metrics["publication_eligible"] = not errors
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as error:
        errors.append(_safe_error(error))
    return list(dict.fromkeys(errors)), metrics
