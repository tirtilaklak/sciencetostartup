"""A short, offline executive briefing from the same reviewed report findings."""
from __future__ import annotations

import html
import re

try:
    from research_findings import executive_findings, finding_anchor, field_text
    from research_offline import evidence_href
except ImportError:
    from scripts.research_findings import executive_findings, finding_anchor, field_text
    from scripts.research_offline import evidence_href


def _line(value):
    return ' '.join(str(value).splitlines())


def _markdown(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!>~|])', r'\\\1', html.escape(_line(value), quote=False))


def executive_brief_assets(context, metadata):
    # Imported at call time so the publication writer can use this renderer
    # without an import cycle. It is also safe when called directly for QA.
    try:
        from research_citations import privacy_filter
    except ImportError:
        from scripts.research_citations import privacy_filter

    context = {**context, 'report': privacy_filter(context['report'])}
    metadata = privacy_filter(metadata)
    findings, withheld = executive_findings(context)
    escape = lambda value: html.escape(_line(value), quote=True)
    title = 'Executive brief · ' + metadata['title']
    status = metadata['status'] + ' · ' + metadata['version'] + ' · ' + metadata['updated_on']
    body = ['<h1>' + escape(title) + '</h1>', '<p>' + escape(status) + '</p>',
            '<p>' + escape(metadata['note']) + '</p>',
            '<nav aria-label="Edition"><a href="report.html">Complete report and reasoning</a> · '
            '<a href="evidence.html">Evidence and review receipts</a></nav>']
    lines = ['# ' + _markdown(title), '', _markdown(status), '', _markdown(metadata['note']), '',
             '[Complete report](report.html) · [Evidence and review receipts](evidence.html)', '']
    coverage = context.get('gate', {}).get('coverage', {})
    labels = (('legacy_inclusion_audits', 'organization inclusion audits'),
              ('qualifying_suppliers', 'qualifying suppliers'), ('reviewed_papers', 'paper works'),
              ('dataset_families', 'dataset families'), ('benchmark_families', 'benchmark families'))
    recorded = ', '.join(str(coverage[key]) + ' ' + label for key, label in labels if key in coverage)
    if recorded:
        note = 'Reviewed coverage: ' + recorded + '. Counts describe this publication’s scope; they do not establish a market census or provider performance.'
        body.append('<p class="scope">' + escape(note) + '</p>')
        lines.extend([_markdown(note), ''])
    fields = (('buyer_implication', 'Buyer implication'), ('confidence', 'Confidence'), ('limitations', 'Limits'))
    for number, finding in enumerate(findings, 1):
        anchor = finding_anchor(finding)
        label = str(number) + '. ' + finding['id'].replace('-', ' ').capitalize()
        body.extend(['<article id="' + escape(anchor) + '"><h2>' + escape(label) + '</h2>',
                     '<p>' + escape(field_text(finding['text'])) + '</p>'])
        lines.extend(['## ' + _markdown(label), '', _markdown(field_text(finding['text'])), ''])
        for key, field_label in fields:
            value = field_text(finding.get(key))
            if value:
                body.append('<p><strong>' + field_label + ':</strong> ' + escape(value) + '</p>')
                lines.extend([field_label + ': ' + _markdown(value), ''])
        links = [(str(index), evidence_href('assertion', cid)) for index, cid in enumerate(finding['claim_ids'], 1)]
        body.append('<p class="evidence">Approved evidence: ' + ', '.join(
            '<a href="' + escape(url) + '">' + label + '</a>' for label, url in links)
            + ' · <a href="report.html#' + escape(anchor) + '">Full reasoning and what would change this finding</a></p></article>')
        lines.extend(['Approved evidence: ' + ', '.join('[' + label + '](' + url + ')' for label, url in links), '',
                      '[Full reasoning and what would change this finding](report.html#' + anchor + ')', ''])
    if withheld:
        note = 'Executive findings are awaiting separate evidence and adversarial AI review. Their draft wording is withheld from this briefing.'
        body.append('<p class="scope">' + note + '</p>')
        lines.extend([note, ''])
    if not findings and not withheld:
        body.append('<p>No executive findings are recorded for this snapshot.</p>')
        lines.extend(['No executive findings are recorded for this snapshot.', ''])
    cite = metadata['author'] + '. ' + metadata['title'] + '. ' + metadata['version'] + '. ' + metadata['updated_on'] + '.'
    if metadata.get('doi'):
        cite += ' DOI: ' + metadata['doi'] + '.'
    body.extend(['<footer><h2>Citation and scope</h2><p>' + escape(cite) + '</p>',
                 '<p>This brief summarizes the report’s analytical judgments. Consult the full report for methods, '
                 'supporting observations, alternatives and limitations. Separate AI review is not human peer review. '
                 'Source publication, capture and substantive review dates remain distinct.</p></footer>'])
    lines.extend(['## Citation and scope', '', _markdown(cite), '',
                  'Consult the full report for methods, supporting observations, alternatives and limitations. '
                  'Separate AI review is not human peer review. Source publication, capture and substantive review dates remain distinct.', ''])
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width"><title>' + escape(title) + '</title>'
            '<style>body{max-width:76ch;margin:3rem auto;padding:0 1rem;font:17px/1.55 system-ui;'
            'color:#18312c;overflow-wrap:anywhere}h1,h2{line-height:1.2}h2{font-size:1.2em}'
            'article{border-top:1px solid #ccd6d0;margin-top:1.6rem;padding-top:.4rem}'
            '.scope{padding:.8rem;background:#eef3ef}.evidence,footer{font-size:.9em}'
            'a{color:#125b4b}nav{margin:1rem 0}footer{margin-top:2rem}'
            '@page{size:A4;margin:18mm}@media print{body{max-width:none;margin:0;padding:0;font-size:10pt}'
            'h2{break-after:avoid}article{break-inside:avoid}.scope{background:none}}</style></head>'
            '<body><main>' + '\n'.join(body) + '</main></body></html>\n')
    return {'executive-brief.html': page.encode(), 'executive-brief.md': '\n'.join(lines).encode()}
