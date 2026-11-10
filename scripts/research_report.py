#!/usr/bin/env python3
"""Offline report context and fail-closed research publication gate.

Launch floors are code invariants. JSON policy can raise them, never lower them.
Coverage is calculated by the evidence graph, never copied from report claims.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOORS = {
    "legacy_dispositions": 39,
    "qualifying_suppliers": 60,
    "reviewed_papers": 150,
    "dataset_families": 60,
    "benchmark_families": 20,
    "core_disposition_rate": 0.90,
    "reference_sample_size": 200,
    "reference_precision": 0.98,
    "reference_recall": 0.95,
    "screening_sample_size": 200,
    "screening_recovered": 190,
    "screening_stratum_recall": 0.90,
}
PARAGRAPH_KINDS = {"sourced_fact", "analysis", "method", "research_gap"}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_report(root=ROOT):
    return json.loads((Path(root) / "data/research/report.json").read_text())


def _timestamp(value):
    """Require a timezone and a time; a calendar date cannot prove an hourly cutoff."""
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("timezone-aware timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def _validate_report(report, graph):
    reasons = []
    for field in ("title", "release_id", "updated_on", "status", "sections", "editions"):
        if field not in report:
            reasons.append(f"Report is missing {field}.")
    try:
        date.fromisoformat(report.get("updated_on", ""))
    except (ValueError, TypeError):
        reasons.append("Report updated_on must be an ISO calendar date.")
    assertions = {item.get("id"): item for item in graph.get("assertions", [])}
    seen = set()
    sections = report.get("sections", [])
    if len(sections) != 12:
        reasons.append("The report requires all 12 stable chapters.")
    for section in sections:
        section_id = section.get("id")
        if not section_id or section_id in seen or not section.get("title"):
            reasons.append("Report chapter IDs must be unique and titled.")
        seen.add(section_id)
        for paragraph in section.get("paragraphs", []):
            kind = paragraph.get("kind")
            if kind not in PARAGRAPH_KINDS or not paragraph.get("text"):
                reasons.append(f"Invalid paragraph in {section_id}.")
            ids = paragraph.get("claim_ids", [])
            if kind == "sourced_fact" and not ids:
                reasons.append(f"Unbound factual paragraph in {section_id}.")
            for claim_id in ids:
                claim = assertions.get(claim_id)
                if not claim:
                    reasons.append(f"Unknown report assertion {claim_id}.")
                elif claim.get("status") not in {"approved", "historical"}:
                    reasons.append(f"Report cites unapproved candidate {claim_id}.")
                elif claim.get("status") == "historical" and not paragraph.get("historical"):
                    reasons.append(f"Historical assertion {claim_id} needs an explicit historical label.")
    return reasons


def _audit(audit, kind, graph, thresholds):
    """Recompute audit metrics from adjudicated, source-bound holdout rows.

    An audit is an independently adjudicated held-out set, not an accuracy number
    in a release manifest. Source excerpts stay in the graph. IDs, source hashes,
    dates and distinct invocation receipts make the result inspectable offline.
    """
    errors = []
    if not isinstance(audit, dict):
        return [f"Actual {kind} audit has not been supplied."], {}
    if audit.get("kind") != kind or audit.get("status") != "completed" or audit.get("fixture") is not False:
        errors.append(f"{kind} audit must be a completed non-fixture adjudication.")
    if audit.get("release_id") != graph.get("release_id"):
        errors.append(f"{kind} audit does not bind this graph release.")
    if audit.get("graph_sha256") != canonical_hash(graph):
        errors.append(f"{kind} audit graph digest does not match.")
    try:
        frozen_on = _timestamp(audit.get("frozen_on"))
        completed_on = _timestamp(audit.get("completed_on"))
        if completed_on < frozen_on:
            errors.append(f"{kind} audit completion predates its frozen holdout.")
    except (ValueError, TypeError):
        errors.append(f"{kind} audit needs timestamped freeze and completion.")
        frozen_on = completed_on = None
    rows = audit.get("items", [])
    if not isinstance(rows, list):
        return errors + [f"{kind} audit items must be a list."], {}
    minimum = thresholds[f"{kind}_sample_size"]
    if len(rows) < minimum:
        errors.append(f"{kind} audit needs at least {minimum} actual holdout records.")
    if audit.get("holdout_ids_sha256") != canonical_hash(sorted(str(row.get("id", "")) for row in rows)):
        errors.append(f"{kind} frozen holdout membership digest does not match.")
    ids = set()
    sources = {item.get("id"): item for item in graph.get("sources", [])}
    reviews = {item.get("id"): item for item in graph.get("reviews", [])}
    assertions = {item.get("id"): item for item in graph.get("assertions", [])}
    for row in rows:
        row_id = row.get("id")
        if not row_id or row_id in ids:
            errors.append(f"{kind} holdout IDs must be distinct.")
        ids.add(row_id)
        evidence = row.get("evidence", [])
        if not evidence:
            errors.append(f"{kind} holdout {row_id} has no source evidence.")
        for item in evidence:
            source = sources.get(item.get("source_id"), {})
            if (not source or source.get("status") != "captured" or not item.get("locator")
                    or item.get("excerpt_sha256") != source.get("excerpt_sha256")):
                errors.append(f"{kind} holdout {row_id} has unbound source evidence.")
        receipts = [reviews.get(rid, {}) for rid in row.get("review_ids", [])]
        passing = [receipt for receipt in receipts if receipt.get("verdict") == "pass"
                   and receipt.get("invocation_id") and receipt.get("reviewer")
                   and receipt.get("method") == "source_content_review"]
        roles = {receipt.get("role") for receipt in passing}
        invocations = {receipt.get("invocation_id") for receipt in passing}
        if not {"source_verifier", "adversarial"} <= roles or len(invocations) < 2:
            errors.append(f"{kind} holdout {row_id} lacks separate actual adjudication receipts.")
        for receipt in passing:
            if not {item.get("source_id") for item in evidence} <= set(receipt.get("source_ids", [])):
                errors.append(f"{kind} holdout {row_id} review does not bind its sources.")
            try:
                if frozen_on and _timestamp(receipt.get("reviewed_on")) < frozen_on:
                    errors.append(f"{kind} holdout {row_id} was adjudicated before freeze.")
            except (ValueError, TypeError):
                errors.append(f"{kind} holdout {row_id} review lacks a timestamp.")
        if not isinstance(row.get("expected_positive"), bool) or not isinstance(row.get("observed_positive"), bool):
            errors.append(f"{kind} holdout {row_id} needs boolean expected and observed decisions.")
        if not row.get("adjudication") or not row.get("stratum"):
            errors.append(f"{kind} holdout {row_id} needs an adjudication and stratum.")
        if kind == "reference" and row.get("assertion_id") not in assertions:
            errors.append(f"Reference holdout {row_id} has no graph assertion.")
        if row.get("critical_false_attribution") is not False:
            errors.append(f"{kind} holdout {row_id} lacks a clean critical-attribution adjudication.")
    tp = sum(row.get("expected_positive") is True and row.get("observed_positive") is True for row in rows)
    fp = sum(row.get("expected_positive") is False and row.get("observed_positive") is True for row in rows)
    fn = sum(row.get("expected_positive") is True and row.get("observed_positive") is False for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    metrics = {"sample_size": len(rows), "true_positive": tp, "false_positive": fp,
               "false_negative": fn, "precision": precision, "recall": recall}
    if kind == "reference":
        if len({row.get("assertion_id") for row in rows}) != len(rows):
            errors.append("Reference audit must contain distinct assertions.")
        if precision < thresholds["reference_precision"] or recall < thresholds["reference_recall"]:
            errors.append("Reference holdout misses the precision/recall floors.")
    else:
        if any(row.get("expected_positive") is not True for row in rows):
            errors.append("Screening audit must be a frozen set of independently established eligible records.")
        if len({row.get("record_id") for row in rows}) != len(rows) or any(not row.get("record_id") for row in rows):
            errors.append("Screening audit must contain distinct stable record IDs.")
        if tp < thresholds["screening_recovered"]:
            errors.append("Screening audit recovered fewer than the required eligible records.")
        required_strata = {"supplier", "paper", "dataset", "benchmark"}
        declared = set(audit.get("major_strata", []))
        if not required_strata <= declared:
            errors.append("Screening audit must declare all four major corpus strata.")
        metrics["strata"] = {}
        for stratum in declared:
            subset = [row for row in rows if row.get("stratum") == stratum]
            recovered = sum(row.get("observed_positive") is True for row in subset)
            rate = recovered / len(subset) if subset else 0
            metrics["strata"][stratum] = {"eligible": len(subset), "recovered": recovered, "recall": rate}
            if rate < thresholds["screening_stratum_recall"]:
                errors.append(f"Screening stratum {stratum} misses its recall floor.")
    return errors, metrics


def publication_gate(graph, report, policy=None):
    from research_graph import coverage_summary, validate_graph

    policy = {} if policy is None else policy
    reasons = []
    thresholds = dict(FLOORS)
    supplied = policy.get("launch_floors", {})
    for key, floor in FLOORS.items():
        value = supplied.get(key, floor)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or value < floor:
            reasons.append(f"Policy cannot lower the {key} launch floor below {floor}.")
        else:
            thresholds[key] = value
    for field in ("reference_audit_required", "screening_audit_required", "archive_required"):
        if field in policy and policy[field] is not True:
            reasons.append(f"Policy cannot disable {field}.")
    try:
        validation = validate_graph(graph)
        if isinstance(validation, list):
            reasons.extend(f"Evidence graph: {item}" for item in validation)
        elif isinstance(validation, dict) and validation.get("valid") is False:
            reasons.extend(f"Evidence graph: {item}" for item in validation.get("errors", ["invalid graph"]))
        coverage = coverage_summary(graph)
    except (ValueError, TypeError, KeyError) as error:
        reasons.append(f"Evidence graph is invalid: {error}")
        coverage = {}
    reasons.extend(_validate_report(report, graph))
    for key in ("legacy_dispositions", "qualifying_suppliers", "reviewed_papers", "dataset_families", "benchmark_families", "core_disposition_rate"):
        observed = coverage.get(key, 0)
        if not isinstance(observed, (int, float)) or observed < thresholds[key]:
            reasons.append(f"Coverage {key}: {observed} / {thresholds[key]} required.")
    frozen = graph.get("coverage", {}).get("frozen_core", {})
    if not frozen.get("entity_ids") or not frozen.get("frozen_on") or not frozen.get("source_cutoff"):
        reasons.append("Eligible core denominator has not been frozen with its cutoff and date.")
    try:
        cutoff = _timestamp(report.get("source_cutoff"))
        sources = {item.get("id"): item for item in graph.get("sources", [])}
        for assertion in graph.get("assertions", []):
            if assertion.get("status") != "approved":
                continue
            for item in assertion.get("evidence", []):
                captured = _timestamp(sources.get(item.get("source_id"), {}).get("captured_on"))
                if captured > cutoff:
                    reasons.append(f"Approved assertion {assertion.get('id')} uses a source captured after the edition cutoff.")
    except (TypeError, ValueError):
        reasons.append("Edition cutoff and approved source capture dates must be timezone-aware timestamps.")
    audits = policy.get("audits", {})
    metrics = {}
    for kind in ("reference", "screening"):
        errors, metrics[kind] = _audit(audits.get(kind), kind, graph, thresholds)
        reasons.extend(errors)
    # A reference-quality audit and a screening-recall audit are separate samples.
    reference_ids = {item.get("id") for item in audits.get("reference", {}).get("items", [])}
    screening_ids = {item.get("id") for item in audits.get("screening", {}).get("items", [])}
    if reference_ids & screening_ids:
        reasons.append("Reference and screening holdouts must be separate samples.")
    archive = report.get("archive", {})
    if not (archive.get("status") == "published" and re.fullmatch(r"10\.\d{4,9}/\S+", archive.get("doi", ""))
            and str(archive.get("record_url", "")).startswith("https://")
            and re.fullmatch(r"[0-9a-f]{64}", archive.get("artifact_sha256", ""))
            and archive.get("release_id") == report.get("release_id") and archive.get("confirmed_on")):
        reasons.append("An actual public versioned archive receipt with DOI and exact artifact digest is required; a prepared package is not publication.")
    reasons = list(dict.fromkeys(reasons))
    return {"ready": not reasons, "status": "ready" if not reasons else "prelaunch",
            "reasons": reasons, "coverage": coverage, "audit_metrics": metrics,
            "thresholds": thresholds, "source_cutoff": report.get("source_cutoff")}


def build_context(root=ROOT):
    from research_graph import load_graph
    from public_identity import load_identity

    root = Path(root)
    graph, report = load_graph(root), load_report(root)
    policy = json.loads((root / "data/research/policy.json").read_text())
    policy["audits"] = {}
    for kind in ("reference", "screening"):
        path = root / f"data/research/{kind}-audit.json"
        if path.is_file():
            policy["audits"][kind] = json.loads(path.read_text())
    return {"graph": graph, "report": report, "gate": publication_gate(graph, report, policy),
            "identity": load_identity(root), "policy": policy}


if __name__ == "__main__":
    print(json.dumps(build_context()["gate"], indent=2, ensure_ascii=False))
