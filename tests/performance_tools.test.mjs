import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {gzipSync} from 'node:zlib';
import {spawnSync} from 'node:child_process';
import {archiveLeak, checkPayloadBudgets, compressedSizes, extractBootstrapScripts,
  loadArtifactManifest, readBudgets, resourceReferences, sha256, stableJSON} from '../scripts/payload_budgets.mjs';
import {diagnosticReasons, median, mobileHeroRequests, saveDiagnostics, summarizeRoutes, verifyServedArtifact} from '../scripts/performance_audit.mjs';

const {policy, sha256: policySha256} = await readBudgets();

const repositoryRoot = path.resolve(import.meta.dirname, '..');
const browserWorkflow = await readFile(path.join(repositoryRoot, '.github/workflows/browser-qa.yml'), 'utf8');

function browserJob(name) {
  const lines = browserWorkflow.split('\n');
  const start = lines.indexOf('  ' + name + ':');
  assert(start >= 0, 'Missing browser job: ' + name);
  const end = lines.findIndex((line, index) => index > start && /^  [\w-]+:$/.test(line));
  return lines.slice(start + 1, end < 0 ? undefined : end).join('\n');
}

function browserSelection(name, project) {
  const command = browserJob(name).match(/^      - run: npm run test:browser -- (.+)$/m);
  assert(command, 'Missing browser command: ' + name);
  const selection = command[1].match(/^(--project "\$QA_PROJECT" )?(--grep(?:-invert)?) '([^']+)'( --workers=1)?$/);
  assert(selection, 'Unexpected browser command: ' + command[1]);
  assert.equal(Boolean(selection[1]), Boolean(project), 'Wrong project selection for ' + name);
  return [...(project ? ['--project', project] : []), selection[2], selection[3], ...(selection[4] ? ['--workers=1'] : [])];
}

function listBrowserTests(args = []) {
  const listed = spawnSync(process.execPath, ['node_modules/@playwright/test/cli.js', 'test',
    '--list', '--reporter=json', ...args], {cwd: repositoryRoot, encoding: 'utf8',
    env: {...process.env, CI: '1', PLAYWRIGHT_JSON_OUTPUT_FILE: '', PLAYWRIGHT_JSON_OUTPUT_NAME: '', PLAYWRIGHT_JSON_OUTPUT_DIR: ''}});
  assert.equal(listed.status, 0, listed.stderr || listed.error?.message);
  const report = JSON.parse(listed.stdout);
  assert.deepEqual(report.errors, []);
  const entries = [];
  function visit(suites, ancestors = []) {
    for (const suite of suites) {
      const titles = [...ancestors, suite.title];
      for (const spec of suite.specs || []) {
        // The merged reporter generates spec.id from the first selected project.
        for (const check of spec.tests) entries.push({key: JSON.stringify([check.projectName, spec.file, spec.line, spec.column, ...titles, spec.title]),
          project: check.projectName, file: spec.file, title: spec.title, timeout: check.timeout});
      }
      visit(suite.suites || [], titles);
    }
  }
  visit(report.suites);
  assert.equal(new Set(entries.map(entry => entry.key)).size, entries.length, 'Duplicate test identity');
  return {entries, config: report.config};
}

