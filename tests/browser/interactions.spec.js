const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const canonical = require('../../data/canonical.json');
const workData = require('../../data/work-routes.json');

async function ready(page, hash = '#companies') {
  await page.goto('/explore/' + hash);
  await expect(page.locator('html')).toHaveAttribute('data-app', 'ready');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
}

async function openFilters(page) {
  const panel = page.locator('#work-view .responsive-filter-panel');
  if (!(await panel.evaluate(element => element.open))) await panel.locator('summary').click();
}

test.beforeEach(async ({ page, request }, info) => {
  const response = await request.get('/manifest.json');
  expect(response.ok()).toBeTruthy();
  const manifest = await response.json();
  expect(manifest.build_id).toMatch(/^[a-f0-9]{20}$/);
  await info.attach('artifact-identity.json', {
    body: Buffer.from(JSON.stringify({ buildId: manifest.build_id, editorialReleaseId: manifest.editorial_release_id, datasetVersion: manifest.dataset_version })),
    contentType: 'application/json',
  });
  const errors = [];
  const assetErrors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400 && /\/(?:assets|js|presentation)\//.test(new URL(response.url()).pathname)) assetErrors.push({ url: response.url(), status: response.status() });
  });
  info._runtimeErrors = errors;
  info._assetErrors = assetErrors;
});

test.afterEach(async ({}, info) => {
  expect(info._runtimeErrors || [], 'Unexpected browser runtime errors').toEqual([]);
  expect(info._assetErrors || [], 'Missing release assets').toEqual([]);
});

test('bootstrap network failure recovers through the explicit reload action', async ({ page }) => {
  let broken = true;
  await page.route('**/js/data.*.js', route => broken ? route.abort('failed') : route.continue());
  await page.goto('/explore/#work');
  await expect(page.locator('html')).toHaveAttribute('data-app', 'failed');
  await expect(page.locator('html')).toHaveAttribute('data-app-reason', 'script-network');
  await expect(page.locator('#app-failure')).toBeVisible();
  await expect(page.locator('#work-view')).not.toBeVisible();
  broken = false;
  await page.locator('#app-reload').click();
  await expect(page.locator('html')).toHaveAttribute('data-app', 'ready');
  await expect(page.locator('#work-cards [data-work-route]').first()).toBeVisible();
});

test('a stale application asset fails visibly instead of presenting an empty result', async ({ page }) => {
  await page.route('**/js/app.*.js', route => route.fulfill({ status: 200, contentType: 'application/javascript', body: "window.APP_BUILD_ID='stale-release';document.documentElement.dataset.app='ready';" }));
  await page.goto('/explore/#work');
  await expect(page.locator('html')).toHaveAttribute('data-app', 'failed');
  await expect(page.locator('html')).toHaveAttribute('data-app-reason', 'stale-bundle');
  await expect(page.locator('#app-failure')).toBeVisible();
  await expect(page.locator('#work-view')).not.toBeVisible();
});

test('compact work data preserves every selector and visible condition', async ({ page }) => {
  await ready(page, '#work');
  const original = require('../../data/work-routes.json').routes;
  const keys = ['id', 'company_id', 'role', 'route_kind', 'engagement_type', 'pay_terms', 'arrangements', 'pay_label', 'pay_basis', 'numeric_pay', 'status', 'geography', 'requirements', 'hours', 'duration', 'assessment'];
  const compact = await page.evaluate(keys => workRouteRows().map(route => Object.fromEntries(keys.map(key => [key, route[key] ?? null]))), keys);
  const expected = original.map(route => Object.fromEntries(keys.map(key => [key, route[key] ?? null])));
  expect(compact).toEqual(expected);
  const summary = await page.evaluate(() => summarizeWorkResults(workRouteRows()));
  expect(summary).toMatchObject({ total: 135, named: 56, programs: 22, careers: 23, outside: 11 });
  const sage = page.locator('[data-work-route="appen.work.sage-media"]');
  await expect(sage).toContainText('Terms checked 8 Nov 2026');
  await expect(sage.locator('.w4-conditions-column')).toContainText('Qualification tests and identity verification');
  const alternatives = await page.evaluate(() => workRouteRows().filter(route => route.status === 'historical' && ['terac.work.ml-scenarios', 'afterquery.work.senior-software-engineer-security-infrastructure'].includes(route.id)).map(route => ({ id: route.id, original: route.url, action: w4Destination(route), status: w4Status(route) })));
  expect(alternatives).toHaveLength(2);
  for (const item of alternatives) {
    expect(item.action.label).toBe('Browse current company careers');
    expect(item.action.url).not.toBe(item.original);
    expect(item.status).toBe('Past listing · page unavailable');
  }
});

