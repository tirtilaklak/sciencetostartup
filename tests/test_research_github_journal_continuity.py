"""Synthetic retained-journal continuity controls; no credentials or network."""
import copy
import json
import unittest
from unittest.mock import patch

import test_research_github_source_commit as fixtures


class GitHubRetainedSourceBindingControls(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GitHubSourceCommitControls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.release, self.remote = self.fixture.release, self.fixture.remote

    def published_state(self):
        self.fixture.mirror().publish()
        return copy.deepcopy(self.release.journal.state)

    def assert_hold_before_reads(self, state, expected=fixtures.SOURCE):
        blob = (json.dumps(state, sort_keys=True) + "\n").encode()
        self.release.journal.path.write_bytes(blob)
        self.remote.calls.clear()
        # A coherent synthetic remote follows the requested source, so this
        # control cannot pass merely because the transport rejects source B.
        self.remote.ref["object"]["sha"] = expected
        with patch.object(fixtures, "SOURCE", expected):
            with self.assertRaises(fixtures.publish.PublicationBlocked):
                self.fixture.mirror(expected).publish()
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(self.release.journal.path.read_bytes(), blob)

    def test_source_field_loss_cannot_rebind_retained_published_source_a_to_b(self):
        state = self.published_state()
        del state["github"]["source_commit"]
        self.assert_hold_before_reads(state, fixtures.OTHER)

    def test_missing_or_none_live_field_holds_even_for_same_expected_source(self):
        original = self.published_state()
        for value in ("missing", None):
            with self.subTest(value=value):
                state = copy.deepcopy(original)
                if value == "missing":
                    del state["github"]["source_commit"]
                else:
                    state["github"]["source_commit"] = None
                self.assert_hold_before_reads(state)

    def test_live_source_b_cannot_override_retained_source_a(self):
        state = self.published_state()
        state["github"]["source_commit"] = fixtures.OTHER
        self.assert_hold_before_reads(state, fixtures.OTHER)

    def test_lost_binding_event_holds_despite_remaining_live_identity_and_receipt(self):
        state = self.published_state()
        state["events"] = [event for event in state["events"]
                           if event["operation"] != "github-source-commit-bound"]
        self.assert_hold_before_reads(state)

    def test_retained_github_work_without_any_binding_cannot_be_treated_as_initial(self):
        state = self.published_state()
        state["github"] = {"status": "prepared"}
        state["events"] = [event for event in state["events"]
                           if event["operation"] != "github-source-commit-bound"]
        self.assert_hold_before_reads(state)

    def test_conflicting_or_duplicate_binding_history_holds(self):
        original = self.published_state()
        for commit in (fixtures.SOURCE, fixtures.OTHER):
            with self.subTest(commit=commit):
                state = copy.deepcopy(original)
                state["events"].append({"operation": "github-source-commit-bound", "source_commit": commit})
                self.assert_hold_before_reads(state)

    def test_invalid_event_containers_entries_and_binding_sha_shapes_hold(self):
        original = self.published_state()
        malformed_events = (None, {}, "SYNTHETIC invalid events", [None], ["SYNTHETIC invalid event"],
                            [{}], [{"operation": None}], [{"operation": 7}])
        for events in malformed_events:
            with self.subTest(events=events):
                state = copy.deepcopy(original)
                state["events"] = events
                self.assert_hold_before_reads(state)
        for commit in (None, True, "a" * 7, "A" * 40, "g" * 40, fixtures.SOURCE + "\n"):
            with self.subTest(commit=commit):
                state = copy.deepcopy(original)
                binding = next(event for event in state["events"]
                               if event["operation"] == "github-source-commit-bound")
                binding["source_commit"] = commit
                self.assert_hold_before_reads(state)

    def test_matching_published_resume_preserves_one_binding_and_is_get_only(self):
        state = self.published_state()
        original_binding = next(event for event in state["events"]
                                if event["operation"] == "github-source-commit-bound")
        self.remote.calls.clear()
        result = self.fixture.mirror().publish()
        self.assertTrue(result["verified"])
        self.assertEqual(result["source_commit"], fixtures.SOURCE)
        self.assertEqual({method for method, _, _ in self.remote.calls}, {"GET"})
        self.assertEqual([event for event in self.release.journal.state["events"]
                          if event["operation"] == "github-source-commit-bound"], [original_binding])

    def test_first_binding_checkpoint_can_resume_before_any_remote_work(self):
        self.release.journal.state["github"]["source_commit"] = fixtures.SOURCE
        self.release.journal.save("github-source-commit-bound", source_commit=fixtures.SOURCE)
        self.assertTrue(self.fixture.mirror().publish()["verified"])
        self.assertEqual(len([event for event in self.release.journal.state["events"]
                              if event["operation"] == "github-source-commit-bound"]), 1)


if __name__ == "__main__":
    unittest.main()
