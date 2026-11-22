const { test, expect } = require('@playwright/test');

test.use({ launchOptions: { firefoxUserPrefs: {
  'font.minimum-size.x-western': 32,
  'font.minimum-size.x-unicode': 32,
} } });

const destinations = ['Daily scan', 'Research', 'Companies', 'Paid work', 'About'];

function navigation(page) {
  const header = page.locator('body > header.site-header');
  const nav = header.getByRole('navigation', { name: 'Main', exact: true });
  return {
    header,
    nav,
    links: destinations.map(name => nav.getByRole('link', { name, exact: true })),
    skip: page.getByRole('link', { name: 'Skip to content' }),
    wordmark: header.getByRole('link', { name: /ScienceToStartup/ }),
    search: header.getByRole('link', { name: 'Search the guide' }),
    menu: header.getByText('Menu', { exact: true }),
  };
}

async function tabTo(page, ...controls) {
  for (const control of controls) {
    await page.keyboard.press('Tab');
    await expect(control).toBeFocused();
  }
}

async function expectHitArea(control, { minWidth = 44, label = false } = {}) {
  const { viewport, box, hits, text } = await control.evaluate((element, measureLabel) => {
    const rect = element.getBoundingClientRect();
    const containsPoint = (x, y) => element.contains(document.elementFromPoint(x, y));
    const fractions = [0.2, 0.5, 0.8];
    const hits = fractions.flatMap(x => fractions.map(y =>
      containsPoint(rect.left + x * rect.width, rect.top + y * rect.height)));
    const range = document.createRange();
    range.selectNodeContents(element);
    const text = measureLabel ? Array.from(range.getClientRects())
      .filter(line => line.width && line.height)
      .map(line => ({
        left: line.left,
        right: line.right,
        edgesClickable: [line.left + 1, line.right - 1]
          .every(x => containsPoint(x, line.top + line.height / 2)),
      })) : [];
    return { viewport: innerWidth, box: rect.toJSON(), hits, text };
  }, label);

  const target = `${control} at ${viewport}px (${JSON.stringify(box)})`;
  expect(box.width, target).toBeGreaterThanOrEqual(minWidth);
  expect(box.height, target).toBeGreaterThanOrEqual(44);
  expect(box.left, target).toBeGreaterThanOrEqual(0);
  expect(box.right, target).toBeLessThanOrEqual(viewport);
  expect(hits, target).toEqual(Array(9).fill(true));
  if (label) {
    expect(text.length, target).toBeGreaterThan(0);
    for (const line of text) {
      expect(line.left, target).toBeGreaterThanOrEqual(0);
      expect(line.right, target).toBeLessThanOrEqual(viewport);
      expect(line.edgesClickable, target).toBe(true);
    }
  }
}

async function expectViewportWidth(page, width) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
}

async function checkInlineNavigation(page) {
  for (const width of [701, 720, 800]) {
    await test.step(`${width}px inline navigation`, async () => {
      await page.setViewportSize({ width, height: 844 });
      await page.goto('/work/');
      const { skip, wordmark, search, menu, nav, links } = navigation(page);
      await expect(menu).toBeHidden();
      await expect(nav.getByRole('link')).toHaveText(destinations);
      await tabTo(page, skip, wordmark);
      await expectHitArea(wordmark);
      for (const link of links) {
        await tabTo(page, link);
        await expectHitArea(link, { minWidth: 24, label: true });
      }
      await tabTo(page, search);
      await expectHitArea(search);
      await expectViewportWidth(page, width);
    });
  }
}

