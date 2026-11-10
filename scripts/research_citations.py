"""Offline, deterministic citation and archive preparation. Never publishes.

The canonical release is an input, not an output. New exports deliberately have
their own projection version and remove legacy contact/privacy exceptions.
"""
from __future__ import annotations

import csv
import copy
from datetime import datetime
import hashlib
import html
import io
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import shutil
import tempfile
from urllib.parse import quote
import zipfile

try:
    from research_findings import executive_findings, finding_anchor, field_text, JUDGMENT_FIELDS, WITHHELD, paragraph_supported, WITHHELD_PARAGRAPH
    from research_offline import evidence_href, offline_appendix
    from research_corrections import public_corrections
except ImportError:
    from scripts.research_findings import executive_findings, finding_anchor, field_text, JUDGMENT_FIELDS, WITHHELD, paragraph_supported, WITHHELD_PARAGRAPH
    from scripts.research_offline import evidence_href, offline_appendix
    from scripts.research_corrections import public_corrections

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_VERSION = "1.0.0"
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}", re.I)
PRIVATE_KEY = re.compile(r"(?:^|_)(?:email|phone|secret|token|raw_body|cache_path|credential)(?:$|_)", re.I)
LOCAL_PATH = re.compile(r"^(?:file://|/(?:Users|home|private|tmp|var/folders)/|[A-Za-z]:[\\/]|\\\\)", re.I)
SECRET = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
PRIVATE_KEYS = {"email", "personal_email", "contact_email", "phone", "telephone",
                "raw_inputs", "raw_cache", "raw_response", "response_body", "source_quote",
                "full_text", "credentials", "access_token", "api_key"}
DOI = re.compile(r"10\.\d{4,9}/\S+")
RESERVATION_FIELDS = ("reserved_doi", "deposition_id", "api_origin", "environment")
# Cloudflare Workers Static Assets: 25 MiB per file on both Free and Paid.
# https://developers.cloudflare.com/workers/platform/limits/#static-assets
STATIC_ASSET_LIMIT_BYTES = 25 * 1024 * 1024
ARCHIVE_COMPRESSION = {"stored": zipfile.ZIP_STORED, "deflate": zipfile.ZIP_DEFLATED}
LIVE_PACKAGE_FILES = {"package-status.json", "current-metadata.json", "current-CITATION.cff",
                      "current-citation.bib", "current-citation.ris", "current-citation.csl.json"}
CONTEXT_CONTRACT_VERSION = 3
REPRODUCTION_INPUTS_V2 = {name: "schema/" + name for name in (
    "research-graph.schema.json", "report.schema.json", "report-review.schema.json",
    "report-audit.schema.json", "publication-projection.schema.json", "publication-metadata.schema.json")}
REPRODUCTION_INPUTS_V2.update({"research_graph.py": "scripts/research_graph.py",
    "reproduce.py": "scripts/reproduce_research_package.py", "LICENSE": "LICENSE", "LICENSE-DATA.md": "LICENSE-DATA.md"})
REPRODUCTION_INPUTS = {**REPRODUCTION_INPUTS_V2, "LOCATORS.md": "docs/research/locators.md",
    "research_corrections.py": "scripts/research_corrections.py",
    "research-corrections.schema.json": "schema/research-corrections.schema.json",
    "DejaVuSans.ttf": "data/research/fonts/DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf": "data/research/fonts/DejaVuSans-Bold.ttf",
    "DejaVu-LICENSE.txt": "data/research/fonts/LICENSE",
    "DejaVu-PROVENANCE.json": "data/research/fonts/provenance.json",
    "ScienceToStartupCJKSubset.ttf": "data/research/fonts/ScienceToStartupCJKSubset.ttf",
    "CJK-OFL.txt": "data/research/fonts/CJK-OFL.txt",
    "CJK-PROVENANCE.json": "data/research/fonts/cjk-provenance.json"}
PREPARED_REGISTRY = "data/research/prepared-packages.json"


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def privacy_filter(value):
    """Copy public structured data; omit raw text/contact fields and redact emails.

    Redaction is intentionally broader than the one known legacy exception. No
    exception list can silently allow new personal contact details into archives.
    """
    if isinstance(value, dict):
        return {key: privacy_filter(item) for key, item in sorted(value.items())
                if key.lower() not in PRIVATE_KEYS and not PRIVATE_KEY.search(key)
                and not (isinstance(item, str) and (key.lower() == "path" or key.lower().endswith("_path"))
                         and LOCAL_PATH.match(item))}
    if isinstance(value, list):
        return [privacy_filter(item) for item in value]
    if isinstance(value, str):
        return SECRET.sub("[credential removed]", EMAIL.sub("[contact removed]", value))
    return value


def public_projection(context, canonical=None):
    root = Path(context.get("root", ROOT))
    canonical = canonical if canonical is not None else json.loads((root / "data/canonical.json").read_text())
    graph = context["graph"]
    return privacy_filter({"schema_version": 1, "projection_version": PROJECTION_VERSION,
                           "release_id": context["report"]["release_id"],
                           "as_of": graph["as_of"],
                           "canonical_dataset_version": canonical["dataset_version"],
                           "privacy": {"contact_details": "removed", "raw_source_text": "excluded",
                                       "canonical_unchanged": True},
                           "canonical": canonical, "graph": _public_graph(graph)})


def _public_graph(graph):
    # The graph owner chooses public records; missing validation must fail closed.
    try:
        from research_graph import public_graph
    except ImportError:
        from scripts.research_graph import public_graph
    return public_graph(graph)


