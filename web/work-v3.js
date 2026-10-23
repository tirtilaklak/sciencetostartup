/* Role-level public work routes. Loaded after app.js declarations, before initialize(). */
function workRouteBundle(){
  return typeof WORK_ROUTES !== 'undefined' ? WORK_ROUTES : (typeof window !== 'undefined' ? window.WORK_ROUTES : null);
}
function workRouteRows(){
  const bundle=workRouteBundle();
  return Array.isArray(bundle)?bundle:(bundle?.routes||[]);
}
function workRoutesFor(id){return workRouteRows().filter(r=>r.company_id===id);}
// Attribute identifiers must not pass through the prose-normalizing esc().
function workRouteAttr(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
// One formatter for every work date: building a new one per label made the first #work render slow.
const WORK_DAY_FORMAT=new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}),WORK_MONTH_FORMAT=new Intl.DateTimeFormat('en-GB',{month:'short',year:'numeric',timeZone:'UTC'});
function workDayLabel(value){return WORK_DAY_FORMAT.format(new Date(value+'T12:00:00Z')).replace('Sept','Sep');}
function workMonthLabel(value){return WORK_MONTH_FORMAT.format(new Date(value+'-15T12:00:00Z')).replace('Sept','Sep');}
const WORK_ROUTE_STATUS={
  listed:'Listing reviewed',program:'Project network',careers:'Careers route',
  intake_unverified:'Intake unconfirmed',pay_conflict:'Pay conflict',unverified:'Not reverified',
  historical:'Historical',closed:'Applications closed',contributions:'Research contributions',
  paused:'Training paused',no_route:'No verified route',inquiry:'Inquiry only',information:'Information only'
};
const WORK_ROUTE_ARCHIVE=new Set(['historical','closed','contributions','paused','no_route','inquiry','information']);
const WORK_ROUTE_ORDER={listed:0,pay_conflict:2,program:3,intake_unverified:4,careers:5,unverified:6,closed:7,historical:8,paused:9,contributions:10,inquiry:10,information:10,no_route:11};

