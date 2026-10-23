#!/usr/bin/env python3
"""Lean crawlable company pages and a sitemap beside the hash-routed app.

The interactive dashboard is one large HTML document routed by URL fragments,
so search engines see a single URL. This module writes a small static page per
company at /company/<id>/, an index at /companies/, and a sitemap listing them.
Pages embed no dataset and no application script (only GoatCounter's counter when
web/index.html turns analytics on); every string is escaped and
the output is deterministic so rebuilds stay byte-identical.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ORIGIN = "https://sciencetostartup.com"
SITE_NAME = "ScienceToStartup"
PUBLISHER = "Musa Ozdem"
DESCRIPTION_LIMIT = 155
TITLE_LIMIT = 60
METRIC_LIMIT = 8
PRODUCT_LIMIT = 6
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
OG_IMAGE = f"{ORIGIN}/assets/og/sciencetostartup-og-v1.png"
OG_IMAGE_ALT = "ScienceToStartup, the AI data field guide"
# Word for word from the About panel (article#about) of web/index.html.
DISCLOSURE = "The publisher is also proposing an AI research lab, described on the overview page. That proposal is separate from the research here, which applies the same rules to every organization."
NOT_YET_PROFILED = ("Uber AI Solutions", "TELUS Digital", "CloudFactory", "SuperAnnotate", "Encord", "Defined.ai", "LXT", "Welocalize")
EVENTS_NOTE = "Lawsuit entries describe allegations and court filings, not findings. Dates show when a case was filed or an event was reported."
EVENT_KINDS = {"lawsuit": "Lawsuit", "data_incident": "Data incident", "customer_change": "Customer change", "workforce_change": "Workforce change", "filing": "Filing"}
# Only a GoatCounter endpoint switches counting on, as in web/app.js; the meta tag lives in web/index.html.
ANALYTICS_META = re.compile(r'<meta name="sts-analytics" content="([^"]*)">')
ANALYTICS_URL = re.compile(r"https://[a-z0-9-]+\.goatcounter\.com/count")
STATUS_LABELS = {"not preferred": "Older or partial figure"}
LINK_STATES = {"not_found": "page unavailable", "gone": "page unavailable", "sign_in": "sign-in required"}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")

KIND_ORDER = ("annualized_revenue_run_rate", "arr", "revenue", "valuation", "funding_total_reported", "funding_total_calculated", "growth_rate", "headcount", "expert_network", "customer_count", "other")
KIND_LABELS = {"annualized_revenue_run_rate": "Annualized revenue run rate", "arr": "ARR", "revenue": "Revenue", "valuation": "Valuation", "funding_total_reported": "Total funding (reported)", "funding_total_calculated": "Total funding (calculated)", "growth_rate": "Growth rate", "headcount": "Headcount", "expert_network": "Expert network", "customer_count": "Customers", "other": "Other metric"}
QUALIFIERS = {"at_least": "at least ", "greater_than": "more than ", "approximate": "about ", "nearly": "nearly ", "at_most": "up to "}
CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}

STYLE = (
    "body{margin:0;background:#f8f8f4;color:#18231f;font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
    "main,header,footer{max-width:45rem;margin:0 auto;padding:0 16px}"
    "header{padding-top:20px;font-size:14px}"
    "a{color:#285b46;text-underline-offset:3px}"
    "h1{font:400 40px/1.08 Georgia,'Times New Roman',serif;letter-spacing:-1px;margin:24px 0 12px}"
    "h2{font-size:22px;letter-spacing:-.35px;margin:36px 0 12px}h3{font-size:16px;margin:24px 0 8px}"
    ".eyebrow{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#59645d;font-weight:600;margin:28px 0 0}"
    ".lede{font-size:18px;color:#59645d}"
    ".cta{display:inline-block;margin:8px 0 20px;padding:10px 16px;border:1px solid #285b46;border-radius:3px;text-decoration:none;font-weight:600}"
    "dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;font-size:15px}dl.facts dt{color:#59645d}dl.facts dd{margin:0;overflow-wrap:anywhere}"
    "table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:8px 10px 8px 0;border-bottom:1px solid #d8ddd5}th{color:#59645d;font-weight:500}"
    "td.value{font-weight:600;white-space:nowrap}td.date{min-width:6em}ul{padding-left:20px}li{margin:6px 0;overflow-wrap:anywhere}"
    ".muted{color:#59645d;font-size:13px}.nowrap{white-space:nowrap}footer{padding:0 16px 48px;color:#59645d;font-size:13px;margin-top:40px}footer::before{content:'';display:block;border-top:1px solid #d8ddd5;margin-bottom:32px}"
    "@media(min-width:601px){table.events td:last-child a{white-space:nowrap}}"
    "@media(max-width:600px){h1{font-size:32px}dl.facts{grid-template-columns:1fr}table,thead,tbody,tr,td,th{display:block}thead{display:none}td{padding:3px 0;border:0}tr{padding:8px 0;border-bottom:1px solid #d8ddd5}td.value{white-space:normal}td.status::before{content:'Status: ';color:#59645d}td.asof::before{content:'As of ';color:#59645d}}"
)


def escape(value):
    return html.escape("" if value is None else str(value), quote=True)


# Research records carry reviewer notes ("Do not compare ...", snake_case labels). The app shows them through
# publicText in web/app.js; the port below lets the static pages print the same words. The copy table itself is
# read from web/app.js so it lives in one place, and tests/test_static_pages.py runs both versions to keep them equal.
APP_SCRIPT = Path(__file__).resolve().parents[1] / "web" / "app.js"
INDEX_PAGE = APP_SCRIPT.with_name("index.html")
COPY_EDIT_BLOCK = re.compile(r"(?:const PUBLIC_COPY_EDITS=|Object\.assign\(PUBLIC_COPY_EDITS,)(\{.*?\n\})", re.S)
JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
SPACE = f"[{JS_SPACE}]"  # JavaScript's \s, which also sets what trim() removes
DO_NOT_VERBS = {"add": "adding", "assume": "assuming", "attribute": "attributing", "call": "calling", "characterize": "characterizing", "choose": "choosing", "compare": "comparing", "confuse": "confusing", "convert": "converting", "count": "counting", "directly": "directly", "display": "displaying", "equate": "equating", "force": "forcing", "imply": "implying", "import": "importing", "infer": "inferring", "invent": "inventing", "label": "labelling", "mark": "marking", "mechanically": "mechanically", "mislabel": "mislabelling", "normalize": "normalizing", "present": "presenting", "promote": "promoting", "replace": "replacing", "set": "setting", "silently": "silently", "substitute": "substituting", "transfer": "transferring", "treat": "treating", "turn": "turning", "upgrade": "upgrading", "use": "using", "guess": "guessing", "fabricate": "fabricating", "annualize": "annualizing", "erase": "erasing"}
WORDING_RULES = (  # (pattern, replacement) in publicTextCompute order; ASCII matches JavaScript's \b, \w and \d
    (re.compile(r"\bcontact at [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.A), "contact by email"),
    (re.compile(r"Superseded by the final [^.]+\."), "Replaced by later research."),
    (re.compile(r"Retained as historical provenance; excluded from active fact selectors\."), "Historical observation; excluded from current comparisons."),
    (re.compile(r"Final audit source [\w.-]+: ", re.A), ""),
    (re.compile(r"Earlier registry status: "), "Earlier source check: "),
    (re.compile(r"Review status: "), "Source check: "),
    (re.compile(r"Retain claim: Yes\.?"), ""),
    (re.compile(r"Source support was inherited[^.]*\."), "Source support has not been rechecked."),
    (re.compile(r"Historical statements are preserved[^.]*\."), "Historical statements are dated and may not describe current conditions."),
    (re.compile(r"\b([Ff]ound(?:ed|ing)(?: year)?[^.\d]{0,12})([12]),(\d{3})\b", re.A), r"\1\2\3"),
    (re.compile(r"\b([Dd])o not (silently |mechanically |directly )?([a-z]+)\b", re.A), lambda m: (("The" if m[1] == "D" else "the") + " evidence does not support " + (m[2] or "") + DO_NOT_VERBS[m[3]]) if m[3] in DO_NOT_VERBS else m[0]),
    (re.compile(r"\bmust not be (shown|presented|represented|treated|counted|reported|label(?:l)?ed|equated|added|summed|merged|transferred)\b", re.A), r"cannot be \1"),
    (re.compile(r"\bshould not be (treated|mistaken|equated|relabeled|fabricated|read|combined|reported|substituted)\b", re.A), r"cannot be \1"),
    (re.compile(rf"\b(?:Round id|Id): [a-z0-9_.-]+\.(?:{SPACE}|\Z)", re.A | re.I), ""),
    (re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+\b", re.A), lambda m: m[0].replace("_", " ")),
    (re.compile(f"{SPACE}{{2,}}"), " "),
    (re.compile(r" \."), "."),
)
REWORDED_FIELDS = {"claims": ("statement",), "metrics": ("label", "scope_detail"), "sources": ("title",), "companies": ("description",)}


def load_copy_edits(script=APP_SCRIPT):
    """PUBLIC_COPY_EDITS from web/app.js, in the order the app applies them."""
    source = Path(script).read_text(encoding="utf-8")
    blocks = COPY_EDIT_BLOCK.findall(source)
    if not blocks or len(blocks) != source.count("Object.assign(PUBLIC_COPY_EDITS,") + 1: raise ValueError("static pages: cannot read PUBLIC_COPY_EDITS from web/app.js")
    edits = {}
    for block in blocks: edits.update(json.loads(block))
    return edits


def public_wording(data, edits):
    """publicText from web/app.js: record ids and URLs pass through, research notes become public sentences."""
    record_ids = {row["id"] for rows in data.values() if isinstance(rows, list) for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]}
    record_ids |= {stage.get("id") for stage in data.get("rubric", {}).get("stages", [])} | {"not_applicable", "pending"}
    def say(value):
        text = "" if value is None else str(value)
        if text in record_ids or re.match(r"https?://", text, re.I): return text
        for original, copy in edits.items(): text = text.replace(original, copy)
        for pattern, replacement in WORDING_RULES: text = pattern.sub(replacement, text)
        return text.strip(JS_SPACE)
    return say


def reworded(data, say):
    """The dataset with its research text (claim statements, metric labels, source titles, descriptions) in public wording.
    The sidecars are written as public copy already; tests/test_static_pages.py checks that the app leaves them as they are."""
    copy = dict(data)
    for table, fields in REWORDED_FIELDS.items():
        copy[table] = [{**row, **{field: say(row[field]) for field in fields if isinstance(row.get(field), str)}} for row in data.get(table, [])]
    return copy


def truncate(text, limit=DESCRIPTION_LIMIT):
    text = " ".join(str(text or "").split())
    if len(text) <= limit: return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:") + "…"


def full_stop(text):
    text = " ".join(str(text or "").split())
    return text + "." if text and text[-1] not in ".!?" else text


def sentences(text):
    return [part for part in re.split(r"(?<=[.!?])\s+", full_stop(text)) if part]


def describe(name, description, closing="Figures link to their sources.", limit=DESCRIPTION_LIMIT):
    """Whole sentences up to the limit, led by the company name; the page summary repeats the description, so it is left out."""
    lead = " ".join(str(description or "").split())
    if lead and not lead.startswith(name): lead = f"{name} " + (lead[0].lower() + lead[1:] if lead[1:2].islower() else lead)
    text = ""
    for part in sentences(lead) + [closing]:
        if len(text) + 1 + len(part) <= limit: text = (text + " " + part).strip()
    return text or truncate(lead, limit)


def page_title(name):
    """Under 60 characters; long company names drop the site name, then the revenue topic."""
    options = (f"{name}: revenue, funding and paid work · {SITE_NAME}", f"{name}: revenue, funding and paid work", f"{name}: funding and paid work")
    return next((option for option in options if len(option) < TITLE_LIMIT), options[-1])


def date_rank(value):
    """Port of dateRank in web/app.js, so a static page picks the figure the app picks."""
    text = str(value)
    year = re.search(r"(?:19|20)[0-9]{2}", text)
    if not year: return "0000"
    iso = re.search(r"(?:19|20)[0-9]{2}-[0-9]{2}(?:-[0-9]{2})?", text)
    if iso: return iso.group(0)
    if re.search(r"H1|half.year|six.month", text, re.I): return year.group(0) + "-06"
    if re.search(r"H2|end of|year.end", text, re.I): return year.group(0) + "-12"
    month = next((index for index, name in enumerate(MONTHS) if name in text.lower()), None)
    return year.group(0) + (f"-{month + 1:02d}" if month is not None else "")


def by_recent(rows):
    """byRecent in web/app.js: newest first, then preferred_for_comparison, then major- records."""
    rows = sorted(rows, key=lambda row: row["id"])
    return sorted(rows, key=lambda row: (date_rank(row.get("as_of") or row.get("announced_on")), row.get("preferred_for_comparison") is True, "major-" in row["id"]), reverse=True)


def exclusion(metric, claim):
    """Why the app's eligibleMetrics rule keeps a metric out of comparisons; empty when it is eligible."""
    if claim.get("status") != "supported": return str(claim.get("status") or "unverified")
    if (metric.get("observation_status") or "reported") != "reported": return metric["observation_status"]
    return "not preferred" if metric.get("preferred_for_comparison") is False else ""


