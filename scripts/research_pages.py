#!/usr/bin/env python3
"""Crawlable research pages with explicit evidence and publication states.

The renderer performs no network calls. Candidate wording never becomes a fact
merely because a source was captured; only approved assertions are synthesized.
Historical descriptions keep their original assertion and source dates. The
coordinator calls these two public functions from the ordinary static build.
"""
from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
import hashlib
from itertools import groupby
import json
import re
from types import SimpleNamespace
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import static_pages as sp
from research_citations import citation_formats, publication_metadata
from research_corrections import correction_records as _correction_records
from research_findings import executive_findings, finding_anchor, field_text, JUDGMENT_FIELDS, WITHHELD, paragraph_supported, WITHHELD_PARAGRAPH
from research_operating_status import with_operating_status, operating_status_notice

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = "/research/state-of-ai-data-labs/"
CORRECTIONS_PATH = "/research/corrections/"
LEDGER_BUCKETS = "0123456789abcdef"
SOURCE_ANCHORS = "data/research-source-anchors.json"
SOURCE_RECHECKS = "data/research-source-rechecks.json"
COMPANY_WEBSITES = "data/research-company-websites.json"
# Earlier public fragment IDs preserved by the current website wrapper.
RETIRED_ASSERTION_IDS = (
    'candidate.cohort3.dataset.magpie.06',
    'candidate.cohort6.speechocean.current-data-offer',
    'next.claim.oasst1.guidelines',
)
BUYER_OPENING = re.compile(r'^Buyer use case (\d+) — (.+?): requirement and comparison\.')
BUYER_RECORDS = {
    'Common pilot record': 'buyer-common-pilot-record',
    'Proposed commercial acceptance record': 'buyer-commercial-acceptance-record',
}
OVERSIGHT_TITLE = 'Measuring Progress on Scalable Oversight for Large Language Models'
PASSAGE_SHORTCUTS = {
    'technical-landscape': (
        ('scalable-oversight-result', OVERSIGHT_TITLE, f'Study result — {OVERSIGHT_TITLE}.',
         'mandatory1.claim.arxiv.2211.03540.result'),
    ),
    'buyer-decision-guides': (
        ('buyer-statistical-acceptance-rule', 'Proposed statistical acceptance rule',
         'A proposed statistical acceptance rule should make its assumptions explicit.', ''),
    ),
    'commercial-evidence': (
        ('commercial-buyer-calculation', 'Reproducible buyer calculation', 'Reproducible buyer calculation:', ''),
        ('commercial-review-calculation', 'Reproducible review calculation', 'Reproducible review calculation:', ''),
    ),
}
EARLY_READER_SHORTCUTS = {'technical-landscape', 'datasets-and-benchmarks', 'methods-and-appendices',
                          'commercial-evidence'}
PROVIDER_BRANDS = {'Nexdata': 'org.nexdata', 'Clickworker': 'org.clickworker'}
PROVIDER_ADJACENT = {
    'Translated': 'narrow artifact contribution',
    'BenchFlow': 'reviewed adjacent software, commercial qualification pending',
}
EDITION_CITATIONS = {
    'citation.bib': 'Download BibTeX citation',
    'citation.ris': 'Download RIS citation',
    'citation.csl.json': 'Download CSL JSON citation',
    'CITATION.cff': 'Download CITATION.cff',
}
DATA_JSON_DOWNLOADS = ('/publication/clean-dataset.json', '/research/exports/research-graph.json')
# The 12 November archive, PDF and manifest were verified byte-for-byte at this commit.
EDITION_MIRROR_ARCHIVE_SHA256 = 'fdd231690c9bf9ed57339502a9e52b96eb59461afb6771191eb1337b69a85917'
EDITION_MIRROR = ('https://raw.githubusercontent.com/tirtilaklak/sciencetostartup/'
                  'aac87fd94dc86dee4976176fddb0764215898107/data/research/releases/research-2026-11-12.1/publication/')
CATEGORIES = (
    ("papers", "Papers", {"paper", "paper_work", "paper_version"},
     "Papers, source versions and the findings they support."),
    ("datasets", "Datasets", {"dataset", "dataset_family", "dataset_release"},
     "Dataset families, provenance, access and limits."),
    ("benchmarks", "Benchmarks", {"benchmark", "benchmark_family", "benchmark_version"},
     "Benchmark tasks, versions and test conditions."),
    ("workflows", "Workflows", {"workflow"},
     "Recruitment, labeling, review and evaluation."),
)
PROGRESS = (
    ("legacy_inclusion_audits", "Legacy inclusion audits", 39),
    ("qualifying_suppliers", "Qualifying suppliers", 60),
    ("reviewed_papers", "Distinct reviewed papers", 150),
    ("dataset_families", "Dataset families", 60),
    ("benchmark_families", "Benchmark families", 20),
    ("core_disposition_rate", "Frozen core disposition", .9),
)
KIND_LABELS = {"method": "Method", "analysis": "Analysis", "research_gap": "Research gap",
               "sourced_fact": "Source-backed finding"}
STATUS_LABELS = {"approved": "Approved evidence", "candidate": "Candidate · review pending",
                 "historical": "Historical record", "excluded": "Excluded from scope"}
INDEX_FACETS = ("domain", "modality", "workflow", "expertise", "origin", "labels", "oversight",
                "delivery_model", "data_purpose")


def _token(value):
    """A stable ID as one URL path segment; never reinterpret slashes as paths."""
    return quote(str(value), safe="._-")


def _path_token(value):
    """Filesystem-safe stable slugs also work after a web server URL-decodes paths."""
    value = str(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        return value
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")[:80] or "record"
    return readable + "-" + hashlib.sha256(value.encode()).hexdigest()[:12]


def _anchor(kind, stable_id):
    return f"{kind}-{stable_id}"


def _evidence_url(kind, stable_id):
    path = _ledger_path(kind, _ledger_bucket(stable_id)) if kind in {"assertion", "source"} else "/research/data/"
    return path + "#" + _token(_anchor(kind, stable_id))


def _ledger_bucket(stable_id):
    """A corpus-independent destination; adding records never moves old IDs."""
    return hashlib.sha256(str(stable_id).encode("utf-8")).hexdigest()[0]


def _ledger_path(kind, bucket):
    if kind not in {"assertion", "source"} or bucket not in LEDGER_BUCKETS or len(bucket) != 1:
        raise ValueError("Unknown ledger kind or partition")
    return "/research/data/" + {"assertion": "assertions", "source": "sources"}[kind] + "/" + bucket + "/"


def _safe_url(value):
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return ""
    return str(value) if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password else ""


def _link(url, label, css=""):
    url = str(url or "")
    if not (url.startswith("/") and not url.startswith("//")) and not url.startswith('#') and not _safe_url(url):
        return sp.escape(label)
    return f'<a href="{sp.escape(url)}"' + (f' class="{sp.escape(css)}"' if css else "") + f'>{sp.escape(label)}</a>'


def _day(value):
    if isinstance(value, str) and "T" in value:
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                return instant.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
        except ValueError:
            pass
    return str(value or "")[:10]


def _date(value):
    return sp.format_date(_day(value)) if value else "Not recorded"


def _revision_dates(context):
    """Dates of this page's substantive inputs, never the build/snapshot clock.

    A claim review contributes only to the exact assertion it actually binds.
    Entity metadata has no revision timestamp in the graph schema; a metadata
    only page therefore has an unknown revision date rather than an invented one.
    """
    from research_graph import assertion_digest
    from research_report import canonical_hash, report_review_digest

    def latest(values):
        days = [_day(value) for value in values if value]
        return max((day for day in days if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day)), default=None)

    graph = context['graph']
    reviews = {row['id']: row for row in graph.get('reviews', [])}
    claims, source_reviews = {}, {}
    for assertion in graph['assertions']:
        aid = assertion['id']
        bound = [reviews[rid] for rid in assertion.get('review_ids', []) if rid in reviews
                 and aid in reviews[rid].get('assertion_ids', [])
                 and reviews[rid].get('assertion_sha256', {}).get(aid) == assertion_digest(assertion)]
        claims[aid] = latest([assertion.get('as_of')] + [row.get('reviewed_on') for row in bound])
        for evidence in assertion.get('evidence', []):
            source_reviews.setdefault(evidence['source_id'], []).extend(row.get('reviewed_on') for row in bound)
    dates = {}
    for entity in graph['entities']:
        dates[entity_url(entity, context)] = latest(claims[row['id']] for row in _assertions(context, entity))
    for slug, _, kinds, _ in CATEGORIES:
        dates['/research/' + slug + '/'] = latest(dates.get(entity_url(entity, context))
                                                for entity in graph['entities'] if entity.get('kind') in kinds)
    corrections = context.get('_render_corrections')
    if corrections is None:
        corrections = _correction_records(context)
    corrected = {}
    for row in corrections:
        corrected.setdefault(row['claim_id'], []).append(row['corrected_on'])
    assertions, stubs, sources = _ledger_records(context)
    for kind, records in (('assertion', {**assertions, **{aid: {'id': aid} for aid in stubs}}),
                          ('source', sources)):
        for bucket in LEDGER_BUCKETS:
            values = []
            for row in records.values():
                if _ledger_bucket(row['id']) != bucket:
                    continue
                if kind == 'assertion':
                    values.extend([claims.get(row['id']), *corrected.get(row['id'], [])])
                else:
                    values.extend([row.get('captured_on'), *source_reviews.get(row['id'], [])])
            dates[_ledger_path(kind, bucket)] = latest(values)
    report_hash, graph_hash = report_review_digest(context['report']), canonical_hash(graph)
    report_reviews = [row.get('reviewed_on') for row in context.get('policy', {}).get('report_reviews', [])
                      if row.get('fixture') is False and row.get('method') == 'report_content_review'
                      and row.get('report_sha256') == report_hash and row.get('graph_sha256') == graph_hash
                      and row.get('reviewer') and row.get('invocation_id')]
    report_date = latest([context['report'].get('updated_on'), *report_reviews])
    dates[REPORT_PATH] = report_date
    for section in context["report"]["sections"][1:]:
        dates[_reader_path(section)] = report_date
    dates[CORRECTIONS_PATH] = latest(row['corrected_on'] for row in corrections)
    corpus_date = latest(dates.values())
    for path in ('/research/', '/research/data/', '/review/'):
        dates[path] = latest([report_date, corpus_date])
    return dates


def _page_revision(context, path):
    dates = context.get('_page_revisions')
    if dates is None:
        dates = _revision_dates(context)
    # Immutable editions use their own snapshot's map, never today's inputs.
    if re.fullmatch(r'/research/editions/[^/]+/', path):
        path = REPORT_PATH
    elif re.fullmatch(r'/research/editions/[^/]+/chapters/[^/]+/', path):
        path = REPORT_PATH + path.split('/', 4)[4]
    else:
        path = re.sub(r'^/research/editions/[^/]+/data/', '/research/data/', path)
    return dates.get(path)


def _sitemap_record(context, path):
    modified = _page_revision(context, path)
    return {'path': path, **({'lastmod': modified} if modified else {})}


def _category(entity):
    return next((row for row in CATEGORIES if entity.get("kind") in row[2]), None)


def entity_url(entity, context=None):
    """Use existing company canonicals; create new organization pages only on approval."""
    if entity.get("legacy_id"):
        return "/company/" + _path_token(entity["legacy_id"]) + "/"
    category = _category(entity)
    if category:
        return "/research/" + category[0] + "/" + _path_token(entity["id"]) + "/"
    if context is not None and _new_company(context, entity):
        return "/company/" + _path_token(entity["id"]) + "/"
    return _evidence_url("entity", entity["id"])


def _entities(context):
    rows = context.get('_render_entities')
    return rows if rows is not None else {row['id']: row for row in context['graph']['entities']}


def _assertions(context, entity=None, statuses=("approved",)):
    scope = {entity['id']} if entity is not None else set()
    if entity is not None and entity.get('kind') in {'paper', 'paper_work', 'dataset', 'dataset_family', 'benchmark', 'benchmark_family'}:
        # A family view shows its explicit releases; each assertion still names
        # its actual subject/version. Organization views never infer supply.
        scope.update(e['id'] for e in context['graph']['entities'] if e.get('parent_id') == entity['id'])
    return sorted((row for row in context["graph"]["assertions"]
                   if row.get("status") in statuses and (entity is None or
                   scope & {row.get("subject_id"), row.get("object_id")})),
                  key=lambda row: row["id"])


def _approved_entity(context, entity):
    return entity.get("status") == "approved" and bool(_assertions(context, entity))


def _new_company(context, entity):
    companies = context.get('_render_company_ids')
    if companies is not None:
        return entity['id'] in companies
    return (not entity.get('legacy_id') and entity.get('kind') in {'supplier', 'organization', 'institution'}
            and _approved_entity(context, entity)
            and any(a.get('subject_id') == entity['id'] for a in _assertions(context, entity)))


def _display_title(value):
    """Render the two recorded tau spellings without changing source identity."""
    return str(value or "").replace(r"$\tau^2$", "τ²").replace(r"$\tau$", "τ")


def _label(entity):
    if entity.get('status') == 'approved' and entity.get('review_depth') == 'metadata':
        return 'Approved metadata'
    return STATUS_LABELS.get(entity.get("status"), "Review status unknown")


def _meta(context):
    report, graph = context["report"], context["graph"]
    return (f'<p class="r-meta">Prepared {_date(report.get("updated_on"))} '
            f'<span aria-hidden="true">·</span> Evidence snapshot {_date(graph.get("as_of"))} '
            f'<span aria-hidden="true">·</span> Report {sp.escape(report.get("release_id"))}'
            + (f' <span aria-hidden="true">·</span> Evidence {sp.escape(graph.get("release_id"))}' if graph.get('release_id') != report.get('release_id') else '') + '</p>')


def _status(context):
    if context["gate"].get("ready") and context["report"].get("status") in {"published", "superseded"}:
        return "Published research edition"
    return "Publication requirements passed" if context["gate"].get("ready") else "Prelaunch · evidence in preparation"


def _nav(current="", historical=False):
    links = [("Research", "/research/"), ("Current report" if historical else "Report", REPORT_PATH)]
    links += [(label, "/research/" + slug + "/") for slug, label, _, _ in CATEGORIES]
    links += [("Data & sources", "/research/data/"), ("Review", "/review/")]
    return '<nav class="r-nav" aria-label="Research">' + "".join(
        f'<a href="{url}"' + (' aria-current="page"' if url == current else "") + f'>{label}</a>'
        for label, url in links) + "</nav>"


def _crumbs(label, path, parent=None):
    if path.startswith('/company/'):
        crumbs = [('Home', sp.ORIGIN + '/'), ('Research', sp.ORIGIN + '/research/'), (label, sp.ORIGIN + path)]
        return sp.crumb_nav(crumbs, css_class='company-crumbs'), crumbs
    crumbs = [("Home", sp.ORIGIN + "/"), ("Research", sp.ORIGIN + "/research/")]
    if parent:
        if parent[0].startswith("/"):
            crumbs.append((parent[1], sp.ORIGIN + parent[0]))
        else:
            crumbs.append((parent[1], sp.ORIGIN + "/research/" + parent[0] + "/"))
    if path != "/research/":
        crumbs.append((label, sp.ORIGIN + path))
    return sp.crumb_nav(crumbs), crumbs


