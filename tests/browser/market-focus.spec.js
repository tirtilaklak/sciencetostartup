const { test, expect, firefox } = require('@playwright/test');

const handshakeId = 'handshake_ai.metric.major-growth_metrics-0';
const mercorRunRateId = 'mercor.metric.oct14-major-financial-2';
const rwsGroupId = 'rws_trainai.claim.growth_metrics-0.metric-0';
const rwsSegmentId = 'rws_trainai.claim.growth_metrics-1.metric-0';
const gradeA = 'public filing, independent evidence or buyer confirmation';

async function openMarket(page) {
  await page.goto('/explore/#market');
  await expect(page.locator('#bh-ledger .bh-ledger-value').first()).toBeVisible();
  return page.locator('#bh-evidence-dialog');
}

async function ledgerControl(page, observationId, kind) {
  const control = page.locator(`.bh-ledger-${kind}[data-bh-ledger="${observationId}"]`);
  if (!await control.isVisible()) {
    await page.getByRole('button', { name: /^Show all \d+ companies$/ }).press('Enter');
  }
  return control;
}

async function chartControl(page, observationId, measure) {
  await page.locator('#bh-advanced > summary').press('Enter');
  if (measure) await page.getByRole('combobox', { name: 'Measure', exact: true }).selectOption(measure);
  await page.getByRole('combobox', { name: 'Reporting period & scope' }).selectOption('');
  return page.locator(`#bh-plot button[data-bh-observation="${observationId}"]`);
}

async function matrixControl(page, companyId, companyName) {
  await page.locator('.bh-coverage-disclosure > summary').press('Enter');
  await page.getByLabel('Find a company').fill(companyName);
  return page.locator(`#bh-matrix-body button[data-bh-company="${companyId}"][data-bh-signal="revenue"]`);
}

async function openEvidence(control, dialog) {
  await expect(control).toBeVisible();
  await control.press('Enter');
  await expect(dialog).toBeVisible();
}

test('Market puts two sourced revenue rows on the first desktop screen', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await openMarket(page);
  const dashboard = page.locator('#market-view');
  const shortcut = dashboard.locator('.hero-actions').getByRole('link', { name: 'Revenue & growth', exact: true });
  await expect(dashboard.locator('.hero-actions a')).toHaveCount(1);
  await expect(shortcut).toHaveAttribute('href', '#business-health');
  const rows = dashboard.locator('#bh-ledger .bh-ledger-row');
  await expect(rows.nth(0)).toBeInViewport({ ratio: 1 });
  await expect(rows.nth(1)).toBeInViewport({ ratio: 1 });
  await expect(dashboard.getByRole('link', { name: 'Historical company comparisons', exact: true }))
    .toHaveAttribute('href', '#companies');
});

test('Market restores Handshake focus to each successive evidence opener', async ({ page }) => {
  const dialog = await openMarket(page);
  await page.getByRole('tab', { name: /^Annualized pace/ }).press('Enter');

  await test.step('Escape returns to the ledger value', async () => {
    const value = await ledgerControl(page, handshakeId, 'value');
    await openEvidence(value, dialog);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(value).toBeFocused();
  });

  await test.step('Escape returns to the chart bar for the same observation', async () => {
    const bar = await chartControl(page, handshakeId);
    await openEvidence(bar, dialog);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect.soft(bar).toBeFocused();
  });

  await test.step('Close returns to the available-evidence matrix cell', async () => {
    const cell = await matrixControl(page, 'handshake_ai', 'Handshake');
    await openEvidence(cell, dialog);
    await dialog.getByRole('button', { name: 'Close figure details' }).click();
    await expect(dialog).toBeHidden();
    await expect(cell).toBeFocused();
  });
});

