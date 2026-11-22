"""Render source-bound homepage examples and a separately timed work promotion."""
import datetime as dt
from html import escape
import json

from editorial_work import RECEIPT_RESULTS, primary_routes

RIGHT_ARROW = '<svg class="home-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 12h16m-7-7 7 7-7 7"/></svg>'
EXTERNAL_ARROW = '<svg class="home-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true" focusable="false"><path d="M7 17 17 7M7 7h10v10"/></svg>'
SNORKEL_METRIC = "snorkel_ai.metric.major-growth_metrics-0"
SNORKEL_METRIC_SOURCE = "snorkel_ai.source.audit-s5"
RECORDED_PROGRAMS = (
    ("snorkel_ai.work.expert-community", "snorkel_ai.work.expert-community.review-2026-10-28", "Snorkel Expert Community"),
    ("invisible.work.meridial-network", "invisible.work.meridial-network.review-2026-10-28", "Meridial expert network"),
)
FAILED_CHECKS = (RECEIPT_RESULTS - {"readable"}) | {"closed", "gone", "unpublished", "official_role_not_found", "official_role_not_found_redirect"}


def label_date(value):
    return dt.date.fromisoformat(value[:10]).strftime("%-d %b %Y")


def date_tag(value):
    return f'<time datetime="{escape(value[:10])}">{label_date(value)}</time>'


def approved_receipt(route):
    review = route.get("editorial_review", {})
    selected = review.get("approved_terms_receipt_id")
    return next((r for r in review.get("receipts", []) if r.get("id") == selected and r.get("approved") is True and r.get("scope") == "key_terms" and r.get("result") == "readable" and r.get("approval_basis") in ("source_content_review", "editorial_source_review")), None)


def receipt_time(receipt):
    return receipt.get("checked_at") or receipt["checked_on"][:10] + "T00:00:00Z"


def failed_since_review(route, approval):
    """A later failure at the promoted destination makes that approval ineligible."""
    url = route.get("url")
    source_ids = {source["id"] for source in route.get("sources", []) if url and source.get("url") == url}
    receipts = route.get("editorial_review", {}).get("receipts", [])
    if any(receipt.get("scope") == "retrieval" and receipt.get("source_id") in source_ids
           and receipt.get("result") in FAILED_CHECKS and receipt_time(receipt) > receipt_time(approval)
           for receipt in receipts):
        return True
    for field in ("last_route_check", "last_link_check"):
        check = route.get(field) or {}
        if (check.get("result") in FAILED_CHECKS or check.get("http_status") in (404, 410)) and (
                check.get("checked_at", "") > receipt_time(approval) or check.get("date", "") > approval["checked_on"]):
            return True
    return False


def promotion_candidates(work, release):
    routes = {r["id"]: r for r in primary_routes(work)}
    max_age = release.get("publication_policy", {}).get("homepage_work_max_age_days", 3)
    result = []
    for route_id in release.get("homepage", {}).get("work_candidate_route_ids", []):
        route = routes.get(route_id)
        receipt = approved_receipt(route) if route else None
        if not receipt or failed_since_review(route, receipt):
            continue
        reviewed = receipt_time(receipt)
        reviewed_at = dt.datetime.fromisoformat(reviewed.replace("Z", "+00:00"))
        expires = reviewed_at + dt.timedelta(days=max_age)
        result.append({"route": route, "receipt": receipt, "reviewedAt": reviewed, "expiresAt": expires.isoformat().replace("+00:00", "Z")})
    return sorted(result, key=lambda item: item["route"]["route_kind"] != "named_listing")


def work_promotion(candidate, companies):
    route, receipt = candidate["route"], candidate["receipt"]
    conditions = [route.get("geography", ""), *route.get("requirements", [])]
    for value in (route.get("assessment"), route.get("hours"), route.get("duration")):
        if value:
            conditions.append(value)
    conditions = list(dict.fromkeys(value for value in conditions if value))
    if route["route_kind"] == "named_listing":
        kind, original = "Public listing", "Original listing"
    else:
        kind, original = "Expert network", "Official program page"
    return ('<article class="example-card home-work-current" data-home-route="' + escape(route["id"], quote=True) + '">'
            '<p class="example-kind">' + kind + ' · ' + escape(companies[route["company_id"]]["name"]) + '</p>'
            '<h2 class="example-title">' + escape(route["role"]) + '</h2><p class="example-pay">' + escape(route.get("pay_label", "Pay not stated")) + '</p>'
            '<ul class="example-conditions">' + ''.join('<li>' + escape(value) + '</li>' for value in conditions) + '</ul>'
            '<p class="example-meta">Terms checked ' + date_tag(receipt["checked_on"]) + '</p>'
            '<p class="example-note">Check the provider’s current terms, eligibility and project availability.</p>'
            '<div class="example-actions"><a class="example-action" href="/company/' + escape(route["company_id"], quote=True) + '/#' + escape(route["id"], quote=True) + '">Read requirements and sources ' + RIGHT_ARROW + '</a>'
            '<a class="example-action" href="' + escape(route["url"], quote=True) + '" target="_blank" rel="noopener noreferrer">' + original + ' ' + EXTERNAL_ARROW + '<span class="sr-only"> (opens in a new tab)</span></a></div></article>')


