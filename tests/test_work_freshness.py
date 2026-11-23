"""Native/runtime freshness labels follow the exact scoped evidence clocks."""
import copy
import gzip
import html
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import static_pages as sp


class WorkFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = json.loads((ROOT / "data/work-routes.json").read_text())
        cls.routes = {r["id"]: r for r in cls.work["routes"]}
        cls.release = json.loads((ROOT / "data/editorial-release.json").read_text())
        cls.fixtures = [
            {"id": "newer-success", "last_link_check": {"date": "2026-11-17", "result": "blocked"},
             "last_route_check": {"date": "2026-11-18", "result": "listing_content_reviewed"}},
            {"id": "newer-failure", "last_link_check": {"date": "2026-11-18", "result": "blocked"},
             "last_route_check": {"date": "2026-11-17", "result": "listing_content_reviewed"}},
            {"id": "not-found", "last_route_check": {"date": "2026-11-18", "result": "not_found"}},
            {"id": "undated-failure", "last_link_check": {"result": "blocked"}},
            {"id": "note-is-not-status", "last_route_check": {"date": "2026-11-18", "result": "readable", "note": "An earlier request was blocked."}},
            {"id": "unreviewed-is-not-pay", "field_reviews": {"pay": {"state": "not_researched", "basis": "not_reviewed", "reviewed_on": "2026-11-18"}}},
            {"id": "retained-pay-date", "terms_checked_on": "2026-10-14",
             "field_reviews": {"pay": {"state": "sourced", "basis": "stored_evidence", "reviewed_on": "2026-10-28"}}},
            {"id": "reviewed-absence", "field_reviews": {"pay": {"state": "source_not_stated", "basis": "direct_source", "reviewed_on": "2026-11-18"}}},
        ]
        script = r'''
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const context={document:{addEventListener(){},querySelectorAll(){return[]},activeElement:null,body:{}},
 window:{innerWidth:1000,addEventListener(){}},queueMicrotask(){}};
vm.createContext(context);
for(const name of ['work-core.js','work-v3.js','work-v4.js'])vm.runInContext(fs.readFileSync(process.argv[1]+'/web/'+name,'utf8'),context);
context.rows=input.routes;context.asOf=input.asOf;
process.stdout.write(vm.runInContext("JSON.stringify(Object.fromEntries(rows.map(r=>[r.id,{label:w4FreshnessLabel(r),terms:w4TermsReviewDate(r)}])))",context));
'''
        result = subprocess.run(["node", "-e", script, str(ROOT)],
                                input=json.dumps({"routes": cls.work["routes"] + cls.fixtures,
                                                  "asOf": cls.release["publication_as_of"]}),
                                text=True, capture_output=True, check=True)
        cls.runtime = json.loads(result.stdout)

    def test_all_135_native_and_runtime_labels_and_terms_dates_match(self):
        for row in self.work["routes"] + self.fixtures:
            with self.subTest(route=row["id"]):
                self.assertEqual(sp.work_freshness(row), self.runtime[row["id"]]["label"])
                self.assertEqual(sp.work_terms_review_date(row), self.runtime[row["id"]]["terms"])

    def test_current_scoped_pay_uses_its_source_date_without_renewing_full_terms(self):
        for rid in ("aixi.work.machine-learning-research-scientist", "proximal.work.frontierswe-fellowship"):
            row = self.routes[rid]
            self.assertEqual(sp.work_freshness(row), "Pay terms reviewed 18 Nov 2026")
            self.assertEqual(sp.work_terms_age(row, self.release["publication_as_of"])["state"], "not_reviewed")
        for rid in ("mercor.work.expert-network", "appen.work.sage-media"):
            row = self.routes[rid]
            self.assertEqual(sp.work_freshness(row), "Terms checked 8 Nov 2026")
            self.assertEqual(sp.work_terms_review_date(row), "2026-11-08")
        self.assertEqual(self.routes["aixi.work.machine-learning-research-scientist"]["terms_checked_on"], "2026-10-28")

    def test_failure_label_uses_actual_newest_status_and_never_publication_date(self):
        row = self.routes["turing.work.machine-learning"]
        self.assertEqual(row["last_route_check"]["result"], "blocked")
        self.assertEqual(sp.work_freshness(row), "Recheck blocked " + sp.format_date(row["last_route_check"]["date"]))
        self.assertEqual(row["last_link_check"]["date"], "2026-10-28")
        labels = {row["id"]: sp.work_freshness(row) for row in self.fixtures}
        self.assertEqual(labels["newer-success"], "Page checked 18 Nov 2026")
        self.assertEqual(labels["newer-failure"], "Recheck blocked 18 Nov 2026")
        self.assertEqual(labels["not-found"], "Recheck failed 18 Nov 2026")
        self.assertEqual(labels["undated-failure"], "Terms not rechecked")
        self.assertEqual(labels["note-is-not-status"], "Page checked 18 Nov 2026")
        self.assertEqual(labels["unreviewed-is-not-pay"], "Terms not rechecked")
        self.assertEqual(labels["retained-pay-date"], "Pay terms reviewed 28 Oct 2026")
        self.assertEqual(labels["reviewed-absence"], "Pay terms reviewed 18 Nov 2026")

    def test_native_work_keeps_all_routes_caveats_and_existing_transfer_budgets(self):
        data = json.loads((ROOT / "data/canonical.json").read_text())
        research = sp.Research(data, sp.read_js_object(ROOT / "web/app.js", "FINANCIAL_HEADLINES"),
                              json.loads((ROOT / "data/source-updates.json").read_text()),
                              say=sp.public_wording(data, sp.load_copy_edits(ROOT / "web/app.js")),
                              publication_as_of=self.release["publication_as_of"])
        before = copy.deepcopy(self.work)
        rendered = sp.render_work(research, self.work["routes"],
                                  {c["id"]: sp.clean(c["name"]) for c in data["companies"]},
                                  self.release["as_of"])
        raw = rendered.encode()
        self.assertLess(len(raw), 300_000)
        self.assertLess(len(gzip.compress(raw, mtime=0)), 45_000)
        self.assertEqual(raw.count(b'data-work-route='), 136)
        for rid in ("turing.work.machine-learning", "rws_trainai.work.polaris-asr", "invisible.work.full-stack-trainer"):
            self.assertIn(html.escape(self.routes[rid]["availability_note"]), rendered)
        self.assertEqual(self.work, before)


if __name__ == "__main__":
    unittest.main()
