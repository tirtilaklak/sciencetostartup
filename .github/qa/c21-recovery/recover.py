"""Reapply the reviewed follow-up in an isolated checkout for verification."""
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

root=Path(sys.argv[1]).resolve(strict=True)
def update(name, before, after):
    path=root/name
    source=path.read_text()
    assert source.count(before)==1, name
    path.write_text(source.replace(before,after,1))

update('web/landing.html','<a href="/method/">Read the methods</a>',
       '<a href="/method/#figures">How we check figures</a>')
renderer='scripts/research_pages.py'
update(renderer,
       '''    body += f'<p class="r-record-id">Permanent record ID: {_link(_evidence_url("assertion", aid), aid)}</p>'
''',
       '''    record_id = sp.escape(aid) if compact else _link(_evidence_url("assertion", aid), aid)
    body += f'<p class="r-record-id">Permanent record ID: {record_id}</p>'
''')
update(renderer,'"Inspect pinned sources, evidence and separate AI review receipts"', '"Sources and AI review"')
update(renderer,
       '''    if company_page:
        extra += '<link rel="stylesheet" href="/company-profile.css">\\n'
''',
       '''    if path.startswith(('/research/data/assertions/', '/research/data/sources/')):
        # Chromium can restore the scroll position before matching the fragment to :target.
        extra = ('<script>(()=>{const root=document.documentElement;'
                 'const sync=()=>root.toggleAttribute("data-ledger-fragment",'
                 '/^#(?:assertion|source)-/.test(location.hash));'
                 'sync();addEventListener("hashchange",sync);})();</script>\\n') + extra
    if company_page:
        extra += '<link rel="stylesheet" href="/company-profile.css">\\n'
''')
update('web/research.css',
       '''  /* Resolve every preceding height before a native fragment or keyboard jump.
     This also preserves native Back/Forward positions across browser engines. */
  .research:has(:target) :is(.r-assertion,.r-source,.r-source-stub),.research:has(.r-assertion:focus-within,.r-source:focus-within,.r-source-stub:focus-within) :is(.r-assertion,.r-source,.r-source-stub){content-visibility:visible;contain-intrinsic-size:none}
''',
       '''  /* Current ledger fragments need real record heights before native history restoration.
     The target and focus selectors also support script-free reading and keyboard jumps. */
  html[data-ledger-fragment] .research :is(.r-assertion,.r-source,.r-source-stub),
  .research:has(:target) :is(.r-assertion,.r-source,.r-source-stub),
  .research:has(.r-assertion:focus-within,.r-source:focus-within,.r-source-stub:focus-within) :is(.r-assertion,.r-source,.r-source-stub){
    content-visibility:visible;
    contain-intrinsic-size:none;
  }
''')
update('tests/browser/company-handoff.spec.js',
       '''      const scrollY = () => page.evaluate(() => window.scrollY);
      await fourth.evaluate(element => element.closest('[data-company-card]').scrollIntoView({ block: 'start', behavior: 'instant' }));
      const savedY = await scrollY();

      await activate(compare);
''',
       '''      const scrollY = () => page.evaluate(() => window.scrollY);
      await compare.focus();
      await fourth.evaluate(element => element.closest('[data-company-card]').scrollIntoView({ block: 'start', behavior: 'instant' }));
      const savedY = await scrollY();

      await expect(compare).toBeFocused();
      await page.keyboard.press('Enter');
''')
technical='tests/browser/technical-reading.spec.js'
def template(value):
    return value.replace('~',chr(96)).replace('^{',chr(36)+'{')
test_title=template("      test(~^{edition.name} Technical ^{name} citation opens on the first tap after Find~, async ({ page }) => {\n")
update(technical,test_title,test_title+"        const verifyLedgerLayout = edition.name === 'current' && name === 'GPQA';\n")
update(technical,
       '''        await expect(assertion).toBeInViewport();
        const sourcePath = ''',
       '''        await expect(assertion).toBeInViewport();
        if (verifyLedgerLayout) await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');
        const sourcePath = ''')
source_check=template('        await expect(page.locator(~:target[id="^{sourceId}"]~)).toBeInViewport();\n')
update(technical,
       source_check+'''
        await page.goBack();
        await expect(page).toHaveURL(assertionURL);
        await expect(assertion).toBeInViewport();
''',
       source_check+'''        if (verifyLedgerLayout) await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');

        await page.goBack();
        await expect(page).toHaveURL(assertionURL);
        if (verifyLedgerLayout) {
          await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');
          await page.evaluate(() => new Promise(resolve => {
            requestAnimationFrame(() => requestAnimationFrame(resolve));
          }));
        }
        await expect(assertion).toBeInViewport();
''')
update('tests/test_research_pages.py',
       '''                self.assertTrue(all(item.get('type') == 'application/ld+json' for item in facts.scripts))''',
       '''                markers = [item for item in facts.scripts if item.get('type') != 'application/ld+json']
                self.assertEqual(markers, [{}])
                rendered = self.page(path)
                self.assertEqual(rendered.count('data-ledger-fragment'), 1)
                self.assertLess(rendered.index('data-ledger-fragment'), rendered.index('href="/research.css"'))''')

previous=root/'dist'
published=(previous/'manifest.json').read_bytes()
assert sha256(published).hexdigest()=='1fe217bab088009c4fb30ca3b00987bc3291361808823d9c523729fb648015fc'
manifest=json.loads(published)
assets=root/'release-assets'
record=json.loads((assets/'generations.json').read_bytes())
versions=record['generations']
assert [p['cloudflare_version'] for p in versions]==[
    '9884a3b2-a66d-4919-990f-9ef8fcca8234','32be696b-d08e-4805-b565-722d4511f09f']
old={path for generation in versions for path in generation['sha256']}
active={path:checksum for path,checksum in manifest['sha256'].items()
        if path.startswith(('js/','presentation/')) and path not in old}
assert len(active)==len(versions[0]['sha256'])==49
for name,checksum in active.items():
    data=(previous/name).read_bytes()
    assert sha256(data).hexdigest()==checksum
    dest=assets/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(data)
for name in old-versions[0]['sha256'].keys():
    (assets/name).unlink()
(assets/'generations.json').write_text(json.dumps({'generations':[
    {'cloudflare_version':'2382dd9e-ac95-4b90-a1ed-35482a0e7ba8','sha256':active},versions[0]
]},indent=2)+'\n')
print('Verified 49 Worker48 runtime assets and kept all 49 Worker47 entries.')

home=root/'tests/browser/home.spec.js'
with home.open('a') as output:
    output.write("""
for (const javaScriptEnabled of [true, false]) {
  const mode = javaScriptEnabled ? 'with' : 'without';
  test('Home opens the figure methods ' + mode + ' JavaScript', async ({ browser, baseURL }) => {
    const context = await browser.newContext({ javaScriptEnabled, baseURL });
    try {
      const page = await context.newPage();
      await page.goto('/');
      await page.getByRole('link', { name: 'How we check figures', exact: true }).click();
      await expect(page).toHaveURL(/\\/method\\/#figures$/);
      const target = page.locator('#figures');
      await expect(target).toBeInViewport();
      if (javaScriptEnabled) {
        await expect(target.locator('xpath=ancestor-or-self::details[1]')).toHaveJSProperty('open', true);
      }
    } finally {
      await context.close();
    }
  });
}
""")
