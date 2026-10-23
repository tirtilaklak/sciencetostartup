/* Editorial presentation layer. Canonical claims and measures remain inspectable. */
const attr=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const entryFor=id=>window.EDITORIAL.entries.find(e=>e.company_id===id);
const logoFor=id=>(window.LOGOS?.logos||[]).find(l=>l.company_id===id&&l.local_path);
const GROUP_LABELS={
  'Expert data & evaluation':'Expert data & AI testing',
  'Managed AI & data services':'AI & data services',
  'Frontier data & RL environments':'AI training data & practice environments',
  'AI software & analytics':'AI software & analysis',
  'AI evaluation & safety':'AI testing & safety',
  'Compute & model research':'Computing & AI model research'
};
function groupLabel(name){return GROUP_LABELS[name]||name;}
// Stable URL slug for a business group key, shared by #companies/<slug> and /companies/#<slug>.
function groupSlug(name){return String(name||'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');}
// Every logo sits in a tile. Without an image the tile shows initials. Pass decorative=true
// where the company name is printed next to the logo, so screen readers hear the name once.
function logoInitials(id){return String(companies[id]?.name||id).split(/[\s/]+/).filter(word=>/^[\p{L}\p{N}]/u.test(word)).slice(0,2).map(word=>[...word][0]).join('').toUpperCase();}
function logoHTML(id,extra='',decorative=false) { const a=logoFor(id);return a?`<span class="brand-asset ${extra} ${a.background==='dark'?'brand-dark':''}"><img src="${attr(a.local_path)}" alt="${decorative?'':esc(companies[id]?.name||id)+' logo'}" data-initials="${attr(logoInitials(id))}" loading="lazy" decoding="async"></span>`:`<span class="brand-asset brand-text ${extra}" aria-hidden="true">${esc(logoInitials(id))}</span>`; }
function card(c){const e=entryFor(c.id),financial=preferredFinancial(c.id),product=typeof profileProducts==='function'?profileProducts(c.id)[0]:null;return `<article class="company-card" data-company-card="${esc(c.id)}"><a class="company-brand" href="#company/${esc(c.id)}" tabindex="-1" aria-hidden="true">${logoHTML(c.id)}</a><div class="company-card-content"><span class="category-label sr-only">${esc(groupLabel(modelGroup(c.id)))}</span><h3><a href="#company/${esc(c.id)}">${esc(c.name)}</a></h3><p class="company-description">${esc(modelFor(c.id))}</p><div class="capability-tags sr-only">${(e?.capability_tags||[]).map(t=>`<span>${esc(t)}</span>`).join('')}</div></div><div class="company-signal">${financial?compactSignal(c.id):product?`<span class="signal-label">${companies[c.id].entity_type==='adjacent_research'?'Research':'Offering'}</span><p class="product-distinction">${esc(publicOfferingName(product.name))} ${typeof productSourceHTML==='function'?productSourceHTML(product):profileReferences(product.claim_ids,'Source')}</p>${product.status?`<p class="sub offering-status">${esc(title(product.status))}</p>`:''}`:'<span class="signal-label">See the research</span>'}</div><div class="company-card-footer">${compareCheck(c.id)}<button class="text-link" data-open-company="${esc(c.id)}" aria-label="Quick summary of ${esc(c.name)}">Quick summary</button></div></article>`;}

// Overview business groups: each row links to the company list filtered to that group (#companies/<slug>).
function renderModelMap(){const captions={'Expert data & evaluation':'Experts create examples and test AI','Managed AI & data services':'Teams prepare data and run AI projects','Frontier data & RL environments':'Tasks and simulations that help AI learn','AI software & analytics':'Tools for building and measuring AI','AI evaluation & safety':'Tests for reliability and security','Compute & model research':'Computing resources and research on AI models','Nonprofit research':'Public research and shared tests'},list=names=>names.length>2?names.slice(0,-1).join(', ')+' and '+names.at(-1):names.join(' and ');$('model-map').innerHTML=Object.entries(MODEL_GROUPS).map(([name,ids])=>{const names=ids.map(id=>companies[id]?.name).filter(Boolean).sort((a,b)=>a.localeCompare(b,'en',{sensitivity:'base'})),rest=names.length-3;return `<a class="category-card" href="#companies/${attr(groupSlug(name))}" data-category-jump="${attr(name)}"><span class="category-name">${esc(groupLabel(name))}</span><span class="category-description">${esc(captions[name])}</span><span class="category-members">${esc(rest>0?names.slice(0,3).join(', ')+' and '+rest+' more':list(names))}</span><span class="category-count">${ids.length}<small>${ids.length===1?'company':'companies'}</small></span>${iconHTML('right')}</a>`;}).join('');}

