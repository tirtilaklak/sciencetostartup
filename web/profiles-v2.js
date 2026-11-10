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
  if(!companyContextReady(id)){
    const products=window.SEARCH_INDEX?.profileProducts?.[id]||window.SEARCH_INDEX?.companyProducts?.[id];
    if(products)return products;
    const first=companySummaryFor(id)?.firstOffering;return first?[first]:[];
  }
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
// These renderers are registered by the existing verified detail-module factory.
function profileDetailRenderer(name,id){
 const render=window.ScienceProfileDetails?.[name];
 if(typeof render!=='function')throw new Error('Profile renderers are unavailable');
 return render(id);
}
function profileProductGrid(id){return profileDetailRenderer('profileProductGrid',id);}
function profileCase(id){return profileDetailRenderer('profileCase',id);}
function profileContextDescription(text,claimIds=[]){
 if(!claimIds.some(id=>['afterquery.claim.round2-relationship-3','afterquery.claim.round2-research-legora-bar'].includes(id)))return text;
 return String(text||'').replace('synthetic BAR case','synthetic case for BAR (an evaluation of AI on legal work)').replace('BAR uses','BAR (an evaluation of AI on legal work) uses');
}
function profileRelationshipGrid(id){return profileDetailRenderer('profileRelationshipGrid',id);}
const PROFILE_EVENT_KINDS={lawsuit:'Lawsuit',data_incident:'Data incident',customer_change:'Customer change',workforce_change:'Workforce change',filing:'Filing'};
function profileMonthHTML(value,prefix=''){return /^\d{4}-\d{2}(-\d{2})?$/.test(value)?`${prefix}<time datetime="${attr(value)}">${esc(new Date(value.slice(0,7)+'-01T12:00:00Z').toLocaleDateString('en-US',{month:'short',year:'numeric',timeZone:'UTC'}))}</time>`:esc(dateText(value));}
function profileEvents(id){return (window.COMPANY_EVENTS?.events||[]).filter(e=>e.company_id===id||e.related_company_ids.includes(id)).sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));}
// Event statuses carry the date they were checked, since a pending case can change after review.
function profileStatusesChecked(events){
 const days=[...new Set(events.map(e=>e.status_checked_on).filter(d=>/^\d{4}-\d{2}-\d{2}$/.test(d)))].sort(),label=d=>`${Number(d.slice(8))} ${new Date(d+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',timeZone:'UTC'})} ${d.slice(0,4)}`;
 return !days.length?'':days.length===1?`Statuses were checked on ${label(days[0])}.`:`Statuses were checked between ${label(days[0])} and ${label(days.at(-1))}.`;
}
function profileRiskClaims(id){return currentClaims(id).filter(c=>c.subject==='risks'&&c.status==='supported').sort(byRecent);}
function profileRisks(id){return profileDetailRenderer('profileRisks',id);}
function profilePeopleRows(id){
  const curated=profileContent(id).people;
  const all=curated?.length?curated:DATA.company_people.filter(p=>p.company_id===id).map(p=>({person_id:p.person_id,role:title(p.role),bio:'',claim_ids:[p.claim_id]}));
  return all.filter(p=>!p.historical&&!/early founding|historical/i.test(p.role)&&(!/\bformer\b/i.test(p.role)||/\badvisor\b/i.test(p.role)));
}
function profilePeople(id){return profileDetailRenderer('profilePeople',id);}
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
function profileCapital(id){return profileDetailRenderer('profileCapital',id);}
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
function profileTraction(id){return profileDetailRenderer('profileTraction',id);}
function profileArchive(id){return profileDetailRenderer('profileArchive',id);}
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
 return `<section class="profile-peers" aria-labelledby="profile-peers-title"><h2 id="profile-peers-title">More in ${esc(groupLabel(group))}</h2><ul>${peers.map(peer=>`<li><a href="#company/${attr(peer)}"><span>${esc(companies[peer].name)}</span></a></li>`).join('')}</ul><p><a class="profile-peers-all" href="#companies/${attr(groupSlug(group))}" data-category-jump="${attr(group)}">${members.length===2?'Both companies':'All '+members.length+' companies'} in this group ${iconHTML('right')}</a></p></section>`;
}
// Official visuals use the same local, attributed assets as the business record.
function profileHeroVisual(id){
 const media=typeof entryFor==='function'?entryFor(id)?.product_media:null,dimensions=typeof PRODUCT_MEDIA_DIMENSIONS!=='undefined'?PRODUCT_MEDIA_DIMENSIONS[id]:null;
 if(media)return `<figure class="profile-visual profile-visual-product"><div class="profile-visual-image"><img src="${attr(media.local_path)}" alt="${attr(media.title)}"${dimensions?` width="${dimensions[0]}" height="${dimensions[1]}"`:''} decoding="async" fetchpriority="high"></div><figcaption><span>${esc(media.caption||media.title)}</span>${external(media.source_page,'Official image')}</figcaption></figure>`;
 const founders=profilePeopleRows(id).filter(person=>person.portrait).slice(0,2);
 if(founders.length)return `<figure class="profile-visual profile-visual-founders"><div class="profile-founder-images">${founders.map(person=>`<div><img src="${attr(person.portrait)}" alt="${attr(people[person.person_id]?.name||person.name||'Founder')}" width="180" height="200" decoding="async"><span>${esc(people[person.person_id]?.name||person.name)}</span></div>`).join('')}</div><figcaption><span>Founders & leadership</span>${external(founders[0].portrait_source_url||companies[id].website,'Photo source')}</figcaption></figure>`;
 const logo=typeof logoFor==='function'?logoFor(id):null;
 return `<figure class="profile-visual profile-visual-brand"><div class="profile-visual-image">${profileLogoHTML(id,'profile-visual-logo')}</div><figcaption><span>${esc(companies[id].name)}</span>${logo?external(logo.source_page||logo.source_url||companies[id].website,'Official logo'):external(companies[id].website,'Company website')}</figcaption></figure>`;
}
function profileAtAGlance(id){
 const financial=preferredFinancial(id),research=companies[id].entity_type==='adjacent_research',offering=profileProducts(id).find(p=>p.name),metric=financial?(typeof financialSummaryHTML==='function'?financialSummaryHTML(id):compactSignal(id)):`<span class="profile-main-offering">${esc(offering?.name||(research?'Public AI research':'AI data services'))}</span><p class="profile-revenue-note">${research?'Nonprofit research organization':'Revenue not disclosed in the reviewed sources.'}</p>`;
 return `<div class="profile-at-a-glance"><div class="profile-glance-metric"><span class="eyebrow">${financial?'Latest financial evidence':research?'Research focus':'Main offering'}</span>${metric}</div><div class="profile-glance-work"><span class="eyebrow">Work routes</span><p>${esc(workType(id))}</p><a href="#company/${attr(id)}/work">View listings & requirements ${iconHTML('right')}</a></div></div>`;
}
function profileIntroductionHTML(id){
 const c=companies[id],group=modelGroup(id);
 return `<a class="profile-back" href="#companies">${iconHTML('left')} Companies</a><header class="profile-top profile-hero"><div class="profile-introduction"><div class="profile-title-row">${profileLogoHTML(id,'profile-brand')}<h1>${esc(c.name)}</h1></div><p class="profile-summary">${esc(modelFor(id))}</p><a class="profile-group-link" href="#companies/${attr(groupSlug(group))}" data-category-jump="${attr(group)}">${esc(groupLabel(group))} ${iconHTML('right')}</a><div class="profile-links">${external(c.website,'Website')}<a href="#company/${attr(id)}/work">Paid work ${iconHTML('right')}</a><a href="#company/${attr(id)}/sources">Sources ${iconHTML('right')}</a></div></div></header>`;
}
// Build a pane when it is read; populate another pane before its tab or anchor activates.
function profilePaneHTML(id,key){
 const c=companies[id],config=profileContent(id);
 if(key==='business'){
  const background=config.summary&&config.summary!==modelFor(id)?`<details class="profile-background"><summary>About the business</summary><p>${esc(config.summary)}</p></details>`:'';
  return `${background}<div class="profile-business-layout ${config.featured_case?'has-case':''}">${profileSection('products',config.product_heading||'Products and services',profileProductGrid(id))}${profileCase(id)}</div>${typeof productMediaHTML==='function'?productMediaHTML(id):''}${profileSection('customers','Who it works with',profileRelationshipGrid(id))}${profileRisks(id)}`;
 }
 if(key==='traction')return profileSection('traction',profileFiguresHeading(id),`${config.activity?`<div class="profile-activity"><h3>${esc(config.activity.title)}</h3><p>${esc(config.activity.description)}</p>${profileReferences(config.activity.claim_ids)}</div>`:''}${profileTraction(id)}`);
 if(key==='people'){
  const notes=(config.notes||[]).map(n=>typeof n==='string'?`<p>${esc(n)}</p>`:`<p>${esc(n.text)} ${profileReferences(n.claim_ids)}</p>`).join('');
  return `<div class="profile-people-layout">${profileSection('finance',c.entity_type==='adjacent_research'?'Research support':'Funding and valuation',profileCapital(id))}${profileSection('people','Founders and leadership',profilePeople(id))}</div>`+(notes?profileDisclosure('Further context',notes):'');
 }
 if(key==='work')return profileSection('work','Paid work at '+c.name,workSummary(id));
 return '';
}
function profileHTML(id,{deferArchive=false,deferPanes=false,omitIntroduction=false}={}){
 const c=companies[id],target=profileTarget(id),active=target==='observations'?'traction':profileTabFor(target),archiveOpen=PROFILE_ARCHIVE_SECTIONS.includes(target);
 const tabs=[['business','Business'],['traction','Figures'],['people','Funding & people'],['work','Paid work']];
 return `<div class="profile-v2" data-profile-company="${attr(id)}">${omitIntroduction?'':profileIntroductionHTML(id)}<nav class="profile-tabs" role="tablist" aria-label="${attr(c.name)} details">${tabs.map(([key,label])=>`<button type="button" role="tab" id="profile-tab-${key}" data-profile-tab="${key}" aria-controls="profile-pane-${key}" aria-selected="${active===key}" tabindex="${active===key?0:-1}">${esc(label)}</button>`).join('')}</nav><div class="profile-panes">${tabs.map(([key])=>`<section id="profile-pane-${key}" role="tabpanel" aria-labelledby="profile-tab-${key}" tabindex="-1" data-profile-pane="${key}"${deferPanes&&active!==key?' data-profile-pending':''}${active===key?'':' hidden'}>${deferPanes&&active!==key?'':profilePaneHTML(id,key)}</section>`).join('')}</div><details class="profile-evidence"${archiveOpen?' open':''}><summary><span class="archive-summary-label">Sources and review <i aria-hidden="true">+</i></span><span>${companyClaims(id).length} claims · ${companySources(id).length} sources</span></summary>${deferArchive&&!archiveOpen?'':profileArchive(id)}</details><p class="profile-correction">Something wrong here? <a href="#corrections">Request a correction ${iconHTML('right')}</a></p>${profilePeersHTML(id)}</div>`;
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
 const render=()=>{
  const dom=typeof container.querySelector==='function',retainIntroduction=existing?.dataset.profileCompany===id&&existing.hasAttribute('data-profile-loading');
  const html=profileHTML(id,{deferArchive:dom,deferPanes:dom,omitIntroduction:retainIntroduction});
  if(retainIntroduction){
   // Keep the sourced introduction attached while the validated evidence fills in below it.
   const template=document.createElement('template');template.innerHTML=html;
   const content=[...template.content.firstElementChild.children].filter(node=>!node.matches('.profile-back,.profile-top'));
   existing.querySelector('[data-profile-loading-content]').replaceWith(...content);existing.removeAttribute('data-profile-loading');
  }else container.innerHTML=html;
 };
 if(!existing||existing.dataset.profileCompany!==id||existing.hasAttribute('data-profile-loading')){render();return;}
 const target=profileTarget(id);
 // With no operating figures, the archive has a placeholder only on the
 // observations route. Preserve that existing conditional presentation.
 const emptyObservation=existing.querySelector('#profile-observations')?.tagName==='SECTION';
 if(emptyObservation!==(target==='observations'&&!profileOperatingMetrics(id).length)){
  render();return;
 }
 if(PROFILE_ARCHIVE_SECTIONS.includes(target)||existing.querySelector('.profile-evidence')?.open)ensureProfileArchive(existing);
 const active=target==='observations'?'traction':profileTabFor(target);
 existing.querySelectorAll('[data-profile-pane]').forEach(pane=>{
  if(pane.dataset.profilePane===active&&pane.hasAttribute('data-profile-pending')){
   pane.innerHTML=profilePaneHTML(id,active);pane.removeAttribute('data-profile-pending');
  }
  pane.hidden=pane.dataset.profilePane!==active;
 });
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
// (app.js writes one while they scroll), so that entry is new. Back and Forward use the saved position.
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
  if(routeRestoredScroll===null&&parts[0]==='company'&&isCompanyId(parts[1])&&parts[2]){
    const section=profileRouteSection(parts[2]);
    const primary=['business','traction','people','work'].includes(section);
    const destination=profileRouteDestination(section);
    if(destination){
      for(let node=destination;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
      const focusTarget=destination.tagName==='DETAILS'?destination.querySelector('summary'):destination;
      if(focusTarget&&focusTarget.tagName!=='SUMMARY')focusTarget.setAttribute('tabindex','-1');
      if(event?.type==='hashchange')focusTarget?.focus({preventScroll:true});
      const anchor=primary?document.querySelector('.profile-tabs'):destination;
      if(initial&&anchor)settleInitialProfileAnchor(location.hash,anchor);
      else anchor?.scrollIntoView({block:'start',behavior:'instant'});
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
  const nextTab=document.getElementById('profile-tab-'+ids[next]);
  nextTab?.focus({preventScroll:true});
  nextTab?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
});

document.addEventListener('click',event=>{if(event.target.closest?.('.skip')){event.preventDefault();$('main').focus({preventScroll:true});$('main').scrollIntoView({behavior:'instant'});}});
