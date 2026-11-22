const { test, expect } = require('@playwright/test');
const { readFile } = require('node:fs/promises');

const claimId = 'snorkel_ai.claim.major-growth_metrics-0-metric';
const articleTitle = 'Data 2.0 and the research era of AI data';
const articleUrl = 'https://snorkel.ai/blog/data-2-0-and-the-research-era-of-ai-data/';
const citations = [
  { id: 'snorkel_ai.source.audit-s5', checked: '22 Nov 2026', archivedTitle: 'Series E', archivedCheck: '2026-10-12' },
  { id: 'snorkel_ai.source.oct14-006107ac93e3', checked: '28 Oct 2026', archivedTitle: articleTitle, archivedCheck: '2026-10-14' },
];

test('the Snorkel claim pairs same-URL checks by source ID and preserves the archive', async ({ page, context }, info) => {
  await page.goto(`/explore/#company/snorkel_ai/claim/${claimId}`);
  const dialog = page.locator('#evidence-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.evidence-metric-value')).toHaveText('> $375M USD');
  const rows = dialog.locator('.sources-list > li');
  await expect(rows).toHaveCount(citations.length);
  for (const [index, citation] of citations.entries()) {
    const row = rows.nth(index);
    await expect(row).toHaveAttribute('data-source-id', citation.id);
    const link = row.getByRole('link');
    await expect(link).toHaveAccessibleName(`${articleTitle} (opens in a new tab)`);
    await expect(link).toHaveAttribute('href', articleUrl);
    const metadata = row.locator('p').first();
    await expect(metadata).toContainText(`Source checked ${citation.checked}`);
    await expect(metadata).not.toContainText(citations[1 - index].checked);
  }
  const current = await rows.evaluateAll(items => items.map(row => ({ id: row.dataset.sourceId, text: row.innerText })));

  const downloads = await context.newPage();
  await downloads.goto('/explore/#downloads');
  await expect(downloads.locator('html')).toHaveAttribute('data-view-state', 'ready');
  const [download] = await Promise.all([
    downloads.waitForEvent('download'),
    downloads.locator('#download-json').click(),
  ]);
  const archive = JSON.parse(await readFile(await download.path(), 'utf8'));
  expect(archive.claims.find(claim => claim.id === claimId).source_ids).toEqual(citations.map(citation => citation.id));
  const archived = citations.map(citation => archive.sources.find(source => source.id === citation.id));
  for (const [index, citation] of citations.entries()) {
    expect(archived[index]).toMatchObject({ id: citation.id, url: articleUrl, title: citation.archivedTitle, accessed_on: citation.archivedCheck });
  }
  await info.attach('snorkel-claim-sources.json', { body: JSON.stringify({ current, archived }, null, 2), contentType: 'application/json' });
});
