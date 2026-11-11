import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_intake as intake
import check_research_sources as checker
from research_intake import partitions, select_partitions


class ResearchIntakeTests(unittest.TestCase):
    def test_same_host_throttle_survives_partition_client_changes(self):
        from test_research_sources import Opener, Response
        elapsed, sleeps = [0.0], []
        def sleep(seconds):
            sleeps.append(seconds)
            elapsed[0] += seconds
        opener = Opener([Response(b'fixture', url='https://export.arxiv.org/api/query') for _ in range(2)])
        def client(cache, checkpoint, hosts):
            return checker.PublicClient(cache, checkpoint, hosts, interval=3.1, opener=opener,
                sleep=sleep, clock=lambda: elapsed[0], url_checker=lambda url, hosts: 'export.arxiv.org')
        rows = [{'id': 'fixture-' + str(i), 'adapter': 'arxiv', 'query': 'fixture-' + str(i), 'limit': 2}
                for i in range(2)]
        with tempfile.TemporaryDirectory() as temporary, patch.object(intake, 'partitions', return_value=rows), \
                patch.object(intake, 'PublicClient', side_effect=client), \
                patch.object(checker, 'parse_arxiv', return_value=([], None)):
            result = intake.run(ROOT, temporary, datetime(2026, 11, 10, tzinfo=timezone.utc), 2)
        self.assertEqual(result['completed_partitions'], 2)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [3.1])

    def test_scope_includes_old_years_and_replacements(self):
        config = json.loads((ROOT / "data/research/intake.json").read_text())
        rows = partitions(config, datetime(2026, 11, 9, tzinfo=timezone.utc))
        self.assertTrue(any(r["adapter"] == "oai" for r in rows))
        self.assertTrue(any(r["id"].startswith("arxiv-2020-") for r in rows))
        self.assertTrue(any(r["id"].startswith("arxiv-2026-") for r in rows))
        self.assertEqual(len({r["id"] for r in rows}), len(rows))

    def test_blocked_partition_retains_reason_and_resumes_without_approval(self):
        row = {"id": "fixture-blocked", "adapter": "arxiv", "query": "fixture only", "limit": 2}
        blocked = {"complete": False, "candidates": [], "requests_made": 1,
                   "retry_reason": "request_blocked", "token_restarts": 0}
        recovered = {"complete": True, "candidates": [{"id": "metadata-only-fixture"}],
                     "requests_made": 1, "retry_reason": None, "token_restarts": 0}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(intake, "partitions", return_value=[row]), \
                patch.object(intake, "discover", side_effect=[blocked, recovered]):
            first = intake.run(ROOT, temporary, datetime(2026, 11, 10, tzinfo=timezone.utc), 1)
            failed = json.loads((Path(temporary) / "intake-ledger.json").read_text())["partitions"][row["id"]]
            self.assertEqual(failed["retry_reason"], "request_blocked")
            self.assertEqual(failed["requests_made"], 1)
            self.assertEqual(failed["token_restarts"], 0)
            self.assertFalse(failed["complete"])
            self.assertFalse(failed["approved"])
            self.assertEqual(first["completed_partitions"], 0)
            second = intake.run(ROOT, temporary, datetime(2026, 11, 11, tzinfo=timezone.utc), 1)
            resumed = second["attempted"][0]
            self.assertEqual(resumed["discovery_window"], failed["discovery_window"])
            self.assertEqual(resumed["partition_sha256"], failed["partition_sha256"])
            self.assertIsNone(resumed["retry_reason"])
            self.assertFalse(resumed["approved"])
            self.assertFalse(second["facts_modified"])
            self.assertEqual(second["completed_partitions"], 1)

    def test_fair_queue_prioritizes_unattempted_partitions(self):
        rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        previous = {"a": {"attempted_at": "2026-11-09T00:00:00Z"}}
        self.assertEqual([r["id"] for r in select_partitions(rows, previous, 2)], ["b", "c"])
        with self.assertRaises(ValueError):
            select_partitions(rows, previous, 0)

    def run_pages(self, temporary, days, row=None, crash=False):
        starts = []
        row = row or {"id": "fixture", "adapter": "arxiv", "query": "fixture only", "limit": 2}

        class Client:
            def __init__(self, cache, checkpoint, hosts):
                self.path = Path(checkpoint)
                self.state = json.loads(self.path.read_text()) if self.path.exists() else {"cursors": {}}

            def save(self):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.state))

            def get(self, url):
                query = parse_qs(urlsplit(url).query)
                start = int(query.get("start", query.get("resumptionToken", ["0"]))[0])
                starts.append(start)
                return {"result": "retrieved"}, str(start).encode()

        def parse_page(body):
            start = int(body)
            return [{"id": "fixture-" + str(i)} for i in range(start, min(start + 2, 3))], "2" if row["adapter"] == "oai" and start == 0 else None

        original_write = intake.write_json

        def write(path, value):
            if crash and Path(path).parent.name == "candidates":
                raise SystemExit("fixture process interruption after checkpoint")
            original_write(path, value)

        results = []
        with patch.object(intake, "partitions", return_value=[row]), patch.object(intake, "PublicClient", Client), \
                patch.object(checker, "parse_arxiv", side_effect=parse_page), patch.object(checker, "parse_oai", side_effect=parse_page), \
                patch.object(intake, "write_json", side_effect=write):
            for day in days:
                results.append(intake.run(ROOT, temporary, datetime(2026, 11, day, 20, tzinfo=timezone.utc), 1))
        return starts, results

    def test_partial_pagination_survives_days_and_refreshes_only_after_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            starts, results = self.run_pages(temporary, [9, 10, 11])
            self.assertEqual(starts, [0, 2, 0])
            self.assertEqual([result["completed_partitions"] for result in results], [0, 1, 0])
            self.assertEqual([result["attempted"][0]["candidates"] for result in results], [2, 3, 2])

    def test_interrupted_page_checkpoint_retains_its_durable_run_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SystemExit):
                self.run_pages(temporary, [9], crash=True)
            starts, results = self.run_pages(temporary, [10])
            self.assertEqual(starts, [2])
            self.assertEqual(results[0]["completed_partitions"], 1)

    def test_configuration_change_starts_a_new_query_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.run_pages(temporary, [9])
            changed = {"id": "fixture", "adapter": "arxiv", "query": "changed fixture only", "limit": 2}
            starts, results = self.run_pages(temporary, [10], row=changed)
            self.assertEqual(starts, [0])
            self.assertEqual(results[0]["attempted"][0]["discovery_generation"], 2)

    def test_oai_priority_retains_a_fair_queue_for_old_years(self):
        rows = [{"id": "oai-updates", "adapter": "oai"}] + [
            {"id": "arxiv-" + str(year), "adapter": "arxiv"} for year in range(2026, 2019, -1)]
        previous, visited = {}, set()
        for attempt in range(7):
            selected = select_partitions(rows, previous, 2)
            self.assertEqual(selected[0]["id"], "oai-updates")
            visited.add(selected[1]["id"])
            for row in selected:
                previous[row["id"]] = {"attempted_at": str(attempt)}
        self.assertEqual(visited, {"arxiv-" + str(year) for year in range(2020, 2027)})


if __name__ == "__main__":
    unittest.main()
