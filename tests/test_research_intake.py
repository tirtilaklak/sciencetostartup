import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from research_intake import partitions, select_partitions


class ResearchIntakeTests(unittest.TestCase):
    def test_scope_includes_old_years_and_replacements(self):
        config = json.loads((ROOT / "data/research/intake.json").read_text())
        rows = partitions(config, datetime(2026, 11, 9, tzinfo=timezone.utc))
        self.assertTrue(any(r["adapter"] == "oai" for r in rows))
        self.assertTrue(any(r["id"].startswith("arxiv-2020-") for r in rows))
        self.assertTrue(any(r["id"].startswith("arxiv-2026-") for r in rows))
        self.assertEqual(len({r["id"] for r in rows}), len(rows))

    def test_fair_queue_prioritizes_unattempted_partitions(self):
        rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        previous = {"a": {"attempted_at": "2026-11-09T00:00:00Z"}}
        self.assertEqual([r["id"] for r in select_partitions(rows, previous, 2)], ["b", "c"])
        with self.assertRaises(ValueError):
            select_partitions(rows, previous, 0)


if __name__ == "__main__":
    unittest.main()
