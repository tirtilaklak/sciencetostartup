const { test, expect } = require('@playwright/test');

const handshakeId = 'handshake_ai.metric.major-growth_metrics-0';
const mercorRunRateId = 'mercor.metric.oct14-major-financial-2';
const rwsGroupId = 'rws_trainai.claim.growth_metrics-0.metric-0';
const rwsSegmentId = 'rws_trainai.claim.growth_metrics-1.metric-0';

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
    await openEvidence(cell, dialog);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(cell).toBeFocused();
  });
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
