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

for(const [routeName, oldScript] of [['companies',false],['companies',true],['work',true]]) {
  test(`${oldScript?'preceding':'new'} ${routeName} script accepts ${oldScript?'new':'old'} native markup`,async({page,request})=>{
    const pagePath = '/'+routeName+'/';
    let html;
    if (oldScript) {
      const response = await request.get(pagePath);
      expect(response.ok()).toBe(true);
      html = await response.text();
    } else html = previous(routeName+'.html.gz');
    // This isolates the markup contract. The native loader test below uses the delivered HTML unchanged.
    html = html.replace(/<script\b(?![^>]*\btype="application\/(?:ld\+)?json")[^>]*>[\s\S]*?<\/script>/g,'');
    await page.route(origin+'/**',route=>route.fulfill({contentType:'text/html',body:html}));
    await page.goto(origin+pagePath);
    const source = oldScript?previous(routeName+'-page.js'):current(routeName+'-page.js');
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
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await expect(input).toHaveValue('');
    await expect(page.locator(routeName==='companies'?'[data-company]':'[data-work-route]')).toHaveCount(routeName==='companies'?(oldScript?55:53):135);
  });
}

test('new work script accepts old native markup', async ({ page }) => {
  const html = previous('work.html.gz');
  const originalOrder = [...html.matchAll(/data-work-route="([^"]+)"/g)].map(([, id]) => id);
  const originalCount = html.match(/<p [^>]*data-work-count[^>]*>([^<]+)<\/p>/)[1];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(url => url.pathname === '/work/', route => route.fulfill({ contentType: 'text/html', body: html }));

  const packaged = page.waitForResponse(response => new URL(response.url()).pathname === '/work-page.js');
  await page.goto('/work/?reader=keep&pay=hourly&q=Sage#main');
  expect((await packaged).ok()).toBe(true);
  const records = page.locator('[data-work-route]');
  const input = page.locator('[data-work-filters] input[name=q]');
  const sage = page.locator('[data-work-group="named"] [data-work-route="appen.work.sage-media"]');
  await expect(input).toBeVisible();
  await expect(input).toHaveValue('Sage');
  await expect(sage).toBeVisible();
  await expect(sage).toContainText('MacBook Pro');
  await page.locator('.work-page-filter-options').evaluate(node => { node.open = true; });
  await page.locator('[data-work-filters] select[name=arrangement]').selectOption('onsite');
  await expect(sage).toBeHidden();

  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(input).toHaveValue('');
  await expect(input).toBeFocused();
  await expect(page).toHaveURL(/\/work\/\?reader=keep&pay=hourly#main$/);
  await expect(page.locator('[data-work-count]')).toHaveText(originalCount);
  await expect(records).toHaveCount(135);
  expect(await records.evaluateAll(cards => cards.map(card => card.dataset.workRoute))).toEqual(originalOrder);
  expect(errors).toEqual([]);
});

async function pauseWorkDocument(page) {
  const parserBlock = '/qa-work-document-pause.js';
  const { promise: paused, resolve: resume } = Promise.withResolvers();
  await page.route('**' + parserBlock, async route => {
    await paused;
    await route.fulfill({ contentType: 'text/javascript', body: '' });
  });
  await page.route(url => url.pathname === '/work/', async route => {
    // This fixture edits HTML. Playwright fetch may expose raw zstd when Firefox negotiates it.
    const response = await route.fetch({ headers: { ...route.request().headers(), 'accept-encoding': 'identity' } });
    expect(response.ok()).toBe(true);
    const html = await response.text();
    expect(html).toContain('</head>');
    const body = html.replace('</head>', '<script src="' + parserBlock + '"></script></head>');
    const headers = response.headers();
    for (const name of ['content-encoding', 'content-length', 'transfer-encoding']) delete headers[name];
    await route.fulfill({ response, headers, body });
  });
  return resume;
}

test('native Work applies its saved filter when the bundle arrives before slow HTML finishes', async ({ page }) => {
  const resume = await pauseWorkDocument(page);
  // Network setup can take longer than the timer on a busy Firefox runner.
  // Start the simulated delay only after the real bundle has executed.
  await page.clock.install({ time: new Date('2026-11-22T09:00:00Z') });
  await page.clock.pauseAt(new Date('2026-11-22T09:01:00Z'));
  await page.addInitScript(() => {
    const observer = new MutationObserver(changes => {
      for (const change of changes) {
        for (const node of change.addedNodes) {
          if (node instanceof HTMLScriptElement && /\/js\/work\.[0-9a-f]+\.js$/.test(node.src)) {
            node.addEventListener('load', () => { window.workBundleReadyState = document.readyState; });
            observer.disconnect();
          }
        }
      }
    });
    observer.observe(document, { childList: true, subtree: true });
  });
  try {
    await page.goto('/work/?q=Sage', { waitUntil: 'commit' });
    await expect.poll(() => page.evaluate(() => window.workBundleReadyState)).toBe('loading');
    await page.clock.fastForward(4000);
  } finally {
    resume();
  }
  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByRole('searchbox', { name: 'Search listings' })).toHaveValue('Sage');
  await expect(page.locator('.work-page-list [data-work-route]:visible')).toHaveAttribute('data-work-route', 'appen.work.sage-media');
  await expect(page.locator('[data-work-retry]')).toBeHidden();
});

