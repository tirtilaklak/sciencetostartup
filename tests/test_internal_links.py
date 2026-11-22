"""Check every document link against the checked-in public artifact."""
from collections import defaultdict
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import unittest
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://sciencetostartup.com"
HOSTS = {"sciencetostartup.com", "www.sciencetostartup.com"}

# The app resolves these route families after loading; browser QA exercises their destinations.
EXPLORE_ROUTES = {
    "about", "business-health", "companies", "company", "compare", "corrections",
    "coverage", "downloads", "labels", "market", "method", "venture", "work",
}
HTML_LINK_FIELDS = {"a": "href", "area": "href", "link": "href", "form": "action"}
XML_LINK_TAGS = {"comments", "enclosure", "link", "loc"}


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.ids = set()
        self.links = set()
        self.feed(body)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.ids.add(attrs["name"])
        href = attrs.get(HTML_LINK_FIELDS.get(tag))
        if href and href.strip():
            self.links.add(href.strip())


def xml_links(body):
    for link in ElementTree.fromstring(body).iter():
        if link.tag.rsplit("}", 1)[-1] in XML_LINK_TAGS:
            href = link.get("href") or link.get("url") or link.text
            if href and href.strip():
                yield href.strip()


def document_path(asset):
    if asset == "index.html" or asset.endswith("/index.html"):
        return "/" + asset.removesuffix("index.html")
    return "/" + asset


def served_asset(path, assets):
    name = unquote(path or "/").lstrip("/")
    directory_index = (name.rstrip("/") + "/" if name else "") + "index.html"
    # Cloudflare's auto-trailing-slash routing also resolves a sibling .html.
    return next((asset for asset in (name, directory_index, name.rstrip("/") + ".html")
                 if asset in assets), None)


def unresolved_links(dist):
    payload = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
    assets = set(payload["sha256"]) | {"manifest.json"}
    documents = {}
    destinations = defaultdict(set)
    for asset in sorted(assets):
        if asset.endswith(".html"):
            page = Document((dist / asset).read_text(encoding="utf-8"))
            documents[asset] = page.ids
            links = page.links
        elif asset.endswith(".xml"):
            links = xml_links((dist / asset).read_bytes())
        else:
            continue
        source = ORIGIN + document_path(asset)
        for href in links:
            target = urlsplit(urljoin(source, href))
            if target.scheme in {"http", "https"} and target.hostname in HOSTS:
                destinations[(target.path, target.fragment)].add(asset)

    for (path, fragment), sources in sorted(destinations.items()):
        name = served_asset(path, assets)
        fragment = unquote(fragment).partition(":~:")[0]
        if name is None:
            reason = "missing document or download"
        elif not fragment or fragment == "top" or name not in documents or fragment in documents[name]:
            continue
        elif name == "explore/index.html" and fragment.partition("?")[0].partition("/")[0] in EXPLORE_ROUTES:
            # This is a recognized client route, not a static HTML ID.
            continue
        else:
            reason = "missing fragment"
        address = path + ("#" + fragment if fragment else "")
        yield f"{reason}: {address} (linked from {', '.join(sorted(sources)[:3])})"


class InternalLinksTests(unittest.TestCase):
    def test_delivered_links_reach_existing_paths_and_static_fragments(self):
        dist = Path(os.environ.get("QA_DIST", ROOT / "dist"))
        errors = list(unresolved_links(dist))
        self.assertFalse(errors, f"{len(errors)} unresolved links:\n" + "\n".join(errors[:30]))


if __name__ == "__main__":
    unittest.main()
