#!/usr/bin/env python3
"""Validate and export the separately versioned research evidence graph, offline.

An HTTP receipt is not a source review. Historical records and discovery candidates
remain visible, but only complete, source-bound three-role reviews count as approved.
This module never changes canonical.json and makes no network requests.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import ipaddress
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, parse_qsl

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"
LAUNCH_FLOORS = {"legacy_dispositions": 39, "qualifying_suppliers": 60,
                 "reviewed_papers": 150, "dataset_families": 60,
                 "benchmark_families": 20, "core_disposition_rate": 0.9}
KINDS = {"organization", "supplier", "paper", "paper_work", "paper_version", "dataset",
         "dataset_family", "dataset_release", "benchmark", "benchmark_family",
         "benchmark_version", "workflow", "model", "institution"}
PREDICATES = {"legacy_description", "has_capability", "supplies_data_for", "publishes",
              "creates", "documents", "evaluates", "trained_on", "derived_from",
              "licenses", "human_annotation", "dataset_size", "benchmark_task",
              "paper_method", "access_terms", "recruited", "annotated", "adjudicated",
              "generated", "labeled", "filtered", "uses_training", "evaluates_on",
              "has_stage", "version_of", "release_of", "recruited_for", "annotated_for",
              "adjudicated_for", "generated_for", "labeled_for", "filtered_for"}
FACETS = {"domain", "modality", "workflow", "expertise", "origin", "labels", "oversight"}
REVIEW_ROLES = {"author", "source_verifier", "adversarial"}
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SECRET = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
ROOT_FIELDS = {"schema_version", "release_id", "as_of", "canonical_dataset_version",
               "canonical_sha256", "entities", "sources", "assertions", "reviews", "coverage"}
ENTITY_FIELDS = {"id", "kind", "name", "status", "identifiers", "aliases", "legacy_id",
                 "family_id", "parent_id", "taxonomy", "review_depth", "disposition", "disposition_reason", "assertion_ids", "eligible_core"}
SOURCE_FIELDS = {"id", "url", "title", "publisher", "source_type", "version", "published_on",
                 "captured_on", "status", "response_sha256", "excerpt", "excerpt_sha256", "locator", "license"}
ASSERTION_FIELDS = {"id", "subject_id", "predicate", "object_id", "value", "evidence",
                    "qualifications", "status", "review_ids", "as_of", "provenance_kind"}
REVIEW_FIELDS = {"id", "assertion_ids", "role", "reviewer", "reviewer_type", "invocation_id",
                 "reviewed_on", "verdict", "method", "source_ids", "note", "assertion_sha256"}


class GraphValidationError(ValueError):
    """One or more graph invariants failed; errors retain actionable JSON paths."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("Research graph invalid:\n" + "\n".join(errors))


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def assertion_digest(assertion):
    """Bind reviews to exact wording, evidence, scope and values; status may advance."""
    content = {key: value for key, value in assertion.items() if key not in {"status", "review_ids"}}
    return digest(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("expected explicit UTC timestamp ending Z")
    result = datetime.fromisoformat(value[:-1] + "+00:00")
    if result.tzinfo != timezone.utc:
        raise ValueError("expected UTC timestamp")
    return result


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("expected ISO date")
    return date.fromisoformat(value)


def _public_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            if "." not in host:
                return False
        return (parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
                and not parsed.password and parsed.port in {None, 443} and not EMAIL.search(value)
                and not any(re.search(r"token|key|secret|auth|signature|credential", key, re.I)
                            for key, _ in parse_qsl(parsed.query)))
    except (TypeError, ValueError):
        return False


def load_graph(root=ROOT):
    """Load and strictly validate against the actual canonical bytes, without IO to URLs."""
    root = Path(root)
    graph = json.loads((root / "data/research/graph.json").read_text(encoding="utf-8"))
    canonical_bytes = (root / "data/canonical.json").read_bytes()
    validate_graph(graph, canonical=canonical_bytes)
    return graph


def _validate_graph(graph, canonical=None):
    """Return graph after validation, or raise GraphValidationError.

    canonical may be the exact bytes/path or a parsed canonical object. Only exact
    bytes/path can establish canonical_sha256; builds use bytes via load_graph.
    A missing canonical argument validates structure, provenance and references.
    """
    errors = []

    def require(ok, path, message):
        if not ok:
            errors.append(f"{path}: {message}")

    def shape(row, fields, path):
        if not isinstance(row, dict):
            require(False, path, "expected object")
            return False
        require(set(row) == fields, path, f"fields must be exactly {', '.join(sorted(fields))}")
        return True

    def strings(value, path, unique=True):
        valid = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
        require(valid, path, "expected list of nonempty strings")
        if valid and unique:
            require(len(set(value)) == len(value), path, "duplicates forbidden")
        return valid

    def dated(value, path, timestamp=False, nullable=False):
        if value is None and nullable:
            return None
        try:
            return _timestamp(value) if timestamp else _date(value)
        except (ValueError, TypeError, OverflowError):
            require(False, path, "expected valid UTC timestamp" if timestamp else "expected valid ISO date")
            return None

    def indexed(rows, fields, path):
        result = {}
        require(isinstance(rows, list), path, "expected array")
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            p = f"{path}/{i}"
            if not shape(row, fields, p):
                continue
            rid = row.get("id")
            require(isinstance(rid, str) and bool(ID.fullmatch(rid)), p + "/id", "invalid stable id")
            if isinstance(rid, str):
                require(rid not in result, p + "/id", "duplicate id")
                result[rid] = row
        return result

    if not shape(graph, ROOT_FIELDS, "$"):
        raise GraphValidationError(errors)
    require(graph.get("schema_version") == SCHEMA_VERSION, "$/schema_version", "unsupported graph schema")
    require(isinstance(graph.get("release_id"), str) and bool(graph["release_id"].strip()), "$/release_id", "required")
    as_of = dated(graph.get("as_of"), "$/as_of", timestamp=True)
    require(graph.get("canonical_dataset_version") == "2.5.0", "$/canonical_dataset_version", "canonical version must remain 2.5.0")
    require(isinstance(graph.get("canonical_sha256"), str) and bool(SHA.fullmatch(graph["canonical_sha256"])), "$/canonical_sha256", "invalid SHA256")
    canonical_data = None
    if canonical is not None:
        if isinstance(canonical, (str, Path)):
            canonical = Path(canonical).read_bytes()
        if isinstance(canonical, bytes):
            require(digest(canonical) == graph.get("canonical_sha256"), "$/canonical_sha256", "does not bind canonical bytes")
            canonical_data = json.loads(canonical)
        elif isinstance(canonical, dict):
            canonical_data = canonical
        else:
            require(False, "$/canonical_sha256", "unsupported canonical input")
        if canonical_data:
            require(canonical_data.get("dataset_version") == graph.get("canonical_dataset_version"), "$/canonical_dataset_version", "canonical version mismatch")
    entities = indexed(graph.get("entities"), ENTITY_FIELDS, "$/entities")
    sources = indexed(graph.get("sources"), SOURCE_FIELDS, "$/sources")
    assertions = indexed(graph.get("assertions"), ASSERTION_FIELDS, "$/assertions")
    reviews = indexed(graph.get("reviews"), REVIEW_FIELDS, "$/reviews")

    # New public projections never inherit canonical privacy exceptions.
    def privacy(value, path):
        if isinstance(value, str):
            require(not EMAIL.search(value), path, "personal/contact email forbidden in research exports")
            require(not SECRET.search(value), path, "credential-like value forbidden")
        elif isinstance(value, dict):
            for key, val in value.items():
                require(not re.search(r"(?:^|_)(?:email|phone|secret|token|raw_body|cache_path|credential)(?:$|_)", key, re.I), path + "/" + key, "private/cache field forbidden")
                privacy(val, path + "/" + key)
        elif isinstance(value, list):
            for i, val in enumerate(value):
                privacy(val, path + f"/{i}")
        elif isinstance(value, float):
            require(math.isfinite(value), path, "non-finite number forbidden")
    privacy(graph, "$")

    paper_ids = {}
    legacy_ids = []
    for eid, entity in entities.items():
        p = "$/entities/" + eid
        require(entity.get("kind") in KINDS, p + "/kind", "unknown kind")
        require(entity.get("status") in {"historical", "candidate", "approved", "excluded"}, p + "/status", "unknown status")
        require(entity.get("review_depth") in {"metadata", "abstract", "full_source", "historical"}, p + "/review_depth", "explicit review depth required")
        require(isinstance(entity.get("name"), str) and bool(entity["name"].strip()), p + "/name", "required")
        require(entity.get("disposition") in {"pending", "included", "excluded", "unclear", "historical_only"}, p + "/disposition", "unknown disposition")
        require(isinstance(entity.get("disposition_reason"), str) and bool(entity["disposition_reason"].strip()), p + "/disposition_reason", "explicit scope reason required")
        require(type(entity.get("eligible_core")) is bool, p + "/eligible_core", "expected boolean")
        strings(entity.get("aliases"), p + "/aliases")
        if strings(entity.get("assertion_ids"), p + "/assertion_ids"):
            for aid in entity["assertion_ids"]:
                require(aid in assertions, p + "/assertion_ids", f"unknown assertion {aid}")
                if aid in assertions:
                    require(eid in {assertions[aid].get("subject_id"), assertions[aid].get("object_id")}, p + "/assertion_ids", f"assertion {aid} does not involve entity")
        identifiers = entity.get("identifiers")
        require(isinstance(identifiers, dict) and all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in identifiers.items()), p + "/identifiers", "expected string identifiers")
        taxonomy = entity.get("taxonomy")
        if shape(taxonomy, FACETS, p + "/taxonomy"):
            for facet in FACETS:
                strings(taxonomy.get(facet), p + "/taxonomy/" + facet)
        if isinstance(identifiers, dict) and entity.get("kind") in {"paper", "paper_work"}:
            require(bool(set(identifiers) & {"doi", "arxiv", "acl"}), p + "/identifiers", "paper needs DOI, arXiv or ACL work identifier")
            for scheme in ("doi", "arxiv", "acl"):
                identifier = identifiers.get(scheme)
                if identifier:
                    key = (scheme, normalize_identifier(scheme, identifier))
                    require(key not in paper_ids, p + "/identifiers", "duplicate paper work; versions are not separate works")
                    paper_ids[key] = eid
        if entity.get("kind") in {"dataset", "dataset_family", "dataset_release", "benchmark", "benchmark_family", "benchmark_version"}:
            require(isinstance(entity.get("family_id"), str) and bool(ID.fullmatch(entity["family_id"])), p + "/family_id", "family identifier required")
        elif entity.get("family_id") is not None:
            require(False, p + "/family_id", "only dataset/benchmark families use family_id")
        parent = entity.get("parent_id")
        expected_parent = {"paper_version": {"paper", "paper_work"},
                           "dataset_release": {"dataset", "dataset_family"},
                           "benchmark_version": {"benchmark", "benchmark_family"}}
        if entity.get("kind") in expected_parent:
            require(parent in entities and entities[parent].get("kind") in expected_parent[entity["kind"]], p + "/parent_id", "manifestation must link its work/family")
            if parent in entities and entity.get("kind") != "paper_version":
                require(entity.get("family_id") == entities[parent].get("family_id"), p + "/family_id", "release/version must retain parent family")
        else:
            require(parent is None, p + "/parent_id", "only manifestations use parent_id")
        legacy = entity.get("legacy_id")
        if legacy is not None:
            require(isinstance(legacy, str), p + "/legacy_id", "expected canonical company id")
            legacy_ids.append(legacy)
            if canonical_data:
                require(legacy in {c["id"] for c in canonical_data["companies"]}, p + "/legacy_id", "unknown canonical company")
    require(len(legacy_ids) == len(set(legacy_ids)), "$/entities", "duplicate canonical organization import")
    families = [(e["kind"].split("_")[0], e.get("family_id")) for e in entities.values()
                if e.get("kind") in {"dataset", "dataset_family", "benchmark", "benchmark_family"}]
    require(len(families) == len(set(families)), "$/entities", "duplicate dataset/benchmark family; use release/version entities")
    if canonical_data:
        require(set(legacy_ids) == {c["id"] for c in canonical_data["companies"]}, "$/entities", "must retain exactly the canonical 39 organization identities")

    for sid, source in sources.items():
        p = "$/sources/" + sid
        require(_public_url(source.get("url")), p + "/url", "public credential-free HTTPS URL required")
        for field in ("title", "publisher", "version", "locator"):
            require(isinstance(source.get(field), str) and bool(source[field].strip()), p + "/" + field, "required")
        require(source.get("source_type") in {"paper", "dataset_card", "provider_documentation", "repository", "metadata", "legacy"}, p + "/source_type", "unknown type")
        require(source.get("status") in {"captured", "metadata_only", "historical_reference"}, p + "/status", "unknown status")
        published = dated(source.get("published_on"), p + "/published_on", nullable=True)
        captured = dated(source.get("captured_on"), p + "/captured_on", timestamp=True, nullable=source.get("status") == "historical_reference")
        if as_of and captured:
            require(captured <= as_of, p + "/captured_on", "capture cannot follow graph as_of")
        if published and captured:
            require(published <= captured.date(), p + "/published_on", "publication cannot follow capture")
        require(source.get("license") is None or isinstance(source.get("license"), str), p + "/license", "expected explicit license or null, never inferred")
        if source.get("status") == "captured":
            require(isinstance(source.get("response_sha256"), str) and bool(SHA.fullmatch(source["response_sha256"])), p + "/response_sha256", "captured source requires exact response hash")
            require(isinstance(source.get("excerpt"), str) and bool(source["excerpt"].strip()), p + "/excerpt", "captured source requires concise permitted excerpt")
            require(isinstance(source.get("excerpt"), str) and len(source["excerpt"].split()) <= 25, p + "/excerpt", "concise excerpt must not exceed 25 words")
            require(source.get("excerpt_sha256") == digest(source.get("excerpt", "")), p + "/excerpt_sha256", "excerpt digest mismatch")
        elif source.get("status") == "historical_reference":
            require(source.get("source_type") == "legacy", p + "/source_type", "historical reference must retain legacy scope")
            require(source.get("captured_on") is None, p + "/captured_on", "import cannot invent retrieval date")
        else:
            require(source.get("source_type") == "metadata", p + "/source_type", "metadata-only is discovery, not source evidence")

    invocation_roles = {}
    for rid, review in reviews.items():
        p = "$/reviews/" + rid
        require(review.get("role") in REVIEW_ROLES, p + "/role", "unknown role")
        require(review.get("reviewer_type") in {"ai", "human"}, p + "/reviewer_type", "unknown reviewer type")
        require(review.get("verdict") in {"pass", "revise", "reject"}, p + "/verdict", "unknown verdict")
        require(review.get("method") in {"source_content_review", "metadata_review", "historical_import"}, p + "/method", "unknown method")
        for field in ("reviewer", "invocation_id", "note"):
            require(isinstance(review.get(field), str) and bool(review[field].strip()), p + "/" + field, "actual review identity and scope required")
        invocation_roles.setdefault(review.get("invocation_id"), set()).add(review.get("role"))
        reviewed = dated(review.get("reviewed_on"), p + "/reviewed_on", timestamp=True)
        if as_of and reviewed:
            require(reviewed <= as_of, p + "/reviewed_on", "review cannot follow graph as_of")
        if strings(review.get("assertion_ids"), p + "/assertion_ids"):
            require(bool(review["assertion_ids"]), p + "/assertion_ids", "empty review scope")
            bindings = review.get("assertion_sha256")
            require(isinstance(bindings, dict) and set(bindings) == set(review["assertion_ids"]),
                    p + "/assertion_sha256", "review must bind every exact assertion")
            for aid in review["assertion_ids"]:
                require(aid in assertions, p + "/assertion_ids", "unknown assertion")
                if aid in assertions:
                    require(rid in assertions[aid].get("review_ids", []), p, "review/assertion references must be reciprocal")
                    require(isinstance(bindings, dict) and bindings.get(aid) == assertion_digest(assertions[aid]),
                            p + "/assertion_sha256", "reviewed assertion content changed; a new actual review is required")
        if strings(review.get("source_ids"), p + "/source_ids"):
            for sid in review["source_ids"]:
                require(sid in sources, p + "/source_ids", "unknown source")
                if sid in sources and sources[sid].get("captured_on") and reviewed:
                    captured = dated(sources[sid]["captured_on"], p + "/source_ids/captured_on", timestamp=True)
                    if captured:
                        require(reviewed >= captured, p + "/reviewed_on", "review precedes the cited source capture")
    require(all(len(roles) == 1 for roles in invocation_roles.values()), "$/reviews", "one invocation cannot impersonate multiple independent review roles")

    for aid, assertion in assertions.items():
        p = "$/assertions/" + aid
        require(assertion.get("subject_id") in entities, p + "/subject_id", "unknown subject")
        require(assertion.get("predicate") in PREDICATES, p + "/predicate", "unknown predicate")
        obj = assertion.get("object_id")
        value = assertion.get("value")
        require((obj is None) != (value is None), p, "exactly one object_id or typed value required")
        if obj is not None:
            require(obj in entities, p + "/object_id", "unknown object")
        if value is not None and shape(value, {"type", "value"}, p + "/value"):
            typ, val = value.get("type"), value.get("value")
            valid = ((typ == "text" and isinstance(val, str) and bool(val.strip())) or
                     (typ == "number" and type(val) in {int, float} and math.isfinite(val)) or
                     (typ == "boolean" and type(val) is bool))
            if typ == "date":
                valid = dated(val, p + "/value/value") is not None
            require(valid, p + "/value", "typed value/type mismatch")
        require(assertion.get("status") in {"candidate", "approved", "rejected", "historical"}, p + "/status", "unknown status")
        require(assertion.get("provenance_kind") in {"first_party", "independent", "mixed", "historical"}, p + "/provenance_kind", "unknown provenance scope")
        adate = dated(assertion.get("as_of"), p + "/as_of")
        if adate and as_of:
            require(adate <= as_of.date(), p + "/as_of", "assertion date cannot follow graph as_of")
        strings(assertion.get("qualifications"), p + "/qualifications")
        evidence = assertion.get("evidence")
        require(isinstance(evidence, list) and bool(evidence), p + "/evidence", "source-bound evidence required")
        bound_sources = set()
        for i, item in enumerate(evidence if isinstance(evidence, list) else []):
            ep = p + f"/evidence/{i}"
            if not shape(item, {"source_id", "locator", "excerpt_sha256"}, ep):
                continue
            sid = item.get("source_id")
            require(sid in sources, ep + "/source_id", "unknown source")
            require(isinstance(item.get("locator"), str) and bool(item["locator"].strip()), ep + "/locator", "precise locator required")
            if sid in sources:
                bound_sources.add(sid)
                require(item.get("excerpt_sha256") == sources[sid].get("excerpt_sha256"), ep + "/excerpt_sha256", "evidence points to different excerpt")
                if assertion.get("status") == "approved":
                    require(sources[sid].get("status") == "captured", ep, "approved assertion cannot use metadata or historical import")
                    require(sources[sid].get("source_type") not in {"metadata", "legacy"}, ep, "discovery metadata is not source-content evidence")
        if strings(assertion.get("review_ids"), p + "/review_ids"):
            for rid in assertion["review_ids"]:
                require(rid in reviews, p + "/review_ids", "unknown review")
                if rid in reviews:
                    require(aid in reviews[rid].get("assertion_ids", []), p, "assertion/review references must be reciprocal")
        if assertion.get("status") == "historical":
            require(assertion.get("provenance_kind") == "historical", p, "historical provenance must be explicit")
        if assertion.get("status") == "approved":
            receipts = [reviews[rid] for rid in assertion.get("review_ids", []) if rid in reviews]
            passing = [r for r in receipts if r.get("verdict") == "pass" and r.get("method") == "source_content_review" and bound_sources <= set(r.get("source_ids", []))]
            require({r.get("role") for r in passing} >= REVIEW_ROLES, p + "/review_ids", "approval requires actual author, source_verifier and adversarial source reviews")
            require(len({r.get("invocation_id") for r in passing}) >= 3, p + "/review_ids", "three roles must use separate invocations")
            require(not any(r.get("verdict") != "pass" for r in receipts), p + "/review_ids", "unresolved negative review blocks approval")
            require(assertion.get("provenance_kind") != "historical", p, "historical import cannot be new approval")
            if assertion.get("predicate") == "supplies_data_for":
                require(bool(assertion.get("qualifications")), p + "/qualifications", "supplier attribution needs source-specific scope and limitations")
                require(entities.get(assertion.get("subject_id"), {}).get("kind") in {"supplier", "organization"}, p, "supplier attribution subject must be organization/supplier")
                require(entities.get(obj, {}).get("kind") in {"paper", "paper_work", "paper_version", "dataset", "dataset_family", "dataset_release", "benchmark", "benchmark_family", "benchmark_version", "workflow"}, p, "supplier attribution object must be particular research artifact or workflow")
    coverage = graph.get("coverage")
    if shape(coverage, {"frozen_core", "quality_audit", "screening_audit", "notes"}, "$/coverage"):
        frozen = coverage.get("frozen_core")
        if shape(frozen, {"entity_ids", "frozen_on", "source_cutoff", "sha256"}, "$/coverage/frozen_core"):
            if strings(frozen.get("entity_ids"), "$/coverage/frozen_core/entity_ids"):
                for eid in frozen["entity_ids"]:
                    require(eid in entities, "$/coverage/frozen_core/entity_ids", "unknown core entity")
                declared = {eid for eid, ent in entities.items() if ent.get("eligible_core") is True}
                require(declared == set(frozen["entity_ids"]), "$/coverage/frozen_core", "eligible core must exactly match frozen identities")
                if frozen["entity_ids"]:
                    require(frozen.get("sha256") == digest(stable_json(sorted(frozen["entity_ids"]))), "$/coverage/frozen_core/sha256", "frozen core hash mismatch")
                    dated(frozen.get("frozen_on"), "$/coverage/frozen_core/frozen_on", timestamp=True)
                    dated(frozen.get("source_cutoff"), "$/coverage/frozen_core/source_cutoff", timestamp=True)
                else:
                    require(all(frozen.get(k) is None for k in ("frozen_on", "source_cutoff", "sha256")), "$/coverage/frozen_core", "unfrozen scope must remain explicitly null")
        # Audit manifests are interpreted by publication_gate, not accepted as totals here.
        for key in ("quality_audit", "screening_audit"):
            require(coverage.get(key) is None or isinstance(coverage.get(key), dict), "$/coverage/" + key, "expected real audit manifest or null")
        strings(coverage.get("notes"), "$/coverage/notes")
    if errors:
        raise GraphValidationError(errors)
    return graph


