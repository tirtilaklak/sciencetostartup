/* Paid work data helpers: listing rows, dates, the archive statuses and the filter. Loaded after app.js
   declarations and before work-v4.js, which draws the page. */
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
// Search, pay and place helpers (w4QueryMatcher, w4PayMatches, w4WhereMatches) live in work-v4.js.
// A whole-phrase match wins; otherwise every word must match, with worker synonyms.
function filteredWork(){
  const matcher=w4QueryMatcher(state.workQuery);
  let rows=workRouteRows().filter(route=>(!state.workGroup||w4GroupMatches(route,state.workGroup))&&w4PayMatches(route,state.workPay)&&w4WhereMatches(route,state.workEligibility));
  if(matcher){const text=new Map(rows.map(route=>[route,w4SearchText(route)])),phrase=rows.filter(route=>matcher.phrase(text.get(route)));rows=phrase.length?phrase:rows.filter(route=>matcher.all(text.get(route)));}
  return rows.sort((a,b)=>(WORK_ROUTE_ORDER[a.status]??10)-(WORK_ROUTE_ORDER[b.status]??10)||Number(b.numeric_pay)-Number(a.numeric_pay)||companies[a.company_id].name.localeCompare(companies[b.company_id].name)||a.role.localeCompare(b.role));
}
// The page renderers (workCard, renderWork, workSummary) live in work-v4.js, which loads after this file.
