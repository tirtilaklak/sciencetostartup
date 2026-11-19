#!/usr/bin/env python3
"""Build reviewed Daily source on an isolated candidate branch, never publication."""
import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from zoneinfo import ZoneInfo

REPOSITORY = "tirtilaklak/sciencetostartup"
BRANCH = re.compile(r"codex/cloud-daily-(\d{4}-\d{2}-\d{2})\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_KEYS = {"date", "baseline_commit", "baseline_manifest_sha256", "outgoing_cloudflare_version",
                "daily_sha256", "compiled_at", "expected_candidate_manifest_sha256"}
GENERIC_HOLD_REASON = "candidate_builder_failed_no_automatic_retry"
# Only fixed diagnostic codes may reach CLI output; never stringify exceptions.
SAFE_HOLD_REASONS = frozenset("""
artifact_bounds artifact_digest artifact_file_set artifact_symlink artifact_too_large
baseline_html_digest baseline_manifest_mismatch baseline_mismatch candidate_build_or_verify_failed
candidate_digest committed_path_scope compiled_at_identity compiled_source_changed daily_digest_or_size
daily_identity daily_worktree_mismatch dirty_checkout dist_symlink fork_rejected frozen_candidate_mismatch
git_operation_failed head_moved historical_snapshot_changed input_diff_not_source_only invalid_commit
invalid_date invalid_outgoing_version invalid_previous_commit invalid_runtime_path nonregular_source
outgoing_already_retained prior_generation_digest push_commit push_failed_hold_read_branch_before_any_retry
push_head_moved push_parent push_remote push_scope push_token_bounds push_tree receipt_must_be_outside_checkout
repository_root_mismatch request_digest request_fields request_too_large retention_count retention_symlink
runtime_collision runtime_digest summary_identity unexpected_build_edit unexpected_retention_file
unknown_runtime_reference unsafe_git_config unsafe_output unsafe_path wrong_branch wrong_event wrong_repository
""".split())


class Hold(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def clean_environment(env=None):
    return {k: v for k, v in (os.environ if env is None else env).items()
            if not k.upper().startswith(("GIT_", "GCM_"))
            and not re.search(r"TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION|(?:^|_)KEY(?:_|$)", k, re.I)}


def valid_push_token(token):
    """Treat the credential as opaque, with only transport safety/size bounds."""
    if not isinstance(token, str) or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in token):
        return False
    try:
        return 1 <= len(token.encode("utf-8")) <= 16384
    except UnicodeEncodeError:
        return False


def git(repo, *args, env=None):
    environment = clean_environment() if env is None else dict(env)
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=repo,
                            env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, "git_operation_failed")  # Never echo credential-bearing errors.
    return result.stdout


def safe_path(name):
    require(isinstance(name, str) and len(name) <= 2048 and "\\" not in name
            and not re.search(r"[\x00-\x1f\x7f]", name), "unsafe_path")
    p = PurePosixPath(name)
    require(not p.is_absolute() and name == p.as_posix() and all(x not in ("", ".", "..") for x in name.split("/")), "unsafe_path")
    return name


def blob(repo, commit, name):
    safe_path(name)
    entry = git(repo, "ls-tree", "-z", commit, "--", name).split(b"\0")[0]
    require(entry.startswith(b"100644 blob ") and entry.endswith(b"\t" + name.encode()), "nonregular_source")
    return git(repo, "show", commit + ":" + name)


def changes(repo, before, after):
    parts = git(repo, "diff", "--name-status", "--no-renames", "-z", before, after).decode().split("\0")
    return list(zip(parts[0:-1:2], parts[1:-1:2]))


