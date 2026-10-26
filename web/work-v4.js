/* Compact role presentation. Load after work-v3.js and before initialize().
   This module reads WORK_ROUTES; it does not change research or filter state. */
function w4Escape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function w4Text(value){return String(value??'').replace(/\s+/g,' ').trim();}
function w4Date(value){
  if(!value||value==='undated')return 'Undated';
  return /^\d{4}-\d{2}-\d{2}$/.test(value)?workDayLabel(value):/^\d{4}-\d{2}$/.test(value)?workMonthLabel(value):value;
}
function w4SourcePublicationDate(source){
  const recorded=[source.published_on,source.source_publication_date,source.published_at].find(value=>value&&value!=='undated');
  return recorded||(typeof sources!=='undefined'?sources[source.id]?.published_on:null);
}
function w4Checked(route){return [route.availability_checked_on,route.last_route_check?.date].filter(Boolean).sort().at(-1)||null;}
function w4CheckedLabel(route){const checked=w4Checked(route);return checked?w4Date(checked):'Not rechecked';}
// One date per listing: the latest link check, or the research review when the link was never rechecked.
function w4FreshnessLabel(route){const checked=w4Checked(route);return checked?`Checked ${w4Date(checked)}`:`${route.reviewed_on?`Reviewed ${w4Date(route.reviewed_on)} · `:''}Link not rechecked`;}
function w4Uncertain(route){
  if(['unverified','intake_unverified','pay_conflict'].includes(route.status))return true;
  const check=[route.last_route_check?.result,route.last_route_check?.note].filter(Boolean).join(' ');
  return route.research_record?.route?.live_application_verified===false||/HTTP 403|blocked.fetch|JavaScript.only|requires JavaScript|JavaScript shell|not verified open|could not be loaded/i.test(check);
}
function w4Status(route){
  if(route.status==='program'&&/waitlist/i.test(route.availability_note||''))return 'Waitlist may apply';
  const labels={intake_unverified:'Availability unconfirmed',unverified:'Availability unconfirmed',pay_conflict:'Pay conflict',historical:'Historical',closed:'Closed',paused:'Training paused',contributions:'Research contribution',no_route:'No confirmed paid listing',inquiry:'Inquiry only',information:'Information only'};
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
  return 'Pay period not stated.'+(/Bonus eligibility and payout terms are undisclosed/i.test(route.availability_note||'')?' Bonus terms not stated.':'');
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
    'Project-specific':'Location set per project','Role-specific':'Location set per role','Location not published':'Location not listed',
    'Remote · eligibility unverified':'Remote · country rules not confirmed','At home · eligibility unverified':'At home · country rules not confirmed',
    'Remote · project-specific':'Remote · country rules vary by project','Remote · restricted by project':'Remote · country rules vary by project',
    'Remote · eligibility varies':'Remote · country rules vary','Remote · country varies':'Remote · country rules vary',
    'Global community advertised; specific geographic eligibility not exhaustively verified':'Global network · country rules vary',
    'Supported countries · US residents included':'Supported countries, including US',
    'Japan-focused · US eligibility unverified':'Japan-focused · US eligibility not confirmed',
    'Palo Alto · on-site / hybrid wording':'Palo Alto · on-site or hybrid',
    'Remote US listing':'Remote US'
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
// Hidden context tells repeated "View role" links apart; the new-tab note warns before the tab opens.
function w4SourceLink(url,label,extra='',context=''){
  if(!/^https?:\/\//i.test(url||''))return w4Escape(label);
  return `<a href="${w4Escape(url)}" target="_blank" rel="noopener noreferrer" ${extra}>${w4Escape(label)}${context?`<span class="sr-only">: ${w4Escape(context)}</span>`:''} ${iconHTML('external')}<span class="sr-only"> (opens in a new tab)</span></a>${typeof window.linkAvailabilityHTML==='function'?window.linkAvailabilityHTML(url):''}`;
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
  if(route.status==='careers')return 'View career page';
  if(route.status==='program')return 'View program';
  const destinationAction=w4BoundDestinationAction(route);if(destinationAction)return destinationAction;
  if(['unverified','intake_unverified'].includes(route.status)){
    if(route.id==='scale_ai.work.remotasks'&&route.url==='https://www.remotasks.com/en/migration')return 'Migration information';
    const entry=route.entry_point_research?.entry;
    if(entry?.url===route.url&&['expert community','expert fellowship','experts'].includes(entry.type))return 'View program';
  }
  return 'View role';
}
function w4ClaimAccess(ids,topic=''){
  return [...new Set(ids||[])].filter(id=>claims[id]).map((id,i)=>`<span data-work-claim="${w4Escape(id)}">${claimButton(id,`Original evidence${ids.length>1?' '+(i+1):''}`,topic)}</span>`).join('');
}
// Route checks store their result before the note (a code such as public_page_live, or a short phrase).
// Readers see plain words instead of the code, and the result ends with a period so the note reads on.
const W4_CHECK_CODES={public_page_live:'Public page was live.',information_only_not_verified_paid_application:'Information page only. No paid application confirmed.'};
const W4_CHECK_CODE=/^[a-z]+(?:_[a-z]+)+$/;
function w4CheckLead(result){return W4_CHECK_CODE.test(result)?W4_CHECK_CODES[result]||result.charAt(0).toUpperCase()+result.slice(1).replace(/_/g,' ')+'.':result.replace(/[\s.;:,]+$/,'')+'.';}
function w4CheckNote(check){
  const text=w4Text(check?.note),result=w4Text(check?.result);
  if(result&&text.startsWith(result+' '))return `${w4CheckLead(result)} ${text.slice(result.length+1)}`;
  const code=text.match(/^([a-z]+(?:_[a-z]+)+)(?:\s+(.*))?$/);
  return code?(code[2]?`${w4CheckLead(code[1])} ${code[2]}`:w4CheckLead(code[1])):text;
}
function w4Details(route,level=4){
  const requirements=[...new Set((route.requirements||[]).map(w4Text).filter(Boolean))];
  const sourceRows=[...new Map((route.sources||[]).map(s=>[s.url,s])).values()];
  const commitment=[...new Set([route.hours,route.research_record?.route?.hours?.detail].map(w4Text).filter(Boolean))].join(' · ');
  const rows=[['Payment',route.pay_label],['Commitment',commitment],['Duration',route.duration],['Location',route.geography]].filter(([,v])=>v);
  const h=`h${Math.min(Math.max(level,2),6)}`,published=s=>{const date=w4SourcePublicationDate(s);return date&&date!=='undated'?`Published ${w4Date(date)}`:'Publication date not stated';};
  return `<div class="w4-detail-content">
    ${route.summary?`<p class="w4-role-summary">${w4Escape(route.summary)}</p>`:''}
    <dl class="w4-term-table">${rows.map(([label,value])=>`<div><dt>${w4Escape(label)}</dt><dd>${w4Escape(value)}</dd></div>`).join('')}</dl>
    ${requirements.length?`<div class="w4-detail-block"><${h}>Requirements</${h}><ul>${requirements.map(t=>`<li>${w4Escape(t)}</li>`).join('')}</ul></div>`:''}
    ${route.pay_observations?.length?`<div class="w4-detail-block"><${h}>Published pay terms</${h}><dl class="w4-term-table">${route.pay_observations.map(p=>`<div><dt>${w4Escape(p.label)}</dt><dd>${w4Escape(p.value)}</dd></div>`).join('')}</dl></div>`:''}
    ${route.availability_note?`<p class="w4-availability-note">${w4Escape(route.availability_note)}</p>`:''}
    ${route.pay_context?`<p>${w4Escape(route.pay_context)}${route.pay_policy?.source_url?` ${w4SourceLink(route.pay_policy.source_url,'Payment policy')}`:''}</p>`:''}
    ${route.historical_pay_context?`<details class="w4-source-notes"><summary>Past payment offer</summary><p>${w4Escape(route.historical_pay_context.label)}: ${w4Escape(route.historical_pay_context.amount)}.</p><p>${w4Escape(route.historical_pay_context.note)}</p>${w4SourceLink(route.historical_pay_context.url,'Historical source')}</details>`:''}
    <div class="w4-detail-block w4-sources"><${h}>Sources</${h}>
      <p class="w4-source-dates"><span>Terms recorded: ${w4Escape(route.as_of&&route.as_of!=='undated'?w4Date(route.as_of):'date not stated')}</span><span>${w4Escape(w4FreshnessLabel(route))}</span></p>
      ${sourceRows.length?`<ul>${sourceRows.map(s=>`<li>${w4SourceLink(s.url,s.title||s.publisher||'Source')}<small>${w4Escape(published(s))}${s.accessed_on?` · Checked ${w4Escape(w4Date(s.accessed_on))}`:''}</small></li>`).join('')}</ul>`:''}
      ${route.source_quote?`<blockquote>${w4Escape(route.source_quote)}</blockquote>`:''}
      ${route.last_route_check?.note?`<details class="w4-source-notes"><summary>Link check note</summary><p>${w4Escape(w4CheckNote(route.last_route_check))}</p></details>`:''}
      ${route.claim_ids?.length?`<div class="w4-evidence-links">${w4ClaimAccess(route.claim_ids,route.role)}</div>`:''}
    </div>
    ${typeof compareCheck==='function'?`<div class="w4-compare">${compareCheck(route.company_id)}</div>`:''}
  </div>`;
}
function w4PayNotes(route){
  const payNote=w4PayNote(route),payQualification=w4PayQualification(route);
  return `${route.pay_indicator?`<span class="w4-pay-note w4-pay-indicator">${w4Escape(route.pay_indicator)}</span>`:''}${payNote?`<span class="w4-pay-note">${w4Escape(payNote)}</span>`:''}${payQualification?`<span class="w4-pay-note w4-pay-qualification">${w4Escape(payQualification)}</span>`:''}`;
}
function w4StatusBadge(route){const status=w4Status(route);return status?`<span class="w4-status w4-status-${w4Escape(route.status)}">${w4Escape(status)}</span>`:'';}
// Pieces of a card. A compact card shows its pay in the summary, so its offer leaves the pay out.
function w4CardParts(route,compact){
  const company=companies[route.company_id],commitment=w4Hours(route),scheduleNote=w4ScheduleNote(route),requirements=w4Requirements(route);
  const logo=typeof logoHTML==='function'&&(typeof logoFor!=='function'||logoFor(company.id))?logoHTML(company.id,'w4-company-logo',true):'';
  return {context:`${route.role}, ${company.name}`,
    identity:`<a class="w4-company" href="#company/${w4Escape(company.id)}/work">${logo?`<span class="w4-logo" aria-hidden="true">${logo}</span>`:''}<span>${w4Escape(company.name)}</span></a>`,
    offer:`<div class="w4-offer">${compact?'':`<p class="w4-pay ${route.numeric_pay?'':'w4-pay-unspecified'}"><strong>${w4Escape(w4Pay(route))}</strong>${w4PayNotes(route)}</p>`}${commitment?`<p class="w4-commitment">${w4Escape(commitment)}</p>`:''}${scheduleNote?`<p class="w4-schedule-note">${w4Escape(scheduleNote)}</p>`:''}</div>`,
    conditions:`<p class="w4-location">${w4Escape(w4Location(route))}</p>${requirements.length?`<ul class="w4-requirements" aria-label="Requirements">${requirements.map(text=>`<li>${w4Escape(text)}</li>`).join('')}</ul>`:''}`,
    dates:`<p class="w4-dates"><span>${w4Escape(w4FreshnessLabel(route))}</span></p>`};
}
// "Terms & sources". Lazy disclosures carry only their summary and draw the rest on first open (w4FillCard).
function w4DetailsDisclosure(route,level,context,lazy){
  const summary=`<summary>Terms & sources<span class="sr-only">: ${w4Escape(context)}</span><span aria-hidden="true">+</span></summary>`;
  return lazy?`<details class="w4-details" data-w4-detail="${w4Escape(route.id)}" data-w4-level="${level}">${summary}</details>`:`<details class="w4-details">${summary}${w4Details(route,level)}</details>`;
}
// What an open compact card shows under its summary. level is the heading level its details sit under.
function w4CompactBody(route,level,lazy){
  const part=w4CardParts(route,true);
  return `<div class="w4-card-front"><div class="w4-compact-company">${part.identity}</div>${part.offer}${part.conditions}<div class="w4-card-bottom">${part.dates}${w4SourceLink(route.url,w4Action(route),'class="w4-open"',part.context)}</div></div>${w4DetailsDisclosure(route,level+1,part.context,lazy)}`;
}
// level: for a full card, its role heading (3 under a section h2, 4 under a pay block h3); its details use the
// next level. A compact card has no role heading, so level is the heading it sits under (2 under a section h2).
// lazy: the page draws closed parts on first open, so a long list costs little until a reader opens a card.
// workCard(route) with no lazy flag returns every part, which the tests read.
function workCard(route,mode,level=3,lazy=false){
  if(!route.company_id)route=workRoutesFor(route.id)[0];
  if(!route)return '';
  const company=companies[route.company_id];
  if(!company)return '';
  const compact=mode==='compact',heading=Math.min(Math.max(Number(level)||3,2),5);
  const open=`<article class="work-card work-card-v4 ${compact?'w4-compact-card':''}" data-work-route="${w4Escape(route.id)}" data-work-company="${w4Escape(company.id)}" aria-label="${w4Escape(company.name+': '+route.role)}">`;
  if(compact){
    const title=`<summary><span class="w4-compact-title"><small>${w4Escape(company.name)}</small><strong>${w4Escape(route.role)}</strong></span><span class="w4-compact-pay"><strong>${w4Escape(w4Pay(route))}</strong>${w4PayNotes(route)}${w4StatusBadge(route)}</span><span class="w4-toggle-icon" aria-hidden="true">+</span></summary>`;
    return `${open}<details class="w4-compact-toggle"${lazy?` data-w4-card="${w4Escape(route.id)}" data-w4-level="${heading}"`:''}>${title}${lazy?'':w4CompactBody(route,heading,false)}</details></article>`;
  }
  const part=w4CardParts(route,false),action=w4SourceLink(route.url,w4Action(route),'class="w4-open"',part.context);
  return `${open}<div class="w4-card-front"><div class="w4-role-column"><header class="w4-card-heading">${part.identity}${w4StatusBadge(route)}</header><h${heading} class="w4-role">${w4Escape(route.role)}</h${heading}>${part.dates}</div><div class="w4-offer-column">${part.offer}</div><div class="w4-conditions-column">${part.conditions}</div><div class="w4-action-column">${action}</div></div>${w4DetailsDisclosure(route,heading+1,part.context,lazy)}</article>`;
}
let w4RouteIndex=null,w4RouteIndexRows=null;
function w4RouteById(id){const rows=workRouteRows();if(rows!==w4RouteIndexRows){w4RouteIndexRows=rows;w4RouteIndex=new Map(rows.map(route=>[route.id,route]));}return w4RouteIndex.get(id);}
// Draws a lazy card part (a compact card's body or a card's Terms & sources) the first time it opens.
function w4FillCard(box){
  const data=box?.dataset;if(!data||!(data.w4Card||data.w4Detail))return;
  const route=w4RouteById(data.w4Card||data.w4Detail),level=Number(data.w4Level)||3;
  if(data.w4Card){box.removeAttribute('data-w4-card');if(route)box.insertAdjacentHTML('beforeend',w4CompactBody(route,level,true));}
  else{box.removeAttribute('data-w4-detail');if(route)box.insertAdjacentHTML('beforeend',w4Details(route,level));}
}
// Work type options keep the research group values (tests and links use them); labels use plain words.
const W4_TYPE_LABELS={'Expert & contractor projects':'Contract and task work','Employment':'Jobs','Research fellowship':'Research fellowships','Contributor bounties':'Bounties for contributions','Unverified route':'Type not confirmed'};
// Pay and place come from each listing's own fields. Nothing is converted between currencies or pay periods.
const W4_CONTRACT_GROUPS=new Set(['Expert & contractor projects','Contributor bounties']);
const W4_TASK_PAY=new Set(['per_completed_task','task','accepted_task','approved_recording','approved_submission']);
const W4_REMOTE=/remote|at home|worldwide|global/i,W4_ONSITE=/San Francisco|Palo Alto|Berkeley|London|Paris|Tokyo|Bangalore|on-?site|hybrid|in.person|office/i;
// An Employment listing paid by the hour or by a one-time award is contract and task work, not a staff job.
// scripts/static_pages.py work_bucket() uses the same rule (CONTRACT_PAY).
const W4_CONTRACT_PAY=new Set(['hour','one_time']);
// What a worker can do with a listing: contract or task work, a job or fellowship, a career page,
// a company job outside AI training, or a closed or unpaid record.
function w4Bucket(route){
  if(route.status==='careers')return 'boards';
  if(WORK_ROUTE_ARCHIVE.has(route.status))return 'closed';
  if(route.ai_data_work===false)return 'outside';
  return W4_CONTRACT_GROUPS.has(route.group)||(route.group==='Employment'&&W4_CONTRACT_PAY.has(route.pay_basis))?'contract':'jobs';
}
// A published hourly range, read only from labels that state a rate per hour. "Up to" has no low end.
function w4HourlyRange(route){
  if(!route?.numeric_pay||route.status==='pay_conflict'||route.pay_basis==='conflicting_hourly')return null;
  const label=w4Text(route.pay_label);
  if(!/\/\s*(?:approved\s+)?hour/i.test(label))return null;
  const match=label.match(/([$€£¥])\s*([\d,]+(?:\.\d+)?)(?:\s*[–-]\s*[$€£¥]?\s*([\d,]+(?:\.\d+)?))?(\+)?/);
  if(!match)return null;
  const number=value=>Number(value.replace(/,/g,''));
  return {currency:match[1],low:/^up to\b/i.test(label)?null:number(match[2]),high:number(match[3]||match[2]),open:Boolean(match[4])};
}
function w4PayBlock(route){return w4HourlyRange(route)||route.pay_basis==='conflicting_hourly'?'hourly':W4_TASK_PAY.has(route.pay_basis)?'task':'project';}
function w4PayMatches(route,value){
  if(!value)return true;
  if(value==='numeric'||value==='undisclosed')return (value==='numeric')===Boolean(route.numeric_pay);
  if(value==='hourly')return Boolean(w4HourlyRange(route));
  if(value==='task')return W4_TASK_PAY.has(route.pay_basis);
  if(value==='monthly')return ['month_stipend','undisclosed_stipend'].includes(route.pay_basis);
  if(value==='yearly')return /^(?:annual_salary|annual_target_cash)$|salary_period_unspecified$/.test(route.pay_basis||'');
  return false;
}
function w4Where(route){const place=route.geography||'';return W4_REMOTE.test(place)?'remote':W4_ONSITE.test(place)?'onsite':'varies';}
// Older eligibility values (such as "US listing evidence") still filter on the research field itself.
function w4WhereMatches(route,value){return !value||(['remote','onsite','varies'].includes(value)?w4Where(route)===value:route.eligibility===value);}

// Worker words map to the words listings use. Each term must start a word, so "doctor" skips "doctorate".
const W4_WORD_START='(?:^|[^\\p{L}\\p{N}])',W4_WORD_END='(?![\\p{L}\\p{N}])';
const W4_SEARCH_GROUPS=[
  {words:['medical','medicine','doctor','doctors','physician','physicians','clinical','clinician','clinicians','health','healthcare','nurse','nurses','nursing'],terms:['medic','clinic','physician','doctors?'+W4_WORD_END,'health','nurs(?:e|es|ing)'+W4_WORD_END]},
  {words:['code','coding','coder','coders','developer','developers','programmer','programmers','programming','swe','software'],terms:['cod(?:e|es|ing|er|ers)'+W4_WORD_END,'software','swe'+W4_WORD_END,'developers?'+W4_WORD_END,'programm']},
  {words:['label','labels','labeling','labelling','labeler','labelers','annotation','annotations','annotate','annotator','annotators'],terms:['label(?:s|ed|er|ers|ing|ling)?'+W4_WORD_END,'annotat']},
  {words:['beginner','beginners','entry','entry-level','novice','junior'],phrases:['no experience','entry level'],terms:['no experience','generalists','general tasks?','general ai','entry[- ]level','beginner']},
  {words:['student','students','college','intern','interns','internship','internships','graduate','graduates','university'],terms:['student','college','intern(?:s|ship|ships)?'+W4_WORD_END,'graduate','universit','no experience','generalists','general tasks?','entry[- ]level']},
  {words:['part-time','parttime','flexible'],phrases:['part time'],terms:['part[- ]?time','flexible','opt-in']},
  {words:['worldwide','global','anywhere','international'],terms:['worldwide','global','anywhere','international']}
];
function w4RegExpEscape(value){return value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function w4SearchText(route){const c=companies[route.company_id];return [c?.name,...(c?.aliases||[]),route.role,route.summary,route.group,route.geography,w4Location(route),route.pay_label,route.hours,route.duration,...(route.requirements||[])].filter(Boolean).join(' ').toLowerCase();}
function w4QueryMatcher(query){
  let text=w4Text(query).toLowerCase();
  if(!text)return null;
  for(const group of W4_SEARCH_GROUPS)for(const phrase of group.phrases||[])text=text.split(phrase).join(group.words[0]);
  const tokens=text.split(' ').filter(Boolean);
  const tests=tokens.map(token=>{const group=W4_SEARCH_GROUPS.find(g=>g.words.includes(token));return new RegExp(W4_WORD_START+'(?:'+(group?group.terms.join('|'):w4RegExpEscape(token))+')','u');});
  const phrase=tokens.length>1?new RegExp(W4_WORD_START+w4RegExpEscape(tokens.join(' ')),'u'):null;
  return {all:value=>tests.every(test=>test.test(value)),phrase:value=>Boolean(phrase?.test(value))};
}

// Best match: remote listings with an hourly rate first, then the strongest link check, then the latest
// check, then the higher top rate (same currency only), then company and role names.
function w4BestRank(route){return (w4HourlyRange(route)&&W4_REMOTE.test(route.geography||'')?0:10)+(route.research_record?.route?.live_application_verified===true?0:route.last_route_check?.result==='public_page_live'?1:route.status==='listed'?2:3);}
function w4RateTie(a,b){const x=w4HourlyRange(a),y=w4HourlyRange(b);return x&&y&&x.currency===y.currency?y.high-x.high:0;}
function w4BestOrder(a,b){return w4BestRank(a)-w4BestRank(b)||(w4Checked(b)||'').localeCompare(w4Checked(a)||'')||w4RateTie(a,b)||companies[a.company_id].name.localeCompare(companies[b.company_id].name)||a.role.localeCompare(b.role);}
// Highest hourly rate: top of the published range, then its low end ("up to" last), then open-ended
// ranges. Listings without a rate keep best-match order after them. US dollar rates come before other
// currencies, and amounts in different currencies are never compared.
function w4RateOrder(a,b){
  const x=w4HourlyRange(a),y=w4HourlyRange(b);
  if(!x||!y)return Number(Boolean(y))-Number(Boolean(x))||w4BestOrder(a,b);
  if(x.currency!==y.currency)return Number(y.currency==='$')-Number(x.currency==='$')||x.currency.localeCompare(y.currency);
  return y.high-x.high||(y.low??-1)-(x.low??-1)||Number(y.open)-Number(x.open)||w4BestOrder(a,b);
}
function w4CheckedOrder(a,b){return (w4Checked(b)||'').localeCompare(w4Checked(a)||'')||(b.reviewed_on||'').localeCompare(a.reviewed_on||'')||w4BestOrder(a,b);}
// primary, careers and other keep their old meaning for callers in app.js (workType, hasWorkRoute).
function w4RouteGroups(rows,sort=''){
  const groups={contract:[],jobs:[],boards:[],outside:[],closed:[]},order=sort==='hourly'?w4RateOrder:sort==='checked'?w4CheckedOrder:w4BestOrder;
  for(const route of rows)groups[w4Bucket(route)].push(route);
  for(const list of Object.values(groups))list.sort(order);
  for(const block of ['hourly','task','project'])groups[block]=groups.contract.filter(route=>w4PayBlock(route)===block);
  return Object.assign(groups,{primary:[...groups.contract,...groups.jobs],careers:groups.boards,other:[...groups.outside,...groups.closed]});
}
const W4_GROUP_NOTES={boards:'Each link opens a company’s full list of openings. We did not record pay for these pages.',outside:'Open staff roles that are not AI training work.',closed:'Past or paused listings, and pages with no confirmed paid work. We keep them for the record.'};
// A closed group carries only its listing ids. Its cards render on first open, which keeps the page light.
// The trade-off: browser find-in-page cannot reach cards in a closed group, or the closed parts of a card.
// The Paid work search covers every listing. level is the heading the group sits under (2 under a section h2),
// so the compact cards' detail headings follow it (axe heading-order).
function w4GroupDisclosure(rows,label,open=false,key='',note='',level=2){
  return rows.length?`<details class="work-route-archive-group w4-route-group" ${key?`id="${w4Escape(key)}"`:""} ${open?'open':''}><summary>${w4Escape(label)} <span>(${rows.length})</span></summary>${note?`<p class="w4-group-note">${w4Escape(note)}</p>`:''}<div class="w4-secondary-list" data-w4-level="${level}"${open?'':` data-w4-routes="${w4Escape(rows.map(route=>route.id).join(' '))}"`}>${open?w4CompactCards(rows,level):''}</div></details>`:'';
}
function w4CompactCards(rows,level){return rows.map(route=>workCard(route,'compact',level,true)).join('');}
function w4FillGroup(group){
  const list=group?.querySelector?.(':scope>.w4-secondary-list[data-w4-routes]');if(!list)return;
  list.innerHTML=w4CompactCards(list.dataset.w4Routes.split(' ').map(w4RouteById).filter(Boolean),Number(list.dataset.w4Level)||2);list.removeAttribute('data-w4-routes');
}
// Lazy parts fill as they open: on the click, before the browser shows the disclosure, and on toggle for
// disclosures opened by code or by find-in-page.
function w4FillLazy(box){if(box?.tagName==='DETAILS'){w4FillGroup(box);w4FillCard(box);}}
// Fills the closed group that holds one listing, so code that looks for its card (site search) finds it.
function w4FillRouteGroup(scope,id){
  const root=typeof scope==='string'?document.querySelector(scope):scope;
  for(const list of root?.querySelectorAll?.('.w4-secondary-list[data-w4-routes]')||[])if(list.dataset.w4Routes.split(' ').includes(id))w4FillGroup(list.parentElement);
}
document.addEventListener('toggle',event=>{if(event.target.open)w4FillLazy(event.target);},true);
function w4ProfilePrimary(rows,id){
  const preferred=id==='afterquery'?['research-fellow','research-engineer','research-scientist-post-training','technical-content-writer-contract'].map(role=>`afterquery.work.${role}`):[];
  const rank=route=>{const index=preferred.indexOf(route.id);return index<0?preferred.length:index;};
  return [...rows].sort((a,b)=>rank(a)-rank(b));
}
let workReturnFocus=null,workViewRendered=false;
// Typing in the Paid work search draws the list once typing pauses for 180 ms, so each keystroke paints at
// once (measured on a phone at 4x CPU slowdown). A direct render, such as a filter change, cancels a waiting one.
let w4RenderTimer=0;
function w4QueueRender(){if(w4RenderTimer)clearTimeout(w4RenderTimer);w4RenderTimer=setTimeout(renderWork,180);}
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
function w4Count(n,one,many){return `${n} ${n===1?one:many}`;}
// Dates such as "14 and 15 Oct 2026"; more dates read "between 14 and 23 Oct 2026", and dates across
// months read "between 30 Sep 2026 and 2 Oct 2026".
function w4DateList(dates){
  const parts=dates.map(date=>w4Date(date).split(' '));
  if(parts.length===1)return parts[0].join(' ');
  const sameMonth=parts.every(p=>p.length===3&&p[1]===parts[0][1]&&p[2]===parts[0][2]);
  if(parts.length<=3&&sameMonth)return `${parts.slice(0,-1).map(p=>p[0]).join(', ')} and ${parts.at(-1).join(' ')}`;
  return `between ${sameMonth?parts[0][0]:parts[0].join(' ')} and ${parts.at(-1).join(' ')}`;
}
function w4FreshnessSentence(rows){
  const open=rows.filter(route=>['contract','jobs'].includes(w4Bucket(route))),checked=open.filter(w4Checked);
  if(!checked.length)return '';
  const which=open.length===1?'this link':checked.length===open.length?'these links':checked.length*2>=open.length?'most links':'some links',dates=w4DateList([...new Set(checked.map(w4Checked))].sort());
  return `We checked ${which} ${dates.startsWith('between')?'':'on '}${dates}.`;
}
// Scam advice, each tip tied to the public agencies that give it (US FTC and FBI, India's Home Ministry).
const W4_SAFETY_SOURCES={
  ftcJobs:['https://consumer.ftc.gov/articles/job-scams','FTC: Job scams'],
  ftcTasks:['https://consumer.ftc.gov/consumer-alerts/2024/11/task-scams-create-illusion-making-money','FTC: Task scams'],
  fbiHome:['https://www.ic3.gov/PSA/2024/PSA240604','FBI: Work-from-home scams'],
  ftcTexts:['https://consumer.ftc.gov/consumer-alerts/2026/04/job-offer-text-probably-scam','FTC: Job offer texts'],
  fbiPosts:['https://www.ic3.gov/PSA/2022/PSA220201','FBI: Fake job posts'],
  india:['https://pib.gov.in/PressReleaseIframePage.aspx?PRID=1982936','India Home Ministry: Part-time job fraud'],
  fbiData:['https://www.ic3.gov/PSA/2020/PSA200121','FBI: Fake listings that collect data'],
  ftcChecks:['https://consumer.ftc.gov/articles/how-spot-avoid-and-report-fake-check-scams','FTC: Fake checks']
};
const W4_SAFETY_TIPS=[
  ['Never pay to get work or to get your earnings out. Real employers pay you.',['ftcJobs','ftcTasks','fbiHome']],
  ['Ignore job offers you did not ask for that arrive by text or on apps such as WhatsApp or Telegram. Find the job on the company’s own website and apply there.',['ftcTexts','fbiPosts','india']],
  ['Share bank or tax details only after you are hired. First confirm who the employer is, in person or on a video call.',['fbiPosts','fbiData']],
  ['Never deposit a check from a new employer and send part of the money on. A bank can take weeks to spot a fake check, and then you must pay the money back.',['ftcJobs','ftcChecks']]
];
function workSafetyHTML(rows=[]){
  const fresh=w4FreshnessSentence(rows);
  return `<div class="w4-safety"><p><strong>Before you apply.</strong> Never pay to get work. Apply only on the company’s own website, and confirm the pay there.${fresh?' '+w4Escape(fresh):''}</p><details class="w4-safety-tips"><summary>How to spot a job scam</summary><ul>${W4_SAFETY_TIPS.map(([tip,keys])=>`<li><p>${w4Escape(tip)}</p><p class="w4-safety-sources">Sources: ${keys.map(key=>w4SourceLink(...W4_SAFETY_SOURCES[key])).join(' · ')}</p></li>`).join('')}</ul><p class="w4-safety-report">Report a scam: ${w4SourceLink('https://reportfraud.ftc.gov/','ReportFraud.ftc.gov')} in the US. In India, ${w4SourceLink('https://cybercrime.gov.in/','cybercrime.gov.in')} or call 1930.</p></details></div>`;
}
function w4Jump(id,label,n){return `<button type="button" data-work-section="${id}" ${n?'':'disabled'}>${label} <span>(${n})</span></button>`;}
function w4ContractSection(groups){
  if(!groups.contract.length)return '';
  const blocks=[['work-hourly','Hourly pay','Hourly',groups.hourly,true],['work-task','Paid per task','Per task',groups.task,true],['work-project','Pay set per project or not published','Pay set per project',groups.project,false]].filter(block=>block[3].length);
  return `<section class="w4-section"><h2 id="work-listed" class="work-list-heading">Contract and task work <span>(${groups.contract.length})</span></h2><div class="w4-section-intro"><p class="w4-section-note">Freelance and project work for AI training.</p>${blocks.length>1?`<p class="w4-jumps">${blocks.map(([id,,short,list])=>w4Jump(id,short,list.length)).join('')}</p>`:''}</div>${blocks.map(([id,label,,list,full])=>`<h3 id="${id}" class="w4-block-heading">${label} <span>(${list.length})</span></h3>${full?list.map(route=>workCard(route,'',4,true)).join(''):`<div class="w4-secondary-list">${w4CompactCards(list,3)}</div>`}`).join('')}</section>`;
}
function w4JobsSection(shown,more){
  const total=shown.length+more.length;
  return total?`<section class="w4-section"><h2 id="work-jobs" class="work-list-heading">Jobs and fellowships <span>(${total})</span></h2><p class="w4-section-note">Staff jobs and paid fellowships at these companies.</p>${shown.map(route=>workCard(route,'',3,true)).join('')}${w4GroupDisclosure(more,'More jobs and fellowships')}</section>`:'';
}
// Phone budget for typed searches. A one-letter search matches nearly every listing, so typing draws about as
// many full cards as the default view (W4_FULL_CARDS: the contract cards with an hourly or per-task rate, plus
// at least six jobs). Contract work is never cut; jobs get the rest of the budget. Groups under Other listings
// open only when they hold 12 or fewer matches. Every other match waits in a closed group that shows its count
// and draws its cards on first open. A filter change (a select field or Clear) skips the budget: it draws every
// match and opens every group that holds one. Cards draw their closed parts on first open (workCard lazy), and
// work-v5.css lets the browser skip cards far from the screen (content-visibility).
// Measured 26 Oct 2026 on a 390x844 phone at 4x CPU slowdown, interleaved with main's build, median of 7 runs,
// longest task in ms: opening #work main 339, before 413, now 188; typing "a" main 199, before 237, now 110;
// "e" main 270, before 773, now 111; "s" main 199, before 806, now 118. The page draws 1,258 elements (main
// 1,533, before 3,770). Most of the old cost was layout of card text hidden in closed disclosures.
const W4_FULL_CARDS=26,W4_SEARCH_JOBS=6,W4_SEARCH_OPEN_MAX=12;
function w4SearchJobBudget(groups){return Math.max(W4_SEARCH_JOBS,W4_FULL_CARDS-groups.hourly.length-groups.task.length);}
function w4OtherSection(groups,filtered,typed){
  const total=groups.boards.length+groups.outside.length+groups.closed.length,open=list=>filtered&&(!typed||list.length<=W4_SEARCH_OPEN_MAX);
  return total?`<section class="w4-section"><h2 id="work-more" class="work-list-heading">Other listings <span>(${total})</span></h2>${w4GroupDisclosure(groups.boards,'Career pages',open(groups.boards),'work-careers',W4_GROUP_NOTES.boards)}${w4GroupDisclosure(groups.outside,'Company jobs outside AI training',open(groups.outside),'work-outside',W4_GROUP_NOTES.outside)}${w4GroupDisclosure(groups.closed,'Closed or unpaid listings',open(groups.closed),'work-other',W4_GROUP_NOTES.closed)}</section>`:'';
}
// Networks whose location rules are set per project: a next step when a search finds little contract work.
const W4_PROJECT_RULES=/project|role-specific|country varies|eligibility varies|geographic restrictions|global/i;
function w4NetworkSuggestions(shown){
  const seen=new Set(shown.map(route=>route.id)),rows=workRouteRows().filter(route=>w4Bucket(route)==='contract'&&W4_PROJECT_RULES.test(route.geography||'')&&!seen.has(route.id)).sort(w4BestOrder);
  return rows.length?`<section class="w4-section w4-suggestions"><h2 id="work-suggested" class="work-list-heading">Expert networks worth checking <span>(${rows.length})</span></h2><p class="w4-section-note">These networks pick people for each project by skill and country. They may have work that your search words did not match.</p><div class="w4-secondary-list">${w4CompactCards(rows,2)}</div></section>`:'';
}
function w4EmptyState(query,filters){
  if(!workRouteRows().length)return '<p class="w4-empty">No listings are available right now.</p>';
  const matcher=query&&filters?w4QueryMatcher(query):null,queryAlone=matcher?workRouteRows().filter(route=>matcher.all(w4SearchText(route))).length:0;
  const message=!query?'No listing matches these filters.':queryAlone?'No listing matches this search with these filters.':`No listing mentions “${w4Escape(query)}”. Try a broader word.`;
  return `<div class="w4-empty-state"><p class="w4-empty">${message}</p><p class="w4-empty-actions">${query?'<button type="button" data-work-clear="search">Clear search</button>':''}${filters?'<button type="button" data-work-clear="filters">Clear filters</button>':''}</p></div>`;
}
// Each sort says how many paid work listings (contract and task work plus jobs) it can actually order.
function w4SortNote(sort,open,filtered){
  const of=`of ${w4Count(open.length,filtered?'matching paid work listing':'paid work listing',filtered?'matching paid work listings':'paid work listings')}`;
  if(sort==='hourly'){const rated=open.filter(w4HourlyRange);return `Sorted by the top of each published hourly range. ${rated.length} ${of} ${rated.length===1?'publishes':'publish'} one.${rated.some(route=>w4HourlyRange(route).currency!=='$')?' Rates in other currencies follow the US dollar rates.':''}`;}
  if(sort==='checked'){const dated=open.filter(w4Checked);return `Sorted by the date we last checked each link. ${dated.length} ${of} ${dated.length===1?'has':'have'} a check date.`;}
  return '';
}
// What the last render drew from: the raw search text, the select fields (filters and sort), and whether it
// kept the typing budget. A render whose only change is new search text is typing; one that changes a select
// field or a Clear button is a filter change. Nothing changed (a repeat render) keeps the last choice.
let w4LastSearch='',w4LastSelects='\n\n\n',w4LastTyped=false;
function w4TypedRender(query){
  const raw=String(state.workQuery??''),selects=[state.workGroup,state.workPay,state.workEligibility,state.workSort].map(value=>value||'').join('\n');
  const typed=Boolean(query)&&(selects!==w4LastSelects?false:raw!==w4LastSearch?true:w4LastTyped);
  w4LastSearch=raw;w4LastSelects=selects;w4LastTyped=typed;
  return typed;
}
function renderWork(){
  if(w4RenderTimer){clearTimeout(w4RenderTimer);w4RenderTimer=0;}
  workViewRendered=true;
  workReturnFocus=null;
  if(state.workSort===undefined)state.workSort='';
  const rows=filteredWork(),query=w4Text(state.workQuery),matcher=w4QueryMatcher(query),sort=state.workSort;
  const filters=[state.workGroup,state.workPay,state.workEligibility].filter(Boolean).length,filtered=Boolean(query||filters),typed=w4TypedRender(query);
  const groups=w4RouteGroups(rows,sort),orgs=new Set(rows.map(r=>r.company_id));
  // With a search and no chosen sort, listings whose role or company matches come first in each block.
  if(matcher&&!sort){const score=route=>matcher.all(`${companies[route.company_id]?.name} ${route.role}`.toLowerCase())?0:1;for(const key of ['hourly','task','project','jobs'])groups[key].sort((a,b)=>score(a)-score(b));}
  const summary=document.querySelector('.work-filters .responsive-filter-panel>summary');
  if(summary)summary.textContent=filters?`Filters (${filters})`:'Filters';
  // Every record counts here, including career pages and closed listings, so the line says "we reviewed".
  $('work-count').textContent=`${w4Count(rows.length,'listing','listings')} we reviewed at ${w4Count(orgs.size,'company','companies')}.`;
  const other=groups.boards.length+groups.outside.length+groups.closed.length;
  if($('work-overview'))$('work-overview').innerHTML=[['work-listed',groups.contract.length,'contract and task listing','contract and task listings'],['work-jobs',groups.jobs.length,'job or fellowship','jobs and fellowships'],['work-more',other,'other listing','other listings']].map(([id,n,one,many])=>`<button type="button" data-work-section="${id}" ${n?'':'disabled'}><strong>${n}</strong> ${n===1?one:many}</button>`).join('');
  const note=$('work-sort-note');
  if(note){note.textContent=w4SortNote(sort,groups.primary,filtered);note.hidden=!note.textContent;}
  // Unfiltered, the jobs section opens with six cards and at most three per company. Typing shows matching
  // jobs in full up to the phone budget, and the rest wait in the closed More group. A filter change draws
  // every match and opens every group that holds one.
  let jobs=groups.jobs,moreJobs=[];
  if(!filtered){const perCompany={};jobs=[];for(const route of groups.jobs){const n=perCompany[route.company_id]||0;if(jobs.length<6&&n<3){jobs.push(route);perCompany[route.company_id]=n+1;}else moreJobs.push(route);}}
  else if(typed){const budget=w4SearchJobBudget(groups);if(jobs.length>budget+1){moreJobs=jobs.slice(budget);jobs=jobs.slice(0,budget);}}
  // A search that finds little contract work, and does not name a company, also lists the per-project networks.
  const thin=matcher&&!filters&&groups.contract.length<5&&!rows.some(route=>matcher.all([companies[route.company_id]?.name,...(companies[route.company_id]?.aliases||[])].join(' ').toLowerCase()));
  $('work-cards').innerHTML=w4ContractSection(groups)+w4JobsSection(jobs,moreJobs)+w4OtherSection(groups,filtered,typed)+(rows.length?'':w4EmptyState(query,filters))+(thin?w4NetworkSuggestions(rows):'');
  syncSelection();
}
// Clears the search, the filters, or everything (the Clear filters button in the panel).
function resetWorkFilters(scope='all'){
  const fields={search:[['work-search','workQuery']],filters:[['work-group','workGroup'],['work-pay','workPay'],['work-eligibility','workEligibility']]};
  for(const [id,key] of scope==='all'?[...fields.search,...fields.filters,['work-sort','workSort']]:fields[scope]||[]){state[key]='';$(id).value='';}
  renderWork();
}
function workSummary(id){
  const rows=workRoutesFor(id);
  if(!rows.length)return '<p class="w4-empty">No paid work listing recorded for this company.</p>';
  const groups=w4RouteGroups(rows),jobs=w4ProfilePrimary(groups.jobs,id),open=groups.primary.length;
  const covered=new Set(rows.flatMap(r=>r.claim_ids||[]));
  const related=typeof workClaims==='function'?workClaims(id).filter(c=>!covered.has(c.id)).map(c=>c.id):[];
  // A "More" group never holds a single listing: that one is shown in full instead.
  const section=(label,list,full,more)=>{const shown=list.length<=full+1?list.length:full;return list.length?`<h3 class="w4-profile-heading">${label} <span>(${list.length})</span></h3><div class="work-v4-profile-grid">${list.slice(0,shown).map(route=>workCard(route,'',4,true)).join('')}</div>${w4GroupDisclosure(list.slice(shown),more,false,'','',3)}`:'';};
  return `<div class="work-v4-profile">${open||groups.boards.length?workSafetyHTML(rows):''}${section('Contract and task work',groups.contract,4,'More contract and task listings')}${section('Jobs and fellowships',jobs,2,'More jobs and fellowships')}${open?'':`<p class="w4-empty">No confirmed paid listing for ${w4Escape(companies[id]?.name||'this company')}.</p>`}${w4GroupDisclosure(groups.boards,'Career pages',!open,'',W4_GROUP_NOTES.boards)}${w4GroupDisclosure(groups.outside,'Company jobs outside AI training',false,'',W4_GROUP_NOTES.outside)}${w4GroupDisclosure(groups.closed,'Closed or unpaid listings',!open&&!groups.boards.length,'',W4_GROUP_NOTES.closed)}${related.length?`<details class="w4-related"><summary>Related work evidence</summary><div class="w4-evidence-links">${w4ClaimAccess(related)}</div></details>`:''}</div>`;
}

document.addEventListener('click',event=>{const summary=event.target.closest?.('summary');if(summary&&!summary.parentElement?.open)w4FillLazy(summary.parentElement);const clear=event.target.closest?.('[data-work-clear]');if(clear){resetWorkFilters(clear.dataset.workClear);document.getElementById('work-search')?.focus();return;}const button=event.target.closest?.('[data-work-section]');if(!button)return;const target=document.getElementById(button.dataset.workSection);if(target){if(target.tagName==='DETAILS'){w4FillGroup(target);target.open=true;}const focus=target.tagName==='DETAILS'?target.querySelector('summary'):target;if(focus&&focus.tagName!=='SUMMARY')focus.setAttribute('tabindex','-1');focus?.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'instant'});}});

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
