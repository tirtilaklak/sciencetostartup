"""Offline adversarial HTTP/parser fixtures, never factual review receipts."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_research_sources as checker


class Response:
    def __init__(self, body=b"fixture", code=200, headers=None, url="https://example.org/source"):
        self.body, self.code, self.headers, self.url = body, code, headers or {}, url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, size):
        return self.body[:size]


class Opener:
    def __init__(self, responses):
        self.responses, self.requests = iter(responses), []

    def open(self, request, timeout):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def addresses(address):
    return lambda *args, **kwargs: [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


class ResearchSourceTests(unittest.TestCase):
    def client(self, root, opener, sleeps=None):
        return checker.PublicClient(Path(root) / "cache", Path(root) / "checkpoint.json", {"example.org"},
                                    interval=3.1, opener=opener, sleep=(sleeps if sleeps is not None else []).append,
                                    clock=lambda: 100, url_checker=lambda url, hosts: "example.org")

    def test_private_credentialed_non_tls_and_unlisted_destinations_rejected(self):
        for url in ("http://example.org", "https://user:pass@example.org", "https://example.org:8080", "https://example.org/?api_key=abc", "https://example.org/#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.check_public_url(url, {"example.org"}, resolver=addresses("8.8.8.8"))
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "::1", "fc00::1"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                checker.check_public_url("https://example.org/", {"example.org"}, resolver=addresses(address))
        with self.assertRaises(ValueError):
            checker.check_public_url("https://unlisted.example/", {"example.org"}, resolver=addresses("8.8.8.8"))
        self.assertEqual(checker.check_public_url("https://example.org/", {"example.org"}, resolver=addresses("8.8.8.8")), "example.org")

    def test_protected_output_and_symlink_refused(self):
        for directory in ("data/research/new.json", "dist/new.json", "web/new.json", "release-assets/new.json"):
            with self.assertRaises(ValueError):
                checker.safe_output(ROOT / directory)
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "data-link"
            link.symlink_to(ROOT / "data", target_is_directory=True)
            with self.assertRaises(ValueError):
                checker.safe_output(link / "new.json")

    def test_conditional_304_keeps_original_capture_and_verified_hash(self):
        opener = Opener([Response(b"Source content", headers={"ETag": '"test"'}), Response(b"", code=304)])
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, opener)
            first, body = client.get("https://example.org/source")
            second, unchanged = client.get("https://example.org/source")
            self.assertEqual(body, unchanged)
            self.assertEqual(first["captured_on"], second["captured_on"])
            self.assertEqual(second["last_http_status"], 304)
            self.assertFalse(second["approved"])
            self.assertEqual(opener.requests[-1].get_header("If-none-match"), '"test"')
            self.assertTrue((Path(directory) / "checkpoint.json").exists())

    def test_corrupt_cache_never_sends_conditional_validator(self):
        opener = Opener([Response(b"Source content", headers={"ETag": '"test"'}), Response(b"Fresh content")])
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, opener)
            receipt, _ = client.get("https://example.org/source")
            (client.cache / (receipt["response_sha256"] + ".body")).write_bytes(b"corrupt")
            client.get("https://example.org/source")
            self.assertIsNone(opener.requests[-1].get_header("If-none-match"))

    def test_304_without_cache_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, Opener([Response(code=304)]))
            with self.assertRaisesRegex(ValueError, "304 without"):
                client.get("https://example.org/source")

    def test_retry_after_is_honored_and_long_delay_is_deferred(self):
        sleeps = []
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, Opener([Response(code=429, headers={"Retry-After": "5"}), Response(b"Good source")]), sleeps)
            receipt, body = client.get("https://example.org/source")
            self.assertEqual(body, b"Good source")
            self.assertEqual(receipt["attempts"], 2)
            self.assertIn(5, sleeps)
        sleeps = []
        opener = Opener([Response(code=429, headers={"Retry-After": "120"})])
        with tempfile.TemporaryDirectory() as directory:
            receipt, _ = self.client(directory, opener, sleeps).get("https://example.org/source")
            self.assertEqual(receipt["result"], "deferred")
            self.assertEqual(len(opener.requests), 1)
            self.assertFalse(sleeps)

    def test_bounded_read_and_http_challenge_do_not_become_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, Opener([Response(b"x" * (checker.MAX_BYTES + 1))]))
            with self.assertRaisesRegex(ValueError, "bounded read"):
                client.get("https://example.org/source")
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, Opener([Response(b"<html>Verify you are human</html>")]))
            receipt, body = client.get("https://example.org/source")
            self.assertEqual(receipt["result"], "unreadable_challenge")
            with self.assertRaises(ValueError):
                checker.capture_excerpt(receipt, body, "Verify you are human", "body", "v1")

    def test_excerpt_must_match_actual_body_and_never_approves(self):
        body = b"<h2>Methods</h2><p>Human reviewers compared two responses.</p>"
        receipt = {"result": "retrieved", "http_status": 200, "response_sha256": checker.sha256(body)}
        result = checker.capture_excerpt(receipt, body, "Human reviewers compared two responses.", "Methods / paragraph 1", "v1")
        self.assertFalse(result["approved"])
        self.assertTrue(result["editorial_review_required"])
        with self.assertRaisesRegex(ValueError, "not found literally"):
            checker.capture_excerpt(receipt, body, "Fabricated supplier contribution.", "Methods", "v1")
        with self.assertRaises(ValueError):
            checker.capture_excerpt(receipt, body, " ".join(["long"] * 26), "Methods", "v1")

    def test_oai_uses_current_arxivraw_endpoint_and_preserves_versions(self):
        url = checker.discovery_url("oai", "2026-11-01", 50)
        self.assertEqual(urlsplit(url).hostname, "oaipmh.arxiv.org")
        self.assertEqual(parse_qs(urlsplit(url).query)["metadataPrefix"], ["arXivRaw"])
        body = b'''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
        <record><header><identifier>oai:arXiv.org:2203.02155</identifier><datestamp>2026-11-01</datestamp></header>
        <metadata><arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/"><id>2203.02155</id><title>Test work</title>
        <version version="v1"><date>Fri, 4 Mar 2022 07:04:42 GMT</date><size>1000kb</size></version>
        <version version="v2"><date>Sat, 5 Mar 2022 07:04:42 GMT</date><size>1001kb</size></version></arXivRaw></metadata></record>
        <record><header status="deleted"><identifier>oai:arXiv.org:2001.00001</identifier><datestamp>2026-11-01</datestamp></header></record>
        <resumptionToken>next-token</resumptionToken></ListRecords></OAI-PMH>'''
        rows, cursor = checker.parse_oai(body)
        self.assertEqual(len(rows), 2)
        self.assertEqual(cursor, "next-token")
        self.assertEqual([v["version"] for v in rows[0]["versions"]], ["v1", "v2"])
        self.assertEqual(rows[0]["metadata_datestamp"], "2026-11-01")
        self.assertEqual(rows[1]["id"], "oai:2001.00001")
        self.assertEqual(rows[1]["metadata_status"], "deleted")
        self.assertFalse(rows[1]["approved"])
        resumed = parse_qs(urlsplit(checker.discovery_url("oai", "ignored", 50, cursor)).query)
        self.assertEqual(resumed, {"verb": ["ListRecords"], "resumptionToken": [cursor]})

    def test_arxiv_acl_hf_crossref_are_candidate_only(self):
        samples = [
            checker.parse_arxiv(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2203.02155v1</id><title>Test paper</title></entry></feed>')[0],
            checker.parse_acl(b'<collection id="2022.emnlp"><volume id="main"><paper id="340"><title>Test <i>paper</i></title><doi>10.1234/test</doi></paper></volume></collection>', "2022.emnlp")[0],
            checker.parse_huggingface(b'[{"id":"org/dataset","author":"private person"}]')[0],
            checker.parse_crossref(b'{"message":{"items":[{"DOI":"10.1234/Test","title":["Test paper"]}],"next-cursor":"cursor"}}')[0]]
        for rows in samples:
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "candidate")
            self.assertFalse(rows[0]["approved"])
            self.assertNotIn("author", rows[0])
        self.assertEqual(samples[1][0]["identifiers"]["acl"], "2022.emnlp-main.340")

    def test_hf_full_first_page_does_not_claim_query_complete(self):
        response = Response(b'[{"id":"org/dataset"}]')
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, Opener([response]))
            report = checker.discover(client, "huggingface", "test", limit=1, window="2026-11-09")
            self.assertFalse(report["complete"])
            self.assertTrue(report["truncated"])

    def test_checkpoint_resumes_and_new_window_reruns_completed_query(self):
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2203.02155v1</id><title>Test paper</title></entry></feed>'
        opener = Opener([Response(body), Response(body)])
        with tempfile.TemporaryDirectory() as directory:
            client = self.client(directory, opener)
            first = checker.discover(client, "arxiv", "all:example", limit=5, window="2026-11-09")
            self.assertTrue(first["complete"])
            checker.discover(client, "arxiv", "all:example", limit=5, window="2026-11-09")
            self.assertEqual(len(opener.requests), 1)
            checker.discover(client, "arxiv", "all:example", limit=5, window="2026-11-10")
            self.assertEqual(len(opener.requests), 2)


if __name__ == "__main__":
    unittest.main()
