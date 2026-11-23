#!/usr/bin/env python3
"""Check the public Daily page, archive index, and feeds."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from http.client import HTTPException
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


ORIGIN = "https://sciencetostartup.com"
PACIFIC = ZoneInfo("America/Los_Angeles")
AUTOMATION_TARGET = time(8)
PUBLICATION_GRACE = timedelta(hours=4)
MAX_BYTES = 4 * 1024 * 1024


def fetch(path):
    request = Request(ORIGIN + path, headers={"User-Agent": "ScienceToStartup Daily health monitor",
                                              "Cache-Control": "no-cache"})
    with urlopen(request, timeout=15) as response:
        if response.status != 200 or response.geturl() != request.full_url:
            raise OSError(f"Unexpected HTTP response ({response.status}, {response.geturl()})")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise OSError("Response exceeds monitoring size limit")
    return payload


def edition_date(value):
    day = date.fromisoformat(value)
    if value != day.isoformat():
        raise ValueError("Expected YYYY-MM-DD selection date")
    return day


def date_from_url(url):
    match = re.fullmatch(re.escape(ORIGIN) + r"/daily/([0-9]{4}-[0-9]{2}-[0-9]{2})/", url)
    if not match:
        raise ValueError("Expected a canonical Daily snapshot URL")
    return edition_date(match[1])


class DailyPageDates(HTMLParser):
    def __init__(self):
        super().__init__()
        self.editions = []
        self.issue_dates = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "div" and "daily-scan" in classes:
            self.editions.append(attrs.get("data-edition"))
        if tag == "time" and "scan-issue" in classes:
            self.issue_dates.append(attrs.get("datetime"))


def latest_page(payload):
    page = DailyPageDates()
    try:
        page.feed(payload.decode("utf-8"))
        page.close()
    except AssertionError as error:
        raise ValueError("Malformed Daily HTML") from error
    if len(page.editions) != 1 or page.editions != page.issue_dates:
        raise ValueError("Missing or inconsistent Daily page edition date")
    return edition_date(page.editions[0])


def latest_index(payload):
    index = json.loads(payload)
    day = edition_date(index["latest_date"])
    latest = index["snapshots"][0]
    if latest["date"] != day.isoformat() or latest["url"] != f"/daily/{day}/":
        raise ValueError("Latest date and first archive entry disagree")
    return day


def latest_json_feed(payload):
    latest = json.loads(payload)["items"][0]
    if latest["id"] != latest["url"]:
        raise ValueError("Latest JSON Feed ID and URL disagree")
    return date_from_url(latest["url"])


def latest_rss(payload):
    root = ET.fromstring(payload)
    if root.tag != "rss":
        raise ValueError("Expected an RSS document")
    latest = root.find("channel/item")
    if latest is None or latest.findtext("guid") != latest.findtext("link"):
        raise ValueError("Missing or inconsistent latest RSS entry")
    return date_from_url(latest.findtext("link"))


def check_endpoint(path, parse, fetcher):
    try:
        payload = fetcher(path)
    except (OSError, HTTPException) as error:
        return {"status": "fetch_error", "error": str(error)}
    try:
        latest = parse(payload)
    except (ValueError, TypeError, LookupError, RecursionError, ET.ParseError) as error:
        return {"status": "parse_error", "error": str(error)}
    return {"status": "ok", "latest_date": latest.isoformat()}


def check_health(now, fetcher=fetch):
    if now.utcoffset() is None:
        raise ValueError("Health check requires a timezone-aware time")
    local = now.astimezone(PACIFIC)
    today = local.date()
    cutoff = datetime.combine(today, AUTOMATION_TARGET, PACIFIC) + PUBLICATION_GRACE
    due = today if local >= cutoff else today - timedelta(days=1)
    endpoints = {
        path: check_endpoint(path, parse, fetcher) for path, parse in (
            ("/daily/", latest_page),
            ("/daily/index.json", latest_index),
            ("/daily/feed.json", latest_json_feed),
            ("/daily/feed.xml", latest_rss),
        )
    }
    statuses = {endpoint["status"] for endpoint in endpoints.values()}
    report = {"checked_at": now.astimezone(timezone.utc).isoformat(), "timezone": PACIFIC.key,
              "target_local_time": AUTOMATION_TARGET.isoformat(), "grace_hours": PUBLICATION_GRACE.total_seconds() / 3600,
              "expected_latest_date": due.isoformat(), "endpoints": endpoints}
    if "fetch_error" in statuses:
        return {**report, "status": "fetch_error"}
    if "parse_error" in statuses:
        return {**report, "status": "parse_error"}
    dates = {date.fromisoformat(endpoint["latest_date"]) for endpoint in endpoints.values()}
    if len(dates) != 1:
        return {**report, "status": "mismatch"}
    latest = dates.pop()
    status = "fresh"
    if latest < due:
        status = "stale"
    elif latest > today:
        status = "future_date"
    return {**report, "status": status, "latest_date": latest.isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check_health(datetime.now(timezone.utc))
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "fresh" else 1


if __name__ == "__main__":
    raise SystemExit(main())