def date_text(value):
    return "Source date not stated" if value == "undated" else str(value or "")


def month_label(value):
    year, month = str(value).split("-")[:2]
    return f"{MONTHS[int(month) - 1][:3].title()} {year}"


def day_label(value):
    year, month, day = str(value).split("-")
    return f"{int(day)} {MONTHS[int(month) - 1][:3].title()} {year}"


def as_of_cell(value):
    """A risk row's date in the interactive profile's words: 'Jun 2026', or the stated fallback."""
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?", str(value or "")): return f'<td class="date asof">{escape(month_label(value))}</td>'
    return f'<td class="date">{escape(date_text(value))}</td>'


def statuses_checked(events):
    """When the event statuses were last checked, so a pending case is read as of that date."""
    days = sorted({e["status_checked_on"] for e in events})
    if not days: return ""
    return f"Statuses were checked on {day_label(days[0])}." if len(days) == 1 else f"Statuses were checked between {day_label(days[0])} and {day_label(days[-1])}."


def health_key(url):
    """The URL as web/link-health.js compares it: scheme and host in lower case, no fragment, a path of at least /."""
    try:
        parts = urlsplit(str(url or ""))
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname: return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except ValueError: return ""


def link_health_index(link_health):
    """The newest public link observation per URL, as web/link-health.js keeps it."""
    index = {}
    for entry in (link_health or {}).get("entries", []):
        key = health_key(entry.get("url"))
        if key and entry.get("status") in LINK_STATES and (key not in index or entry["checked_on"] >= index[key]["checked_on"]): index[key] = entry
    return index


