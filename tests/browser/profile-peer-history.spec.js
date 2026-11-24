const { test, expect } = require('@playwright/test');

const mercorProfile = '/explore/#company/mercor';
const afterQueryHash = /#company\/afterquery$/;
const peerLink = page => page.locator('.profile-peers').getByRole('link', { name: 'AfterQuery', exact: true });

async function openPeer(peer) {
  await peer.evaluate(async link => {
    await document.fonts.ready;
    link.scrollIntoView({ block: 'center', behavior: 'instant' });
    link.focus({ preventScroll: true });
    link.addEventListener('click', () => { window.testPeerDepartureY = scrollY; }, { once: true });
  });
  await peer.press('Enter');
}

async function expectPeerReturn(page, peer) {
  await expect(peer).toBeFocused();
  await expect(peer).toBeInViewport({ ratio: 1 });
  await expect.poll(() => page.evaluate(() => Math.abs(scrollY - window.testPeerDepartureY))).toBeLessThan(2);
}

test('Back to the profile peer link restores its open archive and reading position', async ({ page }) => {
  await page.goto(mercorProfile);
  const archive = page.locator('.profile-evidence');
  const funding = archive.locator('#profile-financing');
  const peer = peerLink(page);
  await expect(archive).toHaveJSProperty('open', false);
  await archive.locator(':scope > summary').press('Enter');
  await funding.locator(':scope > summary').press('Enter');
  await expect(funding).toHaveJSProperty('open', true);

  await openPeer(peer);
  await expect(page).toHaveURL(afterQueryHash);
  await expect(page.locator('[data-profile-company="afterquery"] .profile-tabs')).toBeVisible();
  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(/#company\/mercor$/);
  await expect(archive).toHaveJSProperty('open', true);
  await expect(funding).toHaveJSProperty('open', true);
  await expectPeerReturn(page, peer);

  await page.goForward({ waitUntil: 'commit' });
  await expect(page).toHaveURL(afterQueryHash);
  await expect(archive).toHaveJSProperty('open', false);
  await page.goBack({ waitUntil: 'commit' });
  await expectPeerReturn(page, peer);

  // A new history entry with the same URL has no peer opener.
  await page.evaluate(() => { location.hash = '#company/afterquery'; });
  await expect(page.getByRole('heading', { name: 'AfterQuery', exact: true })).toBeFocused();
  await page.goBack({ waitUntil: 'commit' });
  await expect(page.getByRole('heading', { name: 'Mercor', exact: true })).toBeFocused();
  await expect(archive).toHaveJSProperty('open', false);
});

test('Back during a peer request preserves a shared Paid work section and its open terms', async ({ page }) => {
  let release, markRequested, markContinued;
  const gate = new Promise(resolve => { release = resolve; });
  const requested = new Promise(resolve => { markRequested = resolve; });
  const continued = new Promise(resolve => { markContinued = resolve; });
  await page.route('**/presentation/company-afterquery.*.json', async route => {
    markRequested();
    await gate;
    try { await route.continue(); }
    finally { markContinued(); }
  });
  try {
    await page.goto(mercorProfile + '/work');
    const work = page.locator('#profile-pane-work');
    const terms = work.locator('details.w4-details').first();
    const peer = peerLink(page);
    await expect(work).toBeVisible();
    await terms.locator(':scope > summary').press('Enter');
    await expect(terms).toHaveJSProperty('open', true);

    await openPeer(peer);
    await requested;
    await expect(page.locator('[data-profile-company="afterquery"][data-profile-loading]')).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(/#company\/mercor\/work$/);
    await expect(work).toBeVisible();
    await expect(terms).toHaveJSProperty('open', true);
    await expect(terms.locator(':scope > :not(summary)').first()).toBeVisible();
    await expectPeerReturn(page, peer);
    release();
    await continued;
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await expectPeerReturn(page, peer);
  } finally {
    release();
  }
});