def validate_graph(graph, canonical=None):
    """Strict validation with a single actionable failure type for malformed input."""
    try:
        return _validate_graph(graph, canonical)
    except GraphValidationError:
        raise
    except (TypeError, KeyError, ValueError, AttributeError, OverflowError) as error:
        raise GraphValidationError(["$: malformed field type or value (" + type(error).__name__ + ")"]) from error


def normalize_identifier(scheme, identifier):
    value = str(identifier).strip().lower()
    if scheme == "doi":
        return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", value)
    if scheme == "arxiv":
        value = re.sub(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:)", "", value)
        return re.sub(r"v\d+(?:\.pdf)?$|\.pdf$", "", value)
    return value.rstrip("/")


def coverage_summary(graph):
    """Compute counts from records; candidates, aliases and versions do not inflate them."""
    validate_graph(graph)
    assertions = {a["id"]: a for a in graph["assertions"] if a["status"] == "approved"}
    qualifying = [e for e in graph["entities"] if e["status"] == "approved" and e["disposition"] == "included" and e["review_depth"] == "full_source"
                  and any(aid in assertions for aid in e["assertion_ids"])]
    suppliers = [e for e in qualifying if e["kind"] == "supplier" and any(
        assertions[aid]["subject_id"] == e["id"] and assertions[aid]["predicate"] == "has_capability"
        for aid in e["assertion_ids"] if aid in assertions)]
    legacy = [e for e in graph["entities"] if e["legacy_id"] is not None]
    disposed = lambda e: e["disposition"] in {"included", "excluded", "historical_only"} and any(aid in assertions for aid in e["assertion_ids"])
    core_ids = set(graph["coverage"]["frozen_core"]["entity_ids"])
    core_disposed = sum(disposed(e) for e in graph["entities"] if e["id"] in core_ids)
    counts = {"legacy_organizations": len(legacy), "legacy_dispositions": sum(disposed(e) for e in legacy),
              "qualifying_suppliers": len(suppliers), "reviewed_papers": sum(e["kind"] in {"paper", "paper_work"} for e in qualifying),
              "dataset_families": len({e["family_id"] for e in qualifying if e["kind"] in {"dataset", "dataset_family"}}),
              "benchmark_families": len({e["family_id"] for e in qualifying if e["kind"] in {"benchmark", "benchmark_family"}}),
              "approved_assertions": len(assertions), "candidate_assertions": sum(a["status"] == "candidate" for a in graph["assertions"]),
              "historical_assertions": sum(a["status"] == "historical" for a in graph["assertions"]),
              "candidate_entities": sum(e["status"] == "candidate" for e in graph["entities"]),
              "abstract_reviewed_entities": sum(e["review_depth"] == "abstract" for e in graph["entities"]),
              "captured_sources": sum(s["status"] == "captured" for s in graph["sources"]),
              "core_eligible": len(core_ids), "core_dispositioned": core_disposed,
              "core_disposition_rate": core_disposed / len(core_ids) if core_ids else 0.0}
    counts["launch_floors"] = dict(LAUNCH_FLOORS)
    counts["coverage_floors_met"] = bool(core_ids) and all(counts[k] >= v for k, v in LAUNCH_FLOORS.items())
    counts["quality_audit_recorded"] = graph["coverage"]["quality_audit"] is not None
    counts["screening_audit_recorded"] = graph["coverage"]["screening_audit"] is not None
    # Full publication readiness is owned by research_report.publication_gate.
    return counts


