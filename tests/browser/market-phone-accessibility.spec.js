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

function matrixButton(page, company, signal) {
  return page.locator(`#bh-matrix-body button[data-bh-company="${company}"][data-bh-signal="${signal}"]`);
}

async function openMatrix(page, minimum = 0) {
  await openPage(page, '/explore/#business-health', minimum);
  await expect(page.locator('#business-health-heading')).toBeFocused();
  await tabTo(page, page.locator('.bh-coverage-disclosure > summary'));
  await page.keyboard.press('Enter');
  await expect(page.locator('.bh-coverage-disclosure')).toHaveAttribute('open', '');
}

async function expectReadableEvidence(button, { organization, metric, value }, phase) {
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
      value: textPlacement((control.querySelector('b') ?? control).firstChild, control, rowHeading.getBoundingClientRect().right),
    };
  }), { message: `${organization} ${metric} ${value} is readable ${phase}`, timeout: 3_000 }).toMatchObject({
    focusVisible: true,
    organization: { text: organization, visible: true },
    metric: { text: metric, visible: true },
    value: { text: value, visible: true },
  });
}

async function closeEvidence(page, dialog, button) {
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(button).toBeFocused();
}

const unavailableEvidence = [
  {
    company: 'appen', signal: 'delivery', organization: 'Appen', metric: 'Paid delivery', value: '—',
    name: /Appen · Expert activity · No reviewed public disclosure/,
    heading: 'No reviewed public figure', description: /for Appen\. Missing is not zero\./,
    profile: '#company/appen/traction',
  },
  {
    company: 'aixi', signal: 'revenue', organization: 'AIXI Labs', metric: 'Revenue', value: 'n/a',
    name: /n\/a · AIXI Labs · Revenue · Nonprofit research/,
    heading: 'Not applied', description: /AIXI Labs is a nonprofit research organization\. Commercial measures are not applied/,
    profile: '#company/aixi',
  },
];

