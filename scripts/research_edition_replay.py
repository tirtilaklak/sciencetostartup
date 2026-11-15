"""Public, source-selected historical edition replay (never fresh approval).

The original private graph is an opaque commitment. Its admitted audit and
synthesis receipts are retained, not reminted against a projected graph. Only a
committed prepared-package selection plus an actual production receipt permits
this separate, versioned reader. No package Python is executed, no input is
fetched, and no archive member is regenerated.
"""
from __future__ import annotations

import copy
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qsl, unquote, urlsplit
import zipfile
from zoneinfo import ZoneInfo

import research_citations as citations

VERSION = "published-edition-replay-v1"
MARKER = "published_edition_replay"
SOURCE_SELECTOR = "data/research/published-source.json"
SOURCE_VERSION = "published-research-source-v1"
SOURCE_MARKER = "published_source_selection"
SOURCE_LEDGER = "public_edition_ledger"
HASH = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
PIN_FIELDS = {"context_contract_version", "context_sha256", "manifest_sha256", "archive_sha256"}
DESCRIPTOR_FIELDS = {"schema_version", "release_id", "package_path", "archive_receipt", *PIN_FIELDS}
REGISTRY_FIELDS = {"release_id", "path", *PIN_FIELDS}
PACIFIC = ZoneInfo("America/Los_Angeles")
# Frozen contracts 4–6 expose only these generated public payloads and their
# versioned owned reproduction inputs. A checksum is not a public-file policy.
PUBLIC_PAYLOADS = {"clean-dataset.json", "clean-dataset.csv", "clean-dataset.sqlite",
    "source-context.json", "metadata.json", "report.md", "report.html", "report.pdf",
    "evidence.html", "corrections.json", "readiness.json", "source-manifest.json",
    "METHODS.md", "README.md", "zenodo-metadata.json", "huggingface-README.md",
    "citation.bib", "citation.ris", "citation.csl.json", "CITATION.cff",
    "executive-brief.html", "executive-brief.md"}


def _hash(blob):
    return hashlib.sha256(blob).hexdigest()


