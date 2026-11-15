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
  const normalize=value=>value.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const cards=sections.map(section=>({section,rows:[...section.querySelectorAll('[data-company]')].map(node=>({node,text:normalize(node.dataset.search)}))}));
  const read=()=>{
    const params=new URLSearchParams(location.search);
    query.value=params.get('q')||'';
    group.value=params.get('group')||'';
  };
  function filter(updateURL=true){
    const terms=normalize(query.value).split(/\s+/).filter(Boolean);
    let visible=0;
    cards.forEach(({section,rows})=>{
      let own=0;
      rows.forEach(({node,text})=>{
        const match=(!group.value||section.dataset.group===group.value)&&terms.every(term=>text.includes(term));
        node.hidden=!match;
        if(match){own++;visible++;}
      });
      section.hidden=own===0;
      section.querySelector('.directory-section-heading>span').textContent=`${own} ${own===1?'company':'companies'}`;
    });
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
  const jumps=document.querySelector('.directory-groups');
  if(jumps)jumps.hidden=true;
})();