test('native Work keeps the downloaded bundle when slow HTML delays its execution', async ({ page }) => {
  const resume = await pauseWorkDocument(page);
  const executionBlock = '/qa-work-execution-pause.js';
  const { promise: blocked, resolve: unblock } = Promise.withResolvers();
  await page.clock.install({ time: 0 });
  await page.clock.pauseAt(60_000);
  await page.route('**' + executionBlock, async route => {
    await blocked;
    await route.fulfill({ contentType: 'text/javascript', body: '' });
  });
  await page.addInitScript(block => {
    const append = Element.prototype.append;
    Element.prototype.append = function (...nodes) {
      const [script] = nodes;
      if (this === document.head && script instanceof HTMLScriptElement && script.src.includes('/js/work.')) {
        // Fetch the actual SRI bundle even if the browser queues the ordered scripts together.
        const preload = document.createElement('link');
        preload.rel = 'preload';
        preload.as = 'script';
        preload.href = script.src;
        preload.integrity = script.integrity;
        append.call(this, preload);

        const first = document.createElement('script');
        first.async = false;
        first.src = block;
        append.call(this, first);
        script.async = false;
      }
      append.apply(this, nodes);
    };
  }, executionBlock);

  try {
    const response = page.waitForResponse(response => /\/js\/work\.[a-f0-9]{12}\.js$/.test(response.url()));
    await page.goto('/work/?q=Sage', { waitUntil: 'commit' });
    const downloaded = await response;
    expect(downloaded.ok()).toBe(true);
    expect(await downloaded.finished()).toBeNull();

    await page.clock.fastForward(4000);
    expect(await page.evaluate(() => {
      const script = document.querySelector('script[src^="/js/work."]');
      return {
        document: document.readyState,
        state: document.documentElement.dataset.workLoad,
        active: Boolean(script && window.WorkPageResource.accepts(script)),
        executed: Boolean(window.WORK_NATIVE_SELECTION),
      };
    })).toEqual({ document: 'loading', state: 'pending', active: true, executed: false });
  } finally {
    resume();
    unblock();
  }

  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByRole('searchbox', { name: 'Search listings' })).toHaveValue('Sage');
  await expect(page.locator('.work-page-list [data-work-route]:visible')).toHaveAttribute('data-work-route', 'appen.work.sage-media');
  await expect(page.locator('[data-work-retry]')).toBeHidden();
});

