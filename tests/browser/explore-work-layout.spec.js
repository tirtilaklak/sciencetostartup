const { test, expect } = require('@playwright/test');

test('Explore Work keeps the result count and controls readable at narrow widths', async ({ page }) => {
  const widths = [320, 360, 390, 480, 540, 600, 700, 844];
  for (const [fragment, label] of [['work', /^\d+ records/], ['work?q=India', 'No recorded matches']]) {
    await page.goto('/explore/#' + fragment);
    await expect(page.locator('#work-count')).toHaveText(label);
    for (const width of widths) {
      await page.setViewportSize({ width, height: 844 });
      const problems = await page.locator('#work-view .w4-results-bar').evaluate(bar => {
        const bounds = bar.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(bar.querySelector('#work-count'));
        const count = [...range.getClientRects()];
        const actions = [...bar.querySelectorAll('.w4-results-actions :is(a,button), #work-sort')];
        const overlaps = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
        const errors = [];
        if (count.length < 1 || count.length > 2) errors.push(`Count occupies ${count.length} lines`);
        for (const action of actions) {
          const box = action.getBoundingClientRect();
          if (box.width < 44 || box.height < 44) errors.push(`${action.id} target is too small`);
          if (box.left < bounds.left || box.right > bounds.right + 1) errors.push(`${action.id} extends outside the bar`);
          if (count.some(text => overlaps(text, box))) errors.push(`${action.id} overlaps the count`);
        }
        return errors;
      });
      expect(problems, `${fragment} at ${width}px`).toEqual([]);
    }
    await page.setViewportSize({ width: 320, height: 844 });
    await page.getByRole('combobox', { name: 'Sort', exact: true }).selectOption('hourly');
    await expect(page).toHaveURL(/sort=hourly$/);
    await expect(page.locator('#work-sort')).toHaveValue('hourly');
  }
});

test('all four Explore Work filters receive desktop pointer input', async ({ page, hasTouch }) => {
  test.skip(hasTouch, 'Checks the desktop pointer at and above the 901px breakpoint');
  await page.setViewportSize({ width: 901, height: 844 });
  await page.goto('/explore/#work');
  const panel = page.locator('#work-view .responsive-filter-panel');
  const summary = panel.locator('summary');
  const ids = ['work-kind', 'work-group', 'work-pay', 'work-eligibility'];
  await expect(panel).toBeVisible();

  for (const width of [901, 1024, 1280]) {
    await test.step(`${width}px`, async () => {
      if (page.viewportSize().width !== width) await page.setViewportSize({ width, height: 844 });

      for (const id of ids) {
        if (!(await panel.evaluate(node => node.open))) await summary.click();
        const select = panel.locator(`#${id}`);
        await expect(select).toBeInViewport({ ratio: 1 });
        const { hits, center } = await select.evaluate(node => {
          const box = node.getBoundingClientRect();
          const hits = [0.2, 0.5, 0.8].flatMap(x => [0.2, 0.5, 0.8].map(y =>
            document.elementFromPoint(box.left + box.width * x, box.top + box.height * y)?.id
          ));
          return { hits, center: { x: box.left + box.width / 2, y: box.top + box.height / 2 } };
        });
        expect(hits, `${id} pointer targets`).toEqual(Array(9).fill(id));
        await page.mouse.click(center.x, center.y);
        await expect(select).toBeFocused();
        await page.keyboard.press('Escape');
      }
    });
  }
});

