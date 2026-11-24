const { test, expect, firefox } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const release = require('../../data/editorial-release.json');
const work = require('../../data/work-routes.json');
const promotionId = release.homepage.work_candidate_route_ids[0];
const promotion = work.routes.find(row => row.id === promotionId);
const approved = promotion.editorial_review.receipts.find(row => row.id === promotion.editorial_review.approved_terms_receipt_id);
const listing = promotion.editorial_review.actions.find(action => action.purpose === 'description');
const reviewed = Date.parse(approved.checked_at);
const day = 86_400_000;
const expires = reviewed + release.publication_policy.homepage_work_max_age_days * day;
const recordedProgram = '[data-recorded-program="invisible.work.meridial-network"]';
const reportTitle = 'State of AI Data Labs and Human Feedback';
const reportPath = '/research/state-of-ai-data-labs/';

test('home leads with the field guide and links dated examples to their sources', async ({ page }) => {
  await page.clock.setFixedTime(new Date(expires));
  for (const viewport of [{ width: 320, height: 720 }, { width: 390, height: 844 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const heading = page.getByRole('heading', { level: 1, name: 'The business of AI training data', exact: true });
    await expect(heading).toBeInViewport({ ratio: 1 });
    const main = page.getByRole('main');
    await expect(main.getByText('See what suppliers sell. Check the pay and terms for training work.')).toBeVisible();
    const report = main.getByRole('article', { name: reportTitle, exact: true });
    await expect(report).toBeVisible();
    await expect(report.locator('time')).toHaveAttribute('datetime', '2026-11-12');
    await expect(report.getByText('12 Nov 2026 snapshot', { exact: true })).toBeVisible();
    await expect(report.getByRole('link')).toHaveCount(1);
    const reportLink = report.getByRole('link', { name: `Read the report ${reportTitle}`, exact: true });
    await expect(reportLink).toHaveAttribute('href', reportPath);
    await expect(reportLink).toHaveAccessibleDescription('Prolific, for example, sells participant access and managed collection.');
    await expect(reportLink.getByRole('heading', { level: 2, name: reportTitle, exact: true })).toBeVisible();
    await expect(main.locator('.hero-actions [data-count="work"]')).toHaveText(String(release.counts.work_routes));

    const company = page.locator('[data-observation="snorkel_ai.metric.major-growth_metrics-0"]');
    await expect(company).toBeVisible();
    await expect(company).toContainText('$375M annualized revenue run rate');
    await expect(company.locator('.example-pay [aria-hidden="true"]')).toHaveText('>');
    await expect(company.locator('.example-pay .sr-only')).toHaveText('More than');
    await expect(company.locator('time')).toHaveAttribute('datetime', '2026-09-22');
    await expect(company.getByRole('link', { name: 'Original disclosure' }))
      .toHaveAttribute('href', 'https://snorkel.ai/blog/data-2-0-and-the-research-era-of-ai-data/');
    const figure = await company.locator('.example-pay').boundingBox();
    expect(figure.y).toBeLessThan((await company.locator('.example-summary').boundingBox()).y);
    if (viewport.width === 320) expect(figure.y).toBeLessThan(viewport.height);

    const program = page.locator(recordedProgram);
    await expect(program).toBeVisible();
    await expect(program).toContainText('Pay agreed before project');
    await expect(program.locator('time')).toHaveAttribute('datetime', '2026-10-28');
    await expect(program.getByRole('link', { name: 'Read recorded terms' }))
      .toHaveAttribute('href', '/company/invisible/#invisible.work.meridial-network');
    await expect(program.getByRole('link', { name: 'Official program page' })).toHaveAttribute('href', 'https://www.meridial.ai/');
    expect((await report.boundingBox()).y).toBeLessThan((await company.boundingBox()).y);
    await expect(page.locator('a[href="/research/data/"]').first()).toBeVisible();
  }

  await page.locator('#research a[href="/method/#method-notes"]').click();
  await expect(page).toHaveURL(/\/method\/#method-notes$/);
  await expect(page.getByRole('heading', { name: 'How figures are shown' })).toBeVisible();
});

test('a short phone opens the whole report card by pointer or keyboard without JavaScript', async ({ browser, browserName, baseURL }) => {
  const context = await browser.newContext({ baseURL, javaScriptEnabled: false, viewport: { width: 320, height: 640 } });
  try {
    const page = await context.newPage();
    await page.goto('/');
    const report = page.getByRole('link', { name: `Read the report ${reportTitle}`, exact: true });
    const priorLink = page.getByRole('navigation', { name: 'Browse the guide' })
      .getByRole('link', { name: 'Research', exact: true });
    const tab = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
    await expect(report).toBeInViewport({ ratio: 1 });
    await expect(report.getByText('Read the report →', { exact: true })).toBeInViewport({ ratio: 1 });
    await priorLink.focus();
    await page.keyboard.press(tab);
    await expect(report).toBeFocused();
    await expect(report).toHaveCSS('outline-style', 'solid');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(reportPath);
    await expect(page.getByRole('heading', { level: 1, name: reportTitle })).toBeVisible();

    await page.goto('/');
    await report.click({ position: { x: 6, y: 6 } });
    await expect(page).toHaveURL(reportPath);
  } finally {
    await context.close();
  }
});

test('the three guide links stay readable and usable on narrow phones', async ({ page }) => {
  for (const width of [320, 360, 375]) {
    await page.setViewportSize({ width, height: 720 });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const actions = page.getByRole('navigation', { name: 'Browse the guide' });
    let nextRow = 0;
    for (const [name, path] of [['Companies', '/companies/'], ['Paid work', '/work/'], ['Research', '/research/']]) {
      const link = actions.getByRole('link', { name, exact: true });
      await expect(link).toHaveAttribute('href', path);
      await expect(link).toBeInViewport({ ratio: 1 });
      const box = await link.boundingBox();
      expect(box.y).toBeGreaterThanOrEqual(nextRow - 0.5);
      expect(box.height).toBeGreaterThanOrEqual(43.5);
      expect(box.x).toBeGreaterThanOrEqual(-0.5);
      expect(box.x + box.width).toBeLessThanOrEqual(width + 0.5);
      nextRow = box.y + box.height;
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
});

test('guide link labels and details wrap between words with enlarged Firefox text', async ({ browserName, baseURL }) => {
  test.skip(browserName !== 'firefox', 'Uses Firefox minimum font sizes');
  const browser = await firefox.launch({ firefoxUserPrefs: {
    'font.minimum-size.x-western': 32,
    'font.minimum-size.x-unicode': 32,
  } });
  try {
    const page = await browser.newPage({ baseURL, javaScriptEnabled: false, reducedMotion: 'reduce' });
    for (const width of [320, 775]) {
      await page.setViewportSize({ width, height: 720 });
      await page.goto('/');
      const actions = page.getByRole('navigation', { name: 'Browse the guide' });
      for (const name of ['Companies', 'Paid work', 'Research']) {
        const link = actions.getByRole('link', { name, exact: true });
        const { height } = await link.boundingBox();
        expect(height).toBeGreaterThanOrEqual(44);
        const brokenWords = await link.evaluate(element => {
          const bounds = element.getBoundingClientRect();
          const range = document.createRange();
          const broken = [];
          for (const attribute of ['aria-labelledby', 'aria-describedby']) {
            const text = document.getElementById(element.getAttribute(attribute));
            const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
              for (const { 0: word, index } of node.data.matchAll(/\S+/g)) {
                range.setStart(node, index);
                range.setEnd(node, index + word.length);
                const lines = [...range.getClientRects()].filter(line => line.width);
                if (lines.length !== 1 || lines[0].left < bounds.left - 0.5 || lines[0].right > bounds.right + 0.5) {
                  broken.push(word);
                }
              }
            }
          }
          return broken;
        });
        expect(brokenWords, `${name} at ${width}px`).toEqual([]);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    }
  } finally {
    await browser.close();
  }
});

test('home promotes only approved current terms and retains all binding conditions', async ({ page }, info) => {
  expect(promotionId).toBe('g2i.work.senior-swe-training-7c54f48a');
  const example = page.locator('#home-work-example [data-home-route]');
  for (const timestamp of [reviewed, expires - 1]) {
    await page.clock.setFixedTime(new Date(timestamp));
    await page.goto('/');
    await expect(example).toHaveAttribute('data-home-route', promotionId);
  }
  await expect(example.locator('.example-pay')).toHaveText(promotion.pay_label);
  await expect(example.locator('.example-summary')).toHaveText(promotion.geography);
  await expect(example.getByRole('link', { name: 'Full work record' }))
    .toHaveAttribute('href', `/company/${promotion.company_id}/#${promotionId}`);
  await expect(example.getByRole('link', { name: /Original listing/ })).toHaveAttribute('href', listing.url);
  await expect(example.locator('time')).toHaveAttribute('datetime', approved.checked_on);
  await expect(page.locator(recordedProgram)).toBeHidden();
  await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(1);
  await example.locator('summary').click();
  await expect(example.locator('q')).toBeVisible();
  await expect(example.locator('q')).toHaveText(promotion.source_quote);
  await expect(example.locator('.example-conditions li')).toHaveText([
    ...promotion.requirements, promotion.eligibility, promotion.assessment,
    promotion.hours, promotion.duration, promotion.availability_note,
  ]);
  await example.locator('summary').click();
  await expect(page.locator('.hero').getByRole('link', { name: 'Companies' })).toBeVisible();
  await expect(page.locator('.hero').getByRole('link', { name: 'Paid work', exact: true })).toBeVisible();
  await info.attach(`home-entry-${info.project.name}.png`, {
    body: await page.screenshot({ fullPage: false, animations: 'disabled', scale: 'css' }), contentType: 'image/png',
  });
});

test('three-day expiry withdraws stale examples and preserves evergreen browse', async ({ page }) => {
  for (const timestamp of [reviewed - 1, expires]) {
    await page.clock.setFixedTime(new Date(timestamp));
    await page.goto('/');
    await expect(page.locator('#home-work-example')).toBeHidden();
    await expect(page.locator(recordedProgram)).toBeVisible();
    await expect(page.locator('.hero-actions').getByRole('link', { name: 'Paid work', exact: true })).toBeVisible();
    await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(0);
  }
});

test('expiry moves focus from the promotion to the native Work link', async ({ page }) => {
  await page.clock.install({ time: new Date(expires - day) });
  await page.clock.pauseAt(new Date(expires - 1_000));
  await page.goto('/');
  const slot = page.locator('#home-work-example');
  const focused = slot.getByRole('link', { name: /original listing|official program page/i });
  await focused.focus();
  await expect(focused).toBeFocused();
  await page.clock.fastForward(60_000);
  const fallback = page.locator('.hero-actions').getByRole('link', { name: 'Paid work', exact: true });
  await expect(fallback).toBeFocused();
  await expect(fallback).toBeInViewport();
  await expect(slot).toBeHidden();
  await expect(page.locator(recordedProgram)).toBeVisible();
});

test('without JavaScript the homepage offers its menu and native browse links', async ({ browser, baseURL }) => {
  const viewport = { width: 320, height: 844 };
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL, viewport });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.locator('#home-work-example')).toBeHidden();
  await expect(page.locator('.hero').getByRole('link', { name: 'Companies', exact: true })).toHaveAttribute('href', '/companies/');
  await expect(page.locator(recordedProgram)).toBeVisible();
  await page.locator('.home-menu summary').press('Enter');
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Daily scan' })).toBeVisible();
  await page.locator('.home-menu summary').press('Enter');
  const browse = page.getByRole('link', { name: 'Browse the guide', exact: true });
  const label = browse.locator('.site-search-label');
  await expect(label).toHaveText('Browse');
  const bounds = await label.boundingBox();
  expect(bounds.width).toBeGreaterThan(20);
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
  await expect(browse.locator('kbd')).toBeHidden();
  await browse.press('Enter');
  await expect(page).toHaveURL(/#browse-guide$/);
  const routes = page.getByRole('navigation', { name: 'Browse the guide' }).getByRole('link');
  for (const [index, name] of ['Companies', 'Paid work', 'Research'].entries()) {
    await expect(routes.nth(index)).toHaveAccessibleName(name);
  }
  expect(await routes.evaluateAll(links => links.map(link => link.getAttribute('href'))))
    .toEqual(['/companies/', '/work/', '/research/']);
  await context.close();
});

test('the Home header can browse when the search runtime is blocked', async ({ page }) => {
  await page.route('**/home-runtime.js', route => route.abort());
  await page.goto('/');
  const browse = page.getByRole('link', { name: 'Browse the guide', exact: true });
  await expect(browse.locator('kbd')).toBeHidden();
  await expect(browse.locator('.ui-icon')).toBeHidden();
  await browse.click();
  await expect(page).toHaveURL(/#browse-guide$/);
  await expect(page.locator('#home-search')).toBeHidden();
});

test('the Home header becomes Search when its pending runtime binds', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  let resume;
  const pending = new Promise(resolve => { resume = resolve; });
  await page.route('**/home-runtime.js', async route => {
    await pending;
    await route.continue();
  });
  try {
    await page.goto('/', { waitUntil: 'commit' });
    const opener = page.locator('#home-search-open');
    const layout = async () => ({
      controls: await page.locator('#home-search-open, .home-menu summary').evaluateAll(nodes =>
        nodes.map(node => {
          const { x, y, width, height } = node.getBoundingClientRect();
          return [x, y + scrollY, width, height];
        })),
      heroTop: await page.locator('#hero-title').evaluate(node => node.getBoundingClientRect().top + scrollY),
    });
    await expect(opener).toHaveAccessibleName('Browse the guide');
    await expect(opener).toHaveCSS('padding-left', '4px');
    await expect(page.locator('.site-header')).toHaveCSS('column-gap', '4px');
    await expect(opener.locator('kbd')).toBeHidden();
    const before = await layout();
    await opener.click();
    await expect(page).toHaveURL(/#browse-guide$/);
    await expect(page.locator('#home-search')).toBeHidden();
    resume();
    await page.waitForLoadState('domcontentloaded');
    await expect(opener).toHaveAccessibleName('Search the guide');
    expect(await layout()).toEqual(before);
    await expect(opener).toHaveAttribute('href', '/?search=#browse-guide');
    await expect(opener).toHaveAttribute('aria-keyshortcuts', 'Control+K Meta+K');
    await expect(opener.locator('kbd')).not.toHaveAttribute('hidden', '');
    await opener.click();
    await expect(page.getByRole('dialog', { name: 'Search the guide' })).toBeVisible();
  } finally {
    resume();
  }
});

test.describe('home keyboard controls in compact viewports', () => {
  test.skip(({ browserName }) => browserName !== 'chromium', 'Exercise the audited Chromium keyboard behavior');
  test.use({ reducedMotion: 'reduce' });

  async function tabThrough(page, ...controls) {
    for (const control of controls) {
      await page.keyboard.press('Tab');
      await expect(control).toBeFocused();
    }
  }

  function headerLinks(page) {
    return ['Skip to content', 'ScienceToStartup home', 'Search the guide']
      .map(name => page.getByRole('link', { name, exact: true }));
  }

  async function expectUncoveredFocus(control) {
    await expect(control).toBeFocused();
    await expect(control).toBeInViewport({ ratio: 1 });
    await expect.poll(() => control.evaluate(element => {
      const { left, top, width, height } = element.getBoundingClientRect();
      const samples = [0.2, 0.5, 0.8];
      return {
        focusVisible: element.matches(':focus-visible'),
        hits: samples.flatMap(x => samples.map(y =>
          element.contains(document.elementFromPoint(left + width * x, top + height * y)))).filter(Boolean).length,
      };
    })).toEqual({ focusVisible: true, hits: 9 });
  }

  for (const { width, height, name, path } of [
    { width: 640, height: 436, name: 'Research data', path: '/research/data/' },
    { width: 320, height: 218, name: 'Paid work', path: '/work/' },
  ]) {
    test(`home Menu leaves ${name} operable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto('/');
      await page.evaluate(() => document.fonts.ready);
      const menu = page.locator('.home-menu');
      const nav = menu.getByRole('navigation', { name: 'Main' });
      const menuLinks = ['Daily scan', 'Research', 'Companies', 'Paid work', 'About']
        .map(name => nav.getByRole('link', { name, exact: true }));
      const target = page.locator(`main a[href="${path}"], footer a[href="${path}"]`).first();

      await tabThrough(page, ...headerLinks(page), menu.getByText('Menu', { exact: true }));
      await page.keyboard.press('Enter');
      await expect(menu).toHaveJSProperty('open', true);
      await tabThrough(page, ...menuLinks);
      const controls = await page.locator('main :is(a, button, summary):visible, footer a:visible').count();
      for (let index = 0; index < controls; index++) {
        await page.keyboard.press('Tab');
        if (await target.evaluate(link => link === document.activeElement)) break;
      }
      await expect(menu).toHaveJSProperty('open', true);
      await expectUncoveredFocus(target);
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(path);
    });
  }

  for (const { height, title } of [
    { height: 218, title: 'home Search pages a tall selected result without moving focus' },
    { height: 178, title: 'home Search reveals the selected result in a 178px viewport' },
  ]) {
    test(title, async ({ page }) => {
      await page.setViewportSize({ width: 320, height });
      await page.goto('/');
      await page.evaluate(() => document.fonts.ready);
      const links = headerLinks(page);
      const opener = links.at(-1);
      const dialog = page.getByRole('dialog', { name: 'Search the guide' });
      const input = dialog.getByRole('combobox');
      const option = dialog.getByRole('option', { name: /^Mercor Company/ });

      await tabThrough(page, ...links);
      await page.keyboard.press('Enter');
      await expect(input).toBeFocused();
      await page.keyboard.type('Mercor');
      await expect(option).toBeVisible();
      await page.keyboard.press('ArrowDown');

      const optionId = await option.getAttribute('id');
      const expectSelection = async () => {
        await expect(input).toBeFocused();
        await expect(input).toBeInViewport({ ratio: 1 });
        await expect(input).toHaveValue('Mercor');
        await expect(input).toHaveAttribute('aria-activedescendant', optionId);
        await expect(option).toHaveAttribute('aria-selected', 'true');
        await expect(option).toHaveAttribute('href', '/company/mercor/');
      };
      const readResult = () => option.evaluate(element => {
        const results = element.closest('[role="listbox"]');
        const content = results.closest('.site-search-content');
        const scroller = content && getComputedStyle(content).overflowY === 'auto' ? content : results;
        const viewport = scroller.getBoundingClientRect();
        const top = Math.max(0, viewport.top);
        const bottom = Math.min(innerHeight, viewport.bottom);
        const range = document.createRange();
        const visibleLines = ['strong', 'span'].flatMap(selector => {
          range.selectNodeContents(element.querySelector(selector));
          return Array.from(range.getClientRects(), line => line.top >= top - 0.5 && line.bottom <= bottom + 0.5
            && element.contains(document.elementFromPoint((line.left + line.right) / 2, (line.top + line.bottom) / 2)));
        });
        return {
          resultHeight: element.getBoundingClientRect().height,
          viewportHeight: viewport.height,
          scrollTop: scroller.scrollTop,
          visibleLines,
        };
      });

      await expectSelection();
      const initial = await readResult();
      expect(initial.visibleLines[0]).toBe(true);
      if (height === 218) {
        expect(initial.resultHeight).toBeGreaterThan(initial.viewportHeight);
        expect(initial.visibleLines.at(-1)).toBe(false);
      }
      const seen = [...initial.visibleLines];
      let pages = 0;
      while (pages < 4 && seen.some(visible => !visible)) {
        const previous = (await readResult()).scrollTop;
        await page.keyboard.press('PageDown');
        await expect.poll(async () => (await readResult()).scrollTop).toBeGreaterThan(previous);
        const down = await readResult();
        down.visibleLines.forEach((visible, index) => { seen[index] ||= visible; });
        pages++;
      }
      expect(seen).toEqual(initial.visibleLines.map(() => true));
      await expectSelection();

      for (let n = 0; n < pages; n++) await page.keyboard.press('PageUp');
      await expect.poll(async () => Math.abs((await readResult()).scrollTop - initial.scrollTop)).toBeLessThan(1);
      await expectSelection();
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expectUncoveredFocus(opener);
    });
  }
});

test('homepage Search loads only its small component and index when invoked', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto('/');
  await expect(page.locator('#home-search')).not.toBeVisible();
  expect(requests.some(url => /home-search\.js|presentation\/search\.|\/js\/(app|data)\.|research\.json/.test(url))).toBe(false);
  await page.locator('#home-search-open').click();
  await expect(page.getByRole('dialog', { name: 'Search the guide' })).toBeVisible();
  const input = page.getByRole('combobox', { name: 'Search the guide' });
  await expect(input).toHaveAttribute('placeholder', 'Search');
  await expect(input).toHaveAccessibleDescription('Search research or companies and their products. Try a role or skill for paid work.');
  expect(requests.some(url => /home-search\.js/.test(url))).toBe(true);
  expect(requests.some(url => /presentation\/search\./.test(url))).toBe(true);
  expect(requests.some(url => /\/js\/(app|data)\.|presentation\/(archive|company-|summary)\.|research\.json/.test(url))).toBe(false);
  await input.fill('C++');
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter(row => ['serious', 'critical'].includes(row.impact))).toEqual([]);
  const action = page.locator('#home-search-results a').filter({ hasText: 'Find paid work matching' });
  await expect(action).toHaveAttribute('href', '/work/?q=C%2B%2B');
  await page.locator('#home-search-close').click();
  await expect(page.locator('#home-search-open')).toBeFocused();
});

test('homepage Search leads to the company directory, comparison and market figures', async ({ page }) => {
  for (const { queries, route, type, destination } of [
    { queries: ['companies', 'company directory'], route: '/companies/', type: 'Company directory',
      destination: page.getByRole('heading', { name: 'AI data companies', exact: true }) },
    { queries: ['compare', 'compare companies', 'shortlist'], route: '/explore/#compare', type: 'Comparison',
      destination: page.getByRole('combobox', { name: 'Add a company', exact: true }) },
    { queries: ['AI data market', 'market overview', 'revenue'], route: '/explore/#business-health', type: 'Market',
      destination: page.getByRole('heading', { name: 'Revenue & growth.', exact: true }) },
  ]) {
    await page.goto('/');
    await page.getByRole('link', { name: 'Search the guide' }).click();
    const search = page.getByRole('dialog', { name: 'Search the guide' });
    const input = search.getByRole('combobox');
    const first = search.getByRole('option').first();
    for (const query of queries) {
      await input.fill(query);
      await expect(first).toHaveAttribute('href', route);
      await expect(first).toHaveAttribute('data-result-type', type);
    }
    await first.click();
    await expect(page).toHaveURL(new URL(route, page.url()).href);
    await expect(destination).toBeInViewport();
  }

  await page.goto('/');
  await page.getByRole('link', { name: 'Search the guide' }).click();
  const search = page.getByRole('dialog', { name: 'Search the guide' });
  await search.getByRole('combobox').fill('market research');
  await expect(search.getByRole('option').first()).toHaveAttribute('href',
    '/research/state-of-ai-data-labs/chapters/market-structure/');
});

test('keyboard paging keeps its focused button and outline inside the short dialog at a 28px Firefox minimum', async ({ browserName, baseURL }) => {
  test.skip(browserName !== 'firefox', 'Uses a Firefox text preference');
  const browser = await firefox.launch({ firefoxUserPrefs: { 'font.minimum-size.x-western': 28 } });
  try {
    const page = await browser.newPage({ baseURL });
    const opener = page.getByRole('link', { name: 'Search the guide' });
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const more = dialog.getByRole('button', { name: 'Show 7 more', exact: true });
    const outlineFits = button => {
      const { top, bottom } = button.getBoundingClientRect();
      const dialog = button.closest('dialog');
      const dialogBox = dialog.getBoundingClientRect();
      const { outlineStyle, outlineWidth, outlineOffset } = getComputedStyle(button);
      const outset = parseFloat(outlineWidth) + parseFloat(outlineOffset);
      const innerTop = dialogBox.top + dialog.clientTop;
      return outlineStyle === 'solid' && top - outset >= Math.max(0, innerTop)
        && bottom + outset <= Math.min(innerHeight, innerTop + dialog.clientHeight);
    };

    for (const height of [360, 373]) {
      await page.setViewportSize({ width: 621, height });
      await page.goto('/');
      await opener.press('Enter');
      await dialog.getByRole('combobox').fill('feedback');
      await expect(more).toBeVisible();
      await page.keyboard.press('Tab');
      await expect(dialog.getByRole('button', { name: 'Close search' })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(more).toBeFocused();
      await expect.poll(() => more.evaluate(outlineFits)).toBe(true);
      await page.keyboard.press('Enter');
      await expect(dialog.getByRole('option')).toHaveCount(15);
      await expect(more).toBeFocused();
      await expect.poll(() => more.evaluate(outlineFits)).toBe(true);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
    }
  } finally {
    await browser.close();
  }
});

test('failed homepage search keeps usable browse actions and a retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', route => route.abort());
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('.site-search-fallback').getByRole('link', { name: 'Browse companies' })).toHaveAttribute('href', '/companies/');
  await page.locator('#home-search-input').fill('RLHF  jobs');
  await expect(page.getByRole('link', { name: 'Search paid work for this query' })).toHaveAttribute('href', '/work/?q=RLHF++jobs');
  await page.locator('#home-search-close').click();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).not.toContainText('could not load');
});

test('a refused Search component retains the query and retries with a new request', async ({ page }) => {
  await page.route('**/home-search.js', route => route.abort());
  await page.goto('/');
  await page.keyboard.press('Control+k');
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await page.locator('#home-search-input').fill('RLHF  jobs');
  const workRecovery = page.getByRole('link', { name: 'Search paid work for this query' });
  await expect(workRecovery).toHaveCount(1);
  await expect(workRecovery).toHaveAttribute('href', '/work/?q=RLHF++jobs');
  const retried = page.waitForResponse(response => /home-search\.js\?retry=1$/.test(response.url()));
  await page.locator('[data-home-component-retry]').click();
  expect((await retried).ok()).toBe(true);
  await expect(page.locator('#home-search-results')).toBeVisible();
});

test('homepage search times out a stalled index and retries without reporting empty results', async ({ page }) => {
  await page.clock.install({ time: new Date(reviewed + day) });
  const { promise: indexRequest, resolve: holdRequest } = Promise.withResolvers();
  await page.route('**/presentation/search.*.json', route => holdRequest(route));
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Loading');
  const stalled = await indexRequest;
  await page.clock.fastForward(15_001);
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-message')).not.toContainText('No recorded company matches');
  await expect(page.locator('#home-search-work-recovery')).toBeVisible();
  await stalled.abort().catch(() => {});
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});

test('homepage search rejects stale index bytes and offers a usable retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, buildId: 'stale-release' } });
  });
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-results')).not.toBeVisible();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});
