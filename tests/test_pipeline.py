import copy
import hashlib
import itertools
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "scripts"))
from observatory import validate, ValidationError, classify, stage_confidence, release, build, safe_csv, canonical_bytes
from fixtures import fixture

class PipelineTests(unittest.TestCase):
    def setUp(self): self.data=fixture()
    def rejected(self):
        with self.assertRaises(ValidationError): validate(self.data)
    def test_valid_normalized_research(self): validate(self.data)
    def test_unknown_fields_and_private_data_rejected(self):
        self.data["companies"][0]["application_status"]="applied"
        self.rejected()
    def test_missing_evidence_rejected(self):
        self.data["claims"][0]["source_ids"]=[]
        self.rejected()
    def test_unverified_not_treated_as_supported(self):
        self.data["claims"][0]["confidence"]="U"
        self.rejected()
    def test_missing_foreign_key(self):
        self.data["metrics"][0]["claim_id"]="missing"
        self.rejected()
    def test_wrong_segment_reference(self):
        self.data["metrics"][0]["segment_scope"]="company"
        self.rejected()
    def test_revenue_requires_period(self):
        self.data["metrics"][0]["kind"]="revenue"
        self.rejected()
    def test_arr_stays_separate_from_run_rate(self):
        row=copy.deepcopy(self.data["metrics"][0]);row.update(id="test-run-rate",kind="annualized_revenue_run_rate")
        self.data["metrics"].append(row)
        validate(self.data)
    def test_expert_network_not_employee_count(self):
        self.data["metrics"][0].update(kind="expert_network")
        self.rejected()
    def test_nonfinite_number(self):
        self.data["metrics"][0]["value"]=float('nan')
        self.rejected()
    def test_invalid_date(self):
        self.data["sources"][0]["accessed_on"]="2026-02-30"
        self.rejected()
    def test_future_evidence(self):
        self.data["claims"][0]["as_of"]="2027-01-01"
        self.rejected()
    def test_unsafe_source_url(self):
        self.data["sources"][0]["url"]="javascript:alert(1)"
        self.rejected()
    def test_duplicate_funding_event(self):
        row=copy.deepcopy(self.data["funding_rounds"][0]);row["id"]="test-duplicate"
        self.data["funding_rounds"].append(row)
        self.rejected()
    def test_talks_not_closed_capital(self):
        row=self.data["funding_rounds"][0];row["status"]="talks";row.pop("closed_on")
        self.rejected()
    def test_cumulative_round_not_new_capital(self):
        self.data["funding_rounds"][0]["amount_basis"]="cumulative_to_date"
        self.rejected()
    def test_secondary_excluded_from_totals(self):
        self.data["funding_rounds"][0]["capital_type"]="secondary"
        self.rejected()
    def test_self_parent_rejected(self):
        self.data["company_relationships"]=[{"id":"test-parent","company_id":"test-alpha","related_company_id":"test-alpha","related_entity_name":"Test self","relationship":"brand_of","claim_id":"test-identity","as_of":"2026-10-01"}]
        self.rejected()
    def test_gate_requires_evidence(self):
        self.data["assessments"][0]["gates"]["P"]["claim_ids"]=[]
        self.rejected()
    def test_c3_requires_independent_evidence(self):
        self.data["claims"][0]["confidence"]="B"
        self.rejected()
    def test_unknown_remains_unknown(self):
        self.data["assessments"][0]["gates"]["P"]={"level":"U","claim_ids":[],"rationale":"Not established."}
        validate(self.data)
        self.assertEqual(classify(self.data,"test-alpha"),"insufficient_public_evidence")
        self.assertEqual(stage_confidence(self.data,"test-alpha"),"unclassified")
    def test_pending_differs_from_insufficient(self):
        self.data["assessments"]=[]
        self.assertEqual(classify(self.data,"test-alpha"),"pending")
    def test_no_cross_segment_assessment(self):
        self.assertEqual(classify(self.data,"test-alpha","company"),"pending")
    def test_adjacent_is_not_commercial(self):
        self.data["companies"][0]["entity_type"]="adjacent_research";self.data["assessments"]=[]
        validate(self.data)
        self.assertEqual(classify(self.data,"test-alpha"),"not_applicable")
    def test_exhaustive_256_stage_combinations(self):
        for p,c,r,o in itertools.product(["U","1","2","3"],repeat=4):
            for dim,level in zip('PCRO',(p,c,r,o)): self.data["assessments"][0]["gates"][dim]["level"]=level
            known=lambda v,n:v!='U' and int(v)>=n
            expected=("established_commercial_evidence" if known(p,2) and known(c,3) and known(r,3) and known(o,2) else "repeatable_commercial_evidence" if all(known(v,2) for v in (p,c,r,o)) else "demonstrated_delivery" if known(p,2) and known(c,2) else "visible_operating_offer" if known(p,1) and known(o,1) else "insufficient_public_evidence")
            self.assertEqual(classify(self.data,"test-alpha"),expected,(p,c,r,o))
    def test_confidence_and_staleness(self):
        self.assertEqual(stage_confidence(self.data,"test-alpha"),"high")
        self.data["assessments"][0]["stale_source_caveat"]="Historical evidence."
        self.assertEqual(stage_confidence(self.data,"test-alpha"),"medium")
        self.data["assessments"][0]["material_conflict"]=True
        self.assertEqual(stage_confidence(self.data,"test-alpha"),"low_provisional")
    def test_pending_rubric_prohibits_scoring(self):
        self.data["rubric"]["status"]="pending"
        self.rejected()
    def test_csv_formula_injection(self):
        for value in ['=HYPERLINK("bad")',' +1','-1','@SUM(A1)','\ttext']:
            self.assertTrue(safe_csv(value).startswith("'"))
    def test_embedded_data_cannot_close_script(self):
        self.data["companies"][0]["description"]='</script><script>window.PWNED=1</script>'
        with tempfile.TemporaryDirectory() as tmp:
            build(self.data,Path(tmp))
            html=(Path(tmp)/'index.html').read_text()
            self.assertNotIn('</script><script>window.PWNED',html)
    def test_database_relations_round_sums_and_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            build(self.data,Path(tmp))
            con=sqlite3.connect(Path(tmp)/'observatory.sqlite')
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(con.execute('SELECT observed_round_sum FROM distinct_new_capital').fetchone()[0],1000000)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM claim_sources').fetchone()[0],1)
            self.assertEqual(json.loads(con.execute('SELECT canonical_json FROM dataset').fetchone()[0]),self.data)
            self.assertEqual(con.execute("SELECT stage FROM classifications WHERE segment_scope='ai_data'").fetchone()[0],classify(self.data,'test-alpha'))
            con.close()
    def test_failed_import_preserves_prior_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.json';source.write_bytes(canonical_bytes(self.data))
            release(source,root)
            prior=(root/'dist/research.json').read_bytes()
            self.data['metrics'][0]['claim_id']='missing';source.write_bytes(canonical_bytes(self.data))
            with self.assertRaises(ValidationError): release(source,root)
            self.assertEqual((root/'dist/research.json').read_bytes(),prior)
    def test_versions_immutable_and_build_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.json';source.write_bytes(canonical_bytes(self.data))
            release(source,root);first=(root/'dist/manifest.json').read_bytes();release(source,root)
            self.assertEqual(first,(root/'dist/manifest.json').read_bytes())
            self.data['meta']['coverage_notes']='Changed';source.write_bytes(canonical_bytes(self.data))
            with self.assertRaises(ValidationError): release(source,root)
    def test_raw_input_digest_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.json'
            self.data['raw_inputs']=[{'path':'data/raw/missing.json','sha256':'0'*64,'description':'test'}]
            source.write_bytes(canonical_bytes(self.data))
            with self.assertRaises(ValidationError): release(source,root)

if __name__=='__main__': unittest.main()