test('deep directory and work routes do not request the unrelated overview product image', async ({ page }) => {
  const unrelated = [];
  const healthModules = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/imerit-exl-visual.png')) unrelated.push(request.url());
    if (/\/js\/health\.[^/]+\.js$/.test(new URL(request.url()).pathname)) healthModules.push(request.url());
  });
  for (const hash of ['#companies', '#work']) {
    await ready(page, hash);
    await page.waitForLoadState('networkidle');
    expect(unrelated, hash + ' requested an overview-only product image').toEqual([]);
    expect(healthModules, hash + ' requested an unnecessary profile financial module').toEqual([]);
    expect(await page.evaluate(() => typeof window.BusinessHealth)).toBe('undefined');
  }
});

test('thin directory renders financials without detail or search payloads and loads search only when needed', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await ready(page);
  const bootstrap = await page.evaluate(() => ({
    details: ['metrics', 'products', 'claims', 'sources', 'people', 'investors'].map(key => DATA[key].length),
    hydrated: window.COMPANY_CONTEXTS_READY.size,
  }));
  expect(bootstrap.details).toEqual([0, 0, 0, 0, 0, 0]);
  expect(bootstrap.hydrated).toBe(0);
  await expect(page.locator('[data-company-card="taskus"]')).toContainText('H1 2026');
  await expect(page.locator('[data-company-card="taskus"]')).toContainText('Whole company');
  expect(requests.filter(url => /\/presentation\/(company-|archive\.|overview\.|full-search\.)/.test(url))).toEqual([]);
  await page.locator('#search').fill('WorldSim');
  await expect(page.locator('[data-company-card="labelbox"]')).toBeVisible();
  await expect(page.locator('#result-count')).toHaveText('Showing 1 of 39 companies');
  expect(requests.filter(url => /\/presentation\/full-search\./.test(url))).toHaveLength(1);
  expect(await page.evaluate(() => DATA.products.length)).toBe(0);
});

