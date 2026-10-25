/* Business health: evidence, arithmetic and scenarios stay separate. */
(() => {
'use strict';
const bundle=window.BUSINESS_HEALTH;
const signals=['revenue','profit','customers','delivery','cash'];
const labels={revenue:'Revenue & growth',profit:'Delivery margin',customers:'Customer durability',delivery:'Paid expert activity',cash:'Cash resilience'};
const questions={revenue:'Is demand expanding?',profit:'What stays after delivery?',customers:'Will customers come back?',delivery:'Is expertise turning into paid work?',cash:'Can the business sustain growth?'};
const bhState={view:'snapshots',trendCompany:'taskus',signal:'revenue',measure:'',cohort:'',group:'',company:'',observation:'',query:'',expanded:false};
const all=()=>bundle?.observations||[];
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const scopeLabel=o=>o.scope_label||scopeText(o.scope,o.company_id);
const basisLabel=o=>o.accounting_basis==='unspecified'?'Gross/net undisclosed':human(o.accounting_basis);
const byId=id=>all().find(o=>o.id===id);
const numeric=o=>typeof o.value==='number'&&Number.isFinite(o.value);
const definition=id=>(bundle?.signals||[]).find(s=>s.id===id)||{};
const human=s=>String(s||'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const plural=(n,word)=>n+' '+word+(n===1?'':'s');
const annualized=o=>/run.?rate|annualized/.test(o.measure);
// Compact labels: a fiscal period drops the month range that restates it, and a scope keeps a few words.
const periodName=o=>String(o.period?.label||'').replace(/ · [A-Z][a-z]{2} \d{4}–[A-Z][a-z]{2} \d{4}$/,'');
const scopeShort=o=>({company:'Whole company',ai_data:'AI business',other_segment:'Other segment'})[o.scope]||scopeLabel(o);
function cohort(o){return o.cohort||[o.period?.label,o.currency,o.scope,o.accounting_basis].filter(Boolean).join(' · ');}
function observations(){return all().map(o=>({...o}));}
function rows(signal,measure,filters={}){
 let result=all().filter(o=>o.signal===signal&&(!measure||o.measure===measure)&&numeric(o));
 if(filters.group)result=result.filter(o=>modelGroup(o.company_id)===filters.group);
 if(filters.company)result=result.filter(o=>o.company_id===filters.company);
 if(filters.cohort)result=result.filter(o=>cohort(o)===filters.cohort);
 if(filters.reportedOnly)result=result.filter(o=>o.evidence_type==='reported');
 if(measure==='annualized_revenue'&&!filters.cohort&&!filters.history){const recent=new Map();for(const o of result){const before=recent.get(o.company_id);if(!before||o.as_of.localeCompare(before.as_of)>0)recent.set(o.company_id,o);}result=[...recent.values()];}
 // Preserve distinct reporting bases; only deduplicate within the exact cohort.
 const latest=new Map();
 for(const o of result){const key=[o.company_id,o.measure,cohort(o)].join('|'),before=latest.get(key);if(!before||o.as_of.localeCompare(before.as_of)>0)latest.set(key,o);}
 return [...latest.values()].sort((a,b)=>b.value-a.value||companies[a.company_id].name.localeCompare(companies[b.company_id].name));
}
function estimate(revenue,lowMargin,highMargin){
 if(![revenue,lowMargin,highMargin].every(v=>typeof v==='number'&&Number.isFinite(v))||revenue<0||lowMargin<0||highMargin>100||lowMargin>highMargin)return null;
 return {low:revenue*lowMargin/100,high:revenue*highMargin/100,lowMargin,highMargin};
}
function evidenceState(company,signal){
 if(companies[company]?.entity_type==='adjacent_research')return 'n-a';
 const list=all().filter(o=>o.company_id===company&&o.signal===signal);
 if(list.some(o=>numeric(o)&&!o.is_context&&o.evidence_type!=='estimate'))return 'observed';
 if(list.length)return 'proxy';
 return 'missing';
}
function valueText(o,amount=o.value,qualify=true){
 if(!numeric({...o,value:amount}))return 'Not disclosed';
 let val;
 if(o.unit==='percent'||o.unit==='%')val=new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(amount)+'%';
 else if(o.currency){const symbol={USD:'$',GBP:'£',EUR:'€'}[o.currency]||o.currency+' ';const abs=Math.abs(amount);val=(amount<0?'−':'')+symbol+new Intl.NumberFormat('en-US',{maximumFractionDigits:abs>=1e6?2:0}).format(abs/(abs>=1e9?1e9:abs>=1e6?1e6:1))+(abs>=1e9?'B':abs>=1e6?'M':'');}
 else val=new Intl.NumberFormat('en-US',{notation:Math.abs(amount)>=1e6?'compact':'standard',maximumFractionDigits:1}).format(amount);
 const q=qualify?({greater_than:'> ',at_least:'≥ ',at_most:'≤ ',less_than:'< ',approximately:'≈ ',approximate:'≈ ',nearly:'Nearly '}[o.qualifier]||''):'';
 return q+val;
}
function measureDefinition(id){const d=bundle?.measure_definitions;if(Array.isArray(d))return d.find(m=>m.id===id)||{};return d?.[id]||{};}
function measureLabel(id){return measureDefinition(id).label||all().find(o=>o.measure===id)?.measure_label||human(id);}
function measures(signal){return [...new Set(all().filter(o=>o.signal===signal&&numeric(o)).map(o=>o.measure))];}
function bestMeasure(signal){const ids=measures(signal),preferred={revenue:['annualized_revenue','revenue_growth_yoy','period_revenue'],profit:['gross_margin','net_margin','net_profit_margin'],customers:['net_revenue_retention','nrr','customer_concentration'],delivery:['daily_expert_payouts','daily_payouts','expert_payouts_daily','cumulative_expert_payouts'],cash:['cash_balance','cash','operating_cash_flow']}[signal];return preferred.find(id=>ids.includes(id))||ids[0]||'';}
function pickCompanyObservation(company,signal){
 const list=all().filter(o=>o.company_id===company&&o.signal===signal);
 const preferred=bestMeasure(signal);
 return list.sort((a,b)=>Number(numeric(b))-Number(numeric(a))||Number(b.measure===preferred)-Number(a.measure===preferred)||Number(!!a.is_context)-Number(!!b.is_context)||b.as_of.localeCompare(a.as_of))[0];
}
function evidenceLinks(o){return `<div class="bh-evidence-links">${o.claim_ids.map((id,i)=>claimButton(id,o.claim_ids.length>1?'Evidence '+(i+1):'Inspect original claim')).join('')}${o.source_ids.slice(0,3).map(id=>external(sources[id].url,sources[id].publisher||'Original source')).join('')}</div>`;}
function renderDetail(){
 const o=byId(bhState.observation),id=bhState.company||(o?.company_id),name=companies[id]?.name;
 if(!o||o.company_id!==id||o.signal!==bhState.signal){
  const context=all().filter(r=>r.company_id===id&&r.signal===bhState.signal);
  $('bh-detail').innerHTML=`<span class="bh-detail-kicker">${safe(name||'READ THE EVIDENCE')}</span><h4>${name?'A question to investigate':'Select a company or chart mark'}</h4><p>${name?'The reviewed evidence does not establish this measure for '+safe(name)+'.':'Every mark opens its source, date, scope and calculation here.'}</p><p class="bh-note">${esc(definition(bhState.signal).ideal_measure||questions[bhState.signal])}</p>${context.length?`<div class="bh-fact"><strong>Available context</strong>${context.map(r=>`<p>${esc(r.label)}: ${numeric(r)?safe(valueText(r)):esc(r.original_text)}</p>${evidenceLinks(r)}`).join('')}</div>`:''}${id?`<a href="#company/${safe(id)}/traction">Open the full company profile</a>`:''}`;
  return;
 }
 const status=o.evidence_type==='estimate'?'Third-party estimate':o.evidence_type==='calculated'?'Calculated from reported inputs':'Reported observation';
 const history=all().filter(r=>r.company_id===id&&r.signal===o.signal&&r.measure===o.measure&&r.id!==o.id).sort((a,b)=>b.as_of.localeCompare(a.as_of));
 const related=all().filter(r=>r.company_id===id&&r.signal===o.signal&&r.measure!==o.measure);
 $('bh-detail').innerHTML=`<span class="bh-detail-kicker">${safe(name)}</span><h4>${esc(o.label)}</h4><div class="bh-detail-value">${safe(numeric(o)?valueText(o):'Amount not disclosed')}</div><span class="bh-pill ${o.evidence_type==='estimate'?'is-estimate':''}">${status}${o.is_context?' · context only':''}</span><p class="bh-note">${esc(o.evidence_assurance||evidenceLabel(claims[o.claim_ids[0]]))}</p><dl class="bh-fact"><dt>Period / date</dt><dd>${safe(o.period.label)}${o.as_of!==o.period.label?' · '+safe(o.as_of):''}</dd><dt>Business scope</dt><dd>${safe(scopeLabel(o))}</dd><dt>Accounting</dt><dd>${safe(basisLabel(o))}</dd></dl>${!o.limitations.includes(o.basis)?`<p>${esc(o.basis)}</p>`:''}${o.normalization?`<p class="bh-note">${esc(o.normalization)}</p>`:''}${o.calculation?`<div class="bh-fact"><strong>How it is calculated</strong><p>${esc(o.calculation.formula||o.calculation)}</p></div>`:''}<p class="bh-warning">${esc(o.limitations)}</p><details class="bh-fact"><summary>Source wording &amp; attribution</summary><p>${esc(o.original_text)}</p></details>${evidenceLinks(o)}${history.length?`<details class="bh-fact"><summary>Other dated observations (${history.length})</summary>${history.map(r=>`<p><button class="text-link" data-bh-observation="${safe(r.id)}">${safe(r.period.label)} · ${safe(valueText(r))}</button><br>${safe(scopeLabel(r))}</p>`).join('')}</details>`:''}${related.length?`<details class="bh-fact"><summary>Other measures for this signal (${related.length})</summary>${related.map(r=>`<p><button class="text-link" data-bh-context="${safe(r.id)}">${esc(r.label)} · ${safe(valueText(r))}</button></p>`).join('')}</details>`:''}<div class="bh-detail-nav"><a href="#company/${safe(id)}/traction">Full company profile ${iconHTML('external')}</a></div>`;
}
function historyMeasures(company){return [...new Set(all().filter(o=>o.company_id===company&&o.signal==='revenue'&&numeric(o)).map(o=>o.measure))];}
function historyMeasure(company,current){const ids=historyMeasures(company);return ids.includes(current)?current:['period_revenue','annualized_revenue'].find(id=>ids.includes(id))||ids[0]||current;}
function historySeries(company,measure){
 const grouped=new Map();
 for(const o of all().filter(o=>o.company_id===company&&o.signal==='revenue'&&o.measure===measure&&numeric(o))){
  const key=[o.period.type,o.currency,scopeLabel(o),o.accounting_basis].join('|');
  if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(o);
 }
 return [...grouped.values()].map(list=>list.sort((a,b)=>(a.period.end||a.as_of).localeCompare(b.period.end||b.as_of)));
}
function renderHistory(){
 const company=bhState.trendCompany,series=historySeries(company,bhState.measure),total=series.flat().length;
 $('bh-chart-header').innerHTML=`<div><h3>${safe(companies[company].name)} · ${esc(measureLabel(bhState.measure))}</h3><p>Follow the same business through time. Each line keeps one period type, currency, business scope and accounting basis.</p></div>`;
 $('bh-plot').innerHTML=series.length?series.map(list=>{
  const max=Math.max(1,...list.map(o=>o.value)),min=Math.min(0,...list.map(o=>o.value)),span=max-min||1;
  const positions=list.map((o,i)=>({o,x:list.length===1?300:65+i/(list.length-1)*470,y:170-(o.value-min)/span*130}));
  const first=list[0],last=list.at(-1),exact=list.length>1&&first.value>0&&list.every(o=>['exact','calculated'].includes(o.qualifier)&&o.evidence_type!=='estimate');
  return `<section class="bh-history-group"><h4 class="bh-cohort-heading">${safe(first.period.type==='annual'?'Full years':first.period.type==='half_year'?'Half years':human(first.period.type))} · ${safe(first.currency||'percent')} · ${safe(scopeLabel(first))} · ${safe(basisLabel(first))}</h4>${exact?`<p class="bh-history-change">${((last.value/first.value-1)*100).toFixed(1)}% change across the displayed span <small>· calculated from endpoints; not an annualized growth rate</small></p>`:''}<svg viewBox="0 0 600 225" role="img" aria-label="${esc(companies[company].name+' '+first.label+', '+list.map(o=>o.period.label+': '+valueText(o)).join('; '))}"><line x1="65" y1="170" x2="535" y2="170" stroke="#cbd1ce"/><line x1="65" y1="40" x2="535" y2="40" stroke="#d8ddd5" stroke-dasharray="3 5"/><text x="4" y="44" class="bh-svg-axis">${safe(valueText(first,max,false))}</text><text x="30" y="174" class="bh-svg-axis">0</text>${positions.length>1?`<polyline points="${positions.map(p=>p.x+','+p.y).join(' ')}" fill="none" stroke="#285b46" stroke-width="3"/>`:''}${positions.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="5" fill="#285b46"/><text x="${p.x}" y="${p.y-13}" text-anchor="middle" class="bh-svg-value">${safe(valueText(p.o))}</text><text x="${p.x}" y="196" text-anchor="middle" class="bh-svg-axis">${safe(periodName(p.o))}</text>`).join('')}</svg><div class="bh-history-points">${list.map(o=>`<button class="text-link" data-bh-observation="${safe(o.id)}" aria-pressed="${bhState.observation===o.id}">${safe(o.period.label)} · ${safe(valueText(o))}</button>`).join('')}</div></section>`;
 }).join(''):`<div class="bh-empty"><strong>No history for this measure.</strong>${historyMeasures(company).length?safe(companies[company].name)+' has '+historyMeasures(company).map(id=>esc(measureLabel(id)).toLowerCase()).join(' and ')+'.':'Select another company.'}</div>`;
 $('bh-chart-note').textContent=`${plural(total,'dated observation')}. Lines connect disclosed observations; unreported periods remain unknown. Annualized snapshots are estimates of pace. Select a dated value to inspect its evidence.`;
 if(!bhState.observation&&series.length){const o=series[0].at(-1);bhState.observation=o.id;bhState.company=company;}
 renderDetail();
}

function renderPlot(){
 if(bhState.view==='history'&&bhState.signal==='revenue'){renderHistory();return;}
 const selected=rows(bhState.signal,bhState.measure,{group:bhState.group,cohort:bhState.cohort}),groups=new Map();
 if(!bhState.observation&&!bhState.company&&selected.length){bhState.observation=selected[0].id;bhState.company=selected[0].company_id;}
 for(const o of selected){const key=cohort(o);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(o);}
 const md=measureDefinition(bhState.measure);
 $('bh-chart-header').innerHTML=`<div><h3>${esc(measureLabel(bhState.measure))}</h3><p>${esc(md.note||md.description||'Dated observations from the reviewed public evidence.')}</p></div><div class="bh-legend"><span><i></i> Reported / calculated</span><span><i class="is-estimate"></i> Estimate</span></div>`;
 if(!selected.length)$('bh-plot').innerHTML=`<div class="bh-empty"><strong>No comparable observations in this selection.</strong>Try another measure or business group. Missing values stay unknown.</div>`;
 else $('bh-plot').innerHTML=[...groups].map(([key,list])=>{
  const min=Math.min(0,...list.map(o=>o.value)),max=Math.max(0,...list.map(o=>o.value)),span=max-min||1,zero=(0-min)/span*100;
  return `<section class="bh-plot-group" aria-label="${safe(key)}"><h4 class="bh-cohort-heading">${safe(key)}</h4><div class="bh-axis"><span>${safe(valueText(list[0],min,false))}</span><span>${safe(valueText(list[0],max,false))}</span></div>${list.map(o=>{const end=(o.value-min)/span*100;const left=Math.min(zero,end),width=Math.abs(end-zero);return `<button class="bh-plot-row ${o.evidence_type==='estimate'?'is-estimate':''}" data-bh-observation="${safe(o.id)}" aria-pressed="${bhState.observation===o.id}" aria-label="${esc(companies[o.company_id].name+': '+valueText(o)+', '+o.label+', '+o.period.label+', '+scopeLabel(o))}"><span class="bh-row-name">${safe(companies[o.company_id].name)}</span><span class="bh-row-track" aria-hidden="true"><span class="bh-row-bar ${['greater_than','at_least','less_than','at_most'].includes(o.qualifier)?'is-bound':''}" style="left:${left}%;width:${width}%;${o.value<0?'background:#7b5141':''}"></span></span><span class="bh-row-value">${safe(valueText(o))}</span><span class="bh-row-meta">${safe(o.as_of)} · ${safe(scopeLabel(o))}${o.is_context?' · context only':''}${o.evidence_type==='estimate'?' · estimate':o.evidence_type==='calculated'?' · calculated':''}</span></button>`;}).join('')}</section>`;
 }).join('');
 $('bh-chart-note').textContent=`${plural(new Set(selected.map(o=>o.company_id)).size,'organization')} · ${plural(selected.length,'observation')}. Each panel has its own scale and reporting basis. Snapshots have different dates; annualized pace is not completed-year revenue. Bounds retain > / ≥ / ≤; none of these views is a company health ranking.`;
 if(!bhState.observation&&!bhState.company&&selected.length){bhState.observation=selected[0].id;bhState.company=selected[0].company_id;}
 renderDetail();
}
function renderMatrix(){
 const pool=DATA.companies.filter(c=>!bhState.group||modelGroup(c.id)===bhState.group),query=bhState.query.trim();
 const list=pool.filter(c=>c.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>a.name.localeCompare(b.name));
 // Start with the most inspectable businesses; this orders evidence, not health.
 const ordered=[...list].sort((a,b)=>signals.filter(s=>evidenceState(b.id,s)==='observed').length-signals.filter(s=>evidenceState(a.id,s)==='observed').length||a.name.localeCompare(b.name));
 const shown=bhState.expanded||query?ordered:ordered.slice(0,8);
 $('bh-matrix-count').textContent=`${query?`${list.length} of ${plural(pool.length,'organization')} match “${query}”.`:`Showing ${shown.length} of ${plural(list.length,'organization')}.`} Ordered by evidence coverage, not business health. “Context” is a proxy; “Missing” is unknown.`;
 $('bh-matrix-body').innerHTML=shown.map(c=>`<tr><th scope="row"><a href="#company/${safe(c.id)}">${safe(c.name)}</a><small>${safe(groupLabel(modelGroup(c.id)))}</small></th>${signals.map(signal=>{const status=evidenceState(c.id,signal),o=pickCompanyObservation(c.id,signal),text=status==='n-a'?'Research':o?(numeric(o)?valueText(o):'Attributed claim'):'Missing';return `<td><button data-bh-company="${safe(c.id)}" data-bh-signal="${signal}" class="bh-matrix-cell" aria-label="${safe(c.name+' · '+labels[signal]+': '+text)}"><span class="bh-pill" data-status="${status}">${safe(text)}</span><small>${status==='n-a'?'Commercial metrics N/A':o?(o.is_context?'Context · ':'')+esc(measureLabel(o.measure)):'No reviewed disclosure'}</small>${o?`<small>${safe(o.as_of)}</small>`:''}</button></td>`;}).join('')}</tr>`).join('');
 $('bh-show-all').hidden=!!query||list.length<=8;
 $('bh-show-all').textContent=bhState.expanded?'Show fewer organizations':`Show all ${list.length} organizations`;
 $('bh-show-all').setAttribute('aria-expanded',String(bhState.expanded));
}
// A closed select shows company · value · period · scope in a few words; the option title keeps the full wording.
function estimateLabel(o,full=false){return [companies[o.company_id]?.name,valueText(o)+(annualized(o)?' annualized':''),full?o.period.label:periodName(o),full?scopeLabel(o):scopeShort(o)].join(' · ');}
function estimateOption(o){return `<option value="${safe(o.id)}" title="${safe(estimateLabel(o,true))}">${safe(estimateLabel(o))}</option>`;}
function renderEstimator(){
 const o=byId($('bh-estimate-company').value);if(!o)return;
 const low=Number($('bh-margin-low').value),high=Number($('bh-margin-high').value);$('bh-margin-low-label').textContent=low+'%';$('bh-margin-high-label').textContent=high+'%';
 const result=estimate(o.value,low,high);
 $('bh-estimate-result').innerHTML=result?`<span class="bh-pill is-estimate">HYPOTHETICAL SCENARIO</span><p><strong>${safe(valueText(o,result.low,false))} – ${safe(valueText(o,result.high,false))}</strong> gross profit${annualized(o)?' at an annualized pace':''}</p><p>${safe(companies[o.company_id].name)} · ${safe(valueText(o))} × ${low}–${high}% assumed gross margin · ${safe(o.period.label)} · ${safe(scopeLabel(o))}. Revenue basis: ${safe(basisLabel(o))}.</p><p>Assumes the revenue input represents sales before direct delivery costs. If it is net platform revenue, this model does not apply. A lower-bound input yields a scenario at that threshold, not an upper forecast. No retention rate is known, so this is not the repeat-customer north star.</p>${evidenceLinks(o)}`:'<p>Lower margin must be at or below upper margin.</p>';
}
function render(){
 if(!bundle||!DATA.companies.some(c=>c.id==='mercor'))return;
 const ids=measures(bhState.signal);if(!ids.includes(bhState.measure))bhState.measure=bestMeasure(bhState.signal);
 $('bh-tabs').innerHTML=signals.map((id,i)=>{const coverage=new Set(all().filter(o=>o.signal===id&&numeric(o)&&!o.is_context).map(o=>o.company_id)).size;return `<button class="bh-metric-tab" id="bh-tab-${id}" role="tab" aria-controls="bh-panel" aria-selected="${id===bhState.signal}" tabindex="${id===bhState.signal?0:-1}" data-bh-tab="${id}"><span class="number">0${i+1}</span><strong>${labels[id]}</strong><span class="question">${questions[id]}</span><small class="coverage">${coverage} / ${DATA.companies.length} with direct observations</small></button>`;}).join('');
 $('bh-panel').setAttribute('aria-labelledby','bh-tab-'+bhState.signal);
 $('bh-question').innerHTML=`<strong>${esc(definition(bhState.signal).ideal_measure||questions[bhState.signal])}</strong><p>${esc(definition(bhState.signal).interpretation||'Use public observations as clues to the underlying business economics.')}</p>`;
 $('bh-measure').innerHTML=ids.map(id=>`<option value="${safe(id)}">${esc(measureLabel(id))}</option>`).join('');$('bh-measure').value=bhState.measure;
 const cohorts=[...new Set(rows(bhState.signal,bhState.measure,{group:bhState.group,history:true}).map(cohort))];
 if(!cohorts.includes(bhState.cohort))bhState.cohort='';
 $('bh-cohort').innerHTML='<option value="">All bases · separate panels</option>'+cohorts.map(c=>`<option value="${safe(c)}">${safe(c)}</option>`).join('');$('bh-cohort').value=bhState.cohort;
 $('bh-group').innerHTML='<option value="">All business groups</option>'+Object.keys(MODEL_GROUPS).map(g=>`<option value="${safe(g)}">${safe(groupLabel(g))}</option>`).join('');$('bh-group').value=bhState.group;
 $('bh-chart-view').value=bhState.view;$('bh-chart-view').disabled=bhState.signal!=='revenue';
 $('bh-trend-company-label').hidden=bhState.view!=='history';$('bh-cohort-label').hidden=bhState.view==='history';
 $('bh-trend-company').innerHTML=DATA.companies.filter(c=>all().some(o=>o.company_id===c.id&&o.signal==='revenue'&&numeric(o))).map(c=>`<option value="${safe(c.id)}">${safe(c.name)}</option>`).join('');$('bh-trend-company').value=bhState.trendCompany;
 renderPlot();renderMatrix();
}
function selectSignal(signal,company=''){
 bhState.signal=signal;bhState.view='snapshots';bhState.measure=bestMeasure(signal);bhState.cohort='';bhState.company=company;bhState.observation='';
 if(company){const o=pickCompanyObservation(company,signal);if(o){bhState.measure=o.measure;bhState.observation=o.id;}}
 render();
}
window.BusinessHealth={observations,rows,evidenceState,estimate,estimateLabel,estimateOption,render,valueText,cohort,historySeries};
if(!bundle)return;
$('bh-chart-view').addEventListener('change',e=>{bhState.view=e.target.value;bhState.cohort='';if(bhState.view==='history'){bhState.measure=historyMeasure(bhState.trendCompany,'period_revenue');bhState.company=bhState.trendCompany;bhState.observation='';}render();});
$('bh-trend-company').addEventListener('change',e=>{bhState.trendCompany=e.target.value;bhState.company=e.target.value;bhState.measure=historyMeasure(e.target.value,bhState.measure);bhState.observation='';render();});
$('bh-measure').addEventListener('change',e=>{bhState.measure=e.target.value;bhState.cohort='';bhState.company='';bhState.observation='';render();});
$('bh-cohort').addEventListener('change',e=>{bhState.cohort=e.target.value;bhState.company='';bhState.observation='';render();});
$('bh-group').addEventListener('change',e=>{bhState.group=e.target.value;bhState.view='snapshots';bhState.cohort='';bhState.company='';bhState.observation='';render();});
$('bh-search').addEventListener('input',e=>{bhState.query=e.target.value;renderMatrix();});
$('bh-show-all').addEventListener('click',()=>{bhState.expanded=!bhState.expanded;renderMatrix();});
for(const id of ['bh-margin-low','bh-margin-high'])$(id).addEventListener('input',renderEstimator);
$('bh-estimate-company').addEventListener('change',renderEstimator);
document.addEventListener('click',e=>{
 const tab=e.target.closest('[data-bh-tab]');if(tab){selectSignal(tab.dataset.bhTab);$('bh-tab-'+tab.dataset.bhTab).focus({preventScroll:true});return;}
 const cell=e.target.closest('[data-bh-company]');if(cell){selectSignal(cell.dataset.bhSignal,cell.dataset.bhCompany);const strip=$('bh-tabs'),tab=$('bh-tab-'+cell.dataset.bhSignal);strip.scrollTo({left:strip.scrollLeft+tab.getBoundingClientRect().left-strip.getBoundingClientRect().left});strip.scrollIntoView({behavior:'auto',block:'start'});$('bh-panel').focus({preventScroll:true});return;}
 const mark=e.target.closest('[data-bh-observation], [data-bh-context]');if(mark){const o=byId(mark.dataset.bhObservation||mark.dataset.bhContext);if(!o)return;bhState.company=o.company_id;bhState.observation=o.id;bhState.measure=o.measure;bhState.cohort='';render();const updated=[...document.querySelectorAll('[data-bh-observation]')].find(el=>el.dataset.bhObservation===o.id);updated?.focus({preventScroll:true});}
});
$('bh-tabs').addEventListener('keydown',e=>{
 if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;e.preventDefault();let i=signals.indexOf(bhState.signal);i=e.key==='Home'?0:e.key==='End'?4:(i+(e.key==='ArrowRight'?1:-1)+5)%5;selectSignal(signals[i]);const active=$('bh-tab-'+signals[i]);active.focus({preventScroll:true});active.scrollIntoView({block:'nearest',inline:'nearest'});
});
const inputs=all().filter(o=>o.signal==='revenue'&&numeric(o)&&o.currency&&/revenue|run_rate/.test(o.measure)&&!/growth|margin/.test(o.measure));
$('bh-estimate-company').innerHTML=inputs.map(estimateOption).join('');
if(inputs.length)$('bh-estimate-company').value=inputs.find(o=>o.company_id==='mercor')?.id||inputs[0].id;
renderEstimator();
$('bh-method-content').innerHTML=`<p>Dashboard curated ${safe(bundle.dashboard_curated_on||'23 October 2026')} from research dataset ${safe(DATA.dataset_version)}. Source review dates remain attached to each original claim; curation does not imply a fresh audit. This is a selected field guide, not a market census.</p><p>Reported means the source states the number. Calculated means arithmetic using cited inputs. Estimates are attributed to their source. The margin model uses your assumptions and stays outside the evidence table.</p><p>Revenue after contractor payouts, gross billings, software ARR and annualized pace have different meanings. Completed periods and business scopes are separated. Employee headcount and registered expert networks are context; neither measures paid utilization. Customer logos and cumulative clients do not establish retention.</p><p>Cash balance alone cannot establish runway without a dated burn rate. Net income, adjusted EBITDA and gross margin are separate measures. Missing disclosure is not evidence of a weak business. Commercial health measures are not applied to nonprofit research organizations.</p><p>Original research reviewed ${safe(bundle.source_dataset_reviewed_on)}. Dashboard curation does not refresh every source. Follow original source links before making a decision.</p>`;
})();
