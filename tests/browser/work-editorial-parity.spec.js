const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

const role = 'ooak.work.data-quality-specialist';
const yearlyStaff = 'bespoke_labs.work.mts-post-training';
const monthlyStaff = 'afterquery.work.software-engineering-intern';
const pastStaff = 'apto.work.ai-data-research-engineer';
const employerListing = 'https://ooakdata.com/careers?job_id=114405#job';
const originalPosting = 'https://www.ycombinator.com/companies/ooak-data/jobs/Gr7Gc1x-data-quality-specialist';
const applicationLink = 'https://www.workatastartup.com/jobs/114405';
const signInLink = 'https://www.workatastartup.com/application?signup_job_id=114405';
const applicationStatus = 'Application link returned 404';
const security = 'afterquery.work.senior-software-engineer-security-infrastructure';
const people = 'afterquery.work.people-programs-lead';
const operations = 'afterquery.work.business-operations-generalist';
const associate = 'afterquery.work.sales-operations-associate';
const engagement = 'afterquery.work.engagement-manager';
const shopping = 'terac.work.ai-evaluator-shopping-assistant';
const closedTerac = 'terac.work.rl-environment-creation';
const rlScenarios = 'terac.work.ml-scenarios';
const rlScenariosStatus = 'Closed · employer confirmed';
const rlScenariosDescription = 'https://terac.com/opportunities/gHZD5v2UVnpSQZv5';
const rlScenariosOriginal = 'https://jobs.ashbyhq.com/terac/9f8d7438-ffd8-42be-b169-a46437154c79/';

const nativeCards = '.work-page-list [data-work-route]';
const exploreCards = '#work-cards [data-work-route]';
const orderedIds = locator => locator.evaluateAll(cards => cards.map(card => card.dataset.workRoute));
const recordFor = (page, selector, id = role) => page.locator(`${selector}[data-work-route="${id}"]`);

