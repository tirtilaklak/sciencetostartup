"""Execute the owned reuse examples on synthetic data, without network/research credit."""
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import test_huggingface_publication as hub_examples


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class ReuseExamplesTests(unittest.TestCase):
    def examples(self):
        return re.findall(r'```python\n(.*?)```', (ROOT / 'docs/research/reuse.md').read_text(), re.S)

    def test_json_and_readonly_sqlite_examples_use_actual_projection_schema(self):
        projection = hub_examples.PublicMirrorTests.reuse_fixture()
        with tempfile.TemporaryDirectory() as temporary, working_directory(temporary):
            citations.write_projection(projection, Path(temporary))
            before = hashlib.sha256(Path('clean-dataset.sqlite').read_bytes()).hexdigest()
            output = io.StringIO()
            with redirect_stdout(output):
                for code in self.examples():
                    exec(compile(code, '<SYNTHETIC reuse example>', 'exec'), {})
            self.assertIn('https://example.invalid/source SYNTHETIC-scope', output.getvalue())
            self.assertIn("('SYNTHETIC-predicate', 1)", output.getvalue())
            self.assertEqual(hashlib.sha256(Path('clean-dataset.sqlite').read_bytes()).hexdigest(), before)

    def test_sqlite_example_refuses_missing_archive_instead_of_creating_database(self):
        code = self.examples()[1]
        with tempfile.TemporaryDirectory() as temporary, working_directory(temporary):
            with self.assertRaises(sqlite3.OperationalError):
                exec(compile(code, '<SYNTHETIC missing archive example>', 'exec'), {})
            self.assertFalse(Path('clean-dataset.sqlite').exists())

    def test_v6_binds_examples_while_prior_contract_inputs_stay_frozen(self):
        self.assertEqual(citations._reproduction_inputs(6)['REUSE.md'], 'docs/research/reuse.md')
        for version in (2, 3, 4, 5):
            self.assertNotIn('REUSE.md', citations._reproduction_inputs(version))


if __name__ == '__main__':
    unittest.main()
