const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const { gunzipSync } = require('node:zlib');
const { createHash } = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const previous = name => name.endsWith('.gz') ? gunzipSync(fs.readFileSync(path.join(root, 'tests/fixtures/previous-search', name))).toString() : read('tests/fixtures/previous-search/' + name);
const current = name => read('web/search-core.js') + '\n' + read('web/' + name);
const companies = require('../../data/canonical.json').companies;
const origin = 'http://127.0.0.1:18769';
const baselineEntries = JSON.parse(previous('index.json.gz')).entries;
async function home(page, { oldMarkup = false, oldIndex = false, oldComponent = false, oldRuntime = false, query = '' } = {}) {
  let html = previous('home.html.gz');
  if (!oldMarkup) html = html.replace('<p id="home-search-status"', '<button id="home-search-more" type="button" hidden>Show more</button><p id="home-search-status"');
  // Use the current legacy-routing source; the remainder is actual baseline markup.
  html = html.replace("legacy.includes(route) || search.has('q') || search.has('search')", "legacy.includes(route) || search.has('q')");
  const aliases = new Map(companies.map(company => [company.id, company.aliases || []]));
  const entries = baselineEntries.map(row => oldIndex ? row : {...row, aliases:aliases.get(row.id) || []});
  const config = JSON.parse(html.match(/<script id="home-config" type="application\/json">(.*?)<\/script>/s)[1]);
  const payload = JSON.stringify({...JSON.parse(previous('index.json.gz')), entries});
  config.search.sha256 = createHash('sha256').update(payload).digest('hex');
  html = html.replace(/(<script id="home-config" type="application\/json">).*?(<\/script>)/s, '$1' + JSON.stringify(config) + '$2');
  await page.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/') return route.fulfill({contentType:'text/html', body:html});
    if (pathname === '/home-runtime.js') return route.fulfill({contentType:'application/javascript', body:oldRuntime ? previous('home-runtime.js') : read('web/home-runtime.js')});
    if (pathname === '/home-search.js') return route.fulfill({contentType:'application/javascript', body:oldComponent ? previous('home-search.js') : current('home-search.js')});
    if (pathname === config.search.href) return route.fulfill({contentType:'application/json', body:payload});
    return route.fulfill({status:200, body:''});
  });
  await page.goto(origin + '/' + query);
  return entries;
}

test('new homepage component accepts old markup and old index without optional aliases', async ({ page }) => {
  await home(page, {oldMarkup:true,oldIndex:true});
  await page.locator('#home-search-open').click();
  await page.locator('#home-search-input').fill('Nexdata');
  await expect(page.locator('#home-search-results a').first()).toHaveAttribute('href','/company/org.nexdata/');
  await expect(page.locator('#home-search-more')).toHaveCount(1);
  await expect(page.locator('#home-search-results #home-search-more')).toHaveCount(0);
});

test('preceding homepage component remains usable with new markup and index', async ({ page }) => {
  await home(page, {oldComponent:true});
  await page.locator('#home-search-open').click();
  await page.locator('#home-search-input').fill('Scale AI');
  await expect(page.locator('#home-search-results a[href="/company/scale_ai/"]')).toBeVisible();
  await expect(page.locator('#home-search-more')).toBeHidden();
  await page.locator('#home-search-close').click();
  await expect(page.locator('#home-search-open')).toBeFocused();
});

test('new component installs behind the preceding runtime without another matcher request', async ({ page }) => {
  const requests=[];page.on('request', request=>requests.push(new URL(request.url()).pathname));
  await home(page, {oldRuntime:true,oldMarkup:true});
  await page.locator('#home-search-open').click();
  await page.locator('#home-search-input').fill('Outlier');
  await expect(page.locator('#home-search-results a').first()).toHaveAttribute('href','/company/scale_ai/');
  expect(requests.some(name=>/search-core|archive|summary|research\.json/.test(name))).toBe(false);
});

test('exact names and recorded aliases lead; paging reports the complete real total', async ({ page }) => {
  const entries=await home(page);await page.locator('#home-search-open').click();const input=page.locator('#home-search-input');
  for(const [query,href] of [['Outlier','/company/scale_ai/'],['Alignerr','/company/labelbox/'],['DataAnnotation','/company/surge_ai/'],['Mindrift','/company/toloka/'],['Nexdata','/company/org.nexdata/'],['Datasets','/research/datasets/']]){
    await input.fill(query);await expect(page.locator('#home-search-results a').first()).toHaveAttribute('href',href);
  }
  await input.fill('Outlier');await expect(page.locator('#home-search-results a').first()).toContainText('contributor brand');
  await input.fill('feedback');
  const count=entries.filter(row=>[row.name,row.summary,row.group,...row.products,...row.aliases].join(' ').toLowerCase().includes('feedback')).length;
  await expect(page.locator('#home-search-message')).toContainText(`Showing 7 of ${count}`);
  await expect(page.locator('#home-search-results [role=option]')).toHaveCount(8);
  while(await page.locator('#home-search-more').isVisible()) await page.locator('#home-search-more').click();
  await expect(page.locator('#home-search-results [role=option]')).toHaveCount(count+1);
  await expect(page.locator('#home-search-message')).toContainText(`Showing ${count} of ${count}`);
  await input.fill('Nexdata');await expect(page.locator('#home-search-more')).toBeHidden();
});