def projection_rows(projection):
    """Lossless relational representation shared by the CSV and SQLite exports."""
    rows = []
    for namespace in sorted(projection):
        value = projection[namespace]
        members = value.items() if namespace in ("canonical", "graph") else [("", value)]
        for key, item in sorted(members):
            collection = namespace + ("." + key if key else "")
            kind = "array" if isinstance(item, list) else "value"
            rows.append((collection, -1, kind, ""))
            for position, record in enumerate(item if kind == "array" else [item]):
                rows.append((collection, position, "record", json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)))
    return rows


def projection_from_rows(rows):
    result, collections = {}, {}
    for collection, position, kind, value_json in rows:
        if int(position) == -1:
            collections[collection] = {"kind": kind, "values": {}}
        else:
            collections[collection]["values"][int(position)] = json.loads(value_json)
    for collection, info in collections.items():
        values = [info["values"][i] for i in sorted(info["values"])]
        value = values if info["kind"] == "array" else values[0]
        if collection.startswith(("canonical.", "graph.")):
            namespace, key = collection.split(".", 1)
            result.setdefault(namespace, {})[key] = value
        else:
            result[collection] = value
    return result


def write_projection(projection, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "clean-dataset.json").write_bytes(json_bytes(projection))
    rows = projection_rows(projection)
    with (output / "clean-dataset.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["collection", "position", "kind", "value_json"])
        writer.writerows(rows)
    target = output / "clean-dataset.sqlite"
    target.unlink(missing_ok=True)
    with sqlite3.connect(target) as database:
        database.execute("PRAGMA page_size=4096")
        database.execute("PRAGMA secure_delete=ON")
        database.execute("CREATE TABLE projection_rows (collection TEXT NOT NULL, position INTEGER NOT NULL, kind TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY (collection, position))")
        database.executemany("INSERT INTO projection_rows VALUES (?, ?, ?, ?)", rows)
        database.execute("PRAGMA user_version=1")
        database.commit()
        observed = database.execute("SELECT collection, position, kind, value_json FROM projection_rows ORDER BY collection, position").fetchall()
    database.close()
    # The SQLite writer version is informational; normalize it exactly as the
    # existing canonical exporter does for byte-identical cross-runtime builds.
    with target.open('r+b') as stream:
        stream.seek(96)
        stream.write(b'\x00' * 4)
    with (output / "clean-dataset.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.reader(stream))[1:]
    if projection_from_rows(observed) != projection or projection_from_rows(csv_rows) != projection:
        raise ValueError("Public JSON, CSV and SQLite projections differ")
    return ["clean-dataset.json", "clean-dataset.csv", "clean-dataset.sqlite"]


def publication_metadata(context):
    report, gate = context["report"], context["gate"]
    identity = context.get("identity", {})
    archive = report.get("archive", {})
    # Reservation belongs in a clearly labelled note, never a registered-DOI
    # field. Actual publication is a separate receipt outside the frozen bundle.
    published = bool(gate.get("ready") and published_archive(context))
    status = "published" if published else ("ready-for-archive" if gate.get("archival_ready", gate.get("ready")) else "prelaunch")
    author = identity.get("publisher", {}).get("name") or identity.get("display_name") or identity.get("name") or "ScienceToStartup"
    if isinstance(author, dict):
        author = author.get("name", "ScienceToStartup")
    metadata = {"schema_version": 1, "title": report["title"], "version": report["release_id"],
                "author": str(author), "url": "https://sciencetostartup.com/research/state-of-ai-data-labs/",
                "updated_on": report["updated_on"], "status": status,
                "license": "CC-BY-4.0", "projection_version": PROJECTION_VERSION,
                "note": "Published archived edition." if published else
                        "Preparation snapshot; not a published research edition. No DOI has been registered for this snapshot."}
    publisher = identity.get("publisher", {})
    if (publisher.get("type") == "Person" and publisher.get("given_names") and publisher.get("family_names")):
        metadata["author_person"] = {"given": publisher["given_names"], "family": publisher["family_names"]}
    if published:
        metadata.update(doi=archive["doi"], url=archive["record_url"])
        if archive.get("published_on"):
            metadata["published_on"] = archive["published_on"]
    elif DOI.fullmatch(archive.get("reserved_doi") or ""):
        metadata["note"] += " Reserved version DOI (not registered): " + archive["reserved_doi"] + "."
    return privacy_filter(metadata)


def _bib(value):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "&": r"\&", "_": r"\_", "#": r"\#"}
    return "".join(replacements.get(char, char) for char in str(value).replace("\n", " "))


def citation_formats(metadata):
    m = metadata
    person = m.get("author_person")
    if person and person.get("given") and person.get("family"):
        bib_author = _bib(person["given"]) + " " + _bib(person["family"])
        ris_author = person["family"] + ", " + person["given"]
        csl_author = {"given": person["given"], "family": person["family"]}
        cff_author = {"given-names": person["given"], "family-names": person["family"]}
    else:
        bib_author = "{" + _bib(m["author"]) + "}"
        ris_author = m["author"]
        csl_author = {"literal": m["author"]}
        cff_author = {"name": m["author"]}
    fields = [("title", m["title"]), ("author", m["author"]),
              ("version", m["version"]), ("url", m["url"]), ("note", m["note"])]
    if m.get("doi"):
        fields.append(("doi", m["doi"]))
        if m.get("published_on"):
            fields.append(("year", m["published_on"][:4]))
    bibtex = "@misc{sciencetostartup_" + re.sub(r"[^a-zA-Z0-9]", "_", m["version"]) + ",\n"
    bibtex += ",\n".join("  " + key + " = {" + (_bib(value) if key != "author" else bib_author) + "}" for key, value in fields) + "\n}\n"
    ris = ["TY  - RPRT", "TI  - " + m["title"], "AU  - " + ris_author, "UR  - " + m["url"], "N1  - " + m["note"], "ET  - " + m["version"]]
    if m.get("doi"):
        ris.append("DO  - " + m["doi"])
        if m.get("published_on"):
            ris.append("PY  - " + m["published_on"][:4])
    ris.extend(["ER  - ", ""])
    csl = {"id": "sciencetostartup-" + m["version"], "type": "report", "title": m["title"],
           "author": [csl_author], "URL": m["url"], "version": m["version"], "note": m["note"]}
    cff = {"cff-version": "1.2.0", "message": m["note"], "title": m["title"], "type": "dataset",
           "authors": [cff_author], "url": m["url"], "version": m["version"], "license": m["license"]}
    if m.get("doi"):
        csl["DOI"], cff["doi"] = m["doi"], m["doi"]
        if m.get("published_on"):
            csl["issued"] = {"date-parts": [[int(x) for x in m["published_on"].split("-")]]}
            cff["date-released"] = m["published_on"]
    # JSON is a YAML 1.2 subset and keeps escaping and Unicode deterministic.
    return {"citation.bib": bibtex.encode(), "citation.ris": "\n".join(ris).encode(),
            "citation.csl.json": json_bytes(csl), "CITATION.cff": json_bytes(cff)}


def report_markdown(context):
    # Filter before Markdown escaping can split an email or credential pattern.
    context = {**context, 'report': privacy_filter(context['report'])}
    report, gate = context["report"], context["gate"]
    lines = ["# " + report["title"], "", "Release: " + report["release_id"],
             "Updated: " + report["updated_on"], "Status: " + publication_metadata(context)["status"], "",
             "## Readiness and limitations", ""]
    lines.extend("- " + str(reason) for reason in gate.get("reasons", []))
    lines.extend(["", "Coverage:", "", "```json", json.dumps(gate.get("coverage", {}), sort_keys=True, indent=2), "```", ""])
    for section in report.get("sections", []):
        lines.extend(["## " + section["title"], ""])
        for paragraph in section.get("paragraphs", []):
            if not paragraph_supported(context, paragraph):
                lines.extend(["[research_gap] " + WITHHELD_PARAGRAPH, ""])
                continue
            lines.extend(["[" + paragraph.get("kind", "analysis") + "] " + paragraph["text"], ""])
            if paragraph.get("claim_ids"):
                lines.extend(["Evidence IDs: " + ", ".join('[' + cid + '](' + evidence_href('assertion', cid) + ')' for cid in paragraph["claim_ids"]), ""])
        if section.get('id') == 'executive-assessment':
            findings, withheld = executive_findings(context)
            def safe(value):
                text = html.escape(' '.join(field_text(value).splitlines()), quote=False)
                return re.sub(r'([\\`*_{}\[\]()#+.!>~|])', r'\\\1', text)
            for finding in findings:
                lines.extend(['<a id="' + finding_anchor(finding) + '"></a>',
                              '### Analytical judgment: ' + finding['id'], '', safe(finding['text']), ''])
                for key, label in JUDGMENT_FIELDS:
                    if field_text(finding.get(key)):
                        lines.extend([label + ': ' + safe(finding[key]), ''])
                lines.extend(['Approved evidence: ' + ', '.join(
                    '[' + cid + '](' + evidence_href('assertion', cid) + ')'
                    for cid in finding['claim_ids']), ''])
            if withheld:
                lines.extend([WITHHELD, ''])
    lines.extend(["## Evidence and reproduction", "", "The accompanying clean-dataset.json, CSV and SQLite contain the same versioned public projection. Canonical dataset 2.5.0 remains unchanged outside this archive. Contact details and raw source text are excluded from this projection. Review receipts describe actual scope. corrections.json records accepted correction metadata and approved replacements; evidence.html preserves superseded IDs without unapproved wording. Candidate assertions and metadata-only discoveries are excluded from approved evidence; completed inclusion audits may leave commercial qualification unresolved.", "",
                  "Open evidence.html for offline entity dossiers, a recorded-scope comparison table, assertions, source bindings and review receipts. Use MANIFEST.json to verify each file's SHA-256. The archive is self-contained and makes no network requests. Source URLs and identifiers are retained in the accompanying public graph.", ""])
    return privacy_filter("\n".join(lines))


def offline_html(context):
    # Render owned structured blocks directly. Source text is never parsed as
    # Markdown or HTML, and privacy applies to titles as well as body content.
    clean = privacy_filter({"report": context["report"], "gate": context["gate"]})
    context = {**context, **clean}
    report, gate = clean["report"], clean["gate"]
    escape = lambda value: html.escape(str(value), quote=True)
    sections = report.get("sections", [])
    ids = [section.get("id") for section in sections]
    def chapter_anchor(section):
        identifier = section.get("id")
        return ("chapter-" + identifier if isinstance(identifier, str)
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}', identifier)
                and ids.count(identifier) == 1 else None)
    def evidence(ids):
        return '<p>Evidence IDs: ' + ', '.join('<a href="' + escape(evidence_href('assertion', cid))
            + '">' + escape(cid) + '</a>' for cid in ids) + '</p>'
    body = ['<h1>' + escape(report['title']) + '</h1>',
            '<p>Release: ' + escape(report['release_id']) + '<br>Updated: ' + escape(report['updated_on'])
            + '<br>Status: ' + escape(publication_metadata(context)['status']) + '</p>',
            '<nav aria-label="Offline edition"><a href="executive-brief.html">Executive brief</a> · '
            '<a href="evidence.html">Evidence appendix and recorded scope comparison</a></nav>',
            '<nav aria-label="Report chapters"><ol>' + ''.join(
                '<li><a href="#' + quote(chapter_anchor(section), safe='') + '">' + escape(section['title']) + '</a></li>'
                for section in sections if chapter_anchor(section)) + '</ol></nav>',
            '<section><h2>Readiness and limitations</h2>']
    body.extend('<p>' + escape(reason) + '</p>' for reason in gate.get('reasons', []))
    body.extend(['<pre>' + escape(json.dumps(gate.get('coverage', {}), sort_keys=True, indent=2)) + '</pre></section>'])
    for section in sections:
        anchor = chapter_anchor(section)
        body.append('<section' + (' id="' + escape(anchor) + '"' if anchor else '') + '><h2>' + escape(section['title']) + '</h2>')
        for paragraph in section.get('paragraphs', []):
            if not paragraph_supported(context, paragraph):
                body.append('<p>[research_gap] ' + WITHHELD_PARAGRAPH + '</p>')
                continue
            body.append('<p>[' + escape(paragraph.get('kind', 'analysis')) + '] '
                        + ('Historical example: ' if paragraph.get('historical') else '') + escape(paragraph['text']) + '</p>')
            if paragraph.get('claim_ids'):
                body.append(evidence(paragraph['claim_ids']))
        if section.get('id') == 'executive-assessment':
            findings, withheld = executive_findings(context)
            for finding in findings:
                body.extend(['<article id="' + escape(finding_anchor(finding)) + '"><h3>Analytical judgment: '
                             + escape(finding['id']) + '</h3>', '<p>' + escape(field_text(finding['text'])) + '</p>'])
                for key, label in JUDGMENT_FIELDS:
                    if field_text(finding.get(key)):
                        body.append('<p><strong>' + label + ':</strong> ' + escape(field_text(finding[key])) + '</p>')
                body.extend([evidence(finding['claim_ids']), '</article>'])
            if withheld:
                body.append('<p>' + WITHHELD + '</p>')
        body.append('</section>')
    body.extend(['<section><h2>Evidence and reproduction</h2>',
        '<p>The accompanying clean-dataset.json, CSV and SQLite contain the same versioned public projection. '
        'Canonical dataset 2.5.0 remains unchanged outside this archive. Contact details and raw source text are excluded. '
        'Candidate assertions and metadata-only discoveries are excluded from approved evidence. Historical records retain their real dates.</p>',
        '<p>Open evidence.html for offline entity dossiers, comparisons, assertions, source bindings and actual review receipts. '
        'Verify MANIFEST.json, then run <code>python3 reproduce.py --write-tables reproduced</code> to reproduce tables without the live site or network. '
        'LOCATORS.md explains source coordinates and extraction conventions.</p></section>'])
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'
            + escape(report['title']) + '</title><style>body{max-width:72ch;margin:3rem auto;padding:0 1rem;font:18px/1.6 system-ui;'
            'color:#18312c;overflow-wrap:anywhere}h1,h2,h3{line-height:1.2}h2{margin-top:2.5rem}pre{white-space:pre-wrap;'
            'font-size:.8em}nav ol{columns:2;padding-left:1.4rem}nav li{break-inside:avoid;margin-bottom:.4rem}'
            'a{color:#125b4b}@media(max-width:540px){nav ol{columns:1}}@media print{body{font-size:11pt;margin:0}h2,h3{break-after:avoid}}</style>'
            '</head><body><main>' + '\n'.join(body) + '</main></body></html>\n').encode()


