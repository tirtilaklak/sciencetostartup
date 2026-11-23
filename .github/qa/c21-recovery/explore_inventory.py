"""Inventory the Explore destinations linked by the signed public artifact."""
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import collections
import json
import os
import runpy

root=Path.cwd()
support=runpy.run_path(str(root/'tests/test_internal_links.py'))
dist=root/'dist'
manifest=(dist/'manifest.json').read_bytes()
assert sha256(manifest).hexdigest()==os.environ['C21_MANIFEST']
entries=json.loads(manifest)['sha256']
routes=collections.defaultdict(set)
for name in sorted(entries):
    path=dist/name
    if name.endswith('.html'):
        links=support['Document'](path.read_text()).links
    elif name.endswith('.xml'):
        links=support['xml_links'](path.read_bytes())
    else:
        continue
    for link in links:
        target=urlsplit(urljoin(support['ORIGIN']+support['document_path'](name),link))
        if target.hostname in support['HOSTS'] and target.path.rstrip('/')=='/explore' and target.fragment:
            route=target.fragment
            if route.partition('?')[0].partition('/')[0].lower() in support['EXPLORE_ROUTES']:
                routes[route].add(name)
assert routes, 'The exact artifact did not enumerate any authored Explore routes'
report={'head':os.environ['C21_HEAD'],'manifest':os.environ['C21_MANIFEST'],'routes':{
    route:sorted(paths) for route,paths in sorted(routes.items())
}}
Path(os.environ['QA_EXPLORE_INVENTORY']).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'authored_explore_destinations':len(routes)}))