test('pending global search keeps the latest query and closing it prevents a late reopen', async ({ page }) => {
  await ready(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/full-search.*.json', async route => { await gate; await route.continue(); });
  await page.locator('#site-search-open').click();
  await expect(page.locator('#site-search')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('#site-search-message')).toContainText('Loading search');
  await page.locator('#site-search-input').fill('Python');
  await page.locator('#site-search-close').click();
  release();
  await page.waitForFunction(() => Boolean(window.SEARCH_INDEX));
  await expect(page.locator('#site-search')).not.toBeVisible();
  await page.locator('#site-search-open').click();
  await expect(page.locator('#site-search-input')).toHaveValue('Python');
  await expect(page.getByRole('option', { name: /See all \d+ matches? for “Python”/ })).toBeVisible();
});

test('a failed deferred work search offers retry without claiming no matching records', async ({ page }) => {
  let blocked = true;
  await page.route('**/presentation/full-search.*.json', route => blocked ? route.abort('failed') : route.continue());
  await ready(page, '#work');
  await page.locator('#work-search').fill('Sage');
  await expect(page.locator('#work-count')).toHaveText('Search could not load.');
  await expect(page.locator('#work-cards')).not.toContainText('No listing mentions');
  await expect(page.locator('html')).toHaveAttribute('data-app', 'ready');
  blocked = false;
  await page.locator('[data-retry-work-search]').click();
  await expect(page.locator('[data-work-route="appen.work.sage-media"]')).toBeVisible();
  await expect(page.locator('#work-count')).toContainText('1 record');
});

test('a failed query deep link preserves its literal query and offers retry and plain work', async ({ page }) => {
  let blocked = true;
  await page.route('**/presentation/full-search.*.json', route => blocked ? route.abort('failed') : route.continue());
  await page.goto('/explore/#work?q=C%2B%2B');
  await expect(page.locator('html')).toHaveAttribute('data-view-reason', 'search-request');
  await expect(page.locator('#work-search')).toHaveValue('C++');
  expect(await page.evaluate(() => location.hash)).toBe('#work?q=C%2B%2B');
  await expect(page.locator('#work-cards')).not.toContainText('No recorded matches');
  await expect(page.locator('#work-cards a[href="/work/"]')).toBeVisible();
  blocked = false;
  await page.locator('[data-retry-search]').click();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#work-search')).toHaveValue('C++');
  expect(await page.evaluate(() => location.hash)).toBe('#work?q=C%2B%2B');
});

test('failed global search has working browse actions and can retry the deferred index', async ({ page }) => {
  let blocked = true;
  await page.route('**/presentation/full-search.*.json', route => blocked ? route.abort('failed') : route.continue());
  await ready(page);
  await page.locator('#site-search-open').click();
  await expect(page.locator('#site-search-message')).toContainText('Search could not load');
  await page.locator('#site-search-message a[href="#companies"]').click();
  await expect(page.locator('#site-search')).not.toBeVisible();
  await expect(page.locator('#companies-view')).toBeVisible();
  await page.locator('#site-search-open').click();
  await page.locator('#site-search-input').fill('Python');
  await expect(page.locator('#site-search-message')).toContainText('Search could not load');
  blocked = false;
  await page.locator('[data-retry-site-search]').click();
  await expect(page.getByRole('option', { name: /See all \d+ matches? for “Python”/ })).toBeVisible();
});

test('current company CSV uses the same financial observation as the visible card', async ({ page }) => {
  await ready(page);
  await page.locator('#search').fill('TaskUs');
  await expect(page.locator('#result-count')).toHaveText('Showing 1 of 39 companies');
  const card = page.locator('[data-company-card="taskus"]');
  await expect(card).toContainText('H1 2026');
  await expect(card).toContainText('Whole company');
  const selected = await page.evaluate(() => currentCompanyResult('taskus'));
  expect(selected).toMatchObject({ value: 615121000, period: 'H1 2026', scope: 'company' });
  await page.locator('a[href="#downloads"]').last().click();
  await expect(page.locator('#download-csv')).toBeVisible();
  const waiting = page.waitForEvent('download');
  await page.locator('#download-csv').click();
  const download = await waiting;
  const csv = require('node:fs').readFileSync(await download.path(), 'utf8');
  expect(csv).toContain('615121000');
  expect(csv).toContain('H1 2026');
  expect(csv).toContain('Whole company');
  expect(csv).toContain(selected.source_urls);
  expect(csv).not.toContain('214218000');
});

test('work CSV exports the current shared selection and its binding conditions', async ({ page }) => {
  await ready(page, '#work?q=Sage&kind=named');
  await openFilters(page);
  const count = await page.evaluate(() => filteredWork().length);
  expect(count).toBeGreaterThan(0);
  const waiting = page.waitForEvent('download');
  await page.locator('#work-export').click();
  const download = await waiting;
  const csv = require('node:fs').readFileSync(await download.path(), 'utf8');
  expect(csv).toContain('search_query');
  expect(csv).toContain('original_application_url');
  expect(csv).toContain('assessment');
  expect(csv).toContain('Sage');
  expect(csv).toMatch(/Up to \$15 \/ hour/);
  expect(csv).toContain('US residence');
  expect(csv).toContain('MacBook Pro');
  expect(csv).toContain('Qualification tests and identity verification');
  expect(csv).toContain('2026-11-08');
  expect(csv).toContain('key_terms');
  expect(csv.trim().split(/\r?\n/)).toHaveLength(count + 1);
});

test('all work criteria survive reload and Back/Forward', async ({ page }) => {
  await ready(page, '#work');
  await page.locator('#work-search').fill('C++ C# café 研究');
  await openFilters(page);
  await page.locator('#work-kind').selectOption('named');
  await page.locator('#work-group').selectOption('employment');
  await page.locator('#work-pay').selectOption('hourly');
  await page.locator('#work-eligibility').selectOption('onsite');
  await page.locator('#work-sort').selectOption('checked');
  await expect.poll(() => page.evaluate(() => location.hash)).toContain('sort=checked');
  const hash = await page.evaluate(() => location.hash);
  const count = await page.locator('#work-count').textContent();
  expect(new URLSearchParams(hash.split('?')[1]).get('q')).toBe('C++ C# café 研究');
  await page.reload();
  await expect(page.locator('#work-search')).toHaveValue('C++ C# café 研究');
  for (const [id, value] of [['work-kind', 'named'], ['work-group', 'employment'], ['work-pay', 'hourly'], ['work-eligibility', 'onsite'], ['work-sort', 'checked']]) {
    await expect(page.locator('#' + id)).toHaveValue(value);
  }
  await expect(page.locator('#work-count')).toHaveText(count);
  await page.locator('nav[aria-label="Main"] a[data-nav="companies"]').click();
  await expect(page.locator('#companies-view')).toBeVisible();
  await page.locator('nav[aria-label="Main"] a[data-nav="work"]').click();
  await expect(page.locator('#work-search')).toHaveValue('');
  await page.goBack();
  await expect(page.locator('#companies-view')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#work-search')).toHaveValue('C++ C# café 研究');
  await expect(page.locator('#work-count')).toHaveText(count);
});

test('suggested work counts and every provider use the approved primary scope', async ({ page }) => {
  await ready(page, '#work?q=Sage&kind=named');
  const counts = await page.evaluate(() => {
    const groups = w4DiscoveryGroups(workRouteRows());
    const ids = rows => rows.map(row => row.id);
    return {
      named: groups.named.length, programs: groups.programs.length,
      primary: ids(groups.primary), legacy: ids(w4RouteGroups(workRouteRows()).primary),
      overview: ids(storyWorkRows()), allRecords: workRouteRows().length,
      providers: new Set(groups.primary.map(row => row.company_id)).size,
      providerParity: DATA.companies.every(company => JSON.stringify(ids(workRouteSummary(company.id).primary).sort()) === JSON.stringify(ids(w4DiscoveryGroups(workRoutesFor(company.id)).primary).sort())),
    };
  });
  expect(counts.named).toBe(56);
  expect(counts.programs).toBe(22);
  expect(counts.primary).toHaveLength(78);
  expect([...counts.legacy].sort()).toEqual([...counts.primary].sort());
  expect(counts.overview).toEqual(counts.primary);
  expect(counts.providers).toBe(29);
  expect(counts.providerParity).toBe(true);
  expect(counts.allRecords).toBe(135);
  await page.locator('#site-search-open').click();
  await expect(page.getByRole('option', { name: /Paid work 56 named listings · 22 networks and programs/ })).toBeVisible();
  await page.locator('#site-search-close').click();
  await expect(page.locator('#work-search')).toHaveValue('Sage');
});

test('global search transfers the literal query and exact work selection', async ({ page }) => {
  await ready(page);
  await page.evaluate(() => window.ensureSearchContext?.());
  for (const query of ['C++', 'C#', 'café', '研究', 'Python']) {
    const parity = await page.evaluate(query => ({
      global: siteSearchWorkCount(query),
      destination: selectWorkRoutes(workRouteRows(), { q: query }).length,
      broad: siteSearchWorkCount('c'),
    }), query);
    expect(parity.global).toBe(parity.destination);
    if (['C++', 'C#'].includes(query)) expect(parity.global).toBeLessThan(parity.broad);
  }
  await page.locator('#site-search-open').click();
  const input = page.locator('#site-search-input');
  await expect(input).toBeFocused();
  await input.fill('Python');
  const option = page.getByRole('option', { name: /See all \d+ matches? for “Python”/ });
  await expect(option).toBeVisible();
  const total = Number((await option.textContent()).match(/See all (\d+)/)[1]);
  await option.click();
  await expect(page.locator('#site-search')).not.toBeVisible();
  await expect(page.locator('#work-search')).toHaveValue('Python');
  expect(await page.evaluate(() => filteredWork().length)).toBe(total);
  expect(new URLSearchParams((await page.evaluate(() => location.hash)).split('?')[1]).get('q')).toBe('Python');
});

test('malformed work links remain usable and canonical', async ({ page }) => {
  await ready(page, '#work?q=%E0%A4%A&kind=invalid&type=__proto__&pay=bogus&sort=invalid');
  await expect(page.locator('#work-view')).toBeVisible();
  for (const id of ['work-kind', 'work-group', 'work-pay', 'work-sort']) await expect(page.locator('#' + id)).toHaveValue('');
  await page.locator('#work-search').fill('remote');
  await expect.poll(() => page.evaluate(() => location.hash)).toBe('#work?q=remote');
});

test('legacy arrangement links cannot apply a filter absent from the visible select', async ({ page }) => {
  for (const arrangement of ['US listing evidence', 'not-an-arrangement']) {
    await ready(page, '#work?arrangement=' + encodeURIComponent(arrangement));
    await expect(page.locator('#work-eligibility')).toHaveValue('');
    expect(await page.evaluate(() => state.workEligibility)).toBe('');
    expect(await page.evaluate(() => filteredWork().length)).toBe(135);
    expect(await page.evaluate(() => location.hash)).toBe('#work');
  }
});

test('work-origin focus and criteria survive a company round trip', async ({ page }) => {
  await ready(page, '#work?q=Surge&kind=named');
  const origin = page.locator('#work-cards .w4-company').first();
  await origin.scrollIntoViewIfNeeded();
  const source = await origin.getAttribute('href');
  await origin.click();
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await page.goBack();
  await expect(page.locator('#work-search')).toHaveValue('Surge');
  await expect(page.locator('#work-kind')).toHaveValue('named');
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute('href'))).toBe(source);
});

