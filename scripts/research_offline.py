"""Readable, script-free evidence appendix from the public package projection.

This renderer adds no research judgments. It displays recorded scope, dates and
review provenance, and deliberately does not reproduce third-party source text.
It has no dependency on the live-site renderer or publication module.
"""
from __future__ import annotations

import html
import json
from urllib.parse import quote, urlsplit


def evidence_href(kind, stable_id):
    return "evidence.html#" + quote(kind + "-" + str(stable_id), safe="._-")


def _escape(value):
    return html.escape(str(value), quote=True)


def _link(kind, stable_id, label=None):
    return '<a href="' + _escape(evidence_href(kind, stable_id)) + '">' + _escape(label if label is not None else stable_id) + '</a>'


def _value(value):
    """Keep nulls and structured financial/operational scope explicit."""
    if value is None:
        return "Not stated in the source"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return '<ul>' + ''.join('<li>' + _value(item) + '</li>' for item in value) + '</ul>' if value else "None recorded"
    if isinstance(value, dict):
        return '<dl>' + ''.join('<dt>' + _escape(key.replace('_', ' ').capitalize()) + '</dt><dd>' + _value(item) + '</dd>'
                               for key, item in sorted(value.items()) if key not in {'claim_class', 'company_entity_id', 'type'}) + '</dl>'
    return _escape(value)


def _statement(assertion, entities):
    subject = entities.get(assertion.get('subject_id'), {})
    value = assertion.get('value')
    if value is not None:
        text = value.get('value') if isinstance(value, dict) else value
        if isinstance(text, str):
            try:
                structured = json.loads(text)
            except (ValueError, RecursionError):
                structured = None
            if isinstance(structured, dict) and isinstance(structured.get('statement'), str) and structured['statement'].strip():
                details = {key: structured[key] for key in ('scope', 'reported_value_and_basis') if key in structured}
                return '<p>' + _escape(structured['statement']) + '</p>' + _value(details)
        return '<p>' + _escape(subject.get('name', assertion.get('subject_id'))) + ' · ' + _escape(assertion['predicate'].replace('_', ' ')) + ': ' + _value(text) + '</p>'
    obj = entities.get(assertion.get('object_id'), {})
    return '<p>' + _link('entity', assertion['subject_id'], subject.get('name', assertion['subject_id'])) + ' ' + _escape(assertion['predicate'].replace('_', ' ')) + ' ' + _link('entity', assertion['object_id'], obj.get('name', assertion['object_id'])) + '.</p>'


def _article(kind, stable_id, title, body):
    return '<article id="' + _escape(kind + '-' + stable_id) + '"><h3>' + _escape(title) + '</h3>' + body + '</article>'


def _source_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
            return '<a href="' + _escape(value) + '">' + _escape(value) + '</a>'
    except (TypeError, ValueError):
        pass
    return _escape(value)


