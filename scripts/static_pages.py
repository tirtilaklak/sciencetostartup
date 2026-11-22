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
from collections import Counter
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import cmp_to_key
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from presentation import observation_source_ids
from schema_def import TABLES

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://sciencetostartup.com"
SITE_NAME = "ScienceToStartup"
SUFFIX = f" · {SITE_NAME}"
from public_identity import load_identity, publisher_node
PUBLIC_IDENTITY = load_identity()
PUBLISHER_NAME = PUBLIC_IDENTITY["publisher"]["name"]
CORRECTION_EMAIL = "musaeminozdem@gmail.com"
DESCRIPTION_LIMIT = 155
# Search results show about 60 characters of a title, so every title stays under 60.
TITLE_LIMIT = 59
METRIC_LIMIT = 8
PRODUCT_LIMIT = 6
# Bump by hand when page links, layout, copy or structured data change; it feeds sitemap <lastmod>.
SITE_REVISED = "2026-11-22"
COMPANY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ISO_DAY = re.compile(r"\b([0-9]{4})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\b")
ISO_MONTH = re.compile(r"\b([0-9]{4})-(0[1-9]|1[0-2])\b")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
NUMBER_WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten")

SHARE_IMAGE = f"{ORIGIN}/assets/share/sciencetostartup-1200x630.png"
SHARE_ALT = "ScienceToStartup, the AI data field guide: the businesses behind AI data. Company profiles and paid work listings, with every figure linked to its source."
# The icon set web/index.html links: an SVG, a 48 px PNG and an opaque 180 px Apple touch icon. /favicon.ico sits at the root.
ICON_LINKS = '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n<link rel="icon" href="/assets/favicon-48.png" sizes="48x48" type="image/png">\n<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
PUBLISHER = publisher_node(PUBLIC_IDENTITY)
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
COVERAGE = "The guide covers selected companies."
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
RUN_RATE_REPORTING_DATES = {
    "a-team.claim.growth_metrics-2.metric-0": ("2022-05-17", "a-team.source.ateam-7"),
    "afterquery.metric.round2-financial-2": ("2026-04-09", "afterquery.source.round2-funding"),
    "micro1.metric.oct14-q3-run-rate": ("2026-10-12", "micro1.source.oct14-19eb5016dbc6"),
    "prime_intellect.metric.audit-pi-run-rate": ("2026-07-08", "prime_intellect.source.oct14-13f8e60149ba"),
    "proximal.metric.oct14-0-revenue-run-rate": ("2026-09-29", "proximal.source.oct14-4e72c4026cdf"),
    "snorkel_ai.metric.major-growth_metrics-0": ("2026-09-22", "snorkel_ai.source.audit-s5"),
}


def snapshot_matches(actual, expected):
    """evidenceContextSnapshotMatches(): every field in the retained snapshot still equals the record."""
    return isinstance(actual, dict) and isinstance(expected, dict) and all(key in actual and actual[key] == value for key, value in expected.items())


class Research:
    """The dataset indexed once, answering the questions the app asks of it.
    The rules read the records as stored, like the app. `say` (public_wording) only changes the words the pages print.
    `health` (link_health_index) carries the link checks."""

    def __init__(self, data, headlines=None, updates=None, say=None, health=None, publication_as_of=None):
        self.data = data
        self.say = say or (lambda value: "" if value is None else str(value))
        self.health = health or {}
        self.claims = {row["id"]: row for row in data.get("claims", [])}
        self.sources = {row["id"]: row for row in data.get("sources", [])}
        self.companies = {row["id"]: row for row in data.get("companies", [])}
        self.by_company = {}
        for row in data.get("metrics", []): self.by_company.setdefault(row.get("company_id"), []).append(row)
        self.as_of = str(data.get("meta", {}).get("as_of", ""))
        self.publication_as_of = publication_as_of or self.as_of
        self.headlines = dict(headlines or {})
        current = isinstance(updates, dict) and updates.get("baseline_dataset_version") == data.get("dataset_version")
        self.corrections = self._corrections(updates) if current else {}
        self.reviewed_source_dates = self._reviewed_source_dates(updates if current else {})
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

    def _reviewed_source_dates(self, updates):
        from observatory import ValidationError, validate_source_publication_date

        dates = {}
        section = updates.get("evidence_context") or {}
        if section.get("version") == "1.0.0":
            corrections = [row for row in section.get("corrections", []) if isinstance(row, dict)]
            id_counts = Counter(row.get("id") for row in [*corrections, *(updates.get("updates") or [])] if isinstance(row, dict) and isinstance(row.get("id"), str))
            publications = [row for row in corrections if row.get("kind") == "source_publication_date"]
            source_counts = Counter(row["target"]["source_id"] for row in publications if isinstance(row.get("target"), dict) and isinstance(row["target"].get("source_id"), str))
            for row in publications:
                try:
                    validate_source_publication_date(row, self.sources, self.data.get("dataset_version"))
                except ValidationError:
                    continue
                sid = row["target"]["source_id"]
                if id_counts[row["id"]] == source_counts[sid] == 1:
                    dates.setdefault(sid, set()).add(row["publication_date"])
        for corrections in self.corrections.values():
            for update in corrections:
                snapshot = update["historical_snapshot"]
                for ref in update.get("sources", []):
                    day, sid = ref.get("publication_date"), ref.get("source_id")
                    if not ISO_DAY.fullmatch(str(day or "")) or ref.get("publication_date_basis") != "retained_page_text" or ref.get("access_status") != "retained_readable_page":
                        continue
                    source, claim = self.sources.get(sid), self.claims.get(ref.get("claim_id"))
                    if not source or source.get("published_on") or not claim or sid not in claim.get("source_ids", []):
                        continue
                    if source.get("company_id") != update["company_id"] or claim.get("company_id") != update["company_id"]:
                        continue
                    if source in snapshot.get("sources", []) and claim in snapshot.get("claims", []):
                        dates.setdefault(sid, set()).add(day)
        return {sid: next(iter(days)) for sid, days in dates.items() if len(days) == 1}

    def observation_period(self, observation):
        source_ids = observation.get("source_ids", [])
        for update in self.corrections.get(observation["id"], []):
            target = update["target"]
            if (update["kind"] == "metric_reporting_context" and observation["company_id"] == update["company_id"]
                    and observation.get("metric_ids") == [target["metric_id"]] and observation.get("claim_ids") == [target["claim_id"]]
                    and any(ref.get("role") == "bound_gross_observation" and ref.get("source_id") in source_ids for ref in update.get("sources", []))):
                return update["display_period"].removesuffix(" · reported")
        period = observation.get("period", {}).get("label") or observation.get("as_of", "")
        reporting_day, source_id = RUN_RATE_REPORTING_DATES.get(observation["id"], (None, None))
        if period == reporting_day and source_id in source_ids:
            return "Reported " + format_date(period)
        return period

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
    if metric.get("company_id") == "rws_trainai" and metric.get("segment_scope") == "company": return "RWS Holdings plc group"
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
    ("contract", "Contract and task work", "Published offers and expert networks. Work is assigned by the employer."),
    ("jobs", "Jobs and fellowships", "Staff jobs and paid fellowships at these companies."),
    ("boards", "Career pages", "Each link opens a company’s full list of openings. We did not record pay for these pages."),
    ("outside", "Company jobs outside AI training", "Open staff roles that are not AI training work."),
    ("closed", "Closed or unpaid listings", "Past or paused listings, and pages with no confirmed paid work. We keep them for the record."),
)
# Discovery is independent of engagement. Keep WORK_BUCKETS/work_bucket for
# callers comparing the older engagement grouping, but render the reviewed kind.
WORK_DISPLAY_BUCKETS = (
    ("named", "Named listings", ""),
    ("programs", "Networks and programs", "Membership and intake routes. Joining a network does not guarantee a project."),
    ("boards", "Career pages", "Each link opens a company’s full list of openings. We did not record pay for these pages."),
    ("outside", "Company jobs outside AI training", "Staff roles outside AI training, kept separate from paid AI training listings."),
    ("closed", "Past and other records", "Past, paused and information-only records. These stay outside the paid work route count."),
)
WORK_KIND_LABELS = {"named_listing": "Specific listing", "network_program": "Expert network or program", "career_page": "Career page", "other_record": "Other record"}
WORK_ENGAGEMENT_LABELS = {"contract": "Contract work", "employment": "Staff employment", "fellowship": "Fellowship", "bounty": "Contribution bounty", "study": "Paid study", "varies": "Engagement varies", "unknown": "Engagement not established"}
WORK_FIELD_LABELS = {"destination": "Application destination", "pay": "Pay", "location": "Location", "requirements": "Requirements", "commitment": "Commitment", "duration": "Duration", "assessment": "Assessment"}
WORK_FIELD_STATES = {"sourced": "Source evidence recorded", "source_not_stated": "Not stated in the reviewed source", "not_researched": "Not researched", "conflicting": "Sources conflict"}
OPEN_BUCKETS = ("contract", "jobs", "boards", "outside")
# Legacy engagement groups. Public route counts use work_primary(), below.
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
    """w4Bucket(): legacy engagement grouping, independent of payment units."""
    status = route.get("status")
    if status == "careers": return "boards"
    if status in WORK_ARCHIVE: return "closed"
    if route.get("ai_data_work") is False: return "outside"
    if work_engagement(route) in ("contract", "bounty", "study", "varies", "unknown"): return "contract"
    return "jobs"


def work_kind(route):
    """w4OpportunityKind(): only stored classification or the app's explicit fallback."""
    kind, status = route.get("route_kind"), route.get("status")
    if kind in WORK_KIND_LABELS: return kind
    if status == "careers": return "career_page"
    if status == "program": return "network_program"
    return "other_record" if status in ("information", "inquiry", "contributions", "no_route") else "named_listing"


def work_engagement(route):
    """w4Engagement(): payment units never determine employment type."""
    if route.get("engagement_type") in WORK_ENGAGEMENT_LABELS: return route["engagement_type"]
    return {"Expert & contractor projects": "contract", "Employment": "employment", "Research fellowship": "fellowship", "Contributor bounties": "bounty"}.get(route.get("group"), "unknown")


def work_display_bucket(route):
    """w4DiscoveryGroups(), preserving archive and outside-AI-training scope."""
    kind = work_kind(route)
    if route.get("status") in WORK_ARCHIVE: return "closed"
    if kind == "career_page": return "boards"
    if route.get("ai_data_work") is False: return "outside"
    return {"named_listing": "named", "network_program": "programs"}.get(kind, "closed")


def work_primary(route):
    return work_display_bucket(route) in ("named", "programs")


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
    if route.get("availability_label"): return clean(route["availability_label"])
    status, check = route.get("status"), route.get("last_route_check") or {}
    if ((route.get("editorial_review") or {}).get("disposition") or {}).get("state") == "historical_page_unavailable": return "Past listing · page unavailable"
    if status == "program" and re.search("waitlist", route.get("availability_note") or "", re.I): return "Waitlist may apply"
    if status == "historical" and check.get("result") in ("official_role_not_found_redirect", "official_role_not_found"): return "Historical · listing unavailable"
    if status in WORK_STATUS: return WORK_STATUS[status]
    uncertain = (route.get("last_link_check") or {}).get("result") in ("blocked", "not_found", "unavailable") or ((route.get("research_record") or {}).get("route") or {}).get("live_application_verified") is False or UNCERTAIN_CHECK.search(" ".join(str(v) for v in (check.get("result"), check.get("note")) if v))
    return "Availability unconfirmed" if uncertain else ""


def work_approved_terms_receipt(route):
    """w4ApprovedTermsReceipt(): a retrieval receipt alone never refreshes terms."""
    review = route.get("editorial_review") or {}
    receipt = next((r for r in review.get("receipts") or [] if r.get("id") == review.get("approved_terms_receipt_id")), None)
    return receipt if receipt and receipt.get("approved") is True and receipt.get("scope") == "key_terms" and receipt.get("result") == "readable" and receipt.get("approval_basis") == "source_content_review" and ISO_DAY.fullmatch(str(receipt.get("checked_on") or "")) else None


def work_terms_review_date(route):
    return (work_approved_terms_receipt(route) or {}).get("checked_on") or route.get("terms_checked_on")


def work_terms_age(route, as_of):
    """A named listing's full-terms review age; retrieval/pay-only dates cannot reset it.

    The caller supplies the publication date explicitly. Static builds never read
    the clock, and the original review date is never rewritten by aging.
    """
    if not isinstance(as_of, str) or not as_of:
        raise ValueError("work terms age requires an explicit publication date")
    if len(as_of) == 10:
        day = date.fromisoformat(as_of)
    else:
        timestamp = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("publication timestamp must have an explicit timezone")
        day = timestamp.astimezone(timezone.utc).date()
    result = {"state": "not_applicable", "reviewed_on": None, "as_of": day.isoformat(), "age_days": None, "label": ""}
    if work_kind(route) != "named_listing" or not work_primary(route):
        return result
    receipt = work_approved_terms_receipt(route)
    reviewed = date.fromisoformat(receipt["checked_on"]) if receipt else None
    if reviewed is None or reviewed > day:
        return {**result, "state": "not_reviewed", "label": "Full terms review not recorded"}
    age = (day - reviewed).days
    return {**result, "state": "needs_recheck" if age >= 14 else "current", "reviewed_on": reviewed.isoformat(), "age_days": age,
            "label": "Needs recheck" if age >= 14 else ""}


def work_review_label(research, route, compact=False):
    label = work_freshness(route)
    age = work_terms_age(route, research.publication_as_of)
    if not age["label"]: return label
    as_of = format_date(age["as_of"])
    date_note = "" if compact and label.endswith(" " + as_of) else f" (as of {as_of})"
    return label + " · " + age["label"] + date_note


def work_freshness(route):
    """w4FreshnessLabel(): terms, pay-only review, blocked recheck, then page check."""
    receipt = work_approved_terms_receipt(route)
    if receipt: return "Terms checked " + format_date(receipt["checked_on"])
    pay = (route.get("field_reviews") or {}).get("pay") or {}
    if (pay.get("state") in {"sourced", "conflicting", "source_not_stated"}
            and pay.get("basis") in {"direct_source", "stored_evidence"}
            and ISO_DAY.fullmatch(str(pay.get("reviewed_on") or ""))):
        return "Pay terms reviewed " + format_date(pay["reviewed_on"])
    if route.get("terms_checked_on"): return "Pay terms reviewed " + format_date(route["terms_checked_on"])
    checks = [route.get("last_route_check") or {}, route.get("last_link_check") or {}]
    latest_check = max((check for check in checks if ISO_DAY.fullmatch(str(check.get("date") or ""))),
                       key=lambda check: check["date"], default={})
    failed = {"blocked", "not_found", "unavailable", "unreadable_shell", "error"}
    if latest_check.get("result") in failed:
        label = "Recheck blocked " if latest_check["result"] == "blocked" else "Recheck failed "
        return label + format_date(latest_check["date"])
    checked = max((d for d in (route.get("availability_checked_on"), (route.get("last_route_check") or {}).get("date")) if d), default="")
    if checked: return "Page checked " + format_date(checked)
    return ("Recorded " + format_date(route["reviewed_on"]) + " · " if route.get("reviewed_on") else "") + "Terms not rechecked"


