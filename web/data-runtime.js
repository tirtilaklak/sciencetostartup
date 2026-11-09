/* One asynchronous route owner. The classic renderers receive only validated contexts. */
window.APP_BUILD_ID=/* APP_BUILD_ID */null;
const presentationIdentity=window.SUMMARY_INDEX;
if(!presentationIdentity||presentationIdentity.schemaVersion!=='1.0.0'||presentationIdentity.buildId!==window.APP_BUILD_ID||presentationIdentity.datasetVersion!==DATA.dataset_version||document.documentElement.dataset.buildId!==window.APP_BUILD_ID)throw new Error('Presentation release identity mismatch');
const detailCache=new Map();
window.COMPANY_CONTEXTS_READY=new Set();
let searchContextPromise=null,searchRouteView='',searchDisabledControls=[];
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
async function fetchPresentation(descriptor,companyId,signal){
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
  return validatePresentation(JSON.parse(new TextDecoder().decode(bytes)),companyId);
 }catch(error){if(timedOut)throw new Error('Evidence request timed out');throw error;}
 finally{clearTimeout(deadline);signal?.removeEventListener('abort',cancel);}
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
 searchContextPromise=fetchPresentation(presentationIdentity.fullSearch).then(payload=>{
  for(const key of ['companySearch','profileProducts','workSearch'])if(!payload[key]||typeof payload[key]!=='object')throw new Error('Invalid search index');
  if(!Array.isArray(payload.editorialReadouts))throw new Error('Invalid export readouts');
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
 if(searchRouteView){$(searchRouteView==='work'?'work-cards':'company-cards')?.removeAttribute('aria-busy');searchRouteView='';}
}
function pendingSearchRoute(view,failed=false){
 document.documentElement.removeAttribute('data-route');
 for(const section of document.querySelectorAll('main>.view'))section.hidden=section.id!==view+'-view';
 const section=$(view+'-view'),cards=$(view==='work'?'work-cards':'company-cards'),count=$(view==='work'?'work-count':'result-count');
 section.hidden=false;searchRouteView=view;
 if(!failed){searchDisabledControls=[...section.querySelectorAll('input,select,button')].map(control=>[control,control.disabled]);for(const [control]of searchDisabledControls)control.disabled=true;cards?.setAttribute('aria-busy','true');}
 const label=failed?'Search could not load. Your query is preserved.':'Loading the search index…';
 if(count)count.textContent=label;
 if(cards)cards.innerHTML='<p role="'+(failed?'alert':'status')+'">'+label+' '+(failed?'<button type="button" data-retry-search>Try again</button> ':'')+'<a href="/'+(view==='work'?'work':'companies')+'/">Read the plain '+(view==='work'?'work':'company')+' page</a></p>';
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
  window.SOURCE_UPDATES={...before,...next,updates:merge(before.updates,next.updates),evidence_context:{...before.evidence_context,...next.evidence_context,corrections:merge(before.evidence_context?.corrections,next.evidence_context?.corrections)}};
 }
 if(payload.workRoutes){
  const rows=Array.isArray(payload.workRoutes)?payload.workRoutes:payload.workRoutes.routes;
  const records=new Map(workRouteRows().map(row=>[row.id,row]));for(const row of rows||[])records.set(row.id,row);
  window.WORK_ROUTES={...window.WORK_ROUTES,routes:[...records.values()]};
 }
 if(payload.businessHealth){
  const merge=(before,after,key='id')=>[...new Map([...(before||[]),...(after||[])].map(row=>[row[key],row])).values()];
  const before=window.BUSINESS_HEALTH||{},next=payload.businessHealth;
  window.BUSINESS_HEALTH={...before,...next,observations:merge(before.observations,next.observations),fresh_claims:merge(before.fresh_claims,next.fresh_claims),sources:merge(before.sources,next.sources),private_company_review:merge(before.private_company_review,next.private_company_review,'company_id'),source_checks:{...before.source_checks,...next.source_checks,entries:merge(before.source_checks?.entries,next.source_checks?.entries,'source_id')}};
  window.BusinessHealth?.refreshBundle();
 }
 if(payload.companyId)window.COMPANY_CONTEXTS_READY.add(payload.companyId);
 if(typeof refreshResearchIndexes==='function')refreshResearchIndexes();
}
async function companyContext(id,signal){
 const descriptor=presentationIdentity.companyDetails[id];if(!descriptor)throw new Error('Company record is missing');
 if(detailCache.has(id))return detailCache.get(id);
 const [payload]=await Promise.all([fetchPresentation(descriptor,id,signal),ensureHealthModule()]);detailCache.set(id,payload);return payload;
}
function loadingProfile(id){
 document.documentElement.removeAttribute('data-route');
 for(const view of document.querySelectorAll('main>.view'))view.hidden=view.id!=='profile-view';
 const target=$('profile-view');target.hidden=false;target.setAttribute('aria-busy','true');
 target.innerHTML=`<div class="page-heading" role="status"><p class="eyebrow">Company evidence</p><h1>${attr(companies[id]?.name||'Loading research')}</h1><p>Loading the sourced profile…</p><p><a href="/company/${encodeURIComponent(id)}/">Read the plain company page</a></p></div>`;
}
function failedProfile(id,error){
 const target=$('profile-view');target.removeAttribute('aria-busy');
 target.innerHTML=`<section class="availability-notice" role="alert"><h1>This company’s evidence could not load.</h1><p>Your connection or an older cached file may be responsible. The record has not been removed.</p><p><button type="button" data-retry-company>Try again</button> <a href="/company/${encodeURIComponent(id)}/">Read the plain company page</a> <a href="#companies">Browse companies</a></p></section>`;
 presentationState('failed',/identity|integrity|Stale/.test(error.message)?'stale-evidence':/timed out/.test(error.message)?'evidence-timeout':'evidence-request');
 console.warn('[ScienceToStartup]',{buildId:window.APP_BUILD_ID,state:'failed',reason:document.documentElement.dataset.viewReason});
}
route=function(event){
 restoreSearchRouteControls();
 if(typeof cancelWorkRouteWrite==='function')cancelWorkRouteWrite();
 if(typeof entryScrollTimer!=='undefined')clearTimeout(entryScrollTimer);
 const generation=++navigationGeneration,hash=location.hash,parts=routeParts();
 if(event?.type==='hashchange')for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
 detailController?.abort();detailController=null;
 const company=String(parts[0]).toLowerCase()==='company'?profileRouteCompany(parts[1]):'';
 const view=String(parts[0]).toLowerCase(),archive=view==='method'||VIEW_ANCHORS[view]==='method';
 const comparison=view==='compare';
 const overview=['','market','venture'].includes(view)||!['companies','work','compare','method','company',...Object.keys(VIEW_ANCHORS)].includes(view);
 const needsSearch=!window.SEARCH_INDEX&&(view==='work'&&Boolean(workCriteriaFromHash(hash).q)||view==='companies'&&Boolean(state.query));
 if(!company&&!archive&&!comparison&&!overview&&!needsSearch){presentationState('ready');const result=synchronousRoute.apply(this,arguments);window.APP_ROUTE_READY=Promise.resolve(result);return result;}
 const ids=company?[company]:(state.selected.length?state.selected:['taskus','appen','scale_ai']);
 const cacheKey=archive?'__archive':overview?'__overview':null;
 const cached=cacheKey?detailCache.get(cacheKey):company||comparison?ids.every(id=>detailCache.has(id)):true;
 if(cached&&!needsSearch){
  for(const payload of cacheKey?[cached]:company||comparison?ids.map(id=>detailCache.get(id)):[])installResearchContext(payload);
  const result=synchronousRoute.apply(this,arguments);presentationState('ready');window.APP_ROUTE_READY=Promise.resolve(result);return result;
 }
 const controller=detailController=new AbortController();presentationState('loading');
 if(company)loadingProfile(company);
 if(needsSearch){if(view==='work')applyWorkCriteria(workCriteriaFromHash(hash));pendingSearchRoute(view);}
 const complete=async()=>{
  if(needsSearch)await window.ensureSearchContext();
  let payloads=[];
  if(cacheKey){const [payload]=await Promise.all([fetchPresentation(archive?presentationIdentity.archive:presentationIdentity.overview,null,controller.signal),ensureHealthModule()]);payloads=[payload];}
  else if(company||comparison)payloads=await Promise.all(ids.map(id=>companyContext(id,controller.signal)));
  if(generation!==navigationGeneration||location.hash!==hash)return;
  for(const payload of payloads)installResearchContext(payload);
  if(cacheKey)detailCache.set(cacheKey,payloads[0]);
  restoreSearchRouteControls();
  $('profile-view').removeAttribute('aria-busy');
  synchronousRoute.call(this,event);presentationState('ready');
 };
 window.APP_ROUTE_READY=complete().catch(error=>{if(error.name==='AbortError'||generation!==navigationGeneration)return;restoreSearchRouteControls();if(company)failedProfile(company,error);else if(needsSearch){pendingSearchRoute(view,true);presentationState('failed','search-request');}else{presentationState('failed','evidence-request');const failure=$('app-failure');failure.hidden=false;document.documentElement.removeAttribute('data-route');}});
 return window.APP_ROUTE_READY;
};
document.addEventListener('click',event=>{if(event.target.closest?.('[data-retry-company],[data-retry-search]'))route();});
const synchronousEvidence=showEvidence,synchronousCompanyStory=openCompanyStory;
let evidenceGeneration=0,storyGeneration=0;
showEvidence=function(id,...args){
 const company=claims[id]?.company_id||String(id).split('.')[0],generation=++evidenceGeneration,hash=location.hash,navigation=navigationGeneration;
 if(!presentationIdentity.companyDetails[company])return synchronousEvidence.call(this,id,...args);
 const dialog=$('evidence-dialog');
 if(!detailCache.has(company)){
  if(!dialog.open){evidenceReturnFocus=document.activeElement;evidenceReturnHash='';evidenceRecordHash='';}
  $('evidence-content').innerHTML='<p id="evidence-statement" role="status">Loading the original source evidence…</p><p><a href="/company/'+encodeURIComponent(company)+'/#sources">Read the plain company page</a></p>';
  dialog.setAttribute('aria-busy','true');if(!dialog.open)dialog.showModal();$('close-evidence').focus({preventScroll:true});
 }
 companyContext(company).then(payload=>{if(generation!==evidenceGeneration||location.hash!==hash||navigation!==navigationGeneration)return;installResearchContext(payload);dialog.removeAttribute('aria-busy');if(!claims[id])throw new Error('Source record not found');synchronousEvidence.call(this,id,...args);}).catch(error=>{
  if(generation!==evidenceGeneration||navigation!==navigationGeneration)return;
  dialog.removeAttribute('aria-busy');$('evidence-content').innerHTML='<p id="evidence-statement" role="alert">'+(error.message==='Source record not found'?'This source record could not be found.':'The source evidence could not load.')+' <a href="/company/'+encodeURIComponent(company)+'/">Read the plain company page</a> or close this dialog and try the source again.</p>';if(!dialog.open)dialog.showModal();
 });
};
$('evidence-dialog').addEventListener('close',()=>{evidenceGeneration++;$('evidence-dialog').removeAttribute('aria-busy');});
openCompanyStory=function(id){const generation=++storyGeneration,navigation=navigationGeneration,hash=location.hash;companyContext(id).then(payload=>{if(generation!==storyGeneration||navigation!==navigationGeneration||location.hash!==hash)return;installResearchContext(payload);synchronousCompanyStory.call(this,id);}).catch(()=>{if(generation===storyGeneration&&navigation===navigationGeneration)location.hash='#company/'+encodeURIComponent(id);});};
const summaryRenderStory=renderStory;
renderStory=function(){const result=summaryRenderStory.apply(this,arguments);if($('source-count'))$('source-count').textContent=presentationIdentity.statistics.sources;return result;};
