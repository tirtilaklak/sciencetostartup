"""Actual search matching, baseline fixture integrity and component-loader races."""
from pathlib import Path
import shutil
import json
from html.parser import HTMLParser
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from frontend_packaging import optional_script_source
from presentation import search_fold, work_native_selection
import static_pages as sp


class NativeSearchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_real_corpus_literals_and_runtime_races(self):
        result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/search/core-runtime.cjs')], text=True, capture_output=True, cwd=ROOT, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_shared_matcher_is_in_existing_optional_payloads(self):
        core = (ROOT / 'web/search-core.js').read_text()
        for name in ('home-search.js', 'companies-page.js', 'work-page.js'):
            delivered = optional_script_source(ROOT, name)
            if name == 'work-page.js':
                prefix, suffix = "(() => {\n", "\n})();\n"
                self.assertTrue(delivered.startswith(prefix) and delivered.endswith(suffix))
                delivered = delivered[len(prefix):-len(suffix)]
                self.assertIn((ROOT / 'web/work-core.js').read_text(), delivered)
            self.assertTrue(delivered.startswith(core + '\n'))
            self.assertTrue(delivered.endswith((ROOT / 'web' / name).read_text()))
            self.assertNotIn('src="/search-core.js"', delivered)
        self.assertEqual(optional_script_source(ROOT, 'home-runtime.js'), (ROOT / 'web/home-runtime.js').read_text())

    def test_native_metadata_keeps_aliases_and_previous_visible_record_selectors(self):
        data = json.loads((ROOT / 'data/canonical.json').read_text())
        editorial = json.loads((ROOT / 'data/editorial.json').read_text())
        profiles = json.loads((ROOT / 'data/profile-content.json').read_text())
        work = json.loads((ROOT / 'data/work-routes.json').read_text())
        release = json.loads((ROOT / 'data/editorial-release.json').read_text())
        research = sp.Research(data, publication_as_of=release['publication_as_of'])
        class Attributes(HTMLParser):
            def __init__(self, html):
                super().__init__(); self.cards = {}; self.work_ids = []; self.feed(html)
            def handle_starttag(self, tag, pairs):
                attrs = dict(pairs)
                if attrs.get('data-company'):
                    self.cards[attrs['data-company']] = attrs
                if attrs.get('data-work-route'):
                    self.work_ids.append(attrs['data-work-route'])
        directory = sp.render_index(research, data['companies'], {row['company_id']: row for row in editorial['entries']}, {}, 78, '2026-11-18', profile_by_id={row['company_id']: row for row in profiles['entries']})
        cards = Attributes(directory).cards
        self.assertEqual(len(cards), len(data['companies']))
        self.assertIn('Outlier', cards['scale_ai']['data-search'])
        self.assertTrue(any('contributor brand' in value for value in json.loads(cards['scale_ai']['data-search-aliases'])))
        self.assertIn('href="/?search=#browse-guide"', directory)
        html = sp.render_work(research, work['routes'], {row['id']: row['name'] for row in data['companies']}, '2026-11-18')
        projected = work_native_selection(work, research.companies)
        projected_ids = [row['id'] for row in projected]
        self.assertCountEqual(Attributes(html).work_ids, projected_ids)
        self.assertEqual(len(projected_ids), len(work['routes']))
        self.assertNotIn('data-work-select=', html)
        scale_rows = [row for row in projected if row['company_id'] == 'scale_ai']
        self.assertTrue(scale_rows)
        for row in scale_rows:
            for alias in research.companies['scale_ai']['aliases']:
                self.assertIn(search_fold(alias), row['searchText'])
        rl_rows = {row['id'] for row in projected if 'rlhf' in row['searchText']}
        self.assertIn('afterquery.work.software-engineer-rl-environments', rl_rows)
        for selector in ('work-heading', 'work-offer', 'work-listing-conditions'):
            self.assertIn('class="' + selector + '"', html)
