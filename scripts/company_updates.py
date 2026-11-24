"""Validate optional, dated current facts beside the frozen company research."""
import re
from datetime import date
from urllib.parse import urlsplit


class CompanyUpdatesValidationError(ValueError):
    """A current company fact lacks a valid scope or source receipt."""


def validate_profile_current_facts(profile_content, data, *, additional_company_ids=(), reviewed_through=None):
    """Return the supplied profile content after validating optional current_facts.

    Profiles without current facts need no current-source receipt. This keeps
    historical profile content independent of current company maintenance.
    Callers may explicitly admit IDs from an already validated current registry;
    ordinary profile validation remains restricted to canonical company IDs.
    """
    def require(condition, message):
        if not condition:
            raise CompanyUpdatesValidationError("company-updates: " + message)

    def day(value, where):
        require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), where + " must be YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise CompanyUpdatesValidationError("company-updates: " + where + " is not a calendar date")
        return value

    def text(value, where, limit):
        require(isinstance(value, str) and value.strip() and value == value.strip(), where + " must be non-empty, trimmed text")
        require(len(value) <= limit, where + " is too long")
        require(not re.search(r"[<>\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]", value), where + " must be plain text")

    require(isinstance(profile_content, dict) and isinstance(profile_content.get("entries"), list), "profiles must contain entries")
    additional_company_ids = tuple(additional_company_ids)
    require(all(isinstance(cid, str) and re.fullmatch(r"org\.[a-z0-9][a-z0-9_.-]*", cid) for cid in additional_company_ids), "additional company IDs must be validated organization IDs")
    companies = {row["id"] for row in data.get("companies", [])} | set(additional_company_ids)
    if reviewed_through is not None:
        day(reviewed_through, "reviewed_through")
    updated = set()
    for entry in profile_content["entries"]:
        require(isinstance(entry, dict), "profile entry must be an object")
        if "current_facts" not in entry:
            continue
        cid = entry.get("company_id")
        require(isinstance(cid, str) and cid in companies, "current facts must belong to a known company")
        require(cid not in updated, "duplicate current facts for " + cid)
        updated.add(cid)
        facts = entry["current_facts"]
        prefix = cid + ".current_facts"
        require(isinstance(facts, dict) and set(facts) == {"reviewed_on", "rows", "sources"}, prefix + " must contain reviewed_on, rows and sources")
        reviewed = day(facts["reviewed_on"], prefix + ".reviewed_on")
        if reviewed_through is not None:
            require(reviewed <= reviewed_through, prefix + ".reviewed_on is after the registry review")
        sources = facts["sources"]
        require(isinstance(sources, list) and sources, prefix + ".sources must be non-empty")
        for index, source in enumerate(sources):
            where = prefix + ".sources[" + str(index) + "]"
            fields = {"url", "title", "published_on", "observed_on", "response_sha256", "locator"}
            require(isinstance(source, dict) and fields <= set(source) <= fields | {"content_kind"}, where + " has unsupported source fields")
            if "content_kind" in source:
                require(source["content_kind"] in ("raw_http_body", "web_tool_text_excerpt"), where + ".content_kind is unsupported")
            url = source["url"]
            require(isinstance(url, str) and not re.search(r"[\s\x00-\x1f\x7f]", url), where + ".url must be an HTTPS URL")
            try:
                parsed = urlsplit(url)
                parsed.port
            except ValueError:
                raise CompanyUpdatesValidationError("company-updates: " + where + ".url must be an HTTPS URL")
            require(parsed.scheme == "https" and parsed.hostname and parsed.username is None and parsed.password is None, where + ".url must be HTTPS without credentials")
            text(source["title"], where + ".title", 240)
            text(source["locator"], where + ".locator", 400)
            observed = day(source["observed_on"], where + ".observed_on")
            require(observed <= reviewed, where + ".observed_on is after the review")
            if source["published_on"] is not None:
                published = day(source["published_on"], where + ".published_on")
                require(published <= observed, where + ".published_on is after observation")
            require(isinstance(source["response_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", source["response_sha256"]), where + ".response_sha256 must be a lowercase SHA-256")
        rows = facts["rows"]
        require(isinstance(rows, list) and rows, prefix + ".rows must be non-empty")
        labels = set()
        for index, row in enumerate(rows):
            where = prefix + ".rows[" + str(index) + "]"
            require(isinstance(row, dict) and set(row) == {"label", "value", "source_indexes"}, where + " must contain label, value and source_indexes")
            text(row["label"], where + ".label", 80)
            text(row["value"], where + ".value", 200)
            require(row["label"] not in labels, where + " repeats a label")
            labels.add(row["label"])
            references = row["source_indexes"]
            require(isinstance(references, list) and references, where + ".source_indexes must be non-empty")
            require(all(type(value) is int and 0 <= value < len(sources) for value in references), where + ".source_indexes contains an invalid reference")
            require(len(set(references)) == len(references), where + ".source_indexes repeats a reference")
    return profile_content
