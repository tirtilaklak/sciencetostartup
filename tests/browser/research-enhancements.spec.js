const { test, expect } = require('@playwright/test');
const { readFileSync, mkdtempSync, writeFileSync, rmSync } = require('node:fs');
const { resolve } = require('node:path');
const { tmpdir } = require('node:os');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { evidenceURL } = require('./research-ledger');

// Keep failure evidence without repeatedly serializing the full offline ledger.
test.use({ trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true } });

const reportPath = '/research/state-of-ai-data-labs/';
const categories = {
  papers: ['paper', 'paper_work', 'paper_version'],
  datasets: ['dataset', 'dataset_family', 'dataset_release'],
  benchmarks: ['benchmark', 'benchmark_family', 'benchmark_version'],
  workflows: ['workflow'],
};
const facets = ['domain', 'modality', 'workflow', 'expertise', 'origin', 'labels', 'oversight', 'delivery_model', 'data_purpose'];
const labels = { approved: 'Approved evidence', candidate: 'Candidate · review pending', historical: 'Historical record', excluded: 'Excluded from scope' };
const judgmentFields = {
  buyer_implication: 'Buyer implication', limitations: 'Limitations', confidence: 'Confidence',
  reasoning: 'Reasoning', what_would_change: 'What would change this assessment',
};
const text = value => Array.isArray(value) ? value.map(item => item.trim()).filter(Boolean).join('; ') : (value || '').trim();
const normalize = value => value.replace(/\s+/g, ' ').trim();
const selector = id => '[id=' + JSON.stringify(id) + ']';

async function getJSON(request, path) {
  const response = await request.get(path);
  expect(response.ok(), path).toBeTruthy();
  return response.json();
}

function values(entity, name) {
  if (name === 'status') return [entity.status || 'unknown'];
  if (name === 'type') return [entity.kind || 'unknown'];
  return [...new Set(entity.taxonomy?.[name] || [])].sort();
}

function matches(entity, filters) {
  const haystack = [entity.name, entity.id, ...(entity.aliases || []), ...Object.values(entity.identifiers || {})].join(' ').toLowerCase();
  return Object.entries(filters).every(([name, value]) => {
    if (!value) return true;
    if (name === 'q') return value.trim().toLowerCase().split(/\s+/).every(word => haystack.includes(word));
    return value === '__not_recorded__' ? values(entity, name).length === 0 : values(entity, name).includes(value);
  });
}

async function expectRecords(page, entities, filters = {}) {
  const expected = entities.filter(entity => matches(entity, filters)).map(entity => entity.id).sort();
  const visible = page.locator('[data-index-row]:visible');
  await expect(visible).toHaveCount(expected.length);
  expect((await visible.locator('th .r-record-id').allTextContents()).sort()).toEqual(expected);
  await expect(page.locator('[data-index-count]')).toHaveText(`${expected.length} of ${entities.length} records shown`);
  await expect(page.locator('[data-index-empty]')).toBeVisible({ visible: expected.length === 0 });
}

test.beforeEach(async ({ page, request }, info) => {
  const manifest = await getJSON(request, '/manifest.json');
  await info.attach('research-enhancements-artifact.json', {
    body: Buffer.from(JSON.stringify({ buildId: manifest.build_id, datasetVersion: manifest.dataset_version,
      editorialReleaseId: manifest.editorial_release_id, reportHtmlSHA256: manifest.sha256['research/state-of-ai-data-labs/index.html'] })),
    contentType: 'application/json',
  });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  info._researchEnhancementErrors = errors;
});

test.afterEach(async ({}, info) => {
  expect(info._researchEnhancementErrors || [], 'Unexpected browser runtime errors').toEqual([]);
});

