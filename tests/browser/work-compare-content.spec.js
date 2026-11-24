const { test, expect } = require('@playwright/test');

test('native Work Compare preserves labeled fields and full-size actions', async ({ page, hasTouch }) => {
  await page.setViewportSize(hasTouch ? { width: 320, height: 720 } : { width: 1440, height: 900 });
  await page.goto('/work/');
  const compareLink = page.getByRole('link', { name: 'Compare results', exact: true });
  await expect(compareLink).toBeVisible();
  const cardIds = await page.locator('.work-page-list [data-work-route]')
    .evaluateAll(cards => cards.map(card => card.dataset.workRoute));
  expect(cardIds).toHaveLength(136);
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
    const values = cell => [...cell.querySelectorAll('dd')].map(text);
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
      const place = text(card.querySelector('.work-place'));
      const details = [place, ...conditionFields, text(card.querySelector('.work-reviewed'))].filter(Boolean);
      const [identityCell, payCell, detailCell] = row.cells;
      const identity = ['.work-company', 'h3', '.work-status'].map(selector => text(card.querySelector(selector)))
        .filter(Boolean).join(' · ');
      const differences = [
        ['identity', identityCell.innerText, identity],
        ['pay', values(payCell), pay],
        ['location and terms', values(detailCell), details],
        ['detail labels', [...detailCell.querySelectorAll('dt')].map(text), [place && 'Location', 'Terms and review'].filter(Boolean)],
        ['action', link(detailCell.querySelector('a')), link(nativeAction)],
      ].filter(([, actual, expected]) => !equal(actual, expected));
      return differences.length ? [{ id, fields: differences.map(([field]) => field) }] : [];
    });
  });
  expect(mismatches).toEqual([]);

  const g2i = rows.filter({ has: page.getByRole('link', { name: /Read role details.*G2i/ }) });
  const labels = g2i.getByRole('term');
  await expect(labels).toHaveText(['Pay', 'Location', 'Terms and review']);
  expect(await labels.evaluateAll(terms => terms.every(term => term.offsetWidth > 1))).toBe(hasTouch);
  const action = g2i.getByRole('link', { name: /Read role details.*G2i/ });
  await action.scrollIntoViewIfNeeded();
  expect(await action.evaluate(link => {
    const { left, width, height, bottom } = link.getBoundingClientRect();
    return width >= 44 && height >= 44 && link.contains(document.elementFromPoint(left + width / 2, bottom - 2));
  })).toBe(true);
  expect(await compare.evaluate(box => box.scrollWidth <= box.clientWidth)).toBe(true);

  await expect(compare.getByRole('cell', { name: /Contract work Schedule conflict\..*Six months Experience writing content/ }))
    .toHaveCount(1);
  await expect(compare.getByRole('cell', { name: /Up to \$150 \/ hour Rates vary by expertise/ })).toHaveCount(1);
});
