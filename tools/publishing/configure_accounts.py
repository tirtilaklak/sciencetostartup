#!/usr/bin/env python3
"""Explicit local credential entry and GET-only publishing-account checks.

No token arguments, environment discovery, publication imports, uploads, draft
creation, DOI reservation, or policy changes. Run in the user's own terminal.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import warnings


CONFIG = Path.home() / ".config/sciencetostartup/publishing-credentials.json"
TOKEN_KEYS = ("zenodo_production_token", "zenodo_sandbox_token", "hf_token")
ALLOWED_KEYS = {"schema_version", *TOKEN_KEYS, "hf_repository"}
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
USER_AGENT = "ScienceToStartup-account-check/1.0 (+https://sciencetostartup.com/research/)"


class SetupError(ValueError):
    """Messages intentionally exclude secrets and server-controlled strings."""


def validate_token(value):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in value):
        raise SetupError("A token must be nonempty printable ASCII without whitespace.")
    return value


def validate_repository(value):
    if not isinstance(value, str) or not REPOSITORY.fullmatch(value) or ".." in value:
        raise SetupError("Use a Hugging Face repository in namespace/dataset-name form.")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SetupError("Credential JSON contains a duplicate key; inspect locally.")
        result[key] = value
    return result


def _validate_config(value):
    if not isinstance(value, dict) or set(value) - ALLOWED_KEYS or value.get("schema_version") != 1 or type(value.get("schema_version")) is not int:
        raise SetupError("Credential schema is unsupported; inspect locally.")
    for key in TOKEN_KEYS:
        if key in value:
            validate_token(value[key])
    if "hf_repository" in value:
        validate_repository(value["hf_repository"])
    return value


def _check_ancestors(path):
    if not path.is_absolute() or ".." in path.parts:
        raise SetupError("Credential path must be an absolute normalized path.")
    for part in reversed((path.parent, *path.parent.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SetupError("Credential parent paths must be real directories, without symlinks.")
    try:
        info = path.parent.lstat()
    except FileNotFoundError:
        return
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SetupError("Credential directory must be owned by this user with mode 0700.")


def _private_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise SetupError("Credential and lock files must be regular, single-link, user-owned files with mode 0600.")


def load_credentials(path=CONFIG):
    path = Path(path)
    _check_ancestors(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {"schema_version": 1}
    except OSError:
        raise SetupError("Cannot safely open credential file; inspect locally.") from None
    try:
        _private_file(os.fstat(descriptor))
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            try:
                raw = stream.read(65537)
            except UnicodeError:
                raise SetupError("Credential JSON is invalid; inspect locally.") from None
        if len(raw) > 65536:
            raise SetupError("Credential file is unexpectedly large; inspect locally.")
        try:
            value = json.loads(raw, object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError):
            raise SetupError("Credential JSON is invalid; inspect locally.") from None
        return _validate_config(value)
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _write_lock(path):
    _check_ancestors(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _check_ancestors(path)
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        raise SetupError("Cannot safely open credential lock; inspect locally.") from None
    try:
        _private_file(os.fstat(descriptor))
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SetupError("Another account setup is writing credentials; retry when it finishes.") from None
        yield
    finally:
        os.close(descriptor)


def merge_credentials(changes, path=CONFIG):
    """Re-read under lock, preserve the other service, and atomically replace."""
    if not changes:
        return load_credentials(path)
    if not isinstance(changes, dict) or set(changes) - (ALLOWED_KEYS - {"schema_version"}):
        raise SetupError("Unsupported credential fields.")
    _validate_config({"schema_version": 1, **changes})
    path = Path(path)
    with _write_lock(path):
        current = load_credentials(path)
        updated = _validate_config({**current, **changes})
        descriptor, temporary = tempfile.mkstemp(prefix=".publishing-credentials-", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(updated, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return updated


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_json(url, token):
    """Fixed-origin callers only. Never expose request/server exception details."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in {"zenodo.org", "sandbox.zenodo.org", "huggingface.co"}
            or parsed.username or parsed.password or parsed.fragment or "access_token" in parsed.query.lower()):
        return {"status": "blocked_origin"}
    validate_token(token)
    if parsed.netloc in {"zenodo.org", "sandbox.zenodo.org"}:
        endpoint_allowed = parsed.path == "/api/deposit/depositions" and parsed.query == "size=1"
    else:
        dataset = parsed.path.removeprefix("/api/datasets/")
        endpoint_allowed = not parsed.query and (parsed.path == "/api/whoami-v2" or (
            parsed.path.startswith("/api/datasets/") and REPOSITORY.fullmatch(dataset) and ".." not in dataset))
    if not endpoint_allowed or token in url:
        return {"status": "blocked_endpoint"}
    request = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + token, "Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        # Disable ambient proxies and every redirect, including same-origin ones.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=25) as response:
            raw = response.read(1048577)
            if response.status != 200 or len(raw) > 1048576:
                return {"status": "unexpected_response"}
            try:
                return {"status": "ok", "data": json.loads(raw, object_pairs_hook=_unique_object)}
            except (ValueError, UnicodeError):
                return {"status": "invalid_json"}
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        status = {401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited"}.get(code, "http_error")
        if 300 <= code < 400:
            status = "redirect_blocked"
        return {"status": status, "http_status": code}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"status": "network_or_tls_error"}


