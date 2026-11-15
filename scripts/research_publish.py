"""Explicit, credentialed publication adapters; routine builds never import clients.

No command here is run by the static builder. An uncertain create operation is
reconciled remotely and never blindly retried. Journals contain no credentials.
"""
from __future__ import annotations

import hashlib
import copy
from datetime import datetime, timezone
import io
import json
import re
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from research_citations import ROOT, DOI, CONTEXT_CONTRACT_VERSION, RESERVATION_FIELDS, json_bytes, sha256, source_context_bytes, publication_metadata, zenodo_metadata, read_prepared_package, published_archive
except ImportError:
    from scripts.research_citations import ROOT, DOI, CONTEXT_CONTRACT_VERSION, RESERVATION_FIELDS, json_bytes, sha256, source_context_bytes, publication_metadata, zenodo_metadata, read_prepared_package, published_archive


class PublicationBlocked(ValueError):
    pass


class AmbiguousRemoteState(RuntimeError):
    """A prior mutation may have succeeded; do not automatically repeat it."""


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        before, after = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(new_url)
        if after.scheme != "https" or after.netloc != before.netloc:
            raise PublicationBlocked("Publication API redirected to an unexpected origin")
        return super().redirect_request(request, response, code, message, headers, new_url)


class HTTP:
    """Small stdlib transport. Bearer tokens never appear in URLs or journals."""
    def __init__(self, token, origin):
        if not token:
            raise PublicationBlocked("Connect the publishing account before remote operations.")
        self.token, self.origin = token, origin.rstrip("/")

    def request(self, method, path, payload=None, data=None, content_type=None, accept="application/json"):
        url = path if path.startswith("https://") else self.origin + path
        parsed = urllib.parse.urlsplit(url)
        # Remote links may be followed only on the configured API origin. This
        # also prevents remote-controlled links from exfiltrating bearer tokens.
        if parsed.scheme != "https" or parsed.netloc != urllib.parse.urlsplit(self.origin).netloc:
            raise PublicationBlocked("Unexpected publication API origin")
        headers = {"Authorization": "Bearer " + self.token,
                   "User-Agent": "ScienceToStartup-research-publisher/1.0 (+https://sciencetostartup.com/research/)",
                   "Accept": accept}
        if payload is not None:
            data, content_type = json_bytes(payload), "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            opener = urllib.request.build_opener(SameOriginRedirect())
            with opener.open(request, timeout=60) as response:
                blob = response.read()
                return json.loads(blob) if blob else {}
        except urllib.error.HTTPError as error:
            # Do not print response bodies, headers, request objects or tokens.
            raise RuntimeError("Publication API returned HTTP " + str(error.code)) from None


def anonymous_zenodo_get(origin, path, limit):
    """Read only official public records/files, with no account credentials."""
    if (origin not in {'https://zenodo.org', 'https://sandbox.zenodo.org'}
            or not re.fullmatch(r'/api/records/[1-9][0-9]*(?:/files/[^/?#]+/content)?', path)
            or type(limit) is not int or not 0 < limit <= 30 * 1024 * 1024):
        raise PublicationBlocked('Invalid anonymous archive read')
    request = urllib.request.Request(origin + path, method='GET', headers={
        'User-Agent': 'ScienceToStartup-research-publisher/1.0 (+https://sciencetostartup.com/research/)',
        'Accept': 'application/json' if '/files/' not in path else '*/*'})
    try:
        with urllib.request.build_opener(SameOriginRedirect()).open(request, timeout=60) as response:
            blob = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise PublicationBlocked('Anonymous archive read returned HTTP ' + str(error.code)) from None
    if len(blob) > limit:
        raise PublicationBlocked('Anonymous archive response exceeds its expected size')
    return blob


class Journal:
    def __init__(self, path, release_id, package_sha256=None, *, context_sha256=None):
        self.path = Path(path).resolve()
        # The journal is local operational state, never a source/public file.
        if self.path.is_relative_to(ROOT):
            raise PublicationBlocked("Keep publication journals outside the source checkout.")
        self.identity = {"release_id": release_id, "package_sha256": package_sha256} if package_sha256 else {
            "release_id": release_id, "reservation_context_sha256": context_sha256}
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "schema_version": 1, **self.identity,
            "zenodo": {"status": "prepared"}, "github": {"status": "prepared"},
            "huggingface": {"status": "prepared"}, "events": []}
        if any(self.state.get(key) != value for key, value in self.identity.items()):
            raise PublicationBlocked("The journal is bound to different release/package bytes.")
        self._lock_depth = 0

    @contextmanager
    def lock(self):
        """One publisher at a time; refresh durable state after acquiring the lock."""
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PublicationBlocked("Another publisher owns this release journal") from None
            try:
                if self.path.exists():
                    observed = json.loads(self.path.read_text())
                    if any(observed.get(key) != value for key, value in self.identity.items()):
                        raise PublicationBlocked("Journal identity changed")
                    self.state = observed
                self._lock_depth = 1
                yield
            finally:
                self._lock_depth = 0
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def save(self, operation, **details):
        self.state["events"].append({"operation": operation, **details})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(json_bytes(self.state))
        temporary.replace(self.path)


def serialized(service):
    def decorate(method):
        @wraps(method)
        def invoke(self, *args, **kwargs):
            with self.release.journal.lock():
                self.state = self.release.journal.state[service]
                return method(self, *args, **kwargs)
        return invoke
    return decorate


def archival_gate(context):
    """Always run the report owner's gate; this API cannot supply a weaker one."""
    if context.get('published_edition_replay') is not None or context.get('policy', {}).get('mode') == 'replay_only':
        raise PublicationBlocked('Historical public replay cannot authorize fresh publication adapters')
    try:
        from research_report import publication_gate as evaluator
    except ImportError:
        from scripts.research_report import publication_gate as evaluator
    gate = evaluator(context["graph"], context["report"], context.get("policy"))
    if context.get("policy", {}).get("mode") != "publish_enabled":
        raise PublicationBlocked("Publication policy is prepare_only; prepare packages until accounts are connected.")
    if not gate.get("archival_ready", gate.get("ready")) or not context.get("gate", {}).get("archival_ready", context.get("gate", {}).get("ready")):
        raise PublicationBlocked("Research archival-readiness gate has not passed.")
    return gate