def work_action(route, research):
    """w4Action(), including its source-bound exceptions."""
    status = route.get("status")
    labels = {"closed": "View source", "historical": "View source", "no_route": "View source", "paused": "View research", "contributions": "View research", "information": "Program details", "inquiry": "Contact page", "careers": "View career page", "program": "View program"}
    if status in labels: return labels[status]
    binding = {
        "rws_trainai.work.polaris-asr": ("rws_trainai", "intake_unverified", "https://app.tai.rws.com/opportunities", "rws_trainai.claim.oct15-work-polaris-asr", "rws_trainai.source.oct15-work-polaris-asr", "View opportunities"),
        "apto.work.harbest-experts": ("apto", "unverified", "https://expert.harbest.io/", "apto.claim.worker_opportunities-0", "apto.source.d_apt5", "View program"),
    }.get(route.get("id"))
    if binding:
        company, expected_status, url, claim_id, source_id, label = binding
        claim, source = research.claims.get(claim_id) or {}, research.sources.get(source_id) or {}
        if route.get("company_id") == company and status == expected_status and route.get("url") == url and claim.get("company_id") == company and claim.get("status") == "supported" and source_id in (claim.get("source_ids") or []) and source.get("company_id") == company and source.get("url") == url and source.get("source_type") == "company" and claim_id in (route.get("claim_ids") or []) and source_id in (route.get("source_ids") or []) and any(s.get("id") == source_id and s.get("url") == url for s in route.get("sources") or []): return label
    if status in ("unverified", "intake_unverified"):
        if route.get("id") == "scale_ai.work.remotasks" and route.get("url") == "https://www.remotasks.com/en/migration": return "Migration information"
        entry = (route.get("entry_point_research") or {}).get("entry") or {}
        if entry.get("url") == route.get("url") and entry.get("type") in ("expert community", "expert fellowship", "experts"): return "View program"
    return "View role"


def work_actions(route, research):
    """Keep the display action separate from the original recorded source."""
    review = route.get("editorial_review") or {}
    actions = review.get("actions")
    if actions is not None:
        bindings = {(s.get("id"), s.get("url")) for s in route.get("sources") or [] if s.get("id")}
        return [(a["url"], clean(a["label"])) for a in actions
                if (a.get("source_id"), a.get("url")) in bindings and is_web_url(a.get("url")) and clean(a.get("label"))]
    alternative, disposition = review.get("alternative_destination") or {}, review.get("disposition") or {}
    if alternative and disposition.get("state") == "historical_page_unavailable" and disposition.get("approval_basis") == "source_content_review" and alternative.get("source_id") in (disposition.get("source_ids") or []) and any(s.get("id") == alternative.get("source_id") and s.get("url") == alternative.get("url") for s in route.get("sources") or []):
        return [(alternative["url"], "Browse current company careers")]
    return [(route["url"], work_action(route, research))] if is_web_url(route.get("url")) else []


def work_destination(route, research):
    """Primary action used by the cards and parity checks."""
    return next(iter(work_actions(route, research)), (None, ""))


def work_checked(route, column=False):
    """w4Checked(): the latest link check, else the review date. In a 'Last check' column the verb is left out."""
    checked = max((d for d in (route.get("availability_checked_on"), (route.get("last_route_check") or {}).get("date")) if d), default="")
    if checked: return format_date(checked) if column else "Checked " + format_date(checked)
    if not route.get("reviewed_on"): return "Not checked" if column else ""
    return f"{format_date(route['reviewed_on'])} (review only)" if column else "Reviewed " + format_date(route["reviewed_on"])


def route_dates(route):
    return (route.get("reviewed_on"), route.get("availability_checked_on"), route.get("entry_point_reviewed_on"), (route.get("last_route_check") or {}).get("date"), work_terms_review_date(route), ((route.get("editorial_review") or {}).get("disposition") or {}).get("reviewed_on"))


def sort_routes(routes, names):
    """filteredWork() order: status, published numeric pay first, company, role."""
    return sorted(routes, key=lambda r: (WORK_ORDER.get(r.get("status"), 10), not r.get("numeric_pay"), locale_key(names.get(r.get("company_id"), "")), locale_key(r.get("role", "")), r.get("id", "")))

# ---------------------------------------------------------------------------
# Page shell

EXTERNAL_MASK = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 17 17 7M7 7h10v10'/%3E%3C/svg%3E\")"
STYLE = (
    ":root{--bg:#f8f8f4;--ink:#18231f;--muted:#59645d;--green:#285b46;--green-dark:#193f2f;--border:#d8ddd5;--mark:#7d8b80;--soft:#eef1ea;--gutter:48px;--content:1232px;--measure:760px;--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--serif:Georgia,'Times New Roman',serif}"
    "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--sans)}"
    "a{color:var(--green);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}a:focus-visible{outline:3px solid var(--green);outline-offset:3px}"
    ".sr-only,.skip:not(:focus){position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.skip:focus{position:absolute;left:var(--gutter);top:8px;z-index:9;padding:10px 14px;background:var(--bg)}"
    ".site-header{display:flex;align-items:center;justify-content:space-between;gap:32px;min-height:80px;padding:0 max(var(--gutter),calc((100% - var(--content))/2));border-bottom:1px solid var(--border)}"
    ".wordmark{display:flex;align-items:center;min-height:44px;color:var(--ink);text-decoration:none;font-size:19px;font-weight:600;letter-spacing:-.6px;line-height:1.2;white-space:nowrap}"
    ".wordmark small{display:block;margin-top:5px;font-size:14px;font-weight:400;letter-spacing:0;color:var(--muted)}"
    ".site-nav{display:flex;align-self:stretch;gap:28px}.site-nav a{display:flex;align-items:center;min-height:44px;padding:0;font-size:14px;color:var(--muted);text-decoration:none;border-bottom:2px solid transparent}"
    ".site-nav a:hover{color:var(--ink)}.site-nav a[aria-current]{color:var(--ink);border-bottom-color:var(--green)}.site-nav a:focus-visible{outline-offset:-3px}"
    "main,.site-footer{margin:0 max(var(--gutter),calc((100% - var(--content))/2))}main{padding:32px 0 8px}main>*{max-width:var(--measure)}main>.wide{max-width:none}"
    ".crumbs ol{display:flex;flex-wrap:wrap;gap:2px 8px;margin:0 0 32px;padding:0;list-style:none;font-size:14px;color:var(--muted)}.crumbs li+li::before{content:'/';margin-right:8px;color:var(--mark)}.crumbs a{color:var(--muted)}"
    ".eyebrow{margin:0 0 16px;font-size:14px;font-weight:500;letter-spacing:.8px;text-transform:uppercase;color:var(--muted)}"
    "h1{margin:0 0 20px;font:400 clamp(44px,5.4vw,64px)/1.06 var(--serif);letter-spacing:-2px;overflow-wrap:break-word}"
    "h2{margin:48px 0 16px;padding-top:24px;border-top:1px solid var(--border);font-size:24px;line-height:1.25;font-weight:600;letter-spacing:-.35px}h3{margin:28px 0 8px;font-size:17px;line-height:1.35}"
    "p{margin:0 0 14px}.lede{margin:0 0 24px;font-size:18px;line-height:1.5;color:var(--muted)}"
    ".actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px}"
    ".cta{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:10px 16px;border-radius:3px;background:var(--green);color:#fff;text-decoration:none;font-size:14px;font-weight:600}.cta:hover{background:var(--green-dark)}"
    ".cta svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}"
    ".muted,.sub{font-size:14px;color:var(--muted)}.sub{display:block;margin-top:4px;font-weight:400}"
    ".tag{display:inline-block;margin:2px 6px 0 0;padding:0;font-size:14px;font-weight:500;line-height:1.5;color:var(--muted);white-space:nowrap}"
    f".ext::after{{content:'';display:inline-block;width:.7em;height:.7em;margin-left:.25em;background:currentColor;-webkit-mask:{EXTERNAL_MASK} center/contain no-repeat;mask:{EXTERNAL_MASK} center/contain no-repeat}}"
    ".note{margin:24px 0;padding:16px 0 16px 20px;border-left:2px solid var(--green)}.note p:last-child{margin:0}"
    ".source-snapshot{margin:22px 0}.source-snapshot>summary{cursor:pointer;min-height:44px;padding:10px 0;color:var(--green);font-size:14px}.source-snapshot>p{font-size:14px;color:var(--muted)}.selected-archive{margin:18px 0;color:var(--muted);font-size:14px}.selected-archive>summary{cursor:pointer;min-height:44px;padding:10px 0}.selected-evidence{margin:24px 0;padding:20px 0;border-block:1px solid var(--border)}.selected-evidence h2{margin:0 0 12px;padding:0;border:0;font-size:16px}.selected-value{font-size:28px;line-height:1.25;letter-spacing:-.5px}.selected-evidence details{margin-top:10px;font-size:14px}.selected-evidence summary{cursor:pointer;min-height:44px;padding:10px 0;color:var(--green)}.selected-evidence details p{margin:8px 0}.index-list .selected-evidence{padding:14px 0;margin:8px 0 0}.index-list .selected-value{font-size:22px}"
    "dl.facts{display:grid;grid-template-columns:minmax(7.5rem,max-content) 1fr;gap:8px 24px;margin:0;font-size:15px}dl.facts dt{color:var(--muted)}dl.facts dd{margin:0;overflow-wrap:anywhere}"
    "table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px 16px 10px 0;border-bottom:1px solid var(--border);text-align:left;vertical-align:top;overflow-wrap:anywhere}"
    "thead th{font-size:14px;font-weight:500;color:var(--muted);white-space:nowrap;overflow-wrap:normal}tbody th{font-weight:600}td.value{font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}"
    "table.figures{max-width:980px}td.date{min-width:6.5em}table.risks tbody th{font-weight:400}@media(min-width:701px){table.events td:last-child a{white-space:nowrap}}"
    "ul{padding-left:20px}li{margin:6px 0;overflow-wrap:anywhere}ul.plain,ul.index-list,ul.inline-list,ul.chips,ul.listings{list-style:none;padding:0}"
    "ul.index-list{margin:16px 0 0;border-top:1px solid var(--border)}ul.index-list li{margin:0;padding:14px 0;border-bottom:1px solid var(--border)}"
    "ul.index-list li>a{font-size:18px;font-weight:600;letter-spacing:-.3px;color:var(--ink);text-decoration:none}ul.index-list li>a:hover{text-decoration:underline}"
    "ul.listings li{margin:0;padding:10px 0;border-bottom:1px solid var(--border)}ul.inline-list{display:flex;flex-wrap:wrap;gap:6px 20px}ul.inline-list li{margin:0}"
    ".work-terms{margin:4px 0;font-size:14px;font-weight:400}.work-terms>summary{min-height:44px;padding:10px 0;color:var(--green);cursor:pointer}.work-terms p{margin:8px 0}.work-terms ul{margin:8px 0;padding-left:20px}.work-terms li,ul.listings .work-terms li{padding:4px 0;border:0}.work-terms blockquote{margin:12px 0;padding-left:12px;border-left:2px solid var(--border)}td[data-label=Action]>a,.work-action>a{display:inline-flex;align-items:center;min-height:44px}.work-action{margin:4px 0}"
    "ul.chips{display:flex;flex-wrap:wrap;gap:8px 24px;margin:20px 0}ul.chips li{margin:0}ul.chips a{display:inline-flex;align-items:center;min-height:44px;font-size:14px;text-decoration:none}ul.chips a:hover{text-decoration:underline}"
    "dl.grades{margin:16px 0 0}dl.grades div{display:grid;grid-template-columns:28px minmax(0,1fr);gap:16px;align-items:baseline;padding:12px 0;border-top:1px solid var(--border)}"
    "dl.grades dt{display:grid;place-items:center;width:28px;height:28px;border:1px solid var(--mark);font:19px/1 var(--serif);color:var(--green)}dl.grades dd{margin:0;color:var(--muted)}"
    ".site-footer{margin-top:80px;padding:28px 0 40px;border-top:1px solid var(--border);font-size:14px;color:var(--muted)}"
    ".site-footer nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px 32px;max-width:var(--measure);margin-bottom:20px}"
    ".site-footer>p{max-width:var(--measure)}.site-footer h2{margin:0 0 6px;padding:0;border:0;font-size:14px;font-weight:500;color:var(--ink)}.site-footer ul{margin:0;padding:0;list-style:none}.site-footer li{margin:0}.site-footer li a{display:inline-flex;align-items:center;min-height:44px;color:var(--muted);text-decoration:none}.site-footer li a:hover{color:var(--green);text-decoration:underline}"
    "@media(max-width:1100px){:root{--gutter:32px}.site-header{gap:24px}.site-nav{gap:22px}}"
    "@media(max-width:700px){:root{--gutter:20px}"
    "h1{font-size:42px;line-height:1.08;letter-spacing:-1.2px}.lede{font-size:17px}h2{margin-top:40px;font-size:22px}dl.facts{grid-template-columns:7rem 1fr;gap:6px 16px;font-size:14px}"
    "thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}table,tbody,th,td{display:block}"
    "tbody tr{display:flex;flex-wrap:wrap;column-gap:18px;padding:12px 0;border-bottom:1px solid var(--border)}th,td{padding:0;border:0}td{margin-top:4px}td.value{white-space:normal}tbody th,td.wide-cell{flex-basis:100%}"
    "td[data-label]::before{content:attr(data-label) ': ';content:attr(data-label) ': ' / '';font-size:14px;font-weight:400;color:var(--muted)}"
    ".site-footer nav{grid-template-columns:1fr 1fr}.site-footer li{margin:0}.site-footer li a{display:inline-flex;align-items:center;min-height:44px}}"
    "@media(max-width:380px){:root{--gutter:16px}h1{font-size:38px}}"
    "@media(forced-colors:active){.ext::after{background:LinkText}}"
)
RIGHT_ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12h16m-7-7 7 7-7 7"/></svg>'
NAV = (("daily", "Daily scan", "/daily/"), ("research", "Research", "/research/"), ("companies", "Companies", "/companies/"), ("work", "Paid work", "/work/"), ("about", "About", "/method/#about"))


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
    nav = f'<nav class="site-nav" aria-label="Main">{links}</nav>'
    return ('<a class="skip" href="#main">Skip to content</a>\n'
            f'<header class="site-header"><a class="wordmark" href="{ORIGIN}/"><span>{SITE_NAME}<small>The AI data field guide</small></span></a>'
            f'{nav}<a class="site-search-open" href="/?search=#browse-guide" aria-label="Search the guide"><svg class="ui-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true" focusable="false"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><span class="site-search-label">Search</span></a>'
            f'<details class="site-menu"><summary>Menu</summary>{nav}</details></header>\n')


def disclosure_html():
    return escape(DISCLOSURE).replace("overview page", f'<a href="{ORIGIN}/explore/#venture">overview page</a>', 1)


def site_footer(research, note=""):
    """Keep research release context separate from the historical company snapshot."""
    links = (("About", "/method/#about"), ("Historical company data", "/method/#downloads"),
             ("Research data", "/research/data/"),
             ("Corrections", "/method/#corrections"), ("Disclosures", "/method/#disclosures"))
    nav = "".join(f'<a href="{ORIGIN}{path}">{label}</a>' for label, path in links)
    data = research.data
    version, snapshot = data.get("dataset_version"), data.get("meta", {}).get("as_of")
    release = getattr(research, "research_release_context", None) or {}
    parts = []
    if release.get("release_id"):
        parts.append("Research release " + str(release["release_id"]))
    if release.get("evidence_as_of"):
        parts.append("Evidence as of " + format_date(release["evidence_as_of"]))
    if version:
        parts.append("Historical company dataset v" + str(version))
        if snapshot:
            parts.append("Snapshot " + format_date(snapshot))
    line = " · ".join(parts)
    return (f'<footer class="site-footer"><div class="footer-line"><p>{SITE_NAME} <span>by {PUBLISHER_NAME}</span></p>'
            f'<nav aria-label="Site map">{nav}</nav></div>'
            + (f'<p class="site-footer-meta">{escape(line)}</p>' if line else "")
            + (f'<details class="footer-note"><summary>Credits</summary>{note}</details>' if note else "") + "</footer>\n")


