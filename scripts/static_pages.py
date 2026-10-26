#!/usr/bin/env python3
"""Lean crawlable pages beside the hash-routed app.

The interactive guide is one large HTML document routed by URL fragments, so
search engines see a single URL. This module writes small static pages: one per
company at /company/<id>/, the company list at /companies/, the paid work
listings at /work/, the method at /method/, the 404 page and the sitemap. Pages
embed no dataset and no application script. Every string is escaped and the
output is deterministic, so rebuilds stay byte-identical.

Figures follow the app's own rules in web/app.js: eligibleMetrics() decides
which figures may be key figures, preferredFinancial() picks the revenue
headline (FINANCIAL_HEADLINES is read from web/app.js), compactSignal() decides
the Historical tag, and later source corrections are applied the way
web/source-updates.js applies them. Research text goes through a port of the
app's publicText(), with PUBLIC_COPY_EDITS read from web/app.js.
tests/test_static_pages.py runs the app code in Node and checks that both
choose the same records and print the same words.
"""
import html
import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from functools import cmp_to_key
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://sciencetostartup.com"
SITE_NAME = "ScienceToStartup"
SUFFIX = f" · {SITE_NAME}"
PUBLISHER_NAME = "Musa Ozdem"
DESCRIPTION_LIMIT = 155
# Search results show about 60 characters of a title, so every title stays under 60.
TITLE_LIMIT = 59
METRIC_LIMIT = 8
PRODUCT_LIMIT = 6
# Bump by hand when page links, layout, copy or structured data change; it feeds sitemap <lastmod>.
SITE_REVISED = "2026-10-26"
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ISO_DAY = re.compile(r"\b([0-9]{4})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\b")
ISO_MONTH = re.compile(r"\b([0-9]{4})-(0[1-9]|1[0-2])\b")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
NUMBER_WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten")

SHARE_IMAGE = f"{ORIGIN}/assets/share/sciencetostartup-1200x630.png"
SHARE_ALT = "ScienceToStartup, the AI data field guide: the businesses behind AI data. Company profiles and paid work listings, with every figure linked to its source."
# The icon set web/index.html links: an SVG, a 48 px PNG and an opaque 180 px Apple touch icon. /favicon.ico sits at the root.
ICON_LINKS = '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n<link rel="icon" href="/assets/favicon-48.png" sizes="48x48" type="image/png">\n<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
PUBLISHER = {"@type": "Person", "@id": f"{ORIGIN}/#publisher", "name": PUBLISHER_NAME, "url": f"{ORIGIN}/method/#about"}
WEBSITE = {"@type": "WebSite", "@id": f"{ORIGIN}/#website", "name": SITE_NAME, "url": f"{ORIGIN}/", "publisher": {"@id": PUBLISHER["@id"]}}
# One dataset identity: the home page's Dataset node (web/index.html). /method/ describes the same node, so it shares the @id and name.
DATASET_ID = f"{ORIGIN}/#dataset"
DATASET_NAME = "ScienceToStartup research database"
# The research data and the site's own text are CC BY 4.0, licensed by ScienceToStartup (LICENSE-DATA.md); the code stays MIT.
DATA_LICENSE = "https://creativecommons.org/licenses/by/4.0/"
SCAM_GUIDE = "https://consumer.ftc.gov/articles/job-scams"
# Word for word from the About panel (article#about) of web/index.html; tests/test_static_pages.py keeps them equal.
DISCLOSURE = "The publisher is also proposing an AI research lab, described on the overview page. That proposal is separate from this research, which applies the same rules to every company."
# The owner's one-line disclosure about paid work. It belongs to the About text only (the app's About panel and /method/), not every footer.
WORK_DISCLOSURE = "The publisher has applied for paid work at some profiled companies and is a member of A.Team's talent network."
# Cloudflare Web Analytics is injected at the edge. Both About texts (web/index.html and /method/) say so in these words.
VISITS_NOTE = "Visits are counted by Cloudflare Web Analytics, which sets no cookies."
COVERAGE = "The guide is a selected study of the market. It does not list every company."
LOGO_NOTE = "Company names and logos belong to their owners and identify them here."
NOT_YET_PROFILED = ("Uber AI Solutions", "TELUS Digital", "CloudFactory", "SuperAnnotate", "Encord", "Defined.ai", "LXT", "Welocalize")
LINK_STATES = {"not_found": "page unavailable", "gone": "page unavailable", "sign_in": "sign-in required"}

# ---------------------------------------------------------------------------
# Text helpers

def escape(value):
    return html.escape("" if value is None else str(value), quote=True)


def clean(value):
    """Collapse whitespace and turn the em-dash separators in research text into plain punctuation."""
    text = " ".join(str(value or "").split())
    return re.sub(r" [—–] ", ": ", text).replace("—", ", ")


def truncate(text, limit=DESCRIPTION_LIMIT):
    text = " ".join(str(text or "").split())
    if len(text) <= limit: return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:") + "…"


def full_stop(text):
    return text + "." if text and not re.search(r"[.!?)]$", text) else text


def upper_first(text):
    """Capitalize a leading all-lowercase word ('headcount'), leaving names such as 'iMerit' alone."""
    return text[:1].upper() + text[1:] if re.match(r"[a-z]+\b", text) else text


def sentences(text):
    return [part for part in re.split(r"(?<=[.!?])\s+", full_stop(clean(text))) if part]


def readable(text):
    """Research keys and labels in plain words: 'recruiting_parent' becomes 'Recruiting parent'."""
    text = clean(text)
    text = LABEL_WORDS.get(text, text).replace("_", " ")
    text = re.sub(r"\s+percent$", "", re.sub(r"\byoy\b", "year over year", text))
    return upper_first(text)


def format_date(value):
    """'2026-10-15' as '15 Oct 2026' and '2026-06' as 'Jun 2026'; anything else unchanged."""
    text = str(value or "")
    day = ISO_DAY.fullmatch(text)
    if day: return f"{int(day.group(3))} {MONTHS[int(day.group(2)) - 1]} {day.group(1)}"
    month = ISO_MONTH.fullmatch(text)
    return f"{MONTHS[int(month.group(2)) - 1]} {month.group(1)}" if month else text


def period_text(value):
    """A metric date or period in reader form: ISO dates spelled out, 'FY ended 2025-12-31' as 'FY2025'."""
    text = clean(value)
    if not text or text == "undated": return "Date not stated"
    fiscal = re.match(r"FY ended ([0-9]{4})", text)
    if fiscal: return "FY" + fiscal.group(1)
    text = re.sub(r"^as of\s+", "", text, flags=re.I)
    text = re.sub(r"\b([0-9]{4})[- ](H[12]|Q[1-4])\b", r"\2 \1", text)
    text = re.sub(r"\b([0-9]{4})-end\b", r"end of \1", text)
    text = re.sub(r"\bYTD\b", "year to date", text)
    text = ISO_DAY.sub(lambda match: format_date(match.group(0)), text)
    text = ISO_MONTH.sub(lambda match: format_date(match.group(0)), text)
    return upper_first(text)


def count_word(number):
    return NUMBER_WORDS[number] if 0 <= number < len(NUMBER_WORDS) else str(number)


def join_words(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def plural(number, word, many=None):
    return f"{number} {word if number == 1 else many or word + 's'}"


def group_slug(name):
    """groupSlug() in web/editorial.js: lowercase, each run of other characters becomes '-', ends trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def latest(*dates):
    """Latest ISO date among the inputs; values such as 'undated' are ignored."""
    return max((d for d in dates if isinstance(d, str) and ISO_DAY.fullmatch(d)), default="")

# ---------------------------------------------------------------------------
# Public wording: publicText() in web/app.js
#
# Research records carry reviewer notes ("Do not compare ...", snake_case labels). The app shows them through
# publicText in web/app.js; the port below lets the static pages print the same words. The copy table itself is
# read from web/app.js so it lives in one place, and tests/test_static_pages.py runs both versions to keep them equal.

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
# The research fields the pages print through public_wording; the sidecars are written as public copy already.
REWORDED_FIELDS = {"claims": ("statement",), "metrics": ("label", "scope_detail"), "sources": ("title",), "companies": ("description",)}


def load_copy_edits(script=ROOT / "web/app.js"):
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

# ---------------------------------------------------------------------------
# Link checks (web/link-health.js)

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
    return f' <span class="muted">({LINK_STATES[entry["status"]]} when checked {escape(format_date(entry["checked_on"]))})</span>' if entry else ""

# ---------------------------------------------------------------------------
# The app's rules, ported from web/app.js and web/source-updates.js

JS_ENTRY =re.compile(r"""\s*(?:([A-Za-z_$][\w$]*)|'([^'\\\n]*)'|"([^"\\\n]*)")\s*:\s*(?:'([^'\\\n]*)'|"([^"\\\n]*)")\s*(?:,\s*|$)""")


def read_js_object(path, name):
    """The string map `const NAME={key:'value',...};` in a web/ script. A missing or reshaped map fails the build."""
    text = Path(path).read_text(encoding="utf-8")
    found = re.findall(r"(?m)^[ \t]*const\s+" + re.escape(name) + r"\s*=\s*\{([^{}]*)\}\s*;", text)
    if len(found) != 1: raise ValueError(f"static pages: expected one `const {name}={{...}};` in {path}, found {len(found)}")
    body, entries, position = found[0].strip(), {}, 0
    while position < len(body):
        match = JS_ENTRY.match(body, position)
        if not match: raise ValueError(f"static pages: {name} in {path} is not a plain string map near {body[position:position + 40]!r}")
        entries[next(g for g in match.group(1, 2, 3) if g is not None)] = next(g for g in match.group(4, 5) if g is not None)
        position = match.end()
    if not entries: raise ValueError(f"static pages: {name} in {path} is empty")
    return entries


# String.prototype.localeCompare uses ICU root collation: punctuation, then digits, then letters; case only breaks ties.
COLLATION = " _-,;:!?.'\"()[]{}@*/\\&#%`^+<=>|~$0123456789abcdefghijklmnopqrstuvwxyz"
PRIMARY = {char: rank for rank, char in enumerate(COLLATION)}


def locale_key(text):
    decomposed = unicodedata.normalize("NFD", str(text))
    base = [char for char in decomposed if not unicodedata.combining(char)]
    return tuple(PRIMARY.get(char.lower(), len(PRIMARY) + ord(char.lower())) for char in base), tuple(char.isupper() for char in base), decomposed


def locale_compare(left, right):
    left, right = locale_key(left), locale_key(right)
    return (left > right) - (left < right)


YEAR = re.compile(r"(?:19|20)[0-9]{2}")
DATE_PREFIX = re.compile(r"(?:19|20)[0-9]{2}-[0-9]{2}(?:-[0-9]{2})?")
MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


def date_rank(value):
    """dateRank(): a sortable YYYY, YYYY-MM or YYYY-MM-DD read from free text, or '0000' when there is no year."""
    text = "undefined" if value is None else str(value)
    year = YEAR.search(text)
    if not year: return "0000"
    exact = DATE_PREFIX.search(text)
    if exact: return exact.group(0)
    if re.search(r"H1|half.year|six.month", text, re.I): return year.group(0) + "-06"
    if re.search(r"H2|end of|year.end", text, re.I): return year.group(0) + "-12"
    month = next((index for index, name in enumerate(MONTH_NAMES) if name in text.lower()), -1)
    return year.group(0) + (f"-{month + 1:02d}" if month >= 0 else "")


