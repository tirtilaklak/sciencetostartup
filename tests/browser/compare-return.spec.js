const { test, expect } = require('@playwright/test');

function compareCell(page, row, company) {
  return page.locator(`[data-comparison-row="${row}"] [data-comparison-company="${company}"]`);
}

test('Compare shows the selected figures on the first phone screen with one selection editor', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/explore/#compare/mercor/snorkel_ai/labelbox');
  const view = page.locator('#compare-view');
  const editor = view.locator('#compare-setup');
  const toggle = editor.locator('summary');
  const add = view.getByRole('combobox', { name: 'Add a company' });
  const examples = view.getByRole('combobox', { name: 'Examples' });
  const clear = view.getByRole('button', { name: 'Clear selection' });
  const share = view.locator('#copy-compare');
  await expect(view.locator('.comparison-table')).toBeVisible();
  await expect(editor).toHaveJSProperty('open', false);
  await expect(view.getByRole('rowheader', { name: 'Business' })).toBeInViewport();
  await expect(compareCell(page, 'Published revenue figure', 'snorkel_ai').locator('.row-number')).toBeInViewport({ ratio: 1 });
  await expect(share).toBeInViewport({ ratio: 1 });
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: { writeText: async text => { window.compareCopiedUrl = text; } },
    });
  });
  await share.press('Enter');
  await expect(share).toHaveText('Link copied');
  expect(await page.evaluate(() => window.compareCopiedUrl)).toBe(page.url());

  await toggle.press('Enter');
  await expect(examples).toBeVisible();
  await clear.press('Enter');
  await expect(page).toHaveURL('/explore/#compare');
  await expect(add).toBeFocused();
  await expect(clear).toBeHidden();
  await expect(share).toBeHidden();
  await expect(view.getByRole('combobox', { name: 'Examples' })).toHaveCount(1);
  await expect(view.getByRole('button', { name: 'TaskUs, Appen & Scale AI' })).toHaveCount(0);

  await examples.focus();
  await examples.selectOption('scale');
  await expect(page).toHaveURL('/explore/#compare/taskus/appen/scale_ai');
  await expect(editor).toHaveJSProperty('open', false);
  await expect(toggle).toBeFocused();
  await expect(view.locator('.comparison-table')).toBeVisible();
});

test('Back returns to the exact Compare link when two links open the same profile', async ({ page }) => {
  const compare = '/explore/#compare/mercor/a-team/sama';
  await page.goto(compare);
  const header = page.locator('.comparison-table thead').getByRole('link', { name: 'Mercor', exact: true });
  const profile = compareCell(page, 'Explore', 'mercor').getByRole('link', { name: 'Full profile & sources' });
  const work = compareCell(page, 'Paid work', 'mercor').getByRole('link', { name: 'Pay & requirements' });
  await expect(header).toHaveAttribute('href', '#company/mercor');
  await expect(profile).toHaveAttribute('href', '#company/mercor');

  for (const [origin, destination] of [[profile, '#company/mercor'], [header, '#company/mercor'], [work, '#company/mercor/work']]) {
    await origin.scrollIntoViewIfNeeded();
    await origin.press('Enter');
    await expect(page).toHaveURL('/explore/' + destination);
    await expect(page.locator('[data-profile-company="mercor"]')).toBeVisible();
    if (origin === work) await expect(page.locator('#profile-work')).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(compare);
    await expect(origin).toBeFocused();
    await expect(origin).toBeInViewport();
  }
});

test('Back restores the opener from a new entry at the same Compare URL', async ({ page }) => {
  const compare = '/explore/#compare/mercor/a-team/sama';
  await page.goto(compare);
  const work = compareCell(page, 'Paid work', 'mercor').getByRole('link', { name: 'Pay & requirements' });
  await expect(work).toBeVisible();
  await page.goto(compare, { waitUntil: 'commit' });
  await work.press('Enter');
  await expect(page).toHaveURL('/explore/#company/mercor/work');

  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(compare);
  await expect(work).toBeFocused();
  await expect(work).toBeInViewport();
});

