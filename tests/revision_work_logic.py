"""Verify work search spacing does not change disclosure state or filter results."""
import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
checks = r'''
const canonicalBefore=run('JSON.stringify(DATA)');
const whitespace=[' ','\t','\r\n','\u00a0',' \t\n '];
const clean=html=>html.replace(/evidence-description-\d+/g,'evidence-description-ID');
function snapshot(query,filters={}){
 run(`Object.assign(state,{workQuery:${JSON.stringify(query)},workGroup:'',workPay:'',workEligibility:''},${JSON.stringify(filters)});renderWork()`);
 const html=node('work-cards').innerHTML;
 return{ids:plain(run('filteredWork().map(route=>route.id)')),html:clean(html),
  beforeGroups:(html.split('<details class="work-route-archive-group w4-route-group"')[0].match(/data-work-route=/g)||[]).length,
  more:html.includes('More listed routes'),
  openGroups:(html.match(/<details class="work-route-archive-group w4-route-group"[^>]*\bopen\b/g)||[]).length,
  count:node('work-count').textContent,overview:node('work-overview').innerHTML};
}
const baseline=snapshot('');
assert.equal(baseline.ids.length,135,'Review route-count coverage after a research update');
assert.equal(baseline.beforeGroups,12,'Default work view must retain its compact preview');
assert.equal(baseline.more,true,'Default work view lost its remaining-role disclosure');
assert.equal(baseline.openGroups,0,'Default secondary groups should start collapsed');
for(const query of whitespace)assert.deepEqual(snapshot(query),baseline,
 'Whitespace-only work search changed results or disclosure state: '+JSON.stringify(query));

let nonemptyCases=0;
for(const query of ['AfterQuery','Python','no-such-work-route-qqz']){
 const exact=snapshot(query),padded=snapshot(' \t'+query+'\n ');
 assert.deepEqual(padded,exact,'Padding changed a genuine search: '+query);
 assert.equal(exact.more,false,'An active search should reveal all matching primary roles');
 if(query==='AfterQuery')assert.equal(exact.ids.length,45,'AfterQuery search coverage changed');
 if(query==='no-such-work-route-qqz')assert.equal(exact.ids.length,0,'Unknown query should remain empty');
 nonemptyCases++;
}
let filterCases=0;
for(const filters of [{workGroup:'Employment'},{workPay:'numeric'},
 {workEligibility:'US listing evidence'},
 {workGroup:'Employment',workPay:'numeric',workEligibility:'US listing evidence'}]){
 const filtered=snapshot('',filters);
 assert.ok(filtered.ids.length>0,'Filter intersection lost its fixture results');
 assert.equal(filtered.more,false,'A real filter should reveal matching primary roles');
 for(const query of whitespace)assert.deepEqual(snapshot(query,filters),filtered,
  'Whitespace bypassed or changed an active filter: '+JSON.stringify(filters));
 filterCases++;
}
assert.equal(run('JSON.stringify(DATA)'),canonicalBefore,'Rendering mutated canonical research');
console.log(JSON.stringify({workRoutes:baseline.ids.length,defaultPrimaryPreview:baseline.beforeGroups,
 whitespaceQueries:whitespace.length,genuineQueries:nonemptyCases,filterCombinations:filterCases,
 canonicalUnchanged:true,browserExecuted:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-",
                         str(ROOT / "data/canonical.json"), str(ROOT)],
                        input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT)
raise SystemExit(result.returncode)