def _source_path(root, relative):
    """Refuse symlinks in any source-selected path component below the root."""
    path = Path(root)
    if path.is_symlink():
        raise ValueError("Source paths cannot contain symlinks")
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Source paths cannot contain symlinks")
    return path


def reproduction_files(context, *, version=CONTEXT_CONTRACT_VERSION):
    """Owned scientific inputs, keyed by their exact archive member names.

    V2 and V3 require their complete versioned allowlists. Local paths
    and source file bodies never enter the context descriptors.
    """
    root = Path(context.get("root", ROOT))
    files = {}
    inputs = REPRODUCTION_INPUTS_V2 if version == 2 else REPRODUCTION_INPUTS
    for name, relative in sorted(inputs.items()):
        path = _source_path(root, relative)
        if not path.is_file():
            raise ValueError("Missing or unsafe owned reproduction input: " + name)
        files[name] = path.read_bytes()
    return files


def _contract_version(version):
    if type(version) is not int or version not in {1, 2, CONTEXT_CONTRACT_VERSION}:
        raise ValueError("Unsupported package context contract version")
    return version


def _research_source_context(context, *, reservation=True, version=CONTEXT_CONTRACT_VERSION):
    """Research/PDF inputs, without publication outcomes that depend on them.

    Keep every research gate metric/blocker and the reserved version identifier.
    Only lifecycle status, final archive blockers and actual receipts are omitted.
    This is also the canonical input to the frozen-package context contract.
    """
    _contract_version(version)
    value = copy.deepcopy({key: context[key] for key in ("graph", "report", "gate", "identity", "policy", "roles") if key in context})
    report, gate = value["report"], value["gate"]
    report.pop("status", None)
    report.pop("editions", None)  # Publication ledger, not report/PDF content.
    archive = report.pop("archive", {})
    report["archive"] = {key: archive[key] for key in RESERVATION_FIELDS
                         if reservation and archive.get("reserved_doi") and archive.get(key) is not None}
    archive_reasons = gate.pop("archive_reasons", [])
    gate["reasons"] = [reason for reason in gate.get("reasons", []) if reason not in archive_reasons]
    gate.pop("ready", None)
    gate.pop("status", None)
    if version >= 2:
        value["graph"] = _public_graph(context["graph"])
        # Preserve exact private input identity without redistributing draft
        # assertions, rejected wording or private extensions in any public graph.
        value["input_commitments"] = {"graph_sha256": sha256(json_bytes(context["graph"]))}
    if version >= 3:
        value["corrections"] = public_corrections(context)
        value["input_commitments"]["corrections_input_sha256"] = sha256(json_bytes(context.get("corrections", [])))
        # Commit to the original authoring input without redistributing held
        # paragraphs or unreviewed synthesis through this machine-readable file.
        value["input_commitments"]["report_input_sha256"] = sha256(json_bytes(report))
        held = 0
        for section in report.get("sections", []):
            for index, paragraph in enumerate(section.get("paragraphs", [])):
                if not paragraph_supported(context, paragraph):
                    section["paragraphs"][index] = {"kind": "research_gap", "text": WITHHELD_PARAGRAPH, "claim_ids": []}
                    held += 1
        findings, withheld = executive_findings(context)
        if "executive_findings" in report:
            report["executive_findings"] = findings
        value["publication_withholds"] = {"paragraphs": held, "executive_findings": withheld}
    return privacy_filter(value)


