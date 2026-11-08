/* Evergreen links remain usable if this optional enhancement cannot load. */
(()=>{
 const node=document.getElementById('home-config');if(!node)return;
 const config=JSON.parse(node.textContent),slot=document.getElementById('home-work-example');
 const evergreen=slot?.innerHTML;
 const refresh=()=>{
  if(!slot)return;const now=Date.now(),candidate=config.candidates.find(c=>now>=Date.parse(c.reviewedAt)&&now<Date.parse(c.expiresAt));
  const template=candidate&&document.getElementById(candidate.templateId);
  if(template){if(slot.dataset.routeId!==candidate.routeId){slot.replaceChildren(template.content.cloneNode(true));slot.dataset.routeId=candidate.routeId;}}
  else if(slot.dataset.routeId){slot.innerHTML=evergreen;delete slot.dataset.routeId;}
 };
 refresh();setInterval(refresh,60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
 let loading=false;
 document.getElementById('home-search-open')?.addEventListener('click',event=>{
  if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  event.preventDefault();if(window.openHomeSearch){window.openHomeSearch();return;}if(loading)return;loading=true;
  const script=document.createElement('script');script.src='/home-search.js';script.onload=()=>{loading=false;window.openHomeSearch?.();};script.onerror=()=>{loading=false;location.href='/companies/';};document.head.append(script);
 });
 document.addEventListener('keydown',event=>{if((event.key==='/'&&!event.metaKey&&!event.ctrlKey&&!event.altKey||event.key.toLowerCase()==='k'&&(event.metaKey||event.ctrlKey))&&!event.target.closest?.('input,textarea,select,[contenteditable=true]')){event.preventDefault();document.getElementById('home-search-open')?.click();}});
})();
