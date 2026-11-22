const { test, expect } = require('@playwright/test');

const listingsURL = '/work/?pay=hourly&sort=hourly';
const compareURL = `${listingsURL}&view=compare`;
const firstRole = 'afterquery.work.world-models';
const firstRoleTitle = 'AfterQuery · World Models Machine Learning Expert · Application access unconfirmed';
const firstRoleRate = '$150–$200 / hour';

const compareLink = page => page.getByRole('link', { name: 'Compare results', exact: true });
const compareHeading = page => page.getByRole('heading', { name: 'Compare paid work results', exact: true });
const matchingRecords = page => page.getByRole('region', { name: 'Matching work records', exact: true });
const listingIDs = page => page.locator('.work-page-list [data-work-route]:visible')
  .evaluateAll(cards => cards.map(card => card.dataset.workRoute));

async function expectSavedCriteria(page) {
  const filters = page.locator('[data-work-filters]');
  await expect(filters.locator('summary')).toHaveText('Filters (2)');
  await expect(filters.locator('select[name=pay] option:checked')).toHaveText('Hourly');
  await expect(filters.locator('select[name=sort] option:checked')).toHaveText('Top listed pay/hr');
}

async function expectUnclipped(locator, { text = true, minimumSize = 0 } = {}) {
  const problems = await locator.evaluate((element, { text, minimumSize }) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const boxes = text ? [...range.getClientRects()] : [element.getBoundingClientRect()];
    if (!boxes.length) return ['No rendered text'];
    return boxes.flatMap(({ left, top, right, bottom, width, height }) => {
      const hit = document.elementFromPoint(left + width / 2, top + height / 2);
      if (left < -0.5 || top < -0.5 || right > innerWidth + 0.5 || bottom > innerHeight + 0.5
          || !element.contains(hit) || width < minimumSize || height < minimumSize) {
        return [{ left, top, right, bottom, width, height, hit: hit?.tagName, viewport: [innerWidth, innerHeight] }];
      }
      return [];
    });
  }, { text, minimumSize });
  expect(problems, `Visible and unobscured ${await locator.innerText()}`).toEqual([]);
}

async function checkArrivalAndBack(page, activate, { keyboard }) {
  await page.goto(listingsURL);
  const compare = compareLink(page);
  await expect(compare).toHaveAttribute('href', compareURL);
  await page.evaluate(() => document.fonts.ready);
  const ids = await listingIDs(page);
  const scroll = await page.evaluate(() => window.scrollY);

  await activate(compare);
  await expect(page).toHaveURL(compareURL);
  await expect(compareHeading(page)).toBeFocused();
  await page.evaluate(() => document.fonts.ready);

  const rows = matchingRecords(page).locator('[data-compare-route]');
  expect(await rows.evaluateAll(items => items.map(row => row.dataset.compareRoute))).toEqual(ids);
  const row = rows.first();
  await expect(row).toHaveAttribute('data-compare-route', firstRole);
  const title = row.getByRole('rowheader', { name: firstRoleTitle, exact: true });
  const rate = row.getByText(firstRoleRate, { exact: true });
  await expectUnclipped(title);
  await expectUnclipped(rate);
  const back = page.getByRole('link', { name: 'Back to listings', exact: true });
  await expect(back).toHaveAttribute('href', listingsURL);
  await expectUnclipped(back, { text: false, minimumSize: 44 });
  await expectSavedCriteria(page);

  if (keyboard) {
    await page.keyboard.press('Tab');
    await expect(matchingRecords(page)).toBeFocused();
  }

  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(listingsURL);
  await expect(compare).toBeFocused();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(scroll);
  await expectSavedCriteria(page);
  expect(await listingIDs(page)).toEqual(ids);
}

test('native Work Compare opens on the first full result from the keyboard at 1024×600', async ({ page, hasTouch }) => {
  test.skip(hasTouch, 'Checks the desktop keyboard sequence');
  await page.setViewportSize({ width: 1024, height: 600 });
  await checkArrivalAndBack(page, async compare => {
    for (let i = 0; i < 30 && !await compare.evaluate(link => link === document.activeElement); i++) {
      await page.keyboard.press('Tab');
    }
    await expect(compare).toBeFocused();
    await page.keyboard.press('Enter');
  }, { keyboard: true });
});

test('native Work Compare opens on the first full result from touch at 320×720', async ({ page, hasTouch }) => {
  test.skip(!hasTouch, 'Checks touch activation on a narrow phone');
  await page.setViewportSize({ width: 320, height: 720 });
  await checkArrivalAndBack(page, compare => compare.tap(), { keyboard: false });
});

test('a directly opened native Work Compare URL leaves initial focus and scroll alone', async ({ page, hasTouch }) => {
  await page.setViewportSize(hasTouch ? { width: 320, height: 720 } : { width: 1024, height: 600 });
  await page.goto(compareURL);
  await expect(compareHeading(page)).toBeVisible();
  const row = matchingRecords(page).locator('[data-compare-route]').first();
  await expect(row).toHaveAttribute('data-compare-route', firstRole);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator('body')).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expectSavedCriteria(page);
});