test('initial arrows, IME and literal native work transfer preserve keyboard behavior', async ({ page }) => {
  await home(page);await page.locator('#home-search-open').click();const input=page.locator('#home-search-input');
  await input.fill('human feedback');await input.press('ArrowUp');
  const options=page.locator('#home-search-results [role=option]');
  await expect(options.last()).toHaveAttribute('aria-selected','true');
  await input.press('ArrowDown');await expect(options.first()).toHaveAttribute('aria-selected','true');
  await input.dispatchEvent('keydown',{key:'ArrowUp',isComposing:true});await expect(options.first()).toHaveAttribute('aria-selected','true');
  await input.fill('C++');await expect(options.last()).toHaveAttribute('href','/work/?q=C%2B%2B');
  await input.press('Escape');await expect(page.locator('#home-search-open')).toBeFocused();
});

test('lightweight search prefills and removes only its parameter', async ({ page }) => {
  await home(page,{query:'?reader=keep&search=C%2B%2B#main'});
  await expect(page.locator('#home-search')).toBeVisible();await expect(page.locator('#home-search-input')).toHaveValue('C++');
  expect(new URL(page.url()).search).toBe('?reader=keep');expect(new URL(page.url()).hash).toBe('#main');
});

for(const routeName of ['companies','work']) for(const oldScript of [false,true]) {
  test(`${oldScript?'preceding':'new'} ${routeName} script accepts ${oldScript?'new':'old'} native markup`,async({page})=>{
    let html=previous(routeName+'.html.gz');
    html=html.replace(/<script\b[^>]*src="[^"]+"[^>]*><\/script>/g,'');
    await page.route(origin+'/**',route=>route.fulfill({contentType:'text/html',body:html}));await page.goto(origin+'/'+routeName+'/');
    if(oldScript) await page.evaluate(({companies,routeName})=>{
      if(routeName==='companies')for(const company of companies){const card=document.querySelector('[data-company="'+company.id+'"]');if(card){card.dataset.search+=' '+(company.aliases||[]).join(' ');card.dataset.searchName=company.name;card.dataset.searchAliases=JSON.stringify(company.aliases||[]);}}
      else {const script=document.createElement('script');script.id='work-search-aliases';script.type='application/json';script.textContent=JSON.stringify(Object.fromEntries(companies.map(company=>[company.id,company.aliases||[]])));document.body.append(script);}
    },{companies,routeName});
    await page.addScriptTag({content:oldScript?previous(routeName+'-page.js'):current(routeName+'-page.js')});
    const input=page.locator(routeName==='companies'?'#company-query':'[data-work-filters] input[name=q]');await expect(input).toBeVisible();
    await input.fill(oldScript&&routeName==='companies'?'Outlier':routeName==='companies'?'Scale AI':'Sage');
    const records=page.locator(routeName==='companies'?'.directory-company:visible':'[data-work-route]:visible');expect(await records.count()).toBeGreaterThan(0);
    if(routeName==='work') await page.locator('.work-page-filter-options').evaluate(node=>{node.open=true;});
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await expect(input).toHaveValue('');
    await expect(page.locator(routeName==='companies'?'[data-company]':'[data-work-route]')).toHaveCount(routeName==='companies'?53:135);
  });
}

test('stalled component recovery can close and retry without a late reopen', async ({ page }) => {
  await home(page);await page.clock.install();let stalled;
  const hold=route=>{stalled=route;};await page.route('**/home-search.js',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-message')).toContainText('Loading search');
  await page.clock.fastForward(15001);await expect(page.locator('[data-home-component-retry]')).toBeVisible();
  await expect(page.locator('#home-search-message a[href="/companies/"]')).toBeVisible();
  await page.locator('#home-search-close').click();await expect(page.locator('#home-search-open')).toBeFocused();
  await stalled.fulfill({contentType:'application/javascript',body:current('home-search.js')}).catch(()=>{});
  await expect(page.locator('#home-search')).not.toBeVisible();await page.unroute('**/home-search.js',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-results')).toBeVisible();
});

test('empty component load offers retry and native modifier navigation', async ({ page, context }) => {
  await home(page);const empty=route=>route.fulfill({contentType:'application/javascript',body:''});await page.route('**/home-search.js',empty);
  await page.locator('#home-search-open').click();await expect(page.locator('[data-home-component-retry]')).toBeVisible();
  await context.route(origin+'/companies/',route=>route.fulfill({contentType:'text/html',body:'<h1>Native companies fallback</h1>'}));
  const opened=context.waitForEvent('page');await page.locator('#home-search-message a[href="/companies/"]').click({modifiers:['ControlOrMeta']});
  const tab=await opened;await expect(tab).toHaveURL(origin+'/companies/');await expect(page.locator('#home-search')).toBeVisible();await tab.close();
  await page.unroute('**/home-search.js',empty);await page.locator('[data-home-component-retry]').click();await expect(page.locator('#home-search-results')).toBeVisible();
});


test('closing while the index is pending keeps late failure out of the closed dialog', async ({ page }) => {
  await home(page);let pending;
  const hold=route=>{pending=route;};await page.route('**/presentation/search.*.json',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-message')).toContainText('Loading the search index');
  await page.locator('#home-search-close').click();await pending.abort().catch(()=>{});
  await expect(page.locator('#home-search')).not.toBeVisible();await page.unroute('**/presentation/search.*.json',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-results')).toBeVisible();
});
