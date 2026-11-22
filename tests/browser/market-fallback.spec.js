const { test, expect } = require('@playwright/test');

async function expectMarketLanding(page) {
  await expect(page).toHaveURL(/\/explore\/#business-health$/);
  const dashboard = page.locator('#business-health');
  const heading = dashboard.getByRole('heading', { name: 'Revenue & growth.' });
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport({ ratio: 1 });
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
      const browse = fallback.getByRole('link', { name: 'Browse the guide', exact: true });
      await expect(browse).toHaveAttribute('href', '/#browse-guide');
      await expect(browse).toBeFocused();
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

test('a timed-out app bundle cannot remove the focused recovery action when it finally arrives', async ({ page }) => {
  let letBundleLoad;
  let bundleRequested;
  const requested = new Promise(resolve => { bundleRequested = resolve; });
  const delayed = new Promise(resolve => { letBundleLoad = resolve; });
  const appBundle = '**/js/app.*.js';
  await page.route(appBundle, async route => {
    bundleRequested();
    await delayed;
    await route.continue();
  });
  await page.clock.install();
  try {
    await page.goto('/explore/#business-health', { waitUntil: 'domcontentloaded' });
    await requested;
    await page.clock.fastForward(15_001);
    const root = page.locator('html');
    const reload = page.getByRole('button', { name: 'Reload page' });
    await expect(root).toHaveAttribute('data-app-reason', 'timeout');
    await reload.focus();
    letBundleLoad();
    await page.waitForLoadState('load');
    await page.clock.runFor(200);
    await expect(root).toHaveAttribute('data-app', 'failed');
    await expect(reload).toBeFocused();
    await page.unroute(appBundle);
    await page.keyboard.press('Enter');
    await expect(root).toHaveAttribute('data-app', 'ready');
    await expectMarketLanding(page);
  } finally {
    letBundleLoad();
  }
});

test('a failed Market handoff replaces the previous results and allows keyboard reload', async ({ page }) => {
  await page.goto('/explore/#companies');
  const companies = page.locator('#companies-view');
  await expect(companies).toBeVisible();
  const oldSearch = companies.getByRole('searchbox');
  await oldSearch.focus();

  const overview = '**/presentation/overview.*.json';
  await page.route(overview, route => route.fulfill({ status: 503, body: 'Temporarily unavailable' }));
  await page.evaluate(() => { location.hash = '#business-health'; });

  const fallback = page.locator('#app-failure');
  await expect(fallback).toBeVisible();
  await expect(companies).toBeHidden();
  await expect(fallback.getByRole('heading')).toHaveText('Market data could not load.');
  const reload = fallback.getByRole('button', { name: 'Reload page' });
  await expect(reload).toBeFocused();
  await expect(fallback.getByRole('link', { name: 'Method' })).toHaveAttribute('href', '/method/');

  await page.unroute(overview);
  await page.keyboard.press('Enter');
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

for (const [asset, path] of [
  ['overview response', '**/presentation/overview.*.json'],
  ['business-health module', '**/js/health.*.js'],
]) {
  test(`Market reloads the bookmark into view after a blocked ${asset}`, async ({ page }) => {
    await page.route(path, route => route.abort('failed'));
    await page.goto('/explore/#business-health');

    const root = page.locator('html');
    const reload = page.getByRole('button', { name: 'Reload page' });
    await expect(root).toHaveAttribute('data-app', 'ready');
    await expect(root).toHaveAttribute('data-view-state', 'failed');
    await expect(reload).toBeVisible();
    // A browser may start sequential focus at the bookmarked section.
    await page.getByRole('link', { name: 'Skip to content' }).focus();
    for (let step = 0; step < 25; step++) {
      if (await reload.evaluate(button => button === document.activeElement)) break;
      await page.keyboard.press('Tab');
    }
    await expect(reload).toBeFocused();
    await page.unroute(path);
    await page.keyboard.press('Enter');

    await expect(root).toHaveAttribute('data-view-state', 'ready');
    await page.waitForLoadState('load');
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(reload).toBeHidden();
    await expectMarketLanding(page);
  });
}

test('Market preserves the reading position on ordinary reload and Back', async ({ page }) => {
  const bookmark = '/explore/#business-health';
  const heading = page.locator('#business-health-heading');
  await page.goto(bookmark);
  await expect(heading).toBeInViewport();
  const readingPosition = await page.evaluate(() => {
    window.scrollBy({ top: 680, behavior: 'instant' });
    return window.scrollY;
  });
  await expect(heading).not.toBeInViewport();
  await expect.poll(() => page.evaluate(() => {
    const entry = window.navigation ? window.navigation.currentEntry.getState() : history.state;
    return entry?.scrollY;
  })).toBe(readingPosition);

  const expectReadingPosition = async () => {
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await page.waitForLoadState('load');
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(readingPosition);
  };
  await page.reload();
  await expectReadingPosition();
  await page.goto('/companies/');
  await page.goBack();
  await expectReadingPosition();
});

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
