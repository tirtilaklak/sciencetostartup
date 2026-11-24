const { test, expect } = require('@playwright/test');

function navigateFromWork(page, query, action) {
  return page.locator('#work-search').evaluate((input, { query, action }) => {
    input.value = query;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (action === 'fragment') location.hash = '#companies';
    if (action === 'back') history.back();
    if (action === 'native') location.assign('/work/');
  }, { query, action }).catch(error => {
    // Cross-document navigation can commit before evaluate returns to Playwright.
    // The caller checks the destination and the saved edit in the history entry.
    if (!error.message.includes('Execution context was destroyed')) throw error;
  });
}

test('editing Explore Work before a fragment or Back preserves both history entries', async ({ page }) => {
  await page.goto('/explore/#companies');
  await page.evaluate(() => { location.hash = '#work?q=Snorkel'; });
  await expect(page.locator('#work-search')).toHaveValue('Snorkel');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');

  await navigateFromWork(page, 'Mercor', 'fragment');
  await expect(page).toHaveURL(/\/explore\/#companies$/);
  await expect(page.locator('#companies-view')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#work-search')).toBeVisible();
  await expect(page.locator('#work-search')).toHaveValue('Mercor');
  await expect(page).toHaveURL(/#work\?q=Mercor$/);
  await page.goForward();
  await expect(page.locator('#companies-view')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#work-search')).toHaveValue('Mercor');

  await navigateFromWork(page, 'Terac', 'back');
  await expect(page.locator('#companies-view')).toBeVisible();
  await expect(page).toHaveURL(/\/explore\/#companies$/);
  await page.goForward();
  await expect(page.locator('#work-search')).toHaveValue('Terac');
  await expect(page).toHaveURL(/#work\?q=Terac$/);
});

test('editing Explore Work before cross-document navigation preserves literal criteria on return', async ({ page }) => {
  await page.goto('/explore/#work?q=Terac');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await navigateFromWork(page, '  RLHF  jobs ', 'native');
  await expect(page).toHaveURL(/\/work\/$/);
  await page.goBack({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#work-search')).toHaveValue('  RLHF  jobs ');
  await expect(page).toHaveURL(/#work\?q=\+\+RLHF\+\+jobs\+$/);
  await page.goForward({ waitUntil: 'domcontentloaded' });
  await expect(page).toHaveURL(/\/work\/$/);

  await page.goto('/explore/#work?q=Mercor');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await navigateFromWork(page, 'Python', 'back');
  await expect(page).toHaveURL(/\/work\/$/);
  await page.goForward({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#work-search')).toHaveValue('Python');
  await expect(page).toHaveURL(/#work\?q=Python$/);
});

async function openExploreWorkListing(page) {
  await page.goto('/explore/#work');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  const group = page.locator('section:has(> #work-listed) > details');
  const listing = group.locator('[data-work-route="afterquery.work.product-manager"]');
  const disclosures = [group, listing.locator('details.w4-compact-toggle'), listing.locator('details.w4-details')];
  const opener = listing.getByRole('link', { name: 'AfterQuery', exact: true });

  for (const disclosure of disclosures) {
    await disclosure.locator(':scope > summary').press('Enter');
    await expect(disclosure).toHaveJSProperty('open', true);
  }
  return { disclosures, opener };
}

test('Back to Explore Work keeps the open listing, terms and company link', async ({ page }) => {
  const { disclosures, opener } = await openExploreWorkListing(page);
  await opener.scrollIntoViewIfNeeded();
  await opener.focus();
  const position = await opener.evaluate(link => link.getBoundingClientRect().top);
  await opener.press('Enter');
  await expect(page).toHaveURL(/#company\/afterquery\/work$/);
  await expect(page.locator('#profile-pane-work')).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/#work$/);
  for (const disclosure of disclosures) await expect(disclosure).toHaveJSProperty('open', true);
  await expect(opener).toBeFocused();
  await expect(opener).toBeInViewport({ ratio: 1 });
  await expect.poll(() => opener.evaluate((link, previous) => Math.abs(link.getBoundingClientRect().top - previous), position)).toBeLessThan(3);
});

test('Back to Explore Work reveals a company link activated before focus scroll settles', async ({ page }) => {
  const { disclosures, opener } = await openExploreWorkListing(page);
  await opener.evaluate(link => {
    // Hold the old viewport to model Enter before the browser reaches the newly focused link.
    window.scrollTo({ top: 0, behavior: 'instant' });
    link.focus({ preventScroll: true });
  });
  await expect(opener).toBeFocused();
  await expect(opener).not.toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#company\/afterquery\/work$/);

  await page.goBack();
  await expect(page).toHaveURL(/#work$/);
  for (const disclosure of disclosures) await expect(disclosure).toHaveJSProperty('open', true);
  await expect(opener).toBeFocused();
  await expect(opener).toBeInViewport({ ratio: 1 });
});

test('Back to Explore Companies restores the original filter after browsing a profile group', async ({ page }) => {
  const directory = '/explore/#companies';
  const group = 'expert-data-evaluation';
  const search = page.locator('#search');
  const count = page.locator('#result-count');
  await page.goto(directory);
  await search.fill('Mercor');
  await expect(count).toHaveText(/Showing 1 of \d+ companies/);
  await page.locator('#company-cards h3 a[href="#company/mercor"]').press('Enter');
  await expect(page.getByRole('heading', { name: 'Mercor', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');

  await page.locator(`.profile-group-link[href="#companies/${group}"]`).press('Enter');
  await expect(page).toHaveURL(`${directory}/${group}`);
  await expect(search).toHaveValue('');
  await expect(count).toHaveText(/Showing 9 of \d+ companies/);

  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Mercor', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(directory);
  await expect(search).toHaveValue('Mercor');
  await expect(page.locator('#category')).toHaveValue('');
  await expect(count).toHaveText(/Showing 1 of \d+ companies/);
});

for (const [query, target] of [
  ['arXiv:2203.02155v1', '/research/papers/paper.arxiv.2203.02155v1/'],
  ['RLHF  jobs', '/work/?q=RLHF++jobs'],
]) {
  test(`cold Back restores the Explore Search result for ${query}`, async ({ page }) => {
    await page.addInitScript(() => {
      addEventListener('unload', () => {});
      addEventListener('pageshow', event => { window.searchPageCached = event.persisted; });
    });
    await page.goto('/explore/#companies', { waitUntil: 'domcontentloaded' });
    await page.locator('#site-search-open').click();
    const input = page.locator('#site-search-input');
    const selected = page.locator('#site-search [aria-selected="true"]');
    await input.fill(query);
    await expect(page.locator(`#site-search a[href="${target}"]`)).toBeVisible();
    await input.press('ArrowDown');
    await expect(selected).toHaveAttribute('href', target);
    await input.press('Enter');
    await page.waitForURL(url => url.pathname + url.search === target, { waitUntil: 'commit' });

    await page.goBack({ waitUntil: 'domcontentloaded' });
    await expect(input).toBeVisible();
    await expect(input).toHaveValue(query);
    await expect(input).toBeFocused();
    await expect(selected).toHaveAttribute('href', target);
    await expect.poll(() => page.evaluate(() => window.searchPageCached)).toBe(false);

    await page.goForward({ waitUntil: 'domcontentloaded' });
    await page.waitForURL(url => url.pathname + url.search === target, { waitUntil: 'commit' });
    await page.goBack({ waitUntil: 'domcontentloaded' });
    await expect(input).toBeFocused();
    await expect(selected).toHaveAttribute('href', target);
    await page.locator('#site-search-close').click();
    await expect(page.locator('#site-search-open')).toBeFocused();
  });
}
