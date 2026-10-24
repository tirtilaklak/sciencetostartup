#!/usr/bin/env python3
"""Focused presentation regressions; Node DOM stub is not rendered browser proof.

Run after building: python3 tests/redesign_checks.py
The canonical audit is pinned; no research, browser navigation or network is used.
"""
import hashlib
import ast
import csv
import io
import json
import re
import sqlite3
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The old pin was immutable 2.0.1 (921613996550332bf70fa5270eeee259ff9c460281d42c4fe168a74fe52f2e69).
# Later reviewed source deltas are recorded in docs/research-update-20261014.json,
# docs/research-update-round2-20261014.json and docs/release-verification-20261015.json.
# This test now checks the exact 2.5.0 snapshot already used by published v14;
# Further citation-only changes: docs/v13-source-relocations-20261015.json
# (2.3→2.4) and docs/v13-surge-provenance-cleanup-20261015.json (2.4→2.5).
# It must not silently follow subsequent canonical edits.
PINNED_VERSION = '2.5.0'
PINNED_SHA256 = '948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061'


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        self.elements.append((tag, dict(attributes)))

    def with_attribute(self, key):
        return [(tag, attrs) for tag, attrs in self.elements if key in attrs]


RUNTIME = r'''
(async()=>{
 window.innerWidth=390;run('initialize()');
 const initial=Object.fromEntries(Object.entries(nodes).filter(([id])=>id!=='research-data').map(([id,n])=>[id,{html:n.innerHTML,text:n.textContent,hidden:n.hidden}]));
 const groups=run('MODEL_GROUPS');
 const healthObservations=plain(run('window.BusinessHealth.observations()'));
 const clearStates={initial:node('reset').hidden};
 for(const [key,value] of Object.entries({query:'Mercor',category:Object.keys(groups)[0],stage:'established_commercial_evidence',financial:true,work:true,sort:'name-desc'})){run(`reset();state[${JSON.stringify(key)}]=${JSON.stringify(value)};renderDirectory()`);clearStates[key]=node('reset').hidden;}run('reset()');clearStates.afterReset=node('reset').hidden;
 const workCards=Object.fromEntries(run('workRouteRows().map(r=>[r.id,workCard(r)])'));const workRoutes=plain(run('workRouteRows()'));
 run(`state.query='Mercor';renderDirectory()`);const search=run('filtered().map(c=>c.id)');
 run(`reset()`);const resetCount=run('filtered().length');
 const categoryCounts={};for(const group of Object.keys(groups)){run(`state.category=${JSON.stringify(group)};renderDirectory()`);categoryCounts[group]=run('filtered().map(c=>c.id)');}run('reset()');
 run(`state.sort='name-desc';renderDirectory()`);const reverseNames=run('filtered().map(c=>c.name)');run('reset()');
 run(`setSelection(['mercor','snorkel_ai','labelbox']);chooseCompare('g2i',true)`);const selection=run('state.selected');const comparison=node('compare-content').innerHTML;
 const lastPage={dataset:{mobileCompare:'2'},hasAttribute:()=>false};click(lastPage);const lastMobileComparison=node('compare-content').innerHTML;const preservedSelection=run('state.selected');run('setSelection([])');
 node('download-json').callbacks.click();const jsonDownload=JSON.parse(await downloadedBlob.text());const jsonFilename=node('created').download;
 run('exportCsv()');const csvDownload=await downloadedBlob.text();const csvFilename=node('created').download;
 console.log(JSON.stringify({initial,groups,healthObservations,clearStates,workCards,workRoutes,search,resetCount,categoryCounts,reverseNames,selection,comparison,lastMobileComparison,preservedSelection,jsonDownloadMatches:JSON.stringify(jsonDownload)===JSON.stringify(data),jsonFilename,csvDownload,csvFilename}));
})().catch(error=>{console.error(error);process.exitCode=1});
'''


