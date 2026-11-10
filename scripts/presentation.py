"""Reproducible presentation assets. Research exports remain the canonical archive."""
import copy
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


SCHEMA_VERSION = "1.0.0"


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


def retain_runtime_generations(root, destination):
    manifest = json.loads((root / "release-assets/generations.json").read_text())
    generations = manifest["generations"]
    if len(generations) != 2:
        raise ValueError("Exactly two prior runtime generations must be retained")
    for generation in generations:
        for name, digest in generation["sha256"].items():
            parts = Path(name).parts
            if len(parts) != 2 or parts[0] not in ("js", "presentation") or ".." in parts or Path(name).suffix not in (".js", ".json"):
                raise ValueError("Invalid retained runtime asset")
            content = (root / "release-assets" / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Retained runtime checksum differs: " + name)
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


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


def health_subset(health, observations):
    if health is None:
        return None
    result = copy.deepcopy(health)
    result["observations"] = observations
    claim_ids = {cid for observation in observations for cid in observation.get("claim_ids", [])}
    source_ids = {sid for observation in observations for sid in observation.get("source_ids", [])}
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
                "source_urls": " | ".join(sources[sid]["url"] for sid in observation.get("source_ids", []) if sources.get(sid, {}).get("url")),
                "scope_label": observation.get("scope_label") or research.scope_text(observation.get("scope"), company_id),
                "limitations": observation.get("limitations") or ""}
    metric = research.headline(company_id)
    if not metric:
        return None
    return {"id": metric["id"], "kind": metric["kind"], "value": metric["value"], "qualifier": metric.get("qualifier") or "",
            "display": financial_value(metric), "upper_value": metric.get("upper_value", ""), "observation_status": metric.get("observation_status") or "",
            "currency": metric.get("currency") or "", "as_of": metric.get("as_of") or "", "period": metric.get("period_label") or "",
            "scope": metric.get("segment_scope") or "", "scope_detail": metric.get("scope_detail") or "", "accounting_basis": metric.get("gross_vs_net") or "",
            "source_urls": " | ".join(research.sources[sid]["url"] for sid in research.claim(metric).get("source_ids", []) if research.sources.get(sid, {}).get("url")),
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
            record = next((s for s in health.get("sources", []) if s["id"] in observation.get("source_ids", [])), None) or research.sources.get(next(iter(observation.get("source_ids", [])), ""))
            fresh = next((c for c in health.get("fresh_claims", []) if c["id"] in observation.get("claim_ids", [])), {})
            checked = fresh.get("observed_on") or next((c.get("checked_on") for c in health.get("source_checks", {}).get("entries", []) if c["source_id"] in observation.get("source_ids", []) and c.get("status") == "content_checked"), None)
            end = observation.get("period", {}).get("end") or next(iter(re.findall(r"\d{4}(?:-\d{2}){0,2}", str(observation.get("as_of") or ""))), "")
            financial = {"recordType": "observation", "id": observation["id"], "claimId": next(iter(observation.get("claim_ids", [])), None),
                         "display": current["display"], "type": "Annualized pace" if observation["measure"] == "annualized_revenue" else "Revenue",
                         "period": current["period"], "currency": current["currency"], "scope": current["scope_label"],
                         "basis": "Gross revenue" if observation.get("accounting_basis") == "gross" else "Net revenue" if observation.get("accounting_basis") == "net" else "Gross/net not disclosed" if observation["measure"] == "annualized_revenue" else "",
                         "attribution": observation.get("evidence_assurance") or "Attributed source", "limitations": observation.get("limitations") or "",
                         "quote": observation.get("original_text") or fresh.get("excerpt") or "", "checkedOn": checked,
                         "source": {"url": record["url"], "publisher": record.get("publisher") or "Original source"} if record else None,
                         "failed": observation.get("refresh_status") == "source_unavailable" or any(c.get("status") == "unavailable" and c["source_id"] in observation.get("source_ids", []) for c in health.get("source_checks", {}).get("entries", [])),
                         "age": "historical" if not end or end < "2025-10-28" else "current"}
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
                         "source": {"url": record["url"], "publisher": record.get("publisher") or "Original source"} if record else None,
                         "failed": False, "age": "undated" if rank == "0000" else "historical" if end < "2025-10-28" else "current"}
            historical = research.historical_year(metric)
            if historical:
                financial["historicalYear"] = historical
        result[cid] = {"firstOffering": {"name": products[0]["name"]} if products else None, "hasFinancial": bool(metric),
                       "financial": financial, "currentCompanyResult": current}
    return result, products_by_company, research


def search_fold(value):
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.category(ch).startswith("M")).lower()


def work_search_text(route, companies):
    from static_pages import work_location
    company = companies.get(route["company_id"], {})
    values = [company.get("name"), *company.get("aliases", []), route.get("role"), route.get("summary"), route.get("group"), route.get("geography"), work_location(route), route.get("pay_label"), route.get("hours"), route.get("duration"), *route.get("requirements", [])]
    return search_fold(" ".join(str(value) for value in values if value))