class PublicationPlan:
    """Reserve a version DOI before rendering; no upload/publish without a bundle.

    The reservation journal is bound to research inputs excluding reservation
    outcomes. The separate Release journal is later bound to exact ZIP bytes.
    """
    def __init__(self, context, journal_path):
        self.context = context
        # An old reservation marker cannot be reconstructed from current owned
        # recipes. Preserve its journal and recover its original context before
        # making any remote mutation; frozen legacy releases use Release replay.
        prior = json.loads(Path(journal_path).read_text()) if Path(journal_path).exists() else None
        self.context_contract_version = prior.get("context_contract_version", 1) if prior is not None else CONTEXT_CONTRACT_VERSION
        if self.context_contract_version != CONTEXT_CONTRACT_VERSION:
            raise PublicationBlocked("Legacy reservation requires its original authenticated frozen context; preserve the journal and reconcile its existing deposit before migration")
        self.source_sha256 = sha256(source_context_bytes(context, reservation=False, version=self.context_contract_version))
        self.journal = Journal(journal_path, context["report"]["release_id"], context_sha256=self.source_sha256)
        self.journal.state["context_contract_version"] = self.context_contract_version

    def verify(self):
        gate = archival_gate(self.context)
        if sha256(source_context_bytes(self.context, reservation=False, version=self.context_contract_version)) != self.source_sha256:
            raise PublicationBlocked("Research inputs changed after DOI reservation planning")
        return gate

    @property
    def marker(self):
        return "sciencetostartup-reservation:" + self.source_sha256

    @property
    def metadata(self):
        return zenodo_metadata(publication_metadata(self.context))

    @property
    def uploads(self):
        raise PublicationBlocked("Freeze and verify the PDF/package before uploading or publishing")

    def reservation(self):
        with self.journal.lock():
            state = self.journal.state["zenodo"]
            number = state.get("id")
            sandbox = state.get("environment") == "sandbox"
            origin = "https://sandbox.zenodo.org" if sandbox else "https://zenodo.org"
            expected = ("10.5072" if sandbox else "10.5281") + "/zenodo." + str(number)
            if (state.get("reservation_source") != "inveniordm.pids.doi"
                    or type(number) is not int or number <= 0
                    or state.get("environment") not in {"production", "sandbox"}
                    or state.get("api_origin") != origin or state.get("reserved_doi") != expected):
                raise PublicationBlocked("Reserve the version DOI before freezing the package")
            return {"status": "reserved", "reserved_doi": state["reserved_doi"], "deposition_id": state["id"],
                    "api_origin": state["api_origin"], "environment": state["environment"]}


