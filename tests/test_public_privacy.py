"""No email address or phone number ships in the public build beyond an explicit allowlist."""
import contextlib
import json
import re
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT = {".html", ".json", ".csv", ".xml", ".txt", ".js"}
# The build moves the app code and the sidecar data out of index.html into content-hashed files in js/.
# They are scanned under a stable name, so the allowlist does not change with every build.
BUNDLE = re.compile(r"^js/([a-z]+)\.[0-9a-f]{12}\.js$")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"""tel:
    | (?<![\w.$£€+-]) (?:\+1[ .-]?)? (?:\(\d{3}\)\ ?|\d{3}[ .-]) \d{3}[ .-]\d{4} (?![\w%-]|\.\d)
    | (?<![\w.]) \+\d{1,3} (?:[ -]\(?\d{1,4}\)?){2,4} (?![\w%]|\.\d)
    | (?<![\w.]) \+\d{10,14} (?![\w.])""", re.I | re.X)
# index.html is scanned as three places: its About panel, its embedded canonical dataset and the rest.
SECTIONS = {"about": re.compile(r'<article\b[^>]*\bid="about"[^>]*>.*?</article>', re.S),
            "research-data": re.compile(r'<script\b[^>]*\bid="research-data"[^>]*>.*?</script>', re.S)}
# Every address that may ship, and the only places it may appear.
ALLOWED = {
    # The publisher's own correction and contact address, shown in the About panel.
    "musaeminozdem@gmail.com": {"index.html#about"},
    # Role address Bespoke Labs publishes for domain experts on https://bespokelabs.ai/contact
    # (checked 2026-10-23); the reviewed Work route cites that page. The app reads the routes from the data bundle.
    "experts@bespokelabs.ai": {"work-routes.json", "js/data.js"},
    # A named person's address quoted in canonical claim benchflow.claim.worker_opportunities-0.
    # Dataset 2.5.0 is pinned, so it stays in canonical-derived files until the pending 2.5.1
    # release removes it. It must never appear in Work routes or a static page.
    "xiangyi@benchflow.ai": {"research.json", "claims.csv", "observatory.sqlite", "index.html#research-data"},
}


def sqlite_text(path):
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for row in con.execute(f'SELECT * FROM "{table}"'):
                yield from (value for value in row if isinstance(value, str))


def places(dist):
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        name = BUNDLE.sub(r"js/\1.js", path.relative_to(dist).as_posix())
        if path.suffix == ".sqlite":
            yield name, "\n".join(sqlite_text(path))
        elif path.suffix in TEXT:
            text = path.read_text()
            if name == "index.html":
                for section, pattern in SECTIONS.items():
                    yield name + "#" + section, "\n".join(pattern.findall(text))
                    text = pattern.sub("", text)
            yield name, text


class PublicPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.places = dict(places(ROOT / "dist"))

    def test_scan_reads_every_public_text(self):
        for place in ("index.html", "index.html#about", "index.html#research-data", "observatory.sqlite", "js/app.js", "js/data.js",
                      "research.json", "claims.csv", "work-routes.json", "sitemap.xml", "companies/index.html",
                      "work/index.html", "method/index.html", "404.html"):
            self.assertTrue(self.places.get(place), place)
        companies = json.loads((ROOT / "data/canonical.json").read_text())["companies"]
        self.assertEqual({p for p in self.places if p.startswith("company/")},
                         {f"company/{c['id']}/index.html" for c in companies})

    def test_only_allowlisted_email_addresses_ship(self):
        found = {(address.lower(), place) for place, text in self.places.items() for address in EMAIL.findall(text)}
        self.assertEqual(sorted(f"{address} in {place}" for address, place in found
                                if place not in ALLOWED.get(address, ())), [])

    def test_no_phone_numbers_ship(self):
        self.assertEqual(sorted(f"{match.group(0)!r} in {place}" for place, text in self.places.items()
                                for match in PHONE.finditer(text)), [])

    def test_patterns_catch_common_formats(self):
        for text in ("Write to jane.doe+ai@example.co.uk today", "JANE@EXAMPLE.COM"):
            self.assertRegex(text, EMAIL)
        for text in ("+1 415-555-0123", "(415) 555-0123", "415.555.0123", "+44 20 7946 0958",
                     "+14155550123", '<a href="tel:4155550123">'):
            self.assertRegex(text, PHONE)
        for text in ("+44.7% reported", "+21.4%", "2026-10-23", "FY2024 2025 2026", "$135,107,000", "v1.300.1234"):
            self.assertNotRegex(text, PHONE)


if __name__ == "__main__":
    unittest.main()