test('Market restores RWS focus after an alternate observation and nested claim', async ({ page }) => {
  const dialog = await openMarket(page);

  await test.step('Close returns to the ledger source button', async () => {
    const source = await ledgerControl(page, rwsGroupId, 'source');
    await openEvidence(source, dialog);
    await expect(dialog.locator('.bh-facts')).toContainText('Interim company reporting; unaudited');
    await expect(dialog.locator('[data-bh-source="rws_trainai.source.d_rws4"] a')).toHaveText(/RWS/);
    await dialog.locator('.bh-caveats > summary').press('Enter');
    await expect(dialog.locator('.bh-caveats')).toContainText(`Research grade A: ${gradeA}.`);
    await dialog.getByRole('button', { name: 'Close figure details' }).click();
    await expect(dialog).toBeHidden();
    await expect.soft(source).toBeFocused();
  });

  await test.step('Close returns to the chart bar after switching scope and inspecting a claim', async () => {
    const bar = await chartControl(page, rwsGroupId);
    await openEvidence(bar, dialog);
    const alternate = `button[data-bh-observation="${rwsSegmentId}"]`;
    const disclosure = dialog.locator('details').filter({ has: page.locator(alternate) });
    await disclosure.locator('summary').press('Enter');
    await disclosure.locator(alternate).press('Enter');

    const claim = dialog.locator('button[data-claim="rws_trainai.claim.growth_metrics-1"]');
    const sources = page.locator('#evidence-dialog');
    await openEvidence(claim, sources);
    await page.keyboard.press('Escape');
    await expect(sources).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect.soft(claim).toBeFocused();
    await dialog.getByRole('button', { name: 'Close figure details' }).click();
    await expect(dialog).toBeHidden();
    await expect.soft(bar).toBeFocused();
  });

  await test.step('Escape returns to the matrix cell after the chart and ledger sessions', async () => {
    const cell = await matrixControl(page, 'rws_trainai', 'RWS');
    await expect(cell.locator('.bh-grade')).toHaveAttribute('title', `Research grade A: ${gradeA}`);
    await openEvidence(cell, dialog);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(cell).toBeFocused();
  });

  await page.locator('.bh-method > summary').press('Enter');
  await expect(page.locator('#bh-method-content')).toContainText(`Grade A covers ${gradeA}.`);
});

test('Market marks the current observation by its exact ID', async ({ page }) => {
  const dialog = await openMarket(page);
  const cell = await matrixControl(page, 'mercor', 'Mercor');
  const bar = await chartControl(page, mercorRunRateId, 'annualized_revenue');

  await openEvidence(bar, dialog);
  await expect(dialog.locator('.bh-value')).toContainText('$2B');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(bar).toBeFocused();
  await expect(bar).toHaveAttribute('aria-current', 'true');
  await expect(cell).toContainText('$614M');
  await expect(cell).not.toHaveAttribute('aria-current', 'true');
  await expect(cell.locator('xpath=ancestor::tr')).toHaveClass('is-selected');
  await expect(page.locator('#bh-grid-head [data-bh-tab="revenue"]')).toHaveClass(/is-active/);

  await openEvidence(cell, dialog);
  await expect(dialog.locator('.bh-value')).toContainText('$614M');
  await dialog.getByRole('button', { name: 'Close figure details' }).click();
  await expect(dialog).toBeHidden();
  await expect(cell).toBeFocused();
  await expect(cell).toHaveAttribute('aria-current', 'true');
});

