"""Validate daily inputs and archive navigation using isolated temporary editions."""
import copy
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from daily_scan import load_editions, render, write_daily_scan
from static_pages import ORIGIN


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

    def handle_data(self, data):
        if self.current_paragraph is not None:
            self.current_paragraph["text"] += data

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
        html = render(snapshot, [snapshot], ORIGIN + "/daily/", self.root)
        article = html.split(f'<article class="scan-item" id="{item["id"]}"', 1)[1].split("</article>", 1)[0]
        visible, details = article.split("<details>", 1)
        self.assertIn('<p class="scan-explanation">', visible)
        self.assertNotIn(item["focus"], visible)
        for field in ("focus", "finding", "caveat", "date_basis", "read_scope"):
            self.assertIn(item[field], details)
        self.assertIn(f'<a href="{item["sources"][0]["url"]}">Primary paper', details)
        self.assertIn('href="#example-0"', details)

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
            selected = PageElements((folder / "index.html").read_text()).date_options
            self.assertEqual([row["value"] for row in selected if "selected" in row], [snapshot["date"]])
        latest = PageElements((destination / "daily/index.html").read_text())
        self.assertEqual([row["value"] for row in latest.date_options if "selected" in row], ["2026-11-18"])
        archive = json.loads((destination / "daily/index.json").read_text())
        self.assertEqual(archive["first_date"], "2026-11-16")
        self.assertEqual(archive["latest_date"], "2026-11-18")
        self.assertEqual([row["date"] for row in archive["snapshots"]], ["2026-11-18", "2026-11-16"])


if __name__ == "__main__":
    unittest.main()
