"""Offline OAI operational simulations. All metadata here is synthetic, not research."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_research_sources as checker
import research_intake as intake
from test_research_sources import Response, addresses


class OAIService:
    """1,300-record pages and opaque tokens invalidated at the next UTC day."""
    def __init__(self, records, day="2026-11-10", page_size=1300):
        self.records, self.day, self.page_size = records, day, page_size
        self.tokens, self.requests = {}, []

    def open(self, request, timeout):
        self.requests.append(request)
        params = {key: values[0] for key, values in parse_qs(urlsplit(request.full_url).query).items()}
        cursor = params.get("resumptionToken")
        if cursor:
            issued, params, start = self.tokens[cursor]
            if issued != self.day:
                return self.response(request.full_url, '<error code="badResumptionToken">expired</error>')
        else:
            start = 0
        rows = [row for row in self.records if params["from"] <= row["date"] <= params.get("until", self.day)]
        if not rows:
            return self.response(request.full_url, '<error code="noRecordsMatch">empty</error>')
        page = rows[start:start + self.page_size]
        body = "<ListRecords>" + "".join(self.record(row) for row in page)
        if start + len(page) < len(rows):
            token = "opaque-" + str(len(self.tokens))
            self.tokens[token] = self.day, params, start + len(page)
            body += "<resumptionToken>" + token + "</resumptionToken>"
        return self.response(request.full_url, body + "</ListRecords>")

    def response(self, url, body):
        return Response(('<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>' +
                         self.day + 'T12:00:00Z</responseDate>' + body + '</OAI-PMH>').encode(), url=url)

    @staticmethod
    def record(row):
        header = ('<header' + (' status="deleted"' if row.get("deleted") else '') + '><identifier>oai:arXiv.org:' +
                  escape(row["id"]) + '</identifier><datestamp>' + row["date"] + '</datestamp></header>')
        if row.get("deleted"):
            return '<record>' + header + '</record>'
        metadata = ('<metadata><arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/"><id>' + escape(row["id"]) +
                    '</id><title>' + escape(row.get("title", "Synthetic operational fixture")) + '</title>' +
                    '<version version="v1"><date>Fri, 1 Jan 2020 00:00:00 GMT</date></version>' +
                    ('<version version="v2"><date>Mon, 9 Nov 2026 00:00:00 GMT</date></version>' if row.get("replaced") else '') +
                    '</arXivRaw></metadata>')
        return '<record>' + header + metadata + '</record>'


class OAIReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name)
        self.row = {"id": "oai-updates", "adapter": "oai", "query": "2026-11-08", "limit": 50}
        self.service = OAIService([])

    def client(self, cache, checkpoint, hosts):
        return checker.PublicClient(cache, checkpoint, hosts, interval=0, opener=self.service,
                                    url_checker=lambda url, hosts: checker.check_public_url(url, hosts, resolver=addresses("8.8.8.8")))

    def run_intake(self, day="2026-11-10", pages=20):
        self.service.day = day
        at = datetime.fromisoformat(day + "T20:00:00+00:00")
        with patch.object(intake, "partitions", return_value=[self.row]), patch.object(intake, "PublicClient", side_effect=self.client):
            result = intake.run(ROOT, self.state, at, max_partitions=1, oai_pages=pages)
        return result["attempted"][0]

    def candidates(self):
        return json.loads((self.state / "candidates/oai-updates.json").read_text())["candidates"]

    def many_records(self, count=1301):
        self.service.records = [{"id": "2001." + str(index).zfill(5), "date": "2026-11-08"} for index in range(count)]

    def test_real_sized_first_page_and_next_page_work_without_credentials(self):
        self.many_records()
        with patch.dict(os.environ, {}, clear=True):
            result = self.run_intake()
        self.assertTrue(result["complete"])
        self.assertEqual(result["requests_made"], 2)
        self.assertEqual(result["last_completed_until"], "2026-11-09")
        self.assertEqual(len(self.candidates()), 1301)
        self.assertEqual(len({row["id"] for row in self.candidates()}), 1301)
        self.assertIn("resumptionToken=", self.service.requests[1].full_url)
        self.assertTrue(all(request.get_header("Authorization") is None for request in self.service.requests))

    def test_expired_daily_token_restarts_exact_window_and_keeps_candidate_ids(self):
        self.many_records()
        first = self.run_intake(pages=1)
        self.assertFalse(first["complete"])
        self.assertEqual(len(self.candidates()), 1300)
        # The query stays frozen when the host's clock moves, despite a newly
        # calculated rolling lookback in partitions(). Budget includes expiry.
        self.row["query"] = "2026-11-09"
        self.row["limit"] = 100
        resumed = self.run_intake("2026-11-11", pages=3)
        self.assertEqual(resumed["partition"]["query"], "2026-11-08/2026-11-09")
        self.assertEqual(resumed["partition"]["limit"], 50)
        self.assertTrue(resumed["window_complete"])
        self.assertFalse(resumed["complete"])
        self.assertEqual(resumed["requests_made"], 3)
        self.assertEqual(resumed["token_restarts"], 1)
        self.assertEqual(len(self.candidates()), 1301)
        restart = parse_qs(urlsplit(self.service.requests[2].full_url).query)
        self.assertEqual(restart["from"], ["2026-11-08"])
        self.assertEqual(restart["until"], ["2026-11-09"])
        final = self.run_intake("2026-11-11")
        self.assertTrue(final["complete"])
        self.assertEqual(len(self.candidates()), 1301)

    def test_interrupted_page_checkpoint_resumes_next_page_same_day(self):
        self.many_records()
        original_save = checker.PublicClient.save

        def save_then_interrupt(client):
            original_save(client)
            if any(progress.get("next") and len(progress["candidates"]) == 1300 for progress in client.state["cursors"].values()):
                raise SystemExit("synthetic process interruption after durable page checkpoint")

        with patch.object(checker.PublicClient, "save", save_then_interrupt), self.assertRaises(SystemExit):
            self.run_intake()
        self.assertEqual(len(self.service.requests), 1)
        result = self.run_intake()
        self.assertTrue(result["complete"])
        self.assertEqual(len(self.service.requests), 2)
        self.assertIn("resumptionToken=", self.service.requests[-1].full_url)
        self.assertEqual(len(self.candidates()), 1301)

    def test_lost_candidate_write_does_not_advance_watermark_and_is_repaired(self):
        self.many_records()
        original_write = intake.write_json

        def interrupt(path, value):
            if Path(path).parent.name == "candidates":
                raise SystemExit("synthetic interruption before candidate materialization")
            original_write(path, value)

        with patch.object(intake, "write_json", side_effect=interrupt), self.assertRaises(SystemExit):
            self.run_intake()
        ledger = json.loads((self.state / "intake-ledger.json").read_text())
        self.assertIsNone(ledger["partitions"]["oai-updates"]["last_completed_until"])
        request_count = len(self.service.requests)
        repaired = self.run_intake()
        self.assertTrue(repaired["complete"])
        self.assertEqual(len(self.service.requests), request_count)
        self.assertEqual(len(self.candidates()), 1301)
        # The candidate file is a rebuildable projection, including prior windows.
        (self.state / "candidates/oai-updates.json").unlink()
        self.run_intake()
        self.assertEqual(len(self.candidates()), 1301)

    def test_month_of_downtime_catches_old_work_replacement_and_deletion(self):
        self.service.records = [{"id": "2001.00001", "date": "2026-11-08"}, {"id": "2002.00002", "date": "2026-11-08"}]
        self.run_intake()
        self.service.records = [{"id": "2001.00001", "date": "2026-11-15", "replaced": True},
                                {"id": "2002.00002", "date": "2026-11-20", "deleted": True},
                                {"id": "2003.00003", "date": "2026-11-21"}]
        count = len(self.service.requests)
        result = self.run_intake("2026-12-10")
        self.assertTrue(result["complete"])
        self.assertEqual(result["last_completed_until"], "2026-12-09")
        first_catchup = parse_qs(urlsplit(self.service.requests[count].full_url).query)
        self.assertEqual(first_catchup["from"], ["2026-11-08"])
        candidates = {row["id"]: row for row in self.candidates()}
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates["oai:2001.00001"]["metadata_datestamp"], "2026-11-15")
        self.assertEqual([version["version"] for version in candidates["oai:2001.00001"]["versions"]], ["v1", "v2"])
        self.assertEqual(candidates["oai:2002.00002"]["metadata_status"], "deleted")
        self.assertTrue(all(row["status"] == "candidate" and not row["approved"] for row in candidates.values()))
        (self.state / "candidates/oai-updates.json").unlink()
        self.run_intake("2026-12-10")
        self.assertEqual({row["id"] for row in self.candidates()}, set(candidates))

    def test_missing_checkpoint_is_explicit_and_does_not_replace_prior_candidates(self):
        self.service.records = [{"id": "2001.00001", "date": "2026-11-08"}]
        self.run_intake()
        before = self.candidates()
        (self.state / "checkpoints/oai-updates.json").unlink()
        result = self.run_intake("2026-11-11")
        self.assertFalse(result["complete"])
        self.assertIn("checkpoint missing", result["error"])
        self.assertEqual(result["last_completed_until"], "2026-11-09")
        self.assertEqual(self.candidates(), before)

    def test_legacy_unbounded_query_retains_identity_and_candidates_after_expiry(self):
        self.many_records()
        window = "2026-11-10:1"
        client = self.client(self.state / "cache", self.state / "checkpoints/oai-updates.json", checker.ADAPTER_HOSTS["oai"])
        checker.discover(client, "oai", self.row["query"], pages=1, window=window)
        previous = {"partition": self.row, "partition_sha256": intake.partition_digest(self.row),
                    "configuration_sha256": intake.configuration_digest(self.row), "complete": False,
                    "attempted_at": "2026-11-10T20:00:00Z", "discovery_window": window, "discovery_generation": 1}
        checker.write_json(self.state / "intake-ledger.json", {"schema_version": "1.0.0", "partitions": {"oai-updates": previous}})
        result = self.run_intake("2026-11-11")
        restart = parse_qs(urlsplit(self.service.requests[2].full_url).query)
        self.assertEqual(restart["from"], ["2026-11-08"])
        self.assertNotIn("until", restart)
        self.assertTrue(result["complete"])
        self.assertEqual(result["last_completed_until"], "2026-11-10")
        self.assertEqual(len(self.candidates()), 1301)

    def test_empty_windows_advance_and_backward_clock_never_lowers_watermark(self):
        result = self.run_intake()
        self.assertTrue(result["complete"])
        self.assertEqual(result["candidates"], 0)
        result = self.run_intake("2026-11-07")
        self.assertEqual(result["last_completed_until"], "2026-11-09")
        self.assertEqual(len(self.service.requests), 1)

    def test_repeated_cursor_never_claims_completion(self):
        class Client:
            state = {"cursors": {}}
            def get(self, url):
                return {"result": "retrieved"}, b'<OAI-PMH><ListRecords><resumptionToken>same</resumptionToken></ListRecords></OAI-PMH>'
            def save(self):
                pass
        result = checker.discover(Client(), "oai", "2026-11-08/2026-11-09", pages=20, window="synthetic")
        self.assertFalse(result["complete"])
        self.assertEqual(result["requests_made"], 2)
        self.assertEqual(result["retry_reason"], "repeated_cursor_requires_operator_attention")

    def test_repeated_expiry_is_bounded_and_old_replay_cannot_restore_deleted_metadata(self):
        newer = {"id": "2001.00001", "date": "2026-11-09", "deleted": True}
        older = {"id": "2001.00001", "date": "2026-11-08"}

        class Client:
            def __init__(self):
                self.state, self.roots = {"cursors": {}}, 0
            def get(self, url):
                if "resumptionToken=" in url:
                    body = '<error code="badResumptionToken">expired</error>'
                else:
                    self.roots += 1
                    body = '<ListRecords>' + OAIService.record(newer if self.roots == 1 else older) + '<resumptionToken>cursor</resumptionToken></ListRecords>'
                return {"result": "retrieved"}, ('<OAI-PMH>' + body + '</OAI-PMH>').encode()
            def save(self):
                pass

        result = checker.discover(Client(), "oai", "2026-11-08/2026-11-09", pages=20, window="synthetic")
        self.assertFalse(result["complete"])
        self.assertEqual(result["requests_made"], 4)
        self.assertEqual(result["token_restarts"], 2)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["metadata_status"], "deleted")

    def test_http_deferral_or_malformed_page_does_not_advance_watermark(self):
        self.run_intake()
        for body, code, headers in ((b"busy", 503, {"Retry-After": "120"}),
                                    (b"<unexpected/>", 200, {})):
            count = len(self.service.requests)
            def failing_open(request, timeout):
                self.service.requests.append(request)
                return Response(body, code=code, headers=headers, url=request.full_url)

            with patch.object(self.service, "open", side_effect=failing_open):
                result = self.run_intake("2026-11-11")
            self.assertFalse(result["complete"])
            self.assertEqual(result["last_completed_until"], "2026-11-09")
            self.assertEqual(len(self.service.requests) - count, 1)
            if code == 503:
                self.assertEqual(result["retry_reason"], "request_deferred")
            else:
                self.assertEqual(result["error_type"], "ValueError")

    def test_public_pagination_exception_does_not_allow_credential_urls(self):
        valid = "https://oaipmh.arxiv.org/oai?verb=ListRecords&resumptionToken=opaque"
        checker.check_public_url(valid, checker.ADAPTER_HOSTS["oai"], resolver=addresses("8.8.8.8"))
        for url in (valid + "&api_key=secret", valid.replace("oaipmh.arxiv.org", "example.org"),
                    valid.replace("ListRecords", "GetRecord"), valid.replace("/oai?", "/other?")):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.check_public_url(url, resolver=addresses("8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
