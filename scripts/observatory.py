#!/usr/bin/env python3
"""Validate public evidence; build immutable JSON releases, SQLite, CSV, offline UI."""
import argparse
import csv
import hashlib
import io
import ipaddress
import json
import math
import re
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from schema_def import SCHEMA, TABLES

ROOT = Path(__file__).resolve().parents[1]
CONFIDENCE = {"U": 0, "C": 1, "B": 2, "A": 3}

class ValidationError(ValueError): pass

def require(condition, message):
    if not condition: raise ValidationError(message)

def validate_link_health(data):
    """Keep public link observations separate from research and private request data."""
    require(isinstance(data, dict) and set(data) == {"version", "entries"}, "link-health: unsupported root fields")
    require(data["version"] == "1.0.0" and isinstance(data["entries"], list), "link-health: unsupported format")
    seen = set()
    for entry in data["entries"]:
        require(isinstance(entry, dict) and set(entry) == {"url", "status", "checked_on"}, "link-health: only public URL, status and checked date are allowed")
        require(entry["status"] in ("not_found", "gone", "sign_in"), "link-health: unsupported observation")
        require(isinstance(entry["checked_on"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["checked_on"]), "link-health: invalid checked date")
        try: date.fromisoformat(entry["checked_on"])
        except ValueError: raise ValidationError("link-health: invalid checked date")
        require(isinstance(entry["url"], str) and not re.search(r"[\s\x00-\x1f]", entry["url"]), "link-health: invalid public URL")
        try:
            parsed = urlsplit(entry["url"])
            host = (parsed.hostname or "").lower().rstrip(".")
            parsed.port
        except ValueError: raise ValidationError("link-health: invalid public URL")
        require(parsed.scheme in ("https", "http") and not parsed.username and not parsed.password and "." in host and ":" not in host and not re.search(r"(?:^|\.)(?:localhost|local|internal|test|invalid)$", host), "link-health: local or credential-bearing URLs are not allowed")
        try: address = ipaddress.ip_address(host)
        except ValueError: address = None
        require(address is None or address.is_global, "link-health: local addresses are not allowed")
        require(not any(re.search(r"(?:^|[-_])(?:token|api[-_]?key|password|passwd|secret|credential|signature)(?:$|[-_])", key, re.I) for key, _ in parse_qsl(parsed.query)), "link-health: credential parameters are not allowed")
        require(entry["url"] not in seen, "link-health: duplicate public URL")
        seen.add(entry["url"])
    return data

EVENT_FIELDS = {"id", "company_id", "related_company_ids", "kind", "date", "date_basis", "title", "detail", "status", "status_checked_on", "sources"}
EVENT_SOURCE_FIELDS = {"url", "title", "publisher", "published_on", "source_type"}

def validate_company_events(events, data):
    """Dated public events reviewed after the pinned dataset. Lawsuit rows describe allegations and filings, not findings."""
    require(isinstance(events, dict) and set(events) == {"version", "reviewed_on", "note", "events"}, "company-events: root must hold exactly version, reviewed_on, note and events")
    require(events["version"] == "1.0.0" and isinstance(events["events"], list), "company-events: unsupported version, or events is not a list")
    def checked_date(value, label, month=False):
        require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}" + (r"(?:-[0-9]{2})?" if month else r"-[0-9]{2}"), value), f"{label} must be YYYY-MM-DD" + (" or YYYY-MM" if month else ""))
        try: date.fromisoformat(value if len(value) == 10 else value + "-01")
        except ValueError: raise ValidationError(f"{label} is not a calendar date")
        return value
    def text(value, label, limit=None):
        require(isinstance(value, str) and value.strip(), f"{label} must be non-empty text")
        require(not re.search(r"[<>\x00-\x1f\x7f]", value), f"{label} must be plain text without < > or control characters")
        require(limit is None or len(value) <= limit, f"{label} is longer than {limit} characters")
    reviewed_on = checked_date(events["reviewed_on"], "company-events: reviewed_on")
    text(events["note"], "company-events: note")
    companies = {row["id"] for row in data["companies"]}
    seen = set()
    for event in events["events"]:
        require(isinstance(event, dict) and set(event) == EVENT_FIELDS, "company-events: each event must hold exactly " + ", ".join(sorted(EVENT_FIELDS)))
        require(isinstance(event["id"], str) and re.fullmatch(r"[a-z0-9_]+\.event\.[a-z0-9-]+", event["id"]), f"company-events: invalid event id {event['id']!r}")
        require(event["id"] not in seen, f"company-events: duplicate event id {event['id']}")
        seen.add(event["id"])
        where = "company-events: " + event["id"]
        require(isinstance(event["company_id"], str) and event["company_id"] in companies, f"{where}: unknown company_id {event['company_id']!r}")
        require(isinstance(event["related_company_ids"], list) and all(isinstance(value, str) and value in companies for value in event["related_company_ids"]), f"{where}: related_company_ids must list known company IDs")
        require(event["kind"] in ("lawsuit", "data_incident", "customer_change", "workforce_change", "filing"), f"{where}: unsupported kind {event['kind']!r}")
        require(checked_date(event["date"], f"{where}: date", month=True) <= reviewed_on, f"{where}: date is after reviewed_on")
        require(event["date_basis"] in ("filed", "reported", "published", "announced"), f"{where}: unsupported date_basis {event['date_basis']!r}")
        text(event["title"], f"{where}: title", 110)
        text(event["detail"], f"{where}: detail", 320)
        text(event["status"], f"{where}: status", 40)
        checked_date(event["status_checked_on"], f"{where}: status_checked_on")
        require(isinstance(event["sources"], list) and event["sources"], f"{where}: sources must be a non-empty list")
        for source in event["sources"]:
            require(isinstance(source, dict) and set(source) == EVENT_SOURCE_FIELDS, f"{where}: each source must hold exactly " + ", ".join(sorted(EVENT_SOURCE_FIELDS)))
            text(source["title"], f"{where}: source title")
            text(source["publisher"], f"{where}: source publisher")
            require(source["source_type"] in ("court_record", "filing", "company", "news"), f"{where}: unsupported source_type {source['source_type']!r}")
            if source["published_on"] is not None: checked_date(source["published_on"], f"{where}: source published_on")
            unsafe = f"{where}: source url must be https with a hostname and no credentials"
            require(isinstance(source["url"], str) and not re.search(r"[\s\x00-\x1f\x7f]", source["url"]), unsafe)
            try: url = urlsplit(source["url"]); url.port
            except ValueError: raise ValidationError(unsafe)
            require(url.scheme == "https" and url.hostname and url.username is None and url.password is None, unsafe)
    return events

def load_company_events(path, data):
    """Events were reviewed against dataset 2.5.0; other datasets, including the pipeline fixtures, receive none."""
    if not path.exists() or data["dataset_version"] != "2.5.0": return {"version": "1.0.0", "events": []}
    return validate_company_events(json.loads(path.read_text()), data)