test('fresh Back from native financing evidence restores More, the Compare pair and keyboard focus', async ({ page }) => {
  await page.addInitScript(() => {
    addEventListener('unload', () => {});
    window.compareTestDocument = Math.random().toString();
  });
  const compare = '/explore/#compare/a-team/sama/mercor';
  await page.goto(compare);
  const headings = page.locator('.comparison-table thead .card-head a');
  await expect(headings).toHaveText(['A.Team', 'Sama', 'Mercor']);
  const changePair = page.locator('.mobile-column-options summary');
  const mobile = await changePair.isVisible();
  if (mobile) {
    await changePair.press('Enter');
    await page.getByRole('button', { name: 'Sama + Mercor', exact: true }).press('Enter');
  }

  const extra = page.locator('#comparison-extra');
  const more = page.locator('[data-compare-extra]');
  const evidence = compareCell(page, 'Funding & investors', 'mercor').getByRole('link', { name: 'Read Mercor’s financing evidence' });
  await expect(extra).toBeHidden();
  await more.press('Enter');
  await expect(more).toHaveAttribute('aria-expanded', 'true');
  await expect(evidence).toHaveAttribute('href', '/company/mercor/#financial-record');
  await evidence.scrollIntoViewIfNeeded();
  const initialDocument = await page.evaluate(() => window.compareTestDocument);
  await evidence.press('Enter');
  await expect(page).toHaveURL('/company/mercor/#financial-record');
  await expect(page.locator('#financial-record')).toHaveJSProperty('open', true);

  for (let visit = 0; visit < 2; visit++) {
    await page.goBack({ waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(compare);
    expect(await page.evaluate(() => window.compareTestDocument)).not.toBe(initialDocument);
    await expect(headings).toHaveText(['A.Team', 'Sama', 'Mercor']);
    await expect(more).toHaveAttribute('aria-expanded', 'true');
    await expect(extra).toBeVisible();
    if (mobile) await expect(headings.first()).toBeHidden();
    await expect(evidence).toBeFocused();
    await expect(evidence).toBeInViewport();

    await page.goForward({ waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL('/company/mercor/#financial-record');
    await expect(page.locator('#financial-record')).toHaveJSProperty('open', true);
  }
});

test('Compare work links describe career pages, archived records and paid networks accurately', async ({ page }) => {
  await page.goto('/explore/#compare/sama/elorian/mercor');
  const links = ['sama', 'elorian', 'mercor'].map(id => compareCell(page, 'Paid work', id).locator('a'));
  await expect(links[0]).toHaveText('See career links');
  await expect(links[1]).toHaveText('See work records');
  await expect(links[2]).toHaveText('Pay & requirements');
  await expect(compareCell(page, 'Paid work', 'mercor')).toContainText('Networks and programs');

  for (const [index, id, routeId] of [
    [0, 'sama', 'sama.work.company-careers'],
    [1, 'elorian', 'elorian.work.model-safety'],
  ]) {
    const link = links[index];
    await expect(link).toHaveAttribute('href', `#company/${id}/work`);
    await link.press('Enter');
    await expect(page).toHaveURL(`/explore/#company/${id}/work`);
    const work = page.locator('#profile-work');
    await expect(work).toContainText('No confirmed paid listing');
    await expect(work.locator(`[data-work-route="${routeId}"]`)).toBeVisible();
    await page.goBack();
    await expect(link).toBeFocused();
  }
});

async function expectFocusedTextInView(locator, checkControl = false) {
  await expect(locator).toBeFocused();
  await expect.poll(() => locator.evaluate((element, checkControl) => {
    if (!element.matches(':focus-visible')) return ['focus ring missing'];
    const hits = (rect, fractions) => fractions.every(fraction => element.contains(
      document.elementFromPoint(rect.left + rect.width * fraction, rect.top + rect.height / 2)
    ));
    const inViewport = rect => rect.left >= 0 && rect.right <= innerWidth &&
      rect.top >= 0 && rect.bottom <= innerHeight;
    const fractions = checkControl ? [0.12, 0.5, 0.88] : [0.5];
    if (checkControl) {
      const box = element.getBoundingClientRect();
      if (!inViewport(box) || !hits(box, fractions)) return [{ control: box.toJSON() }];
      if (element.matches('select')) return [];
    }
    const textNodes = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    const lines = [];
    while (textNodes.nextNode()) {
      const node = textNodes.currentNode;
      if (!node.textContent.trim() || node.parentElement.closest('.sr-only, [aria-hidden="true"]')) continue;
      range.selectNode(node);
      lines.push(...[...range.getClientRects()].filter(rect => rect.width && rect.height));
    }
    if (!lines.length) return ['no rendered label'];
    return lines.filter(rect => !inViewport(rect) || !hits(rect, fractions)).map(rect => rect.toJSON());
  }, checkControl)).toEqual([]);
}

const enlargedCompare = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    await use(browserName === 'chromium' ? {
      ...launchOptions,
      args: [...(launchOptions.args || []), '--blink-settings=minimumFontSize=32,minimumLogicalFontSize=32'],
    } : launchOptions);
  }, { scope: 'worker' }],
});