def _render(context, title, description, path, body, page_type="WebPage", parent=None):
    title = _display_title(title)
    crumbs_html, crumbs = _crumbs(title, path, parent)
    identity = context["identity"]
    person = identity.get("publisher", {})
    publisher = {"@type": person.get("type", "Person"), "@id": person.get("id", sp.ORIGIN + "/#publisher"),
                 "name": person.get("name", sp.PUBLISHER_NAME), "url": person.get("url", sp.ORIGIN + "/method/#about")}
    structured = sp.page_node(page_type, title, description, sp.ORIGIN + path,
                              _page_revision(context, path), crumbs, publisher=publisher)
    if not structured['dateModified']:
        structured.pop('dateModified')
    if page_type in {"TechArticle", "Book", "Chapter"}:
        structured.update({"author": publisher, "creativeWorkStatus": _status(context),
                           "version": context["report"]["release_id"],
                           "license": sp.DATA_LICENSE})
    if page_type in {"Book", "Chapter"}:
        base = path.split('chapters/', 1)[0] if page_type == "Chapter" else path
        parts = [{"@type": "Chapter", "@id": sp.ORIGIN + _reader_path(section, base)
                  + ('#' + _token(section['id']) if section['id'] == 'executive-assessment' else ''),
                  "url": sp.ORIGIN + _reader_path(section, base)
                  + ('#' + _token(section['id']) if section['id'] == 'executive-assessment' else ''),
                  "name": section['title'], "position": index + 1}
                 for index, section in enumerate(context['report']['sections'])]
        if page_type == "Book":
            structured['hasPart'] = parts
        else:
            section = next(section for section in context['report']['sections'] if _reader_path(section, base) == path)
            structured['isPartOf'] = {"@type": "Book", "@id": sp.ORIGIN + base,
                                      "name": context['report']['title'], "version": context['report']['release_id']}
            structured['position'] = next(index + 1 for index, item in enumerate(context['report']['sections']) if item['id'] == section['id'])
    if path == '/research/data/':
        dataset = {"@type": "Dataset", "@id": sp.ORIGIN + '/research/data/#dataset',
                   "name": "ScienceToStartup public research projection", "url": sp.ORIGIN + path,
                   "description": "A separately versioned public research projection with explicit claim status, source evidence and historical provenance.",
                   "version": context['report']['release_id'], "creator": publisher, "license": sp.DATA_LICENSE,
                   "isBasedOn": {"@id": sp.DATASET_ID}, "distribution": [
                       {"@type": "DataDownload", "encodingFormat": mime, "contentUrl": sp.ORIGIN + '/publication/' + name}
                       for name, mime in (("clean-dataset.json", "application/json"), ("clean-dataset.csv", "text/csv"), ("clean-dataset.sqlite", "application/vnd.sqlite3"))]}
        structured = {"@context": "https://schema.org", "@graph": [structured, dataset]}
    research = SimpleNamespace(as_of=_day(context["graph"]["as_of"]),
                               data={"dataset_version": context["graph"].get("canonical_dataset_version")},
                               research_release_context={"release_id": context["report"]["release_id"],
                                                         "evidence_as_of": context["graph"]["as_of"]})
    company_page = path.startswith('/company/')
    document_title = " ".join(title.split())
    edition = re.match(r'^/research/editions/(\d{4}-\d{2}-\d{2})/', path)
    if edition:
        document_title += ' · ' + sp.format_date(edition.group(1)) + ' edition'
    elif parent and parent[0] in {'papers', 'benchmarks'}:
        document_title += ' · ' + ('Research paper' if parent[0] == 'papers' else 'Benchmark')
    current_state = "page" if path == "/research/" or path.startswith("/research/editions/") else "true"
    text = sp.document(research, document_title + sp.SUFFIX, sp.truncate(description),
                       sp.ORIGIN + path, '<div class="research wide">' + crumbs_html
                       + (_nav(path, historical=bool(edition)) if path != "/research/" and not company_page else "") + body + "</div>",
                       structured=structured, current="companies" if company_page else "research", state=current_state)
    extra = ('<link rel="stylesheet" href="/research.css">\n'
             '<link rel="alternate" type="application/rss+xml" title="Published research editions" href="/research/feed.xml">\n'
             '<link rel="alternate" type="application/atom+xml" title="Published research editions" href="/research/atom.xml">\n'
             '<link rel="alternate" type="application/rss+xml" title="Research corrections" href="/research/corrections/feed.xml">\n'
             '<link rel="alternate" type="application/atom+xml" title="Research corrections" href="/research/corrections/atom.xml">\n')
    if company_page:
        extra += '<link rel="stylesheet" href="/company-profile.css">\n'
    if page_type == 'Chapter':
        extra += '<script src="/native-details.js" defer></script>\n'
    if page_type == 'Chapter' and path.endswith('/chapters/technical-landscape/'):
        # A history restoration needs the complete layout used when the reader
        # followed a citation. With scripting unavailable, keep that layout too.
        extra += ('<script>(function(){try{var nav=performance.getEntriesByType("navigation")[0];'
                  'if(nav&&nav.type==="navigate")document.documentElement.setAttribute("data-reader-enhanced","");'
                  'addEventListener("DOMContentLoaded",function(){if(!document.documentElement.hasAttribute("data-reader-end-ready"))'
                  'document.documentElement.removeAttribute("data-reader-enhanced")});'
                  'addEventListener("pageshow",function(event){if(event.persisted)document.documentElement.removeAttribute("data-reader-enhanced")});'
                  '}catch(_){}})();</script>\n')
    if page_type in {"Book", "Chapter"}:
        base = path.split('chapters/', 1)[0] if page_type == 'Chapter' else path
        current = next(index for index, section in enumerate(context['report']['sections']) if _reader_path(section, base) == path)
        for relation, index in (('prev', current - 1), ('next', current + 1)):
            if 0 <= index < len(context['report']['sections']):
                extra += '<link rel="' + relation + '" href="' + sp.escape(_reader_path(context['report']['sections'][index], base)) + '">\n'
    if 'data-research-index' in body:
        extra += '<script src="/research-index.js" defer></script>\n'
    return text.replace("</head>", extra + "</head>", 1)


def _progress(context, compact=False):
    counts = context["gate"].get("coverage", {})
    floors = context["gate"].get("thresholds", {})
    parts = []
    for key, label, default in PROGRESS:
        current, floor = counts.get(key, 0), max(default, floors.get(key, default))
        ratio = min(100, max(0, current / floor * 100))
        value = f"{current:.0%}" if key.endswith("rate") else str(current)
        target = f"{floor:.0%}" if key.endswith("rate") else str(floor)
        if key == "core_disposition_rate" and not counts.get("core_eligible"):
            value = "Not frozen"
        parts.append(f'<div class="r-progress-item"><dt>{sp.escape(label)}</dt>'
                     f'<dd><strong>{sp.escape(value)}</strong><span> / {sp.escape(target)}</span>'
                     f'<span class="r-meter" aria-hidden="true"><span style="width:{ratio:.2f}%"></span></span></dd></div>')
    return '<dl class="r-progress' + (' is-compact' if compact else '') + '">' + "".join(parts) + "</dl>"


def _holds(context):
    reasons = context["gate"].get("reasons", [])
    if not reasons:
        return '<p class="r-callout">The calculated publication requirements pass. Edition publication still follows the recorded release process.</p>'
    return (f'<details class="r-holds"><summary>{len(reasons)} publication requirements remain</summary><ul>'
            + "".join(f"<li>{sp.escape(reason)}</li>" for reason in reasons) + "</ul></details>")


def _counts(context):
    counts = context["gate"].get("coverage", {})
    return (f'{counts.get("approved_assertions", 0)} approved assertions · '
            f'{counts.get("candidate_assertions", 0)} candidate assertions · '
            f'{counts.get("historical_assertions", 0)} historical descriptions')


def _browse(context):
    cards = []
    icons = {
        "papers": '<path d="M7 3h7l4 4v14H7zM14 3v5h4M10 12h5M10 16h5"/>',
        "datasets": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
        "benchmarks": '<path d="M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7M3 20h18"/>',
        "workflows": '<rect x="3" y="8" width="6" height="8" rx="1"/><rect x="15" y="8" width="6" height="8" rx="1"/><path d="M9 12h6m-3-3 3 3-3 3"/>',
    }
    for slug, title, kinds, description in CATEGORIES:
        rows = [e for e in context["graph"]["entities"] if e.get("kind") in kinds]
        approved = sum(e.get('status') == 'approved' for e in rows)
        candidate = sum(e.get("status") == "candidate" for e in rows)
        approval_label = 'approved records'
        if slug == 'datasets':
            approval_label = 'approved catalog records'
        elif slug == 'papers':
            approval_label = 'approved works and versions'
        candidate_label = "candidate" if candidate == 1 else "candidates"
        cards.append(f'<article class="r-browse-card"><a class="r-browse-link" href="/research/{slug}/">'
                     f'<svg class="r-browse-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" '
                     f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{icons[slug]}</svg>'
                     f'<h3>{sp.escape(title)} <span aria-hidden="true">→</span></h3><p>{sp.escape(description)}</p>'
                     f'<span class="r-record-count">{approved} {approval_label} · {candidate} {candidate_label}</span></a></article>')
    return '<div class="r-browse-grid">' + "".join(cards) + "</div>"


def _hub(context, editions=()):
    report = context["report"]
    chapters = "".join(f'<li>{_link(_reader_path(section), section["title"])}</li>'
                       for section in report["sections"])
    archive_links = ('<section class="r-section"><h2>Published editions</h2><ul class="r-entity-list">'
                     + ''.join(f'<li>{_link(path, snapshot["report"]["release_id"])} · {_date(snapshot["report"]["updated_on"])}</li>'
                               for path, snapshot in editions) + '</ul></section>') if editions else ''
    return ('<header class="r-hero"><div>'
            '<h1>AI data research</h1><p class="r-lede">Papers and datasets on AI training, with evidence about the suppliers.</p>'
            f'<p class="r-status">{_status(context)}</p>'
            f'<p class="r-meta">Evidence snapshot {_date(context["graph"].get("as_of"))}</p></div>'
            '<aside class="r-report-card" aria-label="Current research report">'
            f'<h2>{sp.escape(report["title"])}</h2>'
            f'<p>{len(report["sections"])} chapters on suppliers, human feedback, research methods and paid pilots.</p>'
            f'{_link(REPORT_PATH, "Read the report →", "r-button")}</aside></header>'
            '<section class="r-section" aria-labelledby="browse"><div class="r-section-head">'
            '<h2 id="browse">Browse the research</h2>'
            f'{_link("/research/data/", "Sources & downloads →", "r-text-link")}</div>' + _browse(context) + '</section>'
            + operating_status_notice(context) +
            '<section class="r-section r-hub-details" aria-label="Report details">'
            '<details class="r-disclosure" id="chapters">'
            f'<summary>Report contents <span>{len(report["sections"])} chapters</span></summary>'
            f'<ol class="r-chapter-list">{chapters}</ol></details>'
            '<details class="r-disclosure" id="coverage"><summary>Publication status and coverage</summary>'
            f'{_meta(context)}'
            f'<p class="r-section-intro">{sp.escape(report.get("summary"))}</p>'
            '<p class="r-section-intro">Publication totals count suppliers, distinct paper works and dataset or benchmark families. '
            'Browse counts also include individual versions. '
            'Only approved, source-reviewed records meet the publication requirements.</p>' + _progress(context, compact=True)
            + f'<p class="r-meta">{sp.escape(_counts(context))}</p>'
            f'{_link("/research/data/", "Coverage, sources & downloads →", "r-text-link")}</details>'
            '<p class="r-review-link">Found something to correct? '
            f'{_link("/review/", "Review a claim or suggest a source →")}</p></section>'
            + archive_links)


def _structured_claim_value(assertion):
    """Recognize the reviewed statement wrapper without altering stored bytes."""
    value = assertion.get('value')
    if not isinstance(value, dict) or value.get('type') != 'text' or not isinstance(value.get('value'), str):
        return None
    try:
        parsed = json.loads(value['value'])
    except (ValueError, RecursionError):
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get('statement'), str) and parsed['statement'].strip():
        return parsed
    return None


def _scope_value(value):
    """Readable structured scope, preserving explicit unknowns and qualifiers."""
    if value is None:
        return 'Not stated in the source'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        return sp.escape(format(value, ','))
    if isinstance(value, list):
        return '<ul>' + ''.join('<li>' + _scope_value(item) + '</li>' for item in value) + '</ul>'
    if isinstance(value, dict):
        return '<ul>' + ''.join('<li><strong>' + sp.escape(key.replace('_', ' ').capitalize()) + ':</strong> '
                               + _scope_value(item) + '</li>' for key, item in value.items()
                               if key not in {'claim_class', 'company_entity_id', 'type', 'scope_kind'}) + '</ul>'
    label = {'company_reported': 'Reported by the company',
             'reported_audited_financial_statements': 'Reported in audited financial statements',
             'not_explicit_in_bound_pricing_FAQ': 'Not explicit in the cited pricing FAQ'}.get(str(value))
    if label is None:
        label = str(value).replace('_', ' ') if re.fullmatch(r'[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+', str(value)) else str(value)
    return sp.escape(label)


def _claim_scope(assertion):
    value = _structured_claim_value(assertion)
    if not value or assertion.get('status') not in {'approved', 'historical'}:
        return ''
    scope_labels = {'company': 'Entity', 'includes': 'Included entities', 'product': 'Product',
                    'service': 'Service', 'segments': 'Business segments', 'supplier_relevant_segment': 'Supplier segment',
                    'adjacent_segment': 'Adjacent segment', 'geographic_scope': 'Geographic scope',
                    'activities': 'Activities', 'modes': 'Delivery modes', 'not_isolated': 'Not separately reported',
                    'historical_software_context': 'Historical product context', 'provenance_scope': 'Evidence scope'}
    basis_labels = {'amount': 'Amount', 'currency': 'Currency', 'currency_symbol': 'Currency symbol',
                    'currency_note': 'Currency qualification', 'period_start': 'Period start', 'period_end': 'Period end',
                    'period_label': 'Reporting period', 'reported_or_estimated': 'Reported or estimated',
                    'annualized': 'Annualized amount', 'active_window': 'Activity window', 'scope': 'Reported entity or segment scope',
                    'is_revenue': 'Revenue measure', 'is_human_data_segment_revenue': 'Isolated human-data segment revenue',
                    'metric': 'Measure', 'unit': 'Unit', 'qualifier': 'Value qualifier', 'values': 'Reported values',
                    'waitlist': 'Separate waitlist', 'percentage_denominator': 'Percentage denominator',
                    'denominator_status': 'Denominator qualification', 'conditions': 'Source conditions', 'statement': 'Basis statement'}
    scope_kinds = {'company_reported_business_segments': 'Company-described business segments',
                   'described_business_activities_not_financial_reporting_segments': 'Described business activities; financial reporting segments are not established',
                   'geographic_operating_segments': 'Geographic operating segments',
                   'nonexclusive_data_product_line': 'Nonexclusive data product line',
                   'expert_access_product': 'Expert access product', 'expert_data_service': 'Expert data service',
                   'legal_operator_and_statement_group': 'Legal operator and entities covered by the statement',
                   'separate_product_delivery_modes': 'Separate product and delivery modes', 'product_capability': 'Product capability'}
    rows = []
    for field, labels in (('scope', scope_labels), ('reported_value_and_basis', basis_labels)):
        details = value.get(field)
        if not isinstance(details, dict):
            continue
        for key, item in details.items():
            if key in {'claim_class', 'company_entity_id', 'type'}:
                continue
            if key == 'scope_kind':
                if not isinstance(item, str) or item not in scope_kinds:
                    continue
                label, shown = 'Scope', sp.escape(scope_kinds[item])
            else:
                label = labels.get(key, key.replace('_', ' ').capitalize())
                shown = 'Not defined in the source' if key == 'active_window' and item is None else _scope_value(item)
            rows.append('<dt>' + sp.escape(label) + '</dt><dd>' + shown + '</dd>')
    return ('<details class="r-receipts"><summary>Scope and reported basis</summary><dl class="r-facts">'
            + ''.join(rows) + '</dl></details>') if rows else ''


