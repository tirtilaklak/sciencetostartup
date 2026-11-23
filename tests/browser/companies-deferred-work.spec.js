const { test, expect } = require('@playwright/test');
const { readFile } = require('node:fs/promises');

const summaryRoute = '**/presentation/summary.*.json';
const workQuery = 'kind=named&arrangement=onsite';

function workIds(page) {
  return page.locator('#work-cards [data-work-route]:visible')
    .evaluateAll(rows => rows.map(row => row.dataset.workRoute));
}

async function workCsv(page) {
  const event = page.waitForEvent('download');
  await page.locator('#work-export').click();
  const download = await event;
  return readFile(await download.path(), 'utf8');
}

test('Companies defers Work and recovers the same ordered listings and export', async ({ page }) => {
  let attempts = 0;
  let badSummary = true;
  const { promise: held, resolve: release } = Promise.withResolvers();
  await page.route(summaryRoute, async route => {
    attempts++;
    if (!badSummary) return route.continue();
    await held;
    return route.fulfill({ contentType: 'application/json', body: '{}' });
  });
  await page.goto('/explore/#companies');
  await expect(page.locator('#company-cards [data-company-card]').first()).toBeVisible();
  expect(await page.evaluate(() => window.EXPLORE_DEFER_WORK)).toBe(true);
  expect(attempts).toBe(0);

  await page.evaluate(query => { location.hash = 'work?' + query; }, workQuery);
  await expect(page.locator('#work-count')).toHaveText('Loading work listings…');
  release();
  await expect(page.locator('#work-count')).toHaveText('Work listings could not load. Your filters are preserved.');
  await expect(page.locator('#work-cards a')).toHaveAttribute('href', '/work/?' + workQuery);
  expect(attempts).toBe(1);
  badSummary = false;
  await page.locator('[data-retry-search]').click();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  const ids = await workIds(page);
  expect(ids.length).toBeGreaterThan(0);
  const csv = await workCsv(page);
  expect(attempts).toBe(2);

  badSummary = true;
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  expect(await page.evaluate(() => window.EXPLORE_DEFER_WORK)).toBeUndefined();
  expect(await workIds(page)).toEqual(ids);
  expect(await workCsv(page)).toBe(csv);
  expect(attempts).toBe(2);
});

test('Companies Search preserves the query and browse actions when Work data is unavailable', async ({ page }) => {
  let offline = true;
  await page.route(summaryRoute, route => offline ? route.abort('failed') : route.continue());
  await page.goto('/explore/#companies');
  await expect(page.locator('#company-cards [data-company-card]').first()).toBeVisible();
  await page.locator('#site-search-open').click();
  const input = page.locator('#site-search-input');
  await input.fill('Python');
  const message = page.locator('#site-search-message');
  await expect(message).toContainText('Search could not load');
  await expect(message.getByRole('link', { name: 'paid work' })).toHaveAttribute('href', '/work/?q=Python');
  await expect(input).toHaveValue('Python');
  offline = false;
  await page.locator('[data-retry-site-search]').click();
  await expect(page.getByRole('option', { name: /See all d+ matches? for “Python”/ })).toBeVisible();
});

test('a failed Companies bootstrap uses the existing full data script', async ({ page }) => {
  await page.route('**/js/companies-data.*.js', route => route.abort('failed'));
  await page.goto('/explore/#companies');
  await expect(page.locator('#company-cards [data-company-card]').first()).toBeVisible();
  expect(await page.evaluate(() => window.EXPLORE_DEFER_WORK)).toBeUndefined();
});

test('Market evidence remains available after Companies even before Work loads', async ({ page }) => {
  await page.route(summaryRoute, route => route.abort('failed'));
  await page.goto('/explore/#companies');
  await expect(page.locator('#company-cards [data-company-card]').first()).toBeVisible();
  await page.evaluate(() => { location.hash = 'business-health'; });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#business-health')).toBeVisible();
  await expect(page.locator('#overview-work a')).toHaveAttribute('href', '/work/');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#overview-work')).toContainText('providers');
});
