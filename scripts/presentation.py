"""Reproducible presentation assets. Research exports remain the canonical archive."""
import base64
import copy
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


SCHEMA_VERSION = "1.0.0"
PRIVACY_PROJECTION_VERSION = "1.0.0"


def contact_safe_research(data):
    """Derive browser views without changing the versioned canonical download."""
    from research_citations import EMAIL

    def project(value):
        if isinstance(value, dict):
            return {key: project(item) for key, item in value.items()}
        if isinstance(value, list):
            return [project(item) for item in value]
        if isinstance(value, str):
            return EMAIL.sub("[contact removed]", value)
        return value

    return project(data)


def public_logo_provenance(provenance):
    """Keep public attribution while excluding the operator's local QA file."""
    result = copy.deepcopy(provenance)
    if isinstance(result.get("verification"), dict):
        result["verification"].pop("visual_review_file", None)
    return result


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_identity(root):
    digest = hashlib.sha256()
    paths = []
    for directory in ("web", "scripts", "schema", "design-system", "release-assets"):
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    paths.extend(p for p in (root / "data").rglob("*.json") if p.is_file())
    paths.append(root / "docs/research-id-crosswalk.json")
    for name in ("deployment.json", "package.json", "package-lock.json", "quality-budgets.json"):
        if (root / name).exists():
            paths.append(root / name)
    for path in sorted(set(paths)):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()[:20]


@contextmanager
def _runtime_directory(path, *, create=False, missing_ok=False):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Invalid retained runtime directory")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except FileNotFoundError:
                if create:
                    os.mkdir(part, dir_fd=descriptor)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                elif missing_ok:
                    yield None
                    return
                else:
                    raise ValueError("Missing retained runtime directory") from None
            except OSError:
                raise ValueError("Unsafe retained runtime directory") from None
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _runtime_bytes(path):
    with _runtime_directory(path.parent) as parent:
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError:
            raise ValueError("Missing or unsafe retained runtime file: " + str(path)) from None
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 25 * 1024 * 1024:
                raise ValueError("Invalid retained runtime file: " + str(path))
            content = stream.read(25 * 1024 * 1024 + 1)
            if len(content) > 25 * 1024 * 1024:
                raise ValueError("Retained runtime file exceeds hosting limit")
            return content