def _claim_text(context, assertion):
    entities = _entities(context)
    subject = entities.get(assertion.get("subject_id"), {})
    obj = entities.get(assertion.get("object_id"), {})
    subject_html = _link(entity_url(subject, context), subject.get("name", "Unknown subject")) if subject else "Unknown subject"
    if assertion.get("value") is not None:
        structured = _structured_claim_value(assertion)
        if structured:
            statement = structured['statement']
            name = subject.get('name')
            match = re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', statement) if name else None
            return (sp.escape(statement[:match.start()]) + subject_html + sp.escape(statement[match.end():])) if match else sp.escape(statement)
        value = assertion["value"]
        if isinstance(value, dict):
            value = value.get("value", "")
        relation = str(assertion.get("predicate", "observation")).replace("_", " ")
        label = "" if assertion.get("predicate") == "legacy_description" else " · " + relation
        if isinstance(value, bool):
            value = 'Yes' if value else 'No'
        return f'{subject_html}{sp.escape(label)}: {sp.escape(value)}'
    if assertion.get("status") in {"approved", "historical"} and assertion.get("object_id"):
        prefix = "Scoped source statement: "
        statements = [item[len(prefix):].strip() for item in assertion.get("qualifications", [])
                      if isinstance(item, str) and item.startswith(prefix) and item[len(prefix):].strip()]
        if len(statements) == 1:
            return sp.escape(statements[0])
    relation = str(assertion.get("predicate", "relationship")).replace("_", " ")
    object_html = _link(entity_url(obj, context), obj.get("name", "Unknown object")) if obj else "Unknown object"
    return f'{subject_html} {sp.escape(relation)} {object_html}.'


def _source_evidence(context, assertion):
    if assertion.get("status") not in {"approved", "historical"}:
        return ''
    sources = context.get('_render_sources')
    if sources is None:
        sources = {row['id']: row for row in context['graph']['sources']}
    rows = []
    for evidence in assertion.get("evidence", []):
        source = sources.get(evidence.get("source_id"), {})
        excerpt = ''
        if (assertion.get('status') == 'approved' and source.get('status') == 'captured'
                and source.get('excerpt') and evidence.get('excerpt_sha256') == source.get('excerpt_sha256')):
            excerpt = '<blockquote class="r-evidence-excerpt"><p>' + sp.escape(source['excerpt']) + '</p></blockquote>'
        rows.append('<li>' + _link(_evidence_url("source", source.get("id", "")), source.get("title", evidence.get("source_id")))
                    + f'<span class="r-source-locator">Locator: {sp.escape(evidence.get("locator", "Not recorded"))}</span>' + excerpt + '</li>')
    return ('<p class="r-meta">Source records</p><ul class="r-evidence-links">' + "".join(rows) + "</ul>") if rows else ''


def _assertion(context, assertion, *, compact=False, correction='', focusable=False):
    status = assertion.get("status")
    aid = assertion["id"]
    public_rows = context.get('_render_corrections')
    if public_rows is None:
        public_rows = _correction_records(context)
    corrections = [row for row in public_rows if row['claim_id'] == aid]
    body = f'<p class="r-kicker">{sp.escape(STATUS_LABELS.get(status, status))} · As of {_date(assertion.get("as_of"))}</p>'
    if status in {"approved", "historical"}:
        body += '<p class="r-assertion-text">' + _claim_text(context, assertion) + "</p>"
        body += _claim_scope(assertion)
    else:
        body += ('<p>Superseded candidate wording is withheld. Follow the correction record and approved replacement below.</p>'
                 if any(row.get('replacement_claim_id') for row in corrections) else
                 '<p>Candidate wording is withheld from findings while source verification and adversarial review are pending.</p>')
    for row in corrections:
        body += '<p>Correction: ' + _link(_correction_url(row), row['summary']) + '</p>'
        if row.get('replacement_claim_id'):
            body += '<p>Approved replacement: ' + _link(_evidence_url('assertion', row['replacement_claim_id']), row['replacement_claim_id']) + '</p>'
    body += f'<p class="r-record-id">Permanent record ID: {_link(_evidence_url("assertion", aid), aid)}</p>'
    body += correction
    if assertion.get("qualifications") and status in {"approved", "historical"}:
        body += '<ul class="r-qualifications">' + "".join(
            '<li>' + ('<strong>Original author-stage note:</strong> ' if q.startswith(('Author-only candidate', 'Actual new author-only source-content proposal.')) else '') + sp.escape(q) + '</li>'
            for q in assertion["qualifications"]) + "</ul>"
    if compact:
        body += '<p class="r-meta">' + _link(_evidence_url("assertion", aid),
                    "Inspect pinned sources, evidence and separate AI review receipts") + '</p>'
        return f'<article class="r-assertion" data-status="{sp.escape(status)}" id="{sp.escape(_anchor("assertion", aid))}">{body}</article>'
    body += _source_evidence(context, assertion)
    reviews = context.get('_render_reviews')
    if reviews is None:
        reviews = {row['id']: row for row in context['graph'].get('reviews', [])}
    receipts = [reviews[rid] for rid in assertion.get("review_ids", []) if rid in reviews]
    if receipts:
        body += '<details class="r-receipts"><summary>AI review receipts</summary><ul>' + "".join(
            f'<li>{sp.escape(r.get("role", "").replace("_", " ").capitalize())}: {sp.escape(r.get("verdict"))} '
            f'· {_date(r.get("reviewed_on"))}<br><span class="r-record-id">{sp.escape(r.get("invocation_id"))}</span></li>'
            for r in sorted(receipts, key=lambda row: (row.get("role", ""), row["id"]))) + "</ul></details>"
    elif status == "historical":
        body += '<p class="r-meta">Inherited provenance; no fresh research review is claimed.</p>'
    target = ' tabindex="-1"' if focusable else ''
    return f'<article class="r-assertion" data-status="{sp.escape(status)}" id="{sp.escape(_anchor("assertion", aid))}"{target}>{body}</article>'


def _paragraph(context, paragraph, *, anchor='', original_sources=()):
    ids = paragraph.get("claim_ids", [])
    kind = paragraph.get("kind")
    target = f' id="{sp.escape(anchor)}" tabindex="-1"' if anchor else ''
    if not paragraph_supported(context, paragraph):
        return '<div class="r-paragraph is-gap"' + target + '><span class="r-paragraph-kind">Research gap</span><p>' + WITHHELD_PARAGRAPH + '</p></div>'
    label = "Historical example" if paragraph.get("historical") else KIND_LABELS.get(kind, "Research note")
    links = ('<p class="r-paragraph-citations">Evidence: ' + ", ".join(_link(_evidence_url("assertion", cid), cid) for cid in ids) + "</p>") if ids else ""
    originals = ('<div class="r-paragraph-originals">Original sources: ' + ' · '.join(
        _link(url, title) for url, title in original_sources) + '</div>') if original_sources else ''
    return (f'<div class="r-paragraph' + (' is-gap' if kind == "research_gap" else '') + '"' + target + '>'
            f'<span class="r-paragraph-kind">{label}</span><p>{sp.escape(paragraph.get("text"))}</p>{links}{originals}</div>')


def _chapter_outline(section, assertions):
    paragraphs = section['paragraphs']
    if section['id'] == 'buyer-decision-guides':
        for index, paragraph in enumerate(paragraphs):
            value = paragraph['text']
            if match := BUYER_OPENING.match(value):
                number, title = match.groups()
                stages = ('proposed paid pilot', 'proposed acceptance and limits')
                following = paragraphs[index + 1:index + 3]
                if len(following) == len(stages) and all(p['text'].startswith(f'Buyer use case {number} — {title}: {stage}.')
                                                         for p, stage in zip(following, stages)):
                    yield index, index + 3, f'buyer-use-case-{number}', title
            for title, anchor in BUYER_RECORDS.items():
                if value.startswith((title + ':', title + '.')):
                    yield index, index + 1, anchor, title
    elif section['id'] == 'provider-dossiers':
        for name, group in groupby(enumerate(paragraphs), lambda row: row[1]['text'].split(' — ', 1)[0]):
            rows = list(group)
            prefix = name + ' — '
            opening = rows[0][1]['text']
            if not opening.startswith(prefix):
                continue
            qualifier = opening.removeprefix(prefix).split('. ', 1)[0]
            if qualifier == PROVIDER_ADJACENT.get(name):
                title = prefix + qualifier
            elif qualifier == 'offering and scope' or (name in PROVIDER_BRANDS and qualifier.startswith('operating-brand offer within the ')):
                title = name
            else:
                continue
            subjects = {assertions.get(cid, {}).get('subject_id', '') for _, p in rows for cid in p.get('claim_ids', [])}
            orgs = {sid for sid in subjects if sid.startswith('org.')}
            stable_id = PROVIDER_BRANDS.get(name) or (next(iter(orgs)) if len(orgs) == 1 else '')
            if stable_id in orgs:
                yield rows[0][0], rows[-1][0] + 1, 'provider-' + stable_id, title


def _chapter_shortcuts(context, section, assertions):
    for anchor, label, lead_in, claim_id in PASSAGE_SHORTCUTS.get(section['id'], ()):
        if claim_id and assertions.get(claim_id, {}).get('status') != 'approved':
            continue
        matches = [(index, paragraph) for index, paragraph in enumerate(section['paragraphs'])
                   if paragraph['text'].startswith(lead_in) and
                   (claim_id in paragraph.get('claim_ids', []) if claim_id else paragraph['kind'] == 'method')]
        if len(matches) == 1:
            index, paragraph = matches[0]
            if index and paragraph_supported(context, paragraph):
                yield index, anchor, label


def _chapter_content(context, section, outline, passages=()):
    assertions = {row['id']: row for row in context['graph']['assertions']}
    sources = {row['id']: row for row in context['graph']['sources']}
    openings = {start: (anchor, title) for start, _, anchor, title in outline}
    ends = {end for _, end, _, _ in outline}
    passage_anchors = {index: anchor for index, anchor, _ in passages}
    contents = ''
    if outline:
        entries = ''.join('<li>' + _link('#' + anchor, title) + '</li>' for _, _, anchor, title in outline)
        contents = ('<details class="r-bulk-contents"><summary id="section-contents">Section contents</summary>'
                    '<nav class="r-bulk-list" aria-label="Sections in this chapter"><ol>' + entries + '</ol></nav></details>')
    blocks = []
    for index, paragraph in enumerate(section['paragraphs']):
        if index in openings:
            anchor, title = openings[index]
            blocks.append(f'<section class="r-bulk-section" aria-labelledby="{sp.escape(anchor)}">'
                          f'<h2 class="r-bulk-target" id="{sp.escape(anchor)}" tabindex="-1">'
                          + _link('#' + anchor, title) + '</h2>')
        originals = {}
        prose = paragraph.get('text', '')
        if section['id'] == 'methods-and-appendices' and ' bibliography — ' in prose:
            for cid in paragraph.get('claim_ids', []):
                claim = assertions.get(cid, {})
                if claim.get('status') not in {'approved', 'historical'}:
                    continue
                for pin in claim.get('evidence', []):
                    source = sources.get(pin.get('source_id'), {})
                    if (url := _safe_url(source.get('url'))) and re.search(re.escape(url) + r'(?=$|[\s;,.\)])', prose):
                        originals.setdefault(url, source.get('title') or url)
        anchor = 'first-paragraph' if index == 0 else passage_anchors.get(index, '')
        blocks.append(_paragraph(context, paragraph, anchor=anchor, original_sources=originals.items()))
        if index + 1 in ends:
            blocks.append('</section>')
        if index == 0:
            blocks.append(contents)
    return ''.join(blocks)


def _reader_shortcuts(outline=(), passages=(), *, chapter_count=0):
    jumps = ''
    if passages:
        entries = ''.join('<li>' + _link('#' + anchor, label) + '</li>' for _, anchor, label in passages)
        jumps = '<div class="r-passage-shortcuts"><span>Jump to</span><ul>' + entries + '</ul></div>'
    return ('<nav class="r-bulk-shortcuts r-outline-early" aria-label="Reading shortcuts">'
            + _link('#first-paragraph', 'First paragraph')
            + (_link('#contents', f'Browse {sp.plural(chapter_count, "chapter")}') if chapter_count else '')
            + (_link('#section-contents', 'Section contents') if outline else '') + jumps + '</nav>')


def _findings(context):
    findings, withheld = executive_findings(context)
    body = ''
    for finding in findings:
        body += (f'<article class="r-finding" id="{sp.escape(finding_anchor(finding))}">'
                 '<p class="r-kicker">Analytical judgment</p><h3>'
                 + _link('#' + finding_anchor(finding), finding['id']) + '</h3>'
                 + '<p>' + sp.escape(field_text(finding['text'])) + '</p><dl class="r-finding-fields">')
        for key, label in JUDGMENT_FIELDS:
            value = field_text(finding.get(key))
            if value:
                body += f'<dt>{label}</dt><dd>{sp.escape(value)}</dd>'
        body += '</dl><p class="r-paragraph-citations">Approved evidence: ' + ', '.join(
            _link(_evidence_url('assertion', cid), cid) for cid in finding['claim_ids']) + '</p></article>'
    if withheld:
        body += '<p class="r-callout">' + WITHHELD + '</p>'
    return body


def _reader_path(section, base=REPORT_PATH):
    if section['id'] == 'executive-assessment':
        return base
    return base + 'chapters/' + _path_token(section['id']) + '/'


def _reader_toc(context, current, base=REPORT_PATH, legacy_targets=False):
    rows = []
    for section in context['report']['sections']:
        sid = section['id']
        target = (' id="' + sp.escape(sid) + '"') if legacy_targets and sid != 'executive-assessment' else ''
        active = ' aria-current="page"' if sid == current else ''
        path = _reader_path(section, base) + ('#' + _token(sid) if target else '')
        rows.append('<li' + target + '><a href="' + sp.escape(path) + '"'
                    + active + '>' + sp.escape(section['title']) + '</a></li>')
    return ('<nav class="r-toc r-reader-toc" aria-label="Report chapters"><h2 id="contents">In this report</h2>'
            '<ol>' + ''.join(rows) + '</ol>'
            + _link('/research/data/', 'Inspect coverage & evidence →', 'r-text-link') + '</nav>')


def _has_pre_registration_report(archive):
    return archive.get('status') == 'published' and archive.get('artifact_sha256') == EDITION_MIRROR_ARCHIVE_SHA256


def _reader_downloads(context, *, edition=False):
    report = context['report']
    receipt = report.get('archive', {})
    archive = _safe_url(receipt.get('record_url'))
    prefix, note = 'Read offline: ', ''
    if edition and archive:
        if publication_metadata(context).get('doi'):
            links = (_link(_deposit_file(archive, 'report.pdf'), 'Download report PDF') + ' · '
                     + _link(_deposit_file(archive, 'research-archive.zip'), 'Download edition ZIP')
                     + ' · <code>report.html</code> inside the ZIP')
        else:
            links = _link(archive, 'Complete archived report & downloads')
    else:
        available = context.get('publication_assets', [])
        labels = ('Complete HTML report', 'Full report PDF')
        if not edition and _has_pre_registration_report(receipt):
            labels = ('Archived HTML report', 'Archived report PDF')
            prefix = ''
            note = f' · {_date(report["updated_on"])} snapshot. Prepared before DOI registration.'
        links = ' · '.join(_link('/' + path, label)
                           for path, label in zip(('publication/report.html', 'publication/report.pdf'), labels)
                           if path in available)
    return '<p class="r-reader-downloads">' + prefix + links + note + '</p>' if links else ''


def _reader_navigation(context, section_id, base=REPORT_PATH):
    sections = context['report']['sections']
    index = next(i for i, section in enumerate(sections) if section['id'] == section_id)
    links = []
    if index:
        previous = sections[index - 1]
        links.append('<a rel="prev" href="' + sp.escape(_reader_path(previous, base)) + '">← Previous: '
                     + sp.escape(previous['title']) + '</a>')
    links.append(_link(base + '#contents', 'All twelve chapters'))
    if index + 1 < len(sections):
        following = sections[index + 1]
        links.append('<a rel="next" href="' + sp.escape(_reader_path(following, base)) + '">Next: '
                     + sp.escape(following['title']) + ' →</a>')
    return '<nav class="r-reader-pagination" aria-label="Continue reading">' + ''.join(links) + '</nav>'


