/* Compact role presentation. Load after work-v3.js and before initialize().
   This module reads WORK_ROUTES; it does not change research or filter state. */
function w4Escape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function w4Text(value){return String(value??'').replace(/\s+/g,' ').trim();}
function w4Date(value){
  if(!value||value==='undated')return 'Undated';
  return /^\d{4}-\d{2}-\d{2}$/.test(value)?new Date(value+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):value;
}
function w4SourcePublicationDate(source){
  const recorded=[source.published_on,source.source_publication_date,source.published_at].find(value=>value&&value!=='undated');
  return recorded||(typeof sources!=='undefined'?sources[source.id]?.published_on:null);
}
function w4Checked(route){return [route.availability_checked_on,route.last_route_check?.date].filter(Boolean).sort().at(-1)||null;}
function w4CheckedLabel(route){const checked=w4Checked(route);return checked?w4Date(checked):'Not yet checked';}
function w4Uncertain(route){
  if(['unverified','intake_unverified','pay_conflict'].includes(route.status))return true;
  const check=[route.last_route_check?.result,route.last_route_check?.note].filter(Boolean).join(' ');
  return route.research_record?.route?.live_application_verified===false||/HTTP 403|blocked.fetch|JavaScript.only|requires JavaScript|JavaScript shell|not verified open|could not be loaded/i.test(check);
}
function w4Status(route){
  if(route.status==='program'&&/waitlist/i.test(route.availability_note||''))return 'Waitlist may apply';
  const labels={intake_unverified:'Availability unconfirmed',unverified:'Availability unconfirmed',pay_conflict:'Pay conflict',historical:'Historical',closed:'Closed',paused:'Training paused',contributions:'Research contribution',no_route:'No route verified',inquiry:'Inquiry only',information:'Information only'};
  if(route.status==='historical'&&['official_role_not_found_redirect','official_role_not_found'].includes(route.last_route_check?.result))return 'Historical · listing unavailable';
  return labels[route.status]||(w4Uncertain(route)?'Availability unconfirmed':'');
}
function w4SplitPay(route){
  if(route.pay_basis!=='salary_period_unspecified')return null;
  return w4Text(route.pay_label).match(/^(\$[\d,.]+K?\s*[–-]\s*\$[\d,.]+K?) salary band \+ equity;\s*(\$[\d,.]+K?\s*[–-]\s*\$[\d,.]+K?) separate bonus band$/i);
}
function w4Pay(route){
  if(route.status==='pay_conflict'||route.pay_basis==='conflicting_hourly')return 'Rate conflict';
  if(!route.pay_label||route.pay_label==='Not published')return 'Pay not listed';
  const split=w4SplitPay(route);
  if(split)return `${split[1]} salary band`;
  const concise={'Paid route not established':'Pay unconfirmed','Paid opening unconfirmed':'Pay unconfirmed','Compensation not promised':'Pay not promised','No published offer':'Pay not listed','Hourly; rate not published':'Hourly · rate unlisted'};
  return concise[route.pay_label]||route.pay_label;
}
function w4PayNote(route){
  const split=w4SplitPay(route);
  if(split)return `Equity offered. Separate bonus band: ${split[2]}.`;
  if(route.pay_observations?.length)return route.pay_observations.map(p=>`${p.value.replace(/\/hour\b/g,'/h')} ${p.label.toLowerCase().replace(/^listing /,'')}`).join(' · ');
  const labels={per_completed_task:'Paid per completed task',hour_equivalent:'Hourly equivalent',approved_deliverables:'Approved deliverables · advertised range',hour_or_accepted_task:'Hourly or accepted tasks; rejected tasks may be unpaid',month_stipend:'Monthly stipend',approved_recording:'Payment requires approval',approved_submission:'Payment requires approval',accepted_project:'Payment requires acceptance',accepted_task:'Payment requires acceptance'};
  return labels[route.pay_basis]||'';
}
function w4PayQualification(route){
  if(route.pay_basis==='advertised_maximum_hourly')return 'Rates vary by expertise, assessment, location and project. Non-core work can pay less.';
  if(!route.pay_basis?.endsWith('salary_period_unspecified'))return '';
  return 'Pay periods unspecified.'+(/Bonus eligibility and payout terms are undisclosed/i.test(route.availability_note||'')?' Bonus terms undisclosed.':'');
}
function w4Hours(route){
  const hours=w4Text(route.hours),duration=w4Text(route.duration);
  let commitment='';
  if(hours){
    // Keep estimated, minimum and demand-dependent qualifiers with the number.
    if(/\d.*(?:hours?\/week|hours? per week)/i.test(hours))commitment=hours.replace(/hours?\/week/gi,'h/week').replace(/hours? per week/gi,'h/week');
    else if(/^(?:full[- ]time|full- or part-time|part-time to full-time)/i.test(hours))commitment=hours.split(';')[0];
    else if(/^flexible/i.test(hours))commitment='Flexible schedule';
    else if(/^remote, part-time/i.test(hours))commitment='Part-time · flexible';
    else if(/^opt-in studies/i.test(hours))commitment='Opt-in studies';
  }
  if(commitment&&/no guaranteed volume/i.test(hours)&&!/no guaranteed volume/i.test(commitment))commitment+=' · No guaranteed volume';
  const hoursDetail=w4Text(route.research_record?.route?.hours?.detail);
  if(commitment&&hoursDetail&&!commitment.toLowerCase().includes(hoursDetail.toLowerCase()))commitment+=` · ${hoursDetail}`;
  if(duration&&duration.length<=72){
    if(!commitment)return duration;
    if(commitment.toLowerCase().includes(duration.toLowerCase()))return commitment;
    if(duration.toLowerCase().includes(commitment.toLowerCase()))return duration;
    return `${commitment} · ${duration}`;
  }
  return commitment;
}
function w4ScheduleNote(route){
  const note=w4Text(route.availability_note);
  if(route.id==='afterquery.work.research-fellow'&&/^full-time$/i.test(w4Text(route.hours))&&/20\+ hours\/week and in-person preferred/i.test(note))return 'Schedule conflict: full-time on-site required. Another line lists 20+ h/week and says in-person work is preferred.';
  if(route.id==='afterquery.work.technical-content-writer-contract'&&/Header employment type says full-time; role body specifies a part-time contract/i.test(note))return 'Schedule conflict: header says full-time; role body specifies a part-time contract.';
  return '';
}
function w4Location(route){
  const value=w4Text(route.geography);
  const aliases={
    'Project-specific':'Location varies','Role-specific':'Location varies','Location not published':'Location not listed',
    'Remote · eligibility unverified':'Remote · eligibility unconfirmed','At home · eligibility unverified':'At home · eligibility unconfirmed',
    'Remote · project-specific':'Remote · project eligibility','Remote · restricted by project':'Remote · project eligibility',
    'Global community advertised; specific geographic eligibility not exhaustively verified':'Global network · eligibility varies',
    'Supported countries · US residents included':'Supported countries, including US',
    'Japan-focused · US eligibility unverified':'Japan-focused · US eligibility unconfirmed',
    'Palo Alto · on-site / hybrid wording':'Palo Alto · on-site / hybrid terms',
    'Remote US listing':'Remote US · listing evidence'
  };
  return aliases[value]||value||'Location not listed';
}

