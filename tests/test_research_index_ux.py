"""Record identity, grouping and readable evidence boundaries (no network/build)."""
import copy
import json
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_pages as rp
import research_graph as rg
from research_report import build_context


class Tree(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    def __init__(self, text):
        super().__init__(); self.nodes = []; self.stack = []; self.feed(text)
    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'parents': tuple(self.stack)}
        self.nodes.append(node)
        if tag not in self.VOID: self.stack.append(node)
    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                self.stack = self.stack[:index]; break
    def having(self, attribute):
        return [node for node in self.nodes if attribute in node['attrs']]


def entity(identifier, kind, status='approved', parent=None):
    row = {'id': identifier, 'name': identifier, 'kind': kind, 'status': status,
           'review_depth': 'metadata_only', 'taxonomy': {'domain': ['coding']}, 'identifiers': {}}
    if parent: row['parent_id'] = parent
    return row


class ResearchIndexShapeTests(unittest.TestCase):
    def test_versions_are_once_in_sibling_native_disclosures(self):
        records = [entity('work', 'paper_work'), entity('version', 'paper_version', 'candidate', 'work'),
                   entity('orphan', 'paper_version', 'candidate', 'missing')]
        context = {'graph': {'entities': records, 'assertions': []}}
        text = rp._evidence_table(context, records, group_papers=True)
        tree = Tree(text)
        self.assertEqual(len(tree.having('data-index-row')), 3)
        for node in tree.having('data-index-row'):
            self.assertFalse(any('data-index-row' in parent['attrs'] for parent in node['parents']))
            self.assertEqual(node['tag'], 'tr')
            self.assertIsInstance(json.loads(node['attrs']['data-filters']), dict)
        wrapper = tree.having('data-index-versions')[0]
        self.assertNotIn('data-index-row', wrapper['attrs'])
        details = [node for node in tree.nodes if node['tag'] == 'details' and 'r-paper-versions' in node['attrs'].get('class', '')][0]
        self.assertNotIn('open', details['attrs'])
        self.assertEqual(details['parents'][-1]['tag'], 'td')
        self.assertEqual(details['parents'][-1]['attrs']['colspan'], '5')
        summary = [node for node in tree.nodes if node['tag'] == 'summary' and details in node['parents']][0]
        self.assertFalse(any('data-index-row' in parent['attrs'] for parent in summary['parents']))
        self.assertIn('Work context only; not counted as a match', text)
        self.assertIn('1 paper works · 2 source versions (3 records)', text)

    def test_only_populated_advanced_controls_and_primary_reset(self):
        record = entity('work', 'paper_work')
        text = rp._evidence_table({'graph': {'entities': [record], 'assertions': []}}, [record])
        tree = Tree(text)
        selects = {node['attrs']['name']: node for node in tree.nodes if node['tag'] == 'select'}
        self.assertEqual(set(selects), {'status', 'type', 'domain'})
        self.assertFalse(any(parent['tag'] == 'details' for parent in selects['status']['parents']))
        self.assertTrue(any(parent['tag'] == 'details' for parent in selects['type']['parents']))
        reset = next(node for node in tree.nodes if node['tag'] == 'button')
        self.assertFalse(any(parent['tag'] == 'details' for parent in reset['parents']))

    def test_full_title_and_footer_context_use_actual_render_snapshot(self):
        for release, as_of in [('research-current.1', '2026-11-12T17:50:15.040816Z'),
                               ('research-older.1', '2026-10-01T01:02:03Z')]:
            context = {'identity': {}, 'report': {'release_id': release},
                       'graph': {'as_of': as_of, 'canonical_dataset_version': '2.5.0'}}
            title = 'An exact source version with a long distinguishing title ' * 3
            with patch.object(rp, '_page_revision', return_value=None), patch.object(rp.sp, 'document', return_value='<head></head>') as document:
                rp._render(context, title, 'Description', '/research/papers/example/', '')
            snapshot = document.call_args.args[0]
            self.assertEqual(snapshot.research_release_context, {'release_id': release, 'evidence_as_of': as_of})
            self.assertEqual(snapshot.data['dataset_version'], '2.5.0')
            self.assertEqual(document.call_args.args[1], title.strip() + rp.sp.SUFFIX)

    def test_scoped_relationship_fallback_is_narrow_and_escaped(self):
        subject, obj = entity('subject', 'supplier'), entity('object', 'paper_work')
        context = {'graph': {'entities': [subject, obj], 'assertions': []}}
        claim = {'status': 'approved', 'subject_id': 'subject', 'object_id': 'object',
                 'predicate': 'generated', 'value': None, 'qualifications': ['Scoped source statement: Supplier says <careful> & qualified.']}
        self.assertEqual(rp._claim_text(context, claim), 'Supplier says &lt;careful&gt; &amp; qualified.')
        for changes in ({'status': 'candidate'}, {'object_id': None}, {'value': 'A structured value'},
                        {'qualifications': ['Scoped source statement: One.', 'Scoped source statement: Two.']},
                        {'qualifications': ['Scoped source statement:   ']}):
            modified = {**claim, **changes}
            self.assertNotEqual(rp._claim_text(context, modified), 'Supplier says &lt;careful&gt; &amp; qualified.')
        self.assertEqual(rp._claim_text(context, {**claim, 'status': 'historical'}), 'Supplier says &lt;careful&gt; &amp; qualified.')


class ActualResearchCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_context(ROOT)

    def test_all_456_records_and_separate_review_states_remain_initial_html(self):
        records = [row for row in self.context['graph']['entities'] if row['kind'] in {'paper', 'paper_work', 'paper_version'}]
        original = json.dumps(self.context['graph'], sort_keys=True)
        text = rp._evidence_table(self.context, records, group_papers=True)
        tree = Tree(text); rows = tree.having('data-index-row')
        self.assertEqual(len(rows), 456)
        self.assertEqual({node['attrs']['data-record-id'] for node in rows}, {row['id'] for row in records})
        states = [json.loads(node['attrs']['data-filters']) for node in rows]
        self.assertEqual(sum('approved' in item['status'] for item in states), 377)
        self.assertEqual(sum('candidate' in item['status'] for item in states), 79)
        self.assertEqual(sum('paper_version' in item['type'] for item in states), 208)
        self.assertEqual(sum('candidate' in item['status'] and 'paper_version' in item['type'] for item in states), 57)
        self.assertFalse(any(any('data-index-row' in parent['attrs'] for parent in node['parents']) for node in rows))
        self.assertIn('248 paper works · 208 source versions (456 records)', text)
        self.assertEqual(json.dumps(self.context['graph'], sort_keys=True), original)

    def test_tau_is_display_only_and_both_spellings_are_searchable(self):
        entities = [row for row in self.context['graph']['entities'] if r'\tau' in row['name']]
        self.assertEqual(len(entities), 4)
        for entity in entities:
            original = copy.deepcopy(entity)
            shown = rp._display_title(entity['name'])
            self.assertNotIn(r'\tau', shown)
            self.assertIn('τ', shown)
            row = Tree(rp._index_row(self.context, entity)).having('data-index-row')[0]
            self.assertIn(entity['name'].lower(), row['attrs']['data-search'])
            self.assertIn(shown.lower(), row['attrs']['data-search'])
            self.assertEqual(entity, original)

    def test_five_existing_scoped_statements_do_not_change_assertion_digests(self):
        ids = ['candidate.supplier.mercor.apex11-release', 'candidate.supplier.prolific.cohere-recruitment',
               'candidate.supplier.scale_ai.helpsteer3-contribution', 'candidate.supplier.snorkel_ai.finance-benchmark',
               'candidate.supplier.surge_ai.gsm8k-contribution']
        for identifier in ids:
            assertion = next(row for row in self.context['graph']['assertions'] if row['id'] == identifier)
            digest = rg.assertion_digest(assertion)
            statements = [q[len('Scoped source statement: '):].strip() for q in assertion['qualifications']
                          if q.startswith('Scoped source statement: ') and q[len('Scoped source statement: '):].strip()]
            self.assertEqual(len(statements), 1)
            self.assertEqual(rp._claim_text(self.context, assertion), rp.sp.escape(statements[0]))
            self.assertEqual(rg.assertion_digest(assertion), digest)


if __name__ == '__main__':
    unittest.main()