def source_context(context, *, reservation=True, version=CONTEXT_CONTRACT_VERSION):
    value = _research_source_context(context, reservation=reservation, version=version)
    if version >= 2:
        files = reproduction_files(context, version=version)
        value["package_context"] = {"context_contract_version": version,
            "graph_projection": "approved-historical-report-v1" if version >= 3 else "approved-historical-v1", "reproduction_inputs": {
                name: {"sha256": sha256(files[name]), "bytes": len(files[name])}
                for name in sorted(files)}}
    return value


def context_digest(context, *, version=CONTEXT_CONTRACT_VERSION):
    return sha256(json_bytes(source_context(context, version=version)))


def published_archive(context):
    """A typed production receipt, never a sandbox result or a reserved DOI."""
    archive = context["report"].get("archive", {})
    try:
        confirmation = datetime.fromisoformat(archive.get("confirmed_on", "").replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return False
    record_id = archive.get("record_id")
    return bool(archive.get("status") == "published" and archive.get("verified") is True
                and archive.get("api_origin") == "https://zenodo.org" and archive.get("environment") == "production"
                and confirmation.tzinfo is not None and confirmation.utcoffset() is not None
                and re.fullmatch(r"[0-9a-f]{64}", archive.get("artifact_sha256") or "")
                and archive.get("release_id") == context["report"]["release_id"]
                and type(record_id) is int and record_id > 0
                and archive.get("doi") == "10.5281/zenodo." + str(record_id)
                and isinstance(archive.get("concept_doi"), str) and DOI.fullmatch(archive["concept_doi"])
                and archive.get("doi") != archive.get("concept_doi")
                and (not archive.get("reserved_doi") or archive["reserved_doi"] == archive["doi"])
                and archive.get("record_url") == "https://zenodo.org/records/" + str(archive.get("record_id")))


def prepared_package_path(context):
    """Select only the edition's release directory or an explicit external path."""
    root = Path(context.get("root", ROOT)).resolve()
    release_id = context["report"]["release_id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", release_id):
        raise ValueError("Unsafe prepared release identifier")
    default = root / "data/research/releases" / release_id / "publication"
    supplied = context.get("prepared_package") or context["report"].get("archive", {}).get("bundle_path")
    path = Path(supplied) if supplied is not None else default
    if ".." in path.parts or (supplied is not None and not path.is_absolute()):
        raise ValueError("Prepared package path must be absolute and cannot traverse directories")
    resolved = path.resolve()
    allowed = {default, default.parent}
    if (resolved.is_relative_to(root) or path.is_relative_to(root)) and resolved not in allowed:
        raise ValueError("Prepared package must be inside this edition's release directory or explicitly outside the checkout")
    if path.is_symlink():
        raise ValueError("Prepared package path cannot contain symlinks")
    return resolved


def prepared_package_selection(context, root=None):
    """Return an optional committed-source selection overlay, verified before use.

    The registry is a pointer written only after a successful explicit freeze.
    It is never an input to its own context digest. An absent registry or absent
    release entry selects nothing; a selected missing/stale bundle fails closed.
    The coordinator can apply this overlay when constructing the build context.
    """
    root = Path(root if root is not None else context.get("root", ROOT)).absolute()
    registry = _source_path(root, PREPARED_REGISTRY)
    if not registry.exists():
        return {}
    if not registry.is_file():
        raise ValueError("Prepared package registry must be a regular file")
    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate prepared registry field")
            result[key] = value
        return result
    value = json.loads(registry.read_bytes(), object_pairs_hook=unique_pairs)
    if (not isinstance(value, dict) or set(value) != {"schema_version", "packages"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["packages"], list)):
        raise ValueError("Invalid prepared package registry")
    selected, seen = None, set()
    fields = {"release_id", "path", "context_contract_version", "context_sha256", "manifest_sha256", "archive_sha256"}
    for entry in value["packages"]:
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError("Invalid prepared package registry entry")
        release_id, relative = entry["release_id"], entry["path"]
        if (not isinstance(release_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", release_id)
                or release_id in seen):
            raise ValueError("Unsafe or duplicate prepared release identifier")
        seen.add(release_id)
        _contract_version(entry["context_contract_version"])
        if any(not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key])
               for key in ("context_sha256", "manifest_sha256", "archive_sha256")):
            raise ValueError("Prepared registry requires exact SHA-256 bindings")
        allowed = {"data/research/releases/" + release_id,
                   "data/research/releases/" + release_id + "/publication"}
        if not isinstance(relative, str) or relative not in allowed:
            raise ValueError("Prepared registry path must name its committed edition directory")
        path = _source_path(root, relative)
        if release_id == context["report"]["release_id"]:
            selected = {"prepared_package": str(path.absolute()), "prepared_package_expected": {
                key: entry[key] for key in fields - {"release_id", "path"}}}
    if selected is not None:
        read_prepared_package({**context, "root": root, **selected}, selected["prepared_package"])
    return selected or {}