def _redact(value):
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items() if not re.search(r"email|phone|secret|token|cache_path|raw_body|credential", k, re.I)}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return SECRET.sub("[redacted credential]", EMAIL.sub("[redacted email]", value))
    return value


def public_graph(graph):
    """Return an explicit, privacy-filtered versioned projection; no canonical people."""
    # Allowlist before validation strips private extension fields at every graph row.
    projection = {k: copy.deepcopy(graph[k]) for k in ROOT_FIELDS if k in graph}
    for key, fields in (("entities", ENTITY_FIELDS), ("sources", SOURCE_FIELDS),
                        ("assertions", ASSERTION_FIELDS), ("reviews", REVIEW_FIELDS)):
        projection[key] = [{k: row[k] for k in fields if k in row} for row in projection.get(key, [])]
    # Unreviewed draft wording stays in the private intake/review queue. Public
    # metadata may describe a coverage gap, but exports must not leak its proposed
    # factual claim merely because the row has a candidate label.
    projection["assertions"] = [row for row in projection["assertions"] if row.get("status") != "candidate"]
    kept = {row["id"] for row in projection["assertions"]}
    for entity in projection["entities"]:
        entity["assertion_ids"] = [aid for aid in entity.get("assertion_ids", []) if aid in kept]
    retained_reviews = []
    for review in projection["reviews"]:
        review["assertion_ids"] = [aid for aid in review.get("assertion_ids", []) if aid in kept]
        if review["assertion_ids"]:
            review["assertion_sha256"] = {aid: review["assertion_sha256"][aid] for aid in review["assertion_ids"]}
            retained_reviews.append(review)
    projection["reviews"] = retained_reviews
    projection = _redact(projection)
    validate_graph(projection)
    for key in ("entities", "sources", "assertions", "reviews"):
        projection[key].sort(key=lambda row: row["id"])
    return projection


