"""Validate additive editorial work metadata without changing canonical research.

The work sidecar retains its original research/check dates.  This contract records
editorial classification separately from successful source review and retrieval.
"""
from __future__ import annotations

import hashlib
import copy
import json
import re
from datetime import date, datetime
from pathlib import Path

ROUTE_KINDS = {"named_listing", "network_program", "career_page", "other_record"}
ENGAGEMENT_TYPES = {"contract", "employment", "fellowship", "bounty", "study", "varies", "unknown"}
ARRANGEMENTS = {"remote", "onsite", "hybrid"}
PAY_UNITS = {"hour", "hour_equivalent", "task", "month", "year", "one_time", "mixed", "undisclosed", "conflicting"}
FACT_STATES = {"sourced", "source_not_stated", "not_researched", "conflicting"}
FIELD_NAMES = {"destination", "pay", "location", "requirements", "commitment", "duration", "assessment"}
REVIEW_BASES = {"stored_evidence", "direct_source", "not_reviewed"}
RECEIPT_RESULTS = {"readable", "blocked", "not_found", "unavailable", "unreadable_shell", "error"}
ARCHIVE_STATUSES = {"historical", "closed", "contributions", "paused", "no_route", "inquiry", "information"}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class EditorialValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EditorialValidationError("editorial-work: " + message)


def checked_date(value, label):
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), label + " must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EditorialValidationError("editorial-work: " + label + " is invalid") from error


def primary_routes(work):
    """Recorded discovery routes, not a count of open vacancies."""
    return [row for row in work["routes"]
            if row.get("route_kind") in {"named_listing", "network_program"}
            and row.get("status") not in ARCHIVE_STATUSES
            and row.get("ai_data_work") is not False]


def editorial_counts(work):
    primary = primary_routes(work)
    return {
        "records": len(work["routes"]),
        "work_routes": len(primary),
        "named_listings": sum(row["route_kind"] == "named_listing" for row in primary),
        "networks_programs": sum(row["route_kind"] == "network_program" for row in primary),
        "providers": len({row["company_id"] for row in primary}),
        "career_pages": sum(row["route_kind"] == "career_page" for row in work["routes"]),
        "past_other_records": sum(row["route_kind"] == "other_record" or row.get("status") in ARCHIVE_STATUSES for row in work["routes"]),
        "other_company_jobs": sum(row.get("ai_data_work") is False and row.get("status") not in ARCHIVE_STATUSES for row in work["routes"]),
    }


