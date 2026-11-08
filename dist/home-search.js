/* Loaded only when homepage Search is invoked; no application or archive download. */
(()=>{
 const $=id=>document.getElementById(id),dialog=$('home-search'),input=$('home-search-input'),results=$('home-search-results'),message=$('home-search-message');
 const config=JSON.parse($('home-config').textContent);let entries=null,pending=null,active=-1;
 const text=value=>String(value??'').normalize('NFKD').replace(/\p{M}+/gu,'').toLowerCase();
 const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function load(){
  if(entries)return entries;if(pending)return pending;
  message.textContent='Loading the search index…';
  pending=fetch(config.search.href).then(async response=>{
   if(!response.ok)throw new Error('Search unavailable');const data=await response.json();
   if(data.buildId!==config.buildId||data.editorialReleaseId!==config.editorialReleaseId)throw new Error('Search release mismatch');
   entries=data.entries;return entries;
  }).finally(()=>{pending=null;});return pending;
 }
 function render(){
  const raw=input.value.trim(),q=text(raw),tokens=q.split(/\s+/u).filter(Boolean);
  const matches=(entries||[]).filter(row=>tokens.every(token=>text([row.name,row.summary,row.group,...row.products].join(' ')).includes(token))).slice(0,7);
  const work='/explore/#work'+(raw?'?'+new URLSearchParams({q:raw}):'');
  results.innerHTML=matches.map((row,i)=>`<a id="home-result-${i}" class="site-search-option" role="option" aria-selected="false" href="${escape(row.href)}"><strong>${escape(row.name)}</strong><span>${escape(row.summary)}</span></a>`).join('')+`<a class="site-search-option" role="option" aria-selected="false" href="${escape(work)}"><strong>${escape(raw?'Find paid work matching “'+raw+'”':'Browse paid work')}</strong><span>Public listings, expert networks and requirements</span></a>`;
  results.hidden=false;active=-1;input.removeAttribute('aria-activedescendant');input.setAttribute('aria-expanded','true');
  message.textContent=raw?(matches.length?matches.length+' company matches. Paid work uses its own listing filters.':'No recorded company matches. You can search paid work or browse all companies.'):'Search companies, their offerings, or continue to paid work.';
  $('home-search-status').textContent=message.textContent;
 }
 window.openHomeSearch=async()=>{if(!dialog.open)dialog.showModal();$('home-search-open').setAttribute('aria-expanded','true');input.focus();try{await load();render();}catch(error){message.innerHTML='Search could not load. <a href="/companies/">Browse companies</a> or <a href="/work/">browse paid work</a>.';}};
 $('home-search-close').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});dialog.addEventListener('close',()=>{$('home-search-open').setAttribute('aria-expanded','false');$('home-search-open').focus();});
 input.addEventListener('input',()=>{if(entries)render();});
 input.addEventListener('keydown',event=>{
  const options=[...results.querySelectorAll('[role=option]')];if(!options.length)return;
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();active=event.key==='Home'?0:event.key==='End'?options.length-1:(active+(event.key==='ArrowDown'?1:options.length-1))%options.length;options.forEach((node,i)=>{node.id='home-result-'+i;node.setAttribute('aria-selected',String(i===active));});input.setAttribute('aria-activedescendant',options[active].id);options[active].scrollIntoView({block:'nearest'});}
  if(event.key==='Enter'){event.preventDefault();options[Math.max(active,0)].click();}
 });
})();
