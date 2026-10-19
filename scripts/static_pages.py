#!/usr/bin/env python3
"""Lean crawlable company pages and a sitemap beside the hash-routed app.

The interactive dashboard is one large HTML document routed by URL fragments,
so search engines see a single URL. This module writes a small static page per
company at /company/<id>/, an index at /companies/, and a sitemap listing them.
Pages embed no dataset and no application script; every string is escaped and
the output is deterministic so rebuilds stay byte-identical.
"""
import html
import json
import re
from pathlib import Path

ORIGIN = "https://sciencetostartup.com"
SITE_NAME = "ScienceToStartup"
DESCRIPTION_LIMIT = 155
METRIC_LIMIT = 8
PRODUCT_LIMIT = 6
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DATE_IN_TEXT = re.compile(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")

KIND_ORDER = ("annualized_revenue_run_rate", "arr", "revenue", "valuation", "funding_total_reported", "funding_total_calculated", "growth_rate", "headcount", "expert_network", "customer_count", "other")
KIND_LABELS = {"annualized_revenue_run_rate": "Annualized revenue run rate", "arr": "ARR", "revenue": "Revenue", "valuation": "Valuation", "funding_total_reported": "Total funding (reported)", "funding_total_calculated": "Total funding (calculated)", "growth_rate": "Growth rate", "headcount": "Headcount", "expert_network": "Expert network", "customer_count": "Customers", "other": "Other metric"}
QUALIFIERS = {"at_least": "at least ", "greater_than": "more than ", "approximate": "about ", "nearly": "nearly ", "at_most": "up to "}
CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}

STYLE = (
    "body{margin:0;background:#FAFAF7;color:#1D2B2A;font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
    "main,header,footer{max-width:72ch;margin:0 auto;padding:0 16px}"
    "header{padding-top:20px;font-size:14px}header a,footer a{color:#176B61}"
    "a{color:#176B61;text-underline-offset:3px}"
    "h1{font-size:34px;line-height:1.1;letter-spacing:-1px;margin:28px 0 12px}"
    "h2{font-size:22px;margin:36px 0 12px}"
    ".eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#176B61;font-weight:600;margin:28px 0 0}"
    ".lede{font-size:18px;color:#44524f}"
    ".cta{display:inline-block;margin:8px 0 20px;padding:10px 16px;border:1px solid #176B61;border-radius:4px;text-decoration:none;font-weight:600}"
    "dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;font-size:15px}dl.facts dt{color:#596664}dl.facts dd{margin:0;overflow-wrap:anywhere}"
    "table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:8px 10px 8px 0;border-bottom:1px solid #DEE3DF}th{color:#596664;font-weight:500}"
    "td.value{font-weight:600;white-space:nowrap}ul{padding-left:20px}li{margin:6px 0;overflow-wrap:anywhere}"
    ".muted{color:#596664;font-size:13px}footer{padding:32px 16px 48px;color:#596664;font-size:13px;border-top:1px solid #DEE3DF;margin-top:40px}"
    "@media(max-width:600px){h1{font-size:28px}dl.facts{grid-template-columns:1fr}table,thead,tbody,tr,td,th{display:block}thead{display:none}td{padding:3px 0;border:0}tr{padding:8px 0;border-bottom:1px solid #DEE3DF}td.value{white-space:normal}}"
)


def escape(value):
    return html.escape("" if value is None else str(value), quote=True)


def truncate(text, limit=DESCRIPTION_LIMIT):
    text = " ".join(str(text or "").split())
    if len(text) <= limit: return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:") + "…"


def date_key(as_of):
    """Sortable (year, month, day) from a date-like label; undated sorts first."""
    match = DATE_IN_TEXT.search(str(as_of or ""))
    if not match: return (0, 0, 0)
    return tuple(int(part) if part else 0 for part in match.groups())