enlargedCompare('trusted Tab reveals Compare labels on a short phone with large text', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Uses a Chromium minimum font setting');

  for (const height of [568, 720]) await test.step(`320 × ${height}`, async () => {
    await page.setViewportSize({ width: 320, height });
    await page.goto('/companies/');
    await page.getByRole('link', { name: 'Compare Snorkel AI', exact: true }).press('Enter');
    await expect(page).toHaveURL('/explore/#compare/snorkel_ai');
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');

    await page.locator('#compare-setup-toggle').press('Enter');
    const picker = page.getByRole('combobox', { name: 'Add a company', exact: true });
    await picker.focus();
    for (const [company, path] of [['toloka', 'snorkel_ai/toloka'], ['turing', 'snorkel_ai/toloka/turing']]) {
      await picker.selectOption(company);
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(`/explore/#compare/${path}`);
      await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    }
    await expect(picker).toBeFocused();

    const compare = page.locator('#compare-view');
    const revenue = compareCell(page, 'Published revenue figure', 'snorkel_ai');
    const changePair = compare.locator('.mobile-column-options summary');
    const source = revenue.getByRole('link', { name: /snorkel\.ai/ });
    const figure = revenue.getByText('Figure details', { exact: true });
    await page.keyboard.press('Tab');
    await expect(compare.locator('#compare-preset')).toBeFocused();

    for (const target of [
      compare.getByRole('button', { name: 'Clear selection' }),
      ...await compare.locator('[data-comparison-scope] a').all(),
      compare.getByRole('button', { name: 'Copy comparison link' }),
      compare.getByRole('link', { name: 'Snorkel AI', exact: true }),
      compare.getByRole('button', { name: 'Remove Snorkel AI' }),
      compare.getByRole('link', { name: 'Turing', exact: true }),
      compare.getByRole('button', { name: 'Remove Turing' }),
      changePair, source, figure,
    ]) {
      await page.keyboard.press('Tab');
      if (await target.getAttribute('data-remove')) {
        await expect(target).toBeFocused();
        continue;
      }
      await expectFocusedTextInView(target);
    }

    await page.keyboard.press('Enter');
    await expect(figure.locator('..')).toHaveJSProperty('open', true);
    await page.keyboard.press('Enter');
    await page.keyboard.press('Shift+Tab');
    await expectFocusedTextInView(source);
    await page.keyboard.press('Shift+Tab');
    await expectFocusedTextInView(changePair);
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    const tolokaPair = compare.getByRole('button', { name: 'Snorkel AI + Toloka', exact: true });
    await expectFocusedTextInView(tolokaPair);
    await page.keyboard.press('Enter');
    await expectFocusedTextInView(changePair);
    await expect(compareCell(page, 'Published revenue figure', 'toloka')).toBeVisible();
    await expect(compareCell(page, 'Published revenue figure', 'turing')).toBeHidden();
    await expect(page).toHaveURL('/explore/#compare/snorkel_ai/toloka/turing');
  });
});

const threeCompanyComparison = '/explore/#compare/snorkel_ai/toloka/turing';

