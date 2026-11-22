"""Supplemental financial evidence stays dated and honest on plain company pages."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import static_pages as sp


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
        self.assertIn('Original citation could not be rechecked', page)
        self.assertNotIn('Source content checked 28 Oct 2026', page)
        archive = sp.business_observation_html(self.research, self.health, 'a-team')
        self.assertIn('No recent revenue figure', archive)
        self.assertIn('<details', archive)


if __name__ == '__main__':
    unittest.main()
