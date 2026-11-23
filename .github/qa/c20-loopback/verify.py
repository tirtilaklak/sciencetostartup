"""Run the planned exact browser tests on a fresh runner against a signed loopback build."""
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request,urlopen
from release_artifact import validate_artifact

spec=json.loads(Path(__file__).with_name('expected.json').read_bytes())
project=os.environ['QA_PROJECT']
assert project in ('firefox','mobile-chromium')
selected={r['id']:r for r in spec['cases'] if r['project']==project}
assert selected
output=Path('output/c20-loopback').absolute(); output.mkdir(parents=True,exist_ok=False)

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

head=git('rev-parse','HEAD'); source=git('rev-parse','HEAD^'); tree=git('rev-parse','HEAD:dist')
assert head==os.environ['GITHUB_SHA'] and source==spec['head'] and tree==spec['dist_tree']
assert set(git('diff','--name-only','HEAD^').splitlines())=={
    '.github/qa/c20-loopback/expected.json','.github/qa/c20-loopback/verify.py',
    '.github/workflows/c20-isolated-browser-proof.yml'}
assert git('rev-parse','HEAD:tests')==git('rev-parse','HEAD^:tests')
validate_artifact(Path('dist'),spec['manifest'])
assert spec['origin']=='http://127.0.0.1:19007'
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
    req=Request(address,headers={'Cache-Control':'no-cache','User-Agent':'ScienceToStartup signed loopback proof'})
    with urlopen(req,timeout=10) as r:
        content=r.read(); status,final=r.status,r.geturl()
    digest=sha256(content).hexdigest()
    assert status==200 and final==address and digest==spec['manifest'] and json.loads(content)['build_id']==spec['build']
    (output/f'manifest-{name}.json').write_bytes(content)
    return {'http':status,'url':final,'build_id':spec['build'],'manifest_sha256':digest,'utc':datetime.now(timezone.utc).isoformat()}

before=after=result=None
server_env={**os.environ,'QA_DIST':'dist'}
with (output/'server.log').open('x') as server_log:
    server=subprocess.Popen([sys.executable,'scripts/browser_qa_server.py','--port','19007'],env=server_env,stdout=server_log,stderr=subprocess.STDOUT)
    try:
        for attempt in range(25):
            if server.poll() is not None:raise RuntimeError('The signed loopback server stopped before readiness.')
            try:before=observe('before');break
            except OSError:time.sleep(.4)
        assert before
        env={**os.environ,'QA_BASE_URL':spec['origin'],'QA_DIST':'dist',
             'PLAYWRIGHT_JSON_OUTPUT_FILE':str(output/'playwright.json')}
        with (output/'playwright.log').open('x') as log:
            command=['node_modules/.bin/playwright','test','--test-list',str(planned),f'--project={project}',
                     '--workers=1','--retries=0','--reporter=json','--output',str(output/'browser-results')]
            result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=810).returncode
        after=observe('after')
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()

def cases(suite, ancestors=()):
    for row in suite.get('specs',[]):
        for outcome in row['tests']:
            yield row,outcome,ancestors
    for child in suite.get('suites',[]):
        yield from cases(child,(*ancestors,child['title']))

report=json.loads((output/'playwright.json').read_bytes())
actual=list(cases(report)); tested={}; errors=[]
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
missing=sorted(set(selected)-set(tested))
passed=result==0 and not(errors or missing) and all(case['passed'] for case in tested.values())
receipt={'github_run_id':os.environ['GITHUB_RUN_ID'],'github_run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
         'proof_branch_head':head,'product_head':source,'dist_tree':tree,'project':project,'before':before,'after':after,
         'build':spec['build'],'manifest_sha256':spec['manifest'],'passed':passed,'case_count':len(tested),
         'playwright_sha256':sha256((output/'playwright.json').read_bytes()).hexdigest(),
         'case_list_sha256':sha256(planned.read_bytes()).hexdigest(),'results':list(tested.values()),'missing':missing,
         'unexpected':errors,'returncode':result}
(output/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'project':project,'cases':len(tested),'passed':passed,'missing':len(missing),'unexpected':len(errors)}),flush=True)
raise SystemExit(not passed)