def compact_work(work, research=None):
    result = copy.deepcopy(work)
    for route in result.get("routes", []):
        if research:
            from static_pages import UNCERTAIN_CHECK, work_action
            check = route.get("last_route_check") or {}
            route["uncertain"] = (route.get("status") in ("unverified", "intake_unverified", "pay_conflict")
                                  or (route.get("last_link_check") or {}).get("result") in ("blocked", "not_found", "unavailable")
                                  or ((route.get("research_record") or {}).get("route") or {}).get("live_application_verified") is False
                                  or bool(UNCERTAIN_CHECK.search(" ".join(str(v) for v in (check.get("result"), check.get("note")) if v))))
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
        route["field_reviews"] = {field: {k: v for k, v in value.items() if k in ("state", "reviewed_on", "source_ids", "basis") or field == "location" and k == "note"} for field, value in route.get("field_reviews", {}).items()}
        review = route.get("editorial_review")
        if review:
            route["editorial_review"] = {key: value for key, value in review.items() if key in ("triaged_on", "approved_terms_receipt_id", "disposition", "alternative_destination")}
            route["editorial_review"]["receipts"] = [{k: v for k, v in receipt.items() if k in ("id", "source_id", "checked_on", "checked_at", "scope", "result", "approved", "approval_basis", "reviewer", "reviewed_fields")} for receipt in review.get("receipts", []) if receipt.get("id") == review.get("approved_terms_receipt_id")]
    return result


def build_presentation(data, destination, root, sidecars, release):
    identity = {"schemaVersion": SCHEMA_VERSION, "buildId": source_identity(root),
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
        detail["businessHealth"] = health_subset(sidecars["BUSINESS_HEALTH"], [o for o in (sidecars["BUSINESS_HEALTH"] or {}).get("observations", []) if o["company_id"] == cid])
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
    search_rows = []
    for company in data["companies"]:
        entry = next((e for e in sidecars["EDITORIAL"]["entries"] if e["company_id"] == company["id"]), {})
        products = next((e.get("products", []) for e in sidecars["PROFILE_CONTENT"]["entries"] if e["company_id"] == company["id"]), [])
        search_rows.append({"id": company["id"], "name": company["name"], "summary": entry.get("summary", company.get("description", "")), "group": entry.get("primary_offering", ""), "products": [p["name"] for p in products], "href": "/company/" + company["id"] + "/"})
    for entry in sidecars.get("RESEARCH_SEARCH", []):
        search_rows.append({"id": entry["url"], "name": entry["title"], "summary": entry["summary"], "group": entry["kind"], "products": entry.get("keywords", []), "href": entry["url"]})
    summary["researchSearchEntries"] = sidecars.get("RESEARCH_SEARCH", [])
    summary["homeSearch"] = write_asset(destination, "search", dict(identity, entries=search_rows))
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
                                                                     workSearch={route["id"]: work_search_text(route, company_map) for route in sidecars["WORK_ROUTES"]["routes"]}))
    # The full archive is fetched only by the explicitly opened method/archive view.
    summary["archive"] = write_asset(destination, "archive", dict(identity, data=data, businessHealth=sidecars["BUSINESS_HEALTH"], sourceUpdates=copy.deepcopy(sidecars["SOURCE_UPDATES"])))
    health = sidecars["BUSINESS_HEALTH"] or {}
    financial_metrics = [metric for metric in data["metrics"] if metric["kind"] in ("revenue", "arr", "annualized_revenue_run_rate")]
    overview_claim_ids = {cid for observation in health.get("observations", []) for cid in observation.get("claim_ids", [])} | {metric["claim_id"] for metric in financial_metrics}
    canonical_claim_ids = {claim["id"] for claim in data["claims"]}
    for key in ("assessments", "editorial_readouts", "unknowns"):
        overview_claim_ids.update(value for value in strings(data.get(key, [])) if value in canonical_claim_ids)
    overview_claims = [claim for claim in data["claims"] if claim["id"] in overview_claim_ids]
    overview_source_ids = {sid for claim in overview_claims for field in ("source_ids", "historical_source_ids") for sid in claim.get(field, [])}
    overview_data = {"dataset_version": data["dataset_version"], "claims": overview_claims,
                     "sources": [source for source in data["sources"] if source["id"] in overview_source_ids], "metrics": financial_metrics,
                     **{key: copy.deepcopy(data.get(key, [])) for key in ("companies", "assessments", "editorial_readouts", "unknowns")}}
    summary["overview"] = write_asset(destination, "overview", dict(identity, data=overview_data, businessHealth=sidecars["BUSINESS_HEALTH"], sourceUpdates=copy.deepcopy(sidecars["SOURCE_UPDATES"])))
    summary_asset = write_asset(destination, "summary", summary)
    return summary, summary_asset
