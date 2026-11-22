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
  await openMarket(page);
  const chart = await marketChart(page, 'period_revenue');
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

const summaryRecorded = 'Summary only, page not reviewed · recorded 12 Oct 2026';
const unknownDate = 'The record does not identify where this date came from.';
const afterQuerySources = [
  ['afterquery.source.b_aq3', 'https://www.afterquery.com/blog/human-expertise-reimagined', 'AfterQuery', '9 Apr 2026'],
  ['afterquery.source.b_aq4', 'https://www.forbes.com.au/news/innovation/afterquery-becomes-ycs-fastest-unicorn-at-us3-2-billion/', 'Forbes Australia', '2 Sep 2026'],
];

async function expectResearchRecordDate(dialog) {
  const fields = dialog.locator('.evidence-data');
  await expect(fields.locator(':scope > div').first()).toHaveText(/^Research record date\s*12 Oct 2026$/);
  await expect(fields.getByText('Source checked', { exact: true })).toHaveCount(0);
  await expect(dialog).toContainText(unknownDate);
}

test('a risk with only undated source summaries keeps its research record date', async ({ page }) => {
  await page.goto('/explore/#company/refresh/claim/refresh.claim.risks-0');
  const dialog = page.locator('#evidence-dialog');
  await expectResearchRecordDate(dialog);
  const rows = dialog.locator('.sources-list > li');
  await expect(rows.locator('p.sub:first-of-type')).toHaveText(
    ['Refresh', 'Teeming', 'Extruct'].map(publisher => `${publisher} · Publication date not stated · ${summaryRecorded}`),
  );
  await expect(rows.first().getByRole('link')).toHaveAttribute('href', 'https://www.refresh.dev/about');
});

test('a profile risk keeps its research date and two separate publication dates', async ({ page }) => {
  await page.goto('/explore/#company/afterquery/risks');
  const risk = page.locator('[data-profile-risk="afterquery.claim.risks-0"]');
  await expect(risk.locator('.risk-date')).toHaveText('Research record date · 12 Oct 2026');
  const source = risk.getByRole('button');
  await expect(source).toHaveAccessibleName(/AfterQuery.*Research record date: 12 Oct 2026/);
  await expect(source).toHaveAccessibleDescription(new RegExp(unknownDate.replace('.', '\\.')));
  await source.press('Enter');
  const dialog = page.locator('#evidence-dialog');
  await expectResearchRecordDate(dialog);
  await expect(dialog.locator('.sources-list > li')).toHaveCount(2);
  for (const [id, url, publisher, day] of afterQuerySources) {
    const row = dialog.locator(`[data-source-id="${id}"]`);
    await expect(row.getByRole('link')).toHaveAttribute('href', url);
    await expect(row.locator('p.sub').first()).toHaveText(`${publisher} · Published ${day} · ${summaryRecorded}`);
  }
  await page.keyboard.press('Escape');
  await expect(source).toBeFocused();
});

test.describe('plain evidence without scripting', () => {
  test.use({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });

  test('risks show source publication dates and summary status', async ({ page }) => {
    await page.goto('/company/afterquery/');
    await openDisclosure(page.locator('details:has(#risks) > summary'));
    const row = page.locator('[data-risk="afterquery.claim.risks-0"]');
    await expect(row.locator('td.date')).toHaveText(/^Research record date\s*12 Oct 2026$/);
    const citations = row.locator('td.wide-cell');
    await openDisclosure(citations.locator('summary'));
    for (const [, url, publisher, day] of afterQuerySources) {
      const link = citations.locator(`a[href="${url}"]`);
      await expect(link).toBeVisible();
      await expect(citations.locator('a + .sub').filter({ hasText: publisher }))
        .toHaveText(`${publisher} · Published ${day} · ${summaryRecorded}`);
    }
  });

  test('Handshake and Mercor keep the reporting period and exact source dates separate', async ({ page }) => {
    await page.goto('/company/handshake_ai/');
    await openDisclosure(page.locator('#financial-record > summary'));
    const selected = page.locator('#financial-record [data-financial-observation="handshake_ai.metric.major-growth_metrics-0"]');
    await expect(selected.locator(':scope > .sub').first()).toContainText(/Annualized revenue run rate · Apr(?:il)? 2026 ·/);
    await expect(selected).toContainText('Published 14 Apr 2026');
    await expect(selected).toContainText('Source content checked 28 Oct 2026');
    await expect(selected).not.toContainText('reporting period remains 2026-04-14');
    const dealroom = page.locator('[data-metric="handshake_ai.metric.major-growth_metrics-0"]');
    await expect(dealroom.locator('[data-label="Date"]')).toHaveText('April 2026 · reported');
    await expect(dealroom.locator('[data-label="Source"] > .sub')).toHaveText('dealroom.co · Published 14 Apr 2026 · Checked 14 Oct 2026');
    await expect(dealroom.getByRole('link'))
      .toHaveAttribute('href', 'https://dealroom.co/news/127345-handshakes-arr-crosses-1b-as-ai-training-revenue-surges/');

    await page.goto('/company/mercor/');
    await openDisclosure(page.locator('#financial-record > summary'));
    const selectedFelicis = page.locator('#financial-record [data-financial-observation="mercor.metric.oct14-major-financial-2"]');
    await expect(selectedFelicis).toContainText('Published 21 Jul 2026');
    const felicis = page.locator('[data-metric="mercor.metric.oct14-major-financial-2"]');
    await expect(felicis.locator('[data-label="Date"]')).toHaveText('Jun 2026');
    await expect(felicis.locator('[data-label="Source"] > .sub')).toHaveText('www.felicis.com · Published 21 Jul 2026 · Checked 14 Oct 2026');
    await expect(felicis.getByRole('link'))
      .toHaveAttribute('href', 'https://www.felicis.com/blog/mercor-profile-organizing-human-intelligence-to-power-the-ai-economy');
  });
});