def preflight(repo, event):
    repo = Path(repo).resolve()
    require(git(repo, "rev-parse", "--show-toplevel").decode().strip() == str(repo), "repository_root_mismatch")
    require(event.get("repository", {}).get("full_name") == REPOSITORY, "wrong_repository")
    pr = event.get("pull_request", {})
    head, base = pr.get("head", {}), pr.get("base", {})
    require(head.get("repo", {}).get("full_name") == REPOSITORY
            and base.get("repo", {}).get("full_name") == REPOSITORY, "fork_rejected")
    match = BRANCH.fullmatch(head.get("ref", ""))
    require(match is not None and base.get("ref") == "main", "wrong_branch")
    day = match.group(1)
    require(date.fromisoformat(day).isoformat() == day, "invalid_date")
    source, baseline = head.get("sha", ""), base.get("sha", "")
    require(HEX40.fullmatch(source) and HEX40.fullmatch(baseline), "invalid_commit")
    require(git(repo, "rev-parse", "HEAD").decode().strip() == source, "head_moved")
    require(not git(repo, "status", "--porcelain", "--untracked-files=all"), "dirty_checkout")
    daily_path = "data/daily-scan/" + day + ".json"
    # App's same-tree checkpoint (and the builder commit) cannot cause another build.
    before = event.get("before")
    if event.get("action") == "synchronize" and before:
        require(HEX40.fullmatch(before), "invalid_previous_commit")
        if daily_path not in {p for _, p in changes(repo, before, source)}:
            return {"status": "no_source_change", "should_build": False}
    require(event.get("action") in {"opened", "reopened", "synchronize"}, "wrong_event")
    require(changes(repo, baseline, source) == [("A", daily_path)], "input_diff_not_source_only")
    git(repo, "merge-base", "--is-ancestor", baseline, source)
    body = pr.get("body", "")
    require(isinstance(body, str) and len(body.encode()) <= 4096, "request_too_large")
    request = json.loads(body)
    require(isinstance(request, dict) and set(request) == REQUEST_KEYS, "request_fields")
    require(request["date"] == day and request["baseline_commit"] == baseline, "baseline_mismatch")
    for key in ("baseline_manifest_sha256", "daily_sha256"):
        require(isinstance(request[key], str) and HEX64.fullmatch(request[key]), "request_digest")
    expected = request["expected_candidate_manifest_sha256"]
    require(expected is None or isinstance(expected, str) and HEX64.fullmatch(expected), "candidate_digest")
    version = request["outgoing_cloudflare_version"]
    require(isinstance(version, str) and str(uuid.UUID(version)) == version, "invalid_outgoing_version")
    daily = blob(repo, source, daily_path)
    require(len(daily) <= 131072 and digest(daily) == request["daily_sha256"], "daily_digest_or_size")
    require((repo / daily_path).read_bytes() == daily and not (repo / daily_path).is_symlink(), "daily_worktree_mismatch")
    edition = json.loads(daily)
    require(edition["date"] == day and edition["timezone"] == "America/Los_Angeles"
            and edition["compiled_at"] == request["compiled_at"] and 10 <= len(edition["items"]) <= 20, "daily_identity")
    instant = datetime.fromisoformat(request["compiled_at"].replace("Z", "+00:00"))
    require(instant.tzinfo is not None and instant.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat() == day, "compiled_at_identity")
    manifest = blob(repo, baseline, "dist/manifest.json")
    require(digest(manifest) == request["baseline_manifest_sha256"], "baseline_manifest_mismatch")
    return {"status": "source_validated", "should_build": True, "repository": REPOSITORY,
            "branch": head["ref"], "source": source, "baseline": baseline,
            "daily_path": daily_path, "request": request}


def runtime_name(name):
    safe_path(name)
    parts = name.split("/")
    require(len(parts) == 2 and parts[0] in {"js", "presentation"}
            and Path(name).suffix in {".js", ".json"}, "invalid_runtime_path")
    return name


def retention(repo, plan):
    baseline, request = plan["baseline"], plan["request"]
    manifest = json.loads(blob(repo, baseline, "dist/manifest.json"))
    old = json.loads(blob(repo, baseline, "release-assets/generations.json"))["generations"]
    require(len(old) == 2 and old[0]["cloudflare_version"] != old[1]["cloudflare_version"], "retention_count")
    require(request["outgoing_cloudflare_version"] not in {x["cloudflare_version"] for x in old}, "outgoing_already_retained")
    summary = manifest["summary"]
    first = runtime_name(summary["href"].removeprefix("/"))
    queue, current, contents = [first], {}, {}
    # app/data are HTML entrypoints; the summary can reference only health.js.
    for page in ("index.html", "explore/index.html"):
        html = blob(repo, baseline, "dist/" + page)
        require(digest(html) == manifest["sha256"][page], "baseline_html_digest")
        queue.extend(name.decode("ascii") for name in re.findall(
            rb'''\b(?:src|href)\s*=\s*["']/?(js/[A-Za-z0-9._-]+\.js)["']''', html, re.I))
    while queue:
        name = runtime_name(queue.pop())
        if name in current:
            continue
        require(name in manifest["sha256"] and len(current) < 2048, "unknown_runtime_reference")
        data = blob(repo, baseline, "dist/" + name)
        require(digest(data) == manifest["sha256"][name] and len(data) <= 25 * 1024 * 1024, "runtime_digest")
        current[name], contents[name] = digest(data), data
        if name == first:
            require(current[name] == summary["sha256"] and len(data) == summary["bytes"], "summary_identity")
        if name.endswith(".json"):
            def walk(value):
                if isinstance(value, str) and value.startswith(("/js/", "/presentation/")):
                    queue.append(value[1:])
                elif isinstance(value, dict):
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(json.loads(data))
    previous = old[0]
    for name, expected in previous["sha256"].items():
        runtime_name(name)
        data = blob(repo, baseline, "release-assets/" + name)
        require(digest(data) == expected, "prior_generation_digest")
        require(name not in contents or contents[name] == data, "runtime_collision")
        contents[name] = data
    generations = [{"cloudflare_version": request["outgoing_cloudflare_version"], "sha256": current}, previous]
    return generations, contents


