"""Supplemental facts stay sourced, escaped and separate from company prose."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import static_pages


def facts_fixture():
    return {
        "reviewed_on": "2026-11-16",
        "sources": [
            {"url": "https://example.org/filing?a=1&b=2", "title": "Quarterly filing", "published_on": "2026-10-29", "observed_on": "2026-11-15", "response_sha256": "a" * 64, "locator": "Acquisition note"},
            {"url": "https://example.org/announcement", "title": "Completion announcement", "published_on": "2026-08-03", "observed_on": "2026-11-16", "response_sha256": "b" * 64, "locator": "Opening paragraph"},
        ],
        "rows": [
            {"label": "Acquisition closed", "value": "31 Jul 2026", "source_indexes": [0]},
            {"label": "Completion announced", "value": "3 Aug 2026", "source_indexes": [1]},
        ],
    }


class Fragment(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.links = []
        self.details = []
        self.summary = ""
        self.text = ""
        self.in_summary = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if tag == "a": self.links.append(attrs)
        if tag == "details": self.details.append(attrs)
        if tag == "summary": self.in_summary = True

    def handle_endtag(self, tag):
        if tag == "summary": self.in_summary = False

    def handle_data(self, value):
        self.text += value
        if self.in_summary: self.summary += value


NODE_RENDER = r"""
const fs = require('fs'), vm = require('vm');
const root = process.argv[1], input = JSON.parse(fs.readFileSync(0, 'utf8'));
const app = fs.readFileSync(root + '/web/app.js', 'utf8');
const editorial = fs.readFileSync(root + '/web/editorial.js', 'utf8');
function definition(source, prefix) {
  const line = source.split('\n').find(line => line.startsWith(prefix));
  if (!line) throw new Error('Missing application helper: ' + prefix);
  return line;
}
const context = vm.createContext({
  window: {PROFILE_CONTENT: {entries: input.entries}},
  document: {addEventListener() {}},
  publicText: value => String(value ?? ''), iconHTML: () => '',
  dateText: value => value, comparisonRows: () => [], route() {},
  Intl, Date, JSON, Set, Map,
});
vm.runInContext([
  definition(app, 'const esc='),
  definition(editorial, 'const attr='),
  definition(app, 'const external='),
  fs.readFileSync(root + '/web/profiles-v2.js', 'utf8'),
].join('\n'), context);
context.ids = input.ids;
process.stdout.write(vm.runInContext('JSON.stringify(ids.map(id => profileCurrentFacts(id)))', context));
"""


def render_javascript(entries, ids):
    result = subprocess.run(
        ["node", "-e", NODE_RENDER, str(ROOT)],
        input=json.dumps({"entries": entries, "ids": ids}),
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


class CurrentFactsDisplayTests(unittest.TestCase):
    def test_absent_and_empty_facts_produce_no_static_placeholder(self):
        for profile in (None, {}, {"summary": "A related parent article."}, {"current_facts": None}, {"current_facts": {"rows": []}}):
            with self.subTest(profile=profile):
                self.assertEqual(static_pages.current_facts_html(profile), "")

    def test_absent_and_empty_facts_produce_no_javascript_placeholder(self):
        entries = [
            {"company_id": "no-facts", "summary": "A related parent article."},
            {"company_id": "null-facts", "current_facts": None},
            {"company_id": "empty-facts", "current_facts": {"rows": []}},
        ]
        self.assertEqual(render_javascript(entries, ["unknown", "no-facts", "null-facts", "empty-facts"]), ["", "", "", ""])

    def test_static_dates_and_sources_keep_review_distinct_from_event_dates(self):
        facts = facts_fixture()
        page = Fragment(static_pages.current_facts_html({"current_facts": facts}))
        self.assertEqual(page.summary, "Updates checked 16 Nov 2026")
        self.assertIn("Acquisition closed31 Jul 2026", page.text)
        self.assertIn("Completion announced3 Aug 2026", page.text)
        self.assertEqual([link["href"] for link in page.links], [source["url"] for source in facts["sources"]])
        self.assertEqual([link["aria-label"] for link in page.links], [source["title"] for source in facts["sources"]])
        self.assertEqual(len(page.details), 1)
        self.assertNotIn("open", page.details[0])
        self.assertNotIn("29 Oct", page.summary)
        self.assertNotIn("3 Aug", page.summary)

    def test_javascript_dates_and_accessible_sources_match_static_meaning(self):
        facts = facts_fixture()
        page = Fragment(render_javascript([{"company_id": "fixture", "current_facts": facts}], ["fixture"])[0])
        self.assertEqual(page.summary, "Updates checked 16 Nov 2026")
        self.assertIn("Acquisition closed31 Jul 2026", page.text)
        self.assertIn("Completion announced3 Aug 2026", page.text)
        self.assertEqual([link["href"] for link in page.links], [source["url"] for source in facts["sources"]])
        for link, source in zip(page.links, facts["sources"]):
            self.assertIn(source["title"], link["aria-label"])
            self.assertIn("opens in a new tab", link["aria-label"])
            self.assertEqual(link["target"], "_blank")
            self.assertEqual(set(link["rel"].split()), {"noopener", "noreferrer"})
        self.assertNotIn("open", page.details[0])

    def test_both_renderers_escape_values_labels_and_source_attributes(self):
        facts = facts_fixture()
        facts["rows"] = [{"label": '<img src=x onerror="label()">', "value": '<script>value()</script> & "quoted"', "source_indexes": [0]}]
        facts["sources"][0].update(url='https://example.org/?q=" onmouseover="source()', title='Filing "quoted" <unsafe> & source')
        original = copy.deepcopy(facts)
        outputs = [
            static_pages.current_facts_html({"current_facts": facts}),
            render_javascript([{"company_id": "fixture", "current_facts": facts}], ["fixture"])[0],
        ]
        for markup in outputs:
            with self.subTest(markup=markup):
                page = Fragment(markup)
                self.assertNotIn("script", page.tags)
                self.assertNotIn("img", page.tags)
                self.assertIn(facts["rows"][0]["label"], page.text)
                self.assertIn(facts["rows"][0]["value"], page.text)
                self.assertEqual(page.links[0]["href"], facts["sources"][0]["url"])
                self.assertNotIn("onmouseover", page.links[0])
                self.assertIn(facts["sources"][0]["title"], page.links[0]["aria-label"])
        self.assertEqual(facts, original)

    def test_source_indexes_select_the_cited_document_in_both_renderers(self):
        facts = facts_fixture()
        facts["rows"] = [{"label": "Transaction dates", "value": "Closing and announcement are distinct", "source_indexes": [1, 0]}]
        outputs = [static_pages.current_facts_html({"current_facts": facts}), render_javascript([{"company_id": "fixture", "current_facts": facts}], ["fixture"])[0]]
        for markup in outputs:
            page = Fragment(markup)
            self.assertEqual([link["href"] for link in page.links], [facts["sources"][1]["url"], facts["sources"][0]["url"]])
            self.assertIn("[2]", page.text)
            self.assertIn("[1]", page.text)

    def test_current_fact_fragments_do_not_substitute_profile_or_parent_prose(self):
        profile = {"company_id": "fixture", "summary": "PARENT ARTICLE PROSE MUST NOT BECOME A COMPANY DESCRIPTION", "wikipedia": {"extract": "UNSELECTED WIKIPEDIA WORDING"}, "current_facts": facts_fixture()}
        for markup in (static_pages.current_facts_html(profile), render_javascript([profile], ["fixture"])[0]):
            self.assertNotIn(profile["summary"], markup)
            self.assertNotIn(profile["wikipedia"]["extract"], markup)

    def test_directory_keeps_existing_summary_and_does_not_leak_parent_prose(self):
        companies = [{"id": "fixture", "name": "Fixture Company", "description": "CANONICAL SNAPSHOT DESCRIPTION"}]
        editorial = {"fixture": {"summary": "EXISTING EDITORIAL SUMMARY", "primary_offering": "Other"}}
        profile = {"fixture": {"summary": "UNSELECTED PARENT ARTICLE PROSE", "current_facts": facts_fixture()}}
        with mock.patch.object(static_pages, "document", side_effect=lambda research, title, description, canonical, body, *args, **kwargs: body):
            markup = static_pages.render_index(SimpleNamespace(as_of="2026-10-15"), companies, editorial, {}, 0, "2026-11-16", profile_by_id=profile)
        self.assertIn("<p>EXISTING EDITORIAL SUMMARY</p>", markup)
        self.assertNotIn("UNSELECTED PARENT ARTICLE PROSE", markup)
        self.assertNotIn("CANONICAL SNAPSHOT DESCRIPTION", markup)
        self.assertIn("Updates checked 16 Nov 2026", markup)

    def test_reviewed_transaction_rows_keep_closing_and_announcement_distinct(self):
        profiles = json.loads((ROOT / "data/profile-content.json").read_text())["entries"]
        by_id = {entry["company_id"]: entry for entry in profiles}
        expected = {
            "imerit": {"Legal closing": "31 Jul 2026", "Completion announced": "3 Aug 2026", "Acquirer": "EXL / Clairvoyant AI, Inc."},
            "prime_intellect": {"Acquired business": "Moondream", "Acquisition announced": "13 Oct 2026", "Continuing brand": "Moondream"},
        }
        javascript = dict(zip(expected, render_javascript(profiles, list(expected))))
        for cid, rows in expected.items():
            profile = by_id[cid]
            self.assertEqual({row["label"]: row["value"] for row in profile["current_facts"]["rows"]}, rows)
            for markup in (static_pages.current_facts_html(profile), javascript[cid]):
                page = Fragment(markup)
                self.assertEqual(page.summary, "Updates checked 16 Nov 2026")
                for label, value in rows.items():
                    self.assertIn(label + value, page.text)
                self.assertTrue(page.links)
                self.assertTrue(all("wikipedia.org" not in link["href"] for link in page.links))
                self.assertNotIn("EXL completed its acquisition of iMerit on August 3, 2026.", page.text)


if __name__ == "__main__":
    unittest.main()
