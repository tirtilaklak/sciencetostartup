/* Shared by the optional search components at build time; no extra request. */
(() => {
  'use strict';
  if (globalThis.S2SSearch) return;
  // Match both recorded TeX titles and the Greek spelling displayed in the UI.
  const mathTitle = value => String(value ?? '').replace(/\$\\tau(\^2)?\$/gu, (_, squared) => squared ? 'τ²' : 'τ').replace(/\\tau(\^2)?(?![\p{L}\p{N}_])/gu, (_, squared) => squared ? 'τ²' : 'τ');
  const normalize = value => mathTitle(value).normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase().replace(/\s+/gu, ' ').trim();
  const aliasName = value => String(value).replace(/\s*\([^()]*\)\s*$/u, '').trim();
  const values = value => Array.isArray(value) ? value.flatMap(values) : value == null ? [] : [String(value)];
  function compile(row) {
    const aliases = values(row.aliases).map(raw => ({ raw, key: normalize(aliasName(raw)) }));
    const name = normalize(row.name);
    const text = normalize([row.name, ...aliases.map(item => item.raw), ...values(row.summary), ...values(row.group), ...values(row.products), ...values(row.keywords), ...values(row.text)].join(' '));
    return { row, name, aliases, text };
  }
  function rank(entry, query) {
    const key = normalize(query);
    if (!key) return 0;
    if (entry.name === key || entry.aliases.some(alias => alias.key === key)) return 0;
    if (entry.name.startsWith(key)) return 1;
    if (entry.aliases.some(alias => alias.key.startsWith(key))) return 2;
    const words = key.split(' ');
    if (words.every(word => entry.name.includes(word))) return 3;
    return words.every(word => entry.text.includes(word)) ? 4 : -1;
  }
  function compare(a, b) {
    const left = normalize(a.name), right = normalize(b.name);
    // Equally relevant navigation hubs precede individual source versions.
    const priority = row => /^\/company\//u.test(row.href || '') ? 0 : ['report', 'research', 'data', 'review', 'daily'].includes(row.group) || /^\/daily\//u.test(row.href || '') ? 1 : 2;
    return priority(a) - priority(b) || (left < right ? -1 : left > right ? 1 : 0) || String(a.href || a.id || '').localeCompare(String(b.href || b.id || ''), 'en');
  }
  function matchedAlias(entry, query) {
    const key = normalize(query);
    if (!key || entry.name.includes(key)) return '';
    return entry.aliases.find(alias => alias.key === key || alias.key.startsWith(key))?.raw || '';
  }
  globalThis.S2SSearch = Object.freeze({ normalize, compile, rank, compare, matchedAlias });
})();

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
