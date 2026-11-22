"""Public rendering invariants; synthetic approval receipts stay inside tests."""
import copy
import hashlib
import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_graph as rg
import research_pages as rp
from research_report import build_context
from research_lifecycle_fixtures import isolated_render_context, isolated_render_preparation


class Facts(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links, self.canonicals, self.scripts = [], [], [], []
        self.headings = 0
        self.nodes, self.records, self.aliases = 0, {}, {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes += 1
        if attrs.get('id'):
            self.ids.append(attrs['id'])
            if tag == 'article':
                self.records[attrs['id']] = attrs
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
            if attrs.get('id', '').startswith(('assertion-', 'source-')) and attrs['href'].startswith(('assertions/', 'sources/')):
                self.aliases[attrs['id']] = '/research/data/' + attrs['href']
        if tag == 'h1':
            self.headings += 1
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'script':
            self.scripts.append(attrs)


class ReaderTree(HTMLParser):
    """Inspect visible reader structure without depending on renderer helpers."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, text):
        super().__init__()
        self.elements, self.stack = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'children': []}
        self.elements.append(node)
        if self.stack:
            self.stack[-1]['children'].append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]['children'].append(data)

    @staticmethod
    def text(node):
        return ''.join(child if isinstance(child, str) else ReaderTree.text(child)
                       for child in node['children'])

    @staticmethod
    def links(node):
        own = [node['attrs']['href']] if node['tag'] == 'a' and 'href' in node['attrs'] else []
        return own + [href for child in node['children'] if isinstance(child, dict)
                      for href in ReaderTree.links(child)]

    def with_class(self, name):
        return [node for node in self.elements if name in node['attrs'].get('class', '').split()]


def approved_new_org(context):
    """Promote one test-only source-bound assertion with honest fixture receipts."""
    original = next(a for a in context['graph']['assertions'] if a['subject_id'] == 'org.translated')
    assertion = copy.deepcopy(original)
    assertion.update(id='fixture.claim.new-org', subject_id='org.fixture_translated', status='approved',
                     predicate='supplies_data_for',
                     review_ids=[], qualifications=['Synthetic approval fixture only.'])
    entity = copy.deepcopy(next(e for e in context['graph']['entities'] if e['id'] == 'org.translated'))
    entity.update(id='org.fixture_translated', status='approved', disposition='included',
                  review_depth='full_source', identifiers={}, assertion_ids=[assertion['id']],
                  eligible_core=False)
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
        if cls.baseline.get('published_edition_replay'):
            cls.render_baseline = cls.enterClassContext(isolated_render_preparation(
                cls.baseline, canonical_bytes=(ROOT / 'data/canonical.json').read_bytes()))
        else:
            cls.render_baseline = isolated_render_context(cls.baseline)

    def setUp(self):
        self.context = copy.deepcopy(self.render_baseline)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.output = Path(self.scratch.name)

    def build(self):
        return rp.write_research_pages(self.output, self.context)

    def page(self, path):
        return (self.output / path.strip('/') / 'index.html').read_text()

    def test_current_data_explains_the_frozen_pdf_cover(self):
        self.context['publication_assets'] = ['publication/report.pdf']
        report = self.context['report']
        pdf_link = '<a href="/publication/report.pdf">Read the report PDF</a>'
        self.assertIn(pdf_link, rp._data(self.context))
        report.update(release_id='research-2026-11-12.1', archive={
            'status': 'published', 'artifact_sha256': rp.EDITION_MIRROR_ARCHIVE_SHA256})
        self.assertIn('<a href="/publication/report.pdf">Read the archived report PDF (research-2026-11-12.1)</a>'
                      '. The cover was prepared before DOI registration.', rp._data(self.context))

    def test_current_citation_does_not_link_a_reserved_doi(self):
        reserved_doi = '10.5281/zenodo.111111111'
        self.context['report']['archive']['reserved_doi'] = reserved_doi
        data = ReaderTree(rp._data(self.context))
        citation, = (node for node in data.elements if node['attrs'].get('id') == 'citation')
        self.assertNotIn(reserved_doi, ReaderTree.text(citation))
        self.assertNotIn('https://doi.org/' + reserved_doi, ReaderTree.links(citation))

    def test_current_reader_labels_only_available_archived_formats(self):
        html, pdf = 'publication/report.html', 'publication/report.pdf'
        self.context['publication_assets'] = [html, pdf]
        self.assertIn('Read offline: <a href="/publication/report.html">Complete HTML report</a> · '
                      '<a href="/publication/report.pdf">Full report PDF</a>', rp._reader_downloads(self.context))

        self.context['report'].update(updated_on='2026-11-15', archive={
            'status': 'published', 'artifact_sha256': rp.EDITION_MIRROR_ARCHIVE_SHA256})
        for available in ([html, pdf], [html], [pdf], []):
            with self.subTest(available=available):
                self.context['publication_assets'] = available
                downloads = ReaderTree(rp._reader_downloads(self.context)).with_class('r-reader-downloads')
                if not available:
                    self.assertEqual(downloads, [])
                    continue
                control, = downloads
                self.assertEqual(ReaderTree.links(control), ['/' + path for path in available])
                labels = {html: 'Archived HTML report', pdf: 'Archived report PDF'}
                self.assertEqual(ReaderTree.text(control), ' · '.join(labels[path] for path in available)
                                 + ' · 15 Nov 2026 snapshot. Prepared before DOI registration.')

    def test_actual_baseline_lifecycle_has_only_verified_publications(self):
        import research_citations as citations
        from research_report import publication_gate
        # Inspect the actual source separately from the mutable render fixtures.
        self.context = copy.deepcopy(self.baseline)
        if self.context.get('published_edition_replay'):
            from research_edition_replay import read_replay_package
            frozen = read_replay_package(self.context)
            self.assertTrue(frozen['report.pdf'].startswith(b'%PDF-'))
            self.assertEqual(self.context['gate']['status'], 'published_frozen_replay')
            self.assertFalse(self.context['gate']['archival_ready'])
            self.assertFalse(self.context['replay_verification']['current_input_readiness_revalidated'])
            self.assertFalse(self.context['replay_verification']['raw_sources_revalidated'])
        else:
            self.assertEqual(self.context['gate'], publication_gate(
                self.context['graph'], self.context['report'], self.context['policy']))
        json_sizes = {'/publication/clean-dataset.json': 2_810_000, '/research/exports/research-graph.json': 3_920_000}
        for url, size in json_sizes.items():
            file = self.output / url.lstrip('/')
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open('wb') as stream:
                stream.truncate(size)
        self.context['publication_assets'] = ['publication/current-REUSE.md']
        records = self.build()
        paths = [r['path'] for r in records]
        for path in ('/research/', rp.REPORT_PATH, '/research/data/', '/review/',
                     '/research/papers/', '/research/datasets/', '/research/benchmarks/', '/research/workflows/'):
            self.assertIn(path, paths)
        metadata = citations.publication_metadata(self.context)
        if self.context['report'].get('archive', {}).get('status') == 'published':
            self.assertEqual(self.context['report']['status'], 'published')
            self.assertTrue(citations.published_archive(self.context))
            self.assertTrue(self.context['gate']['ready'], self.context['gate']['reasons'])
            self.assertIn('prepared_package', self.context)
            if not self.context.get('published_edition_replay'):
                self.assertIn('prepared_package_expected', self.context)
                frozen = citations.read_prepared_package(self.context, self.context['prepared_package'],
                    expected_archive_sha256=self.context['report']['archive']['artifact_sha256'])
            self.assertTrue(frozen['report.pdf'].startswith(b'%PDF-'))
            self.assertEqual(metadata['status'], 'published')
            self.assertEqual(metadata['doi'], self.context['report']['archive']['doi'])
        else:
            self.assertFalse(self.context['gate']['ready'])
            self.assertNotEqual(metadata['status'], 'published')
            self.assertNotIn('doi', metadata)
            self.assertNotIn('published_on', metadata)
            self.assertIn('Prelaunch', self.page('/research/'))
        editions = rp._published_editions(self.context)
        data = ReaderTree(self.page('/research/data/'))
        citation, = (node for node in data.elements if node['attrs'].get('id') == 'citation')
        if metadata['status'] == 'published':
            doi = self.context['report']['archive']['doi']
            citation_links = ReaderTree.links(citation)
            self.assertIn('Registered version DOI ' + doi, ReaderTree.text(citation))
            self.assertEqual(citation_links[0], 'https://doi.org/' + doi)
            self.assertTrue({'/publication/current-' + name for name in rp.EDITION_CITATIONS} <= set(citation_links))
        links = {node['attrs']['href']: node for node in data.elements if node['tag'] == 'a'}
        for url, size in json_sizes.items():
            self.assertIn('download', links[url]['attrs'])
            self.assertTrue(ReaderTree.text(links[url]).endswith(f'({size / 1_000_000:.1f} MB)'))
        for url in ('/research/exports/research-exports-manifest.json', '/publication/MANIFEST.json'):
            self.assertNotIn('download', links[url]['attrs'])
        for path, snapshot in editions:
            if snapshot['report']['release_id'] == 'research-2026-11-12.1':
                edition_data = self.page(path + 'data/')
                self.assertIn('corrects the Python example for <code>clean-dataset.json</code> to use <code>subject_id</code>', edition_data)
                self.assertIn('/publication/current-REUSE.md', Facts(edition_data).links)
                mirror = ('https://raw.githubusercontent.com/tirtilaklak/sciencetostartup/'
                          'aac87fd94dc86dee4976176fddb0764215898107/data/research/releases/research-2026-11-12.1/publication/')
                self.assertTrue({mirror + name for name in ('research-archive.zip', 'report.pdf', 'MANIFEST.json')}
                                <= set(Facts(edition_data).links))
        if metadata['status'] == 'published':
            self.assertIn(self.context['report']['release_id'],
                          [snapshot['report']['release_id'] for _, snapshot in editions])
        self.assertEqual({path for path in paths if re.fullmatch(r'/research/editions/[^/]+/', path)},
                         {path for path, _ in editions})
        if not self.context['report'].get('editions') and not self.context.get('public_edition_ledger'):
            self.assertFalse(any('/editions/' in path for path in paths))
        expected_companies = {rp.entity_url(entity, self.context) for entity in self.context['graph']['entities'] if rp._new_company(self.context, entity)}
        self.assertEqual({path for path in paths if path.startswith('/company/')}, expected_companies)
        approved = sum(a['status'] == 'approved' for a in self.context['graph']['assertions'])
        self.assertIn(f'{approved} approved assertions', self.page('/research/data/'))
        if not approved:
            self.assertIn('No new assertions have completed', self.page('/research/data/'))
        expected_urls = [rp.sp.ORIGIN + path for path, _ in editions]
        self.assertEqual([item.findtext('link') for item in ET.parse(self.output / 'research/feed.xml').findall('./channel/item')], expected_urls)
        self.assertEqual([entry.findtext('{http://www.w3.org/2005/Atom}id') for entry in
                          ET.parse(self.output / 'research/atom.xml').findall('{http://www.w3.org/2005/Atom}entry')], expected_urls)

    def assert_native_reading_guard(self, source):
        """Execute the actual bounded guard against navigation/history states."""
        self.assertGreater(len(source.encode('utf-8')), 0)
        self.assertLessEqual(len(source.encode('utf-8')), 1024,
                             'The technical chapter permits only a small native-reading guard')
        harness = r"""
const assert = require('node:assert/strict'), vm = require('node:vm');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8')).source;
const scenarios = ['navigate', 'back_forward', 'reload', 'empty', 'missing-api', 'missing-performance'];
for (const scenario of scenarios) {
  const attributes = new Map(), listeners = new Map(), violations = [];
  const element = {
    setAttribute(name, value) { if (name !== 'data-reader-enhanced' || value !== '') violations.push('attribute'); attributes.set(name, value); },
    removeAttribute(name) { if (name !== 'data-reader-enhanced') violations.push('attribute'); attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); }
  };
  const document = new Proxy({documentElement: element}, {get(target, key) {
    if (!(key in target)) violations.push('document access'); return target[key];
  }});
  const sandbox = {document, addEventListener(type, listener) {
    if (!['pageshow', 'DOMContentLoaded'].includes(type) || typeof listener !== 'function') violations.push('listener');
    else listeners.set(type, listener);
  }, fetch() { violations.push('network'); throw Error('No network in guard'); },
  XMLHttpRequest: function() { violations.push('network'); },
  WebSocket: function() { violations.push('network'); }};
  if (scenario !== 'missing-performance') sandbox.performance = scenario === 'missing-api' ? {} : {
    getEntriesByType(type) { assert.equal(type, 'navigation'); return scenario === 'empty' ? [] : [{type: scenario}]; }
  };
  vm.runInContext(source, vm.createContext(sandbox, {codeGeneration: {strings: false, wasm: false}}), {timeout: 100});
  assert.deepEqual(violations, [], scenario);
  assert.equal(attributes.has('data-reader-enhanced'), scenario === 'navigate', scenario);
  if (scenario === 'navigate') {
    assert.equal(listeners.size, 2);
    listeners.get('DOMContentLoaded')();
    assert.equal(attributes.has('data-reader-enhanced'), false, 'Unavailable deferred script retains native End');
    attributes.set('data-reader-enhanced', '');
    attributes.set('data-reader-end-ready', '');
    listeners.get('DOMContentLoaded')();
    listeners.get('pageshow')({persisted: false});
    assert.equal(attributes.has('data-reader-enhanced'), true);
    listeners.get('pageshow')({persisted: true});
    assert.equal(attributes.has('data-reader-enhanced'), false);
    assert.deepEqual(violations, []);
  }
}
console.log(JSON.stringify({scenarios: scenarios.length, passed: true}));
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps({'source': source}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'scenarios': 6, 'passed': True})

    def test_every_complete_chapter_has_a_native_url_without_application_javascript(self):
        records = {row['path']: row for row in self.build()}
        report = self.page(rp.REPORT_PATH)
        facts = Facts(report)
        sections = self.context['report']['sections']
        routes = [rp.REPORT_PATH if index == 0 else rp.REPORT_PATH + 'chapters/' + section['id'] + '/'
                  for index, section in enumerate(sections)]
        early_shortcuts = {'technical-landscape', 'datasets-and-benchmarks', 'methods-and-appendices',
                           'commercial-evidence'}
        passage_targets = {
            'technical-landscape': {'scalable-oversight-result':
                                    'Study result — Measuring Progress on Scalable Oversight for Large Language Models.'},
            'buyer-decision-guides': {'buyer-statistical-acceptance-rule':
                                      'A proposed statistical acceptance rule should make its assumptions explicit.'},
            'commercial-evidence': {'commercial-buyer-calculation': 'Reproducible buyer calculation:',
                                    'commercial-review-calculation': 'Reproducible review calculation:'},
        }
        expected_parts = [rp.sp.ORIGIN + route + ('#executive-assessment' if index == 0 else '')
                          for index, route in enumerate(routes)]
        for index, section in enumerate(sections):
            self.assertIn(section['id'], facts.ids)
            self.assertIn(escape(section['title']), report)
            path = rp.REPORT_PATH if section['id'] == 'executive-assessment' else (
                rp.REPORT_PATH + 'chapters/' + section['id'] + '/')
            self.assertIn(path + ('#' + section['id'] if index else ''), facts.links)
            chapter = self.page(path)
            chapter_facts = Facts(chapter)
            self.assertEqual(chapter_facts.canonicals, [rp.sp.ORIGIN + path])
            self.assertIn(section['id'], chapter_facts.ids)
            self.assertEqual(chapter_facts.ids.count('first-paragraph'), 1)
            self.assertEqual(chapter_facts.links.count('#first-paragraph'), 1)
            for paragraph in section['paragraphs']:
                if rp.paragraph_supported(self.context, paragraph):
                    self.assertIn(escape(paragraph['text']), chapter)
                else:
                    self.assertIn(rp.WITHHELD_PARAGRAPH, chapter)
            self.assertEqual([script for script in chapter_facts.scripts if 'src' in script],
                             [{'src': '/native-details.js', 'defer': None}] if index else [])
            self.assertNotIn('type="module"', chapter)
            tree = ReaderTree(chapter)
            shortcuts = tree.with_class('r-bulk-shortcuts')[0]
            if section['id'] in early_shortcuts:
                self.assertLess(tree.elements.index(shortcuts),
                                next(index for index, item in enumerate(tree.elements) if item['tag'] == 'h1'))
            for anchor, lead_in in passage_targets.get(section['id'], {}).items():
                matching = [paragraph for paragraph in section['paragraphs']
                            if paragraph['text'].startswith(lead_in) and rp.paragraph_supported(self.context, paragraph)]
                if not matching:
                    continue  # The held legacy authoring inputs predate some reviewed passages.
                self.assertEqual(len(matching), 1)
                target, = [item for item in tree.with_class('r-paragraph') if item['attrs'].get('id') == anchor]
                self.assertEqual(target['attrs'].get('tabindex'), '-1')
                self.assertIn('#' + anchor, ReaderTree.links(shortcuts))
                self.assertEqual(ReaderTree.text(target['children'][1]), matching[0]['text'])
            guards = [item for item in tree.elements if item['tag'] == 'script'
                      and 'src' not in item['attrs'] and item['attrs'].get('type') != 'application/ld+json']
            if section['id'] == 'technical-landscape':
                self.assertEqual(len(guards), 1)
                self.assertIn(guards[0]['attrs'].get('type', '').strip().lower(),
                              ('', 'text/javascript', 'application/javascript'))
                self.assertNotIn('data-reader-enhanced', next(
                    item['attrs'] for item in tree.elements if item['tag'] == 'html'))
                self.assert_native_reading_guard(ReaderTree.text(guards[0]))
            else:
                self.assertEqual(guards, [], 'Only the technical chapter permits the reading guard')
            toc = tree.with_class('r-reader-toc')[0]
            toc_links = [item['children'][0] for listing in toc['children']
                         if isinstance(listing, dict) and listing['tag'] == 'ol'
                         for item in listing['children'] if isinstance(item, dict)]
            expected_routes = routes if index else [routes[0]] + [route + '#' + item['id']
                                                                   for route, item in zip(routes[1:], sections[1:])]
            self.assertEqual([link['attrs']['href'] for link in toc_links], expected_routes)
            self.assertEqual([link['attrs']['href'] for link in toc_links if link['attrs'].get('aria-current') == 'page'], [path])
            node = json.loads(next(ReaderTree.text(item) for item in tree.elements
                                   if item['tag'] == 'script' and item['attrs'].get('type') == 'application/ld+json'))
            self.assertEqual(node['@type'], 'Book' if index == 0 else 'Chapter')
            self.assertEqual(node['@id'], rp.sp.ORIGIN + path)
            self.assertEqual(node['dateModified'], records[path]['lastmod'])
            self.assertEqual(node['version'], self.context['report']['release_id'])
            if index == 0:
                self.assertEqual([part['@id'] for part in node['hasPart']], expected_parts)
                self.assertEqual([part['position'] for part in node['hasPart']], list(range(1, 13)))
            else:
                self.assertEqual(node['isPartOf']['@id'], rp.sp.ORIGIN + rp.REPORT_PATH)
                self.assertEqual(node['position'], index + 1)
            for relation, other in [('prev', index - 1), ('next', index + 1)]:
                expected = [routes[other]] if 0 <= other < len(routes) else []
                for tag in ('link', 'a'):
                    self.assertEqual([item['attrs']['href'] for item in tree.elements
                                      if item['tag'] == tag and item['attrs'].get('rel') == relation], expected)
        self.assertEqual(len(sections), 12)
        # Former full-document fragments land on visible, named native links.
        entry_tree = ReaderTree(report)
        for section, route in zip(sections[1:], routes[1:]):
            target = next(item for item in entry_tree.elements if item['attrs'].get('id') == section['id'])
            self.assertEqual(target['tag'], 'li')
            self.assertEqual(target['children'][0]['attrs']['href'], route + '#' + section['id'])
            self.assertEqual(ReaderTree.text(target).strip(), section['title'])

    def test_native_book_conserves_all_ordered_prose_findings_and_evidence_bindings(self):
        before = copy.deepcopy(self.context)
        self.build()
        observed_prose, expected_prose, observed_evidence, expected_evidence = [], [], [], []
        findings, withheld = rp.executive_findings(self.context)
        for index, section in enumerate(self.context['report']['sections']):
            path = rp.REPORT_PATH if index == 0 else rp.REPORT_PATH + 'chapters/' + section['id'] + '/'
            tree = ReaderTree(self.page(path))
            paragraphs = tree.with_class('r-paragraph')
            self.assertEqual(len(paragraphs), len(section['paragraphs']))
            if section['id'] == 'methods-and-appendices':
                originals = {
                    child['attrs']['href'] for original in tree.with_class('r-paragraph-originals')
                    for child in original['children'] if isinstance(child, dict) and child['tag'] == 'a'
                }
                self.assertIn('https://arxiv.org/pdf/2307.13854v1', originals)
                self.assertIn(
                    'https://storage.googleapis.com/gweb-research2023-media/pubtools/pdf/0d556e45afc54afeb2eb6b51a9bc1827b9961ff4.pdf',
                    originals)
                self.assertIn('https://www.mercor.com/apex/', originals)
            for actual, paragraph in zip(paragraphs, section['paragraphs']):
                supported = rp.paragraph_supported(self.context, paragraph)
                main = [child for child in actual['children'] if isinstance(child, dict)
                        and child['tag'] == 'p' and not child['attrs'].get('class')]
                self.assertEqual(len(main), 1)
                observed_prose.append(ReaderTree.text(main[0]))
                expected_prose.append(paragraph['text'] if supported else rp.WITHHELD_PARAGRAPH)
                if supported:
                    expected_evidence.extend(rp._evidence_url('assertion', cid) for cid in paragraph.get('claim_ids', []))
            rendered_findings = tree.with_class('r-finding')
            self.assertEqual([item['attrs']['id'] for item in rendered_findings],
                             [rp.finding_anchor(item) for item in findings] if index == 0 else [])
            if index == 0:
                for actual, finding in zip(rendered_findings, findings):
                    self.assertIn(rp.field_text(finding['text']), ReaderTree.text(actual))
                    for key, _ in rp.JUDGMENT_FIELDS:
                        if rp.field_text(finding.get(key)):
                            self.assertIn(rp.field_text(finding[key]), ReaderTree.text(actual))
                    expected_evidence.extend(rp._evidence_url('assertion', cid) for cid in finding['claim_ids'])
            observed_evidence.extend(child['attrs']['href'] for node in tree.with_class('r-paragraph-citations')
                                     for child in node['children'] if isinstance(child, dict) and child['tag'] == 'a')
        self.assertEqual(observed_prose, expected_prose)
        self.assertEqual(observed_evidence, expected_evidence)
        self.assertEqual(self.context, before, 'Rendering must not mutate reviewed source context')

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
        assertion = next(a for a in self.context['graph']['assertions'] if a['status'] == 'historical')
        data = self.page(urlsplit(rp._evidence_url('assertion', assertion['id'])).path)
        self.assertIn(assertion['value']['value'].replace("'", '&#x27;'), data)
        self.assertIn('Historical record · As of ' + rp._date(assertion['as_of']), data)
        self.assertIn(assertion['evidence'][0]['locator'], data)
        self.assertIn('Inherited provenance; no fresh research review is claimed.', data)
        self.assertIn('/company/mercor/', self.page('/research/data/'))

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
        tree = ReaderTree(page)
        self.assertEqual(len(tree.with_class('research-company-dossier')), 1)
        self.assertTrue(all('open' not in node['attrs'] for node in tree.with_class('company-fold')))
        self.assertIn('approved-findings', Facts(page).ids)
        self.assertTrue(any(e['url'] == '/company/org.fixture_translated/' for e in rp.research_search_entries(self.context)))

    def test_new_company_dossiers_preserve_full_records_inside_closed_sections(self):
        companies = [entity for entity in self.context['graph']['entities'] if rp._new_company(self.context, entity)]
        self.assertTrue(companies)
        for entity in companies:
            with self.subTest(company=entity['id']):
                text = rp._detail(self.context, entity)
                tree = ReaderTree(text)
                folds = tree.with_class('company-fold')
                approved = rp._assertions(self.context, entity)
                historical = rp._assertions(self.context, entity, ('historical',))
                self.assertEqual(len(folds), 4 if historical else 3)
                self.assertTrue(all('open' not in node['attrs'] for node in folds))
                scope = next(node for node in folds if node['attrs']['id'] == 'company-scope')
                scope_text = ReaderTree.text(scope)
                for value in (entity['id'], entity['disposition_reason'], entity['disposition'],
                              entity['review_depth'].replace('_', ' '), *entity.get('identifiers', {}).values()):
                    self.assertIn(value, scope_text)
                self.assertIn(rp._meta(self.context), text)
                for assertion in approved:
                    # Full records include source locators, qualifications and actual receipts.
                    self.assertIn(rp._assertion(self.context, assertion, focusable=True), text)
                for assertion in historical:
                    self.assertIn(rp._assertion(self.context, assertion), text)
                linked = [a for a in self.context['graph']['assertions']
                          if entity['id'] in {a.get('subject_id'), a.get('object_id')}]
                source_ids = {evidence['source_id'] for assertion in linked for evidence in assertion.get('evidence', [])}
                sources = next(node for node in folds if node['attrs']['id'] == 'company-sources')
                for source_id in source_ids:
                    self.assertIn(rp._evidence_url('source', source_id), ReaderTree.links(sources))
                hero = ReaderTree.text(tree.with_class('company-hero')[0])
                self.assertIn(f'{len(approved)} approved finding', hero)
                self.assertNotIn(entity['disposition_reason'], hero)
                website = rp._safe_url(entity.get('identifiers', {}).get('website'))
                if website:
                    self.assertIn(website, ReaderTree.links(tree.with_class('company-hero')[0]))
                facts = Facts(text)
                self.assertEqual(len(facts.ids), len(set(facts.ids)))

    def test_company_detail_branch_does_not_change_other_research_records(self):
        paper = next(entity for entity in self.context['graph']['entities'] if entity['kind'] in {'paper', 'paper_work'})
        legacy = next(entity for entity in self.context['graph']['entities'] if entity.get('legacy_id'))
        with patch.object(rp, '_company_detail', side_effect=AssertionError('Company-only renderer')):
            for entity in (paper, legacy):
                text = rp._detail(self.context, entity)
                self.assertIn('class="r-page-head"', text)
                self.assertNotIn('research-company-dossier', text)

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
        partitions = {rp._ledger_path(kind, bucket): Facts(self.page(rp._ledger_path(kind, bucket)))
                      for kind in ('assertion', 'source') for bucket in '0123456789abcdef'}
        for kind, rows in (('source', self.context['graph']['sources']), ('assertion', self.context['graph']['assertions'])):
            for row in rows:
                self.assertIn(kind + '-' + row['id'], data.ids)
                destination = urlsplit(rp._evidence_url(kind, row['id']))
                self.assertEqual(data.aliases[kind + '-' + row['id']], rp._evidence_url(kind, row['id']))
                self.assertIn(unquote(destination.fragment), partitions[destination.path].records)
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
        from test_research_edition_replay import fixture
        from research_edition_replay import load_published_edition
        root, _, descriptor, current = fixture(self.output / 'SYNTHETIC-fixture', routing_literals=True)
        frozen = load_published_edition(root, descriptor)
        self.context = copy.deepcopy(current)
        self.context['identity']['publisher']['url'] = 'https://example.invalid/SYNTHETIC-publisher'
        self.context['report']['editions'] = [{'release_id': frozen['report']['release_id'], 'status': 'published'}]
        self.context['edition_snapshots'] = {frozen['report']['release_id']: frozen}
        # Frozen replay checks its exact package and receipt, without pretending
        # its public projection can pass a fresh private-input publication gate.
        with patch('research_report.publication_gate', side_effect=AssertionError('No fake fresh gate')):
            paths = [row['path'] for row in self.build()]
        edition = next(path for path in paths if '/editions/' in path)
        self.assertEqual(edition, '/research/editions/2026-11-12/')
        self.assertIn(edition + 'data/', paths)
        archive = frozen['report']['archive']
        dated_data = self.page(edition + 'data/')
        dated_facts = Facts(dated_data)
        self.assertIn(archive['record_url'] + '/files/report.pdf?download=1', dated_facts.links)
        self.assertIn(archive['record_url'] + '/files/research-archive.zip?download=1', dated_facts.links)
        manifest = archive['record_url'] + '/files/MANIFEST.json'
        self.assertIn(manifest, dated_facts.links)
        self.assertNotIn(manifest + '?download=1', dated_facts.links)
        for filename in rp.EDITION_CITATIONS:
            path = edition + 'data/citations/' + filename
            self.assertIn(path, dated_facts.links)
            citation = (self.output / path.strip('/')).read_text()
            self.assertIn(archive['doi'], citation)
            self.assertIn(frozen['report']['release_id'], citation)
        self.assertFalse(set('assertion-' + aid for aid in rp.RETIRED_ASSERTION_IDS) & set(dated_facts.ids))
        for kind in ('assertions', 'sources'):
            for bucket in '0123456789abcdef':
                route = edition + 'data/' + kind + '/' + bucket + '/'
                self.assertIn(route, paths)
                self.assertIn(rp.sp.ORIGIN + route, Facts(self.page(route)).canonicals)
                self.assertFalse(any(link.startswith('/research/data/') for link in Facts(self.page(route)).links))
        self.assertIn('Published edition', self.page(edition))
        source = frozen['graph']['sources'][0]
        source_path = edition + 'data/sources/' + hashlib.sha256(source['id'].encode('utf-8')).hexdigest()[0] + '/'
        self.assertIn('href="https://example.org/research/data/frozen-source"', self.page(source_path))
        self.assertIn('Literal /research/data/#quoted-source-title', self.page(source_path))
        source_record = rp._evidence_url('source', source['id']).replace('/research/data/', edition + 'data/', 1)
        source_corrections = [parse_qs(urlsplit(link).query) for link in Facts(self.page(source_path)).links
                              if link.startswith('/method/?correction=')]
        self.assertIn({'correction': [source['id']], 'edition': [frozen['report']['release_id']],
                       'record': [source_record]}, source_corrections)
        rss = ET.parse(self.output / 'research/feed.xml').findall('./channel/item')
        atom = ET.parse(self.output / 'research/atom.xml').findall('{http://www.w3.org/2005/Atom}entry')
        self.assertEqual(len(rss), 1)
        self.assertEqual(len(atom), 1)
        canonical = rp.sp.ORIGIN + edition
        self.assertEqual(rss[0].findtext('link'), canonical)
        self.assertEqual(rss[0].findtext('guid'), canonical)
        self.assertEqual(atom[0].findtext('{http://www.w3.org/2005/Atom}id'), canonical)
        self.assertEqual(atom[0].find('{http://www.w3.org/2005/Atom}link').get('href'), canonical)
        title = frozen['report']['title'] + ' · ' + frozen['report']['release_id']
        self.assertEqual(rss[0].findtext('title'), title)
        self.assertEqual(atom[0].findtext('{http://www.w3.org/2005/Atom}title'), title)
        self.assertEqual(atom[0].findtext('{http://www.w3.org/2005/Atom}updated'),
                         frozen['report']['updated_on'] + 'T00:00:00Z')

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
        self.assertTrue(all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['lastmod']) for row in first if 'lastmod' in row))

    def test_search_records_are_compact_unique_and_match_generated_routes(self):
        paths = {row['path'] for row in self.build()}
        entries = rp.research_search_entries(self.context)
        self.assertEqual(len(entries), len({row['url'] for row in entries}))
        for entry in entries:
            keys = {'title', 'summary', 'url', 'kind', 'keywords'}
            if entry['kind'] == 'paper':
                keys |= {'identifiers', 'recordKind'}
                self.assertIn(entry['recordKind'], {'paper', 'paper_work', 'paper_version'})
                self.assertTrue(entry['identifiers'])
            self.assertEqual(set(entry), keys)
            self.assertIn(entry['url'], paths)
            self.assertLess(len(entry['summary']), 220)
        self.assertEqual((self.output / 'research.css').read_bytes(), (ROOT / 'web/research.css').read_bytes())

    def test_full_ledger_is_partitioned_once_with_thin_legacy_fragment_hub(self):
        records = self.build()
        paths = {row['path'] for row in records}
        hub = Facts(self.page('/research/data/'))
        self.assertEqual(hub.records, {})
        self.assertEqual(len([url for url in hub.links if re.fullmatch(r'/research/data/(?:assertions|sources)/[0-9a-f]/', url)]), 32)
        all_records = {}
        for kind, rows in (('assertion', self.context['graph']['assertions']), ('source', self.context['graph']['sources'])):
            expected = {kind + '-' + row['id'] for row in rows}
            observed = set()
            for bucket in '0123456789abcdef':
                path = '/research/data/' + ('assertions' if kind == 'assertion' else 'sources') + '/' + bucket + '/'
                self.assertIn(path, paths)
                facts = Facts(self.page(path))
                matching = {key: value for key, value in facts.records.items() if key.startswith(kind + '-')}
                self.assertFalse(observed & set(matching))
                observed.update(matching)
                all_records.update(matching)
                self.assertEqual(facts.canonicals, [rp.sp.ORIGIN + path])
                self.assertTrue(all(item.get('type') == 'application/ld+json' for item in facts.scripts))
            self.assertTrue(expected <= observed)
            for row in rows:
                anchor = kind + '-' + row['id']
                self.assertEqual(hub.aliases[anchor], rp._evidence_url(kind, row['id']))
                expected_bucket = hashlib.sha256(row['id'].encode('utf-8')).hexdigest()[0]
                self.assertIn('/' + expected_bucket + '/#', hub.aliases[anchor])
        self.assertEqual(len(hub.aliases), len(all_records))
        for stable_id in rp.RETIRED_ASSERTION_IDS:
            anchor = 'assertion-' + stable_id
            self.assertEqual(hub.aliases[anchor], rp._evidence_url('assertion', stable_id))
            self.assertEqual(all_records[anchor].get('data-record-scope'), 'bookmark')
            self.assertNotIn('data-status', all_records[anchor])
        # An ID and one native link replace each former full record in the hub.
        # The fixed shell/entity register stays bounded independently of receipts.
        self.assertLess(hub.nodes, len(hub.aliases) + 2500)

    def test_old_correction_identifier_has_only_metadata_in_its_canonical_part(self):
        replacement = approved_new_org(self.context)
        # The explicit synthetic approval receipts are issued at graph as_of.
        correction = self.correction(claim_id='fixture.removed-claim',
            corrected_on=self.context['graph']['as_of'], replacement_claim_id=replacement['id'])
        self.context['corrections'] = [correction]
        self.build()
        target = rp._evidence_url('assertion', correction['claim_id'])
        self.assertEqual(Facts(self.page('/research/data/')).aliases['assertion-fixture.removed-claim'], target)
        self.assertIn('retained as correction metadata', self.page(urlsplit(target).path))
        self.assertIn('Read the approved replacement', self.page(urlsplit(target).path))

    def test_correction_payload_preserves_the_exact_record_url_and_visible_identifier(self):
        stable_id = 'fixture.target+version'
        path = rp._evidence_url('assertion', stable_id)
        title = 'τ² API + Tools & Data'
        disclosure = rp._record_correction(self.context, stable_id, path, title)
        contact, issue = (urlsplit(url) for url in Facts(disclosure).links)
        edition = self.context['report']['release_id']
        permalink = rp.sp.ORIGIN + path
        self.assertEqual((contact.netloc, contact.path, contact.fragment), ('', '/method/', 'corrections'))
        self.assertEqual(parse_qs(contact.query), {'correction': [stable_id], 'edition': [edition],
                                                'record': [path], 'title': [title]})
        self.assertEqual(parse_qs(issue.query), {'template': ['correction.yml'],
                                                'target': [' · '.join((edition, stable_id, permalink, title))]})
        tree = ReaderTree(disclosure)
        self.assertNotIn('open', tree.with_class('r-record-correction')[0]['attrs'])
        subject = next(item for item in tree.elements if item['tag'] == 'input')
        message = next(item for item in tree.elements if item['tag'] == 'textarea')
        self.assertIn('readonly', subject['attrs'])
        self.assertIn('readonly', message['attrs'])
        self.assertEqual(subject['attrs']['value'], 'ScienceToStartup correction · ' + stable_id)
        self.assertEqual(ReaderTree.text(message).splitlines()[:4],
                         ['Edition: ' + edition, 'Stable record ID: ' + stable_id,
                          'Record URL: ' + permalink, 'Record: ' + title])
        self.assertNotIn(rp.sp.CORRECTION_EMAIL, disclosure)
        self.assertIn('/method/#corrections', Facts(rp._review(self.context)).links)
        self.assertNotIn(rp.sp.CORRECTION_EMAIL, rp._review(self.context))

    def test_ledger_destination_is_stable_after_unrelated_records_are_added(self):
        vectors = ['claim.alpha', 'source.example/α:version1', 'entity.unchanged']
        before = {(kind, value): rp._evidence_url(kind, value) for kind in ('assertion', 'source', 'entity') for value in vectors}
        self.context['graph']['sources'].append({**self.context['graph']['sources'][0], 'id': 'fixture.unrelated-source'})
        self.build()
        self.assertEqual(before, {(kind, value): rp._evidence_url(kind, value) for kind, value in before})
        self.assertEqual(rp._evidence_url('entity', 'entity.unchanged'), '/research/data/#entity-entity.unchanged')

    def test_live_ledger_routing_keeps_frozen_pdf_and_doi_context_exact(self):
        import research_citations as citations
        import research_offline
        from research_corrections import public_corrections
        projection = citations.public_projection(self.context)
        before = (citations.context_digest(self.context), citations.offline_html(self.context),
                  research_offline.offline_appendix(projection, corrections=public_corrections(self.context)),
                  citations.citation_formats(citations.publication_metadata(self.context)))
        pdf = (Path(self.baseline['prepared_package']) / 'report.pdf'
               if self.baseline.get('published_edition_replay') else ROOT / 'data/research/report.pdf')
        pdf_digest = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.is_file() else None
        self.build()
        after = (citations.context_digest(self.context), citations.offline_html(self.context),
                 research_offline.offline_appendix(projection, corrections=public_corrections(self.context)),
                 citations.citation_formats(citations.publication_metadata(self.context)))
        self.assertEqual(before, after)
        if pdf_digest:
            self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), pdf_digest)

    def correction(self, **changes):
        return {'id': 'fixture.correction.1', 'edition_id': 'research.fixture.1',
                'claim_id': 'claim.fixture.1', 'summary': 'Synthetic correction <with markup> & qualification.',
                'status': 'accepted', 'corrected_on': '2026-11-09T09:30:00-08:00',
                'evidence_urls': ['https://example.org/evidence?version=1&part=2'], **changes}

    def test_actual_corrections_registry_and_feeds_preserve_all_accepted_repairs(self):
        import json
        if self.baseline.get('published_edition_replay'):
            corrections = self.baseline['corrections']
        else:
            registry = json.loads((ROOT / 'data/research/corrections.json').read_text())
            self.assertEqual(registry['schema_version'], '1.0.0')
            corrections = registry['corrections']
        self.assertGreaterEqual(len(corrections), 65)
        self.assertTrue(all(row['status'] == 'accepted' for row in corrections))
        self.context['corrections'] = corrections
        paths = {row['path'] for row in self.build()}
        self.assertIn(rp.CORRECTIONS_PATH, paths)
        self.assertNotIn('No accepted or published research corrections are recorded.', self.page(rp.CORRECTIONS_PATH))
        rss = ET.parse(self.output / 'research/corrections/feed.xml')
        atom = ET.parse(self.output / 'research/corrections/atom.xml')
        self.assertEqual(len(rss.findall('./channel/item')), len(corrections))
        self.assertEqual(len(atom.findall('{http://www.w3.org/2005/Atom}entry')), len(corrections))
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