test('native Work explains the full count and updates the live count for matching records', async ({ page, browser, request }) => {
  test.setTimeout(90_000);
  const { routes } = await (await request.get('/work-routes.json')).json();
  const count = page.locator('[data-work-count]');
  const fullCount = `${routes.length} records, including career pages and past listings`;
  const hourlyCount = `${routes.filter(route => route.pay_terms?.hourly_comparable).length} records with published hourly pay`;
  const archived = new Set(['historical', 'closed', 'contributions', 'paused', 'no_route', 'inquiry', 'information']);
  const current = routes.filter(route => !archived.has(route.status) && route.ai_data_work !== false);
  const named = current.filter(route => route.route_kind === 'named_listing');
  const programs = current.filter(route => route.route_kind === 'network_program');
  const companies = new Set([...named, ...programs].map(route => route.company_id));
  const totalText = `${named.length} named listings · ${programs.length} networks and programs · ${companies.size} companies`;
  const sections = page.locator('.work-section-disclosure');
  const jump = sections.getByText('Jump to section', { exact: true });
  const totals = sections.locator('.work-page-counts');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('.primary-link.work-link').click();
  await expect(page).toHaveURL(/\/work\/$/);
  await expect(page.getByRole('searchbox', { name: 'Search listings' })).toBeVisible();
  await expect(count).toHaveAttribute('aria-live', 'polite');
  await expect(count).toHaveAttribute('aria-atomic', 'true');
  await expect(page.locator('.work-page-counts')).toHaveCount(1);
  await expect(totals).toBeHidden();
  await page.evaluate(() => document.fonts.ready);
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(count).toHaveText(fullCount);
    await expect(count).toBeInViewport({ ratio: 1 });
    expect(await count.evaluate(node => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return range.getClientRects().length;
    })).toBe(1);
  }

  await page.locator('.work-page-filter-options summary').click();
  await page.getByRole('combobox', { name: 'Sort', exact: true }).selectOption('checked');
  await expect(count).toHaveText(fullCount);
  await jump.press('Enter');
  await expect(jump).toBeFocused();
  await expect(totals).toMatchAriaSnapshot(`- paragraph: ${totalText}`);
  await expect(count).toHaveText(fullCount);
  const pay = page.getByRole('combobox', { name: 'Pay unit' });
  await pay.selectOption('hourly');
  await expect(count).toHaveText(hourlyCount);
  await expect(totals).toMatchAriaSnapshot(`- paragraph: ${totalText}`);
  await jump.press('Space');
  await expect(totals).toBeHidden();
  await expect(count).toHaveText(hourlyCount);
  await pay.selectOption('');
  const search = page.getByRole('searchbox', { name: 'Search listings' });
  await search.fill('Sage');
  await expect(count).toHaveText('1 matching record');
  await search.fill('unfindable-work-record-fixture');
  await expect(count).toHaveText('0 matching records');
  await expect(page.locator('[data-work-empty]')).toContainText('No records match.');
  await page.getByRole('button', { name: 'Clear search and filters' }).click();
  await expect(count).toHaveText(fullCount);

  const noScript = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1024, height: 600 } });
  try {
    const fallback = await noScript.newPage();
    await fallback.goto(new URL('/work/?q=Sage', page.url()).href);
    await expect(fallback.locator('[data-work-count]')).toBeVisible();
    await expect(fallback.locator('[data-work-count]')).toHaveText(fullCount);
    await expect(fallback.locator('[data-work-route]')).toHaveCount(routes.length);
    const fallbackSections = fallback.locator('.work-section-disclosure');
    const fallbackTotals = fallbackSections.locator('.work-page-counts');
    await expect(fallbackTotals).toBeHidden();
    await fallbackSections.getByText('Jump to section', { exact: true }).press('Enter');
    await expect(fallbackTotals).toMatchAriaSnapshot(`- paragraph: ${totalText}`);
    await fallback.getByRole('navigation', { name: 'Work sections' }).getByRole('link', { name: 'Named listings' }).press('Enter');
    await expect(fallback).toHaveURL(/#named$/);
    await fallback.getByText('Before you apply', { exact: true }).press('Space');
    await expect(fallback.locator('.work-page-advice .note')).toBeVisible();
  } finally {
    await noScript.close();
  }
});

