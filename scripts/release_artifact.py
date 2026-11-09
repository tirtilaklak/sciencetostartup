"""Prepare an exact static release and upload assets using a short-lived session JWT.

Account-authorized session/version/deployment calls use the connected Cloudflare API.
This helper handles only local files and the asset API's distinct upload authorization.
"""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_artifact(directory):
    directory = directory.resolve()
    manifest_bytes = (directory / 'manifest.json').read_bytes()
    release = json.loads(manifest_bytes)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(release['sha256']) | {'manifest.json'}:
        raise ValueError('Artifact file set differs from its tested manifest')
    for name in sorted(actual):
        path = directory / name
        content = path.read_bytes()
        if name != 'manifest.json' and digest(content) != release['sha256'][name]:
            raise ValueError('Artifact digest differs: ' + name)
    return release, manifest_bytes, actual


def prepare(directory, output, source_commit):
    directory = directory.resolve()
    release, manifest_bytes, actual = validate_artifact(directory)
    assets, lookup = {}, {}
    for name in sorted(actual):
        path = directory / name
        content = path.read_bytes()
        if name in ('_headers', '_redirects'):
            continue
        encoded = base64.b64encode(content)
        file_hash = digest(encoded + path.suffix.lstrip('.').encode())[:32]
        assets['/' + name] = {'hash': file_hash, 'size': len(content)}
        lookup[file_hash] = name
    config = json.loads((ROOT / 'deployment.json').read_text())
    asset_config = {**config['assets'], '_headers': (directory / '_headers').read_text()}
    metadata = {'assets': {'config': asset_config}, 'compatibility_date': config['compatibility_date'],
                'compatibility_flags': config['compatibility_flags'], 'usage_model': config['usage_model'],
                'annotations': {'workers/commit_sha': source_commit,
                                'workers/message': f"ScienceToStartup build {release['build_id']}; editorial {release['editorial_release_id']}; manifest {digest(manifest_bytes)}"}}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'assets-manifest.json').write_text(json.dumps({'manifest': assets}, separators=(',', ':')) + '\n')
    (output / 'asset-lookup.json').write_text(json.dumps(lookup, sort_keys=True) + '\n')
    (output / 'version-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    receipt = {'source_commit': source_commit, 'build_id': release['build_id'], 'editorial_release_id': release['editorial_release_id'],
               'manifest_sha256': digest(manifest_bytes), 'publication_as_of': release['publication_as_of'],
               'artifact_directory': str(directory), 'assets': len(assets), 'cloudflare_worker': config['worker'],
               'deployment_config_sha256': digest((ROOT / 'deployment.json').read_bytes()),
               'preserved_non_versioned_settings': config['non_versioned_settings']}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def secret_file(path, value):
    path = path.resolve()
    if ROOT == path or ROOT in path.parents:
        raise ValueError('Temporary authorization must stay outside the repository')
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream)
    os.chmod(path, 0o600)


def upload(directory, prepared, session_path, completion_path):
    release, manifest_bytes, _ = validate_artifact(directory)
    receipt = json.loads((prepared / 'receipt.json').read_text())
    if release['build_id'] != receipt['build_id'] or digest(manifest_bytes) != receipt['manifest_sha256']:
        raise ValueError('Prepared release and artifact identities differ')
    if digest((ROOT / 'deployment.json').read_bytes()) != receipt['deployment_config_sha256']:
        raise ValueError('Deployment configuration changed after release preparation')
    session = json.loads(session_path.read_text())
    lookup = json.loads((prepared / 'asset-lookup.json').read_text())
    config = json.loads((ROOT / 'deployment.json').read_text())
    jwt, buckets = session['jwt'], session['buckets']
    completion = jwt if not buckets else None
    uploaded = 0
    for bucket in buckets:
        boundary = 'ScienceToStartup' + uuid.uuid4().hex
        parts = []
        for file_hash in bucket:
            name = lookup[file_hash]
            content = (directory / name).read_bytes()
            mime = 'application/vnd.sqlite3' if name.endswith('.sqlite') else mimetypes.guess_type(name)[0] or 'application/octet-stream'
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{file_hash}"; filename="{file_hash}"\r\nContent-Type: {mime}\r\n\r\n').encode() + base64.b64encode(content) + b'\r\n')
        body = b''.join(parts) + f'--{boundary}--\r\n'.encode()
        url = f"https://api.cloudflare.com/client/v4/accounts/{config['account_id']}/workers/assets/upload?base64=true"
        request = Request(url, data=body, method='POST', headers={'Authorization': 'Bearer ' + jwt, 'Content-Type': 'multipart/form-data; boundary=' + boundary})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=120) as response:
                    result = json.loads(response.read())
                if not result.get('success'):
                    raise ValueError('Asset upload was not accepted')
                completion = result.get('result', {}).get('jwt') or completion
                uploaded += len(bucket)
                break
            except HTTPError as error:
                if error.code >= 500 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise ValueError('Asset upload failed with HTTP ' + str(error.code)) from None
    if not completion:
        raise ValueError('Assets uploaded but no completion authorization was returned')
    secret_file(completion_path, {'jwt': completion})
    return {'uploaded_assets': uploaded, 'buckets': len(buckets), 'completion_stored': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--dist', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--source-commit', required=True)
    send = sub.add_parser('upload')
    send.add_argument('--dist', type=Path, required=True)
    send.add_argument('--prepared', type=Path, required=True)
    send.add_argument('--session', type=Path, required=True)
    send.add_argument('--completion', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.dist, args.output, args.source_commit) if args.command == 'prepare' else upload(args.dist.resolve(), args.prepared, args.session, args.completion)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
