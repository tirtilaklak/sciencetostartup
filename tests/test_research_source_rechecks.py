"""Current source rechecks preserve the signed edition and its URLs."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_pages as rp
from research_report import build_context


class ResearchSourceRecheckTests(unittest.TestCase):
    def test_trustscale_links_are_scoped_to_current_reader(self):
        context = build_context(ROOT)
        rechecks = rp._source_rechecks(context)
        original = 'https://www.trustscale.ai/assets/index-CUMNnpew.js'
        current = 'https://www.trustscale.ai/assets/index-BPxQN8-8.js'
        sources = {row['id']: row for row in context['graph']['sources'] if row['url'] == original}
        self.assertEqual(set(rechecks), set(sources))
        self.assertEqual(len(sources), 6)
        self.assertEqual(len(set().union(*(row['claim_ids'] for row in rechecks.values()))), 7)

        ledger = {**context, '_render_ledger': ({}, {}, sources)}
        updated = {**ledger, '_render_source_rechecks': rechecks}
        live = {path: body for path, _, _, body, _, _ in rp._ledger_pages(updated)}
        archive = '/research/editions/2026-11-12/data/'
        self.assertEqual(rp._ledger_pages(updated, archive), rp._ledger_pages(ledger, archive))
        for source_id in sources:
            path, anchor = rp._evidence_url('source', source_id).split('#')
            article = live[path].split(f'id="{anchor}">', 1)[1].split('</article>', 1)[0]
            self.assertEqual(article.count(f'href="{original}"'), 1)
            self.assertEqual(article.count(f'href="{current}"'), 1)
            self.assertIn('Original file unavailable when checked 22 Nov 2026', article)

        trustscale = next(row for row in context['graph']['entities'] if row['id'] == 'org.e2f')
        approved = rp._assertions(context, trustscale)
        highlight = rp._company_highlight(updated, trustscale, approved, sources)
        for url in (original, current):
            self.assertEqual(highlight.count(f'href="{url}"'), 1)
        self.assertIn('Original file unavailable when checked 22 Nov 2026', highlight)
        self.assertIn('batch quality review', highlight)
