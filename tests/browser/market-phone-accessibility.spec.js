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

async function tabTo(page, control, stops = 60) {
  await expect(control).toBeVisible();
  for (let step = 0; step < stops; step++) {
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
    name: /Appen · Paid delivery · No reviewed public disclosure/,
    heading: 'No reviewed public figure', description: /paid delivery for Appen\. Missing is not zero\./,
    dialogName: 'Appen · Paid delivery No reviewed public figure',
    profile: '#company/appen/traction',
  },
  {
    company: 'aixi', signal: 'revenue', organization: 'AIXI Labs', metric: 'Revenue', value: 'n/a',
    name: /n\/a · AIXI Labs · Revenue · Nonprofit research/,
    heading: 'Not applied', description: /AIXI Labs is a nonprofit research organization\. Commercial measures are not applied/,
    profile: '#company/aixi',
  },
];

async function expectUnavailableDialog(page, { heading, description, profile, dialogName }) {
  const dialog = page.locator('#bh-evidence-dialog');
  await expect(dialog.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  if (dialogName) await expect(dialog).toHaveAccessibleName(dialogName);
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

  test('Market skips the matrix body by keyboard and keeps its filters and position', async ({ page }) => {
    await openMatrix(page);
    const matrix = page.locator('.bh-coverage-disclosure');
    const grid = matrix.locator('#bh-grid-wrap');
    const skip = matrix.getByRole('button', { name: 'Skip to definitions and evidence limits', exact: true });
    const method = page.locator('.bh-method');
    const summary = method.locator(':scope > summary');
    const search = matrix.getByRole('searchbox', { name: 'Find a company' });
    const order = matrix.getByRole('combobox', { name: 'Order' });
    const withFigures = matrix.getByRole('checkbox', { name: 'With public figures' });
    const gridScroll = () => grid.evaluate(element => [element.scrollLeft, element.scrollTop]);
    const historyLength = () => page.evaluate(() => history.length);

    await expect(grid.locator('tbody :is(a, button)')).toHaveCount(234);
    await tabTo(page, withFigures);
    await page.keyboard.press('Tab');
    await expect(skip).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(grid).toBeFocused();

    await search.fill('a');
    await order.selectOption('name');
    await tabTo(page, withFigures);
    await page.keyboard.press('Space');
    await expect(withFigures).toBeChecked();
    await page.keyboard.press('Tab');
    await expect(skip).toBeFocused();
    expect(await grid.evaluate(element => element.previousElementSibling === document.activeElement)).toBe(true);
    const rows = await grid.locator('tbody th a').allTextContents();
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.length).toBeLessThan(39);
    const url = page.url();
    const entries = await historyLength();
    await grid.evaluate(element => element.scrollTo({ left: 40, top: 40, behavior: 'instant' }));
    const position = await gridScroll();
    expect(position).toEqual([40, 40]);

    await page.keyboard.press('Enter');
    await expect(summary).toBeFocused();
    await expect(summary).toBeInViewport({ ratio: 1 });
    expect(await summary.evaluate(element => {
      const box = element.getBoundingClientRect();
      return element.matches(':focus-visible')
        && element.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
    })).toBe(true);
    await expect(method).not.toHaveAttribute('open', '');
    await expect(matrix).toHaveAttribute('open', '');
    await expect(search).toHaveValue('a');
    await expect(order).toHaveValue('name');
    await expect(withFigures).toBeChecked();
    await expect(grid.locator('tbody th a')).toHaveText(rows);
    await expect(page).toHaveURL(url);
    expect(await historyLength()).toBe(entries);
    expect(await gridScroll()).toEqual(position);

    await page.keyboard.press('Enter');
    await expect(method).toHaveAttribute('open', '');
    await page.keyboard.press('Tab');
    await expect(method.getByRole('link', { name: /^Download observations and calculations/ })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(method.getByRole('link', { name: 'Research method', exact: true })).toBeFocused();
  });

  test('Market exposes the selected Cash order as grouped by reporting basis', async ({ page }) => {
    await openMatrix(page);
    const cash = page.locator('#bh-grid-head [data-bh-tab="cash"]');
    const sortedHeader = page.locator('#bh-grid-head th[aria-sort]');
    await expect(sortedHeader).toContainText('Organization');
    await expect(sortedHeader).toHaveAttribute('aria-sort', 'other');
    await tabTo(page, cash);
    await page.keyboard.press('Enter');
    await expect(cash).toBeFocused();
    await expect(cash).toBeInViewport({ ratio: 0.5 });
    const firstCashRows = await page.locator('#bh-matrix-body tr').evaluateAll(rows => rows.slice(0, 5).map(row => {
      const cell = row.querySelector('td[data-bh-signal="cash"]');
      return [row.querySelector('th a').textContent, cell.querySelector('b').firstChild.textContent, cell.dataset.state];
    }));
    expect(firstCashRows).toEqual([
      ['RWS / TrainAI', '£33.7M', 'observed'],
      ['TaskUs', '$180.3M', 'observed'],
      ['Appen', '$44.71M', 'observed'],
      ['micro1', '≈ 180', 'proxy'],
      ['iMerit / EXL', '≈ 3,600', 'proxy'],
    ]);
    await expect(sortedHeader).toHaveCount(1);
    await expect(sortedHeader).toContainText('Cash');
    await expect(sortedHeader).toHaveAttribute('aria-sort', 'other');
    const explanation = 'Figures run high to low within groups that share a measure and reporting basis, including currency.';
    const status = page.locator('#bh-matrix-count');
    await expect(status).toContainText(`Ordered by cash evidence. ${explanation}`);
    await expect(cash).toHaveAccessibleDescription(await status.innerText());
    await page.keyboard.press('Tab');
    await expect(page.locator('#bh-matrix-body th a').first()).toBeFocused();
  });

  test('Market names all unavailable Paid delivery cells and dialogs for that column', async ({ page }) => {
    await openMatrix(page);
    await expect(page.getByRole('columnheader', { name: /^Paid delivery/ })).toBeVisible();
    const unavailable = page.locator('#bh-matrix-body td[data-bh-signal="delivery"]:is([data-state="missing"], [data-state="n-a"])');
    await expect(unavailable).toHaveCount(25);
    await expect(unavailable.getByRole('button', { name: / · Paid delivery · / })).toHaveCount(25);
    const cells = await unavailable.evaluateAll(nodes => nodes.map(cell => ({
      company: cell.dataset.bhCompany,
      organization: cell.parentElement.querySelector('th a').textContent,
      nonprofit: cell.dataset.state === 'n-a',
    })));

    const dialog = page.locator('#bh-evidence-dialog');
    for (const { company, organization, nonprofit } of cells) {
      await test.step(organization, async () => {
        const button = matrixButton(page, company, 'delivery');
        const reason = nonprofit ? 'Nonprofit research: commercial measures are not applied' : 'No reviewed public disclosure. Missing is not zero.';
        const title = nonprofit ? 'Not applied' : 'No reviewed public figure';
        await expect(button).toHaveAccessibleName(`${nonprofit ? 'n/a · ' : ''}${organization} · Paid delivery · ${reason}`);
        await expect(button).toHaveAttribute('aria-haspopup', 'dialog');
        await button.press('Enter');
        await expect(dialog).toHaveAccessibleName(`${organization} · Paid delivery ${title}`);
        await expect(dialog.getByRole('heading', { name: title, exact: true })).toBeVisible();
        await expect(dialog.locator('.bh-lede')).toContainText(organization);
        await closeEvidence(page, dialog, button);
      });
    }

    await page.locator('#bh-advanced > summary').press('Enter');
    await expect(page.getByRole('tab', { name: 'Expert activity', exact: true })).toBeVisible();

    const context = matrixButton(page, 'labelbox', 'delivery');
    await expect(context).toHaveAccessibleName(/Alignerr knowledge contributors.*context only/);
    await context.press('Enter');
    await expect(dialog.locator('.bh-value')).toContainText('≥ 2.6M');
    await closeEvidence(page, dialog, context);

    const mercor = matrixButton(page, 'mercor', 'delivery');
    await mercor.press('Enter');
    await expect(dialog).toHaveAccessibleName('Mercor');
    await expect(dialog.locator('.bh-measure-name')).toHaveText('Daily expert payouts');
    await expect(dialog.locator('.bh-value')).toContainText('> $4M');
    await expect(dialog.locator('.bh-facts')).toContainText('AI business / service line');
    await dialog.getByText('Other dates', { exact: true }).press('Enter');
    await dialog.getByRole('button', { name: /> \$2M/ }).press('Enter');
    await expect(dialog.locator('.bh-value')).toContainText('> $2M');
    await expect(dialog.locator('.bh-facts')).toContainText('Whole company');
    await closeEvidence(page, dialog, mercor);
  });
});

