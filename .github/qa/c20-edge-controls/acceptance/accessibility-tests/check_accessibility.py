#!/usr/bin/env python3
"""Exercise the accessibility regressions found in the November 22 site audit."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright


LIVE = "https://sciencetostartup.com"
VIEWPORT = {"width": 320, "height": 720}
ACTIONS = ".work-listing-action a, .work-action a"
BROWSE = ("/companies/", "/work/", "/research/")


def open_page(page, base, path):
    response = page.goto(base + path, wait_until="load")
    if response is None or not response.ok:
        raise ValueError(f"{path} returned HTTP {response.status if response else 'unknown'}")


def absolute_navigation(context, base):
    """Keep canonical same-site links on the tested build, even on localhost."""
    if base != LIVE:
        context.route(
            re.compile(r"^https://sciencetostartup\.com/"),
            lambda route: route.fulfill(
                status=307,
                headers={"Location": base + route.request.url.removeprefix(LIVE), "Cache-Control": "no-store"},
            ),
        )


def work_names(page, base, path):
    open_page(page, base, path)
    links = page.locator(ACTIONS)
    # Reveal historical groups in the browser so Chromium can compute each name.
    links.evaluate_all("""links => links.forEach(link => {
      for (let item = link.closest('details'); item; item = item.parentElement.closest('details')) {
        item.open = true;
      }
    })""")
    dom = page.context.new_cdp_session(page)
    try:
        root = dom.send("DOM.getDocument", {"depth": -1})["root"]
        ids = dom.send("DOM.querySelectorAll", {"nodeId": root["nodeId"], "selector": ACTIONS})["nodeIds"]
        backend = {}
        stack = [root]
        while stack:
            node = stack.pop()
            backend[node["nodeId"]] = node["backendNodeId"]
            stack.extend(node.get("children", []))
        names = {
            node["backendDOMNodeId"]: node.get("name", {}).get("value", "")
            for node in dom.send("Accessibility.getFullAXTree")["nodes"]
            if "backendDOMNodeId" in node and node.get("role", {}).get("value") == "link"
        }
    finally:
        dom.detach()
    text = links.all_inner_texts()

    def normalize(value):
        return " ".join(value.casefold().split())

    pairs = [(label, names.get(backend[node_id], "")) for label, node_id in zip(text, ids)]
    mismatches = [
        {"text": label, "accessible_name": name}
        for label, name in pairs if not label.strip() or not normalize(name).startswith(normalize(label))
    ]
    return bool(pairs) and not mismatches and len(ids) == len(text), {
        "total": len(ids), "mismatches": len(mismatches), "examples": mismatches[:3],
    }


def research_current(page, base, path):
    open_page(page, base, path)
    page.evaluate("document.fonts.ready")
    data = page.locator('.r-nav [aria-current="page"]').evaluate("""active => {
      const nav = active.closest('nav').getBoundingClientRect();
      const link = active.getBoundingClientRect();
      return {
        current: active.innerText,
        link: [Math.round(link.left), Math.round(link.right)],
        visible_area: [Math.max(0, Math.round(nav.left)), Math.min(innerWidth, Math.round(nav.right))],
        visible: link.width > 0 && link.left >= Math.max(0, nav.left) - 1
          && link.right <= Math.min(innerWidth, nav.right) + 1
      };
    }""")
    return data.pop("visible"), data


def native_search(page, base, path, mode):
    open_page(page, base, path)
    control = page.locator("body > header .site-search-open:visible").first
    if not control.count():
        browse = page.locator("body > header a[href], main .availability-notice a[href]").evaluate_all(
            """links => links.filter(link => link.getClientRects().length
              && /browse/i.test(link.innerText)).map(link => link.pathname)"""
        )
        return any(target in BROWSE for target in browse), {"mode": mode, "visible_browse_links": browse}

    control.click()
    page.wait_for_load_state("domcontentloaded")
    location = urlsplit(page.url)
    detail = {"mode": mode, "destination": location.path + (
        "?" + location.query if location.query else ""
    ) + ("#" + location.fragment if location.fragment else "")}
    if page.locator("dialog[open]:visible").count() or page.get_by_role("searchbox").and_(
        page.locator(":visible")
    ).count():
        return True, detail
    if location.path in BROWSE and location.path != path and page.locator("main h1:visible").count():
        return True, detail
    if location.fragment:
        target = page.locator(":target:visible").first
        if target.count():
            links = target.get_by_role("link").evaluate_all(
                "links => links.filter(link => link.getClientRects().length).map(link => link.pathname)"
            )
            detail["fallback_links"] = links
            return any(path in BROWSE for path in links), detail
    if location.path == "/search/":
        links = page.locator("main a:visible").evaluate_all("links => links.map(link => link.pathname)")
        detail["fallback_links"] = links
        return any(path in BROWSE for path in links), detail
    return False, detail


def caret_keys(page, base):
    open_page(page, base, "/")
    page.locator("#home-search-open").click()
    field = page.get_by_role("combobox", name="Search the guide")
    field.fill("Mercor")
    page.locator("#home-search-results [role=option]").first.wait_for()
    field.press("Home")
    home = field.evaluate("input => input.selectionStart")
    field.press("End")
    end = field.evaluate("input => input.selectionStart")
    field.press("ArrowDown")
    selected = field.get_attribute("aria-activedescendant")
    return (home, end) == (0, 6) and bool(selected), {"home": home, "end": end, "arrow_active": selected}


def run(browser, base):
    results = []

    def check(page, test, path, probe, *extra):
        try:
            passed, detail = probe(page, base, *extra)
            results.append({"test": test, "path": path, "pass": passed, **detail})
        except (Error, ValueError) as error:
            results.append({"test": test, "path": path, "pass": False, "error": str(error).splitlines()[0]})

    for mode in ("normal", "no-js", "runtime-blocked"):
        with browser.new_context(viewport=VIEWPORT, java_script_enabled=mode != "no-js") as context:
            absolute_navigation(context, base)
            if mode == "runtime-blocked":
                context.route(re.compile(r"/home-runtime\.js(?:\?|$)"), lambda route: route.abort())
            page = context.new_page()
            page.set_default_timeout(8_000)
            if mode == "normal":
                for path in ("/work/", "/company/afterquery/", "/company/mercor/", "/company/scale_ai/"):
                    check(page, "action-name", path, work_names, path)
                check(page, "search-caret", "/", caret_keys)
            if mode == "no-js":
                for path in ("/research/data/", "/review/", "/research/benchmarks/"):
                    check(page, "research-current-visible", path, research_current, path)
            if mode != "normal":
                for path in ("/work/", "/daily/", "/research/", "/") + (
                    ("/explore/",) if mode == "no-js" else ()
                ):
                    check(page, "native-search", path, native_search, path, mode)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=LIVE, help="Root URL of the running site or candidate")
    parser.add_argument("--chromium", type=Path, default=shutil.which("chromium"),
                        help="Chromium executable. If omitted, use system or Playwright Chromium.")
    parser.add_argument("--json", type=Path, help="Write detailed results to this file")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urlsplit(base).scheme not in ("http", "https") or not urlsplit(base).netloc:
        parser.error("--base-url must be an HTTP(S) URL")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium)
        results = run(browser, base)
        browser.close()

    for record in results:
        status = "PASS" if record["pass"] else "FAIL"
        detail = {k: v for k, v in record.items() if k not in ("test", "path", "pass")}
        print(f"{status} {record['test']} {record['path']} {json.dumps(detail, ensure_ascii=False)}")
    count = sum(record["pass"] for record in results)
    print(f"{count}/{len(results)} checks passed against {base}")
    if args.json:
        args.json.write_text(json.dumps({
            "base_url": base, "checked_at": datetime.now(timezone.utc).isoformat(), "results": results,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return int(count != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
