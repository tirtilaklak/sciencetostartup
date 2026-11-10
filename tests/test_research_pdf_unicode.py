"""TEST-ONLY Unicode samples verify optional PDF fonts and V3 ownership."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import research_pdf as pdf
from publication_fixtures import populate_owned_inputs
from test_research_citations import context_fixture


class FontInputTests(unittest.TestCase):
    def test_pinned_font_and_unmodified_license_hashes(self):
        assets = pdf.pdf_font_assets(context_fixture())
        expected = {'DejaVuSans.ttf': '7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954',
                    'DejaVuSans-Bold.ttf': 'e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724',
                    'DejaVu-LICENSE.txt': '7a083b136e64d064794c3419751e5c7dd10d2f64c108fe5ba161eae5e5958a93',
                    'ScienceToStartupCJKSubset.ttf': '37f8f1a6db368902ee4a7f09cbb2ad7c9dd4c8ab61763ec6de431450f0811b16',
                    'CJK-OFL.txt': '1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9'}
        for name, digest in expected.items():
            self.assertEqual(citations.sha256(assets[name]), digest)
        self.assertEqual(len(citations.REPRODUCTION_INPUTS_V2), 10)
        self.assertTrue(set(assets).isdisjoint(citations.REPRODUCTION_INPUTS_V2))
        self.assertEqual(citations.STATIC_ASSET_LIMIT_BYTES, 25 * 1024 * 1024)

    def test_context_root_pins_each_asset_without_changing_v2_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = {**context_fixture(), 'root': temporary}
            populate_owned_inputs(temporary)
            current = citations.context_digest(context)
            legacy = citations.context_digest(context, version=2)
            for name in pdf.pdf_font_assets(context):
                path = Path(temporary) / citations.REPRODUCTION_INPUTS[name]
                original = path.read_bytes()
                path.write_bytes(original + b'\nTEST-ONLY mutation')
                self.assertNotEqual(citations.context_digest(context), current)
                self.assertEqual(citations.context_digest(context, version=2), legacy)
                if name not in {'DejaVu-PROVENANCE.json', 'CJK-PROVENANCE.json'}:
                    with self.assertRaisesRegex(ValueError, 'provenance hash'):
                        pdf.pdf_font_assets(context)
                path.write_bytes(original)
            font = Path(temporary) / citations.REPRODUCTION_INPUTS['DejaVuSans.ttf']
            font.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing'):
                pdf.pdf_font_assets(context)
            font.symlink_to(ROOT / citations.REPRODUCTION_INPUTS['DejaVuSans.ttf'])
            with self.assertRaisesRegex(ValueError, 'symlink'):
                pdf.pdf_font_assets(context)


@unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf'), 'Optional PDF dependencies')
class UnicodeRenderingTests(unittest.TestCase):
    def test_exact_letters_survive_regular_bold_source_bibliography_and_repeat_render(self):
        from pypdf import PdfReader
        context = context_fixture()
        sample = 'Ψ κ τ и к → 登录'
        context['report']['title'] = 'TEST ONLY ' + sample
        context['report']['sections'][0]['paragraphs'][0]['text'] = 'TEST ONLY ' + sample
        context['graph']['sources'] = [{'id': 'test-only', 'title': 'TEST ONLY bibliography ' + sample}]
        original = copy.deepcopy(context)
        with tempfile.TemporaryDirectory() as temporary:
            context['root'] = temporary
            populate_owned_inputs(temporary)
            with patch('urllib.request.urlopen', side_effect=AssertionError('No downloads')), \
                    patch('pathlib.Path.home', side_effect=AssertionError('No host font search')):
                first = pdf.render_report_pdf(context)
                self.assertEqual(first, pdf.render_report_pdf(context))
            text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(first)).pages)
            self.assertEqual(text.count(sample), 3)
            self.assertIn('DejaVu-LICENSE.txt', text)
            self.assertEqual(context['report'], original['report'])
            self.assertEqual(context['graph'], original['graph'])
            context['graph']['sources'] = []  # Receipt binding uses a schema-valid empty synthetic graph.
            receipt = pdf.prepare_report_pdf(context, Path(temporary) / 'prepared')
            self.assertIn('DejaVu Sans 2.37', receipt['renderer'])
            for name, metadata in receipt['font_assets'].items():
                self.assertEqual(metadata['sha256'], citations.sha256(pdf.pdf_font_assets(context)[name]))

    def test_unsupported_actual_character_fails_instead_of_missing_glyph_box(self):
        context = context_fixture()
        context['report']['sections'][0]['paragraphs'][0]['text'] = 'TEST ONLY \U00020000'
        with self.assertRaisesRegex(ValueError, 'Unsupported PDF glyphs.*U\\+20000'):
            pdf.render_report_pdf(context)

    def test_both_fonts_cover_all_report_and_bibliography_strings(self):
        from reportlab.pdfbase.ttfonts import TTFont
        from research_report import build_context
        context = build_context(ROOT, select_prepared=False)
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
        documents, _ = pdf.bibliography_documents({source['id']: source for source in context['graph']['sources']})
        bibliography = [{key: group['source'].get(key, '') for key in ('title', 'publisher', 'version', 'published_on', 'url', 'response_sha256', 'status')}
                        for group in documents]
        characters = {ord(char) for value in strings([context['report'], bibliography])
                      for char in pdf.normalized_pdf_text(value) if not char.isspace()}
        fallback = TTFont('TEST-CJK', io.BytesIO(pdf.pdf_font_assets(context)[pdf.PDF_CJK_FONT]))
        for name in pdf.PDF_FONT_FILES:
            font = TTFont('TEST-' + name, io.BytesIO(pdf.pdf_font_assets(context)[name]))
            missing = sorted(code for code in characters
                             if not (font.face.charToGlyph.get(code) or fallback.face.charToGlyph.get(code)))
            self.assertEqual(missing, [], name)


if __name__ == '__main__':
    unittest.main()