def by_recent(a, b):
    """byRecent(): newest first, then preferred records, then 'major-' records, then id order."""
    return (locale_compare(date_rank(b.get("as_of") or b.get("announced_on")), date_rank(a.get("as_of") or a.get("announced_on")))
            or (b.get("preferred_for_comparison") is True) - (a.get("preferred_for_comparison") is True)
            or ("major-" in b["id"]) - ("major-" in a["id"])
            or locale_compare(a["id"], b["id"]))


def financial_period(metric):
    """financialPeriod(): annual, half, ttm, short or other."""
    declared = metric.get("period_type")
    if declared: return "short" if declared in ("week", "quarter", "partial") else declared
    text = f"{metric.get('period_label') or metric.get('label') or ''} {metric.get('as_of', 'undefined')}"
    if re.search(r"half|H1|H2|six.month", text, re.I): return "half"
    if re.search(r"week|quarter|Q[1-4]|month", text, re.I): return "short"
    if re.search(r"FY[0-9]{4}|annual|full.year|^20[0-9]{2}$", text.strip(), re.I): return "annual"
    return "annual" if re.search(r"^20[0-9]{2}$", metric.get("period_label") or "") else "other"


REVENUE_KINDS = ("revenue", "annualized_revenue_run_rate", "arr")
PERIOD_WEIGHT = {"ttm": 3, "annual": 2, "half": 1}
METRIC_CORRECTIONS = ("metric_reporting_context", "financial-basis-source-supplement", "historical-offer-source-context")


def snapshot_matches(actual, expected):
    """evidenceContextSnapshotMatches(): every field in the retained snapshot still equals the record."""
    return isinstance(actual, dict) and isinstance(expected, dict) and all(key in actual and actual[key] == value for key, value in expected.items())


class Research:
    """The dataset indexed once, answering the questions the app asks of it.
    The rules read the records as stored, like the app. `say` (public_wording) only changes the words the pages print.
    `health` (link_health_index) carries the link checks."""

    def __init__(self, data, headlines=None, updates=None, say=None, health=None):
        self.data = data
        self.say = say or (lambda value: "" if value is None else str(value))
        self.health = health or {}
        self.claims = {row["id"]: row for row in data.get("claims", [])}
        self.sources = {row["id"]: row for row in data.get("sources", [])}
        self.companies = {row["id"]: row for row in data.get("companies", [])}
        self.by_company = {}
        for row in data.get("metrics", []): self.by_company.setdefault(row.get("company_id"), []).append(row)
        self.as_of = str(data.get("meta", {}).get("as_of", ""))
        self.headlines = dict(headlines or {})
        current = isinstance(updates, dict) and updates.get("baseline_dataset_version") == data.get("dataset_version")
        self.corrections = self._corrections(updates) if current else {}
        self.product_updates = [row for row in updates.get("updates") or [] if isinstance(row, dict)] if current else []

    def _corrections(self, updates):
        """Display corrections per metric, matched as web/source-updates.js matches them."""
        section = updates.get("evidence_context") or {}
        if section.get("version") != "1.0.0": return {}
        metrics, found = {row["id"]: row for row in self.data.get("metrics", [])}, {}
        for update in section.get("corrections") or []:
            if not isinstance(update, dict) or update.get("kind") not in METRIC_CORRECTIONS: continue
            target, snapshot = update.get("target") or {}, update.get("historical_snapshot") or {}
            metric, rows = metrics.get(target.get("metric_id")), snapshot.get("metrics") or [None]
            if metric and snapshot.get("dataset_version") == self.data.get("dataset_version") and update.get("company_id") == metric.get("company_id") and metric.get("claim_id") == target.get("claim_id") and snapshot_matches(metric, rows[0]):
                found.setdefault(metric["id"], []).append(update)
        return found

    def correction(self, metric, field):
        return next((clean(row[field]) for row in self.corrections.get(metric.get("id"), []) if isinstance(row.get(field), str) and row[field].strip()), "")

    def claim(self, metric): return self.claims.get(metric.get("claim_id")) or {}
    def status(self, metric): return self.claim(metric).get("status")
    def grade(self, metric): return self.claim(metric).get("confidence") or ""

    def eligible(self, metric):
        """eligibleMetrics(): a supported claim, a reported observation, and not marked unfit for comparison."""
        return metric.get("preferred_for_comparison") is not False and self.status(metric) == "supported" and metric.get("observation_status") in (None, "", "reported")

    def ranked(self, company_id, kind=None):
        rows = [m for m in self.by_company.get(company_id, []) if (kind is None or m.get("kind") == kind) and self.eligible(m)]
        return sorted(rows, key=cmp_to_key(by_recent))

    def assessment(self, company_id):
        rows = [row for row in self.data.get("assessments", []) if row.get("company_id") == company_id]
        return next((row for row in rows if row.get("segment_scope") == "ai_data"), rows[0] if rows else None)

    def headline(self, company_id):
        """preferredFinancial(): the reviewed headline, then the assessment's headline, then the latest revenue in scope."""
        ranked = self.ranked(company_id)
        for wanted in (self.headlines.get(company_id), (self.assessment(company_id) or {}).get("headline_metric_id")):
            hit = next((m for m in ranked if wanted and m["id"] == wanted), None)
            if hit: return hit
        has = lambda scope: any(m.get("kind") in REVENUE_KINDS and m.get("segment_scope") == scope for m in ranked)
        scope = "ai_data" if company_id in ("handshake_ai", "taskus") else "company" if has("company") else "ai_data" if has("ai_data") else None
        scoped = [m for m in ranked if not scope or m.get("segment_scope") == scope]
        of_kind = lambda kind: [m for m in scoped if m.get("kind") == kind]
        order = lambda a, b: locale_compare(date_rank(b.get("as_of")), date_rank(a.get("as_of"))) or PERIOD_WEIGHT.get(financial_period(b), 0) - PERIOD_WEIGHT.get(financial_period(a), 0) or by_recent(a, b)
        actual = sorted((m for m in of_kind("revenue") if financial_period(m) in PERIOD_WEIGHT), key=cmp_to_key(order))
        return next(iter(actual), None) or next(iter(of_kind("annualized_revenue_run_rate")), None) or next((m for m in of_kind("arr") if date_rank(m.get("as_of")) >= "2025"), None) or next(iter(of_kind("revenue")), None)

    def historical_year(self, metric):
        """compactSignal(): a figure is Historical when its year is before the year ahead of the snapshot year."""
        rank = date_rank(metric.get("as_of"))
        if rank == "0000" or not re.match(r"[0-9]{4}", self.as_of): return None
        year = int(rank[:4])
        return year if year < int(self.as_of[:4]) - 1 else None

    def scope_text(self, scope, company_id):
        """scopeText()."""
        if scope == "company": return "Parent company" if company_id in ("handshake_ai", "hackerrank", "rws_trainai") else "Whole company"
        if scope == "ai_data": return "AI business"
        if scope == "research": return "Research organization" if (self.companies.get(company_id) or {}).get("entity_type") == "adjacent_research" else "Research activity"
        if scope == "other_segment": return "Generate segment (includes TrainAI)" if company_id == "rws_trainai" else "Other business segment"
        return readable(scope)

    def products(self, company_id, curated):
        """profileProducts() with applyProductSourceUpdates(): curated offerings, else named product records."""
        rows = [dict(row) for row in curated or [] if isinstance(row, dict) and row.get("name")]
        if not rows:
            seen = set()
            records = [p for p in self.data.get("products", []) if p.get("company_id") == company_id and (self.claims.get(p.get("claim_id")) or {}).get("status") != "superseded"]
            named = [p for p in records if not re.match(r"Offer / product evidence|Product evidence", p.get("name", ""), re.I)] or records
            for p in named:
                key = re.sub(r"[^a-z0-9]", "", p.get("name", "").lower())
                if key in seen: continue
                seen.add(key)
                rows.append({"name": p.get("name"), "description": p.get("work_performed"), "record_ids": [p.get("id")], "claim_ids": [p.get("claim_id")]})
        updates = [row for row in self.product_updates if row.get("company_id") == company_id]
        for row in rows:
            for update in updates:
                target = update.get("target") or {}
                if target.get("product_name") == row.get("name") and all(r in (row.get("record_ids") or []) for r in target.get("record_ids") or []) and all(c in (row.get("claim_ids") or []) for c in target.get("claim_ids") or []):
                    row.update(update.get("replacement_fields") or {})
        return rows

# ---------------------------------------------------------------------------
# Figures as shown on the static pages

KIND_LABELS = {"revenue": "Revenue", "annualized_revenue_run_rate": "Annualized pace", "arr": "Yearly recurring subscription revenue", "valuation": "Valuation", "funding_total_reported": "Total funding reported", "funding_total_calculated": "Sum of disclosed funding rounds", "growth_rate": "Growth", "headcount": "Team size", "expert_network": "Expert network", "active_paid_experts": "Active paid experts", "customer_count": "Customers", "gmv": "Gross merchandise value", "other": "Other figure"}
LABELLED_KINDS = ("growth_rate", "headcount", "expert_network", "active_paid_experts", "other")
NOTED_KINDS = ("valuation", "funding_total_reported", "funding_total_calculated")
GENERIC_LABELS = {"valuation", "round valuation", "transaction valuation", "total funding", "funding total reported", "funding total calculated", "reported aggregate funding", "reported total raised"}
LEADING_VALUE = re.compile(r"^(?:[$£€]|[A-Z]{3} )?[0-9][0-9.,]*\s*(?:[KMBkmb]n?)?\+?\s+")
LABEL_WORDS = {"directory_team_size": "Team size listed by Y Combinator (a startup investor)", "employer_headcount_claim": "Team size, employer claim", "parent_arr_growth_percent": "Parent company growth in yearly recurring subscription revenue", "benchmark_task_count": "Benchmark tasks", "worker_payout_ambiguous_period": "Worker payouts, period unclear", "worker_payout_company_claim": "Worker payouts, company claim"}
QUALIFIER_WORDS = {"at_least": "at least ", "greater_than": "more than ", "less_than": "less than ", "approximate": "about ", "nearly": "nearly ", "at_most": "up to "}
CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
ORIGINAL_VALUE = re.compile(r"original value:\s*[^0-9;]*[0-9][0-9,.]*\s*\+?\s*([^;]*)", re.I)
TITLE_TOPICS = (("revenue", REVENUE_KINDS), ("valuation", ("valuation",)), ("funding", ("funding_total_reported", "funding_total_calculated")))


def decimal_text(amount, group=False):
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return (f"{rounded:,.2f}" if group else f"{rounded:.2f}").rstrip("0").rstrip(".")


def number_text(value):
    """compact() in web/app.js without the sign: 'en' compact notation from 100,000, at most two decimals, half away from zero."""
    amount = abs(Decimal(repr(value)) if isinstance(value, float) else Decimal(value))
    if amount >= 100000:
        for power, suffix in ((12, "T"), (9, "B"), (6, "M"), (3, "K")):
            if amount >= Decimal(10) ** power: return decimal_text(amount.scaleb(-power)) + suffix
    return decimal_text(amount, group=True)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unit_from_basis(basis):
    """Figures measured in 'other' units keep the unit only in their basis text ('original value: 18 months')."""
    match = ORIGINAL_VALUE.search(str(basis or ""))
    rest = match.group(1).split(",")[0].strip() if match else ""
    if rest.startswith("%"): return "%"
    return " " + rest if rest and len(rest) <= 40 else ""


