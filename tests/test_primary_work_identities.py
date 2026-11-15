"""Synthetic native/URL identity controls; never research or coverage evidence."""
import copy,importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1];SCI=P;sys.path[:0]=[str(SCI/'tests'),str(SCI/'scripts')]
spec=importlib.util.spec_from_file_location('proposed_primary_work_graph',P/'scripts/research_graph.py');rg=importlib.util.module_from_spec(spec);spec.loader.exec_module(rg)
from test_research_graph import fixture,entity
class WorkIdentityControls(unittest.TestCase):
 def test_ceur_is_native_without_invented_arxiv_or_doi(self):
  g=fixture();g['entities'][0].update(kind='paper_work',identifiers={'ceur':'Vol-2932/invited1'});rg.validate_graph(g);self.assertEqual(rg.coverage_summary(g)['reviewed_papers'],1)
 def test_ceur_pdf_url_and_case_aliases_do_not_add_works(self):
  for value in ['https://ceur-ws.org/Vol-2932/invited1.pdf','http://www.ceur-ws.org/vol-2932/invited1.pdf','VOL-2932/INVITED1']:
   with self.subTest(value=value):
    g=fixture();g['entities'][0]['identifiers']={'ceur':'Vol-2932/invited1'};g['entities'].append(entity('duplicate',identifiers={'ceur':value},assertion_ids=[]))
    with self.assertRaisesRegex(rg.GraphValidationError,'duplicate paper work'):rg.validate_graph(g)
 def test_ceur_traversal_and_missing_publication_key_fail(self):
  for value in ['Vol-2932','vol-2932/../invited1','2932/invited1']:
   g=fixture();g['entities'][0]['identifiers']={'ceur':value}
   with self.assertRaisesRegex(rg.GraphValidationError,'CEUR volume/publication'):rg.validate_graph(g)
 def url_graph(self,url='https://example.org/Author/Study.pdf'):
  g=fixture();g['entities'][0].update(kind='paper_work',identifiers={'primary_work_url':url});g['sources'][0]['url']=url;return g
 def test_creator_primary_work_url_requires_owned_approved_source_binding(self):
  g=self.url_graph();rg.validate_graph(g);g['sources'][0]['url']='https://example.org/unrelated.pdf'
  with self.assertRaisesRegex(rg.GraphValidationError,'exact primary URL'):rg.validate_graph(g)
 def test_host_and_default_port_aliases_do_not_add_works(self):
  g=self.url_graph();g['entities'].append(entity('duplicate',kind='paper_work',identifiers={'primary_work_url':'https://EXAMPLE.ORG:443/Author/Study.pdf'},assertion_ids=[]))
  with self.assertRaisesRegex(rg.GraphValidationError,'duplicate paper work'):rg.validate_graph(g)
 def test_native_arxiv_ceur_or_doi_cannot_bypass_identity_dedup_via_url(self):
  for url in ['https://arxiv.org/pdf/2203.02155v7','https://ceur-ws.org/Vol-2932/invited1.pdf','https://doi.org/10.1234/paper']:
   with self.subTest(url=url):
    g=self.url_graph(url)
    with self.assertRaisesRegex(rg.GraphValidationError,'native work identifier'):rg.validate_graph(g)
 def test_private_or_versioned_url_selectors_do_not_become_stable_work_ids(self):
  for url in ['file:///Users/synthetic/paper.pdf','https://localhost/paper.pdf','https://example.org/paper.pdf?v=2','https://example.org/paper.pdf#p2','https://example.org/../paper.pdf','https://example.org/']:
   with self.subTest(url=url):
    g=self.url_graph(url)
    with self.assertRaises(rg.GraphValidationError):rg.validate_graph(g)
 def test_url_fallback_is_only_work_not_manifestation_or_legacy_paper_shortcut(self):
  g=self.url_graph();g['entities'][0]['kind']='paper'
  with self.assertRaisesRegex(rg.GraphValidationError,'stable credential-free primary work URL'):rg.validate_graph(g)
 def test_source_query_fragment_cannot_satisfy_exact_primary_work_binding(self):
  for suffix in ['?version=other','#different-manifestation']:
   g=self.url_graph();g['sources'][0]['url']+=suffix
   with self.assertRaisesRegex(rg.GraphValidationError,'exact primary URL'):rg.validate_graph(g)
 def test_dns_dot_encoded_host_and_traversal_cannot_bypass_native_or_stable_identity(self):
  for url in ['https://arxiv.org./pdf/2203.02155v7','https://ceur-ws.org./Vol-2932/invited1.pdf','https://example.org./Author/Study.pdf','https://%61rxiv.org/pdf/2203.02155v7','https://example.org/%2e%2e/paper.pdf','https://example.org/a paper.pdf']:
   with self.subTest(url=url):
    g=self.url_graph(url)
    with self.assertRaises(rg.GraphValidationError):rg.validate_graph(g)
 def test_excluded_version_cannot_supply_deep_primary_work_identity(self):
  g=self.url_graph();g['sources'][0]['url']='https://example.org/elsewhere.pdf';child=entity('child',kind='paper_version',parent_id='paper',disposition='excluded',assertion_ids=['child-claim']);g['entities'].append(child);a=copy.deepcopy(g['assertions'][0]);a.update(id='child-claim',subject_id='child',review_ids=[]);s=copy.deepcopy(g['sources'][0]);s.update(id='child-source',url='https://example.org/Author/Study.pdf');g['sources'].append(s);a['evidence'][0]['source_id']='child-source';g['assertions'].append(a)
  for old in list(g['reviews']):
   v=copy.deepcopy(old);v.update(id=old['id']+'-child',assertion_ids=['child-claim'],source_ids=['child-source'],assertion_sha256={'child-claim':rg.assertion_digest(a)});g['reviews'].append(v);a['review_ids'].append(v['id'])
  with self.assertRaisesRegex(rg.GraphValidationError,'exact primary URL'):rg.validate_graph(g)
if __name__=='__main__':unittest.main()
