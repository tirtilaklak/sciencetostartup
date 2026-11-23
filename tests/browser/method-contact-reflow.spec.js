const { test, expect, firefox } = require('@playwright/test');

test('Company correction email has a full touch target on narrow screens', async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 720 });
    await page.goto('/company/org.dataforce/');
    await page.getByText('Company and review scope', { exact: true }).press('Enter');
    const correction = page.locator('.r-record-correction');
    await correction.getByText('Request a correction', { exact: true }).press('Enter');
    await page.keyboard.press('Tab');
    const email = correction.getByRole('link', { name: 'Continue to private email', exact: true });
    await expect(email).toBeFocused();
    expect((await email.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
});

test('Private email correction returns to the same company record on cold Back', async ({ page, hasTouch }) => {
  const profile = '/company/org.dataforce/';
  await page.addInitScript(profile => {
    if (location.pathname !== profile) return;
    addEventListener('unload', () => {});
    addEventListener('pageshow', event => { window.companyCorrectionCached = event.persisted; });
  }, profile);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(profile);
  const scope = page.locator('#company-scope');
  await scope.getByText('Company and review scope', { exact: true }).press('Enter');
  const correction = scope.locator('.r-record-correction');
  await correction.getByText('Request a correction', { exact: true }).press('Enter');
  const email = correction.getByRole('link', { name: 'Continue to private email', exact: true });
  const top = await email.evaluate(link => {
    link.scrollIntoView({ block: 'center', behavior: 'instant' });
    link.focus({ preventScroll: true });
    return link.getBoundingClientRect().top;
  });

  if (hasTouch) await email.tap();
  else await email.press('Enter');
  const method = page.getByRole('complementary', { name: 'Corrections' });
  await expect(method.getByRole('link', { name: 'org.dataforce' })).toHaveAttribute('href', profile);
  await expect(method.getByRole('link', { name: 'Email a correction' })).toHaveAttribute('href', /subject=[^&]*org\.dataforce/);

  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(profile);
  await expect.poll(() => page.evaluate(() => window.companyCorrectionCached)).toBe(false);
  await expect(scope).toHaveJSProperty('open', true);
  await expect(correction).toHaveJSProperty('open', true);
  await expect(email).toBeFocused();
  await expect(email).toBeInViewport({ ratio: 1 });
  await expect.poll(() => email.evaluate((link, top) =>
    Math.abs(link.getBoundingClientRect().top - top), top)).toBeLessThan(3);
  await page.keyboard.press('Tab');
  await expect(correction.getByText('Copy the email draft', { exact: true })).toBeFocused();
});

test('Method correction actions remain separated on narrow screens', async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 720 });
    await page.goto('/method/#corrections');
    const contact = page.getByRole('complementary', { name: 'Corrections' });
    const github = await contact.getByRole('link', { name: 'Submit a correction on GitHub', exact: true }).boundingBox();
    const email = await contact.getByRole('link', { name: 'Email a correction', exact: true }).boundingBox();
    expect(email.y - (github.y + github.height)).toBeGreaterThanOrEqual(4);
  }
});