def value_text(metric):
    """The figure as text, with the qualifier in words and a true minus sign: 'more than $1B', '−$40.1M'."""
    value = metric.get("value")
    if not is_number(value): return clean(value)
    text = number_text(value)
    if metric.get("qualifier") == "range" and is_number(metric.get("upper_value")): text += "–" + number_text(metric["upper_value"])
    unit, currency = metric.get("unit"), metric.get("currency") or ""
    if unit == "currency": text = CURRENCY_SYMBOLS[currency] + text if currency in CURRENCY_SYMBOLS else f"{currency} {text}".strip()
    elif unit == "percent": text += "%"
    elif unit == "multiple": text += "×"
    elif unit == "other": text += unit_from_basis(metric.get("basis"))
    return QUALIFIER_WORDS.get(metric.get("qualifier"), "") + ("−" if value < 0 else "") + text


def shown_text(research, value):
    """Research text in the app's public wording. Keys with a reviewed wording in LABEL_WORDS stay as they are for readable()."""
    text = clean(value)
    return text if text in LABEL_WORDS else clean(research.say(text))


def figure_label(research, metric):
    corrected = research.correction(metric, "display_label")
    if corrected: return corrected
    kind, label = metric.get("kind"), shown_text(research, metric.get("label"))
    if kind == "valuation": return "Pre-money valuation" if re.search(r"pre.money", label, re.I) else "Post-money valuation" if re.search(r"post.money", label, re.I) else "Valuation"
    label = LEADING_VALUE.sub("", label)  # '$14.3B Meta stake investment' repeats the value shown beside it
    if kind in LABELLED_KINDS and label: return readable(label)
    return KIND_LABELS.get(kind) or readable(kind)


def figure_note(research, metric):
    """What a valuation or funding label adds to the kind: the round ('Series E round') or a qualifier ('Recruiting valuation claim')."""
    label = shown_text(research, metric.get("label"))
    if metric.get("kind") not in NOTED_KINDS or not label or re.search(r"[0-9]", label) or label.lower().replace("_", " ") in GENERIC_LABELS: return ""
    funding_round = re.search(r"\b(Pre-seed|Seed|Series [A-Z])\b", label, re.I)
    if funding_round: return upper_first(funding_round.group(1)) + " round"
    return "" if figure_label(research, metric).lower() == label.lower() else readable(label)


def figure_scope(research, metric, context=None):
    """The part of the business a figure covers: a curated scope, then a named scope detail, then scopeText()."""
    if (context or {}).get("scope"): return clean(context["scope"])
    detail = clean(metric.get("scope_detail"))
    if detail and detail not in ("company", "ai_data", "research", "other_segment"): return readable(shown_text(research, detail))
    return research.scope_text(metric.get("segment_scope"), metric.get("company_id"))


def basis_text(research, metric):
    if metric.get("kind") not in REVENUE_KINDS: return ""
    basis = metric.get("gross_vs_net")
    if basis == "gross": return research.correction(metric, "display_basis") or "gross"
    return "net" if basis == "net" else "gross or net not stated"


def metric_period(research, metric):
    """shortPeriod(): a correction's period first, then the period label, then the as-of text."""
    return research.correction(metric, "display_period") or period_text(metric.get("period_label") or metric.get("as_of"))


def latest_source(research, metric):
    """The source to link for a figure, and how many other sources its claim cites.
    The newest dated source from the figure's year or later wins. When every dated source is older than the figure,
    an undated page read more recently (often the company's current page) is the better evidence, so the most
    recently read one wins. Otherwise the newest dated source."""
    rows = [research.sources[sid] for sid in research.claim(metric).get("source_ids", []) if sid in research.sources]
    if not rows: return None, 0
    published = lambda source: source.get("published_on") if ISO_DAY.fullmatch(str(source.get("published_on") or "")) else ""
    year = date_rank(metric.get("as_of"))[:4]
    current = [s for s in rows if published(s) and published(s)[:4] >= year]
    undated = [s for s in rows if not published(s)]
    if current: return max(current, key=published), len(rows) - 1
    if undated: return max(undated, key=lambda s: str(s.get("accessed_on") or "")), len(rows) - 1
    return max(rows, key=published), len(rows) - 1


def key_figures(research, company_id, profile_entry=None):
    """The Key figures rows: the app's revenue headline, then the newest eligible figure of each kind."""
    rows = []
    def add(metric):
        if metric and len(rows) < METRIC_LIMIT and all(metric["id"] != row["id"] for row in rows): rows.append(metric)
    covered = lambda kind: any(row.get("kind") == kind for row in rows)
    add(research.headline(company_id))
    for kind in REVENUE_KINDS:
        if not covered(kind): add(next((m for m in research.ranked(company_id, kind) if not research.historical_year(m)), None))
    ranked = research.ranked(company_id)
    for wanted in (profile_entry or {}).get("metric_ids") or []: add(next((m for m in ranked if m["id"] == wanted), None))
    for kind in ("valuation", "funding_total_reported", "funding_total_calculated", "growth_rate"):
        if not covered(kind): add(next(iter(research.ranked(company_id, kind)), None))
    for kind in ("expert_network", "headcount", "active_paid_experts", "customer_count"):
        if not covered(kind): add(next((m for m in research.ranked(company_id, kind) if m.get("segment_scope") != "other_segment"), None))
    if not covered("other"): add(next(iter(research.ranked(company_id, "other")), None))
    return rows


def unconfirmed_figures(research, company_id, shown):
    """Newer valuation or revenue figures the app keeps out of headlines: talks, unverified claims and conflicting reports.
    Forecasts and targets are left out entirely."""
    found = []
    for kind in ("valuation",) + REVENUE_KINDS:
        candidates = sorted((m for m in research.by_company.get(company_id, []) if m.get("kind") == kind and not research.eligible(m)
                             and research.status(m) in ("supported", "unverified", "contested") and m.get("observation_status") in (None, "", "reported", "talks")
                             and (research.status(m) != "supported" or m.get("observation_status") == "talks")), key=cmp_to_key(by_recent))
        current = next((row for row in shown if row.get("kind") == kind), None)
        if candidates and not research.historical_year(candidates[0]) and not (current and date_rank(candidates[0].get("as_of")) <= date_rank(current.get("as_of"))):
            found.append(candidates[0])
    return found


OTHER_STATUS = {"forecast": "Forecast", "target": "Target", "not preferred": "Older or partial figure"}


def exclusion(research, metric):
    """Why eligibleMetrics() keeps a figure out of comparisons; empty when it is eligible."""
    status = research.status(metric)
    if status != "supported": return str(status or "unverified")
    if (metric.get("observation_status") or "reported") != "reported": return metric["observation_status"]
    return "not preferred" if metric.get("preferred_for_comparison") is False else ""


def other_figures(research, company_id, shown):
    """The newest figure of a kind when the app keeps it out of comparisons as a forecast, a target or an older or partial
    figure. It is listed for the record, so no reported figure silently disappears. Talks, unverified claims and
    conflicting reports follow unconfirmed_figures(). 'Other' groups unrelated measures (a base-model benchmark score,
    say), so an older or partial one is not a newer figure."""
    newest = {}
    for metric in sorted(research.by_company.get(company_id, []), key=cmp_to_key(by_recent)):
        if research.status(metric) != "superseded": newest.setdefault(metric.get("kind"), metric)
    ids, order = {m["id"] for m in shown}, list(KIND_LABELS)
    rows = [m for kind, m in newest.items() if exclusion(research, m) in OTHER_STATUS and m["id"] not in ids and not (kind == "other" and exclusion(research, m) == "not preferred")]
    return sorted(rows, key=lambda m: (order.index(m.get("kind")) if m.get("kind") in order else len(order), m.get("kind") or ""))


def status_words(research, metric):
    words = ["In reported talks" if metric.get("observation_status") == "talks" else "", {"unverified": "Unverified", "contested": "Conflicting reports"}.get(research.status(metric), "")]
    if not any(words): words.append(OTHER_STATUS.get(exclusion(research, metric), ""))
    return ". ".join(word for word in words + [f"Grade {research.grade(metric)}" if research.grade(metric) else ""] if word) + "."

# ---------------------------------------------------------------------------
# Paid work listings, in the order and words the work page uses

WORK_ARCHIVE = frozenset(("historical", "closed", "contributions", "paused", "no_route", "inquiry", "information"))
WORK_ORDER = {"listed": 0, "pay_conflict": 2, "program": 3, "intake_unverified": 4, "careers": 5, "unverified": 6, "closed": 7, "historical": 8, "paused": 9, "contributions": 10, "inquiry": 10, "information": 10, "no_route": 11}
WORK_BUCKETS = (
    ("contract", "Contract and task work", "Freelance and project work for AI training."),
    ("jobs", "Jobs and fellowships", "Staff jobs and paid fellowships at these companies."),
    ("boards", "Career pages", "Each link opens a company’s full list of openings. We did not record pay for these pages."),
    ("outside", "Company jobs outside AI training", "Open staff roles that are not AI training work."),
    ("closed", "Closed or unpaid listings", "Past or paused listings, and pages with no confirmed paid work. We keep them for the record."),
)
OPEN_BUCKETS = ("contract", "jobs", "boards", "outside")
# Paid work listings, the count every surface shows: contract and task work plus jobs and fellowships.
PAID_OPEN_BUCKETS = ("contract", "jobs")
CONTRACT_GROUPS = ("Expert & contractor projects", "Contributor bounties")
# An Employment listing paid by the hour or by a one-time award is contract and task work, not a staff job (w4Bucket).
CONTRACT_PAY = ("hour", "one_time")
# w4Status() and w4Location() in web/work-v4.js; tests/test_static_pages.py runs both and checks every listing prints the same words.
WORK_STATUS = {"intake_unverified": "Availability unconfirmed", "unverified": "Availability unconfirmed", "pay_conflict": "Pay conflict", "historical": "Historical", "closed": "Closed", "paused": "Training paused", "contributions": "Research contribution", "no_route": "No confirmed paid listing", "inquiry": "Inquiry only", "information": "Information only"}
NO_PLACE = "Location not listed"
WORK_PLACES = {
    "Project-specific": "Location set per project", "Role-specific": "Location set per role", "Location not published": NO_PLACE,
    "Remote · eligibility unverified": "Remote · country rules not confirmed", "At home · eligibility unverified": "At home · country rules not confirmed",
    "Remote · project-specific": "Remote · country rules vary by project", "Remote · restricted by project": "Remote · country rules vary by project",
    "Remote · eligibility varies": "Remote · country rules vary", "Remote · country varies": "Remote · country rules vary",
    "Global community advertised; specific geographic eligibility not exhaustively verified": "Global network · country rules vary",
    "Supported countries · US residents included": "Supported countries, including US",
    "Japan-focused · US eligibility unverified": "Japan-focused · US eligibility not confirmed",
    "Palo Alto · on-site / hybrid wording": "Palo Alto · on-site or hybrid",
    "Remote US listing": "Remote US",
}
PAY_WORDS = {"Paid route not established": "Pay unconfirmed", "Paid opening unconfirmed": "Pay unconfirmed", "Compensation not promised": "Pay not promised", "No published offer": "Pay not listed", "Hourly; rate not published": "Hourly · rate unlisted"}
SALARY_SPLIT = re.compile(r"^(\$[\d,.]+K?\s*[–-]\s*\$[\d,.]+K?) salary band \+ equity;\s*(\$[\d,.]+K?\s*[–-]\s*\$[\d,.]+K?) separate bonus band$", re.I)
UNCERTAIN_CHECK = re.compile(r"HTTP 403|blocked.fetch|JavaScript.only|requires JavaScript|JavaScript shell|not verified open|could not be loaded", re.I)


