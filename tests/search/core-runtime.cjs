const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const core = {};
vm.runInNewContext(read('web/search-core.js'), core);
const search = core.S2SSearch;
const html = read('dist/index.html');
const config = JSON.parse(html.match(/<script id="home-config" type="application\/json">(.*?)<\/script>/s)[1]);
const rows = JSON.parse(read('dist' + config.search.href)).entries;
const companies = JSON.parse(read('data/canonical.json')).companies;
const lookup = new Map(companies.map(company => [company.id, company]));
const entries = rows.map(row => ({...row, aliases: lookup.get(row.id)?.aliases || []}));
const results = query => entries.map(row => ({row, rank: search.rank(search.compile(row), query)})).filter(item => item.rank >= 0).sort((a, b) => a.rank - b.rank || search.compare(a.row, b.row));
for (const [query, expected] of [['Outlier', 'scale_ai'], ['Remotasks', 'scale_ai'], ['Alignerr', 'labelbox'], ['DataAnnotation', 'surge_ai'], ['Mindrift', 'toloka']]) assert.equal(results(query)[0].row.id, expected, query);
for (const [query, href] of [['Nexdata', '/company/org.nexdata/'], ['Datasets', '/research/datasets/']]) assert.equal(results(query)[0].row.href, href, query);
const fixture = search.compile({name: 'C++ C# café 研究', aliases: ['Old Name (historical, unverified)'], text: 'Flexible remote work'});
for (const query of ['C++', 'C#', 'CAFÉ', 'cafe\u0301', '研究', 'old name']) assert.ok(search.rank(fixture, query) >= 0, query);
assert.equal(search.matchedAlias(fixture, 'Old Name'), 'Old Name (historical, unverified)');
assert.equal(search.rank(fixture, 'C++++'), -1);
assert.equal(search.rank(search.compile({name:'Older record', summary:'No new metadata', products:[]}), 'older'), 1);
assert.ok(results('feedback').length > 7, 'Real count is computed before paging');
assert.ok(results('human feedback').slice(0, 7).some(item => item.row.href === '/research/state-of-ai-data-labs/'), 'Research hub remains reachable among equally relevant source versions');
const fixtures = JSON.parse(read('tests/fixtures/previous-search/manifest.json'));
assert.equal(fixtures.source_commit, '1517ce1ac1d227a47b9f9f00b6669acb75226cba');
for (const [name, digest] of Object.entries(fixtures.sha256)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'tests/fixtures/previous-search', name))).digest('hex'), digest);
function harness(url = 'https://fixture.test/') {
  const timers = new Map(), scripts = [], listeners = new Map(); let timerId = 0;
  const nodes = {};
  function node(id) {
    const callbacks = {};
    return nodes[id] ||= { id, value:'', textContent:'', innerHTML:'', dataset:{}, hidden:false, open:false, callbacks,
      setAttribute(name,value){this[name]=String(value);},removeAttribute(name){delete this[name];},
      addEventListener(name,fn){(callbacks[name] ||= []).push(fn);},focus(){document.activeElement=this;},
      showModal(){this.open=true;},close(){if(this.open){this.open=false;this.emit('close');}},
      emit(name,event={}){for(const fn of callbacks[name]||[])fn({target:this,preventDefault(){this.prevented=true;},...event});},
      remove(){this.removed=true;},closest(){return null;}};
  }
  const document = {getElementById:id=>id==='home-work-example'?null:node(id), activeElement:null, hidden:false,
    createElement:()=>({remove(){this.removed=true;}}),head:{append:script=>scripts.push(script)},
    addEventListener(name, fn){(listeners.get(name)||listeners.set(name,[]).get(name)).push(fn);}};
  node('home-config').textContent=JSON.stringify({candidates:[]});
  const location = new URL(url), history = {state:{kept:true}, replaceState(state,unused,value){this.state=state;const next=new URL(value,location);location.href=next.href;}};
  const context = {document,location,history,URL,Date,window:null,setInterval(){},setTimeout(fn,delay){timers.set(++timerId,{fn,delay});return timerId;},clearTimeout:id=>timers.delete(id)};
  context.window=context;
  vm.runInNewContext(read('web/home-runtime.js'),context);
  return {context,document,location,history,node,scripts,timers,click:()=>node('home-search-open').emit('click',{button:0}),
    timeout(){const [id,timer]=[...timers].find(([,timer])=>timer.delay===15000);timers.delete(id);timer.fn();},
    retry(){node('home-search-message').emit('click',{target:{closest:selector=>selector==='[data-home-component-retry]'?{}:null}});}};
}
const stalled=harness();stalled.click();assert.equal(stalled.node('home-search').open,true);assert.equal(stalled.scripts.length,1);
const late=stalled.scripts[0].onload;stalled.timeout();assert.match(stalled.node('home-search-message').innerHTML,/Try again/);
stalled.node('home-search-close').emit('click');assert.equal(stalled.node('home-search').open,false);let opens=0;stalled.context.openHomeSearch=()=>opens++;late();assert.equal(opens,0,'Late callback cannot reopen a closed fallback');
stalled.click();assert.equal(opens,1,'Deliberate new activation can reuse a late installation');
const empty=harness();empty.click();empty.scripts[0].onload();assert.match(empty.node('home-search-message').innerHTML,/could not load/);empty.retry();assert.equal(empty.scripts.length,2);empty.context.openHomeSearch=()=>opens++;empty.scripts[1].onload();assert.equal(opens,2);
const retry=harness();retry.click();const previous=retry.scripts[0].onload;retry.timeout();retry.retry();assert.equal(retry.scripts.length,2);retry.context.openHomeSearch=()=>opens++;previous();assert.equal(opens,2,'Stale callback cannot run the newer request');retry.scripts[1].onload();assert.equal(opens,3);
const closed=harness();closed.click();const closedLate=closed.scripts[0].onload;closed.node('home-search-close').emit('click');closed.context.openHomeSearch=()=>opens++;closedLate();assert.equal(opens,3);
const modified=harness();const event={button:0,ctrlKey:true,preventDefault(){this.prevented=true;}};modified.node('home-search-open').emit('click',event);assert.equal(modified.scripts.length,0);assert.equal(modified.node('home-search').open,false);
const prefilled=harness('https://fixture.test/?reader=keep&search=C%2B%2B#main');assert.equal(prefilled.node('home-search-input').value,'C++');assert.equal(prefilled.location.search,'?reader=keep');assert.equal(prefilled.location.hash,'#main');assert.equal(prefilled.node('home-search').open,true);assert.equal(prefilled.history.state.kept,true);
console.log(JSON.stringify({realEntries:entries.length,feedbackMatches:results('feedback').length,fixtures:Object.keys(fixtures.sha256).length,runtimeRaces:'passed'}));