test('native work rejects a stale script and restores the selected record and CSV after retry', async ({ page, request }) => {
  test.setTimeout(45_000);
  const sageId = 'appen.work.sage-media';
  const attempts = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.workScriptAttempts = [];
    new MutationObserver(changes => {
      for (const change of changes) {
        if (change.target !== document.head) continue;
        for (const node of change.addedNodes) {
          const src = node instanceof HTMLScriptElement && node.getAttribute('src');
          if (src && /^\/js\/work\.[a-f0-9]{12}\.js/.test(src)) {
            window.workScriptAttempts.push({ src, integrity: node.integrity });
          }
        }
      }
    }).observe(document, { childList: true, subtree: true });
  });
  await page.route(url => /^\/js\/work\.[a-f0-9]{12}\.js$/.test(url.pathname), async route => {
    attempts.push(new URL(route.request().url()));
    if (attempts.length === 1) {
      // A late response gives the stale enhancer a chance to see the parsed form.
      await page.locator('[data-work-filters]').waitFor({ state: 'attached' });
      await route.fulfill({ contentType: 'application/javascript', body: previous('work-page.js') });
    } else if (attempts.length === 2) await route.abort('failed');
    else await route.continue();
  });

  const retry = page.getByRole('button', { name: 'Retry filters', exact: true });
  const exportButton = page.locator('[data-work-export]');
  const readWork = () => page.evaluate(() => {
    const retry = document.querySelector('[data-work-retry]');
    const input = document.querySelector('[data-work-filters] input[name=q]');
    const message = document.querySelector('[data-work-load-message]');
    const groups = [...document.querySelectorAll('[data-work-group]:not([hidden])')];
    const records = [...document.querySelectorAll('[data-work-group]:not([hidden]) [data-work-route]:not([hidden])')];
    const visible = node => !!node.getClientRects().length && getComputedStyle(node).visibility === 'visible';
    return {
      url: location.pathname + location.search,
      load: document.documentElement.dataset.workLoad || 'ready',
      message: visible(message) ? message.textContent : '',
      count: document.querySelector('[data-work-count]').textContent,
      query: input.value,
      groups: groups.map(node => node.dataset.workGroup),
      records: records.length,
      selectedId: records.length === 1 && visible(records[0]) ? records[0].dataset.workRoute : null,
      listVisible: visible(document.querySelector('.work-page-list')),
      filterVisible: visible(input),
      exportVisible: visible(document.querySelector('[data-work-export]')),
      retryVisible: visible(retry),
      inputFocused: document.activeElement === input,
      retryFocused: document.activeElement === retry,
    };
  });
  const fallback = {
    url: '/work/?q=Sage',
    load: 'failed',
    message: 'Filters did not load. Showing the full directory.',
    groups: ['named', 'programs', 'boards', 'outside', 'closed'],
    records: 135,
    listVisible: true,
    filterVisible: false,
    exportVisible: false,
    retryVisible: true,
  };

  await page.goto('/work/?q=Sage');
  await expect.poll(readWork).toMatchObject(fallback);
  expect(attempts).toHaveLength(1);
  await retry.focus();
  await page.keyboard.press('Enter');
  await expect.poll(readWork).toMatchObject({ ...fallback, retryFocused: true });
  expect(attempts).toHaveLength(2);
  await retry.click();

  await expect.poll(readWork).toMatchObject({
    url: '/work/?q=Sage', load: 'ready', message: '', count: '1 matching record', query: 'Sage',
    records: 1, selectedId: sageId, filterVisible: true, inputFocused: true, exportVisible: true,
  });

  const waiting = page.waitForEvent('download');
  await exportButton.click();
  const download = await waiting;
  expect(download.suggestedFilename()).toBe('sciencetostartup-current-work-results.csv');
  const csv = fs.readFileSync(await download.path(), 'utf8');
  const [header, row, ...extraRows] = csv.trim().split(/\r?\n/);
  expect(header).toMatch(/^"route_id","company","role",/);
  expect(extraRows).toEqual([]);
  expect(row).toMatch(/^"appen\.work\.sage-media","Appen","Sage media-quality evaluator",/);
  expect(row).toContain(',"Sage",');
  expect(row).toContain('MacBook Pro');

  expect(attempts).toHaveLength(3);
  const packaged = await request.get(attempts[0].pathname);
  expect(packaged.ok()).toBe(true);
  const digest = createHash('sha256').update(await packaged.body()).digest();
  const asset = `/js/work.${digest.toString('hex').slice(0, 12)}.js`;
  expect(attempts.map(url => url.pathname)).toEqual([asset, asset, asset]);
  expect(attempts.map(url => url.search)).toEqual(['', expect.stringMatching(/^\?s2s_retry=1-\d+$/), expect.stringMatching(/^\?s2s_retry=2-\d+$/)]);
  const integrity = `sha256-${digest.toString('base64')}`;
  expect(await page.evaluate(() => window.workScriptAttempts)).toEqual(attempts.map(url => ({ src: url.pathname + url.search, integrity })));
  expect(errors).toEqual([]);
});

const sageWorkId = 'appen.work.sage-media';
for (const [bookmark, recordId] of [['excluded', 'mercor.work.company-careers'], ['matching', sageWorkId]]) {
  test(`native work keyboard retry restores visible focus for ${bookmark} bookmarks`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await page.route(url => /^\/js\/work\.[a-f0-9]{12}\.js$/.test(url.pathname), route => route.abort('connectionrefused'), { times: 1 });

    const url = `/work/?reader=keep&q=Sage#${recordId}`;
    const record = page.locator(`[data-work-route="${recordId}"]`);
    const search = page.getByRole('searchbox', { name: 'Search listings', exact: true });
    const retry = page.getByRole('button', { name: 'Retry filters', exact: true });
    await page.goto(url);
    await expect(retry).toBeVisible();
    await expect(record).toBeVisible();
    await retry.focus();
    await page.keyboard.press('Enter');

    await expect(retry).toBeHidden();
    await expect(search).toHaveValue('Sage');
    await expect(page.locator('[data-work-count]')).toHaveText('1 matching record');
    const results = page.locator('[data-work-route]:visible');
    expect(await results.evaluateAll(cards => cards.map(card => card.dataset.workRoute))).toEqual([sageWorkId]);
    await expect(page).toHaveURL(url);
    if (recordId === sageWorkId) {
      await expect(record).toBeFocused();
      await expect(record).toBeInViewport();
    } else {
      await expect(record).toBeHidden();
      await expect(search).toBeFocused();
      await expect(search).toBeInViewport({ ratio: 1 });
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