def work_bucket(route):
    """w4Bucket(), the work page's groups (worker audit WORK-1): job boards, closed links, roles outside AI training,
    contract work (including Employment listings paid by the hour or by a one-time award), then jobs."""
    status = route.get("status")
    if status == "careers": return "boards"
    if status in WORK_ARCHIVE: return "closed"
    if route.get("ai_data_work") is False: return "outside"
    if route.get("group") in CONTRACT_GROUPS or (route.get("group") == "Employment" and route.get("pay_basis") in CONTRACT_PAY): return "contract"
    return "jobs"


def work_location(route):
    """w4Location(): the listing's place in plain words."""
    place = " ".join(str(route.get("geography") or "").split())
    return WORK_PLACES.get(place) or place or NO_PLACE


def work_pay(route):
    """w4Pay() in web/work-v4.js."""
    if route.get("status") == "pay_conflict" or route.get("pay_basis") == "conflicting_hourly": return "Rate conflict"
    label = clean(route.get("pay_label"))
    if not label or label == "Not published": return "Pay not listed"
    split = SALARY_SPLIT.match(label) if route.get("pay_basis") == "salary_period_unspecified" else None
    return f"{split.group(1)} salary band" if split else PAY_WORDS.get(label, label)


def work_status(route):
    """w4Status() and w4Uncertain() in web/work-v4.js; empty when nothing is in doubt."""
    status, check = route.get("status"), route.get("last_route_check") or {}
    if status == "program" and re.search("waitlist", route.get("availability_note") or "", re.I): return "Waitlist may apply"
    if status == "historical" and check.get("result") in ("official_role_not_found_redirect", "official_role_not_found"): return "Historical · listing unavailable"
    if status in WORK_STATUS: return WORK_STATUS[status]
    uncertain = ((route.get("research_record") or {}).get("route") or {}).get("live_application_verified") is False or UNCERTAIN_CHECK.search(" ".join(str(v) for v in (check.get("result"), check.get("note")) if v))
    return "Availability unconfirmed" if uncertain else ""


def work_checked(route, column=False):
    """w4Checked(): the latest link check, else the review date. In a 'Last check' column the verb is left out."""
    checked = max((d for d in (route.get("availability_checked_on"), (route.get("last_route_check") or {}).get("date")) if d), default="")
    if checked: return format_date(checked) if column else "Checked " + format_date(checked)
    if not route.get("reviewed_on"): return "Not checked" if column else ""
    return f"{format_date(route['reviewed_on'])} (review only)" if column else "Reviewed " + format_date(route["reviewed_on"])


def route_dates(route):
    return (route.get("reviewed_on"), route.get("availability_checked_on"), route.get("entry_point_reviewed_on"), (route.get("last_route_check") or {}).get("date"))


def sort_routes(routes, names):
    """filteredWork() order: status, published numeric pay first, company, role."""
    return sorted(routes, key=lambda r: (WORK_ORDER.get(r.get("status"), 10), not r.get("numeric_pay"), locale_key(names.get(r.get("company_id"), "")), locale_key(r.get("role", "")), r.get("id", "")))

# ---------------------------------------------------------------------------
# Page shell

EXTERNAL_MASK = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 17 17 7M7 7h10v10'/%3E%3C/svg%3E\")"
STYLE = (
    ":root{--bg:#f8f8f4;--ink:#18231f;--muted:#59645d;--green:#285b46;--green-dark:#193f2f;--border:#d8ddd5;--mark:#7d8b80;--soft:#eef1ea;--gutter:32px;--content:1232px;--measure:760px;--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--serif:Georgia,'Times New Roman',serif}"
    "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--sans)}"
    "a{color:var(--green);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}a:focus-visible{outline:3px solid var(--green);outline-offset:3px}"
    ".sr-only,.skip:not(:focus){position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.skip:focus{position:absolute;left:var(--gutter);top:8px;z-index:9;padding:10px 14px;background:var(--bg)}"
    ".site-header{display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:72px;padding:0 max(var(--gutter),calc((100% - var(--content))/2));border-bottom:1px solid var(--border)}"
    ".wordmark{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;font-size:17px;font-weight:650;letter-spacing:-.35px;line-height:1.2;white-space:nowrap}"
    ".wordmark small{display:block;margin-top:2px;font-size:9px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}"
    ".mark{position:relative;display:grid;place-items:center;width:32px;height:34px;border:1px solid var(--mark);font:25px/1 var(--serif);color:var(--green)}"
    ".mark svg{position:absolute;right:-4px;top:-7px;width:12px;height:12px;background:var(--bg);fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}"
    ".site-nav{display:flex;align-self:stretch;gap:22px}.site-nav a{display:flex;align-items:center;padding:0 2px;font-size:13px;color:var(--muted);text-decoration:none;border-bottom:2px solid transparent}"
    ".site-nav a:hover{color:var(--ink)}.site-nav a[aria-current]{color:var(--ink);border-bottom-color:var(--green)}.site-nav a:focus-visible{outline-offset:-3px}"
    "main,.site-footer{margin:0 max(var(--gutter),calc((100% - var(--content))/2))}main{padding:24px 0 8px}main>*{max-width:var(--measure)}main>.wide{max-width:none}"
    ".crumbs ol{display:flex;flex-wrap:wrap;gap:2px 8px;margin:0 0 24px;padding:0;list-style:none;font-size:13px;color:var(--muted)}.crumbs li+li::before{content:'/';margin-right:8px;color:var(--mark)}.crumbs a{color:var(--muted)}"
    ".eyebrow{margin:0 0 12px;font-size:11px;font-weight:600;letter-spacing:1.1px;text-transform:uppercase;color:var(--muted)}"
    "h1{margin:0 0 14px;font:400 52px/1.08 var(--serif);letter-spacing:-1.7px;overflow-wrap:break-word}"
    "h2{margin:48px 0 16px;padding-top:24px;border-top:1px solid var(--border);font-size:24px;line-height:1.25;font-weight:600;letter-spacing:-.35px}h3{margin:28px 0 8px;font-size:17px;line-height:1.35}"
    "p{margin:0 0 14px}.lede{margin:0 0 24px;font-size:18px;line-height:1.5;color:var(--muted)}"
    ".actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px}"
    ".cta{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:10px 16px;border-radius:3px;background:var(--green);color:#fff;text-decoration:none;font-size:14px;font-weight:600}.cta:hover{background:var(--green-dark)}"
    ".cta svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}"
    ".muted,.sub{font-size:13px;color:var(--muted)}.sub{display:block;margin-top:2px;font-weight:400}"
    ".tag{display:inline-block;margin:2px 4px 0 0;padding:0 6px;border:1px solid var(--mark);border-radius:2px;font-size:11px;font-weight:600;line-height:18px;color:var(--ink);white-space:nowrap}"
    f".ext::after{{content:'';display:inline-block;width:.7em;height:.7em;margin-left:.25em;background:currentColor;-webkit-mask:{EXTERNAL_MASK} center/contain no-repeat;mask:{EXTERNAL_MASK} center/contain no-repeat}}"
    ".note{margin:20px 0;padding:12px 16px;border:1px solid var(--border);border-left:3px solid var(--green);background:#fff}.note p:last-child{margin:0}"
    "dl.facts{display:grid;grid-template-columns:minmax(7.5rem,max-content) 1fr;gap:8px 24px;margin:0;font-size:15px}dl.facts dt{color:var(--muted)}dl.facts dd{margin:0;overflow-wrap:anywhere}"
    "table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px 16px 10px 0;border-bottom:1px solid var(--border);text-align:left;vertical-align:top;overflow-wrap:anywhere}"
    "thead th{font-size:12px;font-weight:500;color:var(--muted);white-space:nowrap;overflow-wrap:normal}tbody th{font-weight:600}td.value{font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}"
    "table.figures{max-width:980px}td.date{min-width:6.5em}table.risks tbody th{font-weight:400}@media(min-width:701px){table.events td:last-child a{white-space:nowrap}}"
    "ul{padding-left:20px}li{margin:6px 0;overflow-wrap:anywhere}ul.plain,ul.index-list,ul.inline-list,ul.chips,ul.listings{list-style:none;padding:0}"
    "ul.index-list{margin:16px 0 0;border-top:1px solid var(--border)}ul.index-list li{margin:0;padding:14px 0;border-bottom:1px solid var(--border)}"
    "ul.index-list li>a{font-size:18px;font-weight:600;letter-spacing:-.3px;color:var(--ink);text-decoration:none}ul.index-list li>a:hover{text-decoration:underline}"
    "ul.listings li{margin:0;padding:10px 0;border-bottom:1px solid var(--border)}ul.inline-list{display:flex;flex-wrap:wrap;gap:6px 20px}ul.inline-list li{margin:0}"
    "ul.chips{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}ul.chips li{margin:0}ul.chips a{display:inline-block;padding:6px 10px;border:1px solid var(--border);border-radius:3px;background:#fff;font-size:14px;text-decoration:none}"
    "dl.grades{margin:16px 0 0}dl.grades div{display:grid;grid-template-columns:28px minmax(0,1fr);gap:16px;align-items:baseline;padding:12px 0;border-top:1px solid var(--border)}"
    "dl.grades dt{display:grid;place-items:center;width:28px;height:28px;border:1px solid var(--mark);font:19px/1 var(--serif);color:var(--green)}dl.grades dd{margin:0;color:var(--muted)}"
    ".site-footer{margin-top:64px;padding:28px 0 40px;border-top:1px solid var(--border);font-size:13px;color:var(--muted)}"
    ".site-footer nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px 32px;max-width:var(--measure);margin-bottom:20px}"
    ".site-footer>p{max-width:var(--measure)}.site-footer h2{margin:0 0 6px;padding:0;border:0;font-size:11px;font-weight:600;letter-spacing:1.1px;text-transform:uppercase;color:var(--muted)}.site-footer ul{margin:0;padding:0;list-style:none}.site-footer li{margin:0 0 4px}"
    "@media(max-width:700px){:root{--gutter:20px}.site-header{flex-wrap:wrap;gap:4px 12px;min-height:0;padding-top:12px}"
    ".site-nav{flex-basis:100%;justify-content:space-between;gap:8px;height:44px}.site-nav a{font-size:12.5px}"
    "h1{font-size:36px;line-height:1.12;letter-spacing:-1.1px}.lede{font-size:16px}h2{margin-top:40px;font-size:22px}dl.facts{grid-template-columns:7rem 1fr;gap:6px 16px;font-size:14px}"
    "thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}table,tbody,th,td{display:block}"
    "tbody tr{display:flex;flex-wrap:wrap;column-gap:18px;padding:12px 0;border-bottom:1px solid var(--border)}th,td{padding:0;border:0}td{margin-top:4px}td.value{white-space:normal}tbody th,td.wide-cell{flex-basis:100%}"
    "td[data-label]::before{content:attr(data-label) ': ';content:attr(data-label) ': ' / '';font-size:13px;font-weight:400;color:var(--muted)}"
    ".site-footer nav{grid-template-columns:1fr 1fr}.site-footer li{margin:0}.site-footer li a{display:inline-flex;align-items:center;min-height:44px}}"
    "@media(max-width:380px){:root{--gutter:16px}.site-nav{gap:4px}.site-nav a{padding:0;font-size:11.5px;white-space:nowrap}h1{font-size:32px}}"
    "@media(forced-colors:active){.ext::after{background:LinkText}.tag,.mark{border-color:CanvasText}}"
)
WORDMARK_ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 17 17 7M7 7h10v10"/></svg>'
RIGHT_ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12h16m-7-7 7 7-7 7"/></svg>'
NAV = (("companies", "Companies", "/companies/"), ("work", "Paid work", "/work/"), ("compare", "Compare", "/#compare"), ("method", "Method", "/method/"), ("search", "Search", "/?search"))