test('browser CI partitions preserve every test and isolate all twelve chapter scans on all five engines', () => {
  const coreJob = browserJob('browser-core');
  const matrix = coreJob.match(/^        project: \[([^\]]+)\]$/m);
  assert(matrix, 'Missing core browser project matrix');
  assert.match(coreJob, /^      fail-fast: false$/m);
  assert.match(coreJob, /^          QA_PROJECT: \$\{\{ matrix\.project \}\}$/m);
  assert.match(coreJob, /^          name: browser-core-qa-\$\{\{ matrix\.project \}\}$/m);
  const projects = matrix[1].split(',').map(name => name.trim());
  assert.deepEqual([...projects].sort(), ['chromium', 'firefox', 'mobile-chromium', 'mobile-webkit', 'webkit']);
  const reportArgs = browserSelection('report-accessibility');
  const reportTitle = 'no serious or critical accessibility violations on /research/state-of-ai-data-labs/';
  const readingSelection = reportTitle + '($|chapters/)';
  assert.deepEqual(reportArgs, ['--grep', readingSelection, '--workers=1']);
  const all = listBrowserTests();
  const core = {entries: projects.flatMap(project => {
    const args = browserSelection('browser-core', project);
    assert.deepEqual(args, ['--project', project, '--grep-invert', readingSelection]);
    const suite = listBrowserTests(args);
    assert(suite.entries.length && suite.entries.every(entry => entry.project === project));
    assert.equal(suite.config.workers, 2);
    return suite.entries;
  })};
  const report = listBrowserTests(reportArgs);
  const keys = inventory => inventory.entries.map(entry => entry.key).sort();
  const coreKeys = new Set(keys(core));
  assert.equal(coreKeys.size, core.entries.length, 'Core browser projects overlap');
  assert(report.entries.every(entry => !coreKeys.has(entry.key)), 'CI partitions overlap');
  assert.deepEqual([...keys(core), ...keys(report)].sort(), keys(all), 'CI must execute exactly the complete inventory');
  assert(all.entries.length >= 700, 'The original browser inventory must not shrink');
  assert.equal(core.entries.length, all.entries.length - 60);
  assert.equal(report.entries.length, 60);
  assert.deepEqual(report.entries.map(entry => entry.project).sort(), projects.flatMap(name => Array(12).fill(name)).sort());
  const readerRoutes = policy.performance.routes.filter(route => route.startsWith('/research/state-of-ai-data-labs/'));
  assert.equal(readerRoutes.length, 12);
  for (const entry of report.entries) {
    assert.equal(entry.file, 'research.spec.js');
    assert(readerRoutes.some(route => entry.title === 'no serious or critical accessibility violations on ' + route));
    assert.equal(entry.timeout, 30_000);
  }
  assert.equal(report.config.workers, 1);
});

test('required browser check fails unless browser, accessibility and performance succeed', () => {
  const job = browserJob('browser');
  assert.match(job, /^    if: \$\{\{ always\(\) \}\}$/m);
  assert.match(job, /^    needs: \[browser-core, report-accessibility, performance\]$/m);
  assert.match(job, /^          CORE_RESULT: \$\{\{ needs\.browser-core\.result \}\}$/m);
  assert.match(job, /^          REPORT_RESULT: \$\{\{ needs\.report-accessibility\.result \}\}$/m);
  assert.match(job, /^          PERFORMANCE_RESULT: \$\{\{ needs\.performance\.result \}\}$/m);
  const script = job.split('        run: |\n')[1];
  assert(script, 'Missing required-check script');
  for (const core of ['success', 'failure', 'cancelled', 'skipped']) {
    for (const report of ['success', 'failure', 'cancelled', 'skipped']) {
      for (const performance of ['success', 'failure', 'cancelled', 'skipped']) {
        const result = spawnSync('bash', ['-e', '-o', 'pipefail', '-c', script], {
          env: {...process.env, CORE_RESULT: core, REPORT_RESULT: report, PERFORMANCE_RESULT: performance}, encoding: 'utf8'});
        assert.equal(result.status === 0, core === 'success' && report === 'success' && performance === 'success',
          core + '/' + report + '/' + performance);
      }
    }
  }
});

async function fixture(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'field-guide-budget-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const webp = Buffer.alloc(32);
  webp.write('RIFF', 0); webp.writeUInt32LE(24, 4); webp.write('WEBP', 8);
  const files = {
    'index.html': '<!doctype html><picture><source srcset="/assets/human-depth-portrait-400.webp 400w, /assets/human-depth-portrait-600.webp 600w"><img src="/assets/human-depth-portrait-400.webp"></picture><script src="/home-runtime.js"></script>',
    'explore/index.html': '<!doctype html><script id="research-data" type="application/json">{"claims":[],"sources":[],"raw_inputs":[]}</script><script src="/js/data.12345678.js"></script><script src="/js/app.87654321.js"></script>',
    'work/index.html': '<!doctype html><p>Browse work</p>',
    'home-runtime.js': 'console.log("small runtime");',
    'js/data.12345678.js': 'window.guide={raw_inputs:[]};',
    'js/app.87654321.js': 'console.log("small app");',
    'assets/human-depth-portrait-400.webp': webp,
    'assets/human-depth-portrait-600.webp': webp,
    'research.json': JSON.stringify({claims: [{id: 'claim-a'}], sources: [{id: 'source-a'}], raw_inputs: [{full: 'archive'}]}),
  };
  async function save() {
    const inventory = {};
    for (const [name, content] of Object.entries(files)) {
      await mkdir(path.dirname(path.join(directory, name)), {recursive: true});
      await writeFile(path.join(directory, name), content);
      inventory[name] = sha256(content);
    }
    await writeFile(path.join(directory, 'manifest.json'), JSON.stringify({
      build_id: 'test-build', editorial_release_id: 'test-editorial', dataset_version: '2.5.0', sha256: inventory,
    }));
  }
  await save();
  return {directory, files, save};
}

