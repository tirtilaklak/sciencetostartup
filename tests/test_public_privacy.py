"""No email address or phone number ships in the public build beyond an explicit allowlist.
Every file in dist/ is read: text files whole, the SQLite database cell by cell, and images and icons as the
printable text inside them (metadata such as EXIF, XMP or PNG text chunks can carry an address)."""
import contextlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import TextStringObject, IndirectObject


ROOT = Path(__file__).resolve().parents[1]
TEXT = {".html", ".json", ".csv", ".xml", ".txt", ".js", ".svg", ".css", ".md", ".cff", ".bib", ".ris", ".py"}
# Host config files such as _headers and _redirects have no suffix and are text.
BINARY = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif", ".pdf", ".woff", ".woff2"}
PRINTABLE = re.compile(rb"[\x20-\x7e]{6,}")
# The build moves the app code and the sidecar data out of index.html into content-hashed files in js/.
# They are scanned under a stable name, so the allowlist does not change with every build.
BUNDLE = re.compile(r"^js/([a-z]+)\.[0-9a-f]{12}\.js$")
PRESENTATION = re.compile(r"^presentation/(archive|company-benchflow|company-bespoke_labs)\.[0-9a-f]{16}\.json$")


def stable_name(name):
    return PRESENTATION.sub(r"presentation/\1.json", BUNDLE.sub(r"js/\1.js", name))
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
    "musaeminozdem@gmail.com": {"explore/index.html#about"},
    # Role address Bespoke Labs publishes for domain experts on https://bespokelabs.ai/contact
    # (checked 2026-10-23); the reviewed Work route cites that page. The same
    # record's complete research now also loads through its company detail asset.
    "experts@bespokelabs.ai": {"work-routes.json", "js/data.js", "presentation/company-bespoke_labs.json"},
    # A named person's address quoted in canonical claim benchflow.claim.worker_opportunities-0.
    # Dataset 2.5.0 is pinned, so it stays in canonical-derived files until the pending 2.5.1
    # release removes it. It must never appear in Work routes or a static page.
    "xiangyi@benchflow.ai": {"research.json", "claims.csv", "observatory.sqlite", "presentation/archive.json", "presentation/company-benchflow.json"},
}


def sqlite_text(path):
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for row in con.execute(f'SELECT * FROM "{table}"'):
                yield from (value for value in row if isinstance(value, str))


def printable_text(path):
    """The runs of printable ASCII inside a binary file, as the strings tool shows them."""
    return "\n".join(run.decode("ascii") for run in PRINTABLE.findall(path.read_bytes()))