def crumb_nav(crumbs, css_class=""):
    items = []
    for name, url in crumbs[:-1]:
        path = urlsplit(url).path
        parent = ' class="crumb-parent"' if css_class == "company-crumbs" and path in ("/companies/", "/research/") and not urlsplit(url).fragment else ""
        items.append(f'<li{parent}><a href="{escape(url)}">{escape(name)}</a></li>')
    items.append(f'<li><span aria-current="page">{escape(crumbs[-1][0])}</span></li>')
    return f'<nav class="{escape(("crumbs " + css_class).strip())}" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>\n'


def breadcrumb_list(crumbs):
    return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": name, "item": url} for i, (name, url) in enumerate(crumbs)]}


def page_node(page_type, title, description, canonical, modified, crumbs, **extra):
    node = {"@context": "https://schema.org", "@type": page_type, "@id": canonical, "url": canonical, "name": title, "description": description, "inLanguage": "en", "isPartOf": WEBSITE, "publisher": PUBLISHER, "dateModified": modified, "breadcrumb": breadcrumb_list(crumbs)}
    node.update(extra)
    return node


def document(research, title, description, canonical, body, structured=None, current=None, state="page", robots="", note="", work_script=None):
    """One static page: its head tags, the site header, the body and the footer."""
    head = ['<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="color-scheme" content="light">\n',
            f"<title>{escape(title)}</title>\n<meta name=\"description\" content=\"{escape(description)}\">\n"]
    if robots: head.append(f'<meta name="robots" content="{escape(robots)}">\n')
    if canonical: head.append(f'<link rel="canonical" href="{escape(canonical)}">\n')
    if canonical == ORIGIN + '/companies/':
        head.append('<script>document.documentElement.setAttribute("data-page-enhancement","pending");addEventListener("error",function(event){if(event.error||event.target.hasAttribute&&event.target.hasAttribute("data-page-enhancement-script"))document.documentElement.removeAttribute("data-page-enhancement")},true)</script>\n')
    if work_script is not None:
        loader = (ROOT / "web/work-page-loader.js").read_text(encoding="utf-8")
        head.append(f'<script data-work-script="{escape(work_script["href"])}" '
                    f'data-work-integrity="{escape(work_script["integrity"])}">{loader}</script>\n')
    head.append(ICON_LINKS)
    if canonical:
        head.append(f'<meta property="og:type" content="website">\n<meta property="og:title" content="{escape(title)}">\n<meta property="og:description" content="{escape(description)}">\n<meta property="og:url" content="{escape(canonical)}">\n<meta property="og:site_name" content="{SITE_NAME}">\n<meta property="og:locale" content="en_US">\n'
                    f'<meta property="og:image" content="{SHARE_IMAGE}">\n<meta property="og:image:type" content="image/png">\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n<meta property="og:image:alt" content="{escape(SHARE_ALT)}">\n'
                    f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{escape(title)}">\n<meta name="twitter:description" content="{escape(description)}">\n<meta name="twitter:image:alt" content="{escape(SHARE_ALT)}">\n')
    head.append('<link rel="stylesheet" href="/static-pages.css">\n<link rel="stylesheet" href="/field-guide.css">\n<link rel="stylesheet" href="/page-layout.css">\n')
    if structured: head.append(f'<script type="application/ld+json">{json_ld(structured)}</script>\n')
    details_script = '<script src="/native-details.js" defer></script>\n' if re.search(r'class="[^"]*\b(?:company-dossier|method-page)\b', body) else ""
    return "".join(head) + "</head>\n<body class=\"static-page\">\n" + site_header(current, state) + '<main id="main">\n' + body + "</main>\n" + site_footer(research, note) + details_script + '</body>\n</html>\n'

# ---------------------------------------------------------------------------
# Company pages

def figure_row(research, metric, context=None):
    context = context or {}
    details = [figure_note(research, metric), figure_scope(research, metric, context), basis_text(research, metric)]
    label = context.get("display_label") or figure_label(research, metric)
    notes = [research.correction(metric, "display_attribution"), clean(context.get("note"))]
    head = f'<th scope="row">{escape(label)}<span class="sub">{escape(" · ".join(d for d in details if d))}</span>' + "".join(f'<span class="sub">{escape(note)}</span>' for note in notes if note and note != "Undated company claim") + "</th>"
    assurance = context.get("assurance") or ("Third-party estimate" if context.get("estimated") else "Estimate" if metric.get("reported_vs_estimated") == "estimated" else "")
    value = f'<td class="value" data-label="Value">{escape(value_text(metric))}' + (f' <span class="tag">{escape(assurance)}</span>' if assurance else "") + "</td>"
    when = context.get("date") or metric_period(research, metric)
    period = f'<td data-label="Date">{escape("Not stated" if when == "Date not stated" else when)}' + (' <span class="tag">Historical</span>' if research.historical_year(metric) else "") + "</td>"
    citations = source_html(research, metric, evidence=context.get("citation_evidence"), checks=context.get("source_checks"))
    fact = context.get("finance_fact")
    original, _ = latest_source(research, metric)
    if fact and fact.get("source_id") != (original or {}).get("id"):
        origin = external_link(fact["source_url"], fact["source_title"])
        citations += f'<span class="sub">{escape(fact["claimant"])} · {origin}</span>'
    if supplemental := context.get("supplemental_source"):
        link = external_link(supplemental["url"], supplemental["title"])
        citations = f'<span class="sub" data-source-id="{escape(supplemental["id"])}">{link}</span>' + citations
    confidence = context.get("confidence_reason")
    grade = escape(research.grade(metric) or "Not graded") + (f'<span class="sub">{escape(confidence)}</span>' if confidence else "")
    return f'<tr id="metric-{escape(metric["id"])}" data-metric="{escape(metric["id"])}">{head}{value}{period}<td data-label="Grade">{grade}</td><td class="wide-cell" data-label="Source">{citations}</td></tr>'


SOURCE_CHECKS = {"checked": "Checked {}", "summary_only": "Summary only, page not reviewed · recorded {}", "unverified": "Not checked again · recorded {}"}


def source_record_status(source):
    read = source.get("accessed_on")
    return SOURCE_CHECKS.get(source.get("retrieval_status"), "Recorded {}").format(format_date(read)) if ISO_DAY.fullmatch(str(read or "")) else ""


def source_meta(research, source, check=None):
    """Publisher, publication date and when we read the page, in the words of profileSourceMeta() in web/profiles-v2.js."""
    published = source.get("published_on") if ISO_DAY.fullmatch(str(source.get("published_on") or "")) else research.reviewed_source_dates.get(source["id"])
    status = ""
    if check and check.get("status") == "unavailable":
        http = f' (HTTP {check["http_status"]})' if check.get("http_status") else ""
        status = f'Recheck unavailable {format_date(check.get("checked_on"))}{http}'
    return " · ".join(part for part in (clean(source.get("publisher")), f"Published {format_date(published)}" if published else "", source_record_status(source), status) if part)


def company_source_link(research, source, show_availability=True):
    label = shown_text(research, source.get("title")) or clean(source.get("publisher")) or "Source"
    url = source.get("url")
    return external_link(url, label) + (availability(url, research.health) if show_availability else "")


def company_citations(research, claim, primary_id, sources=None, checks=None):
    """Expose the exact supporting records in claim order, even at a shared URL."""
    if sources is None:
        sources = [research.sources[sid] for sid in claim.get("source_ids", []) if sid != primary_id and sid in research.sources]
    if not sources:
        return ""
    lines = []
    for source in sources:
        meta = source_meta(research, source, (checks or {}).get(source["id"]))
        lines.append(f'<li data-source-id="{escape(source["id"])}">{company_source_link(research, source)}'
                     + (f'<span class="sub">{escape(meta)}</span>' if meta else "") + '</li>')
    return (f'<details class="company-citations" data-citations-for="{escape(claim["id"])}">'
            f'<summary>{plural(len(lines), "more source")}</summary><ul>{"".join(lines)}</ul></details>')


def source_html(research, metric, inline=False, evidence=None, checks=None):
    """A primary source and the other records cited by the same claim."""
    source, rest = (evidence[0], evidence[1:]) if evidence else (latest_source(research, metric)[0], None)
    if not source: return '<span class="muted">No source recorded.</span>' if inline else '<span class="sub">No source recorded</span>'
    meta = source_meta(research, source, (checks or {}).get(source["id"]))
    link = company_source_link(research, source)
    rest = company_citations(research, research.claim(metric), source["id"], rest, checks)
    if inline: return "Source: " + link + (f' <span class="muted">({escape(meta)})</span>' if meta else "") + rest
    if evidence: link = f'<span data-source-id="{escape(source["id"])}">{link}</span>'
    return link + (f'<span class="sub">{escape(meta)}</span>' if meta else "") + rest


def pending_item(research, m):
    old = ' <span class="tag">Historical</span>' if research.historical_year(m) else ""
    return f'<li data-metric="{escape(m["id"])}"><strong>{escape(figure_label(research, m))}: {escape(value_text(m))}</strong>{old} · {escape(metric_period(research, m))} · {escape(figure_scope(research, m))}. {escape(status_words(research, m))} {source_html(research, m, inline=True)}</li>'


def figures_html(research, company, figures, pending, others, profile_entry, finance=None, health=None):
    contexts = dict((profile_entry or {}).get("metric_context") or {})
    finance = finance or {}
    archived = finance.get("archived_record")
    if archived and finance.get("archived_record_context"):
        context = contexts.get(archived) or {}
        contexts[archived] = {**context, "note": clean(" ".join(filter(None, (context.get("note"), finance["archived_record_context"]))))}
    updated = [finance.get("headline"), *(finance.get("native_detail_records") or [])]
    figure_ids = {metric["id"] for metric in figures}
    for fact in filter(None, updated):
        rid = fact["record_id"]
        if rid in figure_ids:
            contexts[rid] = {**(contexts.get(rid) or {}), "date": fact["display_date"], "scope": fact["scope"],
                             "display_label": fact["label"], "finance_fact": fact}
    sources = {source["id"]: source for source in (health or {}).get("sources", [])}
    observations = {row["id"]: row for row in (health or {}).get("observations", [])}
    checks = {row["source_id"]: row for row in (health or {}).get("source_checks", {}).get("entries", [])}
    calculated = {}
    for observation in observations.values():
        profile_metric = observation.get("profile_metric_id")
        if profile_metric in figure_ids:
            calculated[profile_metric] = observation
            inputs = [observations[rid] for rid in observation["calculation"]["input_observation_ids"]]
            amounts = " and ".join(f'{value_text(row)} in {row["period"]["label"]}' for row in inputs)
            contexts[profile_metric] = {**(contexts.get(profile_metric) or {}), "scope": observation["scope_detail"],
                "assurance": "Calculated", "note": f"Calculated from rounded revenue of {amounts}.",
                "confidence_reason": observation["profile_confidence_reason"],
                "citation_evidence": [sources[sid] for sid in observation_source_ids(observation)],
                "source_checks": checks}
        rid = observation.get("id")
        if rid not in figure_ids or observation.get("metric_ids") != [rid]:
            continue
        if observation.get("evidence_type") == "estimate":
            contexts[rid] = {**(contexts.get(rid) or {}), "display_label": observation["label"], "estimated": True}
        if observation.get("historical_source_ids"):
            contexts[rid] = {**(contexts.get(rid) or {}),
                "citation_evidence": [sources[sid] if sid in sources else research.sources[sid] for sid in observation_source_ids(observation)],
                "source_checks": checks}
        elif supplemental := sources.get(observation.get("primary_source_id")):
            contexts[rid] = {**(contexts.get(rid) or {}), "supplemental_source": supplemental, "note": observation["limitations"]}
    if figures:
        shown = [{**m, "value": round(calculated[m["id"]]["value"], 1), "qualifier": "approximate"}
                 if m["id"] in calculated else m for m in figures]
        rows = "".join(figure_row(research, m, contexts.get(m["id"])) for m in shown)
        body = f'<table class="figures wide"><thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Date</th><th scope="col">Grade</th><th scope="col">Source</th></tr></thead><tbody>{rows}</tbody></table>\n'
        for observation in calculated.values():
            body += f'<p class="muted">{escape(observation["basis"])}</p>\n'
    else:
        body = f'<p>{"Commercial revenue does not apply to this research organization." if company.get("entity_type") == "adjacent_research" else "No reported figure meets the source requirements."}</p>\n'
    if pending:
        body += f'<h3 id="unconfirmed">Not confirmed</h3>\n<p class="muted">Unverified or disputed figures. Excluded from headline facts.</p>\n<ul class="listings">{"".join(pending_item(research, m) for m in pending)}</ul>\n'
    if others:
        body += f'<h3 id="other-figures">Other reported figures</h3>\n<p class="muted">Forecasts, targets, and earlier or partial figures.</p>\n<ul class="listings">{"".join(pending_item(research, m) for m in others)}</ul>\n'
    if figures or pending or others:
        annualized = "Annualized pace projects recent revenue over a year. " if any(m.get("kind") == "annualized_revenue_run_rate" for m in figures + pending + others) else ""
        body += f'<p class="muted">{annualized}Grades measure source confidence. <a href="{ORIGIN}/method/#grades">How we grade</a>.</p>\n'
    return '<h2 id="figures">Key figures</h2>\n' + body


def labelled(label, value):
    """'Pay: $60 / hour', but 'Pay not listed' and 'Location not listed' as they are, since they already name the field."""
    return value if value.lower().startswith(label.lower()) else f"{label}: {value}"


def work_requirements(route):
    """Requirements in source order, without repeating an assessment already listed."""
    requirements = list(dict.fromkeys(clean(v) for v in route.get("requirements") or [] if clean(v)))
    assessment = clean(route.get("assessment"))
    if assessment and not any(assessment.casefold() in v.casefold() for v in requirements): requirements.append(assessment)
    return requirements


def work_conditions(route, requirements=None, *, include_kind=True):
    """Show the source terms before the destination on both plain surfaces."""
    if requirements is None: requirements = work_requirements(route)
    hours_record = ((route.get("research_record") or {}).get("route") or {}).get("hours") or {}
    hours_detail = hours_record.get("detail") if isinstance(hours_record, dict) else None
    field_reviews = route.get("field_reviews") or {}
    commitment_review = field_reviews.get("commitment") or {}
    conflict = commitment_review.get("state") == "conflicting" and commitment_review.get("note")
    hours = [f"Schedule conflict. {clean(conflict)}"] if conflict else [route.get("hours"), hours_detail]
    commitment = list(dict.fromkeys(clean(v) for v in (*hours, route.get("duration")) if clean(v)))
    classification = WORK_ENGAGEMENT_LABELS[work_engagement(route)]
    if include_kind:
        classification = f"{WORK_KIND_LABELS[work_kind(route)]} · {classification}"
    parts = [f'<span class="sub">{escape(classification)}</span>']
    if commitment: parts.append('<span class="sub">' + escape(" · ".join(commitment)) + '</span>')
    if requirements:
        parts.append('<span class="sub">' + escape(" · ".join(requirements)) + '</span>')
    for field, review in field_reviews.items():
        if field == "commitment" and conflict: continue
        if field in WORK_FIELD_LABELS and review.get("state") == "conflicting":
            parts.append('<span class="sub">' + escape(WORK_FIELD_LABELS[field] + " sources conflict." + (" " + clean(review["note"]) if review.get("note") else "")) + '</span>')
    return "".join(parts)


def work_pay_qualification(route):
    """Conditions on a one-time award belong next to the amount."""
    terms = route.get("pay_terms") or {}
    return clean(terms.get("note")) if terms.get("unit") == "one_time" else ""


def work_pay_notes(route):
    split = SALARY_SPLIT.match(clean(route.get("pay_label"))) if route.get("pay_basis") == "salary_period_unspecified" else None
    notes = [clean(route.get("pay_indicator"))]
    if split: notes.append(f"Equity offered. Separate bonus band: {split.group(2)}.")
    elif route.get("pay_observations"): notes.extend(clean(p.get("value")) + " " + clean(p.get("label")) for p in route["pay_observations"])
    else:
        notes.append({"per_completed_task": "Paid per completed task", "hour_equivalent": "Hourly equivalent", "approved_deliverables": "Approved deliverables · advertised range", "hour_or_accepted_task": "Hourly or accepted tasks; rejected tasks may be unpaid", "month_stipend": "Monthly stipend", "approved_recording": "Payment requires approval", "approved_submission": "Payment requires approval", "accepted_project": "Payment requires acceptance", "accepted_task": "Payment requires acceptance"}.get(route.get("pay_basis"), ""))
    if route.get("pay_basis") == "advertised_maximum_hourly": notes.append("Rates vary by expertise, assessment, location and project. Non-core work can pay less.")
    if str(route.get("pay_basis") or "").endswith("salary_period_unspecified"): notes.append("Pay period not stated." + (" Bonus terms not stated." if re.search("Bonus eligibility and payout terms are undisclosed", route.get("availability_note") or "", re.I) else ""))
    notes.append(work_pay_qualification(route))
    return '<span class="sub">' + escape(" · ".join(dict.fromkeys(n for n in notes if n))) + '</span>' if any(notes) else ""


WORK_SOURCE_PURPOSES = {
    "retrieval": "URL checked", "key_terms": "Key terms reviewed", "terms": "Terms source",
    "field_review": "Specific fields reviewed", "destination": "Destination checked", "application": "Application checked",
    "historical_observation": "Historical observation", "official_board": "Official careers board", "description": "Description",
    "network": "Program page", "registration": "Registration",
}


def work_action_name(label, route, employer):
    return f"{label} for {clean(route.get('role')) or 'Listing'}, {employer}"


def work_source_lines(research, route, employer, detailed, primary_action_url=None):
    """One URL per list item with every distinct observation and field binding."""
    fields, earlier_fields, receipts, grouped, prior_quotes = {}, {}, {}, {}, {}
    review = route.get("editorial_review") or {}
    for field, label in WORK_FIELD_LABELS.items():
        for source_id in ((route.get("field_reviews") or {}).get(field) or {}).get("source_ids", []):
            fields.setdefault(source_id, []).append(label.lower())
        for correction in review.get("correction_history", []):
            values = correction.get("previous_values") or {}
            previous = (values.get("field_reviews") or {}).get(field) or {}
            for source_id in previous.get("source_ids", []):
                if label.lower() not in fields.get(source_id, []):
                    earlier_fields.setdefault(source_id, []).append(label.lower())
                if field == "pay" and values.get("source_quote") and values["source_quote"] != route.get("source_quote"):
                    prior_quotes.setdefault(source_id, []).append(values["source_quote"])
    for receipt in review.get("receipts") or []:
        receipts.setdefault(receipt.get("source_id"), []).append(receipt)
    for source in route.get("sources") or []:
        if is_web_url(source.get("url")):
            grouped.setdefault(source["url"], []).append(source)
    recorded_quote = route.get("source_quote")
    record_quote_html = f'<blockquote>{escape(recorded_quote)}</blockquote>' if recorded_quote else ""
    quote_url = route.get("url")
    pay_sources = ((route.get("field_reviews") or {}).get("pay") or {}).get("source_ids", [])
    quote_source = pay_sources[0] if len(pay_sources) == 1 and re.search(r"[$£€]\s*\d", recorded_quote or "") else None
    last_check = route.get("last_route_check") or {}
    checks = [last_check["application_check"]] if last_check.get("application_check") else []
    checks.extend(last_check.get("application_checks") or [])
    applications = {}
    for check in checks:
        if is_web_url(check.get("url")):
            applications.setdefault(check["url"], []).append(check)
    secondary = dict(work_actions(route, research)[1:])
    separate_evidence_link = any(
        action.get("purpose") == "archived_listing"
        or (action.get("purpose") == "application" and action.get("url") == primary_action_url)
        for action in review.get("actions") or []
    )
    for url in (*applications, *secondary):
        grouped.setdefault(url, [])
    lines = []
    for url, sources in grouped.items():
        first = sources[0] if sources else {}
        label = secondary.get(url) or clean(first.get("title") or first.get("publisher")) or ("Application checked" if url in applications else "Source")
        if primary_action_url and first.get("purpose") == "terms" and url not in secondary and route.get("role"):
            # The surrounding card already identifies the role.
            label = label.removesuffix(" · " + clean(route["role"])) or label
        repeats_action = url == primary_action_url and url not in secondary and not separate_evidence_link
        # The card already links to this page. Keep the exact application and
        # links that compare current and archived destinations in the disclosure.
        link = escape(label) if repeats_action else external_link(url, label, work_action_name(label, route, employer) if url in secondary else "")
        observations = []
        link_check = research.health.get(health_key(url)) if not repeats_action else None
        if link_check:
            checked = link_check["checked_on"]
            code = {"not_found": 404, "gone": 410}.get(link_check["status"])
            displayed = code and any(
                record.get("checked_on") == checked and record.get("http_status") == code
                for source in sources for record in receipts.get(source.get("id"), [])
            )
            if not displayed:
                status = LINK_STATES[link_check["status"]].removeprefix("page ").capitalize()
                observations.append(f'<small>{escape(status)} {escape(format_date(checked))}</small>')
        for index, source in enumerate(sources):
            sid = source.get("id")
            published = next((source[k] for k in ("published_on", "source_publication_date", "published_at") if source.get(k) and source[k] != "undated"), None)
            published = published or (research.sources.get(sid) or {}).get("published_on")
            title = clean(source.get("title"))
            recorded = format_date(source.get("accessed_on"))
            short_title = re.sub(r"([A-Z][a-z]{2})[a-z]+(?= \d{4}$)", r"\1", title)
            check_title = bool(recorded) and short_title == "Official listing checked " + recorded
            details = [title] if index and (detailed or not source.get("purpose") and not check_title and title != label) else []
            if detailed and source.get("publisher"): details.append(clean(source["publisher"]))
            if published and published != "undated": details.append("Published " + format_date(published))
            purpose = source.get("purpose")
            if not index and url == route.get("url"):
                purpose = purpose or review.get("recorded_url_purpose")
            entry_receipts = receipts.get(sid, [])
            terms_review = primary_action_url and purpose == "terms" and sid in fields and recorded and any(
                check.get("scope") == "field_review" and check.get("checked_on") == source.get("accessed_on")
                for check in entry_receipts
            )
            repeats_description = repeats_action and not index and purpose == "description" and label.lower().endswith("description")
            if purpose and not terms_review and not repeats_description:
                details.append(WORK_SOURCE_PURPOSES.get(purpose) or readable(purpose))
            if recorded:
                verb = "URL checked" if any(r.get("scope") == "retrieval" for r in entry_receipts) else "Recorded"
                if not detailed and index and check_title: verb = "Listing checked"
                details.append(verb + " " + recorded)
            if sid in fields: details.append(("Terms fields reviewed: " if terms_review else "Source for ") + ", ".join(fields[sid]))
            if sid in earlier_fields: details.append("Earlier source for " + ", ".join(dict.fromkeys(earlier_fields[sid])))
            for check in entry_receipts:
                reviewed = check.get("checked_on")
                scope = check.get("scope")
                # The source date and exact fields already describe this same terms review.
                repeated_scope = terms_review and scope == "field_review" and reviewed == source.get("accessed_on")
                summary = ["" if repeated_scope else WORK_SOURCE_PURPOSES.get(scope) or readable(scope),
                           format_date(reviewed) if reviewed and reviewed != source.get("accessed_on") else "",
                           f'HTTP {check["http_status"]}' if check.get("http_status") else "",
                           readable(check.get("result")) if check.get("result") != "readable" else "",
                           clean(check.get("note") or check.get("limits")) if detailed else ""]
                details.extend(p for p in summary if p and not any(d.startswith(p) for d in details if d))
            if details:
                attribute = f' data-field-source="{escape(sid)}"' if (sid in fields or sid in earlier_fields) and index < len(sources) - 1 else f' data-work-source="{escape(sid)}"' if detailed else ""
                observations.append(f'<small{attribute}>{escape(" · ".join(dict.fromkeys(p for p in details if p)))}</small>')
            if record_quote_html and sid and sid == quote_source:
                observations.append(record_quote_html)
                record_quote_html = ""
            excerpts = [f'Earlier excerpt · <q>{escape(quote)}</q>' for quote in dict.fromkeys(prior_quotes.get(sid, []))]
            for receipt in entry_receipts:
                for evidence in receipt.get("evidence") or []:
                    if not isinstance(evidence, dict) or not evidence.get("quote"): continue
                    field_label = WORK_FIELD_LABELS.get(evidence.get("field"))
                    checked = receipt.get("checked_on")
                    context = " · ".join(part for part in (field_label, format_date(checked) if checked != source.get("accessed_on") else "") if part)
                    excerpts.append((escape(context) + " · " if context else "") + f'<q>{escape(evidence["quote"])}</q>')
            observations.extend(f'<small>{excerpt}</small>' for excerpt in dict.fromkeys(excerpts))
        for check in applications.get(url, []):
            if not detailed and check.get("result") == "readable" and sources:
                continue
            observation = " · ".join(p for p in (format_date(check.get("date") or check.get("checked_on")),
                                                   f'HTTP {check["http_status"]}' if check.get("http_status") else "",
                                                   readable(check.get("result")), clean(check.get("note")) if detailed else "") if p)
            observations.append(f'<small>Application check · {escape(observation)}</small>')
        if record_quote_html and not quote_source and url == quote_url:
            observations.append(record_quote_html)
            record_quote_html = ""
        # Each next item (or the end of the list) closes the item.
        lines.append(f'<li>{link}{"".join(observations)}')
    return record_quote_html + ("<ul>" + "".join(lines) + "</ul>" if lines else "")


def work_terms_html(research, route, employer, detailed=True, more_requirements=(), primary_action_url=None):
    """One native source disclosure; a replaced original URL remains in its history."""
    label = "More requirements, terms &amp; sources" if more_requirements else "Terms &amp; sources"
    parts = [f'<details class="work-terms"><summary>{label}</summary>']
    # The next block or closing disclosure ends a paragraph. Each list item
    # ends at the next item or at the end of its list.
    if more_requirements:
        parts.append('<ul aria-label="Additional requirements">' + ''.join(f'<li>{escape(term)}' for term in more_requirements) + '</ul>')
    if detailed and route.get("summary"): parts.append('<p>' + escape(clean(route["summary"])))
    availability_note = clean(route.get("availability_note"))
    if not detailed:
        availability_note = {
            "Listed on the employer’s board. Selection and application acceptance are decided by the employer.": "",
            "This is an official route directory or program entry point. Specific openings, pay, hours and individual eligibility require checking the linked destination.": "Check the linked page for individual opportunities.",
            "Official listing and compensation header reviewed 28 October 2026. No application submitted; selection and work availability remain employer decisions.": "Listing and compensation header reviewed 28 Oct 2026.",
        }.get(availability_note, availability_note)
    if availability_note: parts.append(f'<p>{escape(availability_note)}')
    pay_note = clean((route.get("pay_terms") or {}).get("note"))
    repeats_salary_unit = primary_action_url and any(
        pay_note == f"The employer lists this component as {period} salary." and work_pay(route).endswith(f" {period} salary")
        for period in ("monthly", "annual")
    )
    if pay_note and not repeats_salary_unit and pay_note != work_pay_qualification(route) and pay_note not in availability_note:
        parts.append(f'<p>{escape(pay_note)}')
    reviews = {}
    source_dates = {source.get("id"): source.get("accessed_on") for source in route.get("sources") or [] if is_web_url(source.get("url"))}
    for field, review in (route.get("field_reviews") or {}).items():
        if field not in WORK_FIELD_LABELS or review.get("state") not in WORK_FIELD_STATES: continue
        reviewed_on, state = review.get("reviewed_on"), review["state"]
        if not detailed and state not in ("conflicting", "source_not_stated"):
            # The source list already pairs this date and field with the exact link.
            if not reviewed_on or (state == "sourced" and any(source_dates.get(sid) == reviewed_on for sid in review.get("source_ids", []))):
                continue
        label = WORK_FIELD_LABELS[field]
        text = WORK_FIELD_STATES[state]
        if reviewed_on:
            date_label = "Reviewed " + format_date(reviewed_on)
            text = date_label if not detailed and state == "sourced" else date_label + " · " + text
        note = clean(review.get("note"))
        if detailed and note and note not in (availability_note, pay_note) and state != "conflicting":
            text += ". " + note
        reviews.setdefault(text, []).append(label.lower())
    if reviews:
        parts.append('<ul>' + "".join(f'<li>{escape(f"{text} ({join_words(labels)})")}' for text, labels in reviews.items()) + '</ul>')
    if route.get("as_of") and (detailed or route["as_of"] != "undated"):
        parts.append('<p>Terms recorded · ' + escape(format_date(route["as_of"]) if route["as_of"] != "undated" else "date not stated"))
    parts.append(work_source_lines(research, route, employer, detailed, primary_action_url))
    disposition = (route.get("editorial_review") or {}).get("disposition") or {}
    if detailed and disposition.get("note"): parts.append('<p>' + escape(clean(disposition["note"])))
    parts.append('</details>')
    return "".join(parts)


def work_item(research, route, employer, compact=False):
    """One source-backed route; critical conditions and review scope precede its action."""
    status, bucket = work_status(route), work_display_bucket(route)
    place = work_location(route)
    pay = work_pay(route)
    show_pay = bucket != "boards" and (bucket != "closed" or pay != "Pay not listed")
    offer = (f"Historical pay · {pay}" if bucket == "closed" else labelled("Pay", pay)) if show_pay else ""
    pay_notes = work_pay_notes(route) if show_pay else ""
    qualified_offer = ""
    if offer and work_pay_qualification(route):
        qualified_offer = f'<span class="sub">{escape(offer)}</span>{pay_notes}'
        offer, pay_notes = "", ""
    parts = [offer, place if place == NO_PLACE else labelled("Where", place), work_review_label(research, route, compact=compact)]
    tag = f' <span class="tag">{escape(status)}</span>' if status else ""
    destination, action = work_destination(route, research)
    rid, role = escape(route.get("id")), clean(route.get("role")) or "Listing"
    link = f'<p class="work-action">{external_link(destination, action, work_action_name(action, route, employer))}{availability(destination, research.health)}</p>' if destination else ''
    requirements = work_requirements(route)
    visible = len(requirements)
    if compact:
        # Keep at least the first full requirement visible. Longer source lists
        # continue in the disclosure immediately before the employer action.
        while visible > 1 and len(" · ".join(requirements[:visible])) > 280:
            visible -= 1
    conditions = work_conditions(route, requirements[:visible])
    title = f'<a class="work-role-link" href="/work/#{rid}">{escape(role)}</a>' if compact else escape(role)
    terms = work_terms_html(research, route, employer, detailed=not compact, more_requirements=requirements[visible:],
                            primary_action_url=destination if compact else None)
    return (f'<li id="{rid}" tabindex="-1" data-work-route="{rid}"><strong>{title}</strong>{tag}'
            f'{qualified_offer}<span class="sub">{escape(". ".join(p for p in parts if p))}</span>{pay_notes}'
            f'{conditions}{terms}{link}</li>')


def company_work_html(research, company, routes, compact=False):
    cid, name = company["id"], clean(company["name"])
    heading = f'<h2 id="work" tabindex="-1">Paid work at {escape(name)}</h2>\n'
    if not routes: return heading + f'<p class="muted">No public work listing is recorded for {escape(name)}.</p>\n'
    names = {cid: name}
    # Only named listings and networks/programs count; secondary records stay separate.
    paid = sum(1 for r in routes if work_primary(r))
    lead = ("Pay and availability may have changed. Check the current terms on the company’s website." if paid
            else "No confirmed paid listing. Career pages and past records appear below.")
    body = [f"<p>{lead}</p>\n", safety_note()]
    if compact: body.append('<p>Open a role name to see its full Paid work record.</p>\n')
    for key, label, _ in WORK_DISPLAY_BUCKETS:
        rows = sort_routes([r for r in routes if work_display_bucket(r) == key], names)
        if rows: body.append(f"<h3>{label}</h3>\n<ul class=\"listings\">" + "".join(work_item(research, r, name, compact=compact) for r in rows) + "</ul>\n")
    return heading + "".join(body)


def safety_note(show_label=True):
    label = "<strong>Before you apply.</strong> " if show_label else ""
    return (f'<div class="note"><p>{label}Never pay to get work. Use the employer’s official site or a form it links to. '
            f'{external_link(SCAM_GUIDE, "How to spot a job scam")}</p></div>\n')


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
    """A risk claim's cited evidence, with the first source visible by default."""
    rows = [research.sources[sid] for sid in claim.get("source_ids", []) if sid in research.sources]
    if not rows: return '<span class="sub">No source recorded</span>'
    primary = rows[0]
    meta = source_meta(research, primary)
    return company_source_link(research, primary) + (f'<span class="sub">{escape(meta)}</span>' if meta else '') + company_citations(research, claim, primary["id"])


def risk_date_cell(research, claim):
    day = claim.get("as_of")
    if not month_text(day):
        return '<td class="date" data-label="Date">Source date not stated</td>'
    if day != claim.get("observed_on"):
        return f'<td class="date" data-label="As of">{escape(month_text(day))}</td>'
    label = "Research record date"
    # The reviewed RWS risk is dated by the check of two undated pages.
    reviewed = {"rws_trainai.source.d_rws3", "rws_trainai.source.d_rws6"}
    source_ids = claim.get("source_ids", [])
    if claim["id"] == "rws_trainai.claim.risks-1" and len(source_ids) == len(reviewed) and set(source_ids) == reviewed:
        sources = [research.sources.get(sid, {}) for sid in source_ids]
        if all(s.get("retrieval_status") == "checked" and s.get("accessed_on") == day and not s.get("published_on") for s in sources):
            label = "Source checked"
    return f'<td class="date" data-label="Date"><span class="sub">{escape(label)}</span>{escape(format_date(day))}</td>'


def risks_html(research, company_id, events):
    """Dated events, then supported risk claims; nothing at all when both are empty. The lawsuit note goes with the events."""
    dated, risks = company_events(events, company_id), risk_claims(research, company_id)
    if not dated and not risks: return ""
    parts = ['<h2 id="risks" tabindex="-1">Risks and disputes</h2>\n']
    if dated:
        sources = lambda e: " · ".join(external_link(s.get("url"), clean(s.get("publisher")) or "Source") + availability(s.get("url"), research.health) for s in e.get("sources", []))
        rows = "".join(f'<tr data-event="{escape(e["id"])}"><th scope="row">{escape(clean(e.get("title")))}<span class="sub">{escape(clean(e.get("detail")))}</span></th><td class="date" data-label="Date">{escape(month_text(e.get("date")) or clean(e.get("date")))}<span class="sub">{escape(EVENT_KINDS.get(e.get("kind")) or readable(e.get("kind")))}</span></td><td data-label="Status">{escape(clean(e.get("status")))}</td><td class="wide-cell" data-label="Sources">{sources(e)}</td></tr>' for e in dated)
        parts.append(f'<h3>Dated events</h3>\n<table class="wide events"><thead><tr><th scope="col">Event</th><th scope="col">Date</th><th scope="col">Status</th><th scope="col">Sources</th></tr></thead><tbody>{rows}</tbody></table>\n')
    if risks:
        rows = "".join(f'<tr data-risk="{escape(c["id"])}"><th scope="row">{escape(shown_text(research, c.get("statement")))}</th>{risk_date_cell(research, c)}<td class="wide-cell" data-label="Source">{claim_source_html(research, c)}</td></tr>' for c in risks)
        parts.append(f'<h3>Risks named in the evidence</h3>\n<table class="wide risks"><thead><tr><th scope="col">Risk</th><th scope="col">Date</th><th scope="col">Source</th></tr></thead><tbody>{rows}</tbody></table>\n')
    if dated: parts.append(f'<p class="muted">{EVENTS_NOTE} {escape(statuses_checked(dated))}</p>\n')
    parts.append(f'<p><a href="{ORIGIN}/explore/#company/{escape(company_id)}/risks">Open risks and disputes in Explore</a></p>\n')
    return "".join(parts)


def selected_business_observation(health, company_id):
    """Match financialObservationFor(): prefer recent whole-company reported revenue."""
    if not health: return None
    rows = [o for o in health.get("observations", []) if o.get("company_id") == company_id
            and o.get("signal") == "revenue" and o.get("measure") in ("period_revenue", "annualized_revenue")
            and is_number(o.get("value")) and not o.get("is_context") and o.get("evidence_type") == "reported"]
    def end(o):
        dated = re.search(r"\d{4}(?:-\d{2}){0,2}", str(o.get("as_of") or ""))
        return o.get("period", {}).get("end") or (dated.group() if dated else "")
    scopes = {"company": 0, "ai_data": 1, "other_segment": 2, "parent": 3}
    recent = [o for o in rows if end(o) >= "2025-10-28"]
    # Stable passes retain the same tie handling as the JavaScript helper.
    rows = sorted(recent or rows, key=end, reverse=True)
    rows = sorted(rows, key=lambda o: (scopes.get(o.get("scope"), 4), o.get("measure") != "period_revenue"))
    return rows[0] if rows else None


def business_observation_html(research, health, company_id, inline=False, compact=False):
    """A clearly dated supplement beside the unchanged research snapshot."""
    row = selected_business_observation(health, company_id)
    if not row: return ""
    source_ids = observation_source_ids(row)
    primary = row.get("primary_source_id")
    sources = {**research.sources, **{entry["id"]: entry for entry in health.get("sources", [])}}
    source = next((sources[sid] for sid in source_ids if sid in sources), None)
    checks = [c for c in health.get("source_checks", {}).get("entries", []) if c.get("source_id") in source_ids]
    failed = row.get("refresh_status") == "source_unavailable" or any(c.get("status") == "unavailable" for c in checks)
    checked = max((c["checked_on"] for c in checks if source and c.get("status") == "content_checked"
                   and c["source_id"] == source["id"] and c["url"] == source["url"]), default=None)
    period = research.observation_period(row)
    scope = row.get("scope_label") or {"company": "Whole company", "ai_data": "AI data business"}.get(row.get("scope"), row.get("scope", ""))
    if company_id == "rws_trainai" and row.get("scope") in ("company", "parent"): scope = "RWS Holdings plc group"
    kind = "Annualized revenue run rate" if row.get("measure") == "annualized_revenue" else "Revenue"
    basis = {"gross": "Gross revenue", "net": "Net revenue", "latest_discontinued_operations_comparative": "Discontinued operations"}.get(row.get("accounting_basis"), "Gross/net not disclosed")
    shown_period = period_text(period) if compact else period
    meta = " · ".join(str(x) for x in (None if compact else kind, shown_period, row.get("currency"), scope, basis) if x)
    link = external_link(source.get("url"), source.get("publisher") or "Original source") if source else ""
    if source and primary:
        link = external_link(source["url"], source["title"])
    if source and company_id == "snorkel_ai" and row.get("measure") == "annualized_revenue":
        link = external_link(source.get("url"), "Snorkel company disclosure")
    link_check = availability(source.get("url"), research.health) if source else ""
    published = research.reviewed_source_dates.get(source["id"]) if source else None
    dates = f"Published {format_date(published)} · {source_record_status(source)}" if published else ""
    citation = " · ".join(filter(None, (link + link_check, escape(dates), escape(row.get("evidence_assurance") or "Attributed source"))))
    source_attr = f' data-source-id="{escape(source["id"])}"' if source else ""
    warning = f'<span class="sub">{"Earlier" if primary else "Original"} citation could not be rechecked. Historical source attribution retained.</span>' if failed and (primary or not link_check) else ""
    content = (f'<div class="selected-evidence" data-financial-observation="{escape(row["id"])}">'
               + ('' if inline else '<h2>Selected financial evidence</h2>')
               + f'<strong class="selected-value">{escape(value_text(dict(row, qualifier="approximate" if row.get("qualifier") == "approximately" else row.get("qualifier"))))}</strong><span class="sub">{escape(meta)}</span>'
               + f'<span class="sub"{source_attr}>{citation}</span>' + warning)
    if checked and not inline: content += f'<span class="sub">Source content checked {escape(format_date(checked))}.</span>'
    if not inline: content += f'<details><summary>Source wording and limits</summary><p>{escape(row.get("original_text") or "")}</p><p>{escape(row.get("limitations") or "")}</p></details>'
    content += '</div>'
    dated = re.search(r"\d{4}(?:-\d{2}){0,2}", str(row.get("as_of") or ""))
    end = row.get("period", {}).get("end") or (dated.group() if dated else "")
    if not end or end < "2025-10-28":
        return '<details class="selected-archive"><summary>No recent revenue figure · historical evidence</summary>' + content + '</details>'
    return content


def company_metric_fact(research, metric, context=None):
    """A compact reported fact; its full row and source history stay below."""
    source, _ = latest_source(research, metric)
    assurance = {"company": "Company-reported", "investor": "Investor-reported", "independent_reporting": "Reported by press", "filing": "Filing", "customer": "Customer-reported", "database": "Database"}.get((source or {}).get("source_type"), "Attributed source")
    attribution = external_link(source.get("url"), clean(source.get("publisher")) or "Source") if source else "Source not recorded"
    qualifiers = ["Estimate"] if metric.get("reported_vs_estimated") == "estimated" else []
    if research.historical_year(metric): qualifiers.append("Historical")
    meta = " · ".join(value for value in (metric_period(research, metric), figure_scope(research, metric, context), basis_text(research, metric)) if value)
    return (f'<div class="company-key-fact" data-headline-metric="{escape(metric["id"])}"><span class="company-fact-label">{escape(figure_label(research, metric))}</span>'
            f'<strong>{escape(value_text(metric))}</strong>' + (f'<span class="company-fact-status">{escape(" · ".join(qualifiers))}</span>' if qualifiers else "")
            + f'<span class="company-fact-meta">{escape(meta)}</span><span class="company-fact-source">{attribution} · {escape(assurance)}</span></div>')


def finance_fact_html(fact, headline=False):
    """Display a curated finance record without borrowing dates from its source."""
    value = value_text({"value": fact["amount"], "currency": fact["currency"], "unit": "currency", "qualifier": fact.get("qualifier")})
    meta = " · ".join(filter(None, (fact["display_date"], fact["scope"], fact.get("note"))))
    source = external_link(fact["source_url"], fact["source_title"])
    dates = []
    if fact.get("source_published_on") and fact.get("date_role") not in ("announcement", "source_publication"):
        dates.append("Source published " + format_date(fact["source_published_on"]))
    if fact.get("source_accessed_on") and fact.get("date_role") != "source_check":
        verb = "Source summary recorded" if fact.get("source_status") == "summary_only" else "Source checked"
        dates.append(verb + " " + format_date(fact["source_accessed_on"]))
    if fact.get("source_checked_on") and fact["source_checked_on"] != fact.get("source_accessed_on"):
        dates.append("Source checked " + format_date(fact["source_checked_on"]))
    css = "company-key-fact" if headline else "company-finance-detail"
    return (f'<div class="{css}" data-finance-record="{escape(fact["record_id"])}" data-source-id="{escape(fact["source_id"])}">'
            f'<span class="company-fact-label">{escape(fact["label"])}</span><strong>{escape(value)}</strong>'
            f'<span class="company-fact-meta">{escape(meta)}</span><span class="company-fact-source">{escape(fact["claimant"])} · {source}</span>'
            + (f'<span class="company-fact-meta">{escape(" · ".join(dates))}</span>' if dates else "") + '</div>')


def company_headline_facts(research, company, figures, profile_entry, business_health):
    """At most two facts, with unknown and nonprofit states stated directly."""
    cid = company["id"]
    finance = (business_health or {}).get("profile_finance", {}).get(cid)
    fact = (finance or {}).get("headline")
    supplement = selected_business_observation(business_health, cid)
    cards = []
    same_revenue = fact and supplement and fact["record_id"] == supplement["id"]
    if supplement and not same_revenue:
        dated = re.search(r"\d{4}(?:-\d{2}){0,2}", str(supplement.get("as_of") or ""))
        end = supplement.get("period", {}).get("end") or (dated.group() if dated else "")
        if end >= "2025-10-28":
            rendered = business_observation_html(research, business_health, cid, inline=True, compact=True)
            label = "Annualized revenue run rate" if cid == "snorkel_ai" and supplement.get("measure") == "annualized_revenue" else "Annualized revenue pace" if supplement.get("measure") == "annualized_revenue" else "Revenue"
            cards.append(f'<div class="company-key-fact company-current-fact"><span class="company-fact-label">{label}</span>{rendered}</div>')
    contexts = (profile_entry or {}).get("metric_context") or {}
    headline = next((metric for metric in figures if metric.get("kind") in REVENUE_KINDS and not research.historical_year(metric)), None)
    if not cards and not supplement and headline:
        cards.append(company_metric_fact(research, headline, contexts.get(headline["id"])))
    if finance:
        if fact: cards.append(finance_fact_html(fact, headline=True))
        else: cards.append('<div class="company-key-fact company-unreported"><strong>Cumulative funding unverified</strong><a href="#financial-record">Read the seed and recruiting evidence</a></div>')
    if not cards:
        label = "Research organization" if company.get("entity_type") == "adjacent_research" else "No recent revenue figure" if supplement else "No confirmed revenue figure"
        cards.append(f'<div class="company-key-fact company-unreported"><span class="company-fact-label">Revenue</span><strong>{label}</strong><span class="company-fact-meta">' + ("Commercial revenue does not apply." if company.get("entity_type") == "adjacent_research" else "In the reviewed public sources.") + '</span></div>')
    secondary = next((metric for kind in ("valuation", "funding_total_reported", "funding_total_calculated") for metric in figures if metric.get("kind") == kind and not research.historical_year(metric)), None)
    if secondary and not finance: cards.append(company_metric_fact(research, secondary, contexts.get(secondary["id"])))
    return '<section class="company-key-facts" aria-label="Reported facts">' + "".join(cards[:2]) + '</section>'


def current_facts_html(profile_entry):
    """Structured supplemental facts; original research and narrative stay separate."""
    facts = (profile_entry or {}).get("current_facts") or {}
    if not facts.get("rows"): return ""
    sources = facts["sources"]
    rows = []
    for row in facts["rows"]:
        links = " ".join(external_link(sources[i]["url"], f"[{i + 1}]", sources[i]["title"]) for i in row["source_indexes"])
        rows.append(f'<div><dt>{escape(row["label"])}</dt><dd>{escape(row["value"])} {links}</dd></div>')
    return f'<details class="company-current-facts"><summary>Updates checked {escape(format_date(facts["reviewed_on"]))}</summary><dl class="current-fact-list">{"".join(rows)}</dl></details>'


def company_work_source_ids(research, company_id, routes):
    """Find citations already in work cards that serve only paid work claims."""
    recorded = {(source.get("id"), source.get("url")) for route in routes for source in route.get("sources") or []}
    work_claims = {claim_id for route in routes for claim_id in route.get("claim_ids") or []}
    work_ids, shared_ids = set(), set()
    for claim in research.claims.values():
        if claim.get("company_id") != company_id: continue
        group = work_ids if claim["id"] in work_claims else shared_ids
        group.update(claim.get("source_ids") or [])
    return {sid for sid, source in research.sources.items() if sid in work_ids - shared_ids
            and source.get("company_id") == company_id and sid not in research.reviewed_source_dates
            and is_web_url(source.get("url")) and (sid, source["url"]) in recorded}


def company_source_item(research, source, bookmark=False, historical_check=None):
    sid = source["id"]
    meta = source_meta(research, source, historical_check) if bookmark or historical_check or sid in research.reviewed_source_dates else ""
    if historical_check:
        meta = f"Historical citation · {meta}"
    anchor = f' id="{escape(sid)}"' if bookmark else ""
    annotation = f'<span class="sub">{escape(meta)}</span>' if meta else ""
    return f'<li{anchor} data-native-source="{escape(sid)}">{company_source_link(research, source, not historical_check)}{annotation}</li>'


def company_sources_html(research, company_id, name, work_source_ids, health=None):
    health = health or {}
    revised = [row for row in health.get("observations", []) if row["company_id"] == company_id and row.get("historical_source_ids")]
    historical_ids = {sid for row in revised for sid in row["historical_source_ids"]}
    replacement_ids = {sid for row in revised for sid in row["source_ids"] if sid not in research.sources}
    historical_checks = {row["source_id"]: row for row in health.get("source_checks", {}).get("entries", []) if row["source_id"] in historical_ids}
    items = [company_source_item(research, source, historical_check=historical_checks.get(sid)) for sid, source in research.sources.items()
             if source.get("company_id") == company_id and is_web_url(source.get("url")) and sid not in work_source_ids]
    originals = (f'<h3>Original sources for {escape(name)}</h3><ol data-native-source-list>{"".join(items)}</ol>'
                 if items else '<p>No original source links recorded.</p>')
    replacements = "".join(company_source_item(research, source, bookmark=True) for source in health.get("sources", []) if source["id"] in replacement_ids)
    return originals + (f'<h3>Replacement sources</h3><ol>{replacements}</ol>' if replacements else "")


def render_company_work_sources(research, company, source_ids, modified):
    cid, name = company["id"], clean(company["name"])
    canonical = f"{ORIGIN}/company/{cid}/work-sources/"
    heading = f"{name} paid work sources"
    title = heading + SUFFIX
    description = f"Original sources cited in the {name} paid work records."
    crumbs = [("Overview", f"{ORIGIN}/"), ("Companies", f"{ORIGIN}/companies/"),
              (name, f"{ORIGIN}/company/{cid}/"), ("Paid work sources", canonical)]
    items = "".join(company_source_item(research, source, bookmark=True) for sid, source in research.sources.items() if sid in source_ids)
    body = crumb_nav(crumbs) + f'<h1>{escape(heading)}</h1><ol data-native-source-list>{items}</ol>'
    structured = page_node("CollectionPage", title, description, canonical, modified, crumbs)
    return document(research, title, description, canonical, body, structured, current="companies", state="true")


def render_company(research, company, editorial_entry, profile_entry, routes, peers, labels, modified, events, business_health, company_work, work_source_ids):
    cid, name = company["id"], clean(company["name"])
    company = dict(company, name=name)
    canonical, app_url = f"{ORIGIN}/company/{cid}/", f"{ORIGIN}/explore/#company/{cid}"
    entry = editorial_entry or {}
    group = entry.get("primary_offering") or ""
    group_name = labels.get(group, group)
    summary = clean(entry.get("summary")) or shown_text(research, company.get("description"))
    figures = key_figures(research, cid, profile_entry)
    figure_ids = {row["id"] for row in figures}
    reviewed = {row["id"]: row for row in (business_health or {}).get("observations", [])
                if row["company_id"] == cid and row.get("metric_ids") == [row["id"]]
                and (row.get("primary_source_id") or row.get("qualifier_reviewed_on"))}
    figures.extend(row for row in research.by_company.get(cid, []) if row["id"] in reviewed and row["id"] not in figure_ids)
    figures = [{**row, "qualifier": reviewed[row["id"]]["qualifier"]} if row["id"] in reviewed else row for row in figures]
    pending = unconfirmed_figures(research, cid, figures)
    others = other_figures(research, cid, figures + pending)
    open_routes = [r for r in routes if work_display_bucket(r) in ("named", "programs", "boards", "outside")]
    paid_open = [r for r in open_routes if work_primary(r)]
    title = company_title(name, figures, bool(open_routes))
    description = company_description(research, name, summary, figures)
    # The structured breadcrumb follows the visible trail, business group included.
    crumbs = [("Overview", f"{ORIGIN}/"), ("Companies", f"{ORIGIN}/companies/")] + ([(group_name, f"{ORIGIN}/companies/#{group_slug(group)}")] if group else []) + [(name, canonical)]
    lead = next(iter(sentences(summary)), summary)
    work_link = f'<a href="#work">Paid work{f" <span>{len(paid_open)}</span>" if paid_open else ""}</a>' if routes else ""
    legal = legal_name(company)
    logos = {row["company_id"]: row for row in json.loads((ROOT / "data/logo-provenance.json").read_text()).get("logos", []) if row.get("status") == "verified" and row.get("local_path")}
    logo = logos.get(cid)
    brand = (f'<span class="company-logo{(" company-logo-dark" if logo.get("background") == "dark" else "")}"><img src="/{escape(logo["local_path"])}" width="112" height="48" alt=""></span>' if logo
             else f'<span class="company-logo company-monogram" aria-hidden="true">{escape("".join(word[0] for word in name.split()[:2]))}</span>')
    website = external_link(company["website"], "Website") if is_web_url(company.get("website")) else ""
    body = ['<link rel="stylesheet" href="/company-profile.css">\n', crumb_nav(crumbs, "company-crumbs"), '<article class="company-dossier">',
            f'<header class="company-hero"><div class="company-name">{brand}<h1>{escape(name)}</h1></div>'
            f'<p class="lede">{escape(lead)}</p><p class="company-actions">{website}{work_link}</p></header>',
            company_headline_facts(research, company, figures, profile_entry, business_health), current_facts_html(profile_entry)]
    dated, risk_rows = company_events(events, cid), risk_claims(research, cid)
    critical = next((event for event in dated if event.get("kind") in ("lawsuit", "data_incident")), None)
    if critical:
        checked = critical.get("status_checked_on")
        status_date = f' · status checked {format_date(checked)}' if ISO_DAY.fullmatch(str(checked or "")) else ""
        body.append(f'<div class="company-notice" role="note"><a href="#risks">{escape(clean(critical.get("title")))}</a><span>{escape(month_text(critical.get("date")))} · {escape(clean(critical.get("status")) + status_date)}</span></div>')
    body.append('<div class="company-record">')
    facts = []
    if group: facts.append(("Business group", f'<a href="{ORIGIN}/companies/#{group_slug(group)}">{escape(group_name)}</a>'))
    if company.get("founded_year"): facts.append(("Founded", escape(company["founded_year"])))
    if legal and legal != name: facts.append(("Legal entity", escape(legal)))
    tags = [clean(t) for t in entry.get("capability_tags") or [] if clean(t)]
    if tags: facts.append(("Also works on", escape(", ".join(tags))))
    products = research.products(cid, (profile_entry or {}).get("products"))[:PRODUCT_LIMIT]
    overview = [f'<details class="company-fold"><summary><span>Products &amp; company</span><small>{plural(len(products), "offering") if products else "Company details"}</small></summary><div class="company-fold-body">']
    if facts: overview.append(f'<h2 id="facts">About {escape(name)}</h2>\n<dl class="facts">' + "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts) + "</dl>\n")
    remaining_summary = " ".join(sentences(summary)[1:])
    if remaining_summary: overview.append(f'<p>{escape(remaining_summary)}</p>')
    if products:
        verb = "does" if company.get("entity_type") == "adjacent_research" else "sells"
        items = "".join(f"<li><strong>{escape(clean(p.get('name')))}</strong>" + (f": {escape(full_stop(clean(p.get('description'))))}" if clean(p.get("description")) else "") + (f' <span class="muted">{escape(full_stop(clean(p.get("status"))))}</span>' if clean(p.get("status")) else "") + "</li>" for p in products)
        overview.append(f'<h2 id="offerings">What {escape(name)} {verb}</h2>\n<ul>{items}</ul>\n')
    overview.append('</div></details>')
    finance = (business_health or {}).get("profile_finance", {}).get(cid) or {}
    detail_records = finance.get("native_detail_records") or []
    financial_count = len(figures) + len(pending) + len(others) + bool(selected_business_observation(business_health, cid)) + sum(record["record_id"] not in {metric["id"] for metric in figures} for record in detail_records)
    financial_meta = plural(financial_count, "recorded figure") if financial_count else "Disclosure limits"
    if pending: financial_meta += f' · {len(pending)} not confirmed'
    body.append(f'<details class="company-fold" id="financial-record"><summary><span>Financial record</span><small>{financial_meta}</small></summary><div class="company-fold-body">'
                + business_observation_html(research, business_health, cid)
                + figures_html(research, company, figures, pending, others, profile_entry, finance, business_health)
                + ''.join(finance_fact_html(record) for record in detail_records) + '</div></details>')
    body.extend(overview)
    if dated or risk_rows:
        body.append(f'<details class="company-fold"><summary><span>Risks &amp; events</span><small>{plural(len(dated), "event")} · {plural(len(risk_rows), "risk note")}</small></summary><div class="company-fold-body">' + risks_html(research, cid, events) + '</div></details>')
    body.append(f'<details class="company-fold"><summary><span>Paid work</span><small>{plural(len(paid_open), "listing or network", "listings and networks") if paid_open else "No confirmed listing"}</small></summary><div class="company-fold-body">' + company_work + '</div></details>')
    source_count = sum(source.get("company_id") == cid for source in research.data.get("sources", []))
    claim_count = sum(claim.get("company_id") == cid for claim in research.data.get("claims", []))
    body.append(f'<details class="company-fold"><summary id="sources" data-native-sources><span>Sources &amp; data</span><small>{plural(source_count, "source")}</small></summary><div class="company-fold-body"><h2 id="full-profile">Source records</h2>'
                f'<p>{plural(claim_count, "claim")} · Research compiled {escape(format_date(research.as_of))}</p>'
                + (f'<p><a href="/company/{cid}/work-sources/">{plural(len(work_source_ids), "paid work source")}</a></p>' if work_source_ids else '')
                + company_sources_html(research, cid, name, work_source_ids, business_health) +
                f'<ul class="company-source-links"><li><a href="{app_url}/sources">Source ledger</a></li><li><a href="{app_url}/people">Funding and people</a></li><li><a href="{ORIGIN}/research.json" download>Research JSON</a></li><li><a href="{ORIGIN}/observatory.sqlite" download>SQLite database</a></li></ul>'
                f'<p class="company-record-links"><a href="{app_url}">Interactive record</a><a href="{app_url}/traction">Figures</a><a href="{app_url}/work">Paid work</a><a href="{ORIGIN}/method/#grades">Source grades</a></p>')
    if logo: body.append(f'<p class="company-logo-source">Company logo: {external_link(logo.get("source_page") or logo.get("asset_url"), "official source")}. {LOGO_NOTE}</p>')
    if peers:
        links = "".join(f'<li><a href="{ORIGIN}/company/{escape(p["id"])}/">{escape(clean(p["name"]))}</a></li>' for p in peers)
        body.append(f'<h2 id="related">More in {escape(group_name)}</h2>\n<ul class="inline-list">{links}</ul>\n')
    body.append('</div></details></div></article>')
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


def render_index(research, companies, editorial_by_id, labels, work_count, modified, business_health=None, profile_by_id=None, current_entries=None, current_reviewed_on=""):
    from presentation import company_search_aliases

    current_entries = current_entries or []
    current_by_id = {row["entity_id"]: row for row in current_entries}
    historical_count = len(companies)
    companies = sorted([*companies, *[{"id": row["entity_id"], "name": row["name"]} for row in current_entries]], key=lambda c: (locale_key(clean(c["name"])), c["id"]))
    editorial_by_id = {**editorial_by_id, **{row["entity_id"]: {"primary_offering": row["group"], "summary": row["wikipedia"]["description"]} for row in current_entries}}
    canonical, count = f"{ORIGIN}/companies/", len(companies)
    title = f"AI data companies: {count} sourced profiles{SUFFIX}"
    description = f"Profiles of {count} AI data companies, grouped by what they sell. Each figure links to its source and shows when we checked or recorded it."
    crumbs = [("Overview", f"{ORIGIN}/"), ("Companies", canonical)]
    groups = {}
    for c in companies: groups.setdefault((editorial_by_id.get(c["id"]) or {}).get("primary_offering") or "Other", []).append(c)
    order = group_order(groups)
    nonprofit = len(groups.get("Nonprofit research", []))
    compiled = f" · {'historical ' if current_entries else ''}research compiled {format_date(research.as_of)}" if research.as_of else ""
    logos = {row['company_id']: row for row in json.loads((ROOT / 'data/logo-provenance.json').read_text()).get('logos', []) if row.get('status') == 'verified' and row.get('local_path')}
    body = ['<link rel="stylesheet" href="/companies-page.css">', crumb_nav(crumbs, "directory-crumbs"),
            '<header class="directory-intro"><h1>AI data companies</h1></header>',
            '<form class="directory-filters" id="company-filters" role="search" hidden><label>Search companies<input type="search" id="company-query" name="q" placeholder="Name, offering, or specialty" autocomplete="off"></label><label>Business group<select id="company-group" name="group"><option value="">All groups</option>' + ''.join(f'<option value="{group_slug(g)}">{escape(labels.get(g, g))}</option>' for g in order) + '</select></label><button type="reset">Clear</button></form>',
            f'<div class="directory-results-bar"><p class="directory-result" id="company-count" role="status" aria-live="polite">{count} companies</p>'
            '<div class="actions"><a class="directory-compare" href="/explore/#compare">Compare companies</a>'
            '<a class="text-link" href="/explore/#business-health">Revenue &amp; growth</a></div></div>',
            '<p class="directory-selected-group" data-directory-selected-group hidden></p>',
            '<p id="company-empty" class="directory-empty" hidden>No companies in this directory match. <a data-full-guide-search href="/?search=#browse-guide">Search the full guide</a></p>',
            '<nav class="directory-groups" aria-label="Business groups"><ul class="chips">' + "".join(f'<li><a href="#{group_slug(g)}">{escape(labels.get(g, g))} <span>{len(groups[g])}</span></a></li>' for g in order) + "</ul></nav>\n"]
    for g in order:
        items = []
        for c in groups[g]:
            cid, name = c['id'], clean(c['name'])
            summary = clean((editorial_by_id.get(cid) or {}).get('summary')) or shown_text(research, c.get('description'))
            logo = logos.get(cid)
            brand = (f'<span class="directory-logo {"on-dark" if logo.get("background") == "dark" else ""}"><img src="/{escape(logo["local_path"])}" alt="" width="40" height="40" loading="lazy"></span>' if logo else '')
            current_entry = current_by_id.get(cid)
            aliases = list(c.get("aliases", []))
            if current_entry:
                aliases += (current_entry.get("current_identity") or {}).get("aliases", [])
            aliases = company_search_aliases(cid, aliases)
            products = [value for product in ((profile_by_id or {}).get(cid) or {}).get("products", []) for value in [product.get("name", ""), product.get("description", ""), *product.get("aliases", [])] if isinstance(value, str) and value]
            search_text = " ".join([name, summary, g, *aliases, *products] + ([row["label"] for row in current_entry["offerings"]] if current_entry else []))
            matching = ' data-search-name="' + escape(name) + '" data-search-aliases="' + escape(json.dumps(aliases, ensure_ascii=False)) + '"'
            if current_entry:
                from current_companies import current_company_html
                content = current_company_html(current_entry, current_reviewed_on, compact=True)
                compare_link = ''
            else:
                content = f'<p>{escape(summary)}</p>{business_observation_html(research, business_health, cid, inline=True)}{current_facts_html((profile_by_id or {}).get(cid))}'
                compare_link = f'<a class="directory-compare" href="/explore/#compare/{escape(cid)}" aria-label="Compare {escape(name)}">Compare</a>'
            items.append(f'<li class="directory-company" data-company="{escape(cid)}" data-search="{escape(search_text)}"{matching}><div class="directory-company-heading">{brand}<h3><a href="{ORIGIN}/company/{escape(cid)}/">{escape(name)}{RIGHT_ARROW}</a></h3>{compare_link}</div>{content}</li>')
        body.append(f'<section class="directory-section" data-group="{group_slug(g)}"><div class="directory-section-heading"><h2 id="{group_slug(g)}" tabindex="-1">{escape(labels.get(g, g))}</h2><span>{plural(len(groups[g]), "company", "companies")}</span></div><ul class="index-list directory-grid">{"".join(items)}</ul></section>\n')
    missing = [name for name in NOT_YET_PROFILED if not any(name.casefold() in row["name"].casefold().split(" / ") for row in current_entries)]
    remaining = f' Firms not yet listed in this directory include {escape(join_words(missing))}.' if missing else ''
    scope = f'<p>Choose up to three of {plural(historical_count, "historical profile")} in Compare.</p>'
    if current_entries:
        scope += (f'<p>The {len(current_entries)} newer profiles cite dated Wikipedia context and official sources for their offerings.</p>'
                  f'<p><a href="/current-companies.json">Supplemental records for {len(current_entries)} added companies (JSON)</a></p>')
    body.append(f'<details class="directory-scope"><summary>Coverage and sources</summary><p>{len(groups)} business groups{escape(compiled)}.</p><p>{COVERAGE}{remaining}</p>' + scope + '<p>Each figure links to its source and keeps the original reporting date and scope.' + (f' {count_word(nonprofit)} of the {count} companies are nonprofit research groups.' if nonprofit else '') + f'</p><a href="{ORIGIN}/method/">How we check the research</a></details>')
    if work_count:
        body.append(f'<p class="actions directory-next"><a href="{ORIGIN}/work/">See {plural(work_count, "paid work route")}</a></p>')
    body.append('<script src="/companies-page.js" data-page-enhancement-script defer></script>')
    structured = page_node("CollectionPage", title, description, canonical, modified, crumbs, mainEntity={"@type": "ItemList", "numberOfItems": count, "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": clean(c["name"]), "url": f"{ORIGIN}/company/{c['id']}/"} for i, c in enumerate(companies)]})
    return document(research, title, description, canonical, "".join(body), structured, current="companies", note=f"<p>{LOGO_NOTE}</p>")


