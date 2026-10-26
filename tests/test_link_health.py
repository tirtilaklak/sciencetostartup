"""Validate minimal public availability observations and their rendering hooks."""
import ast
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import ValidationError, build, validate_link_health


class LinkHealthTests(unittest.TestCase):
    def valid(self):
        return {"version": "1.0.0", "entries": [{"url": "https://example.org/source", "status": "not_found", "checked_on": "2026-10-15"}]}

    def test_only_observed_negative_categories(self):
        for status in ["not_found", "gone", "sign_in"]:
            data = self.valid(); data["entries"][0]["status"] = status
            self.assertEqual(validate_link_health(data), data)
        for status in ["blocked", "tls_error", "javascript_only", "timeout", "ok", 404]:
            data = self.valid(); data["entries"][0]["status"] = status
            with self.assertRaises(ValidationError): validate_link_health(data)

    def test_request_data_and_private_urls_rejected(self):
        for url in ["http://localhost/source", "http://10.0.0.1/source", "http://172.20.1.1/source", "http://192.168.1.1/source", "http://169.254.169.254/source", "http://[::1]/source", "https://company.internal/source", "https://user:password@example.org/source", "file:///tmp/source", "https://example.org/source?access_token=private", "https://example.org/source?X-Amz-Credential=private"]:
            data = self.valid(); data["entries"][0]["url"] = url
            with self.assertRaises(ValidationError): validate_link_health(data)
        for field in ["request_body", "response_body", "headers", "contact", "final_url"]:
            data = self.valid(); data["entries"][0][field] = "Unnecessary metadata"
            with self.assertRaises(ValidationError): validate_link_health(data)

    def test_dates_and_duplicates_rejected(self):
        for value in ["2026-02-30", "15 Oct 2026", "2026-10-15<script>", None]:
            data = self.valid(); data["entries"][0]["checked_on"] = value
            with self.assertRaises(ValidationError): validate_link_health(data)
        data = self.valid(); data["entries"].append(copy.deepcopy(data["entries"][0]))
        with self.assertRaises(ValidationError): validate_link_health(data)

    def test_build_embeds_helper_before_app_and_exports_only_data_file(self):
        data = json.loads((ROOT / "data/canonical.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            build(data, target)
            html = (target / "index.html").read_text()
            # The data and app scripts load from js/ files in page order; check the order across them.
            html += "".join((target / src).read_text() for src in dict.fromkeys(re.findall(r'"(js/[^"]+[.]js)"', html)))
            self.assertLess(html.index("window.LINK_HEALTH="), html.index("window.linkAvailabilityHTML=url=>"))
            self.assertLess(html.index("window.linkAvailabilityHTML=url=>"), html.index("const external=(url,label)=>"))
            self.assertEqual(json.loads((target / "link-health.json").read_text()), json.loads((ROOT / "data/link-health.json").read_text()))
            self.assertFalse((target / "link-health.js").exists())
            self.assertIn("link-health.json", json.loads((target / "manifest.json").read_text())["sha256"])

    def test_vm_cues_preserve_contacts_and_claims(self):
        tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
        stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
        checks = r'''
const canonicalBefore=run('JSON.stringify(DATA)');
assert.ok(!run(`external('https://example.org/missing','Original source')`).includes('source-link-status'),'Missing helper fallback failed');
const entry=(url,status='not_found',checked_on='2026-10-15')=>({url,status,checked_on});
window.LINK_HEALTH={entries:[entry('https://example.org/missing'),entry('https://example.org/gone','gone'),entry('https://example.org/sign-in','sign_in'),...['blocked','tls_error','javascript_only'].map(status=>entry('https://example.org/'+status,status)),entry('https://example.org/invalid-date','not_found','2026-02-30'),entry('https://user:password@example.org/private'),entry('http://127.0.0.1/private'),entry('http://10.1.1.1/private'),entry('https://example.org/private?access_token=secret'),entry('https://example.org/injection','<img onerror=alert(1)>')]};
vm.runInContext(fs.readFileSync(path.join(root,'web/link-health.js'),'utf8'),context);
const cue=url=>run(`window.linkAvailabilityHTML(${JSON.stringify(url)})`);
for(const url of ['https://example.org/missing','https://example.org/gone']){
 const html=cue(url);assert.ok(html.includes('Page unavailable when checked'));assert.ok(html.includes('15 Oct 2026'));assert.ok(html.includes('<time datetime="2026-10-15">'));assert.ok(html.startsWith('<span class="source-link-status"'));assert.ok(!/<(?:details|summary|button|a)\b/.test(html),'Inline observation introduced an invalid block or extra control');assert.ok(html.includes('<span class="sr-only">Page unavailable when checked 15 Oct 2026.</span>'),'Full observation is unavailable to assistive technology');
}
{const html=cue('https://example.org/sign-in');assert.ok(html.includes('<span aria-hidden="true">Asks for sign-in · <time datetime="2026-10-15">15 Oct 2026</time></span>'));assert.ok(html.includes('<span class="sr-only">When we checked on 15 Oct 2026 without an account, the page asked us to sign in.</span>'),'Sign-in observation is unavailable to assistive technology');}
assert.equal(cue('https://example.org/missing'),cue('https://example.org/missing'),'Repeated lookups must return the same badge');
assert.equal(cue('https://example.org/missing#section'),cue('https://example.org/missing'),'A page observation should cover its fragments');
for(const url of ['https://example.org/healthy','https://example.org/blocked','https://example.org/tls_error','https://example.org/javascript_only','https://example.org/invalid-date','https://user:password@example.org/private','http://127.0.0.1/private','http://10.1.1.1/private','https://example.org/private?access_token=secret','https://example.org/injection','javascript:alert(1)'])assert.equal(cue(url),'',url+' incorrectly advertised a negative result');
for(const html of [run(`external('https://example.org/missing','Original source')`),run(`w4SourceLink('https://example.org/missing','View role')`)]){
 assert.ok(html.includes('href="https://example.org/missing"'),'Original destination changed');assert.ok(html.includes('target="_blank"'));assert.ok(html.indexOf('</a>')<html.indexOf('<span class="source-link-status"'),'Availability cue must stay outside the original anchor');
}
assert.ok(!run(`external('https://example.org/healthy','Healthy source')`).includes('source-link-status'));
assert.ok(!run(`external('https://example.org/missing','<img>')`).includes('><img>'),'Arbitrary anchor label was not escaped');
assert.equal(run('JSON.stringify(DATA)'),canonicalBefore,'Availability cues changed canonical research');
delete window.LINK_HEALTH;
vm.runInContext(fs.readFileSync(path.join(root,'web/link-health.js'),'utf8'),context);
assert.equal(cue('https://example.org/missing'),'','Missing metadata should be a silent fallback');
console.log(JSON.stringify({negative_categories:3,inconclusive_categories_unchanged:3,claims_unchanged:true,browser_verified:false}));
'''
        result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-", str(ROOT / "data/canonical.json"), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