// Keep the original filter option values and the profile API, using explicit
// route data rather than extracting rates from a company's combined prose.
function workTerms(id){
  const rows=workRoutesFor(id),cs=workClaims(id);
  return {cs,groups:[...new Set(rows.map(r=>r.group))],
    pay:rows.filter(r=>r.numeric_pay).map(r=>({text:r.role+': '+r.pay_label,claim_id:r.claim_ids[0]})),
    eligibility:rows.length===1?rows[0].eligibility:'Check project / unverified',
    requirements:rows.flatMap(r=>(r.requirements||[]).map(text=>({text,claim_id:r.claim_ids[0]})))};
}
function workRouteDate(value){
  if(!value||value==='undated')return 'Undated source';
  if(/^\d{4}-\d{2}-\d{2}$/.test(value))return workDayLabel(value);
  return value;
}
function workRoutePayBasis(route){
  if(route.pay_basis==='per_completed_task')return 'Paid per completed task';
  if(route.pay_basis==='hour_equivalent')return 'Estimated hourly equivalent';
  if(route.pay_basis==='approved_deliverables')return 'Subject to approved deliverables';
  if(route.pay_basis==='hour_or_accepted_task')return 'Hourly or accepted-task terms';
  if(route.pay_basis==='month_stipend')return 'Monthly stipend';
  if(route.status==='closed'||route.status==='historical')return 'Historical terms';
  if(route.pay_basis==='conflicting_hourly')return 'Header and body disagree';
  return route.numeric_pay?'Advertised compensation':'Compensation';
}
function workRouteStamp(route){return !route.as_of||route.as_of==='undated'?`Reviewed ${workRouteDate(route.reviewed_on)}`:`Evidence ${workRouteDate(route.as_of)}`;}
function workRouteAction(route){
  if(route.status==='closed'||route.status==='historical')return 'View archived terms';
  if(route.status==='no_route')return 'View reviewed site';
  if(route.status==='paused'||route.status==='contributions')return 'View research status';
  if(route.status==='inquiry')return 'View inquiry route';
  if(route.status==='information')return 'Read program information';
  if(route.status==='careers')return 'Explore careers';
  if(route.group==='Research fellowship')return 'View fellowship';
  if(route.status==='program')return 'Explore program';
  return 'View role & terms';
}
function workRouteEvidence(route){
  const terms=[route.hours,route.duration,...(route.requirements||[])].filter(Boolean);
  const checks=route.last_route_check;
  return `<div class="work-route-evidence">
    ${terms.length?`<ul class="work-term-list">${terms.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`:''}
    ${route.availability_note?`<p>${esc(route.availability_note)}</p>`:''}
    ${route.pay_context?`<p>${esc(route.pay_context)}${route.pay_policy?.source_url?` ${external(route.pay_policy.source_url,'Reward policy source')}`:''}</p>`:''}
    ${route.historical_pay_context?`<details><summary>Historical bounty record · source unavailable</summary><p>${esc(route.historical_pay_context.label)}: ${esc(route.historical_pay_context.amount)}.</p><p>${esc(route.historical_pay_context.note)}</p>${external(route.historical_pay_context.url,'Historical source (returned 404)')}</details>`:''}
    ${route.pay_observations?.length?`<dl class="work-pay-observations">${route.pay_observations.map(p=>`<div><dt>${esc(p.label)}</dt><dd>${esc(p.value)}</dd></div>`).join('')}</dl>`:''}
    <p class="sub">Source / evidence date: ${esc(workRouteDate(route.as_of))}. Reviewed ${esc(workRouteDate(route.reviewed_on))}.</p>
    ${checks?`<p class="sub">Route check ${esc(workRouteDate(checks.date))}: ${esc(checks.note)}</p>`:''}
    ${route.source_quote?`<blockquote class="work-source-quote">${esc(route.source_quote)}</blockquote>`:''}
    <div class="source-links">${[...new Map((route.sources||[]).map(s=>[s.url,s])).values()].map(s=>external(s.url,s.title||s.publisher||'Source')).join('')}</div>
    ${route.claim_ids?.length?`<details class="work-claim-details"><summary>Research evidence (${route.claim_ids.length})</summary>${route.claim_ids.map(id=>claims[id]?claimRecord(claims[id]):'').join('')}</details>`:''}
  </div>`;
}
function workCard(route){
  // Supporting legacy callers that pass a company does not combine its rates.
  if(!route.company_id)route=workRoutesFor(route.id)[0];
  if(!route)return '';
  const company=companies[route.company_id],status=WORK_ROUTE_STATUS[route.status]||'Route reviewed';
  const logo=typeof logoHTML==='function'?logoHTML(company.id):'';
  const compare=typeof compareCheck==='function'?compareCheck(company.id).replace('type="checkbox"',`type="checkbox" aria-label="Compare ${esc(company.name)}"`):'';
  return `<article class="work-card work-route-card ${WORK_ROUTE_ARCHIVE.has(route.status)?'work-route-archive':''}" data-work-company="${esc(company.id)}" data-work-route="${workRouteAttr(route.id)}">
    <div class="card-head"><div class="work-brand">${logo}<a class="work-company-name" href="#company/${esc(company.id)}/work">${esc(company.name)}</a></div>${compare}</div>
    <div class="work-route-meta"><span class="work-status work-status-${workRouteAttr(route.status)}">${esc(status)}</span><span class="sub">${esc(route.group)}</span></div>
    <h3 class="work-role">${esc(route.role)}</h3>
    <p class="work-description">${esc(route.summary)}</p>
    <div class="work-overview"><div class="work-pay-summary"><span class="sub">${esc(workRoutePayBasis(route))}</span><strong>${esc(route.pay_label)}</strong></div></div>
    <p class="work-location">${esc(route.geography)}${route.hours?`<span class="sub">${esc(route.hours)}</span>`:''}</p>
    <div class="work-primary-route">${external(route.url,workRouteAction(route))}<span class="sub">${esc(workRouteStamp(route))}</span></div>
    <details class="work-requirements"><summary>Requirements & sources</summary>${workRouteEvidence(route)}</details>
  </article>`;
}
// Search, pay and place helpers (w4QueryMatcher, w4PayMatches, w4WhereMatches) live in work-v4.js.
// A whole-phrase match wins; otherwise every word must match, with worker synonyms.
function filteredWork(){
  const matcher=w4QueryMatcher(state.workQuery);
  let rows=workRouteRows().filter(route=>(!state.workGroup||route.group===state.workGroup)&&w4PayMatches(route,state.workPay)&&w4WhereMatches(route,state.workEligibility));
  if(matcher){const text=new Map(rows.map(route=>[route,w4SearchText(route)])),phrase=rows.filter(route=>matcher.phrase(text.get(route)));rows=phrase.length?phrase:rows.filter(route=>matcher.all(text.get(route)));}
  return rows.sort((a,b)=>(WORK_ROUTE_ORDER[a.status]??10)-(WORK_ROUTE_ORDER[b.status]??10)||Number(b.numeric_pay)-Number(a.numeric_pay)||companies[a.company_id].name.localeCompare(companies[b.company_id].name)||a.role.localeCompare(b.role));
}
function renderWork(){
  const rows=filteredWork(),active=rows.filter(r=>!WORK_ROUTE_ARCHIVE.has(r.status)&&r.status!=='careers'),careers=rows.filter(r=>r.status==='careers'),archive=rows.filter(r=>WORK_ROUTE_ARCHIVE.has(r.status)),orgs=new Set(rows.map(r=>r.company_id));
  $('work-count').textContent=`${rows.length} ${rows.length===1?'route':'routes'} · ${orgs.size} ${orgs.size===1?'organization':'organizations'}${archive.length?` · ${archive.length} historical or research ${archive.length===1?'route':'routes'}`:''}`;
  const filtered=Boolean(state.workQuery||state.workGroup||state.workPay||state.workEligibility);
  const unreviewed=workRouteBundle()?.unreviewed_organizations||[];
  $('work-cards').innerHTML=active.map(workCard).join('')+(careers.length?`<details class="work-route-archive-group work-career-directory" ${filtered?'open':''}><summary>Company career directories <span>${careers.length}</span></summary><div class="card-grid work-grid">${careers.map(workCard).join('')}</div></details>`:'')+(archive.length?`<details class="work-route-archive-group" ${filtered?'open':''}><summary>Historical, research & information routes <span>${archive.length}</span></summary><div class="card-grid work-grid">${archive.map(workCard).join('')}</div></details>`:'')+(rows.length?'':'<p class="empty-state">No work routes match. Clear a filter to broaden the results.</p>')+(!filtered&&unreviewed.length?`<details class="work-coverage-detail"><summary>Coverage notes · ${unreviewed.length} other organizations</summary><p>No work route has been reviewed for ${unreviewed.map(c=>`<a href="#company/${esc(c.company_id)}/work">${esc(c.name)}</a>`).join(', ')}.</p></details>`:'');
  syncSelection();
}
function workSummary(id){
  const rows=workRoutesFor(id);
  if(!rows.length)return '<p>No public work route has been reviewed for this organization.</p>';
  return `<div class="profile-work-routes">${rows.map(route=>`<section class="profile-work-route" data-work-route="${workRouteAttr(route.id)}"><div class="section-heading"><h3>${esc(route.role)}</h3><span class="work-status work-status-${workRouteAttr(route.status)}">${esc(WORK_ROUTE_STATUS[route.status]||'Route reviewed')}</span></div><p>${esc(route.summary)}</p><p class="work-profile-pay"><strong>${esc(route.pay_label)}</strong> <span class="sub">${esc(workRoutePayBasis(route))} · ${esc(route.geography)} · Evidence ${esc(workRouteDate(route.as_of))}</span></p><div class="work-actions">${external(route.url,workRouteAction(route))}</div><details class="work-requirements"><summary>Requirements & sources</summary>${workRouteEvidence(route)}</details></section>`).join('')}</div>`;
}