def _runtime_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate retained runtime JSON key")
            result[key] = value
        return result
    decoder = json.JSONDecoder(object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite retained runtime JSON")))
    try:
        return decoder.decode(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid retained runtime JSON") from None


def _runtime_name(name):
    if not isinstance(name, str):
        raise ValueError("Invalid retained runtime asset")
    match = re.fullmatch(r"(js|presentation)/([a-z0-9_-]+)\.([0-9a-f]+)\.(js|json)", name)
    if not match or (match[1], match[4], len(match[3])) not in (("js", "js", 12), ("presentation", "json", 16)):
        raise ValueError("Invalid retained runtime asset: " + name)
    return match


def retain_runtime_generations(root, destination):
    """Validate two complete generations and all collisions before copying bytes."""
    root, destination = Path(root).absolute(), Path(destination).absolute()
    source = root / "release-assets"
    manifest = _runtime_json(_runtime_bytes(source / "generations.json"))
    if not isinstance(manifest, dict) or set(manifest) != {"generations"} or not isinstance(manifest["generations"], list) or len(manifest["generations"]) != 2:
        raise ValueError("Exactly two prior runtime generations must be retained")
    versions, merged = set(), {}
    identity_fields = ("schemaVersion", "buildId", "editorialReleaseId", "datasetVersion", "privacyProjectionVersion")
    for generation in manifest["generations"]:
        if not isinstance(generation, dict) or set(generation) != {"cloudflare_version", "sha256"}:
            raise ValueError("Invalid retained generation registry")
        version = generation["cloudflare_version"]
        try:
            canonical_version = str(uuid.UUID(version))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid retained Cloudflare version") from None
        if canonical_version != version or version in versions:
            raise ValueError("Retained Cloudflare versions must be distinct canonical UUIDs")
        versions.add(version)
        checksums = generation["sha256"]
        if not isinstance(checksums, dict) or not checksums:
            raise ValueError("Empty retained runtime generation")
        payloads, documents, families = {}, {}, {}
        for name, checksum in checksums.items():
            match = _runtime_name(name)
            if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError("Invalid retained runtime checksum")
            content = _runtime_bytes(source / name)
            if hashlib.sha256(content).hexdigest() != checksum or not checksum.startswith(match[3]):
                raise ValueError("Retained runtime checksum or filename differs: " + name)
            if name in merged and merged[name] != content:
                raise ValueError("Retained generations collide: " + name)
            payloads[name] = content
            families.setdefault((match[1], match[2]), []).append(name)
            if match[1] == "presentation":
                documents[name] = _runtime_json(content)
        summary_names = families.get(("presentation", "summary"), [])
        if len(summary_names) != 1 or any(len(families.get(("js", family), [])) != 1 for family in ("app", "data", "health")):
            raise ValueError("Retained generation requires one summary and app/data/health assets")
        if {family for directory, family in families if directory == "js"} - {"app", "data", "health", "work"}:
            raise ValueError("Unexpected retained runtime module")
        summary_name = summary_names[0]
        summary = documents[summary_name]
        if not isinstance(summary, dict) or any(not isinstance(summary.get(key), str) or not summary[key] for key in (*identity_fields, "publicationAsOf")):
            raise ValueError("Invalid retained summary identity")
        if summary["schemaVersion"] != SCHEMA_VERSION or summary["privacyProjectionVersion"] != PRIVACY_PROJECTION_VERSION:
            raise ValueError("Unsupported retained runtime schema")
        for document in documents.values():
            if not isinstance(document, dict) or any(document.get(key) != summary[key] for key in identity_fields):
                raise ValueError("Retained runtime generation identity differs")
            if "publicationAsOf" in document and document["publicationAsOf"] != summary["publicationAsOf"]:
                raise ValueError("Retained publication identity differs")
        referenced, visited = set(), {summary_name}
        def descriptors(value):
            if isinstance(value, dict):
                href = value.get("href")
                if isinstance(href, str) and href.startswith(("/js/", "/presentation/")):
                    name = href[1:]
                    _runtime_name(name)
                    if name not in payloads or value.get("sha256") != checksums[name] or type(value.get("bytes")) is not int or value["bytes"] != len(payloads[name]):
                        raise ValueError("Retained runtime dependency differs: " + name)
                    expected_sri = "sha256-" + base64.b64encode(bytes.fromhex(checksums[name])).decode()
                    if (name.startswith("js/") or "integrity" in value) and value.get("integrity") != expected_sri:
                        raise ValueError("Retained runtime integrity differs: " + name)
                    referenced.add(name)
                    if name in documents and name not in visited:
                        visited.add(name)
                        descriptors(documents[name])
                for child in value.values():
                    descriptors(child)
            elif isinstance(value, list):
                for child in value:
                    descriptors(child)
        descriptors(summary)
        data_name = families[("js", "data")][0]
        data = payloads[data_name].decode("utf-8")
        prefix = "window.SUMMARY_INDEX="
        if not data.startswith(prefix):
            raise ValueError("Missing retained data bootstrap")
        # Decode only the JSON prefix. Never execute retained JavaScript.
        decoder = json.JSONDecoder()
        try:
            _, end = decoder.raw_decode(data, len(prefix))
        except json.JSONDecodeError:
            raise ValueError("Invalid retained data bootstrap") from None
        public_summary = _runtime_json(data[len(prefix):end].encode())
        expected_public = {key: value for key, value in summary.items() if key not in ("bootstrap", "companies", "work")}
        expected_public["asset"] = {"href": "/" + summary_name, "sha256": checksums[summary_name], "bytes": len(payloads[summary_name])}
        if data[end:end + 1] != ";" or encoded(public_summary) != encoded(expected_public):
            raise ValueError("Retained data bootstrap differs from summary")
        descriptors(public_summary)
        health_name = families[("js", "health")][0]
        if not isinstance(summary.get("modules"), dict) or not isinstance(summary["modules"].get("businessHealth"), dict) or summary["modules"]["businessHealth"].get("href") != "/" + health_name:
            raise ValueError("Retained health module descriptor differs")
        health_prefix = '(()=>{window.SCIENCE_HEALTH_MODULE={buildId:' + json.dumps(summary["buildId"]) + ','
        if not payloads[health_name].decode("utf-8").startswith(health_prefix):
            raise ValueError("Retained health module build identity differs")
        work_names = families.get(("js", "work"), [])
        if work_names or "nativeWork" in summary["modules"]:
            work_script = summary["modules"].get("nativeWork")
            if len(work_names) != 1 or not isinstance(work_script, dict) or work_script.get("href") != "/" + work_names[0]:
                raise ValueError("Retained native Work module descriptor differs")
        if set(payloads) != referenced | {summary_name, data_name, families[("js", "app")][0]}:
            raise ValueError("Retained runtime dependency closure is incomplete")
        merged.update(payloads)
    # Validate every existing destination before creating directories or copying.
    for name, content in merged.items():
        target = destination / name
        with _runtime_directory(target.parent, missing_ok=True) as parent:
            if parent is not None:
                try:
                    os.stat(target.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if _runtime_bytes(target) != content:
                    raise ValueError("Retained runtime destination collision: " + name)
    for name, content in sorted(merged.items()):
        target = destination / name
        with _runtime_directory(target.parent, create=True) as parent:
            try:
                descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
            except FileExistsError:
                if _runtime_bytes(target) != content:
                    raise ValueError("Retained runtime destination changed: " + name)
                continue
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)


def write_asset(destination, family, value):
    content = encoded(value) + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    name = f"presentation/{family}.{digest[:16]}.json"
    path = destination / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"href": "/" + name, "sha256": digest, "bytes": len(content)}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def rooted_assets(value):
    if isinstance(value, list):
        return [rooted_assets(item) for item in value]
    if isinstance(value, dict):
        return {key: ("/" + item.removeprefix("./") if key in ("local_path", "portrait") and isinstance(item, str) and not item.startswith("/") and ":" not in item else rooted_assets(item)) for key, item in value.items()}
    return value


def health_subset(health, observations, company_id=None):
    if health is None:
        return None
    result = copy.deepcopy(health)
    if "profile_finance" in result:
        profiles = health["profile_finance"]
        result["profile_finance"] = {company_id: copy.deepcopy(profiles[company_id])} if company_id in profiles else {}
    result["observations"] = observations
    claim_ids = {cid for observation in observations for cid in observation.get("claim_ids", [])}
    source_ids = {
        sid
        for observation in observations
        for field in ("source_ids", "historical_source_ids")
        for sid in observation.get(field, [])
    }
    result["fresh_claims"] = [row for row in health.get("fresh_claims", []) if row["id"] in claim_ids]
    result["sources"] = [row for row in health.get("sources", []) if row["id"] in source_ids]
    result["source_checks"]["entries"] = [row for row in health.get("source_checks", {}).get("entries", []) if row["source_id"] in source_ids]
    result["private_company_review"] = []
    return result


def company_graph(data, company_id):
    """Company-owned rows plus every referenced claim/source/person/investor."""
    result = {key: copy.deepcopy(value) if not isinstance(value, list) else [] for key, value in data.items()}
    for key, rows in data.items():
        if isinstance(rows, list):
            result[key] = [copy.deepcopy(row) for row in rows if isinstance(row, dict) and (row.get("company_id") == company_id or key == "companies" and row.get("id") == company_id)]
    # Some evidence records reference another company's source. Close references by identity.
    references = set(strings(result))
    for _ in range(4):
        changed = False
        for key, rows in data.items():
            if not isinstance(rows, list):
                continue
            present = {row.get("id") for row in result[key] if isinstance(row, dict)}
            for row in rows:
                if isinstance(row, dict) and row.get("id") in references and row.get("id") not in present:
                    result[key].append(copy.deepcopy(row))
                    references.update(strings(row))
                    changed = True
        if not changed:
            break
    result["raw_inputs"] = []
    return result


def source_updates_context(updates, company_id=None):
    if not updates:
        return None
    result = {key: copy.deepcopy(value) for key, value in updates.items() if key not in ("updates", "evidence_context")}
    result["updates"] = [copy.deepcopy(row) for row in updates.get("updates", []) if company_id is not None and row.get("company_id") == company_id]
    context = updates.get("evidence_context") or {}
    result["evidence_context"] = {key: copy.deepcopy(value) for key, value in context.items() if key != "corrections"}
    result["evidence_context"]["corrections"] = [copy.deepcopy(row) for row in context.get("corrections", []) if company_id is not None and row.get("company_id") == company_id]
    return result


def health_skeleton(health):
    """Keep listeners and version metadata available without shipping evidence early."""
    if health is None:
        return None
    result = {key: copy.deepcopy(health[key]) for key in ("version", "schema_version", "dashboard_curated_on", "source_dataset_version", "source_dataset_reviewed_on") if key in health}
    result.update(observations=[], fresh_claims=[], sources=[], private_company_review=[])
    result["source_checks"] = {key: copy.deepcopy(health["source_checks"][key]) for key in ("checked_on", "status") if key in health.get("source_checks", {})}
    result["source_checks"]["entries"] = []
    return result


def _rounded(value, places=2):
    amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{amount:,.{places}f}".rstrip("0").rstrip(".") if places else f"{amount:,.0f}"


def financial_value(row, observation=False):
    """Exact public number notation; selection and source facts remain separate."""
    from static_pages import number_text
    value = row["value"]
    qualifier = {"at_least": "≥ ", "greater_than": "> ", "less_than": "< ", "nearly": "Nearly ", "at_most": "≤ ", "approximate": "≈ ", "approximately": "≈ "}.get(row.get("qualifier"), "")
    if observation and row.get("currency"):
        absolute = abs(value)
        divisor, suffix = (1e9, "B") if absolute >= 1e9 else (1e6, "M") if absolute >= 1e6 else (1, "")
        symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(row["currency"], row["currency"] + " ")
        return qualifier + ("−" if value < 0 else "") + symbol + _rounded(absolute / divisor, 2 if absolute >= 1e6 else 0) + suffix
    text = ("-" if value < 0 else "") + number_text(value)
    if row.get("qualifier") == "range":
        text += "–" + ("-" if row["upper_value"] < 0 else "") + number_text(row["upper_value"])
    if row.get("unit") == "currency":
        currency = row.get("currency") or ""
        text = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, currency + " ") + text
    elif row.get("unit") in ("percent", "%"):
        text += "%"
    elif row.get("unit") == "multiple":
        text += "×"
    return qualifier + text


