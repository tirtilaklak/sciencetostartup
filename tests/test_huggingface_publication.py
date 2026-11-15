"""Synthetic remote failure rehearsals; never research or publication evidence."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_publish import HuggingFaceMirror, Journal, PublicationBlocked


class EntryNotFoundError(Exception):
    pass


class Hub:
    def __init__(self, directory):
        self.directory, self.files = directory, {}
        self.sha, self.private = "a" * 40, False
        self.commits, self.calls = 0, []
        self.public_error, self.public_wrong = None, None
        self.lose_commit = False

    def repo_info(self, **kwargs):
        self.calls.append(("info", kwargs))
        return SimpleNamespace(sha=self.sha, private=self.private)

    def create_commit(self, **kwargs):
        self.calls.append(("commit", kwargs))
        if kwargs["parent_commit"] != self.sha:
            raise RuntimeError("fixture predecessor changed")
        for operation in kwargs["operations"]:
            self.files[operation["path_in_repo"]] = operation["path_or_fileobj"]
        self.commits += 1
        self.sha = hashlib.sha1(str(self.commits).encode()).hexdigest()
        if self.lose_commit:
            self.lose_commit = False
            raise TimeoutError("fixture lost commit response")

    def _download(self, public, **kwargs):
        self.calls.append(("public" if public else "authenticated", kwargs))
        if public and self.public_error:
            raise self.public_error
        if kwargs["filename"] not in self.files:
            raise EntryNotFoundError()
        blob = self.files[kwargs["filename"]]
        if public and self.public_wrong == kwargs["filename"]:
            blob = b"fixture wrong public bytes"
        path = self.directory / ("public" if public else "authenticated") / kwargs["filename"]
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(blob)
        return str(path)

    def download(self, **kwargs):
        return self._download(False, **kwargs)

    def public_download(self, **kwargs):
        return self._download(True, **kwargs)


class PublicMirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name)
        package = directory / "package"
        package.mkdir()
        for name in ("huggingface-README.md", "MANIFEST.json", "research-archive.zip", "clean-dataset.json"):
            (package / name).write_bytes(("UNIT TEST FIXTURE " + name).encode())
        (package / 'metadata.json').write_text(json.dumps({'schema_version': 1,
            'title': 'SYNTHETIC research fixture', 'version': 'fixture-only', 'author': 'Synthetic fixture',
            'url': 'https://example.org', 'updated_on': '2020-01-01', 'license': 'CC-BY-4.0',
            'projection_version': '1.0.0', 'status': 'ready-for-archive', 'note': 'Synthetic prepublication snapshot'}))
        self.archive = {'status': 'published', 'verified': True, 'anonymous_verified': True, 'api_origin': 'https://zenodo.org',
            'environment': 'production', 'record_id': 1, 'doi': '10.5281/zenodo.1',
            'concept_doi': '10.5281/zenodo.99', 'record_url': 'https://zenodo.org/records/1',
            'url': 'https://doi.org/10.5281/zenodo.1', 'confirmed_on': '2020-01-01T00:00:00Z',
            'published_on': '2020-01-01',
            'artifact_sha256': hashlib.sha256((package / 'research-archive.zip').read_bytes()).hexdigest()}
        self.allowed = True
        def require_archive():
            if not self.allowed:
                raise PublicationBlocked("fixture archive gate held")
            return self.archive
        self.release = SimpleNamespace(package=package, marker="fixture-only",
            context={"report": {"release_id": "fixture-only"}},
            journal=Journal(directory / "journal.json", "fixture-only"), require_archive=require_archive)
        self.hub = Hub(directory)
        self.adapter = HuggingFaceMirror(self.release, "test-owner/test-dataset", api=self.hub,
            downloader=self.hub.download, public_downloader=self.hub.public_download,
            operation_factory=lambda **kwargs: kwargs)

    def test_archive_gate_precedes_remote_operations(self):
        self.allowed = False
        with self.assertRaises(PublicationBlocked):
            self.adapter.publish()
        self.assertEqual(self.hub.calls, [])

    def test_public_card_uses_actual_doi_without_rewriting_frozen_snapshot(self):
        frozen = (self.release.package / 'huggingface-README.md').read_bytes()
        result = self.adapter.publish()
        card = self.hub.files['README.md']
        self.assertIn(b'https://doi.org/10.5281/zenodo.1', card)
        self.assertIn(b'```bibtex', card)
        self.assertIn(b'doi = {10.5281/zenodo.1}', card)
        self.assertNotIn(b'Synthetic prepublication snapshot', card)
        self.assertEqual((self.release.package / 'huggingface-README.md').read_bytes(), frozen)
        self.assertEqual(result['readme_sha256'], hashlib.sha256(card).hexdigest())

    @staticmethod
    def reuse_fixture(release_id="fixture-only"):
        """Entirely fabricated public data for executable documentation checks."""
        return {'release_id': release_id, 'projection_version': '1.2.0', 'graph': {
            'assertions': [{'id': 'SYNTHETIC-claim', 'subject_id': 'SYNTHETIC-entity',
                'predicate': 'SYNTHETIC-predicate', 'value': 'SYNTHETIC-value', 'status': 'approved',
                'evidence': [{'source_id': 'SYNTHETIC-source', 'locator': 'SYNTHETIC-scope'}]},
                {'id': 'SYNTHETIC-history', 'status': 'historical', 'evidence': []}],
            'sources': [{'id': 'SYNTHETIC-source', 'url': 'https://example.invalid/source'}]}}

    def execute_public_card_example(self, data, *, served=None, revision=""):
        raw = json.dumps(data).encode()
        (self.release.package / 'clean-dataset.json').write_bytes(raw)
        card = self.adapter._published_readme(self.archive).decode()
        code = card.split('```python\n', 1)[1].split('\n```', 1)[0]
        calls = []
        def anonymous_read(url, *, timeout):
            calls.append(url)
            if url == 'https://huggingface.co/api/datasets/test-owner/test-dataset':
                return io.BytesIO(json.dumps({'sha': 'a' * 40}).encode())
            return io.BytesIO(raw if served is None else served)
        output = io.StringIO()
        with patch('urllib.request.urlopen', anonymous_read), \
                patch.dict('os.environ', {'STS_RESEARCH_REVISION': revision}), redirect_stdout(output):
            exec(compile(code, '<SYNTHETIC rendered Hub example>', 'exec'), {})
        return calls, output.getvalue()

    def test_rendered_card_example_loads_one_commit_and_follows_real_schema(self):
        data = self.reuse_fixture()
        self.assertIn('subject_id', data['graph']['assertions'][0])
        self.assertNotIn('subject', data['graph']['assertions'][0])
        calls, output = self.execute_public_card_example(data)
        self.assertEqual(calls, ['https://huggingface.co/api/datasets/test-owner/test-dataset',
            'https://huggingface.co/datasets/test-owner/test-dataset/resolve/' + 'a' * 40 + '/clean-dataset.json'])
        self.assertIn('fixture-only 1 approved assertions', output)
        self.assertIn('SYNTHETIC-claim SYNTHETIC-entity SYNTHETIC-predicate SYNTHETIC-value', output)
        self.assertIn('https://example.invalid/source SYNTHETIC-scope', output)

    def test_rendered_card_example_accepts_historical_immutable_commit(self):
        calls, output = self.execute_public_card_example(self.reuse_fixture(), revision='b' * 40)
        self.assertEqual(calls, ['https://huggingface.co/datasets/test-owner/test-dataset/resolve/'
                                  + 'b' * 40 + '/clean-dataset.json'])
        self.assertIn('SYNTHETIC-claim SYNTHETIC-entity SYNTHETIC-predicate SYNTHETIC-value', output)

    def test_rendered_card_example_refuses_changed_bytes_or_wrong_edition(self):
        with self.assertRaisesRegex(ValueError, 'Different edition'):
            self.execute_public_card_example(self.reuse_fixture(), served=b'SYNTHETIC changed mirror')
        with self.assertRaisesRegex(ValueError, 'does not match this citation'):
            self.execute_public_card_example(self.reuse_fixture('another-fixture'))

    def test_rendered_card_example_rejects_movable_revision(self):
        with self.assertRaisesRegex(ValueError, 'immutable Hub commit'):
            self.execute_public_card_example(self.reuse_fixture(), revision='main')

    def test_matching_manifest_with_stale_card_gets_one_reconciliation_commit(self):
        for remote, local in [('publication-manifest.json', 'MANIFEST.json'),
                              ('README.md', 'huggingface-README.md'),
                              ('research-archive.zip', 'research-archive.zip'),
                              ('clean-dataset.json', 'clean-dataset.json')]:
            self.hub.files[remote] = (self.release.package / local).read_bytes()
        self.adapter.publish()
        self.adapter.publish()
        self.assertEqual(self.hub.commits, 1)
        self.assertIn(b'10.5281/zenodo.1', self.hub.files['README.md'])

    def test_untyped_or_mismatched_archive_receipt_cannot_generate_public_card(self):
        for field, value in [('doi', '10.5281/zenodo.999'), ('environment', 'sandbox'), ('anonymous_verified', False),
                             ('artifact_sha256', 'a' * 64), ('record_url', 'https://invalid.example/records/1')]:
            with self.subTest(field=field):
                original = self.archive[field]
                self.archive[field] = value
                with self.assertRaises(PublicationBlocked):
                    self.adapter.publish()
                self.assertEqual(self.hub.calls, [])
                self.assertFalse(self.adapter.state['verified'])
                self.archive[field] = original

    def test_receipt_from_another_edition_cannot_be_relabelled(self):
        self.archive['release_id'] = 'another-edition'
        with self.assertRaisesRegex(PublicationBlocked, 'another research edition'):
            self.adapter.publish()
        self.assertEqual(self.hub.calls, [])
        self.assertFalse(self.adapter.state['verified'])

    def test_private_repository_is_refused_before_upload(self):
        self.hub.private = True
        with self.assertRaisesRegex(PublicationBlocked, "public Hub"):
            self.adapter.publish()
        self.assertEqual(self.hub.commits, 0)
        self.assertFalse(self.release.journal.state["huggingface"]["verified"])

    def test_public_receipt_requires_all_four_anonymous_payloads_at_one_commit(self):
        result = self.adapter.publish()
        public = [kwargs for kind, kwargs in self.hub.calls if kind == "public"]
        self.assertEqual({r["filename"] for r in public}, {
            "README.md", "publication-manifest.json", "research-archive.zip", "clean-dataset.json"})
        self.assertTrue(all(r["revision"] == result["commit"] and r["force_download"] for r in public))
        self.assertTrue(result["verified"] and result["anonymous_verified"])
        self.assertEqual(result["status"], "published")
        self.assertEqual(self.hub.commits, 1)

    def test_gated_public_metadata_does_not_pass_authenticated_reads(self):
        self.hub.public_error = PermissionError("fixture anonymous access denied")
        with self.assertRaises(PermissionError):
            self.adapter.publish()
        state = json.loads(self.release.journal.path.read_text())["huggingface"]
        self.assertFalse(state["verified"])
        self.assertFalse(state["anonymous_verified"])
        self.assertEqual(state["pending"], "public-verification")
        self.assertNotEqual(state["status"], "published")

    def test_wrong_anonymous_card_is_held_even_when_manifest_and_data_match(self):
        self.hub.public_wrong = "README.md"
        with self.assertRaisesRegex(PublicationBlocked, "Anonymous Hub mirror bytes"):
            self.adapter.publish()
        self.assertFalse(self.adapter.state["verified"])

    def test_visibility_change_during_public_reads_is_held(self):
        original = self.hub.public_download
        def changing(**kwargs):
            result = original(**kwargs)
            self.hub.private = True
            return result
        self.adapter.public_download = changing
        with self.assertRaisesRegex(PublicationBlocked, "visibility changed"):
            self.adapter.publish()
        self.assertFalse(self.adapter.state["verified"])

    def test_retry_after_public_access_repair_does_not_duplicate_commit(self):
        self.hub.public_error = TimeoutError("fixture interruption")
        with self.assertRaises(TimeoutError):
            self.adapter.publish()
        self.hub.public_error = None
        self.assertTrue(self.adapter.publish()["anonymous_verified"])
        self.assertEqual(self.hub.commits, 1)

    def test_lost_commit_response_reconciles_same_immutable_bytes(self):
        self.hub.lose_commit = True
        with self.assertRaises(TimeoutError):
            self.adapter.publish()
        self.assertTrue(self.adapter.publish()["anonymous_verified"])
        self.assertEqual(self.hub.commits, 1)

    def test_injected_client_requires_explicit_anonymous_downloader(self):
        with self.assertRaisesRegex(ValueError, "anonymous"):
            HuggingFaceMirror(self.release, "test-owner/test-dataset", api=self.hub,
                downloader=self.hub.download, operation_factory=lambda **kwargs: kwargs)

    def test_sdk_clients_pin_official_origin_and_disable_implicit_public_auth(self):
        calls = []
        module = SimpleNamespace(HfApi=lambda **kwargs: calls.append(("api", kwargs)),
            hf_hub_download=lambda **kwargs: calls.append(("download", kwargs)),
            CommitOperationAdd=lambda **kwargs: kwargs)
        with patch.dict(sys.modules, {"huggingface_hub": module}), patch.dict("os.environ", {"HF_ENDPOINT": "https://invalid.example"}):
            adapter = HuggingFaceMirror(self.release, "test-owner/test-dataset", token="UNIT-TEST-TOKEN")
            adapter.public_download(filename="fixture")
        self.assertEqual(calls[0][1]["endpoint"], "https://huggingface.co")
        self.assertIs(calls[1][1]["token"], False)
        self.assertEqual(calls[1][1]["endpoint"], "https://huggingface.co")


if __name__ == "__main__":
    unittest.main()