// Concise, source-backed previews for dense requirement strings. Each preview
// is conditional on the current route text so future data corrections can
// remove it. Unmatched routes use short original clauses, never title inference.
function w4Requirements(route){
  if(route.id==='ooak.work.data-quality-specialist'&&/conflict/i.test((route.requirements||[]).join(' ')))return ['Experience conflict: 6+ years in header; 4+ in body','Python/SQL, data quality and fluent English'];
  if(route.id==='scale_ai.work.outlier-statistics'&&/Degree conflict/i.test((route.requirements||[]).join(' ')))return ["Degree conflict: master's badge; doctorate in ideal qualifications",'Authorization to work in the country of residence'];
  const originals=(route.requirements||[]).map(w4Text).filter(Boolean),text=originals.join(' ');
  if(!text)return [];
  const age=text.match(/\b(?:aged?\s*)?18\+|\bover\s+18\b|\bat\s+least\s+18\b/i)?.[0];
  const preserveAge=rows=>age&&!rows.some(row=>/\b18(?:\+|\b)/.test(row))?(rows.length?[age+' · '+rows[0],...rows.slice(1)]:[age]):rows;
  const tailored={
    'g2i.work.senior-swe-training':[
      [/Senior\/staff\/principal.*TypeScript\/JavaScript or Python/i,'Senior engineering · JS/TS or Python'],
      [/take-home evaluation.*recorded walkthrough/i,'Take-home evaluation + recorded walkthrough']],
    'elorian.work.model-safety':[
      [/LLM safety.*red.team.*data.annotation/i,'Language-model safety, attack testing or safety data labeling'],
      [/harm taxonomies and clear writing/i,'Harm categories + clear writing']],
    'toloka.work.cad-simulation':[
      [/5\+ years/i,'5+ years’ experience'],[/own professional CAD license/i,'Own professional CAD license']],
    'appen.work.sage-media':[
      [/US residence/i,'US residence'],[/MacBook Pro/i,'MacBook Pro']],
    'terac.work.ml-scenarios':[
      [/ML\/research and simulation or reinforcement.learning/i,'AI research + simulation or RL (training AI through rewards for completing tasks) experience'],
      [/No H1-B or STEM OPT support/i,'H1-B / STEM OPT unsupported']],
    'terac.work.rl-environment-creation':[
      [/Experienced domain professionals/i,'Professional domain experience'],
      [/H1-B and STEM OPT unsupported/i,'H1-B / STEM OPT unsupported']],
    'terac.work.ai-evaluator-shopping-assistant':[
      [/AI evaluation, QA or data training experience plus ecommerce familiarity/i,'AI evaluation, QA or data training + ecommerce'],
      [/H1-B and STEM OPT unsupported/i,'H1-B / STEM OPT unsupported']],
    'ooak.work.data-quality-specialist':[
      [/6\+ years.*Python\/SQL.*data.quality/i,'6+ years · Python/SQL + data quality'],
      [/fluent English/i,'Fluent English']],
    'aixi.work.research-fellowship':[
      [/PhD.level research, or relevant master.s plus substantial applied research/i,'PhD-level research, or relevant master’s + substantial applied research']],
    'abundant_ai.work.research-fellow':[
      [/Research depth in CS\/ML\/NLP/i,'Research in computing, machine learning or language processing'],
      [/requires AI safety\/governance policy experience/i,'AI safety / governance policy experience']],
    'bespoke_labs.work.fulfillment-operations-associate':[
      [/scaled expert\/contractor fulfillment/i,'Expert / contractor fulfillment experience']],
    'a-team.work.expert-network':[
      [/Senior production experience/i,'Senior production experience'],
      [/portfolio review, interview, and additional AI evaluation/i,'Portfolio review + interview; AI-role evaluation']],
    'prolific.work.study-participant':[
      [/verified account|identity verification/i,'Identity verification'],
      [/supported country of residence|supported residence/i,'Supported country of residence']],
    'datacurve.work.shipd-bounties':[
      [/At least 18, legal capacity to contract/i,'18+ and legal capacity to contract'],
      [/project access depends on skills and invitation/i,'Skills-based project access + invitation']],
    'polymath_ai_labs.work.member-of-technical-staff-engineering':[
      [/US citizen\/visa only/i,'US citizen / visa requirement'],
      [/strong engineering\/full-stack\/infrastructure experience/i,'Full-stack / infrastructure engineering']],
    'polymath_ai_labs.work.member-of-technical-staff-research':[
      [/US citizen\/visa only/i,'US citizen / visa requirement'],
      [/post-training and publication experience/i,'AI model improvement and published research']],
    'elorian.work.rl-infrastructure-engineer':[
      [/3\+ years distributed systems including RL pipelines/i,'3+ years in distributed systems, including reward-based AI training'],
      [/Python and PyTorch\/JAX/i,'Python + PyTorch/JAX']],
    'apto.work.ai-data-research-engineer':[
      [/ML\/deep learning, Python and PyTorch\/TensorFlow/i,'Machine learning and deep learning · Python + PyTorch/TensorFlow']]
  };
  const custom=(tailored[route.id]||[]).filter(([pattern])=>pattern.test(text)).map(([,label])=>label);
  if(custom.length)return preserveAge(custom.slice(0,2));
  // Boards list departments, not applicant requirements.
  if(route.status==='careers'||route.status==='no_route'||route.status==='information')return [];
  const clauses=originals.flatMap(s=>s.split(/\s*;\s*/)).map(s=>s.replace(/[.;]$/,'').trim()).filter(s=>s.length>=5&&s.length<=100);
  const locations=/^(?:Remote|Remote or Palo Alto|San Francisco|San Francisco and Bangalore roles|Berkeley or remote|London or Berkeley|Worldwide remote or London|Palo Alto|Tokyo|Paris)(?:[.,])?$/i;
  const generic=/^(?:requirements vary|role-specific|current intake|check |project allocation|joining is free|no public|weekly hours)/i;
  const selected=[];
  for(const clause of clauses.filter(s=>!locations.test(s)&&!generic.test(s))){
    const signature=clause.toLowerCase().replace(/[^a-z0-9]+/g,' ');
    if(selected.some(s=>s.signature.includes(signature)||signature.includes(s.signature)))continue;
    selected.push({text:clause,signature});
    if(selected.length===2)break;
  }
  return preserveAge(selected.map(s=>s.text));
}
function w4SourceLink(url,label,extra=''){
  if(!/^https?:\/\//i.test(url||''))return w4Escape(label);
  return `<a href="${w4Escape(url)}" target="_blank" rel="noopener noreferrer" ${extra}>${w4Escape(label)} ${iconHTML('external')}</a>${typeof window.linkAvailabilityHTML==='function'?window.linkAvailabilityHTML(url):''}`;
}
function w4BoundDestinationAction(route){
  const binding={
    'rws_trainai.work.polaris-asr':{company:'rws_trainai',status:'intake_unverified',url:'https://app.tai.rws.com/opportunities',claim:'rws_trainai.claim.oct15-work-polaris-asr',source:'rws_trainai.source.oct15-work-polaris-asr',label:'View opportunities'},
    'apto.work.harbest-experts':{company:'apto',status:'unverified',url:'https://expert.harbest.io/',claim:'apto.claim.worker_opportunities-0',source:'apto.source.d_apt5',label:'View program'}
  }[route.id];
  if(!binding||route.company_id!==binding.company||route.status!==binding.status||route.url!==binding.url)return '';
  const claim=typeof claims==='undefined'?null:claims[binding.claim],source=typeof sources==='undefined'?null:sources[binding.source];
  if(claim?.company_id!==binding.company||claim.status!=='supported'||!claim.source_ids?.includes(binding.source))return '';
  if(source?.company_id!==binding.company||source.url!==binding.url||source.source_type!=='company')return '';
  if(!route.claim_ids?.includes(binding.claim)||!route.source_ids?.includes(binding.source)||!route.sources?.some(item=>item.id===binding.source&&item.url===binding.url))return '';
  return binding.label;
}
function w4Action(route){
  if(route.status==='closed'||route.status==='historical'||route.status==='no_route')return 'View source';
  if(route.status==='paused'||route.status==='contributions')return 'View research';
  if(route.status==='information')return 'Program details';
  if(route.status==='inquiry')return 'Contact page';
  if(route.status==='careers')return 'View careers';
  if(route.status==='program')return 'View program';
  const destinationAction=w4BoundDestinationAction(route);if(destinationAction)return destinationAction;
  if(['unverified','intake_unverified'].includes(route.status)){
    if(route.id==='scale_ai.work.remotasks'&&route.url==='https://www.remotasks.com/en/migration')return 'Migration information';
    const entry=route.entry_point_research?.entry;
    if(entry?.url===route.url&&['expert community','expert fellowship','experts'].includes(entry.type))return 'View program';
  }
  return 'View role';
}
function w4ClaimAccess(ids){
  return [...new Set(ids||[])].filter(id=>claims[id]).map((id,i)=>`<span data-work-claim="${w4Escape(id)}">${claimButton(id,`Original evidence${ids.length>1?' '+(i+1):''}`)}</span>`).join('');
}
function w4Details(route){
  const requirements=[...new Set((route.requirements||[]).map(w4Text).filter(Boolean))];
  const sourceRows=[...new Map((route.sources||[]).map(s=>[s.url,s])).values()];
  const commitment=[...new Set([route.hours,route.research_record?.route?.hours?.detail].map(w4Text).filter(Boolean))].join(' · ');
  const rows=[['Payment',route.pay_label],['Commitment',commitment],['Duration',route.duration],['Location',route.geography]].filter(([,v])=>v);
  return `<div class="w4-detail-content">
    ${route.summary?`<p class="w4-role-summary">${w4Escape(route.summary)}</p>`:''}
    <dl class="w4-term-table">${rows.map(([label,value])=>`<div><dt>${w4Escape(label)}</dt><dd>${w4Escape(value)}</dd></div>`).join('')}</dl>
    ${requirements.length?`<div class="w4-detail-block"><h4>Requirements</h4><ul>${requirements.map(t=>`<li>${w4Escape(t)}</li>`).join('')}</ul></div>`:''}
    ${route.pay_observations?.length?`<div class="w4-detail-block"><h4>Published pay terms</h4><dl class="w4-term-table">${route.pay_observations.map(p=>`<div><dt>${w4Escape(p.label)}</dt><dd>${w4Escape(p.value)}</dd></div>`).join('')}</dl></div>`:''}
    ${route.availability_note?`<p class="w4-availability-note">${w4Escape(route.availability_note)}</p>`:''}
    ${route.pay_context?`<p>${w4Escape(route.pay_context)}${route.pay_policy?.source_url?` ${w4SourceLink(route.pay_policy.source_url,'Payment policy')}`:''}</p>`:''}
    ${route.historical_pay_context?`<details class="w4-source-notes"><summary>Past payment offer</summary><p>${w4Escape(route.historical_pay_context.label)}: ${w4Escape(route.historical_pay_context.amount)}.</p><p>${w4Escape(route.historical_pay_context.note)}</p>${w4SourceLink(route.historical_pay_context.url,'Historical source')}</details>`:''}
    <div class="w4-detail-block w4-sources"><h4>Sources</h4>
      <p class="w4-source-dates"><span>Terms recorded: ${w4Escape(w4Date(route.as_of))}</span><span>Checked: ${w4Escape(w4CheckedLabel(route))}</span></p>
      ${sourceRows.length?`<ul>${sourceRows.map(s=>`<li>${w4SourceLink(s.url,s.title||s.publisher||'Source')}<small>Published ${w4Escape(w4Date(w4SourcePublicationDate(s)))}${s.accessed_on?` · Read ${w4Escape(w4Date(s.accessed_on))}`:''}</small></li>`).join('')}</ul>`:''}
      ${route.source_quote?`<blockquote>${w4Escape(route.source_quote)}</blockquote>`:''}
      ${route.last_route_check?.note?`<details class="w4-source-notes"><summary>Availability check</summary><p>${w4Escape(route.last_route_check.note)}</p></details>`:''}
      ${route.claim_ids?.length?`<div class="w4-evidence-links">${w4ClaimAccess(route.claim_ids)}</div>`:''}
    </div>
    ${typeof compareCheck==='function'?`<div class="w4-compare">${compareCheck(route.company_id)}</div>`:''}
  </div>`;
}
function workCard(route,mode){
  if(!route.company_id)route=workRoutesFor(route.id)[0];
  if(!route)return '';
  const company=companies[route.company_id];
  if(!company)return '';
  const status=w4Status(route),payNote=w4PayNote(route),payQualification=w4PayQualification(route),commitment=w4Hours(route),scheduleNote=w4ScheduleNote(route),requirements=w4Requirements(route);
  const logo=typeof logoHTML==='function'&&(typeof logoFor!=='function'||logoFor(company.id))?logoHTML(company.id,'w4-company-logo'):'';
  const terms=w4Date(route.as_of),checked=w4CheckedLabel(route);
  const compact=mode==='compact';
  const identity=`<a class="w4-company" href="#company/${w4Escape(company.id)}/work">${logo?`<span class="w4-logo" aria-hidden="true">${logo}</span>`:''}<span>${w4Escape(company.name)}</span></a>`;
  const badge=status?`<span class="w4-status w4-status-${w4Escape(route.status)}">${w4Escape(status)}</span>`:'';
  const payNotes=`${route.pay_indicator?`<span class="w4-pay-note w4-pay-indicator">${w4Escape(route.pay_indicator)}</span>`:''}${payNote?`<span class="w4-pay-note">${w4Escape(payNote)}</span>`:''}${payQualification?`<span class="w4-pay-note w4-pay-qualification">${w4Escape(payQualification)}</span>`:''}`;
  const offer=`<div class="w4-offer">${compact?'':`<p class="w4-pay ${route.numeric_pay?'':'w4-pay-unspecified'}"><strong>${w4Escape(w4Pay(route))}</strong>${payNotes}</p>`}${commitment?`<p class="w4-commitment">${w4Escape(commitment)}</p>`:''}${scheduleNote?`<p class="w4-schedule-note">${w4Escape(scheduleNote)}</p>`:''}</div>`;
  const body=`${offer}<p class="w4-location">${w4Escape(w4Location(route))}</p>${requirements.length?`<ul class="w4-requirements" aria-label="Requirements">${requirements.map(text=>`<li>${w4Escape(text)}</li>`).join('')}</ul>`:''}<div class="w4-card-bottom"><p class="w4-dates"><span>${terms==='Undated'?'Undated terms':'Terms '+w4Escape(terms)}</span><span>Checked ${w4Escape(checked)}</span></p>${w4SourceLink(route.url,w4Action(route),'class="w4-open"')}</div>`;
  const details=`<details class="w4-details"><summary>Terms & sources<span aria-hidden="true">+</span></summary>${w4Details(route)}</details>`;
  return `<article class="work-card work-card-v4 ${compact?'w4-compact-card':''}" data-work-route="${w4Escape(route.id)}" data-work-company="${w4Escape(company.id)}" aria-label="${w4Escape(company.name+': '+route.role)}">${compact?`<details class="w4-compact-toggle"><summary><span class="w4-compact-title"><small>${w4Escape(company.name)}</small><strong>${w4Escape(route.role)}</strong></span><span class="w4-compact-pay"><strong>${w4Escape(w4Pay(route))}</strong>${payNotes}${badge}</span><span class="w4-toggle-icon" aria-hidden="true">+</span></summary><div class="w4-card-front"><div class="w4-compact-company">${identity}</div>${body}</div>${details}</details>`:`<div class="w4-card-front"><div class="w4-role-column"><header class="w4-card-heading">${identity}${badge}</header><h3 class="w4-role">${w4Escape(route.role)}</h3><p class="w4-dates"><span>${terms==='Undated'?'Undated terms':'Terms '+w4Escape(terms)}</span><span>Checked ${w4Escape(checked)}</span></p></div><div class="w4-offer-column">${offer}</div><div class="w4-conditions-column"><p class="w4-location">${w4Escape(w4Location(route))}</p>${requirements.length?`<ul class="w4-requirements" aria-label="Requirements">${requirements.map(text=>`<li>${w4Escape(text)}</li>`).join('')}</ul>`:''}</div><div class="w4-action-column">${w4SourceLink(route.url,w4Action(route),'class="w4-open"')}</div></div>${details}`}</article>`;
}
function w4RouteGroups(rows){
  const groups={primary:[],careers:[],other:[]};
  for(const route of rows){
    if(route.status==='careers')groups.careers.push(route);
    else if(WORK_ROUTE_ARCHIVE.has(route.status)||route.research_record?.route?.live_application_verified===false||route.ai_data_work===false)groups.other.push(route);
    else groups.primary.push(route);
  }
  const remoteHourly=route=>route.numeric_pay&&/^hour/.test(route.pay_basis||'')&&/remote|worldwide|at home|anywhere|global/i.test(route.geography||'');
  const rank=route=>(remoteHourly(route)?0:10)+(route.research_record?.route?.live_application_verified===true?0:route.last_route_check?.result==='public_page_live'?1:route.status==='listed'?2:3);
  groups.primary.sort((a,b)=>rank(a)-rank(b)||(w4Checked(b)||'').localeCompare(w4Checked(a)||'')||companies[a.company_id].name.localeCompare(companies[b.company_id].name)||a.role.localeCompare(b.role));
  return groups;
}
// A closed group carries only its route ids. Its cards render on first open.
function w4GroupDisclosure(rows,label,open=false,key=''){
  return rows.length?`<details class="work-route-archive-group w4-route-group" ${key?`id="${w4Escape(key)}"`:""} ${open?'open':''}><summary>${w4Escape(label)} <span>(${rows.length})</span></summary><div class="w4-secondary-list"${open?'':` data-w4-routes="${w4Escape(rows.map(route=>route.id).join(' '))}"`}>${open?rows.map(route=>workCard(route,'compact')).join(''):''}</div></details>`:'';
}
function w4FillGroup(group){
  const list=group?.querySelector?.(':scope>.w4-secondary-list[data-w4-routes]');if(!list)return;
  const routes=new Map(workRouteRows().map(route=>[route.id,route]));
  list.innerHTML=list.dataset.w4Routes.split(' ').map(id=>routes.get(id)).filter(Boolean).map(route=>workCard(route,'compact')).join('');list.removeAttribute('data-w4-routes');
}
document.addEventListener('toggle',event=>{if(event.target.open)w4FillGroup(event.target);},true);
function w4ProfilePrimary(rows,id){
  const preferred=id==='afterquery'?['research-fellow','research-engineer','research-scientist-post-training','technical-content-writer-contract'].map(role=>`afterquery.work.${role}`):[];
  const rank=route=>{const index=preferred.indexOf(route.id);return index<0?preferred.length:index;};
  return [...rows].sort((a,b)=>rank(a)-rank(b));
}
let workReturnFocus=null,workViewRendered=false;
function rememberWorkCompanyLink(event){
  if(event.defaultPrevented||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||(event.button!==undefined&&event.button!==0))return;
  const link=event.target.closest?.('#work-view a[href^="#company/"]');
  if(!link||link.hasAttribute('download')||(link.getAttribute('target')&&link.getAttribute('target')!=='_self'))return;
  workReturnFocus=link;
}
function workReturnFocusTarget(){
  const link=workReturnFocus;
  if(!link?.isConnected||link.closest('[hidden]')||!link.getClientRects().length){workReturnFocus=null;return null;}
  const box=link.getBoundingClientRect();
  if(box.bottom<=0||box.top>=window.innerHeight||box.right<=0||box.left>=window.innerWidth){workReturnFocus=null;return null;}
  return link;
}
document.addEventListener('click',rememberWorkCompanyLink);
function renderWork(){
  workViewRendered=true;
  workReturnFocus=null;
  const rows=filteredWork(),groups=w4RouteGroups(rows),orgs=new Set(rows.map(r=>r.company_id));
  const filtered=Boolean((state.workQuery||'').trim()||state.workGroup||state.workPay||state.workEligibility);
  if(!filtered){const perCompany={},kept=[],overflow=[];for(const route of groups.primary){perCompany[route.company_id]=(perCompany[route.company_id]||0)+1;(perCompany[route.company_id]<=3?kept:overflow).push(route);}groups.primary=kept.concat(overflow);}
  const visibleCount=filtered?groups.primary.length:20;
  const filterCount=[state.workGroup,state.workPay,state.workEligibility].filter(Boolean).length,summary=document.querySelector('.work-filters .responsive-filter-panel>summary');
  if(summary)summary.textContent=filterCount?`Filters (${filterCount})`:'Filters';
  $('work-count').textContent=`${rows.length} recorded ${rows.length===1?'link':'links'} across ${orgs.size} ${orgs.size===1?'organization':'organizations'}.`;if($('work-overview'))$('work-overview').innerHTML=`<span>${rows.length} ${rows.length===1?'link':'links'}</span><button data-work-section="work-listed" ${groups.primary.length?'':'disabled'}>${groups.primary.length} roles/programs</button><button data-work-section="work-careers" ${groups.careers.length?'':'disabled'}>${groups.careers.length} careers</button><button data-work-section="work-other" ${groups.other.length?'':'disabled'}>${groups.other.length} other</button>`;
  $('work-cards').innerHTML=(groups.primary.length?`<h2 id="work-listed" class="work-list-heading">Roles and programs <span>${groups.primary.length} recorded links</span></h2>`:'')+groups.primary.slice(0,visibleCount).map(route=>workCard(route)).join('')+w4GroupDisclosure(groups.primary.slice(visibleCount),'More listed routes')+w4GroupDisclosure(groups.careers,'Careers pages',filtered,'work-careers')+w4GroupDisclosure(groups.other,'Uncertain, historical and research links',filtered,'work-other')+(rows.length?'':'<p class="w4-empty">No matching routes. Clear a filter to see more.</p>');
  syncSelection();
}
function workSummary(id){
  const rows=workRoutesFor(id);
  if(!rows.length)return '<p class="w4-empty">No work route listed.</p>';
  const groups=w4RouteGroups(rows);
  const primary=w4ProfilePrimary(groups.primary,id);
  const covered=new Set(rows.flatMap(r=>r.claim_ids||[]));
  const related=typeof workClaims==='function'?workClaims(id).filter(c=>!covered.has(c.id)).map(c=>c.id):[];
  const openCareers=!primary.length&&groups.careers.length>0,openOther=!primary.length&&!groups.careers.length;
  return `<div class="work-v4-profile">${primary.length?`<div class="work-v4-profile-grid">${primary.slice(0,4).map(route=>workCard(route)).join('')}</div>`:`<p class="w4-empty">No verified public pay listing recorded. ${groups.careers.length+groups.other.length} career and research ${groups.careers.length+groups.other.length===1?'link':'links'} below.</p>`}${w4GroupDisclosure(primary.slice(4),'More listed roles')}${w4GroupDisclosure(groups.careers,'Career directories',openCareers)}${w4GroupDisclosure(groups.other,'Other work & research routes',openOther)}${related.length?`<details class="w4-related"><summary>Related work evidence</summary><div class="w4-evidence-links">${w4ClaimAccess(related)}</div></details>`:''}</div>`;
}

document.addEventListener('click',event=>{const button=event.target.closest?.('[data-work-section]');if(!button)return;const target=document.getElementById(button.dataset.workSection);if(target){if(target.tagName==='DETAILS'){w4FillGroup(target);target.open=true;}const focus=target.tagName==='DETAILS'?target.querySelector('summary'):target;if(focus&&focus.tagName!=='SUMMARY')focus.setAttribute('tabindex','-1');focus?.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'instant'});}});

