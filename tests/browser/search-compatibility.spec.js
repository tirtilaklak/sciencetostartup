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
async function home(page, { oldMarkup = false, oldIndex = false, oldComponent = false, oldRuntime = false, query = '', fixtureOrigin = origin } = {}) {
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
  await page.route(fixtureOrigin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/') return route.fulfill({contentType:'text/html', body:html});
    if (pathname === '/home-runtime.js') return route.fulfill({contentType:'application/javascript', body:oldRuntime ? previous('home-runtime.js') : read('web/home-runtime.js')});
    if (pathname === '/home-search.js') return route.fulfill({contentType:'application/javascript', body:oldComponent ? previous('home-search.js') : current('home-search.js')});
    if (pathname === config.search.href) return route.fulfill({contentType:'application/json', body:payload});
    return route.fulfill({status:200, body:''});
  });
  await page.goto(fixtureOrigin + '/' + query);
  return entries;
}

test('new homepage component accepts old markup and old index without optional aliases', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await home(page, {oldMarkup:true,oldIndex:true});
  await page.locator('#home-search-open').click();
  await page.locator('#home-search-input').fill('Nexdata');
  await expect(page.locator('#home-search-results a').first()).toHaveAttribute('href','/company/org.nexdata/');
  await expect(page.locator('#home-search-more')).toHaveCount(1);
  await expect(page.locator('#home-search-results #home-search-more')).toHaveCount(0);
  expect(errors).toEqual([]);
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
  await input.fill('Nexdata');
  const resetCount=entries.filter(row=>[row.name,row.summary,row.group,...row.products,...row.aliases].join(' ').toLowerCase().includes('nexdata')).length;
  await expect(page.locator('#home-search-message')).toContainText(`Showing ${Math.min(7,resetCount)} of ${resetCount}`);
  await expect(page.locator('#home-search-results [role=option]')).toHaveCount(Math.min(7,resetCount)+1);
  await expect(page.locator('#home-search-more')).toBeVisible({visible:resetCount>7});
  await input.fill('s2s-no-record-987654321');
  await expect(page.locator('#home-search-message')).toContainText('No recorded guide matches');
  await expect(page.locator('#home-search-more')).toBeHidden();
  await expect(page.locator('#home-search-results [role=option]')).toHaveCount(1);
});