def work_table(research, rows, names, key, *, include_kind=True, ordered_ids=None):
    """Native listing cards retain all conditions and evidence without JavaScript."""
    out = {}
    for index, r in enumerate(rows):
        cid, status = r.get("company_id"), work_status(r)
        company = names.get(cid, cid)
        company_label = f"{key}-{index}"
        destination, action = work_destination(r, research)
        role = clean(r.get("role")) or "Listing"
        rid = escape(r["id"])
        tag = f'<span class="work-status">{escape(status)}</span>' if status else ""
        arrangements = " ".join(r.get("arrangements") or [])
        pay = work_pay(r)
        show_pay = key != "boards" and (key != "closed" or pay != "Pay not listed")
        archived = '<span class="sub">Historical advertised pay · </span>' if key == "closed" else ""
        pay_class = 'work-pay work-historical-pay' if archived else 'work-pay'
        offer = f'<p class="{pay_class}">{archived}<strong>{escape(pay)}</strong>{work_pay_notes(r)}' if show_pay else ""
        place = f'<p class="work-place">{escape(work_location(r))}' if key != "boards" else ""
        offer_html = f'<div class="work-offer">{offer}{place}</div>' if offer or place else ""
        action_html = f'<p class="work-listing-action">{external_link(destination, action, work_action_name(action, r, company))}{availability(destination, research.health)}</p>' if destination else ""
        full_review = work_review_label(research, r)
        brief_review = work_review_label(research, r, compact=True)
        # Compare reads the full review line. The card only needs a shared date once.
        review_html = escape(brief_review)
        if brief_review != full_review:
            review_html += f'<span hidden>{escape(full_review.removeprefix(brief_review))}</span>'
        out[r["id"]] = (f'<li class="work-listing" id="{rid}" tabindex="-1" data-work-route="{rid}" data-arrangements="{escape(arrangements)}">'
                        f'<div class="work-heading"><span class="work-company" id="{company_label}">{escape(company)}</span>{tag}'
                        f'<h3><a href="/company/{escape(cid)}/#{rid}" aria-describedby="{company_label}">{escape(role)}</a></h3></div>{offer_html}'
                        f'<p class="work-reviewed">{review_html}<div class="work-listing-conditions">{work_conditions(r, include_kind=include_kind)}</div>'
                        f'{action_html}{work_terms_html(research, r, company, detailed=False, primary_action_url=destination)}')
    if ordered_ids is not None and (len(ordered_ids) != len(out) or set(ordered_ids) != out.keys()):
        raise ValueError(f"Work card membership differs from the browser's {key} group")
    render_order = out if ordered_ids is None else ordered_ids
    return f'<ul class="work-listings">{"".join(out[record_id] for record_id in render_order)}</ul>\n'


