"""Current directory additions beside the unchanged canonical and research releases.

This registry selects reviewed organization pages and source-bound current-only
profiles. It does not add assertions to a published research graph or change
any frozen coverage counts.
Source-content review establishes the quotations; offline validation checks their
entity, URL, date, attribution and evidence bindings before they can be rendered.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlsplit


LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
CHANGE_NOTE = "Sentence wording unchanged; links, formatting and citation markers omitted."
KINDS = {"supplier", "organization", "institution"}


class CurrentCompaniesValidationError(ValueError):
    """An additive directory record lacks a valid entity or evidence binding."""


def _require(condition, message):
    if not condition:
        raise CurrentCompaniesValidationError("current-companies: " + message)


def _text(value, where, limit=400):
    _require(isinstance(value, str) and value and value == value.strip(), where + " must be non-empty trimmed text")
    _require(len(value) <= limit and not re.search(r"[<>\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]", value), where + " must be bounded plain text")
    return value


def _day(value, where):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), where + " must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise CurrentCompaniesValidationError("current-companies: " + where + " is not a calendar date") from None
    return value


def _url(value, where):
    _require(isinstance(value, str) and not re.search(r"[\s\x00-\x1f\x7f]", value), where + " must be HTTPS")
    try:
        result = urlsplit(value)
        result.port
    except ValueError:
        raise CurrentCompaniesValidationError("current-companies: " + where + " must be HTTPS") from None
    _require(result.scheme == "https" and result.hostname and not result.username and not result.password and result.port in (None, 443), where + " must be HTTPS without credentials")
    return result


def _sha(value, where):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), where + " must be a lowercase SHA-256")


def _name(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())


def _host(value):
    return (urlsplit(value).hostname or "").lower().removeprefix("www.")


def _source_refs(value, sources, where):
    _require(isinstance(value, list) and value and all(type(i) is int and 0 <= i < len(sources) for i in value), where + " requires valid source indexes")
    _require(len(value) == len(set(value)), where + " repeats a source index")


def validate_current_companies(registry, data, context):
    """Validate without mutating canonical data, graph records or the registry."""
    _require(isinstance(registry, dict) and set(registry) == {"schema_version", "reviewed_on", "entries"}, "registry has unsupported fields")
    _require(registry["schema_version"] == "1.0.0", "unsupported schema version")
    reviewed = _day(registry["reviewed_on"], "reviewed_on")
    _require(isinstance(registry["entries"], list), "entries must be a list")
    _require(isinstance(context, dict) and isinstance(context.get("graph"), dict), "requires the reviewed research context")
    graph = context["graph"]
    entities = {row["id"]: row for row in graph.get("entities", [])}
    canonical = {row["id"] for row in data.get("companies", [])}
    subjects = {row.get("subject_id") for row in graph.get("assertions", []) if row.get("status") == "approved"}
    seen, articles, admitted_names = set(), set(), {}
    for entry in registry["entries"]:
        fields = {"entity_id", "name", "group", "website", "wikipedia", "offerings", "sources"}
        _require(isinstance(entry, dict) and fields <= set(entry) <= fields | {"parent_company", "current_identity"}, "entry has unsupported fields")
        eid = entry["entity_id"]
        _require(isinstance(eid, str) and re.fullmatch(r"org\.[a-z0-9][a-z0-9_.-]*", eid), "entity_id must be an organization ID")
        _require(eid not in canonical, "canonical companies cannot be replaced by current additions")
        _require(eid not in seen, "duplicate entity " + eid)
        seen.add(eid)
        entity = entities.get(eid, {})
        identity = entry.get("current_identity")
        if entity or identity is None:
            _require(entity.get("kind") in KINDS and entity.get("status") == "approved" and not entity.get("legacy_id") and eid in subjects, eid + " must select an existing approved organization page")
        name = _text(entry["name"], eid + ".name", 120)
        _text(entry["group"], eid + ".group", 80)
        website = _url(entry["website"], eid + ".website")
        recorded_website = entity.get("identifiers", {}).get("website")
        names = [entity.get("name", ""), *entity.get("aliases", [])]
        names += [part.strip() for value in names[:] for part in value.split(" / ")]
        if identity is None:
            _require(recorded_website and _host(entry["website"]) == _host(recorded_website), eid + " website must match the reviewed entity")
        else:
            expected_scope = "website_supplement" if entity else "current_only"
            identity_fields = {"scope", "name", "aliases", "website", "source_indexes"}
            _require(isinstance(identity, dict) and set(identity) == identity_fields and identity["scope"] == expected_scope, eid + " requires an explicit current identity scope")
            _require(not recorded_website, eid + " current identity cannot override a recorded official website")
            identity_name = _text(identity["name"], eid + ".current_identity.name", 120)
            _require(identity["website"] == entry["website"], eid + " current identity website differs")
            aliases = identity["aliases"]
            _require(isinstance(aliases, list) and len(aliases) <= 12, eid + " current identity aliases must be bounded")
            for alias in aliases:
                _text(alias, eid + ".current_identity.alias", 120)
            identity_names = [identity_name, *aliases]
            _require(len({_name(value) for value in identity_names}) == len(identity_names), eid + " current identity repeats an alias")
            if entity:
                _require(_name(identity_name) in {_name(value) for value in names}, eid + " website supplement must match its reviewed entity")
                _require(all(_name(alias) in {_name(value) for value in names} for alias in aliases), eid + " website supplement cannot introduce unrelated aliases")
            else:
                other_names = [value for row in [*entities.values(), *data.get("companies", [])]
                               if row.get("kind") in KINDS or row.get("id") in canonical
                               for value in [row.get("name", ""), *row.get("aliases", [])]]
                other_names += [part.strip() for value in other_names[:] for part in value.split(" / ")]
                identity_tokens = [*identity_names, *[part.strip() for value in identity_names for part in value.split(" / ")]]
                _require(not ({_name(value) for value in identity_tokens} & {_name(value) for value in other_names if value}), eid + " current identity duplicates an existing organization")
            names += identity_names
            names += [part.strip() for value in identity_names for part in value.split(" / ")]
        wiki = entry["wikipedia"]
        wf = {"title", "article_url", "revision_url", "history_url", "page_id", "revision_id", "revision_timestamp", "observed_on", "response_sha256", "content_kind", "description", "license_url", "change_note"}
        _require(isinstance(wiki, dict) and wf <= set(wiki) <= wf | {"article_scope"}, eid + ".wikipedia has unsupported fields")
        scope = wiki.get("article_scope", "company")
        _require(scope in {"company", "parent_company"}, eid + " has unsupported article scope")
        sources = entry["sources"]
        _require(isinstance(sources, list) and sources, eid + " sources must be non-empty")
        for index, source in enumerate(sources):
            where = eid + ".sources[" + str(index) + "]"
            sf = {"url", "title", "published_on", "observed_on", "response_sha256", "locator", "content_kind"}
            _require(isinstance(source, dict) and set(source) == sf, where + " has unsupported fields")
            _url(source["url"], where + ".url")
            _text(source["title"], where + ".title", 240)
            _text(source["locator"], where + ".locator", 500)
            observed = _day(source["observed_on"], where + ".observed_on")
            _require(observed <= reviewed, where + " observed after review")
            if source["published_on"] is not None:
                _require(_day(source["published_on"], where + ".published_on") <= observed, where + " published after observation")
            _sha(source["response_sha256"], where + ".response_sha256")
            _require(source["content_kind"] in {"raw_http_body", "web_tool_text_excerpt"}, where + " has unsupported content_kind")
        _require(any(_host(s["url"]) == website.hostname.removeprefix("www.") or _host(s["url"]).endswith("." + website.hostname.removeprefix("www.")) for s in sources), eid + " needs a source on its reviewed official website")
        if identity is not None:
            _source_refs(identity["source_indexes"], sources, eid + ".current_identity")
            _require(any(_host(sources[i]["url"]) == _host(entry["website"]) or _host(sources[i]["url"]).endswith("." + _host(entry["website"])) for i in identity["source_indexes"]), eid + " current identity needs an official identity source")
        if scope == "parent_company":
            parent = entry.get("parent_company")
            _require(eid == "org.dataforce" and isinstance(parent, dict) and set(parent) == {"name", "source_indexes"} and parent["name"] == "TransPerfect", eid + " parent article requires the reviewed DataForce–TransPerfect binding")
            _source_refs(parent["source_indexes"], sources, eid + ".parent_company")
            _require(name in {entity["name"], "TransPerfect / DataForce"}, eid + " parent profile name does not match its reviewed identity")
            title_names = [parent["name"]]
        else:
            _require("parent_company" not in entry, eid + " company article cannot carry an unrelated parent binding")
            _require(_name(name) in {_name(value) for value in names}, eid + " name must match its reviewed entity")
            title_names = names
        title = _text(wiki["title"], eid + ".wikipedia.title", 200)
        article_name = re.sub(r"\s*\([^)]*\)$", "", title)
        _require(_name(article_name) in {_name(value) for value in title_names}, eid + " Wikipedia title does not match the reviewed entity or explicit parent")
        for key in ("page_id", "revision_id"):
            _require(type(wiki[key]) is int and wiki[key] > 0, eid + ".wikipedia." + key + " must be a positive integer")
        _require(wiki["page_id"] not in articles, "duplicate Wikipedia entity page")
        articles.add(wiki["page_id"])
        article = _url(wiki["article_url"], eid + ".wikipedia.article_url")
        revision = _url(wiki["revision_url"], eid + ".wikipedia.revision_url")
        history = _url(wiki["history_url"], eid + ".wikipedia.history_url")
        _require(all(u.hostname == "en.wikipedia.org" and not u.fragment for u in (article, revision, history)), eid + " Wikipedia attribution must use en.wikipedia.org")
        _require(article.path.startswith("/wiki/") and not article.query and unquote(article.path[6:]).replace("_", " ") == title, eid + " Wikipedia article URL and title differ")
        _require(revision.path == "/w/index.php" and parse_qs(revision.query) == {"title": [title.replace(" ", "_")], "oldid": [str(wiki["revision_id"])]}, eid + " Wikipedia revision URL must pin the stated title and revision")
        _require(history.path == "/w/index.php" and parse_qs(history.query) == {"title": [title.replace(" ", "_")], "action": ["history"]}, eid + " Wikipedia history URL and title differ")
        observed = _day(wiki["observed_on"], eid + ".wikipedia.observed_on")
        _require(observed <= reviewed, eid + " Wikipedia observed after review")
        stamp = wiki["revision_timestamp"]
        _require(isinstance(stamp, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", stamp), eid + " Wikipedia revision_timestamp must be UTC")
        try:
            revised = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise CurrentCompaniesValidationError("current-companies: " + eid + " invalid Wikipedia revision timestamp") from None
        _require(revised.date().isoformat() <= observed, eid + " Wikipedia revision is after observation")
        _sha(wiki["response_sha256"], eid + ".wikipedia.response_sha256")
        _require(wiki["content_kind"] in {"mediawiki_revision_wikitext", "mediawiki_revision_html"}, eid + " Wikipedia receipt must identify revision content")
        _text(wiki["description"], eid + ".wikipedia.description", 1800)
        _require(bool(re.search(r'[.!?][\u201d\u2019"\']?$', wiki["description"])), eid + " description must retain complete Wikipedia sentences")
        _require(wiki["license_url"] == LICENSE and wiki["change_note"] == CHANGE_NOTE, eid + " requires explicit Wikipedia license and excerpt modification attribution")
        offerings = entry["offerings"]
        _require(isinstance(offerings, list) and offerings, eid + " offerings must be non-empty")
        labels = set()
        for offering in offerings:
            _require(isinstance(offering, dict) and set(offering) == {"label", "source_indexes"}, eid + " offering has unsupported fields")
            label = _text(offering["label"], eid + ".offering.label", 100)
            _require(label not in labels, eid + " repeats an offering label")
            labels.add(label)
            _source_refs(offering["source_indexes"], sources, eid + ".offering")
        current_only = bool(identity and identity["scope"] == "current_only")
        selected_names = [name, *([identity["name"], *identity["aliases"]] if identity else [])]
        selected_names += [part.strip() for value in selected_names[:] for part in value.split(" / ")]
        for token in {_name(value) for value in selected_names}:
            previous = admitted_names.get(token)
            _require(not previous or previous[0] == eid or not (current_only or previous[1]), eid + " current identity duplicates an existing organization")
            admitted_names[token] = (eid, current_only)
    return registry


def load_current_companies(root, data, context):
    path = Path(root) / "data/current-companies.json"
    if not path.exists():
        return {"schema_version": "1.0.0", "reviewed_on": None, "entries": []}
    registry = validate_current_companies(json.loads(path.read_text()), data, context)
    groups = {row["primary_offering"] for row in json.loads((Path(root) / "data/editorial.json").read_text())["entries"]}
    _require(all(row["group"] in groups for row in registry["entries"]), "current additions must use an existing reviewed business group")
    return registry


def company_path(entry):
    return "/company/" + entry["entity_id"] + "/"


def search_entries(entries, current_entries):
    """Find current brands/offerings using existing, non-Wikipedia search copy.

    The exact Wikipedia excerpts stay on attributed cards and profiles. Existing
    research summary wording and canonical counts remain unchanged in search.
    """
    replacements = {company_path(row): row for row in current_entries}
    output, seen = [], set()
    for entry in entries:
        url = entry["url"]
        if url in seen:
            continue
        seen.add(url)
        current = replacements.get(url)
        if current:
            keywords = entry.get("keywords", "")
            if isinstance(keywords, list):
                keywords = " ".join(keywords)
            output.append({**entry, "title": current["name"], "kind": "company", "keywords": " ".join([keywords, current["name"], *[o["label"] for o in current["offerings"]]])})
        else:
            output.append(entry)
    for url, current in replacements.items():
        if url in seen:
            continue
        _require((current.get("current_identity") or {}).get("scope") == "current_only", "every current addition must have an existing research search result or explicit current-only identity")
        labels = [o["label"] for o in current["offerings"]]
        output.append({"url": url, "title": current["name"], "summary": " · ".join(labels), "kind": "company",
                       "keywords": " ".join([current["name"], *labels])})
    return output


def _link(url, label):
    return '<a class="ext" href="' + escape(url, quote=True) + '" rel="noopener noreferrer" target="_blank">' + escape(label) + '</a>'


def current_review_date(entry):
    """A later registry update cannot refresh an unchanged entry's receipts."""
    return min(entry["wikipedia"]["observed_on"], *(source["observed_on"] for source in entry["sources"]))


