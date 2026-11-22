const { test, expect, firefox } = require('@playwright/test');

const viewport = { width: 320, height: 720 };

test('Daily phone search and filter values fit at enlarged Firefox text sizes', async ({ browserName, baseURL }, info) => {
  test.skip(browserName !== 'firefox', 'Firefox provides a minimum font preference');
  test.setTimeout(90_000);

  for (const minimum of [28, 32]) {
    await test.step(`${minimum}px minimum text`, async () => {
      const browser = await firefox.launch({ firefoxUserPrefs: {
        'font.minimum-size.x-western': minimum,
        'font.minimum-size.x-unicode': minimum,
      } });
      try {
        const page = await browser.newPage({ baseURL, viewport });
        await page.goto('/daily/');
        const search = page.getByRole('searchbox', { name: 'Search', exact: true });
        await expect(search).toBeHidden();
        await page.getByText('Search and filter', { exact: true }).press('Enter');
        await expect(search).toBeVisible();
        await page.evaluate(() => document.fonts.ready);

        const controls = await page.locator('.scan-controls').evaluate(grid => {
          const input = grid.querySelector('input');
          const style = getComputedStyle(input);
          const probe = document.createElement('span');
          probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre';
          grid.append(probe);
          probe.style.font = getComputedStyle(input, '::placeholder').font;
          probe.textContent = input.placeholder;
          const hint = { text: input.placeholder, needed: probe.getBoundingClientRect().width,
            available: input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - 2 };
          probe.remove();

          // The native select's intrinsic width includes its longest option, padding and arrow.
          const selects = [...grid.querySelectorAll('select')].map(select => {
            const sample = select.cloneNode(true);
            sample.removeAttribute('id');
            sample.style.cssText = 'position:absolute;visibility:hidden;width:max-content';
            select.after(sample);
            const needed = sample.getBoundingClientRect().width;
            sample.remove();
            const { top, bottom, width } = select.getBoundingClientRect();
            return { name: select.labels[0].textContent, needed, available: width, top, bottom };
          });
          return { hint, selects, documentWidth: document.scrollingElement.scrollWidth };
        });

        await info.attach(`daily-minimum-font-${minimum}.json`, {
          body: JSON.stringify(controls), contentType: 'application/json',
        });
        expect(controls.documentWidth).toBe(viewport.width);
        expect(controls.hint.text).toBeTruthy();
        expect(controls.hint.needed).toBeLessThanOrEqual(controls.hint.available);
        expect(controls.selects.map(select => select.name)).toEqual(['Topic', 'Type']);
        expect(controls.selects[1].top).toBeGreaterThanOrEqual(controls.selects[0].bottom);
        for (const { name, needed, available } of controls.selects) {
          expect(needed, name).toBeLessThanOrEqual(available);
        }
      } finally {
        await browser.close();
      }
    });
  }
});

test.describe('Daily phone sources without JavaScript', () => {
  test.use({ viewport, javaScriptEnabled: false });

  test('Chromium renders the external marker and retains the native source links', async ({ page, request }, info) => {
    test.skip(info.project.name !== 'chromium', 'Exercise the standard Chromium source rendering');
    await page.goto('/daily/');
    const date = await page.locator('.daily-scan').getAttribute('data-edition');
    const snapshot = await request.get(`/daily/${date}/snapshot.json`);
    expect(snapshot.ok()).toBeTruthy();
    const { title, sources: [primary] } = (await snapshot.json()).items[0];
    const article = page.locator('.scan-item').first();
    const headline = article.getByRole('link', { name: title, exact: true });
    await expect(headline).toHaveAttribute('href', primary.url);
    await article.getByText('Details & sources', { exact: true }).press('Enter');
    const source = article.getByRole('link', { name: primary.label, exact: true });
    await expect(source).toHaveAttribute('href', primary.url);

    for (const link of [headline, source]) {
      const icon = await link.evaluate(anchor => {
        const style = getComputedStyle(anchor, '::after');
        return { content: style.content, mask: style.maskImage, width: parseFloat(style.width) };
      });
      expect(icon.content).toBe('""');
      expect(icon.mask).not.toBe('none');
      expect(icon.width).toBeGreaterThan(0);
    }

    const destination = new URL(primary.url).href;
    await page.route(url => url.href === destination, route => route.fulfill({ body: 'Original source' }));
    await source.press('Enter');
    await expect(page).toHaveURL(destination);
  });
});