class Release:
    def __init__(self, context, package, journal_path, *, reservation=None):
        self.context, self.package = context, Path(package)
        manifest_bytes = (self.package / "MANIFEST.json").read_bytes()
        self.manifest = json.loads(manifest_bytes)
        self.manifest_sha256 = sha256(manifest_bytes)
        # ZIP envelope bytes also matter: a recompressed or annotated archive
        # must never reuse another artifact's reconciliation marker or journal.
        self.package_sha256 = sha256((self.package / "research-archive.zip").read_bytes())
        self.journal = Journal(journal_path, context["report"]["release_id"], self.package_sha256)
        if reservation is not None:
            reservation.verify()
            reserved = reservation.reservation()
            archive = context["report"].get("archive", {})
            if (reservation.context["report"]["release_id"] != context["report"]["release_id"]
                    or self.manifest.get("context_contract_version", 1) != reservation.context_contract_version
                    or sha256(source_context_bytes(context, reservation=False, version=reservation.context_contract_version)) != reservation.source_sha256
                    or any(archive.get(key) != reserved[key] for key in RESERVATION_FIELDS)):
                raise PublicationBlocked("Frozen context differs from the DOI reservation")
            with self.journal.lock():
                if not self.journal.state["events"]:
                    self.journal.state["zenodo"] = copy.deepcopy(reservation.journal.state["zenodo"])
                    self.journal.state["zenodo"].update(pending="metadata", reservation_marker=reservation.marker)
                    self.journal.save("zenodo-reservation-adopted", id=reserved["deposition_id"])

    def verify(self):
        """Recompute the authoritative gate and verify exact prepared bytes."""
        gate = archival_gate(self.context)
        manifest_bytes = (self.package / "MANIFEST.json").read_bytes()
        if sha256(manifest_bytes) != self.manifest_sha256 or json.loads(manifest_bytes) != self.manifest:
            raise PublicationBlocked("Package manifest changed.")
        if (self.manifest.get("schema_version") != 1
                or self.manifest.get("release_id") != self.context["report"]["release_id"]):
            raise PublicationBlocked("Package manifest identity differs.")
        required = {"report.pdf", "metadata.json", "clean-dataset.json", "zenodo-metadata.json", "huggingface-README.md"}
        if not required <= set(self.manifest["files"]):
            raise PublicationBlocked("Prepare a verified PDF and all publication payloads in the manifest.")
        for name, descriptor in self.manifest["files"].items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise PublicationBlocked("Unsafe package member")
            blob = (self.package / name).read_bytes()
            if sha256(blob) != descriptor["sha256"] or len(blob) != descriptor["bytes"]:
                raise PublicationBlocked("Prepared package file changed: " + name)
        if sha256((self.package / "research-archive.zip").read_bytes()) != self.package_sha256:
            raise PublicationBlocked("Prepared archive bytes changed.")
        expected = set(self.manifest["files"]) | {"MANIFEST.json"}
        with zipfile.ZipFile(self.package / "research-archive.zip") as archive:
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
                raise PublicationBlocked("Archive members differ from the manifest")
            for name in expected:
                if archive.read(name) != (self.package / name).read_bytes():
                    raise PublicationBlocked("Archive differs from prepared file: " + name)
        try:
            context = self.context
            # A fully verified production publication journal can authorize
            # historical replay for mirror/reconciliation retries. Pending or
            # merely labelled published state cannot skip current recipe checks.
            if context["report"].get("archive", {}).get("status") != "published":
                state = self.journal.state["zenodo"]
                outcome = {key: state[key] for key in ("status", "verified", "api_origin", "environment", "doi", "concept_doi",
                    "record_id", "record_url", "confirmed_on", "artifact_sha256", "anonymous_verified") if key in state}
                outcome.update(release_id=context["report"]["release_id"])
                outcome.update({key: context["report"].get("archive", {})[key] for key in RESERVATION_FIELDS
                                if key in context["report"].get("archive", {})})
                candidate = {**context, "report": {**context["report"], "archive": outcome}}
                if published_archive(candidate) and outcome["artifact_sha256"] == self.package_sha256:
                    context = candidate
            read_prepared_package(context, self.package, expected_archive_sha256=self.package_sha256)
        except ValueError as error:
            raise PublicationBlocked(str(error)) from None
        return gate

    @property
    def uploads(self):
        return {name: (self.package / name).read_bytes() for name in
                ("research-archive.zip", "report.pdf", "metadata.json", "MANIFEST.json")}

    @property
    def marker(self):
        return "sciencetostartup-package:" + self.package_sha256

    @property
    def metadata(self):
        return json.loads((self.package / "zenodo-metadata.json").read_text())

    def verify_existing_archive(self):
        """Authenticate old public bytes only for an already published journal.

        A public replay never gains fresh publication authority. The descriptor
        and retained private journal must independently identify the same exact
        production release before mirror or read-only reconciliation recovery.
        """
        replay = (self.context.get("published_edition_replay") is not None
                  or self.context.get("policy", {}).get("mode") == "replay_only")
        if not replay:
            return self.verify()
        try:
            from research_edition_replay import read_replay_package
            files = read_replay_package(self.context, self.package)
        except (ValueError, KeyError, TypeError) as error:
            raise PublicationBlocked(str(error)) from None
        if (sha256(files["MANIFEST.json"]) != self.manifest_sha256
                or json.loads(files["MANIFEST.json"]) != self.manifest
                or sha256(files["research-archive.zip"]) != self.package_sha256):
            raise PublicationBlocked("Historical package identity changed")
        state = self.journal.state
        receipt = state["zenodo"]
        expected = self.context["report"]["archive"]
        candidate = {**receipt, "release_id": state.get("release_id"),
                     "deposition_id": receipt.get("id")}
        if (state.get("release_id") != self.context["report"]["release_id"]
                or state.get("package_sha256") != self.package_sha256
                or not published_archive({"report": {"release_id": self.context["report"]["release_id"],
                                                      "archive": candidate}})
                or receipt.get("pending") is not None
                or expected.get("reserved_doi") != expected.get("doi")
                or type(receipt.get("id")) is not int
                or receipt["id"] != expected.get("deposition_id")
                or any(candidate.get(key) != expected.get(key) for key in (
                    "doi", "concept_doi", "record_id", "record_url", "artifact_sha256",
                    *RESERVATION_FIELDS))):
            raise PublicationBlocked("Historical recovery requires its matching verified production archive journal")
        # A later anonymous recheck may advance the private confirmation time;
        # it must never precede the immutable descriptor's actual confirmation.
        try:
            confirmed = datetime.fromisoformat(receipt["confirmed_on"].replace("Z", "+00:00"))
            original = datetime.fromisoformat(expected["confirmed_on"].replace("Z", "+00:00"))
            if confirmed < original:
                raise ValueError("confirmation predates the published descriptor")
        except (KeyError, TypeError, ValueError) as error:
            raise PublicationBlocked("Historical journal confirmation differs: " + str(error)) from None
        return self.context["gate"]

    def require_archive(self):
        self.verify_existing_archive()
        receipt = self.journal.state["zenodo"]
        if (receipt.get("status") != "published" or receipt.get("verified") is not True
                or receipt.get('anonymous_verified') is not True
                or receipt.get("api_origin") != "https://zenodo.org" or receipt.get("environment") != "production"):
            raise PublicationBlocked("Mirrors require a remotely verified published archive on production Zenodo.")
        if receipt.get("artifact_sha256") != self.package_sha256:
            raise PublicationBlocked("Published archive receipt differs from this exact package")
        return receipt

    def archive_receipt(self):
        """Export verified publication outcomes for the report/website context."""
        with self.journal.lock():
            receipt = self.require_archive()
            value = {key: receipt[key] for key in ("status", "verified", "api_origin", "environment", "doi", "concept_doi",
                     "record_id", "record_url", "confirmed_on", "artifact_sha256")}
            value.update(release_id=self.context["report"]["release_id"], bundle_path=str(self.package.resolve()))
            for key in RESERVATION_FIELDS:
                if key in self.context["report"].get("archive", {}):
                    value[key] = self.context["report"]["archive"][key]
            if receipt.get("published_on"):
                value["published_on"] = receipt["published_on"]
            if receipt.get('anonymous_verified') is True:
                value['anonymous_verified'] = True
            if self.context["report"].get("edition_date"):
                value["edition_date"] = self.context["report"]["edition_date"]
            return value


def _checksum_matches(remote, blob):
    checksum = remote.get("checksum", "")
    return (checksum.removeprefix("md5:") == hashlib.md5(blob).hexdigest()
            and remote.get("filesize", remote.get("size")) == len(blob))


