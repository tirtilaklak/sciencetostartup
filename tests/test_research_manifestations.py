"""Deterministic extraction controls only; these do not approve research."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_manifestations import extract, lf_lines, main, sha256


class ManifestationTests(unittest.TestCase):
    def test_raw_preserves_bom_cr_formfeed_unicode_and_terminal_empty_line(self):
        raw = '\ufeffOne\r\n二\f\n'.encode()
        self.assertEqual(extract(raw, 'raw_utf8_lf', source_sha256=sha256(raw)), raw)
        self.assertEqual(lf_lines(raw, 1, 3), ['\ufeffOne\r', '二\f', ''])

    def test_html_recipe_decodes_entities_and_ignores_declared_elements(self):
        raw = b'<p> A &amp; B </p><script>bad<style>worse</style>bad</script><noscript>bad</noscript><span hidden>retained</span>'
        expected = b'A & B\nretained\n'
        self.assertEqual(extract(raw, 'html_textnodes_v1', source_sha256=sha256(raw),
                                 expected_sha256=sha256(expected)), expected)

    def test_wrong_response_or_manifestation_never_retargets_locator(self):
        for kwargs in ({'source_sha256': 'a' * 64},
                       {'source_sha256': sha256(b'ok'), 'expected_sha256': 'b' * 64}):
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                extract(b'ok', 'raw_utf8_lf', **kwargs)
        with self.assertRaises(UnicodeDecodeError):
            extract(b'\xff', 'raw_utf8_lf', source_sha256=sha256(b'\xff'))

    def test_ranges_cannot_silently_truncate_or_use_splitlines(self):
        self.assertEqual(lf_lines(b'a\fb\rc\n', 1, 2), ['a\fb\rc', ''])
        for start, end in ((0, 1), (2, 1), (1, 3), (True, 1)):
            with self.assertRaises(ValueError):
                lf_lines(b'a\n', start, end)

    def test_pdf_uses_exact_page_arguments_version_and_stdout(self):
        raw, result = b'%PDF-fixture', b'  table\n\f'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'body.pdf'
            path.write_bytes(raw)
            with patch('research_manifestations.subprocess.run') as run:
                run.side_effect = [subprocess.CompletedProcess([], 0, b'', b'pdftotext version fixture\n'),
                                   subprocess.CompletedProcess([], 0, result, b'')]
                actual = extract(raw, 'pdf_physical_page_layout', source_sha256=sha256(raw),
                                 physical_page=2, pdf_path=path, tool_version='pdftotext version fixture',
                                 expected_sha256=sha256(result))
                self.assertEqual(actual, result)
                self.assertEqual(run.call_args_list[1].args[0], ['pdftotext', '-f', '2', '-l', '2', '-layout', '-enc', 'UTF-8', str(path), '-'])
            with patch('research_manifestations.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'', b'wrong version\n')):
                with self.assertRaisesRegex(ValueError, 'version differs'):
                    extract(raw, 'pdf_physical_page_layout', source_sha256=sha256(raw),
                            physical_page=1, pdf_path=path, tool_version='required version')

    def test_cli_verifies_before_writing_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'source.txt', Path(temporary) / 'out.txt'
            source.write_bytes(b'ok\n')
            args = [str(source), '--source-sha256', sha256(source.read_bytes()), '--recipe', 'raw_utf8_lf',
                    '--expected-sha256', sha256(source.read_bytes()), '--output', str(output)]
            main(args)
            main(args)
            output.write_bytes(b'prior evidence')
            with self.assertRaisesRegex(ValueError, 'different bytes'):
                main(args)
            self.assertEqual(output.read_bytes(), b'prior evidence')
