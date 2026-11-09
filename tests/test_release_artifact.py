"""Exact-artifact preparation and pre-upload identity guards."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from release_artifact import prepare, secret_file, upload


class ReleaseArtifactTests(unittest.TestCase):
    def fixture(self, directory):
        files = {'index.html': b'<h1>Guide</h1>', '_headers': b'/*\n  X-Content-Type-Options: nosniff\n', '_redirects': b'https://www.example.com/* https://example.com/:splat 301!\n'}
        for name, content in files.items():
            (directory / name).write_bytes(content)
        manifest = {'build_id': 'fixture', 'editorial_release_id': 'review-fixture', 'publication_as_of': '2026-11-08T00:00:00Z',
                    'sha256': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
        (directory / 'manifest.json').write_text(json.dumps(manifest))

    def test_preparation_preserves_headers_and_records_non_versioned_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            artifact, prepared = folder / 'artifact', folder / 'prepared'
            artifact.mkdir()
            self.fixture(artifact)
            receipt = prepare(artifact, prepared, 'a' * 40)
            metadata = json.loads((prepared / 'version-metadata.json').read_text())
            assets = json.loads((prepared / 'assets-manifest.json').read_text())['manifest']
            self.assertEqual(set(assets), {'/index.html', '/manifest.json'})
            self.assertEqual(metadata['assets']['config']['_headers'], (artifact / '_headers').read_text())
            self.assertTrue(receipt['preserved_non_versioned_settings']['observability']['logs']['enabled'])
            self.assertFalse(receipt['preserved_non_versioned_settings']['observability']['traces']['enabled'])
            self.assertEqual(receipt['source_commit'], 'a' * 40)

    def test_mutated_artifact_is_rejected_before_reading_upload_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            artifact, prepared = folder / 'artifact', folder / 'prepared'
            artifact.mkdir()
            self.fixture(artifact)
            prepare(artifact, prepared, 'a' * 40)
            (artifact / 'index.html').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Artifact digest differs'):
                upload(artifact, prepared, folder / 'absent-session', folder / 'completion')

    def test_upload_authorization_cannot_be_written_inside_repository(self):
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            secret_file(ROOT / 'output' / 'forbidden-authorization.json', {'jwt': 'fixture'})


if __name__ == '__main__':
    unittest.main()
