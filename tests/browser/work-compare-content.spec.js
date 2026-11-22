const { test, expect } = require('@playwright/test');

test('native Work Compare preserves separate pay and terms fields for every record', async ({ page }) => {
  await page.goto('/work/');
  const compareLink = page.getByRole('link', { name: 'Compare results', exact: true });
  await expect(compareLink).toBeVisible();
  const cardIds = await page.locator('.work-page-list [data-work-route]')
    .evaluateAll(cards => cards.map(card => card.dataset.workRoute));
  expect(cardIds).toHaveLength(135);
  const named = page.locator('[data-work-group="named"] .work-listing-conditions > :first-child').first();
  await expect(named).not.toContainText('Specific listing');
  const duplicatedDates = await page.locator('.work-reviewed:visible > [hidden]').evaluateAll(notes => notes.map(note => ({
    hidden: !note.getClientRects().length,
    day: note.textContent.trim().match(/^\(as of (.+)\)$/)?.[1],
    visibleReview: note.parentElement.innerText,
  })));
  for (const { hidden, day, visibleReview } of duplicatedDates) {
    expect(hidden).toBe(true);
    expect(day).toBeTruthy();
    expect(visibleReview).toContain(day);
    expect(visibleReview).not.toContain('as of');
  }
  await compareLink.click();

  const compare = page.getByRole('region', { name: 'Matching work records' });
  await expect(compare.getByRole('columnheader')).toHaveText([
    'Listing or program', 'Recorded pay', 'Location and terms',
  ]);
  const rows = compare.locator('[data-compare-route]');
  await expect(rows).toHaveCount(cardIds.length);
  expect(await rows.evaluateAll(rows => rows.map(row => row.dataset.compareRoute))).toEqual(cardIds);

  const mismatches = await rows.evaluateAll(rows => {
    const cards = new Map([...document.querySelectorAll('.work-page-list [data-work-route]')]
      .map(card => [card.dataset.workRoute, card]));
    const text = node => node?.textContent.trim() || '';
    const lines = cell => cell.innerText.split(/\n+/).map(line => line.trim()).filter(Boolean);
    const link = anchor => anchor && [text(anchor), anchor.getAttribute('href'), anchor.getAttribute('aria-label')];
    const equal = (actual, expected) => JSON.stringify(actual) === JSON.stringify(expected);
    const sharedKinds = { named: 'Specific listing', programs: 'Expert network or program', boards: 'Career page' };
    return rows.flatMap(row => {
      const id = row.dataset.compareRoute;
      const card = cards.get(id);
      const nativePay = card.querySelector('.work-pay');
      const pay = nativePay ? [...nativePay.children].map(text) : ['Pay not listed'];
      if (nativePay?.classList.contains('work-historical-pay')) {
        pay.splice(0, 2, pay.slice(0, 2).join(' '));
      }
      const nativeAction = card.querySelector('.work-listing-action a');
      const conditionFields = [...card.querySelector('.work-listing-conditions').children].map(text);
      const kind = sharedKinds[card.closest('[data-work-group]').dataset.workGroup];
      if (kind) conditionFields[0] = kind + ' · ' + conditionFields[0];
      const details = [
        text(card.querySelector('.work-place')),
        ...conditionFields,
        text(card.querySelector('.work-reviewed')),
        text(nativeAction),
      ].filter(Boolean);
      const [identityCell, payCell, detailCell] = row.cells;
      const identity = ['.work-company', 'h3', '.work-status'].map(selector => text(card.querySelector(selector)))
        .filter(Boolean).join(' · ');
      const differences = [
        ['identity', identityCell.innerText, identity],
        ['pay', lines(payCell), pay],
        ['location and terms', lines(detailCell), details],
        ['action', link(detailCell.querySelector('a')), link(nativeAction)],
      ].filter(([, actual, expected]) => !equal(actual, expected));
      return differences.length ? [{ id, fields: differences.map(([field]) => field) }] : [];
    });
  });
  expect(mismatches).toEqual([]);

  await expect(compare.getByRole('cell', { name: /Contract work Schedule conflict\..*Six months Experience writing content/ }))
    .toHaveCount(1);
  await expect(compare.getByRole('cell', { name: /Up to \$150 \/ hour Rates vary by expertise/ })).toHaveCount(1);
});