def check_zenodo(token, sandbox=False, fetch=get_json):
    if not token:
        return {"status": "not_configured", "write_scopes": "unverified"}
    origin = "https://sandbox.zenodo.org" if sandbox else "https://zenodo.org"
    result = fetch(origin + "/api/deposit/depositions?size=1", token)
    status = result["status"]
    if status == "ok":
        status = "authenticated_read" if isinstance(result.get("data"), list) else "unexpected_response"
    # A read success does not prove deposit:write or deposit:actions.
    return {"status": status, **({"http_status": result["http_status"]} if "http_status" in result else {}),
            "write_scopes": "unverified"}


def check_huggingface(token, repository, fetch=get_json):
    if not token:
        return {"status": "not_configured", "repository_status": "not_checked", "write_access": "unverified"}
    result = fetch("https://huggingface.co/api/whoami-v2", token)
    safe = {"status": result["status"], "repository_status": "not_checked", "write_access": "unverified"}
    if "http_status" in result:
        safe["http_status"] = result["http_status"]
    if result["status"] != "ok":
        return safe
    data = result.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", data["name"]):
        safe["status"] = "unexpected_response"
        return safe
    safe.update(status="authenticated_read", account=data["name"] if data["name"] != token else "withheld")
    auth = data.get("auth", {})
    access = auth.get("accessToken", {}) if isinstance(auth, dict) else {}
    role = access.get("role") if isinstance(access, dict) else None
    if isinstance(role, str) and role in {"read", "write", "god", "fineGrained"}:
        safe["reported_token_role"] = role
    if not repository:
        safe["repository_status"] = "not_configured"
        return safe
    validate_repository(repository)
    repo = fetch("https://huggingface.co/api/datasets/" + repository, token)
    safe["repository_status"] = repo["status"]
    if "http_status" in repo:
        safe["repository_http_status"] = repo["http_status"]
    if repo["status"] == "ok":
        info = repo.get("data")
        if not isinstance(info, dict) or info.get("id") != repository:
            safe["repository_status"] = "unexpected_response"
        else:
            safe["repository_status"] = "readable"
            if type(info.get("private")) is bool:
                safe["repository_private"] = info["private"]
            if isinstance(info.get("sha"), str) and re.fullmatch(r"[0-9a-f]{40,64}", info["sha"]):
                safe["repository_commit"] = info["sha"]
    return safe


def connection_status(credentials, service="all", network=True):
    results = {"schema_version": 1, "publication_enabled": False, "check_mode": "GET_only" if network else "presence_only"}
    if service in {"all", "zenodo"}:
        for label, sandbox in (("zenodo_production", False), ("zenodo_sandbox", True)):
            token = credentials.get(label + "_token")
            results[label] = check_zenodo(token, sandbox) if network else {"configured": bool(token)}
    if service in {"all", "huggingface"}:
        token, repository = credentials.get("hf_token"), credentials.get("hf_repository")
        results["huggingface"] = check_huggingface(token, repository) if network else {
            "token_configured": bool(token), "repository_configured": bool(repository)}
    return results


def collect_changes(service):
    if not sys.stdin.isatty():
        raise SetupError("Run account entry in your own interactive terminal; piped input is refused.")
    changes = {}
    prompts = []
    if service in {"all", "zenodo"}:
        prompts.extend((("zenodo_production_token", "Zenodo PRODUCTION token (hidden; blank keeps current): "),
                        ("zenodo_sandbox_token", "Zenodo SANDBOX token (hidden; blank keeps current): ")))
    if service in {"all", "huggingface"}:
        prompts.append(("hf_token", "Hugging Face token (hidden; blank keeps current): "))
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        for key, prompt in prompts:
            try:
                value = getpass.getpass(prompt).strip()
            except getpass.GetPassWarning:
                raise SetupError("Hidden token entry is unavailable; no token was saved.") from None
            if value:
                changes[key] = validate_token(value)
    if service in {"all", "huggingface"}:
        repository = input("Hugging Face dataset repository namespace/name (blank keeps current): ").strip()
        if repository:
            changes["hf_repository"] = validate_repository(repository)
    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=("all", "zenodo", "huggingface"), default="all")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true", help="GET-only checks using locally stored credentials; no prompts or writes")
    mode.add_argument("--status", action="store_true", help="nonsecret presence only; no network, prompts, or writes")
    args = parser.parse_args(argv)
    try:
        credentials = load_credentials(CONFIG)
        if not args.check_only and not args.status:
            print("Tokens stay in the private user config; blank inputs preserve current values.")
            credentials = merge_credentials(collect_changes(args.service), CONFIG)
        report = connection_status(credentials, args.service, network=not args.status)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.status:
            return 0
        services = [v for v in report.values() if isinstance(v, dict)]
        return 0 if all(v.get("status") == "authenticated_read" and v.get("repository_status", "readable") == "readable" for v in services) else 2
    except SetupError as error:
        # SetupError messages are constant local strings without input values.
        print("Account setup stopped: " + str(error), file=sys.stderr)
        return 1
    except OSError:
        # Never print exception repr, user-supplied values, paths or server bodies.
        print("Account setup could not complete a local file operation safely; inspect file access locally.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Account entry cancelled; rerun --status to inspect whether credentials were saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
