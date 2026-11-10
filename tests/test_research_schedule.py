import json
import os
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from research_schedule import (activate_candidate, edition_window, prepare_candidate,
                               read_journal, record_approval, schedule_status, source_in_window, state_lock)
from test_research_report import empty_graph, test_report


def context():
    return {"graph": empty_graph(), "report": test_report(), "identity": {"name": "Fixture only"},
            "policy": {"mode": "prepare_only"}}


class ScheduleTests(unittest.TestCase):
    def test_pacific_summer_and_winter_hours(self):
        self.assertEqual(edition_window("2026-07-06")["publish_at"], "2026-07-06T16:00:00Z")
        self.assertEqual(edition_window("2026-11-09")["publish_at"], "2026-11-09T17:00:00Z")
        self.assertEqual(edition_window("2026-11-09")["source_cutoff"], "2026-11-07T01:00:00Z")

    def test_dst_transition_uses_calendar_local_cutoff(self):
        spring = edition_window("2026-03-09")
        self.assertEqual(spring["publish_at"], "2026-03-09T16:00:00Z")
        self.assertEqual(spring["source_cutoff"], "2026-03-07T01:00:00Z")
        fall = edition_window("2026-11-02")
        self.assertEqual(fall["source_cutoff"], "2026-10-31T00:00:00Z")
        self.assertEqual(fall["publish_at"], "2026-11-02T17:00:00Z")

    def test_daily_prepare_is_sixteen_pacific(self):
        self.assertFalse(schedule_status("2026-11-10T23:59:59Z")["prepare_due"])
        self.assertTrue(schedule_status("2026-11-11T00:00:00Z")["prepare_due"])
        self.assertFalse(schedule_status("2026-11-11T00:01:00Z", "2026-11-11T00:00:00Z")["prepare_due"])

    def test_monday_boundary(self):
        before = schedule_status("2026-11-09T16:59:59Z")
        after = schedule_status("2026-11-09T17:00:00Z")
        self.assertEqual(before["next_edition"]["edition_id"], "2026-11-09")
        self.assertEqual(after["next_edition"]["edition_id"], "2026-11-16")
        self.assertEqual(after["latest_due_edition"]["edition_id"], "2026-11-09")

    def test_naive_dates_and_non_monday_are_rejected(self):
        with self.assertRaises(ValueError):
            schedule_status("2026-11-09T17:00:00")
        with self.assertRaises(ValueError):
            edition_window("2026-11-10")
        with self.assertRaises(ValueError):
            source_in_window("2026-11-06", edition_window("2026-11-09"))

    def test_cutoff_is_inclusive_to_the_second(self):
        window = edition_window("2026-11-09")
        self.assertTrue(source_in_window("2026-11-07T01:00:00Z", window))
        self.assertFalse(source_in_window("2026-11-07T01:00:01Z", window))

    def test_retry_resumes_same_candidate_and_approval_binds_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            second = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T21:00:00Z")
            self.assertEqual(first, second)
            self.assertEqual(len(read_journal(temporary)), 1)
            receipt = {"candidate_sha256": "b" * 64, "release_id": "test-fixture", "decision": "approved",
                       "approved_by": "Fixture only", "rationale": "Fixture only", "approved_on": "2026-11-08T22:00:00Z"}
            with self.assertRaises(ValueError):
                record_approval(temporary, first["candidate_sha256"], receipt, "2026-11-08T23:00:00Z")
            result = activate_candidate(temporary, first["candidate_sha256"], "2026-11-09T17:00:00Z")
            self.assertEqual(result["status"], "held")
            self.assertFalse((Path(temporary) / "active.json").exists())

    def test_mutated_candidate_does_not_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            path = Path(temporary) / "candidates" / f"{candidate['candidate_sha256']}.json"
            candidate["snapshot"]["report"]["title"] = "Changed"
            path.write_text(json.dumps(candidate))
            with self.assertRaises(ValueError):
                activate_candidate(temporary, candidate["candidate_sha256"], "2026-11-09T17:00:00Z")

    def test_live_lock_is_not_stolen(self):
        with tempfile.TemporaryDirectory() as temporary:
            with state_lock(temporary):
                with self.assertRaises(RuntimeError):
                    with state_lock(temporary):
                        pass

    def test_stale_lock_is_recovered_only_for_dead_local_pid(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scheduler.lock"
            path.write_text(json.dumps({"host": socket.gethostname(), "pid": 123456789, "token": "old"}))
            with patch("research_schedule.os.kill", side_effect=ProcessLookupError):
                with state_lock(temporary):
                    self.assertEqual(json.loads(path.read_text())["pid"], os.getpid())
            self.assertFalse(path.exists())

    def test_journal_tamper_and_partial_tail_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            path = Path(temporary) / "journal.jsonl"
            raw = path.read_text()
            path.write_text(raw.replace('"sequence":1', '"sequence":2'))
            with self.assertRaises(ValueError):
                read_journal(temporary)
            path.write_text(raw[:-1])
            with self.assertRaises(ValueError):
                read_journal(temporary)

    def test_old_candidate_cannot_supersede_newer_activation(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            from research_schedule import _append
            with state_lock(temporary):
                _append(temporary, "activated", {"candidate_sha256": "c" * 64, "edition_id": "2026-11-16"}, "2026-11-16T17:00:00Z")
            with self.assertRaises(ValueError):
                activate_candidate(temporary, candidate["candidate_sha256"], "2026-11-16T17:00:00Z")


if __name__ == "__main__":
    unittest.main()