def validate_shape(value, spec, path="$",):
    """Small strict validator for the deliberately limited vocabulary in schema_def."""
    kind = spec.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list), "string": lambda: isinstance(value, str), "number": lambda: type(value) in (int, float) and math.isfinite(value), "boolean": lambda: type(value) is bool}[kind]()
    require(valid, f"{path}: expected {kind}")
    if "enum" in spec: require(value in spec["enum"], f"{path}: invalid value {value!r}")
    if "const" in spec: require(value == spec["const"], f"{path}: unsupported schema version")
    if kind == "object":
        require(not set(value) - set(spec["properties"]), f"{path}: unknown fields {sorted(set(value) - set(spec['properties']))}; only public research fields are allowed")
        require(not set(spec["required"]) - set(value), f"{path}: missing required fields {sorted(set(spec['required']) - set(value))}")
        for key, child in value.items(): validate_shape(child, spec["properties"][key], f"{path}.{key}")
    elif kind == "array":
        require(len(value) >= spec.get("minItems", 0), f"{path}: too few items")
        if spec.get("uniqueItems"): require(len({json.dumps(v, sort_keys=True) for v in value}) == len(value), f"{path}: duplicate items")
        for i, child in enumerate(value): validate_shape(child, spec["items"], f"{path}[{i}]")
    elif kind == "string":
        require(len(value.strip()) >= spec.get("minLength", 0), f"{path}: empty value")
        if "pattern" in spec: require(re.fullmatch(spec["pattern"], value) is not None, f"{path}: invalid format")
        if spec.get("pattern") == r"^\d{4}-\d{2}-\d{2}$":
            try: date.fromisoformat(value)
            except ValueError: raise ValidationError(f"{path}: invalid calendar date")
    elif kind == "number": require(value >= spec.get("minimum", -math.inf), f"{path}: negative value")

def not_future(value, snapshot):
    # Partial dates stay partial. Validate exact dates, otherwise only reject explicit future years.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try: date.fromisoformat(value)
        except ValueError: return False
        return value <= snapshot
    match = re.match(r"^(?:FY)?(\d{4})", value)
    return not match or int(match.group(1)) <= int(snapshot[:4])


def validate(data):
    validate_shape(data, SCHEMA)
    indices = {}
    for name in TABLES:
        indices[name] = {r["id"]: r for r in data[name]}
        require(len(indices[name]) == len(data[name]), f"{name}: duplicate id")
    def ref(table, key):
        require(key in indices[table], f"missing {table} reference: {key}")
        return indices[table][key]
    def url(value):
        parsed = urlsplit(value)
        require(parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password, f"unsafe or non-public URL: {value}")
        require(parsed.hostname not in ("localhost", "127.0.0.1", "::1") and not parsed.hostname.endswith(".local"), "local URLs are not public evidence")
    for source in data["sources"]:
        url(source["url"])
        if "archive_url" in source: url(source["archive_url"])
        require(source["accessed_on"] <= data["meta"]["as_of"], f"{source['id']}: accessed after snapshot date")
    for claim in data["claims"]:
        ref("companies", claim["company_id"])
        for cid in claim.get("confidence_basis_claim_ids",[]):
            inherited=ref("claims",cid)
            require(inherited["company_id"]==claim["company_id"], "confidence basis belongs to another company")
        if claim.get("confidence_basis_claim_ids"):
            inherited_grade=max((ref("claims",cid)["confidence"] for cid in claim["confidence_basis_claim_ids"]),key=lambda x:"ABCU".index(x))
            require(claim["confidence"]==inherited_grade, "criterion evidence must preserve inherited confidence")
        for sid in claim["source_ids"] + claim.get("historical_source_ids", []) + claim.get("contradicting_source_ids", []): ref("sources", sid)
        require(not set(claim["source_ids"]) & set(claim.get("historical_source_ids", [])), f"{claim['id']}: historical citation cannot be current support")
        require(not set(claim["source_ids"]) & set(claim.get("contradicting_source_ids", [])), f"{claim['id']}: source both supports and contradicts")
        require(not_future(claim["as_of"], data["meta"]["as_of"]), f"{claim['id']}: future claim")
        if claim["confidence"] != "U":
            require(bool(claim["source_ids"]), f"{claim['id']}: verified claim requires sources")
            current_support=any(ref("sources", s)["retrieval_status"] in ("checked", "summary_only") for s in claim["source_ids"])
            historical_gate=any(a.get("stale_source_caveat") and any(claim["id"] in g["claim_ids"] for g in a["gates"].values()) for a in data["assessments"]) and any(any(check["retrieval_status"] in ("checked","summary_only") for check in ref("sources",sid).get("previous_checks",[])) for sid in claim["source_ids"])
            require(claim["status"]=="superseded" or current_support or historical_gate, f"{claim['id']}: verified claim requires checked evidence")
        else: require(claim["status"] in ("unverified", "contested", "superseded"), f"{claim['id']}: U cannot be supported")
    for raw in data["raw_inputs"]:
        raw_path = Path(raw["path"])
        require(not raw_path.is_absolute() and ".." not in raw_path.parts and raw_path.parts[:2] == ("data", "raw"), "raw inputs must use data/raw relative paths")
    for name in ("metrics", "funding_rounds", "company_people", "customer_evidence", "company_relationships", "products", "editorial_readouts"):
        for row in data[name]:
            ref("companies", row["company_id"])
            require(ref("claims", row["claim_id"])["company_id"] == row["company_id"], f"{row['id']}: claim belongs to another company")
            if "segment_scope" in row: require(ref("claims", row["claim_id"])["segment_scope"] == row["segment_scope"], f"{row['id']}: claim belongs to another segment")
    for company in data["companies"]:
        url(company["website"])
        for cid in [company["identity_claim_id"]] + company["profile_claim_ids"]:
            require(ref("claims", cid)["company_id"] == company["id"], f"{company['id']}: profile claim belongs to another company")
    money = {"arr", "annualized_revenue_run_rate", "gmv", "revenue", "valuation", "funding_total_reported", "funding_total_calculated"}
    for metric in data["metrics"]:
        require(metric["value"] >= 0 or metric["kind"] in ("growth_rate", "other"), f"{metric['id']}: negative value requires signed growth or other accounting measure")
        require(not_future(metric["as_of"], data["meta"]["as_of"]), f"{metric['id']}: future metric")
        require(metric["as_of"] == ref("claims", metric["claim_id"])["as_of"], f"{metric['id']}: metric/claim date mismatch")
        if metric["kind"] in money: require(metric["unit"] == "currency" and "currency" in metric, f"{metric['id']}: currency required")
        if metric["unit"] == "currency": require("currency" in metric, f"{metric['id']}: currency required")
        else: require("currency" not in metric, f"{metric['id']}: unexpected currency")
        if metric["kind"] in ("headcount", "expert_network", "active_paid_experts"): require(metric["unit"] == "people", f"{metric['id']}: people unit required")
        if metric["kind"] == "growth_rate": require(metric["unit"] == "percent", f"{metric['id']}: percent unit required")
        if metric["qualifier"] == "range": require("upper_value" in metric and metric["upper_value"] >= metric["value"], f"{metric['id']}: invalid range")
        else: require("upper_value" not in metric, f"{metric['id']}: upper value requires range")
        require(("period_start" in metric) == ("period_end" in metric), f"{metric['id']}: incomplete period")
        if metric["kind"] == "revenue": require("period_start" in metric or "period_label" in metric, f"{metric['id']}: actual revenue requires reporting period")
        if "period_start" in metric: require(metric["period_start"] <= metric["period_end"] and not_future(metric["period_end"], data["meta"]["as_of"]), f"{metric['id']}: invalid reporting period")
    events = set()
    for row in data["funding_rounds"]:
        key = (row["company_id"], row["event_key"])
        require(key not in events, f"duplicate funding event: {key}")
        events.add(key)
        require(not_future(row["announced_on"], data["meta"]["as_of"]), f"{row['id']}: future funding event")
        if "closed_on" in row:
            require(row["status"] == "closed" and not_future(row["closed_on"], data["meta"]["as_of"]), f"{row['id']}: close date requires a closed round")
        require(("amount" in row) == ("currency" in row), f"{row['id']}: amount and currency must be paired")
        if row.get("include_in_disclosed_primary_sum"):
            require(row["status"] in ("closed","announced") and row["capital_type"] in ("equity","debt","grant","undisclosed") and row["amount_basis"]=="new_capital" and row["qualifier"]=="exact" and "amount" in row and ref("claims",row["claim_id"])["status"]=="supported", f"{row['id']}: disclosed primary sum requires a supported distinct primary amount")
        if row["capital_type"]=="mixed": require(row["amount_basis"]!="new_capital", f"{row['id']}: mixed transaction is not all new capital")
        if row["include_in_total"]:
            require(row["status"] == "closed" and row["qualifier"] == "exact" and row["amount_basis"] == "new_capital" and "amount" in row and row["capital_type"] in ("equity", "debt", "grant") and ref("claims", row["claim_id"])["status"] == "supported", f"{row['id']}: only distinct supported closed primary new capital can enter totals")
        if "parent_round_id" in row:
            parent = ref("funding_rounds", row["parent_round_id"])
            require(parent["company_id"] == row["company_id"] and parent["id"] != row["id"], f"{row['id']}: invalid parent round")
    for row in data["company_relationships"]:
        if "related_company_id" in row:
            ref("companies", row["related_company_id"])
            require(row["related_company_id"] != row["company_id"], "company relationship cannot reference itself")
        require(row["as_of"] <= data["meta"]["as_of"], "company relationship after snapshot date")
    for row in data.get("company_investors", []):
        ref("investors", row["investor_id"])
    for row in data["company_people"]:
        ref("people", row["person_id"])
        for cid in row.get("background_claim_ids", []): require(ref("claims", cid)["company_id"] == row["company_id"], "background claim belongs to another company")
    for row in data["round_investors"]:
        ref("investors", row["investor_id"])
        require(ref("claims", row["claim_id"])["company_id"] == ref("funding_rounds", row["round_id"])["company_id"], f"{row['id']}: investor claim belongs to another company")
    rubric = data["rubric"]
    require(len({s["id"] for s in rubric["stages"]}) == len(rubric["stages"]), "duplicate rubric stage")
    if rubric["status"] == "pending":
        require(not data["assessments"], "cannot assess companies before final rubric")
    else:
        require({c["id"] for c in rubric["dimensions"]} == {"P", "C", "R", "O"}, "final rubric must define P/C/R/O")
        expected = [{"P":"2","C":"3","R":"3","O":"2"},{"P":"2","C":"2","R":"2","O":"2"},{"P":"2","C":"2"},{"P":"1","O":"1"},{}]
        require([s["minimums"] for s in rubric["stages"]] == expected, "rubric v1 stage thresholds must match the approved methodology")
    assessment_keys = set()
    for assessment in data["assessments"]:
        company = ref("companies", assessment["company_id"])
        if assessment.get("headline_metric_id"):
            headline=ref("metrics",assessment["headline_metric_id"])
            require(headline["company_id"]==assessment["company_id"] and headline["segment_scope"]==assessment["segment_scope"], "headline metric must match assessment scope")
        require(company["entity_type"] == "commercial", "commercial gates apply only to commercial entities")
        key = (assessment["company_id"], assessment["segment_scope"])
        require(key not in assessment_keys, "one current assessment per company and segment")
        assessment_keys.add(key)
        require(assessment["rubric_version"] == rubric["version"], "assessment rubric version mismatch")
        require(assessment["as_of"] <= data["meta"]["as_of"], "assessment after snapshot date")
        for dimension, result in assessment["gates"].items():
            gate_claims = []
            for cid in result["claim_ids"]:
                claim = ref("claims", cid)
                require(claim["company_id"] == assessment["company_id"], "assessment claim belongs to another company")
                require(claim["segment_scope"] == assessment["segment_scope"], "assessment cannot inherit another segment's evidence")
                require(not_future(claim["as_of"], assessment["as_of"]), "assessment uses future evidence")
                gate_claims.append(claim)
            if result["level"] != "U":
                require(gate_claims and all(c["status"] == "supported" and c["confidence"] != "U" for c in gate_claims), "known gate needs supported, verified evidence")
                if dimension == "C" and result["level"] == "3":
                    reported_buyer = result.get("corroboration_basis")=="reported_buyer_statement" and any(any(ref("sources",sid)["source_type"]=="independent_reporting" for sid in c["source_ids"]) for c in gate_claims)
                    require(any(c["confidence"] == "A" for c in gate_claims) or reported_buyer, "C3 requires independent A evidence or explicitly reviewed attributed buyer statements")
    return indices


