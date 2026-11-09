/* Fetch only the initial research route while the classic app is loading.
   The route owner still verifies bytes, release identity and navigation. */
(()=>{
 const summary=window.PRESENTATION_PRELOAD_CONFIG||window.SUMMARY_INDEX;delete window.PRESENTATION_PRELOAD_CONFIG;if(!summary)return;
 let parts;try{parts=location.hash.slice(1).split('?')[0].split('/').map(decodeURIComponent);}catch{return;}
 const view=String(parts[0]||'').toLowerCase(),aliases=summary.aliases||window.RESEARCH_ALIASES||{};
 const company=String(parts[1]||'').toLowerCase(),id=Object.hasOwn(aliases,company)?aliases[company]:company;
 const archive=['method','about','labels','corrections','coverage','downloads'].includes(view);
 const overview=['','market','venture'].includes(view)||!['company','companies','work','compare',...['method','about','labels','corrections','coverage','downloads']].includes(view);
 const descriptor=view==='company'?(Object.hasOwn(summary.companyDetails,id)?summary.companyDetails[id]:null):archive?summary.archive:overview?summary.overview:null;
 if(!descriptor)return;
 const health=summary.modules?.businessHealth;
 if(health){const link=document.createElement('link');link.rel='preload';link.as='script';link.href=health.href;link.integrity=health.integrity;link.crossOrigin='anonymous';document.head.append(link);}
 const controller=new AbortController();let timedOut=false;
 const deadline=setTimeout(()=>{timedOut=true;controller.abort();},15000);
 const promise=fetch(descriptor.href,{signal:controller.signal,cache:'no-cache'}).then(response=>{
  if(!response.ok)throw new Error('Evidence request failed ('+response.status+')');return response.arrayBuffer();
 }).then(bytes=>({bytes}),error=>({error:timedOut?new Error('Evidence request timed out'):error})).finally(()=>clearTimeout(deadline));
 window.PRESENTATION_PREFETCH={href:descriptor.href,sha256:descriptor.sha256,buildId:summary.buildId,controller,promise};
})();
