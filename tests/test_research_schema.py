"""Delivered research must conform to its public structural contract."""
import json
from pathlib import Path
import re
import sys
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from research_graph import load_graph, public_graph
from research_citations import publication_metadata
from research_report import build_context


class ResearchSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / 'schema/research-graph.schema.json').read_text())
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_approved_source_and_public_graph_conform_without_rewriting_review_times(self):
        graph = load_graph(ROOT)
        for instance in (graph, public_graph(graph)):
            errors = list(self.validator.iter_errors(instance))
            self.assertEqual([(list(error.absolute_path), error.message) for error in errors], [])
        # The real source receipts retain their actual subsecond precision.
        self.assertTrue(any('.' in review['reviewed_on'] for review in graph['reviews']))

    def test_every_utc_timestamp_pattern_accepts_seconds_and_fractional_seconds(self):
        patterns = []
        def visit(node):
            if isinstance(node, dict):
                if 'pattern' in node and r'T\d{2}:\d{2}:\d{2}' in node['pattern']:
                    patterns.append(node['pattern'])
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(self.schema)
        self.assertEqual(len(patterns), 5)
        for pattern in patterns:
            for value in ('2026-11-10T05:28:56Z', '2026-11-10T05:28:56.759940Z'):
                self.assertIsNotNone(re.fullmatch(pattern, value))
            for value in ('2026-11-10', '2026-11-10T05:28:56', '2026-11-10T05:28:56+00:00'):
                self.assertIsNone(re.fullmatch(pattern, value))

    def test_actual_citation_metadata_matches_its_downloadable_schema(self):
        schema = json.loads((ROOT / 'schema/publication-metadata.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        metadata = publication_metadata(build_context(ROOT, select_prepared=False))
        Draft202012Validator(schema).validate(metadata)
        self.assertEqual(set(metadata['author_person']), {'given', 'family'})


if __name__ == '__main__':
    unittest.main()
