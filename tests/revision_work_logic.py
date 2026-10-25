"""Verify work search spacing does not change disclosure state or filter results, searches keep the phone budget,
and closed groups draw their cards on first open."""
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
const whitespace=[' ','\t','\r\n',' ',' \t\n '];
const clean=html=>html.replace(/evidence-description-\d+/g,'evidence-description-ID');
const GROUP='<details class="work-route-archive-group w4-route-group"';
const cardIds=html=>[...html.matchAll(/data-work-route="([^"]+)"/g)].map(m=>m[1]);
function snapshot(query,filters={}){
 run(`Object.assign(state,{workQuery:${JSON.stringify(query)},workGroup:'',workPay:'',workEligibility:''},${JSON.stringify(filters)});renderWork()`);
 const html=node('work-cards').innerHTML;
 const section=id=>{const start=html.indexOf(`<h2 id="${id}"`);if(start<0)return '';const end=html.indexOf('<section class="w4-section',start);return html.slice(start,end<0?undefined:end);};
 return{ids:plain(run('filteredWork().map(route=>route.id)')),html:clean(html),
  beforeGroups:(html.split(GROUP)[0].match(/data-work-route=/g)||[]).length,
  more:html.includes('More jobs and fellowships'),
  openGroups:(html.match(/<details class="work-route-archive-group w4-route-group"[^>]*\bopen\b/g)||[]).length,
  groups:(html.match(/<details class="work-route-archive-group w4-route-group"/g)||[]).length,
  // Listings drawn as cards, and listings a closed group draws on first open.
  drawn:cardIds(html),waiting:[...html.matchAll(/data-w4-routes="([^"]*)"/g)].flatMap(m=>m[1].split(' ')),
  full:(html.match(/class="work-card work-card-v4 "/g)||[]).length,
  contractCards:cardIds(section('work-listed')).length,jobsFull:cardIds(section('work-jobs').split(GROUP)[0]).length,
  count:node('work-count').textContent,overview:node('work-overview').innerHTML};
}
// Every match is either drawn or waits in a closed group with its count: no hidden caps.
function assertReachable(view,label){
 const drawn=new Set(view.drawn);
 assert.equal(new Set(view.waiting).size,view.waiting.length,label+': a listing waits in two closed groups');
 for(const id of view.waiting)assert.ok(!drawn.has(id),label+': '+id+' is drawn and also waits in a closed group');
 for(const id of view.ids)assert.ok(drawn.has(id)||view.waiting.includes(id),label+': match '+id+' cannot be reached');
}
// The search budget (W4_FULL_CARDS and friends in work-v4.js): contract work is never cut, jobs fill the
// rest of 26 full cards (at least six, never a More group of one), and Other listings groups open at 12 or fewer.
function assertSearchView(view,label){
 const g=plain(run(`(()=>{const g=w4RouteGroups(filteredWork());return Object.fromEntries(['contract','hourly','task','jobs','boards','outside','closed'].map(k=>[k,g[k].length]));})()`));
 const budget=Math.max(6,26-g.hourly-g.task),cut=g.jobs>budget+1;
 assert.equal(view.contractCards,g.contract,label+': a search must show every matching contract listing');
 assert.equal(view.jobsFull,cut?budget:g.jobs,label+': matching jobs shown in full');
 assert.equal(view.more,cut,label+': jobs beyond the budget belong in the closed More jobs and fellowships group');
 assert.equal(view.openGroups,[g.boards,g.outside,g.closed].filter(n=>n&&n<=12).length,label+': only groups with 12 or fewer matches open');
 assertReachable(view,label);
}
const baseline=snapshot('');
assert.equal(baseline.ids.length,135,'Review route-count coverage after a research update');
// The default view shows every contract listing, then six jobs (at most three per company).
const preview=plain(run(`(()=>{const g=w4RouteGroups(filteredWork()),seen={};let jobs=0;
 for(const route of g.jobs){const n=seen[route.company_id]||0;if(jobs<6&&n<3){jobs++;seen[route.company_id]=n+1;}}
 return{contract:g.contract.length,jobs,allJobs:g.jobs.length};})()`));
assert.ok(preview.contract>0&&preview.allJobs>6,'Fixture lost the contract or jobs listings the preview needs');
assert.equal(preview.jobs,6,'Jobs preview should fill six cards from the current data');
assert.equal(baseline.beforeGroups,preview.contract+preview.jobs,'Default work view must retain its compact preview');
assert.equal(baseline.more,true,'Default work view lost its remaining-jobs disclosure');
assert.equal(baseline.openGroups,0,'Default secondary groups should start collapsed');
assert.equal(baseline.drawn.length,preview.contract+preview.jobs,'Closed groups in the default view must not draw their cards');
assert.ok(baseline.waiting.length>0,'Closed groups lost the listing ids they draw on first open');
assertReachable(baseline,'default view');
for(const query of whitespace)assert.deepEqual(snapshot(query),baseline,
 'Whitespace-only work search changed results or disclosure state: '+JSON.stringify(query));