def compact_number(value):
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= divisor:
            scaled = value / divisor
            text = f"{scaled:.2f}" if abs(scaled) < 10 else f"{scaled:.1f}"
            return text.rstrip("0").rstrip(".") + suffix
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def format_value(metric):
    value = metric.get("value")
    unit = metric.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool): text = str(value)
    elif unit == "currency":
        currency = metric.get("currency") or ""
        symbol = CURRENCY_SYMBOLS.get(currency)
        text = (symbol + compact_number(value)) if symbol else (compact_number(value) + (" " + currency if currency else ""))
    elif unit == "percent": text = f"{value:g}%"
    elif unit == "multiple": text = f"{value:g}x"
    elif unit in ("count", "people"): text = compact_number(value) if abs(value) >= 1e6 else (f"{value:,.0f}" if float(value).is_integer() else f"{value:g}")
    else: text = f"{value:,.0f}" if float(value).is_integer() else f"{value:g}"
    text = QUALIFIERS.get(metric.get("qualifier"), "") + text
    notes = []
    if metric.get("reported_vs_estimated") == "estimated": notes.append("estimated")
    status = metric.get("observation_status")
    if status and status != "reported": notes.append(status)
    return text + (" (" + ", ".join(notes) + ")" if notes else "")


def headline_metrics(data, company_id, limit=METRIC_LIMIT):
    """One row per metric kind, most recent as_of first; superseded claims are skipped."""
    claims = {claim["id"]: claim for claim in data.get("claims", [])}
    sources = {source["id"]: source for source in data.get("sources", [])}
    by_kind = {}
    for metric in data.get("metrics", []):
        if metric.get("company_id") != company_id: continue
        claim = claims.get(metric.get("claim_id"), {})
        if claim.get("status") == "superseded": continue
        key = (date_key(metric.get("as_of")), metric.get("id", ""))
        kind = metric.get("kind", "other")
        if kind not in by_kind or key > by_kind[kind][0]: by_kind[kind] = (key, metric, claim)
    rows = []
    for kind in sorted(by_kind, key=lambda k: (KIND_ORDER.index(k) if k in KIND_ORDER else len(KIND_ORDER), k)):
        _, metric, claim = by_kind[kind]
        source = next((sources[sid] for sid in claim.get("source_ids", []) if sid in sources), None)
        label = str(metric.get("label", ""))
        if label.replace("_", " ").strip().lower() == kind.replace("_", " ").lower(): label = ""  # label merely repeats the kind
        rows.append({"kind": KIND_LABELS.get(kind, kind.replace("_", " ").capitalize()), "label": label, "value": format_value(metric), "as_of": metric.get("as_of", ""), "source_title": (source or {}).get("title", ""), "source_url": (source or {}).get("url", "")})
    return rows[:limit]


def company_routes(work_data, company_id):
    routes = [r for r in (work_data or {}).get("routes", []) if r.get("company_id") == company_id]
    return sorted(routes, key=lambda r: (str(r.get("role", "")).lower(), r.get("id", "")))


def json_ld(payload):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def external_link(url, label):
    return f'<a href="{escape(url)}" rel="noopener">{escape(label)}</a>'


def document(title, description, canonical, body, structured):
    head = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="color-scheme" content="light">\n'
        f"<title>{escape(title)}</title>\n<meta name=\"description\" content=\"{escape(description)}\">\n<link rel=\"canonical\" href=\"{escape(canonical)}\">\n"
        f'<meta property="og:type" content="website">\n<meta property="og:title" content="{escape(title)}">\n<meta property="og:description" content="{escape(description)}">\n<meta property="og:url" content="{escape(canonical)}">\n<meta property="og:site_name" content="{SITE_NAME}">\n'
        f"<style>{STYLE}</style>\n<script type=\"application/ld+json\">{json_ld(structured)}</script>\n</head>\n"
    )
    header = f'<header><a href="{ORIGIN}/">{SITE_NAME}</a> · <a href="{ORIGIN}/companies/">All companies</a> · <a href="{ORIGIN}/#work">Paid work</a> · <a href="{ORIGIN}/#method">Method</a></header>\n'
    footer = f'<footer><p>Public research by {SITE_NAME}. Figures carry their own dates and sources; nothing here is a verification of the companies\' current status. <a href="{ORIGIN}/#method">How evidence is graded</a> · <a href="{ORIGIN}/research.json">Download the dataset</a>.</p></footer>\n'
    return head + "<body>\n" + header + "<main>\n" + body + "</main>\n" + footer + "</body>\n</html>\n"


def website_label(url):
    return re.sub(r"^https?://(www\.)?", "", str(url or "")).rstrip("/")