class Zenodo:
    def __init__(self, release, token=None, transport=None, sandbox=False, public_reader=None):
        self.release = release
        self.api_origin = "https://sandbox.zenodo.org" if sandbox else "https://zenodo.org"
        self.environment = "sandbox" if sandbox else "production"
        self.http = transport or HTTP(token, self.api_origin)
        self.public_read = public_reader or anonymous_zenodo_get
        self.state = release.journal.state["zenodo"]

    def _bind_environment(self):
        if getattr(self.http, "origin", self.api_origin).rstrip("/") != self.api_origin:
            raise PublicationBlocked("Zenodo transport origin differs from the selected environment")
        origin = self.state.get("api_origin")
        if origin is None:
            if self.state.get("id") or self.state.get("status") not in {None, "prepared"}:
                raise PublicationBlocked("Existing Zenodo journal lacks a verified API origin; inspect it before recovery")
            self.state.update(api_origin=self.api_origin, environment=self.environment)
            self.release.journal.save("zenodo-environment-bound", api_origin=self.api_origin, environment=self.environment)
        elif origin != self.api_origin or self.state.get("environment") != self.environment:
            raise PublicationBlocked("Zenodo journal belongs to a different API environment")

    def _request(self, method, path, **kwargs):
        return self.http.request(method, path, **kwargs)

    def _deposit(self, deposition_id):
        return self._request("GET", "/api/deposit/depositions/" + str(deposition_id))

    def _matching_deposits(self):
        matches, page = [], 1
        while True:
            items = self._request("GET", "/api/deposit/depositions?size=100&page=" + str(page) + "&all_versions=true")
            for item in items:
                if self.release.marker in item.get("metadata", {}).get("notes", ""):
                    matches.append(item)
            if len(items) < 100:
                return matches
            page += 1
            if page > 1000:
                raise AmbiguousRemoteState("Remote deposit pagination exceeded the reconciliation bound")

    def _remember(self, deposit):
        if self.release.marker not in deposit.get("metadata", {}).get("notes", ""):
            raise PublicationBlocked("Remote deposit is not bound to this package")
        number = deposit.get("id")
        prior_id = self.state.get("id")
        if (type(number) is not int or number <= 0
                or deposit.get("record_id", number) != number
                or (prior_id is not None and (type(prior_id) is not int or prior_id != number))):
            raise PublicationBlocked("Remote draft identity differs from the reservation journal")
        if self.state.get("status") in {"published", "published_unverified"}:
            raise PublicationBlocked("Published archive cannot be replaced by an unpublished draft")
        expected = ("10.5072" if self.environment == "sandbox" else "10.5281") + "/zenodo." + str(number)
        previous = self.state.get("reserved_doi")
        legacy_alias = "10.5281/zenodo." + str(number)
        # Legacy deposit JSON fabricates this DOI even when native pids is empty,
        # and hardcodes the production prefix on Sandbox. Only native PID proof
        # may replace an unproven alias; a proven reservation is immutable here.
        if (self.state.get("reservation_source") not in (None, "inveniordm.pids.doi")
                or previous not in (None, expected, legacy_alias)) or (
                self.state.get("reservation_source") == "inveniordm.pids.doi" and previous != expected):
            raise PublicationBlocked("Reserved version DOI changed")
        frozen = self.release.context.get("report", {}).get("archive", {})
        if isinstance(self.release, Release) and frozen.get("status") == "reserved" and frozen.get("reserved_doi") != expected:
            raise PublicationBlocked("Frozen package reservation differs from the native version DOI")
        self.state.update(id=number)
        self.release.journal.save("zenodo-draft-identified", id=number)
        path = "/api/records/" + str(number) + "/draft"
        native = self._request("GET", path, accept="application/vnd.inveniordm.v1+json")
        self._validate_native_draft(native, number)
        if "doi" not in native["pids"]:
            if self.state.get("reservation_source") == "inveniordm.pids.doi":
                raise PublicationBlocked("Previously verified native DOI is missing from the draft")
            if self.state.get("pending") == "publish":
                raise AmbiguousRemoteState("Publication is pending without a native reserved DOI")
            reserve_path = path + "/pids/doi"
            advertised = native.get("links", {}).get("reserve_doi")
            if advertised not in (reserve_path, self.api_origin + reserve_path):
                raise PublicationBlocked("Native DOI reservation link differs from this draft and API origin")
            # A bodyless POST reserves the PID on this exact existing draft.
            # Save intent first. After a lost response the next invocation GETs
            # native state above and POSTs again only if the PID is still absent.
            self.state["pending"] = "reserve_doi"
            self.release.journal.save("zenodo-native-doi-reservation-intent", id=number)
            native = self._request("POST", advertised, accept="application/vnd.inveniordm.v1+json")
            self._validate_native_draft(native, number)
        pid = native["pids"].get("doi")
        if (not isinstance(pid, dict) or pid.get("provider") != "datacite" or pid.get("client") != "datacite"
                or pid.get("identifier") != expected):
            raise PublicationBlocked("Zenodo did not return the expected managed native version DOI")
        reserved = pid["identifier"]
        if previous not in (None, reserved):
            alias = {"doi": previous, "source": "legacy_deposit_prereserve_doi",
                     "id": number, "api_origin": self.api_origin}
            aliases = self.state.setdefault("legacy_reservation_aliases", [])
            if alias not in aliases:
                aliases.append(alias)
            # Retain the old field value and its provenance on disk before the
            # corrected native field replaces it. No context or ID is rebound.
            self.release.journal.save("zenodo-legacy-reservation-alias-retained", id=number,
                                      legacy_reserved_doi=previous, native_reserved_doi=reserved)
        pending = "publish" if self.state.get("pending") == "publish" else None
        self.state.update(status="draft", pending=pending, reserved_doi=reserved,
                          reservation_source="inveniordm.pids.doi")
        self.release.journal.save("zenodo-draft-reconciled", id=number)
        return deposit

    def _validate_native_draft(self, native, number):
        if (not isinstance(native, dict) or native.get("id") != str(number)
                or native.get("is_draft") is not True or native.get("is_published") is not False
                or not isinstance(native.get("pids"), dict)):
            raise PublicationBlocked("Native draft identity or PID representation differs")

    def _metadata(self):
        metadata = self.release.metadata
        metadata["metadata"]["notes"] = self.release.marker
        if self.state.get("reservation_marker"):
            metadata["metadata"]["notes"] += "\n" + self.state["reservation_marker"]
        metadata["metadata"]["prereserve_doi"] = True
        return metadata

    @serialized("zenodo")
    def draft(self, previous_id=None):
        self.release.verify()
        self._bind_environment()
        if published_archive(self.release.context):
            if previous_id is not None:
                raise PublicationBlocked("Published archive recovery cannot create a new version")
            receipt = self.release.context["report"]["archive"]
            if self.state.get("id") not in (None, receipt["record_id"]):
                raise PublicationBlocked("Published archive identity differs from the reconciliation journal")
            # A published source receipt names the existing record. Never fall
            # through to account search/create/newversion if a local journal was
            # lost; only reconcile this exact record and its public file bytes.
            self.state.update(id=receipt["record_id"], reserved_doi=receipt["doi"])
            self.release.journal.save("zenodo-published-record-recovery", id=receipt["record_id"])
            return self.reconcile()
        if previous_id is not None and (type(previous_id) is not int or previous_id <= 0):
            raise PublicationBlocked("A new version requires an integer version-record ID, never a concept DOI")
        if self.state.get("id"):
            deposit = self._deposit(self.state["id"])
            if deposit.get("submitted"):
                return self.reconcile()
            if self.state.get("pending") == "metadata":
                deposit = self._request("PUT", "/api/deposit/depositions/" + str(deposit["id"]), payload=self._metadata())
            return self._remember(deposit)
        matches = self._matching_deposits()
        if len(matches) > 1:
            raise AmbiguousRemoteState("Multiple deposits match this exact package; choose one explicitly")
        if matches:
            if matches[0].get("submitted"):
                self.state["id"] = matches[0]["id"]
                self.release.journal.save("zenodo-existing-publication-found", id=matches[0]["id"])
                return self.reconcile()
            return self._remember(matches[0])
        metadata = self._metadata()
        if previous_id:
            previous = self._deposit(previous_id)
            if (not previous.get("submitted") or previous.get("state") != "done"
                    or previous.get("record_id", previous_id) != previous_id
                    or str(previous.get("conceptrecid")) == str(previous_id)):
                raise PublicationBlocked("Previous ID must identify a published version record, never a concept record")
            latest = previous.get("links", {}).get("latest_draft")
            if latest:
                candidate = self._request("GET", latest)
                if str(candidate["id"]) != str(previous_id) and not candidate.get("submitted"):
                    # An unrelated outstanding new version must not be replaced.
                    if self.release.marker not in candidate.get("metadata", {}).get("notes", "") and self.state.get("pending") != "newversion":
                        raise PublicationBlocked("A different unpublished Zenodo version already exists")
                    deposit = candidate
                else:
                    deposit = None
            else:
                deposit = None
            if deposit is None:
                if self.state.get("pending"):
                    raise AmbiguousRemoteState("Prior new-version request remains unresolved")
                self.state.update(pending="newversion", previous_id=previous_id)
                self.release.journal.save("zenodo-newversion-intent", previous_id=previous_id)
                original = self._request("POST", "/api/deposit/depositions/" + str(previous_id) + "/actions/newversion")
                deposit = self._request("GET", original["links"]["latest_draft"])
            # Persist the new ID before metadata mutation. On a lost response the
            # same draft can be reconciled, never create a second version.
            self.state.update(id=deposit["id"], pending="metadata")
            self.release.journal.save("zenodo-newversion-found", id=deposit["id"])
            deposit = self._request("PUT", "/api/deposit/depositions/" + str(deposit["id"]), payload=metadata)
        else:
            if self.state.get("pending"):
                raise AmbiguousRemoteState("Prior create may have succeeded; reconcile before retrying")
            self.state["pending"] = "create"
            self.release.journal.save("zenodo-create-intent")
            deposit = self._request("POST", "/api/deposit/depositions", payload=metadata)
        return self._remember(deposit)

    @serialized("zenodo")
    def upload(self):
        self.release.verify()
        self._bind_environment()
        if self.state.get("status") == "published" or published_archive(self.release.context):
            raise PublicationBlocked("Published archive cannot be overwritten")
        deposit = self.draft()
        if deposit.get("submitted") or deposit.get("status") == "published":
            raise PublicationBlocked("Published archive cannot be overwritten")
        for name, blob in self.release.uploads.items():
            files = self._request("GET", "/api/deposit/depositions/" + str(deposit["id"]) + "/files")
            existing = [item for item in files if item.get("filename", item.get("key")) == name]
            if len(existing) == 1 and _checksum_matches(existing[0], blob):
                continue
            self.state["pending"] = "upload:" + name
            self.release.journal.save("zenodo-upload-intent", name=name, sha256=sha256(blob))
            self._request("PUT", deposit["links"]["bucket"] + "/" + urllib.parse.quote(name), data=blob, content_type="application/octet-stream")
            self.state["pending"] = None
            self.release.journal.save("zenodo-upload-response", name=name)
        self._verify_files(deposit)
        self.state["status"] = "uploaded"
        self.release.journal.save("zenodo-uploads-verified")
        return self.state

    def _verify_files(self, deposit):
        remote = self._request("GET", "/api/deposit/depositions/" + str(deposit["id"]) + "/files")
        by_name = {item.get("filename", item.get("key")): item for item in remote}
        if len(by_name) != len(remote) or set(by_name) != set(self.release.uploads):
            raise PublicationBlocked("Remote archive file set differs; reconcile inherited files before publishing")
        for name, blob in self.release.uploads.items():
            if not _checksum_matches(by_name[name], blob):
                raise PublicationBlocked("Remote archive bytes differ: " + name)

    @serialized("zenodo")
    def reconcile(self):
        replay = (self.release.context.get("published_edition_replay") is not None
                  or self.release.context.get("policy", {}).get("mode") == "replay_only")
        self.release.verify_existing_archive() if replay else self.release.verify()
        self._bind_environment()
        if not self.state.get("id"):
            return self.draft(self.state.get("previous_id"))
        deposit = self._deposit(self.state["id"])
        if self.release.marker not in deposit.get("metadata", {}).get("notes", ""):
            raise PublicationBlocked("Remote archive identity differs")
        if not deposit.get("submitted") or deposit.get("state") != "done":
            if replay:
                raise PublicationBlocked("Historical replay cannot recover an unpublished archive draft")
            return self._remember(deposit)
        if replay and (deposit.get("id") != self.state.get("id")
                or deposit.get("record_id", deposit["id"]) != self.state.get("record_id")):
            raise PublicationBlocked("Historical remote record differs from its verified archive journal")
        self._verify_files(deposit)
        record_id = deposit.get('record_id', deposit['id'])
        if type(record_id) is not int or record_id <= 0:
            raise PublicationBlocked('Published archive has an invalid record identity')
        # Publication is irreversible, but authenticated metadata alone does not
        # prove that an unaffiliated reader can obtain the files. Failed public
        # checks retain the same published record for reconciliation, not another DOI.
        if not replay:
            self.state.update(status='published_unverified', verified=False,
                              anonymous_verified=False, pending='public-verification', record_id=record_id)
            self.release.journal.save('zenodo-public-verification-intent', id=record_id)
        # Historical recovery is a read-only remote recheck of an already
        # verified immutable record. Preserve that prior actual receipt on a
        # transient read failure so the same exact record can be retried.
        record = json.loads(self.public_read(self.api_origin, '/api/records/' + str(record_id), 2_000_000))
        if record.get('metadata', {}).get('access_right') != 'open':
            raise PublicationBlocked('Published archive is not publicly open access')
        doi, concept_doi = record.get("doi"), record.get("conceptdoi")
        if (not isinstance(doi, str) or not DOI.fullmatch(doi)
                or not isinstance(concept_doi, str) or not DOI.fullmatch(concept_doi)
                or (replay and concept_doi != self.release.context["report"]["archive"]["concept_doi"])
                or doi == concept_doi or doi != self.state.get("reserved_doi")
                or type(record.get("id")) is not int
                or record.get("id") != deposit.get("record_id", deposit["id"])
                or doi != ("10.5072" if self.environment == "sandbox" else "10.5281") + "/zenodo." + str(record.get("id"))):
            raise PublicationBlocked("Archive publication is not verified by the public record")
        public_files = record.get("files", [])
        by_name = {item.get("key", item.get("filename")): item for item in public_files}
        if len(by_name) != len(public_files) or set(by_name) != set(self.release.uploads):
            raise PublicationBlocked("Public record file set differs from the frozen archive")
        for name, blob in self.release.uploads.items():
            if not _checksum_matches(by_name[name], blob):
                raise PublicationBlocked("Public record archive bytes differ: " + name)
            public_blob = self.public_read(self.api_origin, '/api/records/' + str(record_id)
                + '/files/' + urllib.parse.quote(name, safe='') + '/content', len(blob))
            if public_blob != blob:
                raise PublicationBlocked('Anonymous archive bytes differ: ' + name)
        self.state.update(status="published", verified=True, anonymous_verified=True,
                          doi=doi, concept_doi=concept_doi, pending=None,
                          artifact_sha256=self.release.package_sha256, record_id=record["id"],
                          record_url=self.api_origin + "/records/" + str(record["id"]),
                          confirmed_on=datetime.now(timezone.utc).isoformat(),
                          url="https://doi.org/" + doi, published_on=record.get("metadata", {}).get("publication_date"))
        self.release.journal.save("zenodo-publication-verified", id=deposit["id"], doi=doi)
        return self.state

    @serialized("zenodo")
    def publish(self):
        self.release.verify()
        self._bind_environment()
        if not self.state.get("id"):
            raise PublicationBlocked("Create and upload the archive draft first")
        deposit = self._deposit(self.state["id"])
        if deposit.get("submitted"):
            return self.reconcile()
        if self.release.marker not in deposit.get("metadata", {}).get("notes", ""):
            raise PublicationBlocked("Remote draft identity differs")
        self._remember(deposit)
        self._verify_files(deposit)
        if self.state.get("pending") == "publish":
            raise AmbiguousRemoteState("Publish response was lost; wait for remote reconciliation")
        self.state["pending"] = "publish"
        self.release.journal.save("zenodo-publish-intent", id=deposit["id"])
        self._request("POST", "/api/deposit/depositions/" + str(deposit["id"]) + "/actions/publish")
        return self.reconcile()


