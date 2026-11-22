"""Build the dated daily reading list independently of frozen research editions."""
import json
import ipaddress
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from static_pages import document, escape as e, format_date, ORIGIN, PUBLISHER_NAME, render_sitemap

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ("RLHF", "Data", "Evaluation", "Companies")
KINDS = ("Paper", "Dataset", "Release", "Company news")
RECENT_EDITIONS = 30
WIKI_FIELDS = {"label", "title", "sentence", "article_url", "revision_id", "revision_timestamp",
               "revision_url", "history_url", "download_sha256", "downloaded_at", "normalization", "license"}


@dataclass(frozen=True)
class DailyContext:
    """Validated inputs shared by HTML, feeds and compact search; never a public sidecar."""
    editions: tuple
    wikipedia: dict
    wikipedia_bytes: bytes
    edition_bytes: tuple = ()


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Daily dates must be calendar days")
    return date.fromisoformat(value)


def _instant(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValueError("Daily provenance timestamps require an explicit timezone")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.utcoffset() is None:
        raise ValueError("Daily provenance timestamps require an explicit timezone")
    return instant


def _public_url(value):
    """Validate a public link offline, without fetching it or changing its spelling."""
    if (not isinstance(value, str) or re.search(r"[\s\x00-\x1f\x7f\\]", value)
            or re.search(r"%(?![0-9a-fA-F]{2})", value)
            or re.search(r"[\x00-\x1f\x7f\\]", unquote(value))):
        raise ValueError("Daily scan source must be a public HTTPS URL")
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or port not in (None, 443)):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            labels = host.rstrip(".").split(".")
            if (len(labels) < 2 or labels[-1].lower() in {"local", "internal", "localhost", "test", "invalid"}
                    or labels[-1].isdigit()
                    or any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in labels)):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
        return parsed
    except (TypeError, ValueError) as error:
        raise ValueError("Daily scan source must be a public HTTPS URL") from error


def _primary_key(url):
    parsed = _public_url(url)
    return urlunsplit((parsed.scheme, parsed.hostname.lower().rstrip("."), parsed.path or "/", parsed.query, ""))


def load_wikipedia_context(root=ROOT):
    raw = (Path(root) / "data/daily-scan/wikipedia-context.json").read_bytes()
    context = json.loads(raw)
    if not isinstance(context, dict) or set(context) != {"entries"} or not isinstance(context["entries"], list):
        raise ValueError("Daily Wikipedia context requires entries")
    seen = set()
    for row in context["entries"]:
        if not isinstance(row, dict) or set(row) != WIKI_FIELDS:
            raise ValueError("Daily Wikipedia context has missing or unsupported fields")
        for key in WIKI_FIELDS - {"revision_id"}:
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError("Daily Wikipedia context requires text: " + key)
        if type(row["revision_id"]) is not int or row["revision_id"] <= 0:
            raise ValueError("Daily Wikipedia revision must be a positive integer")
        if row["license"] != "CC BY-SA 4.0" or not re.fullmatch(r"[0-9a-f]{64}", row["download_sha256"]):
            raise ValueError("Daily Wikipedia context requires its exact license and SHA-256")
        if _instant(row["revision_timestamp"]) > _instant(row["downloaded_at"]):
            raise ValueError("Daily Wikipedia revision cannot follow its download")
        title = row["title"].replace(" ", "_")
        for key in ("article_url", "revision_url", "history_url"):
            parsed = _public_url(row[key])
            if parsed.hostname != "en.wikipedia.org" or parsed.fragment:
                raise ValueError("Daily Wikipedia links require en.wikipedia.org")
            query = parse_qsl(parsed.query, keep_blank_values=True)
            if len({key for key, _ in query}) != len(query):
                raise ValueError("Daily Wikipedia query keys must be unique")
            query = dict(query)
            if key == "article_url":
                valid = unquote(parsed.path) == "/wiki/" + title and not query
            elif key == "revision_url":
                valid = (parsed.path == "/w/index.php" and set(query) in ({"oldid"}, {"oldid", "title"})
                         and query.get("oldid") == str(row["revision_id"])
                         and query.get("title", title).replace(" ", "_") == title)
            else:
                valid = (parsed.path == "/w/index.php" and set(query) == {"title", "action"}
                         and query["title"].replace(" ", "_") == title and query["action"] == "history")
            if not valid:
                raise ValueError("Daily Wikipedia article, revision and history must match")
        identity = (row["title"], row["revision_id"])
        if identity in seen:
            raise ValueError("Daily Wikipedia context repeats a revision")
        seen.add(identity)
    return context, raw


