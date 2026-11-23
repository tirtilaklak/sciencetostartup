"""Run the complete C21 browser selection on the exact signed loopback artifact."""
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from urllib.request import Request,urlopen
from release_artifact import validate_artifact

project=os.environ['QA_PROJECT']
head=os.environ['C21_HEAD']
digest=os.environ['C21_MANIFEST']
tree=os.environ['C21_DIST_TREE']
origin='http://127.0.0.1:19011'
address=origin+'/manifest.json'
output=Path(os.environ['QA_OUTPUT']).resolve()
output.mkdir(parents=True,exist_ok=False)

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

assert git('rev-parse','HEAD')==head and git('rev-parse','HEAD:dist')==tree
old=json.loads(git('show','4b434cc5f344e7bf47983dbbd976f9fa787b187d:.github/qa/c20-loopback/expected.json'))
assert len(old['cases'])==344 and old['group_slots']==354
cases=list(old['cases'])
if project in ('chromium','mobile-chromium'):
    additions={
        'home.spec.js': ['Home opens the figure methods with JavaScript','Home opens the figure methods without JavaScript'],
        'companies-enhancement-focus.spec.js': [
            'native Companies keeps focus while its filters load',
            'native Companies keeps focus on the matching link when its saved search applies',
        ],
        'finance-evidence.spec.js':['Explore uses publisher copies while retaining the original source records'],
    }
    for file,titles in additions.items():
        cases.extend({'file':file,'title':title,'project':project,'suite':[file]} for title in titles)
selected={(row['file'],tuple(row['suite']),row['title']):row for row in cases if row['project']==project}
counts={'chromium':146,'mobile-chromium':121,'firefox':51,'webkit':14,'mobile-webkit':22}
assert len(selected)==counts[project] and sum(counts.values())==354
validate_artifact(Path('dist'),digest)
signed=Path('dist/manifest.json').read_bytes()
build=json.loads(signed)['build_id']

def observe(edge):
    with urlopen(Request(address,headers={'Cache-Control':'no-cache'}),timeout=25) as response:
        body=response.read()
        final,status=response.url,response.status
    assert status==200 and final==address and body==signed and sha256(body).hexdigest()==digest
    (output/f'manifest-{edge}.json').write_bytes(body)
    return {'http':status,'url':final,'manifest_sha256':digest,'build':build,
            'utc':datetime.now(timezone.utc).isoformat()}

before=observe('before')
plan=output/'test-list.txt'
test_lines=[' › '.join((f'[{project}]',file,*suite[1:],title)) for file,suite,title in selected]
assert len(test_lines)==len(set(test_lines))
plan.write_text('\n'.join(sorted(test_lines))+'\n')
raw=output/'playwright.json'
env={**os.environ,'QA_BASE_URL':origin,'QA_DIST':'dist','PLAYWRIGHT_JSON_OUTPUT_FILE':str(raw)}
args=['node_modules/.bin/playwright','test','--test-list',str(plan),f'--project={project}',
      '--workers=1','--timeout=90000','--retries=0','--reporter=json','--output',str(output/'results')]
with (output/'playwright.log').open('x') as log:
    code=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1420).returncode
after=observe('after')

def flatten(suite, ancestors=()):
    for record in suite.get('specs',[]):
        for outcome in record['tests']:
            yield (Path(record['file']).name,ancestors,record['title']),record['id'],outcome
    for child in suite.get('suites',[]):
        yield from flatten(child,(*ancestors,child['title']))

tested={}
report=json.loads(raw.read_bytes()) if raw.is_file() else {'errors':['missing report']}
errors=list(report['errors'])
for key,case_id,test in flatten(report):
    if key not in selected or key in tested or test['projectName']!=project:
        errors.append({'unexpected_case':key,'id':case_id})
        continue
    events=test['results']
    row={'project':project,'file':key[0],'suite':key[1],'title':key[2],'id':case_id,
         'fixture_blob':git('rev-parse',f'HEAD:tests/browser/{key[0]}')}
    row['passed']=(test['status']=='expected' and test['expectedStatus']=='passed'
                   and len(events)==1 and events[0]['status']=='passed')
    tested[key]=row
missing=sorted(set(selected)-set(tested))
passed=(code==0 and not (missing or errors) and all(row['passed'] for row in tested.values()))
validate_artifact(Path('dist'),digest)
assert git('rev-parse','HEAD')==head and git('rev-parse','HEAD:dist')==tree
receipt={'passed':passed,'origin':origin,'head':head,'dist_tree':tree,'manifest':digest,'build':build,
         'qa_head':os.environ['GITHUB_SHA'],'run':int(os.environ['GITHUB_RUN_ID']),
         'project':project,'selected':len(selected),'observed':len(tested),'before':before,'after':after,
         'missing':missing,'errors':errors,'cases':list(tested.values()),
         'raw_sha256':sha256(raw.read_bytes()).hexdigest() if raw.is_file() else None}
(output/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k not in ('cases','before','after')}))
raise SystemExit(not passed)