let responsiveFiltersWide,responsiveFilterFocus;
document.addEventListener('focusin',event=>{
  const panel=event.target.closest?.('.responsive-filter-panel');
  responsiveFilterFocus=panel?{panel,target:event.target}:null;
});
document.addEventListener('pointerdown',event=>{
  if(responsiveFilterFocus&&!responsiveFilterFocus.panel.contains(event.target))responsiveFilterFocus=null;
});
function syncResponsiveFilterMode(){
  const wide=window.innerWidth>900;
  if(wide===responsiveFiltersWide)return;
  // Snapshot before changing any panel: an earlier DOM mutation can blur a
  // summary that the new desktop styles hide in a later panel.
  let active=document.activeElement;
  const remembered=responsiveFilterFocus;
  // CSS may blur the summary before resize runs. Recover only that transition;
  // focus on another control or an outside pointer action cancels the memory.
  if(wide&&responsiveFiltersWide===false&&active===document.body&&remembered?.target.isConnected&&!remembered.panel.closest('[hidden]')&&remembered.panel.querySelector('summary')?.contains(remembered.target))active=remembered.target;
  responsiveFiltersWide=wide;
  document.querySelectorAll('.responsive-filter-panel').forEach(panel=>{
    const fields=panel.querySelector('.responsive-filter-fields'),summary=panel.querySelector('summary');
    // Keep a focused field visible when the filters become collapsible.
    panel.open=wide||Boolean(fields?.contains(active));
    // Desktop hides the summary, so transfer its focus into the visible fields.
    if(wide&&summary?.contains(active))fields?.querySelector('input:not([disabled]), select:not([disabled]), button:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')?.focus({preventScroll:true});
  });
}
queueMicrotask(syncResponsiveFilterMode);window.addEventListener('resize',syncResponsiveFilterMode);
