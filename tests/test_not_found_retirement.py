"""Helpful native 404 content without redirects or revived legacy capabilities."""
import json
from html.parser import HTMLParser
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import static_pages as sp


class NotFoundFacts(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}; self.links = []; self.canonicals = []; self.scripts = []
        self.details = []; self.inside_retirement = False; self.retirement_text = []; self.outside_text = []
        self.feed(html)

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == 'meta': self.meta[attrs.get('name', attrs.get('http-equiv', ''))] = attrs.get('content')
        if tag == 'a': self.links.append(attrs.get('href'))
        if tag == 'link' and attrs.get('rel') == 'canonical': self.canonicals.append(attrs.get('href'))
        if tag == 'script': self.scripts.append(attrs)
        if tag == 'details' and attrs.get('class') == 'not-found-retirement':
            self.details.append(attrs); self.inside_retirement = True

    def handle_endtag(self, tag):
        if tag == 'details': self.inside_retirement = False

    def handle_data(self, data):
        (self.retirement_text if self.inside_retirement else self.outside_text).append(data)


class NotFoundRetirementTests(unittest.TestCase):
    def setUp(self):
        self.research = SimpleNamespace(companies={'original': {}}, as_of='', data={'dataset_version': '2.5.0'})
        self.html = sp.render_not_found(self.research, directory_count=53)
        self.facts = NotFoundFacts(self.html)

    def test_generic_error_keeps_native_research_search_and_existing_destinations(self):
        self.assertIn('<h1>We could not find that page.</h1>', self.html)
        links = {urljoin(sp.ORIGIN, href) for href in self.facts.links}
        for path in ('/research/', '/research/papers/', '/?search=#browse-guide', '/', '/companies/', '/work/', '/method/', '/method/#about'):
            self.assertIn(sp.ORIGIN + path, links)
        self.assertIn('53 companies', self.html)
        self.assertEqual(self.facts.meta.get('robots'), 'noindex')
        self.assertEqual(self.facts.canonicals, [])
        self.assertNotIn('refresh', self.facts.meta)
        self.assertEqual(self.facts.scripts, [])

    def test_retirement_is_a_closed_native_disclosure_without_replacement_claims(self):
        self.assertEqual(len(self.facts.details), 1)
        self.assertNotIn('open', self.facts.details[0])
        retirement = ' '.join(self.facts.retirement_text)
        self.assertIn('Looking for the former platform?', retirement)
        self.assertIn('API and MCP endpoint are unavailable', retirement)
        self.assertIn('do not restore the former platform’s scores or reports', retirement)
        self.assertNotIn('API', ' '.join(self.facts.outside_text))
        self.assertFalse(any('/api/' in href or '/paper/' in href or '/terminal' in href for href in self.facts.links))

    def test_asset_configuration_preserves_missing_route_404_handling(self):
        config = json.loads((ROOT / 'deployment.json').read_text())
        self.assertEqual(config['assets']['not_found_handling'], '404-page')
        self.assertIs(config['assets']['run_worker_first'], False)
        self.assertFalse((ROOT / 'web/404.html').exists())

    def test_asset_configuration_keeps_archive_html_at_sibling_paths(self):
        config = json.loads((ROOT / 'deployment.json').read_text())
        self.assertEqual(config['assets']['html_handling'], 'auto-trailing-slash')
