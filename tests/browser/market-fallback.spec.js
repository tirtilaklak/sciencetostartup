const { test, expect } = require('@playwright/test');

async function expectMarketLanding(page) {
  await expect(page).toHaveURL(/\/explore\/#business-health$/);
  const dashboard = page.locator('#business-health');
  const heading = dashboard.getByRole('heading', { name: 'Revenue & growth.' });
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport();
  await expect(dashboard.getByRole('tablist', { name: 'Revenue views' }).getByRole('tab')).toHaveCount(3);
  await page.keyboard.press('Tab');
  await expect(dashboard.getByRole('link', { name: /^Download data/ })).toBeFocused();
}

test.describe('Explore without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  for (const fragment of ['', '#work', '#business-health']) {
    test(`${fragment || 'base URL'} starts at the skip link and reaches the plain directory`, async ({ page }) => {
      await page.goto('/explore/' + fragment);

      const fallback = page.locator('noscript .availability-notice');
      await expect(fallback.getByRole('heading', { name: 'ScienceToStartup: the AI data field guide' })).toBeInViewport();
      await page.keyboard.press('Tab');
      const skip = page.getByRole('link', { name: 'Skip to content' });
      await expect(skip).toBeFocused();
      await expect(skip).toBeInViewport();
      if (fragment === '#business-health') await expect(page.locator('#business-health')).toHaveCount(0);
      await page.keyboard.press('Enter');
      await expect(page.locator('#main')).toBeFocused();

      await page.keyboard.press('Tab');
      await expect(fallback.getByRole('link', { name: 'Search the plain guide' })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(fallback.getByRole('link', { name: 'Company list' })).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/\/companies\/$/);
    });
  }
});

test('enhanced Market exposes the fragment and focuses the visible heading', async ({ page }) => {
  await page.goto('/explore/#business-health');
  await expectMarketLanding(page);
});

for (const bundle of ['data', 'app']) {
  test(`Market retries the bookmark after a blocked ${bundle} bundle`, async ({ page }) => {
    const path = `**/js/${bundle}.*.js`;
    await page.route(path, route => route.abort('failed'));
    await page.goto('/explore/#business-health');

    const root = page.locator('html');
    const recovery = page.locator('#app-failure');
    await expect(root).toHaveAttribute('data-app-reason', 'script-network');
    await expect(recovery.getByRole('heading')).toBeInViewport();
    await page.keyboard.press('Tab');
    const skip = page.getByRole('link', { name: 'Skip to content' });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await expect(page.locator('#business-health')).toHaveCount(0);
    await page.keyboard.press('Enter');
    await expect(page.locator('#main')).toBeFocused();
    await expect(page).toHaveURL(/\/explore\/#business-health$/);

    await page.keyboard.press('Tab');
    await expect(recovery.getByRole('button', { name: 'Reload page' })).toBeFocused();
    await page.unroute(path);
    await page.keyboard.press('Enter');
    await expect(root).toHaveAttribute('data-app', 'ready');
    await expect(recovery).toBeHidden();
    await expectMarketLanding(page);
  });
}

for (const readerTabbed of [false, true]) {
  test(`Market keeps ${readerTabbed ? 'the selected Download link' : 'the heading'} focused after a late page load`, async ({ page, browserName, isMobile }) => {
    test.skip(browserName !== 'firefox' || isMobile, 'Exercise Firefox’s native fragment processing at pageshow');
    const hash = '/explore/#business-health';
    const bundlePath = '**/js/data.*.js';
    const heading = page.locator('#business-health-heading');
    const download = page.locator('#business-health').getByRole('link', { name: /^Download data/ });
    let unblockImage;
    const held = new Promise(resolve => { unblockImage = resolve; });
    await page.addInitScript(() => {
      if (performance.getEntriesByType('navigation')[0]?.type !== 'reload') return;
      const observer = new MutationObserver(() => {
        if (!document.body) return;
        observer.disconnect();
        const image = document.createElement('img');
        image.hidden = true;
        image.alt = '';
        image.src = '/assets/favicon-48.png?market-load-order=1';
        document.body.append(image);
      });
      observer.observe(document, { childList: true, subtree: true });
    });
    await page.route('**/favicon-48.png?market-load-order=1', async route => {
      await held;
      await route.continue();
    });
    await page.route(bundlePath, route => route.abort('failed'));
    try {
      await page.goto(hash);
      await expect(page.locator('#app-failure')).toBeVisible();
      await page.unroute(bundlePath);
      await page.locator('#app-reload').focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
      await expect(heading).toBeFocused();
      expect(await page.evaluate(() => document.readyState)).toBe('interactive');
      if (readerTabbed) {
        await page.keyboard.press('Tab');
        await expect(download).toBeFocused();
      }
      unblockImage();
      await page.waitForLoadState('load');
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await expect(readerTabbed ? download : heading).toBeFocused();
      if (!readerTabbed) {
        await page.keyboard.press('Tab');
        await expect(download).toBeFocused();
      }
    } finally {
      unblockImage();
    }
  });
}