def offering_source_dates(entry):
    """Only observations bound to an offering; identity/Wikipedia dates stay separate."""
    indexes = {index for offering in entry["offerings"] for index in offering["source_indexes"]}
    return sorted({entry["sources"][index]["observed_on"] for index in indexes})


def current_company_html(entry, reviewed_on, compact=False, native_sources=False):
    """Attribution stays adjacent to the exact quoted text without JavaScript."""
    from static_pages import format_date
    wiki, sources = entry["wikipedia"], entry["sources"]
    refs = lambda indexes: " ".join(_link(sources[i]["url"], "[" + str(i + 1) + "]") for i in indexes)
    offerings = "".join('<li>' + escape(o["label"]) + ' ' + refs(o["source_indexes"]) + '</li>' for o in entry["offerings"])
    scope = ""
    if wiki.get("article_scope") == "parent_company":
        parent = entry["parent_company"]
        scope = '<dl><dt>Article scope</dt><dd>Parent company: ' + escape(parent["name"]) + ' ' + refs(parent["source_indexes"]) + '</dd><dt>Profile scope</dt><dd>DataForce by TransPerfect</dd></dl>'
    attribution = ('<p class="company-wikipedia-attribution">From ' + _link(wiki["article_url"], wiki["title"] + " on Wikipedia")
                   + ' by ' + _link(wiki["history_url"], "Wikipedia contributors") + ' · '
                   + _link(wiki["revision_url"], "Revision " + str(wiki["revision_id"])) + ' · '
                   + _link(LICENSE, "CC BY-SA 4.0") + '. ' + escape(wiki["change_note"]) + '</p>')
    anchor = ' id="sources" data-native-sources' if native_sources else ''
    evidence = (f'<details class="company-current-facts"><summary{anchor}>' + ('Official sources' if compact else 'Current source receipts') + '</summary><ol>'
        + ''.join('<li>' + _link(s["url"], s["title"]) + '<p>' + escape(s["locator"]) + '</p><p>Observed ' + escape(format_date(s["observed_on"])) + ((' · Published ' + escape(format_date(s["published_on"]))) if s["published_on"] else '') + '</p>' + ('' if compact else '<code>SHA-256 ' + escape(s["response_sha256"]) + '</code>') + '</li>' for s in sources)
        + '</ol>' + ('' if compact else '<p>Wikipedia revision ' + escape(wiki["revision_timestamp"]) + ' · Observed ' + escape(format_date(wiki["observed_on"])) + '</p><code>SHA-256 ' + escape(wiki["response_sha256"]) + '</code>') + '<p><a href="/current-companies.json">Current directory records and provenance · JSON</a></p></details>')
    dates = offering_source_dates(entry)
    observed = format_date(dates[0]) + (" to " + format_date(dates[-1]) if len(dates) > 1 else "")
    stamp = '<p class="company-research-snapshot">Current directory addition · Offering sources checked ' + escape(observed) + '</p>'
    context = (scope + '<blockquote class="company-wikipedia-description"><p>' + escape(wiki["description"]) + '</p></blockquote>' + attribution
               + '<p><strong>Current offerings</strong></p><ul>' + offerings + '</ul>' + evidence)
    if compact:
        preview = '<p class="company-offering-preview">' + escape(" · ".join(offering["label"] for offering in entry["offerings"])) + '</p>'
        context = preview + stamp + '<details class="company-current-context"><summary>Company context and sources</summary>' + context + '</details>'
    else:
        context = stamp + context
    return ('<section class="company-current-addition" data-current-company="' + escape(entry["entity_id"]) + '"'
            + ('' if compact else ' id="current-company-description"') + '>' + context + '</section>')