def _reader_citation(context, edition=False):
    report = context['report']
    return ('<section class="r-chapter" id="cite"><h2>Cite this work</h2><p>'
            + sp.escape(context['identity'].get('publisher', {}).get('name', sp.PUBLISHER_NAME)) + '. '
            '<cite>' + sp.escape(report['title']) + '</cite>. ' + sp.escape(report['release_id']) + '. '
            + _date(report['updated_on']) + '.</p>'
            + ('' if edition or (context['gate'].get('ready') and report.get('status') == 'published')
               else '<p>This is a prepublication research snapshot. No published research edition or DOI is claimed.</p>')
            + _link('/research/data/#citation', 'Citation formats & reuse →', 'r-text-link') + '</section>')


def _report(context, edition=False, base=REPORT_PATH):
    report = context['report']
    section = report['sections'][0]
    state = 'Published edition' if edition else _status(context)
    shortcuts = _reader_shortcuts(chapter_count=0 if edition else len(report['sections']))
    header = (f'<header class="r-page-head"><p class="r-kicker">{sp.escape(state)}</p>'
              f'<h1>{sp.escape(report["title"])}</h1>' + shortcuts
              + f'<p class="r-lede">{sp.escape(report.get("subtitle"))}</p>'
              + _meta(context) + '<p class="r-callout">' + sp.escape(report.get('summary')) + '</p>'
              + '<p class="r-meta">' + sp.escape(report.get('review_statement')) + '</p>'
              + _reader_downloads(context, edition=edition) + '</header>')
    body = ('<section class="r-chapter" id="' + sp.escape(section['id']) + '" tabindex="-1"><h2>'
            + sp.escape(section['title']) + '</h2>'
            + _chapter_content(context, section, ())
            + _findings(context) + '</section>'
            + _reader_navigation(context, section['id'], base) + _reader_citation(context, edition))
    return (header + ('' if edition else operating_status_notice(context))
            + '<div class="r-report-layout r-book-reader">'
            + _reader_toc(context, section['id'], base, legacy_targets=True)
            + '<div class="r-report-body">' + body + '</div></div>')


def _reader_chapter(context, section, base=REPORT_PATH, edition=False):
    report = context['report']
    index = next(i for i, item in enumerate(report['sections']) if item['id'] == section['id'])
    assertions = {row['id']: row for row in context['graph']['assertions']}
    outline = tuple(row for row in _chapter_outline(section, assertions)
                    if paragraph_supported(context, section['paragraphs'][row[0]]))
    passages = tuple(_chapter_shortcuts(context, section, assertions))
    shortcuts = _reader_shortcuts(outline, passages)
    early_shortcuts = bool(outline or passages) or section['id'] in EARLY_READER_SHORTCUTS
    header = ('<header class="r-page-head"><p class="r-kicker">Chapter ' + str(index + 1) + ' of '
              + str(len(report['sections'])) + ' · ' + sp.escape(_status(context)) + '</p>'
              + '<p class="r-reader-book-title">' + _link(base, report['title']) + '</p>'
              + '<h1 id="' + sp.escape(section['id']) + '" tabindex="-1">' + sp.escape(section['title']) + '</h1>'
              + ('' if early_shortcuts else shortcuts) + _meta(context) + _reader_downloads(context, edition=edition) + '</header>')
    body = ('<section class="r-chapter r-reader-chapter-content" aria-labelledby="' + sp.escape(section['id']) + '">'
            + _chapter_content(context, section, outline, passages) + '</section>'
            + _reader_navigation(context, section['id'], base) + _reader_citation(context, edition))
    return ((shortcuts if early_shortcuts else '') + header + '<div class="r-report-layout r-book-reader">'
            + _reader_toc(context, section['id'], base)
            + '<div class="r-report-body">' + body + '</div></div>')


def _source_recheck_notice(recheck):
    if not recheck:
        return ''
    return ('Original file unavailable when checked ' + _date(recheck['unavailable_on']) + '. '
            + _link(recheck['current_url'], 'Current issuer source (JavaScript)'))


def _source(source, correction='', recheck=None):
    if source.get('_compatibility'):
        return (f'<article class="r-source-stub" data-evidence-status="withheld" id="{sp.escape(_anchor("source", source["id"]))}">'
                '<h3>Earlier public source identifier</h3><p class="r-record-id">'
                + sp.escape(source['id']) + '</p><p>This earlier public link is retained for traceability. '
                'It has no source metadata or evidence binding in the current approved or historical findings. '
                'This placeholder adds no source record, assertion or coverage.</p>' + correction + '</article>')
    if source.get('_withheld'):
        return (f'<article class="r-source-stub" data-evidence-status="withheld" id="{sp.escape(_anchor("source", source["id"]))}">'
                '<h3>Source metadata withheld</h3><p class="r-record-id">'
                + sp.escape(source['id']) + '</p><p>This stable identifier is retained for traceability. '
                'It has no evidence binding in the current approved or historical findings. '
                'Draft-only citation metadata is withheld while its source identity and support are reviewed.</p>'
                + correction + '</article>')
    notice = _source_recheck_notice(recheck)
    return (f'<article class="r-source" id="{sp.escape(_anchor("source", source["id"]))}">'
            f'<h3>{_link(source.get("url"), source.get("title", source["id"]))}</h3>'
            + (f'<p class="r-meta">{notice}</p>' if notice else '')
            + f'<p class="r-record-id">{_link(_evidence_url("source", source["id"]), source["id"])}</p>'
            '<dl class="r-facts"><dt>Publisher</dt><dd>' + sp.escape(source.get("publisher")) + '</dd>'
            f'<dt>Published</dt><dd>{_date(source.get("published_on"))}</dd>'
            f'<dt>Captured</dt><dd>{_date(source.get("captured_on"))} · {sp.escape(source.get("status", "").replace("_", " "))}</dd>'
            f'<dt>Version</dt><dd>{sp.escape(source.get("version"))}</dd>'
            f'<dt>Locator</dt><dd>{sp.escape(source.get("locator"))}</dd></dl>'
            '<p class="r-meta">A source capture records retrieval. Assertion-specific review is recorded separately.</p>'
            + correction + '</article>')


def _source_rechecks(context):
    """Bind mutable reader links to the still-pinned approved evidence."""
    if not context.get('published_edition_replay') or context.get('root') is None:
        return {}
    root = Path(context['root'])
    path = root / SOURCE_RECHECKS
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError('Research source rechecks must be a bounded JSON file')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('schema_version') != 'research-source-recheck-v1'
            or not data.get('release_id') or not isinstance(data.get('rechecks'), list)):
        raise ValueError('Invalid research source rechecks')
    if data['release_id'] != context['report']['release_id']:
        return {}
    health = sp.link_health_index(json.loads((root / 'data/link-health.json').read_text(encoding='utf-8')))
    sources = {row['id']: row for row in context['graph']['sources']}
    claims = {row['id']: row for row in context['graph']['assertions'] if row['status'] == 'approved'}
    by_source = {}
    for recheck in data['rechecks']:
        original, current, homepage = (recheck[key] for key in ('original_url', 'current_url', 'publisher_homepage'))
        observed = health.get(sp.health_key(original), {})
        urls = [urlsplit(_safe_url(url)) for url in (original, current, homepage)]
        if (original == current or observed.get('status') != 'not_found'
                or any(not url.netloc or url.netloc != urls[0].netloc or url.query or url.fragment for url in urls)
                or any(re.search(r'[\s\x00-\x1f]', url) for url in (original, current, homepage))):
            raise ValueError('Research source recheck requires a dated unavailable original and the same issuer host')
        checked_on = recheck['checked_on']
        if date.fromisoformat(checked_on).isoformat() != checked_on:
            raise ValueError('Invalid research source recheck date')
        if any(not re.fullmatch(r'[a-f0-9]{64}', recheck[key])
               for key in ('original_response_sha256', 'current_response_sha256', 'homepage_sha256')):
            raise ValueError('Invalid research source recheck hashes')
        matched, seen_claims = {}, set()
        for proof in recheck['evidence']:
            claim_id = proof['claim_id']
            pins = {pin['source_id'] for pin in claims.get(claim_id, {}).get('evidence', [])}
            pinned = {sid for sid in pins if sources[sid]['url'] == original}
            if not pinned or pinned != set(proof['source_ids']) or claim_id in seen_claims:
                raise ValueError('Research source recheck does not match approved evidence pins')
            if not proof['support_spans'] or any(
                    type(span['start']) is not int or type(span['end']) is not int
                    or not 0 <= span['start'] < span['end']
                    or not re.fullmatch(r'[a-f0-9]{64}', span['sha256']) for span in proof['support_spans']):
                raise ValueError('Invalid research source recheck support spans')
            for sid in pinned:
                matched.setdefault(sid, set()).add(claim_id)
            seen_claims.add(claim_id)
        if not matched or matched.keys() & by_source.keys() or any(
                sources[sid]['response_sha256'] != recheck['original_response_sha256'] for sid in matched):
            raise ValueError('Research source recheck does not match original evidence captures')
        for sid, claim_ids in matched.items():
            by_source[sid] = {'current_url': current, 'unavailable_on': observed['checked_on'], 'claim_ids': claim_ids}
    return by_source


def _company_websites(context):
    """Read current homepage links without changing the reviewed entities."""
    if not context.get('published_edition_replay') or context.get('root') is None:
        return {}
    path = Path(context['root']) / COMPANY_WEBSITES
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != '1.0.0' or not isinstance(data.get('entries'), list):
        raise ValueError('Invalid research company websites')
    if data['release_id'] != context['report']['release_id']:
        return {}
    checked = data['checked_on']
    if date.fromisoformat(checked).isoformat() != checked:
        raise ValueError('Invalid research company website check date')
    entities = _entities(context)
    claims = {row['id']: row for row in context['graph']['assertions'] if row['status'] == 'approved'}
    websites = {}
    for entry in data['entries']:
        eid, original, current = (entry[key] for key in ('entity_id', 'recorded_url', 'current_url'))
        entity = entities.get(eid, {})
        if (eid in websites or entity.get('status') != 'approved'
                or entity.get('identifiers', {}).get('website') != original
                or not _safe_url(original) or current == original or not _safe_url(current)
                or re.search(r'[\s\x00-\x1f]', current) or urlsplit(current).query or urlsplit(current).fragment
                or entry.get('language') not in ('en', 'zh')
                or not re.fullmatch(r'[a-f0-9]{64}', entry.get('response_sha256', ''))):
            raise ValueError(f'Invalid current website for {eid}')
        if not entry['evidence'] or any(
                (claim := claims.get(proof['claim_id'], {})).get('subject_id') != eid
                or not any(pin.get('source_id') == proof['source_id'] for pin in claim.get('evidence', []))
                for proof in entry['evidence']):
            raise ValueError(f'Current website for {eid} requires approved evidence for that entity')
        websites[eid] = {**entry, 'checked_on': checked}
    return websites


