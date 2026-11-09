"""Thin browse models preserve the full renderer's choices and evidence boundaries."""
import copy
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import INITIAL_PRESENTATION_JS, PRESENTATION_JS, write_business_health_module
from presentation import (build_presentation, company_summaries, compact_work,
                          current_company_result, health_skeleton, source_updates_context,
                          work_search_text)
from static_pages import work_terms_age
from test_static_pages import APP_RULES


class PresentationProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def read(name):
            return json.loads((ROOT / "data" / name).read_text())
        cls.data = read("canonical.json")
        profiles = read("profile-content.json")
        afterquery = read("profile-afterquery.json")
        profiles["entries"] = [entry for entry in profiles["entries"] if entry["company_id"] != "afterquery"] + [afterquery]
        cls.sidecars = dict(EDITORIAL=read("editorial.json"), PROFILE_CONTENT=profiles,
                           COMPANY_EVENTS=read("company-events.json"), WORK_ROUTES=read("work-routes.json"),
                           SOURCE_UPDATES=read("source-updates.json"), BUSINESS_HEALTH=read("business-health.json"))
        cls.summaries, cls.products, cls.research = company_summaries(cls.data, cls.sidecars, ROOT)
        cls.lean = compact_work(cls.sidecars["WORK_ROUTES"], cls.research)
        cls.temporary = tempfile.TemporaryDirectory(prefix="presentation-projections-")
        cls.destination = Path(cls.temporary.name)
        cls.summary, _ = build_presentation(cls.data, cls.destination, ROOT, cls.sidecars, read("editorial-release.json"))
        # Execute the full production selectors in tests only. The Python builder never needs Node.
        script = APP_RULES.replace("const document={", "window.BUSINESS_HEALTH=json('data/business-health.json');\nconst document={")
        script = script.replace("return r;", """
 r.projections=Object.fromEntries(DATA.companies.map(c=>[c.id,{firstOffering:profileProducts(c.id).find(p=>p.name)?.name||null,hasFinancial:Boolean(preferredFinancial(c.id)),currentCompanyResult:currentCompanyResult(c.id)}]));
 const savedFinancialFilter=state.financial;state.financial=true;r.financialFilter=filtered().map(c=>c.id);state.financial=savedFinancialFilter;
 download=(name,body,type)=>{r.companyCsv=body;};exportCsv();
 r.profileProducts=Object.fromEntries(DATA.companies.map(c=>[c.id,profileProducts(c.id)]));
 const active=DATA.claims.filter(c=>c.status!=='superseded');r.researchStatistics={companies:DATA.companies.length,sources:DATA.sources.length,sourcePages:new Set(DATA.sources.map(s=>s.url)).size,claims:DATA.claims.length,currentClaims:active.length,gradeCounts:Object.fromEntries(['A','B','C','U'].map(g=>[g,active.filter(c=>c.confidence===g).length])),openUnknowns:active.filter(c=>c.subject==='unknowns'&&c.confidence==='U').length,supersededClaims:DATA.claims.length-active.length,companySources:DATA.sources.filter(s=>s.source_type==='company').length};
 const savedHealth=window.BUSINESS_HEALTH;window.BUSINESS_HEALTH={};r.metricOnlyResults=Object.fromEntries(DATA.companies.map(c=>[c.id,currentCompanyResult(c.id)]));window.BUSINESS_HEALTH=savedHealth;
 r.workProjection=Object.fromEntries(window.WORK_ROUTES.routes.map(w=>[w.id,{uncertain:w4Uncertain(w),source_action:w4Action(w),search:w4SearchText(w)}]));
 r.termsAge=Object.fromEntries(window.WORK_ROUTES.routes.map(w=>[w.id,['2026-11-07','2026-11-08','2026-11-21','2026-11-22','2026-11-23T01:00:00Z'].map(day=>w4TermsAge(w,day))]));
 r.companySearch=Object.fromEntries(DATA.companies.map(c=>[c.id,[c.name,...(c.aliases||[]),c.description,modelFor(c.id),...DATA.products.filter(p=>p.company_id===c.id).flatMap(p=>[p.name,p.work_performed]),...profileProducts(c.id).flatMap(p=>[p.name,p.description,...(p.aliases||[])])].filter(Boolean).join(' ').toLowerCase()]));
 return r;""")
        modules = ["web/app.js", "web/editorial.js", "web/work-v3.js"] + ["web/" + name for name in PRESENTATION_JS]
        node = shutil.which("node")
        if not node:
            raise AssertionError("Node is required for independent full-JS selector parity tests")
        result = subprocess.run([node, "-e", script, str(ROOT), json.dumps(modules)], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.full_js = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_39_current_company_csv_results_match_full_data_js(self):
        self.assertEqual(len(self.summaries), 39)
        for cid, summary in self.summaries.items():
            with self.subTest(company=cid):
                self.assertEqual(summary["currentCompanyResult"], self.full_js["projections"][cid]["currentCompanyResult"])
                self.assertEqual(summary["hasFinancial"], self.full_js["projections"][cid]["hasFinancial"])
                self.assertEqual((summary["firstOffering"] or {}).get("name"), self.full_js["projections"][cid]["firstOffering"])

    def test_135_route_actions_uncertainty_and_search_keep_full_data_semantics(self):
        self.assertEqual(len(self.lean["routes"]), 135)
        companies = {c["id"]: c for c in self.data["companies"]}
        for route in self.lean["routes"]:
            expected = self.full_js["workProjection"][route["id"]]
            with self.subTest(route=route["id"]):
                self.assertEqual(route["uncertain"], expected["uncertain"])
                self.assertEqual(route["source_action"], expected["source_action"])
                self.assertEqual(work_search_text(route, companies), expected["search"])

    def test_metric_fallback_exports_also_match_full_js_when_no_health_observation_exists(self):
        for company in self.data["companies"]:
            cid = company["id"]
            with self.subTest(company=cid):
                self.assertEqual(current_company_result(self.research, {}, cid), self.full_js["metricOnlyResults"][cid])

    def test_full_research_statistics_are_independent_of_loaded_view_subsets(self):
        self.assertEqual(self.summary["statistics"], self.full_js["researchStatistics"])
        self.assertEqual(self.summary["statistics"]["currentClaims"], 1964)
        self.assertEqual(self.summary["statistics"]["sources"], 880)
        overview = json.loads((self.destination / self.summary["overview"]["href"].lstrip('/')).read_text())
        self.assertLess(len(overview["data"]["claims"]), self.summary["statistics"]["currentClaims"])
        self.assertLess(len(overview["data"]["sources"]), self.summary["statistics"]["sources"])

    def test_work_search_tolerates_a_fixture_with_a_different_company_universe(self):
        route = self.sidecars["WORK_ROUTES"]["routes"][0]
        text = work_search_text(route, {})
        self.assertIn(route["role"].lower(), text)
        self.assertNotIn("undefined", text)

    def test_all_route_aging_labels_match_runtime_at_explicit_publication_dates(self):
        dates = ["2026-11-07", "2026-11-08", "2026-11-21", "2026-11-22", "2026-11-23T01:00:00Z"]
        for route in self.sidecars["WORK_ROUTES"]["routes"]:
            with self.subTest(route=route["id"]):
                self.assertEqual([work_terms_age(route, day) for day in dates], self.full_js["termsAge"][route["id"]])

    def test_every_selected_financial_keeps_original_source_limits_and_review_semantics(self):
        for cid, summary in self.summaries.items():
            financial = summary["financial"]
            if financial:
                self.assertEqual(financial["id"], summary["currentCompanyResult"]["id"])
                self.assertEqual(financial["display"], summary["currentCompanyResult"]["display"])
                self.assertTrue(financial["source"]["url"].startswith("https://"))
                self.assertIn("limitations", financial)
                self.assertIn("quote", financial)
        self.assertEqual(self.summaries["taskus"]["currentCompanyResult"]["value"], 615121000)
        self.assertEqual(self.summaries["taskus"]["financial"]["scope"], "Whole company")
        self.assertTrue(self.summaries["turing"]["financial"]["failed"])
        self.assertEqual(self.summaries["a-team"]["financial"]["age"], "historical")
        self.assertIsNone(self.summaries["labelbox"]["financial"])

    def test_bootstrap_has_no_canonical_evidence_or_product_graph(self):
        bootstrap = self.summary["bootstrap"]
        for key, value in bootstrap.items():
            if isinstance(value, list) and key not in ("companies", "assessments"):
                self.assertEqual(value, [], key)
        self.assertEqual(len(bootstrap["companies"]), 39)
        self.assertTrue(all(set(gate) == {"level"} for assessment in bootstrap["assessments"] for gate in assessment["gates"].values()))

    def test_source_updates_and_full_work_records_arrive_only_with_company_context(self):
        original_routes = {route["id"]: route for route in self.sidecars["WORK_ROUTES"]["routes"]}
        for cid, descriptor in self.summary["companyDetails"].items():
            detail = json.loads((self.destination / descriptor["href"].lstrip('/')).read_text())
            self.assertEqual(detail["sourceUpdates"], source_updates_context(self.sidecars["SOURCE_UPDATES"], cid))
            for route in detail["workRoutes"]["routes"]:
                self.assertEqual(route, original_routes[route["id"]])
            self.assertTrue(all(entry["company_id"] == cid for entry in detail["profileContent"]["entries"]))
        empty = source_updates_context(self.sidecars["SOURCE_UPDATES"])
        self.assertEqual(empty["updates"], [])
        self.assertEqual(empty["evidence_context"]["corrections"], [])
        self.assertEqual(empty["baseline_dataset_version"], "2.5.0")

    def test_health_metadata_remains_truthy_without_initial_observations_or_evidence(self):
        skeleton = health_skeleton(self.sidecars["BUSINESS_HEALTH"])
        self.assertTrue(skeleton)
        for key in ("observations", "fresh_claims", "sources", "private_company_review"):
            self.assertEqual(skeleton[key], [])
        self.assertEqual(skeleton["source_checks"]["entries"], [])
        self.assertEqual(skeleton["source_dataset_version"], "2.5.0")
        self.assertEqual(set(skeleton), {"version", "dashboard_curated_on", "source_dataset_version", "source_dataset_reviewed_on", "observations", "fresh_claims", "sources", "private_company_review", "source_checks"})
        self.assertEqual(set(skeleton["source_checks"]), {"checked_on", "status", "entries"})
        self.assertEqual(skeleton["source_dataset_reviewed_on"], self.sidecars["BUSINESS_HEALTH"]["source_dataset_reviewed_on"])

    def test_minimal_health_initialization_keeps_listeners_and_hydrates_real_observations(self):
        skeleton = health_skeleton(self.sidecars["BUSINESS_HEALTH"])
        script = APP_RULES.split("process.stdout.write(vm.runInContext", 1)[0]
        script = script.replace("addEventListener(){}", "addEventListener(name,fn){this.listeners??={};this.listeners[name]=fn;}", 1)
        script = script.replace("const document={", "window.BUSINESS_HEALTH=" + json.dumps(skeleton) + ";\nconst document={")
        expression = """JSON.stringify((()=>{
         const before={observations:window.BusinessHealth.observations().length,listener:Boolean(document.getElementById('bh-measure').listeners?.change),method:document.getElementById('bh-method-content').innerHTML};
         window.BUSINESS_HEALTH=JSON.parse(FULL_HEALTH_JSON);window.BusinessHealth.refreshBundle();
         const after={observations:window.BusinessHealth.observations().length,rows:window.BusinessHealth.rows('revenue','period_revenue').length,mercor:window.BusinessHealth.evidenceState('mercor','revenue'),definitions:window.BUSINESS_HEALTH.measure_definitions};
         return {before,after};})())"""
        script += "context.FULL_HEALTH_JSON=read('data/business-health.json');process.stdout.write(vm.runInContext(" + json.dumps(expression) + ",context));"
        modules = ["web/app.js", "web/editorial.js", "web/work-v3.js"] + ["web/" + name for name in PRESENTATION_JS]
        result = subprocess.run(["node", "-e", script, str(ROOT), json.dumps(modules)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["before"]["observations"], 0)
        self.assertTrue(state["before"]["listener"])
        self.assertIn(self.sidecars["BUSINESS_HEALTH"]["source_dataset_reviewed_on"], state["before"]["method"])
        self.assertEqual(state["after"]["observations"], len(self.sidecars["BUSINESS_HEALTH"]["observations"]))
        self.assertGreater(state["after"]["rows"], 0)
        self.assertEqual(state["after"]["mercor"], "observed")
        self.assertEqual(state["after"]["definitions"], self.sidecars["BUSINESS_HEALTH"]["measure_definitions"])

    def test_thin_financial_cards_filters_and_csv_do_not_require_business_health_module(self):
        self.check_deferred_health_models(hydrate=False)

    def test_real_deferred_health_factory_and_context_keep_all_financial_exports_stable(self):
        state = self.check_deferred_health_models(hydrate=True)
        self.assertTrue(state["after"]["factoryWasDeferred"])
        self.assertTrue(state["after"]["moduleReady"])
        self.assertEqual(state["after"]["fullContextCompanies"], 39)
        self.assertEqual(state["after"]["results"], state["before"]["results"])
        self.assertEqual(state["after"]["filter"], state["before"]["filter"])
        self.assertEqual(state["after"]["csv"], state["before"]["csv"])
        self.assertEqual(state["after"]["csv"], self.full_js["companyCsv"])

    def check_deferred_health_models(self, *, hydrate):
        summary = copy.deepcopy(self.summary)
        if hydrate:
            descriptor = write_business_health_module(self.destination, summary["buildId"])
            source = (self.destination / descriptor["href"].lstrip('/')).read_bytes()
            self.assertEqual(descriptor["sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(descriptor["integrity"], "sha256-" + base64.b64encode(hashlib.sha256(source).digest()).decode())
            summary["modules"] = {"businessHealth": descriptor}
        fixture = self.destination / "deferred-health-test-model.json"
        fixture.write_text(json.dumps({"summary": summary, "health": health_skeleton(self.sidecars["BUSINESS_HEALTH"])}))
        script = APP_RULES.split("process.stdout.write(vm.runInContext", 1)[0]
        setup = """
const fixture=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
node('research-data').textContent=JSON.stringify(fixture.summary.bootstrap);
window.SUMMARY_INDEX=fixture.summary;window.COMPANY_CONTEXTS_READY=new Set();window.WORK_ROUTES=fixture.summary.work;
window.PROFILE_CONTENT={entries:[]};window.SOURCE_UPDATES={updates:[],evidence_context:{corrections:[]}};window.BUSINESS_HEALTH=fixture.health;
"""
        script = script.replace("const document={", setup + "\nconst document={")
        script += """
context.TEST_FIXTURE_DIRECTORY=path.dirname(process.argv[3]);
context.clearTimeout=()=>{};
context.INITIALIZE_RUNTIME=()=>{
 document.documentElement={dataset:{buildId:fixture.summary.buildId},setAttribute(){},removeAttribute(){}};
 document.head={append(script){
  const descriptor=fixture.summary.modules.businessHealth;
  if(script.src!==descriptor.href||script.integrity!==descriptor.integrity||script.crossOrigin!=='anonymous')throw new Error('Module loader lost its identity or SRI contract');
  vm.runInContext(fs.readFileSync(path.join(path.dirname(process.argv[3]),descriptor.href.slice(1)),'utf8'),context);
  context.FACTORY_WAS_DEFERRED=window.BusinessHealth===undefined;
  queueMicrotask(()=>script.onload?.());
 }};
 const source=read('web/data-runtime.js').replace('/* APP_BUILD_ID */null',JSON.stringify(fixture.summary.buildId));
 vm.runInContext(source,context);
};
"""
        expression = """(async()=>{
          if(window.BusinessHealth!==undefined)throw new Error('Thin startup unexpectedly loaded the health module');
          const current=()=>Object.fromEntries(DATA.companies.map(c=>[c.id,currentCompanyResult(c.id)]));
          const filter=()=>{const before=state.financial;state.financial=true;const ids=filtered().map(c=>c.id);state.financial=before;return ids;};
          const before={results:current(),filter:filter(),cards:Object.fromEntries(DATA.companies.map(c=>[c.id,card(c)])),moduleAbsent:window.BusinessHealth===undefined};
          let csv=null;download=(name,body,type)=>{csv=body;};
          window.ensureSearchContext=async()=>{window.SEARCH_INDEX=JSON.parse(FS_READ(SEARCH_PATH));return window.SEARCH_INDEX;};
          await exportCsv();before.csv=csv;
          if(!HYDRATE_TEST)return {before};
          INITIALIZE_RUNTIME();
          await ensureHealthModule();
          for(const descriptor of Object.values(window.SUMMARY_INDEX.companyDetails))installResearchContext(JSON.parse(FS_READ(CONTEXT_PATH(descriptor.href))));
          csv=null;await exportCsv();
          const after={results:current(),filter:filter(),cards:Object.fromEntries(DATA.companies.map(c=>[c.id,card(c)])),csv,
            factoryWasDeferred:FACTORY_WAS_DEFERRED,moduleReady:window.APP_HEALTH_READY===window.SUMMARY_INDEX.buildId,
            fullContextCompanies:window.COMPANY_CONTEXTS_READY.size};
          return {before,after};
        })()"""
        script += "context.FS_READ=p=>fs.readFileSync(p,'utf8');context.SEARCH_PATH=path.join(path.dirname(process.argv[3]),fixture.summary.fullSearch.href.slice(1));"
        script += "context.CONTEXT_PATH=href=>path.join(path.dirname(process.argv[3]),href.slice(1));context.HYDRATE_TEST=" + json.dumps(hydrate) + ";"
        script += "Promise.resolve(vm.runInContext(" + json.dumps(expression) + ",context)).then(result=>process.stdout.write(JSON.stringify(result))).catch(error=>{console.error(error);process.exitCode=1;});"
        self.assertIn("business-health.js", PRESENTATION_JS)
        self.assertNotIn("business-health.js", INITIAL_PRESENTATION_JS)
        modules = ["web/app.js", "web/editorial.js", "web/work-v3.js"] + ["web/" + name for name in INITIAL_PRESENTATION_JS]
        result = subprocess.run(["node", "-e", script, str(ROOT), json.dumps(modules), str(fixture)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertTrue(state["before"]["moduleAbsent"])
        self.assertEqual(state["before"]["results"], {cid: row["currentCompanyResult"] for cid, row in self.full_js["projections"].items()})
        self.assertEqual(state["before"]["filter"], self.full_js["financialFilter"])
        self.assertEqual(state["before"]["csv"], self.full_js["companyCsv"])
        for cid, summary in self.summaries.items():
            if summary["hasFinancial"]:
                display = summary["financial"]["display"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                self.assertIn(display, state["before"]["cards"][cid])
                if "after" in state:
                    self.assertIn(display, state["after"]["cards"][cid])
        return state

    def test_lazy_full_search_corpus_exactly_matches_full_company_and_work_text(self):
        descriptor = self.summary["fullSearch"]
        search = json.loads((self.destination / descriptor["href"].lstrip('/')).read_text())
        self.assertEqual(search["data"], {"dataset_version": "2.5.0"})
        self.assertEqual(search["companySearch"], self.full_js["companySearch"])
        self.assertEqual(search["editorialReadouts"], self.data["editorial_readouts"])
        self.assertEqual(search["workSearch"], {key: value["search"] for key, value in self.full_js["workProjection"].items()})
        self.assertEqual(set(search["profileProducts"]), set(self.summaries))
        self.assertEqual(search["profileProducts"], self.full_js["profileProducts"])

    def test_thin_routes_preserve_decision_facts_and_explicit_field_states(self):
        original = {route["id"]: route for route in self.sidecars["WORK_ROUTES"]["routes"]}
        fields = ("pay_terms", "arrangements", "requirements", "assessment", "hours", "duration", "availability_note", "pay_context", "pay_observations", "pay_policy", "pay_indicator", "historical_pay_context")
        for route in self.lean["routes"]:
            full = original[route["id"]]
            for key in fields:
                self.assertEqual(route.get(key), full.get(key), (route["id"], key))
            for field, review in full.get("field_reviews", {}).items():
                self.assertEqual(route["field_reviews"][field]["state"], review["state"])
                self.assertEqual(route["field_reviews"][field].get("source_ids"), review.get("source_ids"))
            self.assertEqual(route.get("research_record", {}).get("route", {}).get("live_application_verified"), full.get("research_record", {}).get("route", {}).get("live_application_verified"))


if __name__ == "__main__":
    unittest.main()
