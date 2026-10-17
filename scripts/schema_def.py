"""Single editable definition of the canonical v1 JSON schema (stdlib only)."""
import json
from pathlib import Path

def string(**kw): return {"type": "string", "minLength": 1, **kw}
def enum(*values): return {"type": "string", "enum": list(values)}
def array(items, **kw): return {"type": "array", "items": items, **kw}
def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}

ID = string(pattern=r"^[a-z0-9][a-z0-9._-]*$")
DATE = string(pattern=r"^\d{4}-\d{2}-\d{2}$")
RESEARCH_DATE = string()  # Exact supplied date label or undated; never synthesized from access date.
TEXT = {"type": "string"}
CONF = enum("A", "B", "C", "U")
SCOPE = enum("company", "ai_data", "research", "other_segment")
REFS = array(ID, minItems=1, uniqueItems=True)
OPTIONAL_REFS = array(ID, uniqueItems=True)
NUMBER = {"type": "number", "minimum": 0}
METRICS = ["funding_total_reported", "funding_total_calculated", "valuation", "arr", "annualized_revenue_run_rate", "revenue", "gmv", "headcount", "expert_network", "active_paid_experts", "customer_count", "growth_rate", "other"]

TABLES = {
    "editorial_readouts": obj({"id":ID,"company_id":ID,"segment":TEXT,"readout":string(),"signal":TEXT,"claim_id":ID}),
    "companies": obj({"id": ID, "name": string(), "website": string(), "description": TEXT, "categories": array(string(), uniqueItems=True), "entity_type": enum("commercial", "adjacent_research", "unknown"), "aliases": array(string()), "legal_entity_name": string(), "founded_year": {"type":"number","minimum":1800}, "headquarters_country": string(), "headquarters_city": string(), "incorporation_country": string(), "original_scope": {"type":"boolean"}, "identity_claim_id": ID, "profile_claim_ids": OPTIONAL_REFS}, ["id","name","website","description","categories","entity_type","identity_claim_id","profile_claim_ids"]),
    "sources": obj({"id": ID, "company_id":ID, "url": string(), "title": string(), "publisher": string(), "source_type": enum("company", "customer", "investor", "filing", "independent_reporting", "database", "other"), "published_on": DATE, "accessed_on": DATE, "retrieval_status": enum("checked", "summary_only", "inaccessible", "unverified"), "evidence_chain_id": ID, "archive_url": string(), "previous_checks": {"type":"array", "items":obj({"accessed_on":DATE,"retrieval_status":enum("checked","summary_only","inaccessible","unverified")},["accessed_on","retrieval_status"])}, "notes": TEXT}, ["id", "url", "title", "publisher", "source_type", "accessed_on", "retrieval_status"]),
    "claims": obj({"id": ID, "company_id": ID, "subject": string(), "statement": string(), "as_of": RESEARCH_DATE, "observed_on": DATE, "date_note":TEXT, "raw_path":string(), "raw_pointer":string(), "segment_scope": SCOPE, "confidence": CONF, "confidence_reason": string(), "evidence_label":TEXT, "status": enum("supported", "contested", "superseded", "unverified"), "source_ids": OPTIONAL_REFS, "historical_source_ids": OPTIONAL_REFS, "contradicting_source_ids": OPTIONAL_REFS, "evidence_excerpt": TEXT, "self_reported": {"type":"boolean"}, "caveat": TEXT, "conflict_group_id": ID,"confidence_basis_claim_ids":OPTIONAL_REFS}, ["id", "company_id", "subject", "statement", "as_of", "observed_on", "segment_scope", "confidence", "confidence_reason", "status", "source_ids"]),
    "metrics": obj({"id": ID, "company_id": ID, "claim_id": ID, "segment_scope": SCOPE, "kind": enum(*METRICS), "label": string(), "value": {"type":"number"}, "upper_value": NUMBER, "qualifier": enum("exact", "approximate", "at_least", "at_most", "greater_than", "less_than", "nearly", "range"), "unit": enum("currency", "people", "percent", "count", "multiple", "other"), "currency": string(pattern=r"^[A-Z]{3}$"), "as_of": RESEARCH_DATE, "period_label":string(), "period_type":enum("annual","half","quarter","week","ttm","partial","point","unspecified"), "scope_detail":TEXT, "preferred_for_comparison":{"type":"boolean"}, "period_start": DATE, "period_end": DATE, "basis": string(), "reported_vs_estimated": enum("reported", "estimated"), "observation_status":enum("reported","forecast","talks","target"), "gross_vs_net": enum("gross", "net", "unspecified"), "comparable_series_id": ID}, ["id", "company_id", "claim_id", "segment_scope", "kind", "label", "value", "qualifier", "unit", "as_of", "basis", "reported_vs_estimated", "gross_vs_net"]),
    "products": obj({"id":ID,"company_id":ID,"claim_id":ID,"name":string(),"segment_scope":SCOPE,"delivery_model":TEXT,"work_performed":string(),"quality_method":TEXT,"buyer_type":TEXT,"modalities":array(string()),"differentiators_claimed":TEXT,"differentiators_demonstrated":TEXT},["id","company_id","claim_id","name","segment_scope","delivery_model","work_performed"]),
    "funding_rounds": obj({"id": ID, "company_id": ID, "claim_id": ID, "event_key": ID, "round_name": string(), "status": enum("closed", "announced", "talks", "rumored", "cancelled", "committed"), "announced_on": RESEARCH_DATE, "closed_on": RESEARCH_DATE, "segment_scope":SCOPE, "qualifier":enum("exact","approximate","at_least","at_most","greater_than","less_than","nearly","range"), "amount": NUMBER, "currency": string(pattern=r"^[A-Z]{3}$"), "capital_type": enum("equity", "debt", "grant", "secondary", "mixed", "undisclosed"), "amount_basis": enum("new_capital", "mixed_transaction", "cumulative_to_date", "includes_prior_round", "undisclosed"), "include_in_total": {"type": "boolean"}, "inclusion_reason": string(), "parent_round_id": ID, "include_in_disclosed_primary_sum":{"type":"boolean"}, "first_sale_on":RESEARCH_DATE, "filing_on":RESEARCH_DATE, "offering_ceiling":NUMBER, "remaining_unsold_at_filing":NUMBER, "primary_component":NUMBER, "secondary_component":NUMBER}, ["id", "company_id", "claim_id", "event_key", "round_name", "status", "announced_on", "segment_scope", "qualifier", "capital_type", "amount_basis", "include_in_total", "inclusion_reason"]),
    "company_relationships": obj({"id": ID, "company_id": ID, "related_company_id": ID, "related_entity_name":string(), "relationship": enum("brand_of", "has_brand", "subsidiary_of", "acquired_by", "formerly_known_as", "division_of"), "claim_id": ID, "as_of": DATE},["id","company_id","related_entity_name","relationship","claim_id","as_of"]),
    "people": obj({"id": ID, "name": string()}),
    "company_people": obj({"id": ID, "company_id": ID, "person_id": ID, "role": enum("founder", "cofounder", "ceo", "executive"), "claim_id": ID,"role_start":DATE,"role_end":DATE,"background_claim_ids":OPTIONAL_REFS},["id","company_id","person_id","role","claim_id"]),
    "investors": obj({"id": ID, "name": string()}),
    "round_investors": obj({"id": ID, "round_id": ID, "investor_id": ID, "role": enum("lead", "participant", "undisclosed"), "claim_id": ID}),
    "company_investors": obj({"id":ID,"company_id":ID,"investor_id":ID,"claim_id":ID,"allocation":TEXT}),
    "customer_evidence": obj({"id": ID, "company_id": ID, "organization": string(), "segment_scope": SCOPE, "relationship": enum("customer", "pilot", "partner", "claimed_customer", "research_collaborator", "displayed_logo", "former_employer", "unverified", "research_adopter", "research_citation", "implementation_partner", "grantor", "former_customer", "commissioned_evaluation", "dataset_user", "technology_vendor"), "claim_id": ID, "disclosure": enum("customer_confirmed", "company_named", "third_party", "anonymous"), "paid_status":enum("paid","unpaid","unknown"),"use_case":TEXT,"relationship_detail":TEXT,"period_label":TEXT,"production_status":enum("production","pilot","unknown")},["id","company_id","organization","segment_scope","relationship","claim_id","disclosure","paid_status"]),
    "assessments": obj({"id": ID, "company_id": ID, "segment_scope":SCOPE,"rubric_version": string(), "as_of": DATE, "reviewer": string(), "stage_limitations":string(),"material_conflict": {"type":"boolean"},"stale_source_caveat":TEXT,"headline_metric_id":ID,"business_headline":string(),"business_verdict":string(),"scope_label":string(),"scope_exclusions":array(string()),"stage_use":string(),"formal_stage_details_only":{"type":"boolean"},"raw_path":string(),"raw_pointer":string(),"gates":obj({key:obj({"level":enum("U","1","2","3"),"claim_ids":OPTIONAL_REFS,"rationale":string(),"corroboration_basis":enum("reported_buyer_statement")},["level","claim_ids","rationale"]) for key in ("P","C","R","O")})},["id","company_id","segment_scope","rubric_version","as_of","reviewer","stage_limitations","material_conflict","gates"])
}

