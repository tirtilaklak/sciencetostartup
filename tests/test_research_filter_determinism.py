"""Case-distinct facet labels must not inherit Python's randomized set order."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResearchFilterDeterminismTests(unittest.TestCase):
    def test_casefold_ties_render_identically_across_process_hash_seeds(self):
        script = """
import sys
sys.path.insert(0, 'scripts')
from research_pages import _evidence_table
entity = {'id': 'paper.fixture', 'kind': 'paper', 'name': 'Synthetic fixture',
          'status': 'candidate', 'taxonomy': {'domain': ['stem', 'STEM', 'straße', 'STRASSE']}}
context = {'graph': {'entities': [entity], 'assertions': []}}
print(_evidence_table(context, [entity]))
"""
        outputs = []
        for seed in ('0', '1', '2', '17'):
            result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                    env={**os.environ, 'PYTHONHASHSEED': seed},
                                    text=True, capture_output=True, check=True)
            outputs.append(result.stdout)
        self.assertEqual(len(set(outputs)), 1)
        self.assertLess(outputs[0].index('value="STEM"'), outputs[0].index('value="stem"'))
        self.assertLess(outputs[0].index('value="STRASSE"'), outputs[0].index('value="straße"'))


if __name__ == '__main__':
    unittest.main()
