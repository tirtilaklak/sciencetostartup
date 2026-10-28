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
        self.assertEqual(row['period']['label'], 'H1 2026')
        self.assertEqual(row['scope'], 'company')
        self.assertEqual(row['value'], 615121000)
        page = sp.business_observation_html(self.research, self.health, 'taskus')
        self.assertIn('Selected financial evidence', page)
        self.assertIn('$615.12M', page)
        self.assertIn('H1 2026', page)
        self.assertIn('Whole company', page)
        self.assertIn('https://', page)
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