def availability(url, health):
    """After a link the app marks as unavailable, the same observation in muted type."""
    entry = (health or {}).get(health_key(url))
    return f' <span class="muted">({LINK_STATES[entry["status"]]} when checked {escape(day_label(entry["checked_on"]))})</span>' if entry else ""


def analytics_endpoint(index_html):
    """The GoatCounter endpoint named in web/index.html, or empty while counting is off."""
    match = ANALYTICS_META.search(index_html or "")
    url = match.group(1).strip() if match else ""
    return url if ANALYTICS_URL.fullmatch(url) else ""


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
    return text + (" (estimated)" if metric.get("reported_vs_estimated") == "estimated" else "")


def headline_metrics(data, company_id, limit=METRIC_LIMIT, metric_context=None):
    """Per metric kind, the figure the app compares (eligibleMetrics, then byRecent). When the newest figure of a kind
    is one the app excludes, it is returned separately with the reason, so nothing reported silently disappears."""
    claims = {claim["id"]: claim for claim in data.get("claims", [])}
    sources = {source["id"]: source for source in data.get("sources", [])}
    newest, compared = {}, {}
    for metric in by_recent([m for m in data.get("metrics", []) if m.get("company_id") == company_id]):
        claim = claims.get(metric.get("claim_id"), {})
        status = exclusion(metric, claim)
        if status == "superseded": continue
        kind = metric.get("kind", "other")
        newest.setdefault(kind, (metric, claim, status))
        if not status: compared.setdefault(kind, (metric, claim, status))
    def row(kind, metric, claim, status):
        source = first_source(claim, sources)
        label = str(metric.get("label", ""))
        if label.replace("_", " ").strip().lower() == kind.replace("_", " ").lower(): label = ""  # label merely repeats the kind
        # metricMeta in web/app.js: the part of the business a figure covers, and a revenue figure's own period.
        scope = ((metric_context or {}).get(metric.get("id")) or {}).get("scope") or (metric.get("scope_detail") if metric.get("scope_detail") not in (None, "", "company", "ai_data", "other_segment") else "")
        period = metric.get("period_label") if kind == "revenue" and metric.get("period_label") != metric.get("as_of") else ""
        context = " · ".join(str(part) for part in (scope, period) if part)
        return {"id": metric.get("id", ""), "kind": KIND_LABELS.get(kind, kind.replace("_", " ").capitalize()), "label": label, "context": context, "value": format_value(metric), "as_of": date_text(metric.get("as_of")), "status": status, "source_title": source.get("title", ""), "source_url": source.get("url", "")}
    order = lambda kind: (KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER), kind)
    rows = [row(kind, *compared[kind]) for kind in sorted(compared, key=order)][:limit]
    # "other" groups unrelated measures, so a non-preferred one (a base-model benchmark score, say) is not a newer figure.
    others = [row(kind, *newest[kind]) for kind in sorted(newest, key=order) if newest[kind][2] and not (kind == "other" and newest[kind][2] == "not preferred")]
    return rows, others