test('fixed gates retain the approved limits across field-guide and research routes', () => {
  assert.equal(policy.performance.lighthouseVersion, '13.6.0');
  assert.equal(policy.performance.playwrightVersion, '1.65.0');
  assert.equal(policy.performance.minimumRunsPerRoute, 3);
  assert.deepEqual(policy.performance.routes, ['/', '/companies/', '/explore/#companies', '/explore/#work', '/explore/#company/mercor/work', '/work/',
    '/daily/', '/research/', '/research/papers/', '/research/state-of-ai-data-labs/',
    '/research/state-of-ai-data-labs/chapters/weekly-developments/',
    '/research/state-of-ai-data-labs/chapters/market-structure/',
    '/research/state-of-ai-data-labs/chapters/technical-landscape/',
    '/research/state-of-ai-data-labs/chapters/provider-dossiers/',
    '/research/state-of-ai-data-labs/chapters/datasets-and-benchmarks/',
    '/research/state-of-ai-data-labs/chapters/human-expertise-and-operations/',
    '/research/state-of-ai-data-labs/chapters/commercial-evidence/',
    '/research/state-of-ai-data-labs/chapters/governance/',
    '/research/state-of-ai-data-labs/chapters/buyer-decision-guides/',
    '/research/state-of-ai-data-labs/chapters/research-outlook/',
    '/research/state-of-ai-data-labs/chapters/methods-and-appendices/',
    '/research/data/', '/review/']);
  assert.deepEqual(Object.values(policy.performance.medianLimits).map(limit => limit.maximum), [2500, 200, 0.05]);
  assert.equal(policy.payload.bootstrap.maximumBrotliBytes, 300 * 1024);
  assert.equal(policy.payload.bootstrap.maximumGzipBytes, 360 * 1024);
  assert.equal(policy.payload.home.maximumGzipBytes, 12 * 1024);
  assert.equal(policy.payload.home.maximumRuntimeGzipBytes, 5 * 1024);
  assert.deepEqual(policy.payload.home.heroVariants.map(row => row.maximumBytes), [150000, 250000]);
});

test('median does not convert missing or invalid measurements to passing zeros', () => {
  assert.equal(median([9, 1, 3]), 3);
  assert.equal(median([2, 4]), 3);
  for (const values of [[], [null, 2], [NaN], [Infinity]]) assert.equal(median(values), null);
});

test('route gates require three complete samples and use inclusive median thresholds', () => {
  const configuration = {...policy.performance, routes: ['/']};
  const results = [1, 2, 3].map(run => ({route: '/', run, valid: true, metrics: {
    'largest-contentful-paint': [1000, 2500, 9000][run - 1],
    'total-blocking-time': 200, 'cumulative-layout-shift': 0.05,
  }}));
  assert.equal(summarizeRoutes(results, configuration, 3)[0].passed, true);
  assert.equal(summarizeRoutes(results.slice(0, 2), configuration, 2)[0].passed, false);
  const missing = structuredClone(results); missing[0].metrics['total-blocking-time'] = null;
  assert.equal(summarizeRoutes(missing, configuration, 3)[0].medians['total-blocking-time'], null);
  const invalid = structuredClone(results); invalid[2].valid = false;
  assert.equal(summarizeRoutes(invalid, configuration, 3)[0].complete, false);
  const slow = structuredClone(results); slow[0].metrics['largest-contentful-paint'] = 2501;
  slow[1].metrics['largest-contentful-paint'] = 2501;
  assert.equal(summarizeRoutes(slow, configuration, 3)[0].passed, false);
});

