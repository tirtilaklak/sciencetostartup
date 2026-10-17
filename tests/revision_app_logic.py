"""Regression checks for the post-v15 app fixes; actual modules, no browser/build."""
import ast
import hashlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [ROOT / "data/canonical.json", ROOT / "data/medalists.json", ROOT / "web/assets/Investor_Snapshot_Human_Depth.png"]
before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
stub = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets))
assert 'id="financial-only"> Revenue figures</label>' in (ROOT / "web/index.html").read_text()
checks = r'''
const original=run('JSON.stringify(DATA)');
const visible=html=>html.replace(/<span\b[^>]*data-evidence-description\b[^>]*>[\s\S]*?<\/span>/g,'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
run('initialize()');
const forecasts=data.metrics.filter(m=>m.kind==='revenue'&&m.observation_status==='forecast');
assert.ok(forecasts.length>0,'Real forecast regression fixtures disappeared');
for(const m of forecasts){const html=run(`metricTile(DATA.metrics.find(m=>m.id===${JSON.stringify(m.id)}))`);assert.ok(html.includes('<h3>Period revenue</h3>'));assert.ok(visible(html).includes('Forecast'));assert.ok(!visible(html).includes('Actual period revenue'));assert.ok(html.includes(m.claim_id));}
const beforeFilter=['a-team','afterquery','appen','handshake_ai','imerit','invisible','mercor','micro1','prime_intellect','prolific','proximal','rws_trainai','scale_ai','snorkel_ai','surge_ai','taskus','toloka','turing'];
run('state.financial=true;renderDirectory()');
assert.deepEqual(plain(run('filtered().map(c=>c.id)')),beforeFilter,'Relabeling must not change revenue selection');
assert.ok(node('active-filters').innerHTML.includes('Revenue figures'));assert.ok(!node('active-filters').innerHTML.includes('Financial disclosure'));
run('state.financial=false');

const placeholder={textContent:''};node('compare-preset').querySelector=()=>placeholder;
const selections=[{ids:['taskus','appen','scale_ai'],value:'scale',label:'Choose an example'},{ids:['surge_ai','toloka','labelbox'],value:'work',label:'Choose an example'},{ids:['mercor','micro1'],value:'',label:'Custom selection'},{ids:[],value:'',label:'Choose an example'}];
for(const sample of selections){run(`setSelection(${JSON.stringify(sample.ids)})`);node('compare-preset').value='';node('compare-preset').callbacks.change({target:node('compare-preset')});assert.deepEqual(plain(run('state.selected')),sample.ids);assert.equal(node('compare-preset').value,sample.value);assert.equal(placeholder.textContent,sample.label);}

const expectedRelations={laude:['Anthropic','Benchmark adoption'],benchflow:['Hugging Face','Compute provider'],aixi:['Principles of Intelligence','Fiscal sponsor']};
for(const [id,terms]of Object.entries(expectedRelations)){const text=visible(run(`selectionFact('${id}')`));for(const term of terms)assert.ok(text.includes(term),id+': '+text);assert.ok(!text.includes('Claimed customer'),id);}
const groupedIds=run(`profileRelationships('laude')[0].claim_ids`).join('|'),groupedButton={dataset:{profileEvidence:groupedIds}};
node('company-dialog').open=true;let summaryOpenAtEvidence=null;node('evidence-dialog').showModal=function(){summaryOpenAtEvidence=node('company-dialog').open;this.open=true};
for(const handler of documentCallbacks.click)handler({target:{closest:selector=>selector==='[data-profile-evidence]'?groupedButton:null}});
assert.equal(summaryOpenAtEvidence,false,'Grouped quick-summary evidence must close its parent modal before opening');assert.equal(node('evidence-dialog').open,true);node('evidence-dialog').close();
const elorianUpdate=window.SOURCE_UPDATES.updates.find(update=>update.id==='elorian-platform-availability-2026-10-16');
assert.ok(elorianUpdate,'The approved Elorian release correction must be present');
assert.equal(elorianUpdate.company_id,'elorian');
assert.deepEqual(elorianUpdate.target,{product_name:'Visual-thinking foundation model',record_ids:['elorian.product.oct14-0'],claim_ids:['elorian.claim.oct14-product-0']});
assert.deepEqual(elorianUpdate.previous_fields,{description:'An unreleased model for spatial and physical reasoning. Early access has a waitlist.',status:'Unreleased; early-access waitlist'});
assert.deepEqual(elorianUpdate.replacement_fields,{description:'Glimpse is a visual-thinking model, offered through API and chat as a research preview.',status:'Research preview available · company-reported'});
assert.deepEqual(elorianUpdate.source,{url:'https://elorian.ai/blog/introducing-glimpse',title:'Introducing Glimpse',observed_on:'2026-10-16',published_on:'2026-10-16'});
const curatedBefore=JSON.stringify(window.PROFILE_CONTENT),updatesBefore=JSON.stringify(window.SOURCE_UPDATES);
const originalElorian=window.PROFILE_CONTENT.entries.find(entry=>entry.company_id==='elorian').products[0];
assert.deepEqual(originalElorian.claim_ids,elorianUpdate.target.claim_ids);assert.deepEqual(originalElorian.record_ids,elorianUpdate.target.record_ids);
for(const [field,value]of Object.entries(elorianUpdate.previous_fields))assert.equal(originalElorian[field],value);
assert.deepEqual(plain(run("claims['elorian.claim.oct14-product-0']")),elorianUpdate.historical_snapshot.claims.find(claim=>claim.id==='elorian.claim.oct14-product-0'));
const reviewedOfferingLabels={
 datacurve:{name:'RL environments',label:'AI practice environments',record:'datacurve.product.oct14-0',claim:'datacurve.claim.oct14-product-0',source:'datacurve.source.oct14-a5da84956a24',url:'https://datacurve.ai/products'},
 abundant_ai:{name:'Custom RL environments and datasets',label:'Custom AI practice environments and datasets',record:'abundant_ai.product.oct14-0',claim:'abundant_ai.claim.oct14-product-0',source:'abundant_ai.source.oct14-8fcc746dfc96',url:'https://www.abundant.ai/'}
};
let reviewedOfferingControls=0;
for(const id of ['elorian','datacurve','abundant_ai','polymath_ai_labs']){
 const html=run(`selectionFact('${id}')`),product=run(`profileProducts('${id}')[0]`),reviewed=reviewedOfferingLabels[id];
 if(reviewed){
  assert.equal(product.name,reviewed.name);assert.deepEqual(plain(product.record_ids),[reviewed.record]);assert.deepEqual(plain(product.claim_ids),[reviewed.claim]);
  const record=data.products.find(row=>row.id===reviewed.record),claim=data.claims.find(row=>row.id===reviewed.claim),source=data.sources.find(row=>row.id===reviewed.source);
  assert.equal(record.company_id,id);assert.equal(record.name,reviewed.name);assert.equal(record.claim_id,reviewed.claim);
  assert.equal(claim.company_id,id);assert.equal(claim.status,'supported');assert.equal(claim.as_of,'undated');assert.equal(claim.segment_scope,'ai_data');assert.deepEqual(claim.source_ids,[reviewed.source]);
  assert.equal(source.company_id,id);assert.equal(source.url,reviewed.url);
  const buttons=[...html.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)].map(match=>match[0]);
  assert.equal(buttons.length,1);assert.ok(buttons[0].includes('data-claim="'+reviewed.claim+'"'));assert.ok(buttons[0].endsWith('>'+reviewed.label+'</button>'));
  assert.ok(buttons[0].includes('aria-label="'+reviewed.label+' for '));assert.ok(html.includes(run(`publicText(claims[${JSON.stringify(reviewed.claim)}].statement)`)),'Original product statement remains in the bound description');
  assert.ok(visible(html).includes(reviewed.label));reviewedOfferingControls++;
 }else assert.ok(visible(html).includes(product.name));
 assert.ok(visible(html).includes('Offering'));assert.ok(!visible(html).includes('Claimed customer'));
 if(id==='elorian'){
  assert.deepEqual(plain(product.source_updates),[elorianUpdate]);
  assert.deepEqual(plain(product.claim_ids),elorianUpdate.target.claim_ids);assert.deepEqual(plain(product.record_ids),elorianUpdate.target.record_ids);
  assert.equal(product.status,elorianUpdate.replacement_fields.status);assert.equal(product.description,elorianUpdate.replacement_fields.description);
  assert.deepEqual([...html.matchAll(/data-source-update="([^"]+)"/g)].map(match=>match[1]),[elorianUpdate.id]);
  assert.deepEqual([...html.matchAll(/href="([^"]+)"/g)].map(match=>match[1]),[elorianUpdate.source.url]);
  assert.ok(visible(html).includes(elorianUpdate.replacement_fields.status));assert.ok(visible(html).includes('Checked 16 Oct 2026'));
  assert.ok(!html.includes('data-claim="elorian.claim.oct14-product-0"'),'The current release must not reuse the historical waitlist claim as its source');
 }else assert.ok(product.claim_ids.some(cid=>html.includes(cid)),id+' must retain its existing claim control');
}
assert.equal(reviewedOfferingControls,2);
// Explicitly exercise the old source layer as well. Its waitlist record and
// original claim control remain available when later corrections are disabled.
const savedSourceUpdates=window.SOURCE_UPDATES;
try{
 window.SOURCE_UPDATES=null;
 const product=plain(run("profileProducts('elorian')[0]")),html=run("selectionFact('elorian')");
 assert.deepEqual(product,originalElorian);
 assert.ok(visible(html).includes('Unreleased; early-access waitlist'));
 assert.deepEqual([...html.matchAll(/data-claim="([^"]+)"/g)].map(match=>match[1]),['elorian.claim.oct14-product-0']);
 assert.ok(!html.includes('data-source-update=')&&!html.includes(elorianUpdate.source.url));
}finally{window.SOURCE_UPDATES=savedSourceUpdates;}
assert.equal(JSON.stringify(window.PROFILE_CONTENT),curatedBefore);assert.equal(JSON.stringify(window.SOURCE_UPDATES),updatesBefore);
let summaries=0;
for(const c of data.companies){const html=run(`selectionFact(${JSON.stringify(c.id)})`);assert.ok(!html.includes('[object Object]'));if(run(`preferredFinancial(${JSON.stringify(c.id)})`))assert.equal(html.replace(/evidence-description-\d+/g,'evidence-description-ID'),run(`compactSignal(${JSON.stringify(c.id)})`).replace(/evidence-description-\d+/g,'evidence-description-ID'));for(const match of html.matchAll(/data-claim="([^"]+)"/g))assert.ok(data.claims.some(cl=>cl.id===match[1]&&cl.company_id===c.id));summaries++;}
const expectedCapital={taskus:['$303.6M','2021-06-10','Includes existing shares sold by shareholders.','not all new company funding.','taskus.claim.financing-2'],scale_ai:['$1.6B','2025-06-11','Includes primary financing and sales of existing shares','not a pure new-capital total.','scale_ai.claim.major-total_funding'],labelbox:['$100M','2026-10-14','Includes equity and credit.','Component amounts and credit drawdown are undisclosed.','labelbox.claim.oct14-series-e']};
for(const [id,terms]of Object.entries(expectedCapital)){const html=run(`compactFundingSummary('${id}')`),text=visible(html);for(const term of terms.slice(0,-1))assert.ok(text.includes(term),id+': '+text);assert.ok(html.includes(terms.at(-1)));}

// The DOM fixture models the route destinations, modal closure and deferred
// frame independently. It deliberately leaves the dialog open during navigation.
const frames=[],events=[];context.requestAnimationFrame=cb=>frames.push(cb);
function focusNode(id,tag='SECTION',parent=null){const n=node(id);n.tagName=tag;n.parentElement=parent;n.isConnected=true;n.focus=()=>{document.activeElement=n;events.push('focus:'+id)};n.scrollIntoView=()=>events.push('scroll:'+id);return n;}
const heading=focusNode('route-heading','H1'),tabs=focusNode('route-tabs','NAV'),archive=focusNode('route-archive','DETAILS'),questions=focusNode('route-questions','DETAILS',archive);
const destinations={sources:focusNode('profile-sources','SECTION',archive),questions:focusNode('profile-questions','DIV',questions),finance:focusNode('profile-finance'),work:focusNode('profile-pane-work')};
document.querySelector=s=>s==='.view:not([hidden]) h1'?heading:s==='.profile-tabs'?tabs:s.startsWith('[data-profile-')?destinations[s.match(/="([^"]+)"/)?.[1]]||null:null;
document.body=focusNode('body','BODY');
let historyTransitions=0;
for(const c of data.companies)for(const section of ['sources','questions','capital','work']){
 const destination=destinations[section==='capital'?'finance':section];archive.open=false;questions.open=false;events.length=0;
 node('evidence-dialog').open=true;location.hash='#company/'+c.id+'/'+section;run(`route({type:'hashchange'})`);while(frames.length)frames.shift()();
 assert.equal(node('evidence-dialog').open,false);assert.equal(document.activeElement,destination,c.id+'/'+section+' lost destination focus');assert.equal(events.at(-1),'scroll:'+(section==='work'?'route-tabs':destination.id));
 if(['sources','questions'].includes(section))assert.equal(archive.open,true);if(section==='questions')assert.equal(questions.open,true);historyTransitions++;
}
let repeatedLinks=0;
for(const c of data.companies)for(const section of ['sources','questions']){
 location.hash='#company/'+c.id+'/'+section;archive.open=false;questions.open=false;let prevented=false;
 const link={getAttribute:key=>key==='href'?location.hash:null,hasAttribute:()=>false};
 context.repeatEvent={target:{closest:()=>link},button:0,preventDefault(){prevented=true}};run('repeatCompanyRoute(repeatEvent)');
 assert.equal(prevented,true);assert.equal(archive.open,true);assert.equal(document.activeElement,destinations[section]);if(section==='questions')assert.equal(questions.open,true);repeatedLinks++;
}
for(const modifier of ['metaKey','ctrlKey','shiftKey','altKey']){let prevented=false;context.repeatEvent={target:{closest:()=>({getAttribute:key=>key==='href'?location.hash:null,hasAttribute:()=>false})},[modifier]:true,preventDefault(){prevented=true}};run('repeatCompanyRoute(repeatEvent)');assert.equal(prevented,false,'Modified links must preserve browser behavior');}
// Missing profile adapters are supported by the base-module harness.
run('const savedRelationships=profileRelationships,savedProducts=profileProducts,savedReferences=profileReferences,savedLabel=relationshipLabel;profileRelationships=undefined;profileProducts=undefined;profileReferences=undefined;relationshipLabel=undefined');
assert.ok(run(`selectionFact('elorian')`).includes('Offering'));run('profileRelationships=savedRelationships;profileProducts=savedProducts;profileReferences=savedReferences;relationshipLabel=savedLabel');
assert.equal(run('JSON.stringify(DATA)'),original,'Presentation changed research');
console.log(JSON.stringify({forecast_metrics:forecasts.length,revenue_filter_unchanged:beforeFilter.length,preset_transitions:selections.length,company_summaries:summaries,reviewed_offering_controls:reviewedOfferingControls,capital_qualifications:3,dialog_open_history_transitions:historyTransitions,repeated_section_links:repeatedLinks,modified_link_cases:4,elorian_source_update_compatibility_cases:2,elorian_raw_and_curated_history_unchanged:true,core_fallback:true,canonical_unchanged:true,browser_verified:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-", str(ROOT / "data/canonical.json"), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT)
assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before
raise SystemExit(result.returncode)
