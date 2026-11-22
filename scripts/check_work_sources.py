#!/usr/bin/env python3
"""Collect public-source check candidates; never edit reviewed editorial facts.

Run daily, then let an editor inspect material changes. HTTP 200 is not a
readability or hiring assertion. Response bodies stay out of the output.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 4 * 1024 * 1024
BLOCKED_TEXT = re.compile(r"^(?:request unsuccessful|this request was blocked|access (?:is )?denied|verify (?:you are|that you are) (?:a )?human|just a moment|attention required.*cloudflare)\b", re.I)
PROVIDER_CHALLENGE_FRAME = re.compile(r'<iframe\b[^>]*\bsrc=["\'][^"\']*/_Incapsula_Resource\?', re.I)
SHELL_TEXT = re.compile(r"you need to enable javascript|enable javascript to (?:run|view)|javascript is required", re.I)
CLOSED_TEXT = re.compile(r"^this listing has closed(?:\s*[,!.]|$)", re.I)
UNPUBLISHED_TEXT = re.compile(r"(?:この求人は現在非公開|非公開の求人です)")
NO_APPLICATION_TEXT = re.compile(r"応募(?:することができません|を受け付けていません)")
REGISTRATION_ERROR = re.compile(r"^oops!\s*this url might not be the one you were looking for\.", re.I)
SECONDARY_SIGNALS = {
    'application_check': 'linked_application_unpublished',
    'rendered_observation': 'registration_soft_error',
}


@dataclass(frozen=True)
class FetchObservation:
    status: int
    final_url: str
    body: bytes
    truncated: bool = False
    vercel_mitigation: str = ''


@dataclass(frozen=True)
class LinkedApplicationObservation:
    source_url: str
    requested_url: str
    checked_at: str
    observation: FetchObservation


@dataclass(frozen=True)
class RenderedObservation:
    url: str
    checked_at: str
    text: str


class PublicText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, text):
        if not self.skip and text.strip():
            self.parts.append(text.strip())


def source_summary(body):
    html = body.decode("utf-8", "replace")
    parser = PublicText()
    parser.feed(html)
    visible = " ".join(parser.parts)
    jobs = []
    for block in re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            value = json.loads(block)
        except (ValueError, TypeError):
            continue
        values = value if isinstance(value, list) else value.get("@graph", [value]) if isinstance(value, dict) else []
        jobs.extend(row for row in values if isinstance(row, dict) and row.get("@type") == "JobPosting")
    # For employer job pages compare the job document, not rotating site chrome.
    if jobs:
        stable = json.dumps([{key: row.get(key) for key in (
            "title", "description", "employmentType", "baseSalary", "jobLocation",
            "jobLocationType", "applicantLocationRequirements", "validThrough")}
            for row in jobs], sort_keys=True, ensure_ascii=False)
    else:
        stable = re.sub(r"\s+", " ", unescape(visible)).strip()
    challenge = ((len(visible) < 4000 and any(BLOCKED_TEXT.match(part) for part in parser.parts))
                 or (len(visible) < 120 and bool(PROVIDER_CHALLENGE_FRAME.search(html))))
    shell = bool(SHELL_TEXT.search(visible)) and not jobs
    readable = not challenge and not shell and (bool(jobs) or len(visible) >= 120)
    return {
        "readable": readable,
        "challenge": challenge,
        "shell": shell,
        "explicitly_closed": any(CLOSED_TEXT.match(part) for part in parser.parts),
        "application_unpublished": bool(UNPUBLISHED_TEXT.search(visible) and NO_APPLICATION_TEXT.search(visible)),
        "stable_content_sha256": hashlib.sha256(stable.encode()).hexdigest(),
        "extraction": "jobposting_jsonld" if jobs else "public_text",
        "document_titles": [str(row.get("title") or "")[:180] for row in jobs],
    }


def fetch_public(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ScienceToStartup public-source review)"})
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(MAX_BYTES + 1)
        return FetchObservation(
            response.code, response.geturl(), body[:MAX_BYTES], len(body) > MAX_BYTES,
            response.headers.get('x-vercel-mitigated', ''),
        )


def result_and_reason(observation, summary):
    status = observation.status
    if observation.truncated:
        return 'unavailable', 'bounded_read_truncated'
    if status == 429:
        return 'blocked', 'rate_limited'
    if observation.vercel_mitigation.strip().lower() in ('deny', 'challenge'):
        return 'blocked', 'provider_security'
    if summary['challenge']:
        return 'blocked', 'access_restricted'
    if status in (404, 410):
        return 'not_found', 'http_not_found'
    if status == 403 and summary['application_unpublished']:
        return 'unavailable', 'application_unpublished'
    if status in (401, 403, 407):
        return 'blocked', 'access_restricted'
    if status >= 400:
        return 'unavailable', 'http_error'
    if summary['shell'] or not (summary['readable'] or summary['explicitly_closed']):
        return 'unreadable_shell', 'no_readable_document'
    return 'readable', 'public_document'


def summarize_observation(observation, rendered=None):
    if not isinstance(observation, FetchObservation):
        observation = FetchObservation(*observation)
    summary = source_summary(observation.body)
    result, reason = result_and_reason(observation, summary)
    signals = []
    if result == 'readable' and summary['explicitly_closed']:
        signals.append('explicitly_closed')
    if reason == 'application_unpublished':
        signals.append(reason)
    valid_render = result == 'unreadable_shell' and rendered and rendered.url == observation.final_url
    registration_error = valid_render and any(REGISTRATION_ERROR.match(line.strip()) for line in rendered.text.splitlines())
    if registration_error:
        signals.append('registration_soft_error')
    report = {
        'http_status': observation.status,
        'final_url': observation.final_url,
        'result': result,
        'retrieval_reason': reason,
        'review_signals': signals,
        'response_sha256': hashlib.sha256(observation.body).hexdigest(),
        'truncated': observation.truncated,
        **{key: summary[key] for key in ('stable_content_sha256', 'extraction', 'document_titles')},
    }
    if valid_render:
        report['rendered_observation'] = {
            'url': rendered.url,
            'checked_at': rendered.checked_at,
            'visible_text_sha256': hashlib.sha256(rendered.text.encode()).hexdigest(),
            'review_signal': 'registration_soft_error' if registration_error else None,
        }
    return report


def observation_time(value):
    if isinstance(value, str) and 'T' in value and value.endswith('Z'):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
    return None


def valid_timestamp(value, checked_at):
    observed_at = observation_time(value)
    if observed_at is None or not isinstance(checked_at, str):
        return False
    try:
        return observed_at <= datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False


def link_observation(route, receipt, application):
    """Keep a supplied public application-step check separate from the primary check."""
    if not application or receipt['result'] != 'readable':
        return
    primary_urls = (receipt['url'], receipt['final_url'])
    if (application.source_url not in primary_urls or application.requested_url in primary_urls
            or not application.requested_url.startswith('https://') or not valid_timestamp(application.checked_at, receipt['checked_at'])):
        return
    actions = (route.get('editorial_review') or {}).get('actions', [])
    bound_urls = {source['url'] for source in route.get('sources', []) if source.get('url')}
    bound_urls.update(action['url'] for action in actions)
    if bound_urls and application.requested_url not in bound_urls:
        return
    step = summarize_observation(application.observation)
    receipt['application_check'] = {'url': application.requested_url, 'checked_at': application.checked_at, **step}
    if 'application_unpublished' in step['review_signals']:
        receipt['review_signals'].append('linked_application_unpublished')


def previous_observation(previous, key):
    observation = (previous or {}).get(key)
    return observation if isinstance(observation, dict) else {}


def discard_superseded_observations(previous, receipt):
    for key, signal in SECONDARY_SIGNALS.items():
        current = receipt.get(key)
        stored = previous_observation(previous, key)
        if not current or current['url'] != stored.get('url'):
            continue
        current_time = observation_time(current['checked_at'])
        stored_time = observation_time(stored.get('checked_at'))
        if stored_time is None or stored_time < current_time:
            continue
        # A replay of the same receipt is harmless. Conflicting evidence at the
        # same timestamp cannot establish which observation came later.
        if stored_time == current_time and all(stored.get(field) == value for field, value in current.items()):
            continue
        del receipt[key]
        if signal in receipt['review_signals']:
            receipt['review_signals'].remove(signal)


def review_state_changed(previous, receipt):
    # A primary-page check has no evidence that an earlier, separate step recovered.
    excluded = set(SECONDARY_SIGNALS.values())
    if set(previous.get('review_signals', [])) - excluded != set(receipt['review_signals']) - excluded:
        return True
    keys = ('url', 'final_url', 'http_status', 'result', 'retrieval_reason', 'review_signals')
    left, right = previous_observation(previous, 'application_check'), receipt.get('application_check')
    if right and any(left.get(key) != right.get(key) for key in keys):
        return True
    rendered = receipt.get('rendered_observation')
    previous_rendered = previous_observation(previous, 'rendered_observation')
    return bool(rendered) and previous_rendered.get('review_signal') != rendered.get('review_signal')


def retain_skipped_observations(previous, receipt):
    """Carry forward evidence with its old URL, timestamp and hash."""
    for key in SECONDARY_SIGNALS:
        stored = previous_observation(previous, key)
        if key not in receipt and stored:
            receipt[key] = {**stored, 'reobserved': False}


def check_route(route, checked_at, previous=None, fetcher=fetch_public, *, application=None, rendered=None):
    receipt = {"route_id": route["id"], "url": route["url"], "checked_at": checked_at,
               "scope": "automated_retrieval", "approved": False, "editorial_review_required": True}
    try:
        if rendered and not valid_timestamp(rendered.checked_at, checked_at):
            rendered = None
        receipt.update(summarize_observation(fetcher(route['url']), rendered))
        link_observation(route, receipt, application)
        discard_superseded_observations(previous, receipt)
        if receipt['truncated']:
            receipt["note"] = "Response exceeded the bounded read; no complete content comparison."
        if receipt['result'] != 'readable':
            same_failure = (
                previous
                and previous.get('final_url', receipt['final_url']) == receipt['final_url']
                and all(previous.get(key) == receipt[key] for key in ('result', 'http_status'))
                and previous.get('retrieval_reason', receipt['retrieval_reason']) == receipt['retrieval_reason']
                and not review_state_changed(previous, receipt)
            )
            receipt["candidate_reason"] = "unchanged_failure" if same_failure else "recheck_failed"
        elif previous is not None and previous.get("final_url") and previous["final_url"] != receipt['final_url']:
            receipt["candidate_reason"] = "destination_changed"
        elif previous is None or not previous.get("stable_content_sha256"):
            receipt["candidate_reason"] = "baseline_needed"
        elif previous["stable_content_sha256"] != receipt["stable_content_sha256"] or review_state_changed(previous, receipt):
            receipt["candidate_reason"] = "content_changed"
        else:
            receipt["candidate_reason"] = "unchanged"
    except Exception as error:
        receipt.update({"result": "error", "candidate_reason": "recheck_failed", "error": type(error).__name__})
        if previous and previous.get("result") == "error" and previous.get("error") == receipt["error"]:
            receipt["candidate_reason"] = "unchanged_failure"
    retain_skipped_observations(previous, receipt)
    kind = route.get("route_kind")
    past = route.get("status") in {"historical", "closed", "contributions", "paused", "no_route", "inquiry", "information"}
    secondary = past or route.get("ai_data_work") is False
    receipt["priority"] = "low" if secondary else "high" if kind == "named_listing" else "normal" if kind == "network_program" else "low"
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / "data/work-routes.json")
    parser.add_argument("--previous", type=Path, help="Previous candidate run, for stable-content comparisons")
    parser.add_argument("--route-id", action="append", default=[], help="Limit this research run to selected IDs")
    parser.add_argument("--output", type=Path, help="Write candidates here instead of stdout; cannot be inside data/ or dist/")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be between one and four")
    if args.output:
        output = args.output.resolve()
        if any(parent == output or parent in output.parents for parent in (ROOT / "data", ROOT / "dist")):
            parser.error("candidate output cannot replace reviewed data or published files")
    work = json.loads(args.work.read_text())
    rows = work["routes"]
    if args.route_id:
        wanted = set(args.route_id)
        rows = [row for row in rows if row["id"] in wanted]
        if {row["id"] for row in rows} != wanted:
            parser.error("unknown route ID")
    previous = {}
    if args.previous:
        previous = {receipt["route_id"]: receipt for receipt in json.loads(args.previous.read_text())["receipts"]}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        receipts = list(pool.map(lambda row: check_route(row, now, previous.get(row["id"], row.get("last_link_check"))), rows))
    report = {"schema_version": "1.0.0", "generated_at": now, "status": "candidates_only",
              "facts_modified": False, "method": "Bounded public GET; stable text/JobPosting diffs are review signals, not factual updates.",
              "receipts": receipts}
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
