import copy
import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from research_schedule import (activate_candidate, edition_window, load_edition, main, prepare_candidate,
                               read_journal, record_approval, resolve_edition_reference, schedule_status,
                               source_in_window, state_lock)
from test_research_report import approved_graph, empty_graph, test_report


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

    def test_cli_due_prepares_current_edition_and_daily_prepares_upcoming(self):
        with tempfile.TemporaryDirectory() as temporary:
            def run(action, now, *extra):
                output = io.StringIO()
                argv = ["research_schedule.py", action, "--state-directory", temporary, "--now", now, *extra]
                with patch("sys.argv", argv), patch("research_report.build_context", return_value=context()), redirect_stdout(output):
                    main()
                return json.loads(output.getvalue())

            due = run("prepare-due", "2026-11-09T17:00:00Z")
            daily = run("prepare", "2026-11-09T17:00:00Z")
            catchup = run("prepare", "2026-11-11T20:00:00Z", "--due")
            self.assertEqual(due["identity"]["edition_date"], "2026-11-09")
            self.assertEqual(daily["identity"]["edition_date"], "2026-11-16")
            self.assertEqual(catchup["candidate_sha256"], due["candidate_sha256"])
            self.assertEqual(due["prepared_on"], "2026-11-09T17:00:00Z")
            self.assertEqual(catchup["prepared_on"], due["prepared_on"])
            self.assertEqual(catchup["publication"], "not_published")

    def test_due_selection_on_dst_monday_and_missed_run_is_truthful(self):
        for now, edition in (("2026-03-09T16:00:00Z", "2026-03-09"),
                             ("2026-11-02T17:00:00Z", "2026-11-02")):
            self.assertEqual(schedule_status(now)["latest_due_edition"]["edition_date"], edition)
        with tempfile.TemporaryDirectory() as temporary:
            late = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-11T20:00:00Z")
            self.assertTrue(late["prepared_after_window"])
            self.assertEqual(late["prepared_on"], "2026-11-11T20:00:00Z")
            self.assertEqual(late["identity"]["window"]["publish_at"], "2026-11-09T17:00:00Z")
            self.assertEqual(read_journal(temporary)[0]["at"], "2026-11-11T20:00:00Z")
            self.assertEqual(late["publication"], "not_published")

    def test_new_edition_identity_invalidates_old_archive_without_mutating_inputs(self):
        supplied = context()
        supplied["report"].update({"edition_date": "2026-11-02", "release_id": "research-2026-11-02.1",
                                    "status": "published", "archive": {"status": "published", "doi": "10.1234/old",
                                    "release_id": "research-2026-11-02.1", "reserved_doi": "10.1234/old",
                                    "artifact_sha256": "a" * 64, "confirmed_on": "2026-11-02T18:00:00Z"}})
        supplied["graph"] = approved_graph()
        supplied["roles"] = {"coordinator": {"reviewer_type": "ai", "name": "Test fixture only"}}
        original = copy.deepcopy(supplied)
        with tempfile.TemporaryDirectory() as temporary:
            candidate = prepare_candidate(supplied, temporary, "2026-11-09", "2026-11-10T20:00:00Z")
            report = candidate["snapshot"]["report"]
            self.assertEqual(report["release_id"], "research-2026-11-09.1")
            self.assertEqual(report["edition_date"], "2026-11-09")
            self.assertEqual(report["source_cutoff"], "2026-11-07T01:00:00Z")
            self.assertEqual(report["archive"], {"status": "not_published", "doi": None, "record_url": None})
            self.assertEqual(report["status"], "prepared")
            self.assertEqual(report["updated_on"], original["report"]["updated_on"])
            self.assertEqual(candidate["snapshot"]["graph"], original["graph"])
            self.assertEqual(candidate["snapshot"]["roles"], original["roles"])
            self.assertEqual(supplied, original)
            self.assertIn("roles", candidate["identity"]["bindings"])
            self.assertFalse(any("prepared_on" in candidate["snapshot"][key] for key in candidate["snapshot"]))
            # Later verification dates are retained, never backdated to Friday.
            self.assertEqual(candidate["snapshot"]["graph"]["reviews"][0]["reviewed_on"], "2026-11-09T20:00:00Z")
            supplied["roles"]["coordinator"]["name"] = "Changed fixture only"
            changed = prepare_candidate(supplied, temporary, "2026-11-09", "2026-11-10T21:00:00Z")
            self.assertNotEqual(changed["candidate_sha256"], candidate["candidate_sha256"])

    def test_unchanged_facts_still_create_distinct_editions_and_older_inputs_survive(self):
        supplied = context()
        with tempfile.TemporaryDirectory() as temporary:
            first = prepare_candidate(supplied, temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            second = prepare_candidate(supplied, temporary, "2026-11-16", "2026-11-15T20:00:00Z")
            self.assertNotEqual(first["candidate_sha256"], second["candidate_sha256"])
            self.assertEqual(first["snapshot"]["graph"], second["snapshot"]["graph"])
            self.assertEqual(first["snapshot"]["report"]["sections"], second["snapshot"]["report"]["sections"])
            supplied["report"]["title"] = "Live report changed after freezing"
            self.assertEqual(load_edition(temporary, "2026-11-09"), first["snapshot"])
            manifest = Path(temporary) / "editions" / "2026-11-09" / f"{first['candidate_sha256']}.json"
            reference = json.loads(manifest.read_text())
            self.assertEqual(resolve_edition_reference(temporary, reference), first["snapshot"])
            self.assertEqual(reference["publication"], "not_published")
            with self.assertRaises(ValueError):
                load_edition(temporary, "2026-11-16", first["candidate_sha256"])

    def test_nested_archives_become_compact_verified_snapshot_references(self):
        supplied = context()
        older = context()
        older["report"].update({"edition_date": "2026-11-02", "release_id": "research-2026-11-02.1",
                                "status": "published"})
        oldest = context()
        oldest["report"].update({"edition_date": "2026-10-26", "release_id": "research-2026-10-26.1",
                                 "status": "published"})
        older["report"]["editions"] = [{"release_id": oldest["report"]["release_id"], "status": "published", **oldest}]
        supplied["report"]["editions"] = [{"release_id": older["report"]["release_id"], "status": "published", **older}]
        with tempfile.TemporaryDirectory() as temporary:
            candidate = prepare_candidate(supplied, temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            reference = candidate["snapshot"]["report"]["editions"][0]
            self.assertNotIn("report", reference)
            frozen = resolve_edition_reference(temporary, reference)
            self.assertEqual(frozen["report"]["release_id"], "research-2026-11-02.1")
            oldest_reference = frozen["report"]["editions"][0]
            self.assertNotIn("report", oldest_reference)
            self.assertEqual(resolve_edition_reference(temporary, oldest_reference)["report"]["release_id"], "research-2026-10-26.1")
            path = Path(temporary) / "snapshots" / f"{reference['snapshot_sha256']}.json"
            path.write_text('{}')
            with self.assertRaises(ValueError):
                resolve_edition_reference(temporary, reference)

    def test_actual_ai_coordinator_can_approve_only_after_quality_passes(self):
        scientific_pass = {"ready": False, "archival_ready": True, "reasons": ["Actual archive missing"]}
        with tempfile.TemporaryDirectory() as temporary:
            with patch("research_report.publication_gate", return_value=scientific_pass):
                candidate = prepare_candidate(context(), temporary, "2026-11-09", "2026-11-08T20:00:00Z")
                receipt = {"candidate_sha256": candidate["candidate_sha256"], "release_id": candidate["identity"]["release_id"],
                           "decision": "approved", "approved_by": "Test AI coordinator fixture only", "reviewer_type": "ai",
                           "role": "coordinator", "invocation_id": "test-only-coordinator", "method": "final_quality_review",
                           "fixture": False, "rationale": "Test fixture only", "approved_on": "2026-11-08T21:00:00Z"}
                approval = record_approval(temporary, candidate["candidate_sha256"], receipt, "2026-11-08T22:00:00Z")
                self.assertEqual(approval["payload"]["receipt"]["reviewer_type"], "ai")
                self.assertEqual(record_approval(temporary, candidate["candidate_sha256"], receipt, "2026-11-08T23:00:00Z"), approval)
            with self.assertRaises(ValueError):
                record_approval(temporary, candidate["candidate_sha256"], receipt, "2026-11-08T23:00:00Z")

    def test_early_activation_holds_and_delayed_activation_uses_actual_time(self):
        supplied = context()
        supplied["policy"]["mode"] = "publish_enabled"
        gate = {"ready": True, "archival_ready": True, "reasons": []}
        with tempfile.TemporaryDirectory() as temporary, patch("research_report.publication_gate", return_value=gate):
            candidate = prepare_candidate(supplied, temporary, "2026-11-09", "2026-11-08T20:00:00Z")
            receipt = {"candidate_sha256": candidate["candidate_sha256"], "release_id": candidate["identity"]["release_id"],
                       "decision": "approved", "approved_by": "Test AI coordinator fixture only", "reviewer_type": "ai",
                       "role": "coordinator", "invocation_id": "test-only-coordinator", "method": "final_quality_review",
                       "fixture": False, "rationale": "Test fixture only", "approved_on": "2026-11-08T21:00:00Z"}
            record_approval(temporary, candidate["candidate_sha256"], receipt, "2026-11-08T22:00:00Z")
            early = activate_candidate(temporary, candidate["candidate_sha256"], "2026-11-09T16:59:59Z")
            self.assertEqual(early["status"], "held")
            self.assertFalse((Path(temporary) / "active.json").exists())
            delayed = activate_candidate(temporary, candidate["candidate_sha256"], "2026-11-11T20:00:00Z")
            self.assertEqual(delayed["status"], "activated_locally")
            self.assertEqual(delayed["activation_timing"], "delayed")
            self.assertEqual(delayed["activated_on"], "2026-11-11T20:00:00Z")
            self.assertEqual(delayed["scheduled_publish_at"], "2026-11-09T17:00:00Z")
            self.assertEqual(delayed["publication"], "not_published")
            self.assertFalse(delayed["external_mutations"])

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
