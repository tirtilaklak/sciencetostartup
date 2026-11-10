"""Synthetic operational fixtures only; never research evidence or approvals."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_schedule as schedule
from research_graph import GraphValidationError, coverage_summary, digest, stable_json, validate_graph
from research_report import canonical_hash
from test_research_report import approved_graph, test_report

NOW = "2026-11-10T20:00:00Z"


def freeze(graph, identifiers):
    """Change the declared inventory and its flags/hash together, as a job can."""
    identifiers = sorted(identifiers)
    for entity in graph["entities"]:
        entity["eligible_core"] = entity["id"] in identifiers
    graph["coverage"]["frozen_core"] = {
        "entity_ids": identifiers, "frozen_on": "2026-11-08T00:00:00Z" if identifiers else None,
        "source_cutoff": "2026-11-07T01:00:00Z" if identifiers else None,
        "sha256": digest(stable_json(identifiers)) if identifiers else None}
    return graph


def supplied_context():
    graph = approved_graph()
    pending = copy.deepcopy(graph["entities"][0])
    pending.update(id="fixture-pending", kind="organization", status="candidate", review_depth="metadata",
                   disposition="pending", assertion_ids=[], disposition_reason="Synthetic operational fixture only.")
    graph["entities"].append(pending)
    freeze(graph, [entity["id"] for entity in graph["entities"]])
    return {"graph": graph, "report": test_report(), "identity": {"name": "Synthetic operational fixture only"},
            "policy": {"mode": "prepare_only"}}


def add_core(context):
    expanded = copy.deepcopy(context)
    added = copy.deepcopy(expanded["graph"]["entities"][1])
    added["id"] = "fixture-added"
    expanded["graph"]["entities"].append(added)
    freeze(expanded["graph"], [entity["id"] for entity in expanded["graph"]["entities"]])
    return expanded


def certificates(directory):
    return [event for event in schedule.read_journal(directory) if event["kind"] in {"core_frozen", "core_expanded"}]


class CoreContinuityTests(unittest.TestCase):
    def test_first_freeze_precedes_incomplete_readiness_and_binds_actual_graph(self):
        supplied = supplied_context()
        self.assertEqual(coverage_summary(supplied["graph"])["core_disposition_rate"], 0.5)
        with tempfile.TemporaryDirectory() as state:
            candidate = schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            events = schedule.read_journal(state)
            self.assertEqual([event["kind"] for event in events], ["core_frozen", "prepared"])
            self.assertFalse(candidate["gate"]["ready"])
            self.assertFalse(candidate["gate"]["archival_ready"])
            payload = events[0]["payload"]
            self.assertEqual(payload["entity_ids"], ["fixture-pending", "fixture-supplier"])
            self.assertEqual(payload["source_graph_sha256"], canonical_hash(supplied["graph"]))
            self.assertEqual(payload["core_sha256"], supplied["graph"]["coverage"]["frozen_core"]["sha256"])
            self.assertEqual(schedule.load_snapshot(state, payload["snapshot_sha256"])["graph"], supplied["graph"])

    def test_gate_interruption_keeps_first_freeze_and_retry_is_idempotent(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            def interrupted(*_):
                self.assertEqual(len(certificates(state)), 1)
                raise RuntimeError("Synthetic interruption before readiness, never a research result")
            with patch("research_report.publication_gate", side_effect=interrupted):
                with self.assertRaises(RuntimeError):
                    schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            first = schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            second = schedule.prepare_candidate(supplied, state, "2026-11-09", "2026-11-11T20:00:00Z")
            self.assertEqual(first, second)
            self.assertEqual(len(certificates(state)), 1)
            self.assertEqual(len(schedule.read_journal(state)), 2)

    def test_draft_metadata_and_later_source_changes_do_not_reset_inventory(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            first = schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            changed = copy.deepcopy(supplied)
            changed["report"]["title"] = "Changed synthetic draft only"
            changed["identity"]["name"] = "Changed synthetic operational identity"
            changed["graph"]["coverage"]["notes"] = ["Changed synthetic metadata only"]
            changed["graph"]["sources"][0]["response_sha256"] = "b" * 64
            second = schedule.prepare_candidate(changed, state, "2026-11-16", NOW)
            self.assertNotEqual(first["candidate_sha256"], second["candidate_sha256"])
            self.assertEqual(len(certificates(state)), 1)
            freeze(changed["graph"], ["fixture-supplier"])
            validate_graph(changed["graph"])
            with self.assertRaisesRegex(ValueError, "cannot shrink"):
                schedule.prepare_candidate(changed, state, "2026-11-09", NOW)

    def test_expansion_is_durable_before_gate_and_retains_excluded_historical_units(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            expanded = add_core(supplied)
            with patch("research_report.publication_gate", side_effect=RuntimeError("Synthetic interrupted gate")):
                with self.assertRaises(RuntimeError):
                    schedule.prepare_candidate(expanded, state, "2026-11-16", NOW)
            ledger = certificates(state)
            self.assertEqual([event["kind"] for event in ledger], ["core_frozen", "core_expanded"])
            self.assertEqual(ledger[1]["payload"]["previous_core_sha256"], ledger[0]["payload"]["core_sha256"])
            expanded["graph"]["entities"][0].update(status="excluded", disposition="excluded")
            expanded["graph"]["entities"][1].update(status="historical", disposition="historical_only", review_depth="historical")
            schedule.prepare_candidate(expanded, state, "2026-11-16", NOW)
            self.assertEqual(len(certificates(state)), 2)
            freeze(expanded["graph"], ["fixture-added"])
            with self.assertRaisesRegex(ValueError, "fixture-pending.*fixture-supplier"):
                schedule.prepare_candidate(expanded, state, "2026-11-23", NOW)

    def test_unfreezing_and_valid_hash_rewriting_cannot_bypass_by_due_or_retry(self):
        for identifiers in ([], ["fixture-supplier"]):
            with self.subTest(identifiers=identifiers), tempfile.TemporaryDirectory() as state:
                supplied = supplied_context()
                schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
                freeze(supplied["graph"], identifiers)
                validate_graph(supplied["graph"])
                before = (Path(state) / "journal.jsonl").read_bytes()
                for arguments in (("prepare-due",), ("prepare", "--due"), ("prepare", "--edition", "2026-11-09")):
                    argv = ["research_schedule.py", *arguments, "--state-directory", state, "--now", NOW]
                    with patch("sys.argv", argv), patch("research_report.build_context", return_value=supplied):
                        with self.assertRaisesRegex(ValueError, "cannot shrink or unfreeze"):
                            schedule.main()
                self.assertEqual((Path(state) / "journal.jsonl").read_bytes(), before)

    def test_invalid_graph_cannot_mutate_journal_or_snapshot_state(self):
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as state:
                supplied = supplied_context()
                if existing:
                    schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
                before = {path.relative_to(state): path.read_bytes() for path in Path(state).rglob("*") if path.is_file()}
                supplied["graph"]["coverage"]["frozen_core"]["sha256"] = "0" * 64
                supplied["report"]["editions"] = [{"status": "prepared", **copy.deepcopy(supplied)}]
                with self.assertRaises(GraphValidationError):
                    schedule.prepare_candidate(supplied, state, "2026-11-16", NOW)
                after = {path.relative_to(state): path.read_bytes() for path in Path(state).rglob("*") if path.is_file()}
                self.assertEqual(before, after)

    def test_legacy_prepared_history_seeds_largest_frozen_inventory_before_rejecting_shrink(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            with patch("research_schedule._ensure_core_continuity"):
                schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
                expanded = add_core(supplied)
                schedule.prepare_candidate(expanded, state, "2026-11-16", NOW)
            self.assertEqual(certificates(state), [])
            with self.assertRaisesRegex(ValueError, "fixture-added"):
                schedule.prepare_candidate(supplied, state, "2026-11-23", NOW)
            self.assertEqual(certificates(state)[0]["payload"]["entity_ids"],
                             ["fixture-added", "fixture-pending", "fixture-supplier"])
            schedule.prepare_candidate(expanded, state, "2026-11-23", NOW)
            self.assertEqual(len(certificates(state)), 1)

    def test_legacy_published_snapshot_cannot_be_ignored_by_an_empty_declaration(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            with schedule.state_lock(state):
                snapshot_id = schedule._store_snapshot(state, supplied)
                schedule._append(state, "published", {"snapshot_sha256": snapshot_id}, NOW)
            empty = copy.deepcopy(supplied)
            freeze(empty["graph"], [])
            with self.assertRaisesRegex(ValueError, "cannot shrink or unfreeze"):
                schedule.prepare_candidate(empty, state, "2026-11-16", NOW)
            self.assertEqual(certificates(state)[0]["payload"]["snapshot_sha256"], snapshot_id)

    def test_expansion_blocks_stale_approval_activation_retry_and_published_export(self):
        supplied = supplied_context()
        with tempfile.TemporaryDirectory() as state:
            first = schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
            candidate_id = first["candidate_sha256"]
            with schedule.state_lock(state):
                schedule._append(state, "activated", {"candidate_sha256": candidate_id, "edition_id": "2026-11-09"}, NOW)
            schedule.prepare_candidate(add_core(supplied), state, "2026-11-16", NOW)
            receipt = {"candidate_sha256": candidate_id, "release_id": first["identity"]["release_id"],
                       "decision": "approved", "approved_by": "Synthetic operational fixture only", "rationale": "Test only",
                       "role": "coordinator", "reviewer_type": "ai", "method": "final_quality_review",
                       "fixture": False, "invocation_id": "test-only-coordinator"}
            before = (Path(state) / "journal.jsonl").read_bytes()
            with patch("research_report.publication_gate") as gate:
                for action in (lambda: schedule.record_approval(state, candidate_id, receipt, NOW),
                               lambda: schedule.activate_candidate(state, candidate_id, NOW),
                               lambda: schedule.export_edition(state, candidate_id, Path(state) / "published.json", {})):
                    with self.assertRaisesRegex(ValueError, "fixture-added"):
                        action()
                gate.assert_not_called()
            self.assertFalse((Path(state) / "published.json").exists())
            self.assertEqual((Path(state) / "journal.jsonl").read_bytes(), before)

    def test_certificate_source_tamper_and_broken_journal_stop_reuse(self):
        for mutation in ("snapshot", "journal", "certificate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as state:
                supplied = supplied_context()
                schedule.prepare_candidate(supplied, state, "2026-11-09", NOW)
                payload = certificates(state)[0]["payload"]
                if mutation == "snapshot":
                    (Path(state) / "snapshots" / f"{payload['snapshot_sha256']}.json").write_text("{}")
                elif mutation == "journal":
                    path = Path(state) / "journal.jsonl"
                    path.write_bytes(path.read_bytes()[:-1])
                else:
                    with schedule.state_lock(state):
                        schedule._append(state, "core_expanded", {**payload, "source_graph_sha256": "0" * 64}, NOW)
                with self.assertRaises(ValueError):
                    schedule.prepare_candidate(supplied, state, "2026-11-16", NOW)


if __name__ == "__main__":
    unittest.main()