def read_prepared_package(context, package, *, expected_archive_sha256=None):
    """Read and verify a frozen bundle without regenerating its PDF or ZIP."""
    package = Path(package).resolve()
    def read(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise ValueError("Unsafe package member")
        path = package / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe prepared file: " + name)
        return path.read_bytes()
    contract_blob, manifest_blob = read("PREPARED.json"), read("MANIFEST.json")
    contract, manifest = json.loads(contract_blob), json.loads(manifest_blob)
    version = _contract_version(contract.get("context_contract_version", 1))
    expected = context.get("prepared_package_expected", {})
    if expected and (not isinstance(expected, dict) or set(expected) != {
            "context_contract_version", "context_sha256", "manifest_sha256", "archive_sha256"}):
        raise ValueError("Invalid source-selected registry bindings")
    if (contract.get("schema_version") != 1 or manifest.get("schema_version") != 1
            or _contract_version(manifest.get("context_contract_version", 1)) != version
            or contract.get("release_id") != context["report"]["release_id"]
            or manifest.get("release_id") != contract["release_id"]
            or manifest.get("context_sha256") != contract["context_sha256"]):
        raise ValueError("Frozen package context or release identity does not match")
    if expected and any(contract.get(key, 1 if key == "context_contract_version" else None) != expected[key]
                        for key in ("context_contract_version", "context_sha256", "manifest_sha256", "archive_sha256")):
        raise ValueError("Frozen package differs from the source-selected registry bindings")
    if sha256(manifest_blob) != contract.get("manifest_sha256"):
        raise ValueError("Frozen package manifest changed")
    files = {"MANIFEST.json": manifest_blob}
    for name, descriptor in manifest["files"].items():
        if name in {"MANIFEST.json", "PREPARED.json", "research-archive.zip", "package-status.json"}:
            raise ValueError("A frozen manifest cannot contain its own receipt or archive")
        blob = read(name)
        if sha256(blob) != descriptor.get("sha256") or len(blob) != descriptor.get("bytes"):
            raise ValueError("Prepared package file changed: " + name)
        files[name] = blob
    expected = set(files) | {"PREPARED.json", "research-archive.zip"}
    if any(path.name not in expected | LIVE_PACKAGE_FILES or path.is_symlink() or not path.is_file()
           for path in package.iterdir()):
        raise ValueError("Unexpected or unsafe prepared package inventory")
    archive = read("research-archive.zip")
    if (sha256(archive) != contract.get("archive_sha256") or len(archive) != contract.get("archive_bytes")
            or (expected_archive_sha256 is not None and sha256(archive) != expected_archive_sha256)):
        raise ValueError("Frozen archive bytes changed or do not match the publication receipt")
    published = published_archive(context)
    receipt = context["report"].get("archive", {})
    if receipt.get("status") == "published" and not published:
        raise ValueError("Published frozen reuse requires a verified production archive receipt")
    if published and sha256(archive) != receipt["artifact_sha256"]:
        raise ValueError("Frozen archive does not match the exact published artifact receipt")
    source_blob = files.get("source-context.json")
    if source_blob is None or sha256(source_blob) != contract.get("context_sha256"):
        raise ValueError("Frozen source context differs from its context digest")
    if version >= 2:
        pinned_source = json.loads(source_blob)
        recipe = pinned_source.get("package_context") if isinstance(pinned_source, dict) else None
        if (not isinstance(recipe, dict) or set(recipe) != {"context_contract_version", "graph_projection", "reproduction_inputs"}
                or type(recipe["context_contract_version"]) is not int or recipe["context_contract_version"] != version
                or recipe["graph_projection"] != ("approved-historical-report-v1" if version >= 3 else "approved-historical-v1")
                or not isinstance(recipe["reproduction_inputs"], dict)
                or set(recipe["reproduction_inputs"]) != set(REPRODUCTION_INPUTS if version >= 3 else REPRODUCTION_INPUTS_V2)):
            raise ValueError("Frozen reproduction input allowlist differs from its versioned contract")
        for name, descriptor in recipe["reproduction_inputs"].items():
            if (not isinstance(descriptor, dict) or set(descriptor) != {"sha256", "bytes"}
                    or not isinstance(descriptor["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"])
                    or type(descriptor["bytes"]) is not int or descriptor["bytes"] < 0
                    or manifest["files"].get(name) != descriptor or name not in files
                    or sha256(files[name]) != descriptor["sha256"] or len(files[name]) != descriptor["bytes"]):
                raise ValueError("Frozen reproduction inputs differ from their context bindings")
        if published:
            # Only the typed production receipt plus its verified exact archive
            # permits historical recipe replay. The research core stays current
            # and exact; caller flags cannot select this path.
            expected_source = _research_source_context(context, version=version)
            expected_source["package_context"] = recipe
        else:
            expected_source = source_context(context, version=version)
    else:
        expected_source = source_context(context, version=version)
    if source_blob != json_bytes(expected_source):
        raise ValueError("Frozen source context differs from the current research inputs")
    pdf = files.get("report.pdf")
    if (contract.get("pdf_sha256") != (sha256(pdf) if pdf else None)
            or contract.get("pdf_bytes") != (len(pdf) if pdf else None)):
        raise ValueError("Frozen PDF differs from its preparation contract")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if len(zipped.namelist()) != len(files) or set(zipped.namelist()) != set(files):
            raise ValueError("Frozen archive members differ from its manifest")
        for name, blob in files.items():
            if zipped.getinfo(name).compress_type not in ARCHIVE_COMPRESSION.values():
                raise ValueError("Unsupported frozen archive compression: " + name)
            if zipped.read(name) != blob:
                raise ValueError("Frozen archive differs from prepared file: " + name)
    return {**files, "PREPARED.json": contract_blob, "research-archive.zip": archive}


def freeze_publication_package(context, package, *, archive_compression="stored"):
    """Create an immutable edition package, or verify an identical prior freeze.

    An existing target is never regenerated or overwritten. Missing/incomplete
    prior packages fail closed for operator inspection after an interrupted run.
    """
    # A build selection points to an existing bundle; it is not a request to
    # reuse that bundle while explicitly preparing a different new target.
    context = {key: value for key, value in context.items() if key not in {"prepared_package", "prepared_package_expected"}}
    target = prepared_package_path({**context, "prepared_package": str(Path(package).absolute())})
    if context["report"].get("archive", {}).get("status") == "published" and not target.exists():
        raise ValueError("New frozen packages require prepublication source context; reuse the existing published bundle")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError:
        read_prepared_package(context, target)
        return target
    with tempfile.TemporaryDirectory(prefix="research-freeze-", dir=target.parent) as temporary:
        write_publication_assets(context, temporary, archive_compression=archive_compression)
        prepared = Path(temporary) / "publication"
        read_prepared_package(context, prepared)
        for source in prepared.iterdir():
            if not source.is_file() or source.is_symlink():
                raise ValueError("Unexpected prepared package member")
            shutil.copyfile(source, target / source.name)
    read_prepared_package(context, target)
    return target


def verified_pdf(context):
    """Use a prepared PDF only when its byte digest and source context match."""
    root = Path(context.get("root", ROOT))
    path = root / "data/research/report.pdf"
    receipt_path = root / "data/research/report-pdf.json"
    if not path.exists() or not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text())
    blob = path.read_bytes()
    if (type(receipt.get("context_contract_version", 1)) is not int
            or receipt.get("context_contract_version", 1) != CONTEXT_CONTRACT_VERSION
            or receipt.get("sha256") != sha256(blob) or receipt.get("context_sha256") != context_digest(context)):
        raise ValueError("Prepared report PDF does not match the publication context")
    return blob


