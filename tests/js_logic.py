"""Exercise the delivered JS modules with a DOM stub; this is not browser QA.

The synthetic fixture checks every rubric combination. The real dataset run loads
all presentation modules and JSON inputs in the build's order before initialize.
"""
import itertools, json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from observatory import classify, stage_confidence
from fixtures import fixture

STUB=r'''
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const [dataPath,root,expectedPath]=process.argv.slice(2),data=JSON.parse(fs.readFileSync(dataPath,'utf8'));
const synthetic=data.companies[0].id==='test-alpha',readJSON=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const nodes={},boxes=[],documentCallbacks={},windowCallbacks={};
function node(id){return nodes[id]??={id,textContent:'',innerHTML:'',value:'',hidden:false,dataset:{},callbacks:{},addEventListener(k,f){this.callbacks[k]=f},setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},showModal(){this.open=true},close(){this.open=false},scrollIntoView(){},focus(){},click(){},insertAdjacentHTML(where,html){this.innerHTML=where==='afterbegin'?html+this.innerHTML:this.innerHTML+html}};}
node('research-data').textContent=JSON.stringify(data);
const document={getElementById:node,querySelectorAll:s=>s==='[data-compare]'?boxes:[],querySelector:()=>null,createElement:()=>node('created'),addEventListener(k,f){(documentCallbacks[k]??=[]).push(f)}};
const location={hash:'#market'};
// Match observatory.py's optional single-company profile overlay exactly.
const profileData=readJSON('data/profile-content.json'),afterqueryPath=path.join(root,'data/profile-afterquery.json');
if(fs.existsSync(afterqueryPath))profileData.entries=profileData.entries.filter(entry=>entry.company_id!=='afterquery').concat(JSON.parse(fs.readFileSync(afterqueryPath,'utf8')));
const window={scrollY:0,scrollTo(){},addEventListener(k,f){(windowCallbacks[k]??=[]).push(f)},EDITORIAL:readJSON('data/editorial.json'),LOGOS:readJSON('data/logo-provenance.json'),WORK_ROUTES:synthetic?{routes:[]}:readJSON('data/work-routes.json'),PROFILE_CONTENT:profileData,RESEARCH_ALIASES:readJSON('docs/research-id-crosswalk.json')};
window.SOURCE_UPDATES=readJSON('data/source-updates.json');
const history={replaceState(state,title,hash){location.hash=hash;}};
let downloadedBlob;
class CaptureURL extends URL {static createObjectURL(blob){downloadedBlob=blob;return 'blob:test'}static revokeObjectURL(){}}
const context=vm.createContext({document,window,history,location,Intl,Set,Map,Date,JSON,URL:CaptureURL,Blob,queueMicrotask,setTimeout:()=>{},clearTimeout:()=>{},console});
// The icon script runs first. This stub's window is separate from its global.
// Combining the remaining modules matches declaration hoisting in the build.
const modules=['web/icons.js','web/app.js','web/editorial.js','web/work-v3.js','web/work-v4.js','web/profiles-v2.js','web/source-updates.js'];
vm.runInContext(fs.readFileSync(path.join(root,modules[0]),'utf8'),context);
context.iconHTML=window.iconHTML;
assert.equal(typeof context.iconHTML,'function');
vm.runInContext(modules.slice(1).map(f=>fs.readFileSync(path.join(root,f),'utf8')).join('\n'),context);
const run=s=>vm.runInContext(s,context),plain=v=>JSON.parse(JSON.stringify(v));
const click=button=>{for(const handler of documentCallbacks.click||[])handler({target:{closest:s=>s==='button'?button:null}});};
const button=dataset=>({dataset,hasAttribute:()=>false});

(async()=>{
 if(synthetic){
  let checked=0;
  for(const expected of readJSONFrom(expectedPath)){
   run(`Object.entries(${JSON.stringify(expected.levels)}).forEach(([k,v])=>DATA.assessments[0].gates[k].level=v)`);
   assert.equal(run('stageFor("test-alpha")'),expected.stage);
   assert.equal(run('stageConfidence("test-alpha")'),expected.confidence);checked++;
  }
  assert.equal(checked,256);assert.equal(run('filtered().length'),1);
  assert.ok(run('profileHTML("test-alpha")').includes('test-round'));
  console.log(JSON.stringify({entities:1,rubric_combinations:checked,browser_rendering_verified:false}));return;
 }
 run('initialize()');
 assert.equal(data.companies.length,39);assert.equal(run('filtered().length'),39);
 assert.equal((node('company-cards').innerHTML.match(/data-company-card=/g)||[]).length,39);
 assert.equal(Number(node('source-count').textContent),data.sources.length);
 assert.ok(node('stage').innerHTML.includes('value="established_commercial_evidence"'));
 assert.ok(!node('coverage-notes').innerHTML.match(/blocker|QA remains|publication|authorization/i));

 // Every typed record and source remains inspectable on its company's profile.
 const presentationFailures=[];
 let curatedProducts=0,relationshipsChecked=0,svgControlsChecked=0;
 const checkSvgControls=(html,label)=>{
  let rawArrows=0;
  for(const match of html.matchAll(/<(?:a|button)\b[^>]*>[\s\S]*?<\/(?:a|button)>/g)){
   if(/[↗→←]/.test(match[0]))rawArrows++;
   for(const svg of match[0].matchAll(/<svg\b[^>]*class="ui-icon"[^>]*>/g)){
    assert.ok(svg[0].includes('aria-hidden="true"')&&svg[0].includes('focusable="false"'),label+' decorative icon semantics');svgControlsChecked++;
   }
  }
  if(rawArrows)presentationFailures.push(label+': '+rawArrows+' controls still use raw arrow glyphs');
 };
 const curated=window.PROFILE_CONTENT.entries;
 assert.ok(curated.length>0,'Curated profile content is missing');
 assert.equal(new Set(curated.map(e=>e.company_id)).size,curated.length,'Duplicate curated profiles');
 for(const entry of curated)assert.ok(data.companies.some(c=>c.id===entry.company_id),'Unknown curated company '+entry.company_id);
 let referenced=0;
 for(const c of data.companies){
  const html=run(`profileHTML(${JSON.stringify(c.id)})`);
  assert.ok(html.includes(c.name.replaceAll('&','&amp;')),c.id);assert.ok(!html.includes('[object Object]'));assert.ok(!html.includes('&quot;verification_label&quot;'));
  for(const table of ['products','funding_rounds','company_people','company_investors','customer_evidence'])for(const row of (data[table]||[]).filter(r=>r.company_id===c.id)){assert.ok(html.includes(row.id),table+' missing from profile: '+row.id);referenced++;}
  for(const src of data.sources.filter(s=>s.company_id===c.id||s.id.startsWith(c.id+'.source.')))assert.ok(html.includes(src.id),'source missing '+src.id);
  for(const cl of data.claims.filter(r=>r.company_id===c.id&&r.subject==='worker opportunities'))assert.ok(html.includes(cl.id),'work claim missing '+cl.id);
  checkSvgControls(html,c.id+' profile');
  const config=curated.find(entry=>entry.company_id===c.id);
  for(const product of config?.products||[]){
   const name=run(`attr(${JSON.stringify(product.name)})`);
   assert.ok(html.includes('data-profile-product="'+name+'"'),c.id+' curated product absent: '+product.name);
   const presented=plain(run(`profileProducts(${JSON.stringify(c.id)})`)).find(row=>row.name===product.name);
   assert.ok(html.includes(run(`esc(${JSON.stringify(presented.description)})`)),c.id+' current product description absent: '+product.name);
   for(const id of product.record_ids||[])assert.ok(data.products.some(r=>r.id===id&&r.company_id===c.id),c.id+' invalid product source record '+id);
   for(const id of product.claim_ids||[])assert.ok(data.claims.some(r=>r.id===id),c.id+' invalid product claim '+id);
   curatedProducts++;
  }
  for(const relation of plain(run(`profileRelationships(${JSON.stringify(c.id)})`))){
   const name=String(relation.name||'').trim();relationshipsChecked++;
   if(!name||name.length>75||/[:;]/.test(name)||/\b(?:unnamed|undisclosed|anonymous|named as|describes?|supports?|claimed|reported collaborations|lists?|credits|frontier labs|unverified customer)\b/i.test(name))presentationFailures.push(c.id+': relationship heading contains prose or unresolved identity: '+name);
   assert.ok(html.includes('data-profile-relationship="'+run(`attr(${JSON.stringify(name)})`)+'"'),c.id+' named relationship absent: '+name);
  }
 }
 // AfterQuery's overlay must replace the generic entry, preserving distinct roles.
 const afterquery=curated.filter(entry=>entry.company_id==='afterquery');assert.equal(afterquery.length,1);
 assert.equal(afterquery[0].products.length,8);assert.equal(afterquery[0].relationships.length,6);
 const afterqueryProducts=run(`profileProductGrid('afterquery')`),afterqueryPeople=run(`profilePeople('afterquery')`),afterqueryRelations=run(`profileRelationshipGrid('afterquery')`);
 assert.equal((afterqueryProducts.match(/data-profile-product=/g)||[]).length,8);
 for(const product of afterquery[0].products){
  assert.ok(product.claim_ids?.length,'AfterQuery product has no source: '+product.name);
  const productCard=[...afterqueryProducts.matchAll(/<article class="offering-card"[\s\S]*?<\/article>/g)].map(match=>match[0]).find(html=>html.includes('data-profile-product="'+run(`attr(${JSON.stringify(product.name)})`)+'"'));
  assert.ok(productCard,'AfterQuery product missing: '+product.name);
  for(const claimId of product.claim_ids)assert.ok(productCard.includes(claimId),'AfterQuery product source missing: '+claimId);
 }
 for(const [personId,name,role] of [['afterquery.person.spencer-mateega','Spencer Mateega','Co-founder · CEO'],['afterquery.person.carlos-georgescu','Carlos Georgescu','Co-founder · CTO']]){
  const person=afterquery[0].people.find(p=>p.person_id===personId);assert.ok(person,'AfterQuery leader missing: '+personId);assert.equal(person.role,role);
  assert.equal(data.people.find(p=>p.id===personId)?.name,name);
  const card=[...afterqueryPeople.matchAll(/<article class="leadership-card"[\s\S]*?<\/article>/g)].map(match=>match[0]).find(html=>html.includes('<h3>'+name+'</h3>'));
  assert.ok(card?.includes('<p class="leadership-role">'+role+'</p>'),'Wrong rendered leadership role for '+name);
  for(const claimId of person.claim_ids)assert.ok(card.includes(claimId),'Leadership source missing: '+claimId);
 }
 const thinkingMachines=afterquery[0].relationships.filter(r=>r.name==='Thinking Machines Lab');
 assert.equal(thinkingMachines.length,2);assert.deepEqual(thinkingMachines.map(r=>r.relationship).sort(),['dataset_user','technology_vendor']);
 assert.equal((afterqueryRelations.match(/data-profile-relationship="Thinking Machines Lab"/g)||[]).length,2);
 assert.equal(new Set(thinkingMachines.flatMap(r=>r.claim_ids)).size,2,'Distinct Thinking Machines roles require distinct evidence');
 for(const relation of thinkingMachines)for(const claimId of relation.claim_ids)assert.ok(afterqueryRelations.includes(claimId),'Thinking Machines role evidence missing: '+claimId);
 const performance=run(`profilePerformance('afterquery')`);
 assert.ok(performance.includes('35.3')&&performance.includes('46.7'),'Warmup comparison values missing');
 assert.ok(performance.includes('Scale zero to 100'),'Performance chart must disclose its scale');
 assert.ok(performance.includes(run(`esc(${JSON.stringify(afterquery[0].performance_chart.qualification)})`)),'Warmup attribution qualification missing');
 for(const claimId of afterquery[0].performance_chart.claim_ids)assert.ok(performance.includes(claimId),'Performance experiment source missing');
 assert.equal(run(`esc('<script>"x"</script>')`),'&lt;script&gt;&quot;x&quot;&lt;/script&gt;');
 assert.ok(!run(`external('javascript:alert(1)','bad')`).includes('href'));
 for(const value of ['=1+1','+1','@SUM(1)','-1','\tvalue'])assert.ok(run(`csvCell(${JSON.stringify(value)})`).startsWith('"\''));
 assert.equal(run(`publicText('Founding year: 2,023.')`),'Founding year: 2023.');
 assert.equal(run(`publicText('https://example.com/a_b')`),'https://example.com/a_b');
 assert.ok(run('DATA.claims.every(c=>esc(c.id)===c.id)&&DATA.sources.every(s=>esc(s.id)===s.id)'));
 assert.ok(run('workRouteRows().every(r=>workRouteAttr(r.id)===r.id)'));

 // Group membership and filtering must use the complete, non-overlapping universe.
 const groups=plain(run('MODEL_GROUPS')),grouped=Object.values(groups).flat();
 assert.equal(Object.keys(groups).length,7);assert.equal(grouped.length,39);assert.equal(new Set(grouped).size,39);
 assert.deepEqual([...grouped].sort(),data.companies.map(c=>c.id).sort());
 assert.deepEqual(Object.fromEntries(Object.entries(groups).map(([name,ids])=>[name,ids.length])),{
  'Expert data & evaluation':9,'Managed AI & data services':11,'Frontier data & RL environments':10,
  'AI software & analytics':2,'AI evaluation & safety':3,'Compute & model research':2,'Nonprofit research':2
 });
 assert.equal(window.EDITORIAL.entries.length,39);
 for(const company of data.companies){
  const entries=window.EDITORIAL.entries.filter(e=>e.company_id===company.id);assert.equal(entries.length,1,company.id);
  assert.equal(run(`modelGroup(${JSON.stringify(company.id)})`),entries[0].primary_offering,company.id+' primary offering drift');
 }
 assert.deepEqual([...groups['AI software & analytics']].sort(),['hackerrank','quesma']);
 for(const id of ['labelbox','snorkel_ai']){
  const primary='Frontier data & RL environments',escaped=run(`esc(groupLabel(${JSON.stringify(primary)}))`);
  assert.equal(run(`modelGroup('${id}')`),primary);assert.ok(groups[primary].includes(id));
  assert.ok(run(`card(companies['${id}'])`).includes(`<span class="category-label sr-only">${escaped}</span>`),id+' card primary');
  assert.ok(run(`profileHTML('${id}')`).includes(`<p class="profile-category">${escaped}</p>`),id+' profile primary');
  assert.ok(run(`comparisonRows().find(([label])=>label==='Main offering')[1]('${id}')`).includes(`<span class="category-label">${escaped}</span>`),id+' comparison primary');
  const softwareTags=window.EDITORIAL.entries.find(e=>e.company_id===id).capability_tags.filter(tag=>/software/i.test(tag));
  assert.ok(softwareTags.length,id+' retains secondary software capability');
  for(const tag of softwareTags)assert.ok(run(`card(companies['${id}'])`).includes(run(`esc(${JSON.stringify(tag)})`)),id+' software tag visible');
 }
 for(const [group,ids] of Object.entries(groups)){run(`state.category=${JSON.stringify(group)}`);assert.deepEqual(plain(run('filtered().map(c=>c.id)')).sort(),[...ids].sort());}
 run(`reset();state.query='Astra'`);assert.ok(run(`filtered().some(c=>c.id==='hackerrank')`));
 run(`state.query='zzzzz-absent';renderDirectory()`);assert.equal(run('filtered().length'),0);assert.equal(node('empty-state').hidden,false);
 run(`state.financial=true;state.work=true;state.category='bad';reset()`);assert.equal(run('filtered().length'),39);
 run(`state.work=true`);assert.ok(run(`filtered().some(c=>c.id==='imerit')`));assert.ok(!run(`filtered().some(c=>c.id==='hackerrank')`));run('reset()');
 for(const [alias,id] of Object.entries(window.RESEARCH_ALIASES)){location.hash='#company/'+alias;run('route()');assert.equal(location.hash,'#company/'+id);assert.ok(node('profile-view').innerHTML.includes(data.companies.find(c=>c.id===id).name.replaceAll('&','&amp;')));}
 location.hash='#market';run('route()');

 // Selection preserves identity across repeated controls and rejects a fourth.
 for(const id of ['mercor','snorkel_ai','labelbox','appen','g2i','surge_ai','toloka'])for(const view of ['directory','work','profile'])boxes.push({dataset:{compare:id},checked:false,view});
 run(`setSelection(['mercor','snorkel_ai','labelbox','appen'])`);assert.equal(run('state.selected.length'),3);assert.ok(boxes.filter(b=>b.dataset.compare==='mercor').every(b=>b.checked));
 boxes.filter(b=>b.dataset.compare==='g2i').forEach(b=>b.checked=true);run(`chooseCompare('g2i',true)`);assert.ok(boxes.filter(b=>b.dataset.compare==='g2i').every(b=>!b.checked));
 assert.equal((node('compare-content').innerHTML.match(/data-comparison-row=/g)||[]).length,9);assert.equal((node('compare-content').innerHTML.match(/data-comparison-company=/g)||[]).length,27);
 node('clear-compare').callbacks.click();assert.ok(boxes.every(b=>!b.checked));assert.equal(run('state.selected.length'),0);
 node('compare-preset').value='work';node('compare-preset').callbacks.change({target:node('compare-preset')});assert.deepEqual(plain(run('state.selected')),['surge_ai','toloka','labelbox']);assert.ok(boxes.filter(b=>b.dataset.compare==='surge_ai').every(b=>b.checked));
 run('setSelection([])');assert.equal((node('compare-content').innerHTML.match(/data-mobile-compare=/g)||[]).length,3);assert.ok(node('compare-content').innerHTML.includes('TaskUs + Appen'));assert.ok(node('compare-content').innerHTML.includes('data-mobile-compare="2"'));click(button({mobileCompare:'1'}));assert.equal(run('state.mobileCompare'),1,'Default example must reach final company');
 assert.ok(/data-comparison-company="scale_ai" class=""/.test(node('compare-content').innerHTML));run('setSelection([])');

 // Routes ignore hash queries and letter case, land on in-page sections and carry the comparison.
 for(const [hash,view] of [['#work?utm_source=x','work'],['#venture','market'],['#about','method']]){location.hash=hash;run('route()');assert.equal(node(view+'-view').hidden,false,hash);assert.equal(location.hash,hash,hash+' must stay linkable');}
 location.hash='#market';run('route()');assert.equal(run('document.title'),'Overview · ScienceToStartup');
 location.hash='#company/Scale_AI/WORK';run('route()');assert.ok(node('profile-view').innerHTML.includes('data-profile-pane="work">'),'Section case must not hide the Paid work tab');
 location.hash='#compare/mercor,Handshake_AI,unknown,mercor';run('route()');assert.deepEqual(plain(run('state.selected')),['mercor','handshake_ai']);assert.equal(location.hash,'#compare/mercor,handshake_ai');
 run(`chooseCompare('appen',true)`);assert.equal(location.hash,'#compare/mercor,handshake_ai,appen');run('setSelection([])');assert.equal(location.hash,'#compare');location.hash='#market';run('route()');

 // Curated profile headings render as text.
 const headed=curated.find(entry=>entry.traction_heading),heading=headed.traction_heading;headed.traction_heading='<b>x</b>';
 const tractionHeading=run(`profileHTML(${JSON.stringify(headed.company_id)})`).match(/data-profile-section="traction"><h2>([\s\S]*?)<\/h2>/)[1];headed.traction_heading=heading;
 assert.equal(tractionHeading,'&lt;b&gt;x&lt;/b&gt;');assert.ok(!tractionHeading.includes('<'),'Profile heading h2 must have no element children');

 // Role routes, pay units and availability remain separate, with no company pay band.
 const routes=window.WORK_ROUTES.routes;assert.equal(run('filteredWork().length'),routes.length);
 assert.ok(routes.length>39);assert.equal(new Set(routes.map(r=>r.id)).size,routes.length);
 run(`state.workQuery='AIXI';renderWork()`);assert.deepEqual(plain(run('filteredWork().map(r=>r.company_id)')),routes.filter(r=>r.company_id==='aixi').map(r=>r.company_id));assert.ok(node('work-count').textContent.includes('1 organization'));node('work-reset').callbacks.click();
 for(const route of routes){
  const html=run(`workCard(${JSON.stringify(route)})`),details=html.slice(html.indexOf('<details class="w4-details">'));
  assert.ok(html.includes('data-work-route="'+route.id+'"'),route.id);assert.ok(html.includes(run(`esc(${JSON.stringify(route.role)})`)));
  assert.ok(html.includes('<summary>Terms & sources'),route.id+' missing terms disclosure');
  assert.ok(details.includes('<dt>Payment</dt><dd>'+run(`esc(${JSON.stringify(route.pay_label)})`)+'</dd>'),route.id+' original pay terms missing from details');
  if(route.status==='pay_conflict'||route.pay_basis==='conflicting_hourly')assert.ok(html.split('<details class="w4-details">')[0].includes('Rate conflict'),route.id+' missing conflict summary');
  checkSvgControls(html,route.id+' work card');
 }
 run(`state.workPay='numeric'`);assert.ok(run('filteredWork().every(r=>r.numeric_pay)'));assert.ok(run(`filteredWork().some(r=>r.company_id==='g2i')`));assert.ok(!run(`filteredWork().some(r=>r.company_id==='handshake_ai')`));
 run(`state.workEligibility='US listing evidence'`);assert.ok(run(`filteredWork().every(r=>r.eligibility==='US listing evidence')`));assert.ok(run(`filteredWork().some(r=>r.company_id==='terac')`));
 run(`state.workPay='';state.workEligibility='';state.workGroup='Research fellowship'`);for(const id of ['surge_ai','proximal','aixi'])assert.ok(run(`filteredWork().some(r=>r.company_id==='${id}')`),id);
 node('work-reset').callbacks.click();assert.equal(run('filteredWork().length'),routes.length);
 const after=routes.filter(r=>r.company_id==='afterquery');assert.ok(after.length>=3);assert.ok(after.some(r=>r.role.includes('World Models')&&r.pay_label.includes('150')));assert.ok(after.some(r=>r.role.includes('College')&&r.status==='pay_conflict'));
 assert.ok(routes.some(r=>r.company_id==='benchflow'&&r.status==='paused'&&!r.numeric_pay));
 assert.ok(routes.some(r=>r.company_id==='prime_intellect'&&r.status==='contributions'&&!r.numeric_pay));
 assert.ok(routes.some(r=>r.company_id==='elorian'&&r.role==='Model Safety Contractor'&&r.pay_label.includes('75–125')));
 assert.ok(!routes.some(r=>r.company_id==='ooak'&&/300.*K/.test(r.pay_label)),'Corporate licensing value must not become worker pay');
 for(const id of ['aixi','g2i','toloka'])assert.ok(run(`workSummary('${id}')`).includes('data-work-route='));

 // Current financial claims stay distinct from actual revenues, historical talks,
 // funding, acquisition consideration, short periods and out-of-scope parent sales.
 for(const [id,kind,value] of [['bespoke_labs','funding_total_reported',40000000],['elorian','funding_total_reported',55000000],['snorkel_ai','funding_total_calculated',585000000],['mercor','funding_total_calculated',483600000]])assert.equal(run(`metricFor('${id}','${kind}').value`),value);
 assert.equal(run(`metricFor('rws_trainai','revenue').currency`),'GBP');
 const mercorProfile=run(`profileHTML('mercor')`);assert.ok(mercorProfile.includes('Unconfirmed valuation · Talks'));assert.ok(mercorProfile.includes('class="metric-tile unconfirmed-metric"'));assert.ok(mercorProfile.indexOf('$10B')<mercorProfile.indexOf('$20B'));
 assert.equal(run(`preferredFinancial('micro1').id`),'micro1.metric.oct14-q3-run-rate');assert.equal(run(`preferredFinancial('micro1').qualifier`),'greater_than');assert.equal(run(`metricValue(preferredFinancial('micro1'))`),'> $1B');
 assert.equal(run(`metricFor('micro1','valuation').value`),4000000000);assert.equal(run(`metricFor('micro1','valuation').observation_status`),'reported');assert.equal(run(`metricFor('micro1','valuation').as_of`),'2026-10-12');
 assert.equal(run(`claims['micro1.claim.major-valuation-metric'].status`),'superseded');assert.equal(run(`DATA.metrics.find(m=>m.id==='micro1.metric.major-valuation').observation_status`),'talks');assert.ok(run(`profileHTML('micro1')`).includes('micro1.claim.major-valuation-metric'));
 assert.ok(!run(`profileHTML('micro1')`).includes('Founded 2022'));assert.equal(run(`DATA.funding_rounds.find(r=>r.id==='micro1.round.major-1').amount`),undefined);
 assert.equal(run(`preferredFinancial('taskus').value`),214218000);assert.equal(run(`preferredFinancial('taskus').segment_scope`),'ai_data');assert.equal(run(`preferredFinancial('taskus').kind`),'revenue');
 assert.equal(run(`preferredFinancial('snorkel_ai').value`),375000000);assert.equal(run(`preferredFinancial('snorkel_ai').kind`),'annualized_revenue_run_rate');
 assert.equal(run(`preferredFinancial('turing').id`),'turing.metric.major-growth_metrics-1');assert.equal(run(`preferredFinancial('turing').value`),300000000);assert.equal(run(`preferredFinancial('turing').as_of`),'2024-12');assert.equal(run(`preferredFinancial('turing').kind`),'annualized_revenue_run_rate');
 assert.ok(run(`profileHTML('turing')`).includes('turing.metric.major-growth_metrics-0'),'Undated pricing observation remains inspectable');assert.equal(run(`DATA.metrics.find(m=>m.id==='turing.metric.major-growth_metrics-0').value`),167000000);
 assert.equal(run(`preferredFinancial('appen').value`),119915000);assert.equal(run(`financialPeriod(preferredFinancial('appen'))`),'half');
 assert.equal(run(`preferredFinancial('handshake_ai').qualifier`),'nearly');assert.equal(run(`preferredFinancial('handshake_ai').segment_scope`),'ai_data');
 run(`state.revenuePeriod='annual';state.revenueCurrency='USD';renderCharts()`);assert.ok(node('revenue-chart').innerHTML.includes('$870M'));assert.ok(node('revenue-chart').innerHTML.includes('$230.8M'));assert.ok(!node('revenue-chart').innerHTML.includes('$614M'));
 run(`state.revenuePeriod='half';renderCharts()`);assert.ok(node('revenue-chart').innerHTML.includes('$614M'));assert.ok(node('revenue-chart').innerHTML.includes('$119.92M'));assert.ok(!node('revenue-chart').innerHTML.includes('$239.8M'));
 run(`state.runratesExpanded=true;renderCharts()`);assert.ok(node('runrate-chart').innerHTML.includes('$375M'));assert.ok(node('runrate-chart').innerHTML.includes('Gross or net revenue not stated'));assert.ok(!node('runrate-chart').innerHTML.includes('End-May annualized-revenue target'));
 for(const id of ['appen','taskus'])assert.ok(run(`growthHTML('${id}')`).includes(`data-growth-trend="${id}"`));assert.ok(!run(`growthHTML('toloka')`).includes('data-growth-trend='));
 for(const [id,stage] of [['taskus','visible_operating_offer'],['imerit','repeatable_commercial_evidence'],['sama','established_commercial_evidence']])assert.equal(run(`stageFor('${id}')`),stage);
 for(const id of ['aixi','rws_trainai'])assert.equal(run(`DATA.funding_rounds.filter(r=>r.company_id==='${id}').length`),0);
 for(const [id,value] of [['handshake_ai',1500000000],['scale_ai',3500000000],['scale_ai',29000000000]])assert.equal(run(`uniqueMetrics('${id}').filter(m=>m.kind==='valuation'&&m.value===${value}).length`),1);
 assert.ok(run(`profileHTML('toloka')`).includes('First sale: 2025-05-02'));assert.ok(run(`profileHTML('appen')`).includes('New company funding: AUD 9.85M'));
 assert.ok(run(`fundingSummary('handshake_ai')`).includes('$434M'));assert.ok(run(`profileHTML('labelbox')`).includes('2026-10-14'));
 const labelboxMixed=data.funding_rounds.find(r=>r.id==='labelbox.round.oct14-equity');assert.equal(labelboxMixed.capital_type,'mixed');assert.equal(labelboxMixed.amount_basis,'undisclosed');assert.equal(labelboxMixed.qualifier,'greater_than');assert.equal(labelboxMixed.include_in_total,false);assert.equal(data.funding_rounds.find(r=>r.id==='labelbox.round.oct14-credit').parent_round_id,labelboxMixed.id);assert.ok(run(`profileCapital('labelbox')`).includes('Pre-money valuation'));const selectedLabelbox=data.funding_rounds.filter(r=>r.company_id==='labelbox'&&r.include_in_disclosed_primary_sum);assert.ok(selectedLabelbox.every(r=>r.qualifier==='exact'&&r.capital_type==='equity'));
 assert.ok(run(`disclosedPrimarySummary('labelbox')`).includes(run(`metricValue({value:${selectedLabelbox.reduce((n,r)=>n+r.amount,0)},unit:'currency',currency:'USD',qualifier:'exact'})`)));

 // Download handlers preserve the complete canonical object and numerical bounds.
 node('download-json').callbacks.click();assert.deepEqual(JSON.parse(await downloadedBlob.text()),data);
 run('exportCsv()');const csv=await downloadedBlob.text(),header=csv.split('\r\n')[0];
 for(const field of ['financial_qualifier','financial_display','upper_value','observation_status','metric_period','metric_scope','scope_detail'])assert.ok(header.includes('"'+field+'"'));
 const microLine=csv.split('\r\n').find(line=>line.startsWith('"micro1",'));assert.ok(microLine.includes('"greater_than"'));assert.ok(microLine.includes('"> $1B"'));
 const handshakeLine=csv.split('\r\n').find(line=>line.startsWith('"handshake_ai",'));assert.ok(handshakeLine.includes('"nearly"'));assert.ok(handshakeLine.includes('"Nearly $1B"'));
 assert.equal(csv.split('\r\n').filter(Boolean).length,40);
 checkSvgControls(node('company-cards').innerHTML,'company cards');checkSvgControls(node('compare-content').innerHTML,'comparison');
 assert.ok(svgControlsChecked>0,'No shared SVG controls rendered');
 console.log(JSON.stringify({status:presentationFailures.length?'failed':'passed',presentation_failures:presentationFailures,entities:39,modules_loaded:modules,curated_profiles_checked:curated.length,afterquery_overlay_and_source_links:true,afterquery_exact_leadership:true,afterquery_distinct_relationship_roles:true,afterquery_performance_attribution:true,curated_products_checked:curatedProducts,relationship_names_checked:relationshipsChecked,shared_svg_controls_checked:svgControlsChecked,visible_typed_records_checked:referenced,source_records_checked:data.sources.length,work_routes_checked:routes.length,unique_primary_groups:7,editorial_primary_alignment:39,frontier_primary_and_secondary_software_regressions:true,canonical_json_download:true,csv_bounds_and_scope:true,current_and_historical_financial_semantics:true,browser_rendering_verified:false}));
 assert.equal(presentationFailures.length,0,'Presentation checks failed; see the JSON report above.');
})().catch(error=>{console.error(error);process.exitCode=1});
function readJSONFrom(file){return JSON.parse(fs.readFileSync(file,'utf8'));}
'''

with tempfile.TemporaryDirectory(prefix='observatory-js-') as tmp:
 tmp=Path(tmp);(tmp/'test.cjs').write_text(STUB);data=fixture();expected=[]
 for levels in itertools.product(['U','1','2','3'],repeat=4):
  for dim,level in zip('PCRO',levels):data['assessments'][0]['gates'][dim]['level']=level
  expected.append({'levels':dict(zip('PCRO',levels)),'stage':classify(data,'test-alpha'),'confidence':stage_confidence(data,'test-alpha')})
 (tmp/'expected.json').write_text(json.dumps(expected));(tmp/'fixture.json').write_text(json.dumps(fixture()))
 target=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'data/canonical.json'
 for data_path in [tmp/'fixture.json',target]:
  subprocess.run(['node',str(tmp/'test.cjs'),str(data_path),str(ROOT),str(tmp/'expected.json')],check=True)
