const { test, expect } = require('@playwright/test');

for (const { query, company, title } of [
  { query: '', company: 'a-team', title: 'native Companies keeps focus while its filters load' },
  { query: '?q=Appen', company: 'appen', title: 'native Companies keeps focus on the matching link when its saved search applies' },
]) {
  test(title, async ({ page }) => {
    const { promise: held, resolve: release } = Promise.withResolvers();
    await page.route('**/companies-page.js', async route => {
      await held;
      await route.continue();
    });
    try {
      await page.goto('/companies/' + query, { waitUntil: 'commit' });
      const form = page.locator('#company-filters');
      await expect(form).toBeHidden();
      const links = page.locator('.directory-company-heading h3 a');
      const target = page.locator(`.directory-company-heading h3 a[href$="/company/${company}/"]`);
      await expect(target).toBeVisible();
      for (let count = 0; count < 40 && !await target.evaluate(node => node === document.activeElement); count++) {
        await page.keyboard.press('Tab');
      }
      await expect(target).toBeFocused();
      const initialOrder = await links.evaluateAll(nodes => nodes.map(node => node.href));
      const top = (await target.boundingBox()).y;

      release();
      await expect(form).toBeVisible();
      await expect(target).toBeFocused();
      if (query) {
        await expect(page.locator('.directory-company:visible h3 a').first()).toHaveAttribute('href', /\/company\/appen\/$/);
      } else {
        expect(await links.evaluateAll(nodes => nodes.map(node => node.href))).toEqual(initialOrder);
        expect((await target.boundingBox()).y).toBeCloseTo(top, 1);
      }
    } finally {
      release();
    }
  });
}