def company_events(events, company_id):
    """Dated events naming the company as subject or as a related party, newest first."""
    rows = [e for e in (events or {}).get("events", []) if e.get("company_id") == company_id or company_id in e.get("related_company_ids", [])]
    return sorted(sorted(rows, key=lambda e: e["id"]), key=lambda e: e["date"], reverse=True)


def risk_claims(data, company_id):
    return by_recent([c for c in data.get("claims", []) if c.get("company_id") == company_id and c.get("subject") == "risks" and c.get("status") == "supported"])


def company_routes(work_data, company_id):
    routes = [r for r in (work_data or {}).get("routes", []) if r.get("company_id") == company_id]
    return sorted(routes, key=lambda r: (str(r.get("role", "")).lower(), r.get("id", "")))


def json_ld(payload):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def external_link(url, label):
    return f'<a href="{escape(url)}" rel="noopener">{escape(label)}</a>'


def source_link(title, url, health=None):
    return external_link(url, title) + availability(url, health) if url else escape(title)


def first_source(claim, sources):
    return next((sources[sid] for sid in claim.get("source_ids", []) if sid in sources), {})


def document(title, description, canonical, body, structured, note="", analytics=""):
    meta = {"og:type": "website", "og:title": title, "og:description": description, "og:url": canonical, "og:site_name": SITE_NAME, "og:image": OG_IMAGE, "og:image:width": "1200", "og:image:height": "630", "og:image:alt": OG_IMAGE_ALT}
    head = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="color-scheme" content="light">\n'
        f"<title>{escape(title)}</title>\n<meta name=\"description\" content=\"{escape(description)}\">\n<link rel=\"canonical\" href=\"{escape(canonical)}\">\n"
        + "".join(f'<meta property="{key}" content="{escape(value)}">\n' for key, value in meta.items())
        + f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{escape(title)}">\n<meta name="twitter:description" content="{escape(description)}">\n'
        '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n<link rel="icon" href="/assets/favicon-48.png" sizes="48x48" type="image/png">\n<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
        f"<style>{STYLE}</style>\n<script type=\"application/ld+json\">{json_ld(structured)}</script>\n"
        # Static pages have no hash routes, so GoatCounter's own page-load count is the right one here.
        + (f'<script async src="https://gc.zgo.at/count.js" data-goatcounter="{escape(analytics)}"></script>\n' if analytics else "")
        + "</head>\n"
    )
    header = f'<header><a href="{ORIGIN}/">{SITE_NAME}</a> · <a href="{ORIGIN}/companies/">All companies</a> · <a href="{ORIGIN}/#work">Paid work</a> · <a href="{ORIGIN}/#method">Method</a></header>\n'
    disclosure = escape(DISCLOSURE).replace("overview page", f'<a href="{ORIGIN}/#venture">overview page</a>', 1)
    footer = (
        f"<footer><p>{SITE_NAME} is published by {PUBLISHER}. {disclosure}</p>\n"
        "<p>Figures carry their own dates and sources. They do not confirm a company’s current status.</p>\n"
        f'<p><span class="nowrap"><a href="{ORIGIN}/#method">How evidence is graded</a> ·</span> <span class="nowrap"><a href="{ORIGIN}/research.json">Download the dataset</a> ·</span> <a href="{ORIGIN}/#about">Corrections</a></p>\n{note}</footer>\n'
    )
    return head + "<body>\n" + header + "<main>\n" + body + "</main>\n" + footer + "</body>\n</html>\n"


