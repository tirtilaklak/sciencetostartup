"""Remote state machines use test fixtures only; no review/publication is claimed."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations
import research_publish as publish
from test_research_citations import context_fixture


class FakeZenodo:
    def __init__(self):
        self.deposits, self.files, self.calls, self.lose = {}, {}, [], None

    def request(self, method, path, payload=None, data=None, **kwargs):
        self.calls.append((method, path))
        parts = path.split("?")[0].rstrip("/").split("/")
        if method == "GET" and path.startswith("/api/deposit/depositions?"):
            return copy.deepcopy(list(self.deposits.values()))
        if method == "POST" and path == "/api/deposit/depositions":
            number = len(self.deposits) + 1
            metadata = copy.deepcopy(payload["metadata"])
            metadata["prereserve_doi"] = {"doi": "10.1234/reserved-" + str(number)}
            result = {"id": number, "metadata": metadata, "submitted": False, "state": "unsubmitted",
                      "links": {"bucket": "/api/files/" + str(number)}, "record_id": number}
            self.deposits[number], self.files[number] = result, {}
            if self.lose == "create":
                self.lose = None
                raise TimeoutError("test lost create response")
            return copy.deepcopy(result)
        if "/api/files/" in path and method == "PUT":
            number, name = int(parts[-2]), parts[-1]
            self.files[number][name] = {"filename": name, "filesize": len(data), "checksum": hashlib.md5(data).hexdigest()}
            if self.lose == "upload":
                self.lose = None
                raise TimeoutError("test lost upload response")
            return self.files[number][name]
        if path.startswith("/api/records/") and method == "GET":
            number = int(parts[-1])
            if self.deposits[number]["submitted"]:
                return {"id": number, "doi": "10.1234/published-" + str(number), "metadata": {"publication_date": "2026-11-09"}}
            raise RuntimeError("not published")
        if parts[-1] == "files" and method == "GET":
            return copy.deepcopy(list(self.files[int(parts[-2])].values()))
        if parts[-1] == "publish" and method == "POST":
            number = int(parts[-3])
            self.deposits[number].update(submitted=True, state="done")
            if self.lose == "publish":
                self.lose = None
                raise TimeoutError("test lost publish response")
            return copy.deepcopy(self.deposits[number])
        if parts[-1] == "newversion" and method == "POST":
            previous = int(parts[-3])
            number = len(self.deposits) + 1
            draft = copy.deepcopy(self.deposits[previous])
            draft.update(id=number, record_id=number, submitted=False, state="unsubmitted", links={"bucket": "/api/files/" + str(number)})
            self.deposits[number], self.files[number] = draft, copy.deepcopy(self.files[previous])
            self.deposits[previous]["links"]["latest_draft"] = "/api/deposit/depositions/" + str(number)
            if self.lose == "newversion":
                self.lose = None
                raise TimeoutError("test lost new version response")
            return copy.deepcopy(self.deposits[previous])
        if path.startswith("/api/deposit/depositions/"):
            number = int(parts[-1])
            if method == "GET":
                return copy.deepcopy(self.deposits[number])
            if method == "PUT":
                metadata = copy.deepcopy(payload["metadata"])
                metadata["prereserve_doi"] = {"doi": "10.1234/reserved-" + str(number)}
                self.deposits[number]["metadata"] = metadata
                if self.lose == "metadata":
                    self.lose = None
                    raise TimeoutError("test lost metadata response")
                return copy.deepcopy(self.deposits[number])
        raise AssertionError((method, path))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.context = context_fixture()
        self.context["policy"]["mode"] = "publish_enabled"
        self.context["gate"].update(ready=True, archival_ready=True, reasons=[])
        self.rebuild()
        # Only unit tests supply an artificial gate. Production Release always
        # imports and executes the repository's actual publication_gate.
        self.fake_gate = types.SimpleNamespace(publication_gate=lambda *args: self.context["gate"])
        self.patch_gate = patch.dict(sys.modules, {"research_report": self.fake_gate})
        self.patch_gate.start()
        self.addCleanup(self.patch_gate.stop)
        self.release = publish.Release(self.context, self.package, self.directory / "journal.json")
        self.remote = FakeZenodo()
        self.zenodo = publish.Zenodo(self.release, transport=self.remote)

    def rebuild(self):
        projection = citations.public_projection(self.context, {"dataset_version": "2.5.0", "companies": []})
        with patch.object(citations, "public_projection", return_value=projection), patch.object(citations, "verified_pdf", return_value=b"UNIT TEST PDF FIXTURE - not a publication artifact"):
            citations.write_publication_assets(self.context, self.directory)
        self.package = self.directory / "publication"

    def test_prepare_only_policy_blocks_all_remote_operations(self):
        self.context["policy"]["mode"] = "prepare_only"
        with self.assertRaisesRegex(publish.PublicationBlocked, "prepare_only"):
            self.zenodo.draft()
        self.assertEqual(self.remote.calls, [])

    def test_actual_gate_is_recomputed_not_trusted_from_prepared_context(self):
        self.fake_gate.publication_gate = lambda *args: {"ready": False, "archival_ready": False}
        with self.assertRaisesRegex(publish.PublicationBlocked, "readiness"):
            self.zenodo.draft()
        self.assertEqual(self.remote.calls, [])

    def test_archival_ready_can_create_before_the_final_archive_gate_passes(self):
        self.context["gate"]["ready"] = False
        self.context["gate"]["reasons"] = ["Public archive receipt still required."]
        self.rebuild()
        self.release = publish.Release(self.context, self.package, self.directory / "archive-ready-journal.json")
        adapter = publish.Zenodo(self.release, transport=self.remote)
        self.assertEqual(adapter.draft()["id"], 1)

    def test_changed_package_and_missing_pdf_are_blocked(self):
        (self.package / "report.md").write_text("changed")
        with self.assertRaisesRegex(publish.PublicationBlocked, "changed"):
            self.zenodo.draft()
        self.assertEqual(self.remote.calls, [])

    def test_no_credential_request_happens_implicitly(self):
        with self.assertRaisesRegex(publish.PublicationBlocked, "Connect"):
            publish.Zenodo(self.release)

    def test_lost_create_is_reconciled_without_duplicate_deposit(self):
        self.remote.lose = "create"
        with self.assertRaises(TimeoutError):
            self.zenodo.draft()
        recovered = self.zenodo.draft()
        self.assertEqual(recovered["id"], 1)
        self.assertEqual(len(self.remote.deposits), 1)
        self.assertEqual(self.release.journal.state["zenodo"]["status"], "draft")
        self.assertNotIn("doi", self.release.journal.state["zenodo"])
        self.assertIn("reserved_doi", self.release.journal.state["zenodo"])

    def test_duplicate_remote_package_marker_blocks_automatic_selection(self):
        self.zenodo.draft()
        duplicate = copy.deepcopy(self.remote.deposits[1])
        duplicate["id"] = 2
        self.remote.deposits[2] = duplicate
        self.zenodo.state.pop("id")
        self.release.journal.save("test-only-clear-known-id")
        with self.assertRaisesRegex(publish.AmbiguousRemoteState, "Multiple deposits"):
            self.zenodo.draft()

    def test_lost_newversion_response_follows_existing_latest_draft(self):
        self.zenodo.draft()
        self.remote.deposits[1]["metadata"]["notes"] = "prior-release"
        self.remote.deposits[1].update(submitted=True, state="done")
        self.zenodo.state.clear()
        self.zenodo.state["status"] = "prepared"
        self.release.journal.save("test-only-new-version-state")
        self.remote.lose = "newversion"
        with self.assertRaises(TimeoutError):
            self.zenodo.draft(previous_id=1)
        recovered = self.zenodo.draft(previous_id=1)
        self.assertEqual(recovered["id"], 2)
        self.assertIn(self.release.marker, recovered["metadata"]["notes"])
        self.assertEqual(sum(path.endswith("/actions/newversion") for _, path in self.remote.calls), 1)

    def test_lost_newversion_metadata_response_recovers_same_persisted_id(self):
        self.zenodo.draft()
        self.remote.deposits[1]["metadata"]["notes"] = "prior-release"
        self.remote.deposits[1].update(submitted=True, state="done")
        self.zenodo.state.clear()
        self.release.journal.save("test-only-new-version-state")
        self.remote.lose = "metadata"
        with self.assertRaises(TimeoutError):
            self.zenodo.draft(previous_id=1)
        self.assertEqual(self.zenodo.draft()["id"], 2)
        self.assertEqual(len(self.remote.deposits), 2)

    def test_uncertain_create_with_no_remote_match_never_retries(self):
        self.release.journal.state["zenodo"]["pending"] = "create"
        with self.assertRaises(publish.AmbiguousRemoteState):
            self.zenodo.draft()
        self.assertFalse(any(method == "POST" for method, _ in self.remote.calls))

    def test_lost_upload_is_verified_then_skipped_on_retry(self):
        self.remote.lose = "upload"
        with self.assertRaises(TimeoutError):
            self.zenodo.upload()
        self.zenodo.upload()
        puts = [path for method, path in self.remote.calls if method == "PUT" and "/api/files/" in path]
        self.assertEqual(len(puts), len(self.release.uploads))
        self.assertEqual(self.zenodo.state["status"], "uploaded")

    def test_lost_publish_reconciles_public_record_and_does_not_publish_twice(self):
        self.zenodo.upload()
        self.remote.lose = "publish"
        with self.assertRaises(TimeoutError):
            self.zenodo.publish()
        receipt = self.zenodo.publish()
        self.assertEqual(receipt["status"], "published")
        self.assertEqual(receipt["doi"], "10.1234/published-1")
        self.assertTrue(receipt["verified"])
        self.assertEqual(sum(path.endswith("/actions/publish") for _, path in self.remote.calls), 1)

    def test_unresolved_publish_is_not_retried_after_reconcile(self):
        self.zenodo.upload()
        self.zenodo.state["pending"] = "publish"
        self.release.journal.save("test-only-publish-intent")
        self.zenodo.reconcile()
        with self.assertRaises(publish.AmbiguousRemoteState):
            self.zenodo.publish()
        self.assertFalse(any(path.endswith("/actions/publish") for _, path in self.remote.calls))

    def test_remote_corruption_or_inherited_file_blocks_publication(self):
        self.zenodo.upload()
        self.remote.files[1]["unexpected"] = {"filename": "unexpected", "filesize": 0, "checksum": ""}
        with self.assertRaisesRegex(publish.PublicationBlocked, "file set differs"):
            self.zenodo.publish()

    def test_mirrors_require_a_verified_published_archive(self):
        mirror = publish.GitHubMirror(self.release, "owner/repo", transport=self.remote, upload_transport=self.remote)
        with self.assertRaisesRegex(publish.PublicationBlocked, "published archive"):
            mirror.publish()
        self.assertEqual(self.remote.calls, [])

    def test_journal_binds_release_and_package_and_omits_credentials(self):
        self.zenodo.draft()
        value = json.loads((self.directory / "journal.json").read_text())
        self.assertEqual(value["package_sha256"], self.release.package_sha256)
        self.assertNotIn("token", str(value).lower())
        with self.assertRaises(publish.PublicationBlocked):
            publish.Journal(self.directory / "journal.json", "other-release", self.release.package_sha256)

    def test_http_transport_rejects_cross_origin_links_before_token_can_leave(self):
        transport = publish.HTTP("unit-test-token", "https://zenodo.org")
        with patch("urllib.request.urlopen", side_effect=AssertionError("must not request")):
            with self.assertRaisesRegex(publish.PublicationBlocked, "origin"):
                transport.request("GET", "https://attacker.invalid/steal")

    def test_redirect_cannot_forward_bearer_credentials_to_another_origin(self):
        import urllib.request
        request = urllib.request.Request("https://zenodo.org/api/deposit/depositions", headers={"Authorization": "Bearer unit-test-token"})
        with self.assertRaisesRegex(publish.PublicationBlocked, "redirected"):
            publish.SameOriginRedirect().redirect_request(request, None, 302, "Found", {}, "https://attacker.invalid/")


if __name__ == "__main__":
    unittest.main()