for (const [category, kinds] of Object.entries(categories)) {
  test(`${category} filters combine search, review status and every available facet`, async ({ page, request }) => {
    const graph = await getJSON(request, '/research/exports/research-graph.json');
    const entities = graph.entities.filter(entity => kinds.includes(entity.kind));
    expect(entities.length, `${category} needs real records`).toBeGreaterThan(0);
    await page.goto(`/research/${category}/`);
    const form = page.getByRole('search', { name: 'Filter research records' });
    await expect(form).toBeVisible();
    await expect(page.locator('[data-index-count]')).toHaveAttribute('role', 'status');
    await expect(page.locator('[data-index-count]')).toHaveAttribute('aria-live', 'polite');
    await expectRecords(page, entities);

    const status = entities.some(entity => entity.status === 'candidate') ? 'candidate' : entities[0].status;
    await form.getByRole('combobox', { name: 'Review status', exact: true }).selectOption(status);
    await expectRecords(page, entities, { status });
    const target = entities.find(entity => entity.status === status);
    // An identifier searches one actual metadata record, including punctuation.
    await form.getByLabel('Search records', { exact: true }).fill(target.id.toUpperCase());
    await expectRecords(page, entities, { status, q: target.id.toUpperCase() });
    expect(new URL(page.url()).searchParams.get('q')).toBe(target.id.toUpperCase());
    await form.getByRole('button', { name: 'Clear filters', exact: true }).click();
    await expectRecords(page, entities);

    // Search terms are case insensitive and may appear in a different order.
    const words = entities.find(entity => entity.name.trim().split(/\s+/).length > 1)?.name.split(/\s+/).reverse().join(' ').toUpperCase() || target.id;
    await form.getByLabel('Search records', { exact: true }).fill(`  ${words}  `);
    await expectRecords(page, entities, { q: words });
    expect(new URL(page.url()).searchParams.get('q')).toBe(words);
    await form.getByRole('button', { name: 'Clear filters', exact: true }).click();

    const selects = await form.locator('select').evaluateAll(nodes => nodes.map(node => ({ name: node.name,
      options: Array.from(node.options, option => option.value) })));
    for (const { name, options } of selects) {
      const expected = [...new Set(entities.flatMap(entity => values(entity, name)))].sort();
      if (entities.some(entity => !values(entity, name).length)) expected.push('__not_recorded__');
      expect(options.filter(Boolean).sort(), `${category}/${name} options`).toEqual(expected.sort());
      for (const selected of [options.find(Boolean), ...(options.includes('__not_recorded__') ? ['__not_recorded__'] : [])]) {
        await form.locator(`select[name="${name}"]`).selectOption(selected);
        await expectRecords(page, entities, { [name]: selected });
        expect(new URL(page.url()).searchParams.get(name)).toBe(selected);
        await form.getByRole('button', { name: 'Clear filters', exact: true }).click();
      }
    }
    const facet = selects.find(item => facets.includes(item.name) && item.options.some(value => value && value !== '__not_recorded__'));
    expect(facet, `${category} must exercise a populated taxonomy facet`).toBeTruthy();
    const selected = facet.options.find(value => value && value !== '__not_recorded__');
    const combinedTarget = entities.find(entity => values(entity, facet.name).includes(selected));
    await form.locator(`select[name="${facet.name}"]`).selectOption(selected);
    await form.getByRole('combobox', { name: 'Review status', exact: true }).selectOption(combinedTarget.status);
    await form.getByLabel('Search records', { exact: true }).fill(combinedTarget.id);
    await expectRecords(page, entities, { [facet.name]: selected, status: combinedTarget.status, q: combinedTarget.id });

    await form.getByLabel('Search records', { exact: true }).fill('no-such-research-record-87e78d');
    await expectRecords(page, entities, { [facet.name]: selected, status: combinedTarget.status, q: 'no-such-research-record-87e78d' });
    await expect(page.locator('[data-index-empty]')).toContainText('Clear filters');
    await form.getByRole('button', { name: 'Clear filters', exact: true }).click();
    await expectRecords(page, entities);
    for (const input of await form.locator('input, select').all()) await expect(input).toHaveValue('');
    expect(new URL(page.url()).search).toBe('');
  });
}

