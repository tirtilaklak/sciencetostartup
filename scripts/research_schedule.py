#!/usr/bin/env python3
"""Offline, resumable Pacific-time research edition preparation.

This command prepares held packages. It never connects to an archive, mirror,
website or credentialed API. Journaled local activation requires explicit bound
approval and actual publication receipts; the present policy is prepare-only.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
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
    return {"edition_id": monday.isoformat(), "timezone": PACIFIC.key,
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
    return event


def _candidate_path(directory, candidate_id):
    if not isinstance(candidate_id, str) or len(candidate_id) != 64 or any(char not in "0123456789abcdef" for char in candidate_id):
        raise ValueError("Candidate ID must be a SHA-256 digest.")
    return Path(directory) / "candidates" / f"{candidate_id}.json"


def _read_candidate(directory, candidate_id):
    candidate = json.loads(_candidate_path(directory, candidate_id).read_text())
    if candidate.get("candidate_sha256") != candidate_id or canonical_hash(candidate.get("identity")) != candidate_id:
        raise ValueError("Candidate identity digest failed verification.")
    for key, digest in candidate["identity"]["bindings"].items():
        if canonical_hash(candidate["snapshot"][key]) != digest:
            raise ValueError(f"Candidate {key} bytes no longer match its identity.")
    return candidate


def prepare_candidate(context, directory, monday, now):
    """Freeze exact inputs. Repeating the same identity resumes the same candidate."""
    directory = Path(directory)
    window = edition_window(monday)
    report = dict(context["report"])
    report["source_cutoff"] = window["source_cutoff"]
    from research_report import publication_gate
    gate = publication_gate(context["graph"], report, context["policy"])
    snapshot = {"graph": context["graph"], "report": report, "policy": context["policy"], "identity": context["identity"]}
    identity = {"edition_id": window["edition_id"], "release_id": report["release_id"],
                "window": window, "bindings": {key: canonical_hash(value) for key, value in snapshot.items()}}
    candidate_id = canonical_hash(identity)
    candidate = {"candidate_sha256": candidate_id, "identity": identity, "snapshot": snapshot,
                 "created_on": _iso(_aware(now)), "status": "prepared" if gate["ready"] else "held",
                 "gate": gate, "publication": "not_published"}
    with state_lock(directory):
        events = read_journal(directory)
        path = _candidate_path(directory, candidate_id)
        if path.exists():
            candidate = _read_candidate(directory, candidate_id)
        else:
            _atomic_json(path, candidate)
        if not any(event["kind"] == "prepared" and event["payload"].get("candidate_sha256") == candidate_id for event in events):
            _append(directory, "prepared", {"candidate_sha256": candidate_id, "edition_id": window["edition_id"], "status": candidate["status"]}, now)
    return candidate


def record_approval(directory, candidate_id, receipt, now):
    """Import an explicit review receipt; this function does not create approval."""
    with state_lock(directory):
        candidate = _read_candidate(directory, candidate_id)
        if receipt.get("candidate_sha256") != candidate_id or receipt.get("release_id") != candidate["identity"]["release_id"]:
            raise ValueError("Approval does not bind the exact candidate and release.")
        if receipt.get("decision") != "approved" or not receipt.get("approved_by") or not receipt.get("rationale"):
            raise ValueError("An explicit attributed approval receipt is required.")
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


def activate_candidate(directory, candidate_id, now):
    """Journal local activation after receipts; never performs external mutations."""
    from research_report import publication_gate
    with state_lock(directory):
        candidate = _read_candidate(directory, candidate_id)
        events = read_journal(directory)
        activated = [event for event in events if event["kind"] == "activated"]
        if activated and activated[-1]["payload"].get("candidate_sha256") == candidate_id:
            return {"status": "already_active", "candidate_sha256": candidate_id}
        edition = candidate["identity"]["edition_id"]
        if activated and edition <= activated[-1]["payload"]["edition_id"]:
            raise ValueError("Publication identity must advance monotonically; old candidates cannot replace newer editions.")
        snapshot = candidate["snapshot"]
        gate = publication_gate(snapshot["graph"], snapshot["report"], snapshot["policy"])
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
        event = _append(directory, "activated", {"candidate_sha256": candidate_id, "edition_id": edition,
                                                "release_id": candidate["identity"]["release_id"]}, now)
        # The journal is authoritative. A crash before this convenience pointer
        # is harmless: activation() recognizes and restores the same candidate.
        _atomic_json(Path(directory) / "active.json", event["payload"])
        return {"status": "activated_locally", **event["payload"], "external_mutations": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "prepare", "approve", "activate"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state-directory", type=Path, default=ROOT / "build/research-state")
    parser.add_argument("--now", help="Timezone-aware timestamp; default is current UTC.")
    parser.add_argument("--edition", help="Monday ISO date; prepare defaults to the next edition.")
    parser.add_argument("--candidate", help="Exact prepared candidate SHA-256.")
    parser.add_argument("--receipt", type=Path, help="Existing explicit approval receipt JSON.")
    args = parser.parse_args()
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
    elif args.action == "prepare":
        from research_report import build_context
        monday = args.edition or schedule_status(now)["next_edition"]["edition_id"]
        candidate = prepare_candidate(build_context(root), state, monday, now)
        result = {key: candidate[key] for key in ("candidate_sha256", "identity", "status", "gate", "publication")}
    elif args.action == "approve":
        if not args.candidate or not args.receipt:
            parser.error("approve requires --candidate and --receipt")
        result = record_approval(state, args.candidate, json.loads(args.receipt.read_text()), now)
    else:
        if not args.candidate:
            parser.error("activate requires --candidate")
        result = activate_candidate(state, args.candidate, now)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