def render_work(research, routes, names, modified, work_results=None, work_script=None):
    canonical = f"{ORIGIN}/work/"
    rows = [r for r in routes if r.get("company_id") in names]
    checked = latest(*(d for r in rows for d in (r.get("availability_checked_on"), (r.get("last_route_check") or {}).get("date"))))
    open_rows = [r for r in rows if work_primary(r)]
    open_count, open_companies = len(open_rows), len({r["company_id"] for r in open_rows})
    named_count = sum(work_display_bucket(r) == "named" for r in rows)
    program_count = sum(work_display_bucket(r) == "programs" for r in rows)
    title = f"Paid AI training work: {open_count} sourced routes{SUFFIX}"
    description = truncate(f"{plural(named_count, 'named listing')} and {plural(program_count, 'expert network or program', 'expert networks and programs')} at {plural(open_companies, 'AI data company', 'AI data companies')}, with published pay, requirements, sources and separate review dates.")
    crumbs = [("Overview", f"{ORIGIN}/"), ("Paid work", canonical)]
    buckets = {key: sort_routes([r for r in rows if work_display_bucket(r) == key], names) for key, _, _ in WORK_DISPLAY_BUCKETS}
    ranked = {}
    if work_script is not None:
        from frontend_packaging import work_default_order
        from presentation import work_native_selection
        ranked = work_default_order(work_native_selection({"routes": rows}, research.companies))
    directory_labels = {"outside": "Non-training jobs", "closed": "Past & reference"}
    groups = [(key, directory_labels.get(key, label), note) for key, label, note in WORK_DISPLAY_BUCKETS]
    scope = " and ".join(label for present, label in (
        (bool(buckets["boards"]), "career pages"),
        (any(row.get("status") in ("historical", "closed") for row in buckets["closed"]), "past listings"),
    ) if present)
    count_label = plural(len(rows), "record") + (f", including {scope}" if scope else "")
    directory_counts = (
        f'<p class="work-page-counts">{plural(named_count, "named listing")} <span>·</span> '
        f'{plural(program_count, "network or program", "networks and programs")} <span>·</span> '
        f'{plural(open_companies, "company", "companies")}</p>'
    )
    export = work_results or {}
    section_links = "".join(f'<li><a data-work-jump="{key}" href="#{key}">{escape(label)}</a></li>' for key, label, _ in groups if buckets[key])
    kind_options = "".join(f'<option value="{key}">{escape("Network/program" if key == "programs" else label)}</option>'
                           for key, label, _ in groups)
    engagement_filter_labels = {
        "employment": "Staff jobs", "bounty": "Bounty", "varies": "Varies", "unknown": "Unconfirmed",
    }
    engagement_options = "".join(
        f'<option value="{key}">{escape(engagement_filter_labels.get(key, label))}</option>'
        for key, label in WORK_ENGAGEMENT_LABELS.items()
    )
    body = ['<link rel="stylesheet" href="/work-page.css">\n<div class="work-page-intro">', crumb_nav(crumbs, "work-crumbs"),
            '<header class="work-page-heading" id="work-directory"><h1>Paid work in AI training</h1></header></div>\n',
            '<div class="work-page-filter-slot" data-work-filter-slot><form class="work-page-filters" data-work-filters hidden role="search" aria-label="Find paid work" id="work-filters">'
            '<label class="work-page-search">Search listings<input name="q" type="search" placeholder="Role, skill or firm" maxlength="256" autocomplete="off" id="name-filter"></label>'
            '<details class="work-page-filter-options"><summary>Filters</summary><div class="work-page-filter-fields">'
            f'<label>Listing type<select name="kind"><option value="">All records</option>{kind_options}</select></label>'
            '<label>Work arrangement<select name="arrangement"><option value="">Any arrangement</option><option value="remote">Remote possible</option><option value="onsite">On-site or hybrid</option><option value="varies">Varies or unlisted</option></select></label>'
            f'<label>Engagement<select name="type"><option value="">Any engagement</option>{engagement_options}</select></label>'
            '<label>Pay unit<select name="pay"><option value="">Any pay</option><option value="hourly">Hourly</option><option value="task">Per task</option><option value="yearly">Yearly</option><option value="monthly">Monthly</option><option value="numeric">Listed amount</option><option value="undisclosed">Pay unlisted</option></select></label>'
            '<label>Sort<select name="sort"><option value="">Default order</option><option value="hourly">Top listed pay/hr</option><option value="checked">Last checked</option></select></label>'
            '<button type="reset" class="work-page-clear">Clear</button></div></details></form>'
            '<div class="work-load-status" data-work-load-status hidden><p data-work-load-message role="status"></p><button type="button" data-work-retry hidden>Retry filters</button></div></div>'
            '<noscript><p data-work-native-fallback>Filters need JavaScript. Use your browser’s Find command to search the full list.</p></noscript>'
            '<div class="work-page-tools"><div class="work-results-toolbar" data-work-toolbar id="work-results">'
            '<p class="work-page-results" data-work-count aria-live="polite" aria-atomic="true">'
            f'{count_label}</p>'
            '<div class="work-results-actions"><a href="/work/?view=compare" data-work-compare hidden>Compare results</a>'
            f'<button type="button" data-work-export data-work-export-asset="{escape(export.get("href"))}" data-work-export-digest="{escape(export.get("sha256"))}" hidden>Download CSV</button></div></div>'
            '<p class="work-export-status" data-work-export-status aria-live="polite"></p>'
            '<div class="work-page-disclosures"><details class="work-page-groups work-section-disclosure"><summary>Jump to section</summary>'
            f'{directory_counts}<nav aria-label="Work sections" data-work-section-navigation><ul>{section_links}</ul></nav></details>'
            '<details class="work-page-advice"><summary>Before you apply</summary><p class="work-page-note">Check the employer’s page for current openings and pay. The employer sets eligibility.' + (f' Latest link check {escape(format_date(checked))}.' if checked else '') + '</p>\n' + safety_note(show_label=False) + '</details></div></div>\n',
            '<div class="work-page-empty" data-work-empty hidden><p>No records match. Try another word or clear the filters.</p><button type="button" data-work-clear>Clear search and filters</button></div>\n',
            '<section id="work-integrated-table" data-work-comparison hidden><h2 tabindex="-1">Compare paid work results</h2></section>',
            '<div class="work-page-list">']
    for key, label, note in groups:
        if not buckets[key]: continue
        fallback = '<noscript><p class="work-no-js-message">Filters need JavaScript. Showing the full directory.</p></noscript>'
        common_kind = WORK_KIND_LABELS[work_kind(buckets[key][0])] if key in ("named", "programs", "boards") else ""
        kind_attr = f' data-work-kind-label="{escape(common_kind)}"' if common_kind else ""
        cards = work_table(research, buckets[key], names, key, include_kind=not common_kind, ordered_ids=ranked.get(key))
        contents = f'<h2 id="{key}" tabindex="-1">{escape(label)}</h2>\n{fallback}' + (f'<p class="muted">{note}</p>\n' if note else '') + cards
        if key in ("named", "programs"):
            body.append(f'<section class="work-page-group" data-work-group="{key}"{kind_attr}>{contents}</section>\n')
        else:
            body.append(f'<details class="work-page-group work-page-secondary" data-work-group="{key}"{kind_attr}><summary>{escape(label)} <span>{len(buckets[key])}</span></summary>{contents}</details>\n')
    body.append('</div><p class="work-page-more"><a href="/explore/#work" data-work-explore>Open Work in Explore</a></p>')
    structured = page_node("CollectionPage", title, description, canonical, modified, crumbs)
    return document(research, title, description, canonical, "".join(body), structured, current="work", work_script=work_script)


