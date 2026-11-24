const { test, expect } = require('@playwright/test');

test.use({ viewport: { width: 390, height: 844 } });

for (const [company, sourceIndex] of [['org.dataforce', 1], ['org.nexdata', 0]]) {
  test(`Back restores the selected source on the ${company} profile`, async ({ page, hasTouch }) => {
    const profile = `/company/${company}/`;
    await page.addInitScript(profilePath => {
      if (location.pathname !== profilePath) return;
      addEventListener('unload', () => {});
      addEventListener('pageshow', event => { window.companySourcePageCached = event.persisted; });
    }, profile);

    await page.goto(profile);
    await expect(page.locator('script[src="/native-details.js"]')).toHaveCount(1);
    const sources = page.locator('#company-sources');
    await sources.getByText('Sources', { exact: true }).press('Enter');
    const links = sources.getByRole('link');
    const source = links.nth(sourceIndex);
    const destination = new URL(await source.getAttribute('href'), page.url());
    const sourceTitle = await source.innerText();
    const initialTop = await source.evaluate(link => {
      link.scrollIntoView({ block: 'center', behavior: 'instant' });
      link.focus({ preventScroll: true });
      return link.getBoundingClientRect().top;
    });

    if (hasTouch) await source.tap();
    else await source.press('Enter');
    await expect(page).toHaveURL(destination.href);
    const fragment = decodeURIComponent(destination.hash.slice(1));
    const record = page.locator('[id=' + JSON.stringify(fragment) + ']');
    await expect(record.getByRole('heading', { name: sourceTitle, exact: true })).toBeInViewport();

    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(profile);
    await expect.poll(() => page.evaluate(() => window.companySourcePageCached)).toBe(false);
    await expect(sources).toHaveJSProperty('open', true);
    await expect(source).toBeFocused();
    await expect(source).toBeInViewport({ ratio: 1 });
    await expect.poll(() => source.evaluate((link, top) =>
      Math.abs(link.getBoundingClientRect().top - top), initialTop)).toBeLessThan(3);
    await page.keyboard.press('Tab');
    await expect(links.nth(sourceIndex + 1)).toBeFocused();
  });
}