def company_example(companies, sidecars):
    from static_pages import value_text

    health = sidecars.get("BUSINESS_HEALTH") or {}
    figure = next((row for row in health.get("observations", []) if row["id"] == SNORKEL_METRIC), None)
    source = next((row for row in health.get("sources", []) if row["id"] == SNORKEL_METRIC_SOURCE), None)
    entry = next((row for row in sidecars["EDITORIAL"]["entries"] if row["company_id"] == "snorkel_ai"), None)
    if not (entry and "snorkel_ai" in companies and figure and source
            and source["id"] in figure["source_ids"] and source.get("published_on") == figure["as_of"]
            and figure["measure"] == "annualized_revenue" and figure["scope"] == "company"
            and figure["period"]["type"] == "run_rate" and figure["evidence_assurance"] == "Company-reported"):
        return ('<article class="example-card company-example"><h3 class="example-title">AI data companies</h3>'
                '<div class="example-actions"><a class="example-action" href="/companies/">Browse sourced company profiles</a></div></article>')
    return (f'<article class="example-card company-example" data-observation="{SNORKEL_METRIC}" data-source="{SNORKEL_METRIC_SOURCE}">'
            f'<p class="example-kind">Company</p><h3 class="example-title">{escape(companies["snorkel_ai"]["name"])}</h3>'
            f'<p class="example-summary">{escape(entry["summary"])}</p>'
            f'<p class="example-pay">{escape(value_text(figure))} {escape(figure["label"].lower())}</p>'
            f'<p class="example-meta">{escape(figure["evidence_assurance"])} · {date_tag(figure["as_of"])}</p>'
            '<div class="example-actions"><a class="example-action" href="/company/snorkel_ai/">Read profile</a>'
            f'<a class="example-action" href="{escape(source["url"], quote=True)}">Original disclosure</a></div></article>')


def recorded_work_example(work):
    routes = {row["id"]: row for row in primary_routes(work) if row["route_kind"] == "network_program"}
    for route_id, source_id, title in RECORDED_PROGRAMS:
        route = routes.get(route_id)
        if not route:
            continue
        pay = route.get("field_reviews", {}).get("pay", {})
        source = next((row for row in route["sources"] if row["id"] == source_id and row.get("retrieval_status") == "content_reviewed"), None)
        if source and source_id in pay.get("source_ids", []) and route.get("pay_label"):
            return (f'<article class="example-card work-example" data-recorded-program="{route_id}" data-source="{source_id}">'
                    f'<p class="example-kind">Recorded expert program</p><h3 class="example-title">{title}</h3>'
                    f'<p class="example-pay">Pay {escape(route["pay_label"].lower())}</p>'
                    f'<p class="example-summary">{escape(route["geography"])}</p>'
                    f'<p class="example-meta">Program page reviewed {date_tag(source["accessed_on"])}.</p>'
                    '<p class="example-note">Check current project availability with the provider.</p>'
                    f'<div class="example-actions"><a class="example-action" href="/company/{escape(route["company_id"], quote=True)}/#{route_id}">Read recorded terms</a>'
                    f'<a class="example-action" href="{escape(source["url"], quote=True)}">Official program page</a></div></article>')
    return ('<article class="example-card work-example"><h3 class="example-title">Paid work records</h3>'
            '<p class="example-summary">Find listings and expert networks with pay and requirements.</p>'
            '<div class="example-actions"><a class="example-action" href="/work/">Browse paid work</a></div></article>')


def render_home(html, data, sidecars, release, summary, current_companies=None):
    companies = {c["id"]: c for c in data["companies"]}
    company = company_example(companies, sidecars)
    work = recorded_work_example(sidecars["WORK_ROUTES"])
    fallback = ('<article class="example-card home-work-fallback"><h2 class="example-title">More paid work</h2>'
                '<p class="example-summary">Compare pay and requirements for public listings and expert networks.</p>'
                '<div class="example-actions"><a class="example-action" href="/work/">Browse paid work ' + RIGHT_ARROW + '</a></div></article>')
    candidates = promotion_candidates(sidecars["WORK_ROUTES"], release)
    config = {**{key: summary[key] for key in ("schemaVersion", "buildId", "editorialReleaseId", "datasetVersion")}, "search": summary["homeSearch"], "candidates": []}
    templates = []
    for i, candidate in enumerate(candidates):
        if candidate["route"]["company_id"] not in companies:
            continue
        template_id = "home-work-candidate-" + str(i)
        templates.append('<template id="' + template_id + '">' + work_promotion(candidate, companies) + '</template>')
        config["candidates"].append({"templateId": template_id, "reviewedAt": candidate["reviewedAt"], "expiresAt": candidate["expiresAt"], "routeId": candidate["route"]["id"]})
    primary = len(primary_routes(sidecars["WORK_ROUTES"]))
    directory_count = len(companies.keys() | {row["entity_id"] for row in (current_companies or {}).get("entries", [])})
    html = (html.replace("{{HOME_COMPANY_EXAMPLE}}", company).replace("{{HOME_WORK_EXAMPLE}}", work)
            .replace("{{HOME_WORK_PROMOTION}}", fallback).replace("{{PRIMARY_WORK_COUNT}}", str(primary))
            .replace("{{DIRECTORY_COUNT}}", str(directory_count)))
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return html.replace("</body>", ''.join(templates) + '<script id="home-config" type="application/json">' + config_json + '</script></body>')