def validate_editorial_release(work, release, canonical, *, canonical_sha256=None, work_sha256=None):
    require(isinstance(release, dict) and release.get("schema_version") == "1.0.0", "unsupported release format")
    release_id = release.get("release_id")
    require(isinstance(release_id, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", release_id)), "invalid release_id")
    as_of = checked_date(release.get("as_of"), "as_of")
    require(release["as_of"] == release_id.split(".", 1)[0], "release date differs from as_of")
    publication = release.get("publication_as_of", "")
    require(isinstance(publication, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", publication)), "publication_as_of must be an explicit UTC timestamp")
    try:
        publication_time = datetime.fromisoformat(publication.replace("Z", "+00:00"))
    except ValueError as error:
        raise EditorialValidationError("editorial-work: invalid publication timestamp") from error
    require(publication[:10] == release["as_of"], "publication date differs from as_of")
    require(release.get("canonical_dataset_version") == canonical.get("dataset_version") == "2.5.0", "canonical dataset version must remain 2.5.0")
    require(bool(SHA256.fullmatch(release.get("canonical_sha256", ""))), "canonical receipt missing")
    if canonical_sha256 is not None:
        require(release["canonical_sha256"] == canonical_sha256, "canonical bytes changed")
    require(bool(SHA256.fullmatch(release.get("work_routes_sha256", ""))), "work sidecar receipt missing")
    if work_sha256 is not None:
        require(release["work_routes_sha256"] == work_sha256, "work sidecar differs from approved release")
    policy = release.get("publication_policy", {})
    require(policy.get("automated_checks_change_facts") is False, "automated checks may only create candidates")
    require(policy.get("editor_days_per_week") == 5, "editorial coverage must distinguish five editor days from daily automation")
    require(policy.get("homepage_work_max_age_days") == 3, "homepage review window differs")
    require(policy.get("named_review_interval_days") == 7 and policy.get("named_needs_recheck_days") == 14, "named-listing review policy differs")
    require(policy.get("program_review_interval_days") == 30 and policy.get("program_promotion_max_age_days") == 45, "program review policy differs")

    rows = work.get("routes", [])
    require(release.get("counts") == editorial_counts(work), "release counts differ from classified routes")
    ids = {row["id"] for row in rows}
    calibration = release.get("calibration_route_ids", [])
    require(len(calibration) == len(set(calibration)) == 12 and set(calibration) <= ids, "calibration must identify twelve existing routes")
    canonical_sources = {source["id"] for source in canonical.get("sources", [])}
    for row in rows:
        label = row["id"]
        require(row.get("route_kind") in ROUTE_KINDS, label + ": route kind missing")
        require(row.get("engagement_type") in ENGAGEMENT_TYPES, label + ": engagement type missing")
        arrangements = row.get("arrangements")
        require(isinstance(arrangements, list) and len(arrangements) == len(set(arrangements)) and set(arrangements) <= ARRANGEMENTS, label + ": invalid arrangements")
        pay = row.get("pay_terms", {})
        require(pay.get("unit") in PAY_UNITS and isinstance(pay.get("hourly_comparable"), bool), label + ": invalid pay semantics")
        require(pay.get("basis") == row.get("pay_basis"), label + ": pay basis changed without provenance")
        require(pay.get("currency") is None or bool(re.fullmatch(r"[A-Z]{3}", pay["currency"])), label + ": invalid currency")
        require(not pay["hourly_comparable"] or (pay["unit"] == "hour" and row.get("numeric_pay") and row.get("status") != "pay_conflict"), label + ": hourly equivalent/mixed/conflicting pay cannot be compared as hourly payment")
        require(row.get("pay_basis") not in {"per_completed_task", "hour_equivalent", "hour_or_accepted_task", "approved_deliverables"} or not pay["hourly_comparable"], label + ": task/conditional pay misclassified as actual hourly payment")

        editorial = row.get("editorial_review", {})
        require(editorial.get("release_id") == release_id, label + ": editorial release mismatch")
        require(checked_date(editorial.get("classified_on"), label + ": classified_on") <= as_of, label + ": future classification")
        require(editorial.get("classification_basis") == "stored_evidence", label + ": classification must retain its evidence basis")
        available_sources = canonical_sources | {source["id"] for source in row.get("sources", [])}
        references = editorial.get("classification_source_ids", [])
        require(bool(references) and set(references) <= available_sources, label + ": missing classification sources")
        reviews = row.get("field_reviews", {})
        require(set(reviews) == FIELD_NAMES, label + ": incomplete explicit field states")
        for name, review in reviews.items():
            where = label + ": " + name
            require(review.get("state") in FACT_STATES and review.get("basis") in REVIEW_BASES, where + ": invalid review state")
            refs = review.get("source_ids", [])
            require(isinstance(refs, list) and len(refs) == len(set(refs)) and set(refs) <= available_sources, where + ": unknown source")
            if review["state"] == "not_researched":
                require(review.get("reviewed_on") is None and review["basis"] == "not_reviewed", where + ": an unresearched field cannot claim a review date")
            else:
                require(bool(refs) and review["basis"] != "not_reviewed", where + ": reviewed fact lacks evidence")
                # A source-supported legacy value does not imply that a precise
                # field-review date was recorded. Do not copy a route-wide date.
                if review.get("reviewed_on") is None:
                    require(review["basis"] == "stored_evidence" and review["state"] != "source_not_stated", where + ": direct review or source absence requires an actual date")
                else:
                    require(checked_date(review["reviewed_on"], where) <= as_of, where + ": future review date")
            if review["state"] == "source_not_stated":
                require(bool(review.get("note")), where + ": absence must name its reviewed scope")
        receipt_ids = set()
        for receipt in editorial.get("receipts", []):
            require(isinstance(receipt, dict) and isinstance(receipt.get("id"), str) and bool(receipt["id"]), label + ": receipt identity missing")
            require(receipt.get("id") not in receipt_ids, label + ": duplicate receipt")
            receipt_ids.add(receipt["id"])
            require(receipt.get("result") in RECEIPT_RESULTS and receipt.get("scope") in {"retrieval", "field_review", "key_terms"}, label + ": invalid receipt scope/result")
            require(checked_date(receipt.get("checked_on"), label + ": receipt date") <= as_of, label + ": future receipt")
            checked_at = receipt.get("checked_at", "")
            require(isinstance(checked_at, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", checked_at)) and checked_at[:10] == receipt["checked_on"], label + ": receipt timestamp differs from its review date")
            require(datetime.fromisoformat(checked_at.replace("Z", "+00:00")) <= publication_time, label + ": receipt follows publication timestamp")
            require(bool(SHA256.fullmatch(receipt.get("response_sha256", ""))), label + ": missing response receipt")
            require(receipt.get("source_id") in available_sources, label + ": receipt source missing")
            if receipt.get("approved"):
                require(receipt["scope"] in {"field_review", "key_terms"} and receipt["result"] == "readable" and receipt.get("approval_basis") == "source_content_review", label + ": retrieval cannot approve facts")
                require(isinstance(receipt.get("reviewer"), str) and bool(receipt["reviewer"].strip()), label + ": source reviewer missing")
                require(set(receipt.get("reviewed_fields", [])) <= FIELD_NAMES and bool(receipt.get("reviewed_fields")), label + ": approved receipt has no review scope")
                require(len(receipt["reviewed_fields"]) == len(set(receipt["reviewed_fields"])), label + ": duplicate reviewed fields")
                require(bool(receipt.get("evidence")), label + ": approved receipt lacks evidence locators")
                if receipt["scope"] == "key_terms":
                    require(set(receipt["reviewed_fields"]) == FIELD_NAMES, label + ": homepage key terms require all explicit field states")
                for field in receipt["reviewed_fields"]:
                    review = reviews[field]
                    require(review["basis"] == "direct_source" and review.get("reviewed_on") == receipt["checked_on"] and receipt["source_id"] in review["source_ids"] and review["state"] != "not_researched", label + ": approved receipt does not bind its reviewed fields")
        terms_id = editorial.get("approved_terms_receipt_id")
        if terms_id:
            require(any(receipt["id"] == terms_id and receipt.get("approved") and receipt["scope"] == "key_terms" for receipt in editorial.get("receipts", [])), label + ": approved terms pointer is invalid")
        disposition = editorial.get("disposition")
        if disposition:
            require(disposition.get("state") == "historical_page_unavailable" and row.get("status") == "historical", label + ": invalid unavailable-page disposition")
            require(disposition.get("approval_basis") == "source_content_review" and bool(disposition.get("reviewer")), label + ": disposition review missing")
            require(set(disposition.get("source_ids", [])) <= available_sources and len(disposition.get("source_ids", [])) >= 2, label + ": disposition needs posting and board evidence")
            require(checked_date(disposition.get("reviewed_on"), label + ": disposition date") <= as_of, label + ": future disposition")
            require(any(item.get("result") == "not_found" and item.get("http_status") in {404, 410} for item in editorial.get("receipts", [])), label + ": unavailable page lacks a not-found receipt")
            alternative = editorial.get("alternative_destination", {})
            require(alternative.get("source_id") in available_sources and any(source.get("id") == alternative.get("source_id") and source.get("url") == alternative.get("url") for source in row.get("sources", [])), label + ": career-board alternative lacks its source binding")
    homepage = release.get("homepage", {})
    candidates = homepage.get("work_candidate_route_ids", [])
    require(bool(candidates) and len(candidates) == len(set(candidates)) and set(candidates) <= ids, "homepage candidate order is invalid")
    require(homepage.get("require_approved_key_terms_receipt") is True and homepage.get("fallback") == "browse_paid_work", "homepage fallback must require approved content reviews")
    return release


def prepare_editorial_release(work, previous_release, canonical, *, release_id, publication_as_of, canonical_sha256):
    """Stage publication identity from already reviewed facts, never monitoring output.

    No fact, check timestamp, classification date or approval is manufactured.
    Explicit inputs make repeated preparation byte-for-byte reproducible.
    """
    require(isinstance(work, dict) and isinstance(work.get("routes"), list) and work.get("status") != "candidates_only", "monitoring candidates cannot be promoted as reviewed work")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", release_id)), "invalid release_id")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", publication_as_of)), "publication_as_of must be an explicit UTC timestamp")
    require(publication_as_of[:10] == release_id.split(".", 1)[0], "publication timestamp and release date differ")
    require(canonical_sha256 == previous_release.get("canonical_sha256"), "canonical bytes changed")
    staged_work = copy.deepcopy(work)
    staged_release = copy.deepcopy(previous_release)
    staged_work["editorial_release_id"] = release_id
    for row in staged_work["routes"]:
        row["editorial_review"]["release_id"] = release_id
    staged_release.update({"release_id": release_id, "as_of": publication_as_of[:10],
                           "publication_as_of": publication_as_of, "counts": editorial_counts(staged_work)})
    staged_bytes = (json.dumps(staged_work, indent=2, ensure_ascii=False) + "\n").encode()
    staged_release["work_routes_sha256"] = hashlib.sha256(staged_bytes).hexdigest()
    validate_editorial_release(staged_work, staged_release, canonical, canonical_sha256=canonical_sha256,
                               work_sha256=hashlib.sha256(staged_bytes).hexdigest())
    return staged_work, staged_release


def load_editorial_release(path, work, canonical):
    path = Path(path)
    try:
        release = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise EditorialValidationError("editorial-work: editorial release is missing or unreadable") from error
    canonical_path = path.parent / "canonical.json"
    work_path = path.parent / "work-routes.json"
    return validate_editorial_release(
        work, release, canonical,
        canonical_sha256=hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
        work_sha256=hashlib.sha256(work_path.read_bytes()).hexdigest(),
    )