DOWNLOADS = (("research.json", "JSON", "application/json", "The core research data in one file"), ("observatory.sqlite", "SQLite", "application/vnd.sqlite3", "The same data as one database file"),
             ("work-routes.json", "JSON", "application/json", "Paid-work records and editorial updates"), ("source-updates.json", "JSON", "application/json", "Later source corrections and the values they replace"),
             ("profile-content.json", "JSON", "application/json", "Profile summaries and the records they cite"), ("editorial.json", "JSON", "application/json", "Business groups and plain-language summaries"),
             ("business-health.json", "JSON", "application/json", "Each business health dashboard observation, with its sources and calculations"))
GRADES = (("A", "Public filing, independent evidence or buyer confirmation."), ("B", "The company, an investor or another named first-hand source says it."), ("C", "Reporting by others, an estimate, or indirect evidence."), ("U", "Not confirmed. The fact may be undisclosed or still unresolved."))


def render_method(research, sizes, modified):
    data, canonical = research.data, f"{ORIGIN}/method/"
    title = f"About{SUFFIX}"
    description = f"How {SITE_NAME} grades each claim and how to request a correction. Published by {PUBLISHER_NAME}. The research data is free to download."
    crumbs = [("Overview", f"{ORIGIN}/"), ("About", canonical)]
    year = re.match(r"[0-9]{4}", research.as_of)
    claims = data.get("claims", [])
    doubtful = sum(1 for c in claims if c.get("status") in ("unverified", "contested"))
    compiled = f" · research compiled {format_date(research.as_of)}" if research.as_of else ""
    subject = quote("ScienceToStartup correction")
    request = quote("Record ID or page link\r\n\r\nWhat needs correcting\r\n\r\nSource that supports the correction\r\n")
    email_link = f"mailto:{CORRECTION_EMAIL}?subject={subject}&body={request}"
    github_link = PUBLIC_IDENTITY["repository"]["url"] + "/issues/new?template=correction.yml"
    body = ['<link rel="stylesheet" href="/method-page.css">\n<div class="method-page">\n',
            '<header class="method-intro"><h1 id="about">About</h1>\n'
            f'<p>A public-source guide to AI data companies and paid work, published by {escape(PUBLISHER_NAME)}.</p></header>\n',
            '<div class="method-sections">',
            '<details class="method-detail" id="method-notes"><summary>How we check figures</summary><div class="method-detail-body"><h2 id="figures">How figures are shown</h2>\n'
            '<p>Each claim links to its evidence. Missing figures stay unknown.</p><ul>'
            '<li>Figures keep their reporting period and business scope, whether they cover a segment or the whole company.</li>'
            '<li>Key figures show reported results supported by sources.</li>'
            '<li>Talks, unverified reports, and conflicting sources appear separately as Not confirmed, with their status in words.</li>'
            + (f'<li>Historical marks figures from {int(year.group(0)) - 2} or earlier.</li>' if year else '')
            + '<li>Annualized pace projects recent revenue across a full year. Gross or net revenue is stated when the source specifies it.</li>'
            '<li>Estimates are labeled. Forecasts, targets, and older or partial figures appear under other reported figures, never as key figures.</li>'
            '<li>Later corrections appear beside the figure. The original records remain in the downloads.</li></ul></div></details>\n',
            '<details class="method-detail" id="evidence-notes"><summary>Evidence grades and delivery rules</summary><div class="method-detail-body"><h2 id="grades">Confidence grades</h2>\n<p>A grade describes the strength of a claim’s sources.</p>\n<dl class="grades method-grades">' + "".join(f'<div><dt>{g}</dt><dd>{escape(text)}</dd></div>' for g, text in GRADES) + '</dl>\n<p>A public filing can come from the company itself.</p>\n']
    dimensions = (data.get("rubric") or {}).get("dimensions") or []
    if dimensions:
        rows = "".join(f'<tr><th scope="row">{escape(d.get("id"))} · {escape(clean(d.get("label")))}</th>' + "".join(f'<td data-label="Level {n}">{escape(clean((d.get("levels") or {}).get(n)))}</td>' for n in ("1", "2", "3")) + "</tr>" for d in dimensions)
        body.append('<h2 id="labels">Delivery evidence</h2>\n<p>This level describes public proof that a company sells and delivers its offer. Four measures, rated 1–3, cover a specific business scope. Funding and valuations do not count toward it.</p>\n'
                    f'<table class="wide"><thead><tr><th scope="col">Measure</th><th scope="col">Level 1</th><th scope="col">Level 2</th><th scope="col">Level 3</th></tr></thead><tbody>{rows}</tbody></table>\n')
    body.append('</div></details>\n')
    # Some companies hold two ratings (one per business scope), so count the companies rated, as the app's method page does.
    rated = {row.get("company_id") for row in data.get("assessments", [])} & set(research.companies)
    unrated = [c for cid, c in research.companies.items() if cid not in rated]
    unrated_note = (f" The {count_word(len(unrated)).lower()} nonprofit research {'group gets' if len(unrated) == 1 else 'groups get'} no level." if unrated and all(c.get("entity_type") == "adjacent_research" for c in unrated)
                    else f" {plural(len(unrated), 'company has', 'companies have')} no level yet." if unrated else "")
    body.append('<details class="method-detail" id="coverage-notes"><summary>Coverage and limits</summary><div class="method-detail-body"><h2 id="coverage">Research coverage</h2>\n'
                f'<p class="method-snapshot">Dataset v{escape(data.get("dataset_version", ""))}{escape(compiled)}</p>\n'
                f'<p>{plural(len(research.companies), "company profile")} · {plural(len(rated), "company", "companies")} with a delivery evidence level · {plural(len(data.get("sources", [])), "source record")}.{unrated_note}</p>\n'
                f"<p>{plural(doubtful, 'claim is', 'claims are')} unverified or disputed. Each one is labeled. {COVERAGE}</p></div></details>\n")
    files = [(name, kind, mime, text) for name, kind, mime, text in DOWNLOADS if name in sizes] + [(name, "CSV", "text/csv", f"The {name[:-4].replace('_', ' ')} table") for name in sorted(n for n in sizes if n.endswith(".csv"))]
    canonical_names = {"research.json", "observatory.sqlite", "classifications.csv"} | {name + ".csv" for name in TABLES}
    historical_files = [item for item in files if item[0] in canonical_names]
    supporting_files = [item for item in files if item[0] not in canonical_names]
    if files:
        tables = []
        for label, selected in (("Historical company dataset", historical_files), ("Current supporting data", supporting_files)):
            if not selected:
                continue
            rows = "".join(f'<tr><th scope="row"><a href="{ORIGIN}/{escape(name)}" download>{escape(name)}</a></th><td data-label="Format">{kind}</td><td data-label="Size">{escape(sizes[name])}</td><td data-label="Contents">{escape(text)}</td></tr>' for name, kind, mime, text in selected)
            tables.append(f'<h3>{label}</h3><table class="wide"><thead><tr><th scope="col">File</th><th scope="col">Format</th><th scope="col">Size</th><th scope="col">Contents</th></tr></thead><tbody>{rows}</tbody></table>')
        version = data.get("dataset_version", "")
        body.append(f'<details class="method-detail" id="download-files"><summary>Data and license</summary><div class="method-detail-body"><h2 id="downloads">Download the data</h2>\n<p>Dataset version {escape(version)}{escape(compiled.replace(" · research", ", research"))}. The research data files keep every claim that later research replaced.</p>\n'
                    f'<p>{SITE_NAME} licenses this data under the <a class="ext" rel="license" href="{DATA_LICENSE}">CC BY 4.0 license</a> (any use is allowed if you credit us). Cite {SITE_NAME} and the original sources. Company names and logos belong to their owners. The license does not cover them. It also leaves out product images, photos of people, text quoted from sources and personal contact details.</p>\n'
                    + ''.join(tables) + '</div></details>\n')
    body.append('<details class="method-detail" id="disclosures"><summary>Publisher and disclosures</summary><div class="method-detail-body">\n'
                '<p>No profiled company has paid for coverage, and none is a customer, investor or affiliate of the publisher.</p>\n'
                f'<p>{escape(WORK_DISCLOSURE)}</p>\n'
                f'<p><strong>Disclosure.</strong> {disclosure_html()}</p>\n'
                '<p><strong>Personal data and removal.</strong> Company profiles name founders and executives from public company sources only. Profiles do not show personal contact details. If you are named here and want a record corrected or removed, <a href="#corrections">send a correction request</a>. '
                f'{VISITS_NOTE}</p></div></details></div>\n'
                '<aside id="corrections" tabindex="-1" aria-labelledby="corrections-title"><h2 id="corrections-title">Corrections</h2>'
                '<p>Include the record or page link, what needs correcting, and a source. We review requests within seven days.</p>'
                '<p id="correction-record" hidden>Record to correct <a href="#corrections"></a></p>'
                f'<div class="method-contact">{external_link(github_link, "Submit a correction on GitHub")}'
                f'<a id="correction-email" href="{escape(email_link)}">Email a correction</a>'
                f'<p>Email address <span>{escape(CORRECTION_EMAIL)}</span></p>'
                f'<a href="{ORIGIN}/research/corrections/">Read the accepted correction log</a></div></aside></div>\n'
                '<script src="/method-correction.js" defer></script>\n')
    counts = {key: len(data.get(key, [])) for key in ("companies", "claims", "sources", "metrics", "funding_rounds", "products")}
    counts["current_claims"] = sum(1 for claim in data.get("claims", []) if claim.get("status") != "superseded")
    measured = sorted({KIND_LABELS.get(m.get("kind"), "") for m in data.get("metrics", [])} - {"", KIND_LABELS["other"]})
    # The home page's Dataset node, described in full where its files are listed. Publisher and creator link to the one Person by @id.
    dataset = {"@context": "https://schema.org", "@type": "Dataset", "@id": DATASET_ID, "name": DATASET_NAME, "alternateName": clean((data.get("meta") or {}).get("title")) or SITE_NAME,
               "description": f"Historical public-source research on {counts['companies']} AI data companies: {counts['current_claims']:,} non-superseded claims ({counts['claims']:,} including earlier versions) from {counts['sources']:,} sources, with {counts['metrics']} figures, {counts['funding_rounds']} funding rounds and {counts['products']} products. Each claim keeps its business scope and confidence grade, and each figure links to its sources.",
               "url": canonical, "version": data.get("dataset_version", ""), "dateModified": research.as_of, "isAccessibleForFree": True, "license": DATA_LICENSE,
               "creator": {"@id": PUBLISHER["@id"]}, "publisher": {"@id": PUBLISHER["@id"]},
               "measurementTechnique": "Public-source research. Each claim is graded A, B, C or U by the strength of its sources.", "variableMeasured": measured,
               "distribution": [{"@type": "DataDownload", "name": name, "contentUrl": f"{ORIGIN}/{name}", "encodingFormat": mime} for name, kind, mime, text in historical_files]}
    structured = [page_node("AboutPage", title, description, canonical, modified, crumbs, about={"@id": WEBSITE["@id"]}), dataset]
    return document(research, title, description, canonical, "".join(body), structured, current="method")


