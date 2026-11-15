"""Public correction provenance, offline targets and private proposal isolation."""
import copy
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import research_graph as graph
from research_corrections import correction_records, public_corrections
from research_offline import offline_appendix, evidence_href
import research_pages as pages
from research_report import build_context
from research_lifecycle_fixtures import isolated_render_context, isolated_render_preparation


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.hrefs = [], []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.hrefs.append(unquote(attrs['href']))


class PublicCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_context(ROOT, select_prepared=False)

    def test_actual_corrections_preserve_history_and_real_review_relationships(self):
        rows = public_corrections(self.context)
        self.assertGreaterEqual(len(rows), 151)
        self.assertEqual(len(rows), 170)
        # Preserve the complete original history, including wording and dates.
        original = sorted((row for row in self.context['corrections']
                           if row['id'].startswith('correction.binding.')), key=lambda row: row['id'])
        self.assertEqual(len(original), 26)
        self.assertEqual(hashlib.sha256(json.dumps(original, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False).encode()).hexdigest(),
            '29d0b1d76e75afbdc4b93737050e034140faaefa84d66dcbaf5e01da7f5ff613')
        previous = sorted((row for row in self.context['corrections']
                           if row['id'].startswith(('correction.binding.',
                                                    'correction.complete-binding.20261111.'))),
                          key=lambda row: row['id'])
        self.assertEqual(len(previous), 65)
        self.assertEqual(hashlib.sha256(json.dumps(previous, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False).encode()).hexdigest(),
            'd6492cd8eb09a707401bb073bac64a7e9f8e5111e78a6d81219880b801b3d6aa')
        prior_151 = sorted((row for row in self.context['corrections']
                            if row['id'].startswith(('correction.binding.',
                                'correction.complete-binding.20261111.',
                                'correction.qualbinding.20261111.'))), key=lambda row: row['id'])
        self.assertEqual(len(prior_151), 151)
        self.assertEqual(hashlib.sha256(json.dumps(prior_151, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
            'd378a7538fa89cb90abce783a5b5fd0ceb61151ad57f90986d281633fc776e19')
        self.assert_correction_review_relationships(self.context, rows,
            public_replay=self.context.get('published_edition_replay') is not None)

    def assert_correction_review_relationships(self, context, rows, *, public_replay):
        assertions = {row['id']: row for row in context['graph']['assertions']}
        reviews = {row['id']: row for row in context['graph']['reviews']}
        if public_replay:
            self.assertTrue(all(row['status'] in {'approved', 'historical'}
                                for row in assertions.values()))
        for row in rows:
            new = assertions[row['replacement_claim_id']]
            if public_replay:
                # The frozen public projection retains correction metadata,
                # never the private original hypothesis or its exclusive reviews.
                self.assertNotIn(row['claim_id'], assertions)
                self.assertTrue(all(row['claim_id'] not in review['assertion_ids']
                                    for review in reviews.values()))
                self.assertEqual(new['status'], 'approved')
            else:
                old = assertions[row['claim_id']]
                self.assertEqual((old['status'], new['status']), ('candidate', 'approved'))
                if row['id'].startswith(('correction.binding.', 'correction.complete-binding.20261111.')):
                    self.assertEqual(old['value'], new['value'])
                if row['id'].startswith('correction.normal12.'):
                    self.assertTrue(any(reviews[rid]['verdict'] == 'revise'
                                        for rid in old['review_ids']))
            self.assertEqual(row['status'], 'accepted')
            receipts = [reviews[rid] for rid in new['review_ids']]
            self.assertEqual({r['verdict'] for r in receipts}, {'pass'})
            self.assertEqual({r['role'] for r in receipts}, {'author', 'source_verifier', 'adversarial'})
            self.assertEqual(len({r['invocation_id'] for r in receipts}), 3)
            latest_review = max(datetime.fromisoformat(r['reviewed_on'].replace('Z', '+00:00')) for r in receipts)
            self.assertGreaterEqual(datetime.fromisoformat(row['corrected_on'].replace('Z', '+00:00')), latest_review)
            for receipt in receipts:
                self.assertEqual(receipt['assertion_sha256'][new['id']], graph.assertion_digest(new))
                if row['id'].startswith('correction.binding.'):
                    self.assertIn(receipt['id'], row['summary'])

    def test_synthetic_public_projection_keeps_correction_bindings_without_private_hypothesis(self):
        from test_research_graph import fixture
        private = fixture()
        original = copy.deepcopy(private['assertions'][0])
        sentinel = 'TEST-ONLY-PRIVATE-ORIGINAL-HYPOTHESIS'
        original.update(id='TEST-ONLY.original', status='candidate', review_ids=[],
                        value={'type': 'text', 'value': sentinel})
        private['assertions'].append(original)
        correction = {'id': 'TEST-ONLY.correction', 'edition_id': 'test-only',
                      'claim_id': original['id'], 'replacement_claim_id': 'claim',
                      'status': 'accepted', 'summary': 'TEST-ONLY correction metadata.',
                      'corrected_on': '2026-11-08T14:00:00Z',
                      'evidence_urls': ['https://example.org/paper/v1']}
        # This tests the public projection contract, not a publication receipt.
        # The fixture's original synthetic approved reviews are unchanged.
        public = {'graph': graph.public_graph(private), 'corrections': [correction]}
        rows = public_corrections(public)
        self.assertEqual(rows, [correction])
        self.assertNotIn(sentinel.encode(), citations.json_bytes(public))
        self.assertIn(sentinel.encode(), citations.json_bytes(private))
        self.assert_correction_review_relationships(public, rows, public_replay=True)

    def test_legacy_record_and_invalid_replacements_fail_closed(self):
        row = copy.deepcopy(self.context['corrections'][0])
        row.pop('replacement_claim_id')
        row['claim_id'] = 'historical.no-longer-present'
        self.assertEqual(len(public_corrections({'corrections': [row]})), 1)
        for replacement in ('missing.assertion', self.context['corrections'][0]['claim_id'], '', None):
            broken = {**self.context['corrections'][0], 'replacement_claim_id': replacement}
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                public_corrections({**self.context, 'corrections': [broken]})

    def test_all_old_and_new_offline_targets_are_unique_and_heading_independent(self):
        projection = citations.public_projection(self.context)
        rows = public_corrections(self.context)
        text = offline_appendix(projection, corrections=rows).decode()
        parsed = Links(text)
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        for row in rows:
            for aid in (row['claim_id'], row['replacement_claim_id']):
                self.assertEqual(parsed.ids.count('assertion-' + aid), 1)
                self.assertIn(evidence_href('assertion', aid), parsed.hrefs)
            self.assertIn(row['corrected_on'], text)
        renamed = copy.deepcopy(projection)
        for entity in renamed['graph']['entities']:
            entity['name'] = 'Renamed heading'
        self.assertEqual(set(parsed.ids), set(Links(offline_appendix(renamed, corrections=rows).decode()).ids))
        # A projection containing an affected ID never gets a duplicate placeholder.
        synthetic = copy.deepcopy(projection)
        old = copy.deepcopy(synthetic['graph']['assertions'][0])
        old['id'] = rows[0]['claim_id']
        synthetic['graph']['assertions'].append(old)
        ids = Links(offline_appendix(synthetic, corrections=rows).decode()).ids
        self.assertEqual(ids.count('assertion-' + old['id']), 1)

    def test_legacy_live_claim_links_have_one_metadata_target_without_old_wording(self):
        context = isolated_render_context(self.context)
        row = copy.deepcopy(context['corrections'][0])
        row.pop('replacement_claim_id')
        row['claim_id'] = 'historical.no-longer-present'
        context['corrections'] = [row]
        text = pages._data(context)
        parsed = Links(text)
        self.assertEqual(parsed.ids.count('assertion-' + row['claim_id']), 1)
        destination = pages._evidence_url('assertion', row['claim_id'])
        self.assertIn(destination, parsed.hrefs)
        ledger = next(body for path, _, _, body, _, _ in pages._ledger_pages(context)
                      if path == destination.split('#')[0])
        record = Links(ledger)
        self.assertEqual(record.ids.count('assertion-' + row['claim_id']), 1)
        self.assertIn(pages._correction_url(row), record.hrefs)
        self.assertIn('historical identifier is retained as correction metadata', ledger)

    def test_replacement_correction_cannot_predate_passing_approval(self):
        row = {**self.context['corrections'][0], 'corrected_on': '2000-01-01T00:00:00Z'}
        with self.assertRaisesRegex(ValueError, 'predate'):
            public_corrections({**self.context, 'corrections': [row]})
        # Legacy representations normalize to interoperable RFC3339 output
        # without changing the historical instant or the private input bytes.
        original = copy.deepcopy(self.context['corrections'][0])
        original['corrected_on'] = original['corrected_on'].replace('T', ' ')
        exported = public_corrections({**self.context, 'corrections': [original]})[0]
        self.assertIn('T', exported['corrected_on'])
        self.assertIn(' ', original['corrected_on'])

    def test_contact_or_credential_evidence_urls_are_rejected_without_url_redaction(self):
        for url in ('https://example.org/person@example.org', 'https://example.org/person%40example.org',
                    'https://example.org:invalid/', 'https://example.org/?token=private',
                    'https://example.org/sk-proj-ABCDEFGHIJKLMNOPQRSTUV'):
            row = {**self.context['corrections'][0], 'evidence_urls': [url]}
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'safe HTTPS'):
                public_corrections({**self.context, 'corrections': [row]})

    def test_proposals_and_contacts_never_enter_live_or_archive_representations(self):
        with isolated_render_preparation(self.context, canonical_bytes=(ROOT / 'data/canonical.json').read_bytes()) as context:
            self.assert_proposals_and_contacts_are_private(context)

    def assert_proposals_and_contacts_are_private(self, context):
        for status in ('pending', 'rejected'):
            row = {**context['corrections'][0], 'id': 'fixture.' + status, 'status': status,
                   'summary': 'PRIVATE-' + status.upper() + '-SENTINEL private@example.org'}
            context['corrections'].append(row)
        context['corrections'][0]['summary'] += ' Contact private@example.org.'
        affected = next((a for a in context['graph']['assertions']
                         if a['id'] == context['corrections'][0]['claim_id']), None)
        if affected is None:
            # Public replay has no original hypothesis to mutate. Add an
            # unrelated, explicitly synthetic draft rather than reconstruct it.
            affected = copy.deepcopy(next(a for a in context['graph']['assertions']
                                          if a['status'] == 'approved'))
            affected.update(id='TEST-ONLY.private-candidate', status='candidate', review_ids=[])
            context['graph']['assertions'].append(affected)
        affected['value'] = {'type': 'text', 'value': 'PRIVATE-CANDIDATE-WORDING'}
        source = copy.deepcopy(next(s for s in context['graph']['sources'] if s['id'] == affected['evidence'][0]['source_id']))
        source.update(id='fixture.private-old-source', excerpt='PRIVATE-BAD-EXCERPT', cache_path='PRIVATE-INPUT-PATH')
        source['excerpt_sha256'] = hashlib.sha256(source['excerpt'].encode()).hexdigest()
        context['graph']['sources'].append(source)
        affected['evidence'][0]['source_id'] = source['id']
        affected['evidence'][0]['excerpt_sha256'] = source['excerpt_sha256']
        forbidden_values = (b'PRIVATE-PENDING-SENTINEL', b'PRIVATE-REJECTED-SENTINEL', b'private@example.org',
                            b'PRIVATE-CANDIDATE-WORDING', b'PRIVATE-INPUT-PATH')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            pages.write_research_pages(output, context)
            with patch.object(citations, 'verified_pdf', return_value=None):
                citations.write_publication_assets(context, output)
            for path in output.rglob('*'):
                if path.is_file() and path.suffix != '.zip':
                    blob = path.read_bytes()
                    for forbidden in forbidden_values:
                        self.assertNotIn(forbidden, blob, str(path))
                    if path.suffix == '.html':
                        self.assertNotIn(b'PRIVATE-BAD-EXCERPT', blob, str(path))
            with zipfile.ZipFile(output / 'publication/research-archive.zip') as archive:
                for member in archive.namelist():
                    for forbidden in forbidden_values:
                        self.assertNotIn(forbidden, archive.read(member), member)
                    if member.endswith('.html'):
                        self.assertNotIn(b'PRIVATE-BAD-EXCERPT', archive.read(member), member)
            exported = json.loads((output / 'publication/corrections.json').read_text())['corrections']
            self.assertEqual(len(exported), len(public_corrections(self.context)))
            self.assertTrue(all(row['status'] == 'accepted' for row in exported))
            source = json.loads((output / 'publication/source-context.json').read_text())
            self.assertEqual(source['corrections'], exported)
            ledger_by_path = None
            for row in exported:
                old = next((a for a in context['graph']['assertions'] if a['id'] == row['claim_id']), None)
                if old is not None:
                    article = pages._assertion(context, old)
                else:
                    destination = pages._evidence_url('assertion', row['claim_id'])
                    if ledger_by_path is None:
                        ledger_by_path = {path: body for path, _, _, body, _, _ in pages._ledger_pages(context)}
                    article = ledger_by_path[destination.split('#')[0]]
                self.assertIn(pages._correction_url(row), article)
                self.assertIn(pages._evidence_url('assertion', row['replacement_claim_id']), article)

    def test_corrections_bind_current_and_historical_v3_plus_comparison_inputs(self):
        from test_research_citations import context_fixture
        with isolated_render_preparation(self.context, canonical_bytes=(ROOT / 'data/canonical.json').read_bytes()) as owner:
            context = context_fixture()
            context['root'] = owner['root']
            self.assert_correction_comparison_inputs(context)

    def assert_correction_comparison_inputs(self, context):
        # Historical recipes must use inputs compatible with their own grammar,
        # rather than retrofitting later task identifiers into an old redactor.
        legacy_correction = {**self.context['corrections'][0],
                             'id': 'fixture.legacy-correction',
                             'claim_id': 'fixture.historical-claim'}
        legacy_correction.pop('replacement_claim_id', None)
        context['corrections'] = [legacy_correction]

        def comparison_inputs(value):
            # Historical normalization is replay-only. Full owned-recipe
            # verification is exercised by the frozen-context regression tests;
            # this test isolates when correction commitments were introduced.
            historical = {v: citations.json_bytes(citations._research_source_context(
                value, version=v, frozen_graph_version='1.0.0' if v >= 2 else None))
                for v in (1, 2, 3, 4)}
            return {**historical, citations.CONTEXT_CONTRACT_VERSION:
                    citations.json_bytes(citations.source_context(value))}

        before = comparison_inputs(context)
        context['corrections'].append({**context['corrections'][0], 'id': 'fixture.private-pending', 'status': 'pending', 'summary': 'PRIVATE-CHANGED'})
        after = comparison_inputs(context)
        self.assertEqual(before[1], after[1])
        self.assertEqual(before[2], after[2])
        for version in (3, 4, citations.CONTEXT_CONTRACT_VERSION):
            self.assertNotEqual(before[version], after[version])
            self.assertNotIn(b'PRIVATE-CHANGED', after[version])
        for version in (1, 2, 3, 4):
            with self.assertRaisesRegex(ValueError, 'replay-only'):
                citations.source_context(context, version=version)
        self.assertNotIn('corrections.json', citations.REPRODUCTION_INPUTS)


if __name__ == '__main__':
    unittest.main()
