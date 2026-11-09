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
const WORK_TYPE_GROUPS={contract:'Expert & contractor projects',employment:'Employment',fellowship:'Research fellowship',bounty:'Contributor bounties',study:'study',varies:'varies',unknown:'Unverified route'};
const WORK_FILTER_VALUES={kind:['','named','programs'],type:['',...Object.keys(WORK_TYPE_GROUPS)],pay:['','hourly','task','yearly','monthly','numeric','undisclosed'],arrangement:['','remote','onsite','varies'],sort:['','hourly','checked']};
function normalizeWorkCriteria(value={}){
  const result={q:String(value.q??'').trim().slice(0,256)};
  for(const key of Object.keys(WORK_FILTER_VALUES)){const raw=String(value[key]??'');result[key]=WORK_FILTER_VALUES[key].includes(raw)?raw:'';}
  return result;
}
function currentWorkCriteria(){
  const type=Object.hasOwn(WORK_TYPE_GROUPS,state.workGroup)?state.workGroup:Object.keys(WORK_TYPE_GROUPS).find(key=>WORK_TYPE_GROUPS[key]===state.workGroup)||'';
  return normalizeWorkCriteria({q:state.workQuery,kind:state.workKind,type,pay:state.workPay,arrangement:state.workEligibility,sort:state.workSort});
}
function workCriteriaFromHash(hash=location.hash){
  const text=String(hash||''),query=text.includes('?')?text.slice(text.indexOf('?')+1):'',params=new URLSearchParams(query),value={};
  for(const key of ['q',...Object.keys(WORK_FILTER_VALUES)])value[key]=params.get(key)||'';
  // Earlier links sometimes use the internal group label; canonical links use engagement ids.
  if(!WORK_FILTER_VALUES.type.includes(value.type))value.type=Object.keys(WORK_TYPE_GROUPS).find(key=>WORK_TYPE_GROUPS[key]===value.type)||'';
  return normalizeWorkCriteria(value);
}
function workHashFor(value=currentWorkCriteria()){
  const criteria=normalizeWorkCriteria(value),params=new URLSearchParams();
  for(const key of ['q','kind','type','pay','arrangement','sort'])if(criteria[key])params.set(key,criteria[key]);
  const query=params.toString();return '#work'+(query?'?'+query:'');
}
function applyWorkCriteria(value){
  const criteria=normalizeWorkCriteria(value);
  Object.assign(state,{workQuery:criteria.q,workKind:criteria.kind,workGroup:criteria.type,workPay:criteria.pay,workEligibility:criteria.arrangement,workSort:criteria.sort});
  for(const [id,key] of [['work-search','workQuery'],['work-kind','workKind'],['work-group','workGroup'],['work-pay','workPay'],['work-eligibility','workEligibility'],['work-sort','workSort']]){const field=$(id);if(field)field.value=state[key];}
  return criteria;
}
const workEntryCriteria=new Map();
let workRouteTimer=0,workRouteGeneration=0;
function cancelWorkRouteWrite(){clearTimeout(workRouteTimer);workRouteTimer=0;workRouteGeneration++;}
function flushWorkRoute(){
  cancelWorkRouteWrite();
  if(routeParts()[0]!=='work')return;
  const criteria=currentWorkCriteria(),key=historyKey();if(key)workEntryCriteria.set(key,criteria);
  const hash=workHashFor(criteria);
  if(location.hash!==hash)history.replaceState({...history.state,workCriteria:criteria},'',hash);
}
function queueWorkRoute(immediate=false){
  cancelWorkRouteWrite();
  if(routeParts()[0]!=='work')return;
  const criteria=currentWorkCriteria(),key=historyKey();if(key)workEntryCriteria.set(key,criteria);
  if(immediate){flushWorkRoute();return;}
  const generation=workRouteGeneration;
  workRouteTimer=setTimeout(()=>{if(generation===workRouteGeneration&&key===historyKey()&&routeParts()[0]==='work')flushWorkRoute();},180);
}
function syncWorkRoute(traversal=false){
  cancelWorkRouteWrite();
  const key=historyKey(),criteria=traversal&&workEntryCriteria.has(key)?workEntryCriteria.get(key):workCriteriaFromHash();
  applyWorkCriteria(criteria);if(key)workEntryCriteria.set(key,criteria);
  const hash=workHashFor(criteria);if(location.hash!==hash)history.replaceState({...history.state,workCriteria:criteria},'',hash);
  renderWork();
}
// Capture outgoing state before the browser creates another fragment entry. The router
// cancels pending replacements on traversal, so late typing cannot rewrite a destination.
document.addEventListener('click',event=>{const link=event.target?.closest?.('a[href]');if(normalSelfLinkActivation(event,link)&&routeParts()[0]==='work')flushWorkRoute();},true);
window.addEventListener('pagehide',flushWorkRoute);
function selectWorkRoutes(input,criteria={}){
  if(searchContextPending(criteria.q))throw new Error('Work search context is not ready');
  const filter=normalizeWorkCriteria(criteria),matcher=w4QueryMatcher(filter.q),group=WORK_TYPE_GROUPS[filter.type]||'';
  let rows=input.filter(route=>(!filter.kind||w4OpportunityKind(route)===(filter.kind==='named'?'named_listing':'network_program'))&&(!group||w4GroupMatches(route,group))&&w4PayMatches(route,filter.pay)&&w4WhereMatches(route,filter.arrangement));
  if(matcher){const text=new Map(rows.map(route=>[route,w4SearchText(route)])),phrase=rows.filter(route=>matcher.phrase(text.get(route)));rows=phrase.length?phrase:rows.filter(route=>matcher.all(text.get(route)));}
  return rows.sort((a,b)=>(WORK_ROUTE_ORDER[a.status]??10)-(WORK_ROUTE_ORDER[b.status]??10)||Number(b.numeric_pay)-Number(a.numeric_pay)||companies[a.company_id].name.localeCompare(companies[b.company_id].name)||a.role.localeCompare(b.role));
}
function filteredWork(){return selectWorkRoutes(workRouteRows(),currentWorkCriteria());}
function summarizeWorkResults(rows){
  const summary={total:rows.length,named:0,programs:0,careers:0,other:0,archived:0,outside:0,companies:new Set(rows.map(route=>route.company_id)).size};
  for(const route of rows){if(WORK_ROUTE_ARCHIVE.has(route.status)){summary.archived++;continue;}if(route.ai_data_work===false){summary.outside++;continue;}const kind=w4OpportunityKind(route);summary[kind==='named_listing'?'named':kind==='network_program'?'programs':kind==='career_page'?'careers':'other']++;}
  return summary;
}
function workResultsLabel(summary){
  if(!summary.total)return 'No recorded matches';
  return [`${summary.total} ${summary.total===1?'record':'records'}`,summary.named?`${summary.named} ${summary.named===1?'listing':'listings'}`:'',summary.programs?`${summary.programs} ${summary.programs===1?'program':'programs'}`:''].filter(Boolean).join(' · ');
}
// Current-results CSV keeps fact states and source identities; full narrative
// notes and history are linked separately so opening a profile cannot alter it.
function workReviewMetadata(route){
 return Object.fromEntries(Object.entries(route.field_reviews||{}).sort(([a],[b])=>a.localeCompare(b)).map(([field,review])=>[field,{state:review.state,reviewed_on:review.reviewed_on??null,source_ids:[...(review.source_ids||[])],basis:review.basis,...(field==='location'&&review.note?{note:review.note}:{})}]));
}
function exportWorkCsv(){
  if(searchContextPending(state.workQuery)){const hash=workHashFor();return window.ensureSearchContext().then(()=>{if(routeParts()[0]==='work'&&workHashFor()===hash)exportWorkCsv();}).catch(()=>workSearchFailure());}
  flushWorkRoute();const criteria=currentWorkCriteria();
  const head=['route_id','company','role','opportunity_kind','engagement_type','availability','advertised_pay','pay_unit','hourly_comparable','currency','arrangements','location','requirements','assessment','commitment','duration','terms_reviewed_on','terms_review_scope','original_application_url','current_action_url','current_action_label','source_urls','field_review_metadata','full_research_profile_url','search_query','opportunity_filter','engagement_filter','pay_filter','arrangement_filter','sort'];
  const groups=w4DiscoveryGroups(selectWorkRoutes(workRouteRows(),criteria),criteria.sort);
  const rows=['named','programs','boards','outside','closed'].flatMap(key=>groups[key]).map(route=>[route.id,companies[route.company_id]?.name||route.company_id,route.role,w4OpportunityKind(route),w4Engagement(route),w4Status(route)||'Recorded listing',route.pay_label||'',route.pay_terms?.unit||'',route.pay_terms?.hourly_comparable===true,route.pay_terms?.currency||'',w4Arrangements(route).join(' | '),route.geography||'',(route.requirements||[]).join(' | '),route.assessment||'',route.hours||'',route.duration||'',w4TermsReviewDate(route)||'',w4ApprovedTermsReceipt(route)?'key_terms':route.terms_checked_on?'pay_terms':'',route.url||'',w4Destination(route).url||'',w4Destination(route).label||'',(route.sources||[]).map(source=>source.url).join(' | '),JSON.stringify(workReviewMetadata(route)),'https://sciencetostartup.com/company/'+encodeURIComponent(route.company_id)+'/',criteria.q,criteria.kind,criteria.type,criteria.pay,criteria.arrangement,criteria.sort]);
  download('sciencetostartup-current-work-results.csv','\ufeff'+[head,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n','text/csv;charset=utf-8');
}
// The page renderers (workCard, renderWork, workSummary) live in work-v4.js, which loads after this file.
