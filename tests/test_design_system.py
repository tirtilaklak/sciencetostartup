"""The design system's tokens and stylesheet stay in step with web/ and the built page."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import design_system
from design_system import CASCADE, TOKENS, build, normal_hex


def tokens():
    return json.loads(TOKENS.read_text())


def set_colour(data, name, value):
    for entry in data["color"]["tokens"]:
        if entry["name"] == name:
            entry["value"] = value
            return data
    raise KeyError(name)


class DesignSystemTest(unittest.TestCase):
    def test_tokens_match_the_live_stylesheet(self):
        result = build()
        self.assertEqual(result["problems"], [])

    def test_cascade_order_matches_the_built_page(self):
        page = (ROOT / "dist/index.html").read_text()
        positions = [page.find((ROOT / "web" / name).read_text()) for name in CASCADE]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

    def test_every_wired_colour_is_read_from_its_token(self):
        bundle = build()["files"]["project/components/bundle.css"]
        values = design_system.token_values(tokens())
        for name in design_system.WIRED:
            self.assertIn(f"var(--{name})", bundle)
            self.assertNotIn(normal_hex(values[name]), normal_hex(bundle).replace(f"var(--{name})", ""), name)

    def test_a_changed_root_colour_is_reported(self):
        result = build(set_colour(tokens(), "green", "#000000"))
        self.assertTrue(any(problem.startswith("--green:") for problem in result["problems"]))

    def test_a_wired_colour_missing_from_the_css_is_reported(self):
        result = build(set_colour(tokens(), "track", "#123456"))
        self.assertTrue(any(problem.startswith("track:") for problem in result["problems"]))

    def test_two_tokens_sharing_a_literal_are_reported(self):
        data = set_colour(tokens(), "wash", design_system.token_values(tokens())["band"])
        self.assertTrue(any(problem.startswith("band:") for problem in build(data)["problems"]))

    def test_a_token_name_already_used_in_the_css_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            web = Path(temporary)
            for name in CASCADE:
                (web / name).write_text((ROOT / "web" / name).read_text())
            with (web / "edition.css").open("a") as css:
                css.write(".example{color:var(--track)}\n")
            problems = build(web=web)["problems"]
        self.assertIn("var(--track) already appears in web/; wiring would be ambiguous", problems)

    def test_tokens_css_declares_every_token(self):
        css = build()["files"]["tokens.css"]
        for name in design_system.token_values(tokens()):
            self.assertIn(f"--{name}:", css)
        self.assertTrue(css.startswith("/* ScienceToStartup — generated from tokens.json */"))


if __name__ == "__main__":
    unittest.main()