def assessment_for(data, company_id, segment="ai_data"):
    return next((a for a in data["assessments"] if a["company_id"] == company_id and a["segment_scope"] == segment), None)


def classify(data, company_id, segment="ai_data"):
    company = next(c for c in data["companies"] if c["id"] == company_id)
    if company["entity_type"] == "adjacent_research": return "not_applicable"
    if data["rubric"]["status"] != "final": return "pending"
    assessment = assessment_for(data, company_id, segment)
    if not assessment: return "pending"
    for stage in data["rubric"]["stages"]:
        if all(assessment["gates"][gate]["level"] != "U" and int(assessment["gates"][gate]["level"]) >= int(minimum) for gate, minimum in stage["minimums"].items()): return stage["id"]
    return "insufficient_public_evidence"


def stage_confidence(data, company_id, segment="ai_data"):
    stage = next((s for s in data["rubric"]["stages"] if s["id"] == classify(data, company_id, segment)), None)
    if not stage or not stage["minimums"]: return "unclassified"
    assessment = assessment_for(data, company_id, segment)
    index = {c["id"]: c for c in data["claims"]}
    essential = [index[cid] for dim in stage["minimums"] for cid in assessment["gates"][dim]["claim_ids"]]
    if assessment["material_conflict"] or any(c["confidence"] in ("C", "U") for c in essential): return "low_provisional"
    if assessment.get("stale_source_caveat"): return "medium"
    buyer_claims = [index[cid] for dim in ("C", "R") if dim in stage["minimums"] for cid in assessment["gates"][dim]["claim_ids"]]
    sources = {s["id"]: s for s in data["sources"]}
    direct = any(c["confidence"] == "A" and any(sources[sid]["source_type"] in ("customer", "filing") for sid in c["source_ids"]) for c in buyer_claims)
    return "high" if direct else "medium"


def canonical_bytes(data): return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()

def safe_csv(value):
    if value is None: return ""
    if isinstance(value, (list, dict)): value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    # Prevent spreadsheet formula execution, including control-character prefixes.
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))): return "'" + value
    return value

def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: safe_csv(row.get(key)) for key in columns} for row in rows)