def observation_source_ids(observation):
    source_ids = observation.get("source_ids", [])
    primary = observation.get("primary_source_id")
    return [primary, *(sid for sid in source_ids if sid != primary)] if primary else source_ids


def financial_source_urls(sources, ids):
    urls = (sources.get(sid, {}).get("url") for sid in ids)
    return " | ".join(dict.fromkeys(url for url in urls if url))


def current_company_result(research, health, company_id):
    """Pure Python port of currentCompanyResult; all-company JS parity is tested."""
    from static_pages import selected_business_observation
    observation = selected_business_observation(health, company_id)
    if observation:
        sources = {**research.sources, **{s["id"]: s for s in health.get("sources", [])}}
        return {"id": observation["id"], "kind": "annualized_revenue_run_rate" if observation["measure"] == "annualized_revenue" else "revenue",
                "value": observation["value"], "qualifier": observation.get("qualifier") or "", "display": financial_value(observation, True),
                "upper_value": observation.get("upper_value", ""), "observation_status": observation.get("evidence_type") or "",
                "currency": observation.get("currency") or "", "as_of": observation.get("as_of") or "",
                "period": observation.get("period", {}).get("label") or observation.get("as_of") or "",
                "scope": observation.get("scope") or "", "scope_detail": observation.get("scope_detail") or observation.get("scope_label") or "",
                "accounting_basis": observation.get("accounting_basis") or "",
                "source_urls": financial_source_urls(sources, observation_source_ids(observation)),
                "scope_label": observation.get("scope_label") or research.scope_text(observation.get("scope"), company_id),
                "limitations": observation.get("limitations") or ""}
    metric = research.headline(company_id)
    if not metric:
        return None
    return {"id": metric["id"], "kind": metric["kind"], "value": metric["value"], "qualifier": metric.get("qualifier") or "",
            "display": financial_value(metric), "upper_value": metric.get("upper_value", ""), "observation_status": metric.get("observation_status") or "",
            "currency": metric.get("currency") or "", "as_of": metric.get("as_of") or "", "period": metric.get("period_label") or "",
            "scope": metric.get("segment_scope") or "", "scope_detail": metric.get("scope_detail") or "", "accounting_basis": metric.get("gross_vs_net") or "",
            "source_urls": financial_source_urls(research.sources, research.claim(metric).get("source_ids", [])),
            "scope_label": research.scope_text(metric.get("segment_scope"), company_id), "limitations": metric.get("limitations") or ""}