test('native Work shows the complete first role and hourly rate on the first screen', async ({ page, request }) => {
  test.setTimeout(90_000);
  const { routes } = await (await request.get('/work-routes.json')).json();
  const hourly = routes.filter(route => route.pay_terms?.hourly_comparable).length;
  const entries = [
    ['/work/', 'afterquery.work.technical-content-writer-contract', `${routes.length} records, including career pages and past listings`],
    ['/work/?pay=hourly&sort=hourly', 'afterquery.work.world-models', `${hourly} records with published hourly pay`],
  ];
  for (const [width, height] of [[320, 720], [390, 844], [760, 390], [844, 390], [1024, 600]]) {
    await page.setViewportSize({ width, height });
    for (const [url, firstId, scopedCount] of entries) {
      await test.step(`${url} at ${width} × ${height}`, async () => {
        await page.goto(url);
        const search = page.getByRole('searchbox', { name: 'Search listings' });
        await expect(search).toBeVisible();
        await expect(page.locator('[data-work-count]')).toHaveText(scopedCount);
        await page.evaluate(() => document.fonts.ready);
        expect(await page.evaluate(() => [scrollX, scrollY])).toEqual([0, 0]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
        await expect(page.locator('.work-page-counts')).toBeHidden();
        const first = page.locator('[data-work-route]:visible').first();
        const { role, company_id: company, pay_label: pay } = routes.find(route => route.id === firstId);
        await expect(first).toHaveAttribute('data-work-route', firstId);
        const title = first.getByRole('heading', { name: role, exact: true })
          .getByRole('link', { name: role, exact: true });
        const profile = `/company/${company}/#${firstId}`;
        await expect(title).toHaveAttribute('href', profile);
        await expect(title).toHaveAccessibleDescription('AfterQuery');
        await expect(title).toHaveCSS('text-decoration-line', 'underline');
        await expect(first.locator(`a[href="${profile}"]`)).toHaveCount(1);
        expect((await title.boundingBox()).height).toBeGreaterThanOrEqual(44);
        const rate = first.locator('.work-pay strong');
        await expect(rate).toHaveText(pay);
        await expect(title).toBeInViewport({ ratio: 1 });
        await expect(rate).toBeInViewport({ ratio: 1 });
        const { needed, available, placeholder } = await search.evaluate(input => {
          const style = getComputedStyle(input);
          const canvas = document.createElement('canvas').getContext('2d');
          canvas.font = getComputedStyle(input, '::placeholder').font || style.font;
          return { needed: canvas.measureText(input.placeholder).width, placeholder: input.placeholder,
            available: input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) };
        });
        expect(placeholder.trim()).not.toBe('');
        expect(needed, `Search placeholder has ${available}px`).toBeLessThanOrEqual(available);
      });
    }
  }
});

