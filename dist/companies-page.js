/* Shared by the optional search components at build time; no extra request. */
(() => {
  'use strict';
  if (globalThis.S2SSearch) return;
  // Match both recorded TeX titles and the Greek spelling displayed in the UI.
  const mathTitle = value => String(value ?? '').replace(/\$\\tau(\^2)?\$/gu, (_, squared) => squared ? 'τ²' : 'τ').replace(/\\tau(\^2)?(?![\p{L}\p{N}_])/gu, (_, squared) => squared ? 'τ²' : 'τ');
  const normalize = value => mathTitle(value).normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase().replace(/\s+/gu, ' ').trim();
  const aliasName = value => String(value).replace(/\s*\([^()]*\)\s*$/u, '').trim();
  const values = value => Array.isArray(value) ? value.flatMap(values) : value == null ? [] : [String(value)];
  const arxiv = /^(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*\/\d{7})(?:v[1-9]\d*)?$/u;
  const doi = /^10\.\d{4,9}\/\S+$/u;
  const record = /^paper\.[a-z0-9_-]+(?:\.[a-z0-9_-]+)+$/u;
  function identifier(value) {
    let text = String(value ?? '').trim().toLowerCase();
    let type = '';
    if (/^https?:\/\//u.test(text) || text.startsWith('/research/papers/')) {
      let url, path;
      try {
        url = new URL(text, 'https://sciencetostartup.com');
        path = decodeURIComponent(url.pathname).toLowerCase();
      } catch { return ''; }
      if (url.username || url.password || url.port) return '';
      if (['arxiv.org', 'www.arxiv.org', 'export.arxiv.org'].includes(url.hostname)) {
        const match = path.match(/^\/(abs|pdf|html)\/(.+?)\/?$/u);
        if (!match) return '';
        type = 'arxiv';
        text = match[1] === 'pdf' ? match[2].replace(/\.pdf$/u, '') : match[2];
      } else if (['doi.org', 'dx.doi.org'].includes(url.hostname)) {
        type = 'doi'; text = path.slice(1);
      } else if (url.hostname === 'sciencetostartup.com') {
        type = 'record'; text = path.match(/^\/research\/papers\/([^/]+)\/?$/u)?.[1] || '';
      } else return '';
    } else {
      const prefix = text.match(/^(arxiv|doi):\s*/u);
      if (prefix) { type = prefix[1]; text = text.slice(prefix[0].length); }
    }
    if ((!type || type === 'arxiv') && arxiv.test(text)) return 'arxiv:' + text;
    if ((!type || type === 'doi') && doi.test(text)) return 'doi:' + text;
    if ((!type || type === 'record') && record.test(text)) return 'record:' + text;
    return '';
  }
  const identifiers = value => [...new Set(values(value).map(identifier).filter(Boolean))];
  const leadingWork = /^(?:jobs?|careers?|hiring|vacancies|openings)(?:\s+(?:for|in))?(?=\s|$)/iu;
  const trailingWork = /(?:^|\s)(?:jobs?|careers?|vacancies|openings)\s*$/iu;
  const researchTerms = /\b(?:papers?|datasets?|benchmarks?|literature|arxiv|doi)\b/iu;
  function explicitWork(value) {
    const text = String(value ?? '').trim();
    return !researchTerms.test(text) && (leadingWork.test(text) || trailingWork.test(text));
  }
  function isWorkQuery(value, titles) {
    return !identifier(value) && (explicitWork(value) || Boolean(titles?.has(normalize(value))));
  }
  function workTerms(value) {
    const text = String(value ?? '');
    return explicitWork(text) ? text.trim().replace(leadingWork, '').replace(trailingWork, '').trim() : text;
  }
  const workUrl = value => '/work/' + (String(value ?? '').trim() ? '?' + new URLSearchParams({ q: value }) : '');
  function compile(row) {
    const aliases = values(row.aliases).map(raw => ({ raw, key: normalize(aliasName(raw)) }));
    const name = normalize(row.name);
    const text = normalize([row.name, ...aliases.map(item => item.raw), ...values(row.summary), ...values(row.group), ...values(row.products), ...values(row.keywords), ...values(row.text)].join(' '));
    return { row, name, aliases, text, identifiers: identifiers(row.identifiers) };
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
  globalThis.S2SSearch = Object.freeze({ normalize, identifier, identifiers, isWorkQuery, workTerms, workUrl, compile, rank, compare, matchedAlias });
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
  const fullGuide=empty?.querySelector('[data-full-guide-search]');
  const selectedGroup=document.querySelector('[data-directory-selected-group]');
  const sections=[...document.querySelectorAll('.directory-section')];
  const handoffs='.directory-compare, .directory-company-heading h3 a, [data-full-guide-search]';
  const search=globalThis.S2SSearch;
  if(!search){document.documentElement.removeAttribute('data-page-enhancement');return;}
  const aliases=node=>{try{const value=JSON.parse(node.dataset.searchAliases||'[]');return Array.isArray(value)?value:[];}catch{return [];}};
  const cards=sections.map((section,order)=>({section,order,rows:[...section.querySelectorAll('[data-company]')].map((node,index)=>({node,index,compiled:search.compile({name:node.dataset.searchName||node.querySelector('.directory-company-heading a')?.textContent||'',aliases:aliases(node),text:node.dataset.search||node.textContent})}))}));
  const sectionParent=sections[0]?.parentNode,sectionAnchor=sections.at(-1)?.nextElementSibling;
  let displayedSearch;
  const read=savedQuery=>{
    const params=new URLSearchParams(location.search);
    query.value=savedQuery??params.get('q')??'';
    const selected=params.get('group')||'';group.value=[...group.options].some(option=>option.value===selected)?selected:'';
  };
  function orderChildren(parent,nodes,next=null){
    for(let index=nodes.length-1;index>=0;index--){
      const node=nodes[index];
      if(node.nextElementSibling!==next)parent.insertBefore(node,next);
      next=node;
    }
  }
  function filter(updateURL=true){
    const key=search.normalize(query.value);
    const focused=document.activeElement;
    const focusedLink=focused?.matches('a[href]')&&focused.closest('.directory-section')?focused:null;
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
      if(list)orderChildren(list,[...rows].sort((a,b)=>(key?a.rank-b.rank:0)||a.index-b.index).map(row=>row.node));
      section.hidden=own===0;
      section.querySelector('.directory-section-heading>span').textContent=`${own} ${own===1?'company':'companies'}`;
    });
    if(sectionParent)orderChildren(sectionParent,[...cards].sort((a,b)=>(key?a.best-b.best:0)||a.order-b.order).map(entry=>entry.section),sectionAnchor);
    if(focusedLink&&document.activeElement===document.body&&focusedLink.isConnected&&
      !focusedLink.closest('[hidden]')&&focusedLink.getClientRects().length){
      focusedLink.focus({preventScroll:true});
    }
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
      state.directoryReturn={page:location.href,href:link.href,query:query.value,top:link.getBoundingClientRect().top,
        entry:window.S2SNativeHandoff?.begin(link.href,event)};
    }else if(!directoryReturn)return;
    try{history.replaceState(state,'');}catch{}
  });

  const activation=window.navigation?.activation;
  const fromIndex=activation?.from?.index;
  const goingForward=fromIndex>=0&&fromIndex<=activation.entry?.index;
  const saved=history.state?.directoryReturn;
  const revisiting=saved?.page===location.href&&performance.getEntriesByType('navigation')[0]?.type==='back_forward';
  const returning=revisiting&&
    (window.navigation?!goingForward:window.S2SNativeHandoff?.returnedFrom(saved.entry));
  if(returning){
    const restoration=new AbortController();
    const {signal}=restoration;
    const stop=()=>restoration.abort();
    const stillReturning=()=>location.href===saved.page&&history.state?.directoryReturn?.href===saved.href;
    for(const type of ['wheel','keydown','touchstart','touchmove','pointerdown']){
      window.addEventListener(type,event=>{if(event.isTrusted)stop();},{capture:true,passive:true,signal});
    }
    window.addEventListener('pagehide',stop,{once:true,signal});
    window.addEventListener('pageshow',event=>{
      if(event.persisted){stop();return;}
      requestAnimationFrame(()=>{
        if(signal.aborted)return;
        if(document.activeElement!==document.body||!stillReturning()){stop();return;}
        const link=[...document.querySelectorAll(handoffs)].find(link=>link.href===saved.href&&!link.closest('[hidden]'));
        if(!link){stop();return;}
        function restorePosition(){
          const bounds=link.getBoundingClientRect();
          const headerBottom=Math.max(0,document.querySelector('.site-header')?.getBoundingClientRect().bottom||0);
          if(saved.top>=headerBottom&&saved.top+bounds.height<=innerHeight){
            scrollBy({top:bounds.top-saved.top,behavior:'instant'});
          }else link.scrollIntoView({block:'center',behavior:'instant'});
        }
        link.focus({preventScroll:true});
        restorePosition();

        // WebKit can restore history scroll after the opener has already been positioned.
        const restoredScroll=scrollY;
        window.addEventListener('scroll',()=>{
          if(signal.aborted)return;
          if(document.activeElement!==link||!stillReturning()||link.closest('[hidden]')){stop();return;}
          if(Math.abs(scrollY-restoredScroll)<1)return;
          stop();
          restorePosition();
        },{passive:true,signal});
        setTimeout(stop,250);
      });
    },{once:true,signal});
  }

  form.addEventListener('submit',event=>event.preventDefault());
  query.addEventListener('input',()=>filter());
  group.addEventListener('change',()=>filter());
  form.addEventListener('reset',event=>{event.preventDefault();query.value='';group.value='';filter();query.focus();});
  window.addEventListener('popstate',()=>{
    if(displayedSearch!==location.search){read();filter(false);}
  });
  read(revisiting?saved.query:undefined);filter(false);form.hidden=false;
  document.documentElement.removeAttribute('data-page-enhancement');
  const jumps=document.querySelector('.directory-groups');
  if(jumps)jumps.hidden=true;
})();