def compiled_products(research, company_id, curated):
    """profileProducts(), including later corrections and their source provenance."""
    from static_pages import Research
    rows = Research(research.data).products(company_id, curated)
    for row in rows:
        matched = [u for u in research.product_updates if u.get("company_id") == company_id and u.get("target", {}).get("product_name") == row.get("name")
                   and all(r in row.get("record_ids", []) for r in u.get("target", {}).get("record_ids", []))
                   and all(c in row.get("claim_ids", []) for c in u.get("target", {}).get("claim_ids", []))]
        if matched:
            for update in matched:
                row.update(copy.deepcopy(update.get("replacement_fields") or {}))
            row["source_updates"] = copy.deepcopy(matched)
    return rows


def company_summaries(data, sidecars, root):
    from static_pages import Research, read_js_object, selected_business_observation, date_rank, metric_period, latest_source, basis_text
    research = Research(data, read_js_object(root / "web/app.js", "FINANCIAL_HEADLINES"), sidecars["SOURCE_UPDATES"])
    health = sidecars["BUSINESS_HEALTH"] or {}
    health_sources = {**research.sources, **{s["id"]: s for s in health.get("sources", [])}}
    health_checks = {c["source_id"]: c for c in health.get("source_checks", {}).get("entries", [])}
    products_by_company = {}
    result = {}
    for company in data["companies"]:
        cid = company["id"]
        curated = next((e.get("products", []) for e in sidecars["PROFILE_CONTENT"]["entries"] if e["company_id"] == cid), [])
        products = compiled_products(research, cid, curated)
        products_by_company[cid] = products
        metric = research.headline(cid)
        current = current_company_result(research, health, cid)
        observation = selected_business_observation(health, cid)
        financial = None
        if observation:
            primary = observation.get("primary_source_id")
            record = next((health_sources[sid] for sid in observation_source_ids(observation) if sid in health_sources), None)
            fresh = next((c for c in health.get("fresh_claims", []) if c["id"] in observation.get("claim_ids", [])), {})
            checked = None
            if record:
                check = health_checks.get(record["id"])
                if check and check.get("status") == "content_checked":
                    checked = check.get("checked_on")
                elif not check and record["id"] in fresh.get("source_ids", []):
                    checked = fresh.get("observed_on")
            end = observation.get("period", {}).get("end") or next(iter(re.findall(r"\d{4}(?:-\d{2}){0,2}", str(observation.get("as_of") or ""))), "")
            financial = {"recordType": "observation", "id": observation["id"], "claimId": next(iter(observation.get("claim_ids", [])), None),
                         "display": current["display"], "type": "Annualized pace" if observation["measure"] == "annualized_revenue" else "Revenue",
                         "period": research.observation_period(observation), "currency": current["currency"], "scope": current["scope_label"],
                         "basis": {"gross": "Gross revenue", "net": "Net revenue", "latest_discontinued_operations_comparative": "Discontinued operations"}.get(observation.get("accounting_basis"), "Gross/net not disclosed" if observation["measure"] == "annualized_revenue" else ""),
                         "attribution": observation.get("evidence_assurance") or "Attributed source", "limitations": observation.get("limitations") or "",
                         "quote": observation.get("original_text") or fresh.get("excerpt") or "", "checkedOn": checked,
                         "failed": observation.get("refresh_status") == "source_unavailable" or any(c.get("status") == "unavailable" and c["source_id"] in observation.get("source_ids", []) for c in health.get("source_checks", {}).get("entries", [])),
                         "age": "historical" if not end or end < "2025-10-28" else "current"}
            if primary:
                financial["primarySource"] = True
        elif metric:
            record, _ = latest_source(research, metric)
            claim = research.claim(metric)
            rank = date_rank(metric.get("as_of"))
            end = rank + "-12-31" if len(rank) == 4 else rank + "-31" if len(rank) == 7 else rank
            financial = {"recordType": "metric", "id": metric["id"], "claimId": metric["claim_id"], "display": current["display"],
                         "type": {"revenue": "Revenue", "annualized_revenue_run_rate": "Annualized pace", "arr": "Yearly recurring subscription revenue"}.get(metric["kind"], metric["kind"]),
                         "period": metric_period(research, metric), "currency": metric.get("currency") or "", "scope": current["scope_label"],
                         "basis": basis_text(research, metric), "attribution": research.correction(metric, "display_attribution") or claim.get("evidence_label") or "Attributed source",
                         "limitations": metric.get("limitations") or "", "quote": claim.get("statement") or "", "checkedOn": claim.get("observed_on"),
                         "failed": False, "age": "undated" if rank == "0000" else "historical" if end < "2025-10-28" else "current"}
            historical = research.historical_year(metric)
            if historical:
                financial["historicalYear"] = historical
        if financial is not None:
            citation = {"url": record["url"], "publisher": (record["title"] if observation and observation.get("primary_source_id") else record.get("publisher")) or "Original source"} if record else None
            if record and observation:
                citation["id"] = record["id"]
            if record and (published := research.reviewed_source_dates.get(record["id"]) or (record.get("published_on") if observation and observation.get("primary_source_id") else None)):
                citation.update(id=record["id"], publishedOn=published, accessedOn=record.get("accessed_on"), retrievalStatus=record.get("retrieval_status"))
                if not observation:
                    financial["checkedOn"] = None
            financial["source"] = citation
        result[cid] = {"firstOffering": {"name": products[0]["name"]} if products else None, "hasFinancial": bool(metric),
                       "financial": financial, "currentCompanyResult": current}
        if health.get("profile_finance", {}).get(cid, {}).get("compare_projection") == "native_evidence_link_only":
            result[cid]["financingEvidenceHref"] = f"/company/{cid}/#financial-record"
    return result, products_by_company, research