def deterministic_zip(files, *, compression="stored"):
    """Stable ZIP metadata; explicit deflate is for preparation before freezing.

    Deflate output can vary between zlib versions. Cross-runtime builds reuse the
    frozen archive bytes rather than regenerating compressed streams.
    """
    if compression not in ARCHIVE_COMPRESSION:
        raise ValueError("Archive compression must be stored or deflate")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, blob in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, blob, compress_type=ARCHIVE_COMPRESSION[compression],
                             compresslevel=9 if compression == "deflate" else None)
    return stream.getvalue()


def publication_asset_inventory(package, *, limit=STATIC_ASSET_LIMIT_BYTES):
    """Inspect every exposed file, not just the compressed archive."""
    package = Path(package)
    sizes = {path.name: path.stat().st_size for path in sorted(package.iterdir()) if path.is_file()}
    return {"limit_bytes": limit, "files": sizes,
            "oversized": {name: size for name, size in sizes.items() if size > limit}}


def write_publication_assets(context, output, *, archive_compression="stored"):
    """Prepare local files even while accounts and launch gates are unavailable."""
    output = Path(output)
    publication = output / "publication"
    publication.mkdir(parents=True, exist_ok=True)
    archive_receipt = context["report"].get("archive", {})
    if archive_receipt.get("status") == "published" or context.get("prepared_package"):
        if archive_receipt.get("status") == "published" and not published_archive(context):
            raise ValueError("Published website assets require a verified production archive receipt")
        frozen = read_prepared_package(context, prepared_package_path(context),
            expected_archive_sha256=archive_receipt.get("artifact_sha256") if archive_receipt.get("status") == "published" else None)
        for name, blob in frozen.items():
            (publication / name).write_bytes(blob)
        return write_package_status(context, publication, frozen)
    projection = public_projection(context)
    paths = write_projection(projection, publication)
    metadata = publication_metadata(context)
    files = {name: (publication / name).read_bytes() for name in paths}
    files.update(citation_formats(metadata))
    files.update({"metadata.json": json_bytes(metadata), "report.md": report_markdown(context).encode(),
                  "report.html": offline_html(context), "evidence.html": offline_appendix(projection, corrections=public_corrections(context)),
                  "corrections.json": json_bytes({"schema_version": "1.0.0", "corrections": public_corrections(context)}),
                  "readiness.json": json_bytes(privacy_filter(context["gate"])),
                  "source-context.json": json_bytes(source_context(context))})
    try:
        from research_brief import executive_brief_assets
    except ImportError:
        from scripts.research_brief import executive_brief_assets
    files.update(executive_brief_assets(context, metadata))
    pdf = verified_pdf(context)
    if pdf:
        files["report.pdf"] = pdf
    files.update(reproduction_files(context))
    files["source-manifest.json"] = json_bytes(projection["graph"]["sources"])
    files["METHODS.md"] = privacy_filter("# Research methods\n\n" + "\n\n".join(paragraph["text"] if paragraph_supported(context, paragraph) else WITHHELD_PARAGRAPH for section in context["report"].get("sections", [])
                                           if section["id"] == "methods-and-appendices" for paragraph in section.get("paragraphs", [])) + "\n\nAccepted correction metadata is preserved in corrections.json and the offline evidence appendix. Superseded identifiers link to approved replacements without restoring unapproved wording. Pending and rejected proposals remain private. Context contract V3 binds the public records and an opaque raw-input commitment; the manifest covers the correction export, validator and schema.\n").encode()
    files["README.md"] = ("# ScienceToStartup research package\n\n" + metadata["note"] + "\n\nStart with executive-brief.html for the short briefing, report.html for the full offline report, then evidence.html for entity dossiers, a recorded-scope comparison, assertions, source metadata and review receipts. corrections.json contains accepted correction metadata; the appendix retains superseded IDs as metadata-only links to approved replacements. Evidence links resolve within the extracted edition without the live site. Citation files reflect archive status. JSON, CSV and SQLite are equivalent privacy-filtered projection " + PROJECTION_VERSION + ", not replacements for canonical dataset 2.5.0. Full source text and personal contacts are excluded. CC BY 4.0 covers owned research/text; third-party evidence retains its rights. The DejaVu fonts and Noto Sans SC derived CJK subset are excluded from the project CC BY 4.0 and MIT licenses. Their unmodified upstream terms are in DejaVu-LICENSE.txt and CJK-OFL.txt; DejaVu-PROVENANCE.json and CJK-PROVENANCE.json record source hashes and the subset recipe.\n\nRun `python3 reproduce.py --write-tables reproduced` inside this extracted package to verify MANIFEST.json, compare all three exports, validate the graph and reproduce coverage and approved-assertion tables. This needs only Python's standard library and no network. Schemas, methods and a source manifest are included. The PDF is accepted only when its receipt binds this exact context. No remote publication occurs during the build.\n").encode()
    # These files are sent to external services, so they belong to the same
    # immutable manifest and archive as the report and dataset.
    files["zenodo-metadata.json"] = json_bytes(zenodo_metadata(metadata))
    files["huggingface-README.md"] = ("---\nlicense: cc-by-4.0\nlanguage:\n- en\n---\n\n# " + metadata["title"] + "\n\n" + metadata["note"] + "\n\nPublic projection " + PROJECTION_VERSION + ". Read report.html and README.md before reuse. No third-party source text or personal contacts are licensed for reuse. DejaVu fonts and the Noto Sans SC derived CJK subset are excluded from the project CC BY 4.0 and MIT licenses; upstream terms are in DejaVu-LICENSE.txt and CJK-OFL.txt, with source hashes and the subset recipe in their provenance files.\n").encode()
    manifest = {"schema_version": 1, "context_contract_version": CONTEXT_CONTRACT_VERSION,
                "release_id": metadata["version"], "context_sha256": context_digest(context),
                "files": {name: {"sha256": sha256(blob), "bytes": len(blob)} for name, blob in sorted(files.items())}}
    files["MANIFEST.json"] = json_bytes(manifest)
    files["research-archive.zip"] = deterministic_zip(files, compression=archive_compression)
    # Receipts contain the ZIP digest and therefore cannot be ZIP members.
    files["PREPARED.json"] = json_bytes({"schema_version": 1, "context_contract_version": CONTEXT_CONTRACT_VERSION, "release_id": metadata["version"],
        "context_sha256": context_digest(context), "manifest_sha256": sha256(files["MANIFEST.json"]),
        "archive_sha256": sha256(files["research-archive.zip"]), "archive_bytes": len(files["research-archive.zip"]),
        "pdf_sha256": sha256(pdf) if pdf else None, "pdf_bytes": len(pdf) if pdf else None})
    for name, blob in files.items():
        (publication / name).write_bytes(blob)
    return write_package_status(context, publication, files)


