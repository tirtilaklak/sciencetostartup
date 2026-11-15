"""Invented in-memory fixtures, never actual source truth or accepted admissions."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import reference_audit_v3 as v3
import research_graph as rg
from test_research_graph import fixture as small_graph


def blob(value):
    return (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()


def fixture():
    graph=small_graph()
    template=copy.deepcopy(graph["assertions"][0])
    graph["assertions"],graph["reviews"]=[],[]
    for i in range(200):
        claim=copy.deepcopy(template)
        claim.update(id=f"SYNTHETIC.claim.{i:03d}",status="approved" if i<180 else "candidate",review_ids=[])
        claim["value"]["value"]=f"Synthetic substantive finding {i}; never research."
        if i<180:
            for role in sorted(rg.REVIEW_ROLES):
                rid=f"SYNTHETIC.original.{i:03d}.{role}"
                claim["review_ids"].append(rid)
                graph["reviews"].append({"id":rid,"assertion_ids":[claim["id"]],"role":role,
                    "reviewer":"Synthetic fixture","reviewer_type":"ai","invocation_id":rid,
                    "reviewed_on":"2026-11-08T13:00:00Z","verdict":"pass","method":"source_content_review",
                    "source_ids":["source"],"note":"Synthetic fixture, not research.",
                    "assertion_sha256":{claim["id"]:rg.assertion_digest(claim)}})
        graph["assertions"].append(claim)
    graph["entities"][0]["assertion_ids"]=[r["id"] for r in graph["assertions"]]
    exposure={"assertion_ids":["SYNTHETIC.excluded.old.finding"],"scientific_digests":[v3.canonical_hash("old scientific finding")],
        "finding_equivalence_keys":[v3.canonical_hash("old equivalence")],
        "semantic_review_sha256":v3.canonical_hash("synthetic independent exposure review"),
        "source_artifact_pins":{scope:v3.canonical_hash("SYNTHETIC fixture") for scope in ("reference250","reference226","citation62")}}
    curation=[{"assertion_id":r["id"],"disposition":"include","scope_kind":"substantive_scientific_finding",
               "finding_equivalence_sha256":v3.canonical_hash(r["id"])} for r in graph["assertions"]]
    frame=v3.build_reference_frame(graph,curation,exposure)
    selected=v3.select_reference_panel(frame)
    output=rg.public_graph(graph)
    h=v3.canonical_hash("SYNTHETIC fixture")
    method={key:h for key in ("adoption_sha256","policy_sha256","source_packet_sha256")}
    method.update(endpoint=v3.ENDPOINT,seed=v3.SEED,sut_source_sha256=v3.byte_hash((ROOT/"scripts/research_graph.py").read_bytes()),
        input_graph_sha256=v3.canonical_hash(graph),input_graph_bytes_sha256=v3.byte_hash(blob(graph)),
        output_graph_sha256=v3.canonical_hash(output))
    bindings=v3.sampled_bindings(graph,selected,{r["id"] for r in output["assertions"]})
    truth=[]
    for binding in bindings:
        decision="supported" if binding["observed_positive"] else "unsupported"
        receipts=[]
        for run,artifact in [("SYNTHETIC.source","truth_source"),("SYNTHETIC.adversarial","truth_adversarial")]:
            receipts.append({"invocation_id":run,"decision":decision,"critical_if_accepted":False,
                "scientific_sha256":binding["scientific_sha256"],"evidence":[{"source_id":"source",
                    "locator":"Synthetic source reading only","reading_scope_sha256":h}],
                "artifact_id":artifact,"entry_pointer":"/records/0","entry_sha256":h})
        truth.append({"assertion_id":binding["assertion_id"],"decision":decision,
                      "critical_if_accepted":False,"review_receipts":receipts})
    runs=[]
    for rid,role,start,end,notes in [("SYNTHETIC.sut","sut","05:00:00","05:30:00",None),
        ("SYNTHETIC.source","audit_source_adjudicator","07:00:00","07:30:00","source_notes"),
        ("SYNTHETIC.adversarial","audit_adversarial_adjudicator","07:00:00","07:30:00","adversarial_notes")]:
        runs.append({"invocation_id":rid,"role":role,"reviewer":"Synthetic fixture",
            "started_on":f"2026-11-10T{start}+00:00","completed_on":f"2026-11-10T{end}+00:00",
            "input_projection_sha256":method["input_graph_bytes_sha256"] if role=="sut" else method["source_packet_sha256"],
            "actual_execution":True,"fixture":False,"source_observations_frozen_on":None if role=="sut" else "2026-11-10T07:15:00+00:00",
            "source_observations_sha256":None if role=="sut" else h,"source_observations_artifact_id":notes,
            "blind_to_predictions_and_status":role!="sut"})
    audit={"schema_version":v3.VERSION,"kind":"reference","evaluation_kind":v3.KIND,"status":"completed",
        "actual_execution":True,"fixture":False,"release_id":graph["release_id"],"method":method,
        "method_sha256":h,"frame":frame,"frame_sha256":v3.canonical_hash(frame),
        "selected_assertion_ids":selected,"bindings":bindings,"truth":truth,"exposure_registry":exposure,
        "artifacts":{k:h for k in v3.REQUIRED_ARTIFACTS|{"truth_source","truth_adversarial","source_notes","adversarial_notes"}},
        "runs":runs,"chronology":{k:f"2026-11-10T{t}+00:00" for k,t in [
            ("method_adopted_on","01:00:00"),("input_frozen_on","02:00:00"),("frame_frozen_on","03:00:00"),
            ("panel_frozen_on","04:00:00"),("sut_started_on","05:00:00"),("predictions_sealed_on","06:00:00"),
            ("truth_started_on","07:00:00"),("truth_sealed_on","08:00:00"),("outcomes_opened_on","09:00:00"),("scored_on","10:00:00")]},
        "commitments":{},"limitations":["genuine_disposition_stratified_panel","raw_panel_metrics_not_population_estimates",
            "no_extraction_or_discovery_recall","supported_prudently_withheld_claim_is_false_negative",
            "withheld_live_bindings_require_complete_current_input"]}
    audit["artifacts"]["exposure_semantic_review"]=exposure["semantic_review_sha256"]
    return reseal(audit),graph


def reseal(audit):
    audit["method_sha256"]=v3.canonical_hash(audit["method"])
    audit["frame_sha256"]=v3.canonical_hash(audit["frame"])
    audit["commitments"]={name:v3.canonical_hash(value) for name,value in [
        ("bindings_sha256",audit["bindings"]),("truth_sha256",audit["truth"]),
        ("membership_sha256",audit["selected_assertion_ids"]) ]}
    return audit


def simulated_trust(audit):
    """Invented trusted rows only inside tests; no actual admission creator."""
    ab=blob(reseal(audit)); h=v3.canonical_hash("SYNTHETIC receipt")
    pins={name:v3.byte_hash((ROOT/name).read_bytes()) for name in v3.CODE_FILES}
    receipt={"schema_version":v3.RECEIPT_VERSION,"audit_sha256":v3.byte_hash(ab),"method_sha256":audit["method_sha256"],
        "sample_bindings_sha256":v3.canonical_hash(audit["bindings"]),"artifact_commitments_sha256":v3.canonical_hash(audit["artifacts"]),
        "source_authentication_sha256":v3.canonical_hash(sorted({p["response_sha256"] for b in audit["bindings"] for p in b["source_pins"]})),
        "validator_code_pins":pins,"validation_run":{"invocation_id":"SYNTHETIC.validator","reviewer":"Synthetic fixture",
            "validated_on":"2026-11-10T11:00:00+00:00","fixture":False,"actual_execution":True},"validation_errors":[]}
    rb=blob(receipt)
    admission={"schema_version":v3.ADMISSION_VERSION,"status":"accepted","audit_sha256":v3.byte_hash(ab),
        "receipt_sha256":v3.byte_hash(rb),"validator_capsule_sha256":v3.canonical_hash(pins),
        "validation_invocation_id":"SYNTHETIC.validator","independent_review_invocation_id":"SYNTHETIC.admitter",
        "independent_reviewer":"Synthetic fixture","independent_review_sha256":h,
        "reviewed_on":"2026-11-10T12:00:00+00:00","admitted_on":"2026-11-10T13:00:00+00:00",
        "method_adoption_sha256":audit["method"]["adoption_sha256"],
        "exposure_review_sha256":audit["exposure_registry"]["semantic_review_sha256"],"completion_authorized":True}
    return ab,rb,admission


def private_fixture(audit,graph):
    """Authenticated synthetic originals only; returned validation stays fixture."""
    payloads={"input_graph":blob(graph),"sut_output":blob(rg.public_graph(graph)),
        "source_packet":b"SYNTHETIC source-only fixture packet",
        "method_adoption":b"SYNTHETIC method adoption fixture, never actual authorization",
        "exposure_reference250":b"SYNTHETIC old250 fixture",
        "exposure_reference226":b"SYNTHETIC old226 fixture",
        "exposure_citation62":b"SYNTHETIC old62 fixture",
        "exposure_semantic_review":b"SYNTHETIC semantic review fixture",
        "source_notes":b"SYNTHETIC independent observations only",
        "adversarial_notes":b"SYNTHETIC adversarial observations only"}
    for scope in ("reference250","reference226","citation62"):
        audit["exposure_registry"]["source_artifact_pins"][scope]=v3.byte_hash(payloads["exposure_"+scope])
    audit["exposure_registry"]["semantic_review_sha256"]=v3.byte_hash(payloads["exposure_semantic_review"])
    payloads["exposure_registry"]=blob(audit["exposure_registry"])
    curation=[{"assertion_id":a["id"],"disposition":"include","scope_kind":"substantive_scientific_finding",
               "finding_equivalence_sha256":v3.canonical_hash(a["id"])} for a in graph["assertions"]]
    payloads["frame_curation"]=blob({"records":curation})
    audit["method"].update(source_packet_sha256=v3.byte_hash(payloads["source_packet"]),
        adoption_sha256=v3.byte_hash(payloads["method_adoption"]))
    for run in audit["runs"]:
        if run["role"]!="sut":
            run["input_projection_sha256"]=audit["method"]["source_packet_sha256"]
            run["source_observations_sha256"]=v3.byte_hash(payloads[run["source_observations_artifact_id"]])
    sutrun=next(r for r in audit["runs"] if r["role"]=="sut")
    execution={key:sutrun[key] for key in ("invocation_id","reviewer","started_on","completed_on","fixture","actual_execution")}
    execution.update(endpoint=v3.ENDPOINT,input_bytes_sha256=audit["method"]["input_graph_bytes_sha256"],
        **{key:audit["method"][key] for key in ("input_graph_sha256","output_graph_sha256","sut_source_sha256")})
    payloads["sut_execution"]=blob(execution)
    for rid,artifact in [("SYNTHETIC.source","truth_source"),("SYNTHETIC.adversarial","truth_adversarial")]:
        run=next(r for r in audit["runs"] if r["invocation_id"]==rid)
        records=[]
        for i,case in enumerate(audit["truth"]):
            receipt=next(r for r in case["review_receipts"] if r["invocation_id"]==rid)
            entry={"assertion_id":case["assertion_id"],**{k:receipt[k] for k in (
                "decision","critical_if_accepted","scientific_sha256","evidence")}}
            receipt.update(entry_pointer=f"/records/{i}",entry_sha256=v3.canonical_hash(entry))
            records.append(entry)
        payloads[artifact]=blob({**run,"records":records})
    audit["artifacts"]={name:v3.byte_hash(raw) for name,raw in payloads.items()}
    reseal(audit)
    rawsource=b"synthetic fixture response"
    return payloads,{v3.byte_hash(rawsource):rawsource}


class ReferenceV3Controls(unittest.TestCase):
    def setUp(self): self.audit,self.graph=fixture()
    def read(self):
        ab,rb,a=simulated_trust(self.audit)
        return v3.validate_public_reference_v3(ab,self.graph,rb,trusted_admission=a)
    def change_truth(self,aid,decision,critical=False):
        row=next(r for r in self.audit["truth"] if r["assertion_id"]==aid)
        row.update(decision=decision,critical_if_accepted=critical)
        for r in row["review_receipts"]: r.update(decision=decision,critical_if_accepted=critical)
    def test_positive_control_is_synthetic_only(self):
        errors,m=self.read(); self.assertEqual(errors,[]); self.assertEqual(m["true_positive"],180); self.assertEqual(m["true_negative"],20)
    def test_supported_withheld_is_false_negative_even_without_original_approvals(self):
        withheld=[b for b in self.audit["bindings"] if not b["observed_positive"]]
        self.assertEqual(withheld[0]["original_review_record_sha256"],{})
        for b in withheld[:11]: self.change_truth(b["assertion_id"],"supported")
        errors,m=self.read(); self.assertTrue(errors); self.assertEqual(m["false_negative"],11); self.assertLess(m["recall"],.95)
    def test_unsupported_output_is_false_positive(self):
        for b in [b for b in self.audit["bindings"] if b["observed_positive"]][:4]: self.change_truth(b["assertion_id"],"unsupported")
        errors,m=self.read(); self.assertTrue(errors); self.assertEqual(m["false_positive"],4); self.assertLess(m["precision"],.98)
    def test_gold_unknown_stays_selected_and_holds(self):
        before=list(self.audit["selected_assertion_ids"])
        self.change_truth(before[0],"unknown")
        errors,m=self.read(); self.assertTrue(errors); self.assertEqual(m["unknown"],1); self.assertEqual(before,self.audit["selected_assertion_ids"])
    def test_critical_error_holds_despite_numeric_floors(self):
        aid=next(b["assertion_id"] for b in self.audit["bindings"] if b["observed_positive"])
        self.change_truth(aid,"unsupported",True)
        errors,m=self.read(); self.assertTrue(errors); self.assertTrue(m["numerical_thresholds_met"]); self.assertEqual(m["critical_false_attributions"],1)
    def test_exposed_equivalence_and_new_seed_cannot_be_resealed(self):
        self.audit["exposure_registry"]["finding_equivalence_keys"].append(self.audit["frame"][0]["finding_equivalence_sha256"])
        errors,_=self.read(); self.assertTrue(any("Exposed" in e for e in errors))
        self.audit["exposure_registry"]["finding_equivalence_keys"].clear(); self.audit["method"]["seed"]="score tuned"
        errors,_=self.read(); self.assertTrue(any("seed" in e for e in errors))
    def test_metadata_identity_filler_rejected_at_neutral_construction(self):
        self.graph["assertions"][0]["predicate"]="version_of"
        c=[{"assertion_id":a["id"],"disposition":"include","scope_kind":"substantive_scientific_finding","finding_equivalence_sha256":v3.canonical_hash(a["id"])} for a in self.graph["assertions"]]
        with self.assertRaises(ValueError): v3.build_reference_frame(self.graph,c,self.audit["exposure_registry"])
    def test_projection_helper_executes_unchanged_function_only_on_fixture(self):
        output,run=v3.execute_reference_projection(blob(self.graph),invocation_id="SYNTHETIC.actual-code-test",reviewer="Synthetic fixture",fixture=True)
        self.assertEqual(v3.load_exact(output),rg.public_graph(self.graph)); self.assertTrue(v3.load_exact(run)["fixture"])
    def test_filtered_graph_cannot_reconstruct_mutable_withheld_bindings(self):
        self.graph=rg.public_graph(self.graph)
        errors,_=self.read(); self.assertTrue(errors)
    def test_unrelated_genuine_addition_allowed_but_sample_change_held(self):
        extra=copy.deepcopy(self.graph["assertions"][-1]); extra["id"]="SYNTHETIC.unrelated.candidate"
        self.graph["assertions"].append(extra); self.graph["entities"][0]["assertion_ids"].append(extra["id"])
        errors,_=self.read(); self.assertEqual(errors,[])
        self.graph["assertions"][-2]["qualifications"].append("Changed true scientific scope")
        errors,_=self.read(); self.assertTrue(errors)
    def test_source_capture_original_binding_cannot_change(self):
        self.graph["sources"][0]["captured_on"]="2026-11-08T11:59:59Z"
        errors,_=self.read(); self.assertTrue(errors)
    def test_no_admission_from_numeric_success_and_no_threshold_lowering(self):
        ab,rb,a=simulated_trust(self.audit)
        errors,_=v3.validate_public_reference_v3(ab,self.graph,rb,trusted_admission=None); self.assertTrue(errors)
        errors,_=v3.validate_public_reference_v3(ab,self.graph,rb,trusted_admission=a,thresholds={"reference_recall":.94}); self.assertTrue(errors)
    def test_duplicate_disclosures_cannot_hide_scope_limits(self):
        self.audit["limitations"]=[self.audit["limitations"][0]]*5
        errors,_=self.read(); self.assertTrue(any("five distinct" in e for e in errors))
    def test_private_missing_originals_and_sources_remain_holds(self):
        receipt=v3.load_exact(v3.validate_private_reference_v3(blob(self.audit),self.graph,
            expected_artifact_hashes=dict(self.audit["artifacts"]),artifact_payloads={},source_payloads={},
            invocation_id="SYNTHETIC.private-validator",reviewer="Synthetic fixture",fixture=True))
        self.assertTrue(any("Original artifact authentication failed: input_graph" in e for e in receipt["validation_errors"]))
        self.assertTrue(any("Original artifact authentication failed: sut_output" in e for e in receipt["validation_errors"]))
        self.assertTrue(any("raw primary-source" in e for e in receipt["validation_errors"]))
        self.assertTrue(receipt["validation_run"]["fixture"])
    def test_authenticated_private_fixture_then_tampered_original_truth_projection(self):
        payloads,sources=private_fixture(self.audit,self.graph)
        expected=dict(self.audit["artifacts"])
        def validate():
            return v3.load_exact(v3.validate_private_reference_v3(blob(reseal(self.audit)),self.graph,
                expected_artifact_hashes=expected,artifact_payloads=payloads,source_payloads=sources,
                invocation_id="SYNTHETIC.private-validator",reviewer="Synthetic fixture",fixture=True))
        clean=validate()
        self.assertEqual(clean["validation_errors"],[])
        self.assertTrue(clean["validation_run"]["fixture"])
        withheld=next(b["assertion_id"] for b in self.audit["bindings"] if not b["observed_positive"])
        self.change_truth(withheld,"supported")
        changed=validate()
        self.assertTrue(any("exact original independent decision entry" in e for e in changed["validation_errors"]))
        payloads["sut_output"]+=b" "
        changed=validate()
        self.assertTrue(any("Original artifact authentication failed: sut_output" in e for e in changed["validation_errors"]))


if __name__=="__main__": unittest.main()
