"""Quarantined report evidence must not reappear through offline formats."""
import copy
import importlib.util
import io
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_citations as citations
import research_pages as pages
from test_research_citations import context_fixture


def fixture(status='candidate'):
    context = context_fixture()
    context['graph']['assertions'] = [{'id': 'synthetic-held-claim', 'status': status, 'evidence': []}]
    paragraph = {'kind': 'sourced_fact', 'text': 'FORBIDDEN-QUARANTINED-FIXTURE', 'claim_ids': ['synthetic-held-claim']}
    context['report']['sections'] = [{'id': 'scope', 'title': 'Synthetic test only', 'paragraphs': [paragraph]}]
    return context, paragraph


class PublicBlockTests(unittest.TestCase):
    def test_held_or_missing_bindings_do_not_leak_through_site_markdown_or_html(self):
        for status in ('candidate', 'rejected', 'historical', 'missing'):
            context, paragraph = fixture(status)
            if status == 'missing':
                context['graph']['assertions'] = []
            before = copy.deepcopy(context)
            for kind in ('sourced_fact', 'analysis'):
                paragraph['kind'] = kind
                values = (pages._paragraph(context, paragraph), citations.report_markdown(context),
                          citations.offline_html(context).decode())
                for value in values:
                    self.assertNotIn('FORBIDDEN-QUARANTINED-FIXTURE', value)
                    self.assertNotIn('evidence.html#assertion-synthetic-held-claim', value)
                    self.assertIn('withheld because its evidence', value)
            paragraph['kind'] = before['report']['sections'][0]['paragraphs'][0]['kind']
            self.assertEqual(context, before)

    def test_explicit_historical_example_and_approved_fact_remain_readable(self):
        for status in ('approved', 'historical'):
            context, paragraph = fixture(status)
            paragraph.update(text='SYNTHETIC-SUPPORTED-FIXTURE', historical=status == 'historical')
            for value in (pages._paragraph(context, paragraph), citations.report_markdown(context), citations.offline_html(context).decode()):
                self.assertIn('SYNTHETIC-SUPPORTED-FIXTURE', value)

    def test_current_source_descriptor_withholds_drafts_but_commits_to_author_input(self):
        from test_research_graph import fixture as graph_fixture
        context = context_fixture()
        context['graph'] = graph_fixture()
        held = copy.deepcopy(context['graph']['assertions'][0])
        held.update(id='held', status='candidate', review_ids=[], value={'type': 'text', 'value': 'SECRET-HELD-FIXTURE'})
        context['graph']['assertions'].append(held)
        context['graph']['entities'][0]['assertion_ids'].append('held')
        context['gate']['report_review_ready'] = False
        context['report']['sections'][0]['paragraphs'] = [
            {'kind': 'sourced_fact', 'text': 'SECRET-HELD-FIXTURE', 'claim_ids': ['held']}]
        context['report']['executive_findings'] = [{'id': 'test-only', 'text': 'SECRET-SYNTHESIS-FIXTURE',
            'buyer_implication': 'Test only', 'limitations': 'Test only', 'claim_ids': ['claim']}]
        before = copy.deepcopy(context)
        source = citations.source_context(context)
        self.assertNotIn(b'SECRET-', citations.json_bytes(source))
        self.assertEqual(source['publication_withholds'], {'paragraphs': 1, 'executive_findings': 1})
        self.assertEqual(context, before)
        digest = citations.context_digest(context)
        context['report']['sections'][0]['paragraphs'][0]['text'] += ' edited'
        self.assertNotEqual(citations.context_digest(context), digest)

    def test_methods_hold_survives_every_package_file_and_zip_member(self):
        from test_research_graph import fixture as graph_fixture
        context = context_fixture()
        context['graph'] = graph_fixture()
        held = copy.deepcopy(context['graph']['assertions'][0])
        held.update(id='held', status='candidate', review_ids=[])
        context['graph']['assertions'].append(held)
        context['graph']['entities'][0]['assertion_ids'].append('held')
        marker = b'SECRET-METHOD-SENTINEL-TEST-ONLY'
        context['report']['title'] = 'Synthetic private-title@example.org sk-proj-ABCDEFGHIJKLMNOPQRSTUV'
        context['report']['sections'] = [{'id': 'methods-and-appendices', 'title': 'Test-only methods', 'paragraphs': [
            {'kind': 'sourced_fact', 'text': marker.decode(), 'claim_ids': ['held']},
            {'kind': 'method', 'text': 'SYNTHETIC allowed method description.', 'claim_ids': []}]}]
        projection = citations.public_projection(context, {'dataset_version': '2.5.0', 'companies': []})
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(citations, 'public_projection', return_value=projection), patch.object(citations, 'verified_pdf', return_value=None):
                citations.write_publication_assets(context, temporary, archive_compression='deflate')
            package = Path(temporary) / 'publication'
            for path in package.iterdir():
                if path.suffix != '.zip':
                    self.assertNotIn(marker, path.read_bytes(), path.name)
                    self.assertNotIn(b'private-title@example.org', path.read_bytes(), path.name)
                    self.assertNotIn(b'sk-proj-ABCDEFGHIJKLMNOPQRSTUV', path.read_bytes(), path.name)
            with zipfile.ZipFile(package / 'research-archive.zip') as archive:
                for name in archive.namelist():
                    self.assertNotIn(marker, archive.read(name), name)
                    self.assertNotIn(b'private-title@example.org', archive.read(name), name)
                    self.assertNotIn(b'sk-proj-ABCDEFGHIJKLMNOPQRSTUV', archive.read(name), name)
            self.assertIn('SYNTHETIC allowed method', (package / 'METHODS.md').read_text())
            self.assertIn('withheld because its evidence', (package / 'METHODS.md').read_text())

    def test_offline_chapter_navigation_keeps_id_when_heading_changes(self):
        from html.parser import HTMLParser
        class Targets(HTMLParser):
            def __init__(self, markup):
                super().__init__(); self.ids = []; self.links = []; self.feed(markup)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'id' in attrs: self.ids.append(attrs['id'])
                if tag == 'a': self.links.append(attrs.get('href'))
        context, _ = fixture('approved')
        for title in ('First heading', 'Changed <scope> & heading'):
            context['report']['sections'][0]['title'] = title
            markup = citations.offline_html(context).decode()
            targets = Targets(markup)
            self.assertIn('chapter-scope', targets.ids)
            self.assertIn('#chapter-scope', targets.links)
            self.assertEqual(len(targets.ids), len(set(targets.ids)))
            self.assertIn('Report chapters', markup)

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_pdf_withholds_same_quarantined_paragraph_and_citation(self):
        from research_pdf import render_report_pdf
        from pypdf import PdfReader
        context, _ = fixture()
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(render_report_pdf(context))).pages)
        self.assertNotIn('FORBIDDEN-QUARANTINED-FIXTURE', text)
        self.assertIn('withheld because its evidence', text)


if __name__ == '__main__':
    unittest.main()
