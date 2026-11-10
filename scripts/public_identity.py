"""One validated public identity; no credentials or unconfirmed affiliations."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _https(value):
    parsed = urlsplit(str(value))
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def validate_identity(identity):
    required = {"schema_version", "updated_on", "brand", "origin", "description", "publisher", "repository", "contacts", "products", "disclosures", "review_policy", "external_profiles"}
    if not isinstance(identity, dict) or set(identity) != required:
        raise ValueError("public identity: unexpected or missing fields")
    if identity["schema_version"] != "1.0.0" or identity["brand"] != "ScienceToStartup":
        raise ValueError("public identity: unsupported identity")
    date.fromisoformat(identity["updated_on"])
    if identity["origin"] != "https://sciencetostartup.com":
        raise ValueError("public identity: canonical origin changed")
    publisher = identity["publisher"]
    if set(publisher) != {"id", "name", "url", "website", "type"} or publisher["type"] != "Person":
        raise ValueError("public identity: publisher must be the disclosed person")
    if publisher["id"] != identity["origin"] + "/#publisher" or publisher["url"] != identity["origin"] + "/method/#about":
        raise ValueError("public identity: publisher identifiers drifted")
    if not publisher["name"].strip() or not all(_https(publisher[k]) for k in ("id", "url", "website")):
        raise ValueError("public identity: invalid publisher")
    repo = identity["repository"]
    if set(repo) != {"url", "owner", "name"} or repo["url"] != f'https://github.com/{repo["owner"]}/{repo["name"]}':
        raise ValueError("public identity: invalid repository")
    if not all(_https(url) for url in identity["contacts"].values()):
        raise ValueError("public identity: unsafe contact link")
    for product in identity["products"]:
        if set(product) != {"id", "title", "path", "status"} or product["status"] not in {"public", "prelaunch", "retired"}:
            raise ValueError("public identity: invalid product")
        if not re.fullmatch(r"/[a-z0-9/_-]*/", product["path"]):
            raise ValueError("public identity: invalid product path")
    policy = identity["review_policy"]
    if policy.get("automated_review_label") != "Separate AI review" or policy.get("external_credit_requires_consent") is not True:
        raise ValueError("public identity: review attribution weakened")
    if policy.get("external_participation_required_for_release") is not False or policy.get("outreach_status") != "drafts_only":
        raise ValueError("public identity: unsupported review or outreach authority")
    if len(identity["disclosures"]) < 3:
        raise ValueError("public identity: missing conflicts disclosure")
    for profile in identity["external_profiles"]:
        if set(profile) != {"service", "url", "status"} or not _https(profile["url"]):
            raise ValueError("public identity: invalid external profile")
        if profile["status"] not in {"verified_current", "update_pending", "owner_access_required", "namespace_owner_access_required"}:
            raise ValueError("public identity: unknown external state")
    return identity


def load_identity(root=ROOT):
    return validate_identity(json.loads((Path(root) / "data/public-identity.json").read_text()))


def publisher_node(identity=None):
    identity = identity or load_identity()
    person = identity["publisher"]
    return {"@type": "Person", "@id": person["id"], "name": person["name"], "url": person["url"], "sameAs": [person["website"]]}


def review_contributions(root=ROOT):
    """Only consented, scoped contributions may become public credit."""
    payload = json.loads((Path(root) / "data/review-contributions.json").read_text())
    if set(payload) != {"schema_version", "contributions"} or payload["schema_version"] != "1.0.0":
        raise ValueError("review contributions: unsupported schema")
    for row in payload["contributions"]:
        if not all(row.get(k) for k in ("id", "edition_id", "section_id", "contribution", "source_url")):
            raise ValueError("review contributions: missing scoped evidence")
        if row.get("credit_consent") is not True or not _https(row["source_url"]):
            raise ValueError("review contributions: public credit requires consent and source")
        if row.get("reviewer_type") not in {"human", "ai"}:
            raise ValueError("review contributions: actual reviewer type required")
    return payload["contributions"]