async function expectUnavailableDialog(page, { heading, description, profile }) {
  const dialog = page.locator('#bh-evidence-dialog');
  await expect(dialog.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  await expect(dialog.locator('.bh-lede')).toHaveText(description);
  await expect(dialog.getByRole('link', { name: 'Full company profile' })).toHaveAttribute('href', profile);
  await expect(dialog.getByRole('button', { name: 'Close figure details' })).toBeFocused();
  return dialog;
}

test.describe('390px Chromium matrix', () => {
  test.describe.configure({ timeout: 60_000 });
  test.skip(({ browserName }) => browserName !== 'chromium', 'Exercise Chromium keyboard panning');
  test.use({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });

  test('Market reveals the entire Appen Profit and Toloka Revenue figures on Tab and after Escape', async ({ page }) => {
    await openMatrix(page);

    for (const figure of [
      { company: 'appen', signal: 'profit', organization: 'Appen', metric: 'Profit', value: '−$4.45M' },
      { company: 'toloka', signal: 'revenue', organization: 'Toloka', metric: 'Revenue', value: '$26.1M' },
    ]) {
      await test.step(`${figure.organization} ${figure.metric}`, async () => {
        const button = matrixButton(page, figure.company, figure.signal);
        await tabTo(page, button);
        await expectReadableEvidence(button, figure, 'after Tab');

        await page.keyboard.press('Enter');
        const dialog = page.locator('#bh-evidence-dialog');
        await expect(dialog.getByRole('heading', { name: figure.organization, exact: true })).toBeVisible();
        await expect(dialog.locator('.bh-value')).toContainText(figure.value);
        await closeEvidence(page, dialog, button);
        await expectReadableEvidence(button, figure, 'after Escape');
      });
    }
  });

  test('Market opens Appen missing evidence from the visible cell padding', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium', 'Exercise a mouse click on the cell outside its button');
    await openMatrix(page);
    const figure = unavailableEvidence[0];
    const cell = page.locator(`#bh-matrix-body td[data-bh-company="${figure.company}"][data-bh-signal="${figure.signal}"]`);
    const button = matrixButton(page, figure.company, figure.signal);
    await cell.scrollIntoViewIfNeeded();
    const point = await cell.evaluate(td => {
      const grid = td.closest('#bh-grid-wrap');
      const clipRight = grid.getBoundingClientRect().left + grid.clientLeft + grid.clientWidth;
      grid.scrollLeft += td.getBoundingClientRect().right - clipRight + 3;
      const box = td.getBoundingClientRect();
      const x = box.right - 3;
      const y = box.top + box.height / 2;
      return { x, y, hitsCell: document.elementFromPoint(x, y) === td };
    });
    expect(point.hitsCell).toBe(true);
    await page.mouse.click(point.x, point.y);
    const dialog = await expectUnavailableDialog(page, figure);
    await closeEvidence(page, dialog, button);
  });
});

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
    phone.describe.configure({ timeout: 60_000 });
    phone.skip(({ browserName }) => browserName !== 'firefox', 'Exercise Firefox keyboard panning and minimum font behavior');
    phone.use({ viewport: { width: 320, height: 720 }, reducedMotion: 'reduce' });

    phone('Market keeps the focused Appen amount alongside its organization and Revenue heading', async ({ page }) => {
      await openMatrix(page, minimum);
      const figure = { organization: 'Appen', metric: 'Revenue', value: '$193.8M' };
      const button = matrixButton(page, 'appen', 'revenue');
      await tabTo(page, button);
      await expectReadableEvidence(button, figure, 'after Tab');

      const dialog = page.locator('#bh-evidence-dialog');
      await page.keyboard.press('Enter');
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('.bh-value')).toContainText(figure.value);
      await closeEvidence(page, dialog, button);
      await expectReadableEvidence(button, figure, 'after Escape');
    });

    for (const figure of unavailableEvidence) {
      phone(`Market opens ${figure.organization} ${figure.metric} ${figure.value} with the keyboard`, async ({ page }) => {
        await openMatrix(page, minimum);
        if (figure.company === 'aixi') {
          const filter = page.getByRole('searchbox', { name: 'Find a company' });
          await tabTo(page, filter);
          await page.keyboard.type(figure.organization);
          await expect(page.locator('#bh-matrix-body tr')).toHaveCount(1);
          await tabTo(page, page.getByRole('rowheader').getByRole('link', { name: figure.organization, exact: true }));
        } else {
          await tabTo(page, matrixButton(page, 'appen', 'customers'));
        }

        const button = matrixButton(page, figure.company, figure.signal);
        await page.keyboard.press('Tab');
        await expect(button).toBeFocused({ timeout: 3_000 });
        await expect(button).toHaveAccessibleName(figure.name);
        await expectReadableEvidence(button, figure, 'after Tab');

        await page.keyboard.press('Enter');
        const dialog = await expectUnavailableDialog(page, figure);
        await closeEvidence(page, dialog, button);
        await expectReadableEvidence(button, figure, 'after Escape');
      });
    }

    if (minimum) {
      phone('Market keeps wrapped organization names readable beside short matrix values', async ({ page }) => {
        await openMatrix(page, minimum);
        for (const figure of [
          { company: 'taskus', signal: 'delivery', organization: 'TaskUs', metric: 'Paid delivery', value: '—' },
          { company: 'rws_trainai', signal: 'customers', organization: 'RWS / TrainAI', metric: 'Customers', value: '—' },
        ]) {
          const button = matrixButton(page, figure.company, figure.signal);
          await tabTo(page, button);
          await expectReadableEvidence(button, figure, 'after Tab');
        }
      });
    } else {
      phone('Market includes every unavailable evidence cell in the matrix Tab order', async ({ page }) => {
        phone.setTimeout(90_000);
        await openMatrix(page);
        const matrix = page.locator('#bh-matrix-body');
        const expected = await matrix.locator('td:is([data-state="missing"], [data-state="n-a"])').evaluateAll(cells =>
          cells.map(cell => [cell.dataset.bhCompany, cell.dataset.bhSignal]),
        );
        expect(expected.length).toBeGreaterThan(0);
        await tabTo(page, matrix.locator('th a').first());

        const visited = [];
        const cells = await matrix.locator('th, td').count();
        for (let step = 0; step < cells; step++) {
          await page.keyboard.press('Tab');
          const activeCell = await page.evaluate(() => {
            const control = document.activeElement;
            const cell = control.closest('#bh-matrix-body :is(th, td)');
            if (!cell) return null;
            return { tag: control.tagName, ...cell.dataset };
          });
          if (!activeCell) break;
          if (activeCell.tag === 'BUTTON' && ['missing', 'n-a'].includes(activeCell.state)) {
            visited.push([activeCell.bhCompany, activeCell.bhSignal]);
          }
        }
        expect(visited).toHaveLength(expected.length);
        expect(visited).toEqual(expected);
      });
    }

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
