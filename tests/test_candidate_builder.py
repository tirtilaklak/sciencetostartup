"""Offline tests: temporary Git repositories, synthetic public fixture, mocked push only."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("builder", ROOT / ".github/scripts/candidate_builder.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
V0, V1, V2 = ("00000000-0000-0000-0000-00000000000" + str(i) for i in range(3))
TOKEN = "SYNTHETIC_OFFLINE_TOKEN_1234567890"

# Deliberately tiny executable fixture, NOT a substitute for the repository's real builder/CI.
BUILD = '''import argparse,hashlib,json,pathlib,tempfile,shutil
r=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--verify',action='store_true');a=p.parse_args()
def build(o):
 o.mkdir(parents=True)
 for f in (r/'data/daily-scan').glob('*.json'):
  d=json.loads(f.read_text());q=o/'daily'/d['date']/'snapshot.json';q.parent.mkdir(parents=True);q.write_bytes(f.read_bytes())
 for f in (r/'release-assets').rglob('*'):
  if f.is_file() and f.name!='generations.json':
   q=o/f.relative_to(r/'release-assets');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(f.read_bytes())
 (o/'index.html').write_text('candidate')
 hashes={f.relative_to(o).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in o.rglob('*') if f.is_file()}
 m={'build_id':hashlib.sha256((r/'release-assets/generations.json').read_bytes()).hexdigest()[:20],'sha256':hashes}
 (o/'manifest.json').write_text(json.dumps(m,sort_keys=True))
if a.verify:
 with tempfile.TemporaryDirectory() as t:
  o=pathlib.Path(t)/'built';build(o)
  expected={f.relative_to(r/'dist').as_posix():f.read_bytes() for f in (r/'dist').rglob('*') if f.is_file()}
  assert {f.relative_to(o).as_posix():f.read_bytes() for f in o.rglob('*') if f.is_file()}==expected
else:build(pathlib.Path(a.output))
'''


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.rawgit("init", "-q", "-b", "main")
        self.rawgit("config", "user.name", "Offline fixture")
        self.rawgit("config", "user.email", "fixture@example.invalid")
        self.rawgit("remote", "add", "origin", "https://github.com/" + c.REPOSITORY + ".git")
        self.put("scripts/build_public_snapshot.py", BUILD.encode())
        self.put(".gitignore", b"node_modules/\n")
        self.put("data/daily-scan/2026-11-16.json", self.edition("2026-11-16", "2026-11-16T16:00:00+00:00"))
        current = {"js/current.js": b"current", "js/data.js": b"data", "js/health.js": b"health", "js/shared.js": b"shared",
                   "presentation/archive.current.json": b'{"buildId":"baseline"}'}
        summary = json.dumps({"modules": {"health": "/js/health.js", "shared": "/js/shared.js"},
                              "archive": {"href": "/presentation/archive.current.json"}}).encode()
        current["presentation/summary.current.json"] = summary
        previous = {"js/previous.js": b"previous", "js/shared.js": b"shared"}
        ancient = {"js/ancient.js": b"ancient"}
        for name, data in {**current, **previous, **ancient}.items():
            self.put("dist/" + name, data)
        self.put("dist/index.html", b'<script src="/js/current.js"></script>')
        self.put("dist/explore/index.html", b'<script src="/js/data.js"></script>')
        historical = self.repo / "data/daily-scan/2026-11-16.json"
        self.put("dist/daily/2026-11-16/snapshot.json", historical.read_bytes())
        hashes = {f.relative_to(self.repo / "dist").as_posix(): c.digest(f.read_bytes())
                  for f in (self.repo / "dist").rglob("*") if f.is_file()}
        manifest = {"build_id": "baseline", "summary": {"href": "/presentation/summary.current.json",
                    "sha256": c.digest(summary), "bytes": len(summary)}, "sha256": hashes}
        self.put("dist/manifest.json", json.dumps(manifest).encode())
        for name, data in {**previous, **ancient}.items():
            self.put("release-assets/" + name, data)
        registry = {"generations": [{"cloudflare_version": V1, "sha256": {n: c.digest(v) for n, v in previous.items()}},
                                    {"cloudflare_version": V2, "sha256": {n: c.digest(v) for n, v in ancient.items()}}]}
        self.put("release-assets/generations.json", json.dumps(registry).encode())
        self.commit("baseline")
        self.baseline = self.head()
        self.rawgit("switch", "-q", "-c", "codex/cloud-daily-2026-11-18")
        self.daily = self.edition("2026-11-18", "2026-11-18T16:07:40.844549+00:00")
        self.put("data/daily-scan/2026-11-18.json", self.daily)
        self.commit("reviewed public Daily input")
        self.source = self.head()
        self.request = {"date": "2026-11-18", "baseline_commit": self.baseline,
                        "baseline_manifest_sha256": c.digest((self.repo / "dist/manifest.json").read_bytes()),
                        "outgoing_cloudflare_version": V0, "daily_sha256": c.digest(self.daily),
                        "compiled_at": "2026-11-18T16:07:40.844549+00:00", "expected_candidate_manifest_sha256": None}
        self.event = {"action": "opened", "repository": {"full_name": c.REPOSITORY}, "pull_request": {
            "head": {"sha": self.source, "ref": "codex/cloud-daily-2026-11-18", "repo": {"full_name": c.REPOSITORY}},
            "base": {"sha": self.baseline, "ref": "main", "repo": {"full_name": c.REPOSITORY}},
            "body": json.dumps(self.request)}}

    def rawgit(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def put(self, path, data):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def commit(self, message):
        self.rawgit("add", "-A")
        self.rawgit("commit", "-q", "-m", message)

    def head(self):
        return self.rawgit("rev-parse", "HEAD").decode().strip()

    @staticmethod
    def edition(day, instant):
        return json.dumps({"schema_version": "1.0.0", "date": day, "timezone": "America/Los_Angeles",
                           "compiled_at": instant, "items": [{} for _ in range(13)]}).encode()

    def build(self):
        return c.prepare(self.repo, self.event, self.root / "built", install=False)

    def reject_network(self, *args, **kwargs):
        raise AssertionError("unexpected push dispatch")

    def test_valid_source_only_preflight(self):
        self.assertTrue(c.preflight(self.repo, self.event)["should_build"])

    def test_fork_wrong_repository_and_main_branch_rejected(self):
        for field, value in [("repo", "other/repo"), ("branch", "main"), ("base", "codex/not-main")]:
            e = copy.deepcopy(self.event)
            if field == "repo": e["pull_request"]["head"]["repo"]["full_name"] = value
            elif field == "branch": e["pull_request"]["head"]["ref"] = value
            else: e["pull_request"]["base"]["ref"] = value
            with self.subTest(field=field), self.assertRaises(c.Hold): c.preflight(self.repo, e)

    def test_stale_head_and_baseline_digest_rejected(self):
        e = copy.deepcopy(self.event); e["pull_request"]["head"]["sha"] = self.baseline
        with self.assertRaises(c.Hold): c.preflight(self.repo, e)
        q = {**self.request, "baseline_manifest_sha256": "0" * 64}
        e = copy.deepcopy(self.event); e["pull_request"]["body"] = json.dumps(q)
        with self.assertRaises(c.Hold): c.preflight(self.repo, e)

    def test_branch_script_edit_rejected_before_build(self):
        self.put("scripts/build_public_snapshot.py", b"raise SystemExit('must not execute')")
        self.commit("untrusted code")
        self.event["pull_request"]["head"]["sha"] = self.head()
        with self.assertRaises(c.Hold): self.build()
        self.assertFalse((self.root / "built").exists())

    def test_symlink_daily_rejected(self):
        p = self.repo / "data/daily-scan/2026-11-18.json"; p.unlink(); p.symlink_to("2026-11-16.json")
        self.commit("symlink")
        self.event["pull_request"]["head"]["sha"] = self.head()
        with self.assertRaises(c.Hold): c.preflight(self.repo, self.event)

    def test_historical_delete_or_rename_rejected(self):
        self.rawgit("rm", "data/daily-scan/2026-11-16.json"); self.commit("delete history")
        self.event["pull_request"]["head"]["sha"] = self.head()
        with self.assertRaises(c.Hold): c.preflight(self.repo, self.event)

    def test_unexpected_request_fields_and_bounds_rejected(self):
        for body in [json.dumps({**self.request, "secret": "never admissible"}), " " * 4097]:
            e = copy.deepcopy(self.event); e["pull_request"]["body"] = body
            with self.assertRaises(c.Hold): c.preflight(self.repo, e)

    def test_dirty_worktree_rejected(self):
        self.put("untracked-private-file", b"synthetic")
        with self.assertRaises(c.Hold): c.preflight(self.repo, self.event)

    def test_current_runtime_closure_and_exact_two_prior_generations(self):
        plan = c.preflight(self.repo, self.event)
        generations, contents = c.retention(self.repo, plan)
        self.assertEqual([g["cloudflare_version"] for g in generations], [V0, V1])
        self.assertIn("js/shared.js", generations[0]["sha256"])
        self.assertIn("presentation/archive.current.json", contents)
        self.assertNotIn("js/ancient.js", contents)

    def test_html_only_app_data_are_in_the_outgoing_generation(self):
        generations, _ = c.retention(self.repo, c.preflight(self.repo, self.event))
        self.assertIn("js/current.js", generations[0]["sha256"])
        self.assertIn("js/data.js", generations[0]["sha256"])

    def test_build_staging_outside_output_is_rejected_before_commit(self):
        real_run = subprocess.run
        def intercept(args, **kw):
            result = real_run(args, **kw)
            if "scripts/build_public_snapshot.py" in args and "--output" in args:
                self.put("data/forbidden.json", b"{}")
                real_run(["git", "add", "data/forbidden.json"], cwd=self.repo, check=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result
        with patch.object(c.subprocess, "run", side_effect=intercept):
            with self.assertRaises(c.Hold): self.build()
        self.assertEqual(self.head(), self.source)

    def test_build_freezes_bytes_preserves_timestamp_and_history(self):
        old = (self.repo / "dist/daily/2026-11-16/snapshot.json").read_bytes()
        result = self.build()
        self.assertEqual(result["status"], "built_not_pushed_or_certified")
        self.assertEqual((self.repo / "data/daily-scan/2026-11-18.json").read_bytes(), self.daily)
        self.assertEqual((self.repo / "dist/daily/2026-11-16/snapshot.json").read_bytes(), old)
        self.assertEqual(json.loads((self.repo / "dist/daily/2026-11-18/snapshot.json").read_text())["compiled_at"], self.request["compiled_at"])
        self.assertFalse((self.repo / "release-assets/js/ancient.js").exists())
        self.assertTrue(all(p.startswith(("dist/", "release-assets/")) for _, p in c.changes(self.repo, self.source, result["builder_commit"])))

    def test_builder_event_and_app_same_tree_checkpoint_do_not_loop(self):
        result = self.build(); before = self.head()
        e = copy.deepcopy(self.event); e.update(action="synchronize", before=self.source)
        e["pull_request"]["head"]["sha"] = before
        self.assertFalse(c.preflight(self.repo, e)["should_build"])
        self.rawgit("commit", "-q", "--allow-empty", "-m", "App same-tree checkpoint")
        e["before"] = before; e["pull_request"]["head"]["sha"] = self.head()
        output = self.root / "never-built"
        self.assertEqual(c.prepare(self.repo, e, output, install=False)["status"], "no_source_change")
        self.assertFalse(output.exists())
        self.assertEqual(self.rawgit("rev-parse", "HEAD^{tree}").decode().strip(), result["tree"])

    def test_expected_frozen_manifest_mismatch_holds_before_commit(self):
        self.request["expected_candidate_manifest_sha256"] = "0" * 64
        self.event["pull_request"]["body"] = json.dumps(self.request)
        with self.assertRaises(c.Hold): self.build()
        self.assertEqual(self.head(), self.source)

    def test_unsafe_output_inside_checkout_rejected(self):
        with self.assertRaises(c.Hold): c.prepare(self.repo, self.event, self.repo / "output", install=False)

    def test_artifact_symlink_rejected(self):
        output = self.root / "artifact"; output.mkdir(); (output / "link").symlink_to(self.repo / "dist/manifest.json")
        with self.assertRaises(c.Hold): c.artifact(output)

    def test_paths_reject_escape_controls_and_backslashes(self):
        for path in ["../escape", "/absolute", "js/../bad.js", "js\\bad.js", "js/a\n.js", "js//a.js"]:
            with self.subTest(path=path), self.assertRaises(c.Hold): c.runtime_name(path)

    def test_build_environment_removes_all_synthetic_credentials(self):
        clean = c.clean_environment({"PATH": "/usr/bin", "GH_PUSH_TOKEN": TOKEN,
                                     "OPENAI_API_KEY": "synthetic", "ACTIONS_RUNTIME_TOKEN": "synthetic",
                                     "GIT_CONFIG_PARAMETERS": "'url.https://example.invalid.insteadOf=https://github.com'",
                                     "GIT_SSH_COMMAND": "unsafe", "GIT_PROXY_COMMAND": "unsafe"})
        self.assertEqual(clean, {"PATH": "/usr/bin"})

    def test_push_has_one_exact_branch_lease_and_no_token_in_args_or_output(self):
        receipt = self.build(); calls = []
        def fake(args, **kw):
            calls.append(args)
            self.assertNotIn(TOKEN, repr(args))
            self.assertEqual(kw["env"]["GH_PUSH_TOKEN"], TOKEN)
            ask = Path(kw["env"]["GIT_ASKPASS"])
            self.assertEqual(ask.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(TOKEN, ask.read_text())
            self.assertIn("--force-with-lease=refs/heads/codex/cloud-daily-2026-11-18:" + self.source, args)
            return subprocess.CompletedProcess(args, 0, stdout=TOKEN.encode(), stderr=TOKEN.encode())
        result = c.push(self.repo, receipt, TOKEN, execute=fake)
        self.assertEqual(len(calls), 1)
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertTrue(calls[0][-1].endswith("refs/heads/codex/cloud-daily-2026-11-18"))

    def test_failed_push_is_not_retried_and_does_not_echo_error_secret(self):
        receipt = self.build(); calls = []
        def fake(args, **kw):
            calls.append(args); return subprocess.CompletedProcess(args, 1, stderr=TOKEN.encode())
        with self.assertRaises(c.Hold) as failure: c.push(self.repo, receipt, TOKEN, execute=fake)
        self.assertEqual(len(calls), 1)
        self.assertNotIn(TOKEN, str(failure.exception))

    def test_push_forbids_main_stale_head_and_noncanonical_remote(self):
        receipt = self.build()
        with self.assertRaises(c.Hold): c.push(self.repo, {**receipt, "branch": "main"}, TOKEN, execute=self.reject_network)
        self.rawgit("remote", "set-url", "origin", "https://example.invalid/repo")
        with self.assertRaises(c.Hold): c.push(self.repo, receipt, TOKEN, execute=self.reject_network)
        self.rawgit("remote", "set-url", "origin", "https://github.com/" + c.REPOSITORY + ".git")
        self.rawgit("commit", "-q", "--allow-empty", "-m", "concurrent change")
        with self.assertRaises(c.Hold): c.push(self.repo, receipt, TOKEN, execute=self.reject_network)

    def test_token_newlines_short_and_oversized_values_rejected_before_push(self):
        receipt = self.build()
        for token in ["short", "x" * 513, TOKEN + "\n", TOKEN + "$(bad)"]:
            with self.subTest(length=len(token)), self.assertRaises(c.Hold): c.push(self.repo, receipt, token, execute=self.reject_network)

    def test_push_rejects_included_git_configuration(self):
        receipt = self.build()
        included = self.root / "included.gitconfig"
        included.write_text('[url "https://example.invalid/"]\n insteadOf = https://github.com/\n')
        self.rawgit("config", "include.path", str(included))
        with self.assertRaises(c.Hold): c.push(self.repo, receipt, TOKEN, execute=self.reject_network)


if __name__ == "__main__":
    unittest.main()
