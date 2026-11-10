"""Frozen compression, offline evidence and TEST-ONLY weekly-scale storage."""
import copy
import io
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
from research_offline import offline_appendix, evidence_href
from test_research_citations import context_fixture
from test_research_report import approved_graph
from publication_scale_fixture import COUNTS, scale_context, scale_pdf_allowance
from publication_fixtures import populate_owned_inputs


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))


class FrozenCompressionTests(unittest.TestCase):
    def prepare(self, root, *, compression='deflate'):
        context = context_fixture()
        context['root'] = str(root / 'source')
        populate_owned_inputs(context['root'])
        projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
        with patch.object(citations, 'public_projection', return_value=projection), patch.object(citations, 'verified_pdf', return_value=b'TEST-ONLY PDF fixture'):
            target = citations.freeze_publication_package(context, root / 'frozen', archive_compression=compression)
        return context, target

    def test_stored_and_deflate_round_trip_sorted_fixed_metadata_and_manifest(self):
        files = {'z.txt': b'scoped evidence\n' * 1000, 'a.txt': b'owned text'}
        for method, code in citations.ARCHIVE_COMPRESSION.items():
            archive = citations.deterministic_zip(files, compression=method)
            self.assertEqual(archive, citations.deterministic_zip(dict(reversed(list(files.items()))), compression=method))
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                self.assertEqual(zipped.namelist(), sorted(files))
                for name, blob in files.items():
                    info = zipped.getinfo(name)
                    self.assertEqual(zipped.read(name), blob)
                    self.assertEqual(info.compress_type, code)
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(info.external_attr >> 16, 0o100644)
        self.assertLess(len(citations.deterministic_zip(files, compression='deflate')), len(citations.deterministic_zip(files)))
        with self.assertRaisesRegex(ValueError, 'stored or deflate'):
            citations.deterministic_zip(files, compression='zstd')

    def test_frozen_reuse_never_calls_sqlite_pdf_zip_or_network_and_accepts_legacy_stored(self):
        for compression in ('stored', 'deflate'):
            with self.subTest(compression=compression), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                context, package = self.prepare(root, compression=compression)
                frozen = citations.read_prepared_package(context, package)
                context['prepared_package'] = str(package)
                with patch.object(citations, 'write_projection', side_effect=AssertionError('No SQLite writer in frozen reuse')), \
                        patch.object(citations, 'verified_pdf', side_effect=AssertionError('No PDF preparation in frozen reuse')), \
                        patch.object(citations, 'deterministic_zip', side_effect=AssertionError('No zlib generation in frozen reuse')), \
                        patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
                    citations.write_publication_assets(context, root / 'website')
                    citations.freeze_publication_package(context, package, archive_compression='deflate')
                for name, blob in frozen.items():
                    self.assertEqual((root / 'website/publication' / name).read_bytes(), blob)

    def test_interrupted_freeze_is_not_overwritten_and_stale_context_or_inventory_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, package = self.prepare(root)
            before = (package / 'research-archive.zip').read_bytes()
            changed = copy.deepcopy(context)
            changed['report']['title'] += ' changed'
            with self.assertRaisesRegex(ValueError, 'context'):
                citations.freeze_publication_package(changed, package)
            (package / 'unlisted-contact-cache.txt').write_text('TEST-ONLY unlisted file')
            with self.assertRaisesRegex(ValueError, 'inventory'):
                citations.read_prepared_package(context, package)
            (package / 'unlisted-contact-cache.txt').unlink()
            interrupted = root / 'interrupted'
            interrupted.mkdir()
            (interrupted / 'report.pdf').write_bytes(b'TEST-ONLY partial copy')
            with patch.object(citations, 'write_publication_assets', side_effect=AssertionError('Never regenerate incomplete prior freeze')):
                with self.assertRaisesRegex(ValueError, 'Missing'):
                    citations.freeze_publication_package(context, interrupted)
            self.assertEqual((interrupted / 'report.pdf').read_bytes(), b'TEST-ONLY partial copy')
            self.assertEqual((package / 'research-archive.zip').read_bytes(), before)

    def test_changed_frozen_member_and_archive_envelope_are_detected(self):
        for name in ('report.html', 'research-archive.zip'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                context, package = self.prepare(Path(temporary))
                target = package / name
                target.write_bytes(target.read_bytes() + b'TEST-ONLY corruption')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    citations.read_prepared_package(context, package)

    def test_unsupported_zip_method_is_rejected_even_with_matching_byte_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = self.prepare(Path(temporary))
            files = citations.read_prepared_package(context, package)
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_BZIP2) as zipped:
                for name in sorted(set(files) - {'PREPARED.json', 'research-archive.zip'}):
                    zipped.writestr(name, files[name])
            archive = stream.getvalue()
            (package / 'research-archive.zip').write_bytes(archive)
            contract = json.loads((package / 'PREPARED.json').read_text())
            contract.update(archive_sha256=citations.sha256(archive), archive_bytes=len(archive))
            (package / 'PREPARED.json').write_bytes(citations.json_bytes(contract))
            with self.assertRaisesRegex(ValueError, 'Unsupported frozen archive compression'):
                citations.read_prepared_package(context, package)