test('Handshake keeps the corrected Dealroom date separate from its reporting period', async ({ page }) => {
  await page.goto('/explore/#company/handshake_ai/claim/handshake_ai.claim.oct14-major-financial-0');
  const dialog = page.locator('#evidence-dialog');
  const fields = dialog.locator('.evidence-data');
  await expect(fields.locator(':scope > div').first()).toHaveText(/^Original dataset reporting date\s*23 Apr 2026$/);
  await expect(fields).toContainText(/Research observation recorded\s*14 Oct 2026/);
  await expect(dialog.locator('[data-evidence-metric="handshake_ai.metric.major-growth_metrics-0"]'))
    .toContainText('April 2026 · reported');
  const dealroom = dialog.locator('.sources-list [data-source-id="handshake_ai.source.oct14-e0de0f3911dc"]');
  await expect(dealroom.getByRole('link'))
    .toHaveAttribute('href', 'https://dealroom.co/news/127345-handshakes-arr-crosses-1b-as-ai-training-revenue-surges/');
  await expect(dealroom.locator('p.sub').first()).toHaveText('dealroom.co · Published 14 Apr 2026 · Checked 14 Oct 2026');
  await expect(dialog.getByRole('listitem').filter({ hasText: 'Separate investor corroboration' }))
    .toContainText('Published 23 Apr 2026');

  await page.goto('/explore/#company/handshake_ai/claim/handshake_ai.claim.oct14-major-financial-1');
  await expect(fields.locator(':scope > div').first()).toHaveText(/^Research record date\s*Apr 2026$/);
  await expect(dealroom.locator('p.sub').first()).toHaveText('dealroom.co · Published 14 Apr 2026 · Checked 14 Oct 2026');
});

test('Mercor binds the reviewed publication date to Felicis and leaves Sacra undated', async ({ page }) => {
  await page.goto('/explore/#company/mercor/claim/mercor.claim.oct14-major-financial-2');
  const dialog = page.locator('#evidence-dialog');
  const felicis = dialog.locator('.sources-list [data-source-id="mercor.source.oct14-88dab2271689"]');
  await expect(felicis.getByRole('link'))
    .toHaveAttribute('href', 'https://www.felicis.com/blog/mercor-profile-organizing-human-intelligence-to-power-the-ai-economy');
  await expect(felicis.locator('p.sub').first()).toContainText('Published 21 Jul 2026 · Checked 14 Oct 2026');
  const sacra = dialog.getByRole('listitem').filter({ hasText: 'Sacra · separate secondary gross estimate' });
  await expect(sacra.getByRole('link')).toHaveAttribute('href', 'https://sacra.com/c/mercor/');
  await expect(sacra).not.toContainText('Published');
});

async function openMarket(page) {
  await page.goto('/explore/#market');
  await expect(page.locator('#bh-ledger > article').first()).toBeVisible();
}

async function marketLedgerFigure(page, metric, tab) {
  if (tab) await page.getByRole('tab', { name: tab }).press('Enter');
  const figure = page.locator(`.bh-ledger-value[data-bh-ledger="${metric}"]`);
  if (!await figure.isVisible()) {
    await page.getByRole('button', { name: /^Show all \d+ companies$/ }).press('Enter');
  }
  return figure;
}

async function marketChart(page, measure) {
  await openDisclosure(page.locator('#bh-advanced > summary'));
  await page.getByRole('combobox', { name: 'Measure', exact: true }).selectOption(measure);
  await page.getByRole('combobox', { name: 'Reporting period & scope' }).selectOption('');
  return page.locator('#bh-plot');
}

