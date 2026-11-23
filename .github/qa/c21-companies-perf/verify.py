"""Verify a frozen prototype and its reference on one clean browser runner."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
TEMP = Path(os.environ["RUNNER_TEMP"]) / "companies-perf"
EVIDENCE = Path(os.environ["RUNNER_TEMP"]) / "companies-perf-evidence"
EXPECTED = json.loads((QA / "identities.json").read_text())


def run(name, args, *, cwd=ROOT, env=None):
    with (EVIDENCE / f"{name}.log").open("w") as log:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    print(f"{name} exited with {result.returncode}", flush=True)
    return result.returncode


def freeze(label, source, destination):
    if run(f"{label}-build", [sys.executable, "scripts/build_public_snapshot.py", "--output", str(destination)], cwd=source):
        raise RuntimeError(f"{label} build failed")
    manifest = (destination / "manifest.json").read_bytes()
    (EVIDENCE / f"{label}-manifest.json").write_bytes(manifest)
    if sha256(manifest).hexdigest() != EXPECTED[label]["manifest"]:
        raise RuntimeError(f"{label} artifact differs from the locally frozen manifest")


@contextmanager
def preview(label, dist, port):
    origin = f"http://127.0.0.1:{port}"
    with (EVIDENCE / f"{label}-origin.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "scripts/preview_server.py", "--directory", str(dist), "--port", str(port)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(50):
                try:
                    with urlopen(origin + "/manifest.json", timeout=2) as response:
                        manifest = response.read()
                    if sha256(manifest).hexdigest() != EXPECTED[label]["manifest"]:
                        raise RuntimeError(f"{label} origin served a different manifest")
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"{label} origin did not start")
            yield origin
        finally:
            process.terminate()
            process.wait(timeout=10)


def report_comparison():
    routes = {}
    for label in EXPECTED:
        summaries = sorted((EVIDENCE / f"{label}-lighthouse").glob("*/summary.json"))
        if len(summaries) != 1:
            raise RuntimeError(f"{label} Lighthouse summary missing")
        summary_path = summaries[0]
        summary = json.loads(summary_path.read_text())
        route, = summary["routes"]
        if summary["manifestSha256"] != EXPECTED[label]["manifest"] or route["route"] != "/explore/#companies":
            raise RuntimeError(f"{label} Lighthouse identity differs")
        runs = []
        for receipt in route["runReports"]:
            report = (summary_path.parent / receipt["report"]).read_bytes()
            if sha256(report).hexdigest() != receipt["reportSha256"]:
                raise RuntimeError(f"{label} Lighthouse report digest differs")
            audits = json.loads(report)["audits"]
            resources = audits["network-requests"]["details"]["items"]
            runs.append({
                "simulatedLcpMs": audits["largest-contentful-paint"]["numericValue"],
                "observedLcpMs": audits["metrics"]["details"]["items"][0]["observedLargestContentfulPaint"],
                "requests": len(resources),
                "transferBytes": sum(item["transferSize"] for item in resources),
                "workRequests": [item["url"] for item in resources if "/presentation/summary." in item["url"]],
                "bootData": [{"url": item["url"], "transferBytes": item["transferSize"]}
                             for item in resources if "/js/" in item["url"] and "-data." in item["url"]
                             or "/js/data." in item["url"]],
            })
        routes[label] = {"settings": summary["resolvedSettingsSha256"], "limitedRoutePassed": route["passed"],
                         "medians": route["medians"], "manifest": summary["manifestSha256"], "runs": runs}
    if routes["reference"]["settings"] != routes["prototype"]["settings"]:
        raise RuntimeError("Lighthouse settings differ between artifacts")
    (EVIDENCE / "comparison.json").write_text(json.dumps(routes, indent=2) + "\n")


def main():
    TEMP.mkdir()
    reference = TEMP / "reference-source"
    reference_dist, prototype_dist = TEMP / "reference-dist", TEMP / "prototype-dist"
    source = subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=ROOT, text=True).strip()
    if source != EXPECTED["prototype"]["source"]:
        raise RuntimeError("QA workflow is not a single commit above the frozen source")
    if run("reference-checkout", ["git", "worktree", "add", "--detach", str(reference), EXPECTED["reference"]["source"]]):
        raise RuntimeError("Reference source checkout failed")
    (reference / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
    freeze("reference", reference, reference_dist)
    freeze("prototype", ROOT, prototype_dist)
    if run("projection", ["node", str(QA / "projection.cjs"), str(prototype_dist), str(reference_dist)]):
        raise RuntimeError("Work projection or recovery probe failed")
    # Pin the official settings, runner and policy. Only narrow the route list in this copy.
    official = (ROOT / "scripts/performance_audit.mjs").read_text()
    line = "const performance = policy.performance;"
    if official.count(line) != 1:
        raise RuntimeError("Performance runner has changed its policy entry point")
    narrow = ROOT / "scripts/companies_perf_trial.mjs"
    narrow.write_text(official.replace(line, "const performance = {...policy.performance, routes: ['/explore/#companies']};"))
    outcomes = {}
    with preview("reference", reference_dist, 18770) as reference_origin, preview("prototype", prototype_dist, 18771) as prototype_origin:
        env = {**os.environ, "QA_BASE_URL": prototype_origin, "QA_REFERENCE_URL": reference_origin,
               "PLAYWRIGHT_JSON_OUTPUT_NAME": str(EVIDENCE / "browser.json")}
        outcomes["browser"] = run("browser", ["node", "node_modules/@playwright/test/cli.js", "test",
                                           "tests/browser/companies-deferred-work.spec.js", "--workers=1", "--retries=0",
                                           "--project=chromium", "--project=mobile-chromium", "--reporter=list,json",
                                           "--output", str(EVIDENCE / "browser-results")], env=env)
        for label, dist, origin in (("reference", reference_dist, reference_origin), ("prototype", prototype_dist, prototype_origin)):
            outcomes[f"{label}-lighthouse"] = run(f"{label}-lighthouse", ["node", str(narrow), "--base-url", origin,
                    "--dist", str(dist), "--runs", "3", "--output", str(EVIDENCE / f"{label}-lighthouse")])
        report_comparison()
    (EVIDENCE / "outcomes.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    if any(outcomes.values()):
        raise RuntimeError("One or more proof checks failed. See the retained reports.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        (EVIDENCE / "failure.txt").write_text(f"{type(error).__name__}: {error}\n")
        raise