def create_database(path, data):
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript((ROOT / "schema/database.sql").read_text())
        with con:
            con.execute("PRAGMA defer_foreign_keys=ON")
            con.execute("INSERT INTO dataset VALUES (?, ?, ?, ?)", (data["dataset_version"], data["schema_version"], data["meta"]["as_of"], canonical_bytes(data).decode()))
            for name in TABLES:
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
                for row in data[name]:
                    encoded = {**row, "record_json": json.dumps(row, ensure_ascii=False)}
                    values = [json.dumps(encoded[c], ensure_ascii=False) if isinstance(encoded.get(c), (list, dict)) else encoded.get(c) for c in cols]
                    con.execute(f"INSERT INTO {name} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", values)
            for claim in data["claims"]:
                for relation, key in [("supports", "source_ids"), ("historical", "historical_source_ids"), ("contradicts", "contradicting_source_ids")]:
                    for sid in claim.get(key, []): con.execute("INSERT INTO claim_sources VALUES (?, ?, ?)", (claim["id"], sid, relation))
            for company in data["companies"]:
                for segment in ("ai_data", "company", "research", "other_segment"):
                    con.execute("INSERT INTO classifications VALUES (?, ?, ?, ?, ?)", (company["id"], segment, classify(data, company["id"], segment), stage_confidence(data, company["id"], segment), data["rubric"]["version"]))
        require(not con.execute("PRAGMA foreign_key_check").fetchall(), "SQLite foreign key failure")
        require(con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity failure")
    finally: con.close()
    # Bytes 96-100 hold the SQLite library version that wrote the file. They are informational only;
    # zeroing them keeps the database byte-identical across machines so --verify is reproducible.
    with open(path, "r+b") as handle:
        handle.seek(96); handle.write(b"\x00" * 4)

def render_snapshot_metadata(html, data):
    compiled = date.fromisoformat(data["meta"]["as_of"])
    month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[compiled.month - 1]
    label = f"Public research · compiled {compiled.day} {month} {compiled.year}"
    return html.replace("{{SNAPSHOT_LABEL}}", label).replace("{{DATASET_VERSION}}", data["dataset_version"])

STATIC_DOWNLOAD_FILES = {
    "INVESTOR": ("assets/Investor_Snapshot_Human_Depth.png", "PNG"),
    "SQLITE": ("observatory.sqlite", "SQLite"),
    "WORK": ("work-routes.json", "JSON"),
    "PROFILES": ("profile-content.json", "JSON"),
    "EDITORIAL": ("editorial.json", "JSON"),
    "LOGOS": ("logo-provenance.json", "JSON"),
    "LINK_HEALTH": ("link-health.json", "JSON"),
    "SOURCE_UPDATES": ("source-updates.json", "JSON"),
}

def validate_source_updates(updates, data, profile_content):
    """Validate later product presentation facts without rewriting their snapshots."""
    require(isinstance(updates, dict) and updates.get("version") == "1.0.0", "source-updates: unsupported format")
    require(updates.get("baseline_dataset_version") == data["dataset_version"], "source-updates: snapshot version mismatch")
    require(isinstance(updates.get("updates"), list), "source-updates: updates must be a list")
    companies = {row["id"] for row in data["companies"]}
    records = {row["id"]: row for row in data["products"]}
    claims = {row["id"]: row for row in data["claims"]}
    profiles = {entry["company_id"]: entry for entry in profile_content["entries"]}
    seen = set()
    def checked_source(source):
        require(isinstance(source, dict) and set(source) == {"url", "title", "observed_on", "published_on"}, "source-updates: invalid source fields")
        require(isinstance(source["url"], str) and not re.search(r"[\s\x00-\x1f]", source["url"]), "source-updates: invalid source URL")
        parsed = urlsplit(source["url"])
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password, "source-updates: invalid source URL")
        require(isinstance(source["title"], str) and source["title"].strip(), "source-updates: source title missing")
        for field in ("observed_on", "published_on"):
            value = source[field]
            if field == "published_on" and value is None: continue
            require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "source-updates: invalid source date")
            try: date.fromisoformat(value)
            except ValueError: raise ValidationError("source-updates: invalid source date")
    for update in updates["updates"]:
        require(isinstance(update, dict) and isinstance(update.get("id"), str) and update["id"] not in seen, "source-updates: duplicate or missing update ID")
        seen.add(update["id"])
        company = update.get("company_id")
        require(company in companies, "source-updates: unknown company")
        target = update.get("target", {})
        require(isinstance(target, dict) and set(target) == {"product_name", "record_ids", "claim_ids"}, "source-updates: invalid product target")
        matches = [product for product in profiles.get(company, {}).get("products", []) if product["name"] == target["product_name"]]
        require(len(matches) == 1, "source-updates: product target must match one curated product")
        product = matches[0]
        for field in ("record_ids", "claim_ids"):
            require(target[field] == product[field], "source-updates: product binding mismatch")
        replacements = update.get("replacement_fields", {})
        require(isinstance(replacements, dict) and replacements and set(replacements) <= {"description", "status"}, "source-updates: only product descriptions and statuses may change")
        require(all(isinstance(value, str) and value.strip() for value in replacements.values()), "source-updates: replacement text missing")
        require(update.get("previous_fields") == {field: product.get(field) for field in replacements}, "source-updates: previous product fields mismatch")
        require(isinstance(update.get("qualification"), str) and update["qualification"].strip(), "source-updates: qualification missing")
        checked_source(update.get("source"))
        require(isinstance(update.get("supporting_sources"), list), "source-updates: supporting sources must be a list")
        for source in update["supporting_sources"]: checked_source(source)
        snapshot = update.get("historical_snapshot", {})
        require(isinstance(snapshot, dict) and snapshot.get("dataset_version") == data["dataset_version"], "source-updates: historical snapshot version mismatch")
        for field, table, binding in (("products", records, "affected_record_ids"), ("claims", claims, "affected_claim_ids")):
            ids = update.get(binding)
            require(isinstance(ids, list) and ids and len(ids) == len(set(ids)) and all(record in table and table[record]["company_id"] == company for record in ids), "source-updates: invalid affected record or claim IDs")
            target_ids = target["record_ids" if field == "products" else "claim_ids"]
            require(set(target_ids) <= set(ids), "source-updates: affected IDs omit target bindings")
            require(snapshot.get(field) == [row for row in data[field] if row["id"] in ids], "source-updates: historical snapshot differs from original records")
    if "evidence_context" in updates:
        validate_evidence_context(updates["evidence_context"], data, seen, profiles)
    return updates