async function marketMatrixRow(page, company) {
  await openDisclosure(page.locator('.bh-coverage-disclosure > summary'));
  await page.getByLabel('Find a company').fill(company);
  return page.locator('#bh-matrix-body').getByRole('row').filter({
    has: page.getByRole('link', { name: company, exact: true }),
  });
}

function marketFact(dialog, label) {
  return dialog.locator('dl.bh-facts').getByText(label, { exact: true })
    .locator('xpath=following-sibling::*[1][self::dd]');
}

function marketCitation(dialog, id) {
  return marketFact(dialog, 'Source').locator(`[data-bh-source="${id}"]`);
}

async function closeMarketEvidence(page) {
  await page.keyboard.press('Escape');
  await expect(page.locator('#bh-evidence-dialog')).toBeHidden();
}

const handshakeMetric = 'handshake_ai.metric.major-growth_metrics-0';
const handshakePeriod = /^Apr(?:il)? 2026$/;
for (const path of ['ledger', 'chart', 'matrix']) {
  test(`Market ${path} keeps Handshake’s April period separate from Dealroom’s publication and check`, async ({ page }) => {
    await openMarket(page);
    let figure;
    if (path === 'ledger') {
      figure = await marketLedgerFigure(page, handshakeMetric, /^Annualized pace/);
      await expect(figure.locator('..').locator('.bh-ledger-period')).toHaveText(handshakePeriod);
      await expect(figure).toHaveAccessibleName(/Handshake AI.*Nearly \$1B.*Reporting period Apr(?:il)? 2026/);
    } else if (path === 'chart') {
      const chart = await marketChart(page, 'annualized_revenue');
      figure = chart.locator(`[data-bh-observation="${handshakeMetric}"]`);
      await expect(figure).toHaveAccessibleName(/Handshake AI.*Nearly \$1B.*Reporting period Apr(?:il)? 2026.*AI business/);
      await expect(figure).not.toHaveAccessibleName(/14 Apr|2026-04-14/);
    } else {
      const row = await marketMatrixRow(page, 'Handshake AI');
      figure = row.getByRole('button', { name: /^Nearly \$1B\b/ });
      await expect(figure).toHaveText(/grade C.*Apr(?:il)? 2026$/);
      await expect(figure).toHaveAccessibleName(/Nearly \$1B.*Reporting period Apr(?:il)? 2026.*grade C/);
      await expect(figure).not.toHaveAccessibleName(/14 Apr|2026-04-14/);
    }
    await figure.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Handshake AI' });
    await expect(dialog.locator('.bh-value')).toHaveText(/Nearly \$1B\s*Reported/);
    await expect(marketFact(dialog, 'Reporting period')).toHaveText(handshakePeriod);
    await expect(marketFact(dialog, 'Basis')).toHaveText('Gross');
    const source = marketCitation(dialog, 'handshake_ai.source.oct14-e0de0f3911dc');
    await expect(source.getByRole('link', { name: /dealroom\.co/ })).toHaveAttribute('href',
      'https://dealroom.co/news/127345-handshakes-arr-crosses-1b-as-ai-training-revenue-surges/');
    await expect(source).toContainText('Published 14 Apr 2026');
    await expect(source).toContainText(/(?:Source page read|Source content checked) 28 Oct 2026/);
  });
}

test('Market keeps the Mercor June $2B investor report separate from the $614M H1 estimate', async ({ page }) => {
  await openMarket(page);
  const pace = await marketLedgerFigure(page, 'mercor.metric.oct14-major-financial-2', /^Annualized pace/);
  await expect(pace.locator('..').locator('.bh-ledger-period')).toHaveText(/^Jun(?:e)? 2026$/);
  const dialog = page.getByRole('dialog', { name: 'Mercor' });
  const expectFelicisPace = async () => {
    await expect(dialog.locator('.bh-value')).toHaveText(/^\$2B\s*Reported$/);
    await expect(marketFact(dialog, 'Reporting period')).toHaveText(/^Jun(?:e)? 2026$/);
    await expect(marketFact(dialog, 'Scope')).toHaveText('Whole company');
    await expect(marketFact(dialog, 'Source')).toContainText('Investor-reported');
    const felicis = marketCitation(dialog, 'mercor.source.oct14-88dab2271689');
    await expect(felicis.getByRole('link', { name: /felicis\.com/ })).toHaveAttribute('href',
      'https://www.felicis.com/blog/mercor-profile-organizing-human-intelligence-to-power-the-ai-economy');
    await expect(felicis).toContainText('Published 21 Jul 2026');
  };
  await pace.press('Enter');
  await expectFelicisPace();
  await closeMarketEvidence(page);

  const row = await marketMatrixRow(page, 'Mercor');
  const estimate = row.getByRole('button', { name: /^\$614M\b/ });
  await expect(estimate).toHaveText(/grade C.*H1 2026$/);
  await estimate.press('Enter');
  await expect(dialog.locator('.bh-value')).toHaveText(/^\$614M\s*Third-party estimate$/);
  await expect(marketFact(dialog, 'Reporting period')).toHaveText('H1 2026');
  await expect(marketFact(dialog, 'Basis')).toHaveText('Gross');
  const sacra = marketCitation(dialog, 'mercor.source.audit-m6');
  await expect(sacra.getByRole('link', { name: /sacra\.com/ })).toHaveAttribute('href', 'https://sacra.com/c/mercor/');
  await expect(sacra).not.toContainText(/Published \d/);
  await openDisclosure(dialog.getByText('Other measures', { exact: true }));
  await dialog.getByRole('button', { name: /Jun(?:e)? 2026.*\$2B/ }).press('Enter');
  await expectFelicisPace();
});