def website_label(url):
    return re.sub(r"^https?://(www\.)?", "", str(url or "")).rstrip("/")


def risks_section(data, company_id, events, health=None):
    """Dated events, then supported risk claims; nothing at all when both are empty. The lawsuit note goes with the events."""
    dated, risks = company_events(events, company_id), risk_claims(data, company_id)
    if not dated and not risks: return ""
    sources = {source["id"]: source for source in data.get("sources", [])}
    parts = ["<h2>Risks and disputes</h2>\n"]
    if dated:
        rows = "".join(f'<tr><td class="date">{escape(month_label(e["date"]))}<br><span class="muted">{escape(EVENT_KINDS.get(e["kind"], e["kind"]))}</span></td><td>{escape(e["title"])}<br><span class="muted">{escape(e["detail"])}</span></td><td class="status">{escape(e["status"])}</td><td>{" · ".join(external_link(s["url"], s["publisher"]) for s in e["sources"])}</td></tr>' for e in dated)
        parts.append(f"<h3>Dated events</h3>\n<table class=\"events\"><thead><tr><th>Date</th><th>Event</th><th>Status</th><th>Sources</th></tr></thead><tbody>{rows}</tbody></table>\n")
    if risks:
        cited = [(c, first_source(c, sources)) for c in risks]
        rows = "".join(f'<tr><td>{escape(c["statement"])}</td>{as_of_cell(c.get("as_of"))}<td>{source_link(source.get("title", ""), source.get("url"), health)}</td></tr>' for c, source in cited)
        parts.append(f"<h3>Risks named in the evidence</h3>\n<table><thead><tr><th>Risk</th><th>As of</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>\n")
    if dated: parts.append(f'<p class="muted">{EVENTS_NOTE} {escape(statuses_checked(dated))}</p>\n')
    return "".join(parts)


