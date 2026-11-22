const { test, expect } = require('@playwright/test');

const enlargedText = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    await use(browserName === 'firefox' ? {
      ...launchOptions,
      firefoxUserPrefs: {
        ...launchOptions.firefoxUserPrefs,
        'font.minimum-size.x-western': 32,
        'font.minimum-size.x-unicode': 32,
      },
    } : launchOptions);
  }, { scope: 'worker' }],
});

async function openPage(page, path, minimum) {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => document.fonts.ready);
  if (!minimum) return;

  // Firefox enlarges the rendered glyphs without changing the CSS font size.
  const [small, minimumSize, large] = await page.evaluate(() => {
    const sample = document.createElement('span');
    sample.style.cssText = 'position:fixed;visibility:hidden;white-space:nowrap;font-family:monospace';
    sample.textContent = 'MMMMMMMMMM';
    document.body.append(sample);
    const widths = [16, 32, 40].map(size => {
      sample.style.fontSize = `${size}px`;
      return sample.getBoundingClientRect().width;
    });
    sample.remove();
    return widths;
  });
  expect(small).toBeCloseTo(minimumSize, 1);
  expect(minimumSize / large).toBeCloseTo(32 / 40, 2);
}

async function tabTo(page, control) {
  await expect(control).toBeVisible();
  for (let step = 0; step < 60; step++) {
    if (await control.evaluate(node => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(control).toBeFocused();
}

async function expectReadableEvidence(button, phase) {
  await expect.soft.poll(() => button.evaluate(control => {
    const cell = control.closest('td');
    const rowHeading = cell.parentElement.querySelector('th[scope="row"]');
    const headings = cell.closest('table').tHead.rows[0].cells;
    const metricHeading = headings[cell.cellIndex].querySelector('button');
    const wrap = control.closest('#bh-grid-wrap');
    const wrapBox = wrap.getBoundingClientRect();
    const left = Math.max(0, wrapBox.left + wrap.clientLeft);
    const right = Math.min(innerWidth, wrapBox.left + wrap.clientLeft + wrap.clientWidth);
    const top = Math.max(0, wrapBox.top + wrap.clientTop);
    const bottom = Math.min(innerHeight, wrapBox.top + wrap.clientTop + wrap.clientHeight);

    function textPlacement(text, owner, minLeft) {
      const range = document.createRange();
      range.selectNodeContents(text);
      const lines = [...range.getClientRects()].filter(line => line.width && line.height);
      return {
        text: text.textContent.trim(),
        lines: lines.map(({ left, top, right, bottom }) => [left, top, right, bottom].map(Math.round)),
        visible: lines.length > 0 && lines.every(line => (
          line.left >= minLeft && line.right <= right && line.top >= top && line.bottom <= bottom
          && [0.1, 0.5, 0.9].every(fraction => owner.contains(document.elementFromPoint(
            line.left + line.width * fraction, line.top + line.height / 2,
          )))
        )),
      };
    }

    return {
      focusVisible: control.matches(':focus-visible'),
      organization: textPlacement(rowHeading.querySelector('a span'), rowHeading, left),
      metric: textPlacement(metricHeading.firstChild, metricHeading, headings[0].getBoundingClientRect().right),
      amount: textPlacement(control.querySelector('b').firstChild, control, rowHeading.getBoundingClientRect().right),
    };
  }), { message: `Organization, metric and amount are readable ${phase}`, timeout: 3_000 }).toMatchObject({
    focusVisible: true,
    organization: { text: 'Appen', visible: true },
    metric: { text: 'Revenue', visible: true },
    amount: { text: '$193.8M', visible: true },
  });
}

const sharedHeaders = {
  Market: '/explore/',
  Work: '/work/?pay=hourly&sort=hourly',
  Research: '/research/',
  Companies: '/companies/',
  AfterQuery: '/company/afterquery/',
};

for (const minimum of [0, 32]) {
  const phone = minimum ? enlargedText : test;
  phone.describe(`320px Firefox at ${minimum ? 'a 32px minimum font' : 'default text size'}`, () => {
    phone.skip(({ browserName }) => browserName !== 'firefox', 'Exercise Firefox keyboard panning and minimum font behavior');
    phone.use({ viewport: { width: 320, height: 720 }, reducedMotion: 'reduce' });

    phone('Market keeps the focused Appen amount alongside its organization and Revenue heading', async ({ page }) => {
      await openPage(page, '/explore/#business-health', minimum);
      await expect(page.locator('#business-health-heading')).toBeFocused();
      await tabTo(page, page.locator('.bh-coverage-disclosure > summary'));
      await page.keyboard.press('Enter');
      const button = page.locator('#bh-matrix-body button[data-bh-company="appen"][data-bh-signal="revenue"]');
      await tabTo(page, button);
      await expectReadableEvidence(button, 'after Tab');

      const dialog = page.locator('#bh-evidence-dialog');
      await page.keyboard.press('Enter');
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('.bh-value')).toContainText('$193.8M');
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(button).toBeFocused();
      await expectReadableEvidence(button, 'after Escape');
    });

    for (const [name, path] of Object.entries(sharedHeaders)) {
      phone(`${name} keeps Search and the last wordmark letter independently clickable`, async ({ page }) => {
        await openPage(page, path, minimum);
        const original = page.url();
        const home = new URL('/', original).href;
        const canonicalHome = 'https://sciencetostartup.com/';
        if (home !== canonicalHome) {
          // Static templates use an absolute Home link. Follow it within the build under test.
          await page.route(canonicalHome, route => route.fulfill({ status: 307, headers: { location: home } }));
        }
        const header = page.locator('header').filter({ has: page.locator('.wordmark') });
        const search = header.getByRole('link', { name: /^Search(?: the guide)?$/ });
        const dialog = page.getByRole('dialog', { name: 'Search the guide' });
        await search.click();
        await expect(dialog.getByRole('combobox', { name: 'Search the guide' })).toBeFocused();
        await page.keyboard.press('Escape');
        await expect(dialog).toBeHidden();
        if (page.url() !== original) await openPage(page, path, minimum);

        const glyph = await header.locator('.wordmark').evaluate(link => {
          const label = 'ScienceToStartup';
          const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT);
          for (let text = walker.nextNode(); text; text = walker.nextNode()) {
            const start = text.textContent.indexOf(label);
            if (start < 0) continue;
            const range = document.createRange();
            range.setStart(text, start + label.length - 1);
            range.setEnd(text, start + label.length);
            const { x, y, width, height } = range.getBoundingClientRect();
            return { x: x + width / 2, y: y + height / 2, width, height };
          }
          return null;
        });
        expect(glyph?.width).toBeGreaterThan(0);
        expect(glyph.height).toBeGreaterThan(0);
        // The homepage removes the Search query after it opens the dialog, so check the actual request.
        const [navigation] = await Promise.all([
          page.waitForRequest(request => request.isNavigationRequest() && request.frame() === page.mainFrame(), { timeout: 4_000 }),
          page.mouse.click(glyph.x, glyph.y),
        ]);
        expect([home, canonicalHome]).toContain(navigation.url());
        await expect(page).toHaveURL(home, { timeout: 4_000 });
      });
    }
  });
}
