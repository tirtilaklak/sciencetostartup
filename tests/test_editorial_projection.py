"""Initial editorial projection: exact real-corpus rendering and access parity."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from presentation import compact_editorial, EDITORIAL_RUNTIME_FIELDS, rooted_assets


class EditorialProjectionTests(unittest.TestCase):
    def test_projection_preserves_root_metadata_order_and_complete_nested_values(self):
        original = json.loads((ROOT / 'data/editorial.json').read_text())
        original.update(schema_version='synthetic-root-schema', metadata={'fixture': True})
        before = copy.deepcopy(original)
        projected = compact_editorial(original)
        self.assertEqual({k: v for k, v in projected.items() if k != 'entries'},
                         {k: v for k, v in original.items() if k != 'entries'})
        self.assertEqual([e['company_id'] for e in projected['entries']], [e['company_id'] for e in original['entries']])
        for entry, full in zip(projected['entries'], original['entries']):
            self.assertEqual(entry, {k: v for k, v in full.items() if k in EDITORIAL_RUNTIME_FIELDS})
        projected['entries'][0]['capability_tags'].append('synthetic-test-mutation')
        self.assertEqual(original, before)

    def test_all_39_cards_profiles_work_and_search_are_identical_with_observed_field_access(self):
        tree = ast.parse((ROOT / 'tests/js_logic.py').read_text())
        stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'STUB' for target in node.targets))
        prefix = stub.split('(async()=>{', 1)[0]
        instrumentation = r'''
const editorial=JSON.parse(fs.readFileSync(expectedPath,'utf8')),accesses=new Set();
const allowed=new Set(['company_id','summary','primary_offering','capability_tags','product_media']);
function instrument(value){return {...value,entries:value.entries.map(entry=>new Proxy(entry,{
 get(target,key){if(typeof key==='string'){accesses.add(key);assert.ok(allowed.has(key),'Unexpected editorial authoring-field access: '+key)}return target[key]},
 ownKeys(){throw Error('Runtime must not enumerate editorial authoring entries')}
}))}}
'''
        prefix = prefix.replace('const window={', instrumentation + 'const window={')
        prefix = prefix.replace("EDITORIAL:readJSON('data/editorial.json')", 'EDITORIAL:instrument(editorial)')
        checks = r'''
run('initialize()');
assert.equal(data.companies.length,39);assert.equal(editorial.entries.length,39);
const before=run('JSON.stringify(DATA)'),rows=[];
for(const c of data.companies){const id=JSON.stringify(c.id);rows.push({id:c.id,
 card:run(`card(companies[${id}])`),profile:run(`profileHTML(${id})`),
 intro:run(`profileIntroductionHTML(${id})`),visual:run(`profileHeroVisual(${id})`),
 media:run(`productMediaHTML(${id})`),peers:run(`profilePeersHTML(${id})`),work:run(`workSummary(${id})`),
 model:run(`modelFor(${id})`),group:run(`modelGroup(${id})`)});}
const search=plain(run('siteSearchIndex()'));
const queries=data.companies.map(c=>c.name).concat(['expert','evaluation','AI','research']);
const directory=queries.map(q=>{run(`state.query=${JSON.stringify(q)};state.category='';state.stage='';state.financial=false;state.work=false`);return {q,ids:plain(run('filtered().map(c=>c.id)'))}});
const groups=plain(run('MODEL_GROUPS'));
assert.equal(run('JSON.stringify(DATA)'),before,'Rendering mutated canonical evidence');
process.stdout.write(JSON.stringify({rows,search,directory,groups,accesses:[...accesses].sort(),
 metadata:Object.fromEntries(Object.entries(editorial).filter(([k])=>k!=='entries'))}));
'''
        original = json.loads((ROOT / 'data/editorial.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            script = folder / 'parity.cjs'
            script.write_text(prefix + checks)
            outputs = []
            for name, payload in [('full', rooted_assets(original)),
                                  ('projected', rooted_assets(compact_editorial(original)))]:
                path = folder / (name + '.json')
                path.write_text(json.dumps(payload))
                result = subprocess.run(['node', str(script), str(ROOT / 'data/canonical.json'), str(ROOT), str(path)],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(set(outputs[1]['accesses']), EDITORIAL_RUNTIME_FIELDS)
        self.assertEqual(len(outputs[1]['rows']), 39)
        self.assertTrue(outputs[1]['search'])
        print(json.dumps({'companies': len(outputs[1]['rows']), 'search_records': len(outputs[1]['search']),
                          'directory_queries': len(outputs[1]['directory']), 'fields_observed': outputs[1]['accesses'],
                          'parity_sha256': hashlib.sha256(json.dumps(outputs[1], sort_keys=True).encode()).hexdigest(),
                          'scope': 'Actual source-module Node VM parity; browser layout and Lighthouse are separate.'}))


if __name__ == '__main__':
    unittest.main()
