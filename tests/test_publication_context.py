"""Versioned frozen scientific inputs and source-selected bundle contracts.

All generated packages, PDF bytes, receipts and remote state are TEST-ONLY.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import research_publish as publish
from research_pdf import prepare_report_pdf
from test_research_citations import context_fixture
from test_research_publish import FakeZenodo
from publication_fixtures import populate_owned_inputs


def prepare_fixture(directory, *, committed_path=False, publish_enabled=False):
    context = context_fixture()
    root = directory / 'source'
    context['root'] = str(root)
    if publish_enabled:
        context['policy']['mode'] = 'publish_enabled'
        context['gate'].update(ready=True, archival_ready=True, reasons=[])
    populate_owned_inputs(root)
    pdf = b'TEST-ONLY synthetic PDF byte fixture, never a research publication.'
    pdf_root = root / 'data/research'
    pdf_root.mkdir(parents=True, exist_ok=True)
    (pdf_root / 'report.pdf').write_bytes(pdf)
    (pdf_root / 'report-pdf.json').write_bytes(citations.json_bytes({
        'schema_version': 1, 'context_contract_version': citations.CONTEXT_CONTRACT_VERSION, 'sha256': citations.sha256(pdf),
        'context_sha256': citations.context_digest(context)}))
    target = root / 'data/research/releases/test.1/publication' if committed_path else directory / 'frozen'
    projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
    with patch.object(citations, 'public_projection', return_value=projection):
        citations.freeze_publication_package(context, target, archive_compression='deflate')
    return context, target


def legacy_fixture(context, package, version=1):
    """Recreate a previous envelope format in a TEST-ONLY package."""
    files = citations.read_prepared_package(context, package)
    files = {name: blob for name, blob in files.items() if name not in {'PREPARED.json', 'research-archive.zip', 'MANIFEST.json'}}
    if version == 2:
        files.pop('LOCATORS.md', None)
    files['source-context.json'] = citations.json_bytes(citations.source_context(context, version=version))
    manifest = {'schema_version': 1, 'release_id': context['report']['release_id'],
                'context_sha256': citations.context_digest(context, version=version),
                'files': {name: {'sha256': citations.sha256(blob), 'bytes': len(blob)} for name, blob in sorted(files.items())}}
    if version == 2:
        manifest['context_contract_version'] = version
    files['MANIFEST.json'] = citations.json_bytes(manifest)
    archive = citations.deterministic_zip(files)
    contract = {'schema_version': 1, 'release_id': manifest['release_id'], 'context_sha256': manifest['context_sha256'],
                'manifest_sha256': citations.sha256(files['MANIFEST.json']), 'archive_sha256': citations.sha256(archive),
                'archive_bytes': len(archive), 'pdf_sha256': citations.sha256(files['report.pdf']), 'pdf_bytes': len(files['report.pdf'])}
    if version == 2:
        contract['context_contract_version'] = version
    files.update({'research-archive.zip': archive, 'PREPARED.json': citations.json_bytes(contract)})
    for path in package.iterdir():
        if path.name not in files:
            path.unlink()
    for name, blob in files.items():
        (package / name).write_bytes(blob)
    return files


def write_registry(context, package):
    root = Path(context['root'])
    contract = json.loads((package / 'PREPARED.json').read_text())
    entry = {'release_id': context['report']['release_id'], 'path': package.relative_to(root).as_posix(),
             **{key: contract.get(key, 1) for key in ('context_contract_version', 'context_sha256', 'manifest_sha256', 'archive_sha256')}}
    path = root / citations.PREPARED_REGISTRY
    path.write_bytes(citations.json_bytes({'schema_version': 1, 'packages': [entry]}))
    return path, entry


class ContextContractTests(unittest.TestCase):
    def test_previous_v2_allowlist_is_not_retroactively_extended_with_locator_doc(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            legacy_fixture(context, package, version=2)
            frozen = citations.read_prepared_package(context, package)
            self.assertNotIn('LOCATORS.md', frozen)
            (Path(context['root']) / 'docs/research/locators.md').unlink()
            self.assertEqual(citations.read_prepared_package(context, package), frozen)
            self.assertEqual(json.loads(frozen['source-context.json'])['package_context']['context_contract_version'], 2)

    def test_v2_binds_every_archived_schema_reproducer_and_license_by_target_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            source = json.loads((package / 'source-context.json').read_text())
            contract = json.loads((package / 'PREPARED.json').read_text())
            self.assertEqual(contract['context_contract_version'], citations.CONTEXT_CONTRACT_VERSION)
            bindings = source['package_context']['reproduction_inputs']
            manifest = json.loads((package / 'MANIFEST.json').read_text())
            self.assertEqual(set(bindings), set(citations.REPRODUCTION_INPUTS))
            for name in bindings:
                self.assertEqual(bindings[name], manifest['files'][name])
                self.assertEqual(bindings[name]['sha256'], citations.sha256((package / name).read_bytes()))
            self.assertNotIn('scripts/reproduce_research_package.py', bindings)
            baseline = citations.context_digest(context)
            archive = (package / 'research-archive.zip').read_bytes()
            for name, relative in citations.REPRODUCTION_INPUTS.items():
                with self.subTest(name=name):
                    path = Path(context['root']) / relative
                    original = path.read_bytes()
                    path.write_bytes(original + b'\nTEST-ONLY changed owned scientific input\n')
                    self.assertNotEqual(citations.context_digest(context), baseline)
                    with self.assertRaisesRegex(ValueError, 'context'):
                        citations.read_prepared_package(context, package)
                    with self.assertRaisesRegex(ValueError, 'context'):
                        citations.freeze_publication_package(context, package)
                    path.write_bytes(original)
            self.assertEqual((package / 'research-archive.zip').read_bytes(), archive)
            citations.read_prepared_package(context, package)

    def test_missing_and_symlinked_owned_inputs_cannot_silently_reuse_v2_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            source = Path(context['root']) / 'schema/research-graph.schema.json'
            original = source.read_bytes()
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing'):
                citations.read_prepared_package(context, package)
            with self.assertRaisesRegex(ValueError, 'Missing'):
                citations.source_context(context)
            projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
            with patch.object(citations, 'public_projection', return_value=projection):
                with self.assertRaisesRegex(ValueError, 'Missing'):
                    citations.write_publication_assets(context, Path(temporary) / 'incomplete-write')
            source.symlink_to(package / 'research-graph.schema.json')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                citations.context_digest(context)
            source.unlink()
            source.write_bytes(original)

    def test_legacy_published_bundle_ignores_new_owned_inputs_and_reuses_old_pdf_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary), committed_path=True)
            files = legacy_fixture(context, package)
            write_registry(context, package)
            pdf_receipt = Path(context['root']) / 'data/research/report-pdf.json'
            old_receipt = citations.json_bytes({'schema_version': 1, 'sha256': citations.sha256(files['report.pdf']),
                                               'context_sha256': citations.context_digest(context, version=1)})
            pdf_receipt.write_bytes(old_receipt)
            (Path(context['root']) / 'schema/research-graph.schema.json').write_text('TEST-ONLY fixed newer schema')
            (Path(context['root']) / 'LICENSE-DATA.md').unlink()  # No retroactive v2 completeness requirement.
            context['gate']['ready'] = True
            context['report'].update(status='published', archive={'status': 'published', 'verified': True,
                'api_origin': 'https://zenodo.org', 'environment': 'production', 'record_id': 123,
                'doi': '10.5281/zenodo.123', 'concept_doi': '10.5281/zenodo.999',
                'record_url': 'https://zenodo.org/records/123', 'confirmed_on': '2026-11-09T00:00:00Z',
                'release_id': context['report']['release_id'], 'artifact_sha256': citations.sha256(files['research-archive.zip'])})
            context.update(citations.prepared_package_selection(context))
            self.assertEqual(context['prepared_package_expected']['context_contract_version'], 1)
            with patch.object(citations, 'write_projection', side_effect=AssertionError('No SQLite generation')), \
                    patch.object(citations, 'verified_pdf', side_effect=AssertionError('No PDF receipt rewrite')), \
                    patch.object(citations, 'deterministic_zip', side_effect=AssertionError('No ZIP generation')), \
                    patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
                citations.write_publication_assets(context, Path(temporary) / 'site')
            for name, blob in files.items():
                self.assertEqual((Path(temporary) / 'site/publication' / name).read_bytes(), blob)
            self.assertEqual(pdf_receipt.read_bytes(), old_receipt)

    def test_unknown_or_disagreeing_context_versions_fail_before_frozen_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            path = package / 'PREPARED.json'
            original = json.loads(path.read_text())
            for version in (citations.CONTEXT_CONTRACT_VERSION + 1, True, 2.0, '2'):
                path.write_bytes(citations.json_bytes({**original, 'context_contract_version': version}))
                with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'context contract version'):
                    citations.read_prepared_package(context, package)
            path.write_bytes(citations.json_bytes({**original, 'context_contract_version': 1}))
            with self.assertRaisesRegex(ValueError, 'context'):
                citations.read_prepared_package(context, package)

    def test_pdf_preparation_writes_v2_and_old_source_receipt_cannot_prepare_new_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            output = Path(context['root']) / 'data/research'
            with patch('research_pdf.render_report_pdf', return_value=b'TEST-ONLY rendered PDF bytes'):
                receipt = prepare_report_pdf(context, output)
            self.assertEqual(receipt['context_contract_version'], citations.CONTEXT_CONTRACT_VERSION)
            self.assertEqual(citations.verified_pdf(context), b'TEST-ONLY rendered PDF bytes')
            receipt.pop('context_contract_version')
            receipt['context_sha256'] = citations.context_digest(context, version=1)
            (output / 'report-pdf.json').write_bytes(citations.json_bytes(receipt))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                citations.verified_pdf(context)

    def test_legacy_release_lost_upload_and_publish_retry_keep_one_exact_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, publish_enabled=True)
            frozen = legacy_fixture(context, package)
            remote = FakeZenodo()
            gate = types.SimpleNamespace(publication_gate=lambda *args: context['gate'])
            journal = directory / 'TEST-ONLY-journal.json'
            with patch.dict(sys.modules, {'research_report': gate}):
                adapter = publish.Zenodo(publish.Release(context, package, journal), transport=remote)
                remote.lose = 'upload'
                with self.assertRaises(TimeoutError):
                    adapter.upload()
                adapter = publish.Zenodo(publish.Release(context, package, journal), transport=remote)
                adapter.upload()
                remote.lose = 'publish'
                with self.assertRaises(TimeoutError):
                    adapter.publish()
                adapter = publish.Zenodo(publish.Release(context, package, journal), transport=remote)
                adapter.publish()
            self.assertEqual(len(remote.deposits), 1)
            self.assertEqual(sum(path.endswith('/actions/publish') for _, path in remote.calls), 1)
            self.assertEqual((package / 'research-archive.zip').read_bytes(), frozen['research-archive.zip'])

    def test_reservation_journal_restart_preserves_legacy_and_v2_lost_create_markers(self):
        for version in (1, 2, citations.CONTEXT_CONTRACT_VERSION):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                context, package = prepare_fixture(directory, publish_enabled=True)
                journal = directory / 'TEST-ONLY-reservation.json'
                if version < citations.CONTEXT_CONTRACT_VERSION:
                    digest = citations.sha256(citations.json_bytes(citations.source_context(context, reservation=False, version=version)))
                    old = publish.Journal(journal, context['report']['release_id'], context_sha256=digest)
                    if version != 1:
                        old.state['context_contract_version'] = version
                    old.save('TEST-ONLY legacy reservation journal fixture')
                gate = types.SimpleNamespace(publication_gate=lambda *args: context['gate'])
                remote = FakeZenodo()
                with patch.dict(sys.modules, {'research_report': gate}):
                    plan = publish.PublicationPlan(context, journal)
                    remote.lose = 'create'
                    with self.assertRaises(TimeoutError):
                        publish.Zenodo(plan, transport=remote).draft()
                    restarted = publish.PublicationPlan(context, journal)
                    publish.Zenodo(restarted, transport=remote).draft()
                self.assertEqual(restarted.context_contract_version, version)
                self.assertEqual(restarted.marker, plan.marker)
                self.assertEqual(len(remote.deposits), 1)


class PreparedRegistryTests(unittest.TestCase):
    def test_optional_registry_selects_only_completed_matching_release_without_a_hash_cycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary), committed_path=True)
            self.assertEqual(citations.prepared_package_selection(context), {})
            baseline = citations.context_digest(context)
            registry, entry = write_registry(context, package)
            overlay = citations.prepared_package_selection(context)
            self.assertEqual(Path(overlay['prepared_package']), package)
            self.assertEqual(citations.context_digest({**context, **overlay}), baseline)
            source = citations.json_bytes(citations.source_context({**context, **overlay})).decode()
            for value in ('prepared_package', 'prepared_package_expected', str(Path(context['root'])), str(registry)):
                self.assertNotIn(value, source)
            with patch.object(citations, 'write_projection', side_effect=AssertionError('No SQLite generation')), \
                    patch.object(citations, 'verified_pdf', side_effect=AssertionError('No PDF preparation')), \
                    patch.object(citations, 'deterministic_zip', side_effect=AssertionError('No ZIP generation')), \
                    patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
                citations.write_publication_assets({**context, **overlay}, Path(temporary) / 'site')
            for key in ('context_sha256', 'manifest_sha256', 'archive_sha256'):
                changed = copy.deepcopy(entry)
                changed[key] = '0' * 64
                registry.write_bytes(citations.json_bytes({'schema_version': 1, 'packages': [changed]}))
                with self.subTest(hash=key), self.assertRaisesRegex(ValueError, 'registry bindings'):
                    citations.prepared_package_selection(context)

    def test_registry_refuses_traversal_absolute_unrelated_paths_and_private_extensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary), committed_path=True)
            registry, entry = write_registry(context, package)
            for path in ('../publication', str(package), 'data/research/report.pdf',
                         'data/research/releases/test.1/../publication', 'data/research/releases/other/publication',
                         'data/research/releases/test.1//publication'):
                bad = {**entry, 'path': path}
                registry.write_bytes(citations.json_bytes({'schema_version': 1, 'packages': [bad]}))
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'path'):
                    citations.prepared_package_selection(context)
            registry.write_bytes(citations.json_bytes({'schema_version': 1, 'packages': [{**entry, 'contact_email': 'TEST-ONLY private metadata'}]}))
            with self.assertRaisesRegex(ValueError, 'registry entry'):
                citations.prepared_package_selection(context)
            registry.write_text('{"schema_version":1,"schema_version":1,"packages":[]}')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                citations.prepared_package_selection(context)

    def test_registry_symlinked_components_and_selected_missing_bundle_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, committed_path=True)
            registry, entry = write_registry(context, package)
            parent = package.parent
            outside = directory / 'moved-TEST-ONLY-edition'
            parent.rename(outside)
            parent.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                citations.prepared_package_selection(context)
            parent.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing'):
                citations.prepared_package_selection(context)
            outside.rename(parent)
            content = registry.read_bytes()
            registry.unlink()
            alias = directory / 'registry-TEST-ONLY.json'
            alias.write_bytes(content)
            registry.symlink_to(alias)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                citations.prepared_package_selection(context)

    def test_explicit_freeze_can_create_new_target_despite_existing_build_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            context, package = prepare_fixture(directory, committed_path=True)
            write_registry(context, package)
            selected = {**context, **citations.prepared_package_selection(context)}
            target = directory / 'new-explicit-freeze'
            projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
            with patch.object(citations, 'public_projection', return_value=projection):
                citations.freeze_publication_package(selected, target, archive_compression='deflate')
            self.assertTrue((target / 'PREPARED.json').is_file())
            citations.read_prepared_package(context, target)
            self.assertEqual(citations.context_digest(selected), citations.context_digest(context))


if __name__ == '__main__':
    unittest.main()