def zenodo_metadata(metadata):
    return {"metadata": {"title": metadata["title"], "upload_type": "publication", "publication_type": "report",
                         "description": metadata["note"], "creators": [{"name": metadata["author"]}],
                         "version": metadata["version"], "access_right": "open", "license": "cc-by-4.0",
                         "keywords": ["AI data", "research", "ScienceToStartup"]}}


def write_package_status(context, publication, frozen):
    """Live receipt/citations are siblings of, never replacements for, frozen files."""
    receipt = context["report"].get("archive", {})
    archived, pdf = published_archive(context), frozen.get("report.pdf")
    live = {"current-" + name: blob for name, blob in citation_formats(publication_metadata(context)).items()}
    live["current-metadata.json"] = json_bytes(publication_metadata(context))
    state = {"schema_version": 1, "release_id": context["report"]["release_id"],
             "status": "archived" if archived else "prepared",
             "publication_ready": bool(context["gate"].get("archival_ready", context["gate"].get("ready")) and pdf),
             "archive": "published" if archived else "not-published", "website": "independent", "github": "prepared", "huggingface": "prepared",
             "pdf": "prepared" if pdf else "requires-preparation", "manifest_sha256": sha256(frozen["MANIFEST.json"]),
             "archive_sha256": sha256(frozen["research-archive.zip"]), "pdf_sha256": sha256(pdf) if pdf else None,
             "blocked_reasons": list(context["gate"].get("reasons", [])) + ([] if pdf else ["Prepare and verify the PDF before archival publication."])}
    if archived:
        state["archive_receipt"] = privacy_filter(receipt)
    live["package-status.json"] = json_bytes(state)
    for name, blob in live.items():
        (publication / name).write_bytes(blob)
    return ["publication/" + name for name in sorted(set(frozen) | set(live))]
