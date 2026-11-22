"""Validate daily inputs and archive navigation using isolated temporary editions."""
import copy
import hashlib
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from daily_scan import (load_editions, render, write_daily_scan, load_daily_context,
                        load_wikipedia_context, daily_search_entries, daily_search_scope,
                        daily_feed_records, edition_url, item_url)
from static_pages import ORIGIN, format_date


def edition(day="2026-11-16"):
    return {
        "date": day,
        "items": [
            {
                "id": f"example-{index}",
                "kind": "Paper",
                "topics": ["Data", "Evaluation"],
                "published_on": "2026-11-13",
                "title": f"Example paper {index}",
                "explanation": [
                    "The researchers built a way to test AI systems.",
                    "They report better results, but tested only one setting.",
                ],
                "focus": "Dataset evaluation",
                "finding": "Author-reported benchmark result",
                "caveat": "Single tested setting",
                "publisher": "Example research group",
                "read_scope": "Abstract and methods",
                "date_basis": "Original preprint submission",
                "sources": [{"label": "Primary paper", "url": f"https://example.org/papers/{index}"}],
            }
            for index in range(10)
        ],
    }


class PageElements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.date_options = []
        self.in_date_select = False
        self.details_depth = 0
        self.paragraphs = []
        self.current_paragraph = None
        self.links = []
        self.current_link = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "details":
            self.details_depth += 1
        elif tag == "p":
            self.current_paragraph = {
                "classes": attrs.get("class", "").split(),
                "hidden": "hidden" in attrs,
                "details_depth": self.details_depth,
                "text": "",
            }
            self.paragraphs.append(self.current_paragraph)
        elif tag == "a":
            self.current_link = {"attributes": attrs, "text": ""}
            self.links.append(self.current_link)
        if tag == "select" and attrs.get("id") == "scan-date":
            self.in_date_select = True
        elif tag == "option" and self.in_date_select:
            self.date_options.append(attrs)

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_date_select = False
        elif tag == "details":
            self.details_depth -= 1
        elif tag == "p":
            self.current_paragraph = None
        elif tag == "a":
            self.current_link = None

    def handle_data(self, data):
        if self.current_paragraph is not None:
            self.current_paragraph["text"] += data
        if self.current_link is not None:
            self.current_link["text"] += data

    def date_steps(self):
        return [
            attrs for tag, attrs in self.elements
            if tag == "a" and "scan-day-step" in attrs.get("class", "").split()
        ]


class DailyScanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "data/daily-scan"
        self.source.mkdir(parents=True)
        (self.source / "wikipedia-context.json").write_text(json.dumps({"entries": []}))

    def save(self, snapshot):
        (self.source / f"{snapshot['date']}.json").write_text(json.dumps(snapshot))

    def assert_rejected(self, snapshot):
        self.save(snapshot)
        with self.assertRaises(ValueError):
            load_editions(self.root)

    def test_accepts_source_on_snapshot_day_without_mutating_input(self):
        snapshot = edition()
        snapshot["items"][0]["published_on"] = snapshot["date"]
        before = copy.deepcopy(snapshot)
        self.save(snapshot)
        self.assertEqual(load_editions(self.root), [before])
        self.assertEqual(snapshot, before)

    def test_rejects_invalid_source_dates(self):
        for value in ("", "not-a-date", "2026-02-30", "2026-13-01"):
            with self.subTest(value=value):
                snapshot = edition()
                snapshot["items"][0]["published_on"] = value
                self.assert_rejected(snapshot)

    def test_rejects_source_after_snapshot_even_if_it_is_valid_iso_date(self):
        snapshot = edition()
        snapshot["items"][0]["published_on"] = "2026-11-17"
        self.assert_rejected(snapshot)

    def test_rejects_duplicate_item_ids_with_distinct_sources(self):
        snapshot = edition()
        snapshot["items"][1]["id"] = snapshot["items"][0]["id"]
        self.assert_rejected(snapshot)

    def test_rejects_duplicate_primary_source_with_distinct_item_ids(self):
        snapshot = edition()
        snapshot["items"][1]["sources"][0]["url"] = snapshot["items"][0]["sources"][0]["url"]
        self.assert_rejected(snapshot)

    def test_required_editorial_fields_reject_missing_blank_or_nontext_values(self):
        fields = ("title", "focus", "finding", "caveat", "publisher", "read_scope", "date_basis")
        for field in fields:
            for value in ("missing", "", "  ", None):
                with self.subTest(field=field, value=value):
                    snapshot = edition()
                    if value == "missing":
                        del snapshot["items"][0][field]
                    else:
                        snapshot["items"][0][field] = value
                    self.assert_rejected(snapshot)

    def test_explanations_require_an_array_of_two_to_four_sentences(self):
        snapshot = edition()
        del snapshot["items"][0]["explanation"]
        self.assert_rejected(snapshot)
        for value in (None, "One sentence. Another sentence.", {}, [], ["One sentence."], ["A sentence."] * 5):
            with self.subTest(value=value):
                snapshot = edition()
                snapshot["items"][0]["explanation"] = value
                self.assert_rejected(snapshot)

    def test_explanation_sentences_require_text_and_sentence_endings(self):
        for value in (None, 7, {}, "", "  ", "Dataset evaluation", ".", "...", "A fragment;"):
            with self.subTest(value=value):
                snapshot = edition()
                snapshot["items"][0]["explanation"][1] = value
                self.assert_rejected(snapshot)

    def test_accepts_two_to_four_sentences_and_quoted_sentence_endings(self):
        sentences = [
            "The researchers tested an AI system.",
            'An expert called the result "useful."',
            "Does it work in other settings?",
            "More testing is needed!",
        ]
        for count in (2, 3, 4):
            with self.subTest(count=count):
                snapshot = edition()
                snapshot["items"][0]["explanation"] = sentences[:count]
                self.save(snapshot)
                self.assertEqual(load_editions(self.root), [snapshot])

    def test_all_explanations_render_as_visible_escaped_paragraphs(self):
        snapshot = edition()
        snapshot["items"][0]["explanation"] = [
            'Researchers tested <script>alert("read")</script> on the examples.',
            "They report a gain, but only for this dataset.",
        ]
        html = render(snapshot, [snapshot], ORIGIN + "/daily/", self.root)
        page = PageElements(html)
        paragraphs = [row for row in page.paragraphs if "scan-explanation" in row["classes"]]
        self.assertEqual(len(paragraphs), len(snapshot["items"]))
        self.assertEqual(
            [row["text"] for row in paragraphs],
            [" ".join(item["explanation"]) for item in snapshot["items"]],
        )
        self.assertTrue(all(not row["hidden"] and row["details_depth"] == 0 for row in paragraphs))
        self.assertIn("&lt;script&gt;alert(&quot;read&quot;)&lt;/script&gt;", html)
        self.assertNotIn('<script>alert("read")</script>', html)
        articles = [attrs for tag, attrs in page.elements if tag == "article" and "scan-item" in attrs.get("class", "").split()]
        self.assertTrue(all("hidden" not in attrs for attrs in articles))

    def test_original_technical_notes_and_sources_stay_in_expandable_details(self):
        snapshot = edition()
        item = snapshot["items"][0]
        item["sources"].append({"label": "Methods & data", "url": "https://example.org/methods?a=1&b=2"})
        html = render(snapshot, [snapshot], ORIGIN + "/daily/", self.root)
        article = html.split(f'<article class="scan-item" id="{item["id"]}"', 1)[1].split("</article>", 1)[0]
        visible, details = article.split("<details>", 1)
        self.assertIn('<p class="scan-explanation">', visible)
        self.assertNotIn(item["focus"], visible)
        for field in ("focus", "finding", "caveat", "date_basis", "read_scope"):
            self.assertIn(item[field], details)
        headline, = PageElements(visible).links
        self.assertIn("ext", headline["attributes"].get("class", "").split())
        self.assertEqual(
            (headline["text"], headline["attributes"]["href"]),
            (item["title"], item["sources"][0]["url"]),
        )
        *sources, permalink = PageElements(details).links
        self.assertTrue(all("ext" in link["attributes"].get("class", "").split() for link in sources))
        self.assertEqual(
            [(link["text"], link["attributes"]["href"]) for link in sources],
            [(source["label"], source["url"]) for source in item["sources"]],
        )
        self.assertEqual(permalink["attributes"]["href"], "/daily/2026-11-16/#example-0")

    def test_sources_require_a_nonempty_list(self):
        for value in ("missing", [], None, {}):
            with self.subTest(value=value):
                snapshot = edition()
                if value == "missing":
                    del snapshot["items"][0]["sources"]
                else:
                    snapshot["items"][0]["sources"] = value
                self.assert_rejected(snapshot)

    def test_every_source_requires_a_visible_link_label(self):
        for value in ("missing", "", "  ", None):
            with self.subTest(value=value):
                snapshot = edition()
                source = {"label": value, "url": "https://example.org/supplement"}
                if value == "missing":
                    del source["label"]
                snapshot["items"][0]["sources"].append(source)
                self.assert_rejected(snapshot)

    def test_primary_sources_can_recur_in_distinct_historical_editions(self):
        first, latest = edition(), edition("2026-11-18")
        self.save(latest)
        self.save(first)
        self.assertEqual(load_editions(self.root), [first, latest])

    def test_navigation_uses_available_editions_and_selects_rendered_date(self):
        dates = ["2026-11-16", "2026-11-18", "2026-11-21"]
        for day in reversed(dates):
            self.save(edition(day))
        snapshots = load_editions(self.root)
        for index, snapshot in enumerate(snapshots):
            with self.subTest(day=snapshot["date"]):
                html = render(snapshot, snapshots, ORIGIN + "/daily/" + snapshot["date"] + "/", self.root)
                page = PageElements(html)
                self.assertEqual([row["value"] for row in page.date_options], list(reversed(dates)))
                self.assertEqual([row["value"] for row in page.date_options if "selected" in row], [snapshot["date"]])
                actual_targets = [row["href"] for row in page.date_steps()]
                expected_targets = [
                    f"/daily/{dates[target]}/" for target in (index - 1, index + 1)
                    if 0 <= target < len(dates)
                ]
                self.assertEqual(actual_targets, expected_targets)
                self.assertEqual([step["rel"] for step in page.date_steps()],
                                 [rel for rel, target in (("prev", index - 1), ("next", index + 1)) if 0 <= target < len(dates)])
                navigation = html.split('<nav class="scan-edition-nav"', 1)[1].split('<details class="scan-filter-disclosure"', 1)[0]
                archive = navigation.split('<details class="scan-archive-disclosure" open>', 1)[1].split('</details>', 1)[0]
                self.assertIn('<summary>Snapshot archive and feeds</summary>', archive)
                self.assertIn(f'<a href="/daily/{snapshot["date"]}/" aria-current="date">', navigation)
                self.assertIn('<a href="/daily/feed.xml">RSS</a>', archive)
                self.assertIn('<a href="/daily/feed.json">JSON Feed</a>', archive)
                self.assertIn('<form class="scan-date-form" hidden>', navigation)
                self.assertIn('<button id="scan-date-go" type="submit">Go</button>', navigation)
                self.assertIn('<details class="scan-filter-disclosure" open hidden><summary>Search and filter</summary>', html)
                self.assertLess(html.index(navigation), html.index('<article class="scan-item"'))
                self.assertTrue(any(tag == "div" and attrs.get("data-edition") == snapshot["date"] for tag, attrs in page.elements))

    def test_writer_keeps_dated_snapshots_and_points_latest_to_newest(self):
        snapshots = [edition(), edition("2026-11-18")]
        snapshots[1]["items"][0]["id"] = "newer-example"
        for snapshot in reversed(snapshots):
            self.save(snapshot)
        destination = self.root / "output"
        destination.mkdir()
        (destination / "sitemap.xml").write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<url><loc>{ORIGIN}/</loc><lastmod>2026-11-16</lastmod></url></urlset>'
        )
        write_daily_scan(destination, self.root)
        for snapshot in snapshots:
            folder = destination / "daily" / snapshot["date"]
            self.assertEqual(json.loads((folder / "snapshot.json").read_text()), snapshot)
            self.assertEqual((folder / "snapshot.json").read_bytes(), (self.source / f'{snapshot["date"]}.json').read_bytes())
            selected = PageElements((folder / "index.html").read_text()).date_options
            self.assertEqual([row["value"] for row in selected if "selected" in row], [snapshot["date"]])
        latest = PageElements((destination / "daily/index.html").read_text())
        self.assertEqual([row["value"] for row in latest.date_options if "selected" in row], ["2026-11-18"])
        archive = json.loads((destination / "daily/index.json").read_text())
        self.assertEqual(archive["first_date"], "2026-11-16")
        self.assertEqual(archive["latest_date"], "2026-11-18")
        self.assertEqual([row["date"] for row in archive["snapshots"]], ["2026-11-18", "2026-11-16"])

    def output(self):
        destination = self.root / "output"
        destination.mkdir(exist_ok=True)
        (destination / "sitemap.xml").write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<url><loc>{ORIGIN}/</loc></url></urlset>')
        return destination

    def wiki(self):
        return {"label": "Example", "title": "Example article", "sentence": "The exact quoted sentence stays unchanged.",
                "article_url": "https://en.wikipedia.org/wiki/Example_article", "revision_id": 123,
                "revision_timestamp": "2026-11-15T12:00:00Z",
                "revision_url": "https://en.wikipedia.org/w/index.php?oldid=123",
                "history_url": "https://en.wikipedia.org/w/index.php?title=Example_article&action=history",
                "download_sha256": "a" * 64, "downloaded_at": "2026-11-16T12:00:00+00:00",
                "normalization": "None; exact sentence", "license": "CC BY-SA 4.0"}

    def save_wiki(self, row):
        raw = (json.dumps({"entries": [row]}, ensure_ascii=False, indent=2) + "\n").encode()
        (self.source / "wikipedia-context.json").write_bytes(raw)
        return raw

    def test_rejects_unsafe_or_malformed_public_urls_before_output(self):
        urls = [None, 7, "http://example.org/paper", "javascript:alert(1)", "https:///paper", "https://localhost/a",
                "https://internal.local/a", "https://127.0.0.1/a", "https://127.1/a", "https://0x7f.0.0.1/a",
                "https://[::1]/a", "https://example.org:bad/a", "https://example.org:444/a",
                "https://@example.org/a", "https://user:pass@example.org/a", "https://example.org/has space",
                "https://example.org/a\\b", "https://example.org/%0aheader", "https://example.org/%GG", "https://example.org/\tpath"]
        for url in urls:
            with self.subTest(url=url):
                snapshot = edition()
                snapshot["items"][0]["sources"][0]["url"] = url
                self.assert_rejected(snapshot)

    def test_primary_duplicate_fragments_and_default_port_do_not_evade_validation(self):
        snapshot = edition()
        snapshot["items"][1]["sources"][0]["url"] = "https://EXAMPLE.org:443/papers/0#other-section"
        self.assert_rejected(snapshot)

    def test_wikipedia_contract_fails_closed_without_rewriting_quotes(self):
        valid = self.wiki()
        cases = [("article_url", "https://en.wikipedia.org.evil.example/wiki/Example_article"),
                 ("article_url", "https://en.wikipedia.org/wiki/Other"),
                 ("revision_url", "https://en.wikipedia.org/w/index.php?oldid=124"),
                 ("revision_url", "https://en.wikipedia.org/w/index.php?oldid=123&oldid=124"),
                 ("revision_url", "https://en.wikipedia.org/w/index.php?oldid=123&title=Other"),
                 ("history_url", "https://en.wikipedia.org/w/index.php?title=Other&action=history"),
                 ("history_url", "https://en.wikipedia.org/w/index.php?title=Example_article&action=edit"),
                 ("license", "CC BY 4.0"), ("download_sha256", "a" * 63), ("download_sha256", "A" * 64),
                 ("revision_id", True), ("revision_id", 0), ("revision_timestamp", "2026-11-17T12:00:00Z"),
                 ("revision_timestamp", "2026-02-30T12:00:00Z"), ("downloaded_at", "2026-11-16T12:00:00")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                row = {**valid, field: value}
                self.save_wiki(row)
                with self.assertRaises(ValueError):
                    load_wikipedia_context(self.root)
        missing = dict(valid)
        missing.pop("sentence")
        self.save_wiki(missing)
        with self.assertRaises(ValueError):
            load_wikipedia_context(self.root)
        for revision in [valid["revision_url"], valid["revision_url"] + "&title=Example_article"]:
            raw = self.save_wiki({**valid, "revision_url": revision})
            parsed, retained = load_wikipedia_context(self.root)
            self.assertEqual(retained, raw)
            self.assertEqual(parsed["entries"][0]["sentence"], valid["sentence"])

    def test_validated_context_is_reused_without_reading_sources_again(self):
        snapshot = edition()
        self.save(snapshot)
        raw = self.save_wiki(self.wiki())
        context = load_daily_context(self.root)
        (self.source / "wikipedia-context.json").unlink()
        (self.source / (snapshot["date"] + ".json")).unlink()
        destination = self.output()
        with patch("daily_scan._edition_sources", side_effect=AssertionError("second edition load")), \
                patch("daily_scan.load_wikipedia_context", side_effect=AssertionError("second context load")):
            write_daily_scan(destination, self.root, context=context)
            search = daily_search_entries(context)
        self.assertEqual((destination / "daily/wikipedia-context.json").read_bytes(), raw)
        self.assertEqual(search[0]["url"], "/daily/")
        self.assertEqual(search[1]["url"], item_url(snapshot, snapshot["items"][0]).removeprefix(ORIGIN))
        self.assertIn(self.wiki()["sentence"], (destination / "daily/index.html").read_text())

    def test_feeds_use_dated_identity_escape_content_and_omit_unknown_publication_times(self):
        first, latest = edition(), edition("2026-11-18")
        latest["compiled_at"] = "2026-11-18T08:30:00Z"
        latest["workers"] = {"private_marker": "DO-NOT-PROJECT-WORKER-METADATA"}
        latest["items"][0]["explanation"] = ['A source says <script>alert("x")</script>.', "This remains a reported result."]
        self.save(first)
        self.save(latest)
        context = load_daily_context(self.root)
        before = copy.deepcopy(context.editions)
        destination = self.output()
        write_daily_scan(destination, self.root, context=context)
        rss_bytes, json_bytes = [(destination / ("daily/" + name)).read_bytes() for name in ("feed.xml", "feed.json")]
        rss = ET.fromstring(rss_bytes)
        feed = json.loads(json_bytes)
        records = daily_feed_records(context)
        self.assertEqual(feed["version"], "https://jsonfeed.org/version/1.1")
        self.assertEqual(feed["items"], records)
        self.assertEqual([row["id"] for row in records], [edition_url(latest), edition_url(first)])
        items = rss.findall("./channel/item")
        self.assertEqual([row.findtext("guid") for row in items], [r["id"] for r in records])
        self.assertTrue(all(row.find("guid").get("isPermaLink") == "true" for row in items))
        self.assertIn("&lt;script&gt;", items[0].findtext("description"))
        self.assertNotIn('<script>alert("x")</script>', items[0].findtext("description"))
        self.assertIn(latest["items"][0]["caveat"], records[0]["content_text"])
        self.assertIn(latest["items"][0]["read_scope"], records[0]["content_text"])
        self.assertEqual(rss.findall(".//pubDate"), [])
        self.assertEqual(rss.findall(".//lastBuildDate"), [])
        self.assertTrue(all("date_published" not in row and "date_modified" not in row for row in feed["items"]))
        self.assertNotIn("DO-NOT-PROJECT", json_bytes.decode())
        self.assertNotIn("DO-NOT-PROJECT", json.dumps(daily_search_entries(context)))
        self.assertEqual(context.editions, before)
        write_daily_scan(self.output(), self.root, context=context)
        self.assertEqual((destination / "daily/feed.xml").read_bytes(), rss_bytes)
        self.assertEqual((destination / "daily/feed.json").read_bytes(), json_bytes)

    def test_recent_scope_excludes_old_search_and_feed_entries_but_retains_archive(self):
        for offset in range(32):
            self.save(edition((date(2026, 11, 16) + timedelta(days=offset)).isoformat()))
        context = load_daily_context(self.root)
        rows = daily_search_entries(context)
        self.assertEqual(len(rows), 301)
        self.assertEqual(len({row["url"] for row in rows}), 301)
        self.assertTrue(all(set(row) == {"title", "summary", "url", "kind", "keywords"} for row in rows))
        self.assertTrue(all(len(row["summary"]) < 220 and "No independent replication." in row["summary"] for row in rows))
        self.assertFalse(any("/2026-11-16/" in row["url"] for row in rows))
        self.assertEqual(len(daily_feed_records(context)), 30)
        self.assertEqual(daily_search_scope(context)["firstDate"], "2026-11-18")
        destination = self.output()
        write_daily_scan(destination, self.root, context=context)
        self.assertTrue((destination / "daily/2026-11-16/index.html").is_file())
        self.assertEqual(len(json.loads((destination / "daily/index.json").read_text())["snapshots"]), 32)

    def test_presentation_uses_compact_daily_records_without_serializing_input_receipts(self):
        from presentation import build_presentation
        def read(name):
            return json.loads((ROOT / "data" / name).read_text())
        snapshot = edition()
        snapshot["workers"] = {"receipt": "PRIVATE-DAILY-WORKER-MARKER"}
        self.save(snapshot)
        context = load_daily_context(self.root)
        sidecars = {key: read(name) for key, name in [
            ("EDITORIAL", "editorial.json"), ("PROFILE_CONTENT", "profile-content.json"),
            ("COMPANY_EVENTS", "company-events.json"), ("WORK_ROUTES", "work-routes.json"),
            ("SOURCE_UPDATES", "source-updates.json"), ("BUSINESS_HEALTH", "business-health.json")]}
        destination = self.root / "presentation"
        destination.mkdir()
        summary, _ = build_presentation(read("canonical.json"), destination, ROOT, sidecars,
                                         read("editorial-release.json"), daily_context=context)
        home = json.loads((destination / summary["homeSearch"]["href"].lstrip("/")).read_text())
        full = json.loads((destination / summary["fullSearch"]["href"].lstrip("/")).read_text())
        expected = daily_search_entries(context)
        self.assertEqual([row["href"] for row in home["entries"] if row["group"] == "daily"], [row["url"] for row in expected])
        self.assertEqual(full["researchSearchEntries"], expected)
        self.assertEqual(summary["dailySearchScope"]["editionCount"], 1)
        for path in destination.rglob("*.json"):
            self.assertNotIn("PRIVATE-DAILY-WORKER-MARKER", path.read_text())

    def test_dated_metadata_follow_and_item_targets_survive_newer_editions(self):
        first, latest = edition(), edition("2026-11-18")
        self.save(first)
        self.save(latest)
        context = load_daily_context(self.root)
        titles = []
        for snapshot in context.editions:
            for canonical in [ORIGIN + "/daily/", edition_url(snapshot)]:
                html = render(snapshot, context.editions, canonical, self.root, context)
                titles.append(re.search(r"<title>(.*?)</title>", html)[1])
                page = PageElements(html)
                self.assertIn(format_date(snapshot["date"]), titles[-1])
                self.assertTrue(any(tag == "link" and a.get("rel") == "canonical" and a["href"] == canonical for tag, a in page.elements))
                self.assertTrue(any(tag == "a" and a.get("href") == item_url(snapshot, snapshot["items"][0]).removeprefix(ORIGIN) for tag, a in page.elements))
                self.assertTrue(any(tag == "meta" and a.get("name") == "description" and format_date(snapshot["date"]) in a["content"] for tag, a in page.elements))
                self.assertTrue(any(tag == "link" and a.get("type") == "application/feed+json" for tag, a in page.elements))
                self.assertTrue(any(tag == "nav" and a.get("aria-label") == "Follow Daily scan" for tag, a in page.elements))
        self.assertNotEqual(titles[0], titles[2])

    def test_writer_preserves_existing_research_feeds_and_frozen_files(self):
        self.save(edition())
        destination = self.output()
        names = ["research/feed.xml", "research/atom.xml", "research/corrections/feed.xml", "research/corrections/atom.xml",
                 "publication/report.html", "publication/research-archive.zip"]
        for name in names:
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("frozen sentinel " + name).encode())
        before = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in names}
        write_daily_scan(destination, self.root)
        self.assertEqual(before, {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in names})

    def test_serving_header_rules_are_exact_and_leave_native_research_indexable(self):
        rules, current = {}, None
        for line in (ROOT / "web/_headers").read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line[0].isspace():
                current = line
                rules[current] = {}
            else:
                key, value = line.strip().split(":", 1)
                rules[current][key] = value.strip()
        self.assertEqual(rules["/daily/feed.json"]["Content-Type"], "application/feed+json; charset=utf-8")
        self.assertEqual(rules["/daily/feed.xml"]["Content-Type"], "application/rss+xml; charset=utf-8")
        noindex = {path for path, headers in rules.items() if "noindex" in headers.get("X-Robots-Tag", "")}
        self.assertEqual(noindex, {"/publication/" + name + suffix for name in ("report", "executive-brief", "evidence") for suffix in (".html", "", "/")})


if __name__ == "__main__":
    unittest.main()
