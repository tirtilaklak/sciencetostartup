/* Site menus, global search and footer. Loaded after source-updates.js and before initialize(). */

// Global search over companies, business groups, products, paid work listings and pages.
// The index is built from data already in the page on first use, never at load.
const SITE_SEARCH_GROUPS={company:['Companies',5],group:['Business groups',2],work:['Paid work',5],product:['Products',3],page:['Pages',3]};
const SITE_SEARCH_SUGGESTED=['scale_ai','mercor','surge_ai','labelbox'];
let siteSearchEntries=null,siteSearchItems=[],siteSearchActive=-1,siteSearchStatusTimer=0;
const siteSearchFold=v=>String(v??'').normalize('NFKD').replace(/\p{M}+/gu,'').toLowerCase();
const siteSearchWords=v=>siteSearchFold(Array.isArray(v)?v.join(' '):v).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
// "Outlier (contributor brand)" is matched as "Outlier"; the note stays with it in the result.
function siteSearchAlias(value){const m=String(value).match(/^(.+?)\s*\((.+)\)$/);return m?{name:m[1],note:m[2]}:{name:String(value),note:''};}
function siteSearchTopRate(label){const m=String(label||'').match(/\$\s?([\d,.]+)(?:\s*[–-]\s*\$?([\d,.]+))?\+?\s*\/\s*(?:approved\s+)?hour/i);return m?Number((m[2]||m[1]).replace(/,/g,''))||0:0;}
function siteSearchPages(){
 const listings=typeof workRouteRows==='function'?workRouteRows().filter(route=>typeof w4Bucket!=='function'||['contract','jobs'].includes(w4Bucket(route))).length:0;
 return [
  ['market','Overview','The front page, with the main figures and business groups','home start charts market'],
  ['companies','Companies',`All ${DATA.companies.length} companies, with search and filters`,'index directory list organizations organisations firms startups'],
  ['work','Paid work',`${listings} open listings, with pay and location`,'jobs gigs hiring careers contract contractor freelance hourly pay earn'],
  ['compare','Compare','Put up to three companies side by side','versus vs comparison'],
  ['method','Method','How each figure is checked and graded','methodology sources evidence research'],
  ['labels','What the labels mean','Evidence labels and confidence grades','grades confidence rubric'],
  ['about','About the publisher','Who publishes this guide, and the disclosure','contact publisher musa ozdem email disclosure removal privacy'],
  ['corrections','Request a correction','Tell us when a figure or listing is wrong','corrections error mistake wrong fix report'],
  ['downloads','Download the data','JSON, CSV and SQLite files','downloads csv json sqlite dataset export'],
  ['venture','The publisher’s proposed AI lab','The publisher’s proposal, separate from the research','venture neolab investor pitch proposal']
 ].map(([id,name,meta,keys])=>({type:'page',id,name,meta,keys:keys.split(' '),href:'#'+id}));
}
function siteSearchIndex(){
 if(siteSearchEntries)return siteSearchEntries;
 const rows=[],aliasesOf=c=>(c.aliases||[]).map(siteSearchAlias);
 for(const c of DATA.companies){const key=modelGroup(c.id);rows.push({type:'company',id:c.id,company:c.id,name:c.name,aliases:aliasesOf(c),ctx:[groupLabel(key),key],text:[c.description,modelFor(c.id),...(c.categories||[])],meta:groupLabel(key),href:'#company/'+c.id});}
 for(const [key,ids] of Object.entries(MODEL_GROUPS))rows.push({type:'group',id:groupSlug(key),name:groupLabel(key),aliases:[{name:key,note:''}],meta:`${ids.length} ${ids.length===1?'company':'companies'}`,href:'#companies/'+groupSlug(key)});
 for(const c of DATA.companies)for(const p of typeof profileProducts==='function'?profileProducts(c.id):[])rows.push({type:'product',id:c.id+'/'+p.name,company:c.id,product:p.name,name:p.name,aliases:[...(p.aliases||[]),typeof publicOfferingName==='function'?publicOfferingName(p.name):''].filter(Boolean).map(siteSearchAlias),ctx:[c.name],text:[p.description,p.kind],meta:'From '+c.name,href:`#company/${c.id}/products`});
 for(const r of typeof workRouteRows==='function'?workRouteRows():[]){const c=companies[r.company_id];if(!c)continue;
  const pay=typeof w4Pay==='function'?w4Pay(r):r.pay_label,place=typeof w4Location==='function'?w4Location(r):r.geography,status=typeof w4Status==='function'?w4Status(r):'';
  rows.push({type:'work',id:r.id,company:c.id,name:r.role,ctx:[c.name,...aliasesOf(c).map(a=>a.name),r.group,r.geography,r.pay_label],text:[r.summary,r.hours,...(r.requirements||[])],meta:[c.name,pay,place].filter(Boolean).join(' · '),badge:status,order:WORK_ROUTE_ORDER[r.status]??10,rate:siteSearchTopRate(r.pay_label),href:`#company/${c.id}/work`});}
 rows.push(...siteSearchPages());
 return siteSearchEntries=rows.map(row=>{
  const name=siteSearchWords(row.name),aliases=(row.aliases||[]).map(a=>siteSearchWords(a.name)).filter(w=>w.length),keys=siteSearchWords(row.keys||[]),core=[...name,...aliases.flat(),...keys,...siteSearchWords(row.ctx||[])];
  return Object.assign(row,{nameKey:name.join(' '),nameWords:name,aliasKeys:aliases.map(w=>w.join(' ')),labelWords:[...name,...aliases.flat(),...keys],keyWords:keys,coreWords:core,allWords:[...core,...siteSearchWords(row.text||[])]});
 });
}
// Lower is better: 0 exact name or alias, 1 name starts with the query, 2 an alias or page keyword starts with it,
// 3 every word starts a word of the name, 4 of the name, aliases or context, 5 of anything in the entry.
function siteSearchRank(e,tokens,key){
 const has=words=>tokens.every(t=>words.some(w=>w.startsWith(t)));
 if(e.nameKey===key||e.aliasKeys.includes(key))return 0;
 if(e.nameKey.startsWith(key))return 1;
 if(e.aliasKeys.some(k=>k.startsWith(key))||(e.keyWords.length&&has(e.keyWords)))return 2;
 if(has(e.nameWords))return 3;
 if(has(e.coreWords))return 4;
 return has(e.allWords)?5:-1;
}
const siteSearchStem=t=>t.length>3&&t.endsWith('s')?t.replace(/ies$/,'y').replace(/s$/,''):t;
function siteSearchDistance(a,b){const d=[...Array(a.length+1)].map((_,i)=>[i]);for(let j=1;j<=b.length;j++)d[0][j]=j;for(let i=1;i<=a.length;i++)for(let j=1;j<=b.length;j++){d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1));if(i>1&&j>1&&a[i-1]===b[j-2]&&a[i-2]===b[j-1])d[i][j]=Math.min(d[i][j],d[i-2][j-2]+1);}return d[a.length][b.length];}
// Typo tolerance, used only when nothing matches exactly: names and aliases, same first letter,
// one slip in a short word and two in a long one.
function siteSearchNear(t,words){if(t.length<3)return words.some(w=>w.startsWith(t));const max=t.length>6?2:1;return words.some(w=>w[0]===t[0]&&[t.length-1,t.length,t.length+1].some(n=>siteSearchDistance(t,w.slice(0,n))<=max));}
// siteSearch('outlier') -> [{type:'company',id:'scale_ai',...}, ...]: results in display order, grouped by type.
function siteSearch(query,opts={}){
 const o=typeof opts==='number'?{limit:opts}:opts||{},tokens=siteSearchWords(query);
 if(!tokens.length)return [];
 const key=tokens.join(' '),stems=tokens.map(siteSearchStem),entries=siteSearchIndex().filter(e=>!o.types||o.types.includes(e.type));
 // One or two letters match names, aliases and context only; descriptions join from three letters.
 const most=key.length<3?4:5;
 let hits=entries.map(e=>{let rank=siteSearchRank(e,tokens,key);if(rank<0&&stems.join(' ')!==key&&siteSearchRank(e,stems,stems.join(' '))>=0)rank=5;return [rank,e];}).filter(([rank])=>rank>=0&&rank<=most);
 if(!hits.length)hits=entries.filter(e=>tokens.every(t=>siteSearchNear(t,e.labelWords))).map(e=>[6,e]);
 // Groups follow their best match. On a tie the default order holds, except that listings lead
 // when only descriptions match (skill words such as "python" are usually a worker's search).
 const groups=Object.keys(SITE_SEARCH_GROUPS).map((type,order)=>{
  const rows=hits.filter(([,e])=>e.type===type).sort(([ra,a],[rb,b])=>ra-rb||(type==='work'?a.order-b.order||b.rate-a.rate||companies[a.company].name.localeCompare(companies[b.company].name)||a.name.localeCompare(b.name):a.name.length-b.name.length||a.name.localeCompare(b.name)));
  return {type,order,best:rows[0]?.[0],total:rows.length,rows:rows.slice(0,o.limit||SITE_SEARCH_GROUPS[type][1])};
 }).filter(g=>g.total).sort((a,b)=>a.best-b.best||(a.best===5?(b.type==='work')-(a.type==='work'):0)||a.order-b.order);
 return groups.flatMap(g=>g.rows.map(([rank,e])=>{
  const has=words=>tokens.every(t=>words.some(w=>w.startsWith(t))),alias=e.type==='company'&&!has(e.nameWords)?(e.aliases||[]).find(a=>has(siteSearchWords(a.name))):null;
  return {type:e.type,id:e.id,name:e.name,meta:alias?`Also known as ${alias.name}${alias.note?' ('+alias.note+')':''}`:e.meta,badge:e.badge||'',href:e.href,company:e.company||'',product:e.product||'',rank,group:SITE_SEARCH_GROUPS[e.type][0],total:g.total};
 }));
}
// Listing count as the Paid work page will show it after the query is applied to its own search.
function siteSearchWorkCount(query){if(typeof filteredWork!=='function')return 0;const saved=state.workQuery;try{state.workQuery=query;return filteredWork().length;}catch{return 0;}finally{state.workQuery=saved;}}
function siteSearchView(query){
 const tokens=siteSearchWords(query);
 if(!tokens.length){const pages=siteSearchPages();return [{label:'Suggested',items:[...SITE_SEARCH_SUGGESTED.filter(isCompanyId).map(id=>({type:'company',name:companies[id].name,meta:groupLabel(modelGroup(id)),href:'#company/'+id})),...['work','compare','method'].map(id=>pages.find(p=>p.id===id))]}];}
 const results=siteSearch(query),groups=[];
 for(const item of results){if(groups.at(-1)?.type!==item.type)groups.push({type:item.type,label:item.group,items:[]});groups.at(-1).items.push(item);}
 const work=groups.find(g=>g.type==='work'),text=tokens.join(' '),count=work?siteSearchWorkCount(text):0;
 if(work&&count){const all={type:'action',action:'work',query:text,name:`See all ${count} ${count===1?'listing':'listings'} for “${query.trim()}”`,meta:'Opens Paid work with this search',href:'#work'};if(work.items[0].rank>=4)work.items.unshift(all);else work.items.push(all);}
 if(!groups.length)groups.push({label:'Try instead',items:[{type:'page',name:`Browse all ${DATA.companies.length} companies`,meta:'The full company list',href:'#companies'},{type:'page',name:'See all paid work',meta:'Every listing, with filters',href:'#work'}]});
 return groups;
}
function siteSearchMark(text,tokens){
 const value=publicText(String(text??''));let html='',last=0;
 if(tokens.length)for(const m of value.matchAll(/[\p{L}\p{N}\p{M}]+/gu)){
  const word=m[0],folded=siteSearchFold(word),token=tokens.filter(t=>folded.startsWith(t)).sort((a,b)=>b.length-a.length)[0];if(!token)continue;
  let end=0,length=0;for(const ch of word){if(length>=token.length)break;length+=siteSearchFold(ch).length;end+=ch.length;}
  html+=attr(value.slice(last,m.index))+'<mark>'+attr(word.slice(0,end))+'</mark>';last=m.index+end;
 }
 return html+attr(value.slice(last));
}
function siteSearchAnnounce(text){clearTimeout(siteSearchStatusTimer);siteSearchStatusTimer=setTimeout(()=>{$('site-search-status').textContent=text;},450);}
function siteSearchRender(){
 const input=$('site-search-input'),list=$('site-search-results'),query=input.value.trim(),tokens=siteSearchWords(query),groups=siteSearchView(query);
 siteSearchItems=groups.flatMap(g=>g.items);siteSearchActive=-1;let index=0;
 list.innerHTML=groups.map(g=>`<div class="site-search-group" role="group" aria-label="${attr(g.label)}"><div class="site-search-group-label" aria-hidden="true">${esc(g.label)}</div>${g.items.map(item=>{const i=index++;return `<div class="site-search-option${i||!tokens.length?'':' is-first'}" id="site-search-option-${i}" role="option" aria-selected="false" data-site-search-index="${i}"><span class="site-search-name">${siteSearchMark(item.name,item.type==='action'?[]:tokens)}${item.badge?` <span class="site-search-badge">${esc(item.badge)}</span>`:''}</span>${item.meta?`<span class="site-search-meta">${siteSearchMark(item.meta,item.type==='action'?[]:tokens)}</span>`:''}<kbd class="site-search-enter" aria-hidden="true">Enter</kbd></div>`;}).join('')}</div>`).join('');
 list.hidden=!siteSearchItems.length;input.setAttribute('aria-expanded',String(siteSearchItems.length>0));input.removeAttribute('aria-activedescendant');
 const results=siteSearchItems.filter(i=>i.rank!==undefined).length,exact=siteSearchItems.some(i=>i.rank<6);
 $('site-search-message').textContent=!tokens.length?'Type a name or a role. Press Enter to open the first result.':!results?`No match for “${query}”.`:exact?'':`No exact match for “${query}”. Showing close matches.`;
 if(tokens.length)siteSearchAnnounce(results?`${results} ${results===1?'result':'results'}. Top result: ${siteSearchItems[0].name}.`:'No results.');
}
function siteSearchSetActive(index){
 siteSearchActive=index;
 document.querySelectorAll('#site-search-results [role=option]').forEach((option,i)=>{const on=i===index;option.setAttribute('aria-selected',String(on));option.classList.toggle('is-active',on);option.classList.remove('is-first');if(on)option.scrollIntoView({block:'nearest'});});
 $('site-search-input').setAttribute('aria-activedescendant','site-search-option-'+index);
}
// Land on the exact product or listing card once the profile has rendered.
function siteSearchReveal(item){
 const product=item.type==='product';if(!product&&typeof w4FillRouteGroup==='function')w4FillRouteGroup('#profile-view',item.id);
 const card=[...document.querySelectorAll(product?'#profile-view [data-profile-product]':'#profile-view [data-work-route]')].find(el=>product?el.dataset.profileProduct===item.product:el.dataset.workRoute===item.id);
 if(!card)return;
 for(let el=card;el;el=el.parentElement)if(el.tagName==='DETAILS')el.open=true;
 const toggle=card.querySelector('.w4-compact-toggle');if(toggle)toggle.open=true;
 const target=card.querySelector('h3')||toggle?.querySelector('summary')||card;
 if(target.tagName!=='SUMMARY')target.setAttribute('tabindex','-1');
 target.focus({preventScroll:true});card.scrollIntoView({block:'start',behavior:'instant'});
 // Keep the card clear of the sticky header and profile tabs.
 const covered=Math.max(0,...['.topbar','#profile-view .profile-tabs'].map(s=>document.querySelector(s)?.getBoundingClientRect().bottom||0)),gap=card.getBoundingClientRect().top-covered-16;
 if(gap<0)window.scrollBy({top:gap,behavior:'instant'});
 card.classList.add('site-search-target');target.addEventListener('blur',()=>card.classList.remove('site-search-target'),{once:true});
}
function siteSearchChoose(item){
 if(!item)return;
 if(item.action==='work'){const field=$('work-search');field.value=item.query;field.dispatchEvent(new Event('input',{bubbles:true}));}
 $('site-search').close();
 const reveal=item.type==='product'||item.type==='work'?()=>siteSearchReveal(item):null;
 if(location.hash===item.href){route({type:'hashchange'});reveal?.();return;}
 if(reveal)window.addEventListener('hashchange',reveal,{once:true});
 location.hash=item.href;
}
function siteSearchKey(event){
 if(event.isComposing)return;
 const n=siteSearchItems.length,down=event.key==='ArrowDown';
 if(down||event.key==='ArrowUp'){if(!n)return;event.preventDefault();siteSearchSetActive(siteSearchActive<0?(down?0:n-1):(siteSearchActive+(down?1:n-1))%n);}
 else if(event.key==='Enter'){event.preventDefault();siteSearchChoose(siteSearchItems[siteSearchActive]||(siteSearchWords(event.target.value).length?siteSearchItems[0]:null));}
 else if(event.key==='Escape'&&event.target.value){event.preventDefault();event.target.value='';siteSearchRender();}
}
function siteSearchOpen(text){
 const dialog=$('site-search'),input=$('site-search-input');
 if(dialog.open)return;
 if(typeof text==='string')input.value=text;
 dialog.showModal();$('site-search-open').setAttribute('aria-expanded','true');
 siteSearchRender();input.focus();input.select();
}
// "/" and Ctrl or Cmd+K open search, except while typing in a field or while another dialog is open.
function siteSearchTyping(el){return Boolean(el?.isContentEditable||el?.closest?.('textarea,select')||(el?.matches?.('input')&&!/^(?:checkbox|radio|button|submit|reset|range|color|file|image)$/.test(el.type)));}
function siteSearchShortcut(event){
 if(event.defaultPrevented||event.isComposing||event.altKey)return;
 const command=(event.ctrlKey||event.metaKey)&&!event.shiftKey&&(String(event.key).toLowerCase()==='k'||event.code==='KeyK');
 if(!command&&!(event.key==='/'&&!event.ctrlKey&&!event.metaKey))return;
 if(siteSearchTyping(event.target)||document.querySelector('dialog[open]'))return;
 event.preventDefault();siteSearchOpen();
}