def pdf_text(content):
    """Inspect decoded PDF text and strings, rather than compressed/font bytes.

    Binary font data and drawing coordinates are not personal contact text.
    Text extraction includes compressed page streams; object traversal covers
    metadata, annotations, actions and other PDF strings. Attachments are not
    permitted in this research PDF.
    """
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.attachments:
        raise AssertionError('Public report PDF must not contain attachments')
    strings = [page.extract_text() or '' for page in reader.pages]
    visited = set()
    def walk(value):
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in visited:
                return
            visited.add(key)
            walk(value.get_object())
        elif isinstance(value, TextStringObject):
            strings.append(str(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
    walk(reader.trailer)
    return '\n'.join(strings)


def places(dist):
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        name = stable_name(path.relative_to(dist).as_posix())
        if path.suffix == ".sqlite":
            yield name, "\n".join(sqlite_text(path))
        elif path.suffix == ".zip":
            collected = []
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    content = archive.read(member)
                    suffix = Path(member.filename).suffix.lower()
                    if suffix == ".sqlite":
                        with tempfile.NamedTemporaryFile(suffix=".sqlite") as extracted:
                            extracted.write(content)
                            extracted.flush()
                            collected.extend(sqlite_text(Path(extracted.name)))
                    elif suffix in TEXT or not suffix:
                        collected.append(content.decode("utf-8"))
                    elif suffix == '.pdf':
                        collected.append(pdf_text(content))
                    elif suffix in BINARY:
                        collected.append("\n".join(run.decode("ascii") for run in PRINTABLE.findall(content)))
                    else:
                        raise AssertionError("Unscanned archive member: " + member.filename)
            yield name, "\n".join(collected)
        elif path.suffix == '.pdf':
            yield name, pdf_text(path.read_bytes())
        elif path.suffix in BINARY:
            yield name, printable_text(path)
        elif path.suffix in TEXT or not path.suffix:
            text = path.read_text()
            if name == "explore/index.html":
                for section, pattern in SECTIONS.items():
                    yield name + "#" + section, "\n".join(pattern.findall(text))
                    text = pattern.sub("", text)
            yield name, text


class PublicPrivacyTests(unittest.TestCase):
    def test_pdf_scan_reads_decoded_metadata_and_rejects_attachments(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_metadata({'/Title': 'Private name@example.org +1 415-555-0123'})
        stream = io.BytesIO()
        writer.write(stream)
        text = pdf_text(stream.getvalue())
        self.assertRegex(text, EMAIL)
        self.assertRegex(text, PHONE)
        writer.add_attachment('private.txt', b'name@example.org')
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaisesRegex(AssertionError, 'attachments'):
            pdf_text(stream.getvalue())

    @classmethod
    def setUpClass(cls):
        cls.places = {}
        for place, text in places(ROOT / "dist"):
            cls.places[place] = cls.places.get(place, "") + "\n" + text

    def test_scan_covers_every_dist_file(self):
        """No export escapes the scan: every file in dist/ is text, SQLite or a known binary type (coordinator A4)."""
        dist = ROOT / "dist"
        files = {stable_name(p.relative_to(dist).as_posix()) for p in dist.rglob("*") if p.is_file()}
        self.assertEqual(files, {place.split("#", 1)[0] for place in self.places})
        for place in ("_headers", "_redirects", "assets/favicon.svg", "assets/logos/mercor.svg", "favicon.ico", "assets/share/sciencetostartup-1200x630.png"):
            self.assertIn(place, self.places)

    def test_scan_reads_every_public_text(self):
        for place in ("index.html", "explore/index.html", "explore/index.html#about", "explore/index.html#research-data", "presentation/archive.json", "presentation/company-benchflow.json", "observatory.sqlite", "js/app.js", "js/data.js",
                      "research.json", "claims.csv", "work-routes.json", "sitemap.xml", "companies/index.html",
                      "work/index.html", "method/index.html", "404.html", "business-health.json", "company-events.json",
                      "source-updates.json", "link-health.json", "manifest.json", "robots.txt", "_headers"):
            self.assertTrue(self.places.get(place), place)
        companies = json.loads((ROOT / "data/canonical.json").read_text())["companies"]
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from research_report import build_context
        from research_pages import _new_company, entity_url
        context = build_context(ROOT)
        added = {entity_url(entity, context).strip('/') + '/index.html'
                 for entity in context['graph']['entities'] if _new_company(context, entity)}
        self.assertEqual({p for p in self.places if p.startswith("company/")},
                         {f"company/{c['id']}/index.html" for c in companies} | added)

    def test_only_allowlisted_email_addresses_ship(self):
        found = {(address.lower(), place) for place, text in self.places.items() for address in EMAIL.findall(text)}
        self.assertEqual(sorted(f"{address} in {place}" for address, place in found
                                if place not in ALLOWED.get(address, ())), [])

    def test_benchflow_address_stays_out_of_work_data_and_bundles(self):
        """Main removed this address from Work routes on 23 Oct; only the pinned 2.5.0 dataset files still carry it (coordinator E1)."""
        for place in ("work-routes.json", "js/data.js", "js/app.js"):
            self.assertNotIn("@benchflow.ai", self.places[place], place)

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
