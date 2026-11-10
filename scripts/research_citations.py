"""Offline, deterministic citation and archive preparation. Never publishes.

The canonical release is an input, not an output. New exports deliberately have
their own projection version and remove legacy contact/privacy exceptions.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_VERSION = "1.0.0"
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}", re.I)
PRIVATE_KEY = re.compile(r"(?:^|_)(?:email|phone|secret|token|raw_body|cache_path|credential)(?:$|_)", re.I)
SECRET = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
PRIVATE_KEYS = {"email", "personal_email", "contact_email", "phone", "telephone",
                "raw_inputs", "raw_cache", "raw_response", "response_body", "source_quote",
                "full_text", "credentials", "access_token", "api_key"}


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
                if key.lower() not in PRIVATE_KEYS and not PRIVATE_KEY.search(key)}
    if isinstance(value, list):
        return [privacy_filter(item) for item in value]
    if isinstance(value, str):
        return SECRET.sub("[credential removed]", EMAIL.sub("[contact removed]", value))
    return value


def public_projection(context, canonical=None):
    root = Path(context.get("root", ROOT))
    canonical = canonical if canonical is not None else json.loads((root / "data/canonical.json").read_text())
    graph = context["graph"]
    # The graph owner chooses public records; do not accidentally export internal
    # review prompts/caches just because a future graph contains them.
    try:
        from research_graph import public_graph
    except ImportError:
        try:
            from scripts.research_graph import public_graph
        except ImportError:
            public_graph = lambda g: {key: g[key] for key in (
                "schema_version", "release_id", "as_of", "canonical_dataset_version",
                "canonical_sha256", "entities", "sources", "assertions", "reviews", "coverage") if key in g}
    return privacy_filter({"schema_version": 1, "projection_version": PROJECTION_VERSION,
                           "release_id": context["report"]["release_id"],
                           "as_of": graph["as_of"],
                           "canonical_dataset_version": canonical["dataset_version"],
                           "privacy": {"contact_details": "removed", "raw_source_text": "excluded",
                                       "canonical_unchanged": True},
                           "canonical": canonical, "graph": public_graph(graph)})


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
    with (output / "clean-dataset.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.reader(stream))[1:]
    if projection_from_rows(observed) != projection or projection_from_rows(csv_rows) != projection:
        raise ValueError("Public JSON, CSV and SQLite projections differ")
    return ["clean-dataset.json", "clean-dataset.csv", "clean-dataset.sqlite"]


def publication_metadata(context):
    report, gate = context["report"], context["gate"]
    identity = context.get("identity", {})
    archive = report.get("archive", {})
    # A reserved identifier is not registered and must never appear as a DOI in
    # citation formats. Only an explicit verified published archive can supply it.
    published = bool(gate.get("ready") and archive.get("status") == "published"
                     and archive.get("confirmed_on") and archive.get("artifact_sha256")
                     and archive.get("release_id") == report["release_id"]
                     and archive.get("doi") and archive.get("record_url"))
    status = "published" if published else ("ready-for-archive" if gate.get("archival_ready", gate.get("ready")) else "prelaunch")
    author = identity.get("publisher", {}).get("name") or identity.get("display_name") or identity.get("name") or "ScienceToStartup"
    if isinstance(author, dict):
        author = author.get("name", "ScienceToStartup")
    metadata = {"schema_version": 1, "title": report["title"], "version": report["release_id"],
                "author": str(author), "url": "https://sciencetostartup.com/research/",
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
    report, gate = context["report"], context["gate"]
    lines = ["# " + report["title"], "", "Release: " + report["release_id"],
             "Updated: " + report["updated_on"], "Status: " + publication_metadata(context)["status"], "",
             "## Readiness and limitations", ""]
    lines.extend("- " + str(reason) for reason in gate.get("reasons", []))
    lines.extend(["", "Coverage:", "", "```json", json.dumps(gate.get("coverage", {}), sort_keys=True, indent=2), "```", ""])
    for section in report.get("sections", []):
        lines.extend(["## " + section["title"], ""])
        for paragraph in section.get("paragraphs", []):
            lines.extend(["[" + paragraph.get("kind", "analysis") + "] " + paragraph["text"], ""])
            if paragraph.get("claim_ids"):
                lines.extend(["Evidence IDs: " + ", ".join(paragraph["claim_ids"]), ""])
    lines.extend(["## Evidence and reproduction", "", "The accompanying clean-dataset.json, CSV and SQLite contain the same versioned public projection. Canonical dataset 2.5.0 remains unchanged outside this archive. Contact details and raw source text are excluded from this projection. Review receipts describe actual review scope; a candidate is not a deeply reviewed record.", "",
                  "Use MANIFEST.json to verify each file's SHA-256. The archive is self-contained and makes no network requests. Source URLs and identifiers are retained in the accompanying public graph.", ""])
    return privacy_filter("\n".join(lines))


def offline_html(context):
    # Preserve every paragraph as text without interpreting embedded HTML.
    body = []
    for line in report_markdown(context).splitlines():
        if line.startswith("# "):
            body.append("<h1>" + html.escape(line[2:]) + "</h1>")
        elif line.startswith("## "):
            body.append("<h2>" + html.escape(line[3:]) + "</h2>")
        elif line:
            body.append("<p>" + html.escape(line) + "</p>")
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'
            + html.escape(context["report"]["title"]) + '</title><style>body{max-width:72ch;margin:3rem auto;padding:0 1rem;font:18px/1.6 system-ui;color:#18312c}h1,h2{line-height:1.2}p{overflow-wrap:anywhere}h2{margin-top:2.5rem}@media print{body{font-size:11pt}}</style><main>'
            + "\n".join(body) + "</main></html>\n").encode()


def context_digest(context):
    return sha256(json_bytes(privacy_filter({key: context[key] for key in ("graph", "report", "gate", "identity", "policy") if key in context})))


def verified_pdf(context):
    """Use a prepared PDF only when its byte digest and source context match."""
    root = Path(context.get("root", ROOT))
    path = root / "data/research/report.pdf"
    receipt_path = root / "data/research/report-pdf.json"
    if not path.exists() or not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text())
    blob = path.read_bytes()
    if receipt.get("sha256") != sha256(blob) or receipt.get("context_sha256") != context_digest(context):
        raise ValueError("Prepared report PDF does not match the publication context")
    return blob


def deterministic_zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, blob in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, blob)
    return stream.getvalue()


def write_publication_assets(context, output):
    """Prepare local files even while accounts and launch gates are unavailable."""
    output = Path(output)
    publication = output / "publication"
    publication.mkdir(parents=True, exist_ok=True)
    paths = write_projection(public_projection(context), publication)
    metadata = publication_metadata(context)
    files = {name: (publication / name).read_bytes() for name in paths}
    files.update(citation_formats(metadata))
    files.update({"metadata.json": json_bytes(metadata), "report.md": report_markdown(context).encode(),
                  "report.html": offline_html(context), "readiness.json": json_bytes(privacy_filter(context["gate"]))})
    pdf = verified_pdf(context)
    if pdf:
        files["report.pdf"] = pdf
    root = Path(context.get("root", ROOT))
    for schema_name in ("research-graph.schema.json", "report.schema.json", "report-audit.schema.json", "publication-projection.schema.json", "publication-metadata.schema.json"):
        path = root / "schema" / schema_name
        if path.is_file():
            files[schema_name] = path.read_bytes()
    for source_name, target_name in (("research_graph.py", "research_graph.py"), ("reproduce_research_package.py", "reproduce.py")):
        path = root / "scripts" / source_name
        if path.is_file():
            files[target_name] = path.read_bytes()
    files["source-manifest.json"] = json_bytes(privacy_filter(context["graph"]["sources"]))
    files["METHODS.md"] = ("# Research methods\n\n" + "\n\n".join(paragraph["text"] for section in context["report"].get("sections", [])
                                           if section["id"] == "methods-and-appendices" for paragraph in section.get("paragraphs", []))).encode()
    for name in ("LICENSE-DATA.md", "LICENSE"):
        if (root / name).is_file():
            files[name] = (root / name).read_bytes()
    files["README.md"] = ("# ScienceToStartup research package\n\n" + metadata["note"] + "\n\nOpen report.html for the full offline report. Citation files reflect archive status. JSON, CSV and SQLite are equivalent privacy-filtered projection " + PROJECTION_VERSION + ", not replacements for canonical dataset 2.5.0. Full source text and personal contacts are excluded. CC BY 4.0 covers owned research/text; third-party evidence retains its rights.\n\nRun `python3 reproduce.py --write-tables reproduced` inside this extracted package to verify MANIFEST.json, compare all three exports, validate the graph and reproduce coverage and approved-assertion tables. This needs only Python's standard library and no network. Schemas, methods and a source manifest are included. The PDF is accepted only when its receipt binds this exact context. No remote publication occurs during the build.\n").encode()
    # These files are sent to external services, so they belong to the same
    # immutable manifest and archive as the report and dataset.
    zenodo = {"metadata": {"title": metadata["title"], "upload_type": "publication", "publication_type": "report",
                            "description": metadata["note"], "creators": [{"name": metadata["author"]}],
                            "version": metadata["version"], "access_right": "open", "license": "cc-by-4.0",
                            "keywords": ["AI data", "research", "ScienceToStartup"]}}
    files["zenodo-metadata.json"] = json_bytes(zenodo)
    files["huggingface-README.md"] = ("---\nlicense: cc-by-4.0\nlanguage:\n- en\n---\n\n# " + metadata["title"] + "\n\n" + metadata["note"] + "\n\nPublic projection " + PROJECTION_VERSION + ". Read report.html and README.md before reuse. No third-party source text or personal contacts are licensed for reuse.\n").encode()
    manifest = {"schema_version": 1, "release_id": metadata["version"], "context_sha256": context_digest(context),
                "files": {name: {"sha256": sha256(blob), "bytes": len(blob)} for name, blob in sorted(files.items())}}
    files["MANIFEST.json"] = json_bytes(manifest)
    state = {"schema_version": 1, "release_id": metadata["version"], "status": "prepared",
             "publication_ready": bool(context["gate"].get("archival_ready", context["gate"].get("ready")) and pdf),
             "archive": "not-published", "website": "independent", "github": "prepared", "huggingface": "prepared",
             "pdf": "prepared" if pdf else "requires-preparation", "manifest_sha256": sha256(files["MANIFEST.json"]),
             "blocked_reasons": list(context["gate"].get("reasons", [])) + ([] if pdf else ["Prepare and verify the PDF before archival publication."])}
    for name, blob in files.items():
        (publication / name).write_bytes(blob)
    (publication / "package-status.json").write_bytes(json_bytes(state))
    (publication / "research-archive.zip").write_bytes(deterministic_zip(files))
    return ["publication/" + name for name in sorted(list(files) + ["package-status.json", "research-archive.zip"])]
