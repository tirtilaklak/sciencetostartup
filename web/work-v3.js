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
const WORK_ROUTE_ARCHIVE=S2SWork.archive;
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
const WORK_TYPE_GROUPS=S2SWork.types;
function normalizeWorkCriteria(value={}){
  return S2SWork.normalizeCriteria(value);
}
function currentWorkCriteria(){
  const type=Object.hasOwn(WORK_TYPE_GROUPS,state.workGroup)?state.workGroup:Object.keys(WORK_TYPE_GROUPS).find(key=>WORK_TYPE_GROUPS[key]===state.workGroup)||'';
  return normalizeWorkCriteria({q:state.workQuery,kind:state.workKind,type,pay:state.workPay,arrangement:state.workEligibility,sort:state.workSort});
}
function workCriteriaFromHash(hash=location.hash){
  const text=String(hash || '');
  return S2SWork.readCriteria(new URLSearchParams(text.includes('?') ? text.slice(text.indexOf('?')+1) : ''));
}
function workHashFor(value=currentWorkCriteria()){
  const query=S2SWork.writeCriteria(new URLSearchParams(),normalizeWorkCriteria(value)).toString();
  return '#work'+(query?'?'+query:'');
}
function updateWorkCompareLink(criteria){
  const compare=document.getElementById('work-native-compare');
  if(compare)compare.href='/work/?'+S2SWork.writeCriteria(new URLSearchParams('view=compare'),criteria);
}
function applyWorkCriteria(value){
  const criteria=normalizeWorkCriteria(value);
  updateWorkCompareLink(criteria);
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
  updateWorkCompareLink(criteria);
  const hash=workHashFor(criteria);
  if(location.hash!==hash||history.state?.workDraft)history.replaceState({...history.state,workDraft:null},'',hash);
}
function queueWorkRoute(immediate=false){
  cancelWorkRouteWrite();
  if(routeParts()[0]!=='work')return;
  const criteria=currentWorkCriteria(),key=historyKey();if(key)workEntryCriteria.set(key,criteria);
  updateWorkCompareLink(criteria);
  if(immediate){flushWorkRoute();return;}
  // Keep a pending edit on its own entry even if a navigation beats the URL update.
  const generation=workRouteGeneration,hash=location.hash;
  try{history.replaceState({...history.state,workDraft:{hash,criteria}},'');}catch{}
  workRouteTimer=setTimeout(()=>{if(generation===workRouteGeneration&&key===historyKey()&&location.hash===hash)flushWorkRoute();},180);
}
function workCriteriaForRoute(hash=location.hash,traversal=false){
  const draft=history.state?.workDraft,key=historyKey();
  if(draft?.hash===hash&&draft.criteria)return normalizeWorkCriteria(draft.criteria);
  if(traversal&&workEntryCriteria.has(key))return workEntryCriteria.get(key);
  return workCriteriaFromHash(hash);
}
function syncWorkRoute(traversal=false){
  cancelWorkRouteWrite();
  const key=historyKey(),criteria=workCriteriaForRoute(location.hash,traversal);
  applyWorkCriteria(criteria);if(key)workEntryCriteria.set(key,criteria);
  const hash=workHashFor(criteria);if(location.hash!==hash||history.state?.workDraft)history.replaceState({...history.state,workDraft:null},'',hash);
  // Returning from a company keeps the open disclosures and the link inside them.
  const returningToListing=traversal&&workReturnOrigin?.entryKey===key&&workReturnFocus?.isConnected&&workRenderedHash===hash;
  if(!returningToListing)renderWork();
}
window.addEventListener('pageshow',event=>{
  if(event.persisted&&routeParts()[0]==='work'&&history.state?.workDraft?.hash===location.hash)route({type:'work-resume'});
});
function selectWorkRoutes(input,criteria={}){
  if(searchContextPending(criteria.q))throw new Error('Work search context is not ready');
  return S2SWork.select(input,normalizeWorkCriteria(criteria),w4SearchText,w4CompanyName)
    .sort((a,b)=>(WORK_ROUTE_ORDER[a.status]??10)-(WORK_ROUTE_ORDER[b.status]??10)
      || Number(b.numeric_pay)-Number(a.numeric_pay) || w4CompanyName(a).localeCompare(w4CompanyName(b)) || a.role.localeCompare(b.role));
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
function exportWorkCsv(){
  if(searchContextPending(state.workQuery)){
    const hash=workHashFor();
    return window.ensureSearchContext().then(()=>{
      if(routeParts()[0]==='work'&&workHashFor()===hash)exportWorkCsv();
    }).catch(()=>workSearchFailure());
  }
  flushWorkRoute();
  if(w4RenderTimer)renderWork();
  const criteria=currentWorkCriteria();
  const groups=w4DiscoveryGroups(selectWorkRoutes(workRouteRows(),criteria),criteria.sort,criteria.q);
  const rows=S2SWork.groups.flatMap(key=>groups[key]);
  const asset=window.SUMMARY_INDEX?.workResults;
  if(!asset){
    // Legacy embedded contexts have a complete route stream.
    const exportRows=rows.map(route=>({...route,company_name:w4CompanyName(route)}));
    download('sciencetostartup-current-work-results.csv',S2SWork.csvFor(exportRows,criteria,w4Destination),'text/csv;charset=utf-8');
    return;
  }
  const status=$('work-export-status'), button=$('work-export');
  if(button?.getAttribute('aria-busy')==='true')return;
  button?.setAttribute('aria-busy','true');
  if(status)status.textContent='Preparing your CSV…';
  return S2SWork.fetchExport(asset,rows.map(route=>route.id),criteria).then(body=>{
    S2SWork.downloadCsv(body);
    if(status)status.textContent='';
  }).catch(()=>{
    if(status)status.textContent='The CSV could not load. Choose Download CSV to try again.';
  }).finally(()=>button?.removeAttribute('aria-busy'));
}
