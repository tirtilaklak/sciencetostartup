/* One asynchronous route owner. The classic renderers receive only validated contexts. */
window.APP_BUILD_ID=/* APP_BUILD_ID */null;
const presentationIdentity=window.SUMMARY_INDEX;
if(!presentationIdentity||presentationIdentity.schemaVersion!=='1.0.0'||presentationIdentity.buildId!==window.APP_BUILD_ID||presentationIdentity.datasetVersion!==DATA.dataset_version||document.documentElement.dataset.buildId!==window.APP_BUILD_ID)throw new Error('Presentation release identity mismatch');
const detailCache=new Map();
window.COMPANY_CONTEXTS_READY=new Set();
let searchContextPromise=null,searchRouteView='',searchDisabledControls=[];
let workContextPromise=null,workContextReady=!window.EXPLORE_DEFER_WORK;
let healthModulePromise=null,healthModuleAttempts=0;
let navigationGeneration=0,detailController=null;
const synchronousRoute=route;
function presentationState(state,reason=''){
 const root=document.documentElement;root.dataset.viewState=state;root.dataset.viewReason=reason;root.dataset.buildId=window.APP_BUILD_ID;
}
function validatePresentation(payload,companyId){
 for(const key of ['schemaVersion','buildId','editorialReleaseId','datasetVersion'])if(payload?.[key]!==presentationIdentity[key])throw new Error('Stale presentation '+key);
 if(companyId&&payload.companyId!==companyId)throw new Error('Wrong company response');
 if(!payload.data||payload.data.dataset_version!==DATA.dataset_version)throw new Error('Invalid research context');
 return payload;
}
async function fetchPresentation(descriptor,companyId,signal,readSummary=false){
 const controller=new AbortController(),cancel=()=>controller.abort();let timedOut=false;
 if(signal?.aborted)cancel();else signal?.addEventListener('abort',cancel,{once:true});
 const deadline=setTimeout(()=>{timedOut=true;controller.abort();},15000);
 try{
  let bytes;const early=window.PRESENTATION_PREFETCH;
  if(early?.href===descriptor.href&&early.sha256===descriptor.sha256&&early.buildId===presentationIdentity.buildId){
   delete window.PRESENTATION_PREFETCH;
   const cancelEarly=()=>early.controller.abort();controller.signal.addEventListener('abort',cancelEarly,{once:true});
   try{if(controller.signal.aborted)cancelEarly();const result=await early.promise;if(controller.signal.aborted)throw new DOMException('Navigation changed','AbortError');if(result.error)throw result.error;bytes=result.bytes;}
   finally{controller.signal.removeEventListener('abort',cancelEarly);}
  }else{
   const response=await fetch(descriptor.href,{signal:controller.signal,cache:'no-cache'});
   if(!response.ok)throw new Error('Evidence request failed ('+response.status+')');
   bytes=await response.arrayBuffer();
  }
  if(globalThis.crypto?.subtle){
   const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
   if(digest!==descriptor.sha256)throw new Error('Evidence integrity mismatch');
  }
  const payload=JSON.parse(new TextDecoder().decode(bytes));
  if(readSummary)return validatePresentation({...payload,data:payload.bootstrap},companyId);
  return validatePresentation(payload,companyId);
 }catch(error){if(timedOut)throw new Error('Evidence request timed out');throw error;}
 finally{clearTimeout(deadline);signal?.removeEventListener('abort',cancel);}
}
function exploreWorkPending(){return !workContextReady;}
function ensureExploreWork(){
 if(workContextReady)return Promise.resolve();
 if(workContextPromise)return workContextPromise;
 workContextPromise=fetchPresentation(presentationIdentity.asset,null,null,true).then(({work})=>{
  if(!Array.isArray(work?.routes)||new Set(work.routes.map(row=>row.id)).size!==work.routes.length)
   throw new Error('Invalid work listings');
  const rows=new Map(work.routes.map(row=>[row.id,row]));
  for(const row of workRouteRows())rows.set(row.id,row);
  window.WORK_ROUTES={...work,routes:[...rows.values()]};
  workContextReady=true;
 }).finally(()=>{workContextPromise=null;});
 return workContextPromise;
}
function ensureHealthModule(){
 if(window.APP_HEALTH_READY===window.APP_BUILD_ID)return Promise.resolve();
 if(healthModulePromise)return healthModulePromise;
 const descriptor=presentationIdentity.modules?.businessHealth;
 if(!descriptor?.href||!descriptor.integrity)return Promise.reject(new Error('Financial module is unavailable'));
 healthModulePromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');let finished=false;
  const finish=error=>{if(finished)return;finished=true;clearTimeout(deadline);script.onload=script.onerror=null;if(error){script.remove();for(const link of document.querySelectorAll('link[rel="preload"][as="script"]'))if(link.getAttribute('href')===descriptor.href)link.remove();reject(error);}else resolve();};
  const deadline=setTimeout(()=>finish(new Error('Financial module request timed out')),15000);
  // WebKit can retain a failed SRI preload for the page's lifetime. A retry
  // needs a fresh request while keeping the same integrity and release checks.
  const attempt=healthModuleAttempts++;
  script.src=descriptor.href+(attempt?(descriptor.href.includes('?')?'&':'?')+'s2s_retry='+attempt:'');script.integrity=descriptor.integrity;script.crossOrigin='anonymous';script.dataset.presentationModule='business-health';
  script.onerror=()=>finish(new Error('Financial module could not load'));
  script.onload=()=>{
   try{
    const module=window.SCIENCE_HEALTH_MODULE;
    if(module?.buildId!==window.APP_BUILD_ID||typeof module.initialize!=='function')throw new Error('Stale financial module');
    module.initialize();
    if(!['refreshBundle','render','valueText','latestFigures'].every(key=>typeof window.BusinessHealth?.[key]==='function'))throw new Error('Invalid financial module');
    const profiles=window.ScienceProfileDetails;
    if(profiles?.buildId!==window.APP_BUILD_ID||!['profileProductGrid','profileCase','profileRelationshipGrid','profileRisks','profilePeople','profileCapital','profileTraction','profileArchive'].every(key=>typeof profiles[key]==='function'))throw new Error('Invalid profile module');
    const details=window.ScienceDetailViews;
    if(details?.sourceContextBuildId!==window.APP_BUILD_ID)throw new Error('Invalid source-context module');
    if(details?.buildId!==window.APP_BUILD_ID||!['claimRecord','metricTile','disclosedPrimarySummary','financingEvent','customerRecord','profileGrowth','renderAssessment','comparisonRows','renderCompare','evidenceMetricContextHTML','claimConfidenceHTML','showEvidence','openCompanyStory','initMethod'].every(key=>typeof details[key]==='function'))throw new Error('Invalid detail-view module');
    window.APP_HEALTH_READY=window.APP_BUILD_ID;finish();
   }catch(error){finish(error);}
  };
  document.head.append(script);
 }).finally(()=>{healthModulePromise=null;});
 return healthModulePromise;
}
window.ensureSearchContext=function(){
 if(window.SEARCH_INDEX)return Promise.resolve(window.SEARCH_INDEX);
 if(searchContextPromise)return searchContextPromise;
 if(!presentationIdentity.fullSearch)return Promise.reject(new Error('Search index is unavailable'));
 const search=fetchPresentation(presentationIdentity.fullSearch);
 const prerequisites=exploreWorkPending()?Promise.all([search,ensureExploreWork()]).then(([payload])=>payload):search;
 searchContextPromise=prerequisites.then(payload=>{
  for(const key of ['companySearch','profileProducts','workSearch'])if(!payload[key]||typeof payload[key]!=='object')throw new Error('Invalid search index');
  if(!Array.isArray(payload.editorialReadouts))throw new Error('Invalid export readouts');
  if(!Array.isArray(payload.researchSearchEntries))throw new Error('Invalid research search index');
  const readoutCompanies=new Set(payload.editorialReadouts.filter(row=>typeof row?.readout==='string').map(row=>row.company_id));
  for(const company of DATA.companies)if(typeof payload.companySearch[company.id]!=='string'||!Array.isArray(payload.profileProducts[company.id]))throw new Error('Incomplete company search index');
  for(const company of DATA.companies)if(!readoutCompanies.has(company.id))throw new Error('Incomplete export readouts');
  for(const record of workRouteRows())if(typeof payload.workSearch[record.id]!=='string')throw new Error('Incomplete work search index');
  window.SEARCH_INDEX={...payload,companySearchText:payload.companySearch,companyProducts:payload.profileProducts,workSearchText:payload.workSearch};
  if(typeof refreshResearchIndexes==='function')refreshResearchIndexes();
  return window.SEARCH_INDEX;
 }).finally(()=>{searchContextPromise=null;});
 return searchContextPromise;
};
function restoreSearchRouteControls(){
 for(const [control,disabled]of searchDisabledControls)if(control.isConnected)control.disabled=disabled;
 searchDisabledControls=[];
 if(searchRouteView){$('work-cards')?.removeAttribute('aria-busy');searchRouteView='';}
}
function pendingWorkSearchRoute(failed=false,listings=false){
 pendingView('work');
 const section=$('work-view'),cards=$('work-cards'),count=$('work-count');
 section.hidden=false;searchRouteView='work';
 if(!failed){searchDisabledControls=[...section.querySelectorAll('input,select,button')].map(control=>[control,control.disabled]);for(const [control]of searchDisabledControls)control.disabled=true;cards?.setAttribute('aria-busy','true');}
 const label=listings?(failed?'Work listings could not load. Your filters are preserved.':'Loading work listings…')
  :(failed?'Search could not load. Your query is preserved.':'Loading the search index…');
 if(count)count.textContent=label;
 const native='/work/'+workHashFor().slice('#work'.length);
 if(cards)cards.innerHTML=`<p role="${failed?'alert':'status'}">${label} ${failed?'<button type="button" data-retry-search>Try again</button> ':''}<a href="${attr(native)}">Open native Work results</a></p>`;
}
function installResearchContext(payload){
 for(const [key,rows]of Object.entries(payload.data)){
  if(!Array.isArray(rows)||!Array.isArray(DATA[key]))continue;
  const positions=new Map(DATA[key].map((row,i)=>[row?.id,i]));
  for(const row of rows){if(!row?.id)continue;const i=positions.get(row.id);if(i===undefined){positions.set(row.id,DATA[key].length);DATA[key].push(row);}else DATA[key][i]=row;}
 }
 for(const [key,map]of [['claims',claims],['sources',sources],['companies',companies],['people',people],['investors',investors]])Object.assign(map,index(DATA[key]));
 if(payload.profileContent){const entries=new Map((window.PROFILE_CONTENT?.entries||[]).map(e=>[e.company_id,e]));for(const entry of payload.profileContent.entries)entries.set(entry.company_id,entry);window.PROFILE_CONTENT={entries:[...entries.values()]};}
 if(payload.companyEvents){const events=new Map((window.COMPANY_EVENTS?.events||[]).map(e=>[e.id,e]));for(const event of payload.companyEvents.events)events.set(event.id,event);window.COMPANY_EVENTS={...window.COMPANY_EVENTS,events:[...events.values()]};}
 if(payload.sourceUpdates){
  const before=window.SOURCE_UPDATES||{},next=payload.sourceUpdates,merge=(a,b)=>[...new Map([...(a||[]),...(b||[])].map(row=>[row.id,row])).values()];
  const locations=next.source_locations?{source_locations:{...before.source_locations,...next.source_locations}}:{};
  window.SOURCE_UPDATES={...before,...next,...locations,updates:merge(before.updates,next.updates),evidence_context:{...before.evidence_context,...next.evidence_context,corrections:merge(before.evidence_context?.corrections,next.evidence_context?.corrections)}};
 }
 if(payload.workRoutes){
  const rows=Array.isArray(payload.workRoutes)?payload.workRoutes:payload.workRoutes.routes;
  const records=new Map(workRouteRows().map(row=>[row.id,row]));for(const row of rows||[])records.set(row.id,row);
  window.WORK_ROUTES={...window.WORK_ROUTES,routes:[...records.values()]};
 }
 if(payload.businessHealth){
  const merge=(before,after,key='id')=>[...new Map([...(before||[]),...(after||[])].map(row=>[row[key],row])).values()];
  const before=window.BUSINESS_HEALTH||{},next=payload.businessHealth;
  window.BUSINESS_HEALTH={...before,...next,observations:merge(before.observations,next.observations),fresh_claims:merge(before.fresh_claims,next.fresh_claims),sources:merge(before.sources,next.sources),private_company_review:merge(before.private_company_review,next.private_company_review,'company_id'),profile_finance:{...before.profile_finance,...next.profile_finance},source_checks:{...before.source_checks,...next.source_checks,entries:merge(before.source_checks?.entries,next.source_checks?.entries,'source_id')}};
  window.BusinessHealth?.refreshBundle();
 }
 if(payload.financeClaimContext)window.FINANCE_CLAIM_CONTEXT={...window.FINANCE_CLAIM_CONTEXT,...payload.financeClaimContext};
 if(payload.companyId)window.COMPANY_CONTEXTS_READY.add(payload.companyId);
 if(typeof refreshResearchIndexes==='function')refreshResearchIndexes();
}
async function companyContext(id,signal){
 const descriptor=Object.hasOwn(presentationIdentity.companyDetails,id)&&presentationIdentity.companyDetails[id];if(!descriptor)throw new Error('Company record is missing');
 if(detailCache.has(id))return detailCache.get(id);
 const [payload]=await Promise.all([fetchPresentation(descriptor,id,signal),ensureHealthModule()]);detailCache.set(id,payload);return payload;
}
function pendingView(view){
 document.documentElement.removeAttribute('data-route');
 for(const section of document.querySelectorAll('main>.view'))section.hidden=section.id!==view+'-view';
 for(const link of document.querySelectorAll('[data-nav]')){
  if(link.dataset.nav===(view==='profile'?'companies':view))link.setAttribute('aria-current','page');
  else link.removeAttribute('aria-current');
 }
}
function nativeProfileFallback(id,section){
 const fragment=section==='work'?'work':['claim','sources','method','questions','observations','financing'].includes(section)?'sources':'';
 const label=fragment==='work'?'Read the plain paid work section':fragment==='sources'?'Read the plain company sources':'Read the plain company page';
 return `<a data-profile-native-fallback href="/company/${encodeURIComponent(id)}/${fragment?'#'+fragment:''}">${label}</a>`;
}
function loadingProfile(id,section){
 document.title=companies[id].name+' · ScienceToStartup';
 pendingView('profile');
 const target=$('profile-view');
 target.setAttribute('aria-busy','true');
 target.innerHTML=`<div class="profile-v2" data-profile-company="${attr(id)}" data-profile-loading>${profileIntroductionHTML(id)}<div data-profile-loading-content><p role="status">Loading the sourced profile…</p><p>${nativeProfileFallback(id,section)}</p></div></div>`;
}
function afterProfileIntroductionPaint(){
 // Let the browser present the sourced introduction before starting evidence
 // requests. Layout and compositor presentation can span successive frames.
 if(typeof requestAnimationFrame!=='function'||document.visibilityState==='hidden')return Promise.resolve();
 return new Promise(resolve=>{
  let frame=0,timer=0,framesRemaining=4;
  const done=()=>{clearTimeout(timer);if(frame&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(frame);resolve();};
  const nextFrame=()=>{
   if(--framesRemaining)frame=requestAnimationFrame(nextFrame);
   else done();
  };
  timer=setTimeout(done,100);
  frame=requestAnimationFrame(nextFrame);
 });
}
function evidenceFailure(error){
 return /identity|integrity|Stale/.test(error.message)?'stale-evidence':/timed out/.test(error.message)?'evidence-timeout':'evidence-request';
}
function failedProfile(id,section,error){
 const target=$('profile-view');target.removeAttribute('aria-busy');
 const pending=target.querySelector('[data-profile-loading-content]');
 const notice=`<section class="availability-notice" data-profile-recovery><div role="alert"><h2>Evidence for ${esc(companies[id].name)} could not load.</h2></div><p><button type="button" data-retry-company>Try again</button> ${nativeProfileFallback(id,section)}</p></section>`;
 if(pending){pending.parentElement.removeAttribute('data-profile-loading');pending.outerHTML=notice;}
 else target.innerHTML=`<div class="profile-v2" data-profile-company="${attr(id)}">${profileIntroductionHTML(id)}${notice}</div>`;
 presentationState('failed',evidenceFailure(error));
}
function pendingComparison(selection,error){
 pendingView('compare');
 renderComparisonScope('compare');
 compareTitle(selection.ids);
 syncComparisonPreset();syncCompareAdd();
 const names=listText(selection.ids.map(id=>companies[id].name)),target=$('compare-content');
 const notice=compareNoticeHTML(compareRouteNotice(selection));
 const nativeLinks=selection.ids.map(id=>`<li><a href="/company/${encodeURIComponent(id)}/">Read the ${esc(companies[id].name)} profile</a></li>`).join('');
 const status=error?`Evidence for ${names} could not load.`:`Loading evidence for ${names}…`;
 if(error)target.removeAttribute('aria-busy');else target.setAttribute('aria-busy','true');
 $('compare-status').textContent=status;
 target.innerHTML=notice+`<section class="availability-notice"><h2>${esc(status)}</h2>${error?'<p><button type="button" data-retry-compare>Try again</button></p>':''}<ul>${nativeLinks}</ul></section>`;
 if(error)presentationState('failed',evidenceFailure(error));
}
function afterRouteRetry(event,generation){
 if(!['company-retry','compare-retry'].includes(event?.type))return;
 const hash=location.hash;
 queueMicrotask(()=>{
  if(generation!==navigationGeneration||location.hash!==hash||document.activeElement!==document.body)return;
  if(event.type==='company-retry'&&routeParts()[2]!=='claim')focusRouteDestination(hash);
  if(event.type==='compare-retry')focusRouteDestination(hash);
 });
}
route=function(event){
 cancelShortlistScroll();
 restoreSearchRouteControls();
 if(typeof cancelWorkRouteWrite==='function')cancelWorkRouteWrite();
 if(typeof entryScrollTimer!=='undefined')clearTimeout(entryScrollTimer);
 const generation=++navigationGeneration,hash=location.hash,parts=routeParts();
 detailController?.abort();detailController=null;
 $('profile-view').removeAttribute('aria-busy');
 $('compare-content').removeAttribute('aria-busy');
 if($('app-failure'))$('app-failure').hidden=true;
 const view=parts[0],company=view==='company'?profileRouteCompany(parts[1]):'';
 const archive=view==='method'||VIEW_ANCHORS[view]==='method';
 const comparison=view==='compare'?compareRouteSelection(hash):null;
 const correction=view==='corrections'?exploreCorrectionTarget(hash):null;
 const correctionCompany=correction&&!exploreCorrectionClaim(correction)?correction.company:'';
 const overview=view===''||view==='market'||VIEW_ANCHORS[view]==='market'||!['companies','work','compare','method','company',...Object.keys(VIEW_ANCHORS)].includes(view);
 const workCriteria=view==='work'?workCriteriaForRoute(hash,routeTraversal):null;
 const needsSearch=Boolean(workCriteria&&searchContextPending(workCriteria.q));
 const needsWork=exploreWorkPending()&&Boolean(workCriteria);
 const workListingLoad=needsWork&&Boolean(workCriteria)&&!needsSearch;
 const ids=company?[company]:correctionCompany?[correctionCompany]:comparison?.ids||[];
 const cacheKey=archive?'__archive':overview?'__overview':null;
 const cached=(!cacheKey||detailCache.has(cacheKey))&&ids.every(id=>detailCache.has(id));
 if(cached&&!needsSearch&&!needsWork){
  for(const id of [...(cacheKey?[cacheKey]:[]),...ids])installResearchContext(detailCache.get(id));
  const result=synchronousRoute.call(this,event);presentationState('ready');afterRouteRetry(event,generation);window.APP_ROUTE_READY=Promise.resolve(result);return result;
 }
 const closedDialog=event?.type==='hashchange'&&['company-dialog','evidence-dialog'].some(id=>$(id).open);
 if(event?.type==='hashchange')for(const id of ['company-dialog','evidence-dialog'])if($(id).open)$(id).close();
 const controller=detailController=new AbortController();presentationState('loading');
 if(company)loadingProfile(company,parts[2]);
 if(comparison){
  // Prepare the selection before controls can change it, and normalize only
  // after the async route has settled so the request's hash guard stays valid.
  const selection=comparison.ids;
  if(selection.join('|')!==state.selected.join('|')){state.selected=selection;state.mobileCompare=0;syncSelection();renderTray();}
  pendingComparison(comparison);
 }
 if(needsSearch||workListingLoad){applyWorkCriteria(workCriteria);pendingWorkSearchRoute(false,workListingLoad);}
 const complete=async()=>{
  if(company){await afterProfileIntroductionPaint();if(generation!==navigationGeneration||location.hash!==hash||controller.signal.aborted)return;}
  let section=cacheKey&&detailCache.get(cacheKey);
  if(cacheKey&&!section){
   const descriptor=archive?presentationIdentity.archive:presentationIdentity.overview;
   section=Promise.all([fetchPresentation(descriptor,null,controller.signal),ensureHealthModule()]).then(([payload])=>payload);
  }
  const work=needsSearch?window.ensureSearchContext():needsWork?ensureExploreWork():null;
  const [sectionContext,,...payloads]=await Promise.all([section,work,...ids.map(id=>{
   const pending=companyContext(id,controller.signal);
   return correctionCompany?pending.catch(()=>null):pending;
  })]);
  if(generation!==navigationGeneration||location.hash!==hash)return;
  if(sectionContext){installResearchContext(sectionContext);detailCache.set(cacheKey,sectionContext);}
  for(const payload of payloads)if(payload)installResearchContext(payload);
  restoreSearchRouteControls();
  $('profile-view').removeAttribute('aria-busy');
  $('compare-content').removeAttribute('aria-busy');
  const routeEvent=closedDialog?{type:event.type,newURL:event.newURL,closedDialog}:event;
  synchronousRoute.call(this,routeEvent);presentationState('ready');afterRouteRetry(event,generation);
 };
 window.APP_ROUTE_READY=complete().catch(error=>{
  if(error.name==='AbortError'||generation!==navigationGeneration||location.hash!==hash)return;
  restoreSearchRouteControls();
  if(company)failedProfile(company,parts[2],error);
  else if(comparison)pendingComparison(comparison,error);
  else if(needsSearch||workListingLoad){pendingWorkSearchRoute(true,workListingLoad);presentationState('failed',workListingLoad?'work-request':'search-request');}
  else{
   const active=document.activeElement;
   const moveFocus=active?.closest('main>.view')||(event?.type==='hashchange'&&active===document.body);
   pendingView('');
   presentationState('failed',evidenceFailure(error));
   $('app-failure-title').textContent=archive?'Method data could not load.'
    :overview?'Market data could not load.':'The interactive guide could not load.';
   $('app-failure').hidden=false;
   if(moveFocus)$('app-reload').focus();
  }
  if(event?.type==='company-retry'||event?.type==='compare-retry')document.querySelector('[data-retry-company],[data-retry-compare]')?.focus();
 });
 return window.APP_ROUTE_READY;
};
document.addEventListener('click',event=>{
 const button=event.target.closest?.('[data-retry-company],[data-retry-compare],[data-retry-search]');
 if(button)route({type:button.hasAttribute('data-retry-company')?'company-retry':button.hasAttribute('data-retry-compare')?'compare-retry':'search-retry'});
});
const synchronousEvidence=showEvidence,synchronousCompanyStory=openCompanyStory;
let evidenceGeneration=0,storyGeneration=0,retryEvidence=null;
showEvidence=function(id,...args){
 const hash=location.hash,parts=routeParts(hash),bookmark=parts[0]==='company'&&parts[2]==='claim';
 const company=bookmark?profileRouteCompany(parts[1]):claims[id]?.company_id||String(id).split('.')[0];
 const generation=++evidenceGeneration,navigation=navigationGeneration;
 if(!Object.hasOwn(presentationIdentity.companyDetails,company))return synchronousEvidence.call(this,id,...args);
 const dialog=$('evidence-dialog');
 const current=()=>generation===evidenceGeneration&&location.hash===hash&&navigation===navigationGeneration;
 const fallback=nativeProfileFallback(company,'claim');
 const present=(text,pending=false,retry=false)=>{
  if(!dialog.open){evidenceReturnFocus=document.activeElement;evidenceReturnHash='';evidenceRecordHash='';}
  if(pending)dialog.setAttribute('aria-busy','true');else dialog.removeAttribute('aria-busy');
  $('evidence-content').innerHTML=`<p id="evidence-statement" role="${pending?'status':'alert'}">${esc(text)}</p><p>${retry?'<button type="button" data-retry-evidence>Try again</button> ':''}${fallback}</p>`;
  if(!dialog.open)dialog.showModal();
  $('close-evidence').focus({preventScroll:true});
 };
 const display=()=>{
  dialog.removeAttribute('aria-busy');
  if(claims[id]?.company_id!==company){present('This source record could not be found for '+companies[company].name+'.');return;}
  synchronousEvidence.call(this,id,...args);
 };
 retryEvidence=null;
 if(detailCache.has(company)){
  if(!window.COMPANY_CONTEXTS_READY.has(company))installResearchContext(detailCache.get(company));
  return display();
 }
 present('Loading source evidence for '+companies[company].name+'…',true);
 companyContext(company).then(payload=>{
  if(!current())return;
  installResearchContext(payload);display();
 }).catch(()=>{
  if(!current())return;
  retryEvidence=()=>showEvidence(id,...args);
  present('The source evidence for '+companies[company].name+' could not load.',false,true);
 });
};
$('evidence-dialog').addEventListener('click',event=>{if(event.target.closest?.('[data-retry-evidence]'))retryEvidence?.();});
$('evidence-dialog').addEventListener('close',()=>{evidenceGeneration++;retryEvidence=null;$('evidence-dialog').removeAttribute('aria-busy');});
openCompanyStory=function(id){const generation=++storyGeneration,navigation=navigationGeneration,hash=location.hash;companyContext(id).then(payload=>{if(generation!==storyGeneration||navigation!==navigationGeneration||location.hash!==hash)return;installResearchContext(payload);synchronousCompanyStory.call(this,id);}).catch(()=>{if(generation===storyGeneration&&navigation===navigationGeneration)location.hash='#company/'+encodeURIComponent(id);});};
const summaryRenderStory=renderStory;
renderStory=function(){const result=summaryRenderStory.apply(this,arguments);if($('source-count'))$('source-count').textContent=presentationIdentity.statistics.sources;return result;};