def json_ld(payload):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def is_web_url(url):
    return bool(re.match(r"https?://", str(url or ""), re.I))


def external_link(url, label, name=""):
    """A link that leaves the site, marked with the external icon. `name` adds context for screen readers."""
    if not is_web_url(url): return escape(label)
    return f'<a class="ext" href="{escape(url)}"' + (f' aria-label="{escape(name)}"' if name else "") + f">{escape(label)}</a>"


def cta(href, label):
    return f'<a class="cta" href="{escape(href)}">{escape(label)}{RIGHT_ARROW}</a>'


def site_header(current=None, state="page"):
    links = "".join(f'<a href="{ORIGIN}{path}"' + (f' aria-current="{state}"' if key == current else "") + f">{label}</a>" for key, label, path in NAV)
    return ('<a class="skip" href="#main">Skip to content</a>\n'
            f'<header class="site-header"><a class="wordmark" href="{ORIGIN}/"><span class="mark" aria-hidden="true">S{WORDMARK_ARROW}</span><span>{SITE_NAME}<small>The AI data field guide</small></span></a>'
            f'<nav class="site-nav" aria-label="Site">{links}</nav></header>\n')


def disclosure_html():
    return escape(DISCLOSURE).replace("overview page", f'<a href="{ORIGIN}/#venture">overview page</a>', 1)


def site_footer(research, note=""):
    """The site map, then who publishes the guide with the About disclosure, then the research date and dataset version."""
    groups = (("Explore", (("Overview", "/"), ("Companies", "/companies/"), ("Paid work", "/work/"), ("Compare", "/#compare"))),
              ("Research", (("Method", "/method/"), ("What the labels mean", "/method/#labels"), ("Download the data", "/method/#downloads"))),
              ("About", (("About the publisher", "/method/#about"), ("Request a correction", "/#corrections"), ("The publisher’s proposed AI lab", "/#venture"))))
    columns = "".join(f"<div><h2>{heading}</h2><ul>" + "".join(f'<li><a href="{ORIGIN}{path}">{label}</a></li>' for label, path in links) + "</ul></div>" for heading, links in groups)
    line = " · ".join(part for part in (f"Research compiled {format_date(research.as_of)}" if research.as_of else "", f"Dataset v{research.data.get('dataset_version')}" if research.data.get("dataset_version") else "") if part)
    return (f'<footer class="site-footer"><nav aria-label="Site map">{columns}</nav><p>{SITE_NAME} is published by {PUBLISHER_NAME}. {disclosure_html()}</p>'
            + (f"<p>{escape(line)}</p>" if line else "") + note + "</footer>\n")


def crumb_nav(crumbs):
    items = "".join(f'<li><a href="{escape(url)}">{escape(name)}</a></li>' for name, url in crumbs[:-1]) + f'<li><span aria-current="page">{escape(crumbs[-1][0])}</span></li>'
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{items}</ol></nav>\n'


def breadcrumb_list(crumbs):
    return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": name, "item": url} for i, (name, url) in enumerate(crumbs)]}


def page_node(page_type, title, description, canonical, modified, crumbs, **extra):
    node = {"@context": "https://schema.org", "@type": page_type, "@id": canonical, "url": canonical, "name": title, "description": description, "inLanguage": "en", "isPartOf": WEBSITE, "publisher": PUBLISHER, "dateModified": modified, "breadcrumb": breadcrumb_list(crumbs)}
    node.update(extra)
    return node


