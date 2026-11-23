"""Seal the already completed C21 verification on the exact PR head."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from release_artifact import validate_artifact

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('proof',type=Path)
parser.add_argument('out',type=Path)
args=parser.parse_args()
base=args.proof.resolve(strict=True)
output=args.out.resolve()
head=os.environ['C21_HEAD']
initial=os.environ['C21_INITIAL']
manifest=os.environ['C21_MANIFEST']
tree=os.environ['C21_DIST_TREE']
dist=Path('dist').resolve()

def read(path):
    return json.loads(path.read_bytes())

def git(*parts):
    return subprocess.check_output(['git',*parts],text=True).strip()

def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()

source=os.environ['C21_SOURCE']
assert git('rev-parse','HEAD')==head and git('rev-parse','HEAD:dist')==tree
assert git('rev-parse','HEAD^')==source
for directory in ('data','scripts','tests','web','release-assets'):
    assert git('rev-parse',f'{source}:{directory}')==git('rev-parse',f'{head}:{directory}')
changes=set(git('diff','--name-only',initial,head).splitlines())
assert {path for path in changes if not path.startswith('dist/')}=={
    'data/profile-content.json','tests/test_company_updates.py'}
assert all(name.startswith('dist/') for name in git('diff','--name-only',source,head).splitlines())
validate_artifact(dist,manifest)
build=read(dist/'manifest.json')['build_id']
receipts={}

def attest(path):
    receipts[str(path.relative_to(base))]=hash_file(path)
    return read(path)

projects={'chromium':147,'mobile-chromium':122,'firefox':55,'webkit':14,'mobile-webkit':22}
case_total=0
for project,count in projects.items():
    path=base/'core'/f'c21-rws-final-exact-{project}'/project/'summary.json'
    result=attest(path)
    assert result['passed'] and result['head']==head and result['dist_tree']==tree
    assert result['manifest']==manifest and result['origin']=='http://127.0.0.1:19011'
    assert result['selected']==result['observed']==len(result['cases'])==count
    assert result['before']['manifest_sha256']==result['after']['manifest_sha256']==manifest
    assert all(case['passed'] and case['project']==project for case in result['cases'])
    assert len({case['id'] for case in result['cases']})==count
    case_total+=count
assert case_total==360

rows=attest(base/'core/c21-rws-final-exact-routes/routes/routes.json')
assets=read(dist/'manifest.json')['sha256']
assert len(rows)==len(assets)==1282
assert {row['path']:row['sha256'] for row in rows if row['passed']}==assets

accept=attest(base/'core/c21-rws-final-exact-acceptance/acceptance/raw/acceptance/summary.json')
assert accept['status']=='passed'
assert {k:v['passed'] for k,v in accept['suites'].items()}=={
    'search':10,'accessibility':17,'home':48,'editorial':11}
assert all(accept['release'][phase]['sha256']==manifest for phase in ('before','after'))

work=attest(base/'core/c21-rws-final-exact-work/work/raw/work-downloads/summary.json')
assert work['passed'] and work['before']==work['after']==manifest
assert work['canonical_row_count']==136
assert {row['scope'] for row in work['downloads']}=={'native','compare','explore'}
assert len(work['downloads'])==3
assert all(row['rows']==136 and row['columns']==33 for row in work['downloads'])
assert len({row['download_sha256'] for row in work['downloads']})==1
assert all(row['ordered_ids']==work['downloads'][0]['ordered_ids'] for row in work['downloads'])
back=attest(base/'core/c21-rws-final-exact-work/work/raw/work-webkit-back/summary.json')
assert back['passed'] and back['outcomes'][0]['result']['isRoleLink']
assert all(back[phase]['manifest_sha256']==manifest for phase in ('before','after'))

companies=attest(base/'core/c21-rws-final-exact-companies/companies/raw/company-source-index.json')
assert companies['dossierCount']==55 and companies['sourceIndexCount']==1
assert [v['manifestSha256'] for v in companies['beforeAndAfterManifest']]==[manifest,manifest]
assert len(companies['sourceIndexClicks'])==1
assert companies['sourceIndexClicks'][0]['generalSources']==45
assert companies['sourceIndexClicks'][0]['workSources']==48

explore={}
for viewport in ('desktop','phone'):
    report=attest(base/'explore'/f'c21-rws-final-explore-{viewport}'/'summary.json')
    assert report['passed'] and report['head']==head and report['manifest']==manifest
    assert report['before']['sha256']==report['after']['sha256']==manifest
    assert report['destinations']==report['passedDestinations']==len(report['results'])
    assert all(row['passed'] for row in report['results'])
    assert report['destinations']==595 and report['companiesObserved']==39 and report['tabsObserved']==156
    explore[viewport]=report['destinations']

compare=attest(base/'history/compare.json')
market=attest(base/'history/market.json')
assert len(compare)==10 and all(row['passed'] and row['after']['focused'] for row in compare)
assert all(row['returnEntry']['key']==row['after']['key'] for row in compare)
assert len(market)==4 and all(row['passed'] and row['lastReaderPosition']==row['settled'] for row in market)
assert {row['navigationType'] for row in market}=={'reload','back_forward'}
assert sum(row['scrollDuringLoad'] for row in market)==2
assert hash_file(base/'history/manifest-before.json')==hash_file(base/'history/manifest-after.json')==manifest

rws=attest(base/'rws/rws-parity.json')
assert len(rws)==4 and {(row['width'],row['native']) for row in rws}=={
    (390,True),(390,False),(1280,True),(1280,False)}
expected_links=[
    'https://www.tradingview.com/news/reuters.com%2C2026-10-27%3Anewsml_RSa5108Aa%3A0-reg-rws-holdings-plc-trading-statement/',
    'https://www.lse.co.uk/rns/RWS/trading-statement-bgo38kxyahrrjkn.html?mobile_view=desktop',
]
assert all(row['passed'] and row['links']==expected_links for row in rws)
assert hash_file(base/'rws/manifest-before.json')==hash_file(base/'rws/manifest-after.json')==manifest

archived=lambda name: name.startswith(('publication/','research/editions/','daily/202'))
old=json.loads(subprocess.check_output(['git','show','2ded7d039d7605b113d1a8dac83af41dbcf3171b:dist/manifest.json']))['sha256']
archives={name:digest for name,digest in old.items() if archived(name)}
assert all(assets.get(name)==digest for name,digest in archives.items())

reports={}
summaries=[]
for path in (base/'performance').rglob('summary.json'):
    candidate=read(path)
    if isinstance(candidate,dict) and candidate.get('kind')=='mobile-performance-budget-report':
        summaries.append(path)
assert len(summaries)==1,summaries
performance_path=summaries[0]
performance=attest(performance_path)
assert performance['passed'] and performance['payloadPassed'] and not performance['consistencyProblems']
assert performance['manifestSha256']==manifest and performance['buildId']==build
assert len(performance['routes'])==24 and performance['runsPerRoute']==3
for route in performance['routes']:
    assert route['passed'] and route['complete'] and route['validRuns']==3
    for measurement in route['runReports']:
        report=performance_path.parent/measurement['report']
        digest=hash_file(report)
        assert digest==measurement['reportSha256']
        reports[str(report.relative_to(base))]=digest
assert len(reports)==72

output.mkdir(parents=True,exist_ok=False)
stage=output/'worker-prepared'
subprocess.run(['python3','scripts/release_artifact.py','prepare','--dist',str(dist),
                '--output',str(stage),'--source-commit',head],check=True)
plan=read(stage/'receipt.json')
subprocess.run(['python3','scripts/release_artifact.py','validate-prepared','--dist',str(dist),
                '--prepared',str(stage),'--expected-worker','sciencetostartup',
                '--expected-source-commit',head,'--expected-manifest-sha256',manifest,
                '--expected-plan-sha256',plan['plan_sha256']],check=True)
receipt={'pr':38,'head':head,'tested_product_head':head,'source_head':source,'dist_tree':tree,'manifest_sha256':manifest,
         'build':build,'exact_browser_journeys':case_total,'acceptance':86,
         'full_signed_paths':len(rows),'archived_paths':len(archives),'explore_destinations':explore,
         'native_company_dossiers':55,'afterquery_source_index_entries':93,'work_rows':136,'work_columns':33,
         'work_downloads':3,'webKit_work_back':True,'lighthouse_reports':len(reports),
         'ci_run':45113777996,'browser_qa_run':45113777911,'rapid_compare_checks':10,'natural_market_checks':4,'rws_link_parity_checks':4,'plan_sha256':plan['plan_sha256'],
         'provider_dispatched':False,'checked_utc':datetime.now(timezone.utc).isoformat(),
         'raw_receipts_sha256':receipts,'lighthouse_reports_sha256':reports}
(output/'release-ready.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({key:value for key,value in receipt.items() if not key.endswith('_sha256')},indent=2))