def _source_anchor_ids(root):
    """Read website-only public compatibility IDs, outside frozen research."""
    path = Path(root) / SOURCE_ANCHORS
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Public source anchor sidecar cannot be a symlink')
    if not path.exists():
        return []
    if not path.is_file():
        raise ValueError('Public source anchor sidecar must be a regular JSON file')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate public source anchor sidecar key')
            value[key] = item
        return value
    value = json.loads(path.read_bytes(), object_pairs_hook=unique)
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'provenance', 'source_ids', 'source_ids_sha256'}
            or value['schema_version'] != 'public-source-anchor-compatibility-v1'):
        raise ValueError('Invalid public source anchor sidecar')
    origin, ids = value['provenance'], value['source_ids']
    if (not isinstance(origin, dict) or set(origin) != {'source_commit', 'source_path', 'source_html_sha256'}
            or not re.fullmatch(r'[0-9a-f]{40}', str(origin.get('source_commit', '')))
            or origin.get('source_path') != 'dist/research/data/index.html'
            or not re.fullmatch(r'[0-9a-f]{64}', str(origin.get('source_html_sha256', '')))
            or not isinstance(ids, list) or any(not isinstance(sid, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,255}', sid) for sid in ids)
            or ids != sorted(set(ids))
            or value['source_ids_sha256'] != hashlib.sha256(
                (json.dumps(ids, ensure_ascii=False, separators=(',', ':')) + '\n').encode()).hexdigest()):
        raise ValueError('Invalid public source anchor provenance or identifiers')
    return ids


def _ledger_records(context):
    """Full record membership, including metadata-only retained corrections."""
    records = context.get('_render_ledger')
    if records is not None:
        return records
    assertions = {row['id']: row for row in context['graph']['assertions']}
    stubs = {}
    corrections = context.get('_render_corrections')
    if corrections is None:
        corrections = _correction_records(context)
    for row in corrections:
        if row['claim_id'] not in assertions:
            stubs.setdefault(row['claim_id'], row)
    retained_source_ids = {pin['source_id'] for row in assertions.values()
                           if row.get('status') in {'approved', 'historical'}
                           for pin in row.get('evidence', [])}
    sources = {row['id']: row if row['id'] in retained_source_ids else {'id': row['id'], '_withheld': True}
               for row in context['graph']['sources']}
    for sid in context.get('_render_source_anchor_ids', []):
        sources.setdefault(sid, {'id': sid, '_withheld': True, '_compatibility': True})
    return assertions, stubs, sources


def _retired_assertions(context, assertions, stubs):
    if not context.get('_legacy_current_bookmarks'):
        return set()
    return set(RETIRED_ASSERTION_IDS) - assertions.keys() - stubs.keys()


def _assertion_bookmark(stable_id, correction):
    return (f'<article class="r-assertion-stub" id="{sp.escape(_anchor("assertion", stable_id))}" '
            'tabindex="-1" data-record-scope="bookmark"><h3>Earlier public assertion identifier</h3>'
            '<p class="r-record-id">' + _link(_evidence_url('assertion', stable_id), stable_id) + '</p>'
            '<p>This identifier appeared in an earlier public ledger. The current ledger retains it as bookmark metadata.</p>'
            '<p class="r-meta">Historical site snapshot · 10 Nov 2026</p>'
            '<p>' + _link('/research/data/#assertions', 'Return to Research data') + '</p>' + correction + '</article>')


def _correction_stub(aid, row, correction):
    return ('<article class="r-assertion" id="' + sp.escape(_anchor('assertion', aid)) + '"><h3>'
        + sp.escape(aid) + '</h3><p>This historical identifier is retained as correction metadata. '
        'Its earlier finding text is outside this current evidence snapshot.</p><p>'
        + _link(_correction_url(row), 'Read the correction and supporting evidence')
        + (' · ' + _link(_evidence_url('assertion', row['replacement_claim_id']), 'Read the approved replacement')
           if row.get('replacement_claim_id') else '') + '</p>' + correction + '</article>')


def _ledger_parts(kind, ids, current=None):
    counts = {bucket: 0 for bucket in LEDGER_BUCKETS}
    for stable_id in ids:
        counts[_ledger_bucket(stable_id)] += 1
    return '<ol class="r-ledger-parts">' + ''.join(
        '<li><a href="' + _ledger_path(kind, bucket) + '"'
        + (' aria-current="page"' if current == bucket else '') + '>Part '
        + str(index + 1).zfill(2) + '<span class="r-meta"> · ' + str(counts[bucket])
        + (' identifiers' if kind == 'source' else ' records') + '</span></a></li>'
        for index, bucket in enumerate(LEDGER_BUCKETS)) + '</ol>'


def _ledger_pages(context, ledger_path='/research/data/'):
    """Thirty-two bounded static documents; no per-record pages or runtime API."""
    assertions, stubs, sources = _ledger_records(context)
    retired = _retired_assertions(context, assertions, stubs)
    rechecks = context.get('_render_source_rechecks', {}) if ledger_path == '/research/data/' else {}
    pages = []
    for kind, ids, label in (("assertion", sorted(assertions.keys() | stubs.keys() | retired), "Assertion"),
                             ("source", sorted(sources), "Source")):
        for index, bucket in enumerate(LEDGER_BUCKETS):
            selected = [stable_id for stable_id in ids if _ledger_bucket(stable_id) == bucket]
            title = label + " ledger · Part " + str(index + 1).zfill(2)
            description = ("Source records and retained traceability identifiers for this part of the versioned ledger."
                           if kind == 'source' else "Complete assertion records, precise evidence bindings and original review scope for this part of the versioned ledger.")
            withheld = sum(bool(sources[stable_id].get('_withheld')) for stable_id in selected) if kind == 'source' else 0
            membership = (str(len(selected)) + ' retained identifiers: ' + str(len(selected) - withheld)
                          + ' source records and ' + str(withheld) + ' withheld metadata placeholders. '
                          if withheld else str(len(selected)) + ' records. ')
            compatibility = sum(bool(sources[sid].get('_compatibility')) for sid in selected) if kind == 'source' else 0
            if compatibility:
                membership = (str(len(selected)) + ' retained identifiers: ' + str(len(selected) - withheld)
                              + ' source records, ' + str(withheld - compatibility) + ' withheld metadata placeholders and '
                              + str(compatibility) + ' earlier public identifiers. ')
            if kind == 'assertion' and (bookmarks := len(retired.intersection(selected))):
                membership = f'{len(selected) - bookmarks} records and {sp.plural(bookmarks, "earlier bookmark")}. '
            body = ('<header class="r-page-head"><p class="r-kicker">' + _status(context) + '</p><h1>'
                    + title + '</h1><p class="r-lede">' + membership +
                    'Read source bindings and review scope, use find in page, or print this complete part.</p>'
                    + _meta(context) + '<p>' + _link('/research/data/', 'All ledger parts, downloads & citations →') + '</p></header>'
                    '<nav class="r-ledger-nav" aria-label="' + label + ' ledger parts">'
                    + _ledger_parts(kind, ids, current=bucket) + '</nav>'
                    '<section class="r-section" aria-labelledby="records"><h2 id="records">' + label + ' records</h2>')
            for stable_id in selected:
                permalink = ledger_path + _evidence_url(kind, stable_id).removeprefix('/research/data/')
                correction = _record_correction(context, stable_id, permalink)
                if kind == 'source':
                    body += _source(sources[stable_id], correction, rechecks.get(stable_id))
                elif stable_id in assertions:
                    body += _assertion(context, assertions[stable_id], correction=correction)
                elif stable_id in stubs:
                    body += _correction_stub(stable_id, stubs[stable_id], correction)
                else:
                    body += _assertion_bookmark(stable_id, correction)
            if not selected:
                body += '<p>No records in this part of the ledger.</p>'
            body += '</section>'
            pages.append((_ledger_path(kind, bucket), title, description, body, 'CollectionPage', ('data', 'Data & sources')))
    return pages


def _legacy_ledger_aliases(assertions, stubs, sources, retired):
    # Only ID + native destination are retained at old root fragments. Scientific
    # wording, receipts, locators and source dossiers live on the bounded pages.
    return ('<div class="r-legacy-ledger-aliases">' + ''.join(
        '<a id="' + sp.escape(_anchor(kind, stable_id))
        + '" href="' + sp.escape(_evidence_url(kind, stable_id).removeprefix('/research/data/')) + '">'
        + sp.escape(('Open earlier assertion bookmark: ' if stable_id in retired else 'Open ' + kind + ' record: ') + stable_id)
        + '</a>' for kind, ids in (('assertion', sorted(assertions.keys() | stubs.keys() | retired)), ('source', sorted(sources)))
        for stable_id in ids) + '</div>')


def _deposit_file(record, filename, *, download=True):
    return record.rstrip('/') + '/files/' + quote(filename) + ('?download=1' if download else '')


def _edition_downloads(context, metadata, ledger_path, reuse_path):
    record = metadata['url']
    downloads = (
        ('research-archive.zip', 'Download edition ZIP', True),
        ('report.pdf', 'Download report PDF', True),
        ('MANIFEST.json', 'View edition checksums (JSON)', False),
    )
    members = (
        ('Research JSON', 'clean-dataset.json', ''),
        ('Research CSV', 'clean-dataset.csv', ''),
        ('Research SQLite and evidence tables', 'clean-dataset.sqlite', 'projection_rows'),
        ('Evidence graph JSON', 'source-context.json', 'graph'),
        ('Offline report', 'report.html', ''),
        ('Original reuse guide', 'REUSE.md', ''),
    )
    links = ''.join('<li>' + _link(_deposit_file(record, name, download=download), label) + '</li>'
                    for name, label, download in downloads)
    mirror = ''
    if context['report'].get('archive', {}).get('artifact_sha256') == EDITION_MIRROR_ARCHIVE_SHA256:
        mirror_links = ''.join('<li>' + _link(EDITION_MIRROR + name, label) + '</li>' for name, label in (
            ('research-archive.zip', 'Edition ZIP'),
            ('report.pdf', 'Report PDF'),
            ('MANIFEST.json', 'Edition checksums (JSON)'),
        ))
        mirror = f'<h3>Archived copy on GitHub</h3><ul class="r-downloads">{mirror_links}</ul>'
    files = ''.join(f'<li><strong>{label}</strong> <code>{name}</code>'
                    + (f' · <code>{unit}</code>' if unit else '') + '</li>' for label, name, unit in members)
    citations = ''.join(f'<li><a href="{sp.escape(ledger_path)}citations/{name}" download="{name}">{label}</a></li>'
                        for name, label in EDITION_CITATIONS.items())
    originals = ''.join(f'<li><code>{name}</code></li>' for name in EDITION_CITATIONS)
    reuse = ''
    if reuse_path and context['report']['release_id'] == 'research-2026-11-12.1':
        reuse = ('<p>The ' + _link(reuse_path, 'current reuse guide')
                 + ' corrects the Python example for <code>clean-dataset.json</code> to use <code>subject_id</code>.</p>')
    return (
        '<section class="r-section" aria-labelledby="downloads"><h2 id="downloads">Download the research</h2>'
        f'<ul class="r-downloads">{links}</ul>{mirror}<h3>Files inside the ZIP</h3>'
        f'<ul class="r-archive-members">{files}</ul>'
        + reuse +
        f'<p class="r-meta">Frozen evidence graph release <code>{sp.escape(context["graph"]["release_id"])}</code>.</p></section>'
        '<section class="r-section" id="citation"><h2>Cite and reproduce</h2>'
        f'<p>{sp.escape(metadata["author"])}. <cite>{sp.escape(metadata["title"])}</cite>. '
        f'{sp.escape(metadata["version"])}. {_date(metadata.get("published_on"))}.</p><p>'
        + _link('https://doi.org/' + metadata['doi'], 'Published edition DOI ' + metadata['doi']) + '</p>'
        '<p>Use these citations for the registered edition.</p>'
        f'<ul class="r-downloads">{citations}</ul><h3>Original citations in the ZIP</h3>'
        f'<p>The archive contains the citations prepared before DOI registration.</p><ul class="r-frozen-citations">{originals}</ul>'
        '<p>Reuse owned research under ' + _link(sp.DATA_LICENSE, 'CC BY 4.0')
        + '. Credit the publisher, release ID, original sources, and your changes. Source material retains its own rights and qualifications.</p></section>')


def _data(context, *, ledger_path='/research/data/', metadata=None, reuse_path='', download_sizes=None):
    graph, gate, report = context["graph"], context["gate"], context["report"]
    archive = report.get('archive', {})
    assertions, stubs, sources = _ledger_records(context)
    retired = _retired_assertions(context, assertions, stubs)
    rows = [("Privacy-filtered research JSON", "/publication/clean-dataset.json"), ("CSV", "/publication/clean-dataset.csv"),
            ("SQLite", "/publication/clean-dataset.sqlite"), ("Full evidence graph JSON · explicit statuses", "/research/exports/research-graph.json"),
            ("Evidence graph SQLite", "/research/exports/research-graph.sqlite"), ("Export checksums", "/research/exports/research-exports-manifest.json")]
    if 'publication/executive-brief.html' in context.get('publication_assets', []):
        rows.append(('Read the executive brief', '/publication/executive-brief.html'))
    if 'publication/report.pdf' in context.get('publication_assets', []):
        rows.append(('Read the report PDF', '/publication/report.pdf'))
    if 'publication/current-REUSE.md' in context.get('publication_assets', []):
        rows.append(('Working JSON and SQLite examples', '/publication/current-REUSE.md'))
        rows.append(('Original archived reuse guide', '/publication/REUSE.md'))
    elif 'publication/REUSE.md' in context.get('publication_assets', []):
        rows.append(('Working JSON and SQLite examples', '/publication/REUSE.md'))
    download_sizes = download_sizes or {}
    links = []
    for label, url in rows:
        if url in DATA_JSON_DOWNLOADS:
            size = download_sizes.get(url)
            if size is not None:
                label += f' ({size / 1_000_000:.1f} MB)'
            link = f'<a href="{sp.escape(url)}" download>{sp.escape(label)}</a>'
        elif url == '/publication/report.pdf' and _has_pre_registration_report(archive):
            link = (_link(url, f'Read the archived report PDF ({report["release_id"]})')
                    + '. The cover was prepared before DOI registration.')
        else:
            link = _link(url, label)
        links.append(f'<li>{link}</li>')
    citation_prefix = 'current-' if gate.get('ready') and archive.get('status') == 'published' else ''
    cite = "".join('<li>' + _link('/publication/' + citation_prefix + name, label) + '</li>' for name, label in
                   (("citation.bib", "BibTeX"), ("citation.ris", "RIS"), ("citation.csl.json", "CSL JSON"), ("CITATION.cff", "CITATION.cff")))
    other = [e for e in graph["entities"] if not _category(e)]
    entity_rows = "".join(
        f'<li id="{sp.escape(_anchor("entity", e["id"]))}">{_link(entity_url(e, context), e["name"])} '
        f'<span class="r-meta">{sp.escape(_label(e))} · {sp.escape(e["id"])}</span>'
        + _record_correction(context, e['id'], ledger_path + '#' + _token(_anchor('entity', e['id'])), e['name'])
        + '</li>' for e in sorted(other, key=lambda e: (e["name"].casefold(), e["id"])))
    if metadata and metadata.get('doi'):
        download_citation = _edition_downloads(context, metadata, ledger_path, reuse_path)
    else:
        doi = publication_metadata(context).get('doi')
        version_label = 'Evidence data version' if ledger_path == '/research/data/' else 'Research release'
        download_citation = (
            '<section class="r-section" aria-labelledby="downloads"><h2 id="downloads">Download the research</h2>'
            '<p>Downloads keep each record’s review status and source notes. Historical records reflect earlier reviews. '
            f'The separate company dataset remains at version {sp.escape(graph.get("canonical_dataset_version"))}.</p>'
            '<ul class="r-downloads">' + ''.join(links) + '</ul>'
            f'<p class="r-meta">{version_label}: {sp.escape(graph["release_id"])}.</p></section>'
            '<section class="r-section" id="citation"><h2>Cite and reproduce</h2>'
            f'<p>{sp.escape(context["identity"].get("publisher", {}).get("name", sp.PUBLISHER_NAME))}. <cite>{sp.escape(report["title"])}</cite>. '
            f'{sp.escape(report["release_id"])}. {_date(report["updated_on"])}.</p>'
            + ('' if gate.get("ready") and report.get("status") == "published" else '<p>Prepublication research snapshot. No published edition, permanent archive, or DOI is claimed.</p>')
            + ('<p>' + _link('https://doi.org/' + doi, 'Registered version DOI ' + doi) + '</p>' if doi else '')
            + f'<ul class="r-downloads">{cite}</ul><p>Reuse owned research under '
            + _link(sp.DATA_LICENSE, "CC BY 4.0") + '. Credit the publisher, release ID, original sources, and your changes. '
            'Source material retains its own rights and qualifications.</p>'
            f'<ul class="r-downloads"><li>{_link("/publication/research-archive.zip", "Download the reproduction package")}</li>'
            f'<li>{_link("/publication/MANIFEST.json", "Package SHA-256 inventory")}</li>'
            f'<li>{_link("/publication/package-status.json", "Archive & mirror status")}</li></ul></section>')
    coverage = (_progress(context) + f'<p>{sp.escape(_counts(context))}.</p>'
            '<p>The frozen eligible core and two separate 200-record quality audits must also pass. The reference audit requires '
            '98% precision and 95% recall, with no critical false attribution. The screening audit must recover at least 190 records '
            'and reach 90% recall in each major stratum.</p>' + _holds(context))
    if metadata:
        intro = (f'<header class="r-page-head"><p class="r-kicker">{_status(context)}</p><h1>Open data.<br>Visible evidence.</h1>'
                 '<p class="r-lede">Inspect what is supported, what is inherited, and what still needs review. '
                 'Research counts come from the versioned evidence graph; earlier public identifiers are labeled separately.</p>' + _meta(context) + '</header>'
                 + operating_status_notice(context)
                 + '<section class="r-section" aria-labelledby="coverage"><h2 id="coverage">Progress toward publication</h2>'
                 + coverage + '</section>' + download_citation)
    else:
        intro = ('<header class="r-page-head"><h1>Research data and sources</h1>'
                 '<p class="r-lede">Download the data or look up a finding and its sources.</p></header>'
                 + download_citation
                 + operating_status_notice(context)
                 + '<details class="r-section r-disclosure" id="coverage"><summary>Publication checks and coverage</summary>'
                 + _meta(context) + coverage + '</details>')
    return (intro +
            '<section class="r-section" aria-labelledby="assertions"><h2 id="assertions">Assertion records</h2>'
            '<p id="approved">Approved assertions retain their exact source bindings and review receipts.</p>'
            + ('' if any(row.get('status') == 'approved' for row in assertions.values()) else
               '<p class="r-callout">No new assertions have completed the required separate reviews. Candidate evidence stays outside approved findings and coverage totals.</p>')
            + '<p id="historical">Historical baseline descriptions keep their original snapshot dates and inherited provenance.</p>'
            '<p id="candidates">Candidates and retained correction identifiers carry metadata only while their original wording remains withheld.</p>'
            + ('<p class="r-meta">Earlier assertion bookmarks lead to metadata entries in their original ledger parts.</p>' if retired else '')
            + _ledger_parts('assertion', sorted(assertions.keys() | stubs.keys() | retired))
            + '</section><section class="r-section" aria-labelledby="sources"><h2 id="sources">Source records</h2>'
            '<p>A source capture records retrieval. Assertion-specific review is recorded separately.</p>'
            + ('<p>' + str(sum(not row.get('_withheld') for row in sources.values()))
               + ' source records and ' + str(sum(bool(row.get('_compatibility')) for row in sources.values()))
               + ' earlier public identifiers retained without source metadata. These placeholders add no evidence or coverage.</p>'
               if any(row.get('_compatibility') for row in sources.values()) else '')
            + _ledger_parts('source', sources)
            + '</section><section class="r-section" aria-labelledby="organizations"><h2 id="organizations">Organizations & other entities</h2>'
            + f'<ul class="r-entity-register">{entity_rows}</ul></section>'
            + _legacy_ledger_aliases(assertions, stubs, sources, retired))


def _entity_card(context, entity):
    approved = _assertions(context, entity)
    summary = ('<p>' + _claim_text(context, approved[0]) + '</p>') if approved else '<p>Metadata record. Findings await the required source reviews.</p>'
    return (f'<li class="r-entity-card"><div><p class="r-kicker">{sp.escape(_label(entity))}</p>'
            f'<h2>{_link(entity_url(entity, context), entity["name"])}</h2>{summary}'
            f'<p class="r-meta">{len(approved)} approved assertions · Review depth: {sp.escape(entity.get("review_depth", "").replace("_", " "))}</p></div>'
            f'{_link(entity_url(entity, context), "Inspect record →", "r-text-link")}</li>')


def _index_values(entity):
    taxonomy = entity.get('taxonomy', {})
    values = {'status': [entity.get('status', 'unknown')], 'type': [entity.get('kind', 'unknown')]}
    for facet in INDEX_FACETS:
        items = taxonomy.get(facet, [])
        values[facet] = sorted({value for value in items if isinstance(value, str)}) if isinstance(items, list) else []
    return values


def _search_identifiers(entity):
    if entity['kind'] not in {'paper', 'paper_work', 'paper_version'}:
        return []
    identifiers = entity.get('identifiers', {})
    return [entity['id'], *(identifiers[key] for key in ('arxiv', 'arxiv_version', 'doi', 'doi_version')
                            if isinstance(identifiers.get(key), str) and identifiers[key])]


def _catalog_label(entity, claims):
    if entity.get('status') == 'approved' and not claims:
        return 'Approved metadata'
    return _label(entity)


def _pinned_dataset_link(context, entity):
    if entity['id'] != 'dataset.fineweb-edu':
        return ''
    pinned = _entities(context).get('dataset.fineweb-edu.paper-2406.17557v2')
    return (_link(entity_url(pinned, context) + '#approved-findings', 'Findings on pinned release 2406.17557v2')
            if pinned and _approved_entity(context, pinned) else '')


def _index_row(context, entity):
    """One independently filterable record, including all native evidence links."""
    filters = _index_values(entity)
    claims = _assertions(context, entity)
    search = ' '.join([entity['name'], _display_title(entity['name']), entity['id']]
                      + entity.get('aliases', [])
                      + [str(value) for value in entity.get('identifiers', {}).values()])
    taxonomy = '; '.join(key.replace('_', ' ') + ': ' + ', '.join(filters[key])
                         for key in INDEX_FACETS if filters[key])
    identifiers = _search_identifiers(entity)
    identity_attr = ' data-search-identifiers="' + sp.escape(json.dumps(identifiers)) + '"' if identifiers else ''
    label = _catalog_label(entity, claims)
    depth = '' if label == 'Approved metadata' else entity.get('review_depth', '').replace('_', ' ')
    return ('<tr data-index-row data-record-id="' + sp.escape(entity['id'])
            + '" data-search="' + sp.escape(search.lower()) + '" data-filters="'
            + sp.escape(json.dumps(filters, ensure_ascii=False, separators=(',', ':'))) + '"' + identity_attr + '>'
            + '<th scope="row">' + _link(entity_url(entity, context), _display_title(entity['name']))
            + '<span class="r-record-id">' + sp.escape(entity['id']) + '</span></th>'
            + '<td data-label="Review">' + sp.escape(label) + '<span class="r-table-note">'
            + sp.escape(depth) + '</span></td>'
            + '<td data-label="Type">' + sp.escape(entity['kind'].replace('_', ' ')) + '</td>'
            + '<td data-label="Taxonomy">' + sp.escape(taxonomy or 'Not recorded') + '</td>'
            + '<td data-label="Evidence">' + _link(entity_url(entity, context) + '#approved-findings',
                                                    sp.plural(len(claims), 'approved assertion'))
            + '</td></tr>')


def _index_head():
    return ('<thead><tr><th scope="col">Record</th><th scope="col">Review</th>'
            '<th scope="col">Type</th><th scope="col">Taxonomy</th><th scope="col">Evidence</th></tr></thead>')


def _paper_rows(context, entities):
    """Versions sit in sibling nonrecord wrappers, never below a hidden work row."""
    works = [entity for entity in entities if entity['kind'] != 'paper_version']
    work_ids = {entity['id'] for entity in works}
    versions = {}
    for entity in entities:
        if entity['kind'] == 'paper_version':
            versions.setdefault(entity.get('parent_id'), []).append(entity)
    rows = []
    for work in works:
        rows.append(_index_row(context, work))
        children = versions.get(work['id'], [])
        if not children:
            continue
        title = _display_title(work['name'])
        rows.append('<tr class="r-version-row" data-index-versions data-parent-record="'
                    + sp.escape(work['id']) + '"><td colspan="5"><details class="r-paper-versions">'
                    '<summary>Source versions (' + str(len(children)) + ') <span>Work context: '
                    + sp.escape(title) + ' · ' + sp.escape(_label(work)) + '</span></summary>'
                    '<p class="r-version-context" data-index-context hidden>Work context only; not counted as a match: '
                    + _link(entity_url(work, context), title) + ' · ' + sp.escape(_label(work)) + '.</p>'
                    '<table class="r-evidence-table r-version-table"><caption>Source versions for '
                    + sp.escape(title) + '. Each version retains its own review status.</caption>'
                    + _index_head() + '<tbody>' + ''.join(_index_row(context, child) for child in children)
                    + '</tbody></table></details></td></tr>')
    # Preserve an unexpected standalone version instead of silently dropping it.
    rows.extend(_index_row(context, entity) for entity in entities
                if entity['kind'] == 'paper_version' and entity.get('parent_id') not in work_ids)
    return ''.join(rows)


def _evidence_table(context, entities, *, group_papers=False):
    """Complete metadata in HTML; optional controls only change the presentation."""
    values = [_index_values(entity) for entity in entities]
    def select(key):
        options = sorted({value for row in values for value in row[key]}, key=lambda value: (value.casefold(), value))
        if not options:
            return ''
        label = {'status': 'Review status', 'type': 'Record type'}.get(key, key.replace('_', ' ').capitalize())
        html = f'<label>{label}<select name="{key}"><option value="">All</option>' + ''.join(
            f'<option value="{sp.escape(value)}">{sp.escape(value.replace("_", " "))}</option>' for value in options)
        if any(not row[key] for row in values):
            html += '<option value="__not_recorded__">Not recorded</option>'
        return html + '</select></label>'
    advanced = ''.join(select(key) for key in ('type',) + INDEX_FACETS)
    controls = ('<form class="r-index-controls" data-index-controls hidden role="search" aria-label="Filter research records">'
                '<div class="r-index-primary"><label>Search records<input name="q" type="search" autocomplete="off" placeholder="Title or identifier"></label>'
                + select('status') + '<button type="reset">Clear filters</button></div>'
                + ('<details class="r-index-advanced" data-index-advanced><summary>More filters '
                   '<span data-index-advanced-count>0 active</span></summary><div class="r-index-fields">'
                   + advanced + '</div></details>' if advanced else '') + '</form>')
    works = sum(entity['kind'] != 'paper_version' for entity in entities)
    initial_count = (f'{works} paper works · {len(entities) - works} source versions ({len(entities)} records)'
                     if group_papers else f'{len(entities)} records')
    work_search = '<p data-index-work hidden><a href="/work/">Search paid work for this query</a></p>' if group_papers else ''
    if group_papers and context.get('work_search_titles'):
        work_search += ('<script type="application/json" data-index-work-titles>'
                        + json.dumps(context['work_search_titles'], ensure_ascii=False).replace('<', '\\u003c') + '</script>')
    return ('<section data-research-index' + (' data-index-kind="papers"' if group_papers else '') + '>' + controls
            + f'<p class="r-meta" data-index-count role="status" aria-live="polite" aria-atomic="true">{initial_count}</p>'
            + work_search
            + '<div class="r-table-wrap"><table class="r-evidence-table"><caption>Evidence records. Taxonomy on candidate records is provisional.</caption>'
            + _index_head() + '<tbody>'
            + (_paper_rows(context, entities) if group_papers else ''.join(_index_row(context, entity) for entity in entities))
            + '</tbody></table></div><p data-index-empty class="r-callout" hidden>No records match these filters. Clear filters to see all records.</p></section>')


def _index(context, category):
    slug, title, kinds, description = category
    entities = sorted((e for e in context["graph"]["entities"] if e.get("kind") in kinds),
                      key=lambda e: (not _approved_entity(context, e), e["name"].casefold(), e["id"]))
    approved = sum(e.get('status') == 'approved' for e in entities)
    supported = sum(_approved_entity(context, e) for e in entities)
    candidates = sum(e.get("status") == "candidate" for e in entities)
    review_summary = f'{approved} approved records · {candidates} candidate records'
    if slug == 'datasets':
        review_summary = (f'{len(entities)} records · {approved} approved catalog records · '
                          f'{supported} records with approved assertions · {candidates} candidate records')
    elif slug == 'papers':
        approved_works = sum(e['kind'] != 'paper_version' and e.get('status') == 'approved' for e in entities)
        candidate_works = sum(e['kind'] != 'paper_version' and e.get('status') == 'candidate' for e in entities)
        report_works = context['gate'].get('coverage', {}).get('reviewed_papers', 0)
        review_summary = (f'{approved_works} approved paper works · {approved - approved_works} approved source versions'
                          f' · {report_works} works meet the report’s source-review standard'
                          f' · {candidate_works} candidate works and {candidates - candidate_works} candidate source versions')
    return (f'<header class="r-page-head"><p class="r-kicker">Research evidence index</p><h1>{title}</h1>'
            f'<p class="r-lede">{sp.escape(description)}</p><p class="r-status">{review_summary}</p>' + _meta(context) + '</header>'
            '<p class="r-callout">Candidate records help readers inspect the research queue. They are not reviewed findings, '
            'endorsements, or proof of a supplier contribution.</p>'
            + (_evidence_table(context, entities, group_papers=slug == "papers") if entities else
               '<section class="r-section"><h2>How this index will be built</h2><p>No records have entered this index yet. '
               'A workflow must identify its inputs, work stages, output artifact, qualifications, and version-specific source evidence. '
               'Separate source verification and adversarial review precede approval.</p>'
               + _link(REPORT_PATH, 'Read the evidence standard →', 'r-text-link') + '</section>'))


def _company_highlight(context, entity, approved, sources):
    reviews = {row['id']: row for row in context['graph'].get('reviews', [])}
    for claim in approved:
        if claim.get('subject_id') != entity['id'] or not (structured := _structured_claim_value(claim)):
            continue
        statement = structured['statement']
        if len(statement) > 220:
            continue
        review_day = next((_day(review['reviewed_on']) for rid in claim.get('review_ids', [])
                           if (review := reviews.get(rid, {})).get('role') == 'source_verifier'
                           and review.get('verdict') == 'pass' and review.get('reviewed_on')), '')
        source_id, source = next(((pin['source_id'], url) for pin in claim.get('evidence', [])
                                  if (url := _safe_url(sources.get(pin['source_id'], {}).get('url')))), ('', ''))
        if not review_day or not source:
            continue
        statement = statement.removeprefix(entity['name'] + ' ')
        if (claim['id'] == 'candidate.cohort3.humans_in_the_loop.annotation-trial'
                and statement.casefold() == 'describes a two-hour annotation trial on sample data and instructions before final guideline and setup adjustments.'):
            statement = 'Describes a two-hour annotation trial on sample data.'
        recheck = context.get('_render_source_rechecks', {}).get(source_id, {})
        notice = _source_recheck_notice(recheck) if claim['id'] in recheck.get('claim_ids', ()) else ''
        return ('<div class="company-review-highlight"><p class="company-review-finding">'
                + sp.escape(statement[0].upper() + statement[1:])
                + '<span class="company-review-context">' + _link(source, 'Original source')
                + (f' · {notice}' if notice else '')
                + f' · Evidence reviewed <time datetime="{sp.escape(review_day)}">{_date(review_day)}</time></span></p>'
                '<p class="company-actions company-review-actions">'
                + _link('#' + _token(_anchor('assertion', claim['id'])), 'Read finding') + '</p></div>')
    return ''


def _company_detail(context, entity):
    """A compact company view over the complete, unchanged research records."""
    approved, historical = _assertions(context, entity), _assertions(context, entity, ("historical",))
    linked = [a for a in context["graph"]["assertions"] if entity["id"] in {a.get("subject_id"), a.get("object_id")}]
    _, _, sources = _ledger_records(context)
    source_ids = sorted({item["source_id"] for a in linked for item in a.get("evidence", [])})
    current = context.get('_render_company_websites', {}).get(entity['id'])
    identifiers = ''.join(
        f'<dt>Recorded website</dt><dd>{_link(value, value)}</dd>' if current and key == 'website'
        else f'<dt>{sp.escape(key)}</dt><dd>{sp.escape(value)}</dd>'
        for key, value in sorted(entity.get('identifiers', {}).items()))
    taxonomy = "".join(f'<dt>{sp.escape(key.replace("_", " ").capitalize())}</dt><dd>{sp.escape(", ".join(values))}</dd>'
                       for key, values in sorted(entity.get("taxonomy", {}).items()) if values)
    website = current['current_url'] if current else _safe_url(entity.get('identifiers', {}).get('website'))
    website_label = 'Website (Chinese)' if current and current['language'] == 'zh' else 'Website'
    website_review = ('<p class="r-meta">Current website checked ' + _date(current['checked_on']) + ' · '
                      + _link(_evidence_url('assertion', current['evidence'][0]['claim_id']), 'Identity evidence') + '</p>') if current else ''
    highlight = _company_highlight(context, entity, approved, sources)
    body = ['<article class="company-dossier research-company-dossier"><header class="company-hero">'
            '<div class="company-name"><h1>' + sp.escape(entity["name"]) + '</h1></div>'
            + highlight + '<p class="company-research-snapshot">' + sp.plural(len(approved), "approved finding")
            + ' · ' + sp.plural(len(source_ids), "source record") + '</p>'
            + ('<p class="company-actions">' + _link(website, website_label) + '</p>' if website else '')
            + '</header><div class="company-record">',
            '<details class="company-fold" id="company-scope"><summary>Company and review scope</summary>'
            '<div class="company-fold-body"><p class="r-kicker">' + sp.escape(_label(entity)) + '</p>'
            '<p class="r-record-id">' + sp.escape(entity["id"]) + '</p>' + _meta(context)
            + '<h2>Evidence & scope</h2><p>' + sp.escape(entity.get("disposition_reason"))
            + '</p><dl class="r-facts"><dt>Review depth</dt><dd>'
            + sp.escape(entity.get("review_depth", "").replace("_", " "))
            + '</dd><dt>Disposition</dt><dd>' + sp.escape(entity.get("disposition")) + '</dd>'
            + identifiers + '</dl>' + website_review + '<h2>Read this record carefully</h2>'
            '<p>Approval applies to a specific assertion and its qualifications. It does not imply provider endorsement, '
            'commercial quality, or a contribution to another artifact.</p>'
            + ('<h3>Recorded taxonomy</h3><p class="r-meta">Candidate taxonomy remains provisional.</p><dl class="r-facts">' + taxonomy + '</dl>' if taxonomy else '')
            + _record_correction(context, entity['id'], entity_url(entity, context), entity['name']) + '</div></details>',
            '<details class="company-fold" id="approved-findings"><summary>Findings</summary>'
            '<div class="company-fold-body"><h2>Approved findings</h2>'
            + ("".join(_assertion(context, a, focusable=True) for a in approved) if approved else
               '<p class="r-callout">No approved assertions are available for this record. Source metadata and candidate proposals do not establish a finding.</p>')
            + '</div></details>']
    if historical:
        body.append('<details class="company-fold" id="company-history"><summary>Historical evidence</summary>'
                    '<div class="company-fold-body"><h2>Historical evidence</h2>'
                    + "".join(_assertion(context, a) for a in historical) + '</div></details>')
    body.append('<details class="company-fold" id="company-sources"><summary>Sources</summary>'
                '<div class="company-fold-body"><h2>Connected evidence</h2>'
                + ('<ul class="r-evidence-links">' + "".join('<li>' + _link(_evidence_url("source", sid), ("Source metadata withheld · " + sid) if sources.get(sid, {}).get("_withheld") else sources.get(sid, {}).get("title", sid)) + '</li>' for sid in source_ids) + '</ul>'
                   if source_ids else '<p>No source records are attached yet.</p>')
                + '</div></details></div></article>')
    return "".join(body)


def _detail(context, entity):
    if not entity.get('legacy_id') and entity_url(entity, context).startswith('/company/'):
        return _company_detail(context, entity)
    approved, historical = _assertions(context, entity), _assertions(context, entity, ("historical",))
    linked = [a for a in context["graph"]["assertions"] if entity["id"] in {a.get("subject_id"), a.get("object_id")}]
    _, _, sources = _ledger_records(context)
    source_ids = sorted({item["source_id"] for a in linked for item in a.get("evidence", [])})
    identifiers = "".join(f'<dt>{sp.escape(key)}</dt><dd>{_record_identifier(key, value)}</dd>'
                          for key, value in sorted(entity.get("identifiers", {}).items()))
    taxonomy = "".join(f'<dt>{sp.escape(key.replace("_", " ").capitalize())}</dt><dd>{sp.escape(", ".join(values))}</dd>'
                       for key, values in sorted(entity.get("taxonomy", {}).items()) if values)
    title = _display_title(entity["name"])
    pinned = _pinned_dataset_link(context, entity)
    return (f'<header class="r-page-head"><p class="r-kicker">{sp.escape(_catalog_label(entity, approved))}</p><h1 class="r-record-title">{sp.escape(title)}</h1>'
            f'<p class="r-record-id">{sp.escape(entity["id"])}</p>' + _meta(context) + '</header>'
            '<div class="r-detail-layout"><div><section class="r-section"><h2>Evidence & scope</h2>'
            f'<p>{sp.escape(entity.get("disposition_reason"))}</p><dl class="r-facts"><dt>Review depth</dt>'
            f'<dd>{sp.escape(entity.get("review_depth", "").replace("_", " "))}</dd><dt>Disposition</dt><dd>{sp.escape(entity.get("disposition"))}</dd>'
            + identifiers + '</dl></section><section class="r-section" id="approved-findings"><h2>Approved findings</h2>'
            + ("".join(_assertion(context, a) for a in approved) if approved else
               '<p class="r-callout">No approved assertions are available for this record.</p>')
            + (f'<p>{pinned}</p>' if pinned else '')
            + '</section>'
            + ('<section class="r-section"><h2>Historical evidence</h2>' + "".join(_assertion(context, a) for a in historical) + '</section>' if historical else '')
            + '<section class="r-section"><h2>Connected evidence</h2>'
            + ('<ul class="r-evidence-links">' + "".join('<li>' + _link(_evidence_url("source", sid), ("Source metadata withheld · " + sid) if sources.get(sid, {}).get("_withheld") else sources.get(sid, {}).get("title", sid)) + '</li>' for sid in source_ids) + '</ul>'
               if source_ids else '<p>No source records are attached yet.</p>')
            + '</section></div><aside class="r-detail-aside">'
            + _record_correction(context, entity['id'], entity_url(entity, context), title)
            + '<h2>Read this record carefully</h2>'
            '<p>Approval applies to a specific assertion and its qualifications. It does not imply provider endorsement, '
            'commercial quality, or a contribution to another artifact.</p>'
            + ('<h3>Recorded taxonomy</h3><p class="r-meta">Candidate taxonomy remains provisional.</p><dl class="r-facts">' + taxonomy + '</dl>' if taxonomy else '')
            + '</aside></div>')


def _record_identifier(key, value):
    if key in {'doi', 'doi_version'} and re.fullmatch(r'10\.\d{4,9}/\S+', str(value)):
        return _link('https://doi.org/' + quote(value, safe='/'), value)
    if key in {'arxiv', 'arxiv_version'} and re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?', str(value), re.I):
        return _link('https://arxiv.org/abs/' + quote(value, safe='/'), value)
    return sp.escape(value)


def _issue_endpoint(identity):
    return identity.get('contacts', {}).get(
        'issues', identity.get('repository', {}).get('url', '') + '/issues/new/choose').removesuffix('/choose')


def _record_correction(context, stable_id, path, title=''):
    edition = context['report']['release_id']
    permalink = sp.ORIGIN + path
    subject = f'ScienceToStartup correction · {stable_id}'
    lines = [f'Edition: {edition}', f'Stable record ID: {stable_id}', f'Record URL: {permalink}']
    target = [edition, stable_id, permalink]
    contact_params = {'correction': stable_id, 'edition': edition, 'record': path}
    if title:
        title = ' '.join(title.splitlines())
        lines.append(f'Record: {title}')
        target.append(title)
        contact_params['title'] = title
    lines += ['What should change:', 'Supporting public evidence:', '']
    message = '\n'.join(lines)
    contact = '/method/?' + urlencode(contact_params, quote_via=quote) + '#corrections'
    issue = _issue_endpoint(context['identity']) + '?' + urlencode(
        {'template': 'correction.yml', 'target': ' · '.join(target)}, quote_via=quote)
    return ('<details class="r-record-correction"><summary>Request a correction</summary>'
            '<p>' + _link(contact, 'Continue to private email') + '</p>'
            '<noscript><p>Copy the draft below before continuing to email.</p></noscript>'
            '<details class="r-correction-draft"><summary>Copy the email draft</summary>'
            f'<label>Subject<input type="text" value="{sp.escape(subject)}" readonly></label>'
            f'<label>Message<textarea rows="8" readonly>{sp.escape(message)}</textarea></label>'
            '</details><p>' + _link(issue, 'Start a public GitHub correction') + ' · GitHub requires sign-in.</p></details>')


def _review(context):
    identity = context["identity"]
    new_issue = _issue_endpoint(identity)
    return ('<header class="r-page-head"><h1>Review the research</h1>' + _meta(context) + '</header>'
            '<div class="r-browse-grid r-review-grid"><article class="r-browse-card">'
            '<h2>Correct a record</h2><p>Include its record ID, the source version and page or section, the proposed wording, '
            'and the reason. Source and review dates are preserved when a correction is accepted.</p>'
            + _link(new_issue + '?template=correction.yml', 'Submit a correction →', 'r-text-link')
            + '<p>' + _link('/method/#corrections', 'Continue to private email') + '</p></article>'
            '<article class="r-browse-card"><h2>Review a chapter</h2>'
            '<p>Name the report release and chapter. Check the source support, alternatives, missing evidence, and practical '
            'implications. State relevant interests and whether scoped public credit is permitted.</p>'
            + _link(new_issue + '?template=section-review.yml', 'Contribute a review →', 'r-text-link') + '</article>'
            '<article class="r-browse-card"><h2>Share how you used the data</h2>'
            '<p>Link a public artifact and explain which release, data, or methods you used. A visit, download, or repository star '
            'is an activity measure, not evidence of adoption.</p>'
            + _link(new_issue + '?template=reuse.yml', 'Report a public reuse →', 'r-text-link') + '</article></div>'
            '<section class="r-section r-prose"><h2>What review means here</h2>'
            '<p>New evidence requires separate author, source-verifier, and adversarial AI review invocations. '
            'An automated review is labeled as AI review. It does not imply human expert review or external endorsement.</p>'
            '<p>External contributions are voluntary. Public credit requires consent and states the actual edition, section, '
            'and contribution. We do not infer affiliation or employer endorsement from a contribution. No external review '
            'is claimed without an actual receipt.</p><p>External participation is not a release requirement. The same evidence, '
            'coverage, and quality requirements apply to every record.</p></section>'
            '<section class="r-section r-prose"><h2>Accepted corrections</h2><p>'
            + _link(CORRECTIONS_PATH, 'Inspect the correction log') + ' or subscribe with '
            + _link(CORRECTIONS_PATH + 'feed.xml', 'RSS') + ' or '
            + _link(CORRECTIONS_PATH + 'atom.xml', 'Atom') + '.</p></section>'
            '<section class="r-section r-prose"><h2>Publisher & interests</h2><p>Published by '
            + _link(identity.get("publisher", {}).get("url"), identity.get("publisher", {}).get("name", sp.PUBLISHER_NAME)) + '.</p>'
            + "".join(f'<p>{sp.escape(line)}</p>' for line in identity.get("disclosures", [])) + '</section>')


def _published_editions(context):
    """Recompute each archived publication gate; an asserted ready flag is insufficient.

    Edition entries identify a release_id. An immutable older edition supplies
    its graph, report and policy snapshots; a current entry may refer to the
    current context. No route or feed item is created for an incomplete record.
    """
    from research_report import publication_gate
    from research_edition_replay import edition_entries

    editions, seen = [], set()
    for entry in edition_entries(context):
        if not isinstance(entry, dict) or entry.get("status") != "published":
            continue
        rid = entry.get("release_id")
        if not rid or rid in seen:
            continue
        persisted = context.get('edition_snapshots', {}).get(rid, {})
        snapshot = {key: persisted.get(key, entry.get(key, context[key])) for key in ("graph", "report", "policy", "identity")}
        if persisted.get('published_edition_replay') is not None:
            from research_edition_replay import read_replay_package
            # This separate reader rechecks trusted source pins and the actual
            # receipt. A projected graph never runs a fake fresh-input gate.
            read_replay_package(persisted)
            snapshot = dict(persisted)
            gate = snapshot['gate']
        else:
            try:
                gate = publication_gate(snapshot["graph"], snapshot["report"], snapshot["policy"])
            except (ValueError, KeyError, TypeError):
                continue
        if snapshot["report"].get("release_id") != rid or snapshot["report"].get("status") not in {"published", "superseded"}:
            continue
        if not gate.get("ready"):
            continue
        snapshot["gate"] = gate
        edition_date = snapshot['report'].get('edition_date')
        if not edition_date:
            try:
                cutoff = datetime.fromisoformat(snapshot['report']['source_cutoff'].replace('Z', '+00:00'))
                edition_date = (cutoff.astimezone(ZoneInfo('America/Los_Angeles')).date() + timedelta(days=3)).isoformat()
            except (ValueError, KeyError, TypeError):
                continue
        try:
            if (datetime.fromisoformat(edition_date).weekday() != 0
                    and snapshot['report'].get('edition_kind', 'weekly') != 'launch'):
                continue
        except (ValueError, TypeError):
            continue
        revision = entry.get('revision', 1)
        if type(revision) is not int or revision < 1:
            continue
        path = '/research/editions/' + edition_date + ('.r' + str(revision) if revision > 1 else '') + '/'
        if any(existing == path for existing, _ in editions):
            raise ValueError('Published editions cannot share an immutable URL')
        editions.append((path, snapshot))
        seen.add(rid)
    return sorted(editions, key=lambda row: (row[1]["report"]["updated_on"], row[0]), reverse=True)


def _feeds(output, context, editions):
    rss = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(rss, 'channel')
    for key, text in (("title", "ScienceToStartup published research"), ("link", sp.ORIGIN + '/research/'),
                      ("description", "Actual published research editions. Prelaunch preparation does not create feed items.")):
        ET.SubElement(channel, key).text = text
    ns = 'http://www.w3.org/2005/Atom'
    ET.register_namespace('', ns)
    atom = ET.Element('{' + ns + '}feed')
    ET.SubElement(atom, '{' + ns + '}title').text = 'ScienceToStartup published research'
    ET.SubElement(atom, '{' + ns + '}id').text = sp.ORIGIN + '/research/'
    ET.SubElement(atom, '{' + ns + '}link', {'href': sp.ORIGIN + '/research/atom.xml', 'rel': 'self'})
    author = ET.SubElement(atom, '{' + ns + '}author')
    ET.SubElement(author, '{' + ns + '}name').text = context['identity'].get('publisher', {}).get('name', sp.PUBLISHER_NAME)
    ET.SubElement(author, '{' + ns + '}uri').text = context['identity'].get('publisher', {}).get('url', sp.ORIGIN + '/method/#about')
    newest = max([context['report']['updated_on']] + [snapshot['report']['updated_on'] for _, snapshot in editions])
    ET.SubElement(atom, '{' + ns + '}updated').text = newest + 'T00:00:00Z'
    for path, snapshot in editions:
        report = snapshot['report']
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = report['title'] + ' · ' + report['release_id']
        ET.SubElement(item, 'link').text = sp.ORIGIN + path
        ET.SubElement(item, 'guid', {'isPermaLink': 'true'}).text = sp.ORIGIN + path
        ET.SubElement(item, 'description').text = report.get('summary', '')
        entry = ET.SubElement(atom, '{' + ns + '}entry')
        ET.SubElement(entry, '{' + ns + '}title').text = report['title'] + ' · ' + report['release_id']
        ET.SubElement(entry, '{' + ns + '}id').text = sp.ORIGIN + path
        ET.SubElement(entry, '{' + ns + '}link', {'href': sp.ORIGIN + path})
        ET.SubElement(entry, '{' + ns + '}updated').text = report['updated_on'] + 'T00:00:00Z'
        ET.SubElement(entry, '{' + ns + '}summary').text = report.get('summary', '')
    for name, tree in (("feed.xml", rss), ("atom.xml", atom)):
        (output / 'research' / name).write_bytes(ET.tostring(tree, encoding='utf-8', xml_declaration=True) + b'\n')


def _correction_url(row):
    return CORRECTIONS_PATH + '#' + _token('correction-' + row['id'])


def _corrections_page(context, rows):
    prepublication = sum(row['status'] == 'accepted' for row in rows)
    errata = sum(row['status'] == 'published' for row in rows)
    body = ('<header class="r-page-head"><h1>Research corrections</h1>'
            '<p class="r-lede">Each correction links to the original claim and its evidence. Review notes describe how it was checked.</p><p>'
            + sp.plural(prepublication, 'accepted prepublication correction') + ' · '
            + sp.plural(errata, 'published-edition erratum', 'published-edition errata')
            + '</p>' + _meta(context) + '</header>'
            '<p>' + _link(CORRECTIONS_PATH + 'feed.xml', 'Subscribe with RSS') + ' · '
            + _link(CORRECTIONS_PATH + 'atom.xml', 'Subscribe with Atom') + '</p>')
    if not rows:
        return body + '<section class="r-section"><h2>No corrections recorded</h2><p>No accepted or published research corrections are recorded.</p></section>'
    for row in rows:
        stamp = row['instant'].isoformat().replace('+00:00', 'Z')
        body += (f'<article class="r-source" id="{sp.escape("correction-" + row["id"])}"><h2>'
                 + _link(_correction_url(row), 'Correction for ' + row['claim_id']) + '</h2><dl class="r-facts">'
                 f'<dt>Status</dt><dd>{sp.escape(row["status"].capitalize())}</dd>'
                 f'<dt>Edition</dt><dd>{sp.escape(row["edition_id"])}</dd>'
                 '<dt>Claim</dt><dd>' + _link(_evidence_url('assertion', row['claim_id']), row['claim_id']) + '</dd>'
                 + ('<dt>Approved replacement</dt><dd>' + _link(_evidence_url('assertion', row['replacement_claim_id']), row['replacement_claim_id']) + '</dd>' if row.get('replacement_claim_id') else '') +
                 f'<dt>Corrected</dt><dd><time datetime="{stamp}">{stamp}</time></dd></dl>'
                 '<h3>Supporting evidence</h3><ul>'
                 + ''.join('<li>' + _link(url, url) + '</li>' for url in row['evidence_urls']) + '</ul>'
                 + '<details class="r-disclosure"><summary>Review notes</summary><p>' + sp.escape(row['summary']) + '</p></details></article>')
    return body


def _correction_feeds(output, context, rows):
    """Separate correction subscriptions never contain ordinary edition updates."""
    canonical = sp.ORIGIN + CORRECTIONS_PATH
    rss = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(rss, 'channel')
    for key, text in (('title', 'ScienceToStartup research corrections'), ('link', canonical),
                      ('description', 'Accepted research corrections with edition, claim, correction date and evidence.')):
        ET.SubElement(channel, key).text = text
    ns = 'http://www.w3.org/2005/Atom'
    ET.register_namespace('', ns)
    atom = ET.Element('{' + ns + '}feed')
    ET.SubElement(atom, '{' + ns + '}title').text = 'ScienceToStartup research corrections'
    ET.SubElement(atom, '{' + ns + '}id').text = canonical
    ET.SubElement(atom, '{' + ns + '}link', {'href': canonical + 'atom.xml', 'rel': 'self'})
    ET.SubElement(atom, '{' + ns + '}link', {'href': canonical, 'rel': 'alternate'})
    author = ET.SubElement(atom, '{' + ns + '}author')
    ET.SubElement(author, '{' + ns + '}name').text = context['identity']['publisher']['name']
    ET.SubElement(author, '{' + ns + '}uri').text = context['identity']['publisher']['url']
    newest = rows[0]['instant'].isoformat().replace('+00:00', 'Z') if rows else context['report']['updated_on'] + 'T00:00:00Z'
    ET.SubElement(atom, '{' + ns + '}updated').text = newest
    for row in rows:
        permalink = sp.ORIGIN + _correction_url(row)
        description = (f'Edition: {row["edition_id"]}. Claim: {row["claim_id"]}. '
                       f'Status: {row["status"]}. ' + (f'Approved replacement: {row["replacement_claim_id"]}. ' if row.get('replacement_claim_id') else '') + f'{row["summary"]} Evidence: ' + ' '.join(row['evidence_urls']))
        item = ET.SubElement(channel, 'item')
        for key, value in (('title', row['summary']), ('link', permalink), ('description', description),
                           ('pubDate', format_datetime(row['instant'], usegmt=True))):
            ET.SubElement(item, key).text = value
        ET.SubElement(item, 'guid', {'isPermaLink': 'true'}).text = permalink
        entry = ET.SubElement(atom, '{' + ns + '}entry')
        for key, value in (('title', row['summary']), ('id', permalink), ('summary', description),
                           ('updated', row['instant'].isoformat().replace('+00:00', 'Z'))):
            ET.SubElement(entry, '{' + ns + '}' + key).text = value
        ET.SubElement(entry, '{' + ns + '}link', {'href': permalink, 'rel': 'alternate'})
        ET.SubElement(entry, '{' + ns + '}category', {'term': row['status']})
        for url in row['evidence_urls']:
            ET.SubElement(entry, '{' + ns + '}link', {'href': url, 'rel': 'related'})
    directory = output / CORRECTIONS_PATH.strip('/')
    directory.mkdir(parents=True, exist_ok=True)
    for name, tree in (('feed.xml', rss), ('atom.xml', atom)):
        (directory / name).write_bytes(ET.tostring(tree, encoding='utf-8', xml_declaration=True) + b'\n')


def write_company_supplements(output, context):
    """Append dated approved evidence to existing legacy company canonicals.

    Call after static_pages writes original company HTML. Return only changed
    company sitemap records; merge these by path into the existing sitemap.
    Historical prose, figures, source dates and organization metadata are retained.
    """
    output = Path(output)
    context = {**context, '_page_revisions': _revision_dates(context)}
    records = []
    for entity in sorted(context['graph']['entities'], key=lambda row: row['id']):
        legacy = entity.get('legacy_id')
        assertions = _assertions(context, entity)
        if not legacy or not assertions:
            continue
        path = entity_url(entity, context)
        target = output / path.strip('/') / 'index.html'
        if not target.is_file():
            continue
        original = target.read_text(encoding='utf-8')
        canonical = sp.ORIGIN + path
        if f'<link rel="canonical" href="{sp.escape(canonical)}">' not in original or '</main>' not in original:
            raise ValueError('Legacy company supplement requires its existing canonical and main: ' + path)
        modified = _page_revision(context, path)
        def update_page_date(match):
            nonlocal modified
            node = json.loads(match.group(2))
            def update(value):
                nonlocal modified
                if isinstance(value, dict):
                    if value.get('@id') == canonical and value.get('@type') in {'WebPage', 'ProfilePage'}:
                        modified = max(filter(None, [modified, _day(value.get('dateModified'))]), default=None)
                        if modified:
                            value['dateModified'] = modified
                        else:
                            value.pop('dateModified', None)
                    for child in value.values():
                        update(child)
                elif isinstance(value, list):
                    for child in value:
                        update(child)
            update(node)
            return match.group(1) + sp.json_ld(node) + match.group(3)
        text = re.sub(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)', update_page_date, original, flags=re.S)
        section = ('<!-- research-supplement:start --><details class="research r-company-supplement company-fold" id="new-research-evidence">'
                   '<summary><span>Research updates</span><small>' + str(len(assertions)) + ' approved records</small></summary><div class="company-fold-body">'
                   '<h2>New research evidence</h2><p class="r-meta">Research evidence snapshot '
                   + _date(context['graph']['as_of']) + ' · Added assessment ' + _date(context['report']['updated_on']) + '</p>'
                   '<p>These approved assertions supplement the historical profile. Each retains its own evidence date, scope and qualifications. '
                   'They do not establish commercial quality or an unstated supplier contribution.</p>'
                   + ''.join(_assertion(context, assertion, compact=True) for assertion in assertions)
                   + '</div></details><!-- research-supplement:end -->')
        text = re.sub(r'<!-- research-supplement:start -->.*?<!-- research-supplement:end -->', '', text, flags=re.S)
        text = text.replace('</main>', section + '</main>', 1)
        if '<link rel="stylesheet" href="/research.css">' not in text:
            text = text.replace('</head>', '<link rel="stylesheet" href="/research.css">\n</head>', 1)
        target.write_text(text, encoding='utf-8')
        records.append({'path': path, **({'lastmod': modified} if modified else {})})
    if records:
        (output / 'research.css').write_bytes((ROOT / 'web/research.css').read_bytes())
    return records


def _render_context(context, corrections):
    graph = context['graph']
    context = {**context, '_render_corrections': corrections,
               '_render_entities': {row['id']: row for row in graph['entities']},
               '_render_sources': {row['id']: row for row in graph['sources']},
               '_render_reviews': {row['id']: row for row in graph.get('reviews', [])},
               '_render_company_ids': {row['id'] for row in graph['entities'] if _new_company(context, row)}}
    context['_render_ledger'] = _ledger_records(context)
    context['_page_revisions'] = _revision_dates(context)
    return context


def write_research_pages(output, context):
    """Write static research HTML, its stylesheet and publication-only feeds.

    Return sitemap-ready {path, lastmod} records for HTML pages only. Paths are
    site-relative and begin with '/'. Existing legacy company HTML is untouched.
    """
    output = Path(output)
    editions = _published_editions(context)
    corrections = _correction_records(context)
    # Keep current operational notices outside immutable publication contexts.
    context = with_operating_status(context, now=datetime.now(timezone.utc))
    context = {**context, '_legacy_current_bookmarks': True,
               '_render_company_websites': _company_websites(context),
               '_render_source_rechecks': _source_rechecks(context),
               '_render_source_anchor_ids': _source_anchor_ids(context['root']) if context.get('root') is not None else []}
    context = _render_context(context, corrections)
    status = context.get('operating_status')
    if status is not None:
        observed_day = _day(status.observed_on.isoformat())
        for path in ('/research/', REPORT_PATH, '/research/data/'):
            context['_page_revisions'][path] = max(
                context['_page_revisions'].get(path) or observed_day, observed_day)
    download_sizes = {url: file.stat().st_size for url in DATA_JSON_DOWNLOADS
                      if (file := output / url.lstrip('/')).is_file()}
    pages = [("/research/", "AI data research", "Papers and datasets on AI training, with evidence about the suppliers.", _hub(context, editions), "CollectionPage", None),
             (REPORT_PATH, context["report"]["title"], context["report"].get("summary", "Research methods and findings."), _report(context), "Book", None),
             ("/research/data/", "Research data and sources", "Download the research data or look up a finding and its sources.", _data(context, download_sizes=download_sizes), "CollectionPage", None),
             ("/review/", "Review & correct the research", "Contribute a source-backed correction, scoped review, or public reuse of ScienceToStartup research.", _review(context), "WebPage", None),
             (CORRECTIONS_PATH, "Research corrections", "Accepted research corrections, with affected editions, claims, correction dates and supporting evidence.", _corrections_page(context, corrections), "CollectionPage", None)]
    pages.extend((_reader_path(section), section['title'],
                  section['title'] + '. A chapter of ' + context['report']['title'] + ' with complete source-linked text.',
                  _reader_chapter(context, section), "Chapter", (REPORT_PATH, context['report']['title']))
                 for section in context['report']['sections'][1:])
    pages.extend(_ledger_pages(context))
    for category in CATEGORIES:
        slug, label, kinds, description = category
        pages.append(("/research/" + slug + "/", label, description, _index(context, category), "CollectionPage", None))
        for entity in sorted(context["graph"]["entities"], key=lambda row: row["id"]):
            if entity.get("kind") in kinds:
                pages.append((entity_url(entity, context), entity["name"], _label(entity) + ". Evidence, source metadata, review status, and limitations.",
                              _detail(context, entity), "WebPage", category))
    for entity in sorted(context["graph"]["entities"], key=lambda row: row["id"]):
        if _new_company(context, entity):
            pages.append((entity_url(entity, context), entity["name"], "Approved public research evidence and its qualifications.", _detail(context, entity), "WebPage", None))
    records = []
    for path, title, description, body, page_type, parent in pages:
        target = output / path.lstrip('/') / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render(context, title, description, path, body, page_type, parent), encoding='utf-8')
        records.append(_sitemap_record(context, path))
    for path, snapshot in editions:
        snapshot = _render_context(snapshot, _correction_records(snapshot))
        metadata = publication_metadata(snapshot)
        target = output / path.lstrip('/') / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        def edition_links(text):
            # Evidence on an immutable edition must not silently resolve to this
            # week's changed assertions or downloads. Only site URL attributes
            # and structured URL fields change; source URLs and quoted facts do
            # not become edition links merely by containing the same path.
            for prefix, replacement in (('/research/data/', path + 'data/'),
                                        (sp.ORIGIN + '/research/data/', sp.ORIGIN + path + 'data/')):
                text = re.sub(r'((?:href|content)=")' + re.escape(prefix),
                              lambda match: match.group(1) + replacement, text)
                text = re.sub(r'("(?:@id|url|item|contentUrl)"\s*:\s*")' + re.escape(prefix),
                              lambda match: match.group(1) + replacement, text)
            archive = _safe_url(snapshot['report'].get('archive', {}).get('record_url'))
            if archive and not metadata.get('doi'):
                text = re.sub(r'href="/(?:publication|research/exports)/[^\"]+"', 'href="' + sp.escape(archive) + '"', text)
            return text
        target.write_text(edition_links(_render(snapshot, snapshot['report']['title'], snapshot['report'].get('summary', ''), path,
                                  _report(snapshot, edition=True, base=path), 'Book')), encoding='utf-8')
        records.append(_sitemap_record(snapshot, path))
        for section in snapshot['report']['sections'][1:]:
            chapter_path = _reader_path(section, path)
            chapter_target = output / chapter_path.lstrip('/') / 'index.html'
            chapter_target.parent.mkdir(parents=True, exist_ok=True)
            chapter_target.write_text(edition_links(_render(snapshot, section['title'], section['title'] + '. Complete archived chapter.',
                chapter_path, _reader_chapter(snapshot, section, path, edition=True), 'Chapter', (path, snapshot['report']['title']))), encoding='utf-8')
            records.append(_sitemap_record(snapshot, chapter_path))
        ledger_path = path + 'data/'
        ledger = output / ledger_path.lstrip('/') / 'index.html'
        ledger.parent.mkdir(parents=True, exist_ok=True)
        reuse_path = ('/publication/current-REUSE.md'
                      if 'publication/current-REUSE.md' in context.get('publication_assets', []) else '')
        ledger.write_text(edition_links(_render(snapshot, 'Edition evidence and sources', 'Frozen assertion and source records for this exact archived edition.',
                                               ledger_path, _data(snapshot, ledger_path=ledger_path, metadata=metadata,
                                                                  reuse_path=reuse_path), 'CollectionPage')), encoding='utf-8')
        if metadata.get('doi'):
            citation_dir = ledger.parent / 'citations'
            citation_dir.mkdir(exist_ok=True)
            for filename, content in citation_formats(metadata).items():
                (citation_dir / filename).write_bytes(content)
        records.append(_sitemap_record(snapshot, ledger_path))
        for live_path, title, description, body, page_type, parent in _ledger_pages(snapshot, ledger_path):
            bucket_path = ledger_path + live_path.removeprefix('/research/data/')
            bucket = output / bucket_path.lstrip('/') / 'index.html'
            bucket.parent.mkdir(parents=True, exist_ok=True)
            bucket.write_text(edition_links(_render(snapshot, title, description, bucket_path, body, page_type, parent)), encoding='utf-8')
            records.append(_sitemap_record(snapshot, bucket_path))
    (output / 'research.css').write_bytes((ROOT / 'web/research.css').read_bytes())
    from frontend_packaging import optional_script_source
    (output / 'research-index.js').write_text(optional_script_source(ROOT, 'research-index.js'), encoding='utf-8')
    _feeds(output, context, editions)
    _correction_feeds(output, context, corrections)
    return records