def document(research, title, description, canonical, body, structured=None, current=None, state="page", robots="", note=""):
    """One static page: its head tags, the site header, the body and the footer."""
    head = ['<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="color-scheme" content="light">\n',
            f"<title>{escape(title)}</title>\n<meta name=\"description\" content=\"{escape(description)}\">\n"]
    if robots: head.append(f'<meta name="robots" content="{escape(robots)}">\n')
    if canonical: head.append(f'<link rel="canonical" href="{escape(canonical)}">\n')
    head.append(ICON_LINKS)
    if canonical:
        head.append(f'<meta property="og:type" content="website">\n<meta property="og:title" content="{escape(title)}">\n<meta property="og:description" content="{escape(description)}">\n<meta property="og:url" content="{escape(canonical)}">\n<meta property="og:site_name" content="{SITE_NAME}">\n<meta property="og:locale" content="en_US">\n'
                    f'<meta property="og:image" content="{SHARE_IMAGE}">\n<meta property="og:image:type" content="image/png">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n<meta property="og:image:alt" content="{escape(SHARE_ALT)}">\n'
                    f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{escape(title)}">\n<meta name="twitter:description" content="{escape(description)}">\n<meta name="twitter:image:alt" content="{escape(SHARE_ALT)}">\n')
    head.append(f"<style>{STYLE}</style>\n")
    if structured: head.append(f'<script type="application/ld+json">{json_ld(structured)}</script>\n')
    return "".join(head) + "</head>\n<body>\n" + site_header(current, state) + '<main id="main">\n' + body + "</main>\n" + site_footer(research, note) + "</body>\n</html>\n"

# ---------------------------------------------------------------------------
# Company pages

def figure_row(research, metric, context=None):
    details = [figure_note(research, metric), figure_scope(research, metric, context), basis_text(research, metric)]
    notes = [research.correction(metric, "display_attribution"), clean((context or {}).get("note"))]
    head = f'<th scope="row">{escape(figure_label(research, metric))}<span class="sub">{escape(" · ".join(d for d in details if d))}</span>' + "".join(f'<span class="sub">{escape(note)}</span>' for note in notes if note and note != "Undated company claim") + "</th>"
    value = f'<td class="value" data-label="Value">{escape(value_text(metric))}' + (' <span class="tag">Estimate</span>' if metric.get("reported_vs_estimated") == "estimated" else "") + "</td>"
    when = metric_period(research, metric)
    period = f'<td data-label="Date">{escape("Not stated" if when == "Date not stated" else when)}' + (' <span class="tag">Historical</span>' if research.historical_year(metric) else "") + "</td>"
    return f'<tr data-metric="{escape(metric["id"])}">{head}{value}{period}<td data-label="Grade">{escape(research.grade(metric) or "Not graded")}</td><td class="wide-cell" data-label="Source">{source_html(research, metric)}</td></tr>'


SOURCE_CHECKS = {"checked": "Checked {}", "summary_only": "Summary only, page not reviewed · recorded {}", "unverified": "Not checked again · recorded {}"}


def source_meta(source):
    """Publisher, publication date and when we read the page, in the words of profileSourceMeta() in web/profiles-v2.js."""
    published = source.get("published_on") if ISO_DAY.fullmatch(str(source.get("published_on") or "")) else ""
    read = source.get("accessed_on") if ISO_DAY.fullmatch(str(source.get("accessed_on") or "")) else ""
    check = SOURCE_CHECKS.get(source.get("retrieval_status"), "Recorded {}").format(format_date(read)) if read else ""
    return " · ".join(part for part in (clean(source.get("publisher")), f"Published {format_date(published)}" if published else "", check) if part)


def source_html(research, metric, inline=False):
    """The newest source as a link, its publisher and date, and a link to the rest. Inline form for running text."""
    source, more = latest_source(research, metric)
    if not source: return '<span class="muted">No source recorded.</span>' if inline else '<span class="sub">No source recorded</span>'
    meta = source_meta(source)
    link = external_link(source.get("url"), shown_text(research, source.get("title")) or clean(source.get("publisher")) or "Source") + availability(source.get("url"), research.health)
    rest = f'<a href="{ORIGIN}/#company/{escape(metric.get("company_id"))}/sources">+{plural(more, "more source")}</a>' if more else ""
    if inline: return "Source: " + link + (f' <span class="muted">({escape(meta)})</span>' if meta else "") + (f" · {rest}" if rest else "")
    return link + (f'<span class="sub">{escape(meta)}</span>' if meta else "") + rest.replace("<a ", '<a class="sub" ', 1)


def pending_item(research, m):
    old = ' <span class="tag">Historical</span>' if research.historical_year(m) else ""
    return f'<li data-metric="{escape(m["id"])}"><strong>{escape(figure_label(research, m))}: {escape(value_text(m))}</strong>{old} · {escape(metric_period(research, m))} · {escape(figure_scope(research, m))}. {escape(status_words(research, m))} {source_html(research, m, inline=True)}</li>'


def figures_html(research, company, figures, pending, others, profile_entry):
    name, contexts = company["name"], (profile_entry or {}).get("metric_context") or {}
    if figures:
        rows = "".join(figure_row(research, m, contexts.get(m["id"])) for m in figures)
        body = f'<table class="figures wide"><thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Date</th><th scope="col">Grade</th><th scope="col">Source</th></tr></thead><tbody>{rows}</tbody></table>\n'
    else:
        body = f'<p>{"Commercial revenue does not apply to this research organization." if company.get("entity_type") == "adjacent_research" else "No figure for " + escape(name) + " meets the rules for key figures."} The full profile lists every recorded claim.</p>\n'
    if pending:
        body += f'<h3 id="unconfirmed">Not confirmed</h3>\n<p class="muted">These figures were reported, but we could not confirm them. They stay out of the key figures.</p>\n<ul class="listings">{"".join(pending_item(research, m) for m in pending)}</ul>\n'
    if others:
        body += f'<h3 id="other-figures">Other reported figures</h3>\n<p class="muted">These are forecasts, targets, or older or partial figures. We list them for the record. They stay out of the key figures and comparisons.</p>\n<ul class="listings">{"".join(pending_item(research, m) for m in others)}</ul>\n'
    if figures or pending or others:
        year = re.match(r"[0-9]{4}", research.as_of)
        notes = ["Each figure keeps its own date and the part of the business it covers."]
        if any(m.get("kind") == "annualized_revenue_run_rate" for m in figures + pending + others): notes.append("Annualized pace is recent revenue projected across a full year.")
        if year: notes.append(f"Historical marks figures from {int(year.group(0)) - 2} or earlier.")
        notes.append("Estimates are labeled. Forecasts and targets never count as key figures.")
        body += f'<p class="muted">{" ".join(notes)} Grade is our confidence in the sources, from A (a filing or independent evidence) to U (unverified). <a href="{ORIGIN}/method/#grades">How we grade</a>.</p>\n'
    return '<h2 id="figures">Key figures</h2>\n' + body


def labelled(label, value):
    """'Pay: $60 / hour', but 'Pay not listed' and 'Location not listed' as they are, since they already name the field."""
    return value if value.lower().startswith(label.lower()) else f"{label}: {value}"


def work_item(research, route):
    """One listing on a company page: role link, then pay, place and check date. Closed links show no pay or place."""
    status, bucket = work_status(route), work_bucket(route)
    place = work_location(route)
    parts = [labelled("Pay", work_pay(route)) if bucket not in ("boards", "closed") else "", (place if place == NO_PLACE else labelled("Where", place)) if bucket != "closed" else "", work_checked(route)]
    tag = f' <span class="tag">{escape(status)}</span>' if status else ""
    return f'<li data-work-route="{escape(route.get("id"))}">{external_link(route.get("url"), clean(route.get("role")) or "Listing")}{availability(route.get("url"), research.health)}{tag}<span class="sub">{escape(". ".join(p for p in parts if p))}</span></li>'


def company_work_html(research, company, routes):
    cid, name = company["id"], company["name"]
    heading = f'<h2 id="work">Paid work at {escape(name)}</h2>\n'
    if not routes: return heading + f'<p class="muted">No public work listing is recorded for {escape(name)}.</p>\n'
    names = {cid: name}
    # Only contract work and jobs count as paid work listings; career pages, other roles and closed records do not.
    paid = sum(1 for r in routes if work_bucket(r) in PAID_OPEN_BUCKETS)
    lead = (f'{plural(paid, "paid work listing")} at {escape(name)}. Pay is quoted as the company published it and may be out of date. Confirm on the company\'s page before you apply.' if paid
            else f"No confirmed paid listing for {escape(name)}. The groups below show what we found.")
    body = [f"<p>{lead}</p>\n", safety_note()]
    for key, label, _ in WORK_BUCKETS:
        rows = sort_routes([r for r in routes if work_bucket(r) == key], names)
        if rows: body.append(f"<h3>{label}</h3>\n<ul class=\"listings\">" + "".join(work_item(research, r) for r in rows) + "</ul>\n")
    body.append(f'<p><a href="{ORIGIN}/#company/{escape(cid)}/work">See terms and sources in the full profile</a></p>\n')
    return heading + "".join(body)


def safety_note():
    return f'<div class="note"><p><strong>Before you apply.</strong> Never pay to get work. Apply only through the company\'s own website. {external_link(SCAM_GUIDE, "How to spot a job scam")}</p></div>\n'


def company_title(name, figures, has_work):
    """Name the figures the page holds and keep the brand: drop the last figure topics, then 'paid work', then every topic,
    until the title with ' · ScienceToStartup' fits the limit. Only a name too long to carry the brand gets a bare title."""
    kinds = {m.get("kind") for m in figures}
    topics, work = [word for word, group in TITLE_TOPICS if kinds.intersection(group)], ["paid work"] if has_work else []
    bases = [f"{name}: {join_words(topics[:n] + work)}" for n in range(len(topics), -1, -1) if topics[:n] + work] or [f"{name}: company profile"]
    for base in bases + [name]:
        if len(base + SUFFIX) <= TITLE_LIMIT: return base + SUFFIX
    return next((base for base in bases if len(base) <= TITLE_LIMIT), truncate(name, TITLE_LIMIT))


def legal_name(company):
    """The registered name only: research notes follow the first ';' ('Scale AI, Inc.; contributor platforms include ...')."""
    return clean(str(company.get("legal_entity_name") or "").split(";", 1)[0])


def company_sentence(name, text):
    """'Mercor connects specialists…' reads better in results than 'Mercor: Connects specialists…'."""
    text = full_stop(clean(text))
    if not text or text.startswith(name): return text
    return f"{name} {text[0].lower() + text[1:] if text[1:2].islower() else text}"


def company_description(research, name, summary, figures):
    """Whole sentences under the limit, led by the company name: the summary, then the revenue headline when it fits."""
    lead = company_sentence(name, summary)
    headline = figures[0] if figures and figures[0].get("kind") in REVENUE_KINDS and not research.historical_year(figures[0]) else None
    parts = sentences(lead) + ([f"{figure_label(research, headline)}: {value_text(headline)} ({metric_period(research, headline)})."] if headline else [])
    if not parts or len(parts[0]) > DESCRIPTION_LIMIT: return truncate(lead)
    text = parts[0]
    for part in parts[1:]:
        if len(text) + 1 + len(part) <= DESCRIPTION_LIMIT: text += " " + part
    return text

# Risks and disputes: profileRisks() in web/profiles-v2.js

EVENTS_NOTE = "Lawsuit entries describe allegations and court filings, not findings. Dates show when a case was filed or an event was reported."
EVENT_KINDS = {"lawsuit": "Lawsuit", "data_incident": "Data incident", "customer_change": "Customer change", "workforce_change": "Workforce change", "filing": "Filing"}


def company_events(events, company_id):
    """profileEvents(): dated events naming the company as subject or as a related party, newest first."""
    rows = [e for e in (events or {}).get("events", []) if isinstance(e, dict) and (e.get("company_id") == company_id or company_id in e.get("related_company_ids", []))]
    return sorted(sorted(rows, key=lambda e: e["id"]), key=lambda e: e["date"], reverse=True)


def risk_claims(research, company_id):
    """profileRiskClaims(): supported risk claims, newest first."""
    return sorted((c for c in research.data.get("claims", []) if c.get("company_id") == company_id and c.get("subject") == "risks" and c.get("status") == "supported"), key=cmp_to_key(by_recent))


def month_text(value):
    """profileMonthHTML(): an ISO date as its month ('Jun 2026')."""
    text = str(value or "")
    return format_date(text[:7]) if ISO_DAY.fullmatch(text) or ISO_MONTH.fullmatch(text) else ""


def statuses_checked(events):
    """When the event statuses were last checked, so a pending case is read as of that date."""
    days = sorted({e.get("status_checked_on") for e in events if ISO_DAY.fullmatch(str(e.get("status_checked_on") or ""))})
    if not days: return ""
    return f"Statuses were checked on {format_date(days[0])}." if len(days) == 1 else f"Statuses were checked between {format_date(days[0])} and {format_date(days[-1])}."


def claim_source_html(research, claim):
    """A claim's first source with its link check, and a link to the rest in the full profile."""
    rows = [research.sources[sid] for sid in claim.get("source_ids", []) if sid in research.sources]
    if not rows: return '<span class="sub">No source recorded</span>'
    link = external_link(rows[0].get("url"), shown_text(research, rows[0].get("title")) or clean(rows[0].get("publisher")) or "Source") + availability(rows[0].get("url"), research.health)
    more = f'<a class="sub" href="{ORIGIN}/#company/{escape(claim.get("company_id"))}/sources">+{plural(len(rows) - 1, "more source")}</a>' if len(rows) > 1 else ""
    return link + more


def risks_html(research, company_id, events):
    """Dated events, then supported risk claims; nothing at all when both are empty. The lawsuit note goes with the events."""
    dated, risks = company_events(events, company_id), risk_claims(research, company_id)
    if not dated and not risks: return ""
    parts = ['<h2 id="risks">Risks and disputes</h2>\n']
    if dated:
        sources = lambda e: " · ".join(external_link(s.get("url"), clean(s.get("publisher")) or "Source") + availability(s.get("url"), research.health) for s in e.get("sources", []))
        rows = "".join(f'<tr data-event="{escape(e["id"])}"><th scope="row">{escape(clean(e.get("title")))}<span class="sub">{escape(clean(e.get("detail")))}</span></th><td class="date" data-label="Date">{escape(month_text(e.get("date")) or clean(e.get("date")))}<span class="sub">{escape(EVENT_KINDS.get(e.get("kind")) or readable(e.get("kind")))}</span></td><td data-label="Status">{escape(clean(e.get("status")))}</td><td class="wide-cell" data-label="Sources">{sources(e)}</td></tr>' for e in dated)
        parts.append(f'<h3>Dated events</h3>\n<table class="wide events"><thead><tr><th scope="col">Event</th><th scope="col">Date</th><th scope="col">Status</th><th scope="col">Sources</th></tr></thead><tbody>{rows}</tbody></table>\n')
    if risks:
        when = lambda value: f'<td class="date" data-label="As of">{escape(month_text(value))}</td>' if month_text(value) else '<td class="date" data-label="Date">Source date not stated</td>'
        rows = "".join(f'<tr data-risk="{escape(c["id"])}"><th scope="row">{escape(shown_text(research, c.get("statement")))}</th>{when(c.get("as_of"))}<td class="wide-cell" data-label="Source">{claim_source_html(research, c)}</td></tr>' for c in risks)
        parts.append(f'<h3>Risks named in the evidence</h3>\n<table class="wide risks"><thead><tr><th scope="col">Risk</th><th scope="col">As of</th><th scope="col">Source</th></tr></thead><tbody>{rows}</tbody></table>\n')
    if dated: parts.append(f'<p class="muted">{EVENTS_NOTE} {escape(statuses_checked(dated))}</p>\n')
    parts.append(f'<p><a href="{ORIGIN}/#company/{escape(company_id)}/risks">See risks and disputes in the full profile</a></p>\n')
    return "".join(parts)


def render_company(research, company, editorial_entry, profile_entry, routes, peers, labels, modified, events=None):
    cid, name = company["id"], clean(company["name"])
    company = dict(company, name=name)
    canonical, app_url = f"{ORIGIN}/company/{cid}/", f"{ORIGIN}/#company/{cid}"
    entry = editorial_entry or {}
    group = entry.get("primary_offering") or ""
    group_name = labels.get(group, group)
    summary = clean(entry.get("summary")) or shown_text(research, company.get("description"))
    figures = key_figures(research, cid, profile_entry)
    pending = unconfirmed_figures(research, cid, figures)
    others = other_figures(research, cid, figures + pending)
    open_routes = [r for r in routes if work_bucket(r) in OPEN_BUCKETS]
    paid_open = [r for r in open_routes if work_bucket(r) in PAID_OPEN_BUCKETS]
    title = company_title(name, figures, bool(open_routes))
    description = company_description(research, name, summary, figures)
    # The structured breadcrumb follows the visible trail, business group included.
    crumbs = [("Overview", f"{ORIGIN}/"), ("Companies", f"{ORIGIN}/companies/")] + ([(group_name, f"{ORIGIN}/companies/#{group_slug(group)}")] if group else []) + [(name, canonical)]
    compiled = f" · research compiled {format_date(research.as_of)}" if research.as_of else ""
    work_link = (f'<a href="#work">Paid work at {escape(name)} ({plural(len(paid_open), "paid work listing")})</a>' if paid_open
                 else f'<a href="#work">Paid work at {escape(name)}</a>' if open_routes else "")
    legal = legal_name(company)
    body = [crumb_nav(crumbs),f'<p class="eyebrow">Company profile{escape(compiled)}</p>\n<h1>{escape(name)}</h1>\n<p class="lede">{escape(summary)}</p>\n',
            f'<p class="actions">{cta(app_url, "Open the full profile")}{work_link}</p>\n', figures_html(research, company, figures, pending, others, profile_entry)]
    facts = []
    if group: facts.append(("Business group", f'<a href="{ORIGIN}/companies/#{group_slug(group)}">{escape(group_name)}</a>'))
    if is_web_url(company.get("website")): facts.append(("Website", external_link(company["website"], re.sub(r"^https?://(www\.)?", "", company["website"]).rstrip("/"))))
    if company.get("founded_year"): facts.append(("Founded", escape(company["founded_year"])))
    if legal and legal != name: facts.append(("Legal entity", escape(legal)))
    tags = [clean(t) for t in entry.get("capability_tags") or [] if clean(t)]
    if tags: facts.append(("Also works on", escape(", ".join(tags))))
    if facts: body.append(f'<h2 id="facts">About {escape(name)}</h2>\n<dl class="facts">' + "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts) + "</dl>\n")
    products = research.products(cid, (profile_entry or {}).get("products"))[:PRODUCT_LIMIT]
    if products:
        verb = "does" if company.get("entity_type") == "adjacent_research" else "sells"
        items = "".join(f"<li><strong>{escape(clean(p.get('name')))}</strong>" + (f": {escape(full_stop(clean(p.get('description'))))}" if clean(p.get("description")) else "") + (f' <span class="muted">{escape(full_stop(clean(p.get("status"))))}</span>' if clean(p.get("status")) else "") + "</li>" for p in products)
        body.append(f'<h2 id="offerings">What {escape(name)} {verb}</h2>\n<ul>{items}</ul>\n')
    body.append(risks_html(research, cid, events))
    body.append(company_work_html(research, company, routes))
    if peers:
        links = "".join(f'<li><a href="{ORIGIN}/company/{escape(p["id"])}/">{escape(clean(p["name"]))}</a></li>' for p in peers)
        body.append(f'<h2 id="related">More in {escape(group_name)}</h2>\n<ul class="inline-list">{links}</ul>\n<p class="muted"><a href="{ORIGIN}/companies/#{group_slug(group)}">See this group on the company list</a></p>\n')
    tabs = (("Figures", "traction"), ("Funding and people", "people"), ("Paid work", "work"), ("Sources", "sources"))
    body.append(f'<h2 id="full-profile">In the full profile</h2>\n<p>The full profile shows each sourced claim with its confidence grade, including funding rounds and customer relationships.</p>\n<ul class="inline-list">'
                + "".join(f'<li><a href="{app_url}/{part}">{label}</a></li>' for label, part in tabs) + f'</ul>\n<p class="actions">{cta(app_url, "Open the full profile")}</p>\n'
                + f'<p class="muted">{SITE_NAME} is a public guide to {plural(len(research.companies), "AI data company", "AI data companies")}, published by {PUBLISHER_NAME}. Each figure links to its source. We do not confirm any company\'s current status. No profiled company has paid for coverage. <a href="{ORIGIN}/method/">How we check the research</a>.</p>\n')
    organization = {"@type": "Organization", "@id": canonical + "#organization", "name": name, "description": shown_text(research, company.get("description")) or summary}
    if is_web_url(company.get("website")): organization["url"] = company["website"]
    if company.get("founded_year"): organization["foundingDate"] = str(company["founded_year"])
    if legal: organization["legalName"] = legal
    aliases = [clean(a) for a in company.get("aliases") or [] if clean(a) and clean(a) not in (name, legal)]
    if aliases: organization["alternateName"] = aliases
    structured = page_node("WebPage", title, description, canonical, modified, crumbs, about={"@id": organization["@id"]}, mainEntity=organization)
    return document(research, title, description, canonical, "".join(body), structured, current="companies", state="true")

# ---------------------------------------------------------------------------
# Company list, paid work, method and 404 pages

def group_order(groups):
    """Largest business group first, as on the overview; ties by name."""
    return sorted(groups, key=lambda g: (-len(groups[g]), locale_key(g)))


def render_index(research, companies, editorial_by_id, labels, work_count, modified):
    canonical, count = f"{ORIGIN}/companies/", len(companies)
    title = f"AI data companies: {count} sourced profiles{SUFFIX}"
    description = f"Profiles of {count} AI data companies, grouped by what they sell. Each figure links to its source and shows when we checked or recorded it."
    crumbs = [("Overview", f"{ORIGIN}/"), ("Companies", canonical)]
    groups = {}
    for c in companies: groups.setdefault((editorial_by_id.get(c["id"]) or {}).get("primary_offering") or "Other", []).append(c)
    order = group_order(groups)
    nonprofit = len(groups.get("Nonprofit research", []))
    compiled = f" · research compiled {format_date(research.as_of)}" if research.as_of else ""
    body = [crumb_nav(crumbs), f'<p class="eyebrow">Companies{escape(compiled)}</p>\n<h1>AI data companies</h1>\n',
            f'<p class="lede">Profiles of {count} AI data companies. Each figure links to its source and shows when we checked or recorded it. Each profile lists any paid work we found.' + (f" {count_word(nonprofit)} of the {count} are nonprofit research groups." if nonprofit else "") + "</p>\n",
            f'<p class="muted">{COVERAGE} Firms not yet profiled include {escape(join_words(list(NOT_YET_PROFILED)))}.</p>\n',
            f'<p class="actions">{cta(ORIGIN + "/#companies", "Open the interactive list")}' + (f'<a href="{ORIGIN}/work/">See {plural(work_count, "paid work listing")}</a>' if work_count else "") + "</p>\n",
            '<nav aria-label="Business groups"><ul class="chips">' + "".join(f'<li><a href="#{group_slug(g)}">{escape(labels.get(g, g))} ({len(groups[g])})</a></li>' for g in order) + "</ul></nav>\n"]
    for g in order:
        items = "".join(f'<li><a href="{ORIGIN}/company/{escape(c["id"])}/">{escape(clean(c["name"]))}</a><span class="sub">{escape(clean((editorial_by_id.get(c["id"]) or {}).get("summary")) or shown_text(research, c.get("description")))}</span></li>' for c in groups[g])
        body.append(f'<h2 id="{group_slug(g)}">{escape(labels.get(g, g))}</h2>\n<p class="muted">{plural(len(groups[g]), "company", "companies")} · <a href="{ORIGIN}/#companies/{group_slug(g)}">Open this group in the interactive list</a></p>\n<ul class="index-list">{items}</ul>\n')
    structured = page_node("CollectionPage", title, description, canonical, modified, crumbs, mainEntity={"@type": "ItemList", "numberOfItems": count, "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": clean(c["name"]), "url": f"{ORIGIN}/company/{c['id']}/"} for i, c in enumerate(companies)]})
    return document(research, title, description, canonical, "".join(body), structured, current="companies", note=f"<p>{LOGO_NOTE}</p>")


