const { test, expect } = require('@playwright/test');
const { createHash } = require('node:crypto');
const AxeBuilder = require('@axe-core/playwright').default;
const { evidenceURL } = require('./research-ledger');

// Serializing the complete evidence DOM for each trace step exceeds the test
// timeout independently of page behavior. Retain screenshots, network and code.
test.use({ trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true } });

const reportPath = '/research/state-of-ai-data-labs/';
const datedReportPath = '/research/editions/2026-11-12/';
const chapterIds = ['executive-assessment', 'weekly-developments', 'market-structure',
  'technical-landscape', 'provider-dossiers', 'datasets-and-benchmarks',
  'human-expertise-and-operations', 'commercial-evidence', 'governance',
  'buyer-decision-guides', 'research-outlook', 'methods-and-appendices'];
const readingPages = chapterIds.map((id, index) => index ? reportPath + 'chapters/' + id + '/' : reportPath);
const publicPages = ['/', '/daily/', '/daily/2026-11-16/', '/research/', ...readingPages, '/research/data/', '/review/', '/company/scale_ai/'];

async function openRecordCorrection(page, report) {
  await page.goto(report);
  const evidence = page.locator('.r-paragraph-citations a').first();
  const path = await evidence.getAttribute('href');
  const fragment = decodeURIComponent(path.split('#')[1]);
  const id = fragment.slice('assertion-'.length);
  await evidence.press('Enter');
  const correction = page.locator('[id=' + JSON.stringify(fragment) + '] .r-record-correction');
  await correction.getByText('Request a correction', { exact: true }).press('Enter');
  const contact = correction.getByRole('link', { name: 'Continue to private email' });
  const contactURL = new URL(await contact.getAttribute('href'), page.url());
  const edition = contactURL.searchParams.get('edition');
  expect(edition).toMatch(/^research-/);
  expect(contactURL.pathname + contactURL.hash).toBe('/method/#corrections');
  expect(contactURL.searchParams.get('record')).toBe(path);
  expect(contactURL.searchParams.get('correction')).toBe(id);
  return { correction, contact, contactURL, edition, id, path };
}

test.beforeEach(async ({ page, request }, info) => {
  const response = await request.get('/manifest.json');
  expect(response.ok()).toBeTruthy();
  const manifest = await response.json();
  await info.attach('artifact-identity.json', {
    body: Buffer.from(JSON.stringify({ buildId: manifest.build_id, editorialReleaseId: manifest.editorial_release_id, datasetVersion: manifest.dataset_version })),
    contentType: 'application/json',
  });
  const runtimeErrors = [];
  page.on('pageerror', error => runtimeErrors.push(error.message));
  info._researchRuntimeErrors = runtimeErrors;
});

test.afterEach(async ({}, info) => {
  expect(info._researchRuntimeErrors || [], 'Unexpected browser runtime errors').toEqual([]);
});