async function noScriptWork(browser, baseURL, check) {
  const context = await browser.newContext({ baseURL, javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto('/work/');
    return await check(page);
  } finally {
    await context.close();
  }
}

async function downloadRows(page) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download CSV', exact: true }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe('sciencetostartup-current-work-results.csv');
  const parsed = execFileSync('python3', ['-c', [
    'import csv, json, sys',
    'with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:',
    '    print(json.dumps(list(csv.DictReader(f))))',
  ].join('\n'), await download.path()], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  return JSON.parse(parsed);
}

test('native Work keeps the open terms and record order when filters load late', async ({ page }) => {
  // Hold the bundle while exercising the native controls without advancing its watchdog.
  await page.clock.install({ time: 0 });
  await page.clock.pauseAt(60_000);
  let resume;
  const delayed = new Promise(resolve => { resume = resolve; });
  await page.route('**/js/work.*.js', async route => {
    await delayed;
    await route.continue();
  });
  try {
    await page.goto('/work/', { waitUntil: 'domcontentloaded' });
    const before = await orderedIds(page.locator(nativeCards));
    const first = recordFor(page, nativeCards, before[0]);
    const terms = first.locator('.work-terms summary');
    await terms.press('Enter');
    await expect(first.locator('.work-terms')).toHaveJSProperty('open', true);
    await expect(terms).toBeFocused();
    await expect(page.locator('[data-work-compare]')).toBeHidden();
    resume();
    await expect(page.getByRole('link', { name: 'Compare results', exact: true })).toBeVisible();
    await page.clock.resume();
    expect(await orderedIds(page.locator(nativeCards))).toEqual(before);
    await expect(first.locator('.work-terms')).toHaveJSProperty('open', true);
    await expect(terms).toBeFocused();
  } finally {
    resume();
  }
});

const cases = [
  { name: 'all records', criteria: {}, includes: [role, yearlyStaff, monthlyStaff, pastStaff], excludes: [] },
  { name: 'yearly on-site or hybrid staff listings', criteria: { kind: 'named', type: 'employment', pay: 'yearly', arrangement: 'onsite' },
    includes: [role, yearlyStaff, security], excludes: [monthlyStaff, pastStaff, people, engagement] },
  { name: 'yearly on-site or hybrid other company jobs', criteria: { kind: 'outside', type: 'employment', pay: 'yearly', arrangement: 'onsite' },
    includes: [operations, associate], excludes: [security, people, engagement] },
  { name: 'yearly remote staff listings', criteria: { kind: 'named', type: 'employment', pay: 'yearly', arrangement: 'remote' },
    includes: [yearlyStaff], excludes: [role, monthlyStaff, pastStaff] },
  { name: 'past records', criteria: { kind: 'closed' }, includes: [pastStaff, people, closedTerac, rlScenarios],
    excludes: [role, yearlyStaff, monthlyStaff, security, shopping] },
];

for (const { name, criteria, includes, excludes } of cases) {
  test(`Work cards, Compare and both CSV downloads agree for ${name}`, async ({ browser, page, baseURL }, testInfo) => {
    const search = new URLSearchParams(criteria).toString();
    if (!search) test.slow(); // The full directory opens every lazy group before downloading.
    const staticGroups = await noScriptWork(browser, baseURL, async fallback => {
      await expect(fallback.locator('[data-work-native-fallback]')).toBeVisible();
      const groups = await fallback.locator('[data-work-group]').evaluateAll(sections => Object.fromEntries(
        sections.map(section => [section.dataset.workGroup,
          [...section.querySelectorAll('[data-work-route]')].map(card => card.dataset.workRoute)]),
      ));
      const total = Object.values(groups).flat().length;
      await expect(fallback.locator('[data-work-count]')).toHaveText(new RegExp(`^${total} records\\b`));
      await expect(fallback.locator('.work-page-counts')).toHaveText(new RegExp(`^${groups.named.length} named listings\\b`));
      return groups;
    });

    await page.goto(search ? `/work/?${search}` : '/work/');
    const compareLink = page.getByRole('link', { name: 'Compare results', exact: true });
    await expect(compareLink).toBeVisible();
    const kindLabel = { outside: 'Non-training jobs', closed: 'Past & reference' }[criteria.kind];
    if (kindLabel) await expect(page.locator('[data-work-filters] select[name="kind"] option:checked')).toHaveText(kindLabel);
    const chosen = `${nativeCards}:not([hidden])`;
    const ids = await orderedIds(page.locator(chosen));
    const nativeLabel = await page.locator('[data-work-count]').innerText();
    const recordCount = `${ids.length} ${search ? 'matching ' : ''}${ids.length === 1 ? 'record' : 'records'}`;
    expect(nativeLabel).toBe(search ? recordCount : `${recordCount}, including career pages and past listings`);
    expect(new Set(ids).size).toBe(ids.length);
    const staticIds = criteria.kind ? staticGroups[criteria.kind] : Object.values(staticGroups).flat();
    if (!search) expect(ids).toEqual(staticIds);
    else if (criteria.type) expect(staticIds).toEqual(expect.arrayContaining(ids));
    else expect([...ids].sort()).toEqual([...staticIds].sort());
    if (criteria.kind === 'closed') {
      await expect(recordFor(page, chosen, rlScenarios).locator('.work-status')).toHaveText(rlScenariosStatus);
    }

    await compareLink.click();
    await expect(page.getByRole('region', { name: 'Matching work records' })).toBeVisible();
    await expect(page.locator('[data-work-count]')).toHaveText(nativeLabel);
    const compared = await page.locator('[data-compare-route]').evaluateAll(rows => rows.map(row => row.dataset.compareRoute));
    expect(compared).toEqual(ids);
    if (criteria.kind === 'closed') {
      await expect(page.locator(`[data-compare-route="${rlScenarios}"] th`))
        .toHaveText(`Terac · ML Engineer, RL Scenarios · ${rlScenariosStatus}`);
    }
    const nativeCsv = await downloadRows(page);
    expect(nativeCsv.map(row => row.route_id)).toEqual(ids);

    await page.locator('[data-work-explore]').click();
    await expect(page).toHaveURL(`/explore/#work${search ? `?${search}` : ''}`);
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    if (kindLabel) {
      await expect(page.locator('#work-kind option:checked')).toHaveText(kindLabel);
      const group = criteria.kind === 'outside' ? '#work-outside' : '#work-other';
      await expect(page.locator(`${group} > summary`)).toContainText(kindLabel);
    }
    const unopened = page.locator('#work-cards [data-w4-routes]').locator('xpath=../summary');
    while (await unopened.count()) await unopened.first().click();
    const exploreLabel = await page.locator('#work-count').innerText();
    const explore = await orderedIds(page.locator(exploreCards));
    const exploreCsv = await downloadRows(page);
    const named = ids.filter(id => staticGroups.named.includes(id)).length;
    const programs = ids.filter(id => staticGroups.programs.includes(id)).length;
    const countParts = [`${ids.length} ${ids.length === 1 ? 'record' : 'records'}`];
    if (named) countParts.push(`${named} ${named === 1 ? 'listing' : 'listings'}`);
    if (programs) countParts.push(`${programs} ${programs === 1 ? 'program' : 'programs'}`);
    expect(exploreLabel).toBe(countParts.join(' · '));
    expect(explore).toEqual(ids);
    expect(exploreCsv).toEqual(nativeCsv);
    if (criteria.kind === 'closed') {
      const exported = nativeCsv.find(row => row.route_id === rlScenarios);
      expect(exported).toMatchObject({ availability: rlScenariosStatus });
      expect(JSON.parse(exported.original_url_details)).toMatchObject({
        archived_source_url: rlScenariosOriginal,
        application_url: null,
        current_action_purpose: 'career_board',
      });
      expect(JSON.parse(exported.review_evidence)).toMatchObject({
        page_check: { url: rlScenariosDescription, result: 'official_listing_closed', http_status: 200 },
        source_receipts: expect.arrayContaining([
          expect.objectContaining({ url: rlScenariosOriginal, checked_on: '2026-11-22', result: 'not_found', http_status: 404 }),
        ]),
      });
    }
    if (!search) {
      const exported = nativeCsv.find(row => row.route_id === engagement);
      expect(exported).toMatchObject({
        advertised_pay: '$225,000–$450,000 annual salary field (conflicting)',
        availability: 'Pay conflict',
        pay_unit: 'conflicting',
      });
      expect(exported.pay_qualification).toMatch(/\$300,000–\$450,000.*50\/50.*\$150,000–\$225,000/);
    }
    await testInfo.attach('ordered-route-ids', {
      contentType: 'application/json', body: JSON.stringify({
        criteria, nativeLabel, exploreLabel, native: ids, compare: compared, explore,
        nativeCsv: nativeCsv.map(row => row.route_id), exploreCsv: exploreCsv.map(row => row.route_id),
        ...(!search && { staticGroups }),
      }, null, 2),
    });
    for (const id of includes) expect.soft(ids).toContain(id);
    for (const id of excludes) expect.soft(ids).not.toContain(id);
  });
}

async function expectSources(card, termsSummary) {
  await termsSummary.click();
  const terms = termsSummary.locator('..');
  await expect(terms.getByRole('link', { name: 'Original unavailable posting' })).toHaveAttribute('href', originalPosting);
  await expect(terms.getByRole('link', { name: /Data Quality Specialist · employer listing/ })).toHaveAttribute('href', employerListing);
  await expect(terms.getByRole('link', { name: /Employer’s application link · page not found/ })).toHaveAttribute('href', applicationLink);
  await expect(terms.getByRole('link', { name: /Separate application URL · sign-in required/ })).toHaveAttribute('href', signInLink);
  await expect(terms.getByText(/OOAK still lists this role\..*404 Page not found.*empty 406.*Y Combinator sign-in.*original YC posting also returned 404/)).toBeVisible();
  await expect(card.getByRole('link', { name: /^Apply(?: now| for| on| through|$)/i })).toHaveCount(0);
  return terms;
}

test('OOAK’s exact employer listing and application checks keep separate statuses', async ({ browser, page, baseURL }, testInfo) => {
  test.setTimeout(60_000);
  await noScriptWork(browser, baseURL, async fallback => {
    const card = recordFor(fallback, nativeCards);
    await expect(card.locator('xpath=ancestor::*[@data-work-group]')).toHaveAttribute('data-work-group', 'named');
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute('data-arrangements', 'hybrid');
    await expect(card.locator('.work-status')).toHaveText(applicationStatus);
    await expect(card.getByRole('link', { name: /^Read employer listing/ })).toHaveAttribute('href', employerListing);
    const terms = await expectSources(card, card.locator('.work-terms > summary'));
    const linkedApplication = terms.getByRole('link', { name: /Employer’s application link · page not found/ }).locator('..');
    await expect(linkedApplication.getByText(/Application check · .*HTTP 404 · Not found/)).toBeVisible();
    await expect(linkedApplication.getByText(/Application check · .*HTTP 406 · Unavailable/)).toBeVisible();
    const separateApplication = terms.getByRole('link', { name: /Separate application URL · sign-in required/ }).locator('..');
    await expect(separateApplication.getByText(/Application check · .*HTTP 200 · Blocked/)).toBeVisible();
    await expect(terms.getByText(/(?:Historical observation|Exact historical posting).*HTTP 404/).first()).toBeVisible();
  });

  const criteria = 'kind=named&type=employment&pay=yearly&arrangement=onsite';
  await page.goto(`/work/?${criteria}`);
  const card = recordFor(page, nativeCards);
  await expect(card).toBeVisible();
  await expect(card.locator('.work-status')).toHaveText(applicationStatus);
  await expect(card.getByRole('link', { name: /^Read employer listing/ })).toHaveAttribute('href', employerListing);
  await page.getByRole('link', { name: 'Compare results', exact: true }).click();

  const row = page.locator(`[data-compare-route="${role}"]`);
  await expect(row).toBeVisible();
  await expect(row.getByRole('rowheader')).toHaveText(`Ooak Data · Data Quality Specialist · ${applicationStatus}`);
  await expect(row.getByRole('link', { name: /^Read employer listing/ })).toHaveAttribute('href', employerListing);
  await expect(row.getByRole('link', { name: /^Apply/i })).toHaveCount(0);
  const nativeCsv = (await downloadRows(page)).find(row => row.route_id === role);

  await page.locator('[data-work-explore]').click();
  await expect(page).toHaveURL(`/explore/#work?${criteria}`);
  const explore = recordFor(page, exploreCards);
  await expect(explore.locator('.w4-status-listed')).toHaveText(applicationStatus);
  await expect(explore.getByRole('link', { name: /^Read employer listing/ })).toHaveAttribute('href', employerListing);
  await expectSources(explore, explore.locator('.w4-details > summary'));

  const rowCsv = (await downloadRows(page)).find(row => row.route_id === role);
  expect(rowCsv).toEqual(nativeCsv);
  const review = JSON.parse(rowCsv.review_evidence);
  const urls = JSON.parse(rowCsv.original_url_details);
  await testInfo.attach('ooak-browser-export', {
    contentType: 'application/json', body: JSON.stringify({ ...rowCsv, review_evidence: review, original_url_details: urls }, null, 2),
  });
  expect(rowCsv).toMatchObject({
    opportunity_kind: 'named_listing', engagement_type: 'employment', arrangement_filter: 'onsite', arrangements: 'hybrid',
    availability: applicationStatus, original_application_url: '', current_action_url: employerListing, current_action_label: 'Read employer listing',
  });
  expect(urls).toMatchObject({
    source_url: employerListing, application_url: null, recorded_url_purpose: 'description', legacy_url_purpose: null,
    current_action_purpose: 'description', archived_source_url: originalPosting,
    checked_destinations: [{ url: applicationLink, purpose: 'application' }, { url: signInLink, purpose: 'application' }],
  });
  expect(urls).not.toHaveProperty('application_check');
  expect(rowCsv.source_urls.split(' | ')).toEqual(expect.arrayContaining([originalPosting, employerListing, applicationLink, signInLink]));
  expect(review).toMatchObject({
    status: 'listed',
    http_check: { final_url: originalPosting, date: '2026-10-28', http_status: 200, result: 'reachable' },
    page_check: { url: employerListing, date: '2026-11-22', http_status: 200, result: 'readable' },
    application_check: {
      url: applicationLink, final_url: applicationLink, date: '2026-11-22', http_status: 404, result: 'not_found',
      retrieval_reason: 'http_not_found', rendered_observation: { url: applicationLink, http_status: 404 },
    },
    application_checks: [
      { url: applicationLink, date: '2026-11-22', http_status: 406, result: 'unavailable', retrieval_reason: 'http_not_acceptable' },
      { url: signInLink, date: '2026-11-22', http_status: 200, result: 'blocked', retrieval_reason: 'sign_in',
        rendered_observation: { url: 'https://account.ycombinator.com/', http_status: 200 } },
    ],
  });
  expect(review.source_receipts).toEqual(expect.arrayContaining([
    expect.objectContaining({ url: originalPosting, checked_on: '2026-11-08', http_status: 200, result: 'readable' }),
    expect.objectContaining({ url: originalPosting, checked_on: '2026-11-22', http_status: 404, result: 'not_found' }),
    expect.objectContaining({ url: applicationLink, checked_at: '2026-11-22T12:56:45Z', http_status: 404, result: 'not_found' }),
    expect.objectContaining({ url: applicationLink, checked_at: '2026-11-22T12:57:37Z', http_status: 406, result: 'unavailable' }),
    expect.objectContaining({ url: signInLink, checked_at: '2026-11-22T11:56:48Z', http_status: 200, result: 'blocked' }),
  ]));
});

const ashby = 'https://jobs.ashbyhq.com/AfterQuery/';
const afterqueryBoard = 'https://api.ashbyhq.com/posting-api/job-board/AfterQuery?includeCompensation=true';
const peopleDescription = ashby + '2ba013e1-d254-4436-afd7-19d0b451424f';
const shoppingStart = 'https://terac.com/apply/start/58b90b6b-a97d-478e-817c-6666a230e213';
const reconciled = [
  { id: security, jobId: '99afbbe0-5ad1-4f25-a00a-049f14428ac6',
    pay: '$200,000–$350,000 annual salary', status: 'Listed again', note: /labeled fields and a Submit Application control/ },
  { id: operations, jobId: '30b3dddf-9804-4e80-8fc6-2e2b2a511ca7', pay: '$160,000–$250,000 annual salary' },
  { id: associate, jobId: 'd1236ef8-0030-4cbf-bbec-052c6eed971f', pay: '$145,000–$175,000 annual salary' },
  { id: engagement, jobId: '79185014-f08f-4520-923f-e6bb67d31973',
    pay: 'Rate conflict', status: 'Pay conflict' },
  { id: people, pay: '$160K–$230K salary band + equity', status: 'Past listing · page unavailable',
    action: ['Browse current company careers', 'https://www.afterquery.com/careers'],
    secondary: ['Original unavailable posting', peopleDescription + '/application'],
    note: /original role description and application returned HTTP 404.*Employer closure remains unconfirmed/ },
  { id: shopping, pay: '$30 / hour', status: 'Application start available',
    action: ['Read role details', 'https://terac.com/opportunities/TKd76RUIQxw3wy-x'],
    secondary: ['Open application start', shoppingStart], note: /Continue with LinkedIn.*Screening and submission were unverified/ },
  { id: closedTerac, pay: '$90 / hour', status: 'Closed',
    action: ['Read archived listing', 'https://terac.com/opportunities/KZwfXOQhfpdjGT8k'],
    note: /This listing has closed/ },
  { id: rlScenarios, pay: '$90 / hour', status: rlScenariosStatus,
    action: ['Browse current company careers', 'https://jobs.ashbyhq.com/terac'],
    note: /Terac’s description for this role says “This listing has closed\.” The original Ashby posting returned HTTP 404/ },
];

test('Reconciled employer listings render scoped pay and exact source actions in Work and Explore', async ({ browser, page, baseURL }) => {
  test.slow();
  const checkCards = async (page, native) => {
    for (const { id, jobId, pay, status, note, action, secondary } of reconciled) {
      await test.step(id, async () => {
        const card = recordFor(page, native ? nativeCards : exploreCards, id);
        if (native) {
          const group = card.locator('xpath=ancestor::details[@data-work-group and not(@open)]/summary');
          if (await group.count()) await group.click();
        }
        await expect(card).toBeVisible();
        const paySelector = native ? '.work-pay > strong' : '.w4-pay > strong, .w4-compact-pay > strong';
        await expect(card.locator(paySelector)).toHaveText(pay);
        if (status) await expect(card.getByText(status, { exact: true }).first()).toBeVisible();
        const compact = card.locator('.w4-compact-toggle:not([open]) > summary');
        if (await compact.count()) await compact.click();
        const primary = card.locator(native ? '.work-listing-action > a' : '.w4-open');
        const [label, url] = action || ['Read role details', ashby + jobId];
        await expect(primary).toHaveAccessibleName(new RegExp('^' + label));
        await expect(primary).toHaveAttribute('href', url);

        const details = card.locator(native ? '.work-terms' : '.w4-details');
        const summary = details.locator(':scope > summary');
        await expect(summary).toBeVisible();
        await summary.click();
        const linkedAction = secondary || (jobId && ['View official application', url + '/application']);
        if (linkedAction) {
          const [label, url] = linkedAction;
          const links = native ? details : details.locator('.w4-secondary-actions');
          await expect(links.getByRole('link', { name: new RegExp('^' + label) })).toHaveAttribute('href', url);
        }
        if (note) await expect(details.getByText(note).first()).toBeVisible();
        if (jobId) {
          await expect(details.locator(`a[href="${afterqueryBoard}"]`)).toBeVisible();
          await expect(card.locator(paySelector).locator('..')).not.toContainText('Pay period not stated.');
        }
        if (id === people && native) {
          for (const url of [peopleDescription, peopleDescription + '/application']) {
            await expect(details.locator(`a[href="${url}"]`).locator('..')).toContainText('HTTP 404');
          }
        }
        if (id === rlScenarios) {
          const issuer = details.locator(`a[href="${rlScenariosDescription}"]`).locator('..');
          const original = details.locator(`a[href="${rlScenariosOriginal}"]`).locator('..');
          await expect(issuer.getByRole('link')).toBeVisible();
          await expect(original.getByRole('link')).toBeVisible();
          if (native) {
            await expect(issuer.locator('q')).toHaveText('This listing has closed');
            await expect(issuer).toContainText('HTTP 200');
            await expect(original).toContainText('22 Nov 2026 · HTTP 404');
          } else {
            await expect(issuer.locator(`[data-work-source="${rlScenarios}.issuer-closure-2026-11-22"]`))
              .toContainText('Checked 22 Nov 2026 · Terac archived role description and closure notice');
            await expect(original.locator(`[data-work-source="${rlScenarios}.ashby-recheck-2026-11-22"]`))
              .toContainText('Checked 22 Nov 2026 · Original Ashby posting recheck');
          }
        }
        if (id === engagement) {
          await expect(card.getByText(/\$225,000–\$450,000.*\$300,000–\$450,000.*\$150,000–\$225,000/).first()).toBeVisible();
        }
        if (id === shopping) await expect(card.getByText(/20\+ h(?:ours)?\/week/).first()).toBeVisible();
      });
    }
  };
  await noScriptWork(browser, baseURL, page => checkCards(page, true));

  await page.goto('/explore/#work');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  const unopened = page.locator('#work-cards [data-w4-routes]').locator('xpath=../summary');
  while (await unopened.count()) await unopened.first().click();
  await checkCards(page, false);
});
