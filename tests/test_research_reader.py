"""Reader contracts use synthetic findings, never synthetic research evidence."""
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
        self.assertIn(citations.evidence_href('assertion', self.claim['id']), Facts(offline).links)
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

    def test_finding_contacts_are_removed_before_markdown_escaping(self):
        self.finding.update(text='Contact privacy-fixture@example.org.',
                            buyer_implication='Contact private+buyer@example.org.')
        for value in (citations.report_markdown(self.context), citations.offline_html(self.context).decode()):
            self.assertNotIn('example.org', value)
            self.assertIn('contact removed', value)

    def test_finding_prose_cannot_be_mistaken_for_generated_evidence_links(self):
        self.finding['text'] = 'Approved evidence: this synthetic fixture remains limited to one task'
        offline = citations.offline_html(self.context).decode()
        self.assertIn(self.finding['text'], offline)
        self.assertIn(citations.evidence_href('assertion', self.claim['id']), Facts(offline).links)

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

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_prepared_pdf_removes_contacts_from_all_finding_fields(self):
        from research_pdf import render_report_pdf
        from pypdf import PdfReader
        for key in ('text', 'buyer_implication', 'limitations', 'confidence', 'reasoning', 'what_would_change'):
            self.finding[key] = 'Contact privacy-fixture@example.org.'
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(render_report_pdf(self.context))).pages)
        self.assertNotIn('privacy-fixture', text)
        self.assertIn('[contact removed]', text)

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

    def supplier_claim(self, subject, value):
        return {**copy.deepcopy(self.claim), 'id': 'fixture.' + subject, 'subject_id': 'org.' + subject,
                'predicate': 'documents', 'object_id': None, 'status': 'approved', 'evidence': [], 'review_ids': [],
                'qualifications': ['Synthetic fixture only; no segment revenue or independent operational audit is established.'],
                'value': {'type': 'text', 'value': json.dumps(value, ensure_ascii=False, separators=(',', ':'))}}

    def test_structured_financial_statement_keeps_period_currency_consolidated_scope_and_export_bytes(self):
        value = {'statement': 'Synthetic fixture: Appen reports FY2025 consolidated revenue of USD 123.456 million.',
                 'scope': {'claim_class': 'financial', 'company_entity_id': 'org.appen', 'scope_kind': 'financial',
                           'provenance_scope': 'First-party disclosure; execution not independently audited.'},
                 'reported_value_and_basis': {'type': 'metric', 'amount': 123456000, 'currency': 'USD',
                    'period_start': '2025-01-01', 'period_end': '2025-12-31', 'annualized': False,
                    'reported_or_estimated': 'reported_audited_financial_statements',
                    'scope': 'Appen Limited consolidated group', 'is_human_data_segment_revenue': False}}
        claim = self.supplier_claim('appen', value)
        before = copy.deepcopy(claim)
        text = pages._assertion(self.context, claim)
        self.assertIn('Appen</a> reports FY2025 consolidated revenue of USD 123.456 million.', text)
        self.assertIn('<summary>Scope and reported basis</summary>', text)
        for term, shown in (('Period start', '2025-01-01'), ('Period end', '2025-12-31'), ('Currency', 'USD'),
                            ('Reported or estimated', 'Reported in audited financial statements'),
                            ('Reported entity or segment scope', 'Appen Limited consolidated group'),
                            ('Isolated human-data segment revenue', 'No'), ('Annualized amount', 'No')):
            self.assertIn('<dt>' + term + '</dt><dd>' + shown + '</dd>', text)
        self.assertIn(claim['qualifications'][0], text)
        self.assertNotIn('claim_class', text)
        self.assertNotIn('company_entity_id', text)
        self.assertNotIn('&quot;type&quot;', text)
        self.assertEqual(claim, before)
        from research_graph import assertion_digest
        self.assertEqual(assertion_digest(claim), assertion_digest(before))
        projection = {'graph': {'assertions': [claim]}}
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch)
            citations.write_projection(projection, output)
            exported = json.loads((output / 'clean-dataset.json').read_text())
            self.assertEqual(exported['graph']['assertions'][0]['value']['value'], before['value']['value'])
            self.assertEqual(citations.projection_from_rows(citations.projection_rows(projection)), projection)

    def test_structured_prolific_activity_window_stays_unknown_and_waitlist_stays_separate(self):
        value = {'statement': 'Synthetic fixture: Prolific reports 12,000 active participants and a separate waitlist.',
                 'scope': {'claim_class': 'workforce_metric', 'company_entity_id': 'org.prolific'},
                 'reported_value_and_basis': {'type': 'metric', 'amount': 12000, 'active_window': None,
                    'reported_or_estimated': 'company_reported', 'qualifier': 'more_than',
                    'waitlist': {'amount': 34000, 'qualifier': 'over'}}}
        claim = self.supplier_claim('prolific', value)
        claim['qualifications'] = ['The source does not define the activity window. Waitlisted people are not active participants.']
        text = pages._assertion(self.context, claim)
        self.assertIn('<dt>Activity window</dt><dd>Not defined in the source</dd>', text)
        self.assertIn('<dt>Separate waitlist</dt>', text)
        self.assertIn('34,000', text)
        self.assertIn('<dt>Value qualifier</dt><dd>more than</dd>', text)
        self.assertIn(claim['qualifications'][0], text)
        self.assertNotIn('30 days', text)
        self.assertNotIn('46,000', text)
        claim['status'] = 'candidate'
        candidate = pages._assertion(self.context, claim)
        self.assertNotIn('12,000', candidate)
        self.assertNotIn('34,000', candidate)
        self.assertNotIn('Scope and reported basis', candidate)

    def test_unknown_currency_and_denominator_are_explicit_and_structured_text_is_escaped(self):
        claim = self.supplier_claim('prolific', {'statement': 'Synthetic fee <scope> & limits.',
            'scope': {'product': '<img src=x onerror=alert(1)>', 'modes': ['Participant access', 'Managed collection']},
            'reported_value_and_basis': {'currency': None, 'percentage_denominator': None,
                'denominator_status': 'not_explicit_in_bound_pricing_FAQ', 'qualifier': 'usually'}})
        text = pages._assertion(self.context, claim)
        for term in ('Currency', 'Percentage denominator'):
            self.assertIn('<dt>' + term + '</dt><dd>Not stated in the source</dd>', text)
        self.assertIn('Not explicit in the cited pricing FAQ', text)
        self.assertIn('<dt>Value qualifier</dt><dd>usually</dd>', text)
        self.assertIn('Synthetic fee &lt;scope&gt; &amp; limits.', text)
        self.assertIn('&lt;img', text)
        self.assertNotIn('<img', text)
        self.assertNotIn('percentage of rewards', text)

    def test_ordinary_text_and_unrecognized_json_keep_the_existing_rendering(self):
        for value in ('Ordinary text <scope> & limits.', '{bad json', '{"note":"No statement"}', '[1,2]'):
            claim = self.supplier_claim('appen', {})
            claim['value']['value'] = value
            expected = pages._link('/company/appen/', 'Appen') + ' · documents: ' + html.escape(value)
            self.assertEqual(pages._claim_text(self.context, claim), expected)
            self.assertEqual(pages._claim_scope(claim), '')


if __name__ == '__main__':
    unittest.main()
