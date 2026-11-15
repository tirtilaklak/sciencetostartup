"""Synthetic GitHub source-tag and retry controls; no network or real release."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_publish as publish


SOURCE = "a" * 40
OTHER = "b" * 40


class SyntheticGitHub:
    def __init__(self, release):
        self.release = release
        self.calls, self.releases, self.assets = [], [], []
        self.tag = "research-" + release.context["report"]["release_id"]
        self.ref = {"ref": "refs/tags/" + self.tag, "object": {"type": "commit", "sha": SOURCE}}
        self.tag_reads, self.change_on_read, self.lose = 0, None, None

    def request(self, method, path, payload=None, data=None, **kwargs):
        # Every remote request must follow the durable source-commit binding.
        journal = json.loads(self.release.journal.path.read_bytes())
        if journal["github"].get("source_commit") != SOURCE:
            raise AssertionError("Source identity was not journaled before remote access")
        self.calls.append((method, path, copy.deepcopy(payload)))
        if "/git/ref/tags/" in path:
            self.tag_reads += 1
            if self.tag_reads == self.change_on_read:
                self.ref["object"]["sha"] = OTHER
            return copy.deepcopy(self.ref)
        if method == "GET" and "/releases?" in path:
            return copy.deepcopy(self.releases)
        if method == "POST" and path.endswith("/releases"):
            remote = {"id": 7, **copy.deepcopy(payload), "published_at": None,
                      "html_url": "https://github.invalid/SYNTHETIC/release/7"}
            self.releases.append(remote)
            if self.lose == "create":
                self.lose = None
                raise TimeoutError("SYNTHETIC lost create response")
            return copy.deepcopy(remote)
        if path.endswith("/assets?per_page=100"):
            return copy.deepcopy(self.assets)
        if method == "POST" and "/assets?name=" in path:
            self.assets.append({"name": "research-archive.zip", "size": len(data),
                                "digest": "sha256:" + hashlib.sha256(data).hexdigest()})
            if self.lose == "upload":
                self.lose = None
                raise TimeoutError("SYNTHETIC lost upload response")
            return copy.deepcopy(self.assets[-1])
        if method == "PATCH":
            self.releases[0].update(draft=False, published_at="2026-11-16T20:00:00Z")
            if self.lose == "publish":
                self.lose = None
                raise TimeoutError("SYNTHETIC lost publish response")
            return copy.deepcopy(self.releases[0])
        if method == "GET" and path.endswith("/releases/7"):
            return copy.deepcopy(self.releases[0])
        raise AssertionError((method, path))


class GitHubSourceCommitControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        package = directory / "SYNTHETIC-package"
        package.mkdir()
        blob = b"SYNTHETIC archive bytes, not research or a publication artifact"
        (package / "research-archive.zip").write_bytes(blob)
        self.release = types.SimpleNamespace(
            context={"report": {"release_id": "research-SYNTHETIC.1", "title": "SYNTHETIC title"}},
            package=package, marker="sciencetostartup-package:" + hashlib.sha256(blob).hexdigest(),
            package_sha256=hashlib.sha256(blob).hexdigest(),
            journal=publish.Journal(directory / "SYNTHETIC-journal.json", "research-SYNTHETIC.1",
                                    hashlib.sha256(blob).hexdigest()),
            require_archive=lambda: {"url": "https://doi.invalid/SYNTHETIC"})
        self.remote = SyntheticGitHub(self.release)

    def mirror(self, source=SOURCE):
        return publish.GitHubMirror(self.release, "SYNTHETIC/repository", source_commit=source,
                                   transport=self.remote, upload_transport=self.remote)

    def mutations(self):
        return [call for call in self.remote.calls if call[0] != "GET"]

    def test_full_commit_is_required_and_invalid_values_make_no_remote_request(self):
        for value in (None, SOURCE[:7], "A" * 40, "g" * 40, SOURCE + "\n"):
            with self.subTest(value=value), self.assertRaises(publish.PublicationBlocked):
                self.mirror(value)
        with self.assertRaises(TypeError):
            publish.GitHubMirror(self.release, "SYNTHETIC/repository", transport=self.remote)
        self.assertEqual(self.remote.calls, [])

    def test_missing_annotated_wrong_or_misnamed_tag_holds_before_mutation(self):
        invalid = (None, {"ref": "refs/tags/" + self.remote.tag, "object": {"type": "tag", "sha": SOURCE}},
                   {"ref": "refs/tags/" + self.remote.tag, "object": {"type": "commit", "sha": OTHER}},
                   {"ref": "refs/tags/another-tag", "object": {"type": "commit", "sha": SOURCE}})
        for ref in invalid:
            with self.subTest(ref=ref):
                self.remote.ref = ref
                with self.assertRaisesRegex(publish.PublicationBlocked, "lightweight source tag"):
                    self.mirror().publish()
                self.assertEqual(self.mutations(), [])

    def test_conflicting_journal_source_identity_holds_before_remote_access(self):
        self.release.journal.state["github"]["source_commit"] = OTHER
        self.release.journal.save("SYNTHETIC conflicting prior identity")
        before = self.release.journal.path.read_bytes()
        with self.assertRaisesRegex(publish.PublicationBlocked, "different source commit"):
            self.mirror().publish()
        self.assertEqual(self.remote.calls, [])
        self.assertEqual(self.release.journal.path.read_bytes(), before)

    def test_exact_tag_binds_journal_and_targets_source_commit_without_creating_tag(self):
        result = self.mirror().publish()
        self.assertTrue(result["verified"])
        self.assertEqual(result["source_commit"], SOURCE)
        creation = next(call for call in self.remote.calls if call[0] == "POST" and call[1].endswith("/releases"))
        self.assertEqual(creation[2]["target_commitish"], SOURCE)
        self.assertEqual(creation[2]["tag_name"], "research-research-SYNTHETIC.1")
        self.assertEqual(self.remote.tag_reads, 3)
        self.assertTrue(all("/git/" not in path for method, path, _ in self.mutations()))

    def test_tag_change_before_publish_keeps_release_draft_and_unverified(self):
        self.remote.change_on_read = 2
        with self.assertRaises(publish.PublicationBlocked):
            self.mirror().publish()
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.remote.calls))
        self.assertTrue(self.remote.releases[0]["draft"])
        self.assertFalse(self.release.journal.state["github"]["verified"])

    def test_tag_change_during_final_public_state_verification_is_unverified(self):
        self.remote.change_on_read = 3
        with self.assertRaises(publish.PublicationBlocked):
            self.mirror().publish()
        self.assertFalse(self.remote.releases[0]["draft"])
        self.assertFalse(self.release.journal.state["github"]["verified"])
        self.assertNotEqual(self.release.journal.state["github"]["status"], "published")

    def test_matching_existing_public_release_rechecks_tag_using_gets_only(self):
        self.mirror().publish()
        self.remote.calls.clear()
        self.assertTrue(self.mirror().publish()["verified"])
        self.assertEqual(self.mutations(), [])

    def check_lost_response(self, failure):
        self.remote.lose = failure
        with self.assertRaises(TimeoutError):
            self.mirror().publish()
        self.assertTrue(self.mirror().publish()["verified"])
        self.assertEqual(len(self.remote.releases), 1)
        self.assertEqual(len(self.remote.assets), 1)
        creates = [c for c in self.remote.calls if c[0] == "POST" and c[1].endswith("/releases")]
        patches = [c for c in self.remote.calls if c[0] == "PATCH"]
        uploads = [c for c in self.remote.calls if c[0] == "POST" and "/assets?name=" in c[1]]
        self.assertEqual((len(creates), len(uploads), len(patches)), (1, 1, 1))

    def test_lost_create_response_resumes_without_duplicate_create(self):
        self.check_lost_response("create")

    def test_lost_upload_response_resumes_without_duplicate_upload(self):
        self.check_lost_response("upload")

    def test_lost_publish_response_resumes_without_duplicate_publish(self):
        self.check_lost_response("publish")


if __name__ == "__main__":
    unittest.main()