test('diagnostics retain an over-budget sample even when the three-run median passes', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'performance-diagnostics-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const configuration = {...policy.performance, routes: ['/']};
  const records = [100, 150, 230].map((tbt, index) => ({route: '/', run: index + 1, valid: true,
    metrics: {'largest-contentful-paint': 1000, 'total-blocking-time': tbt, 'cumulative-layout-shift': 0}}));
  const artifacts = {Trace: {traceEvents: [{name: 'Layout', dur: 230000}]},
    DevtoolsLog: [{method: 'Network.responseReceived', params: {type: 'Document'}}]};
  const reasons = diagnosticReasons(records[2], configuration);
  assert.deepEqual(reasons, ['total-blocking-time:over-budget']);
  records[2].diagnostics = await saveDiagnostics(directory, 'route-01-run-3', artifacts, reasons);
  assert.equal(records[2].diagnostics.files.length, 2);
  assert.deepEqual(records[2].diagnostics.missing, []);
  assert.deepEqual(records[2].diagnostics.errors, []);
  for (const file of records[2].diagnostics.files) {
    const bytes = await readFile(path.join(directory, file.file));
    assert.equal(bytes.length, file.bytes);
    assert.equal(sha256(bytes), file.sha256);
    assert.deepEqual(JSON.parse(bytes), artifacts[file.artifact]);
  }
  const summary = summarizeRoutes(records, configuration, 3)[0];
  assert.equal(summary.passed, true);
  assert.equal(summary.medians['total-blocking-time'], 150);
  assert.deepEqual(summary.runReports[2].diagnostics, records[2].diagnostics);
  assert.deepEqual(diagnosticReasons(records[0], configuration), []);
  assert.deepEqual(await saveDiagnostics(directory, 'passing', artifacts, []),
    {required: false, reasons: [], files: [], missing: [], errors: []});
});

test('failed navigation retains Lighthouse error traces and identifies their source keys', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'performance-navigation-error-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const artifacts = {Trace: null, TraceError: {traceEvents: [{name: 'navigationStart'}]},
    DevtoolsLogError: [{method: 'Network.loadingFailed', params: {errorText: 'net::ERR_CONNECTION_RESET'}}]};
  const record = {valid: false, error: 'PAGE_HUNG'};
  const diagnostics = await saveDiagnostics(directory, 'failed-navigation', artifacts,
    diagnosticReasons(record, policy.performance));
  assert.deepEqual(diagnostics.missing, []);
  assert.deepEqual(diagnostics.errors, []);
  assert.deepEqual(diagnostics.files.map(file => file.sourceArtifact), ['TraceError', 'DevtoolsLogError']);
  for (const file of diagnostics.files) {
    const raw = await readFile(path.join(directory, file.file));
    assert.deepEqual(JSON.parse(raw), artifacts[file.sourceArtifact]);
    assert.equal(raw.length, file.bytes);
    assert.equal(sha256(raw), file.sha256);
  }
  assert.equal(record.metrics, undefined);
});

test('invalid audits report absent trace artifacts without fabricating measurements', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'performance-missing-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const record = {route: '/', run: 1, valid: false, error: 'Browser stopped before a result'};
  const diagnostics = await saveDiagnostics(directory, 'failed-run', undefined, diagnosticReasons(record, policy.performance));
  assert.deepEqual(diagnostics, {required: true, reasons: ['invalid-run'], files: [],
    missing: ['Trace', 'DevtoolsLog'], errors: []});
  assert.equal(record.metrics, undefined);
  const unwritable = await saveDiagnostics(path.join(directory, 'absent'), 'failed-write',
    {Trace: {traceEvents: []}}, ['invalid-run']);
  assert.equal(unwritable.files.length, 0);
  assert.equal(unwritable.errors.length, 1);
  assert.deepEqual(unwritable.missing, ['DevtoolsLog']);
});

test('settings identity is stable across object key order while arrays remain ordered', () => {
  assert.equal(stableJSON({b: 2, a: {d: 4, c: 3}}), stableJSON({a: {c: 3, d: 4}, b: 2}));
  assert.notEqual(stableJSON([1, 2]), stableJSON([2, 1]));
});

test('bootstrap selection deduplicates preload references and rejects stale bundles', () => {
  const html = '<link href="/js/data.12345678.js"><script src="/js/data.12345678.js"></script><script src="/js/app.87654321.js"></script>';
  assert.deepEqual(extractBootstrapScripts(html), ['js/data.12345678.js', 'js/app.87654321.js']);
  assert.throws(() => extractBootstrapScripts(html + '"/js/app.11111111.js"'), /Expected one current app/);
});

test('empty compatibility archive slots are allowed, nonempty canonical inputs are rejected', () => {
  for (const text of ['{"raw_inputs":[]}', '{"raw_inputs": [ \n ]}', '{"raw_inputs":null}', JSON.stringify('{"raw_inputs":[]}')]) {
    assert.equal(archiveLeak(text), false, text);
  }
  for (const text of ['{"raw_inputs":[{"source":"full archive"}]}', '{"raw_inputs":{}}', JSON.stringify('{"raw_inputs":[{"source":"full archive"}]}')]) {
    assert.equal(archiveLeak(text), true, text);
  }
});

