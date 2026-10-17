"""Bind browser reports to stable disk files and the actual in-page dataset.

The in-page evidence identifies the research script and live DATA, not an
unmodified original HTML response. Disk hashes alone never prove which page
an already-open browser executed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path


FILES = ('index.html', 'manifest.json', 'research.json')


class ResearchScriptParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.collecting = False
        self.matches = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'script' and dict(attrs).get('id') == 'research-data':
            self.matches += 1
            self.collecting = True

    def handle_endtag(self, tag):
        if tag.lower() == 'script':
            self.collecting = False

    def handle_data(self, data):
        if self.collecting:
            self.parts.append(data)


def extract_research_script(html: str) -> str:
    parser = ResearchScriptParser()
    # HTML parsing normalizes CRLF and bare CR in text nodes. Hash the text
    # that browser textContent will expose, retaining literal JSON escapes.
    parser.feed(html.replace('\r\n', '\n').replace('\r', '\n'))
    if parser.matches != 1:
        raise ValueError('Expected exactly one research-data script')
    return ''.join(parser.parts)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_state(path: Path) -> dict:
    stat = path.stat()
    return {'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns, 'inode': stat.st_ino}


def snapshot_dist(directory: Path) -> dict:
    """Capture byte identities, metadata and internal consistency without editing."""
    result = {'schemaVersion': 1, 'capturedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
              'files': {}, 'errors': []}
    before, blobs = {}, {}
    for name in FILES:
        try:
            before[name] = file_state(directory / name)
            blobs[name] = (directory / name).read_bytes()
            result['files'][name] = {**before[name], 'sha256': sha(blobs[name])}
        except OSError as error:
            result['errors'].append(name + ': ' + str(error))
    for name, state in before.items():
        try:
            if state != file_state(directory / name):
                result['errors'].append(name + ' changed while the snapshot was captured')
        except OSError as error:
            result['errors'].append(name + ': ' + str(error))
    try:
        research = json.loads(blobs['research.json'])
        manifest = json.loads(blobs['manifest.json'])
        embedded = extract_research_script(blobs['index.html'].decode('utf-8'))
        parsed = json.loads(embedded)
        result['datasetVersion'] = research['dataset_version']
        result['embeddedResearch'] = {'sha256': sha(embedded.encode('utf-8')),
                                      'bytes': len(embedded.encode('utf-8')),
                                      'datasetVersion': parsed.get('dataset_version'),
                                      'semanticallyMatchesResearch': parsed == research}
        if parsed != research:
            result['errors'].append('Embedded research and research.json differ semantically')
        if manifest.get('dataset_version') != research['dataset_version']:
            result['errors'].append('Manifest dataset version differs from research.json')
        for name in ('index.html', 'research.json'):
            if manifest.get('sha256', {}).get(name) != result['files'][name]['sha256']:
                result['errors'].append('Manifest hash differs from current ' + name)
    except (KeyError, ValueError, UnicodeError) as error:
        result['errors'].append('Cannot reconcile dist identity: ' + str(error))
    result['valid'] = not result['errors']
    return result


def expected_browser_identity(snapshot: dict) -> dict:
    if not snapshot['valid']:
        raise ValueError('Dist snapshot is inconsistent: ' + '; '.join(snapshot['errors']))
    return {'datasetVersion': snapshot['datasetVersion'],
            'researchScriptSha256': snapshot['embeddedResearch']['sha256'],
            'researchFileSha256': snapshot['files']['research.json']['sha256']}


def checkpoint_build_identity(snapshot: dict) -> dict:
    """Include every required file identity so old cursors cannot skip a rebuild."""
    expected_browser_identity(snapshot)
    return {'datasetVersion': snapshot['datasetVersion'],
            'files': {name: snapshot['files'][name]['sha256'] for name in FILES},
            'researchScriptSha256': snapshot['embeddedResearch']['sha256']}


def assess_build_identity(before: dict, after: dict, browser: dict | None) -> dict:
    errors = []
    for label, snapshot in [('before', before), ('after', after)]:
        if not snapshot.get('valid'):
            errors.extend(label + ': ' + text for text in snapshot.get('errors', ['Missing valid snapshot']))
    changed = [name for name in FILES if before.get('files', {}).get(name) != after.get('files', {}).get(name)]
    if changed:
        errors.append('Dist files changed during the CLI invocation: ' + ', '.join(changed))
    actual = browser or {}
    expected = expected_browser_identity(before) if before.get('valid') else None
    for label in ('before', 'after'):
        observed = actual.get(label)
        if not observed:
            errors.append('Missing actual in-page identity ' + label + ' browser work')
            continue
        if expected:
            for key in ('datasetVersion', 'researchScriptSha256'):
                if observed.get(key) != expected[key]:
                    errors.append('In-page ' + key + ' differs from dist ' + label + ' browser work')
            fetched = observed.get('fetchedResearch', {})
            if fetched.get('sha256') != expected['researchFileSha256'] or fetched.get('status') != 200:
                errors.append('Uncached browser research.json differs from dist ' + label + ' browser work')
        if not observed.get('matchesExpected'):
            errors.extend(label + ' browser: ' + text for text in observed.get('errors', ['Browser comparison did not pass']))
    if actual.get('before') and actual.get('after'):
        for key in ('datasetVersion', 'researchScriptSha256', 'liveDataSemanticSha256'):
            if actual['before'].get(key) != actual['after'].get(key):
                errors.append('Actual in-page ' + key + ' changed during browser work')
    return {'schemaVersion': 1, 'passed': not errors, 'errors': errors,
            'diskBefore': before, 'diskAfter': after, 'browser': actual,
            'identityScope': 'Actual in-page research script and live DATA, uncached research.json, '
                             'and stable before/after disk index.html, manifest.json and research.json. '
                             'Disk hashes do not independently identify an already-loaded original HTML response.'}


def attach_build_identity(report: dict, before: dict, after: dict) -> None:
    assessment = assess_build_identity(before, after, report.get('browserBuildIdentity'))
    report['testedBuildIdentity'] = assessment
    report.pop('testedBuild', None)
    report.pop('testedPageBuild', None)
    check = {'scenario': 'build-identity', 'name': 'Browser research matches a stable tested disk build',
             'pass': assessment['passed'], 'details': {'errors': assessment['errors']}}
    report.setdefault('checks', []).append(check)
    report['failures'] = [row for row in report['checks'] if not row['pass']]
    summary = report.setdefault('summary', {})
    summary.update(checks=len(report['checks']), failures=len(report['failures']),
                   buildIdentityPassed=assessment['passed'])