def load_daily_context(root=ROOT):
    sources = tuple(_edition_sources(root))
    wikipedia, raw = load_wikipedia_context(root)
    return DailyContext(tuple(edition for edition, _ in sources), wikipedia, raw,
                        tuple(blob for _, blob in sources))


def load_editions(root=ROOT):
    return [edition for edition, _ in _edition_sources(root)]


def _edition_sources(root):
    for path in sorted((Path(root) / "data/daily-scan").glob("????-??-??.json")):
        raw = path.read_bytes()
        edition = json.loads(raw.decode("utf-8"))
        if not isinstance(edition, dict):
            raise ValueError("Daily scan must be an object")
        day = edition.get("date")
        if str(_day(day)) != path.stem or day < "2026-11-16":
            raise ValueError("Daily scan date and filename differ")
        if "timezone" in edition and edition["timezone"] != "America/Los_Angeles":
            raise ValueError("Daily selection dates use America/Los_Angeles")
        if "compiled_at" in edition:
            _instant(edition["compiled_at"])
        items = edition.get("items")
        if not isinstance(items, list) or not 10 <= len(items) <= 20:
            raise ValueError("Daily scans require 10–20 selected items")
        ids, urls = set(), set()
        for item in items:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not re.fullmatch(r"[a-z0-9-]+", item["id"]) or item["id"] in ids):
                raise ValueError("Daily scan item IDs must be unique and URL safe")
            ids.add(item["id"])
            if (item.get("kind") not in KINDS or not isinstance(item.get("topics"), list)
                    or not item["topics"] or any(topic not in TOPICS for topic in item["topics"])):
                raise ValueError("Unknown daily scan filter")
            if _day(item.get("published_on")) > _day(day):
                raise ValueError("A scan cannot contain future publications")
            if not isinstance(item.get("sources"), list) or not item["sources"]:
                raise ValueError("Daily scan sources must be a nonempty list")
            for source in item["sources"]:
                if not isinstance(source, dict) or not isinstance(source.get("label"), str) or not source["label"].strip():
                    raise ValueError("Daily scan source links require visible labels")
                _public_url(source.get("url"))
            primary = _primary_key(item["sources"][0]["url"])
            if primary in urls:
                raise ValueError("Duplicate primary source in one daily scan")
            urls.add(primary)
            if "source_timestamp" in item:
                if _instant(item["source_timestamp"]).date().isoformat() != item["published_on"]:
                    raise ValueError("Daily source timestamp and source day differ")
            for field in ("title", "focus", "finding", "caveat", "publisher", "read_scope", "date_basis"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError("Missing daily scan field: " + field)
            explanation = item.get("explanation")
            if not isinstance(explanation, list) or not 2 <= len(explanation) <= 4:
                raise ValueError("Daily scan explanations require 2–4 sentences")
            for sentence in explanation:
                if (not isinstance(sentence, str) or not sentence.strip()
                        or not any(character.isalnum() for character in sentence)
                        or not re.search(r'''[.!?]["'”’\)\]]*$''', sentence.rstrip())):
                    raise ValueError("Daily scan explanation sentences require text and a sentence ending")
        yield edition, raw


def _edition_path(edition):
    return f'/daily/{edition["date"]}/'


def edition_url(edition):
    return ORIGIN + _edition_path(edition)


def item_url(edition, item):
    return edition_url(edition) + "#" + item["id"]


def daily_search_entries(context):
    """Only recent public reading-list prose; never workers or provenance receipts."""
    if context is None or not context.editions:
        return []
    rows = [{"title": "Daily scan", "summary": "Source-linked reading lists on AI data and evaluation. Search recent selections or browse the full dated archive. No independent replication.",
             "url": "/daily/", "kind": "daily", "keywords": ["daily", "reading list", "archive", "papers", "company news"]}]
    for edition in reversed(context.editions[-RECENT_EDITIONS:]):
        for item in edition["items"]:
            # Do not clip a substantive caveat mid-sentence into a misleading
            # search claim. The full qualification stays at the dated target.
            summary = (f'Daily selection {edition["date"]}; source {item["published_on"]}. '
                       'Read the dated selection for source-attributed findings, material limits and read scope. '
                       'No independent replication.')
            rows.append({"title": item["title"], "summary": summary,
                         "url": item_url(edition, item).removeprefix(ORIGIN), "kind": "daily",
                         "keywords": [*item["topics"], item["kind"], item["publisher"], edition["date"]]})
    return rows


def daily_search_scope(context):
    editions = context.editions[-RECENT_EDITIONS:] if context else ()
    return {"editionLimit": RECENT_EDITIONS, "editionCount": len(editions),
            "firstDate": editions[0]["date"] if editions else None,
            "latestDate": editions[-1]["date"] if editions else None}


def daily_feed_records(context):
    records = []
    for edition in reversed(context.editions[-RECENT_EDITIONS:]):
        lines = [f'Selection day: {format_date(edition["date"])} · America/Los_Angeles.',
                 f'{len(edition["items"])} sourced selections. Source dates are original publication dates, not issue publication times.']
        for item in edition["items"]:
            lines += ["", item["title"], " ".join(sentence.strip() for sentence in item["explanation"]),
                      f'Source: {item["publisher"]} · {item["published_on"]} · {item["date_basis"]}.',
                      "Limits: " + item["caveat"], "Read scope: " + item["read_scope"],
                      "Inspect this selection: " + item_url(edition, item)]
            lines += [source["label"] + ": " + source["url"] for source in item["sources"]]
        records.append({"id": edition_url(edition), "url": edition_url(edition),
                        "title": "Daily scan · " + format_date(edition["date"]),
                        "content_text": "\n".join(lines)})
    return records


def write_daily_feeds(folder, context):
    records = daily_feed_records(context)
    feed = {"version": "https://jsonfeed.org/version/1.1", "title": "ScienceToStartup Daily scan",
            "home_page_url": ORIGIN + "/daily/", "feed_url": ORIGIN + "/daily/feed.json",
            "description": "The latest 30 selected reading lists on RLHF, data, evaluation and AI companies.",
            "language": "en", "authors": [{"name": PUBLISHER_NAME, "url": ORIGIN + "/method/#about"}],
            "items": records}
    (folder / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    for key, value in (("title", feed["title"]), ("link", feed["home_page_url"]),
                       ("description", feed["description"]), ("language", "en")):
        ET.SubElement(channel, key).text = value
    for row in records:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = row["title"]
        ET.SubElement(item, "link").text = row["url"]
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = row["id"]
        # RSS descriptions permit HTML. Escape the prose before XML encoding so
        # source text cannot turn into active markup in a feed reader.
        ET.SubElement(item, "description").text = "".join("<p>" + e(line) + "</p>" for line in row["content_text"].splitlines() if line)
    (folder / "feed.xml").write_bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n")


def card(item, rank, edition):
    sources = "".join('<li><a href="' + e(s["url"]) + '">' + e(s["label"]) + ' <span aria-hidden="true">↗</span></a></li>' for s in item["sources"])
    topics = " · ".join(item["topics"])
    explanation = " ".join(sentence.strip() for sentence in item["explanation"])
    return (f'<article class="scan-item" id="{e(item["id"])}" data-kind="{e(item["kind"])}" data-topics="{e("|".join(item["topics"]))}">'
            f'<span class="scan-rank" aria-label="Selection {rank}">{rank:02d}</span><div class="scan-item-body">'
            f'<div class="scan-meta"><span class="scan-kind">{e(item["kind"])}</span><span>{e(item["publisher"])}</span>'
            f'<span>Source <time datetime="{item["published_on"]}">{format_date(item["published_on"])}</time></span></div>'
            f'<h2><a href="{e(item["sources"][0]["url"])}">{e(item["title"])} <span class="scan-external" aria-hidden="true">↗</span></a></h2>'
            f'<p class="scan-explanation">{e(explanation)}</p><div class="scan-bottom"><span class="scan-topic-label">{e(topics)}</span>'
            f'<details><summary>Details & sources</summary><dl><div><dt>Focus</dt><dd>{e(item["focus"])}</dd></div>'
            f'<div><dt>Finding</dt><dd>{e(item["finding"])}</dd></div>'
            f'<div><dt>Limits</dt><dd>{e(item["caveat"])}</dd></div>'
            f'<div><dt>Source date</dt><dd>{format_date(item["published_on"])} · {e(item.get("date_basis", "Publication date"))}</dd></div>'
            f'<div><dt>Read scope</dt><dd>{e(item["read_scope"])}</dd></div></dl><ul class="scan-sources">{sources}</ul>'
            f'<a class="scan-permalink" href="{e(item_url(edition, item).removeprefix(ORIGIN))}">Link to this item</a></details></div></div></article>')


def render(edition, editions, canonical, root=ROOT, context=None):
    day = edition["date"]
    current = next(i for i, row in enumerate(editions) if row["date"] == day)
    steps = "".join(
        f'<a class="scan-day-step" href="{_edition_path(editions[target])}" rel="{relation}">'
        f'{label} · {format_date(editions[target]["date"])}</a>'
        for target, relation, label in ((current - 1, "prev", "Previous snapshot"), (current + 1, "next", "Next snapshot"))
        if 0 <= target < len(editions)
    )
    if steps:
        steps = f'<div class="scan-edition-steps">{steps}</div>'
    options = "".join(f'<option value="{row["date"]}"' + (' selected' if row["date"] == day else '') + f'>{format_date(row["date"])}</option>' for row in reversed(editions))
    topic_options = "".join(f'<option>{e(topic)}</option>' for topic in TOPICS)
    kind_options = "".join(f'<option>{e(kind)}</option>' for kind in KINDS)
    items = "".join(card(item, i + 1, edition) for i, item in enumerate(edition["items"]))
    source_dates = [item["published_on"] for item in edition["items"]]
    attribution = context.wikipedia if context is not None else load_wikipedia_context(root)[0]
    contexts = "".join(f'<div><h3>{e(row["label"])}</h3><blockquote>{e(row["sentence"])}</blockquote><p class="scan-credit"><a href="{e(row["revision_url"])}">Wikipedia · {e(row["title"])}</a> · <a href="{e(row["history_url"])}">Authors & history</a> · <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a> · Verbatim excerpt</p></div>' for row in attribution["entries"])
    archive = "".join(
        f'<a href="{_edition_path(row)}"' + (' aria-current="date"' if row["date"] == day else '') +
        f'>{format_date(row["date"])} <span>{len(row["items"])} items</span></a>'
        for row in reversed(editions)
    )
    body = (f'<div class="daily-scan" data-edition="{day}"><header class="scan-heading"><div><p class="eyebrow">THE DAILY READING LIST</p>'
            '<h1>Daily scan<span>.</span></h1><p class="scan-deck">RLHF, data & the companies behind AI.</p></div>'
            f'<div class="scan-issue"><span>ISSUE {current + 1:03d}</span><strong><time datetime="{day}">{format_date(day)}</time></strong><span>{len(edition["items"])} selections · Pacific time</span></div></header>'
            '<nav class="scan-follow" aria-label="Follow Daily scan"><strong>Follow Daily scan</strong> · '
            '<a href="/daily/feed.xml">RSS</a> · <a href="/daily/feed.json">JSON Feed</a> · '
            '<a href="/research/feed.xml">Research editions</a> · <a href="/research/corrections/feed.xml">Research corrections</a></nav>'
            f'<nav class="scan-edition-nav" aria-label="Snapshots">{steps}'
            # Keep the links visible on a native history return even when the
            # browser recreates the document and loses its disclosure state.
            f'<details class="scan-archive-disclosure" open><summary>Snapshot archive</summary><div class="scan-archive">{archive}</div></details>'
            '<script>document.currentScript.previousElementSibling.open=false</script>'
            f'<form class="scan-date-form" hidden><label for="scan-date">Snapshot date</label>'
            f'<div><select id="scan-date">{options}</select><button id="scan-date-go" type="submit">Go</button></div></form></nav>'
            '<div class="scan-controls" hidden>'
            '<div class="scan-search-control"><label for="scan-search">Search</label><input id="scan-search" type="search" placeholder="Paper, company or keyword" autocomplete="off"></div>'
            f'<div><label for="scan-topic">Topic</label><select id="scan-topic"><option value="">All topics</option>{topic_options}</select></div>'
            f'<div><label for="scan-kind">Type</label><select id="scan-kind"><option value="">All types</option>{kind_options}</select></div></div>'
            f'<div class="scan-list-heading"><p id="scan-count" role="status" aria-live="polite">{len(edition["items"])} selections</p><span>Source dates: {format_date(min(source_dates))} – {format_date(max(source_dates))}</span><button type="button" id="scan-reset" hidden>Clear filters</button></div>'
            f'<div class="scan-list">{items}</div><div id="scan-empty" class="scan-empty" hidden><h2>No matching items</h2><button type="button" id="scan-empty-reset">Clear filters</button></div>'
            '<footer class="scan-notes"><details><summary>Dates, sources & background</summary><dl><div><dt>Snapshot</dt><dd>Selection date in America/Los_Angeles</dd></div><div><dt>Source date</dt><dd>Original publication, release or arXiv submission; updates labeled separately</dd></div><div><dt>Selection</dt><dd>Recent papers, datasets and company announcements; source-linked facts; author and company results attributed</dd></div><div><dt>Coverage</dt><dd>Selected reading list; abstracts and announcements where indicated; no independent replication</dd></div><div><dt>Writing</dt><dd>Plain-language explanations paraphrase original sources; verbatim Wikipedia background excerpts below</dd></div></dl>'
            f'<div class="scan-context">{contexts}</div><a href="/daily/wikipedia-context.json">Wikipedia revision & download records</a></details>'
            f'<p>Site search covers the latest {RECENT_EDITIONS} Daily editions.</p>'
            f'<a class="scan-download" href="{_edition_path(edition)}snapshot.json" download>Download this snapshot · JSON</a></footer></div>')
    latest_label = ' · Latest reading list' if canonical == ORIGIN + '/daily/' else ''
    title = f'Daily scan: {format_date(day)}{latest_label} · ScienceToStartup'
    description = f'{len(edition["items"])} sourced selections for {format_date(day)}: RLHF, data, evaluation and AI company news. Original source dates and limits retained.'
    page = document(SimpleNamespace(as_of="", data={}), title, description, canonical, body, current="daily")
    pending = '<script>document.documentElement.setAttribute("data-daily-pending","");addEventListener("error",function(event){if(event.error||event.target.hasAttribute&&event.target.hasAttribute("data-daily-script"))document.documentElement.removeAttribute("data-daily-pending")},true)</script>'
    return page.replace('<head>', '<head>' + pending).replace('</head>', '<link rel="alternate" type="application/rss+xml" title="Daily scan RSS" href="/daily/feed.xml">\n<link rel="alternate" type="application/feed+json" title="Daily scan JSON Feed" href="/daily/feed.json">\n<link rel="stylesheet" href="/daily-scan.css">\n<script src="/daily-scan.js" data-daily-script defer></script>\n</head>')


def write_daily_scan(destination, root=ROOT, context=None):
    context = context if context is not None else load_daily_context(root)
    editions = context.editions
    if not editions:
        return
    folder = destination / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for edition, raw in zip(editions, context.edition_bytes, strict=True):
        dated = folder / edition["date"]
        dated.mkdir(exist_ok=True)
        (dated / "index.html").write_text(render(edition, editions, edition_url(edition), root, context))
        (dated / "snapshot.json").write_bytes(raw)
    (folder / 'index.html').write_text(render(editions[-1], editions, ORIGIN + '/daily/', root, context))
    (folder / 'wikipedia-context.json').write_bytes(context.wikipedia_bytes)
    write_daily_feeds(folder, context)
    snapshots = [{'date': row['date'], 'count': len(row['items']), 'url': _edition_path(row)} for row in reversed(editions)]
    (folder / 'index.json').write_text(json.dumps({'first_date': editions[0]['date'], 'latest_date': editions[-1]['date'],
                                                 'snapshots': snapshots}, indent=2) + '\n')
    namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    sitemap = ET.parse(destination / 'sitemap.xml').getroot()
    entries = [(node.findtext(namespace + 'loc'), node.findtext(namespace + 'lastmod')) for node in sitemap]
    entries += [(ORIGIN + '/daily/', editions[-1]['date'])] + [(edition_url(row), row['date']) for row in editions]
    (destination / 'sitemap.xml').write_text(render_sitemap(entries))