test('native Work shows the hourly role and rate together at 1024×600', async ({ page, hasTouch }) => {
  test.skip(hasTouch, 'Checks the short desktop layout and its keyboard order');
  await page.setViewportSize({ width: 1024, height: 600 });
  await page.goto('/work/?pay=hourly&sort=hourly');
  const summary = page.locator('.work-page-filter-options summary');
  await expect(summary).toHaveText('Filters (2)');
  await page.evaluate(() => document.fonts.ready);

  const firstCard = page.locator('[data-work-route]:visible').first();
  await expect(firstCard).toHaveAttribute('data-work-route', 'afterquery.work.world-models');
  await expect(firstCard.locator('h3')).toBeInViewport({ ratio: 1 });
  await expect(firstCard.locator('.work-pay strong')).toBeInViewport({ ratio: 1 });

  const compare = page.getByRole('link', { name: 'Compare results' });
  const jump = page.getByText('Jump to section', { exact: true });
  const advice = page.getByText('Before you apply', { exact: true });
  const [jumpBox, adviceBox] = await Promise.all([jump.boundingBox(), advice.boundingBox()]);
  expect(jumpBox.y).toBeCloseTo(adviceBox.y);
  expect(jumpBox.x + jumpBox.width).toBeLessThan(adviceBox.x);
  for (const box of [jumpBox, adviceBox]) {
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
  await summary.focus();
  for (const control of [compare, page.getByRole('button', { name: 'Download CSV' }), jump, advice]) {
    await page.keyboard.press('Tab');
    await expect(control).toBeFocused();
  }
  await page.keyboard.press('Space');
  await expect(page.locator('.work-page-advice .note')).toBeVisible();
  await page.keyboard.press('Space');
  await expect(page.locator('.work-page-advice .note')).toBeHidden();
});

test('native Work shows the first hourly result on short desktops and remembers keyboard toggles', async ({ page, hasTouch, request }) => {
  test.skip(hasTouch, 'Checks the desktop disclosure and keyboard history');
  test.setTimeout(60_000);
  const { routes } = await (await request.get('/work-routes.json')).json();
  const hourlyIds = routes.filter(route => route.pay_terms?.hourly_comparable).map(route => route.id).sort();
  const form = page.getByRole('search', { name: 'Find paid work' });
  const options = form.locator('.work-page-filter-options');
  const count = page.locator('[data-work-count]');
  const cards = page.locator('[data-work-route]:visible');
  const ids = () => cards.evaluateAll(nodes => nodes.map(node => node.dataset.workRoute));

  await page.setViewportSize({ width: 1280, height: 720 });
  for (const [sort, firstId] of [['', 'afterquery.work.technical-content-writer-contract'], ['hourly', 'afterquery.work.world-models']]) {
    const params = new URLSearchParams({ pay: 'hourly' });
    if (sort) params.set('sort', sort);
    const url = `/work/?${params}`;
    await page.goto(url);
    await expect(form).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(options).toHaveJSProperty('open', false);
    await expect(count).toHaveText(`${hourlyIds.length} records with published hourly pay`);
    await expect(count).toBeInViewport({ ratio: 1 });
    const firstCard = cards.first();
    await expect(firstCard).toHaveAttribute('data-work-route', firstId);
    await expect(firstCard.locator('h3')).toBeInViewport({ ratio: 1 });
    await expect(firstCard.locator('.work-pay strong')).toBeInViewport({ ratio: 1 });
    const before = await ids();
    expect([...before].sort()).toEqual(hourlyIds);

    const summary = options.getByText(sort ? 'Filters (2)' : 'Filters (1)', { exact: true });
    await summary.press('Enter');
    await expect(summary).toBeFocused();
    await expect(options).toHaveJSProperty('open', true);
    await expect(form.getByRole('combobox', { name: 'Pay unit' })).toHaveValue('hourly');
    await expect(form.getByRole('combobox', { name: 'Sort' })).toHaveValue(sort);
    await expect(page).toHaveURL(url);
    expect(await ids()).toEqual(before);

    const compare = page.getByRole('link', { name: 'Compare results' });
    await compare.press('Enter');
    const rows = page.locator('[data-compare-route]');
    await expect(rows).toHaveCount(before.length);
    expect(await rows.evaluateAll(nodes => nodes.map(node => node.dataset.compareRoute))).toEqual(before);
    await page.goBack();
    await expect(page).toHaveURL(url);
    await expect(compare).toBeFocused();
    await expect(options).toHaveJSProperty('open', true);
    await expect(form.getByRole('combobox', { name: 'Pay unit' })).toHaveValue('hourly');
    await expect(form.getByRole('combobox', { name: 'Sort' })).toHaveValue(sort);
    expect(await ids()).toEqual(before);
  }

  await page.setViewportSize({ width: 1280, height: 844 });
  await page.goto('/work/?pay=hourly');
  await expect(form.getByRole('combobox', { name: 'Pay unit' })).toHaveValue('hourly');
  await expect(options).toHaveJSProperty('open', true);
  const jump = page.getByText('Jump to section', { exact: true });
  const advice = page.getByText('Before you apply', { exact: true });
  const [jumpBox, adviceBox] = await Promise.all([jump.boundingBox(), advice.boundingBox()]);
  expect(jumpBox.y + jumpBox.height).toBeLessThanOrEqual(adviceBox.y);
  await options.getByText('Filters (1)', { exact: true }).press('Space');
  await page.reload();
  await expect(form).toBeVisible();
  await expect(options).toHaveJSProperty('open', false);
  await expect(count).toHaveText(`${hourlyIds.length} records with published hourly pay`);
  const search = form.getByRole('searchbox', { name: 'Search listings' });
  await search.fill('Technical Content Writer');
  await expect(count).toHaveText('1 matching record');
  await search.fill('unfindable-work-record-fixture');
  await expect(count).toHaveText('0 matching records');
  await search.clear();
  await expect(count).toHaveText(`${hourlyIds.length} records with published hourly pay`);
});

test('native Work fits every filter option in its closed select at narrow widths', async ({ page }) => {
  test.setTimeout(60_000);
  const form = page.getByRole('search', { name: 'Find paid work' });
  const count = page.locator('[data-work-count]');
  await page.setViewportSize({ width: 320, height: 844 });
  for (const filtered of [false, true]) {
    await page.goto(filtered ? '/work/?pay=hourly&sort=hourly' : '/work/', { waitUntil: 'domcontentloaded' });
    await expect(form).toBeVisible();
    await expect(count).toHaveText(filtered ? /^[1-9]\d* records? with published hourly pay$/ : /^[1-9]\d* records, including career pages and past listings$/);
    const options = form.locator('.work-page-filter-options');
    if (filtered) {
      await expect(options).toHaveJSProperty('open', false);
      await expect(options.locator('summary')).toHaveText('Filters (2)');
      await expect(page.getByRole('link', { name: 'Compare results' })).toBeInViewport({ ratio: 1 });
      await expect(page.getByRole('button', { name: 'Download CSV' })).toBeInViewport({ ratio: 1 });
    }
    await options.locator('summary').click();
    if (filtered) {
      await expect(form.getByRole('combobox', { name: 'Pay unit' })).toHaveValue('hourly');
      await expect(form.getByRole('combobox', { name: 'Sort' })).toHaveValue('hourly');
    }
    await expect(form.getByRole('combobox')).toHaveCount(5);

    const standardFonts = new Map();
    for (const enlarged of [false, true]) {
      for (const width of enlarged ? [390, 320] : [320, 390]) {
        if (page.viewportSize().width !== width) await page.setViewportSize({ width, height: 844 });
        await test.step(`${filtered ? 'Hourly results' : 'Default results'}, ${enlarged ? 'enlarged' : 'standard'} text at ${width}px`, async () => {
          const { controls, viewportWidth, scrollWidth, overlap } = await form.evaluate(async (form, enlarged) => {
            if (enlarged) document.documentElement.style.fontSize = '200%';
            await document.fonts.ready;
            const search = form.querySelector('input[type=search]').getBoundingClientRect();
            const summary = form.querySelector('summary').getBoundingClientRect();
            const fields = form.querySelector('.work-page-filter-fields').getBoundingClientRect();
            const controls = [...form.querySelectorAll('select')].map(select => {
              const { name, value } = select;
              const box = select.getBoundingClientRect();
              const { appearance, fontSize } = getComputedStyle(select);
              // Measure one option at a time using the actual native font, padding and arrow.
              const probe = select.cloneNode(false);
              probe.removeAttribute('name');
              probe.style.cssText = 'position:absolute;visibility:hidden;width:max-content;min-width:0;max-width:none';
              select.after(probe);
              const clipping = [...select.options].filter(option => option.matches(':enabled')).flatMap(option => {
                probe.replaceChildren(option.cloneNode(true));
                const needed = probe.getBoundingClientRect().width;
                return needed > box.width + 0.5 ? [{ label: option.label, selected: option.value === value, needed }] : [];
              });
              probe.remove();
              return { name, appearance, fontSize: parseFloat(fontSize), width: box.width, height: box.height,
                inBounds: box.left >= fields.left - 0.5 && box.right <= fields.right + 0.5, clipping };
            });
            return {
              controls,
              viewportWidth: document.documentElement.clientWidth,
              scrollWidth: document.documentElement.scrollWidth,
              overlap: search.left < summary.right && summary.left < search.right
                && search.top < summary.bottom && summary.top < search.bottom,
            };
          }, enlarged);

          expect.soft(viewportWidth).toBe(width);
          expect.soft(scrollWidth).toBeLessThanOrEqual(viewportWidth);
          expect.soft(overlap, 'Search and Filters share space').toBe(false);
          for (const control of controls) {
            const { name, appearance, fontSize, width: available, height, inBounds, clipping } = control;
            expect.soft(appearance, name).toBe('auto');
            expect.soft(available, name).toBeGreaterThanOrEqual(44);
            expect.soft(height, name).toBeGreaterThanOrEqual(44);
            expect.soft(inBounds, name).toBe(true);
            expect.soft(clipping, `${name} has ${available}px for its selected label and options`).toEqual([]);
            const key = `${width}/${name}`;
            if (enlarged) expect.soft(fontSize, `${name} font size`).toBeGreaterThan(standardFonts.get(key));
            else standardFonts.set(key, fontSize);
          }
        });
      }
    }
  }
});

const enlargedWorkTest = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    // Firefox's minimum font setting also enlarges text sized in pixels.
    await use(browserName === 'firefox'
      ? { ...launchOptions, firefoxUserPrefs: { ...launchOptions.firefoxUserPrefs, 'font.minimum-size.x-western': 28 } }
      : launchOptions);
  }, { scope: 'worker' }],
});