def validate_relationship_assessment_context(update, data, profiles):
    """Bind the Terac scope clarification to its complete original evidence."""
    prefix = "source-updates: relationship assessment context "
    fields = {"id", "kind", "company_id", "reviewed_on", "checked_at", "review_basis", "target", "affected_claim_ids", "display_scope", "context", "relationship_context", "assessment_context", "criterion_context", "sources", "historical_snapshot"}
    require(set(update) == fields, prefix + "invalid fields")
    require(update["id"] == "terac-dialogue-assessment-scope-2026-10-17" and update["company_id"] == "terac" and update["kind"] == "relationship-assessment-scope-context", prefix + "unsupported correction")
    require(update["reviewed_on"] == "2026-10-17" and date.fromisoformat(update["reviewed_on"]) <= datetime.now(timezone.utc).date() and update["checked_at"] is None and update["review_basis"] == "retained_public_evidence", prefix + "invalid review assertion")
    claim_ids = ["terac.claim.customers-0"] + ["terac.claim.assessment-evidence-" + key for key in ("p", "c", "r")]
    require(update["target"] == {"claim_id": claim_ids[0], "customer_record_id": "terac.customer.0", "assessment_id": "terac.assessment.ai_data"} and update["affected_claim_ids"] == claim_ids and update["display_scope"] == "Market research", prefix + "invalid target or scope")
    require(isinstance(update["criterion_context"], dict) and set(update["criterion_context"]) == {"P", "C", "R"}, prefix + "invalid criterion context")
    for value in [update[key] for key in ("context", "relationship_context", "assessment_context")] + list(update["criterion_context"].values()):
        require(isinstance(value, str) and value.strip() and not re.search(r"[<>\x00-\x1f]", value), prefix + "unsafe or empty context")
    tables = {key: {row["id"]: row for row in data[key]} for key in ("claims", "sources", "assessments", "customer_evidence")}
    snapshot = update["historical_snapshot"]
    require(isinstance(snapshot, dict) and set(snapshot) == {"dataset_version", "metrics", "claims", "sources", "assessments", "customer_evidence", "profile_relationships"} and snapshot["dataset_version"] == data["dataset_version"] == "2.5.0" and snapshot["metrics"] == [], prefix + "invalid snapshot")
    source_ids = ["terac.source.terac-4", "terac.source.terac-1", "terac.source.terac-2", "terac.source.terac-7"]
    for table, ids in (("claims", claim_ids), ("sources", source_ids), ("assessments", ["terac.assessment.ai_data"]), ("customer_evidence", ["terac.customer.0"])):
        require(all(key in tables[table] for key in ids) and snapshot[table] == [tables[table][key] for key in ids], prefix + "original snapshot mismatch")
    relationship = {"name": "Dialogue", "relationship": "claimed_customer", "description": "Terac’s case study describes recruiting 25 startup founders in under four days. Contract value is undisclosed.", "record_ids": ["terac.customer.0"], "claim_ids": [claim_ids[0]]}
    matches = [row for row in (profiles or {}).get("terac", {}).get("relationships", []) if row.get("name") == "Dialogue"]
    require(matches == [relationship] and snapshot["profile_relationships"] == [{"company_id": "terac", "relationship": relationship}], prefix + "curated relationship mismatch")
    bindings = [[source_ids[0]], [source_ids[2], source_ids[0]], [source_ids[0], source_ids[1]], [source_ids[0], source_ids[3]]]
    for index, claim_id in enumerate(claim_ids):
        claim = tables["claims"][claim_id]
        require((claim["company_id"], claim["status"], claim["confidence"], claim["segment_scope"], claim["observed_on"], claim["as_of"], claim["source_ids"]) == ("terac", "supported", "B", "ai_data", "2026-10-12", "2026-05-31" if index == 0 else "2026-10-12", bindings[index]), prefix + "original claim binding mismatch")
    assessment, customer = tables["assessments"]["terac.assessment.ai_data"], tables["customer_evidence"]["terac.customer.0"]
    require(assessment["company_id"] == "terac" and assessment["segment_scope"] == "ai_data" and assessment["as_of"] == "2026-10-12" and assessment["rubric_version"] == "1.0.0" and assessment["material_conflict"] is False, prefix + "assessment mismatch")
    require(set(assessment["gates"]) == {"P", "C", "R", "O"}, prefix + "assessment gates mismatch")
    for key, level in (("P", "2"), ("C", "2"), ("R", "1"), ("O", "1")):
        gate = assessment["gates"][key]
        require(gate["level"] == level and gate["claim_ids"] == ["terac.claim.assessment-evidence-" + key.lower()], prefix + "original gate mismatch")
        if key != "O": require(gate["rationale"] == tables["claims"][gate["claim_ids"][0]]["statement"], prefix + "criterion statement mismatch")
    require((customer["company_id"], customer["claim_id"], customer["segment_scope"], customer["relationship"], customer["disclosure"], customer["paid_status"]) == ("terac", claim_ids[0], "ai_data", "claimed_customer", "company_named", "unknown"), prefix + "customer mismatch")
    refs = update["sources"]
    expected = [(source_ids[0], claim_ids[0], "https://terac.com/customers/dialogue-startup-founders", "2026-05-31", "market_research_engagement"), (source_ids[1], claim_ids[2], "https://terac.com/about", None, "separate_annotation_testimony"), (source_ids[2], claim_ids[1], "https://terac.com/blog/terac-x-berkeley-ai-hackathon", "2026-06-18", "dated_ai_workflow"), (source_ids[3], claim_ids[3], "https://terac.com/blog/zero-human-company-hackathon", "2026-08-12", "expert_payout_forecast")]
    require(isinstance(refs, list) and len(refs) == 4, prefix + "invalid source references")
    for ref, (sid, cid, url, published, role) in zip(refs, expected):
        require(ref == {"source_id": sid, "claim_id": cid, "publication_date": published, "publication_date_basis": "retained_page_text" if published else "not_established", "role": role, "access_status": "retained_readable_page"}, prefix + "source role mismatch")
        source = tables["sources"][sid]
        require((source["company_id"], source["source_type"], source["retrieval_status"], source["url"], source.get("published_on")) == ("terac", "company", "checked", url, published), prefix + "original source mismatch")

def validate_historical_offer_context(update, data):
    """Preserve Ooak's original offer records beside a dated retained-page context."""
    prefix = "source-updates: historical offer context "
    fields = {"id", "kind", "company_id", "reviewed_on", "checked_at", "review_basis", "target", "affected_claim_ids", "display_label", "display_period", "context", "sources", "retained_read", "historical_snapshot"}
    require(set(update) == fields, prefix + "invalid fields")
    require((update["id"], update["kind"], update["company_id"]) == ("ooak-data-partner-offer-context-2026-10-17", "historical-offer-source-context", "ooak"), prefix + "unsupported correction")
    require(update["reviewed_on"] == "2026-10-17" and date(2026, 10, 17) <= datetime.now(timezone.utc).date() and update["checked_at"] is None and update["review_basis"] == "retained_public_evidence", prefix + "invalid review assertion")
    metric_id, claim_id, product_id = "ooak.metric.oct14-4-data-partner-payout-cap", "ooak.claim.oct14-metric-4-data-partner-payout-cap", "ooak.product.1"
    claim_ids, source_ids = [claim_id, "ooak.claim.products-1"], ["ooak.source.oct14-5bc8f134e0b5", "ooak.source.ooak-5"]
    require(update["target"] == {"metric_id": metric_id, "claim_id": claim_id, "product_id": product_id} and update["affected_claim_ids"] == claim_ids, prefix + "invalid target")
    require(update["display_label"] == "Original data-partner offer cap" and update["display_period"] == "Original snapshot recorded 14 Oct 2026 · Source date not stated", prefix + "invalid display label")
    require(update["context"] == "Original research records from 12 and 14 October 2026 list up to $300K for company-data licensing. In a retained read from 16 October, the official partner page advertises up to $1M for the same offer. These are marketing ceilings for payment to the company, subject to a data audit; they are not individual pay rates or guaranteed payments. The change date is not established.", prefix + "unreviewed offer wording")
    for key in ("context", "display_label", "display_period"):
        value = update[key]
        require(isinstance(value, str) and value.strip() and not re.search(r"[<>\x00-\x1f]", value), prefix + "unsafe or empty text")
    retained = {"started_at": "2026-10-16 23:56:42 UTC", "completed_at": "2026-10-16 23:56:43 UTC", "raw_evidence_file": "output/reliability-20261016-2247/link-reader-1/batch-166-166-raw.json", "sha256": "1cb6464c6c50bef5794381345afefd2436cf5b87a501b9c6339ad86186b3da77", "source_publication_date": None, "change_date": None}
    require(update["retained_read"] == retained, prefix + "retained read provenance mismatch")
    snapshot = update["historical_snapshot"]
    require(isinstance(snapshot, dict) and set(snapshot) == {"dataset_version", "metrics", "claims", "sources", "products"} and snapshot["dataset_version"] == data["dataset_version"] == "2.5.0", prefix + "invalid snapshot")
    tables = {key: {row["id"]: row for row in data[key]} for key in ("metrics", "claims", "sources", "products")}
    for table, ids in (("metrics", [metric_id]), ("claims", claim_ids), ("sources", source_ids), ("products", [product_id])):
        require(all(key in tables[table] for key in ids) and snapshot[table] == [tables[table][key] for key in ids], prefix + "original snapshot mismatch")
    metric, product = tables["metrics"][metric_id], tables["products"][product_id]
    expected_metric = {"company_id": "ooak", "claim_id": claim_id, "kind": "other", "value": 300000, "qualifier": "at_most", "currency": "USD", "unit": "currency", "as_of": "undated", "segment_scope": "company", "gross_vs_net": "unspecified", "reported_vs_estimated": "reported", "observation_status": "reported", "label": "Data partner payout cap"}
    require(all(metric.get(key) == value for key, value in expected_metric.items()), prefix + "original metric binding mismatch")
    for index, cid in enumerate(claim_ids):
        claim, source = tables["claims"][cid], tables["sources"][source_ids[index]]
        require((claim["company_id"], claim["status"], claim["confidence"], claim["as_of"], claim["observed_on"], claim["segment_scope"], claim["source_ids"]) == ("ooak", "supported", "B", "undated" if index == 0 else "2026-10-12", "2026-10-14" if index == 0 else "2026-10-12", "company" if index == 0 else "ai_data", [source_ids[index]]), prefix + "original claim binding mismatch")
        require(source["company_id"] == "ooak" and source["source_type"] == "company" and source["retrieval_status"] == "checked" and source["url"] == "https://ooakdata.com/partner" and not source.get("published_on") and source["accessed_on"] == claim["observed_on"], prefix + "original source binding mismatch")
    require(product["company_id"] == "ooak" and product["claim_id"] == claim_ids[1] and product["segment_scope"] == "ai_data" and product["work_performed"] == tables["claims"][claim_ids[1]]["statement"], prefix + "original product binding mismatch")
    require(update["sources"] == [{"source_id": source_ids[0], "claim_id": claim_id, "publication_date": None, "publication_date_basis": "not_established", "role": "retained_issuer_offer", "access_status": "retained_readable_page"}], prefix + "invalid source context")

