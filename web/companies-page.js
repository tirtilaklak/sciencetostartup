/* Filtering enhances the complete static directory; no network is needed. */
(()=>{
  'use strict';
  const form=document.getElementById('company-filters');
  if(!form)return;
  const query=document.getElementById('company-query');
  const group=document.getElementById('company-group');
  const count=document.getElementById('company-count');
  const empty=document.getElementById('company-empty');
  const sections=[...document.querySelectorAll('.directory-section')];
  const search=globalThis.S2SSearch;
  if(!search){document.documentElement.removeAttribute('data-page-enhancement');return;}
  const aliases=node=>{try{const value=JSON.parse(node.dataset.searchAliases||'[]');return Array.isArray(value)?value:[];}catch{return [];}};
  const cards=sections.map((section,order)=>({section,order,rows:[...section.querySelectorAll('[data-company]')].map((node,index)=>({node,index,compiled:search.compile({name:node.dataset.searchName||node.querySelector('.directory-company-heading a')?.textContent||'',aliases:aliases(node),text:node.dataset.search||node.textContent})}))}));
  const sectionParent=sections[0]?.parentNode,sectionAnchor=sections.at(-1)?.nextSibling;
  const read=()=>{
    const params=new URLSearchParams(location.search);
    query.value=params.get('q')||'';
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
    if(updateURL){
      const url=new URL(location.href);
      if(query.value.trim())url.searchParams.set('q',query.value.trim());else url.searchParams.delete('q');
      if(group.value)url.searchParams.set('group',group.value);else url.searchParams.delete('group');
      try{history.replaceState(null,'',url);}catch{}
    }
  }
  form.addEventListener('submit',event=>event.preventDefault());
  query.addEventListener('input',()=>filter());
  group.addEventListener('change',()=>filter());
  form.addEventListener('reset',()=>{query.value='';group.value='';filter();});
  window.addEventListener('popstate',()=>{read();filter(false);});
  read();filter(false);form.hidden=false;
  document.documentElement.removeAttribute('data-page-enhancement');
  const jumps=document.querySelector('.directory-groups');
  if(jumps)jumps.hidden=true;
})();
