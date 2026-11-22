"""Supplemental financial evidence stays dated and honest on plain company pages."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import static_pages as sp
from business_health import load_business_health
from presentation import health_subset


class StaticBusinessSupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'data/canonical.json').read_text())
        cls.health = json.loads((ROOT / 'data/business-health.json').read_text())
        cls.research = sp.Research(cls.data)

    def test_taskus_interim_result_is_separate_from_original_research(self):
        before = json.dumps(self.data, sort_keys=True)
        row = sp.selected_business_observation(self.health, 'taskus')
        self.assertEqual(row['id'], 'refresh.taskus.9m-2026-group-revenue')
        self.assertEqual(row['period'], {'type': 'year_to_date', 'label': '9M 2026', 'year': 2026,
                                         'start': '2026-01-01', 'end': '2026-09-30'})
        self.assertEqual(row['scope'], 'company')
        self.assertEqual(row['value'], 929868000)
        self.assertEqual(row['currency'], 'USD')
        self.assertEqual(row['source_ids'], ['refresh.source.taskus-q3-2026'])
        self.assertEqual(row['evidence_assurance'], 'Interim company reporting; unaudited')
        page = sp.business_observation_html(self.research, self.health, 'taskus')
        self.assertIn('Selected financial evidence', page)
        self.assertIn('$929.87M', page)
        self.assertIn('9M 2026', page)
        self.assertIn('Whole company', page)
        self.assertIn('href="https://www.taskus.com/press-release/taskus-announces-fiscal-third-quarter-2026-results/"', page)
        self.assertIn('Interim company reporting; unaudited', page)
        self.assertIn('Source content checked 16 Nov 2026.</span>', page)
        historical = next(o for o in self.health['observations'] if o['id'] == 'refresh.taskus.h1-2026-group-revenue')
        self.assertEqual((historical['value'], historical['period']['label'], historical['scope']),
                         (615121000, 'H1 2026', 'company'))
        self.assertEqual(historical['source_ids'], ['taskus.source.q22026'])
        self.assertEqual(historical['evidence_checked_on'], '2026-10-28')
        canonical_q2 = next(m for m in self.data['metrics'] if m['id'] == 'taskus.metric.expansion-7')
        self.assertEqual((canonical_q2['value'], canonical_q2['as_of'], canonical_q2['segment_scope']),
                         (308855000, 'three months ended 2026-06-30', 'company'))
        self.assertEqual(before, json.dumps(self.data, sort_keys=True))

    def test_estimates_and_failed_retrieval_are_distinct(self):
        health = copy.deepcopy(self.health)
        rows = [o for o in health['observations'] if o['company_id'] == 'taskus']
        for row in rows:
            if row.get('measure') == 'period_revenue':
                row['evidence_type'] = 'estimate'
        chosen = sp.selected_business_observation(health, 'taskus')
        self.assertTrue(chosen is None or chosen['evidence_type'] == 'reported')
        page = sp.business_observation_html(self.research, self.health, 'turing')
        self.assertIn('data-source-id="refresh.source.turing-2024-run-rate-issuer"', page)
        self.assertIn('Earlier citation could not be rechecked', page)
        self.assertIn('verified through its indexed text', page)
        self.assertIn('direct automated request returned a bot challenge', page)
        self.assertNotIn('Source content checked 28 Oct 2026', page)
        archive = sp.business_observation_html(self.research, self.health, 'a-team')
        self.assertIn('No recent revenue figure', archive)
        self.assertIn('<details', archive)

    def test_dated_source_unavailability_keeps_the_original_financial_claim(self):
        row = sp.selected_business_observation(self.health, 'prolific')
        source = self.research.sources[row['source_ids'][0]]
        health = sp.link_health_index({'entries': [
            {'url': source['url'], 'status': 'not_found', 'checked_on': '2026-11-22'},
        ]})
        research = sp.Research(self.data, health=health)
        for inline in (False, True):
            with self.subTest(inline=inline):
                page = sp.business_observation_html(research, self.health, 'prolific', inline=inline)
                self.assertIn(f'href="{source["url"]}"', page)
                self.assertIn('at least $300M', page)
                self.assertIn('CEO-reported operating figures; unaudited', page)
                self.assertEqual(page.count('page unavailable when checked 22 Nov 2026'), 1)
                self.assertNotIn('citation could not be rechecked', page)

    def test_turing_talent_cloud_keeps_original_citation_beside_official_release(self):
        health = load_business_health(ROOT / 'data/business-health.json', self.data)
        record_id = 'turing.metric.major-growth_metrics-4'
        original_id = 'turing.source.audit-t1'
        issuer_id = 'refresh.source.turing-series-e-issuer'
        issuer_url = 'https://www.turing.com/press/turing-111-million-series-e'
        row = next(row for row in health['observations'] if row['id'] == record_id)
        metric = next(metric for metric in self.data['metrics'] if metric['id'] == record_id)
        self.assertEqual((row['value'], row['unit'], row['qualifier'], row['as_of']),
                         (4_000_000, 'people', 'greater_than', '2025-03-06'))
        self.assertEqual(row['source_ids'], [original_id, issuer_id])
        self.assertEqual(self.research.claim(metric)['source_ids'], [original_id])

        scoped = health_subset(health, [row], 'turing')
        self.assertEqual({source['id'] for source in scoped['sources']}, {original_id, issuer_id})
        page = sp.figures_html(self.research, self.research.companies['turing'], [metric], [], [], {}, health=scoped)
        self.assertIn(f'data-source-id="{issuer_id}"><a class="ext" href="{issuer_url}">Turing’s official Series E release</a>', page)
        self.assertIn(f'href="{self.research.sources[original_id]["url"]}"', page)


if __name__ == '__main__':
    unittest.main()
