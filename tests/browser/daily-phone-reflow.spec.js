const { test, expect, firefox } = require('@playwright/test');

const viewport = { width: 320, height: 720 };
// Independent DOMRect reads can round differently. A thousandth of a CSS pixel
// covers that difference and stays below Firefox's 1/60px layout unit.
const selectWidthTolerance = 0.001;

function firefoxWithMinimumText(minimum) {
  return firefox.launch({ firefoxUserPrefs: {
    'font.minimum-size.x-western': minimum,
    'font.minimum-size.x-unicode': minimum,
  } });
}

function filterLayout(grid) {
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
  const measureSelect = select => {
    const sample = select.cloneNode(true);
    sample.removeAttribute('id');
    sample.style.cssText = 'position:absolute;visibility:hidden;width:max-content';
    select.after(sample);
    const needed = sample.getBoundingClientRect().width;
    sample.remove();
    const { top, bottom, width } = select.getBoundingClientRect();
    return { name: select.labels[0].textContent, needed, available: width, top, bottom };
  };
  const selects = [...grid.querySelectorAll('select')].map(measureSelect);

  const luminance = rgb => rgb.match(/\d+/g).slice(0, 3).reduce((sum, component, i) => {
    const srgb = Number(component) / 255;
    const linear = srgb <= .04045 ? srgb / 12.92 : ((srgb + .055) / 1.055) ** 2.4;
    return sum + linear * [.2126, .7152, .0722][i];
  }, 0);
  const background = luminance(getComputedStyle(document.body).backgroundColor);
  const measureControl = control => {
    const style = getComputedStyle(control);
    const border = luminance(style.borderTopColor);
    const fill = style.backgroundColor === 'rgba(0, 0, 0, 0)' ? background : luminance(style.backgroundColor);
    const contrast = adjacent => (Math.max(border, adjacent) + .05) / (Math.min(border, adjacent) + .05);
    const { left, right } = control.getBoundingClientRect();
    return { name: control.labels[0].textContent, left, right, borderWidth: parseFloat(style.borderTopWidth),
      contrast: Math.min(contrast(background), contrast(fill)) };
  };
  const controls = [...grid.querySelectorAll('input, select')].map(measureControl);
  const scan = grid.closest('.daily-scan');
  const date = scan.querySelector('.scan-date-form select');
  const kind = document.createRange();
  kind.selectNodeContents(scan.querySelector('.scan-kind'));
  const kindLines = Array.from(kind.getClientRects(), ({ left, right }) => ({ left, right }));
  return { hint, selects, controls, searchTop: input.getBoundingClientRect().top,
    documentWidth: document.scrollingElement.scrollWidth, kindLines,
    date: date.getClientRects().length ? { ...measureSelect(date), ...measureControl(date) } : null };
}