test.describe('complete research tables without JavaScript', () => {
  test.use({ javaScriptEnabled: false });
  for (const [category, kinds] of Object.entries(categories)) {
    test(`${category} includes every record, status, type, taxonomy and evidence link`, async ({ page, request }) => {
      const graph = await getJSON(request, '/research/exports/research-graph.json');
      const entities = graph.entities.filter(entity => kinds.includes(entity.kind));
      await page.goto(`/research/${category}/?q=no-such-record&status=excluded`);
      await expect(page.locator('[data-index-controls]')).toBeHidden();
      await expect(page.locator('[data-index-row]')).toHaveCount(entities.length);
      await expect(page.locator('[data-index-row]:visible')).toHaveCount(entities.length);
      await expect(page.locator('[data-index-count]')).toHaveText(`${entities.length} records`);
      await expect(page.getByRole('table')).toHaveAccessibleName('Evidence records. Taxonomy on candidate records is provisional.');
      // JavaScript is disabled and all rows are already attached/visible. Read
      // every rendered cell once, then retain every per-record assertion below.
      // Hundreds of locator round trips otherwise consume the test deadline.
      const records = await page.locator('[data-index-row]').evaluateAll(rows => rows.map(row => {
        const header = row.querySelector('th');
        const evidence = row.querySelector('[data-label="Evidence"] a');
        return { id: row.querySelector('th .r-record-id')?.textContent,
          headerTag: header?.tagName, headerScope: header?.getAttribute('scope'), headerText: header?.textContent,
          review: row.querySelector('[data-label="Review"]')?.textContent,
          type: row.querySelector('[data-label="Type"]')?.textContent,
          taxonomy: row.querySelector('[data-label="Taxonomy"]')?.textContent,
          titleHref: row.querySelector('th a')?.getAttribute('href'),
          evidenceText: evidence?.textContent, evidenceHref: evidence?.getAttribute('href') };
      }));
      const rowHeaders = await page.getByRole('rowheader').evaluateAll(headers => headers.map(header => ({
        rowId: header.closest('[data-index-row]')?.querySelector('th .r-record-id')?.textContent,
        text: header.textContent })));
      for (const entity of entities) {
        const matching = records.filter(row => row.id === entity.id);
        expect(matching, entity.id).toHaveLength(1);
        const row = matching[0];
        expect({ tag: row.headerTag, scope: row.headerScope }, entity.id + ' native rowheader').toEqual({ tag: 'TH', scope: 'row' });
        const accessibleHeaders = rowHeaders.filter(header => header.rowId === entity.id);
        expect(accessibleHeaders, entity.id + ' accessible rowheader').toHaveLength(1);
        expect(normalize(accessibleHeaders[0].text), entity.id).toContain(normalize(entity.name));
        expect(normalize(row.review), entity.id).toContain(labels[entity.status]);
        expect(normalize(row.review), entity.id).toContain((entity.review_depth || '').replaceAll('_', ' '));
        expect(normalize(row.type), entity.id).toBe(entity.kind.replaceAll('_', ' '));
        const taxonomy = facets.filter(name => values(entity, name).length).map(name => `${name.replaceAll('_', ' ')}: ${values(entity, name).join(', ')}`).join('; ');
        expect(normalize(row.taxonomy), entity.id).toBe(taxonomy || 'Not recorded');
        const scope = new Set([entity.id]);
        if (['paper', 'paper_work', 'dataset', 'dataset_family', 'benchmark', 'benchmark_family'].includes(entity.kind)) {
          graph.entities.filter(item => item.parent_id === entity.id).forEach(item => scope.add(item.id));
        }
        const approved = graph.assertions.filter(assertion => assertion.status === 'approved' && (scope.has(assertion.subject_id) || scope.has(assertion.object_id)));
        const href = row.titleHref;
        expect(href).toMatch(new RegExp(`^/research/${category}/[^/#]+/$`));
        expect(normalize(row.evidenceText), entity.id).toBe(`${approved.length} approved assertions`);
        expect(row.evidenceHref, entity.id).toBe(href + '#approved-findings');
      }
      const first = page.locator('[data-index-row] th a').first();
      const href = await first.getAttribute('href');
      await first.click();
      expect(new URL(page.url()).pathname).toBe(href);
      await expect(page.locator('#approved-findings')).toBeAttached();
    });
  }
});

