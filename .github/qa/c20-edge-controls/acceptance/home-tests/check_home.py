#!/usr/bin/env python3
"""Measure the homepage in Chromium and test navigation with enlarged Firefox text."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright


DEFAULT_URL = "https://sciencetostartup.com/"
NORMAL_CASES = ((320, 720), (390, 844), (768, 1024), (959, 768), (960, 768), (1280, 720))
LARGE_FONT_CASES = ((390, 844), (761, 720), (844, 390))
KINDS = ("company", "work")
FIRST_RECORD_TARGETS = {390: 470, 1280: 500}
KNOWN_SOURCES = {
    ("snorkel.ai", "/blog/data-2-0-and-the-research-era-of-ai-data"):
        r"September 22, 2026[\s\S]*annualized revenue run rate of \$375M",
    ("snorkel.ai", "/expert-community"): r"paid per project[\s\S]*rates based on expertise",
}
BLOCKED_TITLE = re.compile(r"404|page not found|access denied|just a moment|verify you are human", re.I)


def result(name, passed, **detail):
    return {"name": name, "pass": bool(passed), **detail}


def first_card(metrics, kind, *, sourced=False):
    return next((card for card in metrics["cards"]
                 if card["kind"] == kind and (not sourced or card["sources"])), None)


def layout_checks(metrics, size, large_font):
    width, height = size
    viewport_width = metrics["viewport"]["width"]
    tests = [result("horizontal fit", viewport_width <= width + 1 and metrics["scrollWidth"] <= width + 1,
                    scroll_width=metrics["scrollWidth"], viewport_width=viewport_width)]
    bad_nav = [item["label"] for item in metrics["nav"] if not item["onFirstScreen"] or item["clippedText"]]
    search = metrics["search"]
    tests.append(result("header and Search visible", search and not bad_nav and not metrics["overlap"],
                        clipped_items=bad_nav, overlap=metrics["overlap"], search=search))
    if large_font:
        return tests

    heading = metrics["heading"]
    headline = heading["box"]
    tests.append(result("headline on first screen", heading["text"] and headline and headline["bottom"] <= height + 1,
                        headline=heading["text"]))
    for kind, action in metrics["actions"].items():
        tests.append(result(f"{kind} browse action on first screen",
                            action and action["onFirstScreen"] and action["box"]["height"] >= 43,
                            action=action))

    if width in FIRST_RECORD_TARGETS:
        cards = {kind: first_card(metrics, kind, sourced=True) for kind in KINDS}
        for kind, card in cards.items():
            fallback = first_card(metrics, kind)
            tests.append(result(f"{kind} sourced record headline on first screen",
                                card and card["headlineBox"]["bottom"] <= height + 1,
                                title=(card or fallback or {}).get("headline"),
                                record_top=(card or fallback or {}).get("box", {}).get("top")))
            evidence = (card or {}).get("evidence", [])
            sources = (card or {}).get("sources", [])
            tests.append(result(f"{kind} record evidence and source on first screen",
                                any(field["onFirstScreen"] for field in evidence)
                                and any(link["onFirstScreen"] for link in sources),
                                evidence=evidence, sources=sources))
        first = min((card["box"]["top"] for card in cards.values() if card), default=None)
        target = FIRST_RECORD_TARGETS[width]
        tests.append(result("first sourced record position", first is not None and first <= target,
                            measured_top=first, maximum_top=target))
    return tests


def measure(browser, args, probe, size, *, engine, minimum_font=0):
    width, height = size
    tag = f"{engine}-{width}x{height}" + (f"-min-font-{minimum_font}" if minimum_font else "")
    outcome = {"case": tag, "browser": browser.version, "requested_viewport": [width, height],
               "minimum_font_px": minimum_font}
    context = browser.new_context(viewport={"width": width, "height": height},
                                  ignore_https_errors=args.ignore_https_errors,
                                  is_mobile=engine == "chromium" and width <= 390,
                                  has_touch=engine == "chromium" and width <= 390)
    with context:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            response = page.goto(args.url, wait_until="load", timeout=30_000)
            if response:
                outcome.update(http_status=response.status, final_url=page.url)
            if not response or not response.ok:
                raise ValueError(f"Homepage returned HTTP {response.status if response else 'unknown'}")
            body = response.body()
            outcome["html_sha256"] = hashlib.sha256(body).hexdigest()
            if args.output_dir and args.record_response_bodies:
                filename = f"{tag}.html"
                (args.output_dir / filename).write_bytes(body)
                outcome["html_body"] = filename
            page.evaluate("document.fonts.ready")
            metrics = page.evaluate(probe, {"proof": args.design_proof, "canonicalHost": args.canonical_host})
            tests = layout_checks(metrics, size, minimum_font > 0)
            outcome.update(metrics=metrics, tests=tests, javascript_errors=errors)
            if args.output_dir:
                page.screenshot(path=args.output_dir / f"{tag}.png", animations="disabled", scale="css")
        except (Error, ValueError) as error:
            outcome.update(tests=[result("open and measure homepage", False, error=str(error).splitlines()[0])])
    return outcome


def check_source(context, url):
    page = context.new_page()
    response = None
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        title = page.title()
        content = page.locator("body").evaluate("""body => {
          const copy = body.cloneNode(true);
          copy.querySelectorAll('script, style, noscript').forEach(node => node.remove());
          return copy.textContent.replace(/\\s+/g, ' ').trim();
        }""", timeout=20_000)
        parsed = urlsplit(url)
        key = parsed.hostname.removeprefix("www."), parsed.path.rstrip("/")
        expected = KNOWN_SOURCES.get(key)
        sample_matches = not expected or bool(re.search(expected, content, re.I))
        passed = response and response.ok and len(content) >= 100 and not BLOCKED_TITLE.search(title)
        if response is None:
            observation = "no_http_response"
        elif response.status in (404, 410):
            observation = "missing"
        elif response.status in (429, 502, 503, 504) or BLOCKED_TITLE.search(title):
            observation = "temporarily_unverified"
        elif not response.ok:
            observation = "http_error"
        elif passed and sample_matches:
            observation = "source_content_verified"
        else:
            observation = "source_content_mismatch"
        return {"href": url, "final_url": page.url, "status": response.status if response else None,
                "observation": observation,
                "title": title, "known_content_match": sample_matches if expected else None,
                "pass": bool(passed and sample_matches)}
    except Error as error:
        return {"href": url, "final_url": page.url, "pass": False,
                "status": response.status if response else None,
                "observation": "browser_observation_incomplete", "error": str(error).splitlines()[0]}
    finally:
        page.close()


def source_checks(browser, args, desktop_case):
    metrics = desktop_case.get("metrics", {"cards": []})
    tests = []
    with browser.new_context(ignore_https_errors=args.ignore_https_errors) as context:
        for kind in KINDS:
            card = first_card(metrics, kind, sourced=True)
            urls = list(dict.fromkeys(link["href"] for link in (card or {}).get("sources", [])))
            observations = [check_source(context, url) for url in urls]
            tests.append(result(f"{kind} external source opens", any(item["pass"] for item in observations),
                                card=(card or {}).get("headline"), sources=observations))
    return tests


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="HTTP(S) homepage URL")
    parser.add_argument("--output-dir", type=Path, help="Save a JSON report and viewport screenshots here")
    parser.add_argument("--chromium", default=shutil.which("chromium"), help="Chromium executable path")
    parser.add_argument("--firefox", help="Playwright-compatible Firefox executable path")
    parser.add_argument("--skip-firefox", action="store_true", help="Explicitly omit the checks with enlarged text")
    parser.add_argument("--design-proof", action="store_true", help="Accept the proof's in-page #paid-work action")
    parser.add_argument("--ignore-https-errors", action="store_true", help="Allow a development TLS certificate")
    parser.add_argument("--canonical-host", default="sciencetostartup.com", help="Site host for canonical same-site links")
    parser.add_argument("--record-only", action="store_true", help="Record expected failures and exit successfully")
    parser.add_argument("--record-response-bodies", action="store_true", help="Keep exact browser HTML responses with the report")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        parser.error("homepage URL must use HTTP(S)")
    return args


def main():
    args = arguments()
    probe = Path(__file__).with_name("measure.js").read_text()
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"url": args.url, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "design_proof": args.design_proof, "firefox_skipped": args.skip_firefox,
              "cases": [], "source_tests": []}
    with sync_playwright() as playwright:
        with playwright.chromium.launch(executable_path=args.chromium) as chromium:
            report["cases"] = [measure(chromium, args, probe, size, engine="chromium") for size in NORMAL_CASES]
            report["source_tests"] = source_checks(chromium, args, report["cases"][-1])
        if not args.skip_firefox:
            try:
                with playwright.firefox.launch(executable_path=args.firefox,
                                                firefox_user_prefs={"font.minimum-size.x-western": 28}) as firefox:
                    report["cases"].extend(measure(firefox, args, probe, size, engine="firefox", minimum_font=28)
                                           for size in LARGE_FONT_CASES)
            except Error as error:
                report["cases"].append({"case": "firefox", "tests": [result("launch Firefox", False,
                                                                         error=str(error).splitlines()[0])]})

    tests = []
    for scope, rows in [(case["case"], case["tests"]) for case in report["cases"]] + [("sources", report["source_tests"])]:
        tests.extend(rows)
        failed = [row["name"] for row in rows if not row["pass"]]
        print(f"{'FAIL' if failed else 'PASS'} {scope}" + (f" · {', '.join(failed)}" if failed else ""))
    passed = sum(row["pass"] for row in tests)
    report["summary"] = {"passed": passed, "total": len(tests)}
    if args.output_dir:
        (args.output_dir / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"{passed}/{len(tests)} checks passed against {args.url}")
    return 0 if args.record_only or passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
