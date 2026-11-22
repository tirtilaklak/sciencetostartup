"""Current source rechecks preserve the signed edition and its URLs."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_pages as rp
from research_report import build_context


class ResearchSourceRecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_context(ROOT)

    def test_trustscale_links_are_scoped_to_current_reader(self):
        context = self.context
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

    def test_current_website_keeps_the_recorded_url_and_approved_identity(self):
        context = self.context
        websites = rp._company_websites(context)
        current_urls = {
            'org.datatang': 'https://www.datatang.com/',
            'org.e2f': 'https://www.trustscale.ai/',
            'org.globose_technology_solutions': 'https://gts.ai/',
            'org.speechocean': 'https://dataoceanai.com/',
        }
        self.assertEqual({eid: row['current_url'] for eid, row in websites.items()}, current_urls)
        self.assertEqual(rp._company_websites({**context, 'report': {'release_id': 'later-edition'}}), {})
        current = {**context, '_render_company_websites': websites}
        entities = {row['id']: row for row in context['graph']['entities']}
        for eid, url in current_urls.items():
            with self.subTest(entity=eid):
                entity = entities[eid]
                original = entity['identifiers']['website']
                original_html = rp._company_detail(context, entity)
                current_html = rp._company_detail(current, entity)
                original_hero = original_html.split('</header>', 1)[0]
                current_hero, scope = current_html.split('</header>', 1)
                label = 'Website (Chinese)' if eid == 'org.datatang' else 'Website'
                self.assertIn(f'<a href="{url}">{label}</a>', current_hero)
                self.assertIn(f'<a href="{original}">Website</a>', original_hero)
                self.assertIn(f'<dt>Recorded website</dt><dd><a href="{original}">{original}', scope)
                self.assertIn('Current website checked 22 Nov 2026', scope)
                claim = websites[eid]['evidence'][0]['claim_id']
                self.assertIn(f'<a href="{rp._evidence_url("assertion", claim)}">Identity evidence</a>', scope)
                self.assertEqual(entity['identifiers']['website'], original)
