#!/usr/bin/env python3
"""Check the editorial acceptance criteria in served, script-free HTML."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


LIVE = 'https://sciencetostartup.com'
ROUTES = {
    'mercor': '/company/mercor/', 'datacurve': '/company/datacurve/',
    'datasets': '/research/datasets/', 'papers': '/research/papers/',
    'review': '/review/', 'corrections': '/research/corrections/',
}
VOID_TAGS = set('area base br col embed hr img input link meta param source track wbr'.split())


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)

    def elements(self, tag=None, visible=False):
        for child in self.parts:
            if isinstance(child, Element):
                if visible and ('hidden' in child.attrs or child.tag in {'script', 'style', 'template'}):
                    continue
                if visible and self.tag == 'details' and 'open' not in self.attrs and child.tag != 'summary':
                    continue
                if tag is None or child.tag == tag:
                    yield child
                yield from child.elements(tag, visible)

    def text(self, visible=False):
        if self.tag in {'script', 'style', 'template'} or (visible and 'hidden' in self.attrs):
            return ''
        if visible and self.tag == 'details' and 'open' not in self.attrs:
            parts = [child for child in self.parts if isinstance(child, Element) and child.tag == 'summary']
        else:
            parts = self.parts
        return ' '.join(' '.join(part.text(visible) if isinstance(part, Element) else part
                                for part in parts).split())

    def links(self, visible=False):
        if visible and ('hidden' in self.attrs or (self.tag == 'details' and 'open' not in self.attrs)):
            return
        if self.tag == 'a' and self.attrs.get('href'):
            yield self.attrs['href']
        for child in self.parts:
            if isinstance(child, Element):
                yield from child.links(visible)


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element('document')
        self.stack = [self.root]
        self.feed(html)
        self.close()
        self.main = next(self.root.elements('main'), self.root)

    def handle_starttag(self, tag, attrs):
        child = Element(tag, dict(attrs))
        self.stack[-1].parts.append(child)
        if tag not in VOID_TAGS:
            self.stack.append(child)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].parts.append(data)


def has(text, pattern):
    return bool(re.search(pattern, text, re.I))


MERCOR_D = r'^https://(?:www\.)?mercor\.com/blog/series-d/?(?:[#?].*)?$'
MERCOR_C = r'^https://(?:www\.)?mercor\.com/blog/series-c/?(?:[#?].*)?$'
DATACURVE_SOURCE = (r'^https://(?:www\.)?(?:chemistry\.vc/post/staying-ahead-of-the-curve|'
                    r'wsgr\.com/[^?#]*advises-datacurve-on-dollar15-million-series-a\.html|'
                    r'linkedin\.com/posts/datacurveai_)[^#]*')
NOV_10 = r'10\s+nov(?:ember)?\.?\s*,?\s+2026|nov(?:ember)?\.?\s+10,?\s+2026|2026-11-10'
OCT_9 = r'0?9\s+oct(?:ober)?\.?\s*,?\s+2025|oct(?:ober)?\.?\s+0?9,?\s+2025|2025-10-09'
OCT_27 = r'27\s+oct(?:ober)?\.?\s*,?\s+2025|oct(?:ober)?\.?\s+27,?\s+2025|2025-10-27'


def money(text, number, unit, full):
    return re.search(rf'(?:US\s*\$|\$|USD\s*)\s*(?:{number}\s*(?:{unit[0]}|{unit})\b|{full}(?![\d,]))',
                     text, re.I)


def leads_amount(first, previous):
    return bool(first and (not previous or first.start() < previous.start()))


def lead(main):
    """Support the current report cards and newer headline containers."""
    candidates = [node for node in main.elements(visible=True) if node.tag == 'header'
                  or has(node.attrs.get('class', ''), r'\bcompany-(?:key-facts|headline|at-a-glance)\b')
                  or 'data-headline-metric' in node.attrs]
    return ' '.join(node.text(visible=True) for node in candidates), [
        href for node in candidates for href in node.links(visible=True)]


def company_checks(name, page):
    headline, links = lead(page)
    records = [node for node in page.elements() if node.tag in {'tr', 'p', 'details', 'aside', 'li', 'dl', 'div'}]
    if name == 'mercor':
        valuation = leads_amount(money(headline, '20', 'billion', '20,000,000,000'),
                                 money(headline, '10', 'billion', '10,000,000,000'))
        company = has(headline, r'company[- ](?:reported|announced)|(?:reported|announced) by mercor|mercor (?:said|reported|announced)')
        yield 'Mercor leads with the sourced November Series D valuation', (
            valuation and has(headline, 'valuat') and company and has(headline, NOV_10)
            and has(headline, r'\bseries\s+d\b') and any(has(link, MERCOR_D) for link in links))
        yield 'Mercor preserves the dated Series C figure as history', any(
            money(node.text(), '10', 'billion', '10,000,000,000') and has(node.text(), OCT_27)
            and any(has(link, MERCOR_C) for link in node.links()) for node in records)
        yield 'Mercor keeps the employee tender qualification with the round', any(
            money(node.text(), '750', 'million', '750,000,000')
            and has(node.text(), r'\b(?:employee|secondary)\s+tender\b') for node in records)
    if name == 'datacurve':
        round_amount = leads_amount(money(headline, '15', 'million', '15,000,000'),
                                    money(headline, '150', 'million', '150,000,000'))
        yield 'Datacurve leads with the dated, attributed Series A amount', (
            round_amount and has(headline, r'\bseries\s+a\b') and has(headline, OCT_9)
            and any(has(link, DATACURVE_SOURCE) for link in links))
        yield 'Datacurve labels cumulative funding separately', any(
            money(node.text(), r'17\.7', 'million', '17,700,000')
            and has(node.text(), r'(?:total|aggregate|cumulative|lifetime).{0,24}(?:funding|financing|raised)')
            for node in records)


def count_unit(text, count, unit):
    return has(text, rf'(?<![\d,]){count}\s+(?:[a-z-]+\s+){{0,6}}(?:{unit})\b')


def index_checks(name, page):
    header = next(page.elements('header'), page).text(visible=True)
    rows = {node.attrs['data-record-id']: node for node in page.elements('tr')
            if 'data-record-id' in node.attrs}
    approved = {key: node for key, node in rows.items()
                if 'approved' in json.loads(node.attrs.get('data-filters', '{}')).get('status', [])}
    if name == 'datasets':
        families = sum('"dataset_release"' not in node.attrs.get('data-filters', '') for node in approved.values())
        releases = len(approved) - families
        zero_evidence = r'\b(?:0|no)\s+(?:approved\s+)?(?:assertions|findings|claims|evidence)\b'
        with_evidence = sum(not has(node.text(), zero_evidence) for node in approved.values())
        item_units = count_unit(header, len(rows), 'records') or (
            count_unit(header, families, r'(?:dataset\s+)?families')
            and count_unit(header, releases, r'(?:dataset\s+)?releases'))
        yield 'Datasets distinguish total records from records with approved evidence', (
            bool(approved) and item_units
            and count_unit(header, with_evidence, r'approved\s+(?:assertions|findings|claims|evidence)'))
        row = rows.get('dataset.fineweb-edu', Element('tr'))
        yield 'FineWeb-Edu is labeled as approved metadata without attached assertions', (
            bool(row.parts) and has(row.text(), r'\bmetadata\b|catalog(?:ue)?\s+entry')
            and has(row.text(), zero_evidence) and not has(row.text(), r'approved evidence\s+full source'))
    if name == 'papers':
        versions = sum('"paper_version"' in node.attrs.get('data-filters', '') for node in approved.values())
        works = len(approved) - versions
        yield 'Papers distinguish approved works from approved source versions', (
            works > 0 and versions > 0 and count_unit(header, works, r'(?:paper\s+)?works')
            and count_unit(header, versions, r'(?:source\s+)?versions'))
        source_review = r'\b(?:source[- ]review|reviews?|reviewed|coverage)\b'
        yield 'Papers explain the narrower report source-review count', any(
            has(part, r'\b225\b') and has(part, source_review) for part in re.split(r'[.;·]', header))


def correction_checks(review, log):
    yield 'Correction requests and the public log have distinct destinations', (
        any(has(link, r'/issues/new(?:\?|/|$)|^mailto:') for link in review.links(visible=True))
        and any(urlsplit(link).path.rstrip('/') == '/research/corrections' for link in review.links(visible=True)))
    intro = ' '.join(node.text(visible=True) for node in log.elements() if node.tag in {'header', 'h2', 'h3', 'summary'})
    yield 'Correction log identifies prepublication review and published errata separately', (
        has(intro, r'\bpre[- ]?publication\b|\bbefore publication\b|\bpre[- ]?launch\b')
        and has(intro, r'\b(?:published(?:[- ]edition)?|post[- ]?publication)\s+(?:corrections|errata)\b|'
                r'\b(?:corrections|errata)\s+(?:to|for)\s+published\b'))


def load(base, path):
    request = Request(base.rstrip('/') + path, headers={'User-Agent': 'ScienceToStartup editorial acceptance probe/1.0'})
    with urlopen(request, timeout=20) as response:
        return Document(response.read().decode('utf-8')).main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=LIVE, help='Published site or candidate preview URL')
    args = parser.parse_args()
    if urlsplit(args.base_url).scheme not in {'http', 'https'} or not urlsplit(args.base_url).hostname:
        parser.error('--base-url must be an http(s) URL')

    checks, pages = [], {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {key: pool.submit(load, args.base_url, route) for key, route in ROUTES.items()}
        for key, future in pending.items():
            try:
                pages[key] = future.result()
            except (OSError, ValueError) as error:
                checks.append((f'Load {ROUTES[key]} ({error})', False))
    for name in ('mercor', 'datacurve', 'datasets', 'papers'):
        if name in pages:
            checks.extend((company_checks if name in ('mercor', 'datacurve') else index_checks)(name, pages[name]))
    if 'review' in pages and 'corrections' in pages:
        checks.extend(correction_checks(pages['review'], pages['corrections']))
    for label, passed in checks:
        print(f'{"PASS" if passed else "FAIL"}  {label}')
    passed = sum(bool(result) for _, result in checks)
    print(f'{passed}/{len(checks)} checks passed on {args.base_url}')
    return int(passed != len(checks))


if __name__ == '__main__':
    raise SystemExit(main())
