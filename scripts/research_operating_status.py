"""Optional source-owned notices about the next edition, never research inputs.

No status file means no change. A present file requires an already verified
published-source context and an explicit aware validation clock. This module
never writes files, opens private authoring inputs, or authorizes publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

STATUS_PATH = "data/research/operating-status.json"
VERSION = "research-operating-status-v1"
CONTEXT_KEY = "operating_status"
FIELDS = {"schema_version", "state", "observed_on", "published_source_sha256",
          "current_release_id", "current_edition_date", "next_edition_date", "reason_codes"}
REASONS = {
    "publication_preparation": "Final publication preparation was still in progress.",
    "research_review": "Research review was still in progress.",
    "source_checks": "Source checks were still in progress.",
    "technical_checks": "Final file and website checks were still in progress.",
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")
_PACIFIC = ZoneInfo("America/Los_Angeles")
_MONTHS = ("", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


@dataclass(frozen=True)
class OperatingStatus:
    """Validated rendering data; created by validate/load, never from raw JSON."""

    state: str
    observed_on: datetime
    current_release_id: str
    current_edition_date: date
    next_edition_date: date
    reason_codes: tuple[str, ...]


def _day(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError("Operating status requires exact ISO calendar dates")
    return date.fromisoformat(value)


def _timestamp(value):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError("Operating status requires an aware ISO timestamp with seconds")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Operating status requires an aware ISO timestamp")
    return stamp.astimezone(timezone.utc)


def _clock(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Operating status needs an explicit aware actual validation clock")
    return now.astimezone(timezone.utc)


def _next_week(day):
    return day + timedelta(days=7 - day.weekday())


def validate_operating_status(value, context, *, now):
    """Pure shape/time/binding checks against an already verified public context.

    Call load_operating_status for source files: it also reauthenticates the
    selector, ledger, receipt and immutable package through the historical reader.
    A frozen replay need not be archival_ready for fresh publication.
    """
    from research_citations import published_archive
    from research_edition_replay import MARKER, SOURCE_MARKER, SOURCE_LEDGER, SOURCE_VERSION

    actual_now = _clock(now)
    if (not isinstance(value, dict) or set(value) != FIELDS
            or value.get("schema_version") != VERSION
            or not isinstance(value.get("state"), str)
            or value["state"] not in {"held", "preparing"}):
        raise ValueError("Invalid operating status fields or state")
    if not isinstance(context, dict):
        raise ValueError("Operating status requires a verified public context")
    source = context.get(SOURCE_MARKER, {})
    report = context.get("report", {})
    descriptor = context.get(MARKER, {})
    ledger = context.get(SOURCE_LEDGER)
    gate = context.get("gate", {})
    if (not isinstance(source, dict) or set(source) != {"schema_version", "sha256"}
            or source.get("schema_version") != SOURCE_VERSION
            or not isinstance(source.get("sha256"), str) or not _HASH.fullmatch(source["sha256"])
            or not isinstance(value.get("published_source_sha256"), str)
            or value["published_source_sha256"] != source["sha256"]
            or not isinstance(report, dict) or report.get("status") != "published"
            or not isinstance(gate, dict) or gate.get("ready") is not True
            or not isinstance(report.get("archive"), dict)
            or not isinstance(descriptor, dict) or descriptor.get("release_id") != report.get("release_id")
            or descriptor.get("archive_receipt") != report.get("archive")
            or not isinstance(ledger, list)
            or not any(isinstance(row, dict) and row.get("release_id") == report.get("release_id")
                       and row.get("status") == "published" for row in ledger)
            or not published_archive(context)):
        raise ValueError("Operating status requires the exact selected verified published edition")
    release = value.get("current_release_id")
    if not isinstance(release, str) or not _TOKEN.fullmatch(release) or release != report.get("release_id"):
        raise ValueError("Operating status cannot change the current published release")
    current_day = _day(value["current_edition_date"])
    target_day = _day(value["next_edition_date"])
    if current_day != _day(report.get("edition_date")) or target_day != _next_week(current_day):
        raise ValueError("Operating status must retain the published date and its next weekly target")
    observed = _timestamp(value["observed_on"])
    confirmed = _timestamp(report["archive"]["confirmed_on"])
    if not datetime.combine(current_day, time(), _PACIFIC) <= confirmed <= observed <= actual_now:
        raise ValueError("Operating status observation conflicts with actual publication or clock")
    reasons = value["reason_codes"]
    if (not isinstance(reasons, list) or any(not isinstance(code, str) or code not in REASONS for code in reasons)
            or len(set(reasons)) != len(reasons)):
        raise ValueError("Operating status permits only distinct known reason codes")
    target = datetime.combine(target_day, time(9), _PACIFIC)
    if value["state"] == "held":
        if not reasons or observed < target:
            raise ValueError("A delayed edition requires observed known reasons at or after its target")
    elif reasons or observed >= target:
        raise ValueError("Preparing status requires a future target and no claimed delay reasons")
    return OperatingStatus(value["state"], observed, release, current_day, target_day, tuple(sorted(reasons)))


def _json(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate operating status field")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite operating status number")

    try:
        return json.loads(blob, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid operating status JSON") from error


def load_operating_status(root, context, *, now=None):
    """Read only the optional small public file, failing closed when it is present.

    Absence performs no historical verification or clock reads. A present status
    cannot select a release: the source selector and frozen package are rechecked
    first, using only public replay inputs. The caller supplies the actual clock;
    it is used solely for validation and is never stored or rendered.
    """
    root = Path(root).resolve()
    path = root / STATUS_PATH
    for part in (root / "data", root / "data/research", path):
        if part.is_symlink():
            raise ValueError("Operating status must be a source-owned regular file")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("Operating status must be a small regular JSON file")
    value = _json(path.read_bytes())
    from research_edition_replay import SOURCE_MARKER, SOURCE_LEDGER, edition_entries

    if (Path(context.get("root", "")).resolve() != root
            or SOURCE_MARKER not in context or SOURCE_LEDGER not in context):
        raise ValueError("Operating status needs the current source-selected published context")
    edition_entries(context)  # Reauthenticates selector, ledger and untouched frozen bytes.
    return validate_operating_status(value, context, now=now)


def with_operating_status(context, *, now=None):
    """Make a rendering-only shallow overlay; absent status returns the same input.

    Use only inside current-page rendering, after build_context has selected the
    public source. Do not add the overlay to archive/context/PDF/export inputs.
    """
    if CONTEXT_KEY in context:
        raise ValueError("Operating status must be loaded from its source file")
    status = load_operating_status(context["root"], context, now=now)
    return context if status is None else {**context, CONTEXT_KEY: status}


def _label(day):
    return f"{_MONTHS[day.month]} {day.day}, {day.year}"


def operating_status_notice(context):
    """Plain static HTML for current hub/report/data only; empty when absent."""
    status = context.get(CONTEXT_KEY)
    if status is None:
        return ""
    if not isinstance(status, OperatingStatus):
        raise ValueError("Render only validated operating status")
    target = datetime.combine(status.next_edition_date, time(9), _PACIFIC)
    target_iso = target.isoformat()
    target_label = _label(status.next_edition_date) + " at 9:00 a.m. Pacific"
    if status.state == "held":
        heading = "Next edition delayed"
        message = (f'At the recorded observation, the edition targeted for <time datetime="{target_iso}">{target_label}</time> '
                   "was delayed. " + " ".join(REASONS[code] for code in status.reason_codes))
    else:
        heading = "Next edition preparation"
        message = f'At the recorded observation, the next edition was being prepared for <time datetime="{target_iso}">{target_label}</time>.'
    observed_iso = status.observed_on.isoformat().replace("+00:00", "Z")
    observed_label = (_label(status.observed_on.date()) + " at "
                      + status.observed_on.strftime("%H:%M:%S") + " UTC")
    return ('<section class="r-section r-operating-status" aria-label="Edition update">'
            f'<h2>{heading}</h2><p>{message}</p>'
            f'<p>The edition shown on this website remains {_label(status.current_edition_date)} '
            f'({escape(status.current_release_id)}).</p>'
            f'<p class="r-meta">Status observed <time datetime="{observed_iso}">{observed_label}</time>.</p></section>')