let nonemptyCases=0;
for(const query of ['AfterQuery','Python','no-such-work-route-qqz']){
 const exact=snapshot(query),padded=snapshot(' \t'+query+'\n ');
 assert.deepEqual(padded,exact,'Padding changed a genuine search: '+query);
 assertSearchView(exact,query);
 if(query==='AfterQuery')assert.equal(exact.ids.length,45,'AfterQuery search coverage changed');
 if(query==='no-such-work-route-qqz')assert.equal(exact.ids.length,0,'Unknown query should remain empty');
 nonemptyCases++;
}
// A one-letter search matches nearly every listing. On a phone it must cost about what the default view costs.
for(const query of ['a','e']){
 const broad=snapshot(query);
 assert.ok(broad.ids.length>=100,'One-letter fixture lost its broad match: '+query);
 assertSearchView(broad,query);
 assert.ok(broad.full<=Math.max(baseline.full,26),query+': a one-letter search drew more full cards than the default view');
 assert.ok(broad.waiting.length>0,query+': a one-letter search should leave long groups closed');
}
let filterCases=0;
for(const filters of [{workGroup:'Employment'},{workPay:'numeric'},
 {workEligibility:'US listing evidence'},
 {workGroup:'Employment',workPay:'numeric',workEligibility:'US listing evidence'}]){
 const filtered=snapshot('',filters);
 assert.ok(filtered.ids.length>0,'Filter intersection lost its fixture results');
 assertSearchView(filtered,JSON.stringify(filters));
 for(const query of whitespace)assert.deepEqual(snapshot(query,filters),filtered,
  'Whitespace bypassed or changed an active filter: '+JSON.stringify(filters));
 filterCases++;
}
// A closed group draws, on first open, the same cards an open group draws at once.
const fill=plain(run(`(()=>{
 const rows=w4RouteGroups(workRouteRows()).boards,closed=w4GroupDisclosure(rows,'Career pages',false,'',W4_GROUP_NOTES.boards),open=w4GroupDisclosure(rows,'Career pages',true,'',W4_GROUP_NOTES.boards);
 const list={dataset:{w4Routes:closed.match(/data-w4-routes="([^"]*)"/)[1]},innerHTML:'',lazy:true,removeAttribute(name){if(name==='data-w4-routes')this.lazy=false;}};
 const group={querySelector:selector=>selector.includes('[data-w4-routes]')&&!list.lazy?null:list};list.parentElement=group;
 const marker='<div class="w4-secondary-list">',expected=open.slice(open.indexOf(marker)+marker.length,open.lastIndexOf('</div></details>'));
 const closedCards=(closed.match(/data-work-route=/g)||[]).length;
 w4FillRouteGroup({querySelectorAll:()=>[list]},rows.at(-1).id);const first=list.innerHTML;
 w4FillGroup(group);
 const clean=html=>html.replace(/evidence-description-\\d+/g,'evidence-description-ID');
 return{rows:rows.length,closedCards,openHasNote:open.includes('w4-group-note'),closedHasNote:closed.includes('w4-group-note'),same:clean(first)===clean(expected),lazy:list.lazy,again:list.innerHTML===first,cards:(first.match(/data-work-route=/g)||[]).length};})()`));
assert.ok(fill.rows>1,'Fixture lost the career pages the lazy-group check needs');
assert.equal(fill.closedCards,0,'A closed group must not draw its cards before it opens');
assert.ok(fill.openHasNote&&fill.closedHasNote,'Group notes must show whether the group is open or closed');
assert.ok(fill.same,'A closed group drew different cards on first open');
assert.equal(fill.cards,fill.rows,'A closed group lost listings on first open');
assert.equal(fill.lazy,false,'A filled group must drop its listing ids');
assert.ok(fill.again,'Opening a filled group again must not redraw it');
assert.equal(run('JSON.stringify(DATA)'),canonicalBefore,'Rendering mutated canonical research');
console.log(JSON.stringify({workRoutes:baseline.ids.length,defaultPrimaryPreview:baseline.beforeGroups,defaultDrawn:baseline.drawn.length,
 defaultWaiting:baseline.waiting.length,whitespaceQueries:whitespace.length,genuineQueries:nonemptyCases,oneLetterQueries:2,
 filterCombinations:filterCases,lazyGroupFill:true,canonicalUnchanged:true,browserExecuted:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-",
                         str(ROOT / "data/canonical.json"), str(ROOT)],
                        input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT)
raise SystemExit(result.returncode)