test.describe('native navigation with standard text', () => {
  test.skip(({ browserName, isMobile }) => browserName !== 'chromium' || isMobile,
    'This suite covers standard-size text in Chromium');

  test.describe('without scripts', () => {
    test.use({ javaScriptEnabled: false });

    test('standard-text navigation stays keyboard reachable at tablet widths', async ({ page }) => {
      await checkInlineNavigation(page);
    });
  });

  for (const path of ['/work/', '/companies/']) {
    test(`the open menu leaves focused filters unobscured on ${path} at 320px`, async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 720 });
      await page.goto(path);
      const { header, skip, wordmark, search, menu, nav, links } = navigation(page);
      const main = page.getByRole('main');
      const breadcrumb = main.getByRole('link', { name: 'Overview' });
      const filterSearch = main.getByRole('searchbox', {
        name: path === '/work/' ? 'Search listings' : 'Search companies',
      });
      await expect(filterSearch).toBeVisible();
      await expect(nav).toHaveCount(0);
      await tabTo(page, skip, wordmark, search, menu);
      await page.keyboard.press('Space');
      await expect(nav.getByRole('link')).toHaveText(destinations);
      for (const link of links) {
        await tabTo(page, link);
        await expectHitArea(link, { label: true });
      }

      await tabTo(page, breadcrumb, filterSearch);
      await expectHitArea(filterSearch);
      if (path === '/work/') {
        const filters = main.getByText('Filters', { exact: true });
        await tabTo(page, filters);
        await expectHitArea(filters);
      }
      await expect(header.locator('details.site-menu')).toHaveJSProperty('open', true);
      await expectViewportWidth(page, 320);
    });
  }
});

test.describe('native navigation with enlarged Firefox text and no scripts', () => {
  test.use({ javaScriptEnabled: false });
  test.skip(({ browserName }) => browserName !== 'firefox', 'The test uses Firefox minimum font sizes');

  for (const width of [320, 390]) {
    test(`main links stay in view in a single keyboard disclosure at ${width}px`, async ({ page, baseURL }) => {
      test.setTimeout(90_000);
      await page.setViewportSize({ width, height: width === 320 ? 720 : 844 });
      const researchURL = new URL('/research/', baseURL).href;
      await page.route('https://sciencetostartup.com/research/', route =>
        route.fulfill({ status: 302, headers: { location: researchURL } }));

      for (const [path, current] of [
        ['/work/', 'Paid work'], ['/daily/', 'Daily scan'],
        ['/companies/', 'Companies'], ['/research/', 'Research'],
      ]) {
        await test.step(path, async () => {
          await page.goto(path);
          const { header, skip, wordmark, search, menu, nav, links } = navigation(page);
          const closedHeight = (await header.boundingBox()).height;
          if (width === 320) expect(closedHeight).toBeLessThanOrEqual(110);
          await expect(nav).toHaveCount(0);
          await expect(search).toHaveAttribute('href', '/?search=#browse-guide');

          await tabTo(page, skip, wordmark, search, menu);
          for (const control of [wordmark, search, menu]) await expectHitArea(control);
          await page.keyboard.press('Enter');
          await expect(nav).toHaveCount(1);
          await expect(nav.getByRole('link')).toHaveText(destinations);
          await expect(nav.getByRole('link', { name: current, exact: true })).toHaveAttribute('aria-current', 'page');
          for (const link of links) {
            await tabTo(page, link);
            await expectHitArea(link, { label: true });
          }
          const panelBox = await nav.boundingBox();
          expect(panelBox.x).toBeGreaterThanOrEqual(0);
          expect(panelBox.x + panelBox.width).toBeLessThanOrEqual(width);
          await expectViewportWidth(page, width);

          await menu.press('Enter');
          await expect(nav).toHaveCount(0);
          expect((await header.boundingBox()).height).toBe(closedHeight);

          if (path === '/work/') {
            await page.keyboard.press('Enter');
            const research = nav.getByRole('link', { name: 'Research', exact: true });
            if (width === 320) {
              await tabTo(page, links[0], research);
              await page.keyboard.press('Enter');
            } else {
              await research.click();
            }
            await expect(page).toHaveURL(researchURL);
            await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Research on\s*AI data\./);
          }
        });
      }
    });
  }

  test('enlarged Firefox navigation stays keyboard reachable at tablet widths', async ({ page }) => {
    test.setTimeout(90_000);
    await checkInlineNavigation(page);
  });

  test('paid work source index is the first tab in the dossier source disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
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
