"""Exercise the production Daily health check without network calls."""

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github/scripts"))
import check_daily_health
from check_daily_health import check_health


PAGE = "/daily/"
INDEX = "/daily/index.json"
JSON_FEED = "/daily/feed.json"
RSS = "/daily/feed.xml"
ORIGIN = "https://sciencetostartup.com"


def payloads(day):
    path = f"/daily/{day}/"
    url = ORIGIN + path
    page = (f'<div class="daily-scan" data-edition="{day}">'
            f'<time class="scan-issue" datetime="{day}"></time></div>')
    return {
        PAGE: page.encode(),
        INDEX: json.dumps({"latest_date": day, "snapshots": [{"date": day, "url": path}]}).encode(),
        JSON_FEED: json.dumps({"items": [{"id": url, "url": url}]}).encode(),
        RSS: f"<rss><channel><item><link>{url}</link><guid>{url}</guid></item></channel></rss>".encode(),
    }


class DailyHealthTests(unittest.TestCase):
    def test_scheduled_run_uses_pacific_selection_day_in_both_seasons(self):
        for scheduled, expected in (("2026-11-23T07:17:00Z", "2026-11-22"),
                                    ("2027-07-23T07:17:00Z", "2027-07-22")):
            with self.subTest(scheduled=scheduled):
                report = check_health(datetime.fromisoformat(scheduled), payloads(expected).__getitem__)
                self.assertEqual(report["expected_latest_date"], expected)
                self.assertEqual(report["status"], "fresh")

    def test_today_becomes_due_at_the_end_of_the_grace_period(self):
        fetch = payloads("2026-11-22").__getitem__
        before = check_health(datetime.fromisoformat("2026-11-23T19:59:59Z"), fetch)
        due = check_health(datetime.fromisoformat("2026-11-23T20:00:00Z"), fetch)
        self.assertEqual((before["expected_latest_date"], before["status"]), ("2026-11-22", "fresh"))
        self.assertEqual((due["expected_latest_date"], due["status"]), ("2026-11-23", "stale"))
        self.assertEqual(due["latest_date"], "2026-11-22")

    def test_an_early_edition_passes_and_a_future_edition_fails(self):
        now = datetime.fromisoformat("2026-11-23T17:00:00Z")
        early = check_health(now, payloads("2026-11-23").__getitem__)
        future = check_health(now, payloads("2026-11-24").__getitem__)
        self.assertEqual(early["status"], "fresh")
        self.assertEqual(future["status"], "future_date")

    def test_page_index_and_both_feeds_must_agree(self):
        now = datetime.fromisoformat("2026-11-23T20:00:00Z")
        for path in (PAGE, INDEX, JSON_FEED, RSS):
            with self.subTest(path=path):
                bodies = payloads("2026-11-23")
                bodies[path] = payloads("2026-11-22")[path]
                report = check_health(now, bodies.__getitem__)
                self.assertEqual(report["status"], "mismatch")
                self.assertEqual(report["endpoints"][path]["latest_date"], "2026-11-22")

    def test_http_failure_is_distinct_from_stale(self):
        now = datetime.fromisoformat("2026-11-23T20:00:00Z")
        bodies = payloads("2026-11-22")

        def fetch(path):
            if path == PAGE:
                raise HTTPError(ORIGIN + PAGE, 503, "Service Unavailable", None, None)
            return bodies[path]

        report = check_health(now, fetch)
        self.assertEqual(report["status"], "fetch_error")
        self.assertIn("503", report["endpoints"][PAGE]["error"])
        self.assertEqual(report["endpoints"][INDEX]["latest_date"], "2026-11-22")

    def test_malformed_content_is_distinct_from_stale(self):
        now = datetime.fromisoformat("2026-11-23T20:00:00Z")
        bad_page_date = payloads("2026-11-22")[PAGE].replace(b'datetime="2026-11-22"', b'datetime="2026-11-23"')
        for path, body in ((PAGE, b'<!DOCTYPE html><title>Error</title>'),
                           (PAGE, b"<![malformed[>"),
                           (PAGE, bad_page_date),
                           (INDEX, b'{"latest_date":"2026-11-22","snapshots":[]}'),
                           (JSON_FEED, b'<!DOCTYPE html><title>Error</title>'),
                           (JSON_FEED, b"[" * 2000 + b"null" + b"]" * 2000),
                           (RSS, b"<rss><channel>")):
            with self.subTest(path=path):
                bodies = payloads("2026-11-22")
                bodies[path] = body
                report = check_health(now, bodies.__getitem__)
                self.assertEqual(report["status"], "parse_error")
                self.assertEqual(report["endpoints"][path]["status"], "parse_error")

    def test_cli_writes_the_report_before_failing(self):
        now = datetime.fromisoformat("2026-11-23T20:00:00Z")
        bodies = payloads("2026-11-22")

        def unavailable(path):
            raise TimeoutError(path)

        for status, fetch in (("stale", bodies.__getitem__), ("fetch_error", unavailable)):
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                report_path = Path(tmp) / "monitor" / "daily-health.json"
                report = check_health(now, fetch)
                self.assertEqual(report["status"], status)
                with (
                    patch.object(sys, "argv", ["check_daily_health.py", "--output", str(report_path)]),
                    patch.object(check_daily_health, "check_health", return_value=report),
                    redirect_stdout(io.StringIO()) as stdout,
                ):
                    self.assertEqual(check_daily_health.main(), 1)
                self.assertEqual(json.loads(report_path.read_text()), report)
                self.assertEqual(json.loads(stdout.getvalue()), report)
