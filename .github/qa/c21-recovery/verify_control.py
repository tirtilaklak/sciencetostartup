"""Run a portable C21 release control against the exact local artifact."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote
from urllib.request import urlopen
from release_artifact import validate_artifact

target=os.environ['QA_TARGET']
out=Path(os.environ['QA_OUTPUT']).resolve()
out.mkdir(exist_ok=False,parents=True)
manifest=os.environ['C21_MANIFEST']
head=os.environ['C21_HEAD']
tree=os.environ['C21_DIST_TREE']
origin=os.environ['QA_BASE_URL']
assert origin=='http://127.0.0.1:19011'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==head
assert subprocess.check_output(['git','rev-parse','HEAD:dist'],text=True).strip()==tree
validate_artifact(Path('dist'),manifest)

def http_bytes(path):
    with urlopen(origin+path,timeout=45) as response:
        assert response.status==200 and response.url==origin+path
        return response.read()

def identify(edge):
    body=http_bytes('/manifest.json')
    assert body==Path('dist/manifest.json').read_bytes() and sha256(body).hexdigest()==manifest
    (out/f'manifest-{edge}.json').write_bytes(body)

identify('before')
config=json.loads(Path('dist/manifest.json').read_bytes())
code=0
if target=='routes':
    rows=[]
    for path,expected in sorted(config['sha256'].items()):
        route='/'+quote(path.removesuffix('index.html') if path.endswith('/index.html') or path=='index.html' else path)
        try:
            received=sha256(http_bytes(route)).hexdigest()
            rows.append({'path':path,'route':route,'passed':received==expected,'sha256':received})
        except Exception as error:
            rows.append({'path':path,'route':route,'passed':False,'error':str(error)})
    code=int(not all(row['passed'] for row in rows))
    (out/'routes.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'signed_paths':len(rows),'passed':len([r for r in rows if r['passed']])}))
else:
    legacy=Path('.github/qa/c20-edge-controls')
    scope=legacy/target
    assert scope.is_dir() and target in {'acceptance','companies','work'}
    source=subprocess.check_output(['git','rev-parse','HEAD^'],text=True).strip()
    replacements={
        '04fd82ccf55bac9e1ed33a08564a9f816786d8c7':source,
        '8ab0452e5f0576ee9da472b79587607315c12d01':head,
        '1fe217bab088009c4fb30ca3b00987bc3291361808823d9c523729fb648015fc':manifest,
        'e4ead044f5b3419c667b':config['build_id'],
    }
    for item in scope.iterdir():
        if item.suffix not in {'.py','.json','.cjs','.sh'} or item.name=='baseline-provenance.json':
            continue
        text=item.read_text()
        for previous,next_value in replacements.items():
            text=text.replace(previous,next_value)
        item.write_text(text)
    if target=='work':
        old_work=subprocess.check_output(['git','show','8ab0452e:data/work-routes.json'])
        assert old_work==Path('data/work-routes.json').read_bytes()
    with (out/'control.log').open('x') as log:
        code=subprocess.run(['bash',str(scope/'run.sh')],stdout=log,stderr=subprocess.STDOUT,
                            timeout=1150).returncode
    reports=Path('output/c20-controls')
    if reports.is_dir():
        shutil.copytree(reports,out/'raw')
identify('after')
(out/'summary.json').write_text(json.dumps({'head':head,'dist_tree':tree,'manifest':manifest,
                                          'origin':origin,'target':target,'passed':code==0,
                                          'run':int(os.environ['GITHUB_RUN_ID'])},indent=2)+'\n')
print(json.dumps({'target':target,'passed':code==0,'head':head,'manifest':manifest}))
raise SystemExit(code)
