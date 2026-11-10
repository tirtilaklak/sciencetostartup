#!/usr/bin/env python3
"""Crawlable research pages with explicit evidence and publication states.

The renderer performs no network calls. Candidate wording never becomes a fact
merely because a source was captured; only approved assertions are synthesized.
Historical descriptions keep their original assertion and source dates. The
coordinator calls these two public functions from the ordinary static build.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import hashlib
import json
import re
from types import SimpleNamespace
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import static_pages as sp
from research_findings import executive_findings, finding_anchor, field_text, JUDGMENT_FIELDS, WITHHELD

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = "/research/state-of-ai-data-labs/"
CORRECTIONS_PATH = "/research/corrections/"
CATEGORIES = (
    ("papers", "Papers", {"paper", "paper_work", "paper_version"},
     "Read the source, distinguish versions, and trace what an operational finding actually supports."),
    ("datasets", "Datasets", {"dataset", "dataset_family", "dataset_release"},
     "Follow dataset families, annotation formats, provenance, access terms, and documented limitations."),
    ("benchmarks", "Benchmarks", {"benchmark", "benchmark_family", "benchmark_version"},
     "Keep benchmark versions, tasks, populations, and test conditions attached to every comparison."),
    ("workflows", "Workflows", {"workflow"},
     "Connect the work to its evidence: recruitment, annotation, adjudication, filtering, and evaluation."),
)
PROGRESS = (
    ("legacy_dispositions", "Legacy organizations reviewed", 39),
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
    return "/research/data/#" + _token(_anchor(kind, stable_id))


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
    return {row["id"]: row for row in context["graph"]["entities"]}


def _assertions(context, entity=None, statuses=("approved",)):
    return sorted((row for row in context["graph"]["assertions"]
                   if row.get("status") in statuses and (entity is None or
                   entity["id"] in {row.get("subject_id"), row.get("object_id")})),
                  key=lambda row: row["id"])


def _approved_entity(context, entity):
    return entity.get("status") == "approved" and bool(_assertions(context, entity))


def _new_company(context, entity):
    return (not entity.get('legacy_id') and entity.get('kind') in {'supplier', 'organization', 'institution'}
            and _approved_entity(context, entity)
            and any(a.get('subject_id') == entity['id'] for a in _assertions(context, entity)))


def _label(entity):
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


def _nav(current=""):
    links = [("Research", "/research/"), ("Report", REPORT_PATH)]
    links += [(label, "/research/" + slug + "/") for slug, label, _, _ in CATEGORIES]
    links += [("Data & sources", "/research/data/"), ("Review", "/review/")]
    return '<nav class="r-nav" aria-label="Research">' + "".join(
        f'<a href="{url}"' + (' aria-current="page"' if url == current else "") + f'>{label}</a>'
        for label, url in links) + "</nav>"


def _crumbs(label, path, parent=None):
    crumbs = [("Home", sp.ORIGIN + "/"), ("Research", sp.ORIGIN + "/research/")]
    if parent:
        crumbs.append((parent[1], sp.ORIGIN + "/research/" + parent[0] + "/"))
    if path != "/research/":
        crumbs.append((label, sp.ORIGIN + path))
    return sp.crumb_nav(crumbs), crumbs


def _render(context, title, description, path, body, page_type="WebPage", parent=None):
    crumbs_html, crumbs = _crumbs(title, path, parent)
    identity = context["identity"]
    person = identity.get("publisher", {})
    publisher = {"@type": person.get("type", "Person"), "@id": person.get("id", sp.ORIGIN + "/#publisher"),
                 "name": person.get("name", sp.PUBLISHER_NAME), "url": person.get("url", sp.ORIGIN + "/method/#about")}
    structured = sp.page_node(page_type, title, description, sp.ORIGIN + path,
                              context["report"]["updated_on"], crumbs, publisher=publisher)
    if page_type == "TechArticle":
        structured.update({"author": publisher, "creativeWorkStatus": _status(context),
                           "version": context["report"]["release_id"],
                           "license": sp.DATA_LICENSE})
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
                               data={"dataset_version": context["graph"].get("canonical_dataset_version")})
    text = sp.document(research, sp.truncate(title + sp.SUFFIX, sp.TITLE_LIMIT), sp.truncate(description),
                       sp.ORIGIN + path, '<div class="research wide">' + crumbs_html + _nav(path) + body + "</div>",
                       structured=structured, current="research")
    extra = ('<link rel="stylesheet" href="/research.css">\n'
             '<link rel="alternate" type="application/rss+xml" title="Published research editions" href="/research/feed.xml">\n'
             '<link rel="alternate" type="application/atom+xml" title="Published research editions" href="/research/atom.xml">\n'
             '<link rel="alternate" type="application/rss+xml" title="Research corrections" href="/research/corrections/feed.xml">\n'
             '<link rel="alternate" type="application/atom+xml" title="Research corrections" href="/research/corrections/atom.xml">\n')
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
    for slug, title, kinds, description in CATEGORIES:
        rows = [e for e in context["graph"]["entities"] if e.get("kind") in kinds]
        approved = sum(_approved_entity(context, e) for e in rows)
        candidate = sum(e.get("status") == "candidate" for e in rows)
        cards.append(f'<article class="r-browse-card"><p class="r-kicker">{approved} approved · {candidate} candidates</p>'
                     f'<h3>{_link("/research/" + slug + "/", title)}</h3><p>{sp.escape(description)}</p>'
                     f'{_link("/research/" + slug + "/", "Explore " + title.lower() + " →", "r-text-link")}</article>')
    return '<div class="r-browse-grid">' + "".join(cards) + "</div>"


def _hub(context, editions=()):
    report = context["report"]
    chapters = "".join(f'<li>{_link(REPORT_PATH + "#" + _token(section["id"]), section["title"])}</li>'
                       for section in report["sections"])
    archive_links = ('<section class="r-section"><h2>Published editions</h2><ul class="r-entity-list">'
                     + ''.join(f'<li>{_link(path, snapshot["report"]["release_id"])} · {_date(snapshot["report"]["updated_on"])}</li>'
                               for path, snapshot in editions) + '</ul></section>') if editions else ''
    return ('<header class="r-hero"><div><p class="r-kicker">Independent public-source research</p>'
            '<h1>The human work<br>behind AI.</h1><p class="r-lede">Follow the evidence connecting AI data suppliers, '
            'papers, datasets, benchmarks, and the work that brings them together.</p>'
            f'<p class="r-status">{_status(context)}</p>{_meta(context)}</div>'
            '<aside class="r-report-card" aria-label="Current research report"><p class="r-kicker">The research report</p>'
            f'<h2>{_link(REPORT_PATH, report["title"])}</h2><p>12 chapters. Source-level evidence. Clear limits.</p>'
            '<div class="r-report-rule" aria-hidden="true"><span></span><span></span><span></span><span></span></div>'
            f'<p>{sp.escape(report.get("summary"))}</p>{_link(REPORT_PATH, "Read the framework →", "r-button")}</aside></header>'
            '<section class="r-section" aria-labelledby="coverage"><div class="r-section-head"><div><p class="r-kicker">Progress you can inspect</p>'
            '<h2 id="coverage">Evidence before conclusions.</h2></div>'
            f'{_link("/research/data/", "Coverage, sources & downloads →", "r-text-link")}</div>'
            '<p class="r-section-intro">Launch requirements count approved, source-reviewed records. A candidate, a captured page, '
            'or an inherited description does not meet that standard.</p>' + _progress(context, compact=True)
            + f'<p class="r-meta">{sp.escape(_counts(context))}</p></section>'
            '<section class="r-section" aria-labelledby="browse"><div class="r-section-head"><div><p class="r-kicker">Explore the evidence</p>'
            '<h2 id="browse">Start with a question.</h2></div></div>' + _browse(context) + "</section>"
            '<section class="r-section r-chapter-preview" aria-labelledby="chapters"><div><p class="r-kicker">A practical research framework</p>'
            '<h2 id="chapters">From source to decision.</h2><p>Read the methods and decision framework while the evidence corpus is prepared. '
            'Historical examples carry their original dates; unresolved questions stay visible.</p>'
            f'{_link("/review/", "Help review a specific claim →", "r-text-link")}</div><ol class="r-chapter-list">{chapters}</ol></section>'
            + archive_links)


def _claim_text(context, assertion):
    entities = _entities(context)
    subject = entities.get(assertion.get("subject_id"), {})
    obj = entities.get(assertion.get("object_id"), {})
    subject_html = _link(entity_url(subject, context), subject.get("name", "Unknown subject")) if subject else "Unknown subject"
    if assertion.get("value") is not None:
        value = assertion["value"]
        if isinstance(value, dict):
            value = value.get("value", "")
        relation = str(assertion.get("predicate", "observation")).replace("_", " ")
        label = "" if assertion.get("predicate") == "legacy_description" else " · " + relation
        if isinstance(value, bool):
            value = 'Yes' if value else 'No'
        return f'{subject_html}{sp.escape(label)}: {sp.escape(value)}'
    relation = str(assertion.get("predicate", "relationship")).replace("_", " ")
    object_html = _link(entity_url(obj, context), obj.get("name", "Unknown object")) if obj else "Unknown object"
    return f'{subject_html} {sp.escape(relation)} {object_html}.'


def _source_evidence(context, assertion):
    sources = {s["id"]: s for s in context["graph"]["sources"]}
    rows = []
    for evidence in assertion.get("evidence", []):
        source = sources.get(evidence.get("source_id"), {})
        excerpt = ''
        if (assertion.get('status') == 'approved' and source.get('status') == 'captured'
                and source.get('excerpt') and evidence.get('excerpt_sha256') == source.get('excerpt_sha256')):
            excerpt = '<blockquote class="r-evidence-excerpt"><p>' + sp.escape(source['excerpt']) + '</p></blockquote>'
        rows.append('<li>' + _link(_evidence_url("source", source.get("id", "")), source.get("title", evidence.get("source_id")))
                    + f'<span class="r-source-locator">Locator: {sp.escape(evidence.get("locator", "Not recorded"))}</span>' + excerpt + '</li>')
    return '<ul class="r-evidence-links">' + "".join(rows) + "</ul>"


def _assertion(context, assertion):
    status = assertion.get("status")
    aid = assertion["id"]
    body = f'<p class="r-kicker">{sp.escape(STATUS_LABELS.get(status, status))} · As of {_date(assertion.get("as_of"))}</p>'
    if status in {"approved", "historical"}:
        body += '<p class="r-assertion-text">' + _claim_text(context, assertion) + "</p>"
    else:
        body += '<p>Candidate wording is withheld from findings while source verification and adversarial review are pending.</p>'
    body += f'<p class="r-record-id">{_link(_evidence_url("assertion", aid), aid)}</p>'
    if assertion.get("qualifications") and status in {"approved", "historical"}:
        body += '<ul class="r-qualifications">' + "".join(f'<li>{sp.escape(q)}</li>' for q in assertion["qualifications"]) + "</ul>"
    body += _source_evidence(context, assertion)
    reviews = {row["id"]: row for row in context["graph"].get("reviews", [])}
    receipts = [reviews[rid] for rid in assertion.get("review_ids", []) if rid in reviews]
    if receipts:
        body += '<details class="r-receipts"><summary>Inspect actual AI review receipts</summary><ul>' + "".join(
            f'<li>{sp.escape(r.get("role", "").replace("_", " ").capitalize())}: {sp.escape(r.get("verdict"))} '
            f'· {_date(r.get("reviewed_on"))}<br><span class="r-record-id">{sp.escape(r.get("invocation_id"))}</span></li>'
            for r in sorted(receipts, key=lambda row: (row.get("role", ""), row["id"]))) + "</ul></details>"
    elif status == "historical":
        body += '<p class="r-meta">Inherited provenance; no fresh research review is claimed.</p>'
    return f'<article class="r-assertion" id="{sp.escape(_anchor("assertion", aid))}">{body}</article>'


def _paragraph(context, paragraph):
    ids = paragraph.get("claim_ids", [])
    claims = {a["id"]: a for a in context["graph"]["assertions"]}
    kind = paragraph.get("kind")
    valid = all(cid in claims and (claims[cid].get("status") == "approved" or
                (claims[cid].get("status") == "historical" and paragraph.get("historical") is True)) for cid in ids)
    if (kind == "sourced_fact" and (not ids or not valid)) or (ids and not valid):
        return '<div class="r-paragraph is-gap"><span class="r-paragraph-kind">Research gap</span><p>A proposed finding is withheld because its evidence is not approved for publication.</p></div>'
    label = "Historical example" if paragraph.get("historical") else KIND_LABELS.get(kind, "Research note")
    links = ('<p class="r-paragraph-citations">Evidence: ' + ", ".join(_link(_evidence_url("assertion", cid), cid) for cid in ids) + "</p>") if ids else ""
    return (f'<div class="r-paragraph' + (' is-gap' if kind == "research_gap" else '') + '">'
            f'<span class="r-paragraph-kind">{label}</span><p>{sp.escape(paragraph.get("text"))}</p>{links}</div>')


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


def _report(context, edition=False):
    report = context["report"]
    # In-page fragment links are generated here, never accepted from source data.
    contents = "".join(f'<li><a href="#{_token(s["id"])}">{sp.escape(s["title"])}</a></li>' for s in report["sections"])
    chapters = "".join(f'<section class="r-chapter" id="{sp.escape(s["id"])}"><h2>{sp.escape(s["title"])}</h2>'
                       + "".join(_paragraph(context, p) for p in s.get("paragraphs", []))
                       + (_findings(context) if s['id'] == 'executive-assessment' else '') + "</section>" for s in report["sections"])
    state = "Published edition" if edition else _status(context)
    return (f'<header class="r-page-head"><p class="r-kicker">{sp.escape(state)}</p><h1>{sp.escape(report["title"])}</h1>'
            f'<p class="r-lede">{sp.escape(report.get("subtitle"))}</p>{_meta(context)}'
            f'<p class="r-callout">{sp.escape(report.get("summary"))}</p>'
            f'<p class="r-meta">{sp.escape(report.get("review_statement"))}</p></header>'
            '<div class="r-report-layout"><aside class="r-toc"><h2>In this report</h2><ol>' + contents + '</ol>'
            + _link("/research/data/", "Inspect coverage & evidence →", "r-text-link") + '</aside><div class="r-report-body">'
            + chapters + '<section class="r-chapter" id="cite"><h2>Cite this work</h2>'
            f'<p>{sp.escape(context["identity"].get("publisher", {}).get("name", sp.PUBLISHER_NAME))}. '
            f'<cite>{sp.escape(report["title"])}</cite>. {sp.escape(report["release_id"])}. {_date(report["updated_on"])}.</p>'
            + ('' if edition or (context["gate"].get("ready") and report.get("status") == "published") else '<p>This is a prepublication framework. No published research edition or DOI is claimed.</p>')
            + _link("/research/data/#citation", "Citation formats & reuse →", "r-text-link") + '</section></div></div>')


def _source(source):
    return (f'<article class="r-source" id="{sp.escape(_anchor("source", source["id"]))}">'
            f'<h3>{_link(source.get("url"), source.get("title", source["id"]))}</h3>'
            f'<p class="r-record-id">{_link(_evidence_url("source", source["id"]), source["id"])}</p>'
            '<dl class="r-facts"><dt>Publisher</dt><dd>' + sp.escape(source.get("publisher")) + '</dd>'
            f'<dt>Published</dt><dd>{_date(source.get("published_on"))}</dd>'
            f'<dt>Captured</dt><dd>{_date(source.get("captured_on"))} · {sp.escape(source.get("status", "").replace("_", " "))}</dd>'
            f'<dt>Version</dt><dd>{sp.escape(source.get("version"))}</dd>'
            f'<dt>Locator</dt><dd>{sp.escape(source.get("locator"))}</dd></dl>'
            '<p class="r-meta">A source capture records retrieval. Assertion-specific review is recorded separately.</p></article>')


def _data(context):
    graph, gate, report = context["graph"], context["gate"], context["report"]
    approved = _assertions(context)
    historical = _assertions(context, statuses=("historical",))
    candidates = _assertions(context, statuses=("candidate",))
    rows = [("Privacy-filtered research JSON", "/publication/clean-dataset.json"), ("CSV", "/publication/clean-dataset.csv"),
            ("SQLite", "/publication/clean-dataset.sqlite"), ("Full evidence graph JSON · explicit statuses", "/research/exports/research-graph.json"),
            ("Evidence graph SQLite", "/research/exports/research-graph.sqlite"), ("Export checksums", "/research/exports/research-exports-manifest.json")]
    if 'publication/report.pdf' in context.get('publication_assets', []):
        rows.insert(0, ('Read the report preparation PDF', '/publication/report.pdf'))
    links = "".join('<li>' + _link(url, label) + '</li>' for label, url in rows)
    citation_prefix = 'current-' if gate.get('ready') and report.get('archive', {}).get('status') == 'published' else ''
    cite = "".join('<li>' + _link('/publication/' + citation_prefix + name, label) + '</li>' for name, label in
                   (("citation.bib", "BibTeX"), ("citation.ris", "RIS"), ("citation.csl.json", "CSL JSON"), ("CITATION.cff", "CITATION.cff")))
    other = [e for e in graph["entities"] if not _category(e)]
    entity_rows = "".join(f'<li id="{sp.escape(_anchor("entity", e["id"]))}">{_link(entity_url(e, context), e["name"])} '
                          f'<span class="r-meta">{sp.escape(_label(e))} · {sp.escape(e["id"])}</span></li>'
                          for e in sorted(other, key=lambda e: (e["name"].casefold(), e["id"])))
    return (f'<header class="r-page-head"><p class="r-kicker">{_status(context)}</p><h1>Open data.<br>Visible evidence.</h1>'
            '<p class="r-lede">Inspect what is supported, what is inherited, and what still needs review. '
            'Every count comes from the versioned evidence graph.</p>' + _meta(context) + '</header>'
            '<section class="r-section" aria-labelledby="coverage"><h2 id="coverage">Progress toward publication</h2>'
            + _progress(context) + f'<p>{sp.escape(_counts(context))}.</p>'
            '<p>The frozen eligible core and two separate 200-record quality audits must also pass. The reference audit requires '
            '98% precision and 95% recall, with no critical false attribution. The screening audit must recover at least 190 records '
            'and reach 90% recall in each major stratum.</p>' + _holds(context) + '</section>'
            '<section class="r-section" aria-labelledby="downloads"><h2 id="downloads">Download the research</h2>'
            '<p>The privacy-filtered projection retains explicit research status and historical qualifications. '
            'Historical records are not fresh verification. Source retrieval is not claim approval. The original canonical dataset stays at version '
            f'{sp.escape(graph.get("canonical_dataset_version"))}, with its existing identity and downloads.</p>'
            f'<ul class="r-downloads">{links}</ul><p class="r-meta">Research release: {sp.escape(graph["release_id"])}.</p></section>'
            '<section class="r-section" id="citation"><h2>Cite and reproduce</h2>'
            f'<p>{sp.escape(context["identity"].get("publisher", {}).get("name", sp.PUBLISHER_NAME))}. <cite>{sp.escape(report["title"])}</cite>. '
            f'{sp.escape(report["release_id"])}. {_date(report["updated_on"])}.</p>'
            + ('' if gate.get("ready") and report.get("status") == "published" else '<p>Prepublication framework. No published edition, permanent archive, or DOI is claimed.</p>')
            + f'<ul class="r-downloads">{cite}</ul><p>Reuse owned research under '
            + _link(sp.DATA_LICENSE, "CC BY 4.0") + '. Credit the publisher, release ID, original sources, and your changes. '
            'Source material retains its own rights and qualifications.</p>'
            f'<ul class="r-downloads"><li>{_link("/publication/research-archive.zip", "Inspect the prepared reproduction package")}</li>'
            f'<li>{_link("/publication/MANIFEST.json", "Package SHA-256 inventory")}</li>'
            f'<li>{_link("/publication/package-status.json", "Archive & mirror status")}</li></ul></section>'
            '<section class="r-section" aria-labelledby="approved"><h2 id="approved">Approved assertions</h2>'
            + ("".join(_assertion(context, a) for a in approved) if approved else
               '<p class="r-callout">No new assertions have completed the required separate reviews. Candidate evidence stays outside approved findings and coverage totals.</p>')
            + '</section><section class="r-section" aria-labelledby="historical"><h2 id="historical">Historical baseline</h2>'
            '<p>These descriptions were imported from canonical dataset 2.5.0. Their snapshot dates are historical provenance, '
            'not fresh source reviews or current supplier findings.</p>' + "".join(_assertion(context, a) for a in historical)
            + '</section><section class="r-section" aria-labelledby="candidates"><h2 id="candidates">Candidate review queue</h2>'
            '<p>Captured sources and author proposals are inspectable preparation work. Separate source verification and '
            'adversarial review have not established these as findings.</p>' + "".join(_assertion(context, a) for a in candidates)
            + '</section><section class="r-section" aria-labelledby="sources"><h2 id="sources">Source records</h2>'
            + "".join(_source(source) for source in sorted(graph["sources"], key=lambda s: s["id"]))
            + '</section><section class="r-section" aria-labelledby="organizations"><h2 id="organizations">Organizations & other entities</h2>'
            + f'<ul class="r-entity-register">{entity_rows}</ul></section>')


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


def _evidence_table(context, entities):
    """Metadata-only enhancement payload; assertions remain on native pages."""
    values = [_index_values(entity) for entity in entities]
    controls = '<form class="r-index-controls" data-index-controls hidden role="search" aria-label="Filter research records"><label>Search records<input name="q" type="search" autocomplete="off" placeholder="Title or identifier"></label>'
    for key in ('status', 'type') + INDEX_FACETS:
        options = sorted({value for row in values for value in row[key]}, key=str.casefold)
        if not options and key in {'delivery_model', 'data_purpose'}:
            continue
        label = {'status': 'Review status', 'type': 'Record type'}.get(key, key.replace('_', ' ').capitalize())
        controls += f'<label>{label}<select name="{key}"><option value="">All</option>' + ''.join(
            f'<option value="{sp.escape(value)}">{sp.escape(value.replace("_", " "))}</option>' for value in options)
        if any(not row[key] for row in values):
            controls += '<option value="__not_recorded__">Not recorded</option>'
        controls += '</select></label>'
    controls += '<button type="reset">Clear filters</button></form>'
    rows = []
    for entity, filters in zip(entities, values):
        claims = _assertions(context, entity)
        search = ' '.join([entity['name'], entity['id']] + entity.get('aliases', [])
                          + [str(value) for value in entity.get('identifiers', {}).values()])
        taxonomy = '; '.join(key.replace('_', ' ') + ': ' + ', '.join(filters[key]) for key in INDEX_FACETS if filters[key])
        rows.append('<tr data-index-row data-search="' + sp.escape(search.lower()) + '" data-filters="'
                    + sp.escape(json.dumps(filters, ensure_ascii=False, separators=(',', ':'))) + '">'
                    + '<th scope="row">' + _link(entity_url(entity, context), entity['name'])
                    + '<span class="r-record-id">' + sp.escape(entity['id']) + '</span></th>'
                    + '<td data-label="Review">' + sp.escape(_label(entity)) + '<span class="r-table-note">'
                    + sp.escape(entity.get('review_depth', '').replace('_', ' ')) + '</span></td>'
                    + '<td data-label="Type">' + sp.escape(entity['kind'].replace('_', ' ')) + '</td>'
                    + '<td data-label="Taxonomy">' + sp.escape(taxonomy or 'Not recorded') + '</td>'
                    + '<td data-label="Evidence">' + _link(entity_url(entity, context) + '#approved-findings', f'{len(claims)} approved assertions') + '</td></tr>')
    return ('<section data-research-index>' + controls
            + f'<p class="r-meta" data-index-count role="status" aria-live="polite" aria-atomic="true">{len(entities)} records</p>'
            + '<div class="r-table-wrap"><table class="r-evidence-table"><caption>Evidence records. Taxonomy on candidate records is provisional.</caption>'
            + '<thead><tr><th scope="col">Record</th><th scope="col">Review</th><th scope="col">Type</th><th scope="col">Taxonomy</th><th scope="col">Evidence</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div><p data-index-empty class="r-callout" hidden>No records match these filters. Clear filters to see all records.</p></section>')


def _index(context, category):
    slug, title, kinds, description = category
    entities = sorted((e for e in context["graph"]["entities"] if e.get("kind") in kinds),
                      key=lambda e: (not _approved_entity(context, e), e["name"].casefold(), e["id"]))
    approved = sum(_approved_entity(context, e) for e in entities)
    return (f'<header class="r-page-head"><p class="r-kicker">Research evidence index</p><h1>{title}</h1>'
            f'<p class="r-lede">{sp.escape(description)}</p><p class="r-status">{approved} approved records · '
            f'{sum(e.get("status") == "candidate" for e in entities)} candidate records</p>' + _meta(context) + '</header>'
            '<p class="r-callout">Candidate records help readers inspect the research queue. They are not reviewed findings, '
            'endorsements, or proof of a supplier contribution.</p>'
            + (_evidence_table(context, entities) if entities else
               '<section class="r-section"><h2>How this index will be built</h2><p>No records have entered this index yet. '
               'A workflow must identify its inputs, work stages, output artifact, qualifications, and version-specific source evidence. '
               'Separate source verification and adversarial review precede approval.</p>'
               + _link(REPORT_PATH, 'Read the evidence standard →', 'r-text-link') + '</section>'))


def _detail(context, entity):
    approved, historical = _assertions(context, entity), _assertions(context, entity, ("historical",))
    linked = [a for a in context["graph"]["assertions"] if entity["id"] in {a.get("subject_id"), a.get("object_id")}]
    sources = {s["id"]: s for s in context["graph"]["sources"]}
    source_ids = sorted({item["source_id"] for a in linked for item in a.get("evidence", [])})
    identifiers = "".join(f'<dt>{sp.escape(key)}</dt><dd>{sp.escape(value)}</dd>' for key, value in sorted(entity.get("identifiers", {}).items()))
    taxonomy = "".join(f'<dt>{sp.escape(key.replace("_", " ").capitalize())}</dt><dd>{sp.escape(", ".join(values))}</dd>'
                       for key, values in sorted(entity.get("taxonomy", {}).items()) if values)
    title = entity["name"]
    return (f'<header class="r-page-head"><p class="r-kicker">{sp.escape(_label(entity))}</p><h1 class="r-record-title">{sp.escape(title)}</h1>'
            f'<p class="r-record-id">{sp.escape(entity["id"])}</p>' + _meta(context) + '</header>'
            '<div class="r-detail-layout"><div><section class="r-section"><h2>Evidence & scope</h2>'
            f'<p>{sp.escape(entity.get("disposition_reason"))}</p><dl class="r-facts"><dt>Review depth</dt>'
            f'<dd>{sp.escape(entity.get("review_depth", "").replace("_", " "))}</dd><dt>Disposition</dt><dd>{sp.escape(entity.get("disposition"))}</dd>'
            + identifiers + '</dl></section><section class="r-section" id="approved-findings"><h2>Approved findings</h2>'
            + ("".join(_assertion(context, a) for a in approved) if approved else
               '<p class="r-callout">No approved assertions are available for this record. Source metadata and candidate proposals do not establish a finding.</p>')
            + '</section>'
            + ('<section class="r-section"><h2>Historical evidence</h2>' + "".join(_assertion(context, a) for a in historical) + '</section>' if historical else '')
            + '<section class="r-section"><h2>Connected evidence</h2>'
            + ('<ul class="r-evidence-links">' + "".join('<li>' + _link(_evidence_url("source", sid), sources.get(sid, {}).get("title", sid)) + '</li>' for sid in source_ids) + '</ul>'
               if source_ids else '<p>No source records are attached yet.</p>')
            + '</section></div><aside class="r-detail-aside"><h2>Read this record carefully</h2>'
            '<p>Approval applies to a specific assertion and its qualifications. It does not imply provider endorsement, '
            'commercial quality, or a contribution to another artifact.</p>'
            + ('<h3>Recorded taxonomy</h3><p class="r-meta">Candidate taxonomy remains provisional.</p><dl class="r-facts">' + taxonomy + '</dl>' if taxonomy else '')
            + _link('/review/', 'Submit a source-backed correction →', 'r-text-link') + '</aside></div>')


def _review(context):
    identity = context["identity"]
    issue_base = identity.get("contacts", {}).get("issues", identity.get("repository", {}).get("url", "") + '/issues/new/choose')
    new_issue = issue_base.removesuffix('/choose')
    return ('<header class="r-page-head"><p class="r-kicker">Open methods. Specific corrections.</p><h1>Help make the<br>evidence better.</h1>'
            '<p class="r-lede">Review a claim, challenge a missing qualification, or show how you reused the research. '
            'A precise source and locator make a contribution useful.</p>' + _meta(context) + '</header>'
            '<div class="r-browse-grid r-review-grid"><article class="r-browse-card"><p class="r-kicker">Correct a record</p>'
            '<h2>A claim needs a change.</h2><p>Include its stable ID, the original source version and locator, the proposed wording, '
            'and the reason. Source and review dates are preserved when a correction is accepted.</p>'
            + _link(new_issue + '?template=correction.yml', 'Submit a correction →', 'r-text-link') + '</article>'
            '<article class="r-browse-card"><p class="r-kicker">Review a section</p><h2>Put a conclusion to the test.</h2>'
            '<p>Name the report release and chapter. Check the source support, alternatives, missing evidence, and practical '
            'implications. State relevant interests and whether scoped public credit is permitted.</p>'
            + _link(new_issue + '?template=section-review.yml', 'Contribute a review →', 'r-text-link') + '</article>'
            '<article class="r-browse-card"><p class="r-kicker">Share a reuse</p><h2>Show the work it supports.</h2>'
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

    editions, seen = [], set()
    for entry in context["report"].get("editions", []):
        if not isinstance(entry, dict) or entry.get("status") != "published":
            continue
        rid = entry.get("release_id")
        if not rid or rid in seen:
            continue
        persisted = context.get('edition_snapshots', {}).get(rid, {})
        snapshot = {key: persisted.get(key, entry.get(key, context[key])) for key in ("graph", "report", "policy", "identity")}
        if snapshot["report"].get("release_id") != rid or snapshot["report"].get("status") not in {"published", "superseded"}:
            continue
        try:
            gate = publication_gate(snapshot["graph"], snapshot["report"], snapshot["policy"])
        except (ValueError, KeyError, TypeError):
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
            if datetime.fromisoformat(edition_date).weekday() != 0:
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


def _correction_records(context):
    """Validate committed records; requests and rejected proposals stay private."""
    rows = context.get('corrections', [])
    if not isinstance(rows, list):
        raise ValueError('Research corrections must be a list')
    required = {'id', 'edition_id', 'claim_id', 'status', 'summary', 'corrected_on', 'evidence_urls'}
    accepted, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError('Research correction has unexpected or missing fields')
        for key in ('id', 'edition_id', 'claim_id'):
            if not isinstance(row[key], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', row[key]):
                raise ValueError('Research correction requires stable record identifiers')
        if row['id'] in seen:
            raise ValueError('Research correction IDs must be unique')
        seen.add(row['id'])
        if not isinstance(row['status'], str) or row['status'] not in {'accepted', 'published', 'pending', 'rejected'}:
            raise ValueError('Research correction has an unknown status')
        if not isinstance(row['summary'], str) or not row['summary'].strip():
            raise ValueError('Research correction requires a summary')
        try:
            instant = datetime.fromisoformat(row['corrected_on'].replace('Z', '+00:00'))
            if instant.utcoffset() is None:
                raise ValueError('Timezone required')
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError('Research correction requires a timezone-aware corrected_on timestamp') from error
        evidence = row['evidence_urls']
        if (not isinstance(evidence, list) or not evidence or
                any(not isinstance(url, str) or not _safe_url(url) or re.search(r'[\x00-\x20\\]', url) for url in evidence) or
                len(evidence) != len(set(evidence))):
            raise ValueError('Research correction requires distinct safe HTTPS evidence URLs')
        if row['status'] in {'accepted', 'published'}:
            accepted.append({**row, 'instant': instant.astimezone(timezone.utc)})
    return sorted(accepted, key=lambda row: (-row['instant'].timestamp(), row['id']))


def _correction_url(row):
    return CORRECTIONS_PATH + '#' + _token('correction-' + row['id'])


def _corrections_page(context, rows):
    body = ('<header class="r-page-head"><p class="r-kicker">Research correction log</p><h1>Corrections</h1>'
            '<p class="r-lede">Accepted corrections identify the affected edition and claim, preserve the correction date, '
            'and link to supporting evidence.</p>' + _meta(context) + '</header>'
            '<p>' + _link(CORRECTIONS_PATH + 'feed.xml', 'Subscribe with RSS') + ' · '
            + _link(CORRECTIONS_PATH + 'atom.xml', 'Subscribe with Atom') + '</p>')
    if not rows:
        return body + '<section class="r-section"><h2>No corrections recorded</h2><p>No accepted or published research corrections are recorded.</p></section>'
    for row in rows:
        stamp = row['instant'].isoformat().replace('+00:00', 'Z')
        body += (f'<article class="r-source" id="{sp.escape("correction-" + row["id"])}"><h2>'
                 + _link(_correction_url(row), row['summary']) + '</h2><dl class="r-facts">'
                 f'<dt>Status</dt><dd>{sp.escape(row["status"].capitalize())}</dd>'
                 f'<dt>Edition</dt><dd>{sp.escape(row["edition_id"])}</dd>'
                 f'<dt>Claim</dt><dd>{sp.escape(row["claim_id"])}</dd>'
                 f'<dt>Corrected</dt><dd><time datetime="{stamp}">{stamp}</time></dd></dl>'
                 '<h3>Supporting evidence</h3><ul>'
                 + ''.join('<li>' + _link(url, url) + '</li>' for url in row['evidence_urls']) + '</ul></article>')
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
                       f'Status: {row["status"]}. {row["summary"]} Evidence: ' + ' '.join(row['evidence_urls']))
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
        modified = max(_day(context['graph']['as_of']), context['report']['updated_on'],
                       *(_day(row.get('as_of')) for row in assertions))
        def update_page_date(match):
            nonlocal modified
            node = json.loads(match.group(2))
            def update(value):
                nonlocal modified
                if isinstance(value, dict):
                    if value.get('@id') == canonical and value.get('@type') in {'WebPage', 'ProfilePage'}:
                        modified = max(modified, _day(value.get('dateModified')))
                        value['dateModified'] = modified
                    for child in value.values():
                        update(child)
                elif isinstance(value, list):
                    for child in value:
                        update(child)
            update(node)
            return match.group(1) + sp.json_ld(node) + match.group(3)
        text = re.sub(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)', update_page_date, original, flags=re.S)
        section = ('<!-- research-supplement:start --><section class="research r-company-supplement" id="new-research-evidence">'
                   '<h2>New research evidence</h2><p class="r-meta">Research evidence snapshot '
                   + _date(context['graph']['as_of']) + ' · Added assessment ' + _date(context['report']['updated_on']) + '</p>'
                   '<p>These approved assertions supplement the historical profile. Each retains its own evidence date, scope and qualifications. '
                   'They do not establish commercial quality or an unstated supplier contribution.</p>'
                   + ''.join(_assertion(context, assertion) for assertion in assertions)
                   + '</section><!-- research-supplement:end -->')
        text = re.sub(r'<!-- research-supplement:start -->.*?<!-- research-supplement:end -->', '', text, flags=re.S)
        text = text.replace('</main>', section + '</main>', 1)
        if '<link rel="stylesheet" href="/research.css">' not in text:
            text = text.replace('</head>', '<link rel="stylesheet" href="/research.css">\n</head>', 1)
        target.write_text(text, encoding='utf-8')
        records.append({'path': path, 'lastmod': modified})
    if records:
        (output / 'research.css').write_bytes((ROOT / 'web/research.css').read_bytes())
    return records


def write_research_pages(output, context):
    """Write static research HTML, its stylesheet and publication-only feeds.

    Return sitemap-ready {path, lastmod} records for HTML pages only. Paths are
    site-relative and begin with '/'. Existing legacy company HTML is untouched.
    """
    output = Path(output)
    modified = max(context["report"]["updated_on"], _day(context["graph"]["as_of"]))
    editions = _published_editions(context)
    corrections = _correction_records(context)
    pages = [("/research/", "Human data research", "Public-source research connecting AI data suppliers, papers, datasets, benchmarks, and workflows, with visible evidence and coverage.", _hub(context, editions), "CollectionPage", None),
             (REPORT_PATH, context["report"]["title"], context["report"].get("summary", "Research methods and findings."), _report(context), "TechArticle", None),
             ("/research/data/", "Research data & evidence", "Versioned research data, source and assertion permalinks, publication progress, citations, and reproducible downloads.", _data(context), "CollectionPage", None),
             ("/review/", "Review & correct the research", "Contribute a source-backed correction, scoped review, or public reuse of ScienceToStartup research.", _review(context), "WebPage", None),
             (CORRECTIONS_PATH, "Research corrections", "Accepted research corrections, with affected editions, claims, correction dates and supporting evidence.", _corrections_page(context, corrections), "CollectionPage", None)]
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
        records.append({"path": path, "lastmod": modified})
    for path, snapshot in editions:
        target = output / path.lstrip('/') / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        def edition_links(text):
            # Evidence on an immutable edition must not silently resolve to this
            # week's changed assertions or downloads.
            text = text.replace('/research/data/#', path + 'data/#')
            archive = _safe_url(snapshot['report'].get('archive', {}).get('record_url'))
            if archive:
                text = re.sub(r'href="/(?:publication|research/exports)/[^\"]+"', 'href="' + sp.escape(archive) + '"', text)
            return text
        target.write_text(edition_links(_render(snapshot, snapshot['report']['title'], snapshot['report'].get('summary', ''), path,
                                  _report(snapshot, edition=True), 'TechArticle')), encoding='utf-8')
        records.append({"path": path, "lastmod": snapshot['report']['updated_on']})
        ledger_path = path + 'data/'
        ledger = output / ledger_path.lstrip('/') / 'index.html'
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(edition_links(_render(snapshot, 'Edition evidence and sources', 'Frozen assertion and source records for this exact archived edition.',
                                               ledger_path, _data(snapshot), 'CollectionPage')), encoding='utf-8')
        records.append({"path": ledger_path, "lastmod": snapshot['report']['updated_on']})
    (output / 'research.css').write_bytes((ROOT / 'web/research.css').read_bytes())
    (output / 'research-index.js').write_bytes((ROOT / 'web/research-index.js').read_bytes())
    _feeds(output, context, editions)
    _correction_feeds(output, context, corrections)
    return records


def research_search_entries(context):
    """Compact local-search records; candidate wording never enters summaries."""
    entries = [
        {"title": "Human data research", "summary": "Research evidence, publication progress, methods, and open data.", "url": "/research/", "kind": "research", "keywords": "AI data labs human feedback evidence"},
        {"title": context["report"]["title"], "summary": _status(context) + ". Twelve chapters of methods, historical examples, and research gaps.", "url": REPORT_PATH, "kind": "report", "keywords": "human feedback RLHF annotation suppliers methods"},
        {"title": "Research data & evidence", "summary": "Coverage, assertion and source records, citations, and versioned downloads.", "url": "/research/data/", "kind": "data", "keywords": "JSON CSV SQLite citation sources provenance"},
        {"title": "Review & correct the research", "summary": "Submit a source-backed correction, scoped review, or public reuse.", "url": "/review/", "kind": "review", "keywords": "correction contribute review reuse"},
        {"title": "Research corrections", "summary": "Accepted corrections with affected editions, claims, correction dates and source evidence.", "url": CORRECTIONS_PATH, "kind": "review", "keywords": "corrections errata RSS Atom evidence"},
    ]
    for slug, title, kinds, description in CATEGORIES:
        entries.append({"title": title, "summary": description, "url": '/research/' + slug + '/', "kind": "research", "keywords": title.lower()})
    for entity in sorted(context['graph']['entities'], key=lambda row: row['id']):
        category = _category(entity)
        approved_org = _new_company(context, entity)
        if category or approved_org:
            entries.append({"title": entity['name'], "summary": _label(entity) + '. Inspect source metadata and assertion-specific qualifications.',
                            "url": entity_url(entity, context), "kind": category[0][:-1] if category else 'company',
                            "keywords": ' '.join([entity['id']] + entity.get('aliases', []) + list(entity.get('identifiers', {}).values()))})
    return entries