def main():
    canonical = (ROOT / 'data/canonical.json').read_bytes()
    assert hashlib.sha256(canonical).hexdigest() == PINNED_SHA256, 'Audited canonical data changed'
    assert canonical == (ROOT / f'data/versions/{PINNED_VERSION}.json').read_bytes(), 'Canonical differs from its immutable audit snapshot'
    data = json.loads(canonical)
    assert data['dataset_version'] == PINNED_VERSION
    expected_ids = {c['id'] for c in data['companies']}
    assert len(expected_ids) == 39
    template = (ROOT / 'web/index.html').read_text()
    tags = Elements(template)
    findings = tags.with_attribute('data-story-finding')
    assert any(a.get('id') == 'business-health' for _, a in tags.elements), 'Business health dashboard missing'
    assert {a['data-story-finding'] for _, a in findings} == {'products'}, 'Obsolete financial stories remain'
    assert any(a.get('id') == 'companies-view' for _, a in tags.elements), 'Separate directory route missing'
    assert len(re.findall(r'<h1\b', template.split('id="market-view"', 1)[1].split('id="companies-view"', 1)[0])) == 1, 'Overview must have one headline'
    assert 'company-cards' not in template.split('id="market-view"', 1)[1].split('id="companies-view"', 1)[0], 'Verbose directory must not be part of overview'

    with tempfile.TemporaryDirectory(prefix='observatory-redesign-') as tmp:
        script = Path(tmp) / 'checks.cjs'
        tree = ast.parse((ROOT / 'tests/js_logic.py').read_text())
        stub = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STUB' for t in n.targets))
        script.write_text(stub.split('(async()=>{', 1)[0] + RUNTIME)
        result = subprocess.run(['node', str(script), str(ROOT / 'data/canonical.json'), str(ROOT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        rendered = json.loads(result.stdout)

    assert len(rendered['groups']) == 7
    grouped_ids = [cid for ids in rendered['groups'].values() for cid in ids]
    assert len(grouped_ids) == len(set(grouped_ids)) == 39 and set(grouped_ids) == expected_ids
    initial_html = '\n'.join(n['html'] for n in rendered['initial'].values())
    runtime_tags = Elements(initial_html)
    map_groups = [a['data-category-jump'] for _, a in runtime_tags.with_attribute('data-category-jump')]
    assert len(map_groups) == len(set(map_groups)) == 7 and set(map_groups) == set(rendered['groups']), 'Category map must expose every reviewed group once'
    map_ids = grouped_ids  # Category navigation replaces the earlier 39-name overview.
    directory = rendered['initial']['company-cards']['html']
    rows = Elements(directory).with_attribute('data-company-card')
    row_ids = [a['data-company-card'] for _, a in rows]
    assert len(row_ids) == len(set(row_ids)) == 39 and set(row_ids) == expected_ids
    assert all('company-card' in a.get('class', '') for _, a in rows)
    for card_html in re.findall(r'<article class="company-card".*?</article>', directory, re.S):
        card_tags = Elements(card_html)
        assert len(card_tags.with_attribute('data-compare')) == 1
        assert len(card_tags.with_attribute('data-open-company')) == 1
        assert sum('number-button' in a.get('class', '') for tag, a in card_tags.elements if tag == 'button') <= 1, 'Directory repeats financial headlines'
        assert 'company-description' in card_html and 'company-signal' in card_html
    assert 'One financial headline each' not in template, 'Removed directory subtitle remains'
    assert rendered['clearStates']['initial'] and rendered['clearStates']['afterReset'], 'Clear must be hidden without an active filter'
    assert all(not rendered['clearStates'][key] for key in ('query', 'category', 'stage', 'financial', 'work', 'sort')), 'Clear must appear for an active query, filter or descending sort'
    assert not any(x in directory for x in ['class="unknown"', 'class="evidence-markers"', 'class="card-context"']), 'Old verbose layers remain in directory'
    assert '[object Object]' not in initial_html
    # The business-health observations have independently tested provenance and
    # comparison rules in test_business_health.py. Preserve the rest of the
    # directory, source, work, comparison and portable-data regression checks.
    claim_index = {c['id']: c for c in data['claims']}
    # v2.0.1 used one prose-derived card per company. The current reviewed
    # route bundle has 135 individually dated records, including closed routes.
    # Retain pay/source coverage checks against those records instead of the
    # removed work-requirements markup and stale company-level pay summaries.
    route_index = {r['id']: r for r in rendered['workRoutes']}
    assert len(route_index) == 135
    assert set(rendered['workCards']) == set(route_index)
    visible_work = {}
    for route_id, card_html in rendered['workCards'].items():
        route = route_index[route_id]
        before_details, details = card_html.split('<details class="w4-details">', 1)
        visible_work[route_id] = before_details
        assert 'Terms & sources' in details
        assert f'data-work-route="{route_id}"' in before_details
        assert f'data-work-company="{route["company_id"]}"' in before_details
        assert 'Checked ' in before_details and 'Terms recorded:' in details
        links = [a['href'] for tag, a in Elements(before_details).elements if tag == 'a' and 'w4-open' in a.get('class', '')]
        assert links == [route['url']], route_id + ': exact route target changed'
        for claim_id in route.get('claim_ids', []):
            assert claim_id in claim_index and f'data-claim="{claim_id}"' in details, route_id + ': original claim inaccessible'
        for source in route.get('sources', []):
            assert any(a.get('href') == source['url'] for tag, a in Elements(details).elements if tag == 'a'), route_id + ': source URL lost'
    for route_id, labels in {
        'pareto.work.investment-analyst': ['Closed', 'Approx. $100 / approved hour'],
        'toloka.work.cad-simulation': ['Historical', 'Up to $69 / hour equivalent'],
        # The existing 19 October route update marked the portal listing closed;
        # the original 12 October pay observation remains visible as history.
        'rws_trainai.work.polaris-asr': ['Closed', '$16 / hour'],
        'afterquery.work.college-swe': ['Rate conflict'],
        'afterquery.work.technical-content-writer-contract': ['Initial commitment; may expand', 'Schedule conflict: header says full-time'],
        'abundant_ai.work.research-product-manager': ['Pay periods unspecified.'],
        'bespoke_labs.work.mts-post-training': ['Pay periods unspecified.'],
        'toloka.work.mindrift-code': ['hour equivalent', 'Paid per completed task'],
    }.items():
        assert all(label in visible_work[route_id] for label in labels), route_id + ': visible pay/status qualifier lost'
    assert rendered['healthObservations'], 'Business-health research does not reach the delivered runtime'
    assert not any(key in rendered['initial'] for key in ('scale-visual', 'growth-visual')), 'Removed story renderer still runs'
    assert rendered['search'] == ['mercor'] and rendered['resetCount'] == 39
    assert rendered['categoryCounts'] == rendered['groups'] or all(set(rendered['categoryCounts'][k]) == set(v) for k, v in rendered['groups'].items())
    assert rendered['reverseNames'][0] == sorted([c['name'] for c in data['companies']], key=str.casefold, reverse=True)[0]
    assert len(rendered['selection']) == 3 and 'g2i' not in rendered['selection']
    assert rendered['preservedSelection'] == rendered['selection']
    for key in ('comparison', 'lastMobileComparison'):
        cells = Elements(rendered[key]).with_attribute('data-comparison-company')
        assert len(cells) == 27
        assert len([a for _, a in cells if 'mobile-hidden' not in a.get('class', '')]) == 18, 'Mobile must retain two visible comparison columns at either end'
    assert rendered['jsonDownloadMatches'] and rendered['jsonFilename'].endswith('.json')
    csv_rows = list(csv.DictReader(io.StringIO(rendered['csvDownload'])))
    assert rendered['csvFilename'].endswith('.csv') and len(csv_rows) == 39
    assert {row['company_id'] for row in csv_rows} == expected_ids
    assert any(a.get('href') == 'observatory.sqlite' and 'download' in a for _, a in tags.elements)

    export = ROOT / 'dist/research.json'
    assert export.read_bytes() == canonical, 'Portable JSON changed'
    html = (ROOT / 'dist/index.html').read_text()
    assert (ROOT / 'web/app.js').read_text() in html, 'Build is stale relative to dashboard JavaScript'
    assert (ROOT / 'web/style.css').read_text() in html, 'Build is stale relative to dashboard CSS'
    embedded = re.search(r'<script id="research-data" type="application/json">(.*?)</script>', html, re.S)
    assert embedded and json.loads(embedded.group(1)) == data
    with sqlite3.connect(ROOT / 'dist/observatory.sqlite') as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        assert con.execute('SELECT count(*) FROM companies').fetchone()[0] == 39
    manifest = json.loads((ROOT / 'dist/manifest.json').read_text())
    for name, expected in manifest['sha256'].items():
        assert hashlib.sha256((ROOT / 'dist' / name).read_bytes()).hexdigest() == expected, name
    print(json.dumps({'audited_dataset_version': PINNED_VERSION, 'canonical_sha256': PINNED_SHA256, 'html_sha256': hashlib.sha256((ROOT / 'dist/index.html').read_bytes()).hexdigest(), 'canonical_unchanged': True, 'business_health_observations': len(rendered['healthObservations']), 'model_groups': 7, 'categorized_companies': len(map_ids), 'company_cards': len(rows), 'conditional_clear': 'passed', 'visible_work_summaries': len(visible_work), 'search_filters_compare_download_handlers': 'passed', 'portable_data_integrity': 'passed', 'browser_rendering_verified': False}, indent=2))


if __name__ == '__main__':
    main()