RUBRIC = obj({
    "version": string(), "status": enum("pending", "final"), "title": string(), "notes": string(),
    "dimensions": array(obj({"id":enum("P","C","R","O"),"label":string(),"levels":obj({key:string() for key in ("1","2","3")})})),
    "stages": array(obj({"id": ID, "label": string(), "definition": string(), "minimums":obj({key:enum("1","2","3") for key in ("P","C","R","O")}, [])}))
})

SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:data-labs-observatory:schema:1.2.0", "title": "Data Labs Observatory public research", **obj({
    "schema_version": {"type":"string", "enum":["1.0.0","1.1.0","1.2.0","1.3.0"]},
    "dataset_version": string(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
    "raw_inputs": array(obj({"path": string(), "sha256": string(pattern=r"^[0-9a-f]{64}$"), "library_file_id": string(), "library_version": string(), "description": string()}, ["path", "sha256", "description"])),
    "meta": obj({"title": string(), "as_of": DATE, "scope": enum("public_company_research"), "research_status": enum("awaiting_research", "partial", "complete"), "coverage_notes": string(), "requested_companies": array(string(), uniqueItems=True)}),
    "rubric": RUBRIC,
    **{name: array(spec) for name, spec in TABLES.items()}
})}

if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "schema/observatory.schema.json"
    destination.write_text(json.dumps(SCHEMA, indent=2) + "\n")
    print(destination)
