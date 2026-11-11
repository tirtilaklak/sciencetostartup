"""Synthetic structural probes, never scholarly evidence or review receipts."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator
from test_research_graph import fixture, entity, rg, ROOT


def identity_fixture(authority='ceur'):
    graph = fixture()
    work, source = graph['entities'][0], graph['sources'][0]
    title, creators = 'Synthetic identity fixture paper', ['Synthetic Creator']
    key = 'vol-123/invited1' if authority == 'ceur' else rg.bibliographic_key(title, creators)
    work['identifiers'] = {'ceur' if authority == 'ceur' else 'bibliographic': key}
    source['url'] = 'https://ceur-ws.org/Vol-123/invited1.pdf' if authority == 'ceur' else 'https://test-university.edu/~creator/papers/paper.pdf'
    graph['entities'].append(entity('paper.v1', kind='paper_version', parent_id='paper', assertion_ids=[], identifiers={'response_sha256':source['response_sha256'], 'source_version':source['version']}))
    work['bibliographic_identity'] = {
        'authority':authority, 'key':key, 'title':title, 'creators':creators,
        'venue':'Synthetic fixture journal', 'year':2026, 'volume':'123' if authority == 'ceur' else '1', 'issue':'1',
        'identity_status':'publisher_item' if authority == 'ceur' else 'provisional_creator_copy',
        'authority_basis':'Synthetic fixture source provenance only.',
        'creator':None, 'institution':None, 'authority_source_id':None, 'authority_locator':None,
        'qualifications':['Synthetic fixture; no real identity or publication approval.'], 'identifier_aliases':{},
        'provenance':[{'source_id':'source', 'version_entity_id':'paper.v1', 'response_sha256':source['response_sha256'], 'source_version':source['version'], 'locator':'Physical page 1 / title and authors'}]}
    if authority != 'ceur':
        authority_source=copy.deepcopy(source)
        authority_source.update(id='creator-page',url='https://test-university.edu/~creator/bio.html',source_type='provider_documentation',excerpt='Synthetic Creator',excerpt_sha256=rg.digest('Synthetic Creator'),response_sha256=rg.digest(b'synthetic creator page'))
        graph['sources'].append(authority_source)
        work['bibliographic_identity'].update(creator='Synthetic Creator', institution='Synthetic Test University',authority_source_id='creator-page',authority_locator='Creator bio heading and institution')
    return graph


class BibliographicIdentityTests(unittest.TestCase):
    def assert_invalid(self, graph, message):
        with self.assertRaisesRegex(rg.GraphValidationError, message):
            rg.validate_graph(graph)

    def test_both_authority_profiles_validate_and_survive_public_exports(self):
        schema=json.loads((ROOT/'schema/research-graph.schema.json').read_text())
        for authority in ('ceur','creator_hosted_journal'):
            with self.subTest(authority=authority):
                graph=identity_fixture(authority)
                rg.validate_graph(graph)
                Draft202012Validator(schema).validate(graph)
                self.assertEqual(rg.public_graph(graph)['entities'][0]['bibliographic_identity'],graph['entities'][0]['bibliographic_identity'])
                with tempfile.TemporaryDirectory() as directory:
                    rg.write_exports(graph,Path(directory))
                    exported=json.loads((Path(directory)/'research-graph.json').read_text())
                    rg.validate_graph(exported)
                self.assertEqual(rg.coverage_summary(graph)['reviewed_papers'],1)

    def test_no_url_only_or_provenance_free_admission(self):
        for change, message in ((lambda w:w.pop('bibliographic_identity'),'provenance'),(lambda w:w['bibliographic_identity'].update(provenance=[]),'provenance'),(lambda w:w['bibliographic_identity'].update(authority='arbitrary_url'),'unknown bibliographic authority')):
            graph=identity_fixture();change(graph['entities'][0]);self.assert_invalid(graph,message)
        graph=identity_fixture();graph['sources'][0]['url']='https://mirror.example/paper.pdf'
        self.assert_invalid(graph,'official publisher')

    def test_exact_source_hash_version_parent_and_primary_evidence_required(self):
        for field,value in (('response_sha256','b'*64),('source_version','v2'),('version_entity_id','unrelated')):
            graph=identity_fixture();graph['entities'][0]['bibliographic_identity']['provenance'][0][field]=value
            self.assert_invalid(graph,'exact|belong')
        graph=identity_fixture();graph['sources'][0].update(source_type='metadata',status='metadata_only')
        self.assert_invalid(graph,'captured primary paper')

    def test_mirror_and_relabel_cannot_inflate_manifestations_or_works(self):
        graph=identity_fixture();work=graph['entities'][0];duplicate=copy.deepcopy(graph['entities'][1]);duplicate['id']='paper.mirror';duplicate['identifiers']['source_version']='relabel'
        graph['entities'].append(duplicate);proof=copy.deepcopy(work['bibliographic_identity']['provenance'][0]);proof.update(version_entity_id='paper.mirror',source_version='relabel');work['bibliographic_identity']['provenance'].append(proof)
        self.assert_invalid(graph,'inflate versions')
        graph=identity_fixture();duplicate=copy.deepcopy(graph['entities'][0]);duplicate.update(id='other',assertion_ids=[]);graph['entities'].append(duplicate)
        self.assert_invalid(graph,'duplicate paper work')
        graph=identity_fixture();graph['entities'].append(entity('paper.unbound',kind='paper_version',parent_id='paper',assertion_ids=[],identifiers={}))
        self.assert_invalid(graph,'every manifestation')

    def test_declared_cross_scheme_alias_collisions_fail_in_either_order(self):
        for reverse in (False,True):
            graph=identity_fixture();graph['entities'][0]['bibliographic_identity']['identifier_aliases']={'arxiv':'2203.02155v7'}
            graph['entities'].append(entity('other',identifiers={'arxiv':'https://arxiv.org/abs/2203.02155'},assertion_ids=[]))
            if reverse:graph['entities'].reverse()
            self.assert_invalid(graph,'alias collides')

    def test_creator_copy_key_is_content_independent_provisional_collision_guard(self):
        self.assertEqual(rg.bibliographic_key('A ‘Title’: Test',['A. Author']),rg.bibliographic_key('a title test',['a author']))
        graph=identity_fixture('creator_hosted_journal');identity=graph['entities'][0]['bibliographic_identity'];identity['key']='sha256:'+'0'*64
        self.assert_invalid(graph,'derive from title')
        graph=identity_fixture('creator_hosted_journal');graph['entities'][0]['bibliographic_identity']['identity_status']='publisher_item'
        self.assert_invalid(graph,'remain provisional')
        graph=identity_fixture('creator_hosted_journal');graph['entities'][0]['bibliographic_identity']['authority_source_id']='missing'
        self.assert_invalid(graph,'creator/institution provenance')
        graph=identity_fixture('creator_hosted_journal');graph['sources'][0]['url']='https://arbitrary.example/paper.pdf'
        self.assert_invalid(graph,'institutional directory')

    def test_identity_admission_does_not_approve_candidates_or_create_coverage(self):
        graph=identity_fixture()
        for row in graph['entities']:
            row.update(status='candidate',disposition='pending',eligible_core=False)
        graph['assertions'][0]['status']='candidate'
        self.assertEqual(rg.coverage_summary(graph)['reviewed_papers'],0)
        self.assertEqual(graph['assertions'][0]['status'],'candidate')

    def test_existing_registry_work_source_cannot_be_reused_as_another_work(self):
        graph=identity_fixture()
        graph['entities'].append(entity('other',identifiers={'arxiv':'9999.12345'},assertion_ids=['otherclaim']))
        claim=copy.deepcopy(graph['assertions'][0]);claim.update(id='otherclaim',subject_id='other',status='candidate',review_ids=[])
        graph['assertions'].append(claim)
        self.assert_invalid(graph,'already belongs to another work')

    def test_legacy_records_export_without_added_columns_or_identity_field(self):
        graph=fixture();rg.validate_graph(graph)
        self.assertNotIn('bibliographic_identity',rg.public_graph(graph)['entities'][0])
        with tempfile.TemporaryDirectory() as directory:
            rg.write_exports(graph,Path(directory))
            self.assertNotIn('bibliographic_identity',(Path(directory)/'research-entities.csv').read_text().splitlines()[0])


if __name__=='__main__':unittest.main()