def search_fold(value):
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.category(ch).startswith("M")).lower()


def work_recorded_titles(route):
    history = (route.get("editorial_review") or {}).get("correction_history", [])
    previous = ((item.get("previous_values") or {}).get("role") for item in history)
    return [title for title in (route.get("role"), *previous) if isinstance(title, str) and title]


def work_search_text(route, companies):
    from static_pages import work_location
    company = companies.get(route["company_id"], {})
    values = [company.get("name"), *company.get("aliases", []), *work_recorded_titles(route), route.get("summary"), route.get("group"), route.get("geography"), work_location(route), route.get("pay_label"), route.get("hours"), route.get("duration"), *route.get("requirements", [])]
    return search_fold(" ".join(str(value) for value in values if value))


def work_search_titles(routes):
    from static_pages import work_kind

    return sorted({title for route in routes if work_kind(route) in ("named_listing", "network_program")
                   for title in work_recorded_titles(route)})


def company_search_aliases(company_id, aliases=()):
    # Both labels resolve to the same reviewed TransPerfect subsidiary profile.
    recorded_names = ("DataForce by TransPerfect", "TransPerfect / DataForce") if company_id == "org.dataforce" else ()
    return list(dict.fromkeys([*aliases, *recorded_names]))


EDITORIAL_RUNTIME_FIELDS = frozenset({'company_id', 'summary', 'primary_offering',
                                     'capability_tags', 'product_media'})


def compact_editorial(editorial):
    """Initial UI fields only; retain the complete downloadable authoring input.

    Preserve root schema/version/provenance metadata and entry order. Nested
    media and tags remain complete values; this is a projection, not a codec.
    """
    result = copy.deepcopy(editorial)
    result['entries'] = [{key: value for key, value in entry.items() if key in EDITORIAL_RUNTIME_FIELDS}
                         for entry in result['entries']]
    return result


def work_uncertain(route):
    from static_pages import UNCERTAIN_CHECK

    check = route.get("last_route_check") or {}
    return (route.get("status") in ("unverified", "intake_unverified", "pay_conflict")
            or (route.get("last_link_check") or {}).get("result") in ("blocked", "not_found", "unavailable")
            or ((route.get("research_record") or {}).get("route") or {}).get("live_application_verified") is False
            or bool(UNCERTAIN_CHECK.search(" ".join(str(v) for v in (check.get("result"), check.get("note")) if v))))


def work_field_reviews(route):
    fields = ("state", "reviewed_on", "source_ids", "basis")
    return {field: {k: v for k, v in value.items() if k in fields or field in ("location", "commitment") and k == "note"}
            for field, value in route.get("field_reviews", {}).items()}


def work_native_selection(work, companies):
    """Supply the native filter script with selection fields and searchable text."""
    from static_pages import work_approved_terms_receipt

    fields = ("id", "company_id", "role", "route_kind", "engagement_type", "status", "group", "ai_data_work",
              "arrangements", "geography", "numeric_pay", "pay_label", "pay_basis", "terms_checked_on",
              "reviewed_on", "availability_checked_on")
    rows = []
    for route in work.get("routes", []):
        row = {key: value for key, value in route.items() if key in fields}
        row["company_name"] = companies.get(route["company_id"], {}).get("name") or route["company_id"]
        row["searchText"] = work_search_text(route, companies)
        row["uncertain"] = work_uncertain(route)
        for key, keys in (("pay_terms", ("unit", "currency", "hourly_comparable")),
                          ("last_route_check", ("date", "result"))):
            if route.get(key):
                row[key] = {field: value for field, value in route[key].items() if field in keys}
        receipt = work_approved_terms_receipt(route)
        if receipt:
            fields_to_keep = ("id", "source_id", "checked_on", "scope", "result", "approved", "approval_basis")
            row["editorial_review"] = {"approved_terms_receipt_id": receipt["id"],
                                       "receipts": [{key: value for key, value in receipt.items() if key in fields_to_keep}]}
        rows.append(row)
    return rows


