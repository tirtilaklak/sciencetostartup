const { test, expect } = require('@playwright/test');

test('Mercor Paid work renders before its initial tabs scroll without shifting the footer', async ({ page, browserName, isMobile }, testInfo) => {
  test.skip(browserName !== 'chromium' || !isMobile, 'Mobile Chromium exposes layout-shift attribution');
  await page.setViewportSize({ width: 412, height: 823 });

  await page.addInitScript(() => {
    const timing = window.profileTiming = { frames: [], shifts: [] };
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        timing.shifts.push({ time: entry.startTime, score: entry.value, hadRecentInput: entry.hadRecentInput,
          footer: entry.sources.some(source => source.node?.matches?.('.explore-layout > footer')) });
      }
    }).observe({ type: 'layout-shift', buffered: true });

    const sample = time => {
      const work = Boolean(document.querySelector('#profile-pane-work:not([hidden]) #profile-work'));
      const top = scrollY;
      const previous = timing.frames.at(-1);
      if (previous?.work !== work || previous?.top !== top) timing.frames.push({ time, work, top });
      if (!work || !top) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });

  let releaseEvidence;
  const evidenceGate = new Promise(resolve => { releaseEvidence = resolve; });
  const isEvidence = url => /\/presentation\/company-mercor\.[^/]+\.json$/.test(new URL(url).pathname);
  await page.route(url => isEvidence(url), async route => { await evidenceGate; await route.continue(); });
  try {
    const evidenceResponse = page.waitForResponse(response => isEvidence(response.url()));
    await page.goto('/explore/#company/mercor/work', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
    await expect.poll(() => page.locator('.profile-introduction img').evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
    expect(await page.evaluate(() => scrollY)).toBe(0);
    releaseEvidence();
    expect((await evidenceResponse).ok()).toBe(true);
    await expect(page.getByRole('tab', { name: 'Paid work', exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('#profile-work')).toBeInViewport();
    await expect.poll(() => page.evaluate(() => window.profileTiming.frames.at(-1)?.top)).toBeGreaterThan(0);
    const timing = await page.evaluate(async () => {
      // A shift is delivered asynchronously after the rendering update.
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return window.profileTiming;
    });
    await testInfo.attach('profile-timing', { body: JSON.stringify(timing), contentType: 'application/json' });
    expect(timing.frames.find(frame => frame.work)).toMatchObject({ top: 0 });
    expect(timing.shifts.filter(shift => shift.footer)).toEqual([]);
    await expect(page.locator('body')).toBeFocused();
  } finally {
    releaseEvidence();
  }
});

test('focus established as the Paid work pane mounts cancels the pending scroll', async ({ page }) => {
  await page.addInitScript(() => {
    const observer = new MutationObserver(() => {
      if (!document.querySelector('#profile-work')) return;
      observer.disconnect();
      document.querySelector('.skip').focus({ preventScroll: true });
    });
    observer.observe(document, { childList: true, subtree: true });
  });
  await page.goto('/explore/#company/mercor/work', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('link', { name: 'Skip to content', exact: true })).toBeFocused();
  const top = await page.evaluate(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return scrollY;
  });
  expect(top).toBe(0);
});
