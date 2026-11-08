#!/usr/bin/env node
/** Three cold, pinned default-mobile Lighthouse navigations per approved route. */
import {readFile, writeFile, mkdir, stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import path from 'node:path';
import os from 'node:os';
import {pathToFileURL, fileURLToPath} from 'node:url';
import lighthouse from 'lighthouse';
import * as chromeLauncher from 'chrome-launcher';
import {chromium} from '@playwright/test';
import {ROOT, readBudgets, loadArtifactManifest, checkPayloadBudgets, sha256, stableJSON} from './payload_budgets.mjs';

const require = createRequire(import.meta.url);
const LH_ROOT = path.dirname(require.resolve('lighthouse/package.json'));
const {defaultSettings} = await import(pathToFileURL(path.join(LH_ROOT, 'core/config/constants.js')).href);
const METRICS = ['largest-contentful-paint', 'total-blocking-time', 'cumulative-layout-shift'];

export function median(values) {
  if (!values.length || values.some(value => !Number.isFinite(value))) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

export function summarizeRoutes(results, policy, requestedRuns) {
  return policy.routes.map(route => {
    const runs = results.filter(result => result.route === route);
    const complete = requestedRuns >= policy.minimumRunsPerRoute && runs.length === requestedRuns &&
      runs.every(result => result.valid && METRICS.every(id => Number.isFinite(result.metrics?.[id])));
    const medians = {};
    const checks = [];
    for (const id of METRICS) {
      const value = complete ? median(runs.map(run => run.metrics[id])) : null;
      medians[id] = value;
      checks.push({metric: id, median: value, maximum: policy.medianLimits[id].maximum,
        unit: policy.medianLimits[id].unit,
        passed: complete && Number.isFinite(value) && value <= policy.medianLimits[id].maximum});
    }
    return {route, complete, validRuns: runs.filter(run => run.valid).length, requestedRuns,
      medians, checks, passed: complete && checks.every(check => check.passed),
      runReports: runs.map(run => ({run: run.run, report: run.report, reportSha256: run.reportSha256,
        metrics: run.metrics ?? null, error: run.error ?? null}))};
  });
}

function artifactName(url, base) {
  const target = new URL(url, base);
  if (target.origin !== new URL(base).origin) return null;
  let name = decodeURIComponent(target.pathname).replace(/^\//, '');
  if (!name || name.endsWith('/')) name += 'index.html';
  return name;
}

export function mobileHeroRequests(lhr, artifact, budget, base) {
  const items = lhr.audits?.['network-requests']?.details?.items ?? [];
  return items.filter(item => /\/assets\/human-depth-portrait-[^/?]+\.(?:webp|jpe?g)(?:[?#]|$)/i.test(item.url || ''))
    .map(item => {
      const name = artifactName(item.url, base);
      return {url: item.url, path: name, resourceBytes: item.resourceSize ?? null,
        transferBytes: item.transferSize ?? null, manifested: Boolean(name && artifact.manifest.sha256[name]),
        webp: /\.webp(?:[?#]|$)/i.test(item.url), maximumBytes: budget.maximumSelectedMobileHeroBytes};
    });
}

async function fileDigest(filename) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(filename)) hash.update(chunk);
  return hash.digest('hex');
}

export async function verifyServedArtifact(base, artifact, names = []) {
  const checked = [];
  for (const name of ['manifest.json', ...new Set(names)]) {
    const response = await fetch(new URL('/' + name, base), {cache: 'no-store', signal: AbortSignal.timeout(20000)});
    if (response.status !== 200) throw new Error('Frozen artifact preflight returned ' + response.status + ' for ' + name);
    const bytes = Buffer.from(await response.arrayBuffer());
    const expected = name === 'manifest.json' ? artifact.manifestSha256 : artifact.manifest.sha256[name];
    if (!expected || sha256(bytes) !== expected) throw new Error('Served bytes differ from frozen manifest: ' + name);
    checked.push({path: name, sha256: expected, contentEncoding: response.headers.get('content-encoding'),
      contentLength: response.headers.get('content-length'), contentType: response.headers.get('content-type')});
  }
  return checked;
}

function metricValues(lhr) {
  return Object.fromEntries(METRICS.map(id => [id,
    Number.isFinite(lhr.audits?.[id]?.numericValue) ? lhr.audits[id].numericValue : null]));
}

function parseArguments(args) {
  const result = {runs: 3, output: path.join(ROOT, 'output/performance')};
  for (let index = 0; index < args.length; index++) {
    const key = args[index];
    if (key === '--help') return {help: true};
    if (!['--base-url', '--dist', '--runs', '--output'].includes(key) || !args[index + 1]) {
      throw new Error('Use --base-url <URL> --dist <frozen artifact> [--runs 3] [--output output/performance]');
    }
    const value = args[++index];
    if (key === '--base-url') result.base = value;
    if (key === '--dist') result.dist = path.resolve(value);
    if (key === '--output') result.output = path.resolve(value);
    if (key === '--runs') result.runs = Number(value);
  }
  if (!result.dist || !result.base) throw new Error('--base-url and --dist are both required; the auditor never builds an artifact');
  const base = new URL(result.base);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash || !['', '/'].includes(base.pathname)) {
    throw new Error('base URL must be an HTTP(S) origin without credentials, query or fragment');
  }
  result.base = base.origin;
  if (!Number.isInteger(result.runs) || result.runs < 1) throw new Error('--runs must be a positive integer');
  if (result.output === result.dist || result.output.startsWith(result.dist + path.sep)) throw new Error('Reports must be outside the frozen artifact');
  return result;
}

export async function main(args = process.argv.slice(2)) {
  const options = parseArguments(args);
  if (options.help) {
    console.log('node scripts/performance_audit.mjs --base-url http://127.0.0.1:18766 --dist <frozen artifact> [--runs 3] [--output output/performance]');
    return;
  }
  const {policy, sha256: budgetsSha256} = await readBudgets();
  const performance = policy.performance;
  const lhVersion = require('lighthouse/package.json').version;
  const pwVersion = require('@playwright/test/package.json').version;
  if (lhVersion !== performance.lighthouseVersion || pwVersion !== performance.playwrightVersion) {
    throw new Error('Pinned auditor versions differ: Lighthouse ' + lhVersion + ', Playwright ' + pwVersion);
  }
  const chromePath = chromium.executablePath();
  if (!(await stat(chromePath)).isFile()) throw new Error('Pinned Playwright Chromium is not installed: ' + chromePath);
  const artifact = await loadArtifactManifest(options.dist);
  if (artifact.problems.length) throw new Error('Artifact manifest is invalid: ' + artifact.problems.join('; '));
  if (!artifact.buildId || !artifact.editorialReleaseId) throw new Error('Frozen artifact lacks current build/editorial identity');
  const startedAt = new Date().toISOString();
  const directory = path.join(options.output, artifact.buildId + '-' + startedAt.replace(/[:.]/g, '-'));
  await mkdir(directory, {recursive: true});
  const payloadReport = await checkPayloadBudgets({dist: options.dist, budgets: policy, budgetsSha256});
  await writeFile(path.join(directory, 'payload-budgets.json'), JSON.stringify(payloadReport, null, 2) + '\n');
  const preflightNames = [policy.payload.home.entry, policy.payload.bootstrap.entry, 'work/index.html',
    policy.payload.home.runtime, ...payloadReport.bootstrap.files.map(file => file.path),
    ...policy.payload.home.heroVariants.map(hero => hero.path)];
  const summaryDescriptor = artifact.manifest.summary;
  let summary = null;
  if (summaryDescriptor?.href) {
    const name = artifactName(summaryDescriptor.href, options.base);
    summary = JSON.parse((await readFile(path.join(artifact.dist, name))).toString('utf8'));
    if (summary.buildId !== artifact.buildId) throw new Error('Summary index belongs to a different build');
    preflightNames.push(name);
  }
  const served = await verifyServedArtifact(options.base, artifact, preflightNames);
  const packageLock = await readFile(path.join(ROOT, 'package-lock.json'));
  const settings = {...structuredClone(defaultSettings), onlyCategories: ['performance'], locale: 'en-US'};
  if (settings.formFactor !== 'mobile' || settings.throttlingMethod !== 'simulate' || settings.disableStorageReset !== false) {
    throw new Error('Installed Lighthouse no longer exposes the pinned default cold-mobile settings');
  }
  const metadata = {
    schemaVersion: '1.0.0', kind: 'pinned-mobile-performance-audit', startedAt,
    policyId: policy.policyId, budgetsSha256, baseURL: options.base,
    artifact: {dist: artifact.dist, buildId: artifact.buildId, editorialReleaseId: artifact.editorialReleaseId,
      datasetVersion: artifact.datasetVersion, manifestSha256: artifact.manifestSha256},
    lighthouse: {version: lhVersion, packageLockSha256: sha256(packageLock), preset: performance.preset,
      requestedSettings: settings, requestedSettingsSha256: sha256(stableJSON(settings))},
    browser: {playwrightVersion: pwVersion, executablePath: chromePath,
      executableSha256: await fileDigest(chromePath), chromeFlags: performance.chromeFlags,
      launcherDefaultFlags: chromeLauncher.Launcher.defaultFlags(), freshProfilePerRun: true},
    runner: {node: process.version, zlib: process.versions.zlib, platform: process.platform, arch: process.arch,
      osRelease: os.release(), scriptSha256: await fileDigest(fileURLToPath(import.meta.url)),
      payloadScriptSha256: await fileDigest(path.join(ROOT, 'scripts/payload_budgets.mjs'))},
    routes: performance.routes, runsPerRoute: options.runs, runOrder: 'sequential round-robin; no concurrent Lighthouse processes',
    servedPreflight: served,
  };
  await writeFile(path.join(directory, 'metadata.json'), JSON.stringify(metadata, null, 2) + '\n');
  console.log(JSON.stringify({event: 'audit-started', buildId: artifact.buildId, routes: performance.routes.length,
    runsPerRoute: options.runs, lighthouseVersion: lhVersion, reportDirectory: directory}));
  const results = [];
  const consistencyProblems = [];
  let firstActualSettingsHash = null;
  let browserVersion = null;
  try {
    for (let run = 1; run <= options.runs; run++) {
      for (const [routeIndex, route] of performance.routes.entries()) {
        const url = new URL(route, options.base).href;
        const prefix = 'route-' + String(routeIndex + 1).padStart(2, '0') + '-run-' + run;
        let chrome;
        let record;
        const runProblems = [];
        const runStartedAt = new Date().toISOString();
        try {
          chrome = await chromeLauncher.launch({chromePath, chromeFlags: performance.chromeFlags, logLevel: 'silent'});
          const browserInfoResponse = await fetch('http://127.0.0.1:' + chrome.port + '/json/version');
          const browserInfo = await browserInfoResponse.json();
          if (browserVersion === null) browserVersion = browserInfo.Browser;
          if (browserVersion !== browserInfo.Browser) runProblems.push('Browser version changed during the run');
          const runner = await lighthouse(url, {port: chrome.port, output: 'json', logLevel: 'error'},
            {extends: 'lighthouse:default', settings: structuredClone(settings)});
          if (!runner?.lhr) throw new Error('Lighthouse returned no result');
          const lhr = runner.lhr;
          const raw = JSON.stringify(lhr, null, 2) + '\n';
          const filename = prefix + '.lhr.json';
          await writeFile(path.join(directory, filename), raw);
          const actualSettingsSha256 = sha256(stableJSON(lhr.configSettings));
          if (firstActualSettingsHash === null) firstActualSettingsHash = actualSettingsSha256;
          if (actualSettingsSha256 !== firstActualSettingsHash) runProblems.push('Resolved settings changed: ' + route + ' run ' + run);
          if (lhr.lighthouseVersion !== lhVersion) runProblems.push('Lighthouse result version differs from installed pin');
          if (lhr.configSettings.formFactor !== 'mobile' || lhr.configSettings.throttlingMethod !== 'simulate') {
            runProblems.push('A result did not use default mobile simulation');
          }
          const metrics = metricValues(lhr);
          const heroes = mobileHeroRequests(lhr, artifact, policy.payload.home, options.base);
          const heroProblems = [];
          if (route === '/') {
            if (!heroes.length) heroProblems.push('Mobile homepage did not request the configured collage');
            if (!heroes.some(hero => hero.webp)) heroProblems.push('Mobile homepage did not request a WebP collage');
            for (const hero of heroes) {
              if (!hero.manifested) heroProblems.push('Mobile hero is not manifested: ' + hero.url);
              if (!Number.isFinite(hero.resourceBytes) || hero.resourceBytes > hero.maximumBytes) heroProblems.push('Selected mobile hero exceeds its byte budget: ' + hero.url);
            }
          }
          const archiveURLs = ['research.json', 'observatory.sqlite', summary?.archive?.href].filter(Boolean).map(item => new URL(item, options.base).href);
          const requests = lhr.audits?.['network-requests']?.details?.items ?? [];
          const archiveRequests = requests.filter(item => archiveURLs.includes((item.url || '').split('?')[0]));
          if (archiveRequests.length) heroProblems.push('Complete canonical archive was requested during initial route navigation');
          consistencyProblems.push(...runProblems);
          record = {route, run, valid: !lhr.runtimeError && METRICS.every(id => Number.isFinite(metrics[id])) && heroProblems.length === 0 && runProblems.length === 0,
            startedAt: runStartedAt, finishedAt: new Date().toISOString(), report: filename,
            reportSha256: sha256(raw), metrics, performanceScore: lhr.categories?.performance?.score ?? null,
            actualSettingsSha256, browser: browserInfo, hostUserAgent: lhr.environment?.hostUserAgent,
            networkUserAgent: lhr.environment?.networkUserAgent, benchmarkIndex: lhr.environment?.benchmarkIndex,
            mobileHeroRequests: heroes, archiveRequests: archiveRequests.map(item => item.url),
            runtimeError: lhr.runtimeError ?? null, warnings: lhr.runWarnings ?? [], problems: [...runProblems, ...heroProblems]};
        } catch (error) {
          record = {route, run, valid: false, startedAt: runStartedAt, finishedAt: new Date().toISOString(), error: error.message};
        } finally {
          if (chrome) {
            try {await chrome.kill();}
            catch (error) {
              consistencyProblems.push('Could not close audit browser: ' + error.message);
              if (record) {record.valid = false; record.problems = [...(record.problems || []), 'Could not close audit browser'];}
            }
          }
        }
        results.push(record);
        await writeFile(path.join(directory, prefix + '.metadata.json'), JSON.stringify(record, null, 2) + '\n');
        console.log(JSON.stringify({event: 'audit-run-complete', route, run, valid: record.valid, metrics: record.metrics ?? null, error: record.error ?? null}));
      }
    }
  } finally {
    try {
      const after = await loadArtifactManifest(options.dist);
      if (after.manifestSha256 !== artifact.manifestSha256 || after.problems.length) consistencyProblems.push('Frozen artifact changed while auditing');
    } catch (error) {consistencyProblems.push('Frozen artifact cannot be verified after audit: ' + error.message);}
    try {await verifyServedArtifact(options.base, artifact, [policy.payload.home.entry, policy.payload.bootstrap.entry]);}
    catch (error) {consistencyProblems.push(error.message);}
  }
  const routes = summarizeRoutes(results, performance, options.runs);
  const report = {schemaVersion: '1.0.0', kind: 'mobile-performance-budget-report', startedAt,
    finishedAt: new Date().toISOString(), buildId: artifact.buildId, manifestSha256: artifact.manifestSha256,
    editorialReleaseId: artifact.editorialReleaseId, policyId: policy.policyId, budgetsSha256,
    lighthouseVersion: lhVersion, playwrightVersion: pwVersion, browserVersion,
    resolvedSettingsSha256: firstActualSettingsHash, requestedSettingsSha256: metadata.lighthouse.requestedSettingsSha256,
    runsPerRoute: options.runs, minimumRunsPerRoute: performance.minimumRunsPerRoute,
    payloadPassed: payloadReport.passed, payloadReport: 'payload-budgets.json',
    routes, consistencyProblems: [...new Set(consistencyProblems)],
    passed: payloadReport.passed && consistencyProblems.length === 0 && routes.every(route => route.passed),
    interpretation: 'Cold-profile laboratory navigation medians under pinned default mobile simulation. TBT is measured here; this is not field INP or a real-user percentile.',
    reportDirectory: directory};
  await writeFile(path.join(directory, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  await mkdir(options.output, {recursive: true});
  await writeFile(path.join(options.output, 'latest.json'), JSON.stringify({summary: path.join(directory, 'summary.json'), passed: report.passed,
    buildId: artifact.buildId, manifestSha256: artifact.manifestSha256, finishedAt: report.finishedAt}, null, 2) + '\n');
  console.log(JSON.stringify({event: 'audit-complete', passed: report.passed, buildId: artifact.buildId,
    summary: path.join(directory, 'summary.json'), medians: routes.map(route => ({route: route.route, ...route.medians, passed: route.passed})),
    consistencyProblems: report.consistencyProblems}));
  if (!report.passed) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => {console.error(JSON.stringify({event: 'audit-failed', passed: false, error: error.message})); process.exitCode = 1;});
}
