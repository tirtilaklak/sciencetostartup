"""Repeat two public Back assertions on the current release and immutable predecessor."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from release_artifact import validate_artifact


SPEC = json.loads(Path(__file__).with_name('expected.json').read_bytes())
TARGET_NAME = os.environ['QA_TARGET']
ITERATION = int(os.environ['QA_ITERATION'])
TARGET = SPEC['targets'][TARGET_NAME]
ORIGIN = TARGET['origin']
SITE = urlsplit(ORIGIN)
assert ITERATION in SPEC['iterations']
assert SITE.scheme == 'https' and SITE.hostname == SITE.netloc
assert not (SITE.path or SITE.query or SITE.fragment)
if TARGET_NAME == 'worker47-immutable':
    assert SITE.hostname.startswith(TARGET['worker_version'].split('-')[0] + '-')
    assert SITE.hostname.endswith('.workers.dev')
else:
    assert SITE.hostname == 'sciencetostartup.com'

OUT = Path('output/c20-back-ab').absolute()
OUT.mkdir(parents=True, exist_ok=False)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def observe(directory, edge):
    url = ORIGIN + '/manifest.json'
    request = Request(url, headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity',
                                    'User-Agent': 'ScienceToStartup-ReleaseVerification/1.0'})
    with urlopen(request, timeout=25) as response:
        content = response.read()
        status, resolved_url, ray = response.status, response.geturl(), response.headers.get('CF-Ray')
    digest = sha256(content).hexdigest()
    assert status == 200 and resolved_url == url and digest == TARGET['manifest_sha256']
    assert json.loads(content)['build_id'] == TARGET['build_id']
    if TARGET_NAME == 'worker48-public':
        assert content == Path('dist/manifest.json').read_bytes()
    (directory / f'manifest-{edge}.json').write_bytes(content)
    return {'http': status, 'url': resolved_url, 'manifest_sha256': digest, 'build_id': TARGET['build_id'],
            'cf_ray': ray, 'utc': datetime.now(timezone.utc).isoformat()}


def cases(suite, ancestry=()):
    for item in suite.get('specs', []):
        for outcome in item['tests']:
            yield item, outcome, ancestry
    for node in suite.get('suites', []):
        yield from cases(node, (*ancestry, node['title']))


def run_case(case):
    project = case['project']
    directory = OUT / project
    directory.mkdir()
    assert case['fixture_blob'] == git('rev-parse', f'HEAD:tests/browser/{case["file"]}')
    assert case['suite'][0] == case['file']
    test_list = directory / 'test-list.txt'
    parts = [f'[{project}]', case['file'], *case['suite'][1:], case['title']]
    assert all('›' not in p and '\n' not in p and '\r' not in p for p in parts)
    test_list.write_text(' › '.join(parts) + '\n')
    before = observe(directory, 'before')
    raw_path = directory / 'playwright.json'
    environment = {**os.environ, 'QA_BASE_URL': ORIGIN, 'QA_DIST': 'dist',
                   'PLAYWRIGHT_JSON_OUTPUT_FILE': str(raw_path)}
    cmd = ['node_modules/.bin/playwright', 'test', '--test-list', str(test_list), f'--project={project}',
           '--workers=1', '--timeout=90000', '--retries=0', '--trace=on', '--reporter=json',
           '--output', str(directory / 'browser-results')]
    with (directory / 'playwright.log').open('x') as log:
        try:
            rc = subprocess.run(cmd, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=140).returncode
        except subprocess.TimeoutExpired:
            rc = 124
            log.write('The single browser case exceeded the hosted execution budget.\n')
    after = observe(directory, 'after')
    result = {'expected': case, 'before': before, 'after': after, 'returncode': rc, 'exact_case_observed': False,
              'passed': False, 'playwright_sha256': None}
    if raw_path.is_file():
        raw_bytes = raw_path.read_bytes()
        raw = json.loads(raw_bytes)
        observed = list(cases(raw))
        result['playwright_sha256'] = sha256(raw_bytes).hexdigest()
        result['reported_case_count'] = len(observed)
        if len(observed) == 1:
            row, outcome, ancestry = observed[0]
            result['actual'] = {'id': row['id'], 'project': outcome['projectName'], 'file': row['file'],
                                'title': row['title'], 'suite': list(ancestry), 'status': outcome['status']}
            result['exact_case_observed'] = all(result['actual'][field] == case[field]
                          for field in ('id', 'project', 'file', 'title', 'suite'))
            runs = outcome['results']
            result['passed'] = (result['exact_case_observed'] and len(runs) == 1 and rc == 0 and not raw['errors']
                and runs[0]['status'] == 'passed' and outcome['status'] == 'expected'
                and outcome['expectedStatus'] == 'passed')
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


head = git('rev-parse', 'HEAD')
product = git('rev-parse', 'HEAD^')
assert head == os.environ['GITHUB_SHA'] and product == SPEC['product_head']
assert git('rev-parse', 'HEAD:dist') == git('rev-parse', 'HEAD^:dist') == SPEC['dist_tree']
assert git('rev-parse', 'HEAD:tests') == git('rev-parse', 'HEAD^:tests')
assert set(git('diff', '--name-only', 'HEAD^').splitlines()) == {
    '.github/qa/c20-loopback/expected.json', '.github/qa/c20-loopback/verify.py',
    '.github/workflows/c20-isolated-browser-proof.yml',
}
assert {row['project'] for row in SPEC['cases']} == {'chromium', 'mobile-chromium'} and len(SPEC['cases']) == 2
validate_artifact(Path('dist'), SPEC['product_manifest_sha256'])
results = [run_case(case) for case in SPEC['cases']]
validate_artifact(Path('dist'), SPEC['product_manifest_sha256'])
summary = {'github_run_id': os.environ['GITHUB_RUN_ID'], 'github_run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
           'runner_commit': head, 'product_head': product, 'dist_tree': SPEC['dist_tree'],
           'target': TARGET_NAME, 'iteration': ITERATION, 'target_identity': TARGET, 'results': results,
           'passed': all(result['passed'] for result in results)}
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'target': TARGET_NAME, 'iteration': ITERATION, 'passed': summary['passed'],
                  'case_outcomes': {r['expected']['project']:r['passed'] for r in results}}), flush=True)
raise SystemExit(not summary['passed'])
