"""Run the exact signed C20 browser cases on one immutable Worker version."""
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from uuid import UUID
from release_artifact import validate_artifact

spec=json.loads(Path(__file__).with_name('expected.json').read_bytes())
project=os.environ['QA_PROJECT']
assert spec['target']=='immutable' and project in spec['case_counts']
selected={r['id']:r for r in spec['cases'] if r['project']==project}
assert len(selected)==spec['case_counts'][project]
assert len(spec['cases'])==len({row['id'] for row in spec['cases']})==344
assert sum(spec['case_counts'].values())==344 and spec['group_slots']==354
output=Path('output/c20-immutable').absolute(); output.mkdir(parents=True,exist_ok=False)

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

head=git('rev-parse','HEAD'); source=git('rev-parse','HEAD^'); tree=git('rev-parse','HEAD:dist')
assert head==os.environ['GITHUB_SHA'] and source==spec['head'] and tree==spec['dist_tree']
assert set(git('diff','--name-only','HEAD^').splitlines())=={
    '.github/qa/c20-loopback/expected.json','.github/qa/c20-loopback/verify.py',
    '.github/workflows/c20-isolated-browser-proof.yml'}
assert git('rev-parse','HEAD:tests')==git('rev-parse','HEAD^:tests')
assert tree==git('rev-parse','HEAD^:dist')
for row in selected.values():
    assert row['fixture_blob']==git('rev-parse',f'HEAD:tests/browser/{row["file"]}')
validate_artifact(Path('dist'),spec['manifest'])
signed_manifest=Path('dist/manifest.json').read_bytes()
version=str(UUID(spec['worker_version']))
target=urlsplit(spec['origin'])
assert target.scheme=='https' and target.hostname==target.netloc and target.hostname.endswith('.workers.dev')
assert target.hostname.startswith(version.split('-')[0]+'-')
assert not (target.path or target.query or target.fragment)
address=spec['origin']+'/manifest.json'
planned=output/'test-list.txt'
lines=[]
for row in selected.values():
    assert row['suite'][0]==row['file']
    components=[f'[{project}]',row['file'],*row['suite'][1:],row['title']]
    assert all('›' not in part and '\n' not in part and '\r' not in part for part in components)
    lines.append(' › '.join(components))
assert len(set(lines))==len(selected)
planned.write_text('\n'.join(sorted(lines))+'\n')

def observe(name):
    req=Request(address,headers={'Cache-Control':'no-cache','Accept-Encoding':'identity',
                                 'User-Agent':'ScienceToStartup-ReleaseVerification/1.0'})
    with urlopen(req,timeout=25) as r:
        content=r.read(); status,final=r.status,r.geturl(); ray=r.headers.get('CF-Ray')
    digest=sha256(content).hexdigest()
    assert status==200 and final==address and content==signed_manifest
    assert digest==spec['manifest'] and json.loads(content)['build_id']==spec['build']
    (output/f'manifest-{name}.json').write_bytes(content)
    return {'http':status,'url':final,'build_id':spec['build'],'manifest_sha256':digest,
            'cf_ray':ray,'utc':datetime.now(timezone.utc).isoformat()}

before=observe('before')
raw_report=output/'playwright.json'
env={**os.environ,'QA_BASE_URL':spec['origin'],'QA_DIST':'dist','PLAYWRIGHT_JSON_OUTPUT_FILE':str(raw_report)}
command=['node_modules/.bin/playwright','test','--test-list',str(planned),f'--project={project}',
         '--workers=1','--timeout=90000','--retries=0','--reporter=json','--output',str(output/'browser-results')]
with (output/'playwright.log').open('x') as log:
    try:
        result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2040).returncode
    except subprocess.TimeoutExpired:
        result=124
        log.write('The exact browser project exceeded the hosted job execution budget.\n')
after=observe('after')

def cases(suite, ancestors=()):
    for row in suite.get('specs',[]):
        for outcome in row['tests']:
            yield row,outcome,ancestors
    for child in suite.get('suites',[]):
        yield from cases(child,(*ancestors,child['title']))

if raw_report.is_file():
    report=json.loads(raw_report.read_bytes())
    actual=list(cases(report))
    errors=[{'reporter_error':error} for error in report['errors']]
else:
    actual=[]
    errors=[{'reporter_error':'Playwright did not produce a JSON report.'}]
tested={}
for row,outcome,ancestor in actual:
    sid=row['id']; path=Path(row['file']).name; title=row['title']; expected=selected.get(sid)
    if (not expected or sid in tested or outcome['projectName']!=project or expected['file']!=path
        or expected['title']!=title or expected['suite']!=list(ancestor)):
        errors.append({'id':sid,'file':path,'title':title,'full_path':ancestor});continue
    events=outcome['results']; outcome_passed=(outcome['status']=='expected' and outcome['expectedStatus']=='passed'
                                              and len(events)==1 and events[0]['status']=='passed')
    tested[sid]={'id':sid,'file':path,'title':title,'suite':ancestor,'project':project,'passed':outcome_passed,
                 'raw_status':outcome['status'],'fixture_blob':git('rev-parse',f'HEAD:tests/browser/{path}')}
validate_artifact(Path('dist'),spec['manifest'])
assert tree==git('rev-parse','HEAD:dist') and head==git('rev-parse','HEAD')
missing=sorted(set(selected)-set(tested))
passed=result==0 and not(errors or missing) and all(case['passed'] for case in tested.values())
receipt={'target':spec['target'],'origin':spec['origin'],'worker_version':version,
         'github_run_id':os.environ['GITHUB_RUN_ID'],'github_run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
         'proof_branch_head':head,'product_head':source,'dist_tree':tree,'project':project,'before':before,'after':after,
         'build':spec['build'],'manifest_sha256':spec['manifest'],'passed':passed,'case_count':len(tested),
         'source_proof_plan_sha256':spec['source_proof_plan_sha256'],'group_slots':spec['group_slots'],
         'playwright_sha256':sha256(raw_report.read_bytes()).hexdigest() if raw_report.is_file() else None,
         'case_list_sha256':sha256(planned.read_bytes()).hexdigest(),'results':list(tested.values()),'missing':missing,
         'unexpected':errors,'returncode':result}
(output/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'project':project,'cases':len(tested),'passed':passed,'missing':len(missing),'unexpected':len(errors)}),flush=True)
raise SystemExit(not passed)