test.describe('research without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('correction evidence links have separate tap targets on narrow screens', async ({ page }) => {
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 720 });
      await page.goto('/research/corrections/');
      const evidence = page.locator('.r-correction-evidence').filter({ has: page.locator('li + li') }).first();
      await evidence.scrollIntoViewIfNeeded();
      const boxes = await evidence.getByRole('link').evaluateAll(links =>
        links.map(link => link.getBoundingClientRect().toJSON()));
      expect(boxes.length).toBeGreaterThan(1);
      for (const [index, box] of boxes.entries()) {
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.left).toBeGreaterThanOrEqual(0);
        expect(box.right).toBeLessThanOrEqual(width);
        if (index) expect(box.top - boxes[index - 1].bottom).toBeGreaterThanOrEqual(8);
      }
    }
  });

  test('hub opens all twelve complete native chapters without JavaScript', async ({ page }) => {
    await page.goto('/research/');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI data research');
    const sections = await page.locator('main [aria-labelledby="browse"], main .r-operating-status')
      .evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-labelledby') || 'edition update'));
    expect(sections[0]).toBe('browse');
    await expect(page.locator('.r-chapter-list a')).toHaveCount(12);
    await page.getByRole('link', { name: 'Read the report →', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(reportPath + '$'));
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
    await expect(page.locator('.r-report-body > .r-chapter:not(#cite)')).toHaveCount(1);
    const chapters = await page.locator('.r-toc ol a').evaluateAll(links => links.map(link => ({ href: link.getAttribute('href'), title: link.textContent })));
    expect(chapters).toHaveLength(12);
    expect(chapters.map(chapter => chapter.href)).toEqual(readingPages.map((path, index) => index ? path + '#' + chapterIds[index] : path));
    for (const [index, chapter] of chapters.entries()) {
      await page.goto(chapter.href);
      const path = readingPages[index];
      await expect(page.locator('[id=' + JSON.stringify(chapterIds[index]) + ']')).toBeVisible();
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://sciencetostartup.com' + path);
      expect(await page.locator('.r-report-body .r-paragraph p').count(), chapter.title).toBeGreaterThan(0);
      const contents = page.getByRole('navigation', { name: 'Report chapters' });
      if (index) {
        const toggle = page.locator('details.r-chapter-index > summary');
        await expect(toggle).toBeVisible();
        await expect(contents).toBeHidden();
        await toggle.press('Enter');
        await expect(contents).toBeVisible();
      }
      await expect(contents.locator('[aria-current="page"]')).toHaveAttribute('href', path);
      if (index) await expect(page.locator('.r-reader-pagination [rel="prev"]')).toHaveAttribute('href', readingPages[index - 1]);
      if (index + 1 < chapters.length) await expect(page.locator('.r-reader-pagination [rel="next"]')).toHaveAttribute('href', readingPages[index + 1]);
    }
    await page.goto(reportPath + '#methods-and-appendices');
    await expect(page.locator('#methods-and-appendices')).toBeInViewport();
    await page.locator('.r-toc ol a').last().click();
    await expect(page).toHaveURL(new URL(readingPages.at(-1) + '#methods-and-appendices', page.url()).href);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Methods');
  });

  test('dated reading names the current report link and keeps chapter navigation in the edition', async ({ page }) => {
    test.setTimeout(45_000);
    await page.setViewportSize({ width: 320, height: 844 });
    const chapter = datedReportPath + 'chapters/technical-landscape/';
    for (const entry of [chapter, datedReportPath + 'data/']) {
      await page.goto(entry);
      if (entry === chapter) {
        const contents = page.getByRole('navigation', { name: 'Report chapters' });
        await expect(contents.getByRole('link', { name: '1. Executive assessment', exact: true }))
          .toHaveAttribute('href', datedReportPath);
      }
      const current = page.getByRole('navigation', { name: 'Research', exact: true })
        .getByRole('link', { name: 'Current report', exact: true });
      await expect(current).toHaveText('Current report');
      await expect(current).toHaveAttribute('href', reportPath);
      for (let step = 0; step < 24; step++) {
        await page.keyboard.press('Tab');
        if (await current.evaluate(link => link === document.activeElement)) break;
      }
      await expect(current).toBeFocused();
      await expect(current).toBeInViewport();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(new URL(reportPath, page.url()).href);
      await page.goBack();
      await expect(page).toHaveURL(new URL(entry, page.url()).href);
    }
  });

  test('reverse keyboard focus reaches the visible final Technical citation from #cite', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const report of [reportPath, datedReportPath]) {
      const entry = report + 'chapters/technical-landscape/#cite';
      await page.goto(entry);
      await expect(page.locator('#cite:target')).toBeInViewport();
      const citation = page.locator('.r-reader-chapter-content .r-paragraph-citations a').last();
      for (let step = 0; step < 7; step++) {
        await page.keyboard.press('Shift+Tab');
        if (await citation.evaluate(link => link === document.activeElement)) break;
      }
      await expect(citation).toBeFocused();
      await expect(citation).toBeInViewport({ ratio: 0.95 });
      const href = await citation.getAttribute('href');
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(new URL(href, page.url()).href);
      await page.goBack();
      await expect(page).toHaveURL(new URL(entry, page.url()).href);
      await expect(citation).toBeInViewport({ ratio: 0.95 });
    }
  });

  test('report evidence opens the assertion and its source ledger entry', async ({ page }) => {
    await page.goto(reportPath);
    const evidence = page.locator('.r-paragraph-citations a').first();
    const assertionHref = await evidence.getAttribute('href');
    expect(assertionHref).toMatch(/^\/research\/data\/assertions\/[0-9a-f]\/#assertion-/);
    expect(assertionHref).toBe(evidenceURL('assertion', decodeURIComponent(assertionHref.split('#')[1]).slice('assertion-'.length)));
    await evidence.click();
    const assertion = page.locator('[id=' + JSON.stringify(decodeURIComponent(assertionHref.split('#')[1])) + ']');
    await expect(assertion).toBeVisible();
    const sourceLink = assertion.locator('a[href*="#source-"]').first();
    const sourceHref = await sourceLink.getAttribute('href');
    await sourceLink.click();
    expect(sourceHref).toMatch(/^\/research\/data\/sources\/[0-9a-f]\/#source-/);
    expect(sourceHref).toBe(evidenceURL('source', decodeURIComponent(sourceHref.split('#')[1]).slice('source-'.length)));
    const source = page.locator('[id=' + JSON.stringify(decodeURIComponent(sourceHref.split('#')[1])) + ']');
    await expect(source).toBeVisible();
    await expect(source.locator('h3 a')).toHaveAttribute('href', /^https:\/\//);
    for (const label of ['Publisher', 'Published', 'Captured', 'Version', 'Locator']) {
      await expect(source.locator('dt').filter({ hasText: new RegExp('^' + label + '$') })).toBeVisible();
    }
    await expect(source).toContainText('Assertion-specific review is recorded separately');
  });

  test('current and dated records keep usable private drafts and direct public links without scripts', async ({ page }) => {
    for (const report of [reportPath, datedReportPath]) {
      const { correction, contact, contactURL, edition, id, path } = await openRecordCorrection(page, report);
      const permalink = 'https://sciencetostartup.com' + path;
      const issue = new URL(await correction.getByRole('link', { name: 'Start a public GitHub correction' }).getAttribute('href'));
      expect(issue.hostname).toBe('github.com');
      expect(issue.searchParams.get('template')).toBe('correction.yml');
      expect(issue.searchParams.get('target')).toBe([edition, id, permalink].join(' · '));
      await correction.getByText('Copy the email draft', { exact: true }).press('Enter');
      const subject = correction.getByRole('textbox', { name: 'Subject' });
      const message = correction.getByRole('textbox', { name: 'Message' });
      await expect(subject).toHaveValue('ScienceToStartup correction · ' + id);
      await expect(subject).toHaveAttribute('readonly', '');
      await expect(message).toHaveAttribute('readonly', '');
      expect((await message.inputValue()).split('\n').slice(0, 3)).toEqual([
        'Edition: ' + edition, 'Stable record ID: ' + id, 'Record URL: ' + permalink,
      ]);
      await expect(correction.locator('a[href^="mailto:"]')).toHaveCount(0);
      await contact.press('Enter');
      await expect(page).toHaveURL(contactURL.href);
      const approvedContact = page.locator('#corrections');
      await expect(approvedContact.getByRole('link', { name: 'Email a correction' })).toHaveAttribute('href', /^mailto:/);
      await expect(approvedContact).toContainText('Email address');
    }
  });

  test('data page exposes working graph exports and citation downloads', async ({ page, request }) => {
    await page.goto('/research/data/');
    const firstFiles = await page.locator('[aria-labelledby="downloads"] .r-downloads a')
      .evaluateAll(links => links.slice(0, 3).map(link => link.getAttribute('href')));
    expect(firstFiles).toEqual([
      '/publication/clean-dataset.json',
      '/publication/clean-dataset.csv',
      '/publication/clean-dataset.sqlite',
    ]);
    const exports = [
      '/research/exports/research-graph.json',
      '/research/exports/research-graph.sqlite',
      '/research/exports/research-exports-manifest.json',
    ];
    for (const href of exports) {
      const link = page.locator('a[href=' + JSON.stringify(href) + ']');
      await expect(link).toBeVisible();
      const response = await request.get(await link.getAttribute('href'));
      expect(response.ok(), href).toBeTruthy();
      const body = await response.body();
      expect(body.length, href).toBeGreaterThan(100);
      if (href.endsWith('.sqlite')) expect(body.subarray(0, 16).toString()).toBe('SQLite format 3\u0000');
      else expect(() => JSON.parse(body.toString()), href).not.toThrow();
    }
    const statusResponse = await request.get('/publication/package-status.json');
    expect(statusResponse.ok()).toBeTruthy();
    const status = await statusResponse.json();
    const published = status.archive === 'published';
    const metadataResponse = await request.get('/publication/current-metadata.json');
    expect(metadataResponse.ok()).toBeTruthy();
    const metadata = await metadataResponse.json();
    expect(metadata.version).toBe(status.release_id);
    let doi;
    if (published) {
      const receipt = status.archive_receipt;
      expect(receipt).toMatchObject({ status: 'published', verified: true, anonymous_verified: true,
        api_origin: 'https://zenodo.org', environment: 'production', release_id: status.release_id,
        artifact_sha256: status.archive_sha256 });
      expect(Number.isSafeInteger(receipt.record_id) && receipt.record_id > 0).toBe(true);
      doi = '10.5281/zenodo.' + receipt.record_id;
      expect(receipt.doi).toBe(doi);
      expect(receipt.reserved_doi).toBe(doi);
      expect(receipt.deposition_id).toBe(receipt.record_id);
      expect(receipt.concept_doi).toMatch(/^10\.5281\/zenodo\.[1-9][0-9]*$/);
      expect(receipt.concept_doi).not.toBe(doi);
      expect(receipt.record_url).toBe('https://zenodo.org/records/' + receipt.record_id);
      expect(metadata).toMatchObject({ status: 'published', doi, url: receipt.record_url });
      if (status.release_id === 'research-2026-11-12.1') expect(doi).toBe('10.5281/zenodo.24249277');
    } else {
      expect(metadata.doi).toBeUndefined();
    }
    const manifestResponse = await request.get('/publication/MANIFEST.json');
    expect(manifestResponse.ok()).toBeTruthy();
    const manifestBody = await manifestResponse.body();
    expect(createHash('sha256').update(manifestBody).digest('hex')).toBe(status.manifest_sha256);
    const frozenManifest = JSON.parse(manifestBody.toString());
    const formats = [
      ['BibTeX', 'citation.bib', /@\w+\s*\{/, text => text.match(/^\s*doi\s*=\s*[{\"]([^}\"]+)[}\"]/mi)?.[1]],
      ['RIS', 'citation.ris', /^TY\s+-/m, text => text.match(/^DO\s+-\s*(\S+)/m)?.[1]],
      ['CSL JSON', 'citation.csl.json', /"title"\s*:/, text => JSON.parse(text).DOI],
      ['CITATION.cff', 'CITATION.cff', /["']?cff-version["']?\s*:/, text => JSON.parse(text).doi],
    ];
    for (const [name, filename, format, registeredDOI] of formats) {
      const href = '/publication/' + (published ? 'current-' : '') + filename;
      await expect(page.locator('#citation').getByRole('link', { name, exact: true })).toHaveAttribute('href', href);
      const response = await request.get(href);
      expect(response.ok(), name).toBeTruthy();
      const content = await response.text();
      expect(content, name).toMatch(format);
      expect(content, name).toContain('State of AI Data Labs and Human Feedback');
      expect(registeredDOI(content), name + ' registered DOI').toBe(doi);
      // Frozen preparation citations retain their original bytes and reserved
      // DOI note; they never acquire a registered DOI field after publication.
      const frozenResponse = await request.get('/publication/' + filename);
      expect(frozenResponse.ok(), name + ' frozen file').toBeTruthy();
      const frozen = await frozenResponse.body();
      expect(frozen.length).toBe(frozenManifest.files[filename].bytes);
      expect(createHash('sha256').update(frozen).digest('hex')).toBe(frozenManifest.files[filename].sha256);
      expect(registeredDOI(frozen.toString()), name + ' frozen registered DOI').toBeUndefined();
    }
    await expect(page.locator('#sources')).toBeVisible();
    const sourceParts = page.locator('section[aria-labelledby="sources"] .r-ledger-parts a');
    await expect(sourceParts).toHaveCount(16);
    await sourceParts.first().click();
    expect(await page.locator('.r-source').count()).toBeGreaterThan(0);
  });
});

test('a fresh Method tab prepares the original edition and record in private email', async ({ page }) => {
  const fresh = await page.context().newPage();
  for (const report of [reportPath, datedReportPath]) {
    const { contactURL, edition, id, path } = await openRecordCorrection(page, report);
    await fresh.goto(contactURL.href);
    const record = fresh.locator('#correction-record a');
    await expect(record).toBeVisible();
    await expect(record).toHaveText(id);
    await expect(record).toHaveAttribute('href', path);
    const email = fresh.locator('#correction-email');
    const draft = new URL(await email.getAttribute('href'));
    expect(draft.protocol).toBe('mailto:');
    expect(draft.searchParams.get('subject')).toBe('ScienceToStartup correction · ' + id);
    expect(draft.searchParams.get('body').split('\r\n').slice(0, 3)).toEqual([
      'Edition: ' + edition, 'Stable record ID: ' + id, 'Record URL: https://sciencetostartup.com' + path,
    ]);
    await fresh.reload();
    await expect(email).toHaveAttribute('href', draft.href);

    contactURL.searchParams.set('record', 'https://example.invalid/research/');
    await fresh.goto(contactURL.href);
    await expect(record).toBeHidden();
    const generic = new URL(await email.getAttribute('href'));
    expect(generic.pathname).toBe(draft.pathname);
    expect(generic.searchParams.get('subject')).toBe('ScienceToStartup correction');
  }
});

test('home search finds human feedback research and opens its native report', async ({ page }) => {
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await page.locator('#home-search-input').fill('human feedback');
  const result = page.locator('#home-search-results a[href=' + JSON.stringify(reportPath) + ']');
  await expect(result).toContainText('State of AI Data Labs and Human Feedback');
  await result.click();
  await expect(page).toHaveURL(new RegExp(reportPath + '$'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
});

test('home search preserves the native static company destination', async ({ page }) => {
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await page.locator('#home-search-input').fill('Scale AI');
  const company = page.locator('#home-search-results a[href="/company/scale_ai/"]');
  await expect(company).toContainText('Scale AI');
  await company.click();
  await expect(page).toHaveURL(/\/company\/scale_ai\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Scale AI');
});

test('global search offers a native research link and respects opening it in a new tab', async ({ page, context }) => {
  await page.goto('/explore/#companies');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await page.locator('#site-search-open').click();
  await page.locator('#site-search-input').fill('human feedback');
  const result = page.locator('#site-search-results a[href=' + JSON.stringify(reportPath) + ']');
  await expect(result).toHaveAttribute('role', 'option');
  await expect(result).toContainText('State of AI Data Labs and Human Feedback');
  const opened = context.waitForEvent('page');
  await result.click({ modifiers: ['ControlOrMeta'] });
  const tab = await opened;
  await tab.waitForLoadState();
  await expect(tab).toHaveURL(new RegExp(reportPath + '$'));
  await expect(tab.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
  await expect(page).toHaveURL(/\/explore\/#companies$/);
  await expect(page.locator('#site-search')).toBeVisible();
  await tab.close();
  await result.click();
  await expect(page).toHaveURL(new RegExp(reportPath + '$'));
});

for (const surface of ['home', 'site']) {
  test(surface + ' search opens a complete chapter with native new-tab, Enter and history behavior', async ({ page, context }) => {
    const start = surface === 'home' ? '/' : '/explore/#companies';
    const chapter = readingPages[3];
    await page.goto(start);
    if (surface === 'site') await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await page.locator('#' + surface + '-search-open').click();
    await page.locator('#' + surface + '-search-input').fill('technical landscape');
    const result = page.locator('#' + surface + '-search-results a[href=' + JSON.stringify(chapter) + ']');
    await expect(result).toContainText('Technical landscape');
    const opened = context.waitForEvent('page');
    await result.click({ modifiers: ['ControlOrMeta'] });
    const tab = await opened;
    await tab.waitForLoadState();
    expect(new URL(tab.url()).pathname).toBe(chapter);
    await expect(tab.getByRole('heading', { level: 1 })).toContainText('Technical landscape');
    await tab.close();
    expect(new URL(page.url()).pathname + new URL(page.url()).hash).toBe(start);
    await result.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(chapter + '$'));
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Technical landscape');
    expect(await page.locator('.r-report-body .r-paragraph').count()).toBeGreaterThan(0);
    await page.goBack();
    expect(new URL(page.url()).pathname + new URL(page.url()).hash).toBe(start);
  });
}

test('public pages retain keyboard skip navigation into the main content', async ({ page, browserName }) => {
  // Safari's default keyboard setting visits links with Option-Tab.
  const nextLink = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
  for (const path of publicPages) {
    await page.goto(path);
    await page.keyboard.press(nextLink);
    // Inspect the focused native skip link itself; a page-wide role query walks
    // the complete evidence ledger before it can assert this one header link.
    const skip = page.locator('body > a.skip[href="#main"]');
    await expect(skip, path).toHaveRole('link');
    await expect(skip, path).toHaveAccessibleName('Skip to content');
    await expect(skip, path).toBeFocused();
    await expect(skip, path).toBeInViewport();
    await page.keyboard.press('Enter');
    await expect(page, path).toHaveURL(/#main$/);
    await page.keyboard.press(nextLink);
    expect(await page.evaluate(() => Boolean(document.activeElement.closest('main'))), path + ' skip must move subsequent keyboard focus into main').toBe(true);
  }
});

test('home search supports arrow selection and restores keyboard focus when closed', async ({ page }) => {
  await page.goto('/');
  const opener = page.locator('#home-search-open');
  await opener.focus();
  await page.keyboard.press('Enter');
  const input = page.locator('#home-search-input');
  await expect(input).toBeFocused();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await input.fill('human feedback');
  await input.press('ArrowDown');
  const selected = page.locator('#home-search-results [aria-selected="true"]');
  await expect(selected).toHaveCount(1);
  await expect(input).toHaveAttribute('aria-activedescendant', await selected.getAttribute('id'));
  await page.keyboard.press('Escape');
  await expect(page.locator('#home-search')).not.toBeVisible();
  await expect(opener).toBeFocused();
});

test('at 320 pixels the public header, navigation and page fit without horizontal overflow', async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 320, height: 720 });
  for (const path of publicPages) {
    await page.goto(path);
    const header = page.locator('body > header.site-header');
    await expect(header).toBeVisible();
    const menu = header.locator('details > summary');
    await expect(menu).toBeVisible();
    await menu.press('Enter');
    const nav = header.getByRole('navigation', { name: 'Main', exact: true });
    for (const name of ['Daily scan', 'Research', 'Companies', 'Paid work', 'About']) {
      const link = nav.getByRole('link', { name, exact: true });
      await expect(link, path).toBeVisible();
      const box = await link.boundingBox();
      expect(box.x, path + ' ' + name).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, path + ' ' + name).toBeLessThanOrEqual(320.5);
      expect(box.height, path + ' ' + name).toBeGreaterThanOrEqual(43.5);
    }
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    expect(dimensions.document, path).toBeLessThanOrEqual(dimensions.viewport + 1);
    expect(dimensions.body, path).toBeLessThanOrEqual(dimensions.viewport + 1);
  }
  // Advanced app flows stay available by hash; the primary site nav opens the native pages.
  for (const [name, target, heading] of [
    ['Daily scan', '/daily/', 'Daily scan'],
    ['Companies', '/companies/', 'AI data companies'],
    ['Paid work', '/work/', 'Paid work in AI training'],
    ['About', '/method/#about', 'About'],
  ]) {
    await page.goto('/explore/#companies');
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    const link = page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name, exact: true });
    await expect(link).toHaveAttribute('href', target);
    await link.click();
    await expect(page).toHaveURL(new URL(target, page.url()).href);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading);
  }
});

for (const path of publicPages) {
  test('no serious or critical accessibility violations on ' + path, async ({ page }, info) => {
    const started = Date.now();
    await page.goto(path);
    const nodes = await page.locator('*').count();
    const analyzing = Date.now();
    const result = await new AxeBuilder({ page }).analyze();
    await info.attach('axe-scan-metrics.json', { body: Buffer.from(JSON.stringify({ path, nodes,
      navigationMs: analyzing - started, analysisMs: Date.now() - analyzing,
      testBudgetMs: 30_000,
      fullPage: true, ruleExclusions: [] })), contentType: 'application/json' });
    expect(result.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
  });
}

// The complete ledger spans these bounded static documents. Audit every node
// and default Axe rule on every part, retaining the original severity gate.
for (const kind of ['assertions', 'sources']) {
  for (const bucket of '0123456789abcdef') {
    const path = '/research/data/' + kind + '/' + bucket + '/';
    test('ledger part ' + path + ' has no serious or critical accessibility violations', async ({ page }, info) => {
      await page.goto(path);
      const nodes = await page.locator('*').count();
      const started = Date.now();
      const result = await new AxeBuilder({ page }).analyze();
      await info.attach('axe-scan-metrics.json', { body: Buffer.from(JSON.stringify({ path, nodes,
        analysisMs: Date.now() - started, testBudgetMs: 30_000, fullPage: true, ruleExclusions: [],
        resultRules: Object.fromEntries(['violations', 'incomplete', 'passes', 'inapplicable'].map(kind =>
          [kind, result[kind].map(rule => rule.id)])) })), contentType: 'application/json' });
      expect(result.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
    });
  }
}
