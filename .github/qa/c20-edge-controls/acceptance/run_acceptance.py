#!/usr/bin/env python3
"""Run the read-only site acceptance probes against one served build."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
MISSING_TOOL = re.compile(
    r"Cannot find module|No module named|Executable doesn't exist|"
    r"missing dependencies to run browsers|browserType\.launch: Failed to launch.*ENOENT",
    re.IGNORECASE,
)
PROBE_HEADERS = {"Cache-Control": "no-cache", "User-Agent": "ScienceToStartup acceptance probe/1.0"}
# Match the observed terminal Insights tag. The remaining bytes must match the manifest.
CF_INSIGHTS = re.compile(
    rb'<script type="module" src="https://static\.cloudflareinsights\.com/beacon\.min\.js/v[0-9a-f]+" '
    rb'integrity="sha512-[A-Za-z0-9+/]{86}==" data-cf-beacon=\'\{"version":"[0-9]+\.[0-9]+\.[0-9]+",'
    rb'"token":"[0-9a-f]{32}","r":1,"spa":2\}\' crossorigin="anonymous"></script>\n(?=</body>\n?</html>\n\Z)'
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def asset_snapshot(base, manifest):
    summary_path = manifest["summary"]["href"].lstrip("/")
    paths = ("home-runtime.js", "home-search.js", "landing.css", summary_path)

    def verify(path):
        row = {"expected_sha256": manifest["sha256"].get(path)}
        try:
            if not row["expected_sha256"]:
                raise ValueError("Asset digest missing from manifest")
            with urlopen(Request(f"{base}/{path}", headers=PROBE_HEADERS), timeout=20) as response:
                row.update(http_status=response.status, sha256=sha256(response.read()).hexdigest())
        except (OSError, ValueError) as error:
            row["error"] = str(error)
        return path, row

    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        return dict(pool.map(verify, paths))


def fetch_manifest(base, output, label):
    result = {"observed_at": utc_now()}
    request = Request(base + "/manifest.json", headers=PROBE_HEADERS)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read()
            result.update(http_status=response.status, final_url=response.geturl())
        filename = f"manifest-{label}.json"
        (output / filename).write_bytes(body)
        result.update(file=filename, sha256=sha256(body).hexdigest())
        manifest = json.loads(body)
        result.update(build_id=manifest["build_id"], editorial_release_id=manifest.get("editorial_release_id"),
                      homepage_sha256=manifest["sha256"]["index.html"], assets=asset_snapshot(base, manifest))
    except (OSError, KeyError, ValueError, TypeError) as error:
        result["error"] = str(error)
    return result


def read_report(path, started_ns):
    if path is None or not path.exists() or path.stat().st_mtime_ns < started_ns:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check_counts(name, output, report):
    if name == "search":
        counts = dict(re.findall(r"^# (tests|pass) (\d+)$", output, re.MULTILINE))
        if "tests" in counts and "pass" in counts:
            return int(counts["pass"]), int(counts["tests"])
    if name == "accessibility" and report is not None:
        rows = report["results"]
        return sum(row["pass"] for row in rows), len(rows)
    if name == "home" and report is not None:
        return report["summary"]["passed"], report["summary"]["total"]
    if name == "editorial":
        counts = re.search(r"^(\d+)/(\d+) checks passed on ", output, re.MULTILINE)
        if counts:
            return tuple(map(int, counts.groups()))
    return None


def run_suite(name, command, env, output, report_path=None):
    started_ns = time.time_ns()
    started = time.monotonic()
    observed_at = utc_now()
    filename = f"{name}.log"
    returncode = None
    with (output / filename).open("wb") as stream:
        try:
            returncode = subprocess.run(command, cwd=HERE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=180).returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            stream.write((str(error) + "\n").encode("utf-8"))
    log = (output / filename).read_text(encoding="utf-8", errors="replace")
    report = read_report(report_path, started_ns)
    counts = check_counts(name, log, report)
    unavailable_checks = []
    if name == "home" and report is not None:
        unavailable_checks = [{"case": case["case"], "error": test["error"]}
                              for case in report["cases"] if "http_status" not in case
                              for test in case["tests"] if not test["pass"] and "error" in test]
    tool_missing = MISSING_TOOL.search(log) or (
        name == "home" and report is not None and MISSING_TOOL.search(json.dumps(report))
    ) or (returncode is None and "No such file or directory" in log)
    if tool_missing:
        status = "missing_tool"
    elif unavailable_checks or re.search(r"^FAIL  Load ", log, re.MULTILINE):
        status = "probe_unavailable"
    elif returncode == 0 and counts and counts[0] == counts[1] > 0:
        status = "passed"
    elif returncode == 1 and counts and counts[0] < counts[1]:
        status = "assertion_failure"
    else:
        status = "probe_error"
    result = {"status": status, "returncode": returncode, "output": filename, "started_at": observed_at,
              "duration_seconds": round(time.monotonic() - started, 2)}
    if counts is not None:
        result.update(passed=counts[0], total=counts[1])
    if report is not None:
        result["report"] = str(report_path.relative_to(output))
    if unavailable_checks:
        result["unavailable_checks"] = unavailable_checks
    print(f"{name}: {status}" + (f" ({counts[0]}/{counts[1]})" if counts else ""), flush=True)
    return result, report


def browser_home_status(expected, report, body_dir):
    observations = {}
    for case in (report or {}).get("cases", []):
        actual = case.get("html_sha256")
        if actual is None:
            continue
        if actual == expected:
            method = "manifest_bytes"
        else:
            filename = case.get("html_body")
            try:
                if not filename or Path(filename).name != filename:
                    raise ValueError("Missing saved browser response")
                body = (body_dir / filename).read_bytes()
                if sha256(body).hexdigest() != actual:
                    raise ValueError("Saved browser response hash differs from the browser receipt")
            except (OSError, ValueError) as error:
                return "unavailable", str(error), list(observations.values())
            clean, changed = CF_INSIGHTS.subn(b"", body)
            if changed != 1 or sha256(clean).hexdigest() != expected:
                return "mixed_build", f"Browser homepage hash {actual} differs from the manifest.", list(observations.values())
            method = "verified_cloudflare_insights_insertion"
        row = observations.setdefault(actual, {"raw_sha256": actual, "verified_sha256": expected,
                                               "method": method, "cases": []})
        row["cases"].append(case["case"])
    if not observations:
        return "unavailable", "No browser observed a homepage body.", []
    return "stable", None, list(observations.values())


def manifest_status(before, after, home_report, body_dir):
    if "error" in before or "error" in after:
        return "unavailable", "Could not verify both release manifests.", []
    if before["sha256"] != after["sha256"]:
        return "mixed_build", "The release manifest changed during the probes.", []
    for snapshot in (before, after):
        for path, asset in snapshot["assets"].items():
            if "error" in asset:
                return "unavailable", f"Could not verify manifest asset {path}.", []
            if asset["sha256"] != asset["expected_sha256"]:
                return "mixed_build", f"Asset {path} does not match its manifest digest.", []
    return browser_home_status(before["homepage_sha256"], home_report, body_dir)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit status: 0 passed, 1 assertion failures, 2 missing tools or incomplete probes, 3 mixed build.",
    )
    parser.add_argument("--base-url", required=True, help="HTTP(S) origin of the live site or exact preview")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for logs, reports and release snapshots")
    parser.add_argument("--chromium", default=os.environ.get("QA_BROWSER_EXECUTABLE") or shutil.which("chromium"),
                        help="Chromium executable for the browser probes")
    parser.add_argument("--firefox", default=os.environ.get("QA_FIREFOX_EXECUTABLE"),
                        help="Playwright-compatible Firefox executable for enlarged-text checks")
    parser.add_argument("--playwright-module", default=os.environ.get("QA_PLAYWRIGHT_MODULE"),
                        help="Playwright Node module path for the search regression suite")
    parser.add_argument("--ignore-https-errors", action="store_true",
                        help="Allow an untrusted proxy or development certificate in the homepage browser probe only")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    url = urlsplit(base)
    if url.scheme not in ("http", "https") or not url.hostname or url.path or url.query or url.fragment or url.username:
        parser.error("--base-url must be an HTTP(S) origin without a path, query, fragment or credentials")

    for option in ("chromium", "firefox"):
        if executable := getattr(args, option):
            setattr(args, option, shutil.which(executable) or str(Path(executable).expanduser().resolve()))
    if args.playwright_module:
        module_path = Path(args.playwright_module).expanduser()
        if args.playwright_module.startswith((".", "~", "/")) or module_path.exists():
            args.playwright_module = str(module_path.resolve())

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "QA_BASE_URL": base}
    if args.chromium:
        env["QA_BROWSER_EXECUTABLE"] = args.chromium
    if args.playwright_module:
        env["QA_PLAYWRIGHT_MODULE"] = args.playwright_module

    started_at = utc_now()
    before = fetch_manifest(base, output, "before")
    python = sys.executable
    chromium = ["--chromium", args.chromium] if args.chromium else []
    firefox = ["--firefox", args.firefox] if args.firefox else []
    home_tls = ["--ignore-https-errors"] if args.ignore_https_errors else []
    accessibility = output / "accessibility.json"
    home = output / "home"
    commands = [
        ("search", ["node", "--test", "--test-reporter=tap", "search-tests/regression.test.cjs"], None),
        ("accessibility", [python, "accessibility-tests/check_accessibility.py", "--base-url", base,
                           "--json", str(accessibility), *chromium], accessibility),
        ("home", [python, "home-tests/check_home.py", base + "/", "--output-dir", str(home),
                  "--record-response-bodies", *chromium, *firefox, *home_tls], home / "results.json"),
        ("editorial", [python, "editorial-tests/probe.py", "--base-url", base], None),
    ]
    suites, home_report = {}, None
    for name, command, report in commands:
        suites[name], details = run_suite(name, command, env, output, report)
        if name == "home":
            home_report = details
            if (os.environ.get("S2S_QA_RECOVER_FIREFOX") == "1" and details
                    and suites[name]["status"] == "probe_unavailable" and suites[name].get("unavailable_checks")):
                from runpy import run_path
                helper = run_path(str(HERE / "followthrough/recover-home-firefox.py"))
                suites[name], home_report = helper["recover"](base, output, suites[name], details,
                                                           allow_test_certificate=args.ignore_https_errors)

    after = fetch_manifest(base, output, "after")
    release_status, release_detail, homepage = manifest_status(before, after, home_report, home)
    suite_states = {report["status"] for report in suites.values()}
    if release_status == "mixed_build":
        status, code = "mixed_build", 3
    elif release_status != "stable" or suite_states - {"assertion_failure", "passed"}:
        status, code = "incomplete", 2
    elif "assertion_failure" in suite_states:
        status, code = "assertion_failure", 1
    else:
        status, code = "passed", 0
    receipt = {"base_url": base, "started_at": started_at, "finished_at": utc_now(), "status": status,
               "home_probe_ignores_https_errors": args.ignore_https_errors,
               "release": {"status": release_status, "detail": release_detail, "homepage": homepage,
                           "before": before, "after": after},
               "suites": suites}
    (output / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"{status} / manifest {release_status} / {output / 'summary.json'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