def compact_work(work, research=None):
    result = copy.deepcopy(work)
    for route in result.get("routes", []):
        if research:
            from static_pages import work_action
            route["uncertain"] = work_uncertain(route)
            route["source_action"] = work_action(route, research)
            route["details_deferred"] = True
        record = route.pop("research_record", None)
        hours = ((record or {}).get("route") or {}).get("hours")
        detail = hours.get("detail") if isinstance(hours, dict) else None
        retained = {}
        if detail:
            retained["hours"] = {"detail": detail}
        if "live_application_verified" in ((record or {}).get("route") or {}):
            retained["live_application_verified"] = record["route"]["live_application_verified"]
        if retained:
            route["research_record"] = {"route": retained}
        # Original verbatim research remains in the downloadable work-routes.json.
        for key in ("previous_checks", "check_history", "evidence"):
            route.pop(key, None)
        for key in ("last_route_check", "last_link_check"):
            if key in route:
                route[key] = {k: v for k, v in route[key].items() if k in ("date", "result")}
        if route.get("entry_point_research"):
            route["entry_point_research"] = {"entry": {k: v for k, v in route["entry_point_research"].get("entry", {}).items() if k in ("url", "type")}}
        route["field_reviews"] = work_field_reviews(route)
        review = route.get("editorial_review")
        if review:
            route["editorial_review"] = {key: value for key, value in review.items() if key in ("triaged_on", "approved_terms_receipt_id", "disposition", "alternative_destination", "actions", "recorded_url_purpose")}
            route["editorial_review"]["receipts"] = [{k: v for k, v in receipt.items() if k in ("id", "source_id", "checked_on", "checked_at", "scope", "result", "approved", "approval_basis", "reviewer", "reviewed_fields")} for receipt in review.get("receipts", []) if receipt.get("id") == review.get("approved_terms_receipt_id")]
            history = []
            for change in review.get("correction_history", []):
                previous = change.get("previous_values") or {}
                previous_fields = previous.get("field_reviews") or {}
                field_sources = {field: {"source_ids": value["source_ids"]} for field, value in previous_fields.items()
                                 if value and value.get("source_ids")}
                retained_values = {"role": previous["role"]} if previous.get("role") else {}
                if field_sources:
                    retained_values["field_reviews"] = field_sources
                if retained_values:
                    history.append({"previous_values": retained_values})
            if history:
                route["editorial_review"]["correction_history"] = history
    return result


def work_export_rows(work, research):
    """Bind CSV evidence to the same release as the filters, on download only."""
    from static_pages import work_actions

    fields = ("id", "company_id", "role", "route_kind", "engagement_type", "status", "group", "ai_data_work",
              "arrangements", "geography", "pay_label", "pay_basis", "pay_terms", "pay_observations", "numeric_pay",
              "requirements", "assessment", "hours", "duration", "terms_checked_on", "availability_label",
              "availability_note", "availability_checked_on", "url", "form_available")

    def retain(record, keys):
        return {key: value for key, value in (record or {}).items() if key in keys}

    result = []
    for route in work.get("routes", []):
        row = retain(route, fields)
        if (route.get("pay_terms") or {}).get("unit") == "conflicting" and route.get("pay_context"):
            row["pay_context"] = route["pay_context"]
        row["company_name"] = research.companies.get(route["company_id"], {}).get("name") or route["company_id"]
        row["source_actions"] = [{"url": url, "label": label} for url, label in work_actions(route, research)]
        row["uncertain"] = work_uncertain(route)
        row["field_reviews"] = work_field_reviews(route)
        link_keys = ("date", "result", "url", "http_status", "final_url")
        page_keys = (*link_keys, "checked_at", "retrieval_reason", "application_check", "application_checks")
        for key, keys in (("last_link_check", link_keys), ("last_route_check", page_keys)):
            if route.get(key):
                row[key] = retain(route[key], keys)
        recorded = retain((route.get("research_record") or {}).get("route"),
                          ("url", "overview_url", "application_url", "checked_on", "live_application_verified"))
        if recorded:
            row["research_record"] = {"route": recorded}
        row["sources"] = [retain(source, ("id", "url", "source_type", "title", "accessed_on", "purpose", "field_support"))
                          for source in route.get("sources", [])]
        review = route.get("editorial_review") or {}
        editorial = retain(review, ("approved_terms_receipt_id", "disposition", "alternative_destination", "actions", "recorded_url_purpose"))
        action_urls = {action["url"] for action in row["source_actions"]}
        separate_archive = any(action.get("purpose") == "archived_listing" and action.get("url") != route.get("url")
                               and action.get("url") in action_urls for action in review.get("actions", []))
        page_check = route.get("last_route_check") or {}
        if page_check.get("result") in ("official_role_not_found", "official_role_not_found_redirect"):
            row["source_ids"] = route.get("source_ids", [])
        history = route.get("check_history") or []
        if history:
            row["check_history"] = [retain(check, ("date", "result", "note", "url", "source_ids")) for check in history]
        receipt_keys = ("id", "source_id", "checked_on", "checked_at", "scope", "result", "http_status",
                        "approved", "approval_basis", "reviewed_fields", "url", "final_url",
                        "retrieval_reason", "rendered_observation")
        source_ids = {source.get("id") for source in row["sources"] if source.get("id")}
        receipts = [retain(receipt, receipt_keys)
                    for receipt in review.get("receipts", [])
                    if receipt.get("id") == review.get("approved_terms_receipt_id")
                    or receipt.get("source_id") in source_ids and (receipt.get("scope") == "retrieval" or separate_archive)]
        if receipts:
            editorial["receipts"] = receipts
        if editorial:
            row["editorial_review"] = editorial
        result.append(row)
    return result