test('Market shows Generate as another RWS business scope in the same reporting period', async ({ page }) => {
  await openMarket(page);
  const row = await marketMatrixRow(page, 'RWS / TrainAI');
  const group = row.getByRole('button', { name: /^£360\.3M\b/ });
  await expect(group).toHaveText(/grade A.*RWS Holdings plc group.*H1 FY2026/);
  await group.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'RWS / TrainAI' });
  const period = marketFact(dialog, 'Reporting period');
  const scope = marketFact(dialog, 'Scope');
  const statement = marketCitation(dialog, 'rws_trainai.source.d_rws4');
  const statementUrl = 'https://www.rws.com/media/images/RWS-HY26-Results-Statement-Final-260610_tcm228-298858.pdf';
  await expect(scope).toHaveText('RWS Holdings plc group');
  const otherDates = dialog.locator('details').filter({ has: page.getByText('Other dates', { exact: true }) });
  await expect(otherDates.locator('button').filter({ hasText: '£99.4M' })).toHaveCount(0);
  await expect(period).toHaveText('H1 FY2026 · Oct 2025–Mar 2026');
  await expect(statement.getByRole('link')).toHaveAttribute('href', statementUrl);
  await openDisclosure(dialog.getByText('Other business scopes', { exact: true }));
  await dialog.getByRole('button', { name: /Generate segment.*H1 FY2026.*£99\.4M/ }).press('Enter');
  await expect(dialog.locator('.bh-value')).toHaveText(/^£99\.4M\s*Reported$/);
  await expect(scope).toHaveText('Generate segment · Includes TrainAI and Content Technology');
  await expect(period).toHaveText('H1 FY2026 · Oct 2025–Mar 2026');
  await expect(statement.getByRole('link')).toHaveAttribute('href', statementUrl);
  await expect(statement).toContainText('Published 11 Jun 2026');
  await openDisclosure(dialog.getByText('Caveats and source wording', { exact: true }));
  await expect(dialog.getByText(/^Research grade A:/)).toBeVisible();
});

test('Market retains exact reporting days for micro1 and Snorkel', async ({ page }) => {
  await openMarket(page);
  const chart = await marketChart(page, 'annualized_revenue');
  for (const [metric, company, day] of [
    ['micro1.metric.oct14-q3-run-rate', 'micro1', '12 Oct 2026'],
    ['snorkel_ai.metric.major-growth_metrics-0', 'Snorkel AI', '22 Sep 2026'],
  ]) {
    await page.getByRole('combobox', { name: 'Reporting period & scope' }).selectOption('');
    const figure = chart.locator(`[data-bh-observation="${metric}"]`);
    await expect(figure).toHaveAccessibleName(new RegExp(`${company}.*Reporting day ${day}`));
    await figure.press('Enter');
    await expect(marketFact(page.getByRole('dialog', { name: company }), 'Reporting day')).toHaveText(day);
    await closeMarketEvidence(page);
  }
});

test('Market distinguishes the July expert payout snapshot from the March reporting day', async ({ page }) => {
  await openMarket(page);
  const row = await marketMatrixRow(page, 'Mercor');
  const july = row.getByRole('button', { name: /^> \$4M\b/ });
  await expect(july).toHaveText(/grade B.*paid in one day/);
  await july.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Mercor' });
  await expect(marketFact(dialog, 'Snapshot')).toHaveText(/^21 Jul 2026(?: snapshot)?$/);
  await closeMarketEvidence(page);

  const chart = await marketChart(page, 'daily_expert_payouts');
  const march = chart.locator('[data-bh-observation="refresh.mercor.march-2026-daily-payouts"]');
  await march.press('Enter');
  await expect(dialog.locator('.bh-value')).toHaveText(/^> \$2M\s*Reported$/);
  await expect(marketFact(dialog, 'Reporting day')).toHaveText(/^3 Mar 2026$/);
  await expect(marketFact(dialog, 'Source').getByRole('link', { name: /^Mercor / })).toHaveAttribute('href',
    'https://www.mercor.com/blog/organizing-human-intelligence-to-power-the-ai-economy/');
});
