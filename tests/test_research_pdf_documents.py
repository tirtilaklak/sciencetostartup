"""PDF document references preserve scoped evidence and exact versions."""
import copy
import importlib.util
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_pdf import bibliography_documents, render_report_pdf
from test_research_citations import context_fixture


def source(sid, version='v1', body='a' * 64):
    return {'id': sid, 'url': 'https://example.org/paper', 'version': version,
            'response_sha256': body, 'title': 'Synthetic pinned reference',
            'publisher': 'TEST ONLY', 'published_on': '2026-01-01', 'status': 'captured'}


class BibliographyTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_pdf_bibliography_excludes_draft_only_and_unreferenced_source_metadata(self):
        from pypdf import PdfReader
        context = context_fixture()
        statuses = {'approved': 'approved', 'historical': 'historical',
                    'candidate': 'candidate', 'rejected': 'rejected'}
        context['graph']['sources'] = [
            {**source(sid), 'url': 'https://example.org/' + sid, 'title': 'SYNTHETIC reference ' + sid}
            for sid in (*statuses, 'unreferenced')]
        context['graph']['assertions'] = [
            {'id': sid, 'status': status, 'evidence': [{'source_id': sid}]}
            for sid, status in statuses.items()]
        context['report']['sections'][0]['paragraphs'] = [
            {'kind': 'sourced_fact', 'text': 'SYNTHETIC approved observation.', 'claim_ids': ['approved']}]
        before = copy.deepcopy(context)
        blob = render_report_pdf(context)
        self.assertEqual(blob, render_report_pdf(context))
        self.assertEqual(context, before)
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(blob)).pages)
        for sid in ('approved', 'historical'):
            self.assertIn('SYNTHETIC reference ' + sid, text)
        for sid in ('candidate', 'rejected', 'unreferenced'):
            self.assertNotIn('SYNTHETIC reference ' + sid, text)
            self.assertNotIn('https://example.org/' + sid, text)

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_completed_prepublication_pdf_keeps_reservation_status_without_incomplete_research_warning(self):
        from pypdf import PdfReader
        context = context_fixture()
        context['gate'].update(archival_ready=True, reasons=[])
        context['report']['archive'] = {'status': 'reserved', 'reserved_doi': '10.5281/zenodo.1234567'}
        before = copy.deepcopy(context)
        text = ' '.join(' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(render_report_pdf(context))).pages).split())
        self.assertEqual(context, before)
        self.assertIn('READY-FOR-ARCHIVE', text)
        self.assertIn('Complete research package frozen before archival publication.', text)
        self.assertIn('Reserved version DOI (not registered): 10.5281/zenodo.1234567.', text)
        self.assertNotIn('The comprehensive weekly series is in preparation.', text)
        self.assertNotIn('PUBLISHED |', text)
        incomplete = context_fixture()
        incomplete_text = ' '.join(' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(render_report_pdf(incomplete))).pages).split())
        self.assertIn('The comprehensive weekly series is in preparation.', incomplete_text)

    def test_repeated_scopes_share_one_reference_and_keep_both_source_ids(self):
        sources = {'b': source('b'), 'a': source('a')}
        before = copy.deepcopy(sources)
        docs, numbers = bibliography_documents(sources)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['source_ids'], ['a', 'b'])
        self.assertEqual(numbers, {'a': 1, 'b': 1})
        self.assertEqual((docs, numbers), bibliography_documents(dict(reversed(list(sources.items())))))
        self.assertEqual(sources, before)

    def test_changed_url_version_or_bytes_never_merge(self):
        sources = {'a': source('a'), 'b': source('b', version='v2'), 'c': source('c', body='b' * 64),
                   'd': {**source('d'), 'url': 'https://example.org/accepted-copy'}}
        docs, numbers = bibliography_documents(sources)
        self.assertEqual(len(docs), 4)
        self.assertEqual(len(set(numbers.values())), 4)

    def test_failed_captures_are_not_collapsed_as_identical_document_bytes(self):
        docs, numbers = bibliography_documents({'a': source('a', body=None), 'b': source('b', body=None)})
        self.assertEqual(len(docs), 2)
        self.assertNotEqual(numbers['a'], numbers['b'])

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_pdf_maps_both_paragraphs_to_document_and_prints_distinct_version_pins(self):
        from pypdf import PdfReader
        context = context_fixture()
        context['graph']['sources'] = [source('a'), source('b'), source('c', version='v2', body='b' * 64)]
        context['graph']['assertions'] = [
            {'id': sid, 'status': 'approved', 'evidence': [{'source_id': sid}]} for sid in ('a', 'b', 'c')]
        context['report']['sections'][0]['paragraphs'] = [
            {'kind': 'sourced_fact', 'text': 'SYNTHETIC bounded observation ' + sid, 'claim_ids': [sid]}
            for sid in ('a', 'b', 'c')]
        blob = render_report_pdf(context)
        self.assertEqual(blob, render_report_pdf(context))
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(blob)).pages)
        self.assertEqual(text.count('Sources: [1]'), 2)
        self.assertEqual(text.count('Sources: [2]'), 1)
        self.assertEqual(text.count('Synthetic pinned reference'), 2)
        self.assertIn('a' * 64, text)
        self.assertIn('b' * 64, text)
        self.assertIn('Scoped evidence bindings: 2', text)

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF preparation dependencies')
    def test_contents_links_and_bookmarks_resolve_to_the_printed_chapter_pages(self):
        from pypdf import PdfReader
        context = context_fixture()
        context['report']['sections'] = [
            {'id': 'stable-scope', 'title': 'Scope & limits', 'paragraphs': [
                {'kind': 'research_gap', 'text': 'SYNTHETIC scope paragraph. ' * 350, 'claim_ids': []}]},
            {'id': 'stable-method', 'title': 'Reproduction <details>', 'paragraphs': [
                {'kind': 'method', 'text': 'SYNTHETIC method paragraph.', 'claim_ids': []}]}]
        before = copy.deepcopy(context)
        blob = render_report_pdf(context)
        self.assertEqual(blob, render_report_pdf(context))
        self.assertEqual(context, before)
        reader = PdfReader(io.BytesIO(blob))
        destinations = {item['/Title']: item for item in reader.outline if isinstance(item, dict)}
        titles = ['Scope & limits', 'Reproduction <details>', 'Bibliography and source versions', 'Evidence and reproduction']
        self.assertEqual(list(destinations), titles)
        contents_page = reader.pages[1]
        contents_text = contents_page.extract_text()
        for title in titles:
            destination = destinations[title]
            page_index = reader.get_destination_page_number(destination)
            self.assertGreater(page_index, 1)
            self.assertIn(title, reader.pages[page_index].extract_text())
            self.assertIn(title, contents_text)
            self.assertIn(str(page_index + 1), contents_text)
        links = [item.get_object() for item in contents_page['/Annots']]
        self.assertTrue(all(link['/Subtype'] == '/Link' and '/Dest' in link for link in links))
        target_pages = {link['/Dest'][0].idnum for link in links}
        self.assertEqual(target_pages, {reader.pages[reader.get_destination_page_number(destinations[title])].indirect_reference.idnum
                                       for title in titles})


if __name__ == '__main__':
    unittest.main()