test('resource inventory covers relative styles and responsive sources without counting navigation', () => {
  const refs = resourceReferences('<link rel="stylesheet" href="../site.css"><a href="/work/">Browse</a><source srcset="/a.webp 400w, /b.webp 600w"><img src="https://external.test/a.png"><style>x{background:url(../c.svg)}</style>', 'explore/index.html');
  assert.deepEqual(refs.map(ref => ref.path), ['site.css', 'a.webp', 'b.webp', 'c.svg']);
});

test('payload checks sum independently compressed HTTP files and pass a valid manifested artifact', async t => {
  const f = await fixture(t);
  const report = await checkPayloadBudgets({dist: f.directory, budgets: policy, budgetsSha256: policySha256});
  assert.equal(report.passed, true, JSON.stringify(report.problems));
  const names = ['explore/index.html', 'js/data.12345678.js', 'js/app.87654321.js'];
  const expected = names.map(name => compressedSizes(Buffer.from(f.files[name]), policy.payload.compression));
  assert.equal(report.bootstrap.total.gzipBytes, expected.reduce((sum, row) => sum + row.gzipBytes, 0));
  assert.equal(report.bootstrap.total.brotliBytes, expected.reduce((sum, row) => sum + row.brotliBytes, 0));
  assert.equal(report.budgetsSha256, policySha256);
});

test('manifest validation rejects byte changes and unlisted assets', async t => {
  const f = await fixture(t);
  await writeFile(path.join(f.directory, 'home-runtime.js'), 'changed after build');
  await writeFile(path.join(f.directory, 'unexpected.js'), 'unlisted');
  const artifact = await loadArtifactManifest(f.directory);
  assert(artifact.problems.includes('Digest mismatch: home-runtime.js'));
  assert(artifact.problems.includes('Unmanifested payload: unexpected.js'));
});

test('full canonical graph fails even when its raw input slot is empty', async t => {
  const f = await fixture(t);
  f.files['explore/index.html'] = f.files['explore/index.html'].replace('"claims":[],"sources":[]', '"claims":[{"id":"claim-a"}],"sources":[{"id":"source-a"}]');
  await f.save();
  const report = await checkPayloadBudgets({dist: f.directory, budgets: policy});
  assert.equal(report.passed, false);
  assert(report.problems.includes('Complete canonical claim/source graph is embedded in bootstrap'));
});

test('mobile hero records report the actually selected variant and uncompressed bytes', () => {
  const artifact = {manifest: {sha256: {'assets/human-depth-portrait-600.webp': 'digest'}}};
  const lhr = {audits: {'network-requests': {details: {items: [{
    url: 'http://localhost/assets/human-depth-portrait-600.webp', resourceSize: 102940, transferSize: 103100,
  }]}}}};
  const [hero] = mobileHeroRequests(lhr, artifact, policy.payload.home, 'http://localhost');
  assert.equal(hero.path, 'assets/human-depth-portrait-600.webp');
  assert.equal(hero.manifested, true);
  assert.equal(hero.resourceBytes, 102940);
  assert.equal(hero.maximumBytes, 150000);
});

test('served-artifact preflight compares decoded gzip bytes with the frozen manifest', async t => {
  const f = await fixture(t);
  const artifact = await loadArtifactManifest(f.directory);
  let corrupt = false;
  const server = http.createServer(async (request, response) => {
    const name = request.url.slice(1);
    const bytes = corrupt && name === 'index.html' ? Buffer.from('wrong build') : await readFile(path.join(f.directory, name));
    response.writeHead(200, {'content-encoding': 'gzip', 'content-type': 'application/octet-stream'});
    response.end(gzipSync(bytes));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {server.closeAllConnections(); await new Promise(resolve => server.close(resolve));});
  const base = 'http://127.0.0.1:' + server.address().port;
  const checked = await verifyServedArtifact(base, artifact, ['index.html']);
  assert.equal(checked[1].sha256, artifact.manifest.sha256['index.html']);
  assert.equal(checked[1].contentEncoding, 'gzip');
  corrupt = true;
  await assert.rejects(verifyServedArtifact(base, artifact, ['index.html']), /Served bytes differ/);
});