def validate_evidence_context(section, data, existing_ids=(), profiles=None):
    """Validate presentation context against complete, unchanged source records."""
    prefix = "source-updates: evidence context "
    require(isinstance(section, dict) and set(section) == {"version", "corrections"} and section["version"] == "1.0.0", prefix + "unsupported format")
    require(isinstance(section["corrections"], list) and section["corrections"], prefix + "corrections must be a nonempty list")
    tables = {key: {row["id"]: row for row in data[key]} for key in ("metrics", "claims", "sources")}
    companies = {row["id"] for row in data["companies"]}
    seen, targets = set(existing_ids), set()
    def text(value):
        return isinstance(value, str) and bool(value.strip()) and not re.search(r"[<>\x00-\x1f]", value)
    def checked_date(value):
        require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), prefix + "invalid date")
        try: return date.fromisoformat(value)
        except ValueError: raise ValidationError(prefix + "invalid date")
    for update in section["corrections"]:
        require(isinstance(update, dict), prefix + "invalid correction")
        kind = update.get("kind")
        if kind == "historical-offer-source-context":
            validate_historical_offer_context(update, data)
            binding = (kind, update["target"]["claim_id"])
            require(update["id"] not in seen and binding not in targets, prefix + "duplicate correction")
            seen.add(update["id"])
            targets.add(binding)
            continue
        if kind == "relationship-assessment-scope-context":
            validate_relationship_assessment_context(update, data, profiles)
            binding = (kind, update["target"]["claim_id"])
            require(update["id"] not in seen and binding not in targets, prefix + "duplicate correction")
            seen.add(update["id"])
            targets.add(binding)
            continue
        require(isinstance(kind, str) and kind in {"metric_reporting_context", "claim_source_supplement", "financial-basis-source-supplement"}, prefix + "unknown kind")
        basis_supplement = kind == "financial-basis-source-supplement"
        fields = {"id", "kind", "company_id", "reviewed_on", "checked_at", "review_basis", "target", "context", "sources", "historical_snapshot"}
        fields.update({"display_basis", "display_attribution"} if basis_supplement else {"display_period" if kind == "metric_reporting_context" else "access_note"})
        require(set(update) == fields, prefix + "invalid correction fields")
        require(text(update["id"]) and update["id"] not in seen, prefix + "duplicate or missing ID")
        seen.add(update["id"])
        company = update["company_id"]
        require(isinstance(company, str) and company in companies, prefix + "unknown company")
        reviewed = checked_date(update["reviewed_on"])
        require(reviewed <= datetime.now(timezone.utc).date(), prefix + "future UTC review date")
        require(update["checked_at"] is None and update["review_basis"] == "retained_public_evidence", prefix + "unsupported retrieval assertion")
        require(text(update["context"]), prefix + "context missing or invalid")
        target = update["target"]
        require(isinstance(target, dict) and set(target) == ({"metric_id", "claim_id"} if kind == "metric_reporting_context" or basis_supplement else {"claim_id"}), prefix + "invalid target")
        require(all(isinstance(value, str) for value in target.values()), prefix + "invalid target ID")
        claim = tables["claims"].get(target["claim_id"])
        require(claim is not None and claim["company_id"] == company and claim["status"] == "supported", prefix + "invalid target claim")
        binding = (kind, target["claim_id"])
        require(binding not in targets, prefix + "duplicate target")
        targets.add(binding)
        refs = update["sources"]
        require(isinstance(refs, list) and len(refs) == (1 if kind == "claim_source_supplement" else 2), prefix + "invalid source count")
        source_ids, claim_ids, publication_dates = [], {target["claim_id"]}, []
        roles = ["bound_investor_run_rate", "secondary_gross_basis_estimate"] if basis_supplement else ["bound_gross_observation", "separate_investor_corroboration"] if kind == "metric_reporting_context" else ["direct_financial_support"]
        for ref, role in zip(refs, roles):
            require(isinstance(ref, dict) and set(ref) == {"source_id", "claim_id", "publication_date", "publication_date_basis", "role", "access_status"}, prefix + "invalid source reference fields")
            require(isinstance(ref["source_id"], str) and isinstance(ref["claim_id"], str), prefix + "invalid source binding")
            source, source_claim = tables["sources"].get(ref["source_id"]), tables["claims"].get(ref["claim_id"])
            require(source is not None and source["company_id"] == company and source_claim is not None and source_claim["company_id"] == company and source_claim["status"] == "supported" and source["id"] in source_claim["source_ids"], prefix + "source/claim binding mismatch")
            require(source["id"] not in source_ids and ref["role"] == role, prefix + "invalid source role")
            source_ids.append(source["id"])
            claim_ids.add(source_claim["id"])
            url = source.get("url")
            require(isinstance(url, str) and not re.search(r"[\s\x00-\x1f]", url), prefix + "invalid source URL")
            parsed = urlsplit(url)
            require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password, prefix + "invalid source URL")
            if kind == "metric_reporting_context":
                published = checked_date(ref["publication_date"])
                require(published <= reviewed and ref["publication_date_basis"] == "retained_page_text" and ref["access_status"] == "retained_readable_page", prefix + "invalid retained publication context")
                require(not source.get("published_on") or source["published_on"] == ref["publication_date"], prefix + "publication date conflicts with source")
                publication_dates.append(published)
                require((role == "bound_gross_observation" and ref["claim_id"] == claim["id"] and source["source_type"] == "database") or (role == "separate_investor_corroboration" and ref["claim_id"] != claim["id"] and source["source_type"] == "investor"), prefix + "invalid reporting source scope")
            elif basis_supplement:
                expected = {
                    "bound_investor_run_rate": ("mercor.source.oct14-88dab2271689", "mercor.claim.oct14-major-financial-2", "investor", "https://www.felicis.com/blog/mercor-profile-organizing-human-intelligence-to-power-the-ai-economy", "2026-07-21", "retained_page_text"),
                    "secondary_gross_basis_estimate": ("mercor.source.audit-m6", "mercor.claim.major-growth_metrics-0", "independent_reporting", "https://sacra.com/c/mercor/", None, "not_established"),
                }[role]
                require((source["id"], source_claim["id"], source["source_type"], url, ref["publication_date"], ref["publication_date_basis"]) == expected and ref["access_status"] == "retained_readable_page", prefix + "basis source scope mismatch")
                require(not source.get("published_on") or source["published_on"] == ref["publication_date"], prefix + "publication date conflicts with source")
                if ref["publication_date"] is not None:
                    require(checked_date(ref["publication_date"]) <= reviewed, prefix + "future publication context")
                else:
                    require(source["id"] not in claim["source_ids"] and source_claim["id"] != claim["id"], prefix + "basis supplement must preserve separate support")
            else:
                require(ref["publication_date"] is None and ref["publication_date_basis"] == "not_established" and ref["access_status"] == "not_refetched", prefix + "unsupported supplement retrieval/date assertion")
                require(source["id"] not in claim["source_ids"] and source_claim["id"] != claim["id"], prefix + "supplement must preserve separate existing support")
        metric_ids = set()
        if kind == "metric_reporting_context" or basis_supplement:
            metric = tables["metrics"].get(target["metric_id"])
            require(metric is not None and metric["company_id"] == company and metric["claim_id"] == claim["id"] and metric["kind"] == "annualized_revenue_run_rate" and metric["gross_vs_net"] == "gross", prefix + "metric binding mismatch")
            metric_ids.add(metric["id"])
            if basis_supplement:
                require(company == "mercor" and metric["id"] == "mercor.metric.oct14-major-financial-2" and claim["id"] == "mercor.claim.oct14-major-financial-2", prefix + "unsupported basis target")
                require((metric["value"], metric["currency"], metric["unit"], metric["qualifier"], metric["as_of"], metric["segment_scope"], metric["reported_vs_estimated"], metric["observation_status"]) == (2000000000, "USD", "currency", "exact", "2026-06", "company", "reported", "reported"), prefix + "basis observation mismatch")
                require(claim["source_ids"] == ["mercor.source.oct14-88dab2271689"] and claim["as_of"] == "2026-06" and claim["segment_scope"] == "company", prefix + "basis claim mismatch")
                require(update["display_basis"] == "gross (Sacra estimate)" and update["display_attribution"] == "Felicis reports the pace; Sacra estimates the gross basis.", prefix + "invalid basis labels")
            else:
                require(all(value.strftime("%Y-%m") == publication_dates[0].strftime("%Y-%m") for value in publication_dates), prefix + "reporting dates cross months")
                require(update["display_period"] == publication_dates[0].strftime("%B %Y") + " · reported", prefix + "display period does not match reporting month")
        else:
            require(text(update["access_note"]), prefix + "access note missing or invalid")
        snapshot = update["historical_snapshot"]
        require(isinstance(snapshot, dict) and set(snapshot) == {"dataset_version", "metrics", "claims", "sources"} and snapshot["dataset_version"] == data["dataset_version"], prefix + "invalid historical snapshot")
        for table, ids in (("metrics", metric_ids), ("claims", claim_ids), ("sources", set(source_ids))):
            rows = snapshot[table]
            require(isinstance(rows, list) and len(rows) == len(ids) and all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows), prefix + "invalid historical records")
            require({row["id"] for row in rows} == ids and all(row == tables[table].get(row["id"]) for row in rows), prefix + "historical snapshot differs from original records")
    return section

