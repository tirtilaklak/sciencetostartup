"""Verify work search spacing does not change disclosure state or filter results, typed searches keep the phone
budget, filter changes draw every match, heading levels never skip, and closed parts draw on first open.

The budget's browser timings (390 px phone, 4x CPU slowdown, against main's build) are in the comment above
W4_FULL_CARDS in web/work-v4.js; this Node run checks the structure those timings depend on."""
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
const whitespace=[' ','\t','\r\n',' ',' \t\n '];
const clean=html=>html.replace(/evidence-description-\d+/g,'evidence-description-ID');
const GROUP='<details class="work-route-archive-group w4-route-group"';
const cardIds=html=>[...html.matchAll(/data-work-route="([^"]+)"/g)].map(m=>m[1]);
const NO_FILTERS={workGroup:'',workPay:'',workEligibility:'',workSort:''};
function view(){
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
// Typing: the filters are already set, then the search text changes.
function typed(query,filters={}){
 run(`Object.assign(state,${JSON.stringify(NO_FILTERS)},${JSON.stringify(filters)},{workQuery:''});renderWork();state.workQuery=${JSON.stringify(query)};renderWork()`);
 return view();
}
// A filter change: the search text is already there, then a select field changes.
function filtered(query,filters){
 run(`Object.assign(state,${JSON.stringify(NO_FILTERS)},{workQuery:${JSON.stringify(query)}});renderWork();Object.assign(state,${JSON.stringify(filters)});renderWork()`);
 return view();
}
// Every match is either drawn or waits in a closed group with its count: no hidden caps.
function assertReachable(v,label){
 const drawn=new Set(v.drawn);
 assert.equal(new Set(v.waiting).size,v.waiting.length,label+': a listing waits in two closed groups');
 for(const id of v.waiting)assert.ok(!drawn.has(id),label+': '+id+' is drawn and also waits in a closed group');
 for(const id of v.ids)assert.ok(drawn.has(id)||v.waiting.includes(id),label+': match '+id+' cannot be reached');
}
const counts=()=>plain(run(`(()=>{const g=w4RouteGroups(filteredWork());return Object.fromEntries(['contract','hourly','task','jobs','boards','outside','closed'].map(k=>[k,g[k].length]));})()`));
// The typing budget (W4_FULL_CARDS and friends in work-v4.js): contract work is never cut, jobs fill the
// rest of 26 full cards (at least six, never a More group of one), and Other listings groups open at 12 or fewer.
function assertTypedView(v,label){
 const g=counts(),budget=Math.max(6,26-g.hourly-g.task),cut=g.jobs>budget+1;
 assert.equal(v.contractCards,g.contract,label+': a search must show every matching contract listing');
 assert.equal(v.jobsFull,cut?budget:g.jobs,label+': matching jobs shown in full');
 assert.equal(v.more,cut,label+': jobs beyond the budget belong in the closed More jobs and fellowships group');
 assert.equal(v.openGroups,[g.boards,g.outside,g.closed].filter(n=>n&&n<=12).length,label+': only groups with 12 or fewer matches open');
 assertReachable(v,label);
}
// A filter change is exempt from the budget: every match is drawn and every group that holds one is open.
function assertFilterView(v,label){
 const g=counts();
 assert.equal(v.contractCards,g.contract,label+': every matching contract listing');
 assert.equal(v.jobsFull,g.jobs,label+': every matching job in full');
 assert.equal(v.more,false,label+': a filter change leaves no closed More group');
 assert.equal(v.openGroups,v.groups,label+': every group that holds a match is open');
 assert.equal(v.waiting.length,0,label+': nothing waits in a closed group');
 assert.deepEqual([...v.drawn].sort(),[...v.ids].sort(),label+': every match is drawn once');
}
const baseline=typed('');
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
// Cards draw their closed parts on first open: the page holds no Terms & sources content until a reader opens one.
assert.ok(!baseline.html.includes('w4-detail-content')&&!baseline.html.includes('w4-card-front"><div class="w4-compact-company'),'Default view drew closed card parts');
for(const query of whitespace)assert.deepEqual(typed(query),baseline,
 'Whitespace-only work search changed results or disclosure state: '+JSON.stringify(query));

let nonemptyCases=0;
for(const query of ['AfterQuery','Python','no-such-work-route-qqz']){
 const exact=typed(query),padded=typed(' \t'+query+'\n ');
 assert.deepEqual(padded,exact,'Padding changed a genuine search: '+query);
 assertTypedView(exact,query);
 if(query==='AfterQuery')assert.equal(exact.ids.length,45,'AfterQuery search coverage changed');
 if(query==='no-such-work-route-qqz')assert.equal(exact.ids.length,0,'Unknown query should remain empty');
 nonemptyCases++;
}
// A one-letter search matches nearly every listing. Typed, it keeps the phone budget.
for(const query of ['a','e']){
 const broad=typed(query);
 assert.ok(broad.ids.length>=100,'One-letter fixture lost its broad match: '+query);
 assertTypedView(broad,query);
 assert.ok(broad.full<=Math.max(baseline.full,26),query+': a one-letter search drew more full cards than the default view');
 assert.ok(broad.waiting.length>0,query+': a one-letter search should leave long groups closed');
 // A select change after typing (the Sort field here) is a filter change: every match, every group open.
 run(`state.workSort='checked';renderWork()`);const sorted=view();assertFilterView(sorted,query+' then a sort change');
 // A repeat render with nothing changed keeps that view; typing again brings the budget back.
 run('renderWork()');assert.deepEqual(view(),sorted,query+': a repeat render changed the view');
 run(`state.workQuery=${JSON.stringify(query+' ')};renderWork()`);assertTypedView(view(),query+' typed after a sort change');
}
// The type filter follows the section rule: an Employment listing paid by the hour or by a
// one-time award is contract work in the sections and in the "Contract and task work" filter.
{
 const ids=group=>plain(run(`(()=>{Object.assign(state,{workQuery:'',workGroup:${JSON.stringify(group)},workPay:'',workEligibility:''});return filteredWork().map(r=>r.id);})()`));
 const contract=ids('Expert & contractor projects'),jobs=ids('Employment');
 const moved=plain(run(`workRouteRows().filter(r=>r.group==='Employment'&&W4_CONTRACT_PAY.has(r.pay_basis)).map(r=>r.id)`));
 assert.ok(moved.length>0,'Fixture lost the Employment listings paid by the hour or one-time award');
 for(const id of moved){
  assert.ok(contract.includes(id),'Contract filter hides a listing the contract section shows: '+id);
  assert.ok(!jobs.includes(id),'Jobs filter shows a listing the contract section owns: '+id);
 }
 assert.deepEqual(contract.filter(id=>jobs.includes(id)),[],'A listing matched both the contract and the jobs filter');
 run(`Object.assign(state,{workGroup:''})`);
}
let filterCases=0;
for(const filters of [{workGroup:'Employment'},{workPay:'numeric'},
 {workEligibility:'US listing evidence'},
 {workGroup:'Employment',workPay:'numeric',workEligibility:'US listing evidence'}]){
 const result=filtered('',filters);
 assert.ok(result.ids.length>0,'Filter intersection lost its fixture results');
 assertFilterView(result,JSON.stringify(filters));
 for(const query of whitespace){
  assert.deepEqual(filtered(query,filters),result,'Whitespace bypassed or changed an active filter: '+JSON.stringify(filters));
  assert.deepEqual(typed(query,filters),result,'Whitespace typed under a filter changed it: '+JSON.stringify(filters));
 }
 // With a search already typed, a filter change still draws every match.
 assertFilterView(filtered('a',filters),'a + '+JSON.stringify(filters));
 filterCases++;
}
// Clear filters in the empty state keeps the search and counts as a filter change.
run(`Object.assign(state,${JSON.stringify(NO_FILTERS)},{workQuery:''});renderWork();state.workPay='monthly';renderWork();state.workQuery='a';renderWork();resetWorkFilters('filters')`);
assertFilterView(view(),'a after Clear filters');

// Lazy parts: a closed group, a compact card body and a Terms & sources block each draw, on first open,
// exactly what the page draws when everything is open (workCard without the lazy flag).
const expand=plain(run(`(()=>{
 const box=(attrs)=>{const b={dataset:{...attrs},html:'',removeAttribute(name){const key=name.replace(/^data-/,'').replace(/-([a-z])/g,(m,c)=>c.toUpperCase());delete this.dataset[key];},insertAdjacentHTML(where,html){this.html+=html;}};return b;};
 // Open every lazy part in html, the way a reader would, and return the result.
 function openAll(html){
  for(let guard=0;guard<10000;guard++){
   const card=html.match(/<details class="(w4-compact-toggle|w4-details)" data-w4-(card|detail)="([^"]+)" data-w4-level="(\\d+)">(<summary>[\\s\\S]*?<\\/summary>)/);
   if(card){const b=box(card[2]==='card'?{w4Card:card[3],w4Level:card[4]}:{w4Detail:card[3],w4Level:card[4]});w4FillCard(b);
    if(Object.keys(b.dataset).some(k=>k!=='w4Level'))return 'marker kept';
    html=html.replace(card[0],'<details class="'+card[1]+'" data-w4-level="'+card[4]+'">'+card[5]+b.html);continue;}
   const group=html.match(/<div class="w4-secondary-list" data-w4-level="(\\d+)" data-w4-routes="([^"]*)"><\\/div>/);
   if(group){const list={dataset:{w4Level:group[1],w4Routes:group[2]},innerHTML:'',removeAttribute(){this.lazy=false;}};
    w4FillGroup({querySelector:()=>list.lazy===false?null:list});
    html=html.replace(group[0],'<div class="w4-secondary-list" data-w4-level="'+group[1]+'">'+list.innerHTML+'</div>');continue;}
   return html;
  }
  return 'too many parts';
 }
 const strip=html=>html.replace(/ data-w4-level="\\d+"/g,'').replace(/evidence-description-\\d+/g,'evidence-description-ID');
 let cards=0,mismatch=[];
 for(const route of workRouteRows())for(const [mode,level] of [['',3],['',4],['compact',2],['compact',3]]){
  const eager=workCard(route,mode,level),lazy=workCard(route,mode,level,true);cards++;
  if(lazy.includes('w4-detail-content')||lazy.length>=eager.length)mismatch.push(route.id+' '+mode+' lazy card drew its closed parts');
  if(strip(openAll(lazy))!==strip(eager))mismatch.push(route.id+' '+mode+' '+level);
 }
 // Headings never skip a level, with every part open, on the page and on every profile work tab (an h2 section).
 const skips=(html,label)=>{let last=1;const out=[];for(const m of html.matchAll(/<h([1-6])\\b/g)){const n=Number(m[1]);if(n>last+1)out.push(label+': h'+last+' then h'+n);last=n;}return out;};
 const pages={};
 Object.assign(state,{workQuery:'',workGroup:'',workPay:'',workEligibility:'',workSort:''});renderWork();pages.default='<h1>'+document.getElementById('work-cards').innerHTML;
 state.workQuery='a';renderWork();pages.typed='<h1>'+document.getElementById('work-cards').innerHTML;
 state.workQuery='india';renderWork();pages.suggestions='<h1>'+document.getElementById('work-cards').innerHTML;
 Object.assign(state,{workQuery:'',workGroup:'Employment'});renderWork();pages.filter='<h1>'+document.getElementById('work-cards').innerHTML;
 Object.assign(state,{workGroup:''});renderWork();
 const headingSkips=[];
 for(const [label,html] of Object.entries(pages))headingSkips.push(...skips(openAll(html),label));
 for(const company of DATA.companies)headingSkips.push(...skips(openAll('<h1><h2>'+workSummary(company.id)),company.id));
 return{cards,mismatch:mismatch.slice(0,5),headingSkips:headingSkips.slice(0,5),suggestions:pages.suggestions.includes('work-suggested')};
})()`));
assert.deepEqual(expand.mismatch,[],'A lazy part drew something different when opened');
assert.ok(expand.suggestions,'The india search lost the network suggestions the heading check needs');
assert.deepEqual(expand.headingSkips,[],'A heading skips a level (axe heading-order)');
// The click on a summary fills its part before the browser opens it.
const clickFill=plain(run(`(()=>{const route=workRouteRows()[0];const box={tagName:'DETAILS',open:false,dataset:{w4Detail:route.id,w4Level:'4'},html:'',removeAttribute(){delete this.dataset.w4Detail;},insertAdjacentHTML(w,h){this.html+=h;},querySelector:()=>null,closest:()=>null,classList:{contains:()=>false}};
 const summary={parentElement:box,closest:()=>null,classList:{contains:()=>false}};for(const handler of __docCallbacks.click||[])handler({target:{closest:s=>s==='summary'?summary:null}});const clean=html=>html.replace(/evidence-description-\\d+/g,'evidence-description-ID');return{filled:Boolean(box.html)&&clean(box.html)===clean(w4Details(route,4)),marker:'w4Detail' in box.dataset};})()`));
assert.ok(clickFill.filled&&!clickFill.marker,'A summary click must fill a lazy card part');
// A closed group draws, on first open, the same cards an open group draws at once.
const fill=plain(run(`(()=>{
 const rows=w4RouteGroups(workRouteRows()).boards,closed=w4GroupDisclosure(rows,'Career pages',false,'',W4_GROUP_NOTES.boards),open=w4GroupDisclosure(rows,'Career pages',true,'',W4_GROUP_NOTES.boards);
 const list={dataset:{w4Routes:closed.match(/data-w4-routes="([^"]*)"/)[1],w4Level:closed.match(/data-w4-level="(\\d+)"/)[1]},innerHTML:'',lazy:true,removeAttribute(name){if(name==='data-w4-routes')this.lazy=false;}};
 const group={querySelector:selector=>selector.includes('[data-w4-routes]')&&!list.lazy?null:list};list.parentElement=group;
 const marker='data-w4-level="2">',expected=open.slice(open.indexOf(marker)+marker.length,open.lastIndexOf('</div></details>'));
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
 filterCombinations:filterCases,lazyCardsChecked:expand.cards,headingOrder:true,lazyGroupFill:true,canonicalUnchanged:true,browserExecuted:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-",
                         str(ROOT / "data/canonical.json"), str(ROOT)],
                        input=stub.split("(async()=>{", 1)[0] + "context.__docCallbacks=documentCallbacks;\n" + checks, text=True, cwd=ROOT)
raise SystemExit(result.returncode)
