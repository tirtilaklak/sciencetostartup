const { test, expect } = require('@playwright/test');

test.describe('native phone navigation with enlarged Firefox text', () => {
  test.skip(({ browserName }) => browserName !== 'firefox', 'The test uses Firefox minimum font sizes');
  test.use({
    javaScriptEnabled: false,
    viewport: { width: 320, height: 720 },
    launchOptions: { firefoxUserPrefs: {
      'font.minimum-size.x-western': 32,
      'font.minimum-size.x-unicode': 32,
    } },
  });

  test('main links stay a single keyboard disclosure at 320px', async ({ page, baseURL }) => {
    const destinations = ['Daily scan', 'Research', 'Companies', 'Paid work', 'About'];
    const researchURL = new URL('/research/', baseURL).href;
    await page.route('https://sciencetostartup.com/research/', route =>
      route.fulfill({ status: 302, headers: { location: researchURL } }));

    for (const [path, current] of [
      ['/work/', 'Paid work'], ['/daily/', 'Daily scan'],
      ['/companies/', 'Companies'], ['/research/', 'Research'],
    ]) {
      await page.goto(path);
      const header = page.locator('body > header.site-header');
      const search = header.getByRole('link', { name: 'Search the guide' });
      const menu = header.getByText('Menu', { exact: true });
      const nav = header.getByRole('navigation', { name: 'Main', exact: true });
      const wordmark = header.getByRole('link', { name: /ScienceToStartup/ });
      const closed = await header.boundingBox();
      expect(closed.height, path).toBeLessThanOrEqual(110);
      await expect(nav, path).toHaveCount(0);

      for (const target of [page.getByRole('link', { name: 'Skip to content' }), wordmark, search, menu]) {
        await page.keyboard.press('Tab');
        await expect(target, path).toBeFocused();
      }
      const [wordmarkBox, searchBox, menuBox] = await Promise.all(
        [wordmark, search, menu].map(control => control.boundingBox()));
      for (const box of [wordmarkBox, searchBox, menuBox]) {
        expect(box.width, path).toBeGreaterThanOrEqual(44);
        expect(box.height, path).toBeGreaterThanOrEqual(44);
        expect(box.x, path).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, path).toBeLessThanOrEqual(320);
      }
      expect(wordmarkBox.y + wordmarkBox.height <= searchBox.y || wordmarkBox.x + wordmarkBox.width <= searchBox.x, path).toBe(true);
      await expect(search).toHaveAttribute('href', '/?search=#browse-guide');

      await page.keyboard.press('Enter');
      await expect(nav, path).toHaveCount(1);
      expect((await header.boundingBox()).height, path).toBe(closed.height);
      await expect(nav.getByRole('link'), path).toHaveText(destinations);
      await expect(nav.getByRole('link', { name: current, exact: true }), path).toHaveAttribute('aria-current', 'page');

      for (const name of destinations) {
        await page.keyboard.press('Tab');
        const link = nav.getByRole('link', { name, exact: true });
        await expect(link, path).toBeFocused();
        const box = await link.boundingBox();
        expect(box.height, path).toBeGreaterThanOrEqual(44);
        expect(box.x, path).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, path).toBeLessThanOrEqual(320);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth), path).toBe(320);

      if (path === '/work/') {
        await nav.getByRole('link', { name: 'Research', exact: true }).press('Enter');
        await expect(page).toHaveURL(researchURL);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Research on\s*AI data\./);
      } else {
        await menu.press('Enter');
        await expect(nav, path).toHaveCount(0);
      }
    }
  });

  test('paid work source index is the first tab in the dossier source disclosure', async ({ page }) => {
    await page.goto('/company/afterquery/');
    const summary = page.locator('summary#sources');
    const paidSources = page.getByRole('link', { name: /paid work sources/ });
    await expect(paidSources).toHaveCount(0);
    await summary.press('Enter');
    await page.keyboard.press('Tab');
    await expect(paidSources).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/company\/afterquery\/work-sources\/$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('AfterQuery paid work sources');
  });
});