test('Method correction contacts and the record link fit at Firefox minimum font sizes', async ({ browserName, baseURL }, info) => {
  test.skip(browserName !== 'firefox', 'Firefox provides a minimum font preference');
  test.setTimeout(120_000);
  const viewport = { width: 320, height: 720 };
  const actionNames = ['Submit a correction on GitHub', 'Email a correction', 'Read the accepted correction log'];
  const stableId = 'assertion.genebench.pro.provenance-wording-discrepancy.20261112';
  const assertionId = `assertion-${stableId}`;
  const recordPath = `/research/data/assertions/2/#${assertionId}`;

  for (const minimum of [0, 28, 32]) {
    await test.step(minimum ? `${minimum}px minimum font` : 'Default font', async () => {
      const browser = await firefox.launch({ firefoxUserPrefs: {
        'font.minimum-size.x-western': minimum,
        'font.minimum-size.x-unicode': minimum,
      } });
      try {
        const page = await browser.newPage({ baseURL, viewport });
        await page.goto('/method/#corrections');
        await page.evaluate(async () => { await document.fonts.ready; });

        const contact = page.getByRole('complementary', { name: 'Corrections' });
        const actions = actionNames.map(name => contact.getByRole('link', { name, exact: true }));
        const genericDraft = new URL(await actions[1].getAttribute('href'));
        const address = await contact.locator('.method-contact > p > span').evaluate(element => {
          element.scrollIntoView({ block: 'center', inline: 'start', behavior: 'instant' });
          window.scrollTo({ left: 0, top: scrollY, behavior: 'instant' });
          const range = document.createRange();
          range.selectNodeContents(element);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          const selected = selection.toString();
          selection.removeAllRanges();
          return {
            text: element.textContent,
            selected,
            userSelect: getComputedStyle(element).userSelect,
            lines: Array.from(range.getClientRects(), rect => rect.toJSON()),
            documentWidth: document.scrollingElement.scrollWidth,
            scrollX,
          };
        });
        const boxes = await Promise.all(actions.map(async (action, index) => ({
          name: actionNames[index],
          bounds: await action.boundingBox(),
        })));
        await info.attach(`minimum-font-${minimum}`, {
          body: JSON.stringify({ browser: browser.version(), viewport, minimum, address, actions: boxes }, null, 2),
          contentType: 'application/json',
        });

        expect(genericDraft.protocol).toBe('mailto:');
        expect(genericDraft.searchParams.get('subject')).toBe('ScienceToStartup correction');
        expect(address.text).toBe(genericDraft.pathname);
        expect(address.selected).toBe(address.text);
        expect(address.userSelect).not.toBe('none');
        expect(address.scrollX).toBe(0);
        expect.soft(address.documentWidth, 'The page fits without horizontal panning').toBe(viewport.width);
        expect(address.lines.length).toBeGreaterThan(0);
        for (const line of address.lines) {
          expect(line.height).toBeGreaterThanOrEqual(minimum || 1);
          expect.soft(line.left).toBeGreaterThanOrEqual(0);
          expect.soft(line.right).toBeLessThanOrEqual(viewport.width);
          expect.soft(line.top).toBeGreaterThanOrEqual(0);
          expect.soft(line.bottom).toBeLessThanOrEqual(viewport.height);
        }
        for (const [index, action] of actions.entries()) {
          await expect.soft(action, boxes[index].name).toBeInViewport({ ratio: 1 });
        }

        await page.goto(recordPath);
        const assertion = page.locator(`[id="${assertionId}"]`);
        await assertion.getByText('Request a correction', { exact: true }).press('Enter');
        const continueToEmail = assertion.getByRole('link', { name: 'Continue to private email', exact: true });
        const bookmark = new URL(await continueToEmail.getAttribute('href'), page.url());
        const destination = new URL(recordPath, page.url()).href;
        await continueToEmail.click();
        await expect(page).toHaveURL(bookmark.href);
        await page.evaluate(async () => { await document.fonts.ready; });

        const record = contact.getByRole('link', { name: stableId, exact: true });
        await expect(record).toHaveText(stableId);
        await expect(record).toHaveAttribute('href', recordPath);
        const draft = new URL(await actions[1].getAttribute('href'));
        const edition = bookmark.searchParams.get('edition');
        const draftRecord = draft.searchParams.get('body').split('\r\n').slice(0, 3);
        expect(edition).toMatch(/^research-/);
        expect(draft.protocol).toBe('mailto:');
        expect(draft.pathname).toBe(genericDraft.pathname);
        expect(draft.searchParams.get('subject')).toBe(`ScienceToStartup correction · ${stableId}`);
        expect(draftRecord).toEqual([
          `Edition: ${edition}`,
          `Stable record ID: ${stableId}`,
          `Record URL: https://sciencetostartup.com${recordPath}`,
        ]);

        const recordGeometry = await record.evaluate(element => {
          element.scrollIntoView({ block: 'center', inline: 'start', behavior: 'instant' });
          window.scrollTo({ left: 0, top: scrollY, behavior: 'instant' });
          const range = document.createRange();
          range.selectNodeContents(element);
          return {
            lines: Array.from(range.getClientRects(), rect => rect.toJSON()),
            documentWidth: document.scrollingElement.scrollWidth,
            scrollX,
          };
        });

        expect(recordGeometry.scrollX).toBe(0);
        expect.soft(recordGeometry.documentWidth, 'The correction bookmark fits without horizontal panning').toBe(viewport.width);
        expect(recordGeometry.lines.length).toBeGreaterThan(0);
        for (const line of recordGeometry.lines) {
          expect(line.height).toBeGreaterThanOrEqual(minimum || 1);
          expect.soft(line.left).toBeGreaterThanOrEqual(0);
          expect.soft(line.right).toBeLessThanOrEqual(viewport.width);
          expect.soft(line.top).toBeGreaterThanOrEqual(0);
          expect.soft(line.bottom).toBeLessThanOrEqual(viewport.height);
        }

        const firstLine = recordGeometry.lines[0];
        await page.mouse.click(firstLine.left + 10, firstLine.top + firstLine.height / 2);
        await expect(page).toHaveURL(destination);
        await expect(assertion).toBeVisible();
        const pointerArrival = page.url();

        await page.goto(bookmark.href);
        await contact.focus();
        await page.keyboard.press('Tab');
        await expect(record).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(destination);
        await expect(assertion).toBeVisible();
        await info.attach(`record-minimum-font-${minimum}`, {
          body: JSON.stringify({ browser: browser.version(), viewport, minimum, stableId, bookmark, draftRecord,
            draftSubject: draft.searchParams.get('subject'), recordGeometry, pointerArrival, keyboardArrival: page.url() }, null, 2),
          contentType: 'application/json',
        });

        if (minimum === 32) {
          await page.close();
          const noScript = await browser.newPage({ baseURL, viewport, javaScriptEnabled: false });
          await noScript.goto(bookmark.href);
          await expect(noScript.locator('#correction-record')).toBeHidden();
          const fallback = noScript.getByRole('complementary', { name: 'Corrections' });
          const genericEmail = fallback.getByRole('link', { name: 'Email a correction', exact: true });
          await expect(genericEmail).toHaveAttribute('href', genericDraft.href);
          await expect(fallback.locator('.method-contact > p > span')).toHaveText(genericDraft.pathname);
          const width = await fallback.evaluate(() => document.scrollingElement.scrollWidth);
          expect(width).toBe(viewport.width);
        }
      } finally {
        await browser.close();
      }
    });
  }
});