def render_not_found(research, directory_count=None):
    count = len(research.companies) if directory_count is None else directory_count
    pages = (("Daily scan and archive", "/daily/", "browse the published editions by date"), ("Research", "/research/", "the current report, evidence and open data"), ("Papers", "/research/papers/", "current paper records and their source versions"), ("Companies", "/companies/", f"profiles of all {plural(count, 'company', 'companies')}" if count else "company profiles"), ("Paid work", "/work/", "public listings with pay and location"), ("Search", "/?search=#browse-guide", "search the current guide"), ("Method", "/method/", "how we check figures and how to request a correction"), ("About the publisher", "/method/#about", "who publishes the guide and how to get in touch"), ("Overview", "/", "what the guide covers"))
    items = "".join(f'<li><a href="{path if path.startswith("/?search=") else ORIGIN + path}">{label}</a> · {text}</li>' for label, path, text in pages)
    body = (f'<p class="eyebrow">Page not found</p>\n<h1>We could not find that page.</h1>\n'
            '<p class="lede">The link may be old or mistyped. Choose a current section or search the guide:</p>\n'
            f'<ul>{items}</ul>\n'
            '<details class="not-found-retirement"><summary>Looking for the former platform?</summary>'
            '<p>The earlier paper-commercialization platform and its tools are retired. Its API and MCP endpoint are unavailable.</p>'
            '<p>ScienceToStartup now publishes research on AI data companies and paid AI training work. '
            'Current paper records show evidence and review status; they do not restore the former platform’s scores or reports.</p>'
            '</details>\n')
    return document(research, f"Page not found{SUFFIX}", "The page you asked for does not exist on ScienceToStartup.", "", body, robots="noindex")

