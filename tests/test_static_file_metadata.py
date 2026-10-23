"""Test download metadata from built file bytes without running a build."""
import ast
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import STATIC_DOWNLOAD_FILES, format_file_size, render_static_file_metadata


class Anchors(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"attrs": dict(attrs), "text": ""}
            self.rows.append(self.current)

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None

    def handle_data(self, text):
        if self.current is not None:
            self.current["text"] += text


class StaticFileMetadataTests(unittest.TestCase):
    def setUp(self):
        self.template = (ROOT / "web/index.html").read_text()

    def test_decimal_sizes_are_deterministic(self):
        for size, expected in [(0, "0 B"), (999, "999 B"), (1000, "1 kB"), (1050, "1.1 kB"), (1234, "1.2 kB"), (999499, "999.5 kB"), (1000000, "1 MB"), (1234567, "1.2 MB")]:
            self.assertEqual(format_file_size(size), expected)

    def test_every_static_target_uses_its_actual_bytes(self):
        before = Anchors(self.template).rows
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for index, (filename, _) in enumerate(STATIC_DOWNLOAD_FILES.values()):
                file = target / filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"x" * (1000 + index * 1300))
            rendered = render_static_file_metadata(self.template, target)
            self.assertEqual(rendered, render_static_file_metadata(self.template, target))
            self.assertNotRegex(rendered, r"\{\{FILE_(?:META|SIZE)_")
            after = Anchors(rendered).rows
            self.assertEqual([row["attrs"] for row in before], [row["attrs"] for row in after], "A link destination, download attribute or new-tab behavior changed")
            for key, (filename, file_type) in STATIC_DOWNLOAD_FILES.items():
                matches = [row for row in after if row["attrs"].get("href") == filename and ("download" in row["attrs"] or row["attrs"].get("class") == "investor-full-image")]
                self.assertGreaterEqual(len(matches), 1, filename)
                for match in matches:
                    self.assertIn(file_type, match["text"])
                    self.assertIn(format_file_size((target / filename).stat().st_size), match["text"])
                    self.assertRegex(match["text"], r"\d(?:\.\d)? (?:kB|MB|B)")
                    if key == "INVESTOR":
                        self.assertIn("(opens in a new tab)", match["text"])
            for button in ["download-json", "download-csv"]:
                pattern = r'<button id="' + button + r'">[\s\S]*?</button>'
                self.assertEqual(re.search(pattern, rendered).group(), re.search(pattern, self.template).group(), "Generated download received a false static size")
            work = target / "work-routes.json"
            work.write_bytes(b"y" * 2300000)
            changed = Anchors(render_static_file_metadata(self.template, target)).rows
            self.assertIn("JSON · 2.3 MB", next(row["text"] for row in changed if row["attrs"].get("href") == "work-routes.json"))
            work.unlink()
            with self.assertRaises(FileNotFoundError):
                render_static_file_metadata(self.template, target)

    def test_current_artifact_sizes_and_builder_order(self):
        rendered = render_static_file_metadata(self.template, ROOT / "dist")
        anchors = Anchors(rendered).rows
        for filename, _ in STATIC_DOWNLOAD_FILES.values():
            self.assertTrue(any(row["attrs"].get("href") == filename and format_file_size((ROOT / "dist" / filename).stat().st_size) in row["text"] for row in anchors), filename)
        tree = ast.parse((ROOT / "scripts/observatory.py").read_text())
        build = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build")
        calls = list(ast.walk(build))
        metadata = next(node for node in calls if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "render_static_file_metadata")
        copy_calls = [node for node in calls if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"copy2", "copytree"}]
        self.assertTrue(all(node.lineno < metadata.lineno for node in copy_calls), "Metadata precedes asset or JSON copy")
        index_write = next(node for node in calls if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "write_text" and isinstance(node.func.value, ast.BinOp) and isinstance(node.func.value.right, ast.Constant) and node.func.value.right.value == "index.html")
        self.assertLess(metadata.lineno, index_write.lineno)


if __name__ == "__main__":
    unittest.main()