def render_company(data, company, editorial_entry, profile_entry, routes, as_of):
    cid, name = company["id"], company["name"]
    canonical = f"{ORIGIN}/company/{cid}/"
    app_url = f"{ORIGIN}/#company/{cid}"
    description = " ".join(str(company.get("description", "")).split())
    summary = (editorial_entry or {}).get("summary", "")
    meta_description = truncate(f"{name}: {description}" + (f" {summary}" if summary else ""))
    title = f"{name}: business model, revenue, funding and paid work · {SITE_NAME}"
    cta = f'<p><a class="cta" href="{app_url}">Open the full interactive profile</a></p>\n'
    body = [f'<p class="eyebrow">Company profile · data as of {escape(as_of)}</p>\n<h1>{escape(name)}</h1>\n<p class="lede">{escape(description)}</p>\n', cta]
    facts = []
    if company.get("website"): facts.append(("Website", external_link(company["website"], website_label(company["website"]))))
    if company.get("founded_year"): facts.append(("Founded", escape(company["founded_year"])))
    if (editorial_entry or {}).get("primary_offering"): facts.append(("Primary offering", escape(editorial_entry["primary_offering"])))
    if (editorial_entry or {}).get("precise_category"): facts.append(("Category", escape(editorial_entry["precise_category"])))
    if company.get("categories"): facts.append(("Tags", escape(", ".join(company["categories"]))))
    if company.get("legal_entity_name") and company["legal_entity_name"] != name: facts.append(("Legal entity", escape(company["legal_entity_name"])))
    if facts: body.append('<dl class="facts">' + "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts) + "</dl>\n")
    products = [p for p in (profile_entry or {}).get("products", []) if p.get("name")][:PRODUCT_LIMIT]
    if summary or products:
        body.append(f"<h2>What {escape(name)} sells</h2>\n")
        if summary: body.append(f"<p>{escape(summary)}</p>\n")
        if products: body.append("<ul>" + "".join(f"<li><strong>{escape(p['name'])}</strong>" + (f" — {escape(p['description'])}" if p.get("description") else "") + "</li>" for p in products) + "</ul>\n")
    metrics = headline_metrics(data, cid)
    body.append("<h2>Headline metrics</h2>\n")
    if metrics:
        rows = "".join(f'<tr><td>{escape(m["kind"])}<br><span class="muted">{escape(m["label"])}</span></td><td class="value">{escape(m["value"])}</td><td>{escape(m["as_of"])}</td><td>{external_link(m["source_url"], m["source_title"]) if m["source_url"] else escape(m["source_title"])}</td></tr>' for m in metrics)
        body.append(f"<table><thead><tr><th>Metric</th><th>Value</th><th>As of</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>\n<p class=\"muted\">Most recent figure per metric kind. Run rate, ARR, revenue, funding and valuation are kept distinct; estimates and forecasts are marked.</p>\n")
    else: body.append('<p class="muted">No headline financial or scale metrics are recorded for this organization.</p>\n')
    body.append("<h2>Paid work and open routes</h2>\n")
    if routes:
        items = "".join(f'<li>{external_link(r["url"], r.get("role", "Route")) if r.get("url") else escape(r.get("role", "Route"))} — {escape(r.get("pay_label", "Not published"))} <span class="muted">({escape(str(r.get("status", "")).replace("_", " "))})</span></li>' for r in routes)
        body.append(f"<ul>{items}</ul>\n<p class=\"muted\">Pay labels are quoted as published and may be out of date; check each listing.</p>\n")
    else: body.append('<p class="muted">No reviewed public work route is recorded for this organization.</p>\n')
    body.append("<h2>Explore further</h2>\n" + cta + f'<p class="muted">The interactive profile shows every sourced claim, funding round, relationship and work listing with its evidence grade. <a href="{ORIGIN}/companies/">Browse all companies</a>.</p>\n')
    organization = {"@type": "Organization", "name": name, "description": description}
    if company.get("website"): organization["url"] = company["website"]
    if company.get("founded_year"): organization["foundingDate"] = str(company["founded_year"])
    if company.get("legal_entity_name"): organization["legalName"] = company["legal_entity_name"]
    if company.get("aliases"): organization["alternateName"] = list(company["aliases"])
    website = {"@type": "WebSite", "@id": f"{ORIGIN}/", "name": SITE_NAME, "url": f"{ORIGIN}/"}
    publisher = {"@type": "Organization", "name": SITE_NAME, "url": f"{ORIGIN}/"}
    structured = {"@context": "https://schema.org", "@type": "WebPage", "@id": canonical, "url": canonical, "name": title, "description": meta_description, "isPartOf": website, "publisher": publisher, "dateModified": as_of, "about": organization, "mainEntity": organization}
    return document(title, meta_description, canonical, "".join(body), structured)


def render_index(data, companies, editorial_by_id, as_of):
    canonical = f"{ORIGIN}/companies/"
    count = len(companies)
    title = f"AI data companies: {count} sourced profiles · {SITE_NAME}"
    description = truncate(f"Public research on {count} AI data organizations: business model, revenue, funding, valuation and paid work routes, each with dated sources.")
    items = "".join(f'<li><a href="{ORIGIN}/company/{escape(c["id"])}/">{escape(c["name"])}</a>' + (f' <span class="muted">· {escape(editorial_by_id[c["id"]]["primary_offering"])}</span>' if editorial_by_id.get(c["id"], {}).get("primary_offering") else "") + f'<br><span class="muted">{escape(c.get("description", ""))}</span></li>' for c in companies)
    body = (f'<p class="eyebrow">Company index · data as of {escape(as_of)}</p>\n<h1>AI data companies</h1>\n<p class="lede">{escape(description)}</p>\n<p><a class="cta" href="{ORIGIN}/#companies">Open the interactive index</a></p>\n<ul>{items}</ul>\n')
    website = {"@type": "WebSite", "@id": f"{ORIGIN}/", "name": SITE_NAME, "url": f"{ORIGIN}/"}
    structured = {"@context": "https://schema.org", "@type": "CollectionPage", "@id": canonical, "url": canonical, "name": title, "description": description, "isPartOf": website, "publisher": {"@type": "Organization", "name": SITE_NAME, "url": f"{ORIGIN}/"}, "dateModified": as_of, "mainEntity": {"@type": "ItemList", "numberOfItems": count, "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": c["name"], "url": f"{ORIGIN}/company/{c['id']}/"} for i, c in enumerate(companies)]}}
    return document(title, description, canonical, body, structured)


