const { test, expect } = require('@playwright/test');

test.use({
  javaScriptEnabled: false,
  viewport: { width: 320, height: 720 },
  reducedMotion: 'reduce',
  trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true },
  launchOptions: { firefoxUserPrefs: {
    'font.minimum-size.x-western': 32,
    'font.minimum-size.x-unicode': 32,
  } },
});

test('one End key reaches the ledger footer without JavaScript', async ({ page, browserName }) => {
  for (const [path, key] of [
    ['/research/data/sources/f/', 'End'],
    ['/research/data/assertions/f/', browserName === 'webkit' ? 'End' : 'Control+End'],
    ['/research/editions/2026-11-12/data/sources/f/', 'End'],
  ]) {
    await page.goto(path);
    await page.keyboard.press(key);
    await expect.poll(() => page.evaluate(() => {
      const root = document.scrollingElement;
      return root.scrollHeight - root.clientHeight - root.scrollTop;
    }), { message: `${key} should reach the document end on ${path}` }).toBeLessThanOrEqual(1);
    await expect(page.locator('body > footer')).toBeInViewport();
  }
});
