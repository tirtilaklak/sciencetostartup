"""Synthetic frozen-reference contract attacks only; no actual research admission."""
import copy,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
PROPOSAL=Path(__file__).resolve().parents[1]
SCI=PROPOSAL
sys.path[:0]=[str(PROPOSAL/'scripts'),str(SCI/'tests'),str(SCI/'scripts')]
import screening_audit_v3 as v3
import screening_audit_v2 as v2
import test_screening_audit_v2 as old

def blob(v):return json.dumps(v,sort_keys=True,indent=2).encode()+b'\n'
def fixture():
 a,g=old.fixture();h=v3.canonical_hash('synthetic fixed reference')
 a.update(schema_version=v3.VERSION,evaluation_kind=v3.KIND)
 times={'truth_started_on':'01:00:00','truth_sealed_on':'02:00:00','membership_sealed_on':'03:00:00','reference_frozen_on':'04:00:00','method_frozen_on':'05:00:00','sut_started_on':'06:00:00','predictions_sealed_on':'07:00:00','source_checks_started_on':'08:00:00','source_checks_sealed_on':'09:00:00','outcomes_opened_on':'10:00:00','scored_on':'11:00:00'}
 a['chronology']={k:'2020-01-01T'+t+'Z' for k,t in times.items()}
 for r in a['runs']:
  if r['role'] in {'source_adjudicator','adversarial_adjudicator'}:start,end,obs='01:05:00','01:50:00','01:20:00'
  elif r['role']=='sut':start,end,obs='06:05:00','06:50:00',None
  else:start,end,obs='08:05:00','08:50:00','08:10:00'
  r.update(started_on='2020-01-01T'+start+'Z',completed_on='2020-01-01T'+end+'Z',source_observations_frozen_on=('2020-01-01T'+obs+'Z') if obs else None,predictions_opened_on='2020-01-01T08:20:00Z' if r['role']=='prediction_source_verifier' else None)
  if r['role']=='prediction_source_verifier':r['source_observations_sha256']=h
 a['limitations']+=['reuses_previously_scored_frozen_reference','sut_has_no_truth_or_prior_predictions']
 for row in a['predictions']:
  roles=['commercial_supply','entity_identity'] if row['route']=='D' else ['official_supplier_link','primary_workflow']
  row['proof_bindings']=[{'role':r,'source_ids':['synthetic-source']} for r in roles]
 old.reseal(a)
 artifacts=a['artifact_commitments'];artifacts.update(frozen_reference_truth_projection_sha256=v3.byte_hash(blob(a['truths'])),frozen_reference_membership_projection_sha256=v3.byte_hash(blob(a['selected_record_ids'])),prior_scored_repeat_sha256=h)
 a['frozen_reference']={'reference_id':'SYNTHETIC-repeat-not-research','truth_projection_sha256':artifacts['frozen_reference_truth_projection_sha256'],'membership_projection_sha256':artifacts['frozen_reference_membership_projection_sha256'],'source_packet_sha256':artifacts['source_packet_artifact_sha256'],'policy_sha256':a['method']['policy_sha256'],'prior_scored_run_sha256':h}
 return a,g

def simulated(a,g):
 ab,rb,ad=old.simulated_admitted(a,g);r=v3.load_exact(rb);r['schema_version']=v3.RECEIPT_VERSION;r['validator_code_pins']={n:v3.byte_hash((PROPOSAL/n).read_bytes()) for n in v3.CODE_FILES};r['validation_run']['validated_on']='2020-01-01T12:00:00Z';rb=blob(r)
 ad.update(schema_version=v3.ADMISSION_VERSION,receipt_sha256=v3.byte_hash(rb),validator_capsule_sha256=v3.canonical_hash(r['validator_code_pins']),reviewed_on='2020-01-01T13:00:00Z',admitted_on='2020-01-01T14:00:00Z')
 return ab,rb,ad