def render_company(data, company, editorial_entry, profile_entry, routes, events, as_of, modified, health=None, analytics=""):
    cid, name = company["id"], company["name"]
    canonical = f"{ORIGIN}/company/{cid}/"
    app_url = f"{ORIGIN}/#company/{cid}"
    description = " ".join(str(company.get("description", "")).split())
    summary = (editorial_entry or {}).get("summary", "")
    meta_description = describe(name, description)
    title = page_title(name)
    cta = f'<p><a class="cta" href="{app_url}">Open the full interactive profile</a></p>\n'
    body = [f'<p class="eyebrow">Company profile · data as of {escape(as_of)}</p>\n<h1>{escape(name)}</h1>\n<p class="lede">{escape(full_stop(description))}</p>\n', cta]
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
        if products: body.append("<ul>" + "".join(f"<li><strong>{escape(p['name'])}</strong>" + (f" · {escape(p['description'])}" if p.get("description") else "") + "</li>" for p in products) + "</ul>\n")
    metrics, others = headline_metrics(data, cid, metric_context=(profile_entry or {}).get("metric_context"))
    explain = lambda m: " · ".join(escape(part) for part in (m["label"], m["context"]) if part)
    body.append("<h2>Headline metrics</h2>\n")
    if metrics:
        rows = "".join(f'<tr><td>{escape(m["kind"])}<br><span class="muted">{explain(m)}</span></td><td class="value">{escape(m["value"])}</td><td class="date">{escape(m["as_of"])}</td><td>{source_link(m["source_title"], m["source_url"], health)}</td></tr>' for m in metrics)
        body.append(f"<table><thead><tr><th>Metric</th><th>Value</th><th>As of</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>\n<p class=\"muted\">The most recent supported figure per metric kind, picked by the same rule as the interactive comparison. Run rate, ARR, revenue, funding and valuation stay distinct. Estimates are marked.</p>\n")
    else: body.append('<p class="muted">No supported headline figure is recorded for this organization.</p>\n')
    if others:
        items = "".join(f'<li>{escape(m["kind"])}: <strong>{escape(m["value"])}</strong> <span class="muted">· {escape(STATUS_LABELS.get(m["status"], m["status"].capitalize()))}</span><br><span class="muted">{explain(m) + " · " if explain(m) else ""}{escape(m["as_of"])} · {source_link(m["source_title"], m["source_url"], health)}</span></li>' for m in others)
        body.append(f"<h3>Other reported figures, not used for comparison</h3>\n<ul>{items}</ul>\n")
    body.append(risks_section(data, cid, events, health))
    body.append("<h2>Paid work and open routes</h2>\n")
    if routes:
        items = "".join(f'<li>{external_link(r["url"], r.get("role", "Route")) + availability(r["url"], health) if r.get("url") else escape(r.get("role", "Route"))} · {escape(r.get("pay_label", "Not published"))} <span class="muted">({escape(str(r.get("status", "")).replace("_", " "))})</span></li>' for r in routes)
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
    structured = {"@context": "https://schema.org", "@type": "WebPage", "@id": canonical, "url": canonical, "name": title, "description": meta_description, "isPartOf": website, "publisher": publisher, "dateModified": modified, "about": organization, "mainEntity": organization}
    return document(title, meta_description, canonical, "".join(body), structured, analytics=analytics)


