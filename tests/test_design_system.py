"""The design system's tokens and stylesheet stay in step with web/ and the built page."""
import json
import re
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


def problems_with(name, extra):
    """Build from a copy of web/ with extra CSS appended to one file."""
    with tempfile.TemporaryDirectory() as temporary:
        web = Path(temporary)
        for file in CASCADE:
            (web / file).write_text((ROOT / "web" / file).read_text())
        with (web / name).open("a") as css:
            css.write(extra)
        return build(web=web)["problems"]


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
            leftover = re.search(re.escape(normal_hex(values[name])) + r"(?![0-9a-f])", normal_hex(bundle))
            self.assertIsNone(leftover, name)

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
        problems = problems_with("edition.css", ".example{color:var(--track)}\n")
        self.assertIn("var(--track) already appears in web/; wiring would be ambiguous", problems)

    def test_a_token_the_site_never_declares_is_reported_even_with_a_fallback(self):
        problems = problems_with("edition.css", ".topbar{border-radius:var( --radius-control,12px)}\n")
        self.assertIn("var(--radius-control) is used in web/ but the site never declares --radius-control", problems)

    def test_an_earlier_media_override_of_a_lifted_variable_is_reported(self):
        problems = problems_with("style.css", "@media(max-width:700px){:root{--green:#000000}}\n")
        self.assertTrue(any(problem.startswith("--green: web/style.css declares it before") for problem in problems))

    def test_root_rules_with_spaces_or_comments_are_lifted_and_checked(self):
        for rule in (":root {--green:#000000}\n", ":root{/* note */--green:#000000}\n"):
            problems = problems_with("edition.css", rule)
            self.assertIn("--green: tokens.json has #285b46, the stylesheet ends at #000000", problems, rule)

    def test_a_token_declared_in_a_mixed_root_selector_is_reported(self):
        problems = problems_with("edition.css", ".a,:root{--green:#285b46}\n")
        self.assertIn("web/edition.css: '.a,:root' declares --green; only a rule whose whole selector is :root can be lifted", problems)

    def test_tokens_css_declares_every_token(self):
        css = build()["files"]["tokens.css"]
        for name in design_system.token_values(tokens()):
            self.assertIn(f"--{name}:", css)
        self.assertTrue(css.startswith("/* ScienceToStartup — generated from tokens.json */"))


if __name__ == "__main__":
    unittest.main()
