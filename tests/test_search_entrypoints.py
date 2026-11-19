"""Search uses the same visible title and real hub destinations as native pages."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from daily_scan import daily_search_entries, load_daily_context
from research_pages import research_search_entries


class SearchEntrypointTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_daily_hub_and_visible_tau_titles_match_without_changing_source_records(self):
        daily = daily_search_entries(load_daily_context(ROOT))
        self.assertEqual(sum(row['url'] == '/daily/' for row in daily), 1)
        graph = json.loads((ROOT / 'dist/research/exports/research-graph.json').read_text())
        entities = [row for row in graph['entities'] if r'\tau' in row['name']]
        self.assertEqual(len(entities), 4)
        before = copy.deepcopy(entities)
        context = {'gate': {'ready': True}, 'report': {'title': 'Fixture report', 'status': 'published', 'sections': []},
                   'graph': {'entities': entities, 'assertions': []}}
        research = research_search_entries(context)
        by_url = {row['url']: row for row in research}
        knowledge = by_url['/research/papers/paper.arxiv.2603.04370/']
        self.assertTrue(knowledge['title'].startswith('τ-Knowledge'))
        self.assertIn(r'$\tau$-Knowledge', knowledge['keywords'])
        self.assertEqual(entities, before)
        rows = [{'name': row['title'], 'summary': row['summary'], 'group': row['kind'],
                 'products': row['keywords'] if isinstance(row['keywords'], list) else row['keywords'].split(),
                 'href': row['url']} for row in [*daily, *research]]
        runner = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
const search=context.S2SSearch,rows=JSON.parse(fs.readFileSync(0,'utf8'));
const first=query=>rows.map(row=>({row,rank:search.rank(search.compile(row),query)})).filter(item=>item.rank>=0).sort((a,b)=>a.rank-b.rank||search.compare(a.row,b.row))[0]?.row;
for(const [query,href] of [['Daily scan','/daily/'],['Daily','/daily/'],['τ-Knowledge','/research/papers/paper.arxiv.2603.04370/'],[String.raw`\tau-Knowledge`,'/research/papers/paper.arxiv.2603.04370/'],['τ²-Bench','/research/papers/paper.arxiv.2506.07982/'],[String.raw`\tau^2-Bench`,'/research/papers/paper.arxiv.2506.07982/']])assert.equal(first(query)?.href,href,query);
'''
        result = subprocess.run([shutil.which('node'), '-e', runner, str(ROOT / 'web/search-core.js')],
                                input=json.dumps(rows), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in rows:
            path, _, fragment = row['href'].partition('#')
            self.assertTrue((ROOT / 'dist' / path.lstrip('/') / 'index.html').is_file(), row['href'])
