"""TEST-ONLY published replay and draft privacy; no real publication is claimed."""
import copy
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import research_publish as publish
from research_graph import assertion_digest
from research_report import build_context
from research_lifecycle_fixtures import isolated_render_context, isolated_render_preparation
from test_publication_context import prepare_fixture, write_registry
from test_research_publish import FakeZenodo


def published_context(context, package):
    value = copy.deepcopy(context)
    value['report'].update(status='published', archive={
        'status': 'published', 'verified': True, 'anonymous_verified': True, 'api_origin': 'https://zenodo.org', 'environment': 'production',
        'record_id': 123, 'doi': '10.5281/zenodo.123', 'concept_doi': '10.5281/zenodo.999',
        'record_url': 'https://zenodo.org/records/123', 'confirmed_on': '2026-11-09T00:00:00Z',
        'release_id': context['report']['release_id'],
        'artifact_sha256': citations.sha256((package / 'research-archive.zip').read_bytes())})
    return value


class HistoricalV2Tests(unittest.TestCase):
    def test_published_v2_replays_complete_pinned_recipe_after_each_current_input_changes_or_disappears(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, committed_path=True)
            write_registry(context, package)
            historical = published_context(context, package)
            frozen = citations.read_prepared_package(historical, package)
            for name, relative in citations.REPRODUCTION_INPUTS.items():
                path = Path(context['root']) / relative
                original = path.read_bytes()
                for missing in (False, True):
                    with self.subTest(name=name, missing=missing):
                        path.unlink() if missing else path.write_bytes(original + b'\nTEST-ONLY later recipe update\n')
                        with self.assertRaises(ValueError):
                            citations.read_prepared_package(context, package)
                        with self.assertRaises(ValueError):
                            citations.prepared_package_selection(context)
                        with patch.object(citations, 'reproduction_files', side_effect=AssertionError('No current recipe reads')), \
                                patch.object(citations, 'write_projection', side_effect=AssertionError('No SQLite writer')), \
                                patch.object(citations, 'verified_pdf', side_effect=AssertionError('No PDF writer/receipt')), \
                                patch.object(citations, 'deterministic_zip', side_effect=AssertionError('No ZIP writer')), \
                                patch('zlib.compressobj', side_effect=AssertionError('No compression')), \
                                patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
                            selected = {**historical, **citations.prepared_package_selection(historical)}
                            self.assertEqual(citations.read_prepared_package(selected, package), frozen)
                            citations.write_publication_assets(selected, directory / 'site')
                        for member, blob in frozen.items():
                            self.assertEqual((directory / 'site/publication' / member).read_bytes(), blob)
                        path.write_bytes(original)
            done = subprocess.run([sys.executable, str(package / 'reproduce.py'), '--directory', str(package)],
                                  check=True, capture_output=True, text=True)
            self.assertTrue(json.loads(done.stdout)['exports_equivalent'])

    def test_typed_receipt_exact_digest_is_required_and_research_core_still_cannot_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            historical = published_context(context, package)
            (Path(context['root']) / 'LICENSE').unlink()
            with self.assertRaisesRegex(ValueError, 'prepublication source context'):
                citations.freeze_publication_package(historical, Path(temporary) / 'new-freeze')
            changes = ({'artifact_sha256': '0' * 64}, {'api_origin': 'https://sandbox.zenodo.org', 'environment': 'sandbox'},
                       {'status': 'published', 'verified': False})
            for change in changes:
                bad = copy.deepcopy(historical)
                bad['report']['archive'].update(change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    citations.read_prepared_package(bad, package)
            bare = copy.deepcopy(context)
            bare['report']['archive'] = {'status': 'published', 'verified': True}
            with self.assertRaises(ValueError):
                citations.read_prepared_package(bare, package)
            flagged = {**context, 'published': True, 'historical_recipe': True}
            with self.assertRaises(ValueError):
                citations.read_prepared_package(flagged, package)
            historical['report']['sections'][0]['paragraphs'][0]['text'] += ' TEST-ONLY changed research'
            with self.assertRaisesRegex(ValueError, 'source context'):
                citations.read_prepared_package(historical, package)

    def test_pinned_recipe_allowlist_and_descriptors_remain_strict_with_a_matching_synthetic_receipt(self):
        for change in ('missing', 'null', 'different-hash'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                context, package = prepare_fixture(Path(temporary))
                files = citations.read_prepared_package(context, package)
                source = json.loads(files['source-context.json'])
                inputs = source['package_context']['reproduction_inputs']
                if change == 'missing':
                    inputs.pop('LICENSE')
                elif change == 'null':
                    inputs['LICENSE'] = None
                else:
                    inputs['LICENSE']['sha256'] = '0' * 64
                files['source-context.json'] = citations.json_bytes(source)
                digest = citations.sha256(files['source-context.json'])
                manifest = json.loads(files['MANIFEST.json'])
                manifest['context_sha256'] = digest
                manifest['files']['source-context.json'] = {'sha256': digest, 'bytes': len(files['source-context.json'])}
                files['MANIFEST.json'] = citations.json_bytes(manifest)
                archive_files = {name: blob for name, blob in files.items() if name not in {'PREPARED.json', 'research-archive.zip'}}
                files['research-archive.zip'] = citations.deterministic_zip(archive_files, compression='deflate')
                contract = json.loads(files['PREPARED.json'])
                contract.update(context_sha256=digest, manifest_sha256=citations.sha256(files['MANIFEST.json']),
                    archive_sha256=citations.sha256(files['research-archive.zip']), archive_bytes=len(files['research-archive.zip']))
                files['PREPARED.json'] = citations.json_bytes(contract)
                for name, blob in files.items():
                    (package / name).write_bytes(blob)
                with self.assertRaisesRegex(ValueError, 'reproduction input'):
                    citations.read_prepared_package(published_context(context, package), package)

    def test_initial_upload_is_current_strict_but_verified_published_retries_use_the_frozen_recipe(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, publish_enabled=True)
            remote = FakeZenodo()
            gate = types.SimpleNamespace(publication_gate=lambda *args: context['gate'])
            journal = directory / 'TEST-ONLY-journal.json'
            source = Path(context['root']) / 'LICENSE'
            original = source.read_bytes()
            with patch.dict(sys.modules, {'research_report': gate}):
                release = publish.Release(context, package, journal)
                adapter = publish.Zenodo(release, transport=remote, public_reader=remote.public_read)
                source.write_bytes(original + b'\nTEST-ONLY premature change\n')
                with self.assertRaises(publish.PublicationBlocked):
                    adapter.upload()
                self.assertEqual(remote.calls, [])
                source.write_bytes(original)
                adapter.upload()
                remote.lose = 'publish'
                with self.assertRaises(TimeoutError):
                    adapter.publish()
                source.unlink()
                calls = len(remote.calls)
                with self.assertRaises(publish.PublicationBlocked):
                    adapter.publish()  # Unconfirmed lost response remains current-input strict.
                self.assertEqual(len(remote.calls), calls)
                source.write_bytes(original)
                adapter.publish()
                self.assertTrue(release.require_archive()['verified'])
                source.unlink()
                retry = publish.Release(context, package, journal)
                adapter = publish.Zenodo(retry, transport=remote, public_reader=remote.public_read)
                with patch.object(citations, 'reproduction_files', side_effect=AssertionError('No current recipe reads')):
                    self.assertTrue(retry.require_archive()['verified'])
                    adapter.publish()
                    adapter.reconcile()
                self.assertEqual(len(remote.deposits), 1)
                self.assertEqual(sum(path.endswith('/actions/publish') for _, path in remote.calls), 1)
                baseline = copy.deepcopy(retry.journal.state['zenodo'])
                for bad in ({'artifact_sha256': '0' * 64}, {'environment': 'sandbox'}, {'verified': False}):
                    retry.journal.state['zenodo'] = {**baseline, **bad}
                    with self.subTest(journal=bad), self.assertRaises(publish.PublicationBlocked):
                        retry.verify()

    def test_published_source_receipt_with_lost_journal_only_reconciles_existing_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, publish_enabled=True)
            remote = FakeZenodo()
            gate = types.SimpleNamespace(publication_gate=lambda *args: context['gate'])
            with patch.dict(sys.modules, {'research_report': gate}):
                release = publish.Release(context, package, directory / 'TEST-ONLY-first.json')
                first = publish.Zenodo(release, transport=remote, public_reader=remote.public_read)
                first.upload()
                first.publish()
                published = copy.deepcopy(context)
                published['report']['archive'] = release.archive_receipt()
                (Path(context['root']) / 'LICENSE').unlink()
                recovered = publish.Zenodo(publish.Release(published, package, directory / 'TEST-ONLY-lost-journal.json'), transport=remote, public_reader=remote.public_read)
                start = len(remote.calls)
                with self.assertRaises(publish.PublicationBlocked):
                    recovered.upload()
                with self.assertRaises(publish.PublicationBlocked):
                    recovered.draft(previous_id=1)
                self.assertEqual(len(remote.calls), start)
                recovered.draft()
                recovered.publish()
                self.assertTrue(all(method == 'GET' for method, _ in remote.calls[start:]))
                self.assertEqual(len(remote.deposits), 1)
                self.assertEqual(sum(path.endswith('/actions/publish') for _, path in remote.calls), 1)


class DraftPrivacyTests(unittest.TestCase):
    def test_verified_synthetic_public_replay_can_only_become_a_held_mutable_fixture(self):
        import research_edition_replay as replay
        from test_research_edition_replay import fixture

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, package, descriptor, _ = fixture(directory)
            baseline = replay.load_published_edition(root, descriptor)
            frozen = replay.read_replay_package(baseline)
            baseline_before = copy.deepcopy(baseline)
            capsule_before = {path.name: path.read_bytes() for path in package.iterdir() if path.is_file()}
            self.assertTrue(baseline['gate']['ready'])
            self.assertFalse(baseline['gate']['archival_ready'])
            self.assertEqual(baseline['policy']['mode'], 'replay_only')
            # Unmodified verified replay never acquires fresh preparation or
            # adapter authority. These controls do not patch a gate or reader.
            with self.assertRaisesRegex(ValueError, 'Historical public replay'):
                citations.freeze_publication_package(baseline, directory / 'forbidden-freeze')
            with self.assertRaisesRegex(ValueError, 'Historical public replay'):
                publish.PublicationPlan(baseline, directory / 'forbidden-plan.json')
            with self.assertRaises(publish.PublicationBlocked):
                publish.archival_gate(baseline)

            enriched = copy.deepcopy(baseline)
            # Explicit TEST-ONLY sentinels check removal of the newer selector
            # keys; they are not assertions of an authenticated source selector.
            enriched['published_source_selection'] = {'TEST-ONLY': 'selector sentinel'}
            enriched['public_edition_ledger'] = [{'TEST-ONLY': 'ledger sentinel'}]
            enriched['edition_snapshots'] = {descriptor['release_id']: copy.deepcopy(baseline)}
            before = copy.deepcopy(enriched)
            stripped = isolated_render_context(enriched)
            self.assertEqual(enriched, before)
            self.assertNotIn('published_source_selection', stripped)
            self.assertNotIn('public_edition_ledger', stripped)
            # A minimal public source tree has capsules, not private authoring
            # or current mutable owned-data inputs beside them.
            for path in (root / 'data/research').iterdir():
                if path.name not in {'releases', 'prepared-packages.json'}:
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
            for name in ('graph.json', 'report.json', 'policy.json', 'audit-admissions.json',
                         'source-manifestations.json', 'fonts'):
                self.assertFalse((root / 'data/research' / name).exists(), name)
            canonical_bytes = (ROOT / 'data/canonical.json').read_bytes()
            with patch('urllib.request.urlopen', side_effect=AssertionError('No network')), \
                    patch('socket.create_connection', side_effect=AssertionError('No network connection')), \
                    patch('subprocess.run', side_effect=AssertionError('No subprocess')), \
                    patch('runpy.run_path', side_effect=AssertionError('No archived Python execution')), \
                    patch('importlib.util.spec_from_file_location', side_effect=AssertionError('No archived Python import')), \
                    isolated_render_preparation(baseline, canonical_bytes=canonical_bytes) as context:
                self.assertNotEqual(context['root'], root)
                self.assertEqual((context['root'] / 'data/canonical.json').read_bytes(), canonical_bytes)
                self.assertEqual(json.loads((context['root'] / 'data/research/audit-admissions.json').read_bytes()),
                                 {'schema_version': '1.0.0', 'admissions': {}})
                for name in ('graph.json', 'report.json', 'policy.json'):
                    self.assertFalse((context['root'] / 'data/research' / name).exists(), name)
                self.assertEqual(context['policy']['mode'], 'prepare_only')
                self.assertEqual(context['report']['status'], 'prelaunch')
                self.assertEqual(context['report']['archive'], {'status': 'not_published', 'doi': None})
                self.assertEqual(context['report']['editions'], [])
                self.assertEqual(context['edition_snapshots'], {})
                for key in ('prepared_package', 'prepared_package_expected', 'published_edition_replay',
                            'replay_verification', 'published_source_selection', 'public_edition_ledger'):
                    self.assertNotIn(key, context)
                for key in ('audits', 'audit_inputs', 'audit_admissions', 'initial_launch_authorization'):
                    self.assertNotIn(key, context['policy'])
                self.assertFalse(context['gate']['ready'])
                self.assertFalse(context['gate']['archival_ready'])
                self.assertTrue(context['gate']['archive_reasons'])

                marker = 'TEST-ONLY-MUTABLE-DRAFT-NOT-PUBLISHED'
                draft = copy.deepcopy(next(row for row in context['graph']['assertions']
                                           if row['status'] == 'approved'))
                draft.update(id='TEST-ONLY.mutable-draft', status='candidate', review_ids=[],
                             value={'type': 'text', 'value': marker})
                context['graph']['assertions'].append(draft)
                projection = citations.public_projection(context, json.loads(canonical_bytes))
                with patch.object(citations, 'public_projection', return_value=projection), \
                        patch.object(citations, 'verified_pdf', return_value=None):
                    held = citations.freeze_publication_package(context, directory / 'TEST-ONLY-held-preparation',
                                                                archive_compression='deflate')
                    files = citations.read_prepared_package(context, held)
                self.assertNotIn(marker.encode(), files['source-context.json'])
                source = json.loads(files['source-context.json'])
                self.assertEqual(source['input_commitments']['graph_sha256'],
                                 citations.sha256(citations.json_bytes(context['graph'])))
                self.assertNotEqual(source['input_commitments']['graph_sha256'],
                                    baseline['replay_verification']['input_commitments']['graph_sha256'])
                status = json.loads((held / 'package-status.json').read_bytes())
                self.assertEqual(status['archive'], 'not-published')
                self.assertFalse(status['publication_ready'])
                with self.assertRaises(publish.PublicationBlocked):
                    publish.PublicationPlan(context, directory / 'held-plan.json').verify()
            self.assertEqual(replay.read_replay_package(baseline), frozen)
            self.assertEqual(baseline, baseline_before)
            self.assertFalse(context['root'].exists(), 'Temporary owned recipe must be cleaned up')
            self.assertEqual({path.name: path.read_bytes() for path in package.iterdir() if path.is_file()},
                             capsule_before)
            self.assertEqual((package / 'research-archive.zip').read_bytes(), frozen['research-archive.zip'])

    def test_public_owned_recipe_must_match_current_owned_bytes_without_fallback(self):
        import research_edition_replay as replay
        from test_research_edition_replay import fixture, reseal

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, package, descriptor, _ = fixture(directory / 'original')
            baseline = replay.load_published_edition(root, descriptor)
            frozen = replay.read_replay_package(baseline)
            changed_root = directory / 'TEST-ONLY-changed-public-recipe'
            shutil.copytree(root, changed_root)
            changed_package = changed_root / package.relative_to(root)
            changed_descriptor = copy.deepcopy(descriptor)

            def incompatible_owned_license(source, files):
                name = 'LICENSE'
                files[name] += b'\nTEST-ONLY later public license fixture, not a license change.\n'
                source['package_context']['reproduction_inputs'][name] = {
                    'bytes': len(files[name]), 'sha256': citations.sha256(files[name])}

            # A coherently pinned, wholly synthetic historical recipe can be
            # read as bytes. It cannot seed a fresh current-recipe test fixture.
            reseal(changed_root, changed_package, changed_descriptor, incompatible_owned_license)
            changed = replay.load_published_edition(changed_root, changed_descriptor)
            with patch('urllib.request.urlopen', side_effect=AssertionError('No network')), \
                    patch('socket.create_connection', side_effect=AssertionError('No network connection')), \
                    patch('runpy.run_path', side_effect=AssertionError('No archived Python execution')), \
                    patch('importlib.util.spec_from_file_location', side_effect=AssertionError('No archived Python import')):
                with self.assertRaisesRegex(ValueError, 'Incompatible current public owned input: LICENSE'):
                    with isolated_render_preparation(changed,
                            canonical_bytes=(ROOT / 'data/canonical.json').read_bytes()):
                        self.fail('Incompatible owned bytes must not seed a preparation')
            self.assertEqual(replay.read_replay_package(baseline), frozen)

    def test_actual_graph_fixture_drafts_are_absent_from_every_archive_representation_and_remain_hash_bound(self):
        baseline = build_context(ROOT, select_prepared=False)
        with isolated_render_preparation(baseline, canonical_bytes=(ROOT / 'data/canonical.json').read_bytes()) as context:
            self.assert_drafts_are_private_and_hash_bound(context)

    def assert_drafts_are_private_and_hash_bound(self, context):
        before = {row['id']: assertion_digest(row) for row in context['graph']['assertions'] if row['status'] == 'approved'}
        marker = 'TEST-ONLY-PRIVATE-UNAPPROVED-DRAFT-NEVER-PUBLISH'
        original = next(row for row in context['graph']['assertions'] if row['status'] == 'approved')
        for status in ('candidate', 'rejected'):
            row = copy.deepcopy(original)
            row.update(id='TEST-ONLY.' + status, status=status, object_id=None,
                       value={'type': 'text', 'value': marker}, qualifications=[marker], review_ids=[])
            review = copy.deepcopy(context['graph']['reviews'][0])
            review.update(id='TEST-ONLY.review.' + status, assertion_ids=[row['id']],
                          assertion_sha256={row['id']: assertion_digest(row)}, note=marker,
                          role='author', invocation_id='TEST-ONLY.private-author')
            row['review_ids'] = [review['id']]
            context['graph']['assertions'].append(row)
            context['graph']['reviews'].append(review)
        context['graph']['sources'][0]['private_draft_extension'] = marker
        context['graph']['private_queue'] = {'wording': marker}
        projection = citations.public_projection(context)
        self.assertEqual({row['id']: assertion_digest(row) for row in projection['graph']['assertions'] if row['status'] == 'approved'}, before)
        self.assertTrue(all(row['status'] in {'approved', 'historical'} for row in projection['graph']['assertions']))
        source = citations.source_context(context)
        self.assertEqual(source['graph'], projection['graph'])
        self.assertEqual(source['input_commitments']['graph_sha256'], citations.sha256(citations.json_bytes(context['graph'])))
        self.assertNotIn(marker, citations.json_bytes(source).decode())
        with tempfile.TemporaryDirectory() as temporary, patch.object(citations, 'verified_pdf', return_value=None):
            package = citations.freeze_publication_package(context, Path(temporary) / 'TEST-ONLY-private-draft', archive_compression='deflate')
            with zipfile.ZipFile(package / 'research-archive.zip') as zipped:
                for name in zipped.namelist():
                    self.assertNotIn(marker.encode(), zipped.read(name), name)
            for path in package.iterdir():
                self.assertNotIn(marker.encode(), path.read_bytes(), path.name)
            context['graph']['assertions'][-1]['value']['value'] += ' changed private input'
            with self.assertRaisesRegex(ValueError, 'source context'):
                citations.read_prepared_package(context, package)
            historical = published_context(context, package)
            with self.assertRaisesRegex(ValueError, 'source context'):
                citations.read_prepared_package(historical, package)


if __name__ == '__main__':
    unittest.main()
