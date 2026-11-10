#!/usr/bin/env python3
"""Free public research discovery and bounded capture, always candidates only.

No API inference, authentication, approval or graph mutation. Raw response caches
and resumable checkpoints must live outside tracked data and published output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = "ScienceToStartup/1.0 public research discovery (https://sciencetostartup.com/method/)"
ADAPTER_HOSTS = {"arxiv": {"export.arxiv.org", "arxiv.org"}, "oai": {"oaipmh.arxiv.org"},
                 "acl": {"raw.githubusercontent.com", "aclanthology.org"},
                 "huggingface": {"huggingface.co"}, "crossref": {"api.crossref.org"}}
BLOCKED = re.compile(r"(?:^just a moment|verify (?:you are|that you are) (?:a )?human|request unsuccessful|access denied|captcha challenge)", re.I)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def safe_output(path):
    """Refuse checked-in/public locations even through symlinks."""
    resolved = Path(path).resolve()
    for protected in (ROOT / "data", ROOT / "dist", ROOT / "web", ROOT / "release-assets"):
        protected = protected.resolve()
        if resolved == protected or protected in resolved.parents:
            raise ValueError("candidate/cache output cannot replace reviewed or published files")
    return resolved


def check_public_url(url, hosts=None, resolver=socket.getaddrinfo):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or parsed.fragment):
        raise ValueError("public credential-free HTTPS URL without fragment required")
    if hosts is not None and parsed.hostname not in hosts:
        raise ValueError("redirect/source host outside explicitly allowed public hosts")
    parameters = urllib.parse.parse_qsl(parsed.query)
    # This is a public pagination cursor, not an authentication token. Keep the
    # exception specific to the documented arXiv ListRecords continuation URL.
    oai_cursor = (parsed.hostname == "oaipmh.arxiv.org" and parsed.path == "/oai"
                  and len(parameters) == 2 and dict(parameters).get("verb") == "ListRecords"
                  and set(dict(parameters)) == {"verb", "resumptionToken"})
    if any(re.search(r"token|secret|password|signature|credential|api.?key|auth", key, re.I)
           and not (oai_cursor and key == "resumptionToken") for key, _ in parameters):
        raise ValueError("credential-bearing URL forbidden")
    addresses = resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("private, local or reserved network destination forbidden")
    return parsed.hostname


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicClient:
    """Per-host throttling, conditional GET, bounded retry and content-addressed cache.

    Cache metadata is committed atomically after every response, so an interrupted
    multi-page query resumes from complete receipts. 304 requires intact original
    bytes; it never becomes a new evidence capture or review timestamp.
    """

    def __init__(self, cache, checkpoint, hosts, *, interval=3.1, attempts=3,
                 timeout=25, sleep=time.sleep, clock=time.monotonic, opener=None,
                 url_checker=check_public_url):
        self.cache = safe_output(cache)
        self.checkpoint = safe_output(checkpoint)
        self.hosts = set(hosts)
        if not 0 <= interval <= 60 or not 1 <= attempts <= 4 or not 1 <= timeout <= 60:
            raise ValueError("invalid bounded request policy")
        self.interval, self.attempts, self.timeout = interval, attempts, timeout
        self.sleep, self.clock, self.url_checker = sleep, clock, url_checker
        self.opener = opener or urllib.request.build_opener(CheckedRedirect(self.hosts))
        self.last_request = {}
        self.state = {"schema_version": "1.0.0", "requests": {}, "cursors": {}}
        if self.checkpoint.exists():
            self.state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
            if self.state.get("schema_version") != "1.0.0" or not isinstance(self.state.get("requests"), dict):
                raise ValueError("invalid request checkpoint")
        self.cache.mkdir(parents=True, exist_ok=True)

    def save(self):
        write_json(self.checkpoint, self.state)

    def _cached(self, previous):
        response_hash = previous.get("response_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", response_hash):
            return None
        path = self.cache / (response_hash + ".body")
        if path.is_file():
            body = path.read_bytes()
            if len(body) <= MAX_BYTES and sha256(body) == response_hash:
                return body
        return None

    def get(self, url):
        host = self.url_checker(url, self.hosts)
        previous = self.state["requests"].get(url, {})
        cached = self._cached(previous)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, text/html;q=0.8, text/plain;q=0.8", "Accept-Encoding": "identity"}
        if cached is not None:
            if previous.get("etag"):
                headers["If-None-Match"] = previous["etag"]
            if previous.get("last_modified"):
                headers["If-Modified-Since"] = previous["last_modified"]
        for attempt in range(self.attempts):
            remaining = self.interval - (self.clock() - self.last_request.get(host, -self.interval))
            if remaining > 0:
                self.sleep(min(remaining, 60))
            self.last_request[host] = self.clock()
            request = urllib.request.Request(url, headers=headers)
            try:
                try:
                    response = self.opener.open(request, timeout=self.timeout)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    status = response.code
                    final_url = response.geturl()
                    self.url_checker(final_url, self.hosts)
                    if status == 304:
                        if cached is None:
                            raise ValueError("304 without verified cached bytes")
                        receipt = {**previous, "checked_at": now(), "last_http_status": 304,
                                   "result": "unchanged", "approved": False}
                        self.state["requests"][url] = receipt
                        self.save()
                        return receipt, cached
                    retry_after = response.headers.get("Retry-After")
                    body = response.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise ValueError("response exceeds bounded read; incomplete evidence refused")
                    if status in {408, 425, 429, 500, 502, 503, 504} and attempt + 1 < self.attempts:
                        delay = min(30.0, 2.0 ** attempt)
                        if retry_after:
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                try:
                                    delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                                except (ValueError, TypeError):
                                    pass
                        # Respect a long server delay by deferring to the next run,
                        # rather than retrying early or blocking the editor for minutes.
                        if delay <= 30:
                            self.sleep(delay)
                            continue
                    stamp = now()
                    response_hash = sha256(body)
                    receipt = {"url": url, "final_url": final_url, "captured_on": stamp, "checked_at": stamp,
                               "http_status": status, "last_http_status": status,
                               "response_sha256": response_hash, "bytes": len(body),
                               "content_type": response.headers.get("Content-Type", ""),
                               "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified"),
                               "retry_after": retry_after,
                               "link": response.headers.get("Link"),
                               "result": "retrieved" if status == 200 else "blocked" if status in {401, 403, 407, 429} else "unavailable",
                               "approved": False, "attempts": attempt + 1}
                    if status == 200 and BLOCKED.search(public_text(body)[:1000]):
                        receipt["result"] = "unreadable_challenge"
                    if status in {429, 503} and retry_after and attempt + 1 < self.attempts:
                        receipt["result"] = "deferred"
                    (self.cache / (response_hash + ".body")).write_bytes(body)
                    self.state["requests"][url] = receipt
                    self.save()
                    return receipt, body
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
                if attempt + 1 < self.attempts:
                    self.sleep(min(30, 2 ** attempt))
                    continue
                receipt = {"url": url, "checked_at": now(), "result": "error", "error": type(error).__name__, "approved": False, "attempts": attempt + 1}
                # Preserve successful capture and validators separately on failure.
                if previous.get("response_sha256"):
                    receipt["previous_success"] = {k: previous[k] for k in ("response_sha256", "captured_on") if k in previous}
                self.state["requests"][url] = receipt
                self.save()
                return receipt, b""
        raise RuntimeError("request attempts exhausted")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def public_text(body):
    parser = TextExtractor()
    parser.feed(body.decode("utf-8", "replace"))
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


def capture_excerpt(receipt, body, excerpt, locator, version):
    """Bind a concise literal excerpt to the complete retrieved response.

    This receipt supports later content review. The function never records a
    reviewer, a factual approval, source publication date or an inferred license.
    """
    if receipt.get("result") not in {"retrieved", "unchanged"} or receipt.get("http_status") != 200:
        raise ValueError("successful readable source retrieval required")
    if len(body) > MAX_BYTES or receipt.get("response_sha256") != sha256(body):
        raise ValueError("source response hash mismatch or incomplete bounded capture")
    if not excerpt.strip() or len(excerpt.split()) > 25 or not locator.strip() or not version.strip():
        raise ValueError("concise excerpt (at most 25 words), locator and version required")
    normalized_excerpt = re.sub(r"\s+", " ", excerpt).strip()
    visible = public_text(body)
    if normalized_excerpt not in visible:
        raise ValueError("excerpt not found literally in captured source text")
    if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", normalized_excerpt):
        raise ValueError("contact emails forbidden in public evidence")
    return {**receipt, "scope": "source_capture_candidate", "version": version,
            "excerpt": normalized_excerpt, "excerpt_sha256": sha256(normalized_excerpt.encode("utf-8")),
            "locator": locator, "editorial_review_required": True, "approved": False}


def _candidate(adapter, identifier, title, url, identifiers, kind="paper"):
    return {"id": adapter + ":" + identifier, "kind": kind, "title": re.sub(r"\s+", " ", title).strip(),
            "url": url, "identifiers": identifiers, "adapter": adapter,
            "status": "candidate", "approved": False, "review_required": True}


def parse_arxiv(body):
    xml = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    rows = []
    for entry in xml.findall("a:entry", ns):
        url = entry.findtext("a:id", "", ns).replace("http://", "https://")
        identifier = url.rsplit("/abs/", 1)[-1]
        if identifier:
            rows.append(_candidate("arxiv", identifier, entry.findtext("a:title", "", ns), url, {"arxiv": identifier}))
    return rows, None


class OAIError(ValueError):
    def __init__(self, codes):
        self.codes = set(codes)
        super().__init__("OAI endpoint error: " + "; ".join(sorted(self.codes)))


def oai_candidate_rank(value):
    versions = [int(version["version"][1:]) for version in value.get("versions", [])
                if re.fullmatch(r"v\d+", str(version.get("version", "")))]
    return (value.get("metadata_datestamp") or "", value.get("metadata_status") == "deleted", max(versions, default=0))


def parse_oai(body):
    xml = ET.fromstring(body)
    errors = xml.findall("{*}error")
    codes = {e.get("code", "unknown") for e in errors}
    if codes == {"noRecordsMatch"}:
        return [], None
    if errors:
        raise OAIError(codes)
    if xml.find("{*}ListRecords") is None:
        raise ValueError("OAI ListRecords response required")
    rows = []
    for record in xml.findall(".//{*}record"):
        header = record.find("{*}header")
        if header is None or not header.findtext("{*}identifier") or not header.findtext("{*}datestamp"):
            raise ValueError("OAI record needs identifier and modification datestamp")
        if header is not None and header.get("status") == "deleted":
            identifier = header.findtext("{*}identifier", "").removeprefix("oai:arXiv.org:")
            candidate = _candidate("oai", identifier, "Deleted arXiv metadata record", "https://arxiv.org/abs/" + identifier, {"arxiv": identifier})
            candidate.update(metadata_status="deleted", metadata_datestamp=header.findtext("{*}datestamp"),
                             date_note="OAI datestamp is the metadata deletion date; this is a review candidate, not a graph deletion.")
            rows.append(candidate)
            continue
        metadata = record.find("{*}metadata")
        if metadata is None:
            raise ValueError("OAI record missing metadata")
        identifier = metadata.findtext(".//{*}id")
        title = metadata.findtext(".//{*}title")
        if identifier and title:
            candidate = _candidate("oai", identifier, title, "https://arxiv.org/abs/" + identifier, {"arxiv": identifier})
            candidate["versions"] = [{"version": version.get("version"), "date": version.findtext("{*}date"),
                                      "size": version.findtext("{*}size")} for version in metadata.findall(".//{*}version")]
            candidate["metadata_datestamp"] = header.findtext("{*}datestamp") if header is not None else None
            candidate["metadata_status"] = "present"
            candidate["date_note"] = "OAI datestamp is a metadata modification date; version history dates are not replaced by it."
            rows.append(candidate)
        else:
            raise ValueError("OAI metadata missing identifier or title")
    token = xml.findtext(".//{*}resumptionToken")
    return rows, token.strip() if token and token.strip() else None


def parse_acl(body, collection):
    xml = ET.fromstring(body)
    rows = []
    for volume in xml.findall("volume"):
        vid = volume.get("id", "")
        for paper in volume.findall("paper"):
            title = paper.find("title")
            if title is None:
                continue
            identifier = f"{collection}-{vid}.{paper.get('id')}"
            # Old collections use volume IDs (e.g. P19-1) as their stable prefix.
            if re.fullmatch(r"[A-Z]\d{2}", collection):
                identifier = f"{collection}-{vid}{paper.get('id', '').zfill(3)}"
            ids = {"acl": identifier}
            doi = paper.findtext("doi")
            if doi:
                ids["doi"] = doi
            rows.append(_candidate("acl", identifier, "".join(title.itertext()), f"https://aclanthology.org/{identifier}/", ids))
    return rows, None


def parse_huggingface(body):
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError("Hugging Face response must be dataset array")
    rows = []
    for item in data:
        identifier = item.get("id")
        if identifier:
            rows.append(_candidate("huggingface", identifier, identifier, "https://huggingface.co/datasets/" + identifier, {"huggingface": identifier}, kind="dataset"))
    return rows, None


def parse_crossref(body):
    message = json.loads(body)["message"]
    rows = []
    for item in message.get("items", []):
        doi = item.get("DOI")
        titles = item.get("title", [])
        if doi and titles:
            rows.append(_candidate("crossref", doi.lower(), titles[0], "https://doi.org/" + doi, {"doi": doi.lower()}))
    return rows, message.get("next-cursor") if rows else None


def discovery_url(adapter, query, limit, cursor=None):
    if not 1 <= limit <= 100:
        raise ValueError("page size must be 1..100")
    if adapter == "arxiv":
        params = {"search_query": query, "start": cursor or "0", "max_results": limit, "sortBy": "submittedDate", "sortOrder": "descending"}
        return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    if adapter == "oai":
        dates = query.split("/")
        if not cursor and (len(dates) not in {1, 2} or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in dates)):
            raise ValueError("OAI query must be YYYY-MM-DD or inclusive YYYY-MM-DD/YYYY-MM-DD")
        for value in dates if not cursor else []:
            datetime.strptime(value, "%Y-%m-%d")
        if len(dates) == 2 and dates[0] > dates[1]:
            raise ValueError("OAI from must not exceed until")
        params = {"verb": "ListRecords", "resumptionToken": cursor} if cursor else {"verb": "ListRecords", "metadataPrefix": "arXivRaw", "from": dates[0]}
        if not cursor and len(dates) == 2:
            params["until"] = dates[1]
        return "https://oaipmh.arxiv.org/oai?" + urllib.parse.urlencode(params)
    if adapter == "acl":
        if not re.fullmatch(r"(?:\d{4}\.[a-z0-9-]+|[A-Z]\d{2})", query):
            raise ValueError("ACL query must be collection id, e.g. 2022.emnlp or P19")
        return "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/" + query + ".xml"
    if adapter == "huggingface":
        if cursor:
            return cursor
        return "https://huggingface.co/api/datasets?" + urllib.parse.urlencode({"search": query, "limit": limit, "sort": "lastModified", "direction": -1})
    if adapter == "crossref":
        return "https://api.crossref.org/works?" + urllib.parse.urlencode({"query": query, "rows": limit, "cursor": cursor or "*", "select": "DOI,title,type,published,URL"})
    raise ValueError("unknown adapter")


def discover(client, adapter, query, *, limit=50, pages=1, window=None):
    """Resume bounded pages, deduplicate works and keep discovery separate from review."""
    if not 1 <= pages <= 20:
        raise ValueError("bounded pages must be 1..20")
    # Resumption tokens expire and mutable collections change. A dated run window
    # prevents last week's exhausted query from suppressing this week's discovery.
    window = window or now()[:10]
    query_key = sha256((adapter + "\0" + query + "\0" + str(limit) + "\0" + window).encode())
    progress = client.state.setdefault("cursors", {}).get(query_key, {"next": None, "complete": False, "candidates": [], "receipts": []})
    requests_made, restarted = 0, False
    progress.pop("retry_reason", None)
    if not progress["complete"]:
        for _ in range(pages):
            url = discovery_url(adapter, query, limit, progress["next"])
            receipt, body = client.get(url)
            requests_made += 1
            progress["receipts"].append(receipt)
            if receipt.get("result") not in {"retrieved", "unchanged"}:
                progress["retry_reason"] = "request_" + receipt.get("result", "unknown")
                client.state["cursors"][query_key] = progress
                client.save()
                break
            try:
                if adapter == "acl":
                    rows, cursor = parse_acl(body, query)
                else:
                    rows, cursor = {"arxiv": parse_arxiv, "oai": parse_oai, "huggingface": parse_huggingface, "crossref": parse_crossref}[adapter](body)
            except OAIError as error:
                if error.codes != {"badResumptionToken"} or not progress["next"]:
                    raise
                # Never change the captured date range or discard already parsed
                # candidates. Re-fetching its first page is safe after expiry.
                progress["next"] = None
                progress["token_restarts"] = progress.get("token_restarts", 0) + 1
                progress["retry_reason"] = "expired_oai_token_restart_same_query"
                client.state["cursors"][query_key] = progress
                client.save()
                if restarted:
                    break
                restarted = True
                continue
            progress.pop("retry_reason", None)
            existing = {r["id"]: r for r in progress["candidates"]}
            for row in rows:
                if adapter != "oai" or row["id"] not in existing or oai_candidate_rank(row) >= oai_candidate_rank(existing[row["id"]]):
                    existing[row["id"]] = row
            progress["candidates"] = sorted(existing.values(), key=lambda r: r["id"])
            if adapter == "arxiv" and len(rows) >= limit:
                cursor = str(int(progress["next"] or "0") + len(rows))
            if adapter == "huggingface":
                match = re.search(r'<([^>]+)>;\s*rel="?next"?', receipt.get("link") or "")
                cursor = match.group(1) if match else None
                if cursor:
                    client.url_checker(cursor, client.hosts)
                if len(rows) >= limit and not cursor:
                    progress["truncated"] = True
            if cursor and cursor == progress["next"]:
                progress["retry_reason"] = "repeated_cursor_requires_operator_attention"
            elif not cursor and not progress.get("truncated"):
                progress["complete"] = True
            progress["next"] = cursor
            client.state["cursors"][query_key] = progress
            client.save()
            if progress["complete"]:
                break
            if progress.get("truncated"):
                break
            if progress.get("retry_reason") == "repeated_cursor_requires_operator_attention":
                break
    return {"schema_version": "1.0.0", "generated_at": now(), "status": "candidates_only", "approved": False,
            "facts_modified": False, "adapter": adapter, "query": query, "window": window,
            "complete": progress["complete"], "truncated": progress.get("truncated", False),
            "next_cursor": progress["next"], "candidates": progress["candidates"], "receipts": progress["receipts"],
            "requests_made": requests_made, "token_restarts": progress.get("token_restarts", 0),
            "retry_reason": progress.get("retry_reason"),
            "limitations": ["Metadata matching is discovery only; it establishes no supplier contribution, dataset provenance, rights or paper review.",
                             "Completeness refers only to this adapter query and dated window. A full page without next-page metadata remains truncated."] if adapter == "huggingface" else ["Metadata matching is discovery only; no factual approvals or review dates are changed.", "Completeness refers only to this adapter query and dated window, not the eligible research universe."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="Untracked raw response cache")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    discovery = sub.add_parser("discover")
    discovery.add_argument("--adapter", choices=sorted(ADAPTER_HOSTS), required=True)
    discovery.add_argument("--query", required=True)
    discovery.add_argument("--limit", type=int, default=50)
    discovery.add_argument("--pages", type=int, default=1)
    discovery.add_argument("--window", help="Dated discovery run identity; defaults to current UTC day")
    capture = sub.add_parser("capture")
    capture.add_argument("--url", required=True)
    capture.add_argument("--excerpt", required=True)
    capture.add_argument("--locator", required=True)
    capture.add_argument("--version", required=True)
    capture.add_argument("--allow-host", action="append", required=True)
    args = parser.parse_args()
    try:
        output = safe_output(args.output)
        hosts = ADAPTER_HOSTS[args.adapter] if args.command == "discover" else set(args.allow_host)
        client = PublicClient(args.cache, args.checkpoint, hosts)
        if args.command == "discover":
            result = discover(client, args.adapter, args.query, limit=args.limit, pages=args.pages, window=args.window)
        else:
            receipt, body = client.get(args.url)
            result = capture_excerpt(receipt, body, args.excerpt, args.locator, args.version)
        write_json(output, result)
        print(json.dumps({"output": str(output), "status": result.get("status", result.get("result")), "approved": False}))
    except (ValueError, ET.ParseError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
