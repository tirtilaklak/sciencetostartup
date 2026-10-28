"""Evidence and calculation checks for the public business-health workbench.

These checks verify quantitative provenance and comparison semantics. Real
browser interaction and responsive layout are checked separately.
"""
import ast
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGNALS = {"revenue", "profit", "customers", "delivery", "cash"}
sys.path.insert(0, str(ROOT / "scripts"))
from business_health import load_business_health


class BusinessHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.health = json.loads((ROOT / "data/business-health.json").read_text())
        cls.observations = cls.health["observations"]
        cls.companies = {row["id"]: row for row in cls.data["companies"]}
        cls.claims = {row["id"]: row for row in cls.data["claims"]}
        cls.claims.update({row["id"]: row for row in cls.health.get("fresh_claims", [])})
        cls.metrics = {row["id"]: row for row in cls.data["metrics"]}
        cls.sources = {row["id"]: row for row in cls.data["sources"]}
        cls.sources.update({row["id"]: row for row in cls.health.get("sources", [])})

    def test_every_number_has_traceable_same_company_evidence(self):
        self.assertTrue(self.observations)
        identifiers = [row["id"] for row in self.observations]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual({row["signal"] for row in self.observations}, SIGNALS)
        for row in self.observations:
            with self.subTest(observation=row["id"]):
                company = row["company_id"]
                self.assertIn(company, self.companies)
                if row["value"] is None:
                    self.assertEqual(row["measure"], "profitability_statement")
                    self.assertEqual(row["unit"], "statement")
                    self.assertTrue(row["is_context"])
                else:
                    self.assertIsInstance(row["value"], (int, float))
                    self.assertNotIsInstance(row["value"], bool)
                    self.assertTrue(math.isfinite(row["value"]))
                for field in ("measure", "unit", "qualifier", "as_of", "scope", "accounting_basis", "evidence_type", "basis", "limitations", "original_text"):
                    self.assertIsInstance(row[field], str, field)
                    self.assertTrue(row[field].strip(), field)
                self.assertIsInstance(row["period"], dict)
                self.assertTrue(row["period"]["type"])
                self.assertTrue(row["period"]["label"])
                self.assertTrue(row["claim_ids"])
                self.assertTrue(row["source_ids"])
                declared_sources = set()
                for claim_id in row["claim_ids"]:
                    claim = self.claims[claim_id]
                    self.assertEqual(claim["company_id"], company)
                    self.assertEqual(claim["status"], "supported")
                    declared_sources.update(claim["source_ids"])
                self.assertLessEqual(set(row["source_ids"]), declared_sources)
                for source_id in row["source_ids"]:
                    self.assertIn(source_id, self.sources)
                    self.assertTrue(self.sources[source_id]["url"].startswith("https://"))
                for metric_id in row["metric_ids"]:
                    metric = self.metrics[metric_id]
                    self.assertEqual(metric["company_id"], company)
                    self.assertIn(metric["claim_id"], row["claim_ids"])

    def test_derived_growth_and_margins_recalculate_from_matching_inputs(self):
        observations = {row["id"]: row for row in self.observations}
        derived = [row for row in self.observations if row["evidence_type"] == "calculated"]
        self.assertTrue(derived)
        for row in derived:
            with self.subTest(observation=row["id"]):
                first, second = [observations[identifier] for identifier in row["calculation"]["input_observation_ids"]]
                self.assertEqual(first["company_id"], second["company_id"])
                self.assertEqual(first["company_id"], row["company_id"])
                self.assertEqual(first["currency"], second["currency"])
                self.assertEqual(first["scope"], second["scope"])
                self.assertEqual(first["scope"], row["scope"])
                self.assertEqual(first["period"]["type"], second["period"]["type"])
                self.assertEqual(first["period"]["type"], row["period"]["type"])
                self.assertEqual(row["unit"], "percent")
                self.assertGreater(second["value"], 0)
                self.assertEqual(first["qualifier"], "exact")
                self.assertEqual(second["qualifier"], "exact")
                if row["measure"] == "revenue_growth_yoy":
                    self.assertEqual(first["measure"], "period_revenue")
                    self.assertEqual(second["measure"], "period_revenue")
                    self.assertEqual(first["accounting_basis"], second["accounting_basis"])
                    self.assertEqual(first["period"]["year"], second["period"]["year"] + 1)
                    for boundary in ("start", "end"):
                        self.assertEqual(first["period"][boundary][5:], second["period"][boundary][5:])
                    expected = (first["value"] / second["value"] - 1) * 100
                else:
                    self.assertIn(row["measure"], {"net_margin", "adjusted_ebitda_margin"})
                    self.assertEqual(second["measure"], "period_revenue")
                    self.assertEqual(first["period"], second["period"])
                    expected = first["value"] / second["value"] * 100
                self.assertAlmostEqual(row["value"], expected, places=10)

    def test_retention_and_concentration_keep_their_percentage_semantics(self):
        by_id = {row["id"]: row for row in self.observations}
        retention = by_id["taskus.metric.expansion-14"]
        self.assertEqual((retention["measure"], retention["value"], retention["unit"], retention["scope"]),
                         ("net_revenue_retention", 113, "percent", "company"))
        self.assertNotIn("currency", retention)
        concentration = by_id["appen.metric.major-growth_metrics-8"]
        self.assertEqual((concentration["measure"], concentration["value"], concentration["unit"]),
                         ("top_five_customer_share", 67.9, "percent"))

    def test_loader_rejects_broken_quantitative_provenance(self):
        def load(value, data=None):
            with tempfile.TemporaryDirectory(prefix="health-validation-") as temporary:
                path = Path(temporary) / "health.json"
                path.write_text(json.dumps(value))
                return load_business_health(path, data or self.data)
        self.assertEqual(load(self.health), self.health)
        mutations = []
        bad = copy.deepcopy(self.health)
        bad["observations"][0]["claim_ids"] = [next(identifier for identifier, claim in self.claims.items() if claim["company_id"] != bad["observations"][0]["company_id"])]
        mutations.append(("cross-company claim", bad))
        bad = copy.deepcopy(self.health)
        bad["observations"][0]["metric_ids"] = [next(identifier for identifier, metric in self.metrics.items() if metric["company_id"] != bad["observations"][0]["company_id"])]
        mutations.append(("cross-company metric", bad))
        bad = copy.deepcopy(self.health)
        bad["observations"][0]["value"] = float("nan")
        mutations.append(("non-finite value", bad))
        bad = copy.deepcopy(self.health)
        bad["observations"].append(copy.deepcopy(bad["observations"][0]))
        mutations.append(("duplicate observation", bad))
        bad = copy.deepcopy(self.health)
        derived = next(row for row in bad["observations"] if row["evidence_type"] == "calculated")
        derived["value"] += 10
        mutations.append(("incorrect calculated ratio", bad))
        bad = copy.deepcopy(self.health)
        derived = next(row for row in bad["observations"] if row["measure"] == "revenue_growth_yoy" and row["evidence_type"] == "calculated")
        baseline_id = derived["calculation"]["input_observation_ids"][1]
        next(row for row in bad["observations"] if row["id"] == baseline_id)["period"]["end"] = "2025-03-31"
        mutations.append(("mismatched growth period", bad))
        bad = copy.deepcopy(self.health)
        fresh_id = bad["fresh_claims"][0]["id"]
        next(row for row in bad["observations"] if fresh_id in row["claim_ids"])["value"] += 1
        mutations.append(("fresh value differs from source fact", bad))
        bad = copy.deepcopy(self.health)
        source_id = bad["fresh_claims"][0]["source_ids"][0]
        next(entry for entry in bad["source_checks"]["entries"] if entry["source_id"] == source_id)["status"] = "unavailable"
        mutations.append(("fresh claim relies on failed retrieval", bad))
        bad = copy.deepcopy(self.health)
        bad["fresh_claims"][0]["id"] = self.data["claims"][0]["id"]
        mutations.append(("fresh claim overrides canonical history", bad))
        bad = copy.deepcopy(self.health)
        supplemental = next(source for source in bad["sources"] if source["id"].startswith("refresh.source."))
        supplemental["url"] = "https://user:password@example.com/evidence"
        mutations.append(("supplemental source includes credentials", bad))
        bad = copy.deepcopy(self.health)
        source = next(source for source in bad["sources"] if source["id"].startswith("refresh.source."))
        source["company_id"] = "taskus"
        mutations.append(("supplemental source belongs to a different company", bad))
        bad = copy.deepcopy(self.health)
        bad["sources"][0]["url"] = "https://example.com/substitute"
        mutations.append(("supplemental layer overrides canonical source URL", bad))
        for name, value in mutations:
            with self.subTest(mutation=name), self.assertRaises(ValueError):
                load(value)
        fixture = {"dataset_version": "fixture"}
        self.assertIsNone(load(self.health, fixture), "Other datasets must not inherit curated research")

    def test_private_company_estimates_and_activity_do_not_become_financial_actuals(self):
        rows = {row["id"]: row for row in self.observations}
        mercor = rows["mercor.metric.major-growth_metrics-1"]
        self.assertEqual(mercor["evidence_type"], "estimate")
        self.assertIn("Sacra", mercor["evidence_assurance"])
        self.assertEqual(rows["mercor.metric.oct14-major-financial-2"]["accounting_basis"], "unspecified")
        for identifier in ("refresh.prolific.2025-contribution-hours", "refresh.prolific.2025-studies-tasks"):
            row = rows[identifier]
            self.assertTrue(row["is_context"])
            self.assertEqual(row["period"]["type"], "year_to_date")
            self.assertNotIn("end", row["period"], "Unstated activity cutoff must not become a precise completed period")
        self.assertEqual(rows["refresh.micro1.october-2026-core-team"]["qualifier"], "approximately")
        self.assertTrue(rows["refresh.micro1.october-2026-core-team"]["is_context"])

    def test_runtime_filters_preserve_context_bounds_and_scenario_uncertainty(self):
        tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
        stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
        checks = r'''
const h=window.BusinessHealth,before=JSON.stringify(data),observations=h.observations();
assert.ok(observations.length>0);
h.render();
assert.ok(node('bh-measure').innerHTML.includes('value="annualized_revenue"'),'Measure option IDs must retain underscores');
assert.ok(!node('bh-measure').innerHTML.includes('value="annualized revenue"'),'Public copy formatting must not rewrite control identifiers');
for(const signal of ['revenue','profit','customers','delivery','cash']){
 const rows=h.rows(signal);
 assert.ok(rows.every(row=>row.signal===signal&&typeof row.value==='number'&&Number.isFinite(row.value)));
 for(const company of data.companies){
  const selected=h.rows(signal,'',{company:company.id});
  assert.ok(selected.every(row=>row.company_id===company.id));
 }
 for(const group of Object.keys(run('MODEL_GROUPS'))){
  const selected=h.rows(signal,'',{group});
  assert.ok(selected.every(row=>run(`modelGroup(${JSON.stringify(row.company_id)})`)===group));
 }
 for(const key of new Set(rows.map(h.cohort))){
  const selected=h.rows(signal,'',{cohort:key});
  assert.ok(selected.length>0&&selected.every(row=>h.cohort(row)===key));
 }
 assert.ok(h.rows(signal,'',{reportedOnly:true}).every(row=>row.evidence_type==='reported'));
}
assert.equal(h.rows('revenue','period_revenue',{company:'constructor'}).length,0);
assert.equal(h.evidenceState('laude','revenue'),'n-a');
assert.equal(h.evidenceState('aixi','profit'),'n-a');
assert.equal(h.evidenceState('abundant_ai','delivery'),'proxy','Network registration is context, not paid activity');
assert.equal(h.evidenceState('labelbox','profit'),'proxy','Qualitative profitability is not a measured margin');
assert.equal(h.evidenceState('proximal','cash'),'proxy','Team size is context, not cash evidence');
assert.equal(h.evidenceState('appen','profit'),'observed');
assert.equal(h.evidenceState('quesma','cash'),'missing');
assert.deepEqual(plain(h.estimate(100000000,10,30)),{low:10000000,high:30000000,lowMargin:10,highMargin:30});
assert.deepEqual(plain(h.estimate(0,0,100)),{low:0,high:0,lowMargin:0,highMargin:100});
for(const args of [[100,30,10],[-100,10,20],[100,-1,20],[100,10,101],[NaN,10,20],[100,NaN,20],[100,10,Infinity],['100',10,20]])assert.equal(h.estimate(...args),null);
const nearly=observations.find(row=>row.qualifier==='nearly');assert.ok(nearly);
assert.ok(/nearly/i.test(h.valueText(nearly)),'Near-bound revenue must not look exact');
const lower=observations.find(row=>row.qualifier==='greater_than');assert.ok(lower);
assert.ok(h.valueText(lower).startsWith('> '),'Revenue lower bound must remain visible');
assert.equal(JSON.stringify(data),before,'Dashboard analysis must not rewrite canonical research');
console.log(JSON.stringify({observations:observations.length,filtering:true,context_semantics:true,scenario_boundaries:true,bounds_preserved:true}));
'''
        with tempfile.TemporaryDirectory(prefix="health-runtime-") as temporary:
            script = Path(temporary) / "checks.cjs"
            script.write_text(stub.split("(async()=>{", 1)[0] + checks)
            result = subprocess.run(["node", str(script), str(ROOT / "data/canonical.json"), str(ROOT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["observations"], len(self.observations))

    def test_reader_facing_wording_has_no_record_dumps_or_reviewer_notes(self):
        # Cards already show scope, period and accounting basis as fields, and sources link
        # through source_ids. Prose must not repeat record fields, raw identifiers, bare URLs
        # or research-team instructions. Methodology names JSON fields on purpose and is exempt.
        patterns = {
            "bare URL": r"https?://|www\.",
            "joined sentences": r"\.;",
            "record-field tail": r"(?i)\b(?:segment scope|scope|original period/date|revenue/accounting basis|source type|original value|kind|label|id|value|qualifier|unit|currency|period start|period end|reported vs estimated|gross vs net|is arr|as of|observation status|remove fields|measurement date|employment type|countries(?: qualifier)?|research label):",
            "raw identifier": r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b",
            "reviewer instruction": r"(?i)(?:^|[.;:]\s+)(?:do not|don't|never|keep|retain|exclude|avoid|remove|treat)\b|\b(?:should|must) not\b",
            "space before punctuation": r" [.,;]",
            "trailing whitespace": r"[ \t]+$",
        }
        texts = [(row["id"] + "." + field, row[field]) for row in self.observations
                 for field in ("label", "basis", "limitations", "original_text", "normalization", "evidence_assurance") if row.get(field)]
        texts += [("north_star." + key, self.health["north_star"][key]) for key in ("label", "definition", "why", "limitation")]
        texts += [("signal." + row["id"] + "." + key, row[key]) for row in self.health["signals"] for key in ("label", "question", "ideal_measure", "interpretation", "limitations")]
        texts += [("measure." + row["id"] + "." + key, row[key]) for row in self.health["measure_definitions"] for key in ("label", "note")]
        texts.append(("source_checks.notes", self.health["source_checks"]["notes"]))
        for where, text in texts:
            for name, pattern in patterns.items():
                with self.subTest(text=where, pattern=name):
                    self.assertNotRegex(text, re.compile(pattern, re.M))
        # Sentence case: every sentence starts with a capital, unless it starts with a company name written in lower case, such as micro1.
        names = tuple({part for company in self.companies.values() for part in company["name"].split(" / ")})
        for row in self.observations:
            for field in ("label", "basis", "limitations", "original_text", "evidence_assurance"):
                with self.subTest(observation=row["id"], field=field):
                    sentences = re.split(r"(?<=[.!?])\s+|\n", row.get(field) or "")
                    self.assertEqual([s for s in sentences if s[:1].islower() and not s.startswith(names)], [], "Sentences start with a capital letter")
        mercor = next(row for row in self.observations if row["id"] == "mercor.metric.oct14-major-financial-2")
        self.assertEqual(mercor["accounting_basis"], "unspecified")
        self.assertIn("Felicis", mercor["basis"])
        self.assertIn("not imposed", mercor["limitations"])

    def test_no_reader_facing_text_calls_a_figure_audited(self):
        # The site has audited nothing, and a filing is not an audit readers can rely on, so notes name the
        # document type instead. "Unaudited" states a negative fact and may stay. Identifiers are not prose,
        # and sources mirror canonical source records, which this layer does not reword.
        audited = lambda text: [word for word in re.findall(r"(?i)[\w-]*audited[\w-]*", text) if word.lower() != "unaudited"]
        self.assertEqual(audited("Audited filing; unaudited notes; re-audited"), ["Audited", "re-audited"])
        def prose(value):
            if isinstance(value, dict): return [text for key, item in value.items() if key != "sources" and not re.search(r"(?:^|_)(?:ids?|key)$", key) for text in prose(item)]
            if isinstance(value, list): return [text for item in value for text in prose(item)]
            return [value] if isinstance(value, str) else []
        texts = prose(self.health)
        # Without its own note a card shows the canonical claim's evidence label.
        texts += [self.claims[row["claim_ids"][0]]["evidence_label"] for row in self.observations if not row.get("evidence_assurance")]
        self.assertGreater(len(texts), 1000)
        self.assertEqual([text for text in texts if audited(text)], [])
        by_id = {row["id"]: row for row in self.observations}
        self.assertEqual(by_id["taskus.metric.expansion-6"]["evidence_assurance"], "Annual report (Form 10-K)")
        self.assertEqual(by_id["appen.metric.major-financial_metrics-0"]["evidence_assurance"], "Annual report (ASX)")

    def test_calculated_records_quote_their_inputs_source_wording(self):
        observations = {row["id"]: row for row in self.observations}
        for row in self.observations:
            if row["evidence_type"] == "calculated":
                with self.subTest(observation=row["id"]):
                    self.assertEqual(row["original_text"], "\n".join(observations[i]["original_text"] for i in row["calculation"]["input_observation_ids"]))

    def test_missing_information_has_no_zero_placeholder_records(self):
        # Zero may be an actual financial result; unknown observations instead
        # have no record and are represented by the runtime's missing state.
        for row in self.observations:
            with self.subTest(observation=row["id"]):
                self.assertNotIn(row["evidence_type"].lower(), {"unknown", "missing", "not_available"})
                self.assertNotRegex(row["measure"].lower(), r"(?:health|quality)_score")

    def test_delivered_assets_preserve_research_and_include_the_workbench(self):
        self.assertEqual((ROOT / "dist/research.json").read_bytes(), (ROOT / "data/canonical.json").read_bytes())
        self.assertEqual(json.loads((ROOT / "dist/business-health.json").read_text()), self.health)
        html = (ROOT / "dist/index.html").read_text()
        # The page scripts load from content-hashed files in dist/js/; the CSS stays inline.
        scripts = "".join((ROOT / "dist" / src).read_text() for src in dict.fromkeys(re.findall(r'"(js/[^"]+[.]js)"', html)))
        self.assertIn((ROOT / "web/business-health.js").read_text(), scripts)
        self.assertIn((ROOT / "web/business-health.css").read_text(), html)
        self.assertIn('id="business-health"', html)
        manifest = json.loads((ROOT / "dist/manifest.json").read_text())["sha256"]
        self.assertEqual(manifest["business-health.json"], hashlib.sha256((ROOT / "dist/business-health.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