test('Daily filter controls fit and have visible boundaries across Firefox text sizes', async ({ browserName, baseURL }, info) => {
  test.skip(browserName !== 'firefox', 'Firefox provides a minimum font preference');
  test.setTimeout(90_000);

  for (const minimum of [0, 28, 32]) {
    await test.step(`${minimum}px minimum text`, async () => {
      const browser = await firefoxWithMinimumText(minimum);
      try {
        const page = await browser.newPage({ baseURL, viewport });
        for (const width of [320, 390, 600, 601, 844]) {
          await test.step(`${width}px viewport`, async () => {
            await page.setViewportSize({ width, height: width === 320 ? viewport.height : 844 });
            await page.goto('/daily/');
            const search = page.getByRole('searchbox', { name: 'Search', exact: true });
            if (width <= 600) {
              await expect(search).toBeHidden();
              await page.getByText('Search and filter', { exact: true }).press('Enter');
            }
            await expect(search).toBeVisible();
            await page.evaluate(() => document.fonts.ready);

            const layout = await page.locator('.scan-controls').evaluate(filterLayout);
            await info.attach(`daily-minimum-font-${minimum}-width-${width}.json`, {
              body: JSON.stringify(layout), contentType: 'application/json',
            });
            expect(layout.hint.text).toBeTruthy();
            expect(layout.hint.needed).toBeLessThanOrEqual(layout.hint.available);
            expect(layout.controls.map(control => control.name)).toEqual(['Search', 'Topic', 'Type']);
            for (const { name, left, right, borderWidth, contrast } of layout.controls) {
              expect(left, name).toBeGreaterThanOrEqual(0);
              expect(right, name).toBeLessThanOrEqual(width);
              expect(borderWidth, name).toBeGreaterThan(0);
              expect(contrast, name).toBeGreaterThanOrEqual(3);
            }
            for (const { name, needed, available } of layout.selects) {
              expect(needed, name).toBeLessThanOrEqual(available + selectWidthTolerance);
            }

            const [topic, type] = layout.selects;
            expect(layout.documentWidth).toBe(width);
            expect(layout.kindLines.length).toBeGreaterThan(0);
            for (const { left, right } of layout.kindLines) {
              expect(left).toBeGreaterThanOrEqual(0);
              expect(right).toBeLessThanOrEqual(width);
            }
            if (width === 320 || (width === 390 && minimum > 0)) {
              expect(type.top).toBeGreaterThanOrEqual(topic.bottom);
            }
            if (width > 320 && minimum === 0) expect(type.top).toBe(topic.top);
            if (width > 600 && minimum === 0) expect(topic.top).toBe(layout.searchTop);
            if (width === 320 && minimum === 32) {
              await page.getByText('Snapshot archive and feeds', { exact: true }).press('Enter');
              const { date } = await page.locator('.scan-controls').evaluate(filterLayout);
              expect(date.needed).toBeLessThanOrEqual(date.available + selectWidthTolerance);
              expect(date.right).toBeLessThanOrEqual(width);
              expect(date.contrast).toBeGreaterThanOrEqual(3);
              await expect(page.getByRole('button', { name: 'Go', exact: true })).toBeVisible();
            }
          });
        }
      } finally {
        await browser.close();
      }
    });
  }
});

test('Daily story details keep enlarged labels and values separate', async ({ browserName, baseURL }, info) => {
  test.skip(browserName !== 'firefox', 'Firefox provides a minimum font preference');
  const browser = await firefoxWithMinimumText(32);
  try {
    const page = await browser.newPage({ baseURL, viewport });
    await page.goto('/daily/2026-11-18/');
    const story = page.locator('#scale-hospital-operations');
    await story.getByText('Details & sources', { exact: true }).press('Enter');
    const source = story.getByRole('link', { name: 'Scale Hospital Operations release and evaluation approach' });
    await expect(source).toHaveAttribute('href', 'https://scale.com/blog/scaleforhospitaloperations');
    await page.evaluate(() => document.fonts.ready);

    for (const width of [320, 390, 600, 601, 701, 844]) {
      await test.step(`${width}px viewport`, async () => {
        await page.setViewportSize({ width, height: viewport.height });
        await expect(source).toBeVisible();
        const { documentWidth, fields } = await story.evaluate(article => {
          const textRects = element => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return [...range.getClientRects()].map(({ left, right, top, bottom }) => ({ left, right, top, bottom }));
          };
          return {
            documentWidth: document.scrollingElement.scrollWidth,
            fields: [...article.querySelectorAll('dl > div')].map(row => {
              const label = row.querySelector('dt');
              return { label: label.textContent, labelRects: textRects(label), valueRects: textRects(row.querySelector('dd')) };
            }),
          };
        });
        await info.attach(`daily-details-minimum-font-32-width-${width}.json`, {
          body: JSON.stringify({ documentWidth, fields }), contentType: 'application/json',
        });

        expect(documentWidth).toBe(width);
        expect(fields.map(field => field.label)).toEqual(expect.arrayContaining(['Finding', 'Source date']));
        for (const { label, labelRects, valueRects } of fields) {
          expect(labelRects.length, `${label} label lines`).toBeGreaterThan(0);
          expect(valueRects.length, `${label} value lines`).toBeGreaterThan(0);
          for (const { left, right } of [...labelRects, ...valueRects]) {
            expect(left, `${label} text left edge`).toBeGreaterThanOrEqual(0);
            expect(right, `${label} text right edge`).toBeLessThanOrEqual(width);
          }
          for (const labelLine of labelRects) {
            for (const valueLine of valueRects) {
              if (Math.min(labelLine.bottom, valueLine.bottom) > Math.max(labelLine.top, valueLine.top)) {
                const overlap = Math.min(labelLine.right, valueLine.right) - Math.max(labelLine.left, valueLine.left);
                expect(overlap, `${label} label and value overlap`).toBeLessThanOrEqual(0);
              }
            }
          }
        }
      });
    }
  } finally {
    await browser.close();
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