def research_search_entries(context):
    """Compact local-search records; candidate wording never enters summaries."""
    entries = [
        {"title": "AI data research", "summary": "Papers and datasets on AI training, with evidence about the suppliers.", "url": "/research/", "kind": "research", "keywords": "AI data labs human feedback evidence"},
        {"title": context["report"]["title"], "summary": _status(context) + ". Twelve chapters of methods, historical examples, and research gaps.", "url": REPORT_PATH, "kind": "report", "keywords": "human feedback RLHF annotation suppliers methods"},
        {"title": "Research data and sources", "summary": "Download the data or look up a finding and its sources.", "url": "/research/data/", "kind": "data", "keywords": "JSON CSV SQLite citation sources provenance"},
        {"title": "Review the research", "summary": "Submit a correction or a chapter review. Share where you used the data.", "url": "/review/", "kind": "review", "keywords": "correction contribute review reuse"},
        {"title": "Research corrections", "summary": "Accepted corrections with affected editions, claims, correction dates and source evidence.", "url": CORRECTIONS_PATH, "kind": "review", "keywords": "corrections errata RSS Atom evidence"},
    ]
    for index, section in enumerate(context['report']['sections'][1:], 2):
        entries.append({"title": section['title'], "summary": _status(context) + '. Chapter ' + str(index) + ' of ' + context['report']['title'] + '.',
                        "url": _reader_path(section), "kind": "report", "keywords": section['id'].replace('-', ' ')})
    for slug, title, kinds, description in CATEGORIES:
        entries.append({"title": title, "summary": description, "url": '/research/' + slug + '/', "kind": "research", "keywords": title.lower()})
    for entity in sorted(context['graph']['entities'], key=lambda row: row['id']):
        category = _category(entity)
        approved_org = _new_company(context, entity)
        if category or approved_org:
            title = _display_title(entity['name'])
            original_title = [entity['name']] if title != entity['name'] else []
            identifiers = _search_identifiers(entity)
            entries.append({"title": title, "summary": _label(entity) + '. Inspect source metadata and assertion-specific qualifications.',
                            "url": entity_url(entity, context), "kind": category[0][:-1] if category else 'company',
                            **({"identifiers": identifiers, "recordKind": entity['kind']} if identifiers else {}),
                            "keywords": ' '.join([entity['id']] + entity.get('aliases', []) + list(entity.get('identifiers', {}).values()) + original_title)})
    return entries