test('a direct profile retains peer names and links without requesting their decorative logos', async ({ page }) => {
  const requested = [];
  page.on('request', request => requested.push(new URL(request.url()).pathname));
  await ready(page, '#company/mercor/work');
  await expect(page.locator('.profile-v2')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const peers = await page.evaluate(() => (MODEL_GROUPS[modelGroup('mercor')] || []).filter(id => id !== 'mercor').map(id => ({ id, name: companies[id].name, logo: logoFor(id)?.local_path })));
  expect(peers).toHaveLength(8);
  for (const peer of peers) {
    await expect(page.locator('.profile-peers a[href="#company/' + peer.id + '"]')).toHaveText(peer.name);
    if (peer.logo) expect(requested).not.toContain(new URL(peer.logo, 'http://localhost/').pathname);
  }
  await expect(page.locator('.profile-peers img')).toHaveCount(0);
  await expect(page.locator('.profile-title-row .profile-brand img')).toBeVisible();
  await expect(page.locator('.profile-peers-all')).toContainText('All 9 companies');
});

test('profile tabs keep keyboard focus visible after narrow reflow', async ({ page }) => {
  await ready(page, '#company/mercor/work');
  await expect(page.locator('.profile-v2')).toBeVisible();
  await page.setViewportSize({ width: 320, height: 225 });
  await page.locator('#profile-tab-business').focus();
  await page.keyboard.press('End');
  const tab = page.locator('#profile-tab-work');
  await expect(tab).toBeFocused();
  const visible = await tab.evaluate(element => {
    const box = element.getBoundingClientRect(), parent = element.parentElement.getBoundingClientRect();
    return box.left >= Math.max(0, parent.left) - 1 && box.right <= Math.min(innerWidth, parent.right) + 1 && box.top >= 0 && box.bottom <= innerHeight;
  });
  expect(visible).toBeTruthy();
  await expect(page.locator('#profile-pane-work')).toBeVisible();
  await expect(page.locator('#profile-pane-business')).not.toBeVisible();
});

test('slow stale company response cannot replace the new route', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/company-mercor*.json', async route => { await gate; await route.continue(); });
  await ready(page, '#work');
  await page.evaluate(() => { location.hash = '#company/mercor/work'; });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  await page.locator('nav[aria-label="Main"] a[data-nav="companies"]').click();
  release();
  await expect(page.locator('#companies-view')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#profile-view')).not.toBeVisible();
});

test('company detail failure provides retry and a readable fallback', async ({ page }) => {
  let broken = true;
  await page.route('**/company-mercor*.json', route => broken ? route.abort('failed') : route.continue());
  await page.goto('/explore/#company/mercor/work');
  await expect(page.getByRole('heading', { name: 'This company’s evidence could not load.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Read the plain company page' })).toHaveAttribute('href', '/company/mercor/');
  broken = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
});

for (const mode of ['network failure', 'integrity mismatch']) {
  test('the deferred financial module recovers from ' + mode + ' through the profile retry', async ({ page }) => {
    let broken = true;
    const healthRequests = [];
    page.on('request', request => { if (/\/js\/health\.[^/]+\.js$/.test(new URL(request.url()).pathname)) healthRequests.push(request.url()); });
    await page.route('**/js/health.*.js*', route => {
      if (!broken) return route.continue();
      return mode === 'network failure' ? route.abort('failed') : route.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.UNTRUSTED_HEALTH_EXECUTED=true;' });
    });
    await page.goto('/explore/#company/mercor/work');
    await expect(page.getByRole('heading', { name: 'This company’s evidence could not load.' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Read the plain company page' })).toHaveAttribute('href', '/company/mercor/');
    expect(await page.evaluate(() => window.UNTRUSTED_HEALTH_EXECUTED)).toBeUndefined();
    expect(await page.evaluate(() => window.APP_HEALTH_READY)).toBeUndefined();
    const failedRequestCount = healthRequests.length;
    broken = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.locator('.profile-v2')).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    expect(await page.evaluate(() => window.APP_HEALTH_READY)).toBe(await page.evaluate(() => window.APP_BUILD_ID));
    expect(healthRequests.length).toBeGreaterThan(failedRequestCount);
    expect(new URL(healthRequests.at(-1)).pathname).toBe(new URL(healthRequests[0]).pathname);
    expect(new URL(healthRequests.at(-1)).searchParams.get('s2s_retry')).toMatch(/^\d+$/);
    const descriptor = await page.evaluate(() => window.SUMMARY_INDEX.modules.businessHealth);
    await expect(page.locator('script[data-presentation-module="business-health"]')).toHaveAttribute('integrity', descriptor.integrity);
  });
}

test('a delayed financial module can finish off-route without restoring a stale profile', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/js/health.*.js*', async route => { await gate; await route.continue(); });
  await ready(page, '#work');
  await page.evaluate(() => { location.hash = '#company/mercor/work'; });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  await page.locator('nav[aria-label="Main"] a[data-nav="companies"]').click();
  release();
  await page.waitForFunction(() => window.APP_HEALTH_READY === window.APP_BUILD_ID);
  await expect(page.locator('#companies-view')).toBeVisible();
  await expect(page.locator('#profile-view')).not.toBeVisible();
  expect(await page.evaluate(() => location.hash)).toBe('#companies');
  await page.evaluate(() => { location.hash = '#company/mercor/work'; });
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(page.locator('#profile-pane-work')).toBeVisible();
});

test('an initially stalled financial module reaches its deadline and can retry', async ({ page }) => {
  let blocked = true;
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/js/health.*.js*', async route => { if (blocked) await gate; await route.continue(); });
  await page.clock.install();
  await page.goto('/explore/#company/mercor/work', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  await expect(page.locator('script[data-presentation-module="business-health"]')).toHaveCount(1);
  await page.clock.fastForward(15_001);
  await expect(page.getByRole('heading', { name: 'This company’s evidence could not load.' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-reason', 'evidence-timeout');
  await expect(page.getByRole('link', { name: 'Read the plain company page' })).toHaveAttribute('href', '/company/mercor/');
  blocked = false;
  release();
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  expect(await page.evaluate(() => window.APP_HEALTH_READY)).toBe(await page.evaluate(() => window.APP_BUILD_ID));
});

test('the evidence API immediately offers loading and a plain-page fallback while its context is pending', async ({ page }) => {
  await ready(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/company-*.json', async route => { await gate; await route.continue(); });
  const claim = canonical.metrics[0].claim_id;
  await page.evaluate(id => showEvidence(id), claim);
  try {
    await expect(page.locator('#evidence-dialog')).toBeVisible({ timeout: 1_000 });
    await expect(page.locator('#evidence-content')).toContainText(/Loading/i);
    await expect(page.locator('#evidence-content a[href^="/company/"]')).toBeVisible();
  } finally {
    release();
  }
});

test('closing a pending source dialog prevents the eventual response reopening it', async ({ page }) => {
  await ready(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/company-*.json', async route => { await gate; await route.continue(); });
  const record = { id: canonical.metrics[0].claim_id, company: canonical.metrics[0].company_id };
  await page.evaluate(id => showEvidence(id), record.id);
  await expect(page.locator('#evidence-dialog')).toBeVisible();
  await page.locator('#close-evidence').click();
  release();
  await page.waitForFunction(company => detailCache.has(company), record.company);
  await expect(page.locator('#evidence-dialog')).not.toBeVisible();
  await expect(page.locator('#evidence-dialog')).not.toHaveAttribute('aria-busy', 'true');
});

test('an initially stalled profile times out with a plain-page fallback and recovers on retry', async ({ page }) => {
  let blocked = true;
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/company-mercor.*.json', async route => { if (blocked) await gate; await route.continue(); });
  await page.clock.install();
  await page.goto('/explore/#company/mercor/work');
  await page.clock.runFor(2_000);
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  await page.clock.fastForward(15_001);
  await expect(page.getByRole('heading', { name: 'This company’s evidence could not load.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Read the plain company page' })).toHaveAttribute('href', '/company/mercor/');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'failed');
  await expect(page.locator('html')).toHaveAttribute('data-view-reason', 'evidence-timeout');
  blocked = false;
  release();
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
});

test('a stalled initial profile reserves the viewport and keeps the footer below it', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/company-mercor.*.json', async route => { await gate; await route.continue(); });
  await page.goto('/explore/#company/mercor/work');
  const profile = page.locator('#profile-view');
  await expect(profile).toBeVisible();
  await expect(profile).toHaveAttribute('aria-busy', 'true');
  try {
    const layout = await profile.evaluate(element => ({
      height: element.getBoundingClientRect().height,
      viewport: innerHeight,
      footerTop: document.querySelector('footer').getBoundingClientRect().top,
    }));
    expect(layout.height).toBeGreaterThanOrEqual(layout.viewport - 1);
    expect(layout.footerTop).toBeGreaterThanOrEqual(layout.viewport - 1);
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  } finally {
    release();
  }
  await expect(page.locator('.profile-v2')).toBeVisible();
  await expect(profile).not.toHaveAttribute('aria-busy', 'true');
});

test('named terms become overdue at the fourteenth UTC day and failed checks do not refresh them', async ({ page }) => {
  const sage = workData.routes.find(route => route.id === 'appen.work.sage-media');
  const review = sage.editorial_review.receipts.find(receipt => receipt.id === sage.editorial_review.approved_terms_receipt_id);
  const reviewed = Date.parse(review.checked_on + 'T00:00:00Z'), day = 86_400_000;
  await page.clock.setFixedTime(new Date(reviewed + 14 * day - 1));
  await ready(page, '#work?q=Sage&kind=named');
  let card = page.locator('#work-cards [data-work-route="appen.work.sage-media"]');
  await expect(card.locator('[data-work-review-age="needs_recheck"]')).toHaveCount(0);
  await page.clock.setFixedTime(new Date(reviewed + 14 * day));
  await page.reload();
  card = page.locator('#work-cards [data-work-route="appen.work.sage-media"]');
  await expect(card.locator('[data-work-review-age="needs_recheck"]')).toHaveText('Needs recheck');
  await page.evaluate(() => {
    const route = workRouteRows().find(route => route.id === 'appen.work.sage-media');
    route.editorial_review.receipts.push({ id: 'test-failed-check', checked_on: new Date().toISOString().slice(0, 10), scope: 'key_terms', result: 'blocked', approved: false });
    renderWork();
  });
  await expect(card.locator('[data-work-review-age="needs_recheck"]')).toHaveText('Needs recheck');
  await expect(card.locator('.w4-dates')).toContainText('Terms checked 8 Nov 2026');
  expect(await page.evaluate(() => w4TermsAge(workRouteRows().find(route => route.id === 'appen.work.sage-media')).reviewed_on)).toBe(review.checked_on);
});

test('an unknown malformed route loads authoritative overview counts which remain stable after company hydration', async ({ page }) => {
  await page.goto('/explore/#unknown%ZZ?q=%E0%A4%A');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await page.getByText('How we check the research', { exact: true }).click();
  await expect(page.locator('#overview-check')).toBeVisible();
  expect(await page.evaluate(() => location.hash)).toBe('#market');
  const current = canonical.claims.filter(claim => claim.status !== 'superseded').length.toLocaleString('en-US');
  await expect(page.locator('#overview-check')).toContainText(current + ' current claims, by grade');
  await expect(page.locator('#overview-check')).toContainText(canonical.sources.length.toLocaleString('en-US') + ' source records');
  const original = await page.locator('#overview-check').textContent();
  await page.evaluate(() => { location.hash = '#company/appen/work'; });
  await expect(page.locator('.profile-v2')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#overview-check')).toBeVisible();
  await expect(page.locator('#overview-check')).toHaveText(original);
});

test('static work and company evidence remain available without JavaScript', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL });
  const page = await context.newPage();
  await page.goto('/work/');
  await expect(page.locator('h1')).toBeVisible();
  await expect(page.locator('a[href^="https://"]').first()).toBeVisible();
  await page.goto('/company/mercor/');
  await expect(page.locator('h1')).toContainText('Mercor');
  await page.goto('/explore/#work');
  await expect(page.getByRole('heading', { name: 'ScienceToStartup: the AI data field guide' })).toBeVisible();
  const exports = await page.locator('noscript a[download]').evaluateAll(links => links.map(link => link.href));
  expect(exports.length).toBeGreaterThan(0);
  for (const url of exports) {
    expect(new URL(url).pathname).not.toMatch(/^\/explore\//);
    expect((await context.request.head(url)).ok()).toBeTruthy();
  }
  await context.close();
});

test('the refined company and work views have no serious automated accessibility findings', async ({ page }) => {
  for (const hash of ['#companies', '#work', '#company/mercor/work']) {
    await ready(page, hash);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(result.violations.filter(issue => ['serious', 'critical'].includes(issue.impact)), hash).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), hash + ' page overflow').toBeTruthy();
  }
});
