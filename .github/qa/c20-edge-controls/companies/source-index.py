"""Audit native company source links and keyboard navigation against the frozen release."""
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from subprocess import check_output
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import json
import os
import re

from lxml import html

HERE = Path(__file__).resolve().parent
EXPECTED_COMMIT = '04fd82ccf55bac9e1ed33a08564a9f816786d8c7'
EXPECTED_BUILD = 'e4ead044f5b3419c667b'
EXPECTED_MANIFEST = '1fe217bab088009c4fb30ca3b00987bc3291361808823d9c523729fb648015fc'
SOURCE_FILE = 'scripts/static_pages.py'
DOSSIER = re.compile(r'company/([^/]+)/index\.html')
CANONICAL_HOSTS = {'sciencetostartup.com', 'www.sciencetostartup.com'}
INDEX = re.compile(r'company/([^/]+)/work-sources/index\.html')
CF_BEACON = re.compile(
    rb'<script type="module" src="https://static\.cloudflareinsights\.com/beacon\.min\.js/v[0-9a-f]+" '
    rb'integrity="sha512-[A-Za-z0-9+/]{86}==" data-cf-beacon=\'\{"version":"[0-9]+\.[0-9]+\.[0-9]+",'
    rb'"token":"[0-9a-f]{32}","r":1,"spa":2\}\' crossorigin="anonymous"></script>\n(?=</body>\n?</html>\n\Z)'
)
PUBLISHER_LINKS = {
    'turing': {'ids': {'turing.source.t1', 'turing.source.audit-t1'}, 'published_on': '2025-03-06',
               'url': 'https://www.turing.com/press/turing-111-million-series-e'},
    'bespoke_labs': {'ids': {'bespoke_labs.source.audit-bl-pr'}, 'published_on': '2026-07-06',
                     'url': 'https://www.businesswire.com/news/home/20260706827813/en/Bespoke-Labs-Announces-%2440M-to-Build-the-Environments-That-Train-Reliable-Agents'},
}


def digest(body):
    return sha256(body).hexdigest()


def checked(body, expected, path, html_page=False):
    received = digest(body)
    canonical, count = CF_BEACON.subn(b'', body) if html_page else (body, 0)
    assert count <= 1 and digest(canonical) == expected, (path, received, digest(canonical), expected)
    return canonical, {'receivedSha256': received, 'manifestSha256': expected,
                       'cloudflareAnalyticsBytes': len(body) - len(canonical)}


def load_manifest(root, expected):
    data = (root / 'manifest.json').read_bytes()
    assert digest(data) == expected, root
    return data, json.loads(data)


def file_asset(root, manifest, asset):
    data = (root / asset).read_bytes()
    return checked(data, manifest['sha256'][asset], asset)[0]


def http_asset(origin, route, expected, html_page=False):
    url = origin + route
    request = Request(url, headers={'Accept-Encoding': 'identity', 'User-Agent': 'ScienceToStartup-ReleaseVerification/1.0'})
    with urlopen(request, timeout=30) as response:
        assert response.status == 200 and response.geturl() == url, (url, response.status, response.geturl())
        data, binding = checked(response.read(), expected, url, html_page)
        return data, {'url': url, 'status': response.status, **binding}


def catalog(tree, expect_anchors=False, supplemental=None, publisher_links=None):
    items = tree.xpath('//main//ol[@data-native-source-list]/li[@data-native-source]')
    extras = tree.xpath('//main//*[@data-native-source and not(ancestor::ol[@data-native-source-list])]')
    actual_extras = {}
    for item in extras:
        record = item.get('data-native-source')
        destination, = item.xpath('./a/@href')
        assert item.get('id') == record and record not in actual_extras
        assert len(tree.xpath('//*[@id=$id]', id=record)) == 1
        actual_extras[record] = destination
    assert actual_extras == (supplemental or {}), actual_extras
    result = {}
    for item in items:
        sid = item.get('data-native-source')
        urls = item.xpath('./a/@href')
        assert sid and sid not in result and len(urls) == 1 and urls[0].startswith(('https://', 'http://')), (sid, urls)
        if location := (publisher_links or {}).get(sid):
            mirrors = item.xpath('./span[contains(concat(" ", normalize-space(@class), " "), " sub ")]/a[normalize-space()="Recorded mirror"]/@href')
            assert urls == [location['url']] and mirrors == [location['recorded_url']], (sid, urls, mirrors)
        if expect_anchors:
            assert item.get('id') == sid and len(tree.xpath('//*[@id=$sid]', sid=sid)) == 1, sid
        result[sid] = urls[0]
    return result


def catalog_by_company(research):
    companies = {}
    for source in research['sources']:
        if source.get('company_id') and (source.get('url') or '').startswith(('http://', 'https://')):
            company = companies.setdefault(source['company_id'], {})
            assert source['id'] not in company, source['id']
            company[source['id']] = source['url']
    return companies


def browser_checks(origin, assets, cases, repo):
    payload = json.dumps({'origin': origin, 'assets': assets, 'cases': cases, 'repo': str(repo)})
    output = check_output(['node', str(HERE / 'source-index-browser.cjs')], input=payload, text=True, cwd=repo)
    return json.loads(output)


