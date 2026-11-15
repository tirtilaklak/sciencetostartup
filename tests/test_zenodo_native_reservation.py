"""Synthetic native DOI state-machine regressions; never contacts Zenodo."""
import copy
import unittest
from unittest.mock import patch

import test_research_publish as publication_fixtures

FakeZenodo = publication_fixtures.FakeZenodo
publish = publication_fixtures.publish


NATIVE_ACCEPT = "application/vnd.inveniordm.v1+json"
SANDBOX_ORIGIN = "https://sandbox.zenodo.org"
SANDBOX_DOI = "10.5072/zenodo.1"
LEGACY_ALIAS = "10.5281/zenodo.1"


class NativeReservationTests(unittest.TestCase):
    # Reuse fixture construction without inheriting or rerunning its test suite.
    setUp = publication_fixtures.PublicationTests.setUp
    rebuild = publication_fixtures.PublicationTests.rebuild

    def planned(self):
        index = getattr(self, "_plan_index", 0) + 1
        self._plan_index = index
        plan = publish.PublicationPlan(self.context, self.directory / f"native-plan-{index}.json")
        remote = FakeZenodo()
        remote.doi_prefix = "10.5072/zenodo."
        adapter = publish.Zenodo(plan, transport=remote, public_reader=remote.public_read, sandbox=True)
        return plan, remote, adapter

    def seed_legacy_draft(self, plan, remote, *, reserved=LEGACY_ALIAS, source=None):
        draft = remote.request("POST", "/api/deposit/depositions", payload={"metadata": {"notes": plan.marker}})
        state = plan.journal.state["zenodo"]
        state.update(id=draft["id"], status="draft", api_origin=SANDBOX_ORIGIN,
                     environment="sandbox", reserved_doi=reserved)
        if source is not None:
            state["reservation_source"] = source
        plan.journal.save("SYNTHETIC legacy journal fixture")
        return draft

    def reservation_posts(self, remote):
        return [path for method, path in remote.calls if method == "POST" and path.endswith("/draft/pids/doi")]

    def reject_native(self, transform):
        plan, remote, adapter = self.planned()
        self.seed_legacy_draft(plan, remote)
        request = remote.request

        def changed(method, path, *args, **kwargs):
            result = request(method, path, *args, **kwargs)
            if method == "GET" and path == "/api/records/1/draft":
                transform(result)
            return result

        with patch.object(remote, "request", side_effect=changed):
            with self.assertRaises(publish.PublicationBlocked):
                adapter.draft()
        self.assertEqual(self.reservation_posts(remote), [])
        self.assertNotEqual(plan.journal.state["zenodo"].get("reservation_source"), "inveniordm.pids.doi")
        return plan, remote

    def test_legacy_prereserve_string_cannot_freeze_a_report(self):
        plan, remote, _ = self.planned()
        self.seed_legacy_draft(plan, remote)
        self.assertEqual(remote.pids[1], {})
        with self.assertRaises(publish.PublicationBlocked):
            plan.reservation()
        self.assertEqual(self.reservation_posts(remote), [])

    def test_sandbox_migration_preserves_legacy_alias_and_journal_history(self):
        plan, remote, adapter = self.planned()
        self.seed_legacy_draft(plan, remote)
        original_events = copy.deepcopy(plan.journal.state["events"])
        adapter.draft()
        state = plan.journal.state["zenodo"]
        self.assertEqual(state["id"], 1)
        self.assertEqual(state["reserved_doi"], SANDBOX_DOI)
        self.assertEqual(state["reservation_source"], "inveniordm.pids.doi")
        self.assertEqual(state["legacy_reservation_aliases"], [{
            "doi": LEGACY_ALIAS, "source": "legacy_deposit_prereserve_doi", "id": 1,
            "api_origin": SANDBOX_ORIGIN,
        }])
        self.assertEqual(plan.journal.state["events"][:len(original_events)], original_events)
        self.assertIn("zenodo-legacy-reservation-alias-retained",
                      [event["operation"] for event in plan.journal.state["events"]])
        self.assertEqual(plan.reservation()["reserved_doi"], SANDBOX_DOI)
        self.assertEqual(len(remote.deposits), 1)
        self.assertEqual(len(self.reservation_posts(remote)), 1)

    def test_native_existing_pid_is_reused_and_repeat_never_posts_again(self):
        plan, remote, adapter = self.planned()
        self.seed_legacy_draft(plan, remote)
        remote.pids[1] = {"doi": {"identifier": SANDBOX_DOI, "provider": "datacite", "client": "datacite"}}
        adapter.draft()
        adapter.draft()
        self.assertEqual(plan.reservation()["reserved_doi"], SANDBOX_DOI)
        self.assertEqual(self.reservation_posts(remote), [])
        self.assertEqual(len(plan.journal.state["zenodo"]["legacy_reservation_aliases"]), 1)

    def test_committed_reservation_lost_response_recovers_same_id_without_duplicate_post(self):
        plan, remote, adapter = self.planned()
        remote.lose = "reserve_doi"
        with self.assertRaises(TimeoutError):
            adapter.draft()
        self.assertEqual(remote.pids[1]["doi"]["identifier"], SANDBOX_DOI)
        self.assertEqual(plan.journal.state["zenodo"]["id"], 1)
        adapter.draft()
        adapter.draft()
        self.assertEqual(plan.reservation()["deposition_id"], 1)
        self.assertEqual(len(remote.deposits), 1)
        self.assertEqual(len(self.reservation_posts(remote)), 1)

    def test_uncommitted_reservation_lost_response_can_retry_after_empty_native_get(self):
        plan, remote, adapter = self.planned()
        remote.lose = "reserve_doi_before"
        with self.assertRaises(TimeoutError):
            adapter.draft()
        self.assertEqual(remote.pids[1], {})
        first_call_count = len(remote.calls)
        adapter.draft()
        subsequent = remote.calls[first_call_count:]
        native_get = subsequent.index(("GET", "/api/records/1/draft"))
        reserve_post = subsequent.index(("POST", "/api/records/1/draft/pids/doi"))
        self.assertLess(native_get, reserve_post)
        self.assertEqual(plan.reservation()["reserved_doi"], SANDBOX_DOI)
        self.assertEqual(len(remote.deposits), 1)
        self.assertEqual(len(self.reservation_posts(remote)), 2)

    def test_untrusted_reservation_link_is_rejected_before_post(self):
        for link in ("https://attacker.invalid/api/records/1/draft/pids/doi",
                     SANDBOX_ORIGIN + "/api/records/2/draft/pids/doi",
                     "/api/records/2/draft/pids/doi"):
            with self.subTest(link=link):
                self.reject_native(lambda record: record["links"].update(reserve_doi=link))

    def test_missing_reservation_link_is_rejected_before_post(self):
        self.reject_native(lambda record: record["links"].pop("reserve_doi"))

    def test_native_draft_identity_must_match_existing_legacy_draft(self):
        self.reject_native(lambda record: record.update(id="2"))

    def test_native_pid_must_be_well_formed_managed_and_bound_to_sandbox_record(self):
        invalid = [
            {"doi": []},
            {"doi": {"identifier": "not-a-doi", "provider": "datacite", "client": "datacite"}},
            {"doi": {"identifier": LEGACY_ALIAS, "provider": "datacite", "client": "datacite"}},
            {"doi": {"identifier": "10.5072/zenodo.2", "provider": "datacite", "client": "datacite"}},
            {"doi": {"identifier": SANDBOX_DOI, "provider": "external"}},
            {"doi": {"identifier": SANDBOX_DOI, "provider": "datacite", "client": "other"}},
        ]
        for pids in invalid:
            with self.subTest(pids=pids):
                self.reject_native(lambda record: record.update(pids=copy.deepcopy(pids)))

    def test_previously_proven_native_doi_cannot_be_replaced_by_legacy_alias(self):
        plan, remote, adapter = self.planned()
        self.seed_legacy_draft(plan, remote, reserved=LEGACY_ALIAS, source="inveniordm.pids.doi")
        remote.pids[1] = {"doi": {"identifier": SANDBOX_DOI, "provider": "datacite", "client": "datacite"}}
        with self.assertRaises(publish.PublicationBlocked):
            adapter.draft()
        self.assertEqual(plan.journal.state["zenodo"]["reserved_doi"], LEGACY_ALIAS)
        self.assertEqual(self.reservation_posts(remote), [])

    def test_frozen_wrong_reservation_cannot_be_silently_migrated(self):
        self.context["report"]["archive"] = {
            "status": "reserved", "reserved_doi": LEGACY_ALIAS, "deposition_id": 1,
            "api_origin": SANDBOX_ORIGIN, "environment": "sandbox",
        }
        self.rebuild()
        release = publish.Release(self.context, self.package, self.directory / "frozen-native.json")
        remote = FakeZenodo()
        remote.doi_prefix = "10.5072/zenodo."
        draft = remote.request("POST", "/api/deposit/depositions", payload={"metadata": {"notes": release.marker}})
        remote.pids[1] = {"doi": {"identifier": SANDBOX_DOI, "provider": "datacite", "client": "datacite"}}
        release.journal.state["zenodo"].update(
            id=draft["id"], status="draft", reserved_doi=LEGACY_ALIAS,
            api_origin=SANDBOX_ORIGIN, environment="sandbox",
        )
        release.journal.save("SYNTHETIC frozen wrong reservation")
        adapter = publish.Zenodo(release, transport=remote, public_reader=remote.public_read, sandbox=True)
        before_package = (self.package / "research-archive.zip").read_bytes()
        with self.assertRaises(publish.PublicationBlocked):
            adapter.draft()
        self.assertEqual(release.journal.state["zenodo"]["reserved_doi"], LEGACY_ALIAS)
        self.assertEqual((self.package / "research-archive.zip").read_bytes(), before_package)
        self.assertEqual(self.reservation_posts(remote), [])

    def test_invalid_reservation_response_keeps_intent_and_recovers_from_native_get(self):
        for corruption in ("identity", "pid"):
            with self.subTest(corruption=corruption):
                plan, remote, adapter = self.planned()
                self.seed_legacy_draft(plan, remote)
                request = remote.request

                def changed(method, path, *args, **kwargs):
                    result = request(method, path, *args, **kwargs)
                    if method == "POST" and path.endswith("/draft/pids/doi"):
                        if corruption == "identity":
                            result["id"] = "2"
                        else:
                            result["pids"]["doi"]["identifier"] = LEGACY_ALIAS
                    return result

                with patch.object(remote, "request", side_effect=changed):
                    with self.assertRaises(publish.PublicationBlocked):
                        adapter.draft()
                state = plan.journal.state["zenodo"]
                self.assertEqual(state["id"], 1)
                self.assertEqual(state["pending"], "reserve_doi")
                self.assertNotEqual(state.get("reservation_source"), "inveniordm.pids.doi")
                with self.assertRaises(publish.PublicationBlocked):
                    plan.reservation()
                adapter.draft()
                self.assertEqual(plan.reservation()["reserved_doi"], SANDBOX_DOI)
                self.assertEqual(len(self.reservation_posts(remote)), 1)
                self.assertEqual(len(remote.deposits), 1)

    def test_previously_verified_native_pid_cannot_disappear(self):
        plan, remote, adapter = self.planned()
        adapter.draft()
        remote.pids[1] = {}
        with self.assertRaises(publish.PublicationBlocked):
            adapter.draft()
        self.assertEqual(len(self.reservation_posts(remote)), 1)
        self.assertEqual(plan.journal.state["zenodo"]["reserved_doi"], SANDBOX_DOI)

    def test_new_reservation_requires_native_accept_and_never_uses_network(self):
        plan, remote, adapter = self.planned()
        request = remote.request
        native_requests = []

        def observed(method, path, *args, **kwargs):
            if path.startswith("/api/records/"):
                native_requests.append((method, path, kwargs.get("accept")))
            return request(method, path, *args, **kwargs)

        with patch.object(publish.HTTP, "request", side_effect=AssertionError("Network forbidden in synthetic fixture")), \
                patch.object(remote, "request", side_effect=observed):
            adapter.draft()
        self.assertTrue(native_requests)
        self.assertTrue(all(accept == NATIVE_ACCEPT for _, _, accept in native_requests))
        self.assertEqual(plan.reservation()["reserved_doi"], SANDBOX_DOI)


if __name__ == "__main__":
    unittest.main()
