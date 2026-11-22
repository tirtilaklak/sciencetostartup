/* Filtering enhances the complete static directory; no network is needed. */
(()=>{
  'use strict';
  const form=document.getElementById('company-filters');
  if(!form)return;
  const query=document.getElementById('company-query');
  const group=document.getElementById('company-group');
  const count=document.getElementById('company-count');
  const empty=document.getElementById('company-empty');
  const fullGuide=empty?.querySelector('[data-full-guide-search]');
  const selectedGroup=document.querySelector('[data-directory-selected-group]');
  const sections=[...document.querySelectorAll('.directory-section')];
  const handoffs='.directory-compare, .directory-company-heading h3 a, [data-full-guide-search]';
  const search=globalThis.S2SSearch;
  if(!search){document.documentElement.removeAttribute('data-page-enhancement');return;}
  const aliases=node=>{try{const value=JSON.parse(node.dataset.searchAliases||'[]');return Array.isArray(value)?value:[];}catch{return [];}};
  const cards=sections.map((section,order)=>({section,order,rows:[...section.querySelectorAll('[data-company]')].map((node,index)=>({node,index,compiled:search.compile({name:node.dataset.searchName||node.querySelector('.directory-company-heading a')?.textContent||'',aliases:aliases(node),text:node.dataset.search||node.textContent})}))}));
  const sectionParent=sections[0]?.parentNode,sectionAnchor=sections.at(-1)?.nextSibling;
  let displayedSearch;
  const read=savedQuery=>{
    const params=new URLSearchParams(location.search);
    query.value=savedQuery??params.get('q')??'';
    const selected=params.get('group')||'';group.value=[...group.options].some(option=>option.value===selected)?selected:'';
  };
  function filter(updateURL=true){
    const key=search.normalize(query.value);
    let visible=0;
    cards.forEach(entry=>{
      const {section,rows}=entry;let own=0;entry.best=Infinity;
      rows.forEach(row=>{
        const {node}=row;row.rank=search.rank(row.compiled,key);
        const match=(!group.value||section.dataset.group===group.value)&&row.rank>=0;
        node.hidden=!match;
        if(match){own++;visible++;entry.best=Math.min(entry.best,row.rank);}
      });
      const list=section.querySelector('.directory-grid')||rows[0]?.node.parentNode;
      if(list) [...rows].sort((a,b)=>(key?a.rank-b.rank:0)||a.index-b.index).forEach(row=>list.append(row.node));
      section.hidden=own===0;
      section.querySelector('.directory-section-heading>span').textContent=`${own} ${own===1?'company':'companies'}`;
    });
    if(sectionParent) [...cards].sort((a,b)=>(key?a.best-b.best:0)||a.order-b.order).forEach(entry=>sectionParent.insertBefore(entry.section,sectionAnchor));
    count.textContent=`${visible} ${visible===1?'company':'companies'}`;
    empty.hidden=visible!==0;
    if(fullGuide) fullGuide.href='/?'+new URLSearchParams({search:query.value})+'#browse-guide';
    if(selectedGroup){
      selectedGroup.hidden=!group.value;
      selectedGroup.textContent=group.value?group.selectedOptions[0].textContent:'';
    }
    if(updateURL){
      const url=new URL(location.href);
      if(query.value.trim())url.searchParams.set('q',query.value.trim());else url.searchParams.delete('q');
      if(group.value)url.searchParams.set('group',group.value);else url.searchParams.delete('group');
      const state={...history.state};
      delete state.directoryReturn;
      try{history.replaceState(state,'',url);}catch{}
    }
    displayedSearch=location.search;
  }

  document.addEventListener('click',event=>{
    const link=event.target.closest?.('a[href]');
    if(!link||!event.isTrusted||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||
      event.shiftKey||event.altKey||link.hasAttribute('download')||(link.target&&link.target.toLowerCase()!=='_self')||
      link.href.split('#')[0]===location.href.split('#')[0])return;
    const {directoryReturn,...state}=history.state||{};
    if(link.matches(handoffs)){
      state.directoryReturn={page:location.href,href:link.href,query:query.value,top:link.getBoundingClientRect().top};
    }else if(!directoryReturn)return;
    try{history.replaceState(state,'');}catch{}
  });

  const activation=window.navigation?.activation;
  const fromIndex=activation?.from?.index;
  const goingForward=fromIndex>=0&&fromIndex<=activation.entry?.index;
  const saved=history.state?.directoryReturn;
  const returning=saved?.page===location.href&&!goingForward&&performance.getEntriesByType('navigation')[0]?.type==='back_forward';
  if(returning)window.addEventListener('pageshow',event=>{
    if(event.persisted)return;
    // The browser applies history scroll restoration after pageshow.
    requestAnimationFrame(()=>{
      if(document.activeElement!==document.body||history.state?.directoryReturn?.href!==saved.href)return;
      const link=[...document.querySelectorAll(handoffs)].find(link=>link.href===saved.href&&!link.closest('[hidden]'));
      if(!link)return;
      link.focus({preventScroll:true});
      const bounds=link.getBoundingClientRect();
      const headerBottom=Math.max(0,document.querySelector('.site-header')?.getBoundingClientRect().bottom||0);
      if(saved.top>=headerBottom&&saved.top+bounds.height<=innerHeight){
        scrollBy({top:bounds.top-saved.top,behavior:'instant'});
      }else link.scrollIntoView({block:'center',behavior:'instant'});
    });
  },{once:true});

  form.addEventListener('submit',event=>event.preventDefault());
  query.addEventListener('input',()=>filter());
  group.addEventListener('change',()=>filter());
  form.addEventListener('reset',event=>{event.preventDefault();query.value='';group.value='';filter();query.focus();});
  window.addEventListener('popstate',()=>{
    if(displayedSearch!==location.search){read();filter(false);}
  });
  read(returning?saved.query:undefined);filter(false);form.hidden=false;
  document.documentElement.removeAttribute('data-page-enhancement');
  const jumps=document.querySelector('.directory-groups');
  if(jumps)jumps.hidden=true;
})();
