#!/usr/bin/env python3
"""Offline, resumable Pacific-time research edition preparation.

This command prepares held packages. It never connects to an archive, mirror,
website or credentialed API. Journaled local activation requires an actual bound
coordinator review and publication receipts; the present policy is prepare-only.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import re
import socket
import tempfile
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from research_report import ROOT, canonical_hash

PACIFIC = ZoneInfo("America/Los_Angeles")


def _aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An explicit timezone-aware timestamp is required.")
    return value


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def edition_window(monday):
    """Construct local wall-clock instants separately, including DST transitions."""
    if isinstance(monday, str):
        monday = date.fromisoformat(monday)
    if not isinstance(monday, date) or isinstance(monday, datetime) or monday.weekday() != 0:
        raise ValueError("Edition date must be an ISO Monday calendar date.")
    publication = datetime.combine(monday, time(9), PACIFIC)
    cutoff = datetime.combine(monday - timedelta(days=3), time(17), PACIFIC)
    return {"edition_id": monday.isoformat(), "edition_date": monday.isoformat(), "timezone": PACIFIC.key,
            "publish_at": _iso(publication), "source_cutoff": _iso(cutoff),
            "publish_local": publication.isoformat(), "cutoff_local": cutoff.isoformat()}


def schedule_status(now, last_prepared_on=None):
    local = _aware(now).astimezone(PACIFIC)
    monday = local.date() - timedelta(days=local.weekday())
    latest = edition_window(monday)
    if _aware(latest["publish_at"]) > local:
        latest = edition_window(monday - timedelta(days=7))
    upcoming = edition_window(monday)
    if _aware(upcoming["publish_at"]) <= local:
        upcoming = edition_window(monday + timedelta(days=7))
    daily = datetime.combine(local.date(), time(16), PACIFIC)
    last = _aware(last_prepared_on).astimezone(PACIFIC) if last_prepared_on else None
    return {"now": _iso(local), "prepare_due": local >= daily and (last is None or last < daily),
            "daily_prepare_at": _iso(daily), "latest_due_edition": latest,
            "next_edition": upcoming}


def source_in_window(captured_on, window):
    """A later verification cannot rescue a source version captured after cutoff."""
    return _aware(captured_on) <= _aware(window["source_cutoff"])


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".research-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def state_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "scheduler.lock"
    token = uuid.uuid4().hex
    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"pid": os.getpid(), "host": socket.gethostname(), "token": token}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            break
        except FileExistsError:
            try:
                stat = path.stat()
                previous = json.loads(path.read_text())
                if previous.get("host") != socket.gethostname():
                    raise RuntimeError("Scheduler lock belongs to another host; inspect it before recovery.")
                pid = previous["pid"]
                if not isinstance(pid, int) or pid < 1:
                    raise RuntimeError("Malformed scheduler lock; inspect it before recovery.")
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    if path.stat().st_ino == stat.st_ino:
                        path.unlink()
                    continue
                raise RuntimeError("Another scheduler process holds the state lock.")
            except (KeyError, ValueError):
                raise RuntimeError("Malformed scheduler lock; inspect it before recovery.") from None
    else:
        raise RuntimeError("Could not acquire scheduler lock after recovery.")
    try:
        yield
    finally:
        if path.exists() and json.loads(path.read_text()).get("token") == token:
            path.unlink()


def read_journal(directory):
    path = Path(directory) / "journal.jsonl"
    events, previous = [], "0" * 64
    if not path.exists():
        return events
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Interrupted journal tail requires inspection; no edition can activate.")
    for line in raw.splitlines():
        event = json.loads(line)
        digest = event.pop("event_sha256", None)
        if event.get("sequence") != len(events) + 1 or event.get("previous_sha256") != previous or canonical_hash(event) != digest:
            raise ValueError("Scheduler journal chain failed verification.")
        event["event_sha256"] = digest
        events.append(event)
        previous = digest
    return events


def _append(directory, kind, payload, now):
    events = read_journal(directory)
    event = {"sequence": len(events) + 1, "previous_sha256": events[-1]["event_sha256"] if events else "0" * 64,
             "kind": kind, "at": _iso(_aware(now)), "payload": payload}
    event["event_sha256"] = canonical_hash(event)
    with (Path(directory) / "journal.jsonl").open("a") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return event


def _candidate_path(directory, candidate_id):
    if not isinstance(candidate_id, str) or len(candidate_id) != 64 or any(char not in "0123456789abcdef" for char in candidate_id):
        raise ValueError("Candidate ID must be a SHA-256 digest.")
    return Path(directory) / "candidates" / f"{candidate_id}.json"


def _digest_path(directory, category, digest):
    # Reuse the strict digest validator before constructing any state path.
    _candidate_path(directory, digest)
    return Path(directory) / category / f"{digest}.json"


def _immutable_json(path, value):
    """Never replace an existing immutable record, including on retry."""
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("An immutable scheduler record no longer matches its digest.")
        return
    _atomic_json(path, value)


def load_snapshot(directory, snapshot_id):
    """Load an older compact edition reference without using current report inputs."""
    snapshot = json.loads(_digest_path(directory, "snapshots", snapshot_id).read_text())
    if canonical_hash(snapshot) != snapshot_id:
        raise ValueError("Edition snapshot digest failed verification.")
    return snapshot


def _store_snapshot(directory, snapshot):
    digest = canonical_hash(snapshot)
    _immutable_json(_digest_path(directory, "snapshots", digest), snapshot)
    return digest


def _edition_references(entries, directory, current_snapshot):
    """Externalize old embedded snapshots so editions never recursively grow."""
    references = []
    snapshot_keys = ("graph", "report", "policy", "identity", "roles")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Edition references must be objects.")
        reference = {key: copy.deepcopy(value) for key, value in entry.items()
                     if key not in {*snapshot_keys, "snapshot", "gate"}}
        embedded = entry.get("snapshot")
        if not isinstance(embedded, dict) and all(key in entry for key in snapshot_keys[:4]):
            embedded = {key: entry.get(key, {}) for key in snapshot_keys}
        if (not isinstance(embedded, dict) and entry.get("status") == "published"
                and entry.get("release_id") == current_snapshot["report"].get("release_id")):
            embedded = copy.deepcopy(current_snapshot)
            # A reference to this current edition is not another nested archive.
            embedded["report"]["editions"] = []
        if isinstance(embedded, dict):
            frozen = {key: copy.deepcopy(embedded.get(key, {})) for key in snapshot_keys}
            frozen["report"]["editions"] = _edition_references(
                frozen["report"].get("editions", []), directory, frozen)
            reference["snapshot_sha256"] = _store_snapshot(directory, frozen)
            reference.setdefault("release_id", frozen["report"].get("release_id"))
            reference.setdefault("edition_date", frozen["report"].get("edition_date"))
        references.append(reference)
    return references


def _read_candidate(directory, candidate_id):
    candidate = json.loads(_candidate_path(directory, candidate_id).read_text())
    if candidate.get("candidate_sha256") != candidate_id or canonical_hash(candidate.get("identity")) != candidate_id:
        raise ValueError("Candidate identity digest failed verification.")
    if candidate.get("record_sha256"):
        record = {key: value for key, value in candidate.items() if key != "record_sha256"}
        if canonical_hash(record) != candidate["record_sha256"]:
            raise ValueError("Candidate record digest failed verification.")
    for key, digest in candidate["identity"]["bindings"].items():
        if canonical_hash(candidate["snapshot"][key]) != digest:
            raise ValueError(f"Candidate {key} bytes no longer match its identity.")
    snapshot_id = candidate["identity"].get("snapshot_sha256")
    if snapshot_id and load_snapshot(directory, snapshot_id) != candidate["snapshot"]:
        raise ValueError("Candidate differs from its immutable edition snapshot.")
    return candidate


def load_edition(directory, monday, candidate_id=None):
    """Resolve an edition to its frozen inputs, never to the current live report.

    Multiple preparations can belong to one edition. Without an explicit digest,
    resolve the most recently journaled preparation for that edition.
    """
    edition = edition_window(monday)["edition_id"]
    if candidate_id is None:
        matches = [event for event in read_journal(directory) if event["kind"] == "prepared"
                   and event["payload"].get("edition_id") == edition]
        if not matches:
            raise ValueError("No immutable preparation exists for this edition.")
        candidate_id = matches[-1]["payload"]["candidate_sha256"]
    candidate = _read_candidate(directory, candidate_id)
    if candidate["identity"]["edition_id"] != edition:
        raise ValueError("Candidate does not belong to the requested edition.")
    return candidate["snapshot"]


def resolve_edition_reference(directory, reference):
    """Hydrate a compact archive entry; this does not establish publication."""
    if reference.get("candidate_sha256"):
        candidate = _read_candidate(directory, reference["candidate_sha256"])
        snapshot = candidate["snapshot"]
        expected = reference.get("snapshot_sha256")
        if expected and canonical_hash(snapshot) != expected:
            raise ValueError("Edition reference and candidate snapshot digests differ.")
    elif reference.get("snapshot_sha256"):
        snapshot = load_snapshot(directory, reference["snapshot_sha256"])
    else:
        raise ValueError("An immutable candidate or snapshot reference is required.")
    if reference.get("release_id") and reference["release_id"] != snapshot["report"].get("release_id"):
        raise ValueError("Edition reference release does not match its immutable snapshot.")
    return snapshot


def _core_record(snapshot, snapshot_id=None):
    """Validate before deriving any durable inventory or authorizing a release."""
    from research_graph import validate_graph

    if not isinstance(snapshot, dict) or "graph" not in snapshot:
        raise ValueError("Core inventory requires an immutable graph snapshot.")
    graph = snapshot["graph"]
    validate_graph(graph)
    frozen = graph["coverage"]["frozen_core"]
    return {"snapshot": snapshot, "snapshot_sha256": snapshot_id,
            "entity_ids": sorted(frozen["entity_ids"]), "core_sha256": frozen["sha256"],
            "source_graph_sha256": canonical_hash(graph)}


def _ensure_core_continuity(directory, snapshot, now):
    """Under the shared lock, freeze scope before readiness and retain every ID.

    The journal is the inventory authority. Source snapshots make certificates
    independently verifiable, including a freeze recorded before any candidate
    passes its scientific gate or finishes writing its preparation event.
    """
    current = _core_record(snapshot)
    events = read_journal(directory)
    latest, history, seen = None, [], set()
    for event in events:
        payload = event["payload"]
        if event["kind"] in {"core_frozen", "core_expanded"}:
            try:
                bound = _core_record(load_snapshot(directory, payload.get("snapshot_sha256")),
                                     payload.get("snapshot_sha256"))
            except OSError as error:
                raise ValueError("Frozen-core certificate source snapshot cannot be verified.") from error
            expected = {key: bound[key] for key in ("entity_ids", "core_sha256", "source_graph_sha256", "snapshot_sha256")}
            expected.update(schema_version=1, previous_core_sha256=latest["core_sha256"] if latest else None)
            old = set(latest["entity_ids"]) if latest else set()
            if (payload != expected or not bound["entity_ids"]
                    or event["kind"] != ("core_expanded" if latest else "core_frozen")
                    or not old < set(bound["entity_ids"])):
                raise ValueError("Frozen-core certificate failed verification.")
            latest = bound
            history.append(bound)
        elif event["kind"] in {"prepared", "activated", "published"}:
            # Older scheduler journals predate certificates. Recover their exact
            # inputs rather than allowing a fresh empty/smaller declaration.
            candidate_id, snapshot_id = payload.get("candidate_sha256"), payload.get("snapshot_sha256")
            reference = (candidate_id, snapshot_id)
            if reference in seen:
                continue
            seen.add(reference)
            try:
                if candidate_id:
                    candidate = _read_candidate(directory, candidate_id)
                    historical = candidate["snapshot"]
                    if snapshot_id and canonical_hash(historical) != snapshot_id:
                        raise ValueError("Journal preparation and candidate snapshot digests differ.")
                    snapshot_id = canonical_hash(historical)
                elif snapshot_id:
                    historical = load_snapshot(directory, snapshot_id)
                else:
                    raise ValueError("Journal edition has no immutable source binding for core recovery.")
            except (OSError, KeyError) as error:
                raise ValueError("Journal edition source cannot be verified for core recovery.") from error
            history.append(_core_record(historical, snapshot_id))

    required = set().union(*(set(record["entity_ids"]) for record in history))

    def certify(record):
        nonlocal latest
        snapshot_id = _store_snapshot(directory, record["snapshot"])
        payload = {key: record[key] for key in ("entity_ids", "core_sha256", "source_graph_sha256")}
        payload.update(schema_version=1, snapshot_sha256=snapshot_id,
                       previous_core_sha256=latest["core_sha256"] if latest else None)
        _append(directory, "core_expanded" if latest else "core_frozen", payload, now)
        latest = record

    if required and (latest is None or not required <= set(latest["entity_ids"])):
        # Prefer an existing frozen edition when seeding a legacy journal. If
        # past inventories diverged, only a validated graph retaining their union
        # can reconcile them; a smaller current declaration cannot erase history.
        recovered = next((record for record in reversed(history)
                          if required <= set(record["entity_ids"])), None)
        if recovered is None and required <= set(current["entity_ids"]):
            recovered = current
        if recovered is None:
            raise ValueError("Historical frozen-core inventories require reconciliation retaining every ID.")
        certify(recovered)
    missing = (set(latest["entity_ids"]) if latest else required) - set(current["entity_ids"])
    if missing:
        raise ValueError("Frozen core cannot shrink or unfreeze; retain previously frozen IDs: " + ", ".join(sorted(missing)))
    if current["entity_ids"] and (latest is None or set(current["entity_ids"]) > set(latest["entity_ids"])):
        certify(current)


def prepare_candidate(context, directory, monday, now):
    """Stage an edition copy; stable inputs resume without changing canonical data."""
    from research_report import publication_gate

    directory = Path(directory)
    window = edition_window(monday)
    prepared_on = _iso(_aware(now))
    release_id = f"research-{window['edition_id']}.1"
    # All changes are confined to this deep copy. Review/capture dates and actual
    # graph/audit release bindings stay unchanged; they must not be relabeled.
    snapshot = {key: copy.deepcopy(context.get(key, {}))
                for key in ("graph", "report", "policy", "identity", "roles")}
    with state_lock(directory):
        events = read_journal(directory)
        # Invalid graphs must not write snapshots, references or certificates.
        _core_record(snapshot)
        prior_snapshot = copy.deepcopy(snapshot)
        report = snapshot["report"]
        report["editions"] = _edition_references(report.get("editions", []), directory, prior_snapshot)
        new_edition = report.get("release_id") != release_id or report.get("edition_date") != window["edition_id"]
        report.update({"edition_date": window["edition_id"], "release_id": release_id,
                       "source_cutoff": window["source_cutoff"], "publish_at": window["publish_at"],
                       "status": "prepared"})
        if new_edition:
            # A previous DOI or reserved deposition does not belong to this issue.
            report["archive"] = {"status": "not_published", "doi": None, "record_url": None}
        _ensure_core_continuity(directory, snapshot, now)
        gate = publication_gate(snapshot["graph"], report, snapshot["policy"])
        snapshot_id = _store_snapshot(directory, snapshot)
        identity = {"edition_id": window["edition_id"], "edition_date": window["edition_id"],
                    "release_id": release_id, "window": window, "snapshot_sha256": snapshot_id,
                    "bindings": {key: canonical_hash(value) for key, value in snapshot.items()}}
        candidate_id = canonical_hash(identity)
        candidate = {"candidate_sha256": candidate_id, "identity": identity, "snapshot": snapshot,
                     "created_on": prepared_on, "prepared_on": prepared_on,
                     "prepared_after_window": _aware(now) > _aware(window["publish_at"]),
                     "status": "prepared" if gate["ready"] else "held", "gate": gate,
                     "publication": "not_published"}
        candidate["record_sha256"] = canonical_hash(candidate)
        path = _candidate_path(directory, candidate_id)
        if path.exists():
            candidate = _read_candidate(directory, candidate_id)
        else:
            _immutable_json(path, candidate)
        reference = {"candidate_sha256": candidate_id, "edition_date": window["edition_id"],
                     "release_id": release_id, "snapshot_sha256": snapshot_id,
                     "prepared_on": candidate["prepared_on"], "publication": "not_published"}
        _immutable_json(directory / "editions" / window["edition_id"] / f"{candidate_id}.json", reference)
        if not any(event["kind"] == "prepared" and event["payload"].get("candidate_sha256") == candidate_id for event in events):
            _append(directory, "prepared", {"candidate_sha256": candidate_id, "edition_id": window["edition_id"],
                                            "snapshot_sha256": snapshot_id, "status": candidate["status"]}, now)
    return candidate


def record_approval(directory, candidate_id, receipt, now):
    """Import an actual coordinator review receipt, including an AI coordinator."""
    from research_report import publication_gate

    with state_lock(directory):
        candidate = _read_candidate(directory, candidate_id)
        if receipt.get("candidate_sha256") != candidate_id or receipt.get("release_id") != candidate["identity"]["release_id"]:
            raise ValueError("Approval does not bind the exact candidate and release.")
        if receipt.get("decision") != "approved" or not receipt.get("approved_by") or not receipt.get("rationale"):
            raise ValueError("An explicit attributed approval receipt is required.")
        if (receipt.get("role") != "coordinator" or receipt.get("reviewer_type") not in {"ai", "human"}
                or receipt.get("method") != "final_quality_review" or receipt.get("fixture") is not False
                or not receipt.get("invocation_id")):
            raise ValueError("An actual attributed coordinator review invocation is required; AI review is allowed.")
        snapshot = candidate["snapshot"]
        _ensure_core_continuity(directory, snapshot, now)
        review_invocations = {review.get("invocation_id") for review in snapshot["graph"].get("reviews", [])}
        if receipt["invocation_id"] in review_invocations:
            raise ValueError("Coordinator approval must use its own review invocation.")
        gate = publication_gate(snapshot["graph"], snapshot["report"], snapshot["policy"])
        if not gate.get("archival_ready"):
            raise ValueError("The scientific quality gate must pass before coordinator approval.")
        approved_on = _aware(receipt.get("approved_on"))
        if approved_on < _aware(candidate["created_on"]) or approved_on > _aware(now):
            raise ValueError("Approval time must follow preparation and cannot be in the future.")
        digest = canonical_hash(receipt)
        events = read_journal(directory)
        existing = [event for event in events if event["kind"] == "approved" and event["payload"].get("candidate_sha256") == candidate_id]
        if existing:
            if existing[-1]["payload"].get("approval_sha256") != digest:
                raise ValueError("A different approval is already journaled for this candidate.")
            return existing[-1]
        return _append(directory, "approved", {"candidate_sha256": candidate_id, "approval_sha256": digest, "receipt": receipt}, now)


def _publication_snapshot(candidate, archive_receipt=None):
    """Overlay later lifecycle evidence without changing frozen science inputs."""
    from research_report import publication_gate

    snapshot = copy.deepcopy(candidate["snapshot"])
    if archive_receipt is not None:
        if not isinstance(archive_receipt, dict):
            raise ValueError("Archive receipt must be an object.")
        if archive_receipt.get("release_id") != candidate["identity"]["release_id"]:
            raise ValueError("Archive receipt does not bind the exact candidate release.")
        if (archive_receipt.get("status") != "published" or archive_receipt.get("verified") is not True
                or archive_receipt.get("api_origin") != "https://zenodo.org"
                or archive_receipt.get("environment") != "production"
                or not re.fullmatch(r"[0-9a-f]{64}", archive_receipt.get("artifact_sha256") or "")):
            raise ValueError("An actual verified production archive receipt and exact artifact digest are required.")
        if _aware(archive_receipt.get("confirmed_on")) < _aware(candidate["identity"]["window"]["publish_at"]):
            raise ValueError("Archive confirmation predates this edition's publication window.")
        existing = snapshot["report"].get("archive", {})
        for key in ("reserved_doi", "deposition_id", "api_origin", "environment"):
            if existing.get(key) is not None and archive_receipt.get(key) != existing[key]:
                raise ValueError("Archive receipt changes the frozen reservation: " + key)
        snapshot["report"]["archive"] = copy.deepcopy(archive_receipt)
    gate = publication_gate(snapshot["graph"], snapshot["report"], snapshot["policy"])
    if archive_receipt is not None and gate.get("ready"):
        snapshot["report"]["status"] = "published"
    return snapshot, gate


def _assert_public_snapshot(snapshot):
    """Reject private inputs instead of altering evidence and invalidating hashes."""
    from research_citations import privacy_filter

    if privacy_filter(snapshot) != snapshot:
        raise ValueError("Edition export requires public inputs; remove private fields before preparing a new candidate.")
    credential_key = re.compile(r"(?:^|_)(?:authorization|password|passwd|cookie|private_key|access_key)(?:$|_)", re.I)
    def inspect(value):
        if isinstance(value, dict):
            if any(credential_key.search(key) for key in value):
                raise ValueError("Credentials cannot enter an exported edition snapshot.")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
        elif isinstance(value, str) and re.search(r"(?:^|\s)Bearer\s+\S+|https?://[^/\s]+:[^/\s]+@", value, re.I):
            raise ValueError("Credentials cannot enter an exported edition snapshot.")
    inspect(snapshot)


def export_edition(directory, candidate_id, output, archive_receipt=None):
    """Write deterministic, public frozen source inputs and a byte-SHA receipt.

    An optional later archive receipt is transient: the scientific candidate is
    never overwritten. Only a passing final gate can export published status.
    """
    from research_citations import json_bytes, sha256

    output = Path(output)
    if output.suffix != ".json":
        raise ValueError("Edition snapshot output must name a .json file.")
    with state_lock(directory):
        candidate = _read_candidate(directory, candidate_id)
        if archive_receipt is not None:
            _ensure_core_continuity(directory, candidate["snapshot"], datetime.now(timezone.utc))
        snapshot, gate = _publication_snapshot(candidate, archive_receipt)
        if archive_receipt is not None and not gate.get("ready"):
            raise ValueError("Archive receipt did not pass the final publication gate: " + "; ".join(gate["reasons"]))
        # The current edition is self-contained. Its historical ledger belongs
        # to the coordinator's report, not recursively inside this source file.
        snapshot["report"]["editions"] = []
        _assert_public_snapshot(snapshot)
        blob = json_bytes(snapshot)
        receipt = {"schema_version": 1, "candidate_sha256": candidate_id,
                   "release_id": candidate["identity"]["release_id"],
                   "edition_date": candidate["identity"]["edition_id"],
                   "snapshot_sha256": sha256(blob), "snapshot_bytes": len(blob),
                   "frozen_snapshot_sha256": candidate["identity"]["snapshot_sha256"],
                   "prepared_on": candidate["prepared_on"],
                   "publication": "published" if archive_receipt is not None and gate.get("ready") else "not_published"}
        if archive_receipt is not None:
            receipt["archive_receipt_sha256"] = canonical_hash(archive_receipt)
        if output.exists() and output.read_bytes() != blob:
            raise ValueError("An exported edition source snapshot cannot be overwritten.")
        _immutable_json(output, snapshot)
        if output.read_bytes() != blob:
            raise ValueError("Exported source bytes differ from their deterministic representation.")
        _immutable_json(output.with_suffix(".receipt.json"), receipt)
    return receipt


def activate_candidate(directory, candidate_id, now, archive_receipt=None):
    """Journal local activation after receipts; never performs external mutations."""
    with state_lock(directory):
        candidate = _read_candidate(directory, candidate_id)
        _ensure_core_continuity(directory, candidate["snapshot"], now)
        events = read_journal(directory)
        activated = [event for event in events if event["kind"] == "activated"]
        if activated and activated[-1]["payload"].get("candidate_sha256") == candidate_id:
            payload = activated[-1]["payload"]
            if archive_receipt is not None and payload.get("archive_receipt_sha256") != canonical_hash(archive_receipt):
                raise ValueError("A different archive receipt is already bound to this activation.")
            _atomic_json(Path(directory) / "active.json", payload)
            return {"status": "already_active", **payload, "external_mutations": False}
        edition = candidate["identity"]["edition_id"]
        if activated and edition <= activated[-1]["payload"]["edition_id"]:
            raise ValueError("Publication identity must advance monotonically; old candidates cannot replace newer editions.")
        snapshot, gate = _publication_snapshot(candidate, archive_receipt)
        if archive_receipt is not None and _aware(archive_receipt["confirmed_on"]) > _aware(now):
            raise ValueError("Archive confirmation cannot be in the future at activation.")
        held = list(gate["reasons"])
        if snapshot["policy"].get("mode", "prepare_only") != "publish_enabled":
            held.append("External accounts are not connected; policy permits package preparation only.")
        if _aware(now) < _aware(candidate["identity"]["window"]["publish_at"]):
            held.append("Monday 09:00 America/Los_Angeles publication window has not opened.")
        if not any(event["kind"] == "approved" and event["payload"].get("candidate_sha256") == candidate_id for event in events):
            held.append("Exact candidate has no attributed approval receipt.")
        if held:
            payload = {"candidate_sha256": candidate_id, "edition_id": edition, "reasons": list(dict.fromkeys(held))}
            previous_holds = [event for event in events if event["kind"] == "held" and event["payload"] == payload]
            if not previous_holds:
                _append(directory, "held", payload, now)
            return {"status": "held", **payload}
        opened_on = _aware(candidate["identity"]["window"]["publish_at"])
        payload = {"candidate_sha256": candidate_id, "edition_id": edition,
                   "release_id": candidate["identity"]["release_id"],
                   "activated_on": _iso(_aware(now)), "scheduled_publish_at": _iso(opened_on),
                   "activation_timing": "at_window" if _aware(now) == opened_on else "delayed",
                   "publication": "not_published"}
        if archive_receipt is not None:
            payload.update(archive_receipt_sha256=canonical_hash(archive_receipt),
                           archive_release_id=archive_receipt["release_id"],
                           artifact_sha256=archive_receipt["artifact_sha256"],
                           archive_confirmed_on=archive_receipt["confirmed_on"])
        event = _append(directory, "activated", payload, now)
        # The journal is authoritative. A crash before this convenience pointer
        # is harmless: activation() recognizes and restores the same candidate.
        _atomic_json(Path(directory) / "active.json", event["payload"])
        return {"status": "activated_locally", **event["payload"], "external_mutations": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "prepare", "prepare-due", "approve", "activate", "export-edition"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state-directory", type=Path, default=ROOT / "output/research-state")
    parser.add_argument("--now", help="Timezone-aware timestamp; default is current UTC.")
    edition = parser.add_mutually_exclusive_group()
    edition.add_argument("--edition", help="Monday ISO date; prepare defaults to the next edition.")
    edition.add_argument("--due", action="store_true", help="Prepare the latest due edition, including a missed Monday run.")
    parser.add_argument("--candidate", help="Exact prepared candidate SHA-256.")
    parser.add_argument("--receipt", type=Path, help="Existing explicit approval receipt JSON.")
    parser.add_argument("--archive-receipt", type=Path, help="Actual verified production archive receipt JSON, for export or activation.")
    parser.add_argument("--output", type=Path, help="Immutable exported edition source .json file.")
    args = parser.parse_args()
    if args.due and args.action != "prepare":
        parser.error("--due is valid with prepare; prepare-due already selects the latest due edition")
    if args.action == "prepare-due" and args.edition:
        parser.error("prepare-due selects the latest due edition; use prepare --edition for an explicit date")
    if args.archive_receipt and args.action not in {"activate", "export-edition"}:
        parser.error("--archive-receipt is valid with activate or export-edition")
    if args.output and args.action != "export-edition":
        parser.error("--output is valid with export-edition")
    now = _aware(args.now) if args.now else datetime.now(timezone.utc)
    state = args.state_directory.resolve()
    root = args.root.resolve()
    for protected in (root / "data", root / "dist", root / "web"):
        if state == protected or protected in state.parents:
            parser.error("Scheduler state must remain outside source data, web and dist.")
    if args.action == "status":
        events = read_journal(state)
        preparations = [event["at"] for event in events if event["kind"] == "prepared"]
        result = schedule_status(now, preparations[-1] if preparations else None)
        result["journal_events"] = len(events)
        result["mode"] = "offline"
    elif args.action in {"prepare", "prepare-due"}:
        from research_report import build_context
        selection = "latest_due_edition" if args.due or args.action == "prepare-due" else "next_edition"
        monday = args.edition or schedule_status(now)[selection]["edition_id"]
        context = build_context(root)
        roles_path = root / "data/research/roles.json"
        if "roles" not in context and roles_path.is_file():
            context["roles"] = json.loads(roles_path.read_text())
        candidate = prepare_candidate(context, state, monday, now)
        result = {key: candidate[key] for key in ("candidate_sha256", "identity", "status", "gate", "publication",
                                                "prepared_on", "prepared_after_window")}
        result["selection"] = "explicit" if args.edition else selection
    elif args.action == "approve":
        if not args.candidate or not args.receipt:
            parser.error("approve requires --candidate and --receipt")
        result = record_approval(state, args.candidate, json.loads(args.receipt.read_text()), now)
    elif args.action == "export-edition":
        if not args.candidate or not args.output:
            parser.error("export-edition requires --candidate and --output")
        receipt = json.loads(args.archive_receipt.read_text()) if args.archive_receipt else None
        result = export_edition(state, args.candidate, args.output, receipt)
    else:
        if not args.candidate:
            parser.error("activate requires --candidate")
        receipt = json.loads(args.archive_receipt.read_text()) if args.archive_receipt else None
        result = activate_candidate(state, args.candidate, now, receipt)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
