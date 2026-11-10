"""Public rendering invariants; synthetic approval receipts stay inside tests."""
import copy
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_graph as rg
import research_pages as rp
from research_report import build_context


class Facts(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links, self.canonicals, self.scripts = [], [], [], []
        self.headings = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'h1':
            self.headings += 1
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'script':
            self.scripts.append(attrs)


def approved_new_org(context):
    """Promote one test-only source-bound assertion with honest fixture receipts."""
    original = next(a for a in context['graph']['assertions'] if a['subject_id'] == 'org.translated')
    assertion = copy.deepcopy(original)
    assertion.update(id='fixture.claim.new-org', subject_id='org.fixture_translated', status='approved',
                     review_ids=[], qualifications=['Synthetic approval fixture only.'])
    entity = copy.deepcopy(next(e for e in context['graph']['entities'] if e['id'] == 'org.translated'))
    entity.update(id='org.fixture_translated', status='approved', disposition='included',
                  review_depth='full_source', identifiers={}, assertion_ids=[assertion['id']])
    context['graph']['entities'].append(entity)
    context['graph']['assertions'].append(assertion)
    for role in ('author', 'source_verifier', 'adversarial'):
        review_id = 'fixture.review.' + role
        assertion['review_ids'].append(review_id)
        context['graph']['reviews'].append({
            'id': review_id, 'assertion_ids': [assertion['id']], 'role': role,
            'reviewer': 'Synthetic test-only reviewer', 'reviewer_type': 'ai',
            'invocation_id': 'test-only-distinct-' + role, 'reviewed_on': context['graph']['as_of'],
            'verdict': 'pass', 'method': 'source_content_review',
            'source_ids': [e['source_id'] for e in assertion['evidence']], 'note': 'Test fixture only.',
            'assertion_sha256': {assertion['id']: rg.assertion_digest(assertion)}})
    rg.validate_graph(context['graph'])
    return assertion


class ResearchPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = build_context(ROOT)

    def setUp(self):
        self.context = copy.deepcopy(self.baseline)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.output = Path(self.scratch.name)

    def build(self):
        return rp.write_research_pages(self.output, self.context)

    def page(self, path):
        return (self.output / path.strip('/') / 'index.html').read_text()

    def test_actual_baseline_is_prelaunch_without_fabricated_editions(self):
        records = self.build()
        paths = [r['path'] for r in records]
        self.assertFalse(self.context['gate']['ready'])
        for path in ('/research/', rp.REPORT_PATH, '/research/data/', '/review/',
                     '/research/papers/', '/research/datasets/', '/research/benchmarks/', '/research/workflows/'):
            self.assertIn(path, paths)
        self.assertFalse(any('/editions/' in path for path in paths))
        expected_companies = {rp.entity_url(entity, self.context) for entity in self.context['graph']['entities'] if rp._new_company(self.context, entity)}
        self.assertEqual({path for path in paths if path.startswith('/company/')}, expected_companies)
        self.assertIn('Prelaunch', self.page('/research/'))
        approved = sum(a['status'] == 'approved' for a in self.context['graph']['assertions'])
        self.assertIn(f'{approved} approved assertions', self.page('/research/data/'))
        if not approved:
            self.assertIn('No new assertions have completed', self.page('/research/data/'))
        self.assertEqual(ET.parse(self.output / 'research/feed.xml').findall('./channel/item'), [])
        self.assertEqual(ET.parse(self.output / 'research/atom.xml').findall('{http://www.w3.org/2005/Atom}entry'), [])

    def test_every_chapter_is_visible_and_anchored_without_application_javascript(self):
        self.build()
        report = self.page(rp.REPORT_PATH)
        facts = Facts(report)
        for section in self.context['report']['sections']:
            self.assertIn(section['id'], facts.ids)
            self.assertIn(escape(section['title']), report)
            for paragraph in section['paragraphs']:
                if rp.paragraph_supported(self.context, paragraph):
                    self.assertIn(escape(paragraph['text'][:45]), report)
                else:
                    self.assertIn(rp.WITHHELD_PARAGRAPH, report)
        self.assertEqual(len(self.context['report']['sections']), 12)
        self.assertTrue(all(s.get('type') == 'application/ld+json' for s in facts.scripts))
        self.assertNotIn('type="module"', report)

    def test_candidate_assertion_wording_is_withheld_from_pages_and_search(self):
        candidate = copy.deepcopy(next(a for a in self.context['graph']['assertions'] if a['status'] == 'approved'))
        candidate.update(id='fixture.unreviewed-candidate', status='candidate', review_ids=[], object_id=None, value={'type': 'text', 'value': 'FORBIDDEN-CANDIDATE-FINDING'})
        candidate['qualifications'] = ['FORBIDDEN-CANDIDATE-QUALIFICATION']
        self.context['graph']['assertions'].append(candidate)
        next(e for e in self.context['graph']['entities'] if e['id'] == candidate['subject_id'])['assertion_ids'].append(candidate['id'])
        self.context['report']['sections'][0]['paragraphs'].append({
            'kind': 'sourced_fact', 'claim_ids': [candidate['id']], 'text': 'FORBIDDEN-CANDIDATE-PARAGRAPH'})
        self.build()
        for path in self.output.rglob('*.html'):
            self.assertNotIn('FORBIDDEN-CANDIDATE', path.read_text(), str(path))
        self.assertNotIn('FORBIDDEN-CANDIDATE', str(rp.research_search_entries(self.context)))
        self.assertIn('withheld because its evidence is not approved', self.page(rp.REPORT_PATH))

    def test_historical_evidence_keeps_its_date_locator_and_legacy_canonical(self):
        self.build()
        data = self.page('/research/data/')
        assertion = next(a for a in self.context['graph']['assertions'] if a['status'] == 'historical')
        self.assertIn(assertion['value']['value'].replace("'", '&#x27;'), data)
        self.assertIn('Historical record · As of ' + rp._date(assertion['as_of']), data)
        self.assertIn(assertion['evidence'][0]['locator'], data)
        self.assertIn('Inherited provenance; no fresh research review is claimed.', data)
        self.assertIn('/company/mercor/', data)

    def test_approved_subject_creates_only_its_new_company_page_with_receipts(self):
        claim = approved_new_org(self.context)
        records = self.build()
        paths = [row['path'] for row in records]
        self.assertIn('/company/org.fixture_translated/', paths)
        self.assertNotIn('/company/mercor/', paths)
        page = self.page('/company/org.fixture_translated/')
        self.assertIn('Translated', page)
        self.assertIn('supplies data for', page)
        self.assertIn('Synthetic approval fixture only.', page)
        self.assertIn(claim['evidence'][0]['locator'], page)
        source = next(s for s in self.context['graph']['sources'] if s['id'] == claim['evidence'][0]['source_id'])
        self.assertIn(source['excerpt'].replace("'", '&#x27;'), page)
        for role in ('author', 'source_verifier', 'adversarial'):
            self.assertIn('test-only-distinct-' + role, page)
        self.assertTrue(any(e['url'] == '/company/org.fixture_translated/' for e in rp.research_search_entries(self.context)))

    def test_object_only_approval_does_not_create_new_company_profile(self):
        claim = approved_new_org(self.context)
        claim['subject_id'], claim['object_id'] = claim['object_id'], claim['subject_id']
        paths = [row['path'] for row in self.build()]
        self.assertNotIn('/company/org.fixture_translated/', paths)
        self.assertNotIn('href="/company/org.fixture_translated/"', self.page('/research/data/'))

    def test_source_and_assertion_permalinks_resolve_to_unique_visible_targets(self):
        self.build()
        data = Facts(self.page('/research/data/'))
        self.assertEqual(len(data.ids), len(set(data.ids)))
        for kind, rows in (('source', self.context['graph']['sources']), ('assertion', self.context['graph']['assertions'])):
            for row in rows:
                self.assertIn(kind + '-' + row['id'], data.ids)
                self.assertIn(unquote(urlsplit(rp._evidence_url(kind, row['id'])).fragment), data.ids)
        for path in self.output.rglob('*.html'):
            facts = Facts(path.read_text())
            self.assertEqual(facts.headings, 1, str(path))
            self.assertEqual(len(facts.canonicals), 1, str(path))
            self.assertEqual(len(facts.ids), len(set(facts.ids)), str(path))

    def test_untrusted_text_is_escaped_and_unsafe_source_urls_are_not_links(self):
        attack = '<img src=x onerror="window.injected=true">'
        entity = next(e for e in self.context['graph']['entities'] if e['kind'] == 'paper')
        entity['name'] = attack
        self.context['graph']['sources'][0]['title'] = attack
        self.context['graph']['sources'][0]['url'] = 'javascript:alert(1)'
        self.build()
        for path in self.output.rglob('*.html'):
            text = path.read_text()
            self.assertNotIn(attack, text)
            self.assertNotIn('href="javascript:', text)
        self.assertIn('&lt;img', self.page(rp.entity_url(entity)))

    def test_forged_ready_edition_is_not_routed_or_added_to_feed(self):
        self.context['report']['status'] = 'published'
        self.context['report']['editions'] = [{'release_id': self.context['report']['release_id'],
                                               'status': 'published', 'gate': {'ready': True}}]
        paths = [row['path'] for row in self.build()]
        self.assertFalse(any('/editions/' in path for path in paths))
        self.assertEqual(ET.parse(self.output / 'research/feed.xml').findall('./channel/item'), [])

    def test_edition_routes_and_feed_entries_use_a_recomputed_passing_gate(self):
        self.context['report']['status'] = 'published'
        # This historical routing fixture stays fixed as the current report advances.
        self.context['report']['source_cutoff'] = '2026-11-06T17:00:00-08:00'
        self.context['report']['editions'] = [{'release_id': self.context['report']['release_id'], 'status': 'published'}]
        # Publication gate itself has separate holdout tests; this isolates its routing contract.
        with patch('research_report.publication_gate', return_value={**self.context['gate'], 'ready': True}) as gate:
            paths = [row['path'] for row in self.build()]
        gate.assert_called_once()
        edition = next(path for path in paths if '/editions/' in path)
        self.assertEqual(edition, '/research/editions/2026-11-09/')
        self.assertIn(edition + 'data/', paths)
        self.assertIn('Published edition', self.page(edition))
        self.assertEqual(len(ET.parse(self.output / 'research/feed.xml').findall('./channel/item')), 1)
        self.assertEqual(len(ET.parse(self.output / 'research/atom.xml').findall('{http://www.w3.org/2005/Atom}entry')), 1)

    def test_routes_are_encoded_as_single_segments_and_output_is_deterministic(self):
        entity = next(e for e in self.context['graph']['entities'] if e['kind'] == 'paper')
        entity['id'] = 'paper.example/../../version:1'
        first = self.build()
        content = {str(p.relative_to(self.output)): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(content, {str(p.relative_to(self.output)): p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
        url = rp.entity_url(entity)
        self.assertNotIn('%2F', url)
        self.assertNotIn('..%2F', url)
        self.assertEqual(url.count('/'), 4)
        self.assertTrue((self.output / url.strip('/') / 'index.html').is_file())
        self.assertEqual(len({row['path'] for row in first}), len(first))
        self.assertTrue(all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['lastmod']) for row in first))

    def test_search_records_are_compact_unique_and_match_generated_routes(self):
        paths = {row['path'] for row in self.build()}
        entries = rp.research_search_entries(self.context)
        self.assertEqual(len(entries), len({row['url'] for row in entries}))
        for entry in entries:
            self.assertEqual(set(entry), {'title', 'summary', 'url', 'kind', 'keywords'})
            self.assertIn(entry['url'], paths)
            self.assertLess(len(entry['summary']), 220)
        self.assertEqual((self.output / 'research.css').read_bytes(), (ROOT / 'web/research.css').read_bytes())

    def correction(self, **changes):
        return {'id': 'fixture.correction.1', 'edition_id': 'research.fixture.1',
                'claim_id': 'claim.fixture.1', 'summary': 'Synthetic correction <with markup> & qualification.',
                'status': 'accepted', 'corrected_on': '2026-11-09T09:30:00-08:00',
                'evidence_urls': ['https://example.org/evidence?version=1&part=2'], **changes}

    def test_actual_corrections_registry_and_feeds_are_truthfully_empty(self):
        import json
        registry = json.loads((ROOT / 'data/research/corrections.json').read_text())
        self.assertEqual(registry, {'schema_version': '1.0.0', 'corrections': []})
        self.context['corrections'] = registry['corrections']
        paths = {row['path'] for row in self.build()}
        self.assertIn(rp.CORRECTIONS_PATH, paths)
        self.assertIn('No accepted or published research corrections are recorded.', self.page(rp.CORRECTIONS_PATH))
        rss = ET.parse(self.output / 'research/corrections/feed.xml')
        atom = ET.parse(self.output / 'research/corrections/atom.xml')
        self.assertEqual(rss.findall('./channel/item'), [])
        self.assertEqual(atom.findall('{http://www.w3.org/2005/Atom}entry'), [])
        for path in ('/research/', '/review/'):
            text = self.page(path)
            self.assertIn('href="/research/corrections/feed.xml"', text)
            self.assertIn('href="/research/corrections/atom.xml"', text)
        self.assertIn('href="/research/corrections/"', self.page('/review/'))

    def test_only_actual_accepted_corrections_have_stable_page_and_feed_entries(self):
        accepted = self.correction()
        published = self.correction(id='fixture.correction.2', status='published', corrected_on='2026-11-10T01:00:00Z')
        pending = self.correction(id='fixture.pending', status='pending', summary='PRIVATE-PENDING-PROPOSAL')
        rejected = self.correction(id='fixture.rejected', status='rejected', summary='PRIVATE-REJECTED-PROPOSAL')
        self.context['corrections'] = [pending, accepted, rejected, published]
        self.build()
        page = self.page(rp.CORRECTIONS_PATH)
        self.assertIn('Synthetic correction &lt;with markup&gt; &amp; qualification.', page)
        self.assertNotIn('<with markup>', page)
        for row in (accepted, published):
            self.assertIn('correction-' + row['id'], Facts(page).ids)
            self.assertIn(row['edition_id'], page)
            self.assertIn(row['claim_id'], page)
        rss = ET.parse(self.output / 'research/corrections/feed.xml')
        atom = ET.parse(self.output / 'research/corrections/atom.xml')
        items, entries = rss.findall('./channel/item'), atom.findall('{http://www.w3.org/2005/Atom}entry')
        self.assertEqual(len(items), 2)
        self.assertEqual(len(entries), 2)
        expected = [rp.sp.ORIGIN + rp._correction_url(row) for row in (published, accepted)]
        self.assertEqual([item.findtext('guid') for item in items], expected)
        self.assertEqual([entry.findtext('{http://www.w3.org/2005/Atom}id') for entry in entries], expected)
        self.assertEqual(items[1].findtext('pubDate'), 'Mon, 09 Nov 2026 17:30:00 GMT')
        self.assertEqual(entries[1].findtext('{http://www.w3.org/2005/Atom}updated'), '2026-11-09T17:30:00Z')
        for item in items:
            self.assertIn('claim.fixture.1', item.findtext('description'))
            self.assertIn(accepted['evidence_urls'][0], item.findtext('description'))
        for path in self.output.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'PRIVATE-PENDING-PROPOSAL', path.read_bytes())
                self.assertNotIn(b'PRIVATE-REJECTED-PROPOSAL', path.read_bytes())
        first = {str(p.relative_to(self.output)): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        self.context['corrections'].reverse()
        self.build()
        self.assertEqual(first, {str(p.relative_to(self.output)): p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_malformed_or_unsafe_correction_records_fail_closed(self):
        cases = [self.correction(corrected_on='2026-11-09'),
                 self.correction(corrected_on='2026-11-09T12:00:00'),
                 self.correction(corrected_on='not-a-date'),
                 self.correction(id='../unsafe'), self.correction(edition_id=''),
                 self.correction(claim_id=''), self.correction(summary=' '),
                 self.correction(status='unconfirmed'), self.correction(status={}),
                 self.correction(evidence_urls=[]), self.correction(evidence_urls=['javascript:alert(1)']),
                 self.correction(evidence_urls=['https://user:secret@example.org/']),
                 self.correction(evidence_urls=['https://example.org/\nunsafe']),
                 self.correction(evidence_urls=['https://example.org/', 'https://example.org/'])]
        missing = self.correction()
        missing.pop('claim_id')
        cases.append(missing)
        for row in cases:
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.context['corrections'] = [row]
                self.build()
        self.context['corrections'] = [self.correction(), self.correction()]
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.build()


if __name__ == '__main__':
    unittest.main()