class GitHubMirror:
    """Mirror exact archive bytes only after Zenodo publication is verified."""
    def __init__(self, release, repository, token=None, transport=None, upload_transport=None, *, source_commit):
        if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise PublicationBlocked("GitHub mirror requires the approved full lowercase source commit SHA")
        self.source_commit = source_commit
        if len(repository.split("/")) != 2 or any(not part for part in repository.split("/")):
            raise ValueError("Expected owner/repository")
        self.release, self.repository = release, repository
        self.http = transport or HTTP(token, "https://api.github.com")
        self.upload_http = upload_transport or HTTP(token, "https://uploads.github.com")
        self.state = release.journal.state["github"]

    def _verify_source_tag(self, tag):
        remote = self.http.request("GET", "/repos/" + self.repository + "/git/ref/tags/" + tag)
        if (not isinstance(remote, dict) or remote.get("ref") != "refs/tags/" + tag
                or remote.get("object", {}).get("type") != "commit"
                or remote.get("object", {}).get("sha") != self.source_commit):
            raise PublicationBlocked("GitHub mirror requires its exact pre-existing lightweight source tag")

    @serialized("github")
    def publish(self):
        archive = self.release.require_archive()
        prefix = "/repos/" + self.repository + "/releases"
        tag = "research-" + self.release.context["report"]["release_id"]
        if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in tag):
            raise PublicationBlocked("Unsafe release tag")
        # This is retained-history consistency, not tamperproof authentication.
        # Losing one live field cannot authorize rebinding prior mirror work.
        events = self.release.journal.state.get("events")
        if (not isinstance(self.state, dict) or not isinstance(events, list)
                or any(not isinstance(event, dict) or not isinstance(event.get("operation"), str)
                       for event in events)):
            raise PublicationBlocked("GitHub source binding requires valid retained journal history")
        bindings = [event.get("source_commit") for event in events
                    if event["operation"] == "github-source-commit-bound"]
        if any(not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
               for commit in bindings):
            raise PublicationBlocked("GitHub retained source binding has an invalid source commit")
        if self.state.get("source_commit") not in (None, self.source_commit):
            raise PublicationBlocked("GitHub mirror journal belongs to a different source commit")
        if bindings:
            if (len(bindings) != 1 or bindings[0] != self.source_commit
                    or self.state.get("source_commit") != self.source_commit):
                raise PublicationBlocked("GitHub source identity was lost or conflicts with retained journal history")
        elif (self.state != {"status": "prepared"}
              or any(event["operation"].startswith("github-") for event in events)):
            raise PublicationBlocked("GitHub source binding is missing from retained journal history")
        if self.state.get("source_commit") is None:
            self.state["source_commit"] = self.source_commit
            self.release.journal.save("github-source-commit-bound", source_commit=self.source_commit)
        self.state.update(status="verifying", verified=False)
        self.release.journal.save("github-verification-intent", source_commit=self.source_commit)
        self._verify_source_tag(tag)
        page, matches = 1, []
        while True:
            releases = self.http.request("GET", prefix + "?per_page=100&page=" + str(page))
            matches.extend(item for item in releases if item.get("tag_name") == tag)
            if len(releases) < 100:
                break
            page += 1
            if page > 1000:
                raise AmbiguousRemoteState("GitHub reconciliation pagination exceeded bound")
        if len(matches) > 1:
            raise AmbiguousRemoteState("Multiple GitHub releases have the release tag")
        if not matches and self.state.get("id"):
            # A temporarily incomplete listing must not cause another create.
            known = self.http.request("GET", prefix + "/" + str(self.state["id"]))
            if known.get("tag_name") != tag:
                raise PublicationBlocked("Known GitHub release identity differs")
            matches = [known]
        if matches:
            remote = matches[0]
            if self.release.marker not in remote.get("body", ""):
                raise PublicationBlocked("GitHub tag belongs to different package bytes")
        else:
            if self.state.get("pending") == "create":
                raise AmbiguousRemoteState("Prior GitHub release create remains unresolved")
            self.state["pending"] = "create"
            self.release.journal.save("github-create-intent", tag=tag)
            remote = self.http.request("POST", prefix, payload={"tag_name": tag, "target_commitish": self.source_commit, "draft": True,
                "name": self.release.context["report"]["title"],
                "body": "Archive: " + archive["url"] + "\n\n" + self.release.marker})
        self.state.update(id=remote["id"], pending=None, status="draft")
        self.release.journal.save("github-draft-reconciled", id=remote["id"])
        assets = self.http.request("GET", prefix + "/" + str(remote["id"]) + "/assets?per_page=100")
        expected = {"research-archive.zip": (self.release.package / "research-archive.zip").read_bytes()}
        for name, blob in expected.items():
            matching = [item for item in assets if item["name"] == name]
            if matching:
                if len(matching) != 1 or matching[0].get("digest") != "sha256:" + sha256(blob) or matching[0].get("size") != len(blob):
                    raise PublicationBlocked("Existing GitHub asset differs from package")
                continue
            if not remote.get("draft"):
                raise PublicationBlocked("Published GitHub mirror is missing its exact archive")
            self.state["pending"] = "upload"
            self.release.journal.save("github-upload-intent", sha256=sha256(blob))
            self.upload_http.request("POST", "/repos/" + self.repository + "/releases/" + str(remote["id"]) + "/assets?name=" + name,
                                     data=blob, content_type="application/zip")
        # Re-read after every upload, including recovery after a lost response.
        assets = self.http.request("GET", prefix + "/" + str(remote["id"]) + "/assets?per_page=100")
        if len(assets) != 1 or assets[0].get("digest") != "sha256:" + sha256(expected["research-archive.zip"]):
            raise PublicationBlocked("GitHub mirror assets are not verified")
        self._verify_source_tag(tag)
        if remote.get("draft"):
            self.state["pending"] = "publish"
            self.release.journal.save("github-publish-intent", id=remote["id"])
            self.http.request("PATCH", prefix + "/" + str(remote["id"]), payload={"draft": False})
        remote = self.http.request("GET", prefix + "/" + str(remote["id"]))
        if remote.get("tag_name") != tag or self.release.marker not in remote.get("body", ""):
            raise PublicationBlocked("Published GitHub release identity differs from the source-bound package")
        if remote.get("draft") or not remote.get("published_at"):
            raise AmbiguousRemoteState("GitHub release has not become publicly published")
        self._verify_source_tag(tag)
        self.state.update(status="published", verified=True, pending=None, url=remote["html_url"])
        self.release.journal.save("github-publication-verified")
        return self.state


