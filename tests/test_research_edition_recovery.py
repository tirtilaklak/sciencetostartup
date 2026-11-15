"""Independent synthetic recovery controls; no real audit/publication is claimed."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations
import research_edition_replay as replay
import research_graph as graph_module
import research_publish as publish
from test_research_edition_replay import fixture, reseal
from test_research_publish import FakeZenodo


class ExistingPublishedReplayRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root, cls.package, cls.descriptor, _ = fixture(
            Path(cls.temporary.name), reference_version=4, reference_original_differs=True)
        cls.context = replay.load_published_edition(cls.root, cls.descriptor)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def release(self, directory, mutate=None, *, existing=True):
        path = Path(directory) / "SYNTHETIC-private-journal.json"
        receipt = copy.deepcopy(self.descriptor["archive_receipt"])
        state = {"schema_version": 1, "release_id": self.descriptor["release_id"],
            "package_sha256": self.descriptor["archive_sha256"],
            "zenodo": {**receipt, "id": receipt["deposition_id"], "pending": None,
                       "url": "https://doi.org/" + receipt["doi"]},
            "github": {"status": "prepared"}, "huggingface": {"status": "prepared"}, "events": []}
        if mutate:
            mutate(state)
        if existing:
            path.write_bytes(citations.json_bytes(state))
        return publish.Release(copy.deepcopy(self.context), self.package, path)

    def test_earlier_reference_graph_is_preserved_separately_from_final_screening_graph(self):
        verification = self.context["replay_verification"]
        original = verification["original_reference_commitments"]
        self.assertNotEqual(original["input_graph_sha256"], verification["original_scientific_graph_sha256"])
        self.assertNotEqual(original["input_graph_bytes_sha256"], verification["input_commitments"]["graph_sha256"])
        source = json.loads((self.package / "source-context.json").read_bytes())
        self.assertEqual(original["output_graph_sha256"], source["policy"]["audits"]["reference"]["method"]["output_graph_sha256"])
        for review in source["policy"]["report_reviews"]:
            self.assertEqual(review["graph_sha256"], verification["original_scientific_graph_sha256"])

    def test_existing_verified_journal_allows_exact_archive_receipt_after_current_inputs_disappear(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            with patch("research_report.publication_gate", side_effect=AssertionError("No current gate")), \
                    patch.object(citations, "reproduction_files", side_effect=AssertionError("No current recipe")):
                archive = release.require_archive()
                self.assertEqual(archive["artifact_sha256"], self.descriptor["archive_sha256"])
                exported = release.archive_receipt()
                self.assertEqual(exported["doi"], self.descriptor["archive_receipt"]["doi"])
                self.assertTrue(exported["anonymous_verified"])

    def test_missing_pending_sandbox_unverified_or_identity_changed_journals_cannot_recover(self):
        mutations = {
            "pending": lambda s: s["zenodo"].update(pending="publish"),
            "unverified": lambda s: s["zenodo"].update(verified=False),
            "anonymous": lambda s: s["zenodo"].update(anonymous_verified=False),
            "sandbox": lambda s: s["zenodo"].update(environment="sandbox"),
            "deposition": lambda s: s["zenodo"].update(id=222222222),
            "typed_deposition": lambda s: s["zenodo"].update(id="111111111"),
            "record": lambda s: s["zenodo"].update(record_id=222222222),
            "concept": lambda s: s["zenodo"].update(concept_doi="10.5281/zenodo.333333333"),
            "reserved": lambda s: s["zenodo"].update(reserved_doi="10.5281/zenodo.333333333"),
            "artifact": lambda s: s["zenodo"].update(artifact_sha256="0" * 64),
            "confirmation": lambda s: s["zenodo"].update(confirmed_on="2026-11-10T20:00:00Z"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(publish.PublicationBlocked):
                    self.release(temporary, mutate).require_archive()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(publish.PublicationBlocked):
                self.release(temporary, existing=False).require_archive()

    def test_replay_cannot_reserve_create_upload_or_publish_any_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            remote = FakeZenodo()
            adapter = publish.Zenodo(release, transport=remote, public_reader=remote.public_read)
            for method in (release.verify, adapter.draft, adapter.upload, adapter.publish):
                with self.subTest(method=method.__name__), self.assertRaises(publish.PublicationBlocked):
                    method()
            with self.assertRaises(ValueError):
                publish.PublicationPlan(release.context, Path(temporary) / "SYNTHETIC-plan.json")
            self.assertEqual(remote.calls, [])
            with self.assertRaises(ValueError):
                citations.freeze_publication_package(release.context, Path(temporary) / "new-publication")

    def test_replay_only_policy_cannot_prepare_fresh_inputs_after_marker_removal(self):
        context = copy.deepcopy(self.context)
        context.pop(replay.MARKER)
        with self.assertRaisesRegex(ValueError, "Historical public replay"):
            citations.source_context(context)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "SYNTHETIC-new-freeze"
            with self.assertRaisesRegex(ValueError, "Historical public replay"):
                citations.freeze_publication_package(context, target)
            self.assertFalse(target.exists())

    def test_actual_mirror_entrypoint_accepts_only_verified_recovery(self):
        class ExistingMirror:
            def __init__(self, release):
                self.calls = []
                self.release = release
            def request(self, method, path, **kwargs):
                self.calls.append((method, path))
                if "/git/ref/tags/" in path:
                    return {"ref": "refs/tags/research-" + self.release.context["report"]["release_id"],
                            "object": {"type": "commit", "sha": "a" * 40}}
                if path.endswith("/assets?per_page=100"):
                    return [{"name": "research-archive.zip", "digest": "sha256:" + self.release.package_sha256,
                             "size": len((self.release.package / "research-archive.zip").read_bytes())}]
                remote = {"id": 7, "tag_name": "research-" + self.release.context["report"]["release_id"],
                          "body": self.release.marker, "draft": False, "published_at": "2026-11-16T20:00:00Z",
                          "html_url": "https://github.invalid/SYNTHETIC"}
                return [remote] if "/releases?per_page=100" in path else remote
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            remote = ExistingMirror(release)
            result = publish.GitHubMirror(release, "SYNTHETIC/repo", source_commit="a" * 40, transport=remote, upload_transport=remote).publish()
            self.assertTrue(result["verified"])
            self.assertTrue(remote.calls)
            self.assertEqual({method for method, _ in remote.calls}, {"GET"})

    def remote(self, release):
        remote = FakeZenodo()
        receipt = self.descriptor["archive_receipt"]
        number = receipt["deposition_id"]
        remote.deposits[number] = {"id": number, "record_id": receipt["record_id"],
            "submitted": True, "state": "done", "metadata": {"notes": release.marker,
            "prereserve_doi": {"doi": receipt["reserved_doi"]}}}
        remote.bodies[number] = release.uploads
        remote.files[number] = {name: {"filename": name, "filesize": len(blob),
            "checksum": hashlib.md5(blob).hexdigest()} for name, blob in release.uploads.items()}
        original = remote.public_read
        def public(origin, path, limit):
            blob = original(origin, path, limit)
            if path == "/api/records/" + str(number):
                record = json.loads(blob)
                record["conceptdoi"] = receipt["concept_doi"]
                return json.dumps(record).encode()
            return blob
        return remote, public

    def test_reconcile_existing_publication_is_get_only_and_retries_remain_possible(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            remote, public = self.remote(release)
            adapter = publish.Zenodo(release, transport=remote, public_reader=public)
            class AfterSyntheticPublication(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 11, 17, tzinfo=timezone.utc)
            with patch.object(publish, "datetime", AfterSyntheticPublication):
                self.assertTrue(adapter.reconcile()["anonymous_verified"])
                self.assertTrue(adapter.reconcile()["anonymous_verified"])
            self.assertEqual({method for method, _ in remote.calls}, {"GET"})
            release.require_archive()

    def test_failed_read_only_recheck_preserves_actual_receipt_and_remains_retryable(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            remote, public = self.remote(release)
            adapter = publish.Zenodo(release, transport=remote, public_reader=public)
            original = copy.deepcopy(release.journal.state)
            remote.public_failure = "report.pdf"
            with self.assertRaisesRegex(publish.PublicationBlocked, "anonymous archive failure"):
                adapter.reconcile()
            self.assertEqual(release.journal.state, original)
            remote.public_failure = None
            class AfterSyntheticPublication(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 11, 17, tzinfo=timezone.utc)
            with patch.object(publish, "datetime", AfterSyntheticPublication):
                self.assertTrue(adapter.reconcile()["anonymous_verified"])
            release.require_archive()
            self.assertEqual({method for method, _ in remote.calls}, {"GET"})

    def test_changed_concept_recheck_preserves_actual_receipt_and_remains_retryable(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = self.release(temporary)
            remote, public = self.remote(release)
            record_path = "/api/records/" + str(self.descriptor["archive_receipt"]["record_id"])
            def wrong_concept(origin, path, limit):
                blob = public(origin, path, limit)
                if path == record_path:
                    record = json.loads(blob)
                    record["conceptdoi"] = "10.5281/zenodo.333333333"
                    return json.dumps(record).encode()
                return blob
            adapter = publish.Zenodo(release, transport=remote, public_reader=wrong_concept)
            original = copy.deepcopy(release.journal.state)
            original_bytes = release.journal.path.read_bytes()
            with self.assertRaises(publish.PublicationBlocked):
                adapter.reconcile()
            self.assertEqual(release.journal.state, original)
            self.assertEqual(release.journal.path.read_bytes(), original_bytes)
            adapter.public_read = public
            class AfterSyntheticPublication(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 11, 17, tzinfo=timezone.utc)
            with patch.object(publish, "datetime", AfterSyntheticPublication):
                self.assertTrue(adapter.reconcile()["anonymous_verified"])
            self.assertEqual(release.require_archive()["concept_doi"], original["zenodo"]["concept_doi"])
            self.assertEqual({method for method, _ in remote.calls}, {"GET"})

    def test_coherent_noop_reseal_preserves_a_valid_public_capsule(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            shutil.copytree(self.root, root)
            package = root / self.package.relative_to(self.root)
            descriptor = copy.deepcopy(self.descriptor)
            reseal(root, package, descriptor, lambda source, files: None)
            self.assertTrue(replay.load_published_edition(root, descriptor)["gate"]["ready"])

    def test_reconcile_cannot_downgrade_replay_to_remote_draft_or_another_record(self):
        for change in ({"submitted": False}, {"record_id": 222222222}, {"id": 222222222}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                release = self.release(temporary)
                remote, public = self.remote(release)
                remote.deposits[self.descriptor["archive_receipt"]["deposition_id"]].update(change)
                with self.assertRaises(publish.PublicationBlocked):
                    publish.Zenodo(release, transport=remote, public_reader=public).reconcile()
                self.assertEqual({method for method, _ in remote.calls}, {"GET"})

    def test_root_release_directory_selection_copies_its_exact_frozen_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            shutil.copytree(self.root, root)
            package = root / self.package.relative_to(self.root)
            descriptor = copy.deepcopy(self.descriptor)
            selected = package.parent
            staged = Path(temporary) / "SYNTHETIC-staged-package"
            package.rename(staged)
            selected.rmdir()
            staged.rename(selected)
            descriptor["package_path"] = selected.relative_to(root).as_posix()
            registry = root / citations.PREPARED_REGISTRY
            entry = {"release_id": descriptor["release_id"], "path": descriptor["package_path"],
                     **{key: descriptor[key] for key in replay.PIN_FIELDS}}
            registry.write_bytes(citations.json_bytes({"schema_version": 1, "packages": [entry]}))
            context = replay.load_published_edition(root, descriptor)
            output = Path(temporary) / "SYNTHETIC-public-assets"
            with patch.object(citations, "reproduction_files", side_effect=AssertionError("No fresh recipe")):
                citations.write_publication_assets(context, output)
            self.assertEqual((output / "publication/research-archive.zip").read_bytes(),
                             (selected / "research-archive.zip").read_bytes())
            self.assertEqual((output / "publication/report.pdf").read_bytes(),
                             (selected / "report.pdf").read_bytes())

    def test_coherent_added_private_cache_is_outside_public_member_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            shutil.copytree(self.root, root)
            package = root / self.package.relative_to(self.root)
            descriptor = copy.deepcopy(self.descriptor)
            reseal(root, package, descriptor, lambda source, files: files.update({
                "source-cache.json": b'{"raw_body":"SYNTHETIC private source body"}\n'}))
            with self.assertRaisesRegex(ValueError, "allowlist"):
                replay.load_published_edition(root, descriptor)

    def test_selected_retained_science_cannot_borrow_admitted_prior_reference_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            shutil.copytree(self.root, root)
            package = root / self.package.relative_to(self.root)
            descriptor = copy.deepcopy(self.descriptor)
            def changed(source, files):
                projection = json.loads(files["clean-dataset.json"])
                binding = next(b for b in source["policy"]["audits"]["reference"]["bindings"] if b["observed_positive"])
                row = next(row for row in projection["graph"]["assertions"] if row["id"] == binding["assertion_id"])
                row["value"]["value"] += " SYNTHETIC altered scientific finding"
                for review in projection["graph"]["reviews"]:
                    if row["id"] in review["assertion_sha256"]:
                        review["assertion_sha256"][row["id"]] = graph_module.assertion_digest(row)
                with tempfile.TemporaryDirectory() as exported:
                    for name in citations.write_projection(projection, exported):
                        files[name] = (Path(exported) / name).read_bytes()
                source["graph"] = projection["graph"]
            reseal(root, package, descriptor, changed)
            with self.assertRaisesRegex(ValueError, "admitted scientific binding"):
                replay.load_published_edition(root, descriptor)

    def test_legacy_reference_selected_semantics_also_allow_later_unrelated_additions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, descriptor, _ = fixture(Path(temporary), reference_version=3, reference_original_differs=True)
            context = replay.load_published_edition(root, descriptor)
            self.assertNotEqual(context["replay_verification"]["original_reference_commitments"]["input_graph_sha256"],
                                context["replay_verification"]["original_scientific_graph_sha256"])


if __name__ == "__main__":
    unittest.main()
