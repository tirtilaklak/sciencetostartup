"""Homepage examples use approved receipts; time only withdraws runtime promotion."""
import datetime as dt
from html import escape
import json

RIGHT_ARROW = '<svg class="home-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 12h16m-7-7 7 7-7 7"/></svg>'
EXTERNAL_ARROW = '<svg class="home-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true" focusable="false"><path d="M7 17 17 7M7 7h10v10"/></svg>'


def label_date(value):
    return dt.date.fromisoformat(value[:10]).strftime("%-d %b %Y")


def approved_receipt(route):
    review = route.get("editorial_review", {})
    selected = review.get("approved_terms_receipt_id")
    return next((r for r in review.get("receipts", []) if r.get("id") == selected and r.get("approved") is True and r.get("scope") == "key_terms" and r.get("result") == "readable" and r.get("approval_basis") in ("source_content_review", "editorial_source_review")), None)


def promotion_candidates(work, release):
    from editorial_work import primary_routes
    routes = {r["id"]: r for r in primary_routes(work)}
    max_age = release.get("publication_policy", {}).get("homepage_work_max_age_days", 3)
    result = []
    for route_id in release.get("homepage", {}).get("work_candidate_route_ids", []):
        route = routes.get(route_id)
        receipt = approved_receipt(route) if route else None
        if not receipt or route.get("route_kind") not in ("named_listing", "network_program"):
            continue
        reviewed = receipt.get("checked_at") or receipt["checked_on"][:10] + "T00:00:00Z"
        reviewed_at = dt.datetime.fromisoformat(reviewed.replace("Z", "+00:00"))
        expires = reviewed_at + dt.timedelta(days=max_age)
        result.append({"route": route, "receipt": receipt, "reviewedAt": reviewed, "expiresAt": expires.isoformat().replace("+00:00", "Z")})
    return sorted(result, key=lambda item: item["route"]["route_kind"] != "named_listing")


def work_example(candidate, companies):
    route, receipt = candidate["route"], candidate["receipt"]
    conditions = [route.get("geography", ""), *route.get("requirements", [])]
    for value in (route.get("assessment"), route.get("hours"), route.get("duration")):
        if value:
            conditions.append(value)
    conditions = list(dict.fromkeys(value for value in conditions if value))
    kind = "Example public listing" if route["route_kind"] == "named_listing" else "Example expert network"
    return ('<article class="example-card work-example home-work-current" data-home-route="' + escape(route["id"], quote=True) + '">'
            '<p class="example-kind">' + kind + '</p><p class="example-company">' + escape(companies[route["company_id"]]["name"]) + '</p>'
            '<h3 class="example-title">' + escape(route["role"]) + '</h3><p class="example-pay">' + escape(route.get("pay_label", "Pay not stated")) + '</p>'
            '<ul class="example-conditions">' + ''.join('<li>' + escape(value) + '</li>' for value in conditions) + '</ul>'
            '<p class="example-meta">Terms checked <time datetime="' + escape(receipt["checked_on"][:10]) + '">' + label_date(receipt["checked_on"]) + '</time></p>'
            '<p class="example-note">A public route is not a guarantee of tasks, acceptance or payment. Check the provider’s current terms.</p>'
            '<div class="example-actions"><a class="example-action" href="/explore/#company/' + escape(route["company_id"], quote=True) + '/work">Read requirements and sources ' + RIGHT_ARROW + '</a>'
            '<a class="example-action" href="' + escape(route["url"], quote=True) + '" target="_blank" rel="noopener noreferrer">Original listing ' + EXTERNAL_ARROW + '<span class="sr-only"> (opens in a new tab)</span></a></div></article>')


def render_home(html, data, sidecars, release, summary, current_companies=None):
    companies = {c["id"]: c for c in data["companies"]}
    entry = next((e for e in sidecars["EDITORIAL"]["entries"] if e["company_id"] == "snorkel_ai"), None)
    if entry and "snorkel_ai" in companies:
        reviewed = entry.get("reviewed_on", "2026-10-14")
        company = ('<article class="example-card company-example"><p class="example-kind">Example company</p><h3 class="example-title">Snorkel AI</h3>'
                   '<p class="example-summary">' + escape(entry["summary"]) + '</p><p class="example-meta">Summary reviewed <time datetime="' + reviewed + '">' + label_date(reviewed) + '</time></p>'
                   '<p class="example-source">Company descriptions and financial figures keep their own sources and review dates.</p><div class="example-actions"><a class="example-action" href="/company/snorkel_ai/">Explore company ' + RIGHT_ARROW + '</a></div></article>')
    else:
        company = '<article class="example-card company-example"><h3>Understand AI data companies.</h3><p><a href="/companies/">Browse sourced company profiles ' + RIGHT_ARROW + '</a></p></article>'
    fallback = '<article class="example-card work-example home-work-fallback"><p class="example-kind">Paid AI training work</p><h3 class="example-title">Find a route that fits your expertise.</h3><p class="example-summary">Compare public listings and expert networks, with pay conditions and requirements beside the source.</p><div class="example-actions"><a class="example-action" href="/work/">Browse paid work ' + RIGHT_ARROW + '</a></div></article>'
    candidates = promotion_candidates(sidecars["WORK_ROUTES"], release)
    config = {**{key: summary[key] for key in ("schemaVersion", "buildId", "editorialReleaseId", "datasetVersion")}, "search": summary["homeSearch"], "candidates": []}
    templates = []
    for i, candidate in enumerate(candidates):
        if candidate["route"]["company_id"] not in companies:
            continue
        template_id = "home-work-candidate-" + str(i)
        templates.append('<template id="' + template_id + '">' + work_example(candidate, companies) + '</template>')
        config["candidates"].append({"templateId": template_id, "reviewedAt": candidate["reviewedAt"], "expiresAt": candidate["expiresAt"], "routeId": candidate["route"]["id"]})
    work = '<div class="home-work-slot" id="home-work-example">' + fallback + '</div>'
    from editorial_work import primary_routes
    primary = len(primary_routes(sidecars["WORK_ROUTES"]))
    directory_count = len(companies) + len((current_companies or {}).get("entries", []))
    html = html.replace("{{HOME_COMPANY_EXAMPLE}}", company).replace("{{HOME_WORK_EXAMPLE}}", work).replace("{{PRIMARY_WORK_COUNT}}", str(primary)).replace("{{DIRECTORY_COUNT}}", str(directory_count))
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return html.replace("</body>", ''.join(templates) + '<script id="home-config" type="application/json">' + config_json + '</script></body>')
