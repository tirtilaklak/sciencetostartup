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
function logoHTML(id,extra='') { const a=logoFor(id);return a?`<span class="brand-asset ${extra} ${a.background==='dark'?'brand-dark':''}"><img src="${attr(a.local_path)}" alt="${esc(companies[id]?.name||id)} logo" loading="lazy" decoding="async"></span>`:`<span class="brand-asset brand-text ${extra}">${esc(companies[id]?.name||id)}</span>`; }
function card(c){const e=entryFor(c.id),financial=preferredFinancial(c.id),product=typeof profileProducts==='function'?profileProducts(c.id)[0]:null;return `<article class="company-card" data-company-card="${esc(c.id)}"><a class="company-brand" href="#company/${esc(c.id)}" aria-label="Explore ${esc(c.name)}">${logoHTML(c.id)}</a><div class="company-card-content"><span class="category-label sr-only">${esc(groupLabel(modelGroup(c.id)))}</span><h3><a href="#company/${esc(c.id)}">${esc(c.name)}</a></h3><p class="company-description">${esc(modelFor(c.id))}</p><div class="capability-tags sr-only">${(e?.capability_tags||[]).map(t=>`<span>${esc(t)}</span>`).join('')}</div></div><div class="company-signal">${financial?compactSignal(c.id):product?`<span class="signal-label">${companies[c.id].entity_type==='adjacent_research'?'Research':'Offering'}</span><p class="product-distinction">${esc(publicOfferingName(product.name))} ${typeof productSourceHTML==='function'?productSourceHTML(product):profileReferences(product.claim_ids,'Source')}</p>${product.status?`<p class="sub offering-status">${esc(title(product.status))}</p>`:''}`:'<span class="signal-label">See the research</span>'}</div><div class="company-card-footer">${compareCheck(c.id)}<button class="text-link" data-open-company="${esc(c.id)}" aria-label="Quick summary of ${esc(c.name)}">Quick summary</button></div></article>`;}

function marketCompanyHTML(id){return `<article class="market-company">${logoHTML(id)}<div><h3><a href="#company/${attr(id)}">${esc(companies[id].name)}</a></h3><p>${esc(modelFor(id))}</p><a class="text-link" href="#company/${attr(id)}">View profile ${iconHTML('right')}</a></div></article>`;}

function renderModelMap(){const captions={'Expert data & evaluation':'Experts create examples and test AI','Managed AI & data services':'Teams prepare data and run AI projects','Frontier data & RL environments':'Tasks and simulations that help AI learn','AI software & analytics':'Tools for building and measuring AI','AI evaluation & safety':'Tests for reliability and security','Compute & model research':'Computing resources and research on AI models','Nonprofit research':'Public research and shared tests'};$('model-map').innerHTML=Object.entries(MODEL_GROUPS).map(([name,ids])=>`<button class="category-card" data-category-jump="${esc(name)}"><span class="category-name">${esc(groupLabel(name))}</span><span class="category-description">${esc(captions[name])}</span><span class="category-count">${ids.length}<small>organizations</small></span>${iconHTML('right')}</button>`).join('');}

const originalRenderStory=renderStory;
renderStory=function(){originalRenderStory();$('source-count').textContent=DATA.sources.length;$('hero-logo-grid').innerHTML=['scale_ai','mercor','surge_ai','snorkel_ai','labelbox','prime_intellect'].map(id=>`<a href="#company/${id}" aria-label="Explore ${esc(companies[id].name)}">${logoHTML(id)}<span class="sr-only">${esc(companies[id].name)}</span></a>`).join('');$('featured-companies').innerHTML=['mercor','labelbox','prime_intellect'].map(marketCompanyHTML).join('');};

const originalRenderCompare=renderCompare;
renderCompare=function(){originalRenderCompare();document.querySelectorAll('.comparison-table thead th:not(:first-child)').forEach((th,i)=>{const id=(state.selected.length?state.selected:['taskus','appen','scale_ai'])[i];if(id)th.insertAdjacentHTML('afterbegin',logoHTML(id,'compare-logo'));});};

const originalProfileHTML=profileHTML;
profileHTML=function(id){const html=originalProfileHTML(id);const a=logoFor(id),e=entryFor(id);const assetEvidence=a?`<details class="profile-disclosure"><summary>Official logo source</summary><p>${external(a.source_page,'Official source')} · ${external(a.asset_url,'Original image')} · Retrieved ${esc(a.retrieved_on||window.LOGOS.retrieved_on)}</p><p class="sub">${esc(a.notes||'Official company logo.')}</p></details>`:'';return html.replace(/(<h1[^>]*>)/,'<div class="profile-brand">'+logoHTML(id,'profile-logo')+'</div>$1')+assetEvidence;};

const originalOpenCompanyStory=openCompanyStory;
openCompanyStory=function(id){originalOpenCompanyStory(id);$('company-story').insertAdjacentHTML('afterbegin',logoHTML(id,'dialog-logo'));const e=entryFor(id);$('company-story').insertAdjacentHTML('beforeend',`<div class="capability-tags">${(e?.capability_tags||[]).map(t=>`<span>${esc(t)}</span>`).join('')}</div>`);};

document.addEventListener('click',e=>{
 const b=e.target.closest('[data-category-jump]'),category=b?.dataset.categoryJump;
 if(!category||!Object.hasOwn(MODEL_GROUPS,category))return;
 // Market cards advertise the complete group, independent of earlier searches.
 Object.assign(state,{query:'',category,stage:'',financial:false,work:false});
 $('search').value='';$('category').value=category;$('stage').value='';
 $('financial-only').checked=false;$('work-only').checked=false;
 renderDirectory();viewScroll.companies=0;location.hash='#companies';window.scrollTo(0,0);
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

document.addEventListener('error',e=>{if(e.target.matches?.('.brand-asset img')){const tile=e.target.parentElement;tile.textContent=e.target.alt.replace(/ logo$/, '');tile.classList.add('brand-text');}},true);

const PRODUCT_MEDIA_DIMENSIONS={labelbox:[1200,627],imerit:[1024,576],sama:[2180,1117]};
function productMediaHTML(id){const e=entryFor(id),m=e?.product_media,dimensions=PRODUCT_MEDIA_DIMENSIONS[id];return m?`<figure class="product-media"><img src="${attr(m.local_path)}" alt="${attr(m.title)}"${dimensions?` width="${dimensions[0]}" height="${dimensions[1]}"`:''} loading="lazy" decoding="async"><figcaption>${esc(m.caption)} ${external(m.source_page,'Source')}</figcaption></figure>`:'';}

function publicOfferingName(name){return String(name).replace(/\bRL\b/g,'AI practice').replace(/\bSFT\b/g,'training from examples');}
