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
const apexCaptures = [
  ['PDF page 1 · lines 17–43', '/research/data/sources/5/#source-third11.source.apex-paper.p001.lf17-43'],
  ['PDF page 2 · lines 8–12', '/research/data/sources/3/#source-third11.source.apex-paper.p002.lf8-12'],
  ['PDF page 3 · lines 23–32', '/research/data/sources/6/#source-third11.source.apex-paper.p003.lf23-32'],
  ['PDF page 3 · lines 6–18', '/research/data/sources/1/#source-third11.source.apex-paper.p003.lf6-18'],
  ['PDF page 6 · lines 1–41', '/research/data/sources/4/#source-third11.source.apex-paper.p006.lf1-41'],
  ['PDF page 9 · lines 5–30', '/research/data/sources/2/#source-third11.source.apex-paper.p009.lf5-30'],
  ['PDF page 13 · lines 1–7', '/research/data/sources/9/#source-third11.source.apex-paper.p013.lf1-7'],
];

test('catalog finds existing source captures and retains results after native Back', async ({ page }) => {
  const indexRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === indexPath) indexRequests.push(request.url());
  });
  await page.goto(catalog);
  const panel = page.locator('#find-source');
  const lookup = panel.getByRole('search', { name: 'Find a source' });
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

test('320px catalog shows both lookup controls before scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(catalog);
  const panel = page.locator('#find-source');
  const lookup = panel.getByRole('search', { name: 'Find a source' });
  const query = lookup.getByRole('searchbox', { name: 'Source title or publisher' });
  const submit = lookup.getByRole('button', { name: 'Find sources' });
  await expect(query).toBeInViewport({ ratio: 1 });
  await expect(submit).toBeInViewport({ ratio: 1 });
  await query.fill('apex-paper');
  await page.keyboard.press('Tab');
  await expect(submit).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(panel.getByRole('status')).toHaveText('7 sources match “apex-paper”.');
});

test('same-title PDF captures give readers exact locations before opening a record', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(catalog + '#find-source');
  const panel = page.locator('#find-source');
  const query = panel.getByRole('searchbox', { name: 'Source title or publisher' });
  const results = panel.getByRole('list');
  await query.fill('apex-paper');
  await query.press('Enter');
  await expect(panel.getByRole('status')).toHaveText('7 sources match “apex-paper”.');
  await expect(results.getByRole('link', { name: 'apex-paper', exact: true })).toHaveCount(apexCaptures.length);

  // Simulate 200% text without scaling the viewport or the touch targets.
  await panel.locator('h2, label, input, button, p, li > a, li > span').evaluateAll(elements => {
    const fontSizes = elements.map(element => Number.parseFloat(getComputedStyle(element).fontSize));
    elements.forEach((element, index) => {
      element.style.fontSize = `${fontSizes[index] * 2}px`;
    });
  });
  expect(await panel.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
  await panel.getByRole('button', { name: 'Find sources' }).scrollIntoViewIfNeeded();
  await expect(panel.getByRole('button', { name: 'Find sources' })).toBeInViewport({ ratio: 1 });

  const captureLink = location => results.getByRole('listitem').filter({ hasText: location })
    .getByRole('link', { name: 'apex-paper', exact: true });
  for (const [location, href] of apexCaptures) {
    await expect(results.getByText(location)).toBeVisible();
    await expect(captureLink(location)).toHaveAccessibleDescription(new RegExp(location + '$'));
    await expect(captureLink(location)).toHaveAttribute('href', href);
  }

  const [location, href] = apexCaptures[3];
  const detail = results.getByText(location);
  await detail.scrollIntoViewIfNeeded();
  await expect(detail).toBeInViewport({ ratio: 1 });
  await captureLink(location).press('Enter');
  await expect(page).toHaveURL(url => url.pathname + url.hash === href);
  const target = page.locator('article:target');
  await expect(target.getByRole('heading', { name: 'apex-paper', exact: true })).toBeInViewport();
  await expect(target).toContainText(/physical PDF page 3.*LF6-18/);

  await page.goBack();
  await expect(page).toHaveURL(/\/research\/data\/\?source=apex-paper#find-source$/);
  await expect(query).toHaveValue('apex-paper');
  await expect(captureLink(location)).toHaveAccessibleDescription(new RegExp(location + '$'));
  await expect(captureLink(location)).toHaveAttribute('href', href);
});

test('source lookup recovers after an unavailable index and reports an empty result', async ({ page }) => {
  let attempts = 0;
  await page.route('**' + indexPath, route => ++attempts === 1 ? route.abort() : route.continue());
  await page.goto(catalog);
  const panel = page.locator('#find-source');
  const lookup = panel.getByRole('search', { name: 'Find a source' });
  const query = lookup.getByRole('searchbox');
  const status = page.locator('[data-source-status]');
  const links = page.locator('[data-source-results] a');
  await query.fill('Prolific');
  await query.press('Enter');
  await expect(status).toContainText('Source lookup couldn’t load.');
  await expect(lookup.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(panel.getByRole('link', { name: 'Browse the source ledger parts' })).toHaveAttribute('href', '#sources');
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
    const panel = page.locator('#find-source');
    await expect(panel.getByRole('searchbox', { name: 'Source title or publisher' })).toHaveCount(0);
    await panel.getByRole('link', { name: 'Browse the source ledger parts' }).press('Enter');
    await expect(page.locator('#sources:target')).toBeInViewport();
    const parts = page.locator('section[aria-labelledby="sources"] .r-ledger-parts a');
    await expect(parts).toHaveCount(16);
    await parts.first().press('Enter');
    await expect(page.getByRole('heading', { name: 'Source ledger · Part 01' })).toBeVisible();
  });
});
