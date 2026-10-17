/* Public, source-linked profile presentation. Raw records remain in the archive. */
function profileContent(id){return (window.PROFILE_CONTENT?.entries||[]).find(e=>e.company_id===id)||{};}
function profileDate(value){return /^\d{4}-\d{2}-\d{2}$/.test(value)?new Date(value+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):dateText(value);}
function profileReferences(ids,label='Source',topic=''){
  const unique=[...new Set(ids||[])].filter(id=>claims[id]);
  if(unique.length<2)return unique.map(id=>claimButton(id,label,topic)).join('');
  const visibleLabel=label==='Source'?'Sources':label,access=evidenceAccess(unique,visibleLabel,topic);
  return `<button type="button" class="evidence-link" data-profile-evidence="${attr(unique.join('|'))}" ${access.attributes}>${esc(visibleLabel)}</button>${access.description}`;
}
document.addEventListener('click',event=>{const button=event.target.closest?.('[data-profile-evidence]');if(!button)return;const ids=button.dataset.profileEvidence.split('|').filter(id=>claims[id]);if(!ids.length)return;showEvidence(ids[0]);$('evidence-content').insertAdjacentHTML('beforeend',`<h3>Related evidence</h3>${ids.slice(1).map((id,i)=>claimButton(id,'Supporting claim '+(i+2))).join(' ')}`);});
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
function profileProductGrid(id){const rows=[...profileProducts(id)].sort((a,b)=>Number(Boolean(b.description))-Number(Boolean(a.description)));const render=items=>`<div class="profile-product-grid">${items.map(p=>`<article class="offering-card" data-profile-product="${attr(p.name)}"><div class="offering-title"><h3>${esc(p.name)}</h3>${p.kind?`<p class="offering-kind">${esc(p.kind)}</p>`:''}</div><div class="offering-description">${p.description?`<p>${esc(p.description)}</p>`:''}${p.status?`<p class="offering-status">${esc(title(p.status))}</p>`:''}${p.aliases?.length?`<details class="offering-aliases"><summary>Other names in the source</summary><p>${esc(p.aliases.join(' · '))}</p></details>`:''}</div><div class="profile-card-source">${typeof productSourceHTML==='function'?productSourceHTML(p,'Source',p.name):profileReferences(p.claim_ids,'Source',p.name)}${typeof productSourceContextHTML==='function'?productSourceContextHTML(p):''}</div></article>`).join('')}</div>`;return render(rows.slice(0,4))+(rows.length>4?profileDisclosure(`More offerings (${rows.length-4})`,render(rows.slice(4))):'');}
function profileCase(id){const c=profileContent(id).featured_case;if(!c)return '';return `<aside class="featured-case"><p class="eyebrow">${esc(c.eyebrow||'A closer look')}</p><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p>${c.qualifier?`<p class="case-qualifier">${esc(c.qualifier)}</p>`:''}${profileReferences(c.claim_ids,'Case source',c.title)}</aside>`;}
function profileContextDescription(text,claimIds=[]){
 if(!claimIds.some(id=>['afterquery.claim.round2-relationship-3','afterquery.claim.round2-research-legora-bar'].includes(id)))return text;
 return String(text||'').replace('synthetic BAR case','synthetic case for BAR (an evaluation of AI on legal work)').replace('BAR uses','BAR (an evaluation of AI on legal work) uses');
}
function profileRelationshipGrid(id){const rows=profileRelationships(id),featured=profileContent(id).featured_case;const render=items=>`<div class="profile-relationship-grid">${items.map(r=>`<article class="relationship-card" data-profile-relationship="${attr(r.name)}"><div><h3>${esc(r.name)}</h3><p class="relationship-kind">${esc(profileRelationshipLabel(id,r))}</p></div><div class="relationship-account">${r.description&&r.description!==featured?.description?`<p>${esc(profileContextDescription(r.description,r.claim_ids))}</p>`:''}${profileRelationshipScopeContext(id,r)?`<p class="sub">${esc(profileRelationshipScopeContext(id,r))}</p>`:''}</div><div class="profile-card-source">${profileReferences(r.claim_ids,'Source',r.name)}</div></article>`).join('')}</div>`;return rows.length?render(rows.slice(0,4))+(rows.length>4?profileDisclosure(`More relationships (${rows.length-4})`,render(rows.slice(4))):''):'<p class="profile-empty">Named relationships are not established in the reviewed sources.</p>';}
function profilePeopleRows(id){
  const curated=profileContent(id).people;
  const all=curated?.length?curated:DATA.company_people.filter(p=>p.company_id===id).map(p=>({person_id:p.person_id,role:title(p.role),bio:'',claim_ids:[p.claim_id]}));
  return all.filter(p=>!p.historical&&!/early founding|historical/i.test(p.role)&&(!/\bformer\b/i.test(p.role)||/\badvisor\b/i.test(p.role)));
}
function profilePeople(id){
  const rows=profilePeopleRows(id);
  return rows.length?`<div class="leadership-grid">${rows.map(p=>`<article class="leadership-card">${p.portrait?`<span class="leadership-photo ${p.portrait.includes('carlos')?'photo-tighter':''}"><img class="leadership-portrait" src="${attr(p.portrait)}" alt="${attr(people[p.person_id]?.name||p.name)}" width="80" height="80" loading="lazy"></span>`:''}<div><h3>${esc(people[p.person_id]?.name||p.name)}</h3><p class="leadership-role">${esc(p.role)}</p>${p.bio?`<p>${esc(p.bio)}</p>`:''}${profileReferences(p.claim_ids,'Source',people[p.person_id]?.name||p.name)}</div></article>`).join('')}</div>`:'<p class="profile-empty">Leadership is not established in the reviewed sources.</p>';
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
 return `<div class="capital-grid">${current.slice(0,3).map(r=>{
  const context=profileCapitalContext(r),leads=DATA.round_investors.filter(x=>x.round_id===r.id&&claims[x.claim_id||r.claim_id]?.status==='supported'&&/lead/i.test(x.role)).map(x=>investors[x.investor_id].name);
  return `<article class="capital-event" data-capital-round="${attr(r.id)}"><div class="capital-time"><p class="capital-date">${esc(context.dateLabel||'Announced')}<span>${esc(profileDate(r.announced_on))}</span></p>${r.closed_on?`<p class="sub">Closed ${esc(profileDate(r.closed_on))}</p>`:''}</div><div class="capital-data"><p class="capital-label">${esc(capitalLabel(r))}</p><h3>${'amount'in r?esc(metricValue({value:r.amount,unit:'currency',currency:r.currency,qualifier:r.qualifier})):'Amount undisclosed'}</h3>${r.capital_type==='mixed'&&r.amount_basis==='undisclosed'?'<p class="sub capital-scope">Company-reported financing includes equity and credit. Component amounts and credit drawdown are undisclosed.</p>':''}${r.amount_basis==='mixed_transaction'?'<p class="sub capital-scope">Includes existing shares sold by shareholders. The total is not all new company funding.</p>':''}${context.qualification?`<p class="sub capital-scope">${esc(context.qualification)}</p>`:''}${leads.length?`<p class="sub">Led by ${esc(leads.join(', '))}</p>`:''}${combined?`<div class="capital-valuation">${numberButton(combined)}<span>Valuation at the round</span></div>`:''}<p class="sub">${config.capital_note?esc(config.capital_note):r.status==='announced'?'':esc(title(r.status))}${r.capital_type==='secondary'?' · Existing shares':''}</p>${profileReferences([r.claim_id],'Round evidence')}</div></article>`;
 }).join('')}${valuations.filter(m=>m!==combined).slice(0,1).map(m=>`<article class="capital-event valuation-event"><div class="capital-time"><p class="capital-date">As of<span>${esc(profileDate(m.as_of))}</span></p></div><div class="capital-data"><p class="capital-label">${esc(/pre.money/i.test(m.label)?'Pre-money valuation':/post.money/i.test(m.label)?'Post-money valuation':'Valuation')}</p><h3>${numberButton(m)}</h3><p class="sub">${esc(scopeText(m.segment_scope,id))}</p>${/pre.money/i.test(m.label)?'<p class="sub">Company value before the new investment is added.</p>':''}<p class="sub">${esc(evidenceLabel(claims[m.claim_id]))}</p></div></article>`).join('')}</div>${!current.length&&!valuations.length?'<p class="profile-empty">No quantified financing is established in the reviewed sources.</p>':''}${outcomeHTML}${rounds.some(r=>claims[r.claim_id]?.status!=='supported'||uncertainStatus.includes(r.status))||uniqueMetrics(id).some(unconfirmedValuation)?`<p class="sub">Other financing records are retained in the <a href="#company/${attr(id)}/questions">evidence archive</a>.</p>`:''}`;
}
function profileMetricLabel(m){
  if(m.id==='ooak.metric.audit-ooak-headcount-scope'&&m.company_id==='ooak'&&m.kind==='headcount'&&m.label==='directory_team_size')return 'YC-listed team size';
  if(m.kind==='annualized_revenue_run_rate')return 'Annualized revenue pace';
  if(['expert_network','headcount','active_paid_experts','other'].includes(m.kind))return m.label;
  return metricLabels[m.kind]||m.label;
}
function profileMetricDate(m){
 const corrected=metricCurrentPeriod(m);if(corrected)return corrected;
 if(m.kind==='revenue')return m.period_label||financialPeriod(m);
 if(m.as_of==='undated')return 'Undated · checked '+profileDate(claims[m.claim_id].observed_on);
 return 'As of '+profileDate(String(m.as_of).replace(/^as of\s+/i,''));
}
const PROFILE_METRIC_ATTRIBUTIONS={
 'elorian.claim.core-elorian.claim.growth_metrics-0.metric-0-metric':'Employer job listing',
 'abundant_ai.claim.audit-abundant-network-metric':'Company-authored Y Combinator profile',
 'ooak.claim.audit-ooak-headcount-scope-metric':'Y Combinator profile snapshot',
 'laude.claim.audit-laude-deployed-grants-metric':'Institute-reported grantmaking'
};
function profileMetricAttribution(m){
 const claim=claims[m.claim_id];
 if(claim.status!=='supported'||claim.source_ids.length&&claim.source_ids.every(id=>sources[id].retrieval_status==='unverified'))return evidenceLabel(claim);
 return metricCurrentAttribution(m,PROFILE_METRIC_ATTRIBUTIONS[claim.id]||evidenceLabel(claim));
}
function profilePerformance(id){
  const config=profileContent(id),chart=config.performance_chart,related=config.operating_case;const chartTitle=chart&&/GDPval/i.test(chart.title)?'Initial training comparison':chart?.title,seriesLabel=value=>String(value).replace(/warmup/gi,'initial training');
  const visual=chart?`<section class="profile-performance"><p class="eyebrow">Performance experiment</p><h2>${esc(chartTitle)}</h2>${/GDPval/i.test(chart.title)?'<p class="sub">GDPval tests AI on professional work tasks. This experiment compares training with and without an initial preparation stage.</p>':''}<p class="sub">${esc(chart.subtitle)}</p><div class="performance-bars" role="img" aria-label="${attr(chart.title+': '+chart.series.map(s=>s.label+' '+s.value).join('; ')+'. Scale zero to 100.')}">${chart.series.map(s=>`<div class="performance-row"><div><span>${esc(seriesLabel(s.label))}</span><strong>${esc(s.value)}</strong></div><div class="performance-track"><span style="width:${Math.max(0,Math.min(100,Number(s.value)))}%"></span></div></div>`).join('')}<div class="performance-axis"><span>0</span><span>GDPval score</span><span>100</span></div></div><p class="performance-note">${esc(chart.qualification)}</p>${profileReferences(chart.claim_ids,'Experiment source')}</section>`:'';
  const context=related?`<aside class="operating-case"><p class="eyebrow">Research collaboration</p><h3>${esc(related.title)}</h3><p>${esc(profileContextDescription(related.description,related.claim_ids))}</p>${profileReferences(related.claim_ids)}</aside>`:'';
  return visual||context?`<div class="profile-performance-layout">${visual}${context}</div>`:'';
}
function profileOperatingMetrics(id,metrics=uniqueMetrics(id)){return metrics.filter(m=>!['valuation','funding_total_reported','funding_total_calculated'].includes(m.kind));}
function profileTraction(id){
 const config=profileContent(id),all=uniqueMetrics(id),primary=preferredFinancial(id),extras=all.filter(m=>['expert_network','headcount','active_paid_experts'].includes(m.kind)&&m.segment_scope!=='other_segment');
 const selected=config.metric_ids?config.metric_ids.map(mid=>all.find(m=>m.id===mid)).filter(Boolean):primary?[primary]:[];if(!config.metric_ids)for(const m of extras)if(!selected.some(x=>x.kind===m.kind)&&selected.length<3)selected.push(m);
 const metrics=selected.map(m=>{const context=config.metric_context?.[m.id],scope=context?.scope||(m.scope_detail&&!['company','ai_data','other_segment'].includes(m.scope_detail)?m.scope_detail:scopeText(m.segment_scope,id));return `<article class="profile-scale-observation"><div class="scale-number">${numberButton(m)}</div><h3 class="observation-label">${esc(profileMetricLabel(m))}</h3><p class="observation-scope">${esc(scope)}${m.currency?' · '+esc(m.currency):''}</p><p class="observation-date">${esc(profileMetricDate(m))}</p><p class="observation-note">${esc(profileMetricAttribution(m))}</p>${context?.note&&!/^Undated company claim$/i.test(context.note)?`<p class="observation-note">${esc(context.note)}</p>`:''}${m.kind==='revenue'&&m.gross_vs_net==='unspecified'?'<p class="observation-note">Gross or net revenue not stated</p>':''}${m.kind==='annualized_revenue_run_rate'?`<p class="metric-definition">Annualized pace (recent revenue projected across a full year).</p><p class="observation-note">${esc(metricCurrentBasisDescription(m,m.gross_vs_net==='unspecified'?'The source does not say whether revenue is gross or net.':m.gross_vs_net==='gross'?'Gross revenue (revenue before deductions described by its source).':'Net revenue (revenue after deductions described by its source).'))}</p>`:''}</article>`;}).join('');
 const observations=profileOperatingMetrics(id,all);
 return `${metrics?`<div class="profile-scale-grid">${metrics}</div>`:(config.activity?'':'<p class="profile-empty">Revenue is not publicly established.</p>')}${profileGrowth(id)}${profilePerformance(id)}${observations.length?`<p class="profile-archive-link"><a href="#company/${attr(id)}/observations">Operating observations (${observations.length}) ${iconHTML('right')}</a></p>`:''}`;
}
function profileArchive(id){
  const rows=table=>DATA[table].filter(r=>r.company_id===id),c=companies[id],registry=companySources(id);
  const products=rows('products').map(p=>`<article class="record" data-product="${attr(p.id)}"><h3>${esc(p.name)}</h3>${originalProductContextHTML(p)}<p>${esc(p.work_performed)}</p>${provenance(claims[p.claim_id])}</article>`).join('');
  const peopleRows=rows('company_people').map(p=>`<article class="record" data-person="${attr(p.id)}"><h3>${esc(people[p.person_id].name)}</h3><p>${esc(title(p.role))}</p>${provenance(claims[p.claim_id])}${(p.background_claim_ids||[]).map(id=>claimButton(id)).join(' ')}</article>`).join('');
  const relationships=rows('customer_evidence').map(customerRecord).join('');
  const backers=(DATA.company_investors||[]).filter(r=>r.company_id===id).map(r=>`<article class="record" data-backer="${attr(r.id)}"><h3>${esc(investors[r.investor_id].name)}</h3><p>${esc(r.allocation)}</p>${provenance(claims[r.claim_id])}</article>`).join('');
  const finance=rows('funding_rounds').map(r=>financingEvent(r).replace(' · Equity · ',' · '+esc(capitalLabel(r))+' · ')).join('')+disclosedPrimarySummary(id)+backers;
  const metricRows=uniqueMetrics(id),financeMetrics=metricRows.filter(m=>['valuation','funding_total_reported','funding_total_calculated'].includes(m.kind));
  const operatingMetrics=profileOperatingMetrics(id,metricRows),financeHTML=finance+(financeMetrics.length?`<div class="metric-grid">${financeMetrics.map(metricTile).join('')}</div>`:'');
  const method=DATA.assessments.filter(a=>a.company_id===id).map(renderAssessment).join('')+rows('company_relationships').map(r=>`<p>${esc(title(r.relationship))} ${esc(r.related_entity_name)} · ${claimButton(r.claim_id,'Evidence')}</p>`).join('');
  const scope=method||(c.entity_type==='adjacent_research'?'<p>Research organizations are outside the commercial assessment rules.</p>':'');
  const observations=operatingMetrics.length?`<details id="profile-observations" data-profile-section="observations"><summary>Operating observations</summary><div class="metric-grid">${operatingMetrics.map(metricTile).join('')}</div></details>`:profileRouteSection(routeParts()[2])==='observations'?'<section id="profile-observations" data-profile-section="observations"><h2>Operating observations</h2><p class="profile-empty">No operating figures are established in the reviewed sources.</p></section>':'';
  const sourceHTML=`<section id="profile-sources" data-profile-section="sources"><h2>Source register</h2><ol class="sources-list">${registry.map(s=>`<li data-source="${attr(s.id)}">${external(s.url,s.title)}<p class="sub">${esc(s.publisher)} · ${s.published_on?'Published '+esc(s.published_on):'Undated'} · ${esc(sourceReviewText(s))}</p></li>`).join('')}</ol></section>`;
  const logo=logoFor(id),brand=logo?`<details><summary>Official brand asset</summary><p>${external(logo.source_page||logo.source_url,'Original source')} · ${esc(logo.verified_on||logo.accessed_on||'2026-10-14')}</p></details>`:'';
  return `<div class="profile-archive"><div class="archive-intro">${typeof sourceUpdatesArchiveHTML==='function'?sourceUpdatesArchiveHTML(id):''}${evidenceContextArchiveHTML(id)}<p>${companyClaims(id).length} claim records · ${registry.length} sources</p><nav aria-label="Evidence sections">${operatingMetrics.length?`<a href="#company/${attr(id)}/observations">Operating observations</a>`:''}<a href="#company/${attr(id)}/questions">All claims</a><a href="#company/${attr(id)}/sources">Source register</a></nav></div>${products?profileDisclosure('Product records',products):''}${relationships?profileDisclosure('Relationship records',relationships):''}${peopleRows?profileDisclosure('Leadership records',peopleRows):''}${financeHTML?profileDisclosure('Financing records',financeHTML):''}${observations}${scope?`<section id="profile-method" data-profile-section="method"><h2>Entity scope & method</h2>${scope}</section>`:''}${profileDisclosure('All claims and historical evidence',`<div id="profile-questions" data-profile-section="questions">${companyClaims(id).map(claimRecord).join('')}</div>`)}${brand}${sourceHTML}</div>`;
}
profileHTML=function(id,{deferArchive=false}={}){
 const c=companies[id],config=profileContent(id),target=profileRouteSection(routeParts()[2])||'business',active=target==='observations'?'traction':profileTabFor(target),archiveOpen=['method','questions','sources','observations'].includes(target);
 const notes=(config.notes||[]).map(n=>typeof n==='string'?`<p>${esc(n)}</p>`:`<p>${esc(n.text)} ${profileReferences(n.claim_ids)}</p>`).join('');
 const panes={business:`<div class="profile-business-intro"><p class="profile-category">${esc(groupLabel(modelGroup(id)))}</p><p>${esc(config.summary||modelFor(id))}</p></div><div class="profile-business-layout ${config.featured_case?'has-case':''}">${profileSection('products',config.product_heading||'Products and services',profileProductGrid(id))}${profileCase(id)}</div>${typeof productMediaHTML==='function'?productMediaHTML(id):''}${profileSection('customers','Evidence of use',profileRelationshipGrid(id))}`,
 traction:profileSection('traction',config.traction_heading||'Reported figures',`${config.activity?`<div class="profile-activity"><h3>${esc(config.activity.title)}</h3><p>${esc(config.activity.description)}</p>${profileReferences(config.activity.claim_ids)}</div>`:''}${profileTraction(id)}`),
 people:`<div class="profile-people-layout">${profileSection('people','Founders and leadership',profilePeople(id))}${profileSection('finance',c.entity_type==='adjacent_research'?'Research support':'Capital history',profileCapital(id))}</div>`+(notes?profileDisclosure('Further context',notes):''),
 work:profileSection('work','Work opportunities',workSummary(id))};
 const tabs=[['business','Business'],['traction','Figures'],['people','People & capital'],['work','Paid work']];
 return `<div class="profile-v2" data-profile-company="${attr(id)}"><a class="profile-back" href="#companies">${iconHTML('left')} Company index</a><header class="profile-top profile-hero"><div class="profile-title-row">${logoHTML(id,'profile-brand')}<h1>${esc(c.name)}</h1></div><div class="profile-links">${external(c.website,'Website')}${c.founded_year?`<span>Founded ${c.founded_year}</span>`:''}${compareCheck(id)}<a href="#company/${attr(id)}/sources">Sources ${iconHTML('external')}</a></div></header><nav class="profile-tabs" role="tablist" aria-label="${attr(c.name)} details">${tabs.map(([key,label])=>`<button type="button" role="tab" id="profile-tab-${key}" data-profile-tab="${key}" aria-controls="profile-pane-${key}" aria-selected="${active===key}" tabindex="${active===key?0:-1}" aria-pressed="${active===key}">${label}</button>`).join('')}</nav><div class="profile-panes">${tabs.map(([key])=>`<section id="profile-pane-${key}" role="tabpanel" aria-labelledby="profile-tab-${key}" tabindex="-1" data-profile-pane="${key}"${active===key?'':' hidden'}>${panes[key]}</section>`).join('')}</div><details class="profile-evidence"${archiveOpen?' open':''}><summary><span class="archive-summary-label">Sources and review <i aria-hidden="true">+</i></span><span>${companyClaims(id).length} claims · ${companySources(id).length} sources</span></summary>${deferArchive&&!archiveOpen?'':profileArchive(id)}</details></div>`;
};

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
 const target=profileRouteSection(routeParts()[2])||'business';
 // With no operating figures, the archive has a placeholder only on the
 // observations route. Preserve that existing conditional presentation.
 const emptyObservation=existing.querySelector('#profile-observations')?.tagName==='SECTION';
 if(emptyObservation!==(target==='observations'&&!profileOperatingMetrics(id).length)){
  render();return;
 }
 if(['method','questions','sources','observations'].includes(target)||existing.querySelector('.profile-evidence')?.open)ensureProfileArchive(existing);
 const active=target==='observations'?'traction':profileTabFor(target);
 existing.querySelectorAll('[data-profile-pane]').forEach(pane=>{pane.hidden=pane.dataset.profilePane!==active;});
 existing.querySelectorAll('[data-profile-tab]').forEach(tab=>{
  const selected=tab.dataset.profileTab===active;
  tab.setAttribute('aria-selected',String(selected));tab.setAttribute('aria-pressed',String(selected));tab.tabIndex=selected?0:-1;
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
  if(label==='Customer evidence')return ['Relationships',id=>`${profileRelationships(id).slice(0,2).map(r=>`<p><b>${esc(r.name)}</b><span class="sub">${esc(profileRelationshipLabel(id,r))}</span>${profileRelationshipScopeContext(id,r)?`<span class="sub">${esc(profileRelationshipScopeContext(id,r))}</span>`:''}</p>`).join('')||'<p class="sub">No named relationship established.</p>'}<a href="#company/${attr(id)}/customers">Evidence of use ${iconHTML('right')}</a>`];
  if(label==='People')return [label,id=>{
    const rows=profilePeopleRows(id);
    return `<p>${rows.slice(0,3).map(p=>`${esc(people[p.person_id]?.name||p.name)} <span class="sub">${esc(p.role)}</span>`).join('<br>')||'Not established'}</p><a href="#company/${attr(id)}/people">People & roles ${iconHTML('external')}</a>`;
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
// Without it, retain the browser's existing scroll behavior.
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
  const result=profileRoute.apply(this,arguments),parts=routeParts();
  const newFragment=event?.type==='hashchange'&&fragmentNavigation&&fragmentNavigation.url===event.newURL&&['push','replace'].includes(fragmentNavigation.type);
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
  return result;
};
document.addEventListener('keydown',event=>{
  const tab=event.target.closest?.('[data-profile-tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const ids=['business','traction','people','work'],index=ids.indexOf(tab.dataset.profileTab),next=event.key==='Home'?0:event.key==='End'?3:(index+(event.key==='ArrowRight'?1:3))%4;
  event.preventDefault();activateProfileTab(ids[next]);
  setTimeout(()=>document.getElementById('profile-tab-'+ids[next])?.focus({preventScroll:true}),0);
});

document.addEventListener('click',event=>{if(event.target.closest?.('.skip')){event.preventDefault();$('main').focus({preventScroll:true});$('main').scrollIntoView({behavior:'instant'});}});
