"""Preserve the original contact-redaction language and substitution order."""
import itertools
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations


class ContactRedactionTests(unittest.TestCase):
    def assert_original_substitution(self, value):
        self.assertEqual(citations._redact_contacts(value),
                         citations.EMAIL.sub("[contact removed]", value), repr(value[:100]))

    def test_adjacent_matches_preserve_nonoverlapping_restart_position(self):
        for value in ("a@b.com1a@d.ef", "a@b.com1a@d.ef2b@c.gh",
                      "x a@b.com1a@d.ef y", "a@b.com@d.ef", "a@b.com.a@d.ef"):
            with self.subTest(value=value):
                self.assert_original_substitution(value)
        self.assertEqual(citations._redact_contacts("a@b.com1a@d.ef"),
                         "[contact removed][contact removed]")

    def test_unicode_casefold_and_delimiters_keep_original_email_language(self):
        for character in ("İ", "ı", "ſ", "K", "é", "中", "\n", "\\", '"', "]"):
            for value in (character + "a@b.cd", "a" + character + "@b.cd",
                          "a@" + character + ".cd", "a@b." + character * 2,
                          "a@b.com" + character + "a@d.ef"):
                with self.subTest(character=character, value=value):
                    self.assert_original_substitution(value)
        for value in ("a+b.c!#$%&'*-/=?^_`{|}~@d.example", "a@@b.cd", "@b.cd",
                      "a@b.c", "a@-b.cd", "a@b-.cd", "a@b.cd_", "a@b.cd1",
                      '{"text":"a@b.cd","escaped":"a\\u0040b.cd"}'):
            with self.subTest(value=value):
                self.assert_original_substitution(value)

    def test_long_hash_and_identifier_runs_match_original_substitution(self):
        for value in ("a" * 4096, "a" * 4096 + "@invalid",
                      "a" * 4096 + "@b.cd", ("0123456789abcdef" * 4 + ",") * 512,
                      "prefix " + "_" * 4096 + "@bad.c suffix a@b.cd"):
            with self.subTest(length=len(value), at_count=value.count("@")):
                self.assert_original_substitution(value)

    def test_seeded_and_exhaustive_inputs_match_original_substitution(self):
        for length in range(8):
            for characters in itertools.product("a@.1", repeat=length):
                self.assert_original_substitution("".join(characters))
        randomizer = random.Random(20261115)
        fragments = ("a@b.com", "1a@d.ef", "@", ".", "..", "a" * 32, "_" * 16,
                     "İ", "ı", "ſ", "K", "é", "中", " ", "\n", '"', "\\u0040", "-", "+")
        for _ in range(10_000):
            value = "".join(randomizer.choices(fragments, k=randomizer.randrange(1, 12)))
            self.assert_original_substitution(value)

    def test_privacy_filter_preserves_contact_then_credential_order_in_both_modes(self):
        for legacy in (False, True):
            secret = citations.LEGACY_SECRET if legacy else citations.SECRET
            for value in ("a@b.com1a@d.ef", "sk-" + "A" * 20 + " a@b.cd",
                          "prefix-sk-" + "A" * 20 + " a@b.cd", "a@b.cd sk-" + "A" * 20):
                with self.subTest(legacy=legacy, value=value):
                    expected = secret.sub("[credential removed]",
                                          citations.EMAIL.sub("[contact removed]", value))
                    self.assertEqual(citations.privacy_filter({"text": [value]}, legacy=legacy),
                                     {"text": [expected]})


if __name__ == "__main__":
    unittest.main()