test('filter history restores controls and results while retaining unrelated query and fragment', async ({ page, request }) => {
  const graph = await getJSON(request, '/research/exports/research-graph.json');
  const entities = graph.entities.filter(entity => categories.papers.includes(entity.kind));
  const target = entities.find(entity => entity.status === 'approved' && values(entity, 'modality').length);
  expect(target).toBeTruthy();
  const initial = '/research/papers/?reader=history-check#main';
  await page.goto(initial);
  const form = page.locator('[data-index-controls]');
  await expect(form).toBeVisible();
  await form.locator('select[name="status"]').selectOption(target.status);
  await form.locator('input[name="q"]').fill(target.id);
  const first = page.url();
  await form.locator('select[name="modality"]').selectOption(values(target, 'modality')[0]);
  const second = page.url();
  await expectRecords(page, entities, { status: target.status, q: target.id, modality: values(target, 'modality')[0] });
  await page.goBack();
  await expect(page).toHaveURL(first);
  await expect(form.locator('select[name="modality"]')).toHaveValue('');
  await expect(form.locator('input[name="q"]')).toHaveValue(target.id);
  await expect(form.locator('select[name="status"]')).toHaveValue(target.status);
  await expectRecords(page, entities, { status: target.status, q: target.id });
  await page.goBack();
  expect(new URL(page.url()).pathname + new URL(page.url()).search + new URL(page.url()).hash).toBe(initial);
  await expectRecords(page, entities);
  await expect(form.locator('input[name="q"]')).toHaveValue('');
  await expect(form.locator('select[name="status"]')).toHaveValue('');
  await page.goForward();
  await expect(page).toHaveURL(first);
  await expectRecords(page, entities, { status: target.status, q: target.id });
  await page.goForward();
  await expect(page).toHaveURL(second);
  await page.reload();
  await expect(form.locator('select[name="modality"]')).toHaveValue(values(target, 'modality')[0]);
  await expectRecords(page, entities, { status: target.status, q: target.id, modality: values(target, 'modality')[0] });
  await form.getByRole('button', { name: 'Clear filters', exact: true }).click();
  expect(new URL(page.url()).search).toBe('?reader=history-check');
  expect(new URL(page.url()).hash).toBe('#main');
  await expectRecords(page, entities);
});

test('category title and evidence links retain native modifier and ordinary navigation', async ({ page, context }) => {
  await page.goto('/research/papers/?status=approved');
  const row = page.locator('[data-index-row]:visible').first();
  for (const link of [row.locator('th a'), row.locator('[data-label="Evidence"] a')]) {
    const href = await link.getAttribute('href');
    const original = page.url();
    const opened = context.waitForEvent('page');
    await link.click({ modifiers: ['ControlOrMeta'] });
    const tab = await opened;
    await tab.waitForLoadState();
    expect(new URL(tab.url()).pathname + new URL(tab.url()).hash).toBe(href);
    await expect(tab.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page).toHaveURL(original);
    await expect(page.locator('select[name="status"]')).toHaveValue('approved');
    await tab.close();
  }
  const href = await row.locator('th a').getAttribute('href');
  await row.locator('th a').click();
  expect(new URL(page.url()).pathname).toBe(href);
  await page.goBack();
  await expect(page).toHaveURL(/\/research\/papers\/\?status=approved$/);
  await expect(page.locator('select[name="status"]')).toHaveValue('approved');
});

