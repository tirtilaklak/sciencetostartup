/* Business health: comparable observations first, complete evidence on demand. */
(() => {
'use strict';
const bundle=window.BUSINESS_HEALTH;
const signals=['revenue','profit','customers','delivery','cash'];
const labels={revenue:'Revenue',profit:'Profitability',customers:'Customers',delivery:'Expert activity',cash:'Cash'};
const columns={revenue:'Revenue',profit:'Profit',customers:'Customers',delivery:'Paid delivery',cash:'Cash'};
const questions={revenue:'Is demand expanding?',profit:'What stays after delivery?',customers:'Will customers come back?',delivery:'Is expertise turning into paid work?',cash:'Can the business sustain growth?'};
// Short cell tags. The inspector and the measure select keep the full measure labels.
const measureShort={period_revenue:'revenue',annualized_revenue:'run rate',revenue_growth_yoy:'growth YoY',net_income:'net income',net_margin:'net margin',adjusted_ebitda:'adj. EBITDA',adjusted_ebitda_margin:'adj. EBITDA margin',gross_margin:'gross margin',pretax_income:'pre-tax',profitability_statement:'profit claim',net_revenue_retention:'net retention',top_five_customer_share:'top-5 share',customer_count:'customers',daily_expert_payouts:'paid in one day',cumulative_expert_payouts:'paid to date',payouts_period_unclear:'paid · basis unclear',cumulative_work_hours:'hours to date',network_reach:'registered experts',cash_balance:'cash',net_debt:'net debt',team_size:'staff'};
// The column header already names the plain measure of these signals, so that word is left out of the tag.
const columnDefault={revenue:'period_revenue',cash:'cash_balance'};
const preferredMeasures={revenue:['period_revenue','revenue_growth_yoy','annualized_revenue'],profit:['gross_margin','net_margin','net_profit_margin'],customers:['net_revenue_retention','nrr','customer_concentration'],delivery:['daily_expert_payouts','daily_payouts','expert_payouts_daily','cumulative_expert_payouts'],cash:['cash_balance','cash','operating_cash_flow']};
const stateRank={observed:0,proxy:1,missing:2,'n-a':3};
const periodRank={annual:0,trailing_year:0,run_rate:0,half_year:1,snapshot:1,daily:1,cumulative:1,undated:2,unclear:2};
const ACRONYMS={us:'US',gaap:'GAAP',ebitda:'EBITDA',fx:'FX',nrr:'NRR (net revenue retention)',ifrs:'IFRS'};
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const bhState={signal:'revenue',measure:'period_revenue',cohort:null,group:'',query:'',sort:'coverage',evidenceOnly:false,company:'',observation:''};
const all=()=>bundle?.observations||[];
const freshClaims=new Map((bundle?.fresh_claims||[]).map(c=>[c.id,c]));
const refreshedSources=new Map((bundle?.sources||[]).map(s=>[s.id,s]));
const claimRecord=id=>claims[id]||freshClaims.get(id);
const sourceRecord=id=>refreshedSources.get(id)||sources[id];
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const scopeLabel=o=>o.scope_label||scopeText(o.scope,o.company_id);
const scopeWord=o=>o.scope==='ai_data'?'AI line':o.scope==='other_segment'?'segment':'';
const byId=id=>all().find(o=>o.id===id);
const numeric=o=>typeof o.value==='number'&&Number.isFinite(o.value);
const definition=id=>(bundle?.signals||[]).find(s=>s.id===id)||{};
const human=s=>String(s||'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()).replace(/\b([a-z]+)\b/gi,w=>ACRONYMS[w.toLowerCase()]||w);
const plural=(n,word)=>n+' '+(n===1?word:word==='company'?'companies':word+'s');
const media=q=>typeof window.matchMedia==='function'&&window.matchMedia(q).matches;
const narrow=()=>media('(max-width:1000px)');
// A gross/net question only exists for money measures; other bases are simply not stated.
const basisLabel=o=>o.accounting_basis==='unspecified'?(o.unit==='currency'&&/revenue|run_rate|payout/.test(o.measure)?'Gross/net undisclosed':'Not stated'):o.accounting_basis==='not_applicable'?'Not applicable':human(o.accounting_basis);
// Research notes end with record fields (scope, period, source type) that the inspector already shows.
const basisText=o=>String(o.basis||'').split(/(?:^|;\s*)(?:Scope|Source type|Original period\/date|Revenue\/accounting basis):/)[0].trim();
const limitationsText=o=>o.basis&&o.limitations.startsWith(o.basis)?(basisText(o)+' '+o.limitations.slice(o.basis.length)).trim():o.limitations;
function cohort(o){return o.cohort||[o.period?.label,o.currency,o.scope,o.accounting_basis].filter(Boolean).join(' · ');}
// The cohort key stays as the data wrote it; only the display drops a money phrase from a people or percent basis.
function cohortDisplay(key,o){return o&&basisLabel(o)==='Not stated'?human(key.replace(/\s·\sGross\/net undisclosed$/,'')):human(key);}
function observations(){return all().map(o=>({...o}));}
function rows(signal,measure,filters={}){
 let result=all().filter(o=>o.signal===signal&&(!measure||o.measure===measure)&&numeric(o));
 if(filters.group)result=result.filter(o=>modelGroup(o.company_id)===filters.group);
 if(filters.company)result=result.filter(o=>o.company_id===filters.company);
 if(filters.cohort)result=result.filter(o=>cohort(o)===filters.cohort);
 if(filters.reportedOnly)result=result.filter(o=>o.evidence_type==='reported');
 // Annualized snapshots: one dated figure per company on each reporting basis.
 if(measure==='annualized_revenue'&&!filters.cohort&&!filters.history){const recent=new Map();for(const o of result){const key=o.company_id+'|'+cohort(o),before=recent.get(key);if(!before||dateKey(o).localeCompare(dateKey(before))>0)recent.set(key,o);}result=[...recent.values()];}
 // Preserve distinct reporting bases; only deduplicate within the exact cohort.
 const latest=new Map();
 for(const o of result){const key=[o.company_id,o.measure,cohort(o)].join('|'),before=latest.get(key);if(!before||dateKey(o).localeCompare(dateKey(before))>0)latest.set(key,o);}
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
const boundWord=o=>({greater_than:'More than ',at_least:'At least ',at_most:'At most ',less_than:'Less than ',approximately:'About ',approximate:'About ',nearly:'Nearly '}[o.qualifier]||'');
function shortDate(text,day=true){
 const s=String(text||'').trim(),m=s.match(/(\d{4})-(\d{2})(?:-(\d{2}))?/);
 if(!m)return s.replace(/^as of /i,'');
 return (/inferred/i.test(s)?'≈ ':'')+(day&&m[3]?Number(m[3])+' ':'')+MONTHS[Number(m[2])-1]+' '+m[1];
}
// Cell tags keep month precision; the inspector shows the full period and date.
function periodShort(o,day=false){
 const p=o.period||{},label=String(p.label||''),named=label.match(/^H[12](?: FY)?\d{4}/);
 switch(p.type){
  case 'annual':return p.end&&!/-12-31$/.test(p.end)?'FY to '+shortDate(p.end,day):p.year?'FY'+p.year:label;
  case 'half_year':{if(named)return named[0];const month=String(p.start||'').slice(5,7);return month==='01'&&p.year?'H1 '+p.year:month==='07'&&p.year?'H2 '+p.year:'6 months to '+shortDate(p.end||o.as_of,day);}
  case 'trailing_year':return '12 months to '+shortDate(p.end||o.as_of,day);
  case 'cumulative':return /\d{4}/.test(o.as_of)?shortDate(o.as_of,day):'';
  case 'undated':return day?'undated':'';
  default:{const d=shortDate(o.as_of,day);return /^undated$/i.test(d)&&!day?'':d||label;}
 }
}
const dateKey=o=>o.period?.end||(String(o.as_of||'').match(/\d{4}(?:-\d{2}){0,2}/)||[''])[0];
// Same rule as the company cards: a figure more than a year older than the dataset is historical.
const asOfYear=Number(String(DATA.meta?.as_of||'').slice(0,4))||0;
const yearOf=o=>Number(dateKey(o).slice(0,4))||0;
const isHistorical=o=>!!asOfYear&&!!yearOf(o)&&yearOf(o)<asOfYear-1;
// The research grade of the weakest cited claim: A strongest, U unverified.
const gradeText={A:'independent or buyer-side evidence',B:'attributed company, investor or named primary statement',C:'secondary reporting, an estimate or indirect evidence',U:'unverified, undisclosed or unresolved'};
const grade=o=>o.claim_ids.map(id=>claimRecord(id)?.confidence).filter(g=>gradeText[g]).sort().at(-1)||'';
const gradeChip=o=>{const g=grade(o);return g?`<i class="bh-grade" title="Research grade ${g}: ${safe(gradeText[g])}"><span class="sr-only">grade </span>${g}</i>`:'';};
// The tag names the scope and a gross basis when they matter, and marks old figures.
function cellTag(o){return [columnDefault[o.signal]===o.measure?'':measureShort[o.measure]||measureLabel(o.measure).toLowerCase(),scopeWord(o),o.accounting_basis==='gross'?'gross':'',periodShort(o),isHistorical(o)?'historical':''].filter(Boolean).join(' · ');}
// Labels for the inspector's lists of a company's other figures: measure, scope, period and value.
function otherLabel(r,withMeasure){return [withMeasure?measureShort[r.measure]||measureLabel(r.measure):'',scopeWord(r),r.accounting_basis==='gross'?'gross':'',periodShort(r,true),numeric(r)?valueText(r):'claim'].filter(Boolean).join(' · ');}
function measureDefinition(id){const d=bundle?.measure_definitions;if(Array.isArray(d))return d.find(m=>m.id===id)||{};return d?.[id]||{};}
function measureLabel(id){return measureDefinition(id).label||all().find(o=>o.measure===id)?.measure_label||human(id);}
function measures(signal){return [...new Set(all().filter(o=>o.signal===signal&&numeric(o)).map(o=>o.measure))];}
// The default measure for a signal; under a group filter, the measure that group reports most.
function bestMeasure(signal,group=''){
 const ids=measures(signal),preferred=preferredMeasures[signal]||[],rank=id=>{const i=preferred.indexOf(id);return i<0?preferred.length:i;};
 if(!group)return preferred.find(id=>ids.includes(id))||ids[0]||'';
 const counted=ids.map(id=>({id,n:rows(signal,id,{group}).length})).filter(m=>m.n).sort((a,b)=>b.n-a.n||rank(a.id)-rank(b.id));
 return counted[0]?.id||bestMeasure(signal);
}
function defaultCohort(list){
 const groups=new Map();
 for(const o of list){const key=cohort(o);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(o);}
 return [...groups].sort((a,b)=>{
  const multiple=x=>new Set(x.map(o=>o.company_id)).size>1;
  const latest=x=>x.map(dateKey).sort().at(-1)||'';
  return Number(multiple(b[1]))-Number(multiple(a[1]))||latest(b[1]).localeCompare(latest(a[1]))||b[1].length-a[1].length;
 })[0]?.[0]||'';
}
function pickCompanyObservation(company,signal){
 const list=all().filter(o=>o.company_id===company&&o.signal===signal),preferred=bestMeasure(signal);
 return list.sort((a,b)=>Number(numeric(b))-Number(numeric(a))||Number(!!a.is_context)-Number(!!b.is_context)||Number(b.measure===preferred)-Number(a.measure===preferred)||dateKey(b).slice(0,7).localeCompare(dateKey(a).slice(0,7))||Number(a.scope!=='company')-Number(b.scope!=='company')||(periodRank[a.period?.type]??2)-(periodRank[b.period?.type]??2))[0];
}
function evidenceLinks(o){return `<span class="bh-evidence-links">${o.claim_ids.filter(id=>claims[id]).map((id,i)=>claimButton(id,o.claim_ids.length>1?'Claim '+(i+1):'Inspect claim')).join('')}${o.source_ids.slice(0,3).map(id=>{const source=sourceRecord(id);return source?external(source.url,source.publisher||'Original source'):'';}).join('')}</span>`;}
function freshnessNote(o){
 const fresh=o.claim_ids.map(id=>freshClaims.get(id)).filter(Boolean);
 return fresh.length?`<p class="bh-refresh-note">Content checked ${safe(shortDate(fresh[0].observed_on))}${fresh[0].source_locator?' · '+safe(fresh[0].source_locator):''}</p>`:'';
}

function statusText(o){return o.evidence_type==='estimate'?'Third-party estimate':o.evidence_type==='calculated'?'Calculated':o.is_context?'Context only':'Reported';}
function pillClass(o){return o.evidence_type==='estimate'?'is-estimate':o.is_context?'is-context':'';}
function assuranceText(o){const text=String(o.evidence_assurance||'');const cl=claimRecord(o.claim_ids[0]);return text&&!/Research label:/i.test(text)?text:cl?.evidence_label||(cl?evidenceLabel(cl):'Source attribution');}
function dateRow(o){
 const label=o.period.label,extra=shortDate(o.as_of,true),month=shortDate(o.as_of,false);
 if(!/\d{4}-\d{2}/.test(o.as_of)||label.includes(o.as_of)||label.includes(month)||label.includes(dateKey(o).slice(0,7)))return label;
 return label+' · stated '+extra;
}
function renderDetail(){
 const o=byId(bhState.observation),id=bhState.company||(o?.company_id),name=companies[id]?.name,group=id?groupLabel(modelGroup(id)):'';
 if(id&&evidenceState(id,bhState.signal)==='n-a'){
  $('bh-detail').innerHTML=`<p class="bh-kicker">${safe(name)} · ${safe(group)}</p><h3>Not applied</h3><p class="bh-lede">${safe(name)} is a nonprofit research organization. Commercial measures are not applied to it.</p><a class="bh-profile" href="#company/${safe(id)}">Full company profile ${iconHTML('external')}</a>`;
  return;
 }
 if(!o||o.company_id!==id||o.signal!==bhState.signal){
  const context=all().filter(r=>r.company_id===id&&r.signal===bhState.signal);
  $('bh-detail').innerHTML=`<p class="bh-kicker">${safe(name?name+' · '+group:'Read the evidence')}</p><h3>${name?'No reviewed public figure':'Select a figure'}</h3><p class="bh-lede">${name?'The reviewed sources do not establish '+labels[bhState.signal].toLowerCase()+' for '+safe(name)+'. Missing is not zero.':'Select a chart bar to read its source and reporting details.'}</p><p class="bh-note">${esc(definition(bhState.signal).ideal_measure||questions[bhState.signal])}</p>${context.length?`<div class="bh-related"><p><strong>Available context</strong></p>${context.map(r=>`<p>${esc(r.label)}: ${numeric(r)?safe(valueText(r)):esc(r.original_text)} ${evidenceLinks(r)}</p>`).join('')}</div>`:''}${id?`<a class="bh-profile" href="#company/${safe(id)}/traction">Full company profile ${iconHTML('external')}</a>`:''}`;
  return;
 }
 const history=all().filter(r=>r.company_id===id&&r.signal===o.signal&&r.measure===o.measure&&r.id!==o.id).sort((a,b)=>dateKey(b).localeCompare(dateKey(a)));
 const related=all().filter(r=>r.company_id===id&&r.signal===o.signal&&r.measure!==o.measure);
 const sparkline=historySeries(id,o.measure).some(list=>list.length>1&&list.some(r=>r.id===o.id));
 const g=grade(o);
 $('bh-detail').innerHTML=`<p class="bh-kicker">Selected evidence</p><h3>${safe(name)}</h3><p class="bh-measure-name">${esc(measureLabel(o.measure))}</p>${isHistorical(o)?`<span class="bh-historical">Historical · ${yearOf(o)}</span>`:''}<p class="bh-value${isHistorical(o)?' is-historical':''}">${safe(numeric(o)?valueText(o):'Not quantified')}<span class="bh-pill ${pillClass(o)}">${statusText(o)}</span></p><dl class="bh-facts"><dt>Date</dt><dd>${safe(dateRow(o))}</dd><dt>Scope</dt><dd>${safe(scopeLabel(o))}</dd><dt>Basis</dt><dd>${safe(basisLabel(o))}</dd><dt>Source</dt><dd>${esc(assuranceText(o))} ${evidenceLinks(o)}${freshnessNote(o)}</dd></dl>${o.calculation?`<p class="bh-note"><strong>Calculated:</strong> ${esc(o.calculation.formula||o.calculation)}</p>`:''}${o.normalization?`<p class="bh-note">${esc(o.normalization)}</p>`:''}<details class="bh-caveats"><summary>Caveats and source wording</summary>${g?`<p class="bh-note">Research grade ${g}: ${safe(gradeText[g])}.</p>`:''}${basisText(o)&&!o.limitations.includes(o.basis)?`<p>${esc(basisText(o))}</p>`:''}<p class="bh-warning">${esc(limitationsText(o))}</p><p class="bh-quote">“${esc(o.original_text)}”</p></details>${history.length&&!sparkline?`<details class="bh-related"><summary>Other dates</summary><p> ${history.map(r=>`<button type="button" class="text-link" data-bh-observation="${safe(r.id)}">${safe(otherLabel(r,false))}</button>`).join(' ')}</p></details>`:''}${related.length?`<details class="bh-related"><summary>Other measures</summary><p> ${related.map(r=>`<button type="button" class="text-link" data-bh-context="${safe(r.id)}">${esc(otherLabel(r,true))}</button>`).join(' ')}</p></details>`:''}<a class="bh-profile" href="#company/${safe(id)}/traction">Full company profile ${iconHTML('external')}</a>`;
}
function historySeries(company,measure){
 const grouped=new Map();
 for(const o of all().filter(o=>o.company_id===company&&o.measure===measure&&numeric(o))){
  const key=[o.period.type,o.currency,scopeLabel(o),o.accounting_basis].join('|');
  if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(o);
 }
 return [...grouped.values()].map(list=>list.sort((a,b)=>dateKey(a).localeCompare(dateKey(b))));
}
function renderHistory(){
 const o=byId(bhState.observation),company=o?.company_id;
 const list=o?historySeries(company,o.measure).find(list=>list.length>1&&list.some(r=>r.id===o.id)):null;
 $('bh-history').hidden=!list;
 if(!list){$('bh-history').innerHTML='';return;}
 const max=Math.max(1,...list.map(r=>r.value)),min=Math.min(0,...list.map(r=>r.value)),span=max-min||1;
 const times=list.map(r=>Date.parse(dateKey(r))),timeSpan=times.at(-1)-times[0];
 const positions=list.map((r,i)=>({r,x:list.length===1?150:28+(Number.isFinite(timeSpan)&&timeSpan>0?(times[i]-times[0])/timeSpan:i/(list.length-1))*244,y:66-(r.value-min)/span*40}));
 const first=list[0],last=list.at(-1),exact=first.value>0&&list.every(r=>['exact','calculated'].includes(r.qualifier)&&r.evidence_type!=='estimate');
 const basis=[first.period.type==='annual'?'Full years':first.period.type==='half_year'?'Half years':human(first.period.type),first.currency||'percent',scopeLabel(first),basisLabel(first)].join(' · ');
 $('bh-history').innerHTML=`<h4>${safe(companies[company].name)} over time</h4><p class="bh-cohort-heading">${safe(basis)}${exact&&list.length>1?` · ${((last.value/first.value-1)*100).toFixed(1)}% change, first to last`:''}</p><svg viewBox="0 0 300 88" role="img" aria-label="${esc(companies[company].name+' '+first.label+', '+list.map(r=>r.period.label+': '+valueText(r)).join('; '))}"><line class="bh-svg-base" x1="28" y1="66" x2="272" y2="66"/>${positions.length>1?`<polyline class="bh-svg-line" points="${positions.map(p=>p.x+','+p.y).join(' ')}" fill="none" stroke-width="2" stroke-linejoin="round"/>`:''}${positions.map((p,i)=>`<circle class="bh-svg-point${p.r.id===o.id?' is-selected':''}" cx="${p.x}" cy="${p.y}" r="${p.r.id===o.id?5:3.5}" stroke-width="2"/>${i===0||i===positions.length-1||p.r.id===o.id?`<text x="${p.x}" y="${p.y-9}" text-anchor="${i===0?'start':i===positions.length-1?'end':'middle'}" class="bh-svg-value">${safe(valueText(p.r))}</text>`:''}<text x="${p.x}" y="82" text-anchor="${i===0?'start':i===positions.length-1?'end':'middle'}" class="bh-svg-axis">${safe(periodShort(p.r))}</text>`).join('')}</svg><div class="bh-history-points">${list.map(r=>`<button type="button" data-bh-observation="${safe(r.id)}"${bhState.observation===r.id?' aria-current="true"':''}>${safe(periodShort(r,true))} · ${safe(valueText(r))}</button>`).join('')}</div>`;
}
function renderCompare(){
 const selected=rows(bhState.signal,bhState.measure,{group:bhState.group,cohort:bhState.cohort}),groups=new Map(),current=byId(bhState.observation);
 if(!bhState.observation&&!bhState.company&&selected.length){bhState.observation=selected[0].id;bhState.company=selected[0].company_id;}
 // A figure chosen from the inspector stays visible in its own panel even when a later snapshot replaced it.
 if(current&&current.signal===bhState.signal&&current.measure===bhState.measure&&numeric(current)&&!selected.some(r=>r.id===current.id)&&(!bhState.cohort||cohort(current)===bhState.cohort)&&(!bhState.group||modelGroup(current.company_id)===bhState.group))selected.push(current);
 for(const o of selected){const key=cohort(o);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(o);}
 const md=measureDefinition(bhState.measure);
 if(!selected.length)$('bh-plot').innerHTML=`<p class="bh-empty">No comparable observations in this selection. Missing values stay unknown.</p>`;
 else $('bh-plot').innerHTML=[...groups].map(([key,list])=>{
  list.sort((a,b)=>b.value-a.value||companies[a.company_id].name.localeCompare(companies[b.company_id].name));
  const min=Math.min(0,...list.map(o=>o.value)),max=Math.max(0,...list.map(o=>o.value)),span=max-min||1,zero=(0-min)/span*100;
  return `<div class="bh-plot-group" role="group" aria-label="${safe(cohortDisplay(key,list[0]))}"><h5 class="bh-cohort-heading">${safe(cohortDisplay(key,list[0]))}</h5>${list.map(o=>{const end=(o.value-min)/span*100;const left=Math.min(zero,end),width=Math.abs(end-zero);return `<button type="button" class="bh-bar" data-bh-observation="${safe(o.id)}"${bhState.observation===o.id?' aria-current="true"':''} aria-label="${esc(companies[o.company_id].name+': '+valueText(o)+', '+o.label+', '+o.period.label+', '+scopeLabel(o)+(isHistorical(o)?', historical':''))}"><span class="bh-bar-name">${safe(companies[o.company_id].name)}<small>${safe(periodShort(o,true))} · ${safe(statusText(o))}${o.is_context?' · context':''}</small></span><span class="bh-bar-track" aria-hidden="true"><i class="bh-bar-fill${['greater_than','at_least','less_than','at_most'].includes(o.qualifier)?' is-bound':''}${o.value<0?' is-negative':''}${o.evidence_type==='estimate'?' is-estimate':''}" style="left:${left}%;width:${width}%"></i>${min<0?`<i class="bh-bar-zero" style="left:${zero}%"></i>`:''}</span><span class="bh-bar-value${isHistorical(o)?' is-historical':''}">${safe(valueText(o))}</span></button>`;}).join('')}<div class="bh-axis"><span>${safe(valueText(list[0],min,false))}</span><span>${safe(valueText(list[0],max,false))}</span></div></div>`;
 }).join('');
 $('bh-chart-note').textContent=`${plural(new Set(selected.map(o=>o.company_id)).size,'company')} in this selection. ${md.note||md.description||''} ${groups.size>1?'Each panel has its own scale. ':''}Select a figure for its source.`;
 if($('bh-chart-title'))$('bh-chart-title').textContent=measureLabel(bhState.measure);
}
function companyRows(){
 const pool=DATA.companies.filter(c=>!bhState.group||modelGroup(c.id)===bhState.group),query=bhState.query.trim().toLowerCase();
 const states=new Map(pool.map(c=>[c.id,Object.fromEntries(signals.map(s=>[s,evidenceState(c.id,s)]))]));
 let list=pool.filter(c=>c.name.toLowerCase().includes(query));
 if(bhState.evidenceOnly)list=list.filter(c=>signals.some(s=>['observed','proxy'].includes(states.get(c.id)[s])));
 const coverage=id=>signals.filter(s=>states.get(id)[s]==='observed').length*2+signals.filter(s=>states.get(id)[s]==='proxy').length;
 const unitRank=o=>!o||!numeric(o)?3:o.currency?0:o.unit==='percent'?1:2;
 // Figures are ordered by size within one measure and reporting basis only; across bases the order is by evidence, never by size.
 const bySignal=(a,b)=>{const sa=states.get(a.id)[bhState.signal],sb=states.get(b.id)[bhState.signal];if(stateRank[sa]!==stateRank[sb])return stateRank[sa]-stateRank[sb];const oa=pickCompanyObservation(a.id,bhState.signal),ob=pickCompanyObservation(b.id,bhState.signal);if(!oa||!ob)return a.name.localeCompare(b.name);const preferred=bestMeasure(bhState.signal);return Number(ob.measure===preferred)-Number(oa.measure===preferred)||unitRank(oa)-unitRank(ob)||Number(oa.scope!=='company')-Number(ob.scope!=='company')||cohort(oa).localeCompare(cohort(ob))||(numeric(ob)?ob.value:0)-(numeric(oa)?oa.value:0)||a.name.localeCompare(b.name);};
 const sorted=[...list].sort(bhState.sort==='name'?(a,b)=>a.name.localeCompare(b.name):bhState.sort==='signal'?bySignal:(a,b)=>coverage(b.id)-coverage(a.id)||a.name.localeCompare(b.name));
 return {pool,sorted,states};
}
function cellHTML(c,signal,state){
 if(state==='n-a')return `<td class="bh-cell" data-state="n-a" data-bh-company="${safe(c.id)}" data-bh-signal="${signal}"><span title="Nonprofit research: commercial measures are not applied">n/a<span class="sr-only"> ${labels[signal]}: not applied</span></span></td>`;
 const o=pickCompanyObservation(c.id,signal),selected=bhState.company===c.id&&bhState.signal===signal;
 if(!o)return `<td class="bh-cell" data-state="missing" data-bh-company="${safe(c.id)}" data-bh-signal="${signal}"><span title="${safe(c.name+' · '+labels[signal]+': no reviewed public disclosure. Missing is not zero.')}">—<span class="sr-only"> ${labels[signal]}: not disclosed</span></span></td>`;
 const value=numeric(o)?valueText(o):'Claim',tag=cellTag(o);
 return `<td class="bh-cell" data-state="${state}"${isHistorical(o)?' data-historical="true"':''} data-bh-company="${safe(c.id)}" data-bh-signal="${signal}"><button type="button" data-bh-company="${safe(c.id)}" data-bh-signal="${signal}"${selected?' aria-current="true"':''} title="${esc(c.name+' · '+o.label+' · '+o.period.label+' · '+scopeLabel(o)+(o.is_context?' · context only':'')+(isHistorical(o)?' · historical':'')+(grade(o)?' · research grade '+grade(o):''))}"><b>${safe(value)}${gradeChip(o)}</b><small>${safe(tag)}${o.is_context?'<span class="sr-only"> (context only)</span>':''}</small></button></td>`;
}
function renderGrid(){
 const {pool,sorted,states}=companyRows(),query=bhState.query.trim();
 const figures=sorted.filter(c=>signals.some(s=>states.get(c.id)[s]==='observed')).length;
 const order={coverage:'ordered by evidence coverage',signal:'ordered by '+labels[bhState.signal].toLowerCase()+' evidence, same basis together',name:'A to Z'}[bhState.sort];
 $('bh-matrix-count').textContent=`${query||bhState.evidenceOnly||bhState.group?`${sorted.length} of ${plural(DATA.companies.length,'organization')}`:plural(sorted.length,'organization')} · ${figures} with a reported figure · ${order}, not by health.`;
 const nextSort=bhState.sort==='name'?'coverage':'name';
 $('bh-grid-head').innerHTML=`<th scope="col"${bhState.sort==='name'?' aria-sort="ascending"':bhState.sort==='coverage'?' aria-sort="other"':''}><button type="button" class="bh-colhead" data-bh-sort="${nextSort}">Organization<small>${nextSort==='name'?'sort A to Z':'sort by most evidence'}</small></button></th>`+signals.map(s=>{const n=new Set(all().filter(o=>o.signal===s&&numeric(o)&&!o.is_context).map(o=>o.company_id)).size;return `<th scope="col"${bhState.sort==='signal'&&bhState.signal===s?' aria-sort="descending"':''}><button type="button" class="bh-colhead${bhState.signal===s?' is-active':''}" data-bh-tab="${s}" title="${esc(questions[s])}">${columns[s]}<small>${n} of ${DATA.companies.length}</small></button></th>`;}).join('');
 $('bh-matrix-body').innerHTML=sorted.length?sorted.map(c=>`<tr${bhState.company===c.id?' class="is-selected"':''}><th scope="row"><a href="#company/${safe(c.id)}"><span>${safe(c.name)}</span></a><small>${safe(groupLabel(modelGroup(c.id)))}</small></th>${signals.map(s=>cellHTML(c,s,states.get(c.id)[s])).join('')}</tr>`).join(''):`<tr><td colspan="6" class="bh-empty">No organization matches. Clear the search or the group filter.</td></tr>`;
}
// After the grid is re-sorted, show the selected cell, or the top of the grid.
function revealSelection(){
 const wrap=$('bh-grid-wrap');if(!wrap||typeof wrap.querySelector!=='function')return;
 const pressed=wrap.querySelector('button[aria-current]');
 if(pressed)pressed.scrollIntoView({block:'nearest',inline:'nearest'});else wrap.scrollTop=0;
}

function render(){
 if(!bundle||!DATA.companies.some(c=>c.id==='mercor'))return;
 const ids=measures(bhState.signal);if(!ids.includes(bhState.measure))bhState.measure=bestMeasure(bhState.signal,bhState.group);
 $('bh-tabs').innerHTML=signals.map(id=>`<button type="button" class="bh-tile" id="bh-tab-${id}" role="tab" aria-controls="bh-inspector" aria-selected="${id===bhState.signal}" tabindex="${id===bhState.signal?0:-1}" data-bh-tab="${id}"><strong>${labels[id]}</strong></button>`).join('');
 $('bh-inspector').setAttribute('aria-labelledby','bh-tab-'+bhState.signal);
 $('bh-measure').innerHTML=ids.map(id=>`<option value="${safe(id)}">${esc(measureLabel(id))}</option>`).join('');$('bh-measure').value=bhState.measure;
 const cohortRows=rows(bhState.signal,bhState.measure,{group:bhState.group,history:true}),cohorts=[...new Set(cohortRows.map(cohort))];
 if(bhState.cohort===null||(bhState.cohort&&!cohorts.includes(bhState.cohort)))bhState.cohort=defaultCohort(cohortRows);
 $('bh-cohort').innerHTML='<option value="">All reporting periods (separate charts)</option>'+cohorts.map(c=>`<option value="${safe(c)}">${safe(cohortDisplay(c,cohortRows.find(o=>cohort(o)===c)))}</option>`).join('');$('bh-cohort').value=bhState.cohort;
 $('bh-group').innerHTML='<option value="">All business groups</option>'+Object.keys(MODEL_GROUPS).map(g=>`<option value="${safe(g)}">${safe(groupLabel(g))}</option>`).join('');$('bh-group').value=bhState.group;
 $('bh-sort').value=bhState.sort;
 renderCompare();renderDetail();renderHistory();renderGrid();
}
function selectSignal(signal,company=''){
 if(!company){bhState.sort='signal';bhState.measure=bestMeasure(signal,bhState.group);}
 else if(signal!==bhState.signal)bhState.measure=bestMeasure(signal);
 bhState.signal=signal;bhState.cohort=null;bhState.company=company;bhState.observation='';
 if(company){const o=pickCompanyObservation(company,signal);if(o){bhState.measure=o.measure;bhState.observation=o.id;bhState.cohort=cohort(o);}}
 render();
}
window.BusinessHealth={observations,rows,evidenceState,estimate,render,valueText,cohort,historySeries};
if(!bundle)return;
$('bh-measure').addEventListener('change',e=>{bhState.measure=e.target.value;bhState.cohort=null;bhState.company='';bhState.observation='';render();});
$('bh-cohort').addEventListener('change',e=>{bhState.cohort=e.target.value;bhState.company='';bhState.observation='';render();});
$('bh-group').addEventListener('change',e=>{bhState.group=e.target.value;bhState.cohort=null;bhState.company='';bhState.observation='';bhState.measure=bestMeasure(bhState.signal,bhState.group);render();revealSelection();});
$('bh-sort').addEventListener('change',e=>{bhState.sort=e.target.value;renderGrid();revealSelection();});
$('bh-search').addEventListener('input',e=>{bhState.query=e.target.value;renderGrid();});
$('bh-evidence-only').addEventListener('change',e=>{bhState.evidenceOnly=!!e.target.checked;renderGrid();});
document.addEventListener('click',e=>{
 // Header buttons are rebuilt with the grid, so focus returns to the new button in the same place.
 const sort=e.target.closest('[data-bh-sort]');if(sort){bhState.sort=sort.dataset.bhSort;$('bh-sort').value=bhState.sort;renderGrid();revealSelection();$('bh-grid-head').querySelector?.('[data-bh-sort]')?.focus({preventScroll:true});return;}
 const tab=e.target.closest('[data-bh-tab]');if(tab){const inGrid=!!tab.closest('thead');selectSignal(tab.dataset.bhTab);if(inGrid)revealSelection();(inGrid?$('bh-grid-head').querySelector?.(`[data-bh-tab="${tab.dataset.bhTab}"]`):$('bh-tab-'+tab.dataset.bhTab))?.focus({preventScroll:true});return;}
 const cell=e.target.closest('[data-bh-company]');if(cell){selectSignal(cell.dataset.bhSignal,cell.dataset.bhCompany);const inspector=$('bh-inspector');inspector.scrollTop=0;inspector.scrollIntoView({behavior:media('(prefers-reduced-motion: reduce)')?'auto':'smooth',block:'start'});inspector.focus({preventScroll:true});return;}
 const mark=e.target.closest('[data-bh-observation], [data-bh-context]');if(mark){const o=byId(mark.dataset.bhObservation||mark.dataset.bhContext);if(!o)return;const panel=mark.closest('#bh-plot, #bh-history, #bh-detail');bhState.company=o.company_id;bhState.observation=o.id;bhState.measure=o.measure;bhState.cohort=cohort(o);render();const home=panel&&document.getElementById(panel.id),find=root=>[...root.querySelectorAll('[data-bh-observation]')].find(el=>el.dataset.bhObservation===o.id);(home&&find(home)||find(document))?.focus({preventScroll:true});}
});
$('bh-tabs').addEventListener('keydown',e=>{
 if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;e.preventDefault();let i=signals.indexOf(bhState.signal);i=e.key==='Home'?0:e.key==='End'?4:(i+(e.key==='ArrowRight'?1:-1)+5)%5;selectSignal(signals[i]);const active=$('bh-tab-'+signals[i]);active.focus({preventScroll:true});active.scrollIntoView({block:'nearest',inline:'nearest'});
});
$('bh-method-content').innerHTML=`<p><strong>Reported</strong> means the source states the number. <strong>Calculated</strong> means arithmetic from cited inputs, shown with its formula. <strong>Context</strong> covers customer counts, registered expert networks, headcount and profitability claims: proxies, never a measured margin, retention rate or cash figure. The letter on each figure is the research grade of its claim: A independent or buyer-side evidence, B an attributed primary statement, C secondary reporting or an estimate.</p><p>Run rate (annualized pace), completed-period revenue, gross billings and net revenue mean different things, so each keeps its own panel and scale. Missing disclosure is not zero and not a sign of weakness. Nonprofit research organizations are not scored on commercial measures.</p><p>Curated ${safe(bundle.dashboard_curated_on||'23 October 2026')} from research dataset ${safe(DATA.dataset_version)}, reviewed ${safe(bundle.source_dataset_reviewed_on)}; review dates stay attached to each claim. Follow the original source before acting on a figure.</p>`;
})();