def work_table(research, rows, names, key):
    columns = {"boards": ("Company", "Where", "Last check"), "closed": ("Company", "Status", "Last check")}.get(key, ("Company", "Pay", "Where", "Last check"))
    head = '<tr><th scope="col">Listing</th>' + "".join(f'<th scope="col">{c}</th>' for c in columns) + "</tr>"
    out = []
    for r in rows:
        cid, status = r.get("company_id"), work_status(r)
        company = names.get(cid, cid)
        cells = {"Company": f'<a href="{ORIGIN}/company/{escape(cid)}/#work">{escape(company)}</a>', "Pay": escape(work_pay(r)), "Where": escape(work_location(r)), "Status": escape(status or "Closed"), "Last check": escape(work_checked(r, column=True))}
        role = clean(r.get("role")) or "Listing"
        tag = f' <span class="tag">{escape(status)}</span>' if status and key != "closed" else ""
        out.append(f'<tr data-work-route="{escape(r.get("id"))}"><th scope="row">{external_link(r.get("url"), role, f"{role}, {company}")}{availability(r.get("url"), research.health)}{tag}</th>' + "".join(f'<td data-label="{c}">{cells[c]}</td>' for c in columns) + "</tr>")
    return f'<table class="wide"><thead>{head}</thead><tbody>{"".join(out)}</tbody></table>\n'


def render_work(research, routes, names, modified):
    canonical = f"{ORIGIN}/work/"
    rows = [r for r in routes if r.get("company_id") in names]
    count, companies = len(rows), len({r["company_id"] for r in rows})
    checked = latest(*(d for r in rows for d in (r.get("availability_checked_on"), (r.get("last_route_check") or {}).get("date"))))
    open_rows = [r for r in rows if work_bucket(r) in PAID_OPEN_BUCKETS]
    open_count, open_companies = len(open_rows), len({r["company_id"] for r in open_rows})
    title = f"{plural(open_count, 'paid work listing')} in AI training{SUFFIX}"
    description = truncate(f"{plural(open_count, 'paid work listing')} in AI training at {plural(open_companies, 'AI data company', 'AI data companies')}, with pay as published and when we last checked or reviewed each one.")
    crumbs = [("Overview", f"{ORIGIN}/"), ("Paid work", canonical)]
    buckets = {key: sort_routes([r for r in rows if work_bucket(r) == key], names) for key, _, _ in WORK_BUCKETS}
    body = [crumb_nav(crumbs), f'<p class="eyebrow">Paid work' + (f" · links checked up to {escape(format_date(checked))}" if checked else "") + "</p>\n<h1>Paid AI training work</h1>\n",
            f'<p class="lede">{plural(open_count, "paid work listing")} at {plural(open_companies, "AI data company", "AI data companies")}, out of {plural(count, "listing")} we reviewed at {plural(companies, "company", "companies")}. Pay is quoted as each company published it and may be out of date. Apply on the company\'s own page.</p>\n',
            safety_note(), f'<p class="actions">{cta(ORIGIN + "/#work", "Filter listings in the full guide")}</p>\n',
            '<nav aria-label="Listing groups"><ul class="chips">' + "".join(f'<li><a href="#{key}">{label} ({len(buckets[key])})</a></li>' for key, label, _ in WORK_BUCKETS if buckets[key]) + "</ul></nav>\n"]
    for key, label, note in WORK_BUCKETS:
        if buckets[key]: body.append(f'<h2 id="{key}">{label}</h2>\n<p class="muted">{note}</p>\n' + work_table(research, buckets[key], names, key))
    structured = page_node("CollectionPage", title, description, canonical, modified, crumbs)
    return document(research, title, description, canonical, "".join(body), structured, current="work")


DOWNLOADS = (("research.json", "JSON", "application/json", "The core research data in one file"), ("observatory.sqlite", "SQLite", "application/vnd.sqlite3", "The same data as one database file"),
             ("work-routes.json", "JSON", "application/json", "Paid work listings and their sources"), ("source-updates.json", "JSON", "application/json", "Later source corrections and the values they replace"),
             ("profile-content.json", "JSON", "application/json", "Profile summaries and the records they cite"), ("editorial.json", "JSON", "application/json", "Business groups and plain-language summaries"),
             ("business-health.json", "JSON", "application/json", "Each business health dashboard observation, with its sources and calculations"))
GRADES = (("A", "Independent or buyer-side evidence, such as a filing or a customer who confirms the work."), ("B", "The company, an investor or another named first-hand source says it."), ("C", "Reporting by others, an estimate, or indirect evidence."), ("U", "Not confirmed. The fact may be undisclosed or still unresolved."))