def _json(blob):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate frozen JSON field")
            value[key] = item
        return value
    def finite(value):
        raise ValueError("Nonfinite frozen JSON number: " + value)
    try:
        return json.loads(blob, object_pairs_hook=pairs, parse_constant=finite)
    except (TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid frozen JSON") from error


def _path(root, relative):
    """Source-owned paths only; inspect each component before resolving it."""
    root = Path(root).absolute()
    if (root.is_symlink() or not isinstance(relative, str) or not relative
            or relative != Path(relative).as_posix() or "\\" in relative
            or Path(relative).is_absolute() or any(p in {".", ".."} for p in relative.split("/"))):
        raise ValueError("Unsafe replay source path")
    path = root
    for component in relative.split("/"):
        path = path / component
        if path.is_symlink():
            raise ValueError("Replay source path cannot contain symlinks")
    return path


def _pins(entry):
    if (type(entry.get("context_contract_version")) is not int
            or entry["context_contract_version"] not in {4, 5, 6}
            or any(not isinstance(entry.get(k), str) or not HASH.fullmatch(entry[k])
                   for k in PIN_FIELDS - {"context_contract_version"})):
        raise ValueError("Replay requires exact pins and an audit-capable frozen contract")
    return {key: entry[key] for key in PIN_FIELDS}


def _selection(root, release_id):
    """The caller cannot nominate a bundle or invent a cached ready result."""
    if not isinstance(release_id, str) or not TOKEN.fullmatch(release_id):
        raise ValueError("Unsafe replay release identifier")
    path = _path(root, citations.PREPARED_REGISTRY)
    if not path.is_file():
        raise ValueError("Historical replay requires the committed prepared-package registry")
    registry = _json(path.read_bytes())
    if (not isinstance(registry, dict) or set(registry) != {"schema_version", "packages"}
            or type(registry["schema_version"]) is not int or registry["schema_version"] != 1
            or not isinstance(registry["packages"], list)):
        raise ValueError("Invalid replay prepared-package registry")
    selected, seen = None, set()
    for entry in registry["packages"]:
        if not isinstance(entry, dict) or set(entry) != REGISTRY_FIELDS:
            raise ValueError("Invalid replay registry entry")
        rid = entry["release_id"]
        if not isinstance(rid, str) or not TOKEN.fullmatch(rid) or rid in seen:
            raise ValueError("Unsafe or duplicate replay registry release")
        seen.add(rid)
        # Legacy prepared selections remain legal registry entries. They gain
        # no new publication authority through this reader.
        citations._contract_version(entry["context_contract_version"])
        if any(not isinstance(entry.get(k), str) or not HASH.fullmatch(entry[k])
               for k in PIN_FIELDS - {"context_contract_version"}):
            raise ValueError("Replay registry requires exact SHA-256 pins")
        if entry["path"] not in {f"data/research/releases/{rid}", f"data/research/releases/{rid}/publication"}:
            raise ValueError("Replay registry path must name its own release directory")
        _path(root, entry["path"])
        if rid == release_id:
            _pins(entry)
            selected = entry
    if selected is None:
        raise ValueError("Historical release is not source-selected")
    return selected


def _public(value):
    if citations.privacy_filter(value) != value:
        raise ValueError("Replay contains private fields or local paths")
    # Unlike the audit's known-channel metadata, replay includes scientific
    # prose and serialized JSON. Recognize filesystem syntax, not taxonomy
    # separators, metric identifiers or JSON/TeX backslash escapes.
    http_url = re.compile(r"https?://[^\s<>\"']+", re.I)
    local_path = re.compile(
        r"file://|(?<![\w/])/+(?:Users|home|private|tmp|var/folders)/"
        r"|(?<![\w])[A-Za-z]:[\\/]"
        r"|(?<!\\)\\\\(?:[?.]\\|[^\s\\/:*?\"<>|{}\[\](),;=&]+[\\/][^\s\\/:*?\"<>|{}\[\](),;=&]+)", re.I)
    def safe_string(text):
        decoded = unquote(text)
        if (re.search(r"file://", decoded, re.I)
                or local_path.search(http_url.sub("", decoded))
                or citations.EMAIL.search(decoded) or citations.SECRET.search(decoded)
                or re.search(r"(?:^|\s)Bearer\s+\S+", decoded, re.I)):
            return True
        for match in http_url.finditer(decoded):
            try:
                url = urlsplit(match.group())
            except ValueError:
                return True
            if url.username or url.password or any(key.lower() in {
                    "token", "access_token", "secret", "api_key", "api-key", "signature", "password"}
                    for key, _ in parse_qsl(url.query, keep_blank_values=True)):
                return True
        return False
    forbidden = re.compile(r"(?:^|_)(?:authorization|password|passwd|cookie|private_key|access_key)(?:$|_)", re.I)
    public_authorization_paths = {("policy", "initial_launch_authorization"),
                                  ("policy", "initial_launch_authorization", "authorization_id")}
    def inspect(item, path=()):
        if isinstance(item, dict):
            if any(forbidden.search(key) and path + (key,) not in public_authorization_paths for key in item):
                raise ValueError("Replay contains credential metadata")
            for key, child in item.items():
                if safe_string(key):
                    raise ValueError("Replay contains an unsafe dynamic field name")
                inspect(child, path + (key,))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                inspect(child, path + (index,))
        elif isinstance(item, str):
            # Parse raw JSON first: percent-encoded quotes inside a valid JSON
            # string must not corrupt its transport before decoding the leaves.
            candidates = (item, unquote(item)) if unquote(item) != item else (item,)
            for candidate in candidates:
                if not candidate.lstrip().startswith(("{", "[", '"')):
                    continue
                try:
                    embedded = _json(candidate)
                except ValueError as error:
                    if str(error) != "Invalid frozen JSON":
                        raise
                else:
                    if isinstance(embedded, (dict, list, str)):
                        if citations.privacy_filter(embedded) != embedded:
                            raise ValueError("Replay contains private fields in embedded JSON")
                        inspect(embedded, path + ("<embedded-json>",))
                        return
            if safe_string(item):
                raise ValueError("Replay contains private paths, contact data or credentials")
    inspect(value)


def _timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Replay requires an aware actual timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Replay requires an aware actual timestamp") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Replay requires an aware actual timestamp")
    return result.astimezone(timezone.utc)