function initSiteNav(){
 const button=$('site-search-open'),dialog=$('site-search'),input=$('site-search-input'),list=$('site-search-results');
 button.addEventListener('click',()=>siteSearchOpen());
 $('site-search-close').addEventListener('click',()=>dialog.close());
 input.addEventListener('input',siteSearchRender);
 input.addEventListener('keydown',siteSearchKey);
 // Options keep focus in the field; a click chooses one.
 list.addEventListener('mousedown',event=>event.preventDefault());
 list.addEventListener('click',event=>{const option=event.target.closest?.('[role=option]');if(option)siteSearchChoose(siteSearchItems[Number(option.dataset.siteSearchIndex)]);});
 dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
 // Focus returns to the opener. When search opened with nothing focused (on load, or "/" on the page), it goes to the button.
 dialog.addEventListener('close',()=>{button.setAttribute('aria-expanded','false');$('site-search-status').textContent='';const active=document.activeElement;if(!active||active===document.body||dialog.contains(active))button.focus();});
 document.addEventListener('keydown',siteSearchShortcut);
 window.addEventListener('hashchange',()=>{if(dialog.open)dialog.close();});
 // Static pages link to /?search (or /?q=text): open search once, then drop the query from the address.
 const params=String(location.search||'');
 if(/[?&](?:search|q)(?:[=&]|$)/.test(params)){
  const match=params.match(/[?&](?:q|search)=([^&]*)/);let text='';try{text=match?decodeURIComponent(match[1].replace(/\+/g,' ')):'';}catch{}
  history.replaceState(history.state,'',location.pathname.replace(/^\/{2,}/,'/')+location.hash);siteSearchOpen(text);
 }
}