def internal_path(origin, href):
    link = urlsplit(urljoin(origin + '/', href))
    if link.hostname in CANONICAL_HOSTS or link.netloc == urlsplit(origin).netloc:
        return link.path
    return None


def audit(args):
    requested_origin = args.origin.rstrip('/')
    origin = requested_origin
    parsed = urlsplit(origin)
    assert parsed.scheme in ('http', 'https') and parsed.netloc and not (parsed.path or parsed.query or parsed.fragment), origin
    proof = json.loads((HERE / 'baseline-provenance.json').read_bytes())
    pin = {'commit': EXPECTED_COMMIT, 'build_id': EXPECTED_BUILD, 'manifest_sha256': EXPECTED_MANIFEST}
    source = (args.repo / SOURCE_FILE).read_bytes()
    assert digest(source) == proof['frozen_source_sha256'][SOURCE_FILE]
    manifest_hash = EXPECTED_MANIFEST
    manifest_data, manifest = load_manifest(args.dist, manifest_hash)
    assert manifest['build_id'] == EXPECTED_BUILD
    assets = manifest['sha256']
    assert assets['research.json'] == proof['canonical_research_sha256']
    archives = {asset: sha for asset, sha in assets.items() if asset.startswith(('publication/', 'research/editions/'))}
    assert len(archives) == 115 and archives == proof['archive_assets']
    if parsed.hostname == 'www.sciencetostartup.com':
        with urlopen(origin + '/manifest.json', timeout=30) as response:
            redirected = urlsplit(response.geturl())
            assert redirected.hostname in CANONICAL_HOSTS and redirected.path == '/manifest.json'
            origin = f'{redirected.scheme}://{redirected.netloc}'
    served, initial_manifest = http_asset(origin, '/manifest.json', manifest_hash)
    assert served == manifest_data
    research, research_http = http_asset(origin, '/research.json', assets['research.json'])
    research_data = json.loads(research)
    expected = catalog_by_company(research_data)
    source_rows = {source['id']: source for source in research_data['sources']}
    updates_bytes, updates_http = http_asset(origin, '/source-updates.json', assets['source-updates.json'])
    assert updates_bytes == (args.repo / 'data/source-updates.json').read_bytes()
    assert digest(updates_bytes) == proof['source_updates_sha256']
    locations = json.loads(updates_bytes)['source_locations']
    assert len(locations) == len(PUBLISHER_LINKS)
    native_locations = {}
    for location in locations:
        company = location['company_id']
        pinned = PUBLISHER_LINKS[company]
        assert company not in native_locations
        assert set(location['source_ids']) == pinned['ids'] and len(location['source_ids']) == len(pinned['ids'])
        assert all(location[key] == pinned[key] for key in ('url', 'published_on'))
        assert all(expected[company][sid] == location['recorded_url'] and source_rows[sid]['published_on'] == location['published_on']
                   for sid in location['source_ids'])
        native_locations[company] = {sid: location for sid in location['source_ids']}
    summary = json.loads(file_asset(args.dist, manifest, manifest['summary']['href'].lstrip('/')))
    presentation_assets = {'archive': summary['archive'], 'overview': summary['overview'],
                           **{company: summary['companyDetails'][company] for company in native_locations}}
    for name, asset in presentation_assets.items():
        projection = json.loads(file_asset(args.dist, manifest, asset['href'].lstrip('/')))
        assert 'source_locations' not in (projection['sourceUpdates'] or {}), name
    health = json.loads(file_asset(args.dist, manifest, 'business-health.json'))
    health_sources = {row['id']: row['url'] for row in health['sources']}
    supplements = {}
    for row in health['observations']:
        if row.get('historical_source_ids'):
            company = row['company_id']
            prior = expected.get(company, {})
            assert set(row['historical_source_ids']) <= prior.keys()
            supplements.setdefault(company, {}).update(
                {record: health_sources[record] for record in row['source_ids'] if record not in prior})

    directory, directory_http = http_asset(origin, '/companies/', assets['companies/index.html'], True)
    cards = html.fromstring(directory).xpath('//main//*[@data-company]')
    native_ids = {card.get('data-company') for card in cards}
    assert len(cards) == len(native_ids) == 55
    for card in cards:
        link, = card.xpath('.//h3/a/@href')
        assert internal_path(origin, link) == f"/company/{card.get('data-company')}/", link
    dossier_ids = {match[1]: path for path in assets if (match := DOSSIER.fullmatch(path))}
    index_ids = {match[1]: path for path in assets if (match := INDEX.fullmatch(path))}
    assert native_ids <= dossier_ids.keys() and index_ids.keys() <= dossier_ids.keys() and 'afterquery' in index_ids

    def check_profile(item):
        company, profile = item
        dossier_route = '/' + profile.removesuffix('index.html')
        body, profile_http = http_asset(origin, dossier_route, assets[profile], True)
        assert body == file_asset(args.dist, manifest, profile), company
        tree = html.fromstring(body)
        supplemental = supplements.get(company, {})
        publisher_links = native_locations.get(company, {})
        on_dossier = catalog(tree, supplemental=supplemental, publisher_links=publisher_links)
        if publisher_links:
            for url in {location['recorded_url'] for location in publisher_links.values()}:
                remaining = tree.xpath('//main//a[@href=$url]', url=url)
                assert remaining and all(link.text_content().strip() == 'Recorded mirror' for link in remaining), company
        if company == 'turing':
            valuation, = tree.xpath('//*[@data-headline-metric="turing.metric.major-round-valuation-3"]')
            assert valuation.xpath('.//a/@href') == [PUBLISHER_LINKS['turing']['url']]
            assert '$2.2B' in valuation.text_content() and '6 Mar 2025' in valuation.text_content()
        matches = [link for link in tree.xpath('//a[@href]')
                   if INDEX.fullmatch((internal_path(origin, link.get('href')) or '').lstrip('/') + 'index.html')]
        assert not [node for node in tree.xpath('//main//a[contains(@href,"/work-sources/")]') if node not in matches], company
        info = {'company': company, 'dossierRoute': dossier_route, 'profileAsset': profile,
                'profileHttp': profile_http, 'listedInDirectory': company in native_ids,
                'generalSources': on_dossier, 'supplementalSources': supplemental,
                'publisherLocations': publisher_links, 'workSources': {}}
        if company in index_ids:
            asset = index_ids[company]
            route = '/' + asset.removesuffix('index.html')
            assert len(matches) == 1 and matches[0].get('href') == route, (company, [m.get('href') for m in matches])
            html_bytes, index_http = http_asset(origin, route, assets[asset], True)
            assert html_bytes == file_asset(args.dist, manifest, asset), company
            page = html.fromstring(html_bytes)
            assert len(page.xpath('//main/h1')) == 1
            assert [urlsplit(href).path for href in page.xpath('//link[@rel="canonical"]/@href')] == [route]
            index_sources = catalog(page, expect_anchors=True)
            assert index_sources and on_dossier.keys().isdisjoint(index_sources), (company, on_dossier.keys() & index_sources.keys())
            assert ' '.join(matches[0].text_content().split()) == f'{len(index_sources)} paid work sources'
            info.update(indexRoute=route, indexAsset=asset, indexHttp=index_http, workSources=index_sources)
        else:
            assert not matches, (company, [m.get('href') for m in matches])
        union = on_dossier | info['workSources']
        original_union = {sid: publisher_links[sid]['recorded_url'] if sid in publisher_links else href for sid, href in union.items()}
        assert original_union == expected.get(company, {}), (company, sorted(original_union.items() ^ expected.get(company, {}).items()))
        return info

    with ThreadPoolExecutor(max_workers=2) as pool:
        profiles = list(pool.map(check_profile, sorted(dossier_ids.items())))
    linked_indexes = [row for row in profiles if 'indexRoute' in row]
    assert {row['company'] for row in linked_indexes} == index_ids.keys()
    afterquery = next(row for row in linked_indexes if row['company'] == 'afterquery')
    assert len(afterquery['generalSources']) == 45 and len(afterquery['workSources']) == 48
    assert len(afterquery['generalSources'] | afterquery['workSources']) == 93
    clicks = browser_checks(origin, assets, linked_indexes, args.repo)
    assert len(clicks) == len(linked_indexes)
    final, final_manifest = http_asset(origin, '/manifest.json', manifest_hash)
    assert final == served
    receipt = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'base': origin, 'requestedBase': requested_origin, 'freeze': pin,
               'frozenSourceSha256': {SOURCE_FILE: digest(source)},
               'beforeAndAfterManifest': [initial_manifest, final_manifest],
               'referenceManifestPins': proof['historical_catalog_receipt']['referenceManifestPins'],
               'historicalCatalogReceipt': proof['historical_catalog_receipt'], 'archiveAssetsUnchanged': len(archives),
               'publicResearch': research_http, 'sourceUpdates': updates_http, 'directory': directory_http, 'dossierCount': len(native_ids),
               'additionalResearchCompanyPages': len(profiles) - len(native_ids), 'sourceIndexCount': len(linked_indexes),
               'dossiers': profiles, 'sourceIndexClicks': clicks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'base': origin, 'build': pin['build_id'], 'manifest': manifest_hash,
                      'dossiers': len(native_ids), 'additionalResearchCompanyPages': len(profiles) - len(native_ids),
                      'linkedIndexes': len(linked_indexes),
                      'afterQueryGeneral': 45, 'afterQueryWork': 48, 'afterQueryTotal': 93, 'keyboard': clicks}, indent=2))


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default=os.environ.get('QA_BASE_URL'))
    parser.add_argument('--repo', type=Path, default=Path(os.environ.get('GITHUB_WORKSPACE', '.')))
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--output', type=Path, default=Path('output/c20-controls/company-source-index.json'))
    arguments = parser.parse_args()
    if not arguments.origin:
        parser.error('Provide QA_BASE_URL or --origin')
    arguments.repo = arguments.repo.resolve()
    arguments.dist = arguments.dist.resolve()
    audit(arguments)
