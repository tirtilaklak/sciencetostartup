"""Reader contracts use synthetic findings only; production findings stay empty."""
import copy
import html
import json
import importlib.util
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from research_report import build_context
from research_findings import executive_findings
import research_pages as pages
import research_citations as citations
from test_research_pages import Facts


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = build_context(ROOT)

    def setUp(self):
        self.context = copy.deepcopy(self.baseline)
        self.claim = next(row for row in self.context['graph']['assertions'] if row['status'] == 'approved')
        self.finding = {'id': 'assessment-1', 'text': 'Evidence <scope> & limits.',
                        'buyer_implication': 'Inspect the task.', 'limitations': ['Narrow evidence.', 'No quality audit.'],
                        'confidence': 'Limited', 'reasoning': 'Specific sources.', 'what_would_change': 'A new source.',
                        'claim_ids': [self.claim['id']]}
        self.context['report']['executive_findings'] = [self.finding]

    def test_finding_anchor_and_evidence_links_survive_heading_changes_and_archive(self):
        self.context['report']['sections'][0]['title'] = 'A changed chapter heading'
        report = pages._report(self.context)
        self.assertIn('finding-assessment-1', Facts(report).ids)
        self.assertIn('#finding-assessment-1', Facts(report).links)
        self.assertIn(pages._evidence_url('assertion', self.claim['id']), Facts(report).links)
        md, offline = citations.report_markdown(self.context), citations.offline_html(self.context).decode()
        self.assertIn('<a id="finding-assessment-1"></a>', md)
        self.assertIn('finding-assessment-1', Facts(offline).ids)
        self.assertIn('https://sciencetostartup.com' + pages._evidence_url('assertion', self.claim['id']), Facts(offline).links)
        for text in ('Evidence <scope> & limits.', 'Inspect the task.', 'Narrow evidence.; No quality audit.',
                     'Limited', 'Specific sources.', 'A new source.'):
            self.assertIn(html.escape(text), report)
            self.assertIn(html.escape(text, quote=False), re.sub(r'\\([\\`*_{}\[\]()#+.!>~|])', r'\1', md))
            self.assertIn(html.escape(text), offline)

    def test_bad_evidence_missing_fields_and_duplicate_ids_withhold_all_wording(self):
        for changes in ({'claim_ids': []}, {'claim_ids': ['missing']}, {'limitations': ''},
                        {'id': 'unsafe" id'}, {'claim_ids': [self.claim['id'], self.claim['id']]}):
            self.context['report']['executive_findings'] = [{**self.finding, **changes, 'text': 'FORBIDDEN'}]
            self.assertEqual(executive_findings(self.context)[0], [])
            self.assertNotIn('FORBIDDEN', pages._report(self.context))
            self.assertNotIn('FORBIDDEN', citations.report_markdown(self.context))
            self.assertNotIn('FORBIDDEN', citations.offline_html(self.context).decode())
        for status in ('candidate', 'historical'):
            self.claim['status'] = status
            self.context['report']['executive_findings'] = [self.finding]
            self.assertEqual(executive_findings(self.context)[0], [])
        self.claim['status'] = 'approved'
        self.context['report']['executive_findings'] = [self.finding, copy.deepcopy(self.finding)]
        self.assertEqual(executive_findings(self.context), ([], 2))
        self.assertNotIn('finding-assessment-1', Facts(pages._report(self.context)).ids)

    def test_untrusted_finding_text_is_escaped_in_site_and_archive(self):
        self.finding['buyer_implication'] = '<img src=x onerror=alert(1)>\n<a id="finding-forged"></a>'
        for text in (pages._report(self.context), citations.report_markdown(self.context), citations.offline_html(self.context).decode()):
            self.assertNotIn('<img src=x', text)
            self.assertNotIn('<a id="finding-forged">', text)

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_prepared_pdf_retains_same_supported_finding_and_readable_identifier(self):
        from research_pdf import render_report_pdf
        from pypdf import PdfReader
        blob = render_report_pdf(self.context)
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(blob)).pages)
        for value in ('assessment-1', 'Evidence <scope> & limits.', 'Inspect the task.', 'Narrow evidence.; No quality audit.',
                      'Limited', 'Specific sources.', 'A new source.', self.claim['id']):
            self.assertIn(value, text)
        self.finding.update(text='FORBIDDEN-PDF', claim_ids=['missing'])
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(render_report_pdf(self.context))).pages)
        self.assertNotIn('FORBIDDEN-PDF', text)

    def test_table_contains_native_records_and_only_metadata_for_enhancement(self):
        candidate = copy.deepcopy(self.claim)
        candidate.update(id='candidate.secret', status='candidate', value={'value': 'FORBIDDEN-CLAIM'})
        self.context['graph']['assertions'].append(candidate)
        paper = next(row for row in self.context['graph']['entities'] if row['kind'] == 'paper')
        paper['taxonomy']['delivery_model'] = ['managed']
        paper['taxonomy']['data_purpose'] = ['evaluation']
        text = pages._index(self.context, pages.CATEGORIES[0])
        self.assertIn('<table', text)
        self.assertIn('data-index-controls hidden', text)
        self.assertIn('name="delivery_model"', text)
        self.assertIn('name="data_purpose"', text)
        for facet in pages.INDEX_FACETS[:7]:
            self.assertIn('name="' + facet + '"', text)
        self.assertIn(pages.entity_url(paper, self.context), Facts(text).links)
        self.assertNotIn('FORBIDDEN-CLAIM', text)
        self.assertNotIn(self.claim.get('qualifications', [''])[0], text)

    def test_existing_company_supplement_preserves_history_identity_and_nested_dates(self):
        legacy = next(row for row in self.context['graph']['entities'] if row.get('legacy_id'))
        self.claim.update(subject_id=legacy['id'], qualifications=['A limited test scope.'])
        self.context['graph']['assertions'] = [self.claim]
        path = pages.entity_url(legacy, self.context)
        canonical = pages.sp.ORIGIN + path
        node = {'@id': canonical, '@type': 'WebPage', 'dateModified': '2025-01-01',
                'mainEntity': {'@id': canonical + '#organization', '@type': 'Organization', 'dateModified': '2020-01-01'}}
        original = ('<html><head><link rel="canonical" href="' + canonical + '">'
                    '<script type="application/ld+json">' + json.dumps(node) + '</script></head><body><main>'
                    '<p>Historical revenue: $10M (2021). Reviewed 2025-01-01.</p></main></body></html>')
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch)
            target = output / path.strip('/') / 'index.html'
            target.parent.mkdir(parents=True)
            target.write_text(original)
            records = pages.write_company_supplements(output, self.context)
            text = target.read_text()
            self.assertEqual(records, [{'path': path, 'lastmod': max(self.context['report']['updated_on'], pages._day(self.context['graph']['as_of']), pages._day(self.claim['as_of']))}])
            self.assertIn('Historical revenue: $10M (2021). Reviewed 2025-01-01.', text)
            self.assertEqual(Facts(text).canonicals, [canonical])
            self.assertIn('A limited test scope.', text)
            self.assertIn('Research evidence snapshot', text)
            structured = json.loads(re.search(r'<script[^>]*>(.*?)</script>', text).group(1))
            self.assertEqual(structured['mainEntity']['dateModified'], '2020-01-01')
            self.assertEqual(structured['dateModified'], records[0]['lastmod'])
            pages.write_company_supplements(output, self.context)
            self.assertEqual(target.read_text(), text)
            self.claim['subject_id'], self.claim['object_id'] = self.claim['object_id'], self.claim['subject_id']
            target.write_text(original)
            self.assertEqual(pages.write_company_supplements(output, self.context), records)
            self.assertIn('A limited test scope.', target.read_text())
            self.claim['status'] = 'candidate'
            target.write_text(original)
            self.assertEqual(pages.write_company_supplements(output, self.context), [])
            self.assertEqual(target.read_text(), original)


if __name__ == '__main__':
    unittest.main()