def _csv_cell(value):
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    elif value is None:
        value = ""
    elif type(value) is bool:
        value = "true" if value else "false"
    value = str(value)
    # CSV may be opened in spreadsheet software; formulas are always literal text.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def write_exports(graph, output):
    """Write byte-stable JSON/CSV/SQLite public projection; return relative paths.

    The caller owns publication. Existing database is replaced so historical freed
    SQLite pages cannot leak values. Export order and JSON serialization are fixed.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    projected = public_graph(graph)
    paths = ["research-graph.json", "research-graph.sqlite"]
    with (output / paths[0]).open("w", encoding="utf-8", newline="\n") as file:
        file.write(stable_json(projected))
    tables = (("entities", ENTITY_FIELDS), ("sources", SOURCE_FIELDS),
              ("assertions", ASSERTION_FIELDS), ("reviews", REVIEW_FIELDS))
    for table, fields in tables:
        name = "research-" + table + ".csv"
        paths.append(name)
        with (output / name).open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            columns = ["id"] + sorted(fields - {"id"})
            writer.writerow(columns)
            writer.writerows([_csv_cell(row[key]) for key in columns] for row in projected[table])
    database = output / "research-graph.sqlite"
    database.unlink(missing_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for key in sorted(ROOT_FIELDS - {"entities", "sources", "assertions", "reviews"}):
            connection.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(projected[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
        for table, fields in tables:
            columns = ["id"] + sorted(fields - {"id"})
            declaration = ",".join('"' + key + '" TEXT' + (" PRIMARY KEY" if key == "id" else "") for key in columns)
            connection.execute(f'CREATE TABLE "{table}" ({declaration})')
            placeholders = ",".join("?" for _ in columns)
            for row in projected[table]:
                values = [json.dumps(row[k], ensure_ascii=False, sort_keys=True, separators=(",", ":")) if isinstance(row[k], (dict, list)) else str(row[k]).lower() if type(row[k]) is bool else row[k] for k in columns]
                connection.execute(f'INSERT INTO "{table}" VALUES ({placeholders})', values)
        connection.execute("CREATE TABLE assertion_evidence (assertion_id TEXT NOT NULL REFERENCES assertions(id), source_id TEXT NOT NULL REFERENCES sources(id), locator TEXT NOT NULL, excerpt_sha256 TEXT, PRIMARY KEY(assertion_id, source_id, locator))")
        connection.execute("CREATE TABLE assertion_reviews (assertion_id TEXT NOT NULL REFERENCES assertions(id), review_id TEXT NOT NULL REFERENCES reviews(id), PRIMARY KEY(assertion_id, review_id))")
        for assertion in projected["assertions"]:
            for evidence in sorted(assertion["evidence"], key=lambda e: (e["source_id"], e["locator"])):
                connection.execute("INSERT INTO assertion_evidence VALUES (?,?,?,?)", (assertion["id"], evidence["source_id"], evidence["locator"], evidence["excerpt_sha256"]))
            for rid in sorted(assertion["review_ids"]):
                connection.execute("INSERT INTO assertion_reviews VALUES (?,?)", (assertion["id"], rid))
        connection.commit()
        connection.execute("VACUUM")
    manifest = {"schema_version": SCHEMA_VERSION, "release_id": graph["release_id"],
                "projection": "privacy-filtered-research-graph", "files": {
                    name: digest((output / name).read_bytes()) for name in sorted(paths)}}
    (output / "research-exports-manifest.json").write_text(stable_json(manifest), encoding="utf-8")
    return paths + ["research-exports-manifest.json"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    graph = load_graph(args.root)
    if args.output:
        write_exports(graph, args.output)
    print(stable_json(coverage_summary(graph)), end="")


if __name__ == "__main__":
    main()