def artifact(directory):
    directory = Path(directory)
    require(not directory.is_symlink(), "artifact_symlink")
    paths = {}
    for p in directory.rglob("*"):
        require(not p.is_symlink(), "artifact_symlink")
        if p.is_file():
            name = safe_path(p.relative_to(directory).as_posix())
            require(p.stat().st_size <= 25 * 1024 * 1024, "artifact_too_large")
            paths[name] = p
    manifest_raw = paths["manifest.json"].read_bytes()
    require(len(manifest_raw) <= 1048576 and len(paths) <= 10000, "artifact_bounds")
    manifest = json.loads(manifest_raw)
    require(set(paths) == set(manifest["sha256"]) | {"manifest.json"}, "artifact_file_set")
    for name, expected in manifest["sha256"].items():
        require(digest(paths[name].read_bytes()) == expected, "artifact_digest")
    return manifest, digest(manifest_raw)


def prepare(repo, event, output, install=True):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    plan = preflight(repo, event)
    if not plan["should_build"]:
        return plan
    require(repo != output and repo not in output.parents and not output.exists(), "unsafe_output")
    generations, retained = retention(repo, plan)  # Always pinned baseline, never candidate dist.
    target = repo / "release-assets"
    require(not target.is_symlink() and all(not p.is_symlink() for p in target.rglob("*")), "retention_symlink")
    for p in list(target.rglob("*")):
        if p.is_file():
            name = p.relative_to(target).as_posix()
            require(name == "generations.json" or runtime_name(name), "unexpected_retention_file")
            if name != "generations.json" and name not in retained:
                p.unlink()
    for name, data in retained.items():
        p = target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (target / "generations.json").write_text(json.dumps({"generations": generations}, indent=2, sort_keys=True) + "\n")
    env = clean_environment()
    def run(args):
        result = subprocess.run(args, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(result.returncode == 0, "candidate_build_or_verify_failed")
    if install:
        run(["npm", "ci"])
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-qa.txt"])
    run([sys.executable, "scripts/build_public_snapshot.py", "--output", str(output)])
    manifest, manifest_sha = artifact(output)
    expected = plan["request"]["expected_candidate_manifest_sha256"]
    require(expected is None or manifest_sha == expected, "frozen_candidate_mismatch")
    baseline_manifest = json.loads(blob(repo, plan["baseline"], "dist/manifest.json"))
    for name in baseline_manifest["sha256"]:
        if re.fullmatch(r"daily/\d{4}-\d{2}-\d{2}/snapshot\.json", name):
            require((output / name).read_bytes() == blob(repo, plan["baseline"], "dist/" + name), "historical_snapshot_changed")
    require(blob(repo, plan["source"], plan["daily_path"]) == (repo / plan["daily_path"]).read_bytes(), "compiled_source_changed")
    require(not (repo / "dist").is_symlink(), "dist_symlink")
    shutil.rmtree(repo / "dist")
    shutil.copytree(output, repo / "dist")
    run([sys.executable, "scripts/build_public_snapshot.py", "--verify"])
    changed = git(repo, "diff", "HEAD", "--name-only", "-z").decode().split("\0")
    require(all(not p or p.startswith(("dist/", "release-assets/")) for p in changed), "unexpected_build_edit")
    git(repo, "add", "-A", "--", "dist", "release-assets")
    git(repo, "-c", "user.name=GitHub Actions", "-c", "user.email=actions@users.noreply.github.com",
        "commit", "-m", "build: prepare isolated Daily candidate " + plan["request"]["date"])
    require(all(p.startswith(("dist/", "release-assets/")) for _, p in
                changes(repo, plan["source"], "HEAD")), "committed_path_scope")
    result = {**plan, "status": "built_not_pushed_or_certified", "builder_commit": git(repo, "rev-parse", "HEAD").decode().strip(),
              "tree": git(repo, "rev-parse", "HEAD^{tree}").decode().strip(), "manifest_sha256": manifest_sha,
              "build_id": manifest.get("build_id"), "compiled_at": plan["request"]["compiled_at"]}
    return result


def push(repo, receipt, token, execute=subprocess.run):
    require(receipt.get("status") == "built_not_pushed_or_certified" and BRANCH.fullmatch(receipt.get("branch", "")), "push_scope")
    require(valid_push_token(token), "push_token_bounds")
    require(HEX40.fullmatch(receipt["source"]) and HEX40.fullmatch(receipt["builder_commit"]), "push_commit")
    require(git(repo, "rev-parse", "HEAD").decode().strip() == receipt["builder_commit"], "push_head_moved")
    require(git(repo, "rev-parse", "HEAD^").decode().strip() == receipt["source"], "push_parent")
    require(git(repo, "rev-parse", "HEAD^{tree}").decode().strip() == receipt["tree"], "push_tree")
    require(git(repo, "remote", "get-url", "--push", "origin").decode().strip() in
            {"https://github.com/" + REPOSITORY, "https://github.com/" + REPOSITORY + ".git"}, "push_remote")
    # Fresh checkout must have persist-credentials:false; reject local rewrite/auth hooks.
    config = git(repo, "config", "--local", "--list").decode()
    require(not re.search(r"(?:insteadof|pushinsteadof|extraheader|credential\.|sshcommand|include\.path|includeif\.)", config, re.I), "unsafe_git_config")
    with tempfile.TemporaryDirectory(prefix="daily-push-") as temporary:
        ask = Path(temporary) / "askpass"
        ask.write_text('#!/bin/sh\ncase "$1" in\n*Username*) printf "%s\\n" x-access-token;;\n*Password*) printf "%s\\n" "$GH_PUSH_TOKEN";;\n*) exit 1;;\nesac\n')
        ask.chmod(0o700)
        env = clean_environment()
        env.update(GH_PUSH_TOKEN=token, GIT_ASKPASS=str(ask), GIT_TERMINAL_PROMPT="0",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        ref = "refs/heads/" + receipt["branch"]
        args = ["git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "push", "--porcelain",
                "--force-with-lease=" + ref + ":" + receipt["source"],
                "https://github.com/" + REPOSITORY + ".git", "HEAD:" + ref]
        outcome = execute(args, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(outcome.returncode == 0, "push_failed_hold_read_branch_before_any_retry")
    return {"status": "push_acknowledged_not_CI_or_publication", "builder_commit": receipt["builder_commit"], "tree": receipt["tree"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "prepare", "push"))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "push":
            result = push(args.repository, json.loads(args.receipt.read_text()), os.environ.get("GH_PUSH_TOKEN"))
        else:
            event = json.loads(args.event.read_text())
            result = preflight(args.repository, event) if args.mode == "preflight" else prepare(args.repository, event, args.output)
            require(args.repository.resolve() not in args.receipt.resolve().parents, "receipt_must_be_outside_checkout")
            args.receipt.write_text(canonical(result) + "\n")
            if args.mode == "preflight" and os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a") as target:
                    target.write("should_build=" + str(result["should_build"]).lower() + "\n")
        print(canonical({k: v for k, v in result.items() if k in {"status", "should_build", "builder_commit", "tree", "manifest_sha256", "build_id"}}))
    except Hold as error:
        code = error.args[0] if error.args and isinstance(error.args[0], str) else None
        print(canonical({"status": "hold", "stage": args.mode,
                         "error": code if code in SAFE_HOLD_REASONS else GENERIC_HOLD_REASON}))
        return 2
    except Exception:
        print(canonical({"status": "hold", "stage": args.mode, "error": GENERIC_HOLD_REASON}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