def write_current_company_supplements(output, registry):
    """Append current content after research rendering, leaving archives untouched."""
    import static_pages as sp
    records = []
    for entry in registry["entries"]:
        reviewed_on = current_review_date(entry)
        path = company_path(entry)
        target = Path(output) / path.strip('/') / 'index.html'
        if (entry.get("current_identity") or {}).get("scope") == "current_only":
            _require(not target.exists(), "current-only profile would overwrite an existing page: " + path)
            from types import SimpleNamespace
            description = entry["wikipedia"]["description"]
            canonical = sp.ORIGIN + path
            crumbs = [("Companies", sp.ORIGIN + "/companies/"), (entry["name"], canonical)]
            body = ('<link rel="stylesheet" href="/company-profile.css">' + sp.crumb_nav(crumbs, "company-crumbs")
                    + '<article class="company-dossier"><header class="company-hero"><p class="eyebrow">Current company profile</p><h1>'
                    + escape(entry["name"]) + '</h1><p>' + _link(entry["website"], "Official website") + '</p></header><div class="company-record">'
                    + current_company_html(entry, reviewed_on, native_sources=True)
                    + '<details class="company-fold"><summary><span>Paid work</span></summary><div class="company-fold-body">'
                    + f'<h2 id="work" tabindex="-1">Paid work at {escape(entry["name"])}</h2>'
                    + '<p>No public work listing is recorded for this company.</p></div></details></div></article>')
            node = sp.page_node("ProfilePage", entry["name"], description, canonical, reviewed_on, crumbs,
                                mainEntity={"@type": "Organization", "name": entry["name"], "url": entry["website"]})
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sp.document(SimpleNamespace(as_of=None, data={}), entry["name"] + " · " + sp.SITE_NAME,
                                          description, canonical, body, node, current="companies", state="location"), encoding="utf-8")
            records.append({"path": path, "lastmod": reviewed_on})
            continue
        _require(target.is_file(), "selected organization profile is missing: " + path)
        original = target.read_text(encoding="utf-8")
        canonical = sp.ORIGIN + path
        _require(f'<link rel="canonical" href="{escape(canonical)}">' in original and original.count('<div class="company-record">') == 1, "selected organization profile has an unexpected canonical or layout: " + path)
        _require('id="current-company-description"' not in original, "current supplement already written: " + path)
        modified = reviewed_on
        text = original.replace('<div class="company-record">', '<div class="company-record">' + current_company_html(entry, modified), 1)
        description = entry["wikipedia"]["description"] if entry["wikipedia"].get("article_scope", "company") == "company" else None
        if description is not None:
            text = re.sub(r'(<meta name="description" content=")[^"]*(">)', lambda m: m.group(1) + escape(description, quote=True) + m.group(2), text)
            text = re.sub(r'(<meta (?:property="og:description"|name="twitter:description") content=")[^"]*(">)', lambda m: m.group(1) + escape(description, quote=True) + m.group(2), text)
        def metadata(match):
            nonlocal modified
            node = json.loads(match.group(2))
            def update(value):
                nonlocal modified
                if isinstance(value, dict):
                    if value.get("@id") == canonical and value.get("@type") in {"WebPage", "ProfilePage"}:
                        modified = max(modified, str(value.get("dateModified") or ""))
                        value["dateModified"] = modified
                        if description is not None:
                            value["description"] = description
                    for child in value.values():
                        update(child)
                elif isinstance(value, list):
                    for child in value:
                        update(child)
            update(node)
            return match.group(1) + sp.json_ld(node) + match.group(3)
        text = re.sub(r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)', metadata, text, flags=re.S)
        target.write_text(text, encoding="utf-8")
        records.append({"path": path, "lastmod": modified})
    return records