test('home research search supports opening its native report in another tab', async ({ page, context }) => {
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await page.locator('#home-search-input').fill('human feedback');
  const link = page.locator('#home-search-results a[href=' + JSON.stringify(reportPath) + ']');
  await expect(link).toContainText('State of AI Data Labs and Human Feedback');
  const opened = context.waitForEvent('page');
  await link.click({ modifiers: ['ControlOrMeta'] });
  const tab = await opened;
  await tab.waitForLoadState();
  expect(new URL(tab.url()).pathname).toBe(reportPath);
  await expect(tab.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
  expect(new URL(page.url()).pathname).toBe('/');
  await expect(page.locator('#home-search-input')).toHaveValue('human feedback');
  await expect(page.locator('#home-search')).toBeVisible();
  await tab.close();
});

test.describe('legacy evidence remains independently readable', () => {
  test.use({ javaScriptEnabled: false });
  test('Scale appends approved evidence while preserving its historical profile and canonical data', async ({ page, request }) => {
    const graph = await getJSON(request, '/research/exports/research-graph.json');
    const scale = graph.entities.find(entity => entity.legacy_id === 'scale_ai');
    expect(scale).toBeTruthy();
    const approved = graph.assertions.filter(assertion => assertion.status === 'approved' && [assertion.subject_id, assertion.object_id].includes(scale.id));
    expect(approved.length).toBeGreaterThan(0);
    const canonical = JSON.parse(readFileSync(resolve('data/canonical.json'), 'utf8'));
    expect(await getJSON(request, '/research.json')).toEqual(canonical);
    expect(graph.canonical_dataset_version).toBe(canonical.dataset_version);
    const baseline = readFileSync(resolve('dist/company/scale_ai/index.html'), 'utf8');
    await page.goto('/company/scale_ai/');
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://sciencetostartup.com/company/scale_ai/');
    const preserved = await page.evaluate(baselineHTML => {
      const original = new DOMParser().parseFromString(baselineHTML, 'text/html');
      const actual = document.querySelector('main').cloneNode(true);
      original.querySelectorAll('#new-research-evidence').forEach(node => node.remove());
      actual.querySelectorAll('#new-research-evidence').forEach(node => node.remove());
      const compact = value => value.replace(/<!-- research-supplement:(?:start|end) -->/g, '').replace(/\s+/g, ' ').trim();
      const data = root => Array.from(root.querySelectorAll('script[type="application/ld+json"]'), node => JSON.parse(node.textContent));
      const stripPageModified = value => {
        if (Array.isArray(value)) return value.map(stripPageModified);
        if (!value || typeof value !== 'object') return value;
        return Object.fromEntries(Object.entries(value).filter(([key]) => !(key === 'dateModified' && ['WebPage', 'ProfilePage'].includes(value['@type'])))
          .map(([key, child]) => [key, stripPageModified(child)]));
      };
      return { expectedMain: compact(original.querySelector('main').innerHTML), actualMain: compact(actual.innerHTML),
        expectedMetadata: stripPageModified(data(original)), actualMetadata: stripPageModified(data(document)),
        lastMainChild: document.querySelector('main').lastElementChild.id };
    }, baseline);
    expect(preserved.actualMain, 'Historical prose, figures, source links and dates').toBe(preserved.expectedMain);
    expect(preserved.actualMetadata, 'Historical organization metadata').toEqual(preserved.expectedMetadata);
    expect(preserved.lastMainChild).toBe('new-research-evidence');
    const supplement = page.locator('#new-research-evidence');
    await expect(supplement.getByRole('heading', { level: 2 })).toHaveText('New research evidence');
    await expect(supplement).toContainText('supplement the historical profile');
    await expect(supplement).toContainText('do not establish commercial quality or an unstated supplier contribution');
    await expect(supplement.locator('.r-assertion')).toHaveCount(approved.length);
    for (const assertion of approved) {
      const record = supplement.locator(selector('assertion-' + assertion.id));
      await expect(record.locator('.r-kicker')).toContainText('Approved evidence · As of');
      const date = await record.locator('.r-kicker').innerText();
      expect(date).toContain(assertion.as_of.slice(0, 4));
      await expect(record.locator('.r-record-id a')).toHaveAttribute('href', evidenceURL('assertion', assertion.id));
      await expect(record.locator('.r-evidence-links li')).toHaveCount(assertion.evidence.length);
      for (const qualification of assertion.qualifications || []) await expect(record).toContainText(qualification);
    }
  });
});

async function importedFindings(request) {
  const source = await getJSON(request, '/publication/source-context.json');
  const findings = source.report.executive_findings || [];
  test.skip(findings.length === 0, 'The tested artifact has no imported executive findings yet; run this case against the integrated report.');
  expect(source.gate.report_review_ready, 'Imported report judgments require completed report review').not.toBe(false);
  return { source, findings, claims: new Map(source.graph.assertions.map(assertion => [assertion.id, assertion])) };
}

// These are separate behaviors with independent 30s budgets. Every finding,
// judgment field, citation, native anchor reload and offline record stays tested.
test('imported executive judgments retain complete content and approved evidence in HTML', async ({ page, request }) => {
  const { findings, claims } = await importedFindings(request);
  await page.goto(reportPath);
  await expect(page.locator('.r-finding')).toHaveCount(findings.length);
  for (const finding of findings) {
    const id = 'finding-' + finding.id;
    const article = page.locator(selector(id));
    await expect(article).toHaveCount(1);
    await expect(article.getByRole('heading', { level: 3 }).getByRole('link')).toHaveAttribute('href', '#' + id);
    await expect(article).toContainText(normalize(text(finding.text)));
    for (const [key, label] of Object.entries(judgmentFields)) {
      if (!text(finding[key])) continue;
      await expect(article.locator('dt', { hasText: new RegExp('^' + label + '$') })).toHaveCount(1);
      await expect(article).toContainText(normalize(text(finding[key])));
    }
    for (const cid of finding.claim_ids) {
      expect(claims.get(cid)?.status, cid).toBe('approved');
      await expect(article.locator('.r-paragraph-citations').getByRole('link', { name: cid, exact: true }))
        .toHaveAttribute('href', evidenceURL('assertion', cid));
    }
  }
  const byPart = new Map();
  for (const cid of new Set(findings.flatMap(finding => finding.claim_ids))) {
    const path = evidenceURL('assertion', cid).split('#')[0];
    byPart.set(path, [...(byPart.get(path) || []), cid]);
  }
  for (const [path, ids] of byPart) {
    await page.goto(path);
    const ledger = await page.locator('.r-assertion').evaluateAll(assertions => assertions.map(assertion => ({
      id: assertion.id, kicker: assertion.querySelector('.r-kicker')?.textContent,
      evidenceLinks: assertion.querySelectorAll('.r-evidence-links a').length })));
    for (const cid of ids) {
      const matching = ledger.filter(assertion => assertion.id === 'assertion-' + cid);
      expect(matching, cid).toHaveLength(1);
      expect(normalize(matching[0].kicker), cid).toContain('Approved evidence');
      expect(matching[0].evidenceLinks, cid).toBeGreaterThan(0);
    }
  }
});

test('imported executive judgments retain stable native anchors after reload', async ({ page, request }) => {
  const { findings } = await importedFindings(request);
  await page.goto(reportPath);
  await expect(page.locator('.r-finding')).toHaveCount(findings.length);
  for (const finding of findings) {
    const id = 'finding-' + finding.id;
    const article = page.locator(selector(id));
    await article.getByRole('heading', { level: 3 }).getByRole('link').click();
    expect(decodeURIComponent(new URL(page.url()).hash)).toBe('#' + id);
    await page.reload();
    await expect(page.locator(selector(id))).toBeInViewport();
  }
});

test('imported executive judgments retain approved evidence in the offline archive', async ({ request, browser }, info) => {
  const { source, findings, claims } = await importedFindings(request);
  const htmlResponse = await request.get('/publication/report.html');
  const markdownResponse = await request.get('/publication/report.md');
  const archiveResponse = await request.get('/publication/research-archive.zip');
  expect(htmlResponse.ok()).toBeTruthy();
  expect(markdownResponse.ok()).toBeTruthy();
  expect(archiveResponse.ok()).toBeTruthy();
  const archive = await archiveResponse.body();
  // Use only Python's standard-library ZIP reader, with the actual downloaded bytes.
  const extraction = spawnSync('python3', ['-c', 'import io,json,sys,zipfile\nz=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))\nprint(json.dumps({name:z.read(name).decode() for name in ["report.html","report.md","evidence.html","MANIFEST.json","source-context.json"]}))'], { input: archive, maxBuffer: 64 * 1024 * 1024 });
  expect(extraction.status, extraction.stderr?.toString()).toBe(0);
  const packaged = JSON.parse(extraction.stdout.toString());
  const inventory = JSON.parse(packaged['MANIFEST.json']);
  for (const name of ['report.html', 'report.md', 'evidence.html', 'source-context.json']) {
    expect(createHash('sha256').update(packaged[name]).digest('hex'), name).toBe(inventory.files[name].sha256);
  }
  expect(packaged['report.html']).toBe(await htmlResponse.text());
  expect(packaged['report.md']).toBe(await markdownResponse.text());
  expect(JSON.parse(packaged['source-context.json'])).toEqual(source);
  await info.attach('executive-findings-archive.json', { body: Buffer.from(JSON.stringify({ findings: findings.map(finding => finding.id),
    archiveSHA256: createHash('sha256').update(archive).digest('hex') })), contentType: 'application/json' });
  const offlineContext = await browser.newContext({ javaScriptEnabled: false, offline: true, viewport: { width: 412, height: 915 } });
  const offlineDirectory = mkdtempSync(resolve(tmpdir(), 'sts-research-archive-'));
  try {
    for (const name of ['report.html', 'evidence.html']) writeFileSync(resolve(offlineDirectory, name), packaged[name]);
    const unexpectedRequests = [];
    await offlineContext.route(/^https?:\/\//, route => {
      unexpectedRequests.push(route.request().url());
      return route.abort();
    });
    const offline = await offlineContext.newPage();
    await offline.goto(pathToFileURL(resolve(offlineDirectory, 'report.html')).href);
    const citedClaims = [...new Set(findings.flatMap(finding => finding.claim_ids))];
    const citedNames = new RegExp('^(?:' + citedClaims.map(cid => cid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')$');
    // Query actual accessible link names once, retaining every matching occurrence.
    const offlineLinkRecords = await offline.getByRole('link', { name: citedNames }).evaluateAll(links => links.map(link => ({
      text: link.textContent.replace(/\s+/g, ' ').trim(), label: link.getAttribute('aria-label'),
      labelledBy: link.getAttribute('aria-labelledby'), href: link.getAttribute('href') })));
    for (const link of offlineLinkRecords) {
      expect(link.labelledBy).toBeNull();
      expect(citedClaims).toContain(link.label || link.text);
    }
    const offlineFindings = await offline.locator('article[id^="finding-"]').evaluateAll(articles => articles.map(article => ({
      id: article.id, text: article.textContent.replace(/\s+/g, ' ').trim() })));
    for (const finding of findings) {
      const id = 'finding-' + finding.id;
      const matching = offlineFindings.filter(article => article.id === id);
      expect(matching, id).toHaveLength(1);
      expect(packaged['report.md']).toContain('<a id="' + id + '"></a>');
      for (const key of Object.keys(judgmentFields)) {
        if (text(finding[key])) expect(matching[0].text, id + ' ' + key).toContain(normalize(text(finding[key])));
      }
      for (const cid of finding.claim_ids) {
        expect(claims.get(cid)?.status, cid).toBe('approved');
        const offlineLinks = offlineLinkRecords.filter(link => (link.label || link.text) === cid);
        expect(offlineLinks.length, cid).toBeGreaterThan(0);
        const localHref = 'evidence.html#' + encodeURIComponent('assertion-' + cid);
        for (const link of offlineLinks) expect(link.href, cid).toBe(localHref);
        expect(packaged['report.md']).toContain('[' + cid + '](' + localHref + ')');
      }
    }
    await offline.locator(selector('finding-' + findings[0].id)).getByRole('link', { name: citedClaims[0], exact: true }).first().click();
    await expect(offline).toHaveURL(pathToFileURL(resolve(offlineDirectory, 'evidence.html')).href + '#' + encodeURIComponent('assertion-' + citedClaims[0]));
    const offlineAssertionIds = await offline.locator('[id^="assertion-"]').evaluateAll(assertions => assertions.map(assertion => assertion.id));
    for (const cid of citedClaims) expect(offlineAssertionIds.filter(id => id === 'assertion-' + cid), cid).toHaveLength(1);
    expect(await offline.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      'The complete offline appendix must fit a mobile viewport, including long record IDs and review notes').toBe(true);
    expect(unexpectedRequests, 'Archived report and evidence must require no external requests').toEqual([]);
  } finally {
    await offlineContext.close();
    rmSync(offlineDirectory, { recursive: true, force: true });
  }
});