def _bundle(root, descriptor):
    selected = _selection(root, descriptor["release_id"])
    if descriptor["package_path"] != selected["path"] or _pins(descriptor) != _pins(selected):
        raise ValueError("Replay descriptor differs from committed package pins")
    package = _path(root, selected["path"])
    if not package.is_dir():
        raise ValueError("Missing source-selected replay package")
    def read(name):
        if not isinstance(name, str) or not TOKEN.fullmatch(name):
            raise ValueError("Unsafe frozen package member")
        path = package / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe frozen package member: " + name)
        return path.read_bytes()
    contract_blob, manifest_blob = read("PREPARED.json"), read("MANIFEST.json")
    contract, manifest = _json(contract_blob), _json(manifest_blob)
    if (not isinstance(contract, dict) or not isinstance(manifest, dict)
            or set(contract) != {"schema_version", "release_id", *PIN_FIELDS, "archive_bytes", "pdf_sha256", "pdf_bytes"}
            or set(manifest) != {"schema_version", "release_id", "context_contract_version", "context_sha256", "files"}
            or type(contract.get("schema_version")) is not int or contract["schema_version"] != 1
            or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or contract.get("release_id") != selected["release_id"]
            or manifest.get("release_id") != selected["release_id"]
            or _pins(contract) != _pins(selected)
            or manifest.get("context_contract_version") != selected["context_contract_version"]
            or manifest.get("context_sha256") != selected["context_sha256"]
            or _hash(manifest_blob) != selected["manifest_sha256"]
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError("Replay contract or manifest differs from source-selected pins")
    if manifest_blob != citations.json_bytes(manifest):
        raise ValueError("Noncanonical frozen manifest")
    files = {"MANIFEST.json": manifest_blob}
    allowed = PUBLIC_PAYLOADS | set(citations._reproduction_inputs(selected["context_contract_version"]))
    if not set(manifest["files"]) <= allowed:
        raise ValueError("Frozen replay contains a member outside the public artifact allowlist")
    forbidden = {"PREPARED.json", "MANIFEST.json", "research-archive.zip", *citations.LIVE_PACKAGE_FILES}
    for name, pin in manifest["files"].items():
        if (name in forbidden or not isinstance(pin, dict) or set(pin) != {"sha256", "bytes"}
                or not isinstance(pin["sha256"], str) or not HASH.fullmatch(pin["sha256"])
                or type(pin["bytes"]) is not int or pin["bytes"] < 0):
            raise ValueError("Invalid frozen manifest member descriptor")
        blob = read(name)
        if _hash(blob) != pin["sha256"] or len(blob) != pin["bytes"]:
            raise ValueError("Frozen package checksum mismatch: " + name)
        files[name] = blob
    expected = set(files) | {"PREPARED.json", "research-archive.zip"}
    if any(p.name not in expected | citations.LIVE_PACKAGE_FILES or p.is_symlink() or not p.is_file()
           for p in package.iterdir()):
        raise ValueError("Unexpected or unsafe frozen package inventory")
    archive = read("research-archive.zip")
    if (_hash(archive) != selected["archive_sha256"] or len(archive) != contract.get("archive_bytes")
            or descriptor["archive_receipt"].get("artifact_sha256") != selected["archive_sha256"]):
        raise ValueError("Frozen archive differs from its pins or publication receipt")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if len(zipped.namelist()) != len(files) or set(zipped.namelist()) != set(files):
            raise ValueError("Frozen archive members differ from manifest")
        for name, blob in files.items():
            info = zipped.getinfo(name)
            if (info.compress_type not in citations.ARCHIVE_COMPRESSION.values()
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                    or info.file_size != len(blob) or zipped.read(name) != blob):
                raise ValueError("Frozen archive member differs from public bytes")
    if not files.get("report.pdf") or (contract.get("pdf_sha256") != _hash(files["report.pdf"])
            or contract.get("pdf_bytes") != len(files["report.pdf"])):
        raise ValueError("Published replay requires its exact prepared PDF")
    source = _json(files.get("source-context.json"))
    if (not isinstance(source, dict) or _hash(files["source-context.json"]) != selected["context_sha256"]
            or files["source-context.json"] != citations._context_json_bytes(source, selected["context_contract_version"])):
        raise ValueError("Frozen source context bytes are not canonical or do not match")
    recipe = source.get("package_context")
    version = selected["context_contract_version"]
    fields = {"context_contract_version", "graph_projection", "reproduction_inputs"}
    if version >= 5:
        fields.add("graph_projection_version")
    if (not isinstance(recipe, dict) or set(recipe) != fields
            or recipe["context_contract_version"] != version
            or recipe["graph_projection"] != ("approved-historical-report-v2" if version >= 5 else "approved-historical-report-v1")
            or (version >= 5 and recipe["graph_projection_version"] != "1.2.0")
            or not isinstance(recipe["reproduction_inputs"], dict)
            or set(recipe["reproduction_inputs"]) != set(citations._reproduction_inputs(version))):
        raise ValueError("Replay owned recipe differs from its versioned allowlist")
    for name, pin in recipe["reproduction_inputs"].items():
        if pin != manifest["files"].get(name):
            raise ValueError("Replay owned recipe pin differs from manifest")
    frozen_projection_version = citations._frozen_graph_projection_version(files)
    if ((version >= 5 and frozen_projection_version != recipe["graph_projection_version"])
            or (version == 4 and frozen_projection_version not in {"1.0.0", "1.1.0"})):
        raise ValueError("Replay graph projection differs from its pinned owned recipe")
    projection = _json(files.get("clean-dataset.json"))
    if (not isinstance(projection, dict) or projection.get("graph") != source.get("graph")
            or files["clean-dataset.json"] != citations.json_bytes(projection)):
        raise ValueError("Frozen public graph differs from its source context")
    from reproduce_research_package import from_rows
    rows = list(csv.reader(io.StringIO(files["clean-dataset.csv"].decode("utf-8"))))
    if not rows or rows[0] != ["collection", "position", "kind", "value_json"] or from_rows(rows[1:]) != projection:
        raise ValueError("Frozen JSON and CSV public payloads disagree")
    database_path = (package / "clean-dataset.sqlite").resolve()
    with sqlite3.connect(database_path.as_uri() + "?mode=ro&immutable=1", uri=True) as database:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Frozen SQLite integrity check failed")
        rows = database.execute("SELECT collection,position,kind,value_json FROM projection_rows ORDER BY collection,position").fetchall()
    if from_rows(rows) != projection:
        raise ValueError("Frozen JSON and SQLite public payloads disagree")
    return package, source, projection, {**files, "PREPARED.json": contract_blob, "research-archive.zip": archive}


def _research(package, source, projection, receipt):
    """Authenticate frozen acceptance and public facts, without pretending to
    rerun full private-input screening or the original synthesis review."""
    from research_graph import validate_graph, coverage_summary
    from research_report import FLOORS, canonical_hash, report_review_digest, _validate_report, _launch_content
    from research_findings import paragraph_supported, executive_findings
    from reproduce_research_package import verify_frozen_audits

    for key in ("graph", "report", "gate", "policy", "identity", "input_commitments"):
        if not isinstance(source.get(key), dict):
            raise ValueError("Frozen replay lacks its complete source context")
    _public(source)
    graph, report, gate, policy = (source[k] for k in ("graph", "report", "gate", "policy"))
    commitments = source["input_commitments"]
    if (set(commitments) != {"graph_sha256", "report_input_sha256", "corrections_input_sha256"}
            or any(not isinstance(v, str) or not HASH.fullmatch(v) for v in commitments.values())):
        raise ValueError("Frozen replay lacks opaque original input commitments")
    if (gate.get("archival_ready") is not True or gate.get("report_review_ready") is not True
            or gate.get("reasons") != [] or source.get("publication_withholds") != {"paragraphs": 0, "executive_findings": 0}):
        raise ValueError("Frozen research acceptance has holds or publication withholds")
    validate_graph(graph)
    validation_report = {**report, "status": "prepared", "editions": []}
    if _validate_report(validation_report, graph) or _launch_content(validation_report, graph):
        raise ValueError("Frozen public graph or substantive report is invalid")
    if any(a.get("status") not in {"approved", "historical"} for a in graph["assertions"]):
        raise ValueError("Unapproved or formerly withheld assertion in public replay")
    coverage = coverage_summary(graph)
    for key, floor in FLOORS.items():
        threshold = policy.get("launch_floors", {}).get(key, floor)
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or threshold < floor or gate.get("thresholds", {}).get(key) != threshold):
            raise ValueError("Frozen replay cannot lower an acceptance floor")
    for key in ("legacy_inclusion_audits", "qualifying_suppliers", "reviewed_papers", "dataset_families", "benchmark_families", "core_disposition_rate"):
        if coverage[key] < gate["thresholds"][key] or coverage[key] != gate.get("coverage", {}).get(key):
            raise ValueError("Frozen public coverage differs from admitted acceptance")
    if any(policy.get(key, True) is not True for key in ("reference_audit_required", "screening_audit_required", "archive_required")):
        raise ValueError("Frozen replay cannot disable a required gate")
    frozen = graph.get("coverage", {}).get("frozen_core", {})
    if not frozen.get("entity_ids") or not frozen.get("frozen_on") or not frozen.get("source_cutoff"):
        raise ValueError("Frozen replay lacks the original coverage denominator")
    cutoff = _timestamp(report.get("source_cutoff"))
    if cutoff > _timestamp(graph.get("as_of")):
        raise ValueError("Frozen cutoff exceeds the actual evidence snapshot")
    sources = {row["id"]: row for row in graph["sources"]}
    for assertion in graph["assertions"]:
        if assertion["status"] == "approved":
            for evidence in assertion["evidence"]:
                if _timestamp(sources[evidence["source_id"]]["captured_on"]) > cutoff:
                    raise ValueError("Frozen approved source exceeds the original cutoff")
    if any(not paragraph_supported(source, p) for s in report.get("sections", []) for p in s.get("paragraphs", [])) or executive_findings(source)[1]:
        raise ValueError("Frozen report exposes unsupported research")
    edition_route_date(source, receipt)
    audits = verify_frozen_audits(package, projection)
    if any(audits.get("audits", {}).get(kind, {}).get("status") != "admitted_frozen_receipt_verified" for kind in ("reference", "screening")):
        raise ValueError("Both actual frozen audit admissions are required")
    parsed = {}
    for kind in ("reference", "screening"):
        entry = policy["audit_inputs"][kind]
        audit, validation = _json(entry["audit_json"]), _json(entry["validation_receipt_json"])
        if audit != policy.get("audits", {}).get(kind):
            raise ValueError("Frozen parsed audit differs from exact admitted bytes")
        parsed[kind] = audit
        if kind == "screening" and validation.get("graph_sha256") != audit.get("graph_sha256"):
            raise ValueError("Frozen screening receipt retargets the original graph")
    original_graph = parsed["screening"].get("graph_sha256")
    if not isinstance(original_graph, str) or not HASH.fullmatch(original_graph):
        raise ValueError("Frozen screening lacks the original scientific graph")
    # Reference methods authenticate their original SUT input/output and retain
    # selected-record applicability. Later approved additions may legitimately
    # change the final graph, so those earlier whole-graph identities must not
    # be equated with the final screening/synthesis commitment.
    reference_method = parsed["reference"].get("method", {})
    reference_commitments = {key: reference_method.get(key) for key in (
        "input_graph_sha256", "input_graph_bytes_sha256", "output_graph_sha256")}
    if any(not isinstance(value, str) or not HASH.fullmatch(value)
           for value in reference_commitments.values()):
        raise ValueError("Frozen reference lacks its original SUT input/output commitments")
    reference_runs = {r.get("invocation_id") for r in parsed["reference"].get("runs", []) if r.get("role") == "sut"}
    screening_runs = {r.get("invocation_id") for r in parsed["screening"].get("runs", []) if r.get("role") == "sut"}
    if not reference_runs or not screening_runs or reference_runs & screening_runs:
        raise ValueError("Frozen audits require separate actual SUT executions")
    expected_report = report_review_digest(report)
    accepted = []
    latest = max((_timestamp(r["reviewed_on"]) for r in graph["reviews"]), default=cutoff)
    for review in policy.get("report_reviews", []):
        if (isinstance(review, dict) and review.get("fixture") is False and review.get("decision") == "pass"
                and review.get("method") == "report_content_review" and review.get("reviewer_type") in {"ai", "human"}
                and review.get("reviewer") and review.get("invocation_id")
                and review.get("graph_sha256") == original_graph and review.get("report_sha256") == expected_report
                and _timestamp(review.get("reviewed_on")) >= latest and review.get("role") in {"evidence_auditor", "adversarial"}):
            accepted.append(review)
    if report.get("executive_findings") and ({r["role"] for r in accepted} != {"evidence_auditor", "adversarial"}
            or len({r["invocation_id"] for r in accepted}) < 2):
        raise ValueError("Frozen synthesis lacks original exact separate reviews")
    # Validate the old report commitment without its publication lifecycle.
    if _hash(citations.json_bytes(report)) != commitments["report_input_sha256"]:
        raise ValueError("Frozen readable report differs from its original authoring commitment")
    return audits, original_graph, reference_commitments