def format_file_size(size):
    if size < 1000: return f"{size} B"
    unit, label = (1000000, "MB") if size >= 1000000 else (1000, "kB")
    tenths = (size * 10 + unit // 2) // unit
    return f"{tenths // 10}{'.' + str(tenths % 10) if tenths % 10 else ''} {label}"

def render_static_file_metadata(html, destination):
    for key, (filename, file_type) in STATIC_DOWNLOAD_FILES.items():
        size = format_file_size((destination / filename).stat().st_size)
        html = html.replace("{{FILE_META_" + key + "}}", file_type + " · " + size).replace("{{FILE_SIZE_" + key + "}}", size)
    return html

def validate_work_routes(work, data):
    """Check the curated sidecar without rebuilding or changing its evidence."""
    require(isinstance(work, dict) and work.get("schema_version") == "1.0.0", "work-routes: unsupported format")
    require(isinstance(work.get("source_dataset_version"), str) and work["source_dataset_version"], "work-routes: source dataset version missing")
    # This sidecar includes later reviewed overlays for the current snapshot.
    # Other selected versions and synthetic fixtures keep structural checks only.
    # The selected dataset, never sidecar metadata, controls reference checks.
    current = data["dataset_version"] == "2.5.0"
    rows = work.get("routes")
    require(isinstance(rows, list) and (rows or not current), "work-routes: reviewed routes missing")
    companies = {row["id"] for row in data["companies"]}
    claims = {row["id"] for row in data["claims"]}
    sources = {row["id"] for row in data["sources"]}
    seen, reviewed, used_claims = set(), set(), set()
    for row in rows:
        require(isinstance(row, dict), "work-routes: route must be an object")
        for field in ("id", "company_id", "role", "summary", "group", "status", "pay_label", "pay_basis", "url"):
            require(isinstance(row.get(field), str) and row[field].strip(), f"work-routes: route {field} missing")
        require(row["id"] not in seen, "work-routes: duplicate route ID")
        seen.add(row["id"])
        reviewed.add(row["company_id"])
        for field in ("claim_ids", "source_ids", "requirements"):
            require(isinstance(row.get(field), list) and all(isinstance(value, str) and value for value in row[field]), f"work-routes: invalid {field}")
        for field in ("claim_ids", "source_ids"):
            require(len(row[field]) == len(set(row[field])), f"work-routes: duplicate {field}")
        for field in ("sources", "evidence"):
            require(isinstance(row.get(field), list) and all(isinstance(value, dict) and isinstance(value.get("id"), str) and value["id"] for value in row[field]), f"work-routes: invalid {field}")
        related = row.get("related_company_ids", [])
        require(isinstance(related, list) and all(isinstance(value, str) and value for value in related), "work-routes: invalid related_company_ids")
        require(isinstance(row.get("numeric_pay"), bool), "work-routes: numeric_pay must be boolean")
        try:
            url = urlsplit(row["url"])
            url.port
            public_url = url.scheme in ("https", "http") and url.hostname and not url.username and not url.password
        except ValueError:
            public_url = False
        require(public_url and not re.search(r"[\s\x00-\x1f]", row["url"]), "work-routes: invalid route URL")
        used_claims.update(row["claim_ids"])
        if current:
            require(row["company_id"] in companies, "work-routes: unknown company reference")
            require(set(related) <= companies, "work-routes: unknown related company reference")
            require(set(row["claim_ids"]) <= claims, "work-routes: unknown claim reference")
            # Inline source records may include separately reviewed entry points.
            # source_ids still identifies the canonical research references.
            require(set(row["source_ids"]) <= sources, "work-routes: unknown source reference")
            # Some reviewed routes intentionally cite another company's claim.
            require({entry["id"] for entry in row["evidence"]} <= claims, "work-routes: unknown evidence reference")
    coverage = work.get("coverage")
    require(isinstance(coverage, dict) and coverage.get("route_count") == len(rows), "work-routes: route coverage count mismatch")
    require(coverage.get("organizations_with_reviewed_routes") == len(reviewed), "work-routes: organization coverage count mismatch")
    require(coverage.get("canonical_work_claims_preserved") == len(used_claims), "work-routes: claim coverage count mismatch")
    if current:
        require(reviewed == companies and coverage.get("organizations_total") == len(companies), "work-routes: current dataset company coverage incomplete")
    return work


def load_work_routes(path, data):
    require(path.is_file(), "work-routes: required curated data/work-routes.json is missing")
    try:
        work = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError("work-routes: curated data/work-routes.json is not readable JSON") from error
    return validate_work_routes(work, data)


def build(data, destination):
    validate(data)
    work_path = ROOT / "data/work-routes.json"
    work_data = load_work_routes(work_path, data)
    destination.mkdir(parents=True, exist_ok=True)
    blob = canonical_bytes(data)
    (destination / "research.json").write_bytes(blob)
    create_database(destination / "observatory.sqlite", data)
    for name, spec in TABLES.items(): write_csv(destination / f"{name}.csv", data[name], list(spec["properties"]))
    classification_rows = [{"company_id": c["id"], "company": c["name"], "segment_scope": segment, "stage": classify(data, c["id"], segment), "confidence": stage_confidence(data, c["id"], segment), "rubric_version": data["rubric"]["version"], "as_of": data["meta"]["as_of"]} for c in data["companies"] for segment in ("ai_data", "company", "research", "other_segment")]
    write_csv(destination / "classifications.csv", classification_rows, ["company_id", "company", "segment_scope", "stage", "confidence", "rubric_version", "as_of"])
    # JSON is inert and HTML-sensitive characters are escaped before embedding.
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    html = (ROOT / "web/index.html").read_text().replace("/* OBSERVATORY_CSS */", (ROOT / "web/style.css").read_text()).replace("/* OBSERVATORY_JS */", (ROOT / "web/link-health.js").read_text() + "\n" + (ROOT / "web/app.js").read_text()).replace("<!-- OBSERVATORY_DATA -->", embedded)
    editorial = json.loads((ROOT / "data/editorial.json").read_text())
    logo_path = ROOT / "data/logo-provenance.json"
    logo_data = json.loads(logo_path.read_text()) if logo_path.exists() else {"logos": []}
    link_health_path = ROOT / "data/link-health.json"
    link_health = validate_link_health(json.loads(link_health_path.read_text()) if link_health_path.exists() else {"version": "1.0.0", "entries": []})
    events_path = ROOT / "data/company-events.json"
    company_events = load_company_events(events_path, data)
    profile_content = json.loads((ROOT / "data/profile-content.json").read_text())
    afterquery_content = ROOT / "data/profile-afterquery.json"
    if afterquery_content.exists():
        entry = json.loads(afterquery_content.read_text())
        profile_content["entries"] = [e for e in profile_content["entries"] if e["company_id"] != "afterquery"] + [entry]
    source_updates_path = ROOT / "data/source-updates.json"
    source_updates = json.loads(source_updates_path.read_text())
    # The actual dataset selects validation; sidecar metadata cannot disable it.
    # Other datasets, including the pipeline fixtures, receive no replacements.
    source_updates = validate_source_updates(source_updates, data, profile_content) if data["dataset_version"] == "2.5.0" else None
    injected = "window.EDITORIAL=" + json.dumps(editorial) + ";window.RESEARCH_ALIASES=" + (ROOT / "docs/research-id-crosswalk.json").read_text() + ";window.LOGOS=" + json.dumps(logo_data) + ";window.WORK_ROUTES=" + json.dumps(work_data) + ";window.PROFILE_CONTENT=" + json.dumps(profile_content) + ";window.LINK_HEALTH=" + json.dumps(link_health) + ";window.COMPANY_EVENTS=" + json.dumps(company_events) + ";"
    injected += "window.SOURCE_UPDATES=" + json.dumps(source_updates) + ";"
    html = html.replace("/* EDITORIAL_DATA */", injected.replace("<", "\\u003c").replace(">", "\\u003e"))
    html = html.replace("/* REDESIGN_CSS */", (ROOT / "web/profiles-v2.css").read_text() + (ROOT / "web/work-v4.css").read_text() + (ROOT / "web/investor.css").read_text() + (ROOT / "web/edition.css").read_text())
    html = html.replace("/* ICONS_CSS */", (ROOT / "web/icons.css").read_text())
    html = html.replace("/* ICONS_JS */", (ROOT / "web/icons.js").read_text())
    html = html.replace("/* EDITORIAL_JS */", (ROOT / "web/editorial.js").read_text())
    work_js = ROOT / "web/work-v3.js"
    html = html.replace("/* WORK_V3_JS */", (work_js.read_text() if work_js.exists() else "") + (ROOT / "web/work-v4.js").read_text() + (ROOT / "web/profiles-v2.js").read_text() + (ROOT / "web/source-updates.js").read_text())
    import shutil
    assets = ROOT / "web/assets"
    if assets.exists(): shutil.copytree(assets, destination / "assets", dirs_exist_ok=True)
    for name in ("robots.txt", "sitemap.xml", "404.html", "_headers", "_redirects", "favicon.ico"):
        shutil.copy2(ROOT / "web" / name, destination / name)
    for source in [ROOT / "data/editorial.json", ROOT / "data/portrait-provenance.json", ROOT / "data/investor-image-provenance.json", logo_path, work_path, link_health_path, events_path, source_updates_path]:
        if source.exists(): shutil.copy2(source, destination / source.name)
    (destination / "profile-content.json").write_text(json.dumps(profile_content, indent=2, ensure_ascii=False) + "\n")
    html = html.replace("{{COMPANY_COUNT}}", str(len(data["companies"]))).replace("{{SOURCE_COUNT}}", str(len(data["sources"]))).replace("{{GROUP_COUNT}}", str(len({e["primary_offering"] for e in editorial["entries"]})))
    html = render_snapshot_metadata(html, data)
    html = render_static_file_metadata(html, destination)
    (destination / "index.html").write_text(html)
    from static_pages import write_static_pages; write_static_pages(data, destination, work_data, profile_content, editorial, company_events)
    files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    (destination / "manifest.json").write_text(json.dumps({"dataset_version": data["dataset_version"], "schema_version": data["schema_version"], "sha256": files}, indent=2) + "\n")

def release(input_path, root=ROOT):
    data = json.loads(input_path.read_text())
    validate(data)
    for raw in data["raw_inputs"]:
        path = root / raw["path"]
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == raw["sha256"], f"raw research file missing or checksum mismatch: {raw['path']}")
    blob = canonical_bytes(data)
    version = root / "data/versions" / f"{data['dataset_version']}.json"
    require(not version.exists() or version.read_bytes() == blob, "immutable dataset version already exists with different bytes; increment dataset_version")
    root.mkdir(parents=True, exist_ok=True)
    # No committed output changes until validation and every export succeed.
    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as temp:
        build(data, Path(temp))
        dist = root / "dist"
        if dist.exists():
            old = root / ".dist-previous"
            require(not old.exists(), "previous interrupted build exists; inspect .dist-previous before retry")
            dist.rename(old)
            try: Path(temp).rename(dist)
            except BaseException:
                old.rename(dist)
                raise
            shutil.rmtree(old)
        else: Path(temp).rename(dist)
    version.parent.mkdir(parents=True, exist_ok=True)
    version.write_bytes(blob)
    (root / "data/canonical.json").write_bytes(blob)
    return {"version": data["dataset_version"], "companies": len(data["companies"]), "claims": len(data["claims"]), "sources": len(data["sources"]), "sha256": hashlib.sha256(blob).hexdigest(), "output": str(root / "dist")}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "build", "import"])
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "data/canonical.json")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            data = json.loads(args.input.read_text())
            validate(data)
            print(json.dumps({"valid": True, "version": data["dataset_version"], "companies": len(data["companies"])}))
        else: print(json.dumps(release(args.input), indent=2))
    except (ValidationError, ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Import rejected: {exc}\n")

if __name__ == "__main__": main()
