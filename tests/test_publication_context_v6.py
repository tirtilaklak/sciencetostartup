"""Encoding migration and frozen replay controls; every generated input is synthetic."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
from test_publication_context import prepare_fixture, legacy_fixture


class CompactContextTests(unittest.TestCase):
    def test_compact_context_preserves_all_values_and_binds_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            before = copy.deepcopy(context)
            source = citations.source_context(context)
            blob = (package / 'source-context.json').read_bytes()
            self.assertEqual(json.loads(blob), source)
            self.assertEqual(blob, citations.source_context_bytes(context))
            self.assertLess(len(blob), len(citations.json_bytes(source)))
            self.assertEqual(blob.count(b'\n'), 1)
            self.assertTrue(blob.endswith(b'\n'))
            receipt = json.loads((package / 'PREPARED.json').read_bytes())
            self.assertEqual(receipt['context_contract_version'], 6)
            self.assertEqual(receipt['context_sha256'], citations.sha256(blob))
            self.assertEqual(receipt['context_sha256'], citations.context_digest(context))
            self.assertEqual(context, before)
            self.assertEqual(citations.read_prepared_package(context, package)['source-context.json'], blob)

    def test_encoding_does_not_change_unicode_empty_values_or_research_numbers(self):
        value = {'z': ['τ', 'line1\nline2', '', {}, [], None, False, 0, 0.125], 'a': '引用'}
        compact = citations._context_json_bytes(value, 6)
        self.assertEqual(json.loads(compact), value)
        self.assertEqual(compact, citations._context_json_bytes(dict(reversed(list(value.items()))), 6))
        for version in range(1, 6):
            self.assertEqual(citations._context_json_bytes(value, version), citations.json_bytes(value))
        for version in (0, 7, True, '6'):
            with self.assertRaises(ValueError):
                citations._context_json_bytes(value, version)
        with self.assertRaises(ValueError):
            citations._context_json_bytes({'invalid': float('nan')}, 6)

    def test_v5_frozen_bytes_replay_without_compaction_or_weaker_input_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, package = prepare_fixture(Path(temporary))
            legacy_fixture(context, package, version=5)
            before = {p.name: p.read_bytes() for p in package.iterdir()}
            self.assertGreater(before['source-context.json'].count(b'\n'), 1)
            frozen = citations.read_prepared_package(context, package)
            self.assertEqual(frozen['source-context.json'], before['source-context.json'])
            self.assertEqual(before, {p.name: p.read_bytes() for p in package.iterdir()})
            with self.assertRaisesRegex(ValueError, 'Fresh source contexts'):
                citations.source_context(context, version=5)
            owned = Path(context['root']) / 'scripts/reproduce_research_package.py'
            owned.write_bytes(owned.read_bytes() + b'\n# SYNTHETIC changed recipe\n')
            with self.assertRaisesRegex(ValueError, 'current research inputs'):
                citations.read_prepared_package(context, package)
            self.assertEqual(before, {p.name: p.read_bytes() for p in package.iterdir()})


if __name__ == '__main__':
    unittest.main()
