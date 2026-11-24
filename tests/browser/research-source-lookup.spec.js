const { test, expect } = require('@playwright/test');

const catalog = '/research/data/';
const indexPath = '/research/data/source-lookup.json';
const title = 'Prolific Pricing | Platform & managed services | Prolific';
const pricingRecords = [
  '/research/data/sources/1/#source-supplier-source.prolific.pricing.excerpt-1f438d67dfae.3abcd5e4',
  '/research/data/sources/8/#source-supplier-source.prolific.pricing.excerpt-0698def90f64.b1797ffa',
  '/research/data/sources/9/#source-supplier-source.prolific.pricing.excerpt-73a0f5798902.9e0368ef',
  '/research/data/sources/b/#source-repair20261111.source.current-reference221.1',
];

test('catalog finds existing source captures and retains results after native Back', async ({ page }) => {
  const indexRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === indexPath) indexRequests.push(request.url());
  });
  await page.goto(catalog);
  const lookup = page.getByRole('search', { name: 'Find a source' });
  const query = lookup.getByRole('searchbox', { name: 'Source title or publisher' });
  const results = page.locator('[data-source-results]');
  await expect(query).toBeInViewport();
  expect(indexRequests).toHaveLength(0);
  await query.fill('Prolific Pricing');
  expect(indexRequests).toHaveLength(0);
  await query.press('Enter');
  await expect(page.locator('[data-source-status]')).toHaveText('4 sources match “Prolific Pricing”.');
  expect(indexRequests).toHaveLength(1);
  const links = results.getByRole('link', { name: title, exact: true });
  await expect(links).toHaveCount(4);
  expect((await links.evaluateAll(items => items.map(link => link.getAttribute('href')))).sort()).toEqual(pricingRecords);
  const faq = results.locator(`a[href="${pricingRecords[2]}"]`);
  await expect(faq).toHaveAccessibleDescription(/Pricing FAQ/);
  await faq.press('Enter');
  expect(new URL(page.url()).pathname + new URL(page.url()).hash).toBe(pricingRecords[2]);
  await expect(page.locator('article:target')).toBeInViewport();
  await expect(page.locator('article:target').getByRole('heading', { name: title })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/research\/data\/\?source=Prolific\+Pricing#find-source$/);
  await expect(query).toHaveValue('Prolific Pricing');
  await expect(links).toHaveCount(4);
  await expect(faq).toHaveAttribute('href', pricingRecords[2]);
});

test('source lookup recovers after an unavailable index and reports an empty result', async ({ page }) => {
  let attempts = 0;
  await page.route('**' + indexPath, route => ++attempts === 1 ? route.abort() : route.continue());
  await page.goto(catalog);
  const lookup = page.getByRole('search', { name: 'Find a source' });
  const query = lookup.getByRole('searchbox');
  const status = page.locator('[data-source-status]');
  const links = page.locator('[data-source-results] a');
  await query.fill('Prolific');
  await query.press('Enter');
  await expect(status).toContainText('Source lookup couldn’t load.');
  await expect(lookup.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Browse the source ledger parts' })).toHaveAttribute('href', '#sources');
  await lookup.getByRole('button', { name: 'Try again' }).press('Enter');
  await expect(status).toContainText(/(?:sources match|of \d+ sources for) “Prolific”/);
  await expect(links.first()).toHaveAccessibleDescription(/^Prolific · Captured /);
  expect(await links.count()).toBeLessThanOrEqual(24);
  await query.fill('absent-source-title-8ceb2d');
  await query.press('Enter');
  await expect(status).toHaveText('No source records match “absent-source-title-8ceb2d”.');
  await expect(links).toHaveCount(0);
  expect(attempts).toBe(2);
});

test.describe('native source browsing', () => {
  test.use({ javaScriptEnabled: false });

  test('catalog still links to its source ledger parts', async ({ page }) => {
    await page.goto(catalog);
    await expect(page.getByRole('searchbox', { name: 'Source title or publisher' })).toHaveCount(0);
    await page.getByRole('link', { name: 'Browse the source ledger parts' }).press('Enter');
    await expect(page.locator('#sources:target')).toBeInViewport();
    const parts = page.locator('section[aria-labelledby="sources"] .r-ledger-parts a');
    await expect(parts).toHaveCount(16);
    await parts.first().press('Enter');
    await expect(page.getByRole('heading', { name: 'Source ledger · Part 01' })).toBeVisible();
  });
});
