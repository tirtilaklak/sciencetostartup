const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const release = require('../../data/editorial-release.json');
const work = require('../../data/work-routes.json');
const sage = work.routes.find(row => row.id === 'appen.work.sage-media');
const approved = sage.editorial_review.receipts.find(row => row.id === sage.editorial_review.approved_terms_receipt_id);
const reviewed = Date.parse(approved.checked_on + 'T00:00:00Z');
const day = 86_400_000;

test('home promotes only approved current terms and retains all binding conditions', async ({ page }) => {
  await page.clock.setFixedTime(new Date(reviewed + day));
  await page.goto('/');
  const example = page.locator('#home-work-example');
  await expect(example.locator('[data-home-route]')).toHaveAttribute('data-home-route', sage.id);
  for (const text of ['15', 'US', 'MacBook Pro', 'qualification', 'identity']) {
    await expect(example).toContainText(new RegExp(text, 'i'));
  }
  await expect(page.locator('.example-grid article')).toHaveCount(2);
  await expect(page.getByRole('link', { name: 'Explore companies' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Find paid work', exact: true })).toBeVisible();
});

test('three-day expiry withdraws stale examples and preserves evergreen browse', async ({ page }) => {
  await page.clock.setFixedTime(new Date(reviewed + (release.publication_policy.homepage_work_max_age_days + 1) * day));
  await page.goto('/');
  await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(0);
  await expect(page.locator('#home-work-example').getByRole('link', { name: 'Browse paid work' })).toBeVisible();
  await expect(page.locator('.example-grid article')).toHaveCount(2);
});

test('without JavaScript the homepage offers evergreen work and company links', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(0);
  await expect(page.locator('#home-work-example').getByRole('link', { name: 'Browse paid work' })).toHaveAttribute('href', '/work/');
  await expect(page.getByRole('link', { name: 'Explore companies' })).toHaveAttribute('href', '/companies/');
  await expect(page.locator('.example-grid article')).toHaveCount(2);
  await context.close();
});

test('homepage Search loads only its small component and index when invoked', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto('/');
  await expect(page.locator('#home-search')).not.toBeVisible();
  expect(requests.some(url => /home-search\.js|presentation\/search\.|\/js\/(app|data)\.|research\.json/.test(url))).toBe(false);
  await page.locator('#home-search-open').click();
  await expect(page.getByRole('dialog', { name: 'Search the guide' })).toBeVisible();
  await expect(page.locator('#home-search-message')).not.toContainText('Loading');
  expect(requests.some(url => /home-search\.js/.test(url))).toBe(true);
  expect(requests.some(url => /presentation\/search\./.test(url))).toBe(true);
  expect(requests.some(url => /\/js\/(app|data)\.|presentation\/(archive|company-|summary)\.|research\.json/.test(url))).toBe(false);
  await page.locator('#home-search-input').fill('C++');
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter(row => ['serious', 'critical'].includes(row.impact))).toEqual([]);
  const action = page.locator('#home-search-results a').filter({ hasText: 'Find paid work matching' });
  await expect(action).toHaveAttribute('href', '/explore/#work?q=C%2B%2B');
  await page.locator('#home-search-close').click();
  await expect(page.locator('#home-search-open')).toBeFocused();
});

test('failed homepage search keeps usable browse actions and a retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', route => route.abort());
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-message').getByRole('link', { name: 'Browse companies' })).toHaveAttribute('href', '/companies/');
  await expect(page.locator('#home-search-message').getByRole('link', { name: 'browse paid work' })).toHaveAttribute('href', '/work/');
  await page.locator('#home-search-close').click();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).not.toContainText('could not load');
});

test('homepage search times out a stalled index and retries without reporting empty results', async ({ page }) => {
  await page.clock.install({ time: new Date(reviewed + day) });
  let stalled;
  await page.route('**/presentation/search.*.json', route => { stalled = route; });
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Loading');
  await page.clock.fastForward(15_001);
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-message')).not.toContainText('No recorded company matches');
  await expect(page.locator('#home-search-message a[href="/work/"]')).toBeVisible();
  await stalled.abort().catch(() => {});
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});

test('homepage search rejects stale index bytes and offers a usable retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, buildId: 'stale-release' } });
  });
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-results')).not.toBeVisible();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});
