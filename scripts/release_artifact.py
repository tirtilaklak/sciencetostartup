"""Validate frozen releases and dispatch one admitted asset bucket without retries.

The caller supplies trusted identities and coordinates Cloudflare operations. Account
session/version/deployment calls remain in the connected API. JWTs stay in private files.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener
import uuid
from research_citations import STATIC_ASSET_LIMIT_BYTES

ROOT = Path(__file__).absolute().parents[1]
PREPARED_FILES = ('assets-manifest.json', 'asset-lookup.json', 'version-metadata.json', 'receipt.json')
SESSION_KEYS = {'worker', 'source_commit', 'manifest_sha256', 'plan_sha256', 'run_id', 'session_operation_id', 'buckets_sha256'}
HEX = {n: re.compile(r'[0-9a-f]{' + str(n) + r'}\Z') for n in (32, 40, 64)}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def strict_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(content, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid JSON document') from None


def absolute(path):
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('Parent traversal is not allowed')
    return path.absolute()


@contextmanager
def directory_fd(path):
    """Walk directory handles without following even a raced parent symlink."""
    path = absolute(path)
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except OSError:
                raise ValueError('Directory must exist without symlinks: ' + str(path)) from None
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def regular_bytes(path, limit=STATIC_ASSET_LIMIT_BYTES, *, private=False):
    path = absolute(path)
    with directory_fd(path.parent) as parent:
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError:
            raise ValueError('Expected a regular file without symlinks: ' + str(path)) from None
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Expected a regular file: ' + str(path))
            if private and (info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError('Authorization file must remain private and unlinked')
            if info.st_size > limit:
                raise ValueError('Static asset exceeds the hosting limit: ' + path.name)
            content = stream.read(limit + 1)
            if len(content) > limit:
                raise ValueError('Static asset exceeds the hosting limit: ' + path.name)
            return content


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('Invalid artifact path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise ValueError('Invalid artifact path')
    return name


def hex_value(value, size, label):
    if not isinstance(value, str) or not HEX[size].fullmatch(value):
        raise ValueError('Invalid ' + label)
    return value


def inventory(directory):
    directory = absolute(directory)
    with directory_fd(directory):
        pass
    files = set()
    for parent, directories, names in os.walk(directory, followlinks=False):
        for name in directories + names:
            path = Path(parent) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError('Unsafe artifact entry: ' + str(path))
            if stat.S_ISREG(info.st_mode):
                files.add(safe_name(path.relative_to(directory).as_posix()))
    return files


def validate_artifact(directory, expected_manifest_sha256=None):
    directory = absolute(directory)
    manifest_bytes = regular_bytes(directory / 'manifest.json')
    if expected_manifest_sha256 is not None and digest(manifest_bytes) != hex_value(expected_manifest_sha256, 64, 'expected manifest digest'):
        raise ValueError('Artifact differs from the trusted manifest')
    release = strict_json(manifest_bytes)
    if not isinstance(release, dict) or not isinstance(release.get('sha256'), dict):
        raise ValueError('Invalid artifact manifest')
    for key in ('build_id', 'editorial_release_id', 'publication_as_of'):
        if not isinstance(release.get(key), str) or not release[key]:
            raise ValueError('Invalid artifact identity: ' + key)
    for name, checksum in release['sha256'].items():
        safe_name(name)
        if name == 'manifest.json':
            raise ValueError('Artifact manifest cannot hash itself')
        hex_value(checksum, 64, 'artifact digest')
    actual = inventory(directory)
    if actual != set(release['sha256']) | {'manifest.json'}:
        raise ValueError('Artifact file set differs from its tested manifest')
    for name in sorted(actual):
        content = regular_bytes(directory / name, STATIC_ASSET_LIMIT_BYTES)
        expected = manifest_bytes if name == 'manifest.json' else None
        if (expected is not None and content != expected) or (expected is None and digest(content) != release['sha256'][name]):
            raise ValueError('Artifact digest differs: ' + name)
    return release, manifest_bytes, actual


def artifact_bytes(directory, name, release, manifest_bytes):
    content = regular_bytes(directory / safe_name(name), STATIC_ASSET_LIMIT_BYTES)
    checksum = digest(manifest_bytes) if name == 'manifest.json' else release['sha256'][name]
    if digest(content) != checksum:
        raise ValueError('Artifact digest differs: ' + name)
    return content


def cloudflare_hash(content, name):
    return digest(base64.b64encode(content) + Path(name).suffix.lstrip('.').encode())[:32]


def derive_plan(directory, source_commit, expected_manifest_sha256=None):
    directory = absolute(directory)
    hex_value(source_commit, 40, 'source commit')
    release, manifest_bytes, actual = validate_artifact(directory, expected_manifest_sha256)
    config_bytes = regular_bytes(ROOT / 'deployment.json')
    config = strict_json(config_bytes)
    if not isinstance(config, dict) or not isinstance(config.get('worker'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', config['worker']):
        raise ValueError('Invalid deployment worker')
    hex_value(config.get('account_id'), 32, 'deployment account')
    assets, lookup, hash_contents = {}, {}, {}
    for name in sorted(actual):
        content = artifact_bytes(directory, name, release, manifest_bytes)
        if name in ('_headers', '_redirects'):
            continue
        file_hash = cloudflare_hash(content, name)
        fingerprint = (digest(content), len(content))
        if file_hash in hash_contents and hash_contents[file_hash] != fingerprint:
            raise ValueError('Different content shares a Cloudflare hash')
        hash_contents[file_hash] = fingerprint
        assets['/' + name] = {'hash': file_hash, 'size': len(content)}
        lookup.setdefault(file_hash, name)
    headers = artifact_bytes(directory, '_headers', release, manifest_bytes).decode('utf-8')
    metadata = {'assets': {'config': {**config['assets'], '_headers': headers}},
                'compatibility_date': config['compatibility_date'], 'compatibility_flags': config['compatibility_flags'],
                'usage_model': config['usage_model'], 'annotations': {'workers/commit_sha': source_commit,
                'workers/message': f"ScienceToStartup build {release['build_id']}; editorial {release['editorial_release_id']}; manifest {digest(manifest_bytes)}"}}
    receipt = {'source_commit': source_commit, 'build_id': release['build_id'], 'editorial_release_id': release['editorial_release_id'],
               'manifest_sha256': digest(manifest_bytes), 'publication_as_of': release['publication_as_of'],
               'artifact_directory': str(directory), 'assets': len(assets), 'cloudflare_worker': config['worker'],
               'deployment_config_sha256': digest(config_bytes), 'preserved_non_versioned_settings': config['non_versioned_settings']}
    documents = {'assets-manifest.json': {'manifest': assets}, 'asset-lookup.json': lookup, 'version-metadata.json': metadata}
    # Local paths are recorded in the receipt, but are not portable release semantics.
    identity = {k: v for k, v in receipt.items() if k != 'artifact_directory'}
    receipt['plan_sha256'] = digest(canonical({'documents': documents, 'identity': identity}))
    return {'documents': documents, 'receipt': receipt, 'release': release, 'manifest_bytes': manifest_bytes, 'config': config}


def separate_paths(left, right, label):
    left, right = absolute(left), absolute(right)
    if left == right or left in right.parents or right in left.parents:
        raise ValueError(label + ' paths must not overlap')


def check_prepared(plan, prepared):
    prepared = absolute(prepared)
    separate_paths(plan['receipt']['artifact_directory'], prepared, 'Artifact and preparation')
    inventory(prepared)
    for name, expected in plan['documents'].items():
        if canonical(strict_json(regular_bytes(prepared / name))) != canonical(expected):
            raise ValueError('Prepared plan differs: ' + name)
    receipt = strict_json(regular_bytes(prepared / 'receipt.json'))
    if not isinstance(receipt, dict) or any(k not in receipt or canonical(receipt[k]) != canonical(v) for k, v in plan['receipt'].items()):
        raise ValueError('Prepared receipt identity differs')
    return receipt


def prepare(directory, output, source_commit):
    directory, output = absolute(directory), absolute(output)
    separate_paths(directory, output, 'Artifact and preparation')
    plan = derive_plan(directory, source_commit)
    if output.exists():
        with directory_fd(output):
            pass
        if list(output.iterdir()):
            check_prepared(plan, output)
            return dict(plan['receipt'])
    else:
        with directory_fd(output.parent):
            pass
        output.mkdir()
    for name, value in {**plan['documents'], 'receipt.json': plan['receipt']}.items():
        # Exclusive creation never overwrites receipt history or a conflicting plan.
        with directory_fd(output) as parent:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(canonical(value) + b'\n')
    return dict(plan['receipt'])


def validate_prepared(directory, prepared, *, expected_source_commit, expected_worker, expected_manifest_sha256, expected_plan_sha256):
    hex_value(expected_plan_sha256, 64, 'expected plan digest')
    plan = derive_plan(directory, expected_source_commit, expected_manifest_sha256)
    if expected_worker != plan['receipt']['cloudflare_worker'] or expected_plan_sha256 != plan['receipt']['plan_sha256']:
        raise ValueError('Prepared release differs from trusted worker or plan')
    check_prepared(plan, prepared)
    return {'receipt': dict(plan['receipt']), 'assets_manifest': plan['documents']['assets-manifest.json'],
            'asset_lookup': plan['documents']['asset-lookup.json'], 'version_metadata': plan['documents']['version-metadata.json'],
            'plan_sha256': plan['receipt']['plan_sha256']}


def private_path(path, forbidden=()):
    path = absolute(path)
    for boundary in (ROOT, *forbidden):
        boundary = absolute(boundary)
        if path == boundary or boundary in path.parents:
            raise ValueError('Temporary authorization must stay outside the repository, artifact and preparation')
    # Cover other worktrees/checkouts too, without reading their Git metadata.
    if any((parent / '.git').exists() for parent in path.parents):
        raise ValueError('Temporary authorization must stay outside the repository')
    with directory_fd(path.parent) as parent:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Authorization directory must be private to its owner')
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return path
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Authorization file must be a private regular file without links')
    return path


def secret_file(path, value, forbidden=()):
    path = private_path(path, forbidden)
    with directory_fd(path.parent) as parent:
        name = '.authorization-' + uuid.uuid4().hex
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(canonical(value) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass


def validate_session(session, validated, expected_binding):
    if not isinstance(session, dict) or set(session) != {'jwt', 'buckets', 'binding'}:
        raise ValueError('Invalid upload session object')
    if not isinstance(session['jwt'], str) or not session['jwt'].strip() or any(ord(c) < 32 for c in session['jwt']):
        raise ValueError('Invalid upload authorization')
    buckets = session['buckets']
    if not isinstance(buckets, list):
        raise ValueError('Upload buckets must be an array')
    seen = set()
    for bucket in buckets:
        if not isinstance(bucket, list) or not bucket:
            raise ValueError('Each upload bucket must be a nonempty array')
        for file_hash in bucket:
            hex_value(file_hash, 32, 'bucket hash')
            if file_hash not in validated['asset_lookup'] or file_hash in seen:
                raise ValueError('Unknown or duplicate upload hash')
            seen.add(file_hash)
    if not isinstance(expected_binding, dict) or set(expected_binding) != SESSION_KEYS or session['binding'] != expected_binding:
        raise ValueError('Upload session differs from trusted binding')
    receipt = validated['receipt']
    for key, value in {'worker': receipt['cloudflare_worker'], 'source_commit': receipt['source_commit'],
                       'manifest_sha256': receipt['manifest_sha256'], 'plan_sha256': receipt['plan_sha256'],
                       'buckets_sha256': digest(canonical(buckets))}.items():
        if expected_binding[key] != value:
            raise ValueError('Upload session differs from trusted ' + key)
    for key in ('run_id', 'session_operation_id'):
        if not isinstance(expected_binding[key], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}', expected_binding[key]):
            raise ValueError('Invalid session operation identity')
    return buckets


class UploadOutcomeError(ValueError):
    """Sanitized remote outcome; callers must never infer retry permission from exit code."""
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


urlopen = build_opener(NoRedirect()).open


def upload_bucket(directory, prepared, session_path, completion_path, bucket_index, *, expected_source_commit,
                  expected_worker, expected_manifest_sha256, expected_plan_sha256, expected_session_binding,
                  expected_run_id, expected_session_operation_id, expected_operation_id=None):
    directory, prepared = absolute(directory), absolute(prepared)
    validated = validate_prepared(directory, prepared, expected_source_commit=expected_source_commit,
        expected_worker=expected_worker, expected_manifest_sha256=expected_manifest_sha256, expected_plan_sha256=expected_plan_sha256)
    session_path = private_path(session_path, (directory, prepared))
    completion_path = private_path(completion_path, (directory, prepared))
    separate_paths(session_path, completion_path, 'Authorization input and output')
    session = strict_json(regular_bytes(session_path, 1_000_000, private=True))
    buckets = validate_session(session, validated, expected_session_binding)
    if expected_session_binding['run_id'] != expected_run_id or expected_session_binding['session_operation_id'] != expected_session_operation_id:
        raise ValueError('Upload session differs from independently expected run or session operation')
    result = {'uploaded_assets': 0, 'buckets': 0, 'total_buckets': len(buckets), 'completion_stored': False,
              'dispatched': False, 'outcome': 'not_sent', 'operation_id': expected_operation_id,
              'session_operation_id': expected_session_operation_id, 'run_id': expected_run_id, 'plan_sha256': expected_plan_sha256,
              'source_commit': expected_source_commit, 'worker': expected_worker, 'manifest_sha256': expected_manifest_sha256}
    if not buckets:
        if bucket_index is not None or expected_operation_id is not None:
            raise ValueError('Zero buckets must not invent an upload operation')
        secret_file(completion_path, {'jwt': session['jwt']}, (directory, prepared))
        return {**result, 'completion_stored': True}
    if isinstance(bucket_index, bool) or not isinstance(bucket_index, int) or not 0 <= bucket_index < len(buckets):
        raise ValueError('Invalid upload bucket index')
    if not isinstance(expected_operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}', expected_operation_id):
        raise ValueError('An admitted upload operation identity is required')
    bucket = buckets[bucket_index]
    result.update(bucket_index=bucket_index, bucket_sha256=digest(canonical(bucket)), buckets=1)
    release, manifest_bytes, _ = validate_artifact(directory, expected_manifest_sha256)
    boundary, parts = 'ScienceToStartup' + uuid.uuid4().hex, []
    for file_hash in bucket:
        name = validated['asset_lookup'][file_hash]
        content = artifact_bytes(directory, name, release, manifest_bytes)
        if cloudflare_hash(content, name) != file_hash:
            raise ValueError('Upload content changed after preparation')
        mime = 'application/vnd.sqlite3' if name.endswith('.sqlite') else mimetypes.guess_type(name)[0] or 'application/octet-stream'
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{file_hash}"; filename="{file_hash}"\r\nContent-Type: {mime}\r\n\r\n').encode() + base64.b64encode(content) + b'\r\n')
    body = b''.join(parts) + f'--{boundary}--\r\n'.encode()
    config_bytes = regular_bytes(ROOT / 'deployment.json')
    config = strict_json(config_bytes)
    if digest(config_bytes) != validated['receipt']['deployment_config_sha256']:
        raise ValueError('Deployment configuration changed before dispatch')
    request = Request(f"https://api.cloudflare.com/client/v4/accounts/{config['account_id']}/workers/assets/upload?base64=true",
        data=body, method='POST', headers={'Authorization': 'Bearer ' + session['jwt'], 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    result.update(dispatched=True, outcome='uncertain')
    try:
        with urlopen(request, timeout=120) as response:
            status = response.status
            result['http_status'] = status
            response_bytes = response.read(1_000_001)
            if len(response_bytes) > 1_000_000:
                raise ValueError('Oversized asset upload response')
            payload = strict_json(response_bytes)
        if status not in (201, 202) or not isinstance(payload, dict) or payload.get('success') is not True or not isinstance(payload.get('result'), dict):
            raise ValueError('Unexpected asset upload response')
        completion = payload['result'].get('jwt')
        if status == 201 and (not isinstance(completion, str) or not completion.strip() or any(ord(c) < 32 for c in completion)):
            raise ValueError('Missing final completion authorization')
        if status == 202 and completion is not None:
            raise ValueError('Unexpected intermediate completion authorization')
    except HTTPError as error:
        result['http_status'] = error.code
        result['outcome'] = 'failed' if error.code in {400, 401, 403, 404, 405, 413, 415, 422, 429} else 'uncertain'
        error.close()
        raise UploadOutcomeError('Asset upload HTTP outcome requires recording', result) from None
    except Exception:
        raise UploadOutcomeError('Asset upload outcome is uncertain; do not retry', result) from None
    result.update(outcome='succeeded', uploaded_assets=len(bucket), remote_succeeded=True)
    if completion is not None:
        try:
            secret_file(completion_path, {'jwt': completion}, (directory, prepared))
        except (OSError, ValueError):
            raise UploadOutcomeError('Asset upload succeeded; private completion persistence failed', result) from None
        result['completion_stored'] = True
    return result


def upload(directory, prepared, session_path, completion_path, **expected):
    """Compatibility entrypoint; safe dispatch requires explicit trusted identities/index."""
    validate_artifact(directory)
    if not expected:
        raise ValueError('Trusted release and admitted bucket identities are required; use upload-bucket with --expected-* and --operation-id')
    return upload_bucket(directory, prepared, session_path, completion_path, **expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--dist', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--source-commit', required=True)
    for name in ('validate-prepared', 'upload-bucket', 'upload'):
        command = sub.add_parser(name)
        command.add_argument('--dist', type=Path, required=True)
        command.add_argument('--prepared', type=Path, required=True)
        for field in ('source-commit', 'worker', 'manifest-sha256', 'plan-sha256'):
            command.add_argument('--expected-' + field, required=True)
        if name != 'validate-prepared':
            command.add_argument('--session', type=Path, required=True)
            command.add_argument('--completion', type=Path, required=True)
            command.add_argument('--expected-run-id', required=True)
            command.add_argument('--expected-session-operation-id', required=True)
            command.add_argument('--expected-buckets-sha256', required=True)
            command.add_argument('--bucket-index', type=int)
            command.add_argument('--operation-id')
    args = vars(parser.parse_args())
    command, directory = args.pop('command'), args.pop('dist')
    try:
        if command == 'prepare':
            result = prepare(directory, args.pop('output'), args.pop('source_commit'))
        elif command == 'validate-prepared':
            result = validate_prepared(directory, **args)
        else:
            buckets_digest = hex_value(args.pop('expected_buckets_sha256'), 64, 'expected bucket inventory digest')
            args['expected_session_binding'] = {
                'worker': args['expected_worker'], 'source_commit': args['expected_source_commit'],
                'manifest_sha256': args['expected_manifest_sha256'], 'plan_sha256': args['expected_plan_sha256'],
                'run_id': args['expected_run_id'], 'session_operation_id': args['expected_session_operation_id'],
                'buckets_sha256': buckets_digest}
            args['expected_operation_id'] = args.pop('operation_id')
            args['session_path'] = args.pop('session')
            args['completion_path'] = args.pop('completion')
            result = upload_bucket(directory, **args)
    except UploadOutcomeError as error:
        print(json.dumps({'error': str(error), **error.result}))
        return 2
    except (ValueError, OSError) as error:
        # No raw remote response or authorization is exposed by these errors.
        print(json.dumps({'error': str(error), 'dispatched': False, 'outcome': 'not_sent'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
