const { chromium, test, expect } = require('@playwright/test');

const catalog = '/research/data/';
const lookupURL = catalog + '?source=apex-paper#find-source';
const captureHref = '/research/data/sources/9/#source-third11.source.apex-paper.p013.lf1-7';
const viewport = { width: 320, height: 720 };

test.use({ viewport });

function lookupControls(page) {
  const panel = page.locator('#find-source');
  const links = panel.getByRole('link', { name: 'apex-paper', exact: true });
  return { panel, links, lastCapture: links.nth(6), query: panel.getByRole('searchbox') };
}

async function observeHistory(page, cold) {
  await page.addInitScript(({ catalog, cold }) => {
    if (location.pathname !== catalog) return;
    addEventListener('pageshow', event => { window.sourceReturnPersisted = event.persisted; });
    if (cold) addEventListener('unload', () => {});
  }, { catalog, cold });
}

async function waitForLayout(page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

async function expectResults(page) {
  const { panel, links, lastCapture, query } = lookupControls(page);
  await expect(page).toHaveURL(lookupURL);
  await expect(query).toHaveValue('apex-paper');
  await expect(panel.getByRole('status')).toHaveText('7 sources match “apex-paper”.');
  await expect(links).toHaveCount(7);
  await expect(lastCapture).toHaveAttribute('href', captureHref);
  await expect(lastCapture).toHaveAccessibleDescription(/PDF page 13 · lines 1–7$/);
}

async function openLastCapture(page) {
  await page.goto('/research/');
  await page.getByRole('main').getByRole('link', { name: 'Data & sources', exact: true }).press('Enter');
  await expect(page).toHaveURL(catalog);
  const { panel, links, lastCapture, query } = lookupControls(page);
  await query.fill('apex-paper');
  await page.keyboard.press('Enter');
  await expectResults(page);

  await page.keyboard.press('Tab');
  await expect(panel.getByRole('button', { name: 'Find sources' })).toBeFocused();
  for (const link of await links.all()) {
    await page.keyboard.press('Tab');
    await expect(link).toBeFocused();
  }
  await waitForLayout(page);
  await expect(lastCapture).toBeInViewport({ ratio: 1 });
  const departure = await lastCapture.evaluate(link => ({
    timeOrigin: performance.timeOrigin,
    top: link.getBoundingClientRect().top,
  }));

  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(captureHref);
  await expect(page.locator('article:target')).toBeInViewport();
  return departure;
}

async function expectHistory(page, previousTimeOrigin, cached) {
  await expect.poll(() => page.evaluate(() => window.sourceReturnPersisted)).toBe(cached);
  const visit = await page.evaluate(() => ({
    timeOrigin: performance.timeOrigin,
    type: performance.getEntriesByType('navigation')[0]?.type,
  }));
  if (cached) {
    expect(visit.timeOrigin).toBe(previousTimeOrigin);
  } else {
    expect(visit.timeOrigin).not.toBe(previousTimeOrigin);
    expect(visit.type).toBe('back_forward');
  }
  return visit.timeOrigin;
}

async function expectReaderReturn(page, departure, cached) {
  const { lastCapture } = lookupControls(page);
  await expectResults(page);
  const timeOrigin = await expectHistory(page, departure.timeOrigin, cached);
  await expect(lastCapture).toBeFocused();
  await waitForLayout(page);
  await expect(lastCapture).toBeInViewport({ ratio: 1 });
  await expect.poll(() => lastCapture.evaluate(
    (link, top) => Math.abs(link.getBoundingClientRect().top - top), departure.top
  )).toBeLessThanOrEqual(2);
  return timeOrigin;
}

async function expectNextTab(page) {
  await page.keyboard.press('Tab');
  await expect(lookupControls(page).panel.getByRole('link', { name: 'Browse the source ledger parts' })).toBeFocused();
}

test('cold Back restores the seventh source capture and resumes the Tab order at 320px', async ({ page }) => {
  await observeHistory(page, true);
  const departure = await openLastCapture(page);
  await page.goBack({ waitUntil: 'commit' });
  await expectReaderReturn(page, departure, false);
  await expectNextTab(page);
});

test('a separate visit to the same source URL leaves catalog focus alone on Back', async ({ page }) => {
  await observeHistory(page, true);
  const departure = await openLastCapture(page);
  await page.goBack({ waitUntil: 'commit' });
  const firstTimeOrigin = await expectReaderReturn(page, departure, false);

  await page.goForward({ waitUntil: 'commit' });
  await expect(page).toHaveURL(captureHref);
  await expect(page.locator('article:target')).toBeInViewport();
  await page.goBack({ waitUntil: 'commit' });
  const secondTimeOrigin = await expectReaderReturn(page, { ...departure, timeOrigin: firstTimeOrigin }, false);

  await page.goto(captureHref);
  await expect(page.locator('article:target')).toBeInViewport();
  await page.goBack({ waitUntil: 'commit' });
  await expectResults(page);
  await expectHistory(page, secondTimeOrigin, false);
  await waitForLayout(page);
  await expect(lookupControls(page).lastCapture).not.toBeFocused();
});

test('cached Back retains the source position and focus at 320px', async ({ baseURL, browserName, isMobile }) => {
  test.skip(browserName !== 'chromium' || isMobile, 'Enable and verify Chromium’s back-forward cache');
  const browser = await chromium.launch({ channel: 'chromium', ignoreDefaultArgs: ['--disable-back-forward-cache'] });
  try {
    const page = await browser.newPage({ baseURL, viewport });
    await observeHistory(page, false);
    const departure = await openLastCapture(page);
    await page.goBack({ waitUntil: 'commit' });
    await expectReaderReturn(page, departure, true);
    await expectNextTab(page);
  } finally {
    await browser.close();
  }
});
