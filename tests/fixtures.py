"""Fictional test-only records; never loaded into deliverable research data."""
import copy
import json
from pathlib import Path

def fixture():
    data = json.loads((Path(__file__).resolve().parents[1] / "data/canonical.json").read_text())
    for key,value in list(data.items()):
        if isinstance(value,list): data[key]=[]
    data.setdefault("company_investors", [])
    data["dataset_version"]="0.0.1"
    data["meta"]["research_status"]="partial"
    data["sources"]=[{"id":"test-source","url":"https://example.org/test-only","title":"Fictional test evidence","publisher":"Test buyer","source_type":"customer","accessed_on":"2026-10-12","retrieval_status":"checked"}]
    data["companies"]=[{"id":"test-alpha","name":"TEST ONLY Alpha","website":"https://example.org","description":"Fictional test fixture, not research.","categories":["Test category"],"entity_type":"commercial","identity_claim_id":"test-identity","profile_claim_ids":[]}]
    data["claims"]=[{"id":"test-identity","company_id":"test-alpha","subject":"identity","statement":"Fictional test evidence, not a company fact.","as_of":"2026-10-01","observed_on":"2026-10-12","segment_scope":"ai_data","confidence":"A","confidence_reason":"Test fixture only.","status":"supported","source_ids":["test-source"]}]
    data["metrics"]=[{"id":"test-metric","company_id":"test-alpha","claim_id":"test-identity","segment_scope":"ai_data","kind":"arr","label":"Test ARR","value":1200000,"qualifier":"approximate","unit":"currency","currency":"USD","as_of":"2026-10-01","basis":"Fictional test basis","reported_vs_estimated":"reported","gross_vs_net":"unspecified"}]
    data["funding_rounds"]=[{"id":"test-round","company_id":"test-alpha","claim_id":"test-identity","event_key":"test-series-a-2025","round_name":"Test round","status":"closed","segment_scope":"ai_data","qualifier":"exact","announced_on":"2025-06-02","closed_on":"2025-05-30","amount":1000000,"currency":"USD","capital_type":"equity","amount_basis":"new_capital","include_in_total":True,"inclusion_reason":"Test-only distinct round."}]
    data["assessments"]=[{"id":"test-assessment","company_id":"test-alpha","segment_scope":"ai_data","rubric_version":"1.0.0","as_of":"2026-10-12","reviewer":"Automated test fixture","stage_limitations":"Synthetic test only.","material_conflict":False,"gates":{dim:{"level":"3","claim_ids":["test-identity"],"rationale":"Test-only evidence."} for dim in ("P","C","R","O")}}]
    return copy.deepcopy(data)