def render_index(data, companies, editorial_by_id, as_of, modified, analytics=""):
    canonical = f"{ORIGIN}/companies/"
    count = len(companies)
    title = f"AI data companies: {count} sourced profiles · {SITE_NAME}"
    description = truncate(f"Public research on {count} AI data organizations: business model, revenue, funding, valuation and paid work routes, each with dated sources.")
    items = "".join(f'<li><a href="{ORIGIN}/company/{escape(c["id"])}/">{escape(c["name"])}</a>' + (f' <span class="muted">· {escape(editorial_by_id[c["id"]]["primary_offering"])}</span>' if editorial_by_id.get(c["id"], {}).get("primary_offering") else "") + f'<br><span class="muted">{escape(full_stop(c.get("description")))}</span></li>' for c in companies)
    coverage = f"Coverage is a selected market study of {count} organizations, not an exhaustive census. Other firms not yet profiled include {', '.join(NOT_YET_PROFILED[:-1])} and {NOT_YET_PROFILED[-1]}."
    body = (f'<p class="eyebrow">Company index · data as of {escape(as_of)}</p>\n<h1>AI data companies</h1>\n<p class="lede">{escape(description)}</p>\n<p class="muted">{escape(coverage)}</p>\n<p><a class="cta" href="{ORIGIN}/#companies">Open the interactive index</a></p>\n<ul>{items}</ul>\n')
    website = {"@type": "WebSite", "@id": f"{ORIGIN}/", "name": SITE_NAME, "url": f"{ORIGIN}/"}
    structured = {"@context": "https://schema.org", "@type": "CollectionPage", "@id": canonical, "url": canonical, "name": title, "description": description, "isPartOf": website, "publisher": {"@type": "Organization", "name": SITE_NAME, "url": f"{ORIGIN}/"}, "dateModified": modified, "mainEntity": {"@type": "ItemList", "numberOfItems": count, "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": c["name"], "url": f"{ORIGIN}/company/{c['id']}/"} for i, c in enumerate(companies)]}}
    return document(title, description, canonical, body, structured, "<p>Company names and logos belong to their owners and identify them here.</p>\n", analytics)