test('Market Back returns to the product link from both Market addresses', async ({ page }) => {
  await openMarket(page);
  const shortcut = page.getByRole('link', { name: 'Revenue & growth', exact: true });
  const product = page.getByRole('link', { name: 'Ango Hub', exact: true });
  const productSource = product.locator('xpath=ancestor::article').getByRole('link', { name: /^Image: iMerit/ });
  const companies = page.getByRole('link', { name: 'Historical company comparisons', exact: true });

  async function activate(link) {
    await link.scrollIntoViewIfNeeded();
    await link.focus();
    // WebKit may still be scrolling a focused link into view when the test presses Enter.
    await link.evaluate(anchor => {
      window.marketActivationScroll = null;
      anchor.addEventListener('click', () => { window.marketActivationScroll = window.scrollY; }, { once: true });
    });
    await page.keyboard.press('Enter');
    const top = await page.evaluate(() => window.marketActivationScroll);
    expect(top).toEqual(expect.any(Number));
    return top;
  }

  async function expectBack(hash, top) {
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`\\/explore\\/#${hash}$`));
    await expect.poll(() => page.evaluate(scroll => Math.abs(window.scrollY - scroll), top)).toBeLessThan(2);
  }

  const shortcutTop = await activate(shortcut);
  await expect(page.locator('#business-health-heading')).toBeFocused();
  await expectBack('market', shortcutTop);
  await expect(shortcut).toBeFocused();

  for (const hash of ['market', 'business-health']) {
    await test.step(`Return to the exact product link on ${hash}`, async () => {
      if (hash === 'business-health') {
        await activate(shortcut);
        await expect(page.locator('#business-health-heading')).toBeFocused();
      }
      const productTop = await activate(product);
      await expect(page).toHaveURL(/#company\/imerit\/business$/);
      await expect(page.locator('#profile-view').getByRole('heading', { name: 'iMerit / EXL', level: 1 })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
      await expectBack(hash, productTop);
      await expect(product).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(productSource).toBeFocused();
    });

    const companiesTop = await activate(companies);
    await expect(page).toHaveURL(/#companies$/);
    await expectBack(hash, companiesTop);
    await expect(companies).toBeFocused();
  }
});

const enlargedText = test.extend({
  enlargedPage: async ({ baseURL }, use) => {
    const browser = await firefox.launch({
      firefoxUserPrefs: { 'font.minimum-size.x-western': 28, 'font.minimum-size.x-unicode': 28 },
    });
    try {
      await use(await browser.newPage({ baseURL, viewport: { width: 320, height: 720 } }));
    } finally {
      await browser.close();
    }
  },
});

enlargedText.describe('Market with a 28px minimum font', () => {
  enlargedText.describe.configure({ timeout: 60_000 });
  enlargedText.skip(({ browserName }) => browserName !== 'firefox', 'Firefox provides a real minimum font preference');

  enlargedText('advanced picks show the entire applied measure and scope', async ({ enlargedPage: page }) => {
    const dialog = await openMarket(page);
    await page.locator('#bh-advanced > summary').click();
    const measure = page.getByRole('combobox', { name: 'Measure', exact: true });
    const scope = page.getByRole('combobox', { name: 'Reporting period & scope' });

    async function expectWrappedValue(control, label) {
      const displayed = control.locator('xpath=following-sibling::span');
      await expect(displayed).toHaveText(label);
      const lines = await displayed.evaluate(field => {
        const box = field.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(field);
        return [...range.getClientRects()].map(line => ({
          height: line.height,
          fits: line.left >= box.left && line.right <= box.right && line.top >= box.top && line.bottom <= box.bottom,
        }));
      });
      expect(lines.length).toBeGreaterThan(1);
      expect(lines.every(line => line.height >= 28 && line.fits)).toBe(true);
    }

    await expectWrappedValue(measure, 'Revenue over a completed period');
    await expectWrappedValue(scope, '9M 2026 · USD · Whole company · Gross/net undisclosed');
    await measure.press('End');
    await expectWrappedValue(measure, 'Year-over-year revenue growth');
    await expect(measure).toBeFocused();
    await measure.press('Home');
    await expectWrappedValue(measure, 'Revenue over a completed period');

    const generate = 'H1 FY2026 · Oct 2025–Mar 2026 · GBP · Generate segment · Gross/net undisclosed';
    await scope.selectOption({ label: generate });
    await expectWrappedValue(scope, generate);
    const bar = page.locator(`#bh-plot button[data-bh-observation="${rwsSegmentId}"]`);
    await bar.click();
    await expect(dialog.locator('.bh-value')).toContainText('£99.4M');
    await expect(dialog.locator('.bh-facts')).toContainText('Generate segment · Includes TrainAI and Content Technology');
    await page.keyboard.press('Escape');
    await expect(bar).toBeFocused();
  });

  enlargedText('Market anchors account for the sticky header and Back restores the keyboard shortcut', async ({ enlargedPage: page }) => {
    const heading = page.locator('#business-health-heading');
    const section = page.locator('#business-health');
    const expectAnchor = async () => {
      await expect(heading).toBeFocused();
      await expect.poll(() => section.evaluate(node => (
        Math.abs(node.getBoundingClientRect().top - parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop))
      ))).toBeLessThan(2);
    };

    await page.goto('/explore/#business-health');
    await expectAnchor();

    await openMarket(page);
    const shortcut = page.getByRole('link', { name: 'Revenue & growth', exact: true });
    for (let step = 0; step < 30; step++) {
      if (await shortcut.evaluate(link => link === document.activeElement)) break;
      await page.keyboard.press('Tab');
    }
    await expect(shortcut).toBeFocused();
    // Record the scroll position after Firefox has brought the focused link into view.
    const originalScroll = await page.evaluate(() => new Promise(resolve => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve(window.scrollY)));
    }));
    await page.keyboard.press('Enter');
    await expectAnchor();
    await page.goBack();
    await expect(page).toHaveURL(/\/explore\/#market$/);
    await expect(shortcut).toBeFocused();
    await expect.poll(() => page.evaluate(scroll => Math.abs(window.scrollY - scroll), originalScroll)).toBeLessThan(2);
  });
});
