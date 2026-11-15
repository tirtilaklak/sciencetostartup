"""Synthetic privacy/version regressions; no actual scientific admission or archive."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_citations as citations
import research_graph as graph
import research_pages as pages
from test_research_graph import fixture


def mixed_context():
    g = fixture()
    draft = copy.deepcopy(g['assertions'][0])
    draft.update(id='draft', status='candidate', review_ids=[])
    draft['evidence'][0]['source_id'] = 'draft-source'
    source = copy.deepcopy(g['sources'][0])
    source.update(id='draft-source', title='SYNTHETIC-PRIVATE-DRAFT-TITLE',
                  version='SYNTHETIC-PRIVATE-DRAFT-VERSION')
    g['assertions'].append(draft)
    g['sources'].append(source)
    g['entities'][0]['assertion_ids'].append('draft')
    for review in g['reviews']:
        review['source_ids'].append('draft-source')
        review['note'] = 'SYNTHETIC-PRIVATE-DRAFT-VERSION and locator that must remain private.'
    return {'graph': g, 'report': {'release_id': 'test-only', 'updated_on': '2026-11-09',
            'sections': [], 'archive': {}, 'status': 'prelaunch'},
            'gate': {'reasons': [], 'archive_reasons': []}, 'identity': {},
            'policy': {}, 'roles': {}, 'corrections': []}


class ProjectionContractTests(unittest.TestCase):
    def test_default_projection_withholds_grouped_draft_note_and_detail_title(self):
        context = mixed_context()
        original = copy.deepcopy(context)
        projected = graph.public_graph(context['graph'])
        self.assertNotIn('SYNTHETIC-PRIVATE-DRAFT', graph.stable_json(projected))
        self.assertTrue(all(row['note'].startswith('Public projection notice:')
                            for row in projected['reviews']))
        detail = pages._detail(context, context['graph']['entities'][0])
        self.assertNotIn('SYNTHETIC-PRIVATE-DRAFT', detail)
        self.assertIn('Source metadata withheld', detail)
        self.assertIn(pages._evidence_url('source', 'draft-source'), detail)
        self.assertEqual(context, original)

    def test_legacy_projection_is_replay_only_and_retains_its_original_semantics(self):
        context = mixed_context()
        for review in context['graph']['reviews']:
            review['note'] += ' /Users/synthetic/ledger.json'
        old10 = graph._public_graph_for_version(context['graph'], '1.0.0')
        old11 = graph._public_graph_for_version(context['graph'], '1.1.0')
        self.assertEqual(len(old10['sources']), 2)
        self.assertEqual(len(old11['sources']), 2)
        self.assertIn('/Users/synthetic/', old10['reviews'][0]['note'])
        self.assertNotIn('/Users/synthetic/', old11['reviews'][0]['note'])
        self.assertEqual(len(graph.public_graph(context['graph'])['sources']), 1)
        for version in (1, 2, 3, 4, 5):
            with self.assertRaisesRegex(ValueError, 'Fresh source contexts'):
                citations.source_context(context, version=version)

    def test_current_context_binds_projection_version_and_preserves_old_allowlist(self):
        context = mixed_context()
        owned = {name: b'SYNTHETIC OWNED INPUT' for name in citations.REPRODUCTION_INPUTS}
        with patch.object(citations, 'reproduction_files', return_value=owned):
            source = citations.source_context(context)
        recipe = source['package_context']
        self.assertEqual(recipe['context_contract_version'], 6)
        self.assertEqual(recipe['graph_projection'], 'approved-historical-report-v2')
        self.assertEqual(recipe['graph_projection_version'], '1.2.0')
        self.assertNotIn('screening_audit_v3.py', citations._reproduction_inputs(4))
        self.assertIn('screening_audit_v3.py', citations._reproduction_inputs(5))

    def test_actual_frozen_10_recipe_is_parsed_without_executing_python(self):
        folder = ROOT / 'data/research/releases/research-2026-11-10.prelaunch.1/publication'
        code = (folder / 'research_graph.py').read_bytes()
        schema = (folder / 'publication-projection.schema.json').read_bytes()
        self.assertEqual(hashlib.sha256(code).hexdigest(),
                         '9399750493566ab2340d2d3ad45a556cb679f0b608a57d7450f2da8c59a247c4')
        self.assertEqual(citations._frozen_graph_projection_version(
            {'research_graph.py': code, 'publication-projection.schema.json': schema}), '1.0.0')
        synthetic = {'research_graph.py': b'PUBLIC_PROJECTION_VERSION = "1.1.0"\n',
                     'publication-projection.schema.json': schema}
        self.assertEqual(citations._frozen_graph_projection_version(synthetic), '1.1.0')
        synthetic['research_graph.py'] += b'PUBLIC_PROJECTION_VERSION = "1.2.0"\n'
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            citations._frozen_graph_projection_version(synthetic)


if __name__ == '__main__':
    unittest.main()