# ---------------------------------------------------------------------------
# Sitemap and the build entry point

def render_sitemap(entries):
    urls = "".join(f"  <url>\n    <loc>{escape(loc)}</loc>\n"
                   + (f"    <lastmod>{escape(lastmod)}</lastmod>\n" if lastmod else "")
                   + "  </url>\n" for loc, lastmod in entries)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n"


def file_size(size):
    try:
        from observatory import format_file_size
    except ImportError:
        return f"{size} B"
    return format_file_size(size)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else None


def write_static_pages(data, destination, work_data=None, profile_content=None, editorial=None, events=None, link_health=None, root=ROOT, business_health=None, current_companies=None, work_results=None, work_script=None):
    """Write /company/<id>/, /companies/, /work/, /method/, 404.html and sitemap.xml.
    `events` is the company events sidecar and `link_health` the link checks, both as the build validated them."""
    destination, root = Path(destination), Path(root)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'static-pages.css').write_text(STYLE, encoding='utf-8')
    publication = read_json(root / "data/editorial-release.json") or {}
    publication_as_of = publication.get("publication_as_of") if publication.get("canonical_dataset_version") == data["dataset_version"] else data.get("meta", {}).get("as_of")
    research = Research(data, read_js_object(root / "web/app.js", "FINANCIAL_HEADLINES"), read_json(root / "data/source-updates.json"),
                        say=public_wording(data, load_copy_edits(root / "web/app.js")), health=link_health_index(link_health), publication_as_of=publication_as_of)
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
        modified = latest(research.as_of, SITE_REVISED, (editorial_by_id.get(cid) or {}).get("reviewed_on"), ((profile_by_id.get(cid) or {}).get("current_facts") or {}).get("reviewed_on"), (selected_business_observation(business_health, cid) or {}).get("evidence_checked_on"), events_reviewed if company_events(events, cid) else "", *(d for r in own for d in route_dates(r))) or research.as_of
        folder = destination / "company" / cid
        folder.mkdir(parents=True, exist_ok=True)
        company_work = company_work_html(research, company, own)
        work_source_ids = ()
        # Long dossiers retain all work evidence in the cards. Their source
        # ledger links to the duplicate work-specific records.
        if len(company_work.encode()) > 70_000:
            company_work = company_work_html(research, company, own, compact=True)
            work_source_ids = company_work_source_ids(research, cid, own)
        page = render_company(research, company, editorial_by_id.get(cid), profile_by_id.get(cid), own, peers, labels,
                              modified, events, business_health, company_work, work_source_ids)
        (folder / "index.html").write_text(page, encoding="utf-8")
        written.append(folder / "index.html")
        company_entries.append((f"{ORIGIN}/company/{cid}/", modified))
        if work_source_ids:
            index = folder / "work-sources/index.html"
            index.parent.mkdir(exist_ok=True)
            index.write_text(render_company_work_sources(research, company, work_source_ids, modified), encoding="utf-8")
            written.append(index)
            company_entries.append((f"{ORIGIN}/company/{cid}/work-sources/", modified))
    index_modified = latest(research.as_of, SITE_REVISED, *reviewed, *((e.get("current_facts") or {}).get("reviewed_on") for e in profile_by_id.values()), (business_health or {}).get("dashboard_curated_on"), (current_companies or {}).get("reviewed_on")) or research.as_of
    work_modified = latest(research.as_of, SITE_REVISED, *(d for r in routes for d in route_dates(r))) or research.as_of
    method_modified = latest(research.as_of, SITE_REVISED) or research.as_of
    sizes = {path.name: file_size(path.stat().st_size) for path in sorted(destination.iterdir()) if path.is_file() and (path.suffix == ".csv" or path.name in {d[0] for d in DOWNLOADS})}
    pages = {"companies": render_index(research, by_name, editorial_by_id, labels, sum(1 for r in routes if work_primary(r)), index_modified, business_health, profile_by_id, (current_companies or {}).get("entries", []), (current_companies or {}).get("reviewed_on", "")), "work": render_work(research, routes, names, work_modified, work_results, work_script), "method": render_method(research, sizes, method_modified)}
    for name, page in pages.items():
        (destination / name).mkdir(parents=True, exist_ok=True)
        (destination / name / "index.html").write_text(page, encoding="utf-8")
        written.append(destination / name / "index.html")
    (destination / "404.html").write_text(render_not_found(research, len(companies) + len((current_companies or {}).get("entries", []))), encoding="utf-8")
    written.append(destination / "404.html")
    entries += [(f"{ORIGIN}/companies/", index_modified)] + company_entries + [(f"{ORIGIN}/work/", work_modified), (f"{ORIGIN}/method/", method_modified)]
    (destination / "sitemap.xml").write_text(render_sitemap(entries), encoding="utf-8")
    written.append(destination / "sitemap.xml")
    return written