test.describe('Market figure return with a sorted table', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('closing a figure reveals its opener after the selected measure reorders the rows', async ({ page, hasTouch }) => {
    await page.goto('/explore/#business-health');
    await page.locator('.bh-coverage-disclosure > summary').click();
    await page.locator('#bh-sort').selectOption('signal');
    const opener = matrixButton(page, 'appen', 'delivery');
    const rowBefore = await opener.evaluate(button => button.closest('tr').rowIndex);
    if (hasTouch) await opener.tap();
    else await opener.click();
    const close = page.getByRole('button', { name: 'Close figure details' });
    if (hasTouch) await close.tap();
    else await close.click();
    await expect(opener).toBeFocused();
    expect(await opener.evaluate(button => button.closest('tr').rowIndex)).not.toBe(rowBefore);
    await expect.poll(() => opener.evaluate(button => {
      const box = button.getBoundingClientRect();
      return button.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
    })).toBe(true);
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
      phone('Market keeps wrapped Laude and Trajectory names readable on Tab and after Escape', async ({ page }) => {
        phone.setTimeout(90_000);
        const figures = [
          {
            company: 'laude', signal: 'cash', organization: 'Laude Institute / Terminal-Bench', metric: 'Cash', value: 'n/a',
            heading: 'Not applied', description: /Laude Institute \/ Terminal-Bench is a nonprofit research organization\./,
            profile: '#company/laude',
          },
          {
            company: 'trajectory_labs_pbc', signal: 'revenue', organization: 'Trajectory Labs, PBC', metric: 'Revenue', value: '—',
            heading: 'No reviewed public figure', description: /for Trajectory Labs, PBC\. Missing is not zero\./,
            profile: '#company/trajectory_labs_pbc/traction',
          },
        ];
        await openMatrix(page, minimum);
        const grid = page.locator('#bh-grid-wrap');
        const readMatrix = () => grid.evaluate(wrap => {
          const table = wrap.querySelector('table');
          return {
            scrollport: [wrap.clientWidth, wrap.clientHeight, wrap.scrollWidth, wrap.scrollHeight],
            columnWidths: [...table.tHead.rows[0].cells].map(cell => cell.offsetWidth),
            rows: [...table.tBodies[0].rows].map(row => ({
              height: row.offsetHeight,
              cells: [...row.cells].map(cell => [cell.dataset.state, cell.textContent.trim()]),
            })),
          };
        });
        const initial = await readMatrix();
        const tabStops = 60 + await grid.locator('a, button').count();

        for (const figure of figures) {
          await test.step(`${figure.organization} ${figure.metric}`, async () => {
            const button = matrixButton(page, figure.company, figure.signal);
            await tabTo(page, button, tabStops);
            await expectReadableEvidence(button, figure, 'after Tab');
            expect(await readMatrix()).toEqual(initial);

            await page.keyboard.press('Enter');
            const dialog = await expectUnavailableDialog(page, figure);
            await closeEvidence(page, dialog, button);
            await expectReadableEvidence(button, figure, 'after Escape');
            expect(await readMatrix()).toEqual(initial);
          });
        }
      });

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