class HuggingFaceMirror:
    """Use the official optional Hub SDK; no implicit login or stored credentials."""
    def __init__(self, release, repository, token=None, api=None, downloader=None, operation_factory=None,
                 public_downloader=None):
        if api is None:
            if not token:
                raise PublicationBlocked("Connect the Hugging Face account before remote operations")
            try:
                from huggingface_hub import HfApi, hf_hub_download, CommitOperationAdd
            except ImportError:
                raise PublicationBlocked("Install the optional huggingface_hub package for this adapter") from None
            api = HfApi(endpoint="https://huggingface.co", token=token)
            downloader = lambda **kwargs: hf_hub_download(endpoint="https://huggingface.co", token=token, **kwargs)
            public_downloader = lambda **kwargs: hf_hub_download(endpoint="https://huggingface.co", token=False, **kwargs)
            operation_factory = CommitOperationAdd
        if downloader is None or operation_factory is None or public_downloader is None:
            raise ValueError("An injected SDK client requires authenticated and anonymous downloaders and its operation factory")
        self.release, self.repository, self.api = release, repository, api
        self.download, self.operation_factory = downloader, operation_factory
        self.public_download = public_downloader
        self.state = release.journal.state["huggingface"]

    def _published_readme(self, archive):
        """A live destination card uses the actual receipt, outside the frozen ZIP."""
        context = self.release.context
        if archive.get('release_id', context['report']['release_id']) != context['report']['release_id']:
            raise PublicationBlocked('Archive receipt belongs to another research edition')
        receipt = {**archive, 'release_id': context['report']['release_id']}
        candidate = {**context, 'report': {**context['report'], 'archive': receipt}}
        if (not published_archive(candidate)
                or receipt['artifact_sha256'] != sha256((self.release.package / 'research-archive.zip').read_bytes())):
            raise PublicationBlocked('A typed verified production archive receipt is required for the public dataset card')
        metadata = json.loads((self.release.package / 'metadata.json').read_bytes())
        if metadata.get('version') != context['report']['release_id']:
            raise PublicationBlocked('Dataset-card metadata belongs to another research edition')
        metadata.update(status='published', doi=receipt['doi'], url=receipt['record_url'],
                        note='Published archived edition.')
        if receipt.get('published_on'):
            metadata['published_on'] = receipt['published_on']
        try:
            from research_citations import citation_formats
        except ImportError:
            from scripts.research_citations import citation_formats
        citation = citation_formats(metadata)['citation.bib'].decode('utf-8').rstrip()
        # Resolve HEAD once, then pin every read and verify this edition's bytes.
        # An old card must refuse a newer main branch rather than miscite its data.
        example = f'''import hashlib, json, os, re
from urllib.request import urlopen

repository = {self.repository!r}
revision = os.environ.get("STS_RESEARCH_REVISION")
if not revision:
    with urlopen("https://huggingface.co/api/datasets/" + repository, timeout=30) as response:
        revision = json.load(response)["sha"]
if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{{40}}", revision):
    raise ValueError("Select an immutable Hub commit, not a branch or tag.")
url = "https://huggingface.co/datasets/" + repository + "/resolve/" + revision + "/clean-dataset.json"
with urlopen(url, timeout=60) as response:
    raw = response.read()
if hashlib.sha256(raw).hexdigest() != {sha256((self.release.package / 'clean-dataset.json').read_bytes())!r}:
    raise ValueError("Different edition: select this edition's immutable Hub commit or use its version DOI.")
data = json.loads(raw)
if data["release_id"] != {metadata['version']!r}:
    raise ValueError("The dataset release does not match this citation.")
graph = data["graph"]
approved = [claim for claim in graph["assertions"] if claim["status"] == "approved"]
sources = {{source["id"]: source for source in graph["sources"]}}
print(data["release_id"], len(approved), "approved assertions")
for claim in approved[:1]:
    print(claim["id"], claim["subject_id"], claim["predicate"], claim["value"])
    for evidence in claim["evidence"]:
        print(sources[evidence["source_id"]]["url"], evidence["locator"])
'''
        return ('---\nlicense: cc-by-4.0\nlanguage:\n- en\n---\n\n# ' + metadata['title']
            + '\n\nPublished research edition **' + metadata['version'] + '**.\n\n'
            + '[Permanent version DOI](https://doi.org/' + receipt['doi'] + ') · '
            + '[Verified archival record](' + receipt['record_url'] + ')\n\n'
            + 'The archive and clean dataset mirror the exact verified edition. The archive manifest identifies every frozen file. '
            + 'Publication status inside the frozen source context describes package preparation; this card records the actual subsequent archival publication.\n\n'
            + '## Citation\n\n```bibtex\n' + citation + '\n```\n\n'
            + '## Load this edition and follow its evidence\n\n'
            + 'This Python example uses only the standard library and anonymous requests. It resolves the Hub commit once, '
            + 'checks this edition\'s SHA-256 and release ID, then follows an approved assertion to its source and locator. '
            + 'For a historical edition, set `STS_RESEARCH_REVISION` to its immutable commit from Files and versions. '
            + 'If the mirror has advanced, the example refuses different bytes; the version DOI above retains the exact archive.\n\n'
            + '```python\n' + example + '```\n\n'
            + 'For offline tables, extract `research-archive.zip` and run '
            + '`python3 reproduce.py --write-tables reproduced` inside the extracted directory. '
            + 'This verifies the manifest, checks the JSON/CSV/SQLite equivalence and reproduces the included tables without network access.\n\n'
            + 'Owned research and the public projection use CC BY 4.0. Third-party source text, personal contacts and media are excluded from that license. '
            + 'See the archive licenses and font provenance before reuse. Separate AI review does not imply human peer review.\n').encode('utf-8')

    def _matches(self, revision, readme):
        try:
            path = self.download(repo_id=self.repository, repo_type="dataset",
                filename="publication-manifest.json", revision=revision, force_download=True)
        except Exception as error:
            # Only a confirmed missing file is a safe absence. Network/auth
            # failures must not be treated as authorization to upload again.
            if type(error).__name__ in ("EntryNotFoundError", "RemoteEntryNotFoundError"):
                return False
            raise
        if Path(path).read_bytes() != (self.release.package / "MANIFEST.json").read_bytes():
            return False
        try:
            path = self.download(repo_id=self.repository, repo_type='dataset', filename='README.md',
                                 revision=revision, force_download=True)
        except Exception as error:
            if type(error).__name__ in ('EntryNotFoundError', 'RemoteEntryNotFoundError'):
                return False
            raise
        return Path(path).read_bytes() == readme

    @serialized("huggingface")
    def publish(self):
        archive = self.release.require_archive()
        self.state.update(status="verifying", verified=False)
        self.release.journal.save("huggingface-verification-intent")
        readme = self._published_readme(archive)
        info = self.api.repo_info(repo_id=self.repository, repo_type="dataset")
        if getattr(info, "private", None) is not False:
            raise PublicationBlocked("A public Hub dataset repository is required for a published mirror")
        if not self._matches(info.sha, readme):
            if self.state.get("pending") == "commit":
                raise AmbiguousRemoteState("Prior Hub commit remains unresolved; inspect remote revision")
            operations = [self.operation_factory(path_in_repo=name, path_or_fileobj=blob) for name, blob in {
                "README.md": readme,
                "research-archive.zip": (self.release.package / "research-archive.zip").read_bytes(),
                "clean-dataset.json": (self.release.package / "clean-dataset.json").read_bytes(),
                "publication-manifest.json": (self.release.package / "MANIFEST.json").read_bytes()}.items()]
            self.state.update(pending="commit", parent_commit=info.sha)
            self.release.journal.save("huggingface-commit-intent", parent_commit=info.sha)
            self.api.create_commit(repo_id=self.repository, repo_type="dataset", operations=operations,
                commit_message="ScienceToStartup " + self.release.context["report"]["release_id"],
                commit_description="Archive: " + archive["url"] + "\n" + self.release.marker,
                parent_commit=info.sha)
        info = self.api.repo_info(repo_id=self.repository, repo_type="dataset")
        if getattr(info, "private", None) is not False:
            raise PublicationBlocked("Hub mirror visibility is no longer public")
        if not self._matches(info.sha, readme):
            raise AmbiguousRemoteState("Hub mirror did not reconcile to the exact publication manifest")
        # Verify actual uploaded files at the same immutable commit, not merely
        # the marker/manifest that could coexist with stale payload bytes.
        for name in ("research-archive.zip", "clean-dataset.json"):
            path = self.download(repo_id=self.repository, repo_type="dataset", filename=name,
                revision=info.sha, force_download=True)
            if Path(path).read_bytes() != (self.release.package / name).read_bytes():
                raise PublicationBlocked("Hub mirror bytes differ at verified commit: " + name)
        # Public metadata and an authenticated download do not prove that an
        # unaffiliated reader can retrieve a gated/restricted dataset. Verify all
        # four payloads anonymously at the same immutable commit before success.
        self.state.update(pending="public-verification", anonymous_verified=False)
        self.release.journal.save("huggingface-public-verification-intent", commit=info.sha)
        for remote, expected in {"README.md": readme,
                              "publication-manifest.json": (self.release.package / 'MANIFEST.json').read_bytes(),
                              "research-archive.zip": (self.release.package / 'research-archive.zip').read_bytes(),
                              "clean-dataset.json": (self.release.package / 'clean-dataset.json').read_bytes()}.items():
            path = self.public_download(repo_id=self.repository, repo_type="dataset", filename=remote,
                                        revision=info.sha, force_download=True)
            if Path(path).read_bytes() != expected:
                raise PublicationBlocked("Anonymous Hub mirror bytes differ at verified commit: " + remote)
        current = self.api.repo_info(repo_id=self.repository, repo_type="dataset")
        if getattr(current, "private", None) is not False:
            raise PublicationBlocked("Hub mirror visibility changed during public verification")
        self.state.update(status="published", verified=True, pending=None, commit=info.sha,
                          anonymous_verified=True,
                          readme_sha256=sha256(readme), archive_doi=archive['doi'],
                          url="https://huggingface.co/datasets/" + self.repository + "/tree/" + info.sha)
        self.release.journal.save("huggingface-publication-verified", commit=info.sha)
        return self.state