test('initial arrows, IME and literal native work transfer preserve keyboard behavior', async ({ page }) => {
  await home(page);await page.locator('#home-search-open').click();const input=page.locator('#home-search-input');
  await input.fill('human feedback');
  const options=page.locator('#home-search-results [role=option]');
  await expect(options.last()).toHaveAttribute('href','/work/?q=human+feedback');
  await expect(options.last()).toBeVisible();
  await input.press('ArrowUp');
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
  test(`${oldScript?'preceding':'new'} ${routeName} script accepts ${oldScript?'new':'old'} native markup`,async({page,request})=>{
    const pagePath = '/'+routeName+'/';
    let html;
    if (oldScript) {
      const response = await request.get(pagePath);
      expect(response.ok()).toBe(true);
      html = await response.text();
    } else html = previous(routeName+'.html.gz');
    html = html.replace(/<script\b(?![^>]*\btype="application\/(?:ld\+)?json")[^>]*>[\s\S]*?<\/script>/g,'');
    const legacyWork = routeName === 'work' && !oldScript;
    await page.route(origin+'/**',route=>route.fulfill({contentType:'text/html',body:html}));
    await page.goto(origin+pagePath+(legacyWork?'?reader=keep&pay=hourly#main':''));
    const recordOrder = () => page.locator('[data-work-route]').evaluateAll(cards => cards.map(card => card.dataset.workRoute));
    const originalOrder = legacyWork ? await recordOrder() : [];
    const originalCount = legacyWork ? await page.locator('[data-work-count]').textContent() : '';
    let source = oldScript?previous(routeName+'-page.js'):current(routeName+'-page.js');
    if (legacyWork) {
      const packaged = await request.get('/work-page.js');
      expect(packaged.ok()).toBe(true);
      source = await packaged.text();
    }
    await page.addScriptTag({content:source});
    const input=page.locator(routeName==='companies'?'#company-query':'[data-work-filters] input[name=q]');await expect(input).toBeVisible();
    await input.fill(oldScript&&routeName==='companies'?'Outlier':routeName==='companies'?'Scale AI':'Sage');
    const records=page.locator(routeName==='companies'?'.directory-company:visible':'[data-work-route]:visible');expect(await records.count()).toBeGreaterThan(0);
    if (routeName === 'companies') await expect(page.locator('.directory-company[data-company="scale_ai"]')).toBeVisible();
    if (oldScript && routeName === 'work') {
      const sage = page.locator('[data-work-group="closed"] [data-work-route="appen.work.sage-media"]');
      await expect(sage).toBeVisible();
      await expect(sage).toContainText('MacBook Pro');
    }
    if(routeName==='work') await page.locator('.work-page-filter-options').evaluate(node=>{node.open=true;});
    if (legacyWork) {
      const sage = page.locator('[data-work-group="named"] [data-work-route="appen.work.sage-media"]');
      await expect(sage).toBeVisible();
      await expect(sage).toContainText('MacBook Pro');
      await page.locator('[data-work-filters] select[name=arrangement]').selectOption('onsite');
      await expect(sage).toBeHidden();
    }
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await expect(input).toHaveValue('');
    await expect(page.locator(routeName==='companies'?'[data-company]':'[data-work-route]')).toHaveCount(routeName==='companies'?(oldScript?55:53):135);
    if (legacyWork) {
      await expect(input).toBeFocused();
      await expect(page).toHaveURL(origin+'/work/?reader=keep&pay=hourly#main');
      await expect(page.locator('[data-work-count]')).toHaveText(originalCount);
      expect(await recordOrder()).toEqual(originalOrder);
    }
  });
}

test('stalled component recovery can close and retry without a late reopen', async ({ page }) => {
  await home(page);await page.clock.install();let stalled;
  const hold=route=>{stalled=route;};await page.route('**/home-search.js',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-message')).toContainText('Loading search');
  await page.clock.fastForward(15001);await expect(page.locator('[data-home-component-retry]')).toBeVisible();
  const browse = page.locator('#home-search').getByRole('link', { name: 'Browse companies' });
  await expect(browse).toBeVisible();
  await expect(browse).toHaveAttribute('href','/companies/');
  await page.locator('#home-search-close').click();await expect(page.locator('#home-search-open')).toBeFocused();
  await stalled.fulfill({contentType:'application/javascript',body:current('home-search.js')}).catch(()=>{});
  await expect(page.locator('#home-search')).not.toBeVisible();await page.unroute('**/home-search.js',hold);
  await page.locator('#home-search-open').click();await expect(page.locator('#home-search-results')).toBeVisible();
});

test('empty component load offers retry and native modifier navigation', async ({ page, context, baseURL }) => {
  // WebKit's first native popup request can precede request interception. Use
  // the real artifact origin so the unmodified relative fallback also resolves.
  const fixtureOrigin=new URL(baseURL).origin;
  await home(page,{fixtureOrigin});const empty=route=>route.fulfill({contentType:'application/javascript',body:''});await page.route('**/home-search.js',empty);
  await page.locator('#home-search-open').click();await expect(page.locator('[data-home-component-retry]')).toBeVisible();
  const fallback=page.locator('#home-search').getByRole('link',{name:'Browse companies'});await expect(fallback).toHaveAttribute('href','/companies/');
  const opened=context.waitForEvent('page');await fallback.click({modifiers:['ControlOrMeta']});
  const tab=await opened;await expect(tab).toHaveURL(fixtureOrigin+'/companies/');
  await expect(tab.getByRole('heading',{level:1})).toHaveText('AI data companies');
  await expect(page.locator('#home-search')).toBeVisible();await tab.close();
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
