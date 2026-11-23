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

assert git('rev-parse','HEAD')==head and git('rev-parse','HEAD:dist')==tree
for directory in ('dist','data','scripts','web','release-assets'):
    assert git('rev-parse',f'{initial}:{directory}')==git('rev-parse',f'{head}:{directory}')
differences=set(git('diff','--name-only',initial,head).splitlines())
assert differences=={'tests/browser/performance-reading.spec.js','tests/browser/research-enhancements.spec.js'}
validate_artifact(dist,manifest)
build=read(dist/'manifest.json')['build_id']
receipts={}

def attest(path):
    receipts[str(path.relative_to(base))]=hash_file(path)
    return read(path)

projects={'chromium':146,'mobile-chromium':121,'firefox':51,'webkit':14,'mobile-webkit':22}
case_total=0
for project,count in projects.items():
    path=base/'core'/f'c21-exact-{project}'/project/'summary.json'
    result=attest(path)
    assert result['passed'] and result['head']==initial and result['dist_tree']==tree
    assert result['manifest']==manifest and result['origin']=='http://127.0.0.1:19011'
    assert result['selected']==result['observed']==len(result['cases'])==count
    assert result['before']['manifest_sha256']==result['after']['manifest_sha256']==manifest
    assert all(case['passed'] and case['project']==project for case in result['cases'])
    assert len({case['id'] for case in result['cases']})==count
    case_total+=count
assert case_total==354

rows=attest(base/'core/c21-exact-routes/routes/routes.json')
assets=read(dist/'manifest.json')['sha256']
assert len(rows)==len(assets)==1282
assert {row['path']:row['sha256'] for row in rows if row['passed']}==assets

accept=attest(base/'core/c21-exact-acceptance/acceptance/raw/acceptance/summary.json')
assert accept['status']=='passed'
assert {k:v['passed'] for k,v in accept['suites'].items()}=={
    'search':10,'accessibility':17,'home':48,'editorial':11}
assert all(accept['release'][phase]['sha256']==manifest for phase in ('before','after'))

work=attest(base/'work/work/raw/work-downloads/summary.json')
assert work['passed'] and work['before']==work['after']==manifest
assert work['canonical_row_count']==136
assert {row['scope'] for row in work['downloads']}=={'native','compare','explore'}
assert len(work['downloads'])==3
assert all(row['rows']==136 and row['columns']==33 for row in work['downloads'])
assert len({row['download_sha256'] for row in work['downloads']})==1
assert all(row['ordered_ids']==work['downloads'][0]['ordered_ids'] for row in work['downloads'])
back=attest(base/'work/work/raw/work-webkit-back/summary.json')
assert back['passed'] and back['outcomes'][0]['result']['isRoleLink']
assert all(back[phase]['manifest_sha256']==manifest for phase in ('before','after'))

companies=attest(base/'companies/companies/raw/company-source-index.json')
assert companies['dossierCount']==55 and companies['sourceIndexCount']==1
assert [v['manifestSha256'] for v in companies['beforeAndAfterManifest']]==[manifest,manifest]
assert len(companies['sourceIndexClicks'])==1
assert companies['sourceIndexClicks'][0]['generalSources']==45
assert companies['sourceIndexClicks'][0]['workSources']==48

explore={}
for viewport in ('desktop','phone'):
    report=attest(base/'explore'/f'c21-loaded-profile-sections-{viewport}'/'summary.json')
    assert report['passed'] and report['head']==head and report['manifest']==manifest
    assert report['before']['sha256']==report['after']['sha256']==manifest
    assert report['destinations']==report['passedDestinations']==len(report['results'])
    assert all(row['passed'] for row in report['results'])
    assert report['destinations']==595 and report['companiesObserved']==39 and report['tabsObserved']==156
    explore[viewport]=report['destinations']

archived=lambda name: name.startswith(('publication/','research/editions/','daily/202'))
old=json.loads(subprocess.check_output(['git','show','2ded7d039d7605b113d1a8dac83af41dbcf3171b:dist/manifest.json']))['sha256']
archives={name:digest for name,digest in old.items() if archived(name)}
assert all(assets.get(name)==digest for name,digest in archives.items())

reports={}
for file in (base/'performance').rglob('*.json'):
    try:
        data=read(file)
    except (ValueError,OSError):
        continue
    if not isinstance(data,dict) or 'lighthouseVersion' not in data or 'categories' not in data:
        continue
    reports[str(file.relative_to(base))]=hash_file(file)
assert len(reports)==72, len(reports)

output.mkdir(parents=True,exist_ok=False)
stage=output/'worker-prepared'
subprocess.run(['python3','scripts/release_artifact.py','prepare','--dist',str(dist),
                '--output',str(stage),'--source-commit',head],check=True)
plan=read(stage/'receipt.json')
subprocess.run(['python3','scripts/release_artifact.py','validate-prepared','--dist',str(dist),
                '--prepared',str(stage),'--expected-worker','sciencetostartup',
                '--expected-source-commit',head,'--expected-manifest-sha256',manifest,
                '--expected-plan-sha256',plan['plan_sha256']],check=True)
receipt={'pr':38,'head':head,'tested_product_head':initial,'dist_tree':tree,'manifest_sha256':manifest,
         'build':build,'exact_browser_journeys':case_total,'acceptance':86,
         'full_signed_paths':len(rows),'archived_paths':len(archives),'explore_destinations':explore,
         'native_company_dossiers':55,'afterquery_source_index_entries':93,'work_rows':136,'work_columns':33,
         'work_downloads':3,'webKit_work_back':True,'lighthouse_reports':len(reports),
         'ci_run':45103074014,'browser_qa_run':45103073995,'plan_sha256':plan['plan_sha256'],
         'provider_dispatched':False,'checked_utc':datetime.now(timezone.utc).isoformat(),
         'raw_receipts_sha256':receipts,'lighthouse_reports_sha256':reports}
(output/'release-ready.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({key:value for key,value in receipt.items() if not key.endswith('_sha256')},indent=2))