async function tabTo(page, target) {
  for (let stops = 0; stops < 30; stops++) {
    if (await target.evaluate(element => document.activeElement === element)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}

async function openPhoneComparison(page) {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto(threeCompanyComparison);
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  const changePair = page.locator('.mobile-column-options summary');
  await expect(changePair).toBeVisible();
  const revenue = company => compareCell(page, 'Published revenue figure', company);
  await expect(revenue('snorkel_ai')).toBeVisible();
  await expect(revenue('toloka')).toBeVisible();
  await expect(revenue('turing')).toBeHidden();
  return { changePair, revenue };
}

async function openPairPicker(page, changePair) {
  await tabTo(page, changePair);
  await expectFocusedTextInView(changePair, true);
  await page.keyboard.press('Enter');
  await expect(changePair.locator('..')).toHaveJSProperty('open', true);
  const first = page.getByRole('button', { name: 'Snorkel AI + Toloka', exact: true });
  const second = page.getByRole('button', { name: 'Snorkel AI + Turing', exact: true });
  await page.keyboard.press('Tab');
  await expectFocusedTextInView(first, true);
  return { first, second };
}

async function afterLayout(page) {
  await page.evaluate(() => new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
}

enlargedCompare('an open Compare pair stays visible and usable after a height change at 32px minimum text', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Uses a Chromium minimum font setting');
  const { changePair, revenue } = await openPhoneComparison(page);
  const { first, second } = await openPairPicker(page, changePair);

  await test.step('increase the phone height with the first pair focused', async () => {
    await page.setViewportSize({ width: 320, height: 720 });
    await afterLayout(page);
    await expectFocusedTextInView(first, true);
  });

  await page.keyboard.press('Tab');
  await expectFocusedTextInView(second, true);
  await page.keyboard.press('Shift+Tab');
  await expectFocusedTextInView(first, true);
  await page.keyboard.press('Enter');
  await expectFocusedTextInView(changePair, true);
  await expect(changePair.locator('..')).toHaveJSProperty('open', false);
  await expect(revenue('toloka')).toBeVisible();
  await expect(revenue('turing')).toBeHidden();
  await expect(page).toHaveURL(threeCompanyComparison);

  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await expectFocusedTextInView(second, true);
  await page.keyboard.press('Enter');
  await expectFocusedTextInView(changePair, true);
  await expect(changePair.locator('..')).toHaveJSProperty('open', false);
  await expect(revenue('turing')).toBeVisible();
  await expect(revenue('toloka')).toBeHidden();
  await expect(page).toHaveURL(threeCompanyComparison);
  await page.keyboard.press('Tab');
  await expectFocusedTextInView(revenue('snorkel_ai').getByRole('link', { name: /snorkel\.ai/ }));
});

enlargedCompare('Compare preserves visible keyboard focus when a phone rotates with the pair picker open', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Uses Chromium phone orientation emulation');
  const { changePair, revenue } = await openPhoneComparison(page);
  const { first, second } = await openPairPicker(page, changePair);
  const cdp = await page.context().newCDPSession(page);
  async function rotate(width, height) {
    const landscape = width > height;
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width, height, deviceScaleFactor: 1, mobile: true,
      screenOrientation: {
        type: landscape ? 'landscapePrimary' : 'portraitPrimary',
        angle: landscape ? 90 : 0,
      },
    });
    await afterLayout(page);
  }

  for (const [width, height] of [[568, 320], [320, 568], [320, 720]]) {
    await test.step(`keep the pair picker open at ${width} × ${height}`, async () => {
      await rotate(width, height);
      await expectFocusedTextInView(first, true);
      await page.keyboard.press('Tab');
      await expectFocusedTextInView(second, true);
      await page.keyboard.press('Shift+Tab');
      await expectFocusedTextInView(first, true);
    });
  }

  const editor = page.locator('#compare-setup-toggle');
  await test.step('use the visible selection editor when landscape hides the pair picker', async () => {
    await rotate(720, 320);
    await expect(changePair).toBeHidden();
    await expectFocusedTextInView(editor, true);
    await rotate(320, 720);
    await expectFocusedTextInView(editor, true);
    await expect(changePair.locator('..')).toHaveJSProperty('open', false);
    await expect(revenue('toloka')).toBeVisible();
    await expect(revenue('turing')).toBeHidden();
    await expect(page).toHaveURL(threeCompanyComparison);
  });
});

enlargedCompare('Compare keeps the reading position after wheel scrolling and a height change', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Uses a Chromium minimum font setting');
  const { changePair } = await openPhoneComparison(page);
  await tabTo(page, changePair);
  await expectFocusedTextInView(changePair, true);

  const initial = await page.evaluate(() => scrollY);
  await page.evaluate(() => {
    window.compareWheelDone = new Promise(resolve => {
      addEventListener('scrollend', () => resolve(scrollY), { once: true });
    });
  });
  await page.mouse.move(160, 460);
  await page.mouse.wheel(0, 1200);
  const readingPosition = await page.evaluate(() => window.compareWheelDone);
  expect(readingPosition - initial).toBeGreaterThan(568);
  await expect(changePair).toBeFocused();

  await page.setViewportSize({ width: 320, height: 720 });
  await afterLayout(page);
  expect(await page.evaluate(() => scrollY)).toBe(readingPosition);
  await expect(page).toHaveURL(threeCompanyComparison);
});