def render_sitemap(company_ids, lastmod):
    entries = [f"{ORIGIN}/", f"{ORIGIN}/companies/"] + [f"{ORIGIN}/company/{cid}/" for cid in company_ids]
    urls = "".join(f"  <url>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{escape(lastmod)}</lastmod>\n  </url>\n" for loc in entries)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n"


def write_static_pages(data, destination, work_data=None, profile_content=None, editorial=None, events=None, link_health=None):
    """Write /company/<id>/index.html for every company, /companies/index.html and sitemap.xml."""
    destination = Path(destination)
    data = reworded(data, public_wording(data, load_copy_edits()))
    as_of = str(data.get("meta", {}).get("as_of", ""))
    # Pages change when the dataset or the reviewed events change; lastmod and dateModified follow the later date.
    modified = max(as_of, str((events or {}).get("reviewed_on") or ""))
    health = link_health_index(link_health)
    analytics = analytics_endpoint(INDEX_PAGE.read_text(encoding="utf-8") if INDEX_PAGE.exists() else "")
    editorial_by_id = {e["company_id"]: e for e in (editorial or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    profile_by_id = {e["company_id"]: e for e in (profile_content or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    companies = sorted(data.get("companies", []), key=lambda c: c["id"])
    written = []
    for company in companies:
        cid = company["id"]
        if not COMPANY_ID.match(cid): raise ValueError(f"static pages: company id is not URL-safe: {cid!r}")
        folder = destination / "company" / cid
        folder.mkdir(parents=True, exist_ok=True)
        page = render_company(data, company, editorial_by_id.get(cid), profile_by_id.get(cid), company_routes(work_data, cid), events, as_of, modified, health, analytics)
        (folder / "index.html").write_text(page, encoding="utf-8")
        written.append(folder / "index.html")
    index_folder = destination / "companies"
    index_folder.mkdir(parents=True, exist_ok=True)
    (index_folder / "index.html").write_text(render_index(data, sorted(companies, key=lambda c: (c["name"].lower(), c["id"])), editorial_by_id, as_of, modified, analytics), encoding="utf-8")
    written.append(index_folder / "index.html")
    (destination / "sitemap.xml").write_text(render_sitemap([c["id"] for c in companies], modified), encoding="utf-8")
    written.append(destination / "sitemap.xml")
    return written
