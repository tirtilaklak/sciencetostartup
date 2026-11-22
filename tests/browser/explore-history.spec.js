const { test, expect } = require('@playwright/test');

test('editing Explore Work before navigation preserves the destination and the edited entry', async ({ page }) => {
  const navigateFromWork = (query, action) => page.locator('#work-search').evaluate((input, { query, action }) => {
    input.value = query;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (action === 'fragment') location.hash = '#companies';
    if (action === 'back') history.back();
    if (action === 'native') location.assign('/work/');
  }, { query, action });

  await page.goto('/explore/#companies');
  await page.evaluate(() => { location.hash = '#work?q=Snorkel'; });
  await expect(page.locator('#work-search')).toHaveValue('Snorkel');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');

  await navigateFromWork('Mercor', 'fragment');
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

  await navigateFromWork('Terac', 'back');
  await expect(page.locator('#companies-view')).toBeVisible();
  await expect(page).toHaveURL(/\/explore\/#companies$/);
  await page.goForward();
  await expect(page.locator('#work-search')).toHaveValue('Terac');
  await expect(page).toHaveURL(/#work\?q=Terac$/);

  await navigateFromWork('  RLHF  jobs ', 'native');
  await expect(page).toHaveURL(/\/work\/$/);
  await page.goBack();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('#work-search')).toHaveValue('  RLHF  jobs ');
  await expect(page).toHaveURL(/#work\?q=\+\+RLHF\+\+jobs\+$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/work\/$/);

  await page.goto('/explore/#work?q=Mercor');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await navigateFromWork('Python', 'back');
  await expect(page).toHaveURL(/\/work\/$/);
  await page.goForward();
  await expect(page.locator('#work-search')).toHaveValue('Python');
  await expect(page).toHaveURL(/#work\?q=Python$/);
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
    await page.goto('/explore/#companies');
    await page.locator('#site-search-open').click();
    const input = page.locator('#site-search-input');
    const selected = page.locator('#site-search [aria-selected="true"]');
    await input.fill(query);
    await expect(page.locator(`#site-search a[href="${target}"]`)).toBeVisible();
    await input.press('ArrowDown');
    await expect(selected).toHaveAttribute('href', target);
    await input.press('Enter');
    await page.waitForURL(url => url.pathname + url.search === target);

    await page.goBack();
    await expect(input).toBeVisible();
    await expect(input).toHaveValue(query);
    await expect(input).toBeFocused();
    await expect(selected).toHaveAttribute('href', target);
    expect(await page.evaluate(() => window.searchPageCached)).toBe(false);

    await page.goForward();
    await page.waitForURL(url => url.pathname + url.search === target);
    await page.goBack();
    await expect(input).toBeFocused();
    await expect(selected).toHaveAttribute('href', target);
    await page.locator('#site-search-close').click();
    await expect(page.locator('#site-search-open')).toBeFocused();
  });
}
