"""Public correction provenance, offline targets and private proposal isolation."""
import copy
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
from research_corrections import correction_records, public_corrections
from research_offline import offline_appendix, evidence_href
import research_pages as pages
from research_report import build_context


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

    def test_actual_26_records_preserve_ids_dates_and_real_review_relationships(self):
        rows = public_corrections(self.context)
        self.assertEqual(len(rows), 26)
        assertions = {row['id']: row for row in self.context['graph']['assertions']}
        reviews = {row['id']: row for row in self.context['graph']['reviews']}
        for row in rows:
            old, new = assertions[row['claim_id']], assertions[row['replacement_claim_id']]
            self.assertEqual((old['status'], new['status']), ('candidate', 'approved'))
            self.assertEqual(row['status'], 'accepted')
            self.assertEqual(old['value'], new['value'])
            receipts = [reviews[rid] for rid in new['review_ids']]
            self.assertEqual({r['verdict'] for r in receipts}, {'pass'})
            self.assertEqual(len({r['invocation_id'] for r in receipts}), 3)
            self.assertEqual(row['corrected_on'], max(r['reviewed_on'] for r in receipts))
            for receipt in receipts:
                self.assertIn(receipt['id'], row['summary'])

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
        context = copy.deepcopy(self.context)
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
        context = copy.deepcopy(self.context)
        for status in ('pending', 'rejected'):
            row = {**context['corrections'][0], 'id': 'fixture.' + status, 'status': status,
                   'summary': 'PRIVATE-' + status.upper() + '-SENTINEL private@example.org'}
            context['corrections'].append(row)
        context['corrections'][0]['summary'] += ' Contact private@example.org.'
        affected = next(a for a in context['graph']['assertions'] if a['id'] == context['corrections'][0]['claim_id'])
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
            self.assertEqual(len(exported), 26)
            self.assertTrue(all(row['status'] == 'accepted' for row in exported))
            source = json.loads((output / 'publication/source-context.json').read_text())
            self.assertEqual(source['corrections'], exported)
            for row in exported:
                article = pages._assertion(context, next(a for a in context['graph']['assertions'] if a['id'] == row['claim_id']))
                self.assertIn(pages._correction_url(row), article)
                self.assertIn(pages._evidence_url('assertion', row['replacement_claim_id']), article)

    def test_only_v3_binds_correction_input_and_invalidates_unpublished_context(self):
        context = copy.deepcopy(self.context)
        before = {v: citations.json_bytes(citations.source_context(context, version=v)) for v in (1, 2, 3)}
        context['corrections'].append({**context['corrections'][0], 'id': 'fixture.private-pending', 'status': 'pending', 'summary': 'PRIVATE-CHANGED'})
        after = {v: citations.json_bytes(citations.source_context(context, version=v)) for v in (1, 2, 3)}
        self.assertEqual(before[1], after[1])
        self.assertEqual(before[2], after[2])
        self.assertNotEqual(before[3], after[3])
        self.assertNotIn(b'PRIVATE-CHANGED', after[3])
        self.assertNotIn('corrections.json', citations.REPRODUCTION_INPUTS)


if __name__ == '__main__':
    unittest.main()
