const { test, expect } = require('@playwright/test');

const financeRecords = [
  { company: 'benchflow', metric: 'benchflow.claim.total_funding.metric-0', label: 'Reported funding',
    date: 'Founder post published: 11 Feb 2025', check: 'Source checked 22 Nov 2026' },
  { company: 'a-team', metric: 'a-team.claim.total_funding.metric-0', label: 'Funding claimed',
    date: 'Source checked: 12 Oct 2026', check: 'The cited statement has no publication date.' },
  { company: 'elorian', metric: 'elorian.claim.valuation.metric-0', label: 'Reported valuation',
    date: 'Interview published: 16 Jul 2026', check: 'Source checked 22 Nov 2026' },
];

async function openDisclosure(summary) {
  if (!await summary.evaluate(node => node.parentElement.open)) await summary.press('Enter');
}

for (const { company, metric, label, date, check } of financeRecords) {
  test(`${company} archive reads the reviewed financing label and date role`, async ({ page }) => {
    await page.goto(`/explore/#company/${company}/financing`);
    const panel = page.locator('#profile-financing');
    await openDisclosure(panel.locator(':scope > summary'));
    const row = panel.locator(`[data-metric="${metric}"]`);
    await expect(row.getByRole('heading')).toHaveText(label);
    const source = row.locator('button.number-button');
    await expect(source).toHaveAccessibleName(new RegExp(`${label}.*${date}`));
    await source.press('Enter');
    const dialog = page.locator('#evidence-dialog');
    const [dateRole, day] = date.split(': ');
    await expect(dialog.locator('.evidence-data > div').filter({ hasText: dateRole }).first()).toContainText(day);
    await expect(dialog).toContainText(check);
    await page.keyboard.press('Escape');
    await expect(source).toBeFocused();
  });
}

test('Mercor keeps the $614M H1 gross estimate attribution and canonical source', async ({ page }) => {
  const metric = 'mercor.metric.major-growth_metrics-1';
  await page.goto('/company/mercor/#financial-record');
  await openDisclosure(page.locator('#financial-record > summary'));
  const retained = page.locator(`[data-metric="${metric}"]`);
  await expect(retained).toContainText('Third-party estimate');
  await expect(retained).toContainText('$614M');
  await expect(retained.locator('a[href="https://sacra.com/c/mercor/"]')).toBeVisible();

  await page.goto('/explore/#company/mercor/observations');
  const panel = page.locator('#profile-observations');
  await openDisclosure(panel.locator(':scope > summary'));
  const row = panel.locator(`[data-metric="${metric}"]`);
  await expect(row.getByRole('heading')).toHaveText('Estimated H1 gross revenue');
  const source = row.locator('button.number-button');
  await expect(source).toHaveAccessibleName(/\$614M.*Estimated H1 gross revenue.*Reporting period: H1 2026/);
  await expect(source).toHaveAccessibleDescription(/Sacra.*Original dataset statement:/);
  await source.press('Enter');
  const dialog = page.locator('#evidence-dialog');
  await expect(dialog.locator(`[data-evidence-metric="${metric}"]`)).toContainText('Third-party estimate');
  await expect(dialog.locator('.claim-confidence')).toContainText(/Confidence grade\s*C/);
  await expect(dialog.locator('a[href="https://sacra.com/c/mercor/"]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(source).toBeFocused();
});

test('the RWS matching chart names Generate and identifies the group separately', async ({ page }) => {
  await page.goto('/explore/#market');
  await expect(page.locator('#bh-ledger > article').first()).toBeVisible();
  await openDisclosure(page.locator('#bh-advanced > summary'));
  await page.locator('#bh-cohort').selectOption('');
  const chart = page.locator('#bh-plot');
  const group = chart.locator('[data-bh-observation="rws_trainai.claim.growth_metrics-0.metric-0"]');
  await expect(group).toContainText('£360.3M');
  await expect(group).toContainText('RWS Holdings plc group');
  const segment = chart.locator('[data-bh-observation="rws_trainai.claim.growth_metrics-1.metric-0"]');
  await expect(segment).toContainText('£99.4M');
  await expect(segment).toHaveAccessibleName(/£99\.4M.*Generate segment/);
  await expect(segment).toContainText('Generate segment');
  await expect(segment.locator('..').getByRole('heading')).toContainText('Generate segment');
  await segment.press('Enter');
  const dialog = page.locator('#bh-evidence-dialog');
  await expect(dialog.locator('.bh-facts')).toContainText('Generate segment · Includes TrainAI and Content Technology');
  await page.keyboard.press('Escape');
  await expect(segment).toBeFocused();
});

test('the RWS risk source control distinguishes checking from publication', async ({ page }) => {
  await page.goto('/explore/#compare/rws_trainai/quesma');
  await page.getByRole('button', { name: 'Show more evidence' }).press('Enter');
  const source = page.locator('[data-claim="rws_trainai.claim.risks-1"]');
  await expect(source).toHaveAccessibleName(/Source checked: 12 Oct 2026/);
  await expect(source).toHaveAccessibleDescription(/The cited sources give no publication dates/);
  await source.press('Enter');
  const dialog = page.locator('#evidence-dialog');
  await expect(dialog.locator('.sources-list li').filter({ hasText: 'Publication date not stated' })).toHaveCount(2);
  await expect(dialog.locator('.evidence-data > div').first()).toHaveText(/^Source checked\s*12 Oct 2026$/);
  await expect(dialog).toContainText('The cited sources give no publication dates.');
  await expect(dialog).not.toContainText('This date comes from the source.');
  await page.keyboard.press('Escape');
  await expect(source).toBeFocused();
});