const originalRenderStory=renderStory;
renderStory=function(){originalRenderStory();$('source-count').textContent=DATA.sources.length;$('hero-logo-grid').innerHTML=['scale_ai','mercor','surge_ai','snorkel_ai','labelbox','prime_intellect'].filter(id=>companies[id]).map(id=>`<a href="#company/${attr(id)}">${logoHTML(id,'',true)}<span class="hero-logo-name">${esc(companies[id].name)}</span></a>`).join('');};

const originalRenderCompare=renderCompare;
renderCompare=function(){originalRenderCompare();document.querySelectorAll('.comparison-table thead th:not(:first-child)').forEach((th,i)=>{const id=compareIds()[i];if(id)th.insertAdjacentHTML('afterbegin',logoHTML(id,'compare-logo',true));});};

// Profiles render in profiles-v2.js (profileHTML).

const originalOpenCompanyStory=openCompanyStory;
openCompanyStory=function(id){originalOpenCompanyStory(id);$('company-story').insertAdjacentHTML('afterbegin',logoHTML(id,'dialog-logo',true));const e=entryFor(id);$('company-story').insertAdjacentHTML('beforeend',`<div class="capability-tags">${(e?.capability_tags||[]).map(t=>`<span>${esc(t)}</span>`).join('')}</div>`);};

document.addEventListener('click',e=>{
 const b=e.target.closest?.('[data-category-jump]'),category=b?.dataset.categoryJump;
 if(!category||!Object.hasOwn(MODEL_GROUPS,category))return;
 // A modified click opens the group link in a new tab; that page reads the group from its URL.
 if(b.tagName==='A'&&(e.defaultPrevented||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||(e.button!==undefined&&e.button!==0)))return;
 // Overview groups show the complete group, independent of earlier searches.
 Object.assign(state,{query:'',category,stage:'',financial:false,work:false});
 $('search').value='';$('category').value=category;$('stage').value='';
 $('financial-only').checked=false;$('work-only').checked=false;
 renderDirectory();viewScroll.companies=0;
 // Links follow their own #companies/<slug> href; any older button form still jumps to the list.
 if(b.tagName!=='A'){location.hash='#companies';window.scrollTo(0,0);}
});

// Route first, then focus the newly visible heading for hash navigation only.
// initialize() registers this wrapper and calls it without an event on first load.
const originalRoute=route;
route=function(event){
  const returningToWork=event?.type==='hashchange'&&location.hash.slice(1).split('/')[0]==='work'&&previousRoute==='company';
  const returningToCompanies=event?.type==='hashchange'&&location.hash==='#companies'&&previousRoute==='company';
  const result=originalRoute.apply(this,arguments);
  if(event?.type==='hashchange'&&location.hash!=='#main'){
    const workLink=returningToWork&&typeof workReturnFocusTarget==='function'?workReturnFocusTarget():null;
    const companyOrigin=returningToCompanies?companyReturnFocusTarget():null;
    if(companyOrigin)companyOrigin.focus({preventScroll:true});
    else if(workLink)workLink.focus({preventScroll:true});
    else{
      const heading=document.querySelector('.view:not([hidden]) h1');
      if(heading){heading.setAttribute('tabindex','-1');heading.focus({preventScroll:true});}
    }
  }
  return result;
};

document.addEventListener('error',e=>{if(e.target.matches?.('.brand-asset img')){const img=e.target,tile=img.parentElement,label=img.alt;tile.textContent=img.dataset.initials||label.replace(/ logo$/,'');tile.classList.add('brand-text');if(label){tile.setAttribute('role','img');tile.setAttribute('aria-label',label);}else tile.setAttribute('aria-hidden','true');}},true);

const PRODUCT_MEDIA_DIMENSIONS={labelbox:[1200,627],imerit:[1024,576],sama:[2180,1117]};
function productMediaHTML(id){const e=entryFor(id),m=e?.product_media,dimensions=PRODUCT_MEDIA_DIMENSIONS[id];return m?`<figure class="product-media"><img src="${attr(m.local_path)}" alt="${attr(m.title)}"${dimensions?` width="${dimensions[0]}" height="${dimensions[1]}"`:''} loading="lazy" decoding="async"><figcaption>${esc(m.caption)} ${external(m.source_page,'Source')}</figcaption></figure>`:'';}

function publicOfferingName(name){return String(name).replace(/\bRL\b/g,'AI practice').replace(/\bSFT\b/g,'training from examples');}
