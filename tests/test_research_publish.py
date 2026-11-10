"""Remote state machines use test fixtures only; no review/publication is claimed."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations
import research_publish as publish
from test_research_citations import context_fixture
from publication_fixtures import populate_owned_inputs


class FakeZenodo:
    def __init__(self):
        self.deposits, self.files, self.calls, self.lose = {}, {}, [], None
        self.doi_prefix = "10.5281/zenodo."

    def request(self, method, path, payload=None, data=None, **kwargs):
        self.calls.append((method, path))
        parts = path.split("?")[0].rstrip("/").split("/")
        if method == "GET" and path.startswith("/api/deposit/depositions?"):
            return copy.deepcopy(list(self.deposits.values()))
        if method == "POST" and path == "/api/deposit/depositions":
            number = len(self.deposits) + 1
            metadata = copy.deepcopy(payload["metadata"])
            metadata["prereserve_doi"] = {"doi": self.doi_prefix + str(number)}
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
                return {"id": number, "doi": self.doi_prefix + str(number), "conceptdoi": self.doi_prefix + "99999",
                        "files": copy.deepcopy(list(self.files[number].values())),
                        "metadata": {"publication_date": "2026-11-09"}}
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
                metadata["prereserve_doi"] = {"doi": self.doi_prefix + str(number)}
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

    def test_external_metadata_changes_are_blocked_before_any_remote_request(self):
        for name in ("zenodo-metadata.json", "huggingface-README.md"):
            with self.subTest(name=name):
                path = self.package / name
                original = path.read_bytes()
                path.write_bytes(b"unreviewed upload content")
                with self.assertRaisesRegex(publish.PublicationBlocked, "changed"):
                    self.zenodo.draft()
                self.assertEqual(self.remote.calls, [])
                path.write_bytes(original)

    def test_archive_envelope_bytes_bind_the_journal_and_marker(self):
        archive = self.package / "research-archive.zip"
        original_digest = self.release.package_sha256
        with zipfile.ZipFile(archive, "a") as stream:
            stream.comment = b"fixture changed envelope, identical members"
        with self.assertRaisesRegex(publish.PublicationBlocked, "archive bytes changed"):
            self.zenodo.draft()
        self.assertEqual(self.remote.calls, [])
        with self.assertRaisesRegex(publish.PublicationBlocked, "different release/package"):
            self.release.journal.save("fixture-existing-journal")
            publish.Release(self.context, self.package, self.directory / "journal.json")
        replacement = publish.Release(self.context, self.package, self.directory / "replacement-journal.json")
        self.assertNotEqual(replacement.package_sha256, original_digest)

    def test_mutated_in_memory_manifest_cannot_weaken_verification(self):
        self.release.manifest["files"].pop("zenodo-metadata.json")
        with self.assertRaisesRegex(publish.PublicationBlocked, "manifest changed"):
            self.zenodo.draft()
        self.assertEqual(self.remote.calls, [])

    def test_sandbox_publication_cannot_authorize_a_production_mirror_or_journal(self):
        self.remote.doi_prefix = "10.5072/zenodo."
        sandbox = publish.Zenodo(self.release, transport=self.remote, sandbox=True)
        sandbox.upload()
        receipt = sandbox.publish()
        self.assertEqual(receipt["environment"], "sandbox")
        self.assertEqual(receipt["api_origin"], "https://sandbox.zenodo.org")
        with self.assertRaisesRegex(publish.PublicationBlocked, "production Zenodo"):
            self.release.require_archive()
        before = len(self.remote.calls)
        with self.assertRaisesRegex(publish.PublicationBlocked, "different API environment"):
            self.zenodo.reconcile()
        self.assertEqual(len(self.remote.calls), before)

    def test_transport_origin_and_unattributed_old_receipts_fail_closed(self):
        self.remote.origin = "https://sandbox.zenodo.org"
        with self.assertRaisesRegex(publish.PublicationBlocked, "transport origin"):
            self.zenodo.draft()
        del self.remote.origin
        self.zenodo.state.update(id=123, status="published", verified=True)
        self.release.journal.save("fixture-originless-receipt")
        with self.assertRaisesRegex(publish.PublicationBlocked, "production Zenodo"):
            self.release.require_archive()
        with self.assertRaisesRegex(publish.PublicationBlocked, "lacks a verified API origin"):
            self.zenodo.reconcile()
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
        self.assertEqual(receipt["doi"], "10.5281/zenodo.1")
        self.assertEqual(receipt["concept_doi"], "10.5281/zenodo.99999")
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

    def test_reserve_freeze_publish_and_website_reuse_exact_pdf_and_archive(self):
        """Synthetic transaction only: no gate/audit/publication evidence is created."""
        reason = "SYNTHETIC TRANSACTION FIXTURE: production archive receipt required"
        def fixture_gate(graph, report, policy):
            ready = citations.published_archive({"report": report})
            return {"ready": ready, "archival_ready": True, "status": "ready" if ready else "prelaunch",
                    "reasons": [] if ready else [reason], "archive_reasons": [] if ready else [reason], "coverage": {"papers": 0}}
        self.fake_gate.publication_gate = fixture_gate
        context = context_fixture()
        context["policy"]["mode"] = "publish_enabled"
        context["root"] = str(self.directory / "synthetic-input")
        populate_owned_inputs(context["root"])
        context["gate"] = fixture_gate(context["graph"], context["report"], context["policy"])
        reservation_path = self.directory / "reservation-journal.json"
        plan = publish.PublicationPlan(context, reservation_path)
        remote = FakeZenodo()
        reserver = publish.Zenodo(plan, transport=remote)
        remote.lose = "create"
        with self.assertRaises(TimeoutError):
            reserver.draft()
        reserver.draft()
        self.assertEqual(len(remote.deposits), 1)
        context["report"]["archive"] = plan.reservation()
        self.assertEqual(context["report"]["archive"]["status"], "reserved")
        with self.assertRaisesRegex(publish.PublicationBlocked, "Freeze"):
            reserver.upload()

        # A real receipt check is used, with clearly synthetic PDF bytes. The
        # context digest is written before publication and never refreshed.
        pdf = b"UNIT TEST PDF FIXTURE - not an actual research publication"
        pdf_directory = Path(context["root"]) / "data/research"
        pdf_directory.mkdir(parents=True)
        (pdf_directory / "report.pdf").write_bytes(pdf)
        frozen_digest = citations.context_digest(context)
        (pdf_directory / "report-pdf.json").write_bytes(citations.json_bytes({"context_contract_version": citations.CONTEXT_CONTRACT_VERSION, "sha256": citations.sha256(pdf), "context_sha256": frozen_digest}))
        projection = citations.public_projection(context, {"dataset_version": "2.5.0", "companies": []})
        prepared = self.directory / "frozen-edition"
        with patch.object(citations, "public_projection", return_value=projection):
            citations.freeze_publication_package(context, prepared / "publication", archive_compression="deflate")
        package = prepared / "publication"
        archive = (package / "research-archive.zip").read_bytes()
        with patch.object(citations, "write_publication_assets", side_effect=AssertionError("Never regenerate an existing freeze")):
            self.assertEqual(citations.freeze_publication_package(context, package), package.resolve())
        changed = copy.deepcopy(context)
        changed["report"]["sections"][0]["paragraphs"][0]["text"] = "Changed frozen research content"
        with self.assertRaisesRegex(ValueError, "context"):
            citations.freeze_publication_package(changed, package)
        self.assertEqual((package / "research-archive.zip").read_bytes(), archive)
        manifest = json.loads((package / "MANIFEST.json").read_text())
        self.assertNotIn("research-archive.zip", manifest["files"])
        self.assertNotIn("PREPARED.json", manifest["files"])
        self.assertNotIn("package-status.json", manifest["files"])
        frozen_metadata = json.loads((package / "metadata.json").read_text())
        self.assertNotIn("doi", frozen_metadata)
        self.assertIn("not registered", frozen_metadata["note"])
        self.assertIn("10.5281/zenodo.1", frozen_metadata["note"])

        release = publish.Release(context, package, self.directory / "frozen-journal.json", reservation=plan)
        publisher = publish.Zenodo(release, transport=remote)
        publisher.upload()
        remote.lose = "publish"
        with self.assertRaises(TimeoutError):
            publisher.publish()
        publisher.publish()
        context["report"]["archive"] = release.archive_receipt()
        context["report"]["status"] = "published"
        context["report"]["editions"] = [{"release_id": context["report"]["release_id"], "archive": context["report"]["archive"]}]
        context["gate"] = fixture_gate(context["graph"], context["report"], context["policy"])
        self.assertTrue(context["gate"]["ready"])
        self.assertEqual(citations.context_digest(context), frozen_digest)
        self.assertEqual(citations.verified_pdf(context), pdf)
        context["prepared_package"] = str(package)
        website = self.directory / "website"
        with patch.object(citations, "public_projection", side_effect=AssertionError("Must reuse frozen projection")), \
                patch.object(citations, "verified_pdf", side_effect=AssertionError("Must reuse frozen PDF")), \
                patch.object(citations, "deterministic_zip", side_effect=AssertionError("Must reuse frozen ZIP")):
            citations.write_publication_assets(context, website)
        self.assertEqual((website / "publication/research-archive.zip").read_bytes(), archive)
        self.assertEqual((website / "publication/report.pdf").read_bytes(), pdf)
        self.assertEqual((website / "publication/metadata.json").read_bytes(), (package / "metadata.json").read_bytes())
        live = json.loads((website / "publication/current-metadata.json").read_text())
        self.assertEqual(live["status"], "published")
        self.assertEqual(live["doi"], "10.5281/zenodo.1")
        status = json.loads((website / "publication/package-status.json").read_text())
        self.assertEqual(status["archive"], "published")
        self.assertEqual(status["archive_sha256"], citations.sha256(archive))
        self.assertEqual(status["pdf_sha256"], citations.sha256(pdf))
        self.assertEqual(status["archive_receipt"]["artifact_sha256"], citations.sha256(archive))
        self.assertEqual(status["archive_receipt"]["concept_doi"], "10.5281/zenodo.99999")
        self.assertEqual(len(remote.deposits), 1)
        self.assertEqual(sum(path.endswith("/actions/publish") for _, path in remote.calls), 1)
        # Website deployment remains a separate receipt.
        self.assertEqual(status["website"], "independent")
        for key, value in (("api_origin", "https://sandbox.zenodo.org"), ("environment", "sandbox"),
                           ("verified", False), ("record_id", 2), ("confirmed_on", "2026-11-09")):
            invalid = copy.deepcopy(context)
            invalid["report"]["archive"][key] = value
            with self.subTest(invalid_receipt_field=key), self.assertRaisesRegex(ValueError, "production archive receipt"):
                citations.write_publication_assets(invalid, self.directory / "blocked-website")

    def test_public_record_requires_distinct_typed_concept_and_reserved_version_dois(self):
        self.zenodo.upload()
        self.remote.deposits[1].update(submitted=True, state="done")
        original = self.remote.request
        for patch_record in ({"doi": "10.5281/zenodo.2"}, {"doi": ["10.5281/zenodo.1"]},
                             {"conceptdoi": ["10.5281/zenodo.99999"]}, {"conceptdoi": "10.5281/zenodo.1"}, {"files": []}):
            def request(method, path, **kwargs):
                result = original(method, path, **kwargs)
                if path.startswith("/api/records/"):
                    result.update(patch_record)
                return result
            with self.subTest(patch=patch_record), patch.object(self.remote, "request", side_effect=request):
                with self.assertRaises(publish.PublicationBlocked):
                    self.zenodo.reconcile()
        self.assertNotEqual(self.zenodo.state.get("status"), "published")

    def test_prepared_without_reservation_can_reuse_bundle_after_actual_receipt(self):
        before = citations.context_digest(self.context)
        self.zenodo.upload()
        self.zenodo.publish()
        self.context["report"]["archive"] = self.release.archive_receipt()
        self.assertEqual(citations.context_digest(self.context), before)
        output = self.directory / "legacy-transaction-site"
        citations.write_publication_assets(self.context, output)
        self.assertEqual((output / "publication/research-archive.zip").read_bytes(), (self.package / "research-archive.zip").read_bytes())

    def test_reservation_rejects_concept_identifier_and_changed_research_before_remote_calls(self):
        with self.assertRaisesRegex(publish.PublicationBlocked, "integer version-record"):
            self.zenodo.draft(previous_id="10.5281/zenodo.99999")
        plan = publish.PublicationPlan(self.context, self.directory / "plan-journal.json")
        self.context["report"]["sections"][0]["paragraphs"][0]["text"] = "Changed inputs after planning"
        reserver = publish.Zenodo(plan, transport=self.remote)
        before = len(self.remote.calls)
        with self.assertRaisesRegex(publish.PublicationBlocked, "inputs changed"):
            reserver.draft()
        self.assertEqual(len(self.remote.calls), before)


if __name__ == "__main__":
    unittest.main()