def offline_appendix(projection):
    """Use only the already privacy-filtered public projection, without synthesis."""
    graph = projection['graph']
    entities = {row['id']: row for row in graph['entities']}
    assertions = sorted(graph['assertions'], key=lambda row: row['id'])
    by_entity = {eid: [] for eid in entities}
    for assertion in assertions:
        if assertion.get('status') in {'approved', 'historical'}:
            for eid in {assertion.get('subject_id'), assertion.get('object_id')} & entities.keys():
                by_entity[eid].append(assertion)
    rows = []
    for entity in sorted(entities.values(), key=lambda row: (row.get('name', '').casefold(), row['id'])):
        approved = [row for row in by_entity[entity['id']] if row['status'] == 'approved']
        if entity.get('status') != 'approved' or not approved:
            continue
        facets = {key: value for key, value in sorted(entity.get('taxonomy', {}).items()) if value}
        rows.append('<tr><th scope="row">' + _link('entity', entity['id'], entity['name']) + '</th><td>' + _escape(entity['kind'].replace('_', ' ')) + '</td><td>' + _escape(entity.get('review_depth', 'Not recorded').replace('_', ' ')) + '</td><td>' + (_value(facets) if facets else 'Not recorded') + '</td><td>' + ', '.join(_link('assertion', row['id']) for row in approved) + '</td></tr>')
    body = ['<h1>Offline evidence appendix</h1>', '<p>Release ' + _escape(projection['release_id']) + ' · Evidence snapshot ' + _escape(projection['as_of']) + '</p>',
            '<nav aria-label="Offline edition"><a href="report.html">Report</a> · <a href="#comparison">Recorded scope comparison</a> · <a href="#dossiers">Entity dossiers</a> · <a href="#assertions">Assertions</a> · <a href="#sources">Sources</a> · <a href="#reviews">Review receipts</a></nav>',
            '<p>This appendix transcribes approved records and explicitly dated historical descriptions. The comparison describes recorded scope; it provides no supplier ranking, performance evaluation, inferred capability, or independent replication. Missing information remains unknown. Candidates are excluded from findings. Source bodies, contact details and third-party media are excluded.</p>',
            '<section id="comparison"><h2>Recorded scope comparison</h2><p>Approved entities with approved evidence. Follow an evidence ID to inspect its dates, qualifications and source bindings.</p><div class="table"><table><thead><tr><th>Entity</th><th>Kind</th><th>Recorded review depth</th><th>Recorded facets</th><th>Approved evidence</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></section>',
            '<section id="dossiers"><h2>Entity dossiers</h2>']
    for entity in sorted(entities.values(), key=lambda row: row['id']):
        details = {key: entity.get(key) for key in ('kind', 'status', 'review_depth', 'disposition', 'disposition_reason', 'identifiers', 'parent_id', 'family_id', 'taxonomy')}
        evidence = ', '.join(_link('assertion', row['id'], row['id'] + ' (' + row['status'] + ')') for row in by_entity[entity['id']])
        body.append(_article('entity', entity['id'], entity['name'], _value(details) + '<p>Evidence: ' + (evidence or 'No approved or historical assertion recorded.') + '</p>'))
    body.append('</section><section id="assertions"><h2>Assertions and qualifications</h2>')
    for assertion in assertions:
        evidence = '<ul>' + ''.join('<li>' + _link('source', item['source_id']) + ' · Locator: ' + _escape(item.get('locator', 'Not recorded')) + ' · Excerpt SHA-256: ' + _escape(item.get('excerpt_sha256') or 'Not recorded') + '</li>' for item in assertion.get('evidence', [])) + '</ul>'
        reviews = ', '.join(_link('review', rid) for rid in assertion.get('review_ids', [])) or 'No fresh research review claimed.'
        approved_or_historical = assertion.get('status') in {'approved', 'historical'}
        content = _statement(assertion, entities) + '<h4>Qualifications</h4>' + _value(assertion.get('qualifications', [])) if approved_or_historical else '<p>Unapproved wording is withheld from findings.</p>'
        body.append(_article('assertion', assertion['id'], assertion['id'], '<p><strong>' + _escape(assertion['status'].capitalize()) + '</strong> · As of ' + _escape(assertion.get('as_of', 'Not recorded')) + ' · Provenance: ' + _escape(assertion.get('provenance_kind', 'Not recorded')) + '</p>' + content + '<h4>Source bindings</h4>' + evidence + '<p>Review receipts: ' + reviews + '</p>'))
    body.append('</section><section id="sources"><h2>Source metadata</h2><p>URLs are citations for optional consultation. Reading this appendix needs no connection; source bodies and excerpts are not reproduced here.</p>')
    for source in sorted(graph['sources'], key=lambda row: row['id']):
        details = {key: source.get(key) for key in ('publisher', 'source_type', 'status', 'version', 'published_on', 'captured_on', 'locator', 'response_sha256', 'excerpt_sha256', 'license')}
        body.append(_article('source', source['id'], source['title'], '<p>' + _source_url(source.get('url', '')) + '</p>' + _value(details)))
    body.append('</section><section id="reviews"><h2>Recorded review receipts</h2><p>Receipts describe actual recorded scope and reviewer type; AI review is not human peer review.</p>')
    for review in sorted(graph.get('reviews', []), key=lambda row: row['id']):
        details = {key: review.get(key) for key in ('role', 'reviewer', 'reviewer_type', 'invocation_id', 'reviewed_on', 'verdict', 'method', 'note', 'assertion_sha256')}
        body.append(_article('review', review['id'], review['id'], _value(details) + '<p>Assertions: ' + ', '.join(_link('assertion', aid) for aid in review.get('assertion_ids', [])) + '</p><p>Sources: ' + ', '.join(_link('source', sid) for sid in review.get('source_ids', [])) + '</p>'))
    body.append('</section>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Offline evidence appendix</title><style>body{max-width:100ch;margin:3rem auto;padding:0 1rem;font:17px/1.6 system-ui;color:#18312c}h1,h2,h3{line-height:1.25}h2{margin-top:3rem}article{border-top:1px solid #ccd6d0;padding:1rem 0}p,dd,td,th{overflow-wrap:anywhere}dt{font-weight:600}dd{margin:0 0 .5rem 1rem}.table{overflow-x:auto}table{border-collapse:collapse;width:100%}td,th{padding:.6rem;border:1px solid #ccd6d0;text-align:left;vertical-align:top}a{color:#125b4b}nav{margin:1.5rem 0}@media print{body{font-size:10pt}.table{overflow:visible}}</style></head><body><main>' + '\n'.join(body) + '</main></body></html>\n').encode('utf-8')
