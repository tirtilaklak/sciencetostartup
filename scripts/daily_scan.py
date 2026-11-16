"""Build the dated daily reading list independently of frozen research editions."""
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from static_pages import document, escape as e, format_date, ORIGIN, render_sitemap

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ("RLHF", "Data", "Evaluation", "Companies")
KINDS = ("Paper", "Dataset", "Release", "Company news")


def load_editions(root=ROOT):
    editions = []
    for path in sorted((root / "data/daily-scan").glob("????-??-??.json")):
        edition = json.loads(path.read_text())
        day = edition["date"]
        if str(date.fromisoformat(day)) != path.stem or day < "2026-11-16":
            raise ValueError("Daily scan date and filename differ")
        items = edition["items"]
        if not 10 <= len(items) <= 20:
            raise ValueError("Daily scans require 10–20 selected items")
        ids, urls = set(), set()
        for item in items:
            if not re.fullmatch(r"[a-z0-9-]+", item["id"]) or item["id"] in ids:
                raise ValueError("Daily scan item IDs must be unique and URL safe")
            ids.add(item["id"])
            if item["kind"] not in KINDS or not item["topics"] or set(item["topics"]) - set(TOPICS):
                raise ValueError("Unknown daily scan filter")
            if date.fromisoformat(item["published_on"]) > date.fromisoformat(day):
                raise ValueError("A scan cannot contain future publications")
            if not isinstance(item.get("sources"), list) or not item["sources"]:
                raise ValueError("Daily scan sources must be a nonempty list")
            if item["sources"][0]["url"] in urls:
                raise ValueError("Duplicate primary source in one daily scan")
            urls.add(item["sources"][0]["url"])
            for source in item["sources"]:
                if not isinstance(source.get("label"), str) or not source["label"].strip():
                    raise ValueError("Daily scan source links require visible labels")
                parsed = urlsplit(source["url"])
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                    raise ValueError("Daily scan source must be a public HTTPS URL")
            for field in ("title", "focus", "finding", "caveat", "publisher", "read_scope", "date_basis"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError("Missing daily scan field: " + field)
        editions.append(edition)
    return editions


def card(item, rank):
    sources = "".join('<li><a href="' + e(s["url"]) + '">' + e(s["label"]) + ' <span aria-hidden="true">↗</span></a></li>' for s in item["sources"])
    topics = " · ".join(item["topics"])
    return (f'<article class="scan-item" id="{e(item["id"])}" data-kind="{e(item["kind"])}" data-topics="{e("|".join(item["topics"]))}">'
            f'<span class="scan-rank" aria-label="Selection {rank}">{rank:02d}</span><div class="scan-item-body">'
            f'<div class="scan-meta"><span class="scan-kind">{e(item["kind"])}</span><span>{e(item["publisher"])}</span>'
            f'<span>Source <time datetime="{item["published_on"]}">{format_date(item["published_on"])}</time></span></div>'
            f'<h2><a href="{e(item["sources"][0]["url"])}">{e(item["title"])} <span class="scan-external" aria-hidden="true">↗</span></a></h2>'
            f'<p class="scan-focus">{e(item["focus"])}</p><div class="scan-bottom"><span class="scan-topic-label">{e(topics)}</span>'
            f'<details><summary>Details & sources</summary><dl><div><dt>Finding</dt><dd>{e(item["finding"])}</dd></div>'
            f'<div><dt>Limits</dt><dd>{e(item["caveat"])}</dd></div>'
            f'<div><dt>Source date</dt><dd>{format_date(item["published_on"])} · {e(item.get("date_basis", "Publication date"))}</dd></div>'
            f'<div><dt>Read scope</dt><dd>{e(item["read_scope"])}</dd></div></dl><ul class="scan-sources">{sources}</ul>'
            f'<a class="scan-permalink" href="#{e(item["id"])}">Link to this item</a></details></div></div></article>')


def render(edition, editions, canonical, root=ROOT):
    day = edition["date"]
    current = next(i for i, row in enumerate(editions) if row["date"] == day)
    def day_link(offset, label):
        target = current + offset
        return (f'<a class="scan-day-step" href="/daily/{editions[target]["date"]}/" aria-label="{label}">{"←" if offset < 0 else "→"}</a>'
                if 0 <= target < len(editions) else f'<span class="scan-day-step" aria-disabled="true">{"←" if offset < 0 else "→"}</span>')
    options = "".join(f'<option value="{row["date"]}"' + (' selected' if row["date"] == day else '') + f'>{format_date(row["date"])}</option>' for row in reversed(editions))
    topic_options = "".join(f'<option>{e(topic)}</option>' for topic in TOPICS)
    kind_options = "".join(f'<option>{e(kind)}</option>' for kind in KINDS)
    items = "".join(card(item, i + 1) for i, item in enumerate(edition["items"]))
    source_dates = [item["published_on"] for item in edition["items"]]
    attribution = json.loads((root / "data/daily-scan/wikipedia-context.json").read_text())
    contexts = "".join(f'<div><h3>{e(row["label"])}</h3><blockquote>{e(row["sentence"])}</blockquote><p class="scan-credit"><a href="{e(row["revision_url"])}">Wikipedia · {e(row["title"])}</a> · <a href="{e(row["history_url"])}">Authors & history</a> · <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a> · Verbatim excerpt</p></div>' for row in attribution["entries"])
    archive = "".join(f'<a href="/daily/{row["date"]}/">{format_date(row["date"])} <span>{len(row["items"])} items</span></a>' for row in reversed(editions))
    body = (f'<div class="daily-scan" data-edition="{day}"><header class="scan-heading"><div><p class="eyebrow">THE DAILY READING LIST</p>'
            '<h1>Daily scan<span>.</span></h1><p class="scan-deck">RLHF, data & the companies behind AI.</p></div>'
            f'<div class="scan-issue"><span>ISSUE {current + 1:03d}</span><strong><time datetime="{day}">{format_date(day)}</time></strong><span>{len(edition["items"])} selections · Pacific time</span></div></header>'
            f'<div class="scan-controls" hidden><div class="scan-date-control"><label for="scan-date">Snapshot date</label><div>{day_link(-1, "Previous snapshot")}<select id="scan-date">{options}</select>{day_link(1, "Next snapshot")}</div></div>'
            '<div class="scan-search-control"><label for="scan-search">Search</label><input id="scan-search" type="search" placeholder="Paper, company or keyword" autocomplete="off"></div>'
            f'<div><label for="scan-topic">Topic</label><select id="scan-topic"><option value="">All topics</option>{topic_options}</select></div>'
            f'<div><label for="scan-kind">Type</label><select id="scan-kind"><option value="">All types</option>{kind_options}</select></div></div>'
            f'<div class="scan-list-heading"><p id="scan-count" role="status" aria-live="polite">{len(edition["items"])} selections</p><span>Source dates: {format_date(min(source_dates))} – {format_date(max(source_dates))}</span><button type="button" id="scan-reset" hidden>Clear filters</button></div>'
            f'<div class="scan-list">{items}</div><div id="scan-empty" class="scan-empty" hidden><h2>No matching items</h2><button type="button" id="scan-empty-reset">Clear filters</button></div>'
            '<footer class="scan-notes"><details><summary>Dates, sources & background</summary><dl><div><dt>Snapshot</dt><dd>Selection date in America/Los_Angeles</dd></div><div><dt>Source date</dt><dd>Original publication, release or arXiv submission; updates labeled separately</dd></div><div><dt>Selection</dt><dd>Recent papers, datasets and company announcements; source-linked facts; author and company results attributed</dd></div><div><dt>Coverage</dt><dd>Selected reading list; abstracts and announcements where indicated; no independent replication</dd></div><div><dt>Writing</dt><dd>Structured source facts and titles; verbatim Wikipedia background excerpts below</dd></div></dl>'
            f'<div class="scan-context">{contexts}</div><a href="/daily/wikipedia-context.json">Wikipedia revision & download records</a></details>'
            f'<details><summary>Snapshot archive</summary><div class="scan-archive">{archive}</div></details><a class="scan-download" href="/daily/{day}/snapshot.json" download>Download this snapshot · JSON</a></footer></div>')
    page = document(SimpleNamespace(as_of="", data={}), "Daily scan · ScienceToStartup", "Daily reading list: RLHF, data, evaluation and AI company news, with dated snapshots and original sources.", canonical, body, current="daily")
    return page.replace('</head>', '<link rel="stylesheet" href="/daily-scan.css">\n<script src="/daily-scan.js" defer></script>\n</head>')


def write_daily_scan(destination, root=ROOT):
    editions = load_editions(root)
    if not editions:
        return
    folder = destination / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for edition in editions:
        dated = folder / edition["date"]
        dated.mkdir(exist_ok=True)
        (dated / "index.html").write_text(render(edition, editions, ORIGIN + '/daily/' + edition["date"] + '/', root))
        (dated / "snapshot.json").write_text(json.dumps(edition, ensure_ascii=False, indent=2) + '\n')
    (folder / 'index.html').write_text(render(editions[-1], editions, ORIGIN + '/daily/', root))
    (folder / 'wikipedia-context.json').write_bytes((root / 'data/daily-scan/wikipedia-context.json').read_bytes())
    (folder / 'index.json').write_text(json.dumps({'first_date': editions[0]['date'], 'latest_date': editions[-1]['date'], 'snapshots': [{'date': row['date'], 'count': len(row['items']), 'url': '/daily/' + row['date'] + '/'} for row in reversed(editions)]}, indent=2) + '\n')
    namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    sitemap = ET.parse(destination / 'sitemap.xml').getroot()
    entries = [(node.findtext(namespace + 'loc'), node.findtext(namespace + 'lastmod')) for node in sitemap]
    entries += [(ORIGIN + '/daily/', editions[-1]['date'])] + [(ORIGIN + '/daily/' + row['date'] + '/', row['date']) for row in editions]
    (destination / 'sitemap.xml').write_text(render_sitemap(entries))
