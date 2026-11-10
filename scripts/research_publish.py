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
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from research_citations import ROOT, DOI, CONTEXT_CONTRACT_VERSION, RESERVATION_FIELDS, context_digest, json_bytes, sha256, source_context, publication_metadata, zenodo_metadata, read_prepared_package
except ImportError:
    from scripts.research_citations import ROOT, DOI, CONTEXT_CONTRACT_VERSION, RESERVATION_FIELDS, context_digest, json_bytes, sha256, source_context, publication_metadata, zenodo_metadata, read_prepared_package


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

    def request(self, method, path, payload=None, data=None, content_type=None):
        url = path if path.startswith("https://") else self.origin + path
        parsed = urllib.parse.urlsplit(url)
        # Remote links may be followed only on the configured API origin. This
        # also prevents remote-controlled links from exfiltrating bearer tokens.
        if parsed.scheme != "https" or parsed.netloc != urllib.parse.urlsplit(self.origin).netloc:
            raise PublicationBlocked("Unexpected publication API origin")
        headers = {"Authorization": "Bearer " + self.token,
                   "User-Agent": "ScienceToStartup-research-publisher/1.0 (+https://sciencetostartup.com/research/)",
                   "Accept": "application/json"}
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
        # Resume the exact existing reservation marker, including legacy v1.
        # A new journal always binds the owned scientific inputs through v2.
        prior = json.loads(Path(journal_path).read_text()) if Path(journal_path).exists() else None
        self.context_contract_version = prior.get("context_contract_version", 1) if prior is not None else CONTEXT_CONTRACT_VERSION
        self.source_sha256 = sha256(json_bytes(source_context(context, reservation=False, version=self.context_contract_version)))
        self.journal = Journal(journal_path, context["report"]["release_id"], context_sha256=self.source_sha256)
        self.journal.state["context_contract_version"] = self.context_contract_version

    def verify(self):
        gate = archival_gate(self.context)
        if sha256(json_bytes(source_context(self.context, reservation=False, version=self.context_contract_version))) != self.source_sha256:
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
            if not DOI.fullmatch(state.get("reserved_doi") or "") or not state.get("id"):
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
                    or sha256(json_bytes(source_context(context, reservation=False, version=reservation.context_contract_version))) != reservation.source_sha256
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
        if self.manifest.get("context_sha256") != context_digest(self.context, version=self.manifest.get("context_contract_version", 1)):
            raise PublicationBlocked("Package context is stale.")
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
            read_prepared_package(self.context, self.package, expected_archive_sha256=self.package_sha256)
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

    def require_archive(self):
        self.verify()
        receipt = self.journal.state["zenodo"]
        if (receipt.get("status") != "published" or receipt.get("verified") is not True
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
            if self.context["report"].get("edition_date"):
                value["edition_date"] = self.context["report"]["edition_date"]
            return value


def _checksum_matches(remote, blob):
    checksum = remote.get("checksum", "")
    return (checksum.removeprefix("md5:") == hashlib.md5(blob).hexdigest()
            and remote.get("filesize", remote.get("size")) == len(blob))


class Zenodo:
    def __init__(self, release, token=None, transport=None, sandbox=False):
        self.release = release
        self.api_origin = "https://sandbox.zenodo.org" if sandbox else "https://zenodo.org"
        self.environment = "sandbox" if sandbox else "production"
        self.http = transport or HTTP(token, self.api_origin)
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
        reservation = deposit.get("metadata", {}).get("prereserve_doi")
        reserved = reservation.get("doi") if isinstance(reservation, dict) else None
        if not isinstance(reserved, str) or not DOI.fullmatch(reserved):
            raise PublicationBlocked("Zenodo did not return one reserved version DOI")
        if self.state.get("reserved_doi") not in (None, reserved):
            raise PublicationBlocked("Reserved version DOI changed")
        pending = "publish" if self.state.get("pending") == "publish" else None
        self.state.update(id=deposit["id"], status="draft", pending=pending,
                          reserved_doi=reserved)
        self.release.journal.save("zenodo-draft-reconciled", id=deposit["id"])
        return deposit

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
        if self.state.get("status") == "published":
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
        self.release.verify()
        self._bind_environment()
        if not self.state.get("id"):
            return self.draft(self.state.get("previous_id"))
        deposit = self._deposit(self.state["id"])
        if self.release.marker not in deposit.get("metadata", {}).get("notes", ""):
            raise PublicationBlocked("Remote archive identity differs")
        if not deposit.get("submitted") or deposit.get("state") != "done":
            return self._remember(deposit)
        self._verify_files(deposit)
        record = self._request("GET", "/api/records/" + str(deposit.get("record_id", deposit["id"])))
        doi, concept_doi = record.get("doi"), record.get("conceptdoi")
        if (not isinstance(doi, str) or not DOI.fullmatch(doi)
                or not isinstance(concept_doi, str) or not DOI.fullmatch(concept_doi)
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
        self.state.update(status="published", verified=True, doi=doi, concept_doi=concept_doi, pending=None,
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
        self._verify_files(deposit)
        if self.state.get("pending") == "publish":
            raise AmbiguousRemoteState("Publish response was lost; wait for remote reconciliation")
        self.state["pending"] = "publish"
        self.release.journal.save("zenodo-publish-intent", id=deposit["id"])
        self._request("POST", "/api/deposit/depositions/" + str(deposit["id"]) + "/actions/publish")
        return self.reconcile()


class GitHubMirror:
    """Mirror exact archive bytes only after Zenodo publication is verified."""
    def __init__(self, release, repository, token=None, transport=None, upload_transport=None):
        if len(repository.split("/")) != 2 or any(not part for part in repository.split("/")):
            raise ValueError("Expected owner/repository")
        self.release, self.repository = release, repository
        self.http = transport or HTTP(token, "https://api.github.com")
        self.upload_http = upload_transport or HTTP(token, "https://uploads.github.com")
        self.state = release.journal.state["github"]

    @serialized("github")
    def publish(self):
        archive = self.release.require_archive()
        prefix = "/repos/" + self.repository + "/releases"
        tag = "research-" + self.release.context["report"]["release_id"]
        if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in tag):
            raise PublicationBlocked("Unsafe release tag")
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
            remote = self.http.request("POST", prefix, payload={"tag_name": tag, "draft": True,
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
        if remote.get("draft"):
            self.state["pending"] = "publish"
            self.release.journal.save("github-publish-intent", id=remote["id"])
            self.http.request("PATCH", prefix + "/" + str(remote["id"]), payload={"draft": False})
        remote = self.http.request("GET", prefix + "/" + str(remote["id"]))
        if remote.get("draft") or not remote.get("published_at"):
            raise AmbiguousRemoteState("GitHub release has not become publicly published")
        self.state.update(status="published", verified=True, pending=None, url=remote["html_url"])
        self.release.journal.save("github-publication-verified")
        return self.state


class HuggingFaceMirror:
    """Use the official optional Hub SDK; no implicit login or stored credentials."""
    def __init__(self, release, repository, token=None, api=None, downloader=None, operation_factory=None):
        if api is None:
            if not token:
                raise PublicationBlocked("Connect the Hugging Face account before remote operations")
            try:
                from huggingface_hub import HfApi, hf_hub_download, CommitOperationAdd
            except ImportError:
                raise PublicationBlocked("Install the optional huggingface_hub package for this adapter") from None
            api = HfApi(token=token)
            downloader = lambda **kwargs: hf_hub_download(token=token, **kwargs)
            operation_factory = CommitOperationAdd
        if downloader is None or operation_factory is None:
            raise ValueError("An injected SDK client requires its downloader and operation factory")
        self.release, self.repository, self.api = release, repository, api
        self.download, self.operation_factory = downloader, operation_factory
        self.state = release.journal.state["huggingface"]

    def _matches(self, revision):
        try:
            path = self.download(repo_id=self.repository, repo_type="dataset",
                filename="publication-manifest.json", revision=revision, force_download=True)
        except Exception as error:
            # Only a confirmed missing file is a safe absence. Network/auth
            # failures must not be treated as authorization to upload again.
            if type(error).__name__ in ("EntryNotFoundError", "RemoteEntryNotFoundError"):
                return False
            raise
        return Path(path).read_bytes() == (self.release.package / "MANIFEST.json").read_bytes()

    @serialized("huggingface")
    def publish(self):
        archive = self.release.require_archive()
        info = self.api.repo_info(repo_id=self.repository, repo_type="dataset")
        if getattr(info, "private", None) is not False:
            raise PublicationBlocked("A public Hub dataset repository is required for a published mirror")
        if not self._matches(info.sha):
            if self.state.get("pending") == "commit":
                raise AmbiguousRemoteState("Prior Hub commit remains unresolved; inspect remote revision")
            operations = [self.operation_factory(path_in_repo=name, path_or_fileobj=blob) for name, blob in {
                "README.md": (self.release.package / "huggingface-README.md").read_bytes(),
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
        if not self._matches(info.sha):
            raise AmbiguousRemoteState("Hub mirror did not reconcile to the exact publication manifest")
        # Verify actual uploaded files at the same immutable commit, not merely
        # the marker/manifest that could coexist with stale payload bytes.
        for name in ("research-archive.zip", "clean-dataset.json"):
            path = self.download(repo_id=self.repository, repo_type="dataset", filename=name,
                revision=info.sha, force_download=True)
            if Path(path).read_bytes() != (self.release.package / name).read_bytes():
                raise PublicationBlocked("Hub mirror bytes differ at verified commit: " + name)
        self.state.update(status="published", verified=True, pending=None, commit=info.sha,
                          url="https://huggingface.co/datasets/" + self.repository + "/tree/" + info.sha)
        self.release.journal.save("huggingface-publication-verified", commit=info.sha)
        return self.state