def edition_route_date(source, receipt):
    """The one authorized launch retains its date; subsequent issues use Mondays."""
    report, policy, graph = source["report"], source["policy"], source["graph"]
    edition = report.get("edition_date")
    try:
        day = date.fromisoformat(edition)
    except (TypeError, ValueError) as error:
        raise ValueError("Frozen edition requires its actual edition date") from error
    cutoff, confirmed = _timestamp(report["source_cutoff"]), _timestamp(receipt["confirmed_on"])
    if report.get("edition_kind", "weekly") == "launch":
        authorization = policy.get("initial_launch_authorization", {})
        if not isinstance(authorization, dict) or set(authorization) != {
                "authorization_id", "one_time", "release_id", "source_cutoff", "recorded_on",
                "imported_on", "provenance", "recorded_in_commit", "recording_path"}:
            raise ValueError("Frozen launch authorization has unknown fields or lacks its exact provenance")
        recorded = _timestamp(authorization.get("recorded_on"))
        imported = _timestamp(authorization.get("imported_on"))
        if (authorization.get("authorization_id") != "user-2026-11-11-initial-launch-as-ready"
                or authorization.get("one_time") is not True or authorization.get("release_id") != report["release_id"]
                or _timestamp(authorization.get("source_cutoff")) != cutoff
                or not isinstance(authorization.get("recorded_in_commit"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", authorization["recorded_in_commit"])
                or authorization.get("recording_path") != "docs/research/CONTRACT.md"
                or not isinstance(authorization.get("provenance"), str) or not authorization["provenance"].strip()
                or recorded.astimezone(PACIFIC).date() < date(2026, 11, 11)
                or imported < recorded or confirmed < imported
                or recorded > _timestamp(graph["as_of"]) or confirmed < recorded or confirmed < cutoff):
            raise ValueError("Frozen launch lacks its exact one-time authorization")
    elif report.get("edition_kind", "weekly") == "weekly":
        local = cutoff.astimezone(PACIFIC)
        publication = datetime.combine(day, datetime.min.time().replace(hour=9), PACIFIC)
        if (day.weekday() != 0 or local.date() != day - timedelta(days=3)
                or (local.hour, local.minute, local.second, local.microsecond) != (17, 0, 0, 0)
                or confirmed < publication):
            raise ValueError("Frozen weekly edition violates its original Monday window")
    else:
        raise ValueError("Unknown frozen edition kind")
    if report["release_id"] != receipt["release_id"]:
        raise ValueError("Frozen edition release differs from its publication receipt")
    return edition


def _verify(root, descriptor):
    if not isinstance(descriptor, dict) or set(descriptor) != DESCRIPTOR_FIELDS or descriptor.get("schema_version") != VERSION:
        raise ValueError("Invalid versioned published-edition descriptor")
    _public(descriptor)
    receipt = descriptor["archive_receipt"]
    if (not isinstance(receipt, dict) or not citations.published_archive({"report": {
            "release_id": descriptor["release_id"], "archive": receipt}})):
        raise ValueError("Historical replay requires an actual anonymously verified production receipt")
    package, source, projection, files = _bundle(root, descriptor)
    if source.get("report", {}).get("release_id") != descriptor["release_id"]:
        raise ValueError("Frozen report release differs from the descriptor")
    if receipt.get("edition_date") is not None and receipt["edition_date"] != source["report"].get("edition_date"):
        raise ValueError("Published receipt changes the frozen edition date")
    reservation = source["report"].get("archive", {})
    for key in citations.RESERVATION_FIELDS:
        if reservation.get(key) is not None and receipt.get(key) != reservation[key]:
            raise ValueError("Published receipt changes the frozen reservation")
    if type(receipt.get("deposition_id")) is not int or receipt["deposition_id"] <= 0:
        raise ValueError("Production receipt must retain its typed deposition identity")
    audits, original_graph, reference_commitments = _research(package, source, projection, receipt)
    snapshot = copy.deepcopy({key: source[key] for key in ("graph", "report", "policy", "identity", "roles", "corrections") if key in source})
    snapshot["report"].update(status="published", archive=copy.deepcopy(receipt), editions=[])
    snapshot["policy"]["mode"] = "replay_only"
    snapshot["gate"] = {**copy.deepcopy(source["gate"]), "ready": True, "status": "published_frozen_replay",
        "archival_ready": False, "archive_reasons": [], "reasons": [], "verification_scope": VERSION}
    snapshot[MARKER] = copy.deepcopy(descriptor)
    snapshot["replay_verification"] = {"schema_version": VERSION, "input_commitments": copy.deepcopy(source["input_commitments"]),
        "original_scientific_graph_sha256": original_graph, "original_reference_commitments": reference_commitments,
        "audit_verification": audits,
        "current_input_readiness_revalidated": False, "raw_sources_revalidated": False,
        "live_private_withheld_records_revalidated": False}
    snapshot["root"] = Path(root)
    snapshot["prepared_package"] = str(package.absolute())
    return snapshot, files


def load_published_edition(root, descriptor):
    """Hydrate a verified frozen public context, after current inputs change."""
    return _verify(root, descriptor)[0]


def read_replay_package(context, package=None):
    """Reverify selection and compare hydrated facts before copying old bytes."""
    descriptor = context.get(MARKER)
    if package is not None and (not isinstance(descriptor, dict) or Path(package).resolve() !=
                                _path(context.get("root", citations.ROOT), descriptor.get("package_path")).resolve()):
        raise ValueError("Replay caller cannot select another frozen package")
    expected, files = _verify(context.get("root", citations.ROOT), descriptor)
    for key in ("graph", "report", "policy", "identity", "roles", "corrections", "gate", "replay_verification", "prepared_package"):
        if context.get(key) != expected.get(key):
            raise ValueError("Hydrated historical context was changed: " + key)
    return files


def resolve_edition_entry(root, entry):
    """Read a source ledger descriptor; the ledger binds its exact public bytes."""
    relative = entry.get("snapshot_path")
    if not isinstance(relative, str) or not relative.startswith("editions/"):
        raise ValueError("Replay descriptor must be under data/research/editions")
    path = _path(root, "data/research/" + relative)
    if not path.is_file():
        raise ValueError("Missing immutable published edition descriptor")
    blob = path.read_bytes()
    if _hash(blob) != entry.get("snapshot_sha256"):
        raise ValueError("Immutable published edition descriptor digest differs")
    descriptor = _json(blob)
    if descriptor.get("release_id") != entry.get("release_id"):
        raise ValueError("Published edition ledger retargets its frozen release")
    return load_published_edition(root, descriptor)


def load_published_source(root):
    """Select the current public edition and its immutable public history.

    Absence preserves private authoring mode. A present selector never falls
    back to private inputs, and has no authority beyond verified publication
    descriptors and the committed prepared-package registry.
    """
    path = _path(root, SOURCE_SELECTOR)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("Published source selector must be a regular JSON file")
    blob = path.read_bytes()
    source = _json(blob)
    if (not isinstance(source, dict)
            or set(source) != {"schema_version", "current_release_id", "editions"}
            or source["schema_version"] != SOURCE_VERSION
            or not isinstance(source["current_release_id"], str)
            or not TOKEN.fullmatch(source["current_release_id"])
            or not isinstance(source["editions"], list) or not source["editions"]):
        raise ValueError("Invalid published source selector")
    _public(source)
    snapshots, paths, routes = {}, set(), set()
    for entry in source["editions"]:
        if (not isinstance(entry, dict)
                or set(entry) not in ({"release_id", "status", "snapshot_path", "snapshot_sha256"},
                                     {"release_id", "status", "snapshot_path", "snapshot_sha256", "revision"})
                or entry.get("status") != "published"
                or not isinstance(entry.get("release_id"), str) or not TOKEN.fullmatch(entry["release_id"])
                or entry["release_id"] in snapshots
                or not isinstance(entry.get("snapshot_path"), str)
                or not entry["snapshot_path"].startswith("editions/")
                or not entry["snapshot_path"].endswith(".json")
                or entry["snapshot_path"] in paths
                or not isinstance(entry.get("snapshot_sha256"), str) or not HASH.fullmatch(entry["snapshot_sha256"])
                or type(entry.get("revision", 1)) is not int or entry.get("revision", 1) < 1):
            raise ValueError("Invalid or duplicate published source edition entry")
        snapshot = resolve_edition_entry(root, entry)
        route = (snapshot["report"]["edition_date"], entry.get("revision", 1))
        if route in routes:
            raise ValueError("Published source editions cannot share an immutable URL")
        snapshots[entry["release_id"]] = snapshot
        paths.add(entry["snapshot_path"])
        routes.add(route)
    current = source["current_release_id"]
    if current not in snapshots:
        raise ValueError("Published source current edition is not in its verified ledger")
    # Keep the publication ledger outside the exact frozen report. In particular
    # its report['editions'] remains [] and read_replay_package can reverify it.
    context = copy.deepcopy(snapshots[current])
    context[SOURCE_MARKER] = {"schema_version": SOURCE_VERSION, "sha256": _hash(blob)}
    context[SOURCE_LEDGER] = copy.deepcopy(source["editions"])
    context["edition_snapshots"] = snapshots
    return context


def edition_entries(context):
    """Read the authenticated public ledger, or the ordinary authoring ledger."""
    expected = load_published_source(context.get("root", citations.ROOT))
    if expected is None:
        if SOURCE_MARKER in context or SOURCE_LEDGER in context:
            raise ValueError("Published source selection or verified edition ledger was changed")
        if (MARKER in context or "replay_verification" in context
                or context.get("policy", {}).get("mode") == "replay_only"):
            # Standalone verified historical contexts remain usable without a
            # current selector, but cannot fall through to a fresh-input gate.
            read_replay_package(context)
        return context["report"].get("editions", [])
    if any(context.get(key) != expected[key] for key in (
            SOURCE_MARKER, SOURCE_LEDGER, "edition_snapshots", MARKER)):
        raise ValueError("Published source selection or verified edition ledger was changed")
    read_replay_package(context)
    return copy.deepcopy(expected[SOURCE_LEDGER])


def export_published_edition(root, release_id, archive_receipt, output):
    """Export a tiny public descriptor only after real publication verification.

    It replaces neither the private scheduler candidate nor any frozen bytes.
    Retrying is deterministic; different existing output is never overwritten.
    """
    selected = _selection(root, release_id)
    receipt = copy.deepcopy(archive_receipt)
    if not isinstance(receipt, dict):
        raise ValueError("An actual production archive receipt is required")
    # The adapter exports this operational location alongside its typed receipt.
    # The source-selected package path replaces it in the public descriptor;
    # every DOI, reservation, verification and lifecycle field stays unchanged.
    receipt.pop("bundle_path", None)
    descriptor = {"schema_version": VERSION, "release_id": release_id, "package_path": selected["path"],
                  **_pins(selected), "archive_receipt": receipt}
    _verify(root, descriptor)
    output = Path(output)
    if output.suffix != ".json" or output.is_symlink():
        raise ValueError("Published edition descriptor must name a regular JSON file")
    blob = citations.json_bytes(descriptor)
    receipt = {"schema_version": VERSION, "release_id": release_id, "publication": "published",
               "snapshot_sha256": _hash(blob), "snapshot_bytes": len(blob),
               "context_sha256": selected["context_sha256"], "archive_sha256": selected["archive_sha256"]}
    outputs = ((output, blob), (output.with_suffix(".receipt.json"), citations.json_bytes(receipt)))
    for path, value in outputs:
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != value)):
            raise ValueError("An exported historical descriptor cannot be overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    for path, value in outputs:
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(value)
    return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--archive-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = _json(args.archive_receipt.read_bytes())
    result = export_published_edition(args.root, args.release, receipt, args.output)
    print(citations.json_bytes(result).decode(), end="")


if __name__ == "__main__":
    main()
