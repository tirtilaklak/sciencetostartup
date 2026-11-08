"""Reproducible presentation assets. Research exports remain the canonical archive."""
import copy
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = "1.0.0"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_identity(root):
    digest = hashlib.sha256()
    paths = []
    for directory in ("web", "scripts", "schema", "design-system", "release-assets"):
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    paths.extend(p for p in (root / "data").glob("*.json") if p.is_file())
    paths.append(root / "docs/research-id-crosswalk.json")
    if (root / "deployment.json").exists():
        paths.append(root / "deployment.json")
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
            if not name.startswith("js/") or Path(name).name != name.split("/")[-1] or ".." in Path(name).parts:
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


def compact_work(work):
    result = copy.deepcopy(work)
    for route in result.get("routes", []):
        record = route.pop("research_record", None)
        hours = ((record or {}).get("route") or {}).get("hours")
        detail = hours.get("detail") if isinstance(hours, dict) else None
        if detail:
            route["research_record"] = {"route": {"hours": {"detail": detail}}}
        # Original verbatim research remains in the downloadable work-routes.json.
        route.pop("previous_checks", None)
        review = route.get("editorial_review")
        if review:
            route["editorial_review"] = {key: value for key, value in review.items() if key in ("triaged_on", "approved_terms_receipt_id", "disposition", "alternative_destination")}
            route["editorial_review"]["receipts"] = [receipt for receipt in review.get("receipts", []) if receipt.get("id") == review.get("approved_terms_receipt_id")]
    return result


def build_presentation(data, destination, root, sidecars, release):
    identity = {"schemaVersion": SCHEMA_VERSION, "buildId": source_identity(root),
                "datasetVersion": data["dataset_version"],
                "editorialReleaseId": release.get("editorial_release_id", release.get("release_id", "baseline-2026-10-28"))}
    details = {}
    for company in data["companies"]:
        cid = company["id"]
        detail = dict(identity, companyId=cid, data=company_graph(data, cid))
        # A fresh root object is installed, invalidating source-context caches safely.
        detail["profileContent"] = rooted_assets({"entries": [e for e in sidecars["PROFILE_CONTENT"].get("entries", []) if e["company_id"] == cid]})
        detail["companyEvents"] = {"events": [e for e in sidecars["COMPANY_EVENTS"].get("events", []) if e["company_id"] == cid or cid in e.get("related_company_ids", [])]}
        detail["businessHealth"] = health_subset(sidecars["BUSINESS_HEALTH"], [o for o in (sidecars["BUSINESS_HEALTH"] or {}).get("observations", []) if o["company_id"] == cid])
        details[cid] = write_asset(destination, "company-" + cid, detail)
    bootstrap = {key: copy.deepcopy(value) if not isinstance(value, list) else [] for key, value in data.items()}
    for key in ("companies", "metrics", "products", "assessments", "editorial_readouts"):
        bootstrap[key] = copy.deepcopy(data[key])
    headline_ids = {a.get("headline_metric_id") for a in data["assessments"]}
    bootstrap["metrics"] = [m for m in bootstrap["metrics"] if m["kind"] in ("revenue", "arr", "annualized_revenue_run_rate") or m["id"] in headline_ids]
    bootstrap["products"] = [{k: value for k, value in p.items() if k in ("id", "company_id", "claim_id", "name", "work_performed", "delivery_model")} for p in bootstrap["products"]]
    bootstrap["assessments"] = [{**{k: value for k, value in a.items() if k in ("id", "company_id", "segment_scope", "headline_metric_id", "material_conflict", "rubric_version")}, "gates": {key: {"level": value["level"]} for key, value in a["gates"].items()}} for a in bootstrap["assessments"]]
    required = set(strings(bootstrap)) | set(strings(sidecars["EDITORIAL"])) | set(strings(sidecars["SOURCE_UPDATES"]))
    claim_rows = [c for c in data["claims"] if c["id"] in required]
    # Summary claims carry selection metadata, never shortened quotations masquerading as evidence.
    claim_keys = ("id", "company_id", "subject", "status", "confidence", "as_of", "segment_scope", "source_ids", "observed_on", "evidence_label")
    bootstrap["claims"] = [{**{k: c[k] for k in claim_keys if k in c}, "statement": ""} for c in claim_rows]
    required_sources = {sid for c in claim_rows for sid in c["source_ids"]}
    source_keys = ("id", "company_id", "url", "publisher", "source_type", "retrieval_status", "published_on", "accessed_on")
    bootstrap["sources"] = [{k: v for k, v in s.items() if k in source_keys} for s in data["sources"] if s["id"] in required_sources]
    bootstrap["raw_inputs"] = []
    stats = {"companies": len(data["companies"]), "sources": len(data["sources"]),
             "sourcePages": len({s["url"] for s in data["sources"]}), "claims": len(data["claims"]),
             "currentClaims": sum(c["status"] != "superseded" for c in data["claims"])}
    exports = {}
    for name in ("research.json", "observatory.sqlite", "work-routes.json"):
        path = destination / name
        if name == "work-routes.json" and not path.exists():
            path = root / "data/work-routes.json"
        if path.exists():
            exports[name.split(".")[0]] = {"href": "/" + name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    summary = dict(identity, bootstrap=bootstrap, companies=bootstrap["companies"], work=compact_work(sidecars["WORK_ROUTES"]),
                   companyDetails=details, statistics=stats, exports=exports,
                   publicationAsOf=release.get("publication_as_of", release.get("published_at", "2026-11-08T20:30:00Z")))
    search_rows = []
    for company in data["companies"]:
        entry = next((e for e in sidecars["EDITORIAL"]["entries"] if e["company_id"] == company["id"]), {})
        products = next((e.get("products", []) for e in sidecars["PROFILE_CONTENT"]["entries"] if e["company_id"] == company["id"]), [])
        search_rows.append({"id": company["id"], "name": company["name"], "summary": entry.get("summary", company.get("description", "")), "group": entry.get("primary_offering", ""), "products": [p["name"] for p in products], "href": "/explore/#company/" + company["id"]})
    summary["homeSearch"] = write_asset(destination, "search", dict(identity, entries=search_rows))
    # The full archive is fetched only by the explicitly opened method/archive view.
    summary["archive"] = write_asset(destination, "archive", dict(identity, data=data, businessHealth=sidecars["BUSINESS_HEALTH"]))
    health = sidecars["BUSINESS_HEALTH"] or {}
    overview_claim_ids = {cid for observation in health.get("observations", []) for cid in observation.get("claim_ids", [])}
    overview_claims = [claim for claim in data["claims"] if claim["id"] in overview_claim_ids]
    overview_source_ids = {sid for claim in overview_claims for sid in claim["source_ids"]}
    overview_data = {"dataset_version": data["dataset_version"], "claims": overview_claims,
                     "sources": [source for source in data["sources"] if source["id"] in overview_source_ids]}
    summary["overview"] = write_asset(destination, "overview", dict(identity, data=overview_data, businessHealth=sidecars["BUSINESS_HEALTH"]))
    summary_asset = write_asset(destination, "summary", summary)
    return summary, summary_asset
