"""Synthetic offline security probes; no real account or publication evidence."""
import contextlib
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


PATH = Path(__file__).resolve().parents[1] / "tools/publishing/configure_accounts.py"
SPEC = importlib.util.spec_from_file_location("configure_accounts", PATH)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
SYNTHETIC = "SYNTHETIC_CREDENTIAL_FOR_OFFLINE_TESTS"


class PrivateConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS /var is a symlink; choose the canonical path for the fixture.
        self.base = Path(self.temp.name).resolve()
        self.path = self.base / "accounts/publishing-credentials.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_blank_preserves_without_creating_file_or_directory(self):
        self.assertEqual(setup.merge_credentials({}, self.path), {"schema_version": 1})
        self.assertFalse(self.path.parent.exists())

    def test_atomic_merge_preserves_other_service_and_private_permissions(self):
        setup.merge_credentials({"hf_token": SYNTHETIC, "hf_repository": "fixture/dataset"}, self.path)
        setup.merge_credentials({"zenodo_production_token": "SYNTHETIC_ZENODO"}, self.path)
        result = setup.load_credentials(self.path)
        self.assertEqual(result["hf_token"], SYNTHETIC)
        self.assertEqual(result["hf_repository"], "fixture/dataset")
        self.assertEqual(result["zenodo_production_token"], "SYNTHETIC_ZENODO")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.path.with_suffix(".json.lock").stat().st_mode & 0o777, 0o600)

    def test_replace_failure_keeps_original_and_removes_temporary(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        original = self.path.read_bytes()
        with patch.object(setup.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                setup.merge_credentials({"zenodo_sandbox_token": "SYNTHETIC_SANDBOX"}, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".publishing-credentials-*")), [])

    def test_concurrent_writer_fails_without_overwriting(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        with setup._write_lock(self.path):
            with self.assertRaises(setup.SetupError):
                setup.merge_credentials({"zenodo_sandbox_token": "SYNTHETIC_SANDBOX"}, self.path)
        self.assertNotIn("zenodo_sandbox_token", setup.load_credentials(self.path))

    def test_file_symlink_refused(self):
        self.path.parent.mkdir(mode=0o700)
        target = self.base / "target"
        target.write_text("do not alter")
        self.path.symlink_to(target)
        with self.assertRaises(setup.SetupError):
            setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        self.assertEqual(target.read_text(), "do not alter")

    def test_parent_symlink_refused(self):
        target = self.base / "actual"
        target.mkdir(mode=0o700)
        self.path.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaises(setup.SetupError):
            setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        self.assertEqual(list(target.iterdir()), [])

    def test_lock_symlink_refused(self):
        self.path.parent.mkdir(mode=0o700)
        target = self.base / "target"
        target.write_text("do not alter")
        self.path.with_suffix(".json.lock").symlink_to(target)
        with self.assertRaises(setup.SetupError):
            setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        self.assertEqual(target.read_text(), "do not alter")

    def test_broad_file_mode_refused(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        self.path.chmod(0o644)
        with self.assertRaises(setup.SetupError):
            setup.load_credentials(self.path)

    def test_broad_directory_mode_refused(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        self.path.parent.chmod(0o755)
        with self.assertRaises(setup.SetupError):
            setup.load_credentials(self.path)

    def test_hardlink_refused(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        os.link(self.path, self.base / "extra-link")
        with self.assertRaises(setup.SetupError):
            setup.load_credentials(self.path)

    def test_invalid_schema_duplicate_json_and_utf8_refused(self):
        self.path.parent.mkdir(mode=0o700)
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"schema_version":true}',
                    b'{"schema_version":1,"unrecognized":"x"}', b'\xff', b'{bad json}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                self.path.chmod(0o600)
                with self.assertRaises(setup.SetupError):
                    setup.load_credentials(self.path)

    def test_status_does_not_network_or_expose_tokens(self):
        setup.merge_credentials({"hf_token": SYNTHETIC}, self.path)
        output = io.StringIO()
        with patch.object(setup, "CONFIG", self.path), patch.object(setup.urllib.request, "build_opener", side_effect=AssertionError("no network")), contextlib.redirect_stdout(output):
            self.assertEqual(setup.main(["--status"]), 0)
        self.assertNotIn(SYNTHETIC, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["huggingface"]["token_configured"])


class TransportTests(unittest.TestCase):
    def test_non_https_cross_origin_credentials_urls_refused(self):
        with patch.object(setup.urllib.request, "build_opener", side_effect=AssertionError("no network")):
            for url in ("http://zenodo.org/api/", "https://attacker.invalid/api/", "https://zenodo.org.attacker.invalid/api/",
                        "https://u:p@zenodo.org/api/", "https://zenodo.org/api/?access_token=synthetic"):
                self.assertEqual(setup.get_json(url, SYNTHETIC)["status"], "blocked_origin")

    def test_token_cannot_inject_header(self):
        for value in ("line\r\nInjection: x", "spaces here", "\t", "", "nonascii\u00e9"):
            with self.assertRaises(setup.SetupError):
                setup.validate_token(value)

    def test_get_only_bearer_header_and_disabled_proxies_redirects(self):
        requests = []
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, count): return b'[]'
        class Opener:
            def open(self, request, timeout):
                requests.append((request, timeout))
                return Response()
        with patch.object(setup.urllib.request, "build_opener", return_value=Opener()) as build:
            self.assertEqual(setup.get_json("https://zenodo.org/api/deposit/depositions?size=1", SYNTHETIC)["status"], "ok")
        request, timeout = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + SYNTHETIC)
        self.assertNotIn(SYNTHETIC, request.full_url)
        self.assertIsNone(request.data)
        self.assertEqual(timeout, 25)
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], setup.NoRedirect)

    def test_every_redirect_is_blocked(self):
        handler = setup.NoRedirect()
        for target in ("https://attacker.invalid/", "https://zenodo.org/login"):
            self.assertIsNone(handler.redirect_request(None, None, 302, "found", {}, target))

    def test_http_failures_are_sanitized_including_reflected_token(self):
        for code, status in ((401, "unauthorized"), (403, "forbidden"), (429, "rate_limited"), (302, "redirect_blocked")):
            opener = unittest.mock.Mock()
            opener.open.side_effect = urllib.error.HTTPError("https://zenodo.org/api/", code, SYNTHETIC, {}, io.BytesIO(SYNTHETIC.encode()))
            with patch.object(setup.urllib.request, "build_opener", return_value=opener):
                result = setup.get_json("https://zenodo.org/api/deposit/depositions?size=1", SYNTHETIC)
            self.assertEqual(result["status"], status)
            self.assertNotIn(SYNTHETIC, json.dumps(result))

    def test_zenodo_read_never_claims_write_scopes(self):
        calls = []
        def fetch(url, token):
            calls.append(url)
            return {"status": "ok", "data": [{"metadata": {"title": SYNTHETIC}}]}
        result = setup.check_zenodo(SYNTHETIC, sandbox=True, fetch=fetch)
        self.assertEqual(result, {"status": "authenticated_read", "write_scopes": "unverified"})
        self.assertEqual(calls, ["https://sandbox.zenodo.org/api/deposit/depositions?size=1"])
        self.assertNotIn(SYNTHETIC, json.dumps(result))

    def test_unlisted_official_endpoints_are_blocked(self):
        with patch.object(setup.urllib.request, "build_opener", side_effect=AssertionError("no network")):
            for url in ("https://zenodo.org/api/", "https://zenodo.org/api/deposit/depositions?size=10",
                        "https://huggingface.co/api/datasets/fixture/dataset?token=x", "https://huggingface.co/api/settings"):
                self.assertEqual(setup.get_json(url, SYNTHETIC)["status"], "blocked_endpoint")

    def test_zenodo_wrong_shape_and_missing_credentials_fail_closed(self):
        self.assertEqual(setup.check_zenodo(None)["status"], "not_configured")
        self.assertEqual(setup.check_zenodo(SYNTHETIC, fetch=lambda *args: {"status": "ok", "data": {}})["status"], "unexpected_response")

    def test_hf_response_filters_secrets_and_does_not_claim_write(self):
        def fetch(url, token):
            data = {"name": "fixture", "email": SYNTHETIC, "auth": {"accessToken": {"role": "fineGrained", "secret": SYNTHETIC}}} if url.endswith("whoami-v2") else {
                "id": "fixture/dataset", "private": True, "sha": "a" * 40, "secret": SYNTHETIC}
            return {"status": "ok", "data": data}
        result = setup.check_huggingface(SYNTHETIC, "fixture/dataset", fetch=fetch)
        self.assertEqual(result["reported_token_role"], "fineGrained")
        self.assertEqual(result["repository_status"], "readable")
        self.assertEqual(result["write_access"], "unverified")
        self.assertNotIn(SYNTHETIC, json.dumps(result))

    def test_hf_wrong_repository_and_path_traversal_rejected(self):
        def fetch(url, token):
            return {"status": "ok", "data": {"name": "fixture"} if url.endswith("whoami-v2") else {"id": "other/dataset"}}
        self.assertEqual(setup.check_huggingface(SYNTHETIC, "fixture/dataset", fetch=fetch)["repository_status"], "unexpected_response")
        for value in ("../path", "fixture/../path", "https://attacker.invalid", "fixture/dataset?token=x"):
            with self.assertRaises(setup.SetupError):
                setup.validate_repository(value)

    def test_hf_malformed_role_is_not_trusted_or_printed(self):
        def fetch(url, token):
            return {"status": "ok", "data": {"name": "fixture", "auth": {"accessToken": {"role": {"secret": SYNTHETIC}}}}}
        result = setup.check_huggingface(SYNTHETIC, None, fetch=fetch)
        self.assertNotIn("reported_token_role", result)
        self.assertNotIn(SYNTHETIC, json.dumps(result))

    def test_noninteractive_entry_and_echo_fallback_refused(self):
        with patch.object(setup.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(setup.SetupError):
                setup.collect_changes("zenodo")
        def no_hidden_input(*args):
            import warnings
            warnings.warn("echo unsupported", getpass.GetPassWarning)
        with patch.object(setup.sys.stdin, "isatty", return_value=True), patch.object(setup.getpass, "getpass", side_effect=no_hidden_input):
            with self.assertRaises(setup.SetupError):
                setup.collect_changes("zenodo")

    def test_all_blank_inputs_preserve_current_values(self):
        with patch.object(setup.sys.stdin, "isatty", return_value=True), patch.object(setup.getpass, "getpass", return_value=""), patch("builtins.input", return_value=""):
            self.assertEqual(setup.collect_changes("all"), {})


if __name__ == "__main__":
    unittest.main()