enlargedWorkTest('native Work stacks full disclosure labels at 320px with enlarged text', async ({ page, browserName }) => {
  test.skip(browserName !== 'firefox', 'Uses the Firefox minimum font setting');
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/work/?pay=hourly&sort=hourly');
  await expect(page.getByRole('searchbox', { name: 'Search listings' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const jump = page.getByText('Jump to section', { exact: true });
  const advice = page.getByText('Before you apply', { exact: true });
  const [jumpBox, adviceBox] = await Promise.all([jump.boundingBox(), advice.boundingBox()]);
  expect(jumpBox.y + jumpBox.height).toBeLessThanOrEqual(adviceBox.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  for (const box of [jumpBox, adviceBox]) {
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.x + box.width).toBeLessThanOrEqual(320);
  }
  await jump.focus();
  await page.keyboard.press('Tab');
  await expect(advice).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('.work-page-advice .note')).toBeVisible();
});

enlargedWorkTest('native Work reserves the search row while the filter count loads', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // Keep the loader's retry deadline out of this layout check on slow runners.
  await page.clock.install({ time: 0 });
  await page.clock.pauseAt(60_000);
  const { promise: gate, resolve: release } = Promise.withResolvers();
  await page.route(url => /^\/js\/work\.[a-f0-9]{12}\.js$/.test(url.pathname), async route => {
    await gate;
    await route.continue();
  });
  const search = page.getByRole('searchbox', { name: 'Search listings' });
  const summary = page.locator('[data-work-filters] summary');
  const snapshot = () => page.evaluate(() => {
    const slot = document.querySelector('[data-work-filter-slot]');
    const input = slot.querySelector('input[type=search]');
    const summary = slot.querySelector('summary');
    const searchBox = input.getBoundingClientRect();
    const toolbar = document.querySelector('[data-work-toolbar]').getBoundingClientRect();
    return {
      state: document.documentElement.dataset.workLoad,
      searchVisibility: getComputedStyle(input).visibility,
      filterLabel: summary.textContent,
      geometry: {
        searchTop: searchBox.top, searchHeight: searchBox.height, summaryTop: summary.getBoundingClientRect().top,
        resultsTop: toolbar.top, slotHeight: slot.getBoundingClientRect().height,
      },
    };
  });

  let reserved;
  try {
    await page.goto('/work/?pay=hourly&sort=hourly', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-work-filters]')).toHaveCSS('display', 'grid');
    reserved = await snapshot();
  } finally {
    release();
  }
  expect(reserved).toMatchObject({ state: 'pending', searchVisibility: 'hidden', filterLabel: 'Filters' });
  expect(reserved.geometry.searchHeight).toBeGreaterThanOrEqual(44);

  await expect(search).toBeVisible();
  await expect(summary).toHaveText('Filters (2)');
  await expect(page.locator('[data-work-count]')).toHaveText(/^[1-9]\d* records? with published hourly pay$/);
  const ready = await snapshot();
  for (const [key, value] of Object.entries(reserved.geometry)) {
    expect.soft(ready.geometry[key], key).toBeCloseTo(value, 1);
  }
});
