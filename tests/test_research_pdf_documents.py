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


if __name__ == '__main__':
    unittest.main()
