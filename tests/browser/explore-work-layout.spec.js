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

test('native Work fits every filter option in its closed select at narrow widths', async ({ page }) => {
  test.setTimeout(60_000);
  const form = page.getByRole('search', { name: 'Find paid work' });
  const count = page.locator('[data-work-count]');
  await page.setViewportSize({ width: 320, height: 844 });
  for (const filtered of [false, true]) {
    await page.goto(filtered ? '/work/?pay=hourly&sort=hourly' : '/work/', { waitUntil: 'domcontentloaded' });
    await expect(form).toBeVisible();
    await expect(count).toHaveText(filtered ? /^[1-9]\d* matching records?$/ : /^[1-9]\d* records?$/);
    if (filtered) {
      await expect(form.getByRole('combobox', { name: 'Pay unit' })).toHaveValue('hourly');
      await expect(form.getByRole('combobox', { name: 'Sort' })).toHaveValue('hourly');
    } else {
      await form.locator('summary').click();
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

const delayedWorkTest = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    // Firefox's minimum font setting exposes the search label wrap on load.
    await use(browserName === 'firefox'
      ? { ...launchOptions, firefoxUserPrefs: { ...launchOptions.firefoxUserPrefs, 'font.minimum-size.x-western': 28 } }
      : launchOptions);
  }, { scope: 'worker' }],
});

delayedWorkTest('native Work reserves the search row while the filter count loads', async ({ page }) => {
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
  await expect(page.locator('[data-work-count]')).toHaveText(/^[1-9]\d* matching records?$/);
  const ready = await snapshot();
  for (const [key, value] of Object.entries(reserved.geometry)) {
    expect.soft(ready.geometry[key], key).toBeCloseTo(value, 1);
  }
});