def render_method(research, sizes, modified):
    data, canonical = research.data, f"{ORIGIN}/method/"
    title = f"Method: how the research is checked{SUFFIX}"
    description = f"How {SITE_NAME} grades each claim and how to request a correction. Published by {PUBLISHER_NAME}. The research data is free to download."
    crumbs = [("Overview", f"{ORIGIN}/"), ("Method", canonical)]
    year = re.match(r"[0-9]{4}", research.as_of)
    claims = data.get("claims", [])
    doubtful = sum(1 for c in claims if c.get("status") in ("unverified", "contested"))
    compiled = f" · research compiled {format_date(research.as_of)}" if research.as_of else ""
    body = [crumb_nav(crumbs), f'<p class="eyebrow">Method{escape(compiled)}</p>\n<h1>How the research is checked.</h1>\n<p class="lede">Each claim links to its evidence. Financial figures keep their dates and the part of the business they cover.</p>\n',
            f'<p class="actions">{cta(ORIGIN + "/#method", "Open the full method page")}</p>\n',
            '<h2 id="about">About and corrections</h2>\n'
            f"<p>{SITE_NAME} is published by {PUBLISHER_NAME}. It is a public-source research guide to the companies that produce AI training data. No profiled company has paid for coverage, and none is a customer, investor or affiliate of the publisher. {escape(WORK_DISCLOSURE)}</p>\n"
            f"<p><strong>Disclosure.</strong> {disclosure_html()}</p>\n"
            f'<p><strong>Corrections.</strong> If a figure or a listing is wrong, <a href="{ORIGIN}/#corrections">request a correction</a> with the company name and the source. We review each request within seven days.</p>\n'
            "<p><strong>Personal data and removal.</strong> Company profiles name founders and executives from public company sources only. Profiles do not show personal contact details. If you are named here and want a record corrected or removed, send a correction request. "
            f"{VISITS_NOTE}</p>\n",
            '<h2 id="figures">How figures are shown</h2>\n<ul>'
            "<li>Each figure keeps its own date and the part of the business it covers, such as the whole company or one business segment.</li>"
            "<li>Key figures come only from supported claims about reported results. The interactive guide uses the same rule.</li>"
            "<li>Figures from talks, unverified reports or conflicting sources appear only in a separate list marked Not confirmed, with their status in words.</li>"
            + (f"<li>Historical marks figures from {int(year.group(0)) - 2} or earlier.</li>" if year else "")
            + "<li>Annualized pace is recent revenue projected across a full year. We say whether revenue is gross or net when the source says so.</li>"
            "<li>Estimates are labeled. Forecasts, targets and older or partial figures go in a separate list of other reported figures. They never count as key figures.</li>"
            "<li>Later source corrections appear next to the figure they correct. The original records stay in the downloads.</li></ul>\n",
            '<h2 id="grades">Confidence grades</h2>\n<p>Each claim carries a confidence grade that says how strong its sources are.</p>\n<dl class="grades">' + "".join(f"<div><dt>{g}</dt><dd>{escape(text)}</dd></div>" for g, text in GRADES) + "</dl>\n"]
    dimensions = (data.get("rubric") or {}).get("dimensions") or []
    if dimensions:
        rows = "".join(f'<tr><th scope="row">{escape(d.get("id"))} · {escape(clean(d.get("label")))}</th>' + "".join(f'<td data-label="Level {n}">{escape(clean((d.get("levels") or {}).get(n)))}</td>' for n in ("1", "2", "3")) + "</tr>" for d in dimensions)
        body.append('<h2 id="labels">What the labels mean</h2>\n<p>Each company also gets a delivery evidence level (public proof that it sells and delivers its offer). The level comes from four measures, each rated from level 1 to level 3, and covers one part of the business, such as the whole company or its AI data work. Funding and valuations do not count toward it.</p>\n'
                    f'<table class="wide"><thead><tr><th scope="col">Measure</th><th scope="col">Level 1</th><th scope="col">Level 2</th><th scope="col">Level 3</th></tr></thead><tbody>{rows}</tbody></table>\n')
    # Some companies hold two ratings (one per business scope), so count the companies rated, as the app's method page does.
    rated = {row.get("company_id") for row in data.get("assessments", [])} & set(research.companies)
    unrated = [c for cid, c in research.companies.items() if cid not in rated]
    unrated_note = (f" The {count_word(len(unrated)).lower()} nonprofit research {'group gets' if len(unrated) == 1 else 'groups get'} no level." if unrated and all(c.get("entity_type") == "adjacent_research" for c in unrated)
                    else f" {plural(len(unrated), 'company has', 'companies have')} no level yet." if unrated else "")
    body.append(f'<h2 id="coverage">Research coverage</h2>\n<p>{plural(len(research.companies), "company profile")} · {plural(len(rated), "company", "companies")} with a delivery evidence level · {plural(len(data.get("sources", [])), "source record")}.{unrated_note}</p>\n'
                f"<p>{plural(doubtful, 'claim is', 'claims are')} unverified or disputed. Each one is labeled. The guide is a selected study of the market. It does not list every company.</p>\n")
    files = [(name, kind, mime, text) for name, kind, mime, text in DOWNLOADS if name in sizes] + [(name, "CSV", "text/csv", f"The {name[:-4].replace('_', ' ')} table") for name in sorted(n for n in sizes if n.endswith(".csv"))]
    if files:
        rows = "".join(f'<tr><th scope="row"><a href="{ORIGIN}/{escape(name)}" download>{escape(name)}</a></th><td data-label="Format">{kind}</td><td data-label="Size">{escape(sizes[name])}</td><td data-label="Contents">{escape(text)}</td></tr>' for name, kind, mime, text in files)
        version = data.get("dataset_version", "")
        body.append(f'<h2 id="downloads">Download the data</h2>\n<p>Dataset version {escape(version)}{escape(compiled.replace(" · research", ", research"))}. The research data files keep every claim that later research replaced.</p>\n'
                    f'<p>{SITE_NAME} licenses this data under the <a class="ext" rel="license" href="{DATA_LICENSE}">CC BY 4.0 license</a> (any use is allowed if you credit us). Cite {SITE_NAME} and the original sources. Company names and logos belong to their owners. The license does not cover them. It also leaves out product images, photos of people, text quoted from sources and personal contact details.</p>\n'
                    f'<table class="wide"><thead><tr><th scope="col">File</th><th scope="col">Format</th><th scope="col">Size</th><th scope="col">Contents</th></tr></thead><tbody>{rows}</tbody></table>\n')
    counts = {key: len(data.get(key, [])) for key in ("companies", "claims", "sources", "metrics", "funding_rounds", "products")}
    counts["current_claims"] = sum(1 for claim in data.get("claims", []) if claim.get("status") != "superseded")
    measured = sorted({KIND_LABELS.get(m.get("kind"), "") for m in data.get("metrics", [])} - {"", KIND_LABELS["other"]})
    # The home page's Dataset node, described in full where its files are listed. Publisher and creator link to the one Person by @id.
    dataset = {"@context": "https://schema.org", "@type": "Dataset", "@id": DATASET_ID, "name": DATASET_NAME, "alternateName": clean((data.get("meta") or {}).get("title")) or SITE_NAME,
               "description": f"Public-source research on {counts['companies']} AI data companies: {counts['current_claims']:,} current claims ({counts['claims']:,} including earlier versions) from {counts['sources']:,} sources, with {counts['metrics']} figures, {counts['funding_rounds']} funding rounds and {counts['products']} products. Each claim keeps its business scope and confidence grade, and each figure links to its sources.",
               "url": canonical, "version": data.get("dataset_version", ""), "dateModified": research.as_of, "isAccessibleForFree": True, "license": DATA_LICENSE,
               "creator": {"@id": PUBLISHER["@id"]}, "publisher": {"@id": PUBLISHER["@id"]},
               "measurementTechnique": "Public-source research. Each claim is graded A, B, C or U by the strength of its sources.", "variableMeasured": measured,
               "distribution": [{"@type": "DataDownload", "name": name, "contentUrl": f"{ORIGIN}/{name}", "encodingFormat": mime} for name, kind, mime, text in files]}
    structured = [page_node("AboutPage", title, description, canonical, modified, crumbs, about={"@id": WEBSITE["@id"]}), dataset]
    return document(research, title, description, canonical, "".join(body), structured, current="method")


def render_not_found(research):
    count = len(research.companies)
    pages = (("Overview", "/", "what the guide covers"), ("Companies", "/companies/", f"profiles of all {plural(count, 'company', 'companies')}" if count else "company profiles"), ("Paid work", "/work/", "public listings with pay and location"), ("Method", "/method/", "how we check figures and how to request a correction"), ("About the publisher", "/#about", "who publishes the guide and how to get in touch"), ("Search", "/?search", "find a company, product or listing"))
    items = "".join(f'<li><a href="{ORIGIN}{path}">{label}</a>: {text}</li>' for label, path, text in pages)
    body = f'<p class="eyebrow">Page not found</p>\n<h1>We could not find that page.</h1>\n<p class="lede">The link may be old or mistyped. Start again from one of these pages:</p>\n<ul>{items}</ul>\n'
    return document(research, f"Page not found{SUFFIX}", "The page you asked for does not exist on ScienceToStartup.", "", body, robots="noindex")

# ---------------------------------------------------------------------------
# Sitemap and the build entry point

def render_sitemap(entries):
    urls = "".join(f"  <url>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{escape(lastmod)}</lastmod>\n  </url>\n" for loc, lastmod in entries)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n"


def file_size(size):
    try:
        from observatory import format_file_size
    except ImportError:
        return f"{size} B"
    return format_file_size(size)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else None


def write_static_pages(data, destination, work_data=None, profile_content=None, editorial=None, events=None, link_health=None, root=ROOT):
    """Write /company/<id>/, /companies/, /work/, /method/, 404.html and sitemap.xml.
    `events` is the company events sidecar and `link_health` the link checks, both as the build validated them."""
    destination, root = Path(destination), Path(root)
    research = Research(data, read_js_object(root / "web/app.js", "FINANCIAL_HEADLINES"), read_json(root / "data/source-updates.json"),
                        say=public_wording(data, load_copy_edits(root / "web/app.js")), health=link_health_index(link_health))
    # A company page with dated events changes when the events are reviewed, so its lastmod follows that review too.
    events_reviewed = str((events or {}).get("reviewed_on") or "")
    labels = read_js_object(root / "web/editorial.js", "GROUP_LABELS")
    editorial_by_id = {e["company_id"]: e for e in (editorial or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    profile_by_id = {e["company_id"]: e for e in (profile_content or {}).get("entries", []) if isinstance(e, dict) and e.get("company_id")}
    companies = sorted(data.get("companies", []), key=lambda c: c["id"])
    by_name = sorted(companies, key=lambda c: (locale_key(clean(c["name"])), c["id"]))
    names = {c["id"]: clean(c["name"]) for c in companies}
    routes = [r for r in (work_data or {}).get("routes", []) if isinstance(r, dict) and r.get("company_id") in names]
    reviewed = [e.get("reviewed_on") for e in editorial_by_id.values()]
    written, entries = [], [(f"{ORIGIN}/", latest(research.as_of, SITE_REVISED) or research.as_of)]
    company_entries = []
    for company in companies:
        cid = company["id"]
        if not COMPANY_ID.match(cid): raise ValueError(f"static pages: company id is not URL-safe: {cid!r}")
        own = [r for r in routes if r["company_id"] == cid]
        group = (editorial_by_id.get(cid) or {}).get("primary_offering")
        peers = [c for c in by_name if c["id"] != cid and group and (editorial_by_id.get(c["id"]) or {}).get("primary_offering") == group]
        modified = latest(research.as_of, SITE_REVISED, (editorial_by_id.get(cid) or {}).get("reviewed_on"), events_reviewed if company_events(events, cid) else "", *(d for r in own for d in route_dates(r))) or research.as_of
        folder = destination / "company" / cid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(render_company(research, company, editorial_by_id.get(cid), profile_by_id.get(cid), own, peers, labels, modified, events), encoding="utf-8")
        written.append(folder / "index.html")
        company_entries.append((f"{ORIGIN}/company/{cid}/", modified))
    index_modified = latest(research.as_of, SITE_REVISED, *reviewed) or research.as_of
    work_modified = latest(research.as_of, SITE_REVISED, *(d for r in routes for d in route_dates(r))) or research.as_of
    method_modified = latest(research.as_of, SITE_REVISED) or research.as_of
    sizes = {path.name: file_size(path.stat().st_size) for path in sorted(destination.iterdir()) if path.is_file() and (path.suffix == ".csv" or path.name in {d[0] for d in DOWNLOADS})}
    pages = {"companies": render_index(research, by_name, editorial_by_id, labels, sum(1 for r in routes if work_bucket(r) in PAID_OPEN_BUCKETS), index_modified), "work": render_work(research, routes, names, work_modified), "method": render_method(research, sizes, method_modified)}
    for name, page in pages.items():
        (destination / name).mkdir(parents=True, exist_ok=True)
        (destination / name / "index.html").write_text(page, encoding="utf-8")
        written.append(destination / name / "index.html")
    (destination / "404.html").write_text(render_not_found(research), encoding="utf-8")
    written.append(destination / "404.html")
    entries += [(f"{ORIGIN}/companies/", index_modified)] + company_entries + [(f"{ORIGIN}/work/", work_modified), (f"{ORIGIN}/method/", method_modified)]
    (destination / "sitemap.xml").write_text(render_sitemap(entries), encoding="utf-8")
    written.append(destination / "sitemap.xml")
    return written
