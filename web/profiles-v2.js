/* Public, source-linked profile presentation. Raw records remain in the archive. */
function profileContent(id){return (window.PROFILE_CONTENT?.entries||[]).find(e=>e.company_id===id)||{};}
// Formatters built once; output matches toLocaleDateString('en-GB').
const PROFILE_DAY_FORMAT=new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}),PROFILE_MONTH_FORMAT=new Intl.DateTimeFormat('en-GB',{month:'short',year:'numeric',timeZone:'UTC'});
// 2026-06-30 -> 30 Jun 2026, 2026-06 -> Jun 2026, FY ended 2025-12-31 -> FY2025.
function readableDate(text){
 const valid=(y,m,d=1)=>{const date=new Date(Date.UTC(+y,+m-1,+d,12));return date.getUTCMonth()===+m-1&&date.getUTCDate()===+d?date:null;};
 return String(text??'').replace(/\bFY ended (\d{4})-12-31\b/g,'FY$1').replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g,(all,y,m,d)=>{const date=valid(y,m,d);return date?PROFILE_DAY_FORMAT.format(date).replace('Sept','Sep'):all;}).replace(/\b(\d{4})-(\d{2})\b(?!-\d)/g,(all,y,m)=>{const date=valid(y,m);return date?PROFILE_MONTH_FORMAT.format(date).replace('Sept','Sep'):all;});
}
function profileDate(value){return readableDate(dateText(value));}
function profileSourceMeta(s){const added=profileDate(s.accessed_on);return [s.publisher,s.published_on?'Published '+profileDate(s.published_on):'Publication date not stated',s.retrieval_status==='checked'?'Checked '+added:s.retrieval_status==='summary_only'?'Summary only, page not reviewed · recorded '+added:s.retrieval_status==='unverified'?'Not checked again · recorded '+added:'Recorded '+added].filter(Boolean).join(' · ');}
function profileProvenance(cl){return `<div class="record-meta">${cl.status!=='supported'?`<b>${esc(title(cl.status))}</b>`:''}<span>${esc(evidenceContextArchiveDate(cl,profileDate(cl.as_of)))}</span><span>· ${esc(evidenceContextOriginalScope(cl,scopeText(cl.segment_scope,cl.company_id)))}</span><span>· ${esc(profileEvidenceLabel(cl))}</span>${claimButton(cl.id,'Source')}</div>`;}
// Canonical company id for a route value (case and alias fixes).
function profileRouteCompany(value=routeParts()[1]){const raw=String(value??''),lower=raw.toLowerCase(),aliases=window.RESEARCH_ALIASES;return isCompanyId(raw)?raw:isCompanyId(lower)?lower:aliases&&Object.hasOwn(aliases,lower)&&isCompanyId(aliases[lower])?aliases[lower]:'';}
function profileReferences(ids,label='Source',topic=''){
  const unique=[...new Set(ids||[])].filter(id=>claims[id]);
  if(unique.length<2)return unique.map(id=>claimButton(id,label,topic)).join('');
  const visibleLabel=label==='Source'?'Sources':label,access=evidenceAccess(unique,visibleLabel,topic);
  return `<button type="button" class="evidence-link" data-profile-evidence="${attr(unique.join('|'))}" ${access.attributes}>${esc(visibleLabel)}</button>${access.description}`;
}
// Grouped sources: the dialog lists the other claims.
document.addEventListener('click',event=>{const button=event.target.closest?.('[data-profile-evidence]');if(!button)return;const ids=button.dataset.profileEvidence.split('|').filter(id=>claims[id]);if(!ids.length)return;showEvidence(ids[0],ids);});
// Copy the record link; without clipboard access, show it.
document.addEventListener('click',event=>{const button=event.target.closest?.('[data-copy-record]');if(!button)return;const url=new URL(button.dataset.copyRecord,location.href).href,status=$('evidence-copy-status'),say=text=>{if(status)status.textContent=text;};const copy=navigator.clipboard?.writeText?navigator.clipboard.writeText(url):Promise.reject();copy.then(()=>say('Link copied.'),()=>say('Copy this link: '+url));});
function profileProducts(id){
  const curated=profileContent(id).products;if(curated?.length)return typeof applyProductSourceUpdates==='function'?applyProductSourceUpdates(id,curated):curated;
  const all=DATA.products.filter(p=>p.company_id===id&&claims[p.claim_id]?.status!=='superseded');
  const named=all.filter(p=>!/^Offer \/ product evidence|^Product evidence/i.test(p.name));
  const rows=named.length?named:all,seen=new Set();
  const products=rows.filter(p=>{const key=p.name.toLowerCase().replace(/[^a-z0-9]/g,'');if(seen.has(key))return false;seen.add(key);return true;}).map(p=>({name:p.name,description:p.work_performed,kind:p.delivery_model,record_ids:[p.id],claim_ids:[p.claim_id]}));
  return typeof applyProductSourceUpdates==='function'?applyProductSourceUpdates(id,products):products;
}
function profileRelationships(id){
  const curated=profileContent(id).relationships;if(curated)return curated;
  const seen=new Set();
  return DATA.customer_evidence.filter(r=>r.company_id===id&&claims[r.claim_id]?.status!=='superseded').filter(r=>{
    if(r.organization.length>75||/unnamed|undisclosed|anonymous|not (?:named|disclosed|established)|every leading|no named|not a |no verified|unverified customer/i.test(r.organization))return false;
    const key=r.organization.toLowerCase().replace(/[^a-z0-9]/g,'');if(seen.has(key))return false;seen.add(key);return true;
  }).map(r=>({name:r.organization,relationship:r.relationship_detail||title(r.relationship),description:r.use_case,record_ids:[r.id],claim_ids:[r.claim_id]}));
}
function relationshipLabel(value){return ({dataset_use:'Dataset used in training',dataset_user:'Dataset use',implementation_partner:'Business implementation',research_collaboration:'Research collaboration',research_collaborator:'Research collaboration',company_reported_customer:'Company-reported customer',company_reported_data_partner:'Company-reported data partner',customer:'Customer evidence',claimed_customer:'Reported customer relationship',technology_vendor:'Technology supplier',research_citation:'Research citation',benchmark_adopter:'Use of an AI test',benchmark_contributor:'Contribution to an AI test',acquirer:'Acquirer',reseller:'Reseller'})[value]||title(value);}
function profileRelationshipLabel(id,row){
 const claimId='quesma.claim.audit-historical-delivery',sourceId='quesma.source.audit-q-hydrolix',claim=claims[claimId],source=sources[sourceId];
 if(id==='quesma'&&row.name==='Hydrolix'&&row.relationship==='former_customer'&&row.claim_ids?.length===1&&row.claim_ids[0]===claimId&&claim?.company_id===id&&claim.status==='supported'&&claim.source_ids?.length===1&&claim.source_ids[0]===sourceId&&source?.company_id===id&&source.url==='https://www.prnewswire.com/news-releases/hydrolix-adds-quesma-gateway-proxy-ip-to-its-portfolio-assuring-continued-kibana-support-302559127.html')return 'Gateway IP buyer';
 return typeof relationshipLabel==='function'?relationshipLabel(row.relationship):title(row.relationship);
}
function profileProductGrid(id){const rows=[...profileProducts(id)].sort((a,b)=>Number(Boolean(b.description))-Number(Boolean(a.description)));const render=items=>`<div class="profile-product-grid">${items.map(p=>`<article class="offering-card" data-profile-product="${attr(p.name)}"><div class="offering-title"><h3>${esc(p.name)}</h3>${p.kind?`<p class="offering-kind">${esc(p.kind)}</p>`:''}</div><div class="offering-description">${p.description?`<p>${esc(p.description)}</p>`:''}${p.status?`<p class="offering-status">${esc(title(p.status))}</p>`:''}${p.aliases?.length?`<details class="offering-aliases"><summary>Other names in the source</summary><p>${esc(p.aliases.join(' · '))}</p></details>`:''}</div><div class="profile-card-source">${typeof productSourceHTML==='function'?productSourceHTML(p,'Source',p.name):profileReferences(p.claim_ids,'Source',p.name)}${typeof productSourceContextHTML==='function'?productSourceContextHTML(p):''}</div></article>`).join('')}</div>`;return render(rows.slice(0,2))+(rows.length>2?profileDisclosure(`More offerings (${rows.length-2})`,render(rows.slice(2))):'');}
function profileCase(id){const c=profileContent(id).featured_case;if(!c)return '';return `<section class="featured-case"><p class="eyebrow">${esc(c.eyebrow||'A closer look')}</p><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p>${c.qualifier?`<p class="case-qualifier">${esc(c.qualifier)}</p>`:''}${profileReferences(c.claim_ids,'Case source',c.title)}</section>`;}
function profileContextDescription(text,claimIds=[]){
 if(!claimIds.some(id=>['afterquery.claim.round2-relationship-3','afterquery.claim.round2-research-legora-bar'].includes(id)))return text;
 return String(text||'').replace('synthetic BAR case','synthetic case for BAR (an evaluation of AI on legal work)').replace('BAR uses','BAR (an evaluation of AI on legal work) uses');
}
function profileRelationshipGrid(id){const rows=profileRelationships(id),featured=profileContent(id).featured_case;const render=items=>`<div class="profile-relationship-grid">${items.map(r=>`<article class="relationship-card" data-profile-relationship="${attr(r.name)}"><div><h3>${esc(r.name)}</h3><p class="relationship-kind">${esc(profileRelationshipLabel(id,r))}</p></div><div class="relationship-account">${r.description&&r.description!==featured?.description?`<p>${esc(profileContextDescription(r.description,r.claim_ids))}</p>`:''}${profileRelationshipScopeContext(id,r)?`<p class="sub">${esc(profileRelationshipScopeContext(id,r))}</p>`:''}</div><div class="profile-card-source">${profileReferences(r.claim_ids,'Source',r.name)}</div></article>`).join('')}</div>`;return rows.length?render(rows.slice(0,4))+(rows.length>4?profileDisclosure(`More relationships (${rows.length-4})`,render(rows.slice(4))):''):'<p class="profile-empty">Named relationships are not established in the reviewed sources.</p>';}
const PROFILE_EVENT_KINDS={lawsuit:'Lawsuit',data_incident:'Data incident',customer_change:'Customer change',workforce_change:'Workforce change',filing:'Filing'};
function profileMonthHTML(value,prefix=''){return /^\d{4}-\d{2}(-\d{2})?$/.test(value)?`${prefix}<time datetime="${attr(value)}">${esc(new Date(value.slice(0,7)+'-01T12:00:00Z').toLocaleDateString('en-US',{month:'short',year:'numeric',timeZone:'UTC'}))}</time>`:esc(dateText(value));}
function profileEvents(id){return (window.COMPANY_EVENTS?.events||[]).filter(e=>e.company_id===id||e.related_company_ids.includes(id)).sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));}
// Event statuses carry the date they were checked, since a pending case can change after review.
function profileStatusesChecked(events){
 const days=[...new Set(events.map(e=>e.status_checked_on).filter(d=>/^\d{4}-\d{2}-\d{2}$/.test(d)))].sort(),label=d=>`${Number(d.slice(8))} ${new Date(d+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',timeZone:'UTC'})} ${d.slice(0,4)}`;
 return !days.length?'':days.length===1?`Statuses were checked on ${label(days[0])}.`:`Statuses were checked between ${label(days[0])} and ${label(days.at(-1))}.`;
}
function profileRiskClaims(id){return currentClaims(id).filter(c=>c.subject==='risks'&&c.status==='supported').sort(byRecent);}
function profileRisks(id){
 const events=profileEvents(id),risks=profileRiskClaims(id);if(!events.length&&!risks.length)return '';
 const eventRows=events.map(e=>`<article class="relationship-card" data-profile-event="${attr(e.id)}"><div><p class="risk-date">${profileMonthHTML(e.date)}</p><p class="relationship-kind">${esc(PROFILE_EVENT_KINDS[e.kind]||title(e.kind))}</p></div><div class="relationship-account"><h4>${esc(e.title)}</h4><p>${esc(e.detail)}</p><p class="risk-meta">${esc(e.status)}${e.sources.map(s=>' · '+external(s.url,s.publisher)).join('')}</p></div></article>`).join('');
 const riskRows=risks.map(c=>`<article class="relationship-card" data-profile-risk="${attr(c.id)}"><div><p class="risk-date">${profileMonthHTML(c.as_of,'As of ')}</p></div><div class="relationship-account"><p>${esc(c.statement)}</p></div><div class="profile-card-source">${profileReferences([c.id])}</div></article>`).join('');
 return profileSection('risks','Risks and disputes',`<div class="profile-risks">${events.length?`<h3 class="eyebrow">Dated events</h3><div class="profile-relationship-grid">${eventRows}</div>`:''}${risks.length?`<h3 class="eyebrow">Risks named in the evidence</h3><div class="profile-relationship-grid">${riskRows}</div>`:''}${events.length?`<p class="sub">Lawsuit entries describe allegations and court filings, not findings. Dates show when a case was filed or an event was reported. ${esc(profileStatusesChecked(events))}</p>`:''}</div>`);
}
function profilePeopleRows(id){
  const curated=profileContent(id).people;
  const all=curated?.length?curated:DATA.company_people.filter(p=>p.company_id===id).map(p=>({person_id:p.person_id,role:title(p.role),bio:'',claim_ids:[p.claim_id]}));
  return all.filter(p=>!p.historical&&!/early founding|historical/i.test(p.role)&&(!/\bformer\b/i.test(p.role)||/\badvisor\b/i.test(p.role)));
}
function profilePeople(id){
  const rows=profilePeopleRows(id);
  return rows.length?`<div class="leadership-grid">${rows.map(p=>`<article class="leadership-card">${p.portrait?`<span class="leadership-photo ${p.portrait.includes('carlos')?'photo-tighter':''}"><img class="leadership-portrait" src="${attr(p.portrait)}" alt="" width="80" height="80" loading="lazy"></span>`:''}<div><h3>${esc(people[p.person_id]?.name||p.name)}</h3><p class="leadership-role">${esc(p.role)}</p>${p.bio?`<p>${esc(p.bio)}</p>`:''}${profileReferences(p.claim_ids,'Source',people[p.person_id]?.name||p.name)}</div></article>`).join('')}</div>`:'<p class="profile-empty">Leadership is not established in the reviewed sources.</p>';
}
const PROFILE_CAPITAL_CONTEXT={
 'bespoke_labs.round.1':{qualification:'Series A amount differs by source: Wing reports $31.3M; SiliconANGLE reports $31.75M.'},
 'giskard.round.1':{label:'Public grants · 2023',dateLabel:'Reported',qualification:'Includes the €500K i-Lab award.'},
 'giskard.round.2':{label:'Consortium grant',dateLabel:'Project announced',qualification:'Company-reported €3M Bpifrance grant linked to ArGiMi. Amount drawn and allocation details are undisclosed.'},
 'apto.round.0':{label:'Investment history',dateLabel:'Interview published',qualification:'Mitsui Sumitomo Insurance Venture Capital first invested in December 2020 and led four later investments. Amounts are undisclosed.'},
 'appen.round.major-8':{dateLabel:'Completed'},
 'appen.round.major-9':{dateLabel:'Completed'},
 'hackerrank.round.recruit-2015':{qualification:'The 2015 announcement reports $7.5M; the company timeline later gives $7.8M.'},
 'invisible.round.major-1':{dateLabel:'Database date',qualification:'Funding database reports the amount and date; an original financing announcement was not verified.'},
 'sama.round.sama-2017':{label:'BESTSELLER Foundation investment · 2017',qualification:'Sama Kenya subsidiary. Amount undisclosed.'},
 'refresh.round.0':{label:'Y Combinator · Spring 2025 cohort'},
 'taskus.round.2':{label:'Initial public share offering',qualification:'Gross base value: 13.2M shares × $23. Excludes the banks’ option to buy extra shares.'},
 'taskus.round.3':{outcome:'The take-private proposal failed its shareholder vote on 8 Oct 2025.',outcomeSourceLabel:'Vote source'}
};
function profileCapitalContext(r){return Object.prototype.hasOwnProperty.call(PROFILE_CAPITAL_CONTEXT,r.id)?PROFILE_CAPITAL_CONTEXT[r.id]:{};}
function capitalLabel(r){
 const context=profileCapitalContext(r);if(context.label)return context.label;
 if(/philanthropic|pledge/i.test(r.round_name+' '+claims[r.claim_id]?.statement))return 'Philanthropic pledge';
 return ({secondary:'Sale of existing shares',debt:'Debt financing',acquisition:'Acquisition',grant:'Grant'})[r.capital_type]||title(r.round_name);
}
function profileCapital(id){
 const config=profileContent(id),rounds=fundingRows(id).filter(r=>claims[r.claim_id]?.status!=='superseded'),uncertainStatus=['talks','rumor','rumoured','proposed','cancelled'];
 const current=rounds.filter(r=>claims[r.claim_id]?.status==='supported'&&!r.parent_round_id&&!uncertainStatus.includes(r.status));
 const valuations=uniqueMetrics(id).filter(m=>m.kind==='valuation'&&!unconfirmedValuation(m)),combined=config.combine_round_and_valuation&&current.length===1?valuations.find(m=>m.as_of===current[0].announced_on):null;
 const outcomes=rounds.filter(r=>r.status==='cancelled'&&claims[r.claim_id]?.status==='supported'&&profileCapitalContext(r).outcome);
 const outcomeHTML=outcomes.map(r=>{const context=profileCapitalContext(r);return `<div class="capital-outcome"><p class="sub">${esc(context.outcome)}</p>${profileReferences([r.claim_id],context.outcomeSourceLabel||'Outcome source')}</div>`;}).join('');
 const unconfirmed=rounds.some(r=>claims[r.claim_id]?.status!=='supported'||uncertainStatus.slice(0,4).includes(r.status))||uniqueMetrics(id).some(unconfirmedValuation),more=unconfirmed||rounds.some(r=>r.status==='cancelled')||current.length>3||valuations.filter(m=>m!==combined).length>1;
 return `<div class="capital-grid">${current.slice(0,3).map(r=>{
  const context=profileCapitalContext(r),leads=DATA.round_investors.filter(x=>x.round_id===r.id&&claims[x.claim_id||r.claim_id]?.status==='supported'&&/lead/i.test(x.role)).map(x=>investors[x.investor_id].name);
  return `<article class="capital-event" data-capital-round="${attr(r.id)}"><div class="capital-time"><p class="capital-date">${esc(context.dateLabel||'Announced')}<span>${esc(profileDate(r.announced_on))}</span></p>${r.closed_on?`<p class="sub">Closed ${esc(profileDate(r.closed_on))}</p>`:''}</div><div class="capital-data"><p class="capital-label">${esc(capitalLabel(r))}</p><h3><span class="sr-only">${esc(capitalLabel(r))}: </span>${'amount'in r?esc(metricValue({value:r.amount,unit:'currency',currency:r.currency,qualifier:r.qualifier})):'Amount undisclosed'}</h3>${r.capital_type==='mixed'&&r.amount_basis==='undisclosed'?'<p class="sub capital-scope">Company-reported financing includes equity and credit. Component amounts and credit drawdown are undisclosed.</p>':''}${r.amount_basis==='mixed_transaction'?'<p class="sub capital-scope">Includes existing shares sold by shareholders. The total is not all new company funding.</p>':''}${context.qualification?`<p class="sub capital-scope">${esc(context.qualification)}</p>`:''}${leads.length?`<p class="sub">Led by ${esc(leads.join(', '))}</p>`:''}${combined?`<div class="capital-valuation">${numberButton(combined)}<span>Valuation at the round</span></div>`:''}<p class="sub">${config.capital_note?esc(config.capital_note):r.status==='announced'?'':esc(title(r.status))}${r.capital_type==='secondary'?' · Existing shares':''}</p>${profileReferences([r.claim_id],'Source')}</div></article>`;
 }).join('')}${valuations.filter(m=>m!==combined).slice(0,1).map(m=>`<article class="capital-event valuation-event"><div class="capital-time"><p class="capital-date">As of<span>${esc(profileDate(m.as_of))}</span></p></div><div class="capital-data"><p class="capital-label">${esc(/pre.money/i.test(m.label)?'Pre-money valuation':/post.money/i.test(m.label)?'Post-money valuation':'Valuation')}</p><h3>${numberButton(m)}</h3><p class="sub">${esc(scopeText(m.segment_scope,id))}</p>${/pre.money/i.test(m.label)?'<p class="sub">Company value before the new investment is added.</p>':''}<p class="sub">${esc(evidenceLabel(claims[m.claim_id]))}</p></div></article>`).join('')}</div>${!current.length&&!valuations.length?'<p class="profile-empty">No quantified financing is established in the reviewed sources.</p>':''}${outcomeHTML}${more?`<p class="sub profile-more-records">More funding records${unconfirmed?', including unconfirmed reports,':''} are in <a href="#company/${attr(id)}/financing">Sources and review</a>.</p>`:''}`;
}
function profileSentenceCase(text){const value=String(text??'');return value.charAt(0).toUpperCase()+value.slice(1);}
function profileMetricLabel(m){
  if(m.id==='ooak.metric.audit-ooak-headcount-scope'&&m.company_id==='ooak'&&m.kind==='headcount'&&m.label==='directory_team_size')return 'Team size listed by Y Combinator (a startup investor)';
  if(m.kind==='annualized_revenue_run_rate')return 'Annualized revenue pace';
  if(['expert_network','headcount','active_paid_experts','other'].includes(m.kind))return profileSentenceCase(m.label);
  return metricLabels[m.kind]||profileSentenceCase(m.label);
}
function profileMetricDate(m){
 const corrected=metricCurrentPeriod(m);if(corrected)return corrected;
 if(m.kind==='revenue')return readableDate(m.period_label||financialPeriod(m));
 if(m.as_of==='undated')return 'Undated · checked '+profileDate(claims[m.claim_id].observed_on);
 const date=profileDate(String(m.as_of).replace(/^as of\s+/i,''));return /^(\d|[A-Z][a-z]{2,3} \d{4})/.test(date)?'As of '+date:date.charAt(0).toUpperCase()+date.slice(1);
}
function profileMetricYear(m){const rank=dateRank(m.as_of);return rank==='0000'?null:Number(rank.slice(0,4));}
// Same Historical rule as compactSignal() on the cards.
function profileMetricHistory(m){const year=profileMetricYear(m);return year&&year<Number(DATA.meta.as_of.slice(0,4))-1?'Historical · '+year:'';}
function profileMetricTags(m){const tags=[metricStatusLabel(m),profileMetricHistory(m)].filter(tag=>tag&&tag!=='Reported');return tags.length?`<p class="observation-tags">${tags.map(tag=>`<span>${esc(tag)}</span>`).join('')}</p>`:'';}
// Signed growth: +58.6%, −1.5%.
function profileMetricValue(m){const value=metricValue(m);return m.kind!=='growth_rate'||m.unit!=='percent'?value:m.value>0?value.replace(/\d/,'+$&'):value.replace('-','−');}
function profileNumberButton(m){const label=profileMetricValue(m);if(label===metricValue(m))return numberButton(m);const access=evidenceAccess([m.claim_id],label,metricEvidenceTopic(m,m.label||metricLabels[m.kind]));return `<button class="number-button" data-claim="${esc(m.claim_id)}" ${access.attributes}>${esc(label)}</button>${access.description}`;}
const PROFILE_METRIC_ATTRIBUTIONS={
 'elorian.claim.core-elorian.claim.growth_metrics-0.metric-0-metric':'Employer job listing',
 'abundant_ai.claim.audit-abundant-network-metric':'Company-authored Y Combinator profile',
 'ooak.claim.audit-ooak-headcount-scope-metric':'Y Combinator profile snapshot',
 'laude.claim.audit-laude-deployed-grants-metric':'Institute-reported grantmaking'
};
// Lead decision: TaskUs and Appen figures are annual-report figures, never "audited".
const PROFILE_EVIDENCE_LABELS={'Audited filing':'Annual report filing','Audited public company':'Public company annual report'};
function profileEvidenceLabel(cl){const label=evidenceLabel(cl);return ['taskus','appen'].includes(cl.company_id)&&PROFILE_EVIDENCE_LABELS[label]||label;}
function profileMetricAttribution(m){
 const claim=claims[m.claim_id];
 if(claim.status!=='supported'||claim.source_ids.length&&claim.source_ids.every(id=>sources[id].retrieval_status==='unverified'))return profileEvidenceLabel(claim);
 return metricCurrentAttribution(m,PROFILE_METRIC_ATTRIBUTIONS[claim.id]||profileEvidenceLabel(claim));
}
function profilePerformance(id){
  const config=profileContent(id),chart=config.performance_chart,related=config.operating_case;const chartTitle=chart&&/GDPval/i.test(chart.title)?'Initial training comparison':chart?.title,seriesLabel=value=>String(value).replace(/warmup/gi,'initial training');
  const visual=chart?`<section class="profile-performance"><p class="eyebrow">Performance experiment</p><h2>${esc(chartTitle)}</h2>${/GDPval/i.test(chart.title)?'<p class="sub">GDPval tests AI on professional work tasks. This experiment compares training with and without an initial preparation stage.</p>':''}<p class="sub">${esc(chart.subtitle)}</p><div class="performance-bars" role="img" aria-label="${attr(chart.title+': '+chart.series.map(s=>s.label+' '+s.value).join('; ')+'. Scale zero to 100.')}">${chart.series.map(s=>`<div class="performance-row"><div><span>${esc(seriesLabel(s.label))}</span><strong>${esc(s.value)}</strong></div><div class="performance-track"><span style="width:${Math.max(0,Math.min(100,Number(s.value)))}%"></span></div></div>`).join('')}<div class="performance-axis"><span>0</span><span>GDPval score</span><span>100</span></div></div><p class="performance-note">${esc(chart.qualification)}</p>${profileReferences(chart.claim_ids,'Experiment source')}</section>`:'';
  const context=related?`<section class="operating-case"><p class="eyebrow">Research collaboration</p><h3>${esc(related.title)}</h3><p>${esc(profileContextDescription(related.description,related.claim_ids))}</p>${profileReferences(related.claim_ids)}</section>`:'';
  return visual||context?`<div class="profile-performance-layout">${visual}${context}</div>`:'';
}
function profileOperatingMetrics(id,metrics=uniqueMetrics(id)){return metrics.filter(m=>!['valuation','funding_total_reported','funding_total_calculated'].includes(m.kind));}
function profileHeadlineMetrics(id,all=uniqueMetrics(id)){
 const config=profileContent(id),primary=preferredFinancial(id),extras=all.filter(m=>['expert_network','headcount','active_paid_experts'].includes(m.kind)&&m.segment_scope!=='other_segment');
 const selected=config.metric_ids?config.metric_ids.map(mid=>all.find(m=>m.id===mid)).filter(Boolean):primary?[primary]:[];if(!config.metric_ids)for(const m of extras)if(!selected.some(x=>x.kind===m.kind)&&selected.length<3)selected.push(m);
 return selected;
}
function profileFiguresHeading(id){return profileContent(id).traction_heading||(profileHeadlineMetrics(id).every(m=>metricStatusLabel(m)==='Reported')?'Reported figures':'Key figures');}
function profileTraction(id){
 const config=profileContent(id),all=uniqueMetrics(id),selected=profileHeadlineMetrics(id,all);
 const metrics=selected.map(m=>{const context=config.metric_context?.[m.id],scope=context?.scope||(m.scope_detail&&!['company','ai_data','other_segment'].includes(m.scope_detail)?m.scope_detail:scopeText(m.segment_scope,id));const html=`<article class="profile-scale-observation">${profileMetricTags(m)}<div class="scale-number">${profileNumberButton(m)}</div><h3 class="observation-label">${esc(profileMetricLabel(m))}</h3><p class="observation-scope">${esc(scope)}${m.currency?' · '+esc(m.currency):''}</p><p class="observation-date">${esc(profileMetricDate(m))}</p><p class="observation-note">${esc(profileMetricAttribution(m))}</p>${context?.note&&!/^Undated company claim$/i.test(context.note)?`<p class="observation-note">${esc(context.note)}</p>`:''}${m.kind==='revenue'&&m.gross_vs_net==='unspecified'?'<p class="observation-note">Gross or net revenue not stated</p>':''}${m.kind==='annualized_revenue_run_rate'?`<p class="metric-definition">Annualized pace (recent revenue projected across a full year).</p><p class="observation-note">${esc(metricCurrentBasisDescription(m,m.gross_vs_net==='unspecified'?'The source does not say whether revenue is gross or net.':m.gross_vs_net==='gross'?'Gross revenue (revenue before deductions described by its source).':'Net revenue (revenue after deductions described by its source).'))}</p>`:''}</article>`;const age=financialObservationAge(m);return age==='current'?html:`<details class="historical-profile-metric"><summary>${age==='undated'?'Undated financial claim':'Historical figure · '+esc(profileMetricDate(m))}</summary>${html}</details>`;}).join('');
 const observations=profileOperatingMetrics(id,all);
 return `${metrics?`<div class="profile-scale-grid">${metrics}</div>`:(config.activity?'':'<p class="profile-empty">Revenue is not publicly established.</p>')}${profileGrowth(id)}${profilePerformance(id)}${observations.length?`<p class="profile-archive-link"><a href="#company/${attr(id)}/observations">All dated figures (${observations.length}) ${iconHTML('right')}</a></p>`:''}`;
}
function profileArchive(id){
  const rows=table=>DATA[table].filter(r=>r.company_id===id),c=companies[id],registry=companySources(id);
  const products=rows('products').map(p=>`<article class="record" data-product="${attr(p.id)}"><h3>${esc(p.name)}</h3>${originalProductContextHTML(p)}<p>${esc(p.work_performed)}</p>${profileProvenance(claims[p.claim_id])}</article>`).join('');
  const peopleRows=rows('company_people').map(p=>`<article class="record" data-person="${attr(p.id)}"><h3>${esc(people[p.person_id].name)}</h3><p>${esc(title(p.role))}</p>${profileProvenance(claims[p.claim_id])}${(p.background_claim_ids||[]).map(id=>claimButton(id,'Background source')).join(' ')}</article>`).join('');
  const relationships=rows('customer_evidence').map(customerRecord).join('');
  const backers=(DATA.company_investors||[]).filter(r=>r.company_id===id).map(r=>`<article class="record" data-backer="${attr(r.id)}"><h3>${esc(investors[r.investor_id].name)}</h3><p>${esc(r.allocation)}</p>${profileProvenance(claims[r.claim_id])}</article>`).join('');
  const finance=rows('funding_rounds').map(r=>financingEvent(r).replace(' · Equity · ',' · '+esc(capitalLabel(r))+' · ')).join('')+disclosedPrimarySummary(id)+backers;
  const metricRows=uniqueMetrics(id),financeMetrics=metricRows.filter(m=>['valuation','funding_total_reported','funding_total_calculated'].includes(m.kind));
  const operatingMetrics=profileOperatingMetrics(id,metricRows),financeHTML=finance+(financeMetrics.length?`<div class="metric-grid">${financeMetrics.map(metricTile).join('')}</div>`:'');
  const method=DATA.assessments.filter(a=>a.company_id===id).map(renderAssessment).join('')+rows('company_relationships').map(r=>`<p>${esc(title(r.relationship))} ${esc(r.related_entity_name)} · ${claimButton(r.claim_id,'Source')}</p>`).join('');
  const scope=method||(c.entity_type==='adjacent_research'?'<p>Research organizations are outside the commercial assessment rules.</p>':'');
  const observations=operatingMetrics.length?`<details id="profile-observations" data-profile-section="observations"><summary>All dated figures</summary><div class="metric-grid">${operatingMetrics.map(metricTile).join('')}</div></details>`:profileRouteSection(routeParts()[2])==='observations'?'<section id="profile-observations" data-profile-section="observations"><h2>All dated figures</h2><p class="profile-empty">No dated figures are established in the reviewed sources.</p></section>':'';
  const sourceHTML=`<section id="profile-sources" data-profile-section="sources"><h2>All sources</h2><ol class="sources-list">${registry.map(s=>`<li data-source="${attr(s.id)}">${external(s.url,s.title)}<p class="sub">${esc(profileSourceMeta(s))}</p></li>`).join('')}</ol></section>`;
  const logo=logoFor(id),brand=logo?`<details><summary>Logo source</summary><p>${external(logo.source_page||logo.source_url,'Original source')} · Checked ${esc(profileDate(logo.verified_on||logo.accessed_on||'2026-10-14'))}</p></details>`:'';
  const finances=financeHTML?`<details class="profile-disclosure" id="profile-financing" data-profile-section="financing"><summary>Funding records</summary>${financeHTML}</details>`:'';
  return `<div class="profile-archive"><div class="archive-intro">${typeof sourceUpdatesArchiveHTML==='function'?sourceUpdatesArchiveHTML(id):''}${evidenceContextArchiveHTML(id)}<p>${companyClaims(id).length} claims and ${registry.length} sources</p><nav aria-label="Evidence sections">${operatingMetrics.length?`<a href="#company/${attr(id)}/observations">All dated figures</a>`:''}${finances?`<a href="#company/${attr(id)}/financing">Funding records</a>`:''}<a href="#company/${attr(id)}/questions">All claims</a><a href="#company/${attr(id)}/sources">All sources</a></nav></div>${products?profileDisclosure('Product records',products):''}${relationships?profileDisclosure('Relationship records',relationships):''}${peopleRows?profileDisclosure('Leadership records',peopleRows):''}${finances}${observations}${scope?`<section id="profile-method" data-profile-section="method"><h2>Assessment and scope</h2>${scope}</section>`:''}${profileDisclosure('All claims and historical evidence',`<div id="profile-questions" data-profile-section="questions">${companyClaims(id).map(claimRecord).join('')}</div>`)}${brand}${sourceHTML}</div>`;
}
const PROFILE_ARCHIVE_SECTIONS=['method','questions','sources','observations','financing'];
// A record link opens the tab that holds the record.
function profileTarget(id,parts=routeParts()){
 const claim=parts[2]==='claim'?claims[parts[3]]:null;
 if(claim?.company_id===id){const section=narrativeSection(claim);return ['products','customers','traction','people','finance','work'].includes(section)?section:'business';}
 return profileRouteSection(parts[2])||'business';
}
// Logos beside a visible name are decorative.
function profileLogoHTML(id,extra){return logoHTML(id,extra,true).replace(/ alt="[^"]*"/,' alt=""');}
function profilePeersHTML(id){
 const group=modelGroup(id),members=(MODEL_GROUPS[group]||[]).filter(peer=>companies[peer]),peers=members.filter(peer=>peer!==id).sort((a,b)=>companies[a].name.localeCompare(companies[b].name));
 if(!peers.length)return '';
 return `<section class="profile-peers" aria-labelledby="profile-peers-title"><h2 id="profile-peers-title">More in ${esc(groupLabel(group))}</h2><ul>${peers.map(peer=>`<li><a href="#company/${attr(peer)}">${logoFor(peer)?profileLogoHTML(peer,'peer-logo'):''}<span>${esc(companies[peer].name)}</span></a></li>`).join('')}</ul><p><a class="profile-peers-all" href="#companies/${attr(groupSlug(group))}" data-category-jump="${attr(group)}">${members.length===2?'Both companies':'All '+members.length+' companies'} in this group ${iconHTML('right')}</a></p></section>`;
}
function profileAtAGlance(id){
 const financial=preferredFinancial(id),research=companies[id].entity_type==='adjacent_research',offering=profileProducts(id).find(p=>p.name),metric=financial?(typeof financialSummaryHTML==='function'?financialSummaryHTML(id):compactSignal(id)):`<span class="profile-main-offering">${esc(offering?.name||(research?'Public AI research':'AI data services'))}</span><p class="profile-revenue-note">${research?'Nonprofit research organization':'Revenue not disclosed in the reviewed sources.'}</p>`;
 return `<div class="profile-at-a-glance"><div class="profile-glance-metric"><span class="eyebrow">${financial?'Latest financial evidence':research?'Research focus':'Main offering'}</span>${metric}</div><div class="profile-glance-work"><span class="eyebrow">Work routes</span><p>${esc(workType(id))}</p><a href="#company/${attr(id)}/work">View listings & requirements ${iconHTML('right')}</a></div></div>`;
}
function profileHTML(id,{deferArchive=false}={}){
 const c=companies[id],config=profileContent(id),target=profileTarget(id),active=target==='observations'?'traction':profileTabFor(target),archiveOpen=PROFILE_ARCHIVE_SECTIONS.includes(target);
 const notes=(config.notes||[]).map(n=>typeof n==='string'?`<p>${esc(n)}</p>`:`<p>${esc(n.text)} ${profileReferences(n.claim_ids)}</p>`).join('');
 const group=modelGroup(id),category=`<p class="profile-category">${esc(groupLabel(group))}</p>`;
 const background=config.summary&&config.summary!==modelFor(id)?`<details class="profile-background"><summary>About the business</summary><p>${esc(config.summary)}</p></details>`:'';
 const panes={business:`${background}<div class="profile-business-layout ${config.featured_case?'has-case':''}">${profileSection('products',config.product_heading||'Products and services',profileProductGrid(id))}${profileCase(id)}</div>${typeof productMediaHTML==='function'?productMediaHTML(id):''}${profileSection('customers','Who it works with',profileRelationshipGrid(id))}${profileRisks(id)}`,
 traction:profileSection('traction',profileFiguresHeading(id),`${config.activity?`<div class="profile-activity"><h3>${esc(config.activity.title)}</h3><p>${esc(config.activity.description)}</p>${profileReferences(config.activity.claim_ids)}</div>`:''}${profileTraction(id)}`),
 people:`<div class="profile-people-layout">${profileSection('finance',c.entity_type==='adjacent_research'?'Research support':'Funding and valuation',profileCapital(id))}${profileSection('people','Founders and leadership',profilePeople(id))}</div>`+(notes?profileDisclosure('Further context',notes):''),
 work:profileSection('work','Paid work at '+c.name,workSummary(id))};
 const tabs=[['business','Business'],['traction','Figures'],['people','Funding & people'],['work','Paid work']];
 return `<div class="profile-v2" data-profile-company="${attr(id)}"><a class="profile-back" href="#companies">${iconHTML('left')} Companies</a><header class="profile-top profile-hero"><div class="profile-title-row">${profileLogoHTML(id,'profile-brand')}<h1>${esc(c.name)}</h1></div><p class="profile-summary">${esc(modelFor(id))}</p><a class="profile-group-link" href="#companies/${attr(groupSlug(group))}" data-category-jump="${attr(group)}">${esc(groupLabel(group))} ${iconHTML('right')}</a><div class="profile-links">${external(c.website,'Website')}${c.founded_year?`<span>Founded ${c.founded_year}</span>`:''}${compareCheck(id)}<a href="#company/${attr(id)}/sources">Sources ${iconHTML('right')}</a><a href="/company/${attr(id)}/">Plain page to share ${iconHTML('right')}</a></div></header>${profileAtAGlance(id)}<nav class="profile-tabs" role="tablist" aria-label="${attr(c.name)} details">${tabs.map(([key,label])=>`<button type="button" role="tab" id="profile-tab-${key}" data-profile-tab="${key}" aria-controls="profile-pane-${key}" aria-selected="${active===key}" tabindex="${active===key?0:-1}">${esc(label)}</button>`).join('')}</nav><div class="profile-panes">${tabs.map(([key])=>`<section id="profile-pane-${key}" role="tabpanel" aria-labelledby="profile-tab-${key}" tabindex="-1" data-profile-pane="${key}"${active===key?'':' hidden'}>${panes[key]}</section>`).join('')}</div><details class="profile-evidence"${archiveOpen?' open':''}><summary><span class="archive-summary-label">Sources and review <i aria-hidden="true">+</i></span><span>${companyClaims(id).length} claims · ${companySources(id).length} sources</span></summary>${deferArchive&&!archiveOpen?'':profileArchive(id)}</details><p class="profile-correction">Something wrong here? <a href="#corrections">Request a correction ${iconHTML('right')}</a></p>${profilePeersHTML(id)}</div>`;
}

function ensureProfileArchive(root){
 const container=$('profile-view'),id=root?.dataset?.profileCompany;
 // Queued disclosure events from a replaced profile must not populate stale DOM.
 if(!isCompanyId(id)||container.querySelector?.('.profile-v2')!==root)return null;
 const evidence=root.querySelector('.profile-evidence');if(!evidence)return null;
 const existing=evidence.querySelector('.profile-archive');if(existing)return existing;
 evidence.insertAdjacentHTML('beforeend',profileArchive(id));
 return evidence.querySelector('.profile-archive');
}

function renderCompanyProfile(id){
 const container=$('profile-view'),existing=container.querySelector?.('.profile-v2');
 const render=()=>{container.innerHTML=profileHTML(id,{deferArchive:typeof container.querySelector==='function'});};
 if(!existing||existing.dataset.profileCompany!==id){render();return;}
 const target=profileTarget(id);
 // With no operating figures, the archive has a placeholder only on the
 // observations route. Preserve that existing conditional presentation.
 const emptyObservation=existing.querySelector('#profile-observations')?.tagName==='SECTION';
 if(emptyObservation!==(target==='observations'&&!profileOperatingMetrics(id).length)){
  render();return;
 }
 if(PROFILE_ARCHIVE_SECTIONS.includes(target)||existing.querySelector('.profile-evidence')?.open)ensureProfileArchive(existing);
 const active=target==='observations'?'traction':profileTabFor(target);
 existing.querySelectorAll('[data-profile-pane]').forEach(pane=>{pane.hidden=pane.dataset.profilePane!==active;});
 existing.querySelectorAll('[data-profile-tab]').forEach(tab=>{
  const selected=tab.dataset.profileTab===active;
  tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
 });
}

// Click precedes the native summary action, including Enter/Space activation.
// Toggle does not bubble, so capture also covers programmatic disclosure opens.
document.addEventListener('click',event=>{
 const summary=event.target.closest?.('summary'),evidence=summary?.parentElement;
 if(evidence?.classList.contains('profile-evidence')&&!evidence.open)ensureProfileArchive(evidence.closest('.profile-v2'));
});
document.addEventListener('toggle',event=>{
 const evidence=event.target;
 if(evidence?.open&&evidence.classList?.contains('profile-evidence'))ensureProfileArchive(evidence.closest('.profile-v2'));
},true);

// Keep comparison content aligned with the visible profiles.
const profileComparisonRows=comparisonRows;
comparisonRows=function(){return profileComparisonRows().map(([label,render])=>{
  if(label==='Products')return [label,id=>`<p>${profileProducts(id).slice(0,4).map(p=>esc(p.name)+(p.status?`<span class="sub">${esc(title(p.status))}</span>`:'')+(p.source_updates?.length?`<span class="sub">${esc(p.description)}</span>${productSourceHTML(p)}`:'')).join('<br>')}</p><a href="#company/${attr(id)}/products">Explore products ${iconHTML('right')}</a>`];
  if(label==='Customer evidence')return ['Relationships',id=>`${profileRelationships(id).slice(0,2).map(r=>`<p><b>${esc(r.name)}</b><span class="sub">${esc(profileRelationshipLabel(id,r))}</span>${profileRelationshipScopeContext(id,r)?`<span class="sub">${esc(profileRelationshipScopeContext(id,r))}</span>`:''}</p>`).join('')||'<p class="sub">No named relationship established.</p>'}<a href="#company/${attr(id)}/customers">Who it works with ${iconHTML('right')}</a>`];
  if(label==='People')return [label,id=>{
    const rows=profilePeopleRows(id);
    return `<p>${rows.slice(0,3).map(p=>`${esc(people[p.person_id]?.name||p.name)} <span class="sub">${esc(p.role)}</span>`).join('<br>')||'Not established'}</p><a href="#company/${attr(id)}/people">Funding &amp; people ${iconHTML('right')}</a>`;
  }];
  return [label,render];
});};

// Direct links can scroll before a lazy product image above the archive has its
// height. Correct that initial position after the visible images and page settle.
let profileHasRouted=false,profileInitialAnchorCleanup=null;
function settleInitialProfileAnchor(hash,destination){
  let cancelled=false;
  const events=['wheel','touchstart','pointerdown','keydown'];
  const cancel=()=>{cancelled=true;for(const name of events)window.removeEventListener(name,cancel);};
  profileInitialAnchorCleanup=cancel;
  for(const name of events)window.addEventListener(name,cancel,{passive:true});
  const top=destination.getBoundingClientRect().top;
  const images=[...document.querySelectorAll('.profile-v2 img')].filter(img=>img.getClientRects().length&&img.getBoundingClientRect().top<top&&!img.complete);
  const pending=images.map(img=>new Promise(resolve=>{
    const ready=()=>{img.removeEventListener('load',ready);img.removeEventListener('error',ready);resolve();};
    img.addEventListener('load',ready);img.addEventListener('error',ready);
    img.loading='eager';
  }));
  if(document.readyState!=='complete')pending.push(new Promise(resolve=>window.addEventListener('load',resolve,{once:true})));
  const frame=callback=>typeof requestAnimationFrame==='function'?requestAnimationFrame(callback):setTimeout(callback,0);
  Promise.all(pending).then(()=>frame(()=>frame(()=>{
    if(!cancelled&&location.hash===hash&&destination.isConnected)destination.scrollIntoView({block:'start',behavior:'instant'});
    cancel();if(profileInitialAnchorCleanup===cancel)profileInitialAnchorCleanup=null;
  })));
}
// The Navigation API distinguishes a new fragment from history traversal.
// Without it, an entry the reader has not scrolled yet has no saved position in history.state
// (app.js writes one while they scroll), so that entry is new. Back and Forward keep the browser's restore.
let profileFragmentNavigation=null;
window.navigation?.addEventListener('navigate',event=>{
  profileFragmentNavigation=event.hashChange&&event.destination.sameDocument?{url:event.destination.url,type:event.navigationType}:null;
});
const profileRoute=route;
route=function(event){
  const initial=!profileHasRouted;profileHasRouted=true;
  profileInitialAnchorCleanup?.();profileInitialAnchorCleanup=null;
  const previousCompany=previousRoute==='company'?document.querySelector('.profile-v2')?.dataset.profileCompany:null;
  const fragmentNavigation=profileFragmentNavigation;
  if(event?.type==='hashchange')profileFragmentNavigation=null;
  const result=profileRoute.apply(this,arguments);let parts=routeParts();
  // Rewrite case-variant addresses (#company/MERCOR) to the canonical id.
  const company=String(parts[0]).toLowerCase()==='company'?profileRouteCompany(parts[1]):'';
  if(company&&(company!==parts[1]||parts[0]!=='company')){parts[0]='company';parts[1]=company;history.replaceState(history.state??null,'','#'+parts.map(encodeURIComponent).join('/'));parts=routeParts();}
  const freshEntry=!window.navigation&&typeof history.state?.scrollY!=='number';
  const newFragment=event?.type==='hashchange'&&(fragmentNavigation?fragmentNavigation.url===event.newURL&&['push','replace'].includes(fragmentNavigation.type):freshEntry);
  if(newFragment&&previousCompany&&parts[0]==='company'&&isCompanyId(parts[1])&&parts[1]!==previousCompany&&!parts[2])window.scrollTo({left:0,top:0,behavior:'instant'});
  if(parts[0]==='company'&&isCompanyId(parts[1])&&parts[2]){
    const section=profileRouteSection(parts[2]);
    const primary=['business','traction','people','work'].includes(section);
    const destination=profileRouteDestination(section);
    if(destination){
      for(let node=destination;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
      const focusTarget=destination.tagName==='DETAILS'?destination.querySelector('summary'):destination;
      if(focusTarget&&focusTarget.tagName!=='SUMMARY')focusTarget.setAttribute('tabindex','-1');
      if(event?.type==='hashchange')focusTarget?.focus({preventScroll:true});
      (primary?document.querySelector('.profile-tabs'):destination)?.scrollIntoView({block:'start',behavior:'instant'});
      if(initial&&!primary)settleInitialProfileAnchor(location.hash,destination);
    }
  }
  if(company&&parts[2]==='claim'&&claims[parts[3]]?.company_id===company)showEvidence(parts[3]);
  return result;
};
function profileTabHash(id){const tab=document.querySelector('#profile-view .profile-tabs [aria-selected="true"]')?.dataset?.profileTab;return '#company/'+id+(tab&&tab!=='business'?'/'+tab:'');}
document.addEventListener('keydown',event=>{
  const tab=event.target.closest?.('[data-profile-tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const ids=['business','traction','people','work'],index=ids.indexOf(tab.dataset.profileTab),next=event.key==='Home'?0:event.key==='End'?3:(index+(event.key==='ArrowRight'?1:3))%4;
  event.preventDefault();activateProfileTab(ids[next]);
  document.getElementById('profile-tab-'+ids[next])?.focus({preventScroll:true});
});

document.addEventListener('click',event=>{if(event.target.closest?.('.skip')){event.preventDefault();$('main').focus({preventScroll:true});$('main').scrollIntoView({behavior:'instant'});}});