class FrozenReferenceControls(unittest.TestCase):
 def setUp(self):self.a,self.g=fixture()
 def errors(self):return v3._audit_errors(self.a,self.g,datetime.now(timezone.utc))[0]
 def test_reference_before_new_method_is_valid_only_in_new_version(self):
  self.assertEqual(self.errors(),[])
  self.assertTrue(v2._audit_errors(self.a,self.g,datetime.now(timezone.utc))[0])
 def test_real_thresholds_and_fixed_panel_are_unchanged(self):
  self.assertEqual(v3.FLOORS,v2.FLOORS);self.assertEqual(v3.select_screening_panel(self.a['frame'],self.a['truths']),self.a['selected_record_ids'])
 def test_fixture_simulated_trust_path_only(self):
  ab,rb,ad=simulated(self.a,self.g);errors,metrics=v3.validate_public_screening_audit(ab,self.g,rb,trusted_admission=ad);self.assertEqual(errors,[]);self.assertTrue(metrics['publication_eligible'])
 def test_missing_trust_still_holds(self):
  ab,rb,_=simulated(self.a,self.g);errors,metrics=v3.validate_public_screening_audit(ab,self.g,rb,trusted_admission=None);self.assertTrue(errors);self.assertFalse(metrics.get('publication_eligible'))
 def test_reference_must_precede_new_sut(self):
  self.a['chronology']['reference_frozen_on']='2020-01-01T06:10:00Z';self.assertTrue(self.errors())
 def test_reference_truth_may_not_be_reinvented_after_sut(self):
  self.a['chronology']['truth_sealed_on']='2020-01-01T07:10:00Z';self.assertTrue(self.errors())
 def test_prior_truth_run_keeps_actual_original_interval(self):
  self.a['runs'][1]['completed_on']='2020-01-01T08:00:00Z';self.assertTrue(self.errors())
 def test_new_sut_cannot_use_old_truth_execution_interval(self):
  self.a['runs'][0]['started_on']='2020-01-01T01:10:00Z';self.assertTrue(self.errors())
 def test_post_reference_source_cannot_rescue_prediction(self):
  self.a['sources'][0]['captured_on']='2020-01-01T04:10:00Z';self.assertTrue(self.errors())
 def test_source_packet_policy_and_metrics_must_match_preserved_reference(self):
  for key in ['source_packet_sha256','policy_sha256','prior_scored_run_sha256']:
   with self.subTest(key=key):
    original=self.a['frozen_reference'][key];self.a['frozen_reference'][key]='0'*64;self.assertTrue(self.errors());self.a['frozen_reference'][key]=original
 def test_repeat_and_exposure_disclosures_required(self):
  self.a['limitations'].remove('reuses_previously_scored_frozen_reference');self.assertTrue(self.errors())
 def test_graph_cannot_be_rebound_after_run(self):
  self.g['release_id']='changed';self.assertTrue(self.errors())
 def test_omitted_prediction_evidence_is_not_recovered(self):
  rid=self.a['selected_record_ids'][0];row=next(p for p in self.a['predictions'] if p['record_id']==rid);row['evidence']=[];old.reseal(self.a);self.assertTrue(self.errors())
 def test_failed_numeric_or_critical_checks_cannot_clear_via_repeat(self):
  for check in self.a['prediction_source_checks']:check['source_supported']=False
  self.assertFalse(v3.recompute_screening(self.a)['numerical_thresholds_met'])
  self.a['prediction_source_checks'][0]['critical_false_attribution']=True;self.assertTrue(self.errors())
 def test_primary_proof_role_is_mandatory_even_if_evidence_list_nonempty(self):
  self.a['predictions'][0]['proof_bindings']=[];old.reseal(self.a);self.assertIn('Eligible prediction omits a mandatory route proof role',self.errors())
 def test_proof_roles_cannot_point_to_uncited_or_duplicate_sources(self):
  p=self.a['predictions'][0];p['proof_bindings'][0]['source_ids']=['not-in-evidence'];old.reseal(self.a);self.assertTrue(self.errors())
 def test_semantic_source_checker_still_controls_despite_all_roles_present(self):
  rid=self.a['selected_record_ids'][0];check=next(c for c in self.a['prediction_source_checks'] if c['record_id']==rid);check['source_supported']=False;old.reseal(self.a);self.assertEqual(v3.recompute_screening(self.a)['recovered'],199)
 def test_source_checker_notes_must_precede_prediction_exposure(self):
  check=next(r for r in self.a['runs'] if r['role']=='prediction_source_verifier');check['source_observations_frozen_on']=None;self.assertTrue(self.errors())
 def test_source_checker_cannot_claim_notes_frozen_after_opening_predictions(self):
  check=next(r for r in self.a['runs'] if r['role']=='prediction_source_verifier');check['source_observations_frozen_on']='2020-01-01T08:30:00Z';self.assertTrue(self.errors())
 def test_any_known_critical_error_in_unselected_cohort_holds(self):
  selected=set(self.a['selected_record_ids']);c=next(c for c in self.a['prediction_source_checks'] if c['record_id'] not in selected);c['critical_false_attribution']=True;self.assertTrue(self.errors())
 def test_unknown_without_conclusive_attribution_stays_retained_without_forced_exclusion(self):
  selected=set(self.a['selected_record_ids']);c=next(c for c in self.a['prediction_source_checks'] if c['record_id'] not in selected);p=next(p for p in self.a['predictions'] if p['record_id']==c['record_id']);p.update(state='unknown',logical_id=None,route=None,evidence=[],proof_bindings=[]);c['critical_false_attribution']=None;old.reseal(self.a);self.assertEqual(self.errors(),[])
 def test_ordinary_task_identifier_is_not_a_credential_but_standalone_key_is(self):
  self.assertEqual(v3._safe_public('task-abcdefghijklmnop'),[]);self.assertTrue(v3._safe_public('sk-'+'a'*20))
 def test_dynamic_keys_receive_the_same_privacy_checks_as_values(self):
  for key in ['sk-'+'a'*20,'文sk-'+'a'*20,'/Users/test/private.txt','%2FUsers%2Ftest%2Fprivate.txt','private@example.invalid']:
   with self.subTest(kind=key[:2]):
    self.assertTrue(v3._safe_public({'artifacts':{key:'a'*64}}))
    self.assertTrue(v3._safe_public({'outer':[{'inner':{key:'a'*64}}]}))
  self.assertEqual(v3._safe_public({'task-abcdefghijklmnop':'a'*64}),[])
 def test_structural_diagnostics_do_not_repeat_untrusted_field_names(self):
  schema={'type':'object','additionalProperties':{'type':'string','pattern':'^[a-f0-9]{64}$'}}
  for key in ['sk-'+'b'*20,'/Users/test/private.txt','private@example.invalid']:
   with self.subTest(kind=key[:2]):
    errors=v3._shape({key:'invalid digest'},schema)
    self.assertTrue(errors);self.assertNotIn(key,str(errors));self.assertEqual(v3._safe_public(errors),[])
    closed=v3._shape({key:'a'*64},{'type':'object','additionalProperties':False})
    self.assertTrue(closed);self.assertNotIn(key,str(closed));self.assertEqual(v3._safe_public(closed),[])
 def test_checker_may_read_sources_in_parallel_but_not_open_unsealed_predictions(self):
  self.a['chronology']['source_checks_started_on']='2020-01-01T05:10:00Z';check=next(r for r in self.a['runs'] if r['role']=='prediction_source_verifier');check['started_on']='2020-01-01T05:15:00Z';check['source_observations_frozen_on']='2020-01-01T06:45:00Z';self.assertEqual(self.errors(),[]);check['predictions_opened_on']='2020-01-01T06:55:00Z';self.assertTrue(self.errors())
 def test_private_validator_authenticates_frozen_projection_bytes(self):
  h=v3.byte_hash(b'fixture');payloads={k:b'fixture' for k in self.a['artifact_commitments']};payloads['frozen_reference_truth_projection_sha256']=blob(self.a['truths']);payloads['frozen_reference_membership_projection_sha256']=blob(self.a['selected_record_ids']);self.a['artifact_commitments']['frozen_reference_truth_projection_sha256']=v3.byte_hash(payloads['frozen_reference_truth_projection_sha256']);self.a['frozen_reference']['truth_projection_sha256']=self.a['artifact_commitments']['frozen_reference_truth_projection_sha256']
  r=v3.load_exact(v3.validate_private_screening_execution(blob(self.a),self.g,expected_artifact_hashes=dict(self.a['artifact_commitments']),artifact_payloads=payloads,source_payloads={},invocation_id='synthetic-validation-extra',reviewer='synthetic',fixture=True));self.assertNotIn('Truth differs from authenticated frozen reference projection',r['validation_errors'])
  payloads['frozen_reference_truth_projection_sha256']=b'[]';r=v3.load_exact(v3.validate_private_screening_execution(blob(self.a),self.g,expected_artifact_hashes=dict(self.a['artifact_commitments']),artifact_payloads=payloads,source_payloads={},invocation_id='synthetic-validation-extra',reviewer='synthetic',fixture=True));self.assertIn('Truth differs from authenticated frozen reference projection',r['validation_errors'])
if __name__=='__main__':unittest.main()
