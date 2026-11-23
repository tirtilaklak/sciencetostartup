"""Record the actual immutable public origin and exact Git artifact for one browser control."""
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request,urlopen
from release_artifact import validate_artifact

phase,control=sys.argv[1:]
assert phase in ('before','after') and control in ('acceptance','archive','companies','work')
head='8ab0452e5f0576ee9da472b79587607315c12d01'
dist_tree='f47cbf7cf557e79bf521905082999cff33c7db70'
expected='1fe217bab088009c4fb30ca3b00987bc3291361808823d9c523729fb648015fc'
origin=os.environ['QA_BASE_URL']; assert origin=='https://2382dd9e-sciencetostartup.musaeminozdem.workers.dev'
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
assert git('rev-parse','HEAD^')==head and git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
assert git('rev-parse','HEAD:dist')==dist_tree and git('rev-parse','HEAD:tests')==git('rev-parse','HEAD^:tests')
allowed=lambda p:p=='.github/workflows/c20-immutable-controls.yml' or p.startswith('.github/qa/c20-edge-controls/')
assert all(allowed(p) for p in git('diff','--name-only','HEAD^').splitlines())
validate_artifact(Path('dist'),expected)
url=origin+'/manifest.json'
with urlopen(Request(url,headers={'User-Agent':'ScienceToStartup release verification','Cache-Control':'no-cache'}),timeout=25) as res:
    manifest=res.read(); status,final=res.status,res.geturl()
assert status==200 and final==url and sha256(manifest).hexdigest()==expected and manifest==Path('dist/manifest.json').read_bytes()
report={'http':status,'url':final,'manifest_sha256':expected,'build':json.loads(manifest)['build_id'],
        'version':'2382dd9e-ac95-4b90-a1ed-35482a0e7ba8','proof_head':git('rev-parse','HEAD'),'product_head':head,
        'dist_tree':dist_tree,'control':control,'run_id':os.environ['GITHUB_RUN_ID'],
        'utc':datetime.now(timezone.utc).isoformat()}
out=Path('output/c20-controls');out.mkdir(parents=True,exist_ok=True)
(out/f'identity-{phase}.json').write_text(json.dumps(report,indent=2)+'\n')
print(control,phase,report['build'],expected,flush=True)
