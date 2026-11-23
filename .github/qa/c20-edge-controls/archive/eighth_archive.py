"""Bind the hosted archive smoke check to the bytes in the checkout's dist manifest."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/c20-controls/eighth-archive.json'))
    args = parser.parse_args()
    base = os.environ.get('QA_BASE_URL', '').rstrip('/')
    parts = urlsplit(base)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.path or parts.query or parts.fragment or parts.username:
        parser.error('QA_BASE_URL must be a site origin')
    artifact = Path(os.environ.get('QA_DIST', 'dist')).resolve()
    manifest_bytes = (artifact / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    expected = sha256(manifest_bytes).hexdigest()
    raw_report = args.output.resolve()
    identity_report = raw_report.with_suffix('.identity.json')
    if raw_report.exists() or identity_report.exists():
        parser.error('report already exists; select a new --output for a retry')
    raw_report.parent.mkdir(parents=True, exist_ok=True)

    def bind_origin():
        request = Request(base + '/manifest.json', headers={
            'Cache-Control': 'no-cache', 'User-Agent': 'ScienceToStartup-ReleaseVerification/1.0',
        })
        with urlopen(request, timeout=30) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                raise ValueError('archive manifest returned an unexpected response')
            return sha256(response.read()).hexdigest()

    identity = {'passed': False, 'origin': base, 'before': None, 'after': None,
                'build': manifest['build_id'], 'http_checks': 0, 'browser_steps': 0}
    errors = []
    try:
        identity['before'] = bind_origin()
        if identity['before'] != expected:
            raise ValueError('archive origin differs from dist before the check')
        subprocess.run(['node', str(Path(__file__).resolve().with_name('verify-release.cjs'))], check=True, env={
            **os.environ, 'QA_BASE_URL': base, 'QA_DIST': str(artifact), 'ARCHIVE_RECEIPT': str(raw_report),
        })
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        errors.append(str(error))
    finally:
        try:
            identity['after'] = bind_origin()
            if identity['after'] != expected:
                errors.append('archive origin differs from dist after the check')
        except (OSError, ValueError) as error:
            errors.append(str(error))
        if raw_report.exists():
            try:
                reports = json.loads(raw_report.read_bytes())
                if len(reports) != 1:
                    raise ValueError('expected one archive report')
                record = reports[0]
                identity['http_checks'] = len(record['routes'])
                identity['browser_steps'] = len(record['browser'])
                if record.get('error'):
                    errors.append(record['error']['message'])
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(str(error))
        if (identity['http_checks'], identity['browser_steps']) != (26, 8):
            errors.append('archive verification did not complete all 26 HTTP checks and 8 browser steps')
        identity['passed'] = not errors and identity['before'] == identity['after'] == expected
        if errors:
            identity['errors'] = errors
        identity_report.write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps(identity), flush=True)
    return 0 if identity['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