class OfflineEvidenceTests(unittest.TestCase):
    def test_native_links_resolve_and_only_reviewed_wording_is_readable(self):
        context = context_fixture()
        context['graph'] = approved_graph()
        context['graph']['entities'][0]['id'] = 'fixture/entity:scope'
        context['graph']['assertions'][0]['subject_id'] = 'fixture/entity:scope'
        claim = context['graph']['assertions'][0]
        claim['value']['value'] = json.dumps({'statement': 'TEST-ONLY scoped <claim>.',
            'scope': {'product': '<img src=x onerror=alert(1)>'}, 'reported_value_and_basis': {'currency': None, 'annualized': False}})
        candidate = {**copy.deepcopy(claim), 'id': 'TEST-ONLY.candidate', 'status': 'candidate',
                     'value': {'type': 'text', 'value': 'FORBIDDEN-CANDIDATE-WORDING'}}
        # The renderer defensively withholds unapproved wording even if a caller
        # supplies it; the production projection excludes candidates entirely.
        context['graph']['assertions'].append(candidate)
        context['graph']['sources'][0]['excerpt'] = 'FORBIDDEN-THIRD-PARTY-EXCERPT'
        projection = citations.privacy_filter({'graph': context['graph'], 'release_id': 'TEST-ONLY', 'as_of': context['graph']['as_of']})
        text = offline_appendix(projection).decode()
        facts = Links(text)
        self.assertEqual(len(facts.ids), len(set(facts.ids)))
        for link in facts.links:
            parsed = urlsplit(link)
            if parsed.path in ('', 'evidence.html') and parsed.fragment:
                self.assertIn(unquote(parsed.fragment), facts.ids, link)
        self.assertIn('TEST-ONLY scoped &lt;claim&gt;.', text)
        self.assertIn('Not stated in the source', text)
        self.assertIn('Annualized', text)
        self.assertNotIn('<img', text)
        self.assertNotIn('FORBIDDEN-CANDIDATE-WORDING', text)
        self.assertNotIn('FORBIDDEN-THIRD-PARTY-EXCERPT', text)
        self.assertNotIn('<script', text)
        self.assertIn(evidence_href('entity', 'fixture/entity:scope'), facts.links)

    def test_report_paragraph_evidence_resolves_in_local_appendix(self):
        context = context_fixture()
        context['graph'] = approved_graph()
        context['report']['sections'][0]['paragraphs'][0]['claim_ids'] = ['fixture-claim']
        text = citations.offline_html(context).decode()
        self.assertIn(evidence_href('assertion', 'fixture-claim'), Links(text).links)
        self.assertNotIn('https://sciencetostartup.com/research/data/', text)

    def test_methods_contact_details_are_removed_from_all_packaged_text(self):
        context = context_fixture()
        context['report']['sections'][0]['id'] = 'methods-and-appendices'
        context['report']['sections'][0]['paragraphs'][0]['text'] = 'TEST-ONLY contact private-fixture@example.org.'
        projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
        with tempfile.TemporaryDirectory() as temporary, patch.object(citations, 'public_projection', return_value=projection), patch.object(citations, 'verified_pdf', return_value=None):
            citations.write_publication_assets(context, temporary, archive_compression='deflate')
            with zipfile.ZipFile(Path(temporary) / 'publication/research-archive.zip') as zipped:
                for name in zipped.namelist():
                    self.assertNotIn(b'private-fixture@example.org', zipped.read(name), name)


class WeeklyScaleTests(unittest.TestCase):
    def test_target_scope_fixture_fits_every_asset_and_reproduces_all_exports(self):
        """TEST ONLY: these counts and synthetic receipts are never launch evidence."""
        context = scale_context(ROOT)
        self.assertEqual(len(context['graph']['entities']), sum(COUNTS.values()))
        self.assertEqual(len(context['graph']['assertions']), 2900)
        self.assertEqual(len(context['graph']['reviews']), 8700)
        self.assertFalse(context['gate']['ready'])
        with tempfile.TemporaryDirectory() as temporary, patch.object(citations, 'verified_pdf', return_value=scale_pdf_allowance()), patch('urllib.request.urlopen', side_effect=AssertionError('No network in fixture build')):
            citations.write_publication_assets(context, temporary, archive_compression='deflate')
            package = Path(temporary) / 'publication'
            inventory = citations.publication_asset_inventory(package)
            self.assertEqual(inventory['oversized'], {})
            files = citations.read_prepared_package(context, package)
            manifest = json.loads(files['MANIFEST.json'])
            with zipfile.ZipFile(package / 'research-archive.zip') as zipped:
                self.assertEqual(set(zipped.namelist()), set(manifest['files']) | {'MANIFEST.json'})
                self.assertTrue(all(info.compress_type == zipfile.ZIP_DEFLATED for info in zipped.infolist()))
                uncompressed_bytes = sum(info.file_size for info in zipped.infolist())
                self.assertGreater(uncompressed_bytes, citations.STATIC_ASSET_LIMIT_BYTES)
                self.assertLess(inventory['files']['research-archive.zip'], uncompressed_bytes // 2)
            result = subprocess.run([sys.executable, str(package / 'reproduce.py'), '--directory', str(package)], check=True, capture_output=True, text=True)
            self.assertTrue(json.loads(result.stdout)['exports_equivalent'])
            self.assertNotIn('private-fixture@example.org', files['evidence.html'].decode())


if __name__ == '__main__':
    unittest.main()
