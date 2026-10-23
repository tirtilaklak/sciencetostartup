"""Check the profile "Risks and disputes" section with the delivered modules; no browser or build.

Synthetic events cover ordering, the related-company rule, escaping and hiding. When
data/company-events.json exists, every reviewed event is also rendered on each company it names.
"""
import ast
import hashlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
canonical = ROOT / "data/canonical.json"
before = hashlib.sha256(canonical.read_bytes()).hexdigest()
tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
stub = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets))
checks = r'''
const original=run('JSON.stringify(DATA)');
const ids=(html,key)=>[...html.matchAll(new RegExp(`data-profile-${key}="([^"]+)"`,'g'))].map(m=>m[1]);
const visible=html=>html.replace(/<span\b[^>]*data-evidence-description\b[^>]*>[\s\S]*?<\/span>/g,'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
const note='Lawsuit entries describe allegations and court filings, not findings. Dates show when a case was filed or an event was reported.';
const supported=id=>data.claims.filter(c=>c.company_id===id&&c.subject==='risks'&&c.status==='supported');
const newest=(a,b)=>(b.as_of==='undated'?'':b.as_of).localeCompare(a.as_of==='undated'?'':a.as_of)||a.id.localeCompare(b.id);
const section=id=>run(`profileRisks(${JSON.stringify(id)})`);

// Without the events sidecar the section still lists supported risk claims, newest first.
assert.equal(window.COMPANY_EVENTS,undefined);
let riskCompanies=0;
for(const c of data.companies){
 const html=section(c.id),expected=supported(c.id).sort(newest).map(cl=>cl.id);
 assert.deepEqual(ids(html,'risk'),expected,c.id+' risk order');
 assert.equal(html.includes('id="profile-risks"'),expected.length>0,c.id+' hidden when empty');
 assert.equal(run(`profileHTML(${JSON.stringify(c.id)})`).includes('id="profile-risks"'),expected.length>0);
 if(!expected.length)continue;riskCompanies++;
 assert.ok(!html.includes('Dated events'));assert.ok(html.includes('Risks named in the evidence'));assert.equal(html.split(note).length,2);
 for(const id of expected)assert.ok(new RegExp(`<button[^>]*data-claim="${id.replace(/\./g,'\\.')}"[^>]*>Source</button>`).test(html),id+' source button');
}
assert.ok(riskCompanies>=30,'Supported risk claims disappeared');
for(const id of ['micro1','aixi','turing'])for(const cl of data.claims.filter(c=>c.company_id===id&&c.subject==='risks'&&c.status!=='supported'))assert.ok(!section(id).includes(cl.id),cl.id+' is not supported');
const mercor=section('mercor');
assert.deepEqual(ids(mercor,'risk'),['mercor.claim.risks-0','mercor.claim.risks-1']);
assert.ok(visible(mercor).includes('As of Jun 2026'));assert.ok(mercor.includes('<time datetime="2026-06-25">'));assert.ok(visible(mercor).includes('Source date not stated'));
assert.equal(section('taskus'),'');

// Synthetic events: ordering, related companies, kinds and month-only dates.
const source=(publisher,url='https://example.com/'+publisher.toLowerCase())=>({url,title:publisher+' page',publisher,published_on:null,source_type:'news'});
const event=(id,company_id,date,kind,related=[])=>({id,company_id,related_company_ids:related,kind,date,date_basis:'reported',title:'Title '+id,detail:'Detail '+id,status:'Pending',status_checked_on:'2026-10-23',sources:[source('Pub'+id.split('.').pop())]});
window.COMPANY_EVENTS={version:'1.0.0',reviewed_on:'2026-10-23',events:[
 event('mercor.event.a','mercor','2025-09-03','lawsuit',['scale_ai']),
 event('mercor.event.b','mercor','2026-04','customer_change'),
 event('mercor.event.c','mercor','2026-04-01','data_incident'),
 event('mercor.event.aa','mercor','2026-04-01','workforce_change'),
 event('handshake_ai.event.x','handshake_ai','2026-07-20','filing'),
 {...event('taskus.event.esc','taskus','2026-01-02','lawsuit'),title:'<img src=x onerror=alert(1)> "quoted" & \'single\'',detail:'<script>alert(1)</script>',status:'</p><p>',sources:[source('<b>Bold</b>','https://example.com/?q="><script>x</script>'),source('Bad','javascript:alert(1)')]}
]};
const withEvents=section('mercor');
assert.deepEqual(ids(withEvents,'event'),['mercor.event.aa','mercor.event.c','mercor.event.b','mercor.event.a'],'Newest first; same date by id');
assert.ok(withEvents.indexOf('Dated events')<withEvents.indexOf('Risks named in the evidence'));assert.equal(withEvents.split(note).length,2);
const text=visible(withEvents);
for(const label of ['Apr 2026 Workforce change','Apr 2026 Data incident','Apr 2026 Customer change','Sep 2025 Lawsuit'])assert.ok(text.includes(label),label);
assert.ok(withEvents.includes('<time datetime="2026-04">Apr 2026</time>'));
assert.ok(/Title mercor\.event\.a<\/h4><p>Detail mercor\.event\.a<\/p><p class="risk-meta">Pending · <a href="https:\/\/example\.com\/puba" target="_blank" rel="noopener noreferrer">Puba /.test(withEvents),'Title, detail, status, then publisher links');
assert.deepEqual(ids(section('scale_ai'),'event'),['mercor.event.a'],'Related company sees the event');
assert.deepEqual(ids(section('handshake_ai'),'event'),['handshake_ai.event.x']);
assert.ok(visible(section('handshake_ai')).includes('Filing'));
assert.ok(!withEvents.includes('handshake_ai.event.x'));

// Escaping, unsafe links, and a section that exists only because of an event.
const escaped=section('taskus');
assert.deepEqual(ids(escaped,'event'),['taskus.event.esc']);assert.deepEqual(ids(escaped,'risk'),[]);
assert.ok(!escaped.includes('Risks named in the evidence'));
for(const raw of ['<img','<script','<b>','</p><p>','"quoted"','javascript:'])assert.ok(!escaped.includes(raw),'Unescaped '+raw);
for(const safe of ['&lt;img src=x onerror=alert(1)&gt; &quot;quoted&quot; &amp; &#39;single&#39;','&lt;script&gt;alert(1)&lt;/script&gt;','&lt;/p&gt;&lt;p&gt;','&lt;b&gt;Bold&lt;/b&gt;','href="https://example.com/?q=&quot;&gt;&lt;script&gt;x&lt;/script&gt;"'])assert.ok(escaped.includes(safe),'Missing '+safe);
assert.equal((escaped.match(/<a /g)||[]).length,1,'Only the https source becomes a link');
assert.ok(run(`profileHTML('taskus')`).includes('id="profile-risks"'));

// Hidden again once the sidecar is empty.
window.COMPANY_EVENTS={version:'1.0.0',events:[]};
assert.equal(section('taskus'),'');assert.ok(!run(`profileHTML('taskus')`).includes('id="profile-risks"'));

// The reviewed sidecar, when present, renders every event on each company it names.
let reviewed=0;
if(fs.existsSync(path.join(root,'data/company-events.json'))){
 window.COMPANY_EVENTS=readJSON('data/company-events.json');
 for(const c of data.companies){
  const html=run(`profileHTML(${JSON.stringify(c.id)})`),expected=window.COMPANY_EVENTS.events.filter(e=>e.company_id===c.id||e.related_company_ids.includes(c.id));
  assert.deepEqual(ids(html,'event').sort(),expected.map(e=>e.id).sort(),c.id);reviewed+=expected.length;
 }
}
assert.equal(run('JSON.stringify(DATA)'),original,'Presentation changed research');
console.log(JSON.stringify({companies_with_risk_claims:riskCompanies,synthetic_events:6,reviewed_event_placements:reviewed,canonical_unchanged:true,browser_verified:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-", str(canonical), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT)
assert hashlib.sha256(canonical.read_bytes()).hexdigest() == before
raise SystemExit(result.returncode)
