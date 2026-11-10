"""Public rendering invariants; synthetic approval receipts stay inside tests."""
import copy
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
    assertion = next(a for a in context['graph']['assertions'] if a['subject_id'] == 'org.translated')
    assertion.update(status='approved', review_ids=[], qualifications=['Synthetic approval fixture only.'])
    for entity in context['graph']['entities']:
        if entity['id'] == 'org.translated':
            entity.update(status='approved', disposition='included', review_depth='full_source')
    context['graph']['reviews'] = [r for r in context['graph']['reviews'] if assertion['id'] not in r['assertion_ids']]
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
            self.assertIn(section['title'].replace('&', '&amp;'), report)
            for paragraph in section['paragraphs']:
                self.assertIn(paragraph['text'][:45].replace("'", '&#x27;').replace('&', '&amp;'), report)
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
        self.assertIn('/company/org.translated/', paths)
        self.assertNotIn('/company/mercor/', paths)
        page = self.page('/company/org.translated/')
        self.assertIn('Translated', page)
        self.assertIn('supplies data for', page)
        self.assertIn('Synthetic approval fixture only.', page)
        self.assertIn(claim['evidence'][0]['locator'], page)
        source = next(s for s in self.context['graph']['sources'] if s['id'] == claim['evidence'][0]['source_id'])
        self.assertIn(source['excerpt'].replace("'", '&#x27;'), page)
        for role in ('author', 'source_verifier', 'adversarial'):
            self.assertIn('test-only-distinct-' + role, page)
        self.assertTrue(any(e['url'] == '/company/org.translated/' for e in rp.research_search_entries(self.context)))

    def test_object_only_approval_does_not_create_new_company_profile(self):
        claim = approved_new_org(self.context)
        claim['subject_id'], claim['object_id'] = claim['object_id'], claim['subject_id']
        paths = [row['path'] for row in self.build()]
        self.assertNotIn('/company/org.translated/', paths)
        self.assertNotIn('href="/company/org.translated/"', self.page('/research/data/'))

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


if __name__ == '__main__':
    unittest.main()