def render_sitemap(company_ids, lastmod):
    entries = [f"{ORIGIN}/", f"{ORIGIN}/companies/"] + [f"{ORIGIN}/company/{cid}/" for cid in company_ids]
    urls = "".join(f"  <url>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{escape(lastmod)}</lastmod>\n  </url>\n" for loc in entries)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n"


def write_static_pages(data, destination, work_data=None, profile_content=None, editorial=None):
    """Write /company/<id>/index.html for every company, /companies/index.html and sitemap.xml."""
    destination = Path(destination)
    as_of = str(data.get("meta", {}).get("as_of", ""))
    editorial_by_id = {e["company_id"]: e for e in (editorial or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    profile_by_id = {e["company_id"]: e for e in (profile_content or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    companies = sorted(data.get("companies", []), key=lambda c: c["id"])
    written = []
    for company in companies:
        cid = company["id"]
        if not COMPANY_ID.match(cid): raise ValueError(f"static pages: company id is not URL-safe: {cid!r}")
        folder = destination / "company" / cid
        folder.mkdir(parents=True, exist_ok=True)
        page = render_company(data, company, editorial_by_id.get(cid), profile_by_id.get(cid), company_routes(work_data, cid), as_of)
        (folder / "index.html").write_text(page, encoding="utf-8")
        written.append(folder / "index.html")
    index_folder = destination / "companies"
    index_folder.mkdir(parents=True, exist_ok=True)
    (index_folder / "index.html").write_text(render_index(data, sorted(companies, key=lambda c: (c["name"].lower(), c["id"])), editorial_by_id, as_of), encoding="utf-8")
    written.append(index_folder / "index.html")
    (destination / "sitemap.xml").write_text(render_sitemap([c["id"] for c in companies], as_of), encoding="utf-8")
    written.append(destination / "sitemap.xml")
    return written
