#!/usr/bin/env python3
"""Collect public-source check candidates; never edit reviewed editorial facts.

Run daily, then let an editor inspect material changes. HTTP 200 is not a
readability or hiring assertion. Response bodies stay out of the output.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
BLOCKED_TEXT = re.compile(r"request unsuccessful|access (?:is )?denied|verify (?:you are|that you are) (?:a )?human|^just a moment|attention required.*cloudflare", re.I)
SHELL_TEXT = re.compile(r"you need to enable javascript|enable javascript to (?:run|view)|javascript is required", re.I)


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
    challenge = bool(BLOCKED_TEXT.search(visible)) and (len(visible) < 4000 or "request unsuccessful" in visible.lower())
    if len(visible) < 120 and re.search(r"_Incapsula_Resource|captcha", html[:4000], re.I):
        challenge = True
    shell = bool(SHELL_TEXT.search(visible)) and not jobs
    readable = not challenge and not shell and (bool(jobs) or len(visible) >= 120)
    return {
        "readable": readable,
        "challenge": challenge,
        "shell": shell,
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
        return response.code, response.geturl(), body[:MAX_BYTES], len(body) > MAX_BYTES


def check_route(route, checked_at, previous=None, fetcher=fetch_public):
    receipt = {"route_id": route["id"], "url": route["url"], "checked_at": checked_at,
               "scope": "automated_retrieval", "approved": False, "editorial_review_required": True}
    try:
        status, final_url, body, truncated = fetcher(route["url"])
        summary = source_summary(body)
        if status in {401, 403, 407, 429} or summary["challenge"]:
            result = "blocked"
        elif status in {404, 410}:
            result = "not_found"
        elif status >= 400:
            result = "unavailable"
        elif summary["shell"] or not summary["readable"]:
            result = "unreadable_shell"
        else:
            result = "readable"
        receipt.update({"http_status": status, "final_url": final_url, "result": result,
                        "response_sha256": hashlib.sha256(body).hexdigest(), "truncated": truncated,
                        **{key: summary[key] for key in ("stable_content_sha256", "extraction", "document_titles")}})
        if truncated:
            receipt["result"] = "unavailable"
            receipt["note"] = "Response exceeded the bounded read; no complete content comparison."
        if result != "readable" or truncated:
            same_failure = previous and previous.get("result") == receipt["result"] and previous.get("http_status") == status and previous.get("final_url", final_url) == final_url
            receipt["candidate_reason"] = "unchanged_failure" if same_failure else "recheck_failed"
        elif previous is not None and previous.get("final_url") and previous["final_url"] != final_url:
            receipt["candidate_reason"] = "destination_changed"
        elif previous is None or not previous.get("stable_content_sha256"):
            receipt["candidate_reason"] = "baseline_needed"
        elif previous["stable_content_sha256"] != receipt["stable_content_sha256"]:
            receipt["candidate_reason"] = "content_changed"
        else:
            receipt["candidate_reason"] = "unchanged"
    except Exception as error:
        receipt.update({"result": "error", "candidate_reason": "recheck_failed", "error": type(error).__name__})
        if previous and previous.get("result") == "error" and previous.get("error") == receipt["error"]:
            receipt["candidate_reason"] = "unchanged_failure"
    kind = route.get("route_kind")
    past = route.get("status") in {"historical", "closed", "contributions", "paused", "no_route", "inquiry", "information"}
    secondary = past or route.get("ai_data_work") is False
    receipt["priority"] = "low" if secondary else "high" if kind == "named_listing" else "normal" if kind == "network_program" else "low"
    if route["id"] == "appen.work.sage-media" and receipt["candidate_reason"] != "unchanged":
        receipt["priority"] = "homepage"
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
