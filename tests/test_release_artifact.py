"""Exact-artifact preparation and pre-upload identity guards."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from release_artifact import prepare, secret_file, upload


class ReleaseArtifactTests(unittest.TestCase):
    def test_asset_limit_accepts_boundary_and_rejects_oversize_before_preparation(self):
        for size in (1024, 1025):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                artifact, prepared = folder / 'artifact', folder / 'prepared'
                artifact.mkdir()
                self.fixture(artifact)
                content = b'x' * size
                (artifact / 'research-archive.zip').write_bytes(content)
                manifest = json.loads((artifact / 'manifest.json').read_text())
                manifest['sha256']['research-archive.zip'] = hashlib.sha256(content).hexdigest()
                (artifact / 'manifest.json').write_text(json.dumps(manifest))
                with patch('release_artifact.STATIC_ASSET_LIMIT_BYTES', 1024):
                    if size == 1024:
                        prepare(artifact, prepared, 'a' * 40)
                    else:
                        with self.assertRaisesRegex(ValueError, 'hosting limit: research-archive.zip'):
                            prepare(artifact, prepared, 'a' * 40)
                        self.assertFalse(prepared.exists())

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


class ReleaseUploadContractTests(unittest.TestCase):
    """Mock Cloudflare only; validate public bytes before any authorization dispatch."""
    fixture = ReleaseArtifactTests.fixture

    def setUp(self):
        import release_artifact as release
        self.release = release
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.artifact, self.prepared = self.folder / 'artifact', self.folder / 'prepared'
        self.artifact.mkdir()
        self.fixture(self.artifact)
        self.receipt = prepare(self.artifact, self.prepared, 'a' * 40)
        self.expected = dict(expected_source_commit='a' * 40, expected_worker=self.receipt['cloudflare_worker'],
            expected_manifest_sha256=self.receipt['manifest_sha256'], expected_plan_sha256=self.receipt['plan_sha256'])
        self.validated = release.validate_prepared(self.artifact, self.prepared, **self.expected)
        self.hashes = [x['hash'] for x in self.validated['assets_manifest']['manifest'].values()]
        self.session, self.completion = self.folder / 'session.json', self.folder / 'completion.json'
        self.write_session([[self.hashes[0]], [self.hashes[1]]])

    def write_session(self, buckets):
        self.binding = dict(worker=self.expected['expected_worker'], source_commit='a' * 40,
            manifest_sha256=self.receipt['manifest_sha256'], plan_sha256=self.receipt['plan_sha256'],
            run_id='contract-run', session_operation_id='session-operation',
            buckets_sha256=self.release.digest(self.release.canonical(buckets)))
        secret_file(self.session, {'jwt': 'synthetic-session-only', 'buckets': buckets, 'binding': self.binding})

    def send(self, index=0, **changes):
        arguments = dict(self.expected, expected_session_binding=self.binding, expected_operation_id='upload-operation',
            expected_run_id='contract-run', expected_session_operation_id='session-operation')
        arguments.update(changes)
        return self.release.upload_bucket(self.artifact, self.prepared, self.session, self.completion, index, **arguments)

    @staticmethod
    def response(status, payload):
        import io
        value = io.BytesIO(json.dumps(payload).encode())
        value.status = status
        return value

    def test_prepared_plan_tampering_fails_before_authorization(self):
        for name in ('asset-lookup.json', 'assets-manifest.json', 'version-metadata.json', 'receipt.json'):
            path = self.prepared / name
            original = path.read_bytes()
            path.write_text('{}')
            with self.subTest(name=name), patch('release_artifact.urlopen') as network:
                with self.assertRaises(ValueError):
                    self.send()
                network.assert_not_called()
            path.write_bytes(original)

    def test_coherent_receipt_and_metadata_retagging_cannot_change_trusted_source(self):
        receipt = json.loads((self.prepared / 'receipt.json').read_text())
        receipt['source_commit'] = 'b' * 40
        (self.prepared / 'receipt.json').write_text(json.dumps(receipt))
        metadata = json.loads((self.prepared / 'version-metadata.json').read_text())
        metadata['annotations']['workers/commit_sha'] = 'b' * 40
        (self.prepared / 'version-metadata.json').write_text(json.dumps(metadata))
        with patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
            self.send()
        network.assert_not_called()

    def test_independent_source_worker_manifest_and_plan_are_required(self):
        for field, wrong in (('expected_source_commit', 'b' * 40), ('expected_worker', 'different-worker'),
                             ('expected_manifest_sha256', '0' * 64), ('expected_plan_sha256', '0' * 64)):
            with self.subTest(field=field), patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
                self.send(**{field: wrong})
            network.assert_not_called()

    def test_prepare_retry_preserves_lifecycle_receipt(self):
        path = self.prepared / 'receipt.json'
        receipt = json.loads(path.read_text())
        receipt['lifecycle'] = [{'version': 'retained-version', 'deployment': 'retained-deployment'}]
        path.write_text(json.dumps(receipt))
        original = path.read_bytes()
        prepare(self.artifact, self.prepared, 'a' * 40)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError):
            prepare(self.artifact, self.prepared, 'b' * 40)
        self.assertEqual(path.read_bytes(), original)

    def test_unsafe_artifact_entries_fail_before_preparation(self):
        outside = self.folder / 'outside.txt'
        outside.write_text('synthetic outside fixture')
        target = self.artifact / 'linked'
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            prepare(self.artifact, self.folder / 'new-prepared', 'a' * 40)
        target.unlink()
        target.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare(self.artifact, self.folder / 'new-prepared', 'a' * 40)
        target.unlink()
        import os
        os.mkfifo(target)
        with self.assertRaises(ValueError):
            prepare(self.artifact, self.folder / 'new-prepared', 'a' * 40)

    def test_manifest_paths_and_duplicate_keys_are_rejected(self):
        path = self.artifact / 'manifest.json'
        original = path.read_bytes()
        for name in ('../outside', '/absolute', 'nested//file', 'nested\\file'):
            value = json.loads(original)
            value['sha256'][name] = '0' * 64
            path.write_text(json.dumps(value))
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.release.validate_artifact(self.artifact)
        path.write_bytes(original[:-1] + b',"build_id":"other"}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.release.validate_artifact(self.artifact)

    def test_authorization_paths_cannot_overlap_artifact_or_preparation(self):
        for output in (self.artifact / 'authorization', self.prepared / 'authorization', self.session):
            with self.subTest(output=output), patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
                self.release.upload_bucket(self.artifact, self.prepared, self.session, output, 0,
                    **self.expected, expected_session_binding=self.binding, expected_operation_id='upload-operation',
                    expected_run_id='contract-run', expected_session_operation_id='session-operation')
            network.assert_not_called()

    def test_completion_path_validation_precedes_dispatch(self):
        self.completion.symlink_to(self.folder / 'outside')
        with patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
            self.send()
        network.assert_not_called()

    def test_authorization_parent_symlink_or_public_directory_is_rejected(self):
        linked = self.folder / 'linked'
        linked.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(ValueError):
            secret_file(linked / 'secret', {'jwt': 'synthetic'})
        public = self.folder / 'public'
        public.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            secret_file(public / 'secret', {'jwt': 'synthetic'})

    def test_unknown_hash_in_later_bucket_prevents_every_request(self):
        self.write_session([[self.hashes[0]], ['0' * 32]])
        with patch('release_artifact.urlopen') as network, self.assertRaisesRegex(ValueError, 'Unknown'):
            self.send()
        network.assert_not_called()

    def test_duplicate_bucket_hashes_are_rejected(self):
        for buckets in ([[self.hashes[0], self.hashes[0]]], [[self.hashes[0]], [self.hashes[0]]]):
            self.write_session(buckets)
            with patch('release_artifact.urlopen') as network, self.assertRaisesRegex(ValueError, 'duplicate'):
                self.send()
            network.assert_not_called()

    def test_malformed_bucket_shapes_are_rejected(self):
        for buckets in (None, True, 'hash', {}, [[]], ['hash'], [[None]], [[True]], [['not-a-hash']]):
            self.write_session(buckets)
            with self.subTest(buckets=buckets), patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
                self.send()
            network.assert_not_called()

    def test_identical_content_deduplication_remains_valid(self):
        content = (self.artifact / 'index.html').read_bytes()
        (self.artifact / 'copy.html').write_bytes(content)
        manifest = json.loads((self.artifact / 'manifest.json').read_text())
        manifest['sha256']['copy.html'] = hashlib.sha256(content).hexdigest()
        (self.artifact / 'manifest.json').write_text(json.dumps(manifest))
        prepared = self.folder / 'deduplicated'
        prepare(self.artifact, prepared, 'a' * 40)
        assets = json.loads((prepared / 'assets-manifest.json').read_text())['manifest']
        self.assertEqual(assets['/index.html'], assets['/copy.html'])
        lookup = json.loads((prepared / 'asset-lookup.json').read_text())
        self.assertEqual(len(lookup), len(assets) - 1)

    def test_zero_bucket_session_still_requires_matching_binding(self):
        self.write_session([])
        for key in self.binding:
            value = dict(self.binding)
            value[key] = 'different'
            with self.subTest(key=key), patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
                self.send(None, expected_session_binding=value, expected_operation_id=None)
            network.assert_not_called()

    def test_payload_changed_after_initial_validation_is_not_sent(self):
        original = self.release.validate_prepared
        def mutate(*args, **kwargs):
            value = original(*args, **kwargs)
            (self.artifact / 'index.html').write_text('changed after validation')
            return value
        with patch('release_artifact.validate_prepared', side_effect=mutate), patch('release_artifact.urlopen') as network:
            with self.assertRaisesRegex(ValueError, 'digest differs'):
                self.send()
        network.assert_not_called()

    def test_bucket_upload_dispatches_exactly_once_and_freezes_verified_bytes(self):
        name = self.validated['asset_lookup'][self.hashes[0]]
        content = (self.artifact / name).read_bytes()
        def accept(request, timeout):
            (self.artifact / name).write_text('changed only after dispatch')
            self.assertIn(__import__('base64').b64encode(content), request.data)
            self.assertNotIn(__import__('base64').b64encode(b'changed only after dispatch'), request.data)
            self.assertEqual(timeout, 120)
            return self.response(202, {'success': True, 'result': {}})
        with patch('release_artifact.urlopen', side_effect=accept) as network:
            result = self.send()
        self.assertEqual(network.call_count, 1)
        self.assertEqual(result['uploaded_assets'], 1)
        self.assertEqual(result['operation_id'], 'upload-operation')
        self.assertEqual(result['outcome'], 'succeeded')

    def test_intermediate_202_does_not_require_completion_jwt(self):
        with patch('release_artifact.urlopen', return_value=self.response(202, {'success': True, 'result': {}})):
            result = self.send()
        self.assertFalse(result['completion_stored'])
        self.assertFalse(self.completion.exists())

    def test_final_201_stores_completion_privately(self):
        with patch('release_artifact.urlopen', return_value=self.response(201, {'success': True, 'result': {'jwt': 'synthetic-final-only'}})):
            result = self.send()
        self.assertTrue(result['completion_stored'])
        self.assertEqual(self.completion.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.completion.read_text()), {'jwt': 'synthetic-final-only'})
        self.assertNotIn('synthetic-final', json.dumps(result))

    def test_zero_buckets_make_no_upload_request(self):
        self.write_session([])
        with patch('release_artifact.urlopen') as network:
            result = self.send(None, expected_operation_id=None)
        network.assert_not_called()
        self.assertFalse(result['dispatched'])
        self.assertTrue(result['completion_stored'])

    def test_ambiguous_transport_outcomes_never_retry(self):
        from urllib.error import HTTPError, URLError
        for failure in (TimeoutError('synthetic timeout'), URLError('synthetic connection loss'),
                        HTTPError('https://api.cloudflare.com/', 500, 'synthetic', {}, None),
                        HTTPError('https://api.cloudflare.com/', 499, 'synthetic', {}, None)):
            with self.subTest(failure=type(failure)), patch('release_artifact.urlopen', side_effect=failure) as network:
                with self.assertRaises(self.release.UploadOutcomeError) as caught:
                    self.send()
                self.assertEqual(caught.exception.result['outcome'], 'uncertain')
                self.assertEqual(network.call_count, 1)
                self.assertNotIn('synthetic-session', str(caught.exception))

    def test_known_remote_success_survives_completion_storage_error(self):
        with patch('release_artifact.urlopen', return_value=self.response(201, {'success': True, 'result': {'jwt': 'synthetic-final-only'}})) as network:
            with patch('release_artifact.secret_file', side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(self.release.UploadOutcomeError) as caught:
                    self.send()
        self.assertEqual(network.call_count, 1)
        self.assertEqual(caught.exception.result['outcome'], 'succeeded')
        self.assertTrue(caught.exception.result['remote_succeeded'])
        self.assertFalse(caught.exception.result['completion_stored'])

    def test_malformed_accepted_response_requires_reconciliation(self):
        for status, payload in ((201, {'success': True, 'result': {}}), (202, {'success': True}),
                                (200, {'success': True, 'result': {}}), (202, {'success': False, 'result': {}})):
            with self.subTest(status=status, payload=payload), patch('release_artifact.urlopen', return_value=self.response(status, payload)) as network:
                with self.assertRaises(self.release.UploadOutcomeError) as caught:
                    self.send()
                self.assertEqual(caught.exception.result['outcome'], 'uncertain')
                self.assertEqual(network.call_count, 1)


    def test_coherent_session_run_retagging_fails_against_independent_run(self):
        payload = json.loads(self.session.read_text())
        self.binding['run_id'] = 'different-run'
        payload['binding'] = self.binding
        secret_file(self.session, payload)
        with patch('release_artifact.urlopen') as network, self.assertRaisesRegex(ValueError, 'independently expected'):
            self.send()
        network.assert_not_called()

    def test_cli_validation_and_zero_bucket_reuse_have_no_network(self):
        import contextlib
        import io
        self.write_session([])
        common = ['--dist', str(self.artifact), '--prepared', str(self.prepared),
                  '--expected-source-commit', 'a' * 40, '--expected-worker', self.expected['expected_worker'],
                  '--expected-manifest-sha256', self.receipt['manifest_sha256'],
                  '--expected-plan-sha256', self.receipt['plan_sha256']]
        for command, extra in (('validate-prepared', []), ('upload-bucket', [
                '--session', str(self.session), '--completion', str(self.completion),
                '--expected-run-id', 'contract-run', '--expected-session-operation-id', 'session-operation',
                '--expected-buckets-sha256', self.binding['buckets_sha256']])):
            output = io.StringIO()
            with patch('sys.argv', ['release_artifact.py', command, *common, *extra]), contextlib.redirect_stdout(output), patch('release_artifact.urlopen') as network:
                self.assertEqual(self.release.main(), 0)
            network.assert_not_called()
            value = json.loads(output.getvalue())
            self.assertNotIn('synthetic-session', output.getvalue())
            self.assertEqual(value['plan_sha256'], self.receipt['plan_sha256'])


    def test_unexpected_prepared_document_types_fail_before_dispatch(self):
        for name in ('assets-manifest.json', 'asset-lookup.json', 'version-metadata.json', 'receipt.json'):
            path = self.prepared / name
            original = path.read_bytes()
            for value in (None, [], True, 'unexpected', 42):
                path.write_text(json.dumps(value))
                with self.subTest(name=name, value=value), patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
                    self.send()
                network.assert_not_called()
            path.write_bytes(original)


    def test_prepared_json_scalar_types_cannot_masquerade_as_equal_values(self):
        path = self.prepared / 'version-metadata.json'
        metadata = json.loads(path.read_text())
        metadata['assets']['config']['run_worker_first'] = 0
        path.write_text(json.dumps(metadata))
        with patch('release_artifact.urlopen') as network, self.assertRaises(ValueError):
            self.send()
        network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