def build_presentation(data, destination, root, sidecars, release, daily_context=None):
    data = contact_safe_research(data)
    identity = {"schemaVersion": SCHEMA_VERSION, "buildId": source_identity(root),
                "privacyProjectionVersion": PRIVACY_PROJECTION_VERSION,
                "datasetVersion": data["dataset_version"],
                "editorialReleaseId": release.get("editorial_release_id", release.get("release_id", "baseline-2026-10-28"))}
    summaries, current_products, research = company_summaries(data, sidecars, root)
    details = {}
    for company in data["companies"]:
        cid = company["id"]
        detail = dict(identity, companyId=cid, data=company_graph(data, cid))
        # A fresh root object is installed, invalidating source-context caches safely.
        detail["profileContent"] = rooted_assets({"entries": [e for e in sidecars["PROFILE_CONTENT"].get("entries", []) if e["company_id"] == cid]})
        detail["companyEvents"] = {"events": [e for e in sidecars["COMPANY_EVENTS"].get("events", []) if e["company_id"] == cid or cid in e.get("related_company_ids", [])]}
        health = sidecars["BUSINESS_HEALTH"] or {}
        detail["businessHealth"] = health_subset(sidecars["BUSINESS_HEALTH"], [o for o in health.get("observations", []) if o["company_id"] == cid], cid)
        if cid in health.get("profile_finance", {}):
            from business_health import profile_finance_claim_context
            detail["financeClaimContext"] = profile_finance_claim_context(health["profile_finance"][cid])
        detail["sourceUpdates"] = source_updates_context(sidecars["SOURCE_UPDATES"], cid)
        detail["workRoutes"] = {**{key: copy.deepcopy(value) for key, value in sidecars["WORK_ROUTES"].items() if key != "routes"}, "routes": [copy.deepcopy(route) for route in sidecars["WORK_ROUTES"].get("routes", []) if route["company_id"] == cid or cid in route.get("related_company_ids", [])]}
        details[cid] = write_asset(destination, "company-" + cid, detail)
    bootstrap = {key: copy.deepcopy(value) if not isinstance(value, list) else [] for key, value in data.items()}
    for key in ("companies", "assessments"):
        bootstrap[key] = copy.deepcopy(data[key])
    bootstrap["assessments"] = [{**{k: value for k, value in a.items() if k in ("id", "company_id", "segment_scope", "headline_metric_id", "material_conflict", "rubric_version")}, "gates": {key: {"level": value["level"]} for key, value in a["gates"].items()}} for a in bootstrap["assessments"]]
    bootstrap["raw_inputs"] = []
    stats = {"companies": len(data["companies"]), "sources": len(data["sources"]),
             "sourcePages": len({s["url"] for s in data["sources"]}), "claims": len(data["claims"]),
             "currentClaims": sum(c["status"] != "superseded" for c in data["claims"]),
             "gradeCounts": {grade: sum(c["status"] != "superseded" and c["confidence"] == grade for c in data["claims"]) for grade in ("A", "B", "C", "U")},
             "openUnknowns": sum(c["status"] != "superseded" and c["subject"] == "unknowns" and c["confidence"] == "U" for c in data["claims"]),
             "supersededClaims": sum(c["status"] == "superseded" for c in data["claims"]),
             "companySources": sum(s["source_type"] == "company" for s in data["sources"])}
    exports = {}
    for name in ("research.json", "observatory.sqlite", "work-routes.json"):
        path = destination / name
        if name == "work-routes.json" and not path.exists():
            path = root / "data/work-routes.json"
        if path.exists():
            exports[name.split(".")[0]] = {"href": "/" + name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    summary = dict(identity, bootstrap=bootstrap, companies=bootstrap["companies"], work=compact_work(sidecars["WORK_ROUTES"], research), companySummaries=summaries,
                   companyDetails=details, statistics=stats, exports=exports,
                   publicationAsOf=release.get("publication_as_of", release.get("published_at", "2026-11-08T20:30:00Z")))
    summary["workResults"] = write_asset(destination, "work-results", dict(identity, routes=work_export_rows(sidecars["WORK_ROUTES"], research)))
    search_rows = []
    for company in data["companies"]:
        entry = next((e for e in sidecars["EDITORIAL"]["entries"] if e["company_id"] == company["id"]), {})
        products = next((e.get("products", []) for e in sidecars["PROFILE_CONTENT"]["entries"] if e["company_id"] == company["id"]), [])
        search_rows.append({"id": company["id"], "name": company["name"], "summary": entry.get("summary", company.get("description", "")), "group": entry.get("primary_offering", ""), "products": [value for p in products for value in [p["name"], p.get("description", ""), *p.get("aliases", [])] if value], "aliases": company_search_aliases(company["id"], company.get("aliases", [])), "href": "/company/" + company["id"] + "/"})
    from daily_scan import daily_search_entries, daily_search_scope
    public_search_entries = [*sidecars.get("RESEARCH_SEARCH", []), *daily_search_entries(daily_context)]
    work_titles = work_search_titles(sidecars["WORK_ROUTES"]["routes"])
    summary["dailySearchScope"] = daily_search_scope(daily_context)
    for entry in public_search_entries:
        keywords = entry.get("keywords", [])
        if isinstance(keywords, str):
            keywords = keywords.split()
        row = {"id": entry["url"], "name": entry["title"], "summary": entry["summary"], "group": entry["kind"], "products": keywords, "href": entry["url"]}
        if entry.get("identifiers"):
            row["identifiers"] = entry["identifiers"]
        if entry.get("recordKind"):
            row["recordKind"] = entry["recordKind"]
        if entry["kind"] == "company":
            row["aliases"] = company_search_aliases(entry["url"].strip("/").removeprefix("company/"), entry.get("aliases", []))
        search_rows.append(row)
    search_rows.append({"id": "market-revenue", "name": "Revenue & growth",
                        "summary": "Company revenue, annualized pace and growth, with figures linked to their sources.",
                        "group": "market", "products": [], "aliases": ["market", "revenue"], "href": "/explore/#business-health"})
    summary["homeSearch"] = write_asset(destination, "search", dict(identity, entries=search_rows, workTitles=work_titles))
    company_map = {company["id"]: company for company in data["companies"]}
    editorial_map = {entry["company_id"]: entry for entry in sidecars["EDITORIAL"]["entries"]}
    company_search = {}
    for cid, company in company_map.items():
        product_values = [value for product in data["products"] if product["company_id"] == cid for value in (product.get("name"), product.get("work_performed"))]
        offering_values = [value for product in current_products[cid] for value in (product.get("name"), product.get("description"), *product.get("aliases", []))]
        values = [company["name"], *company.get("aliases", []), company.get("description"), editorial_map.get(cid, {}).get("summary") or company.get("description"), *product_values, *offering_values]
        company_search[cid] = " ".join(str(value) for value in values if value).lower()
    summary["fullSearch"] = write_asset(destination, "full-search", dict(identity, data={"dataset_version": data["dataset_version"]}, companySearch=company_search,
                                                                     profileProducts=rooted_assets(current_products), editorialReadouts=copy.deepcopy(data["editorial_readouts"]),
                                                                     researchSearchEntries=public_search_entries, workTitles=work_titles,
                                                                     workSearch={route["id"]: work_search_text(route, company_map) for route in sidecars["WORK_ROUTES"]["routes"]}))
    # The full archive is fetched only by the explicitly opened method/archive view.
    summary["archive"] = write_asset(destination, "archive", dict(identity, data=data, businessHealth=sidecars["BUSINESS_HEALTH"], sourceUpdates=copy.deepcopy(sidecars["SOURCE_UPDATES"])))
    health = sidecars["BUSINESS_HEALTH"] or {}
    financial_metrics = [metric for metric in data["metrics"] if metric["kind"] in ("revenue", "arr", "annualized_revenue_run_rate")]
    overview_claim_ids = {cid for observation in health.get("observations", []) for cid in observation.get("claim_ids", [])} | {metric["claim_id"] for metric in financial_metrics}
    canonical_claim_ids = {claim["id"] for claim in data["claims"]}
    for key in ("assessments", "editorial_readouts", "unknowns"):
        overview_claim_ids.update(value for value in strings(data.get(key, [])) if value in canonical_claim_ids)
    source_updates = sidecars["SOURCE_UPDATES"] or {}
    # Retain the claims needed to validate exact financial-basis context in Market.
    bound_basis_claim_ids = {row["id"] for update in (source_updates.get("evidence_context") or {}).get("corrections", [])
                             if update.get("kind") == "financial-basis-source-supplement" and update["target"]["claim_id"] in overview_claim_ids
                             for row in update["historical_snapshot"]["claims"]}
    overview_claim_ids.update(bound_basis_claim_ids)
    overview_claims = [claim for claim in data["claims"] if claim["id"] in overview_claim_ids]
    overview_source_ids = {sid for claim in overview_claims for field in ("source_ids", "historical_source_ids") for sid in claim.get(field, [])}
    overview_data = {"dataset_version": data["dataset_version"], "claims": overview_claims,
                     "sources": [source for source in data["sources"] if source["id"] in overview_source_ids], "metrics": financial_metrics,
                     **{key: copy.deepcopy(data.get(key, [])) for key in ("companies", "assessments", "editorial_readouts", "unknowns")}}
    summary["overview"] = write_asset(destination, "overview", dict(identity, data=overview_data, businessHealth=sidecars["BUSINESS_HEALTH"], sourceUpdates=copy.deepcopy(sidecars["SOURCE_UPDATES"])))
    summary_asset = write_asset(destination, "summary", summary)
    return summary, summary_asset
