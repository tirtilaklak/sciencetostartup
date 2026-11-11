"""Offline Hub mirror staging and conservative, non-secret scope interpretation.

This tool never reads credentials, makes HTTP requests, creates a repository, or
uploads files. It delegates scientific package verification to the existing
frozen-package reader. A staged prelaunch bundle remains a prelaunch bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
HANDLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
OBJECT_ID = re.compile(r"[0-9a-f]{24}\Z")
MIRROR_FILES = {
    "README.md": "huggingface-README.md",
    "research-archive.zip": "research-archive.zip",
    "clean-dataset.json": "clean-dataset.json",
    "publication-manifest.json": "MANIFEST.json",
}
CITATION_FILES = ("CITATION.cff", "citation.bib", "citation.ris", "citation.csl.json", "metadata.json")


def valid_repository(value):
    return isinstance(value, str) and bool(REPO.fullmatch(value)) and ".." not in value and not value.endswith((".", ".git"))


def scope_evidence(identity, dataset, repository):
    """Interpret GET responses without claiming a successful remote write.

Only established schema fields influence the result. Raw responses, email,
token display names, identifiers and permission strings are never returned.
An unknown/changed schema fails closed. A read-only organization membership
does not prove permission to create or modify an organization repository.
"""
    if not valid_repository(repository):
        raise ValueError("Expected an explicit namespace/dataset repository")
    identity = identity if isinstance(identity, dict) else {}
    dataset = dataset if isinstance(dataset, dict) else {}
    namespace = repository.split("/", 1)[0]
    name = identity.get("name")
    safe_name = name if isinstance(name, str) and HANDLE.fullmatch(name) else None
    owner = safe_name == namespace and identity.get("type") == "user"
    organizations = identity.get("orgs", [])
    organizations = organizations if isinstance(organizations, list) else []
    membership = any(isinstance(org, dict) and org.get("name") == namespace for org in organizations)
    auth = identity.get("auth", {})
    token = auth.get("accessToken", {}) if isinstance(auth, dict) else {}
    token = token if isinstance(token, dict) else {}
    fine = token.get("fineGrained", {})
    fine = fine if isinstance(fine, dict) else {}
    scoped = fine.get("scoped", [])
    owner_id = identity.get("id")
    owner_id_known = isinstance(owner_id, str) and bool(OBJECT_ID.fullmatch(owner_id))
    identity_valid = safe_name is not None and identity.get("type") == "user" and owner_id_known
    # These are the complete authorization-container keys in the validated Hub
    # response. Metadata is recognized explicitly; unknown grant locations hold.
    authorization_schema_valid = (
        identity_valid and isinstance(auth, dict)
        and set(auth) == {"type", "accessToken"} and auth["type"] == "access_token"
        and set(token) == {"displayName", "role", "createdAt", "fineGrained"}
        and isinstance(token["displayName"], str) and isinstance(token["createdAt"], str)
        and set(fine) == {"scoped", "global", "canReadGatedRepos"})
    # Hub includes a zero-permission owner descriptor beside the dataset grant.
    # It is metadata only when both identifiers bind the authenticated owner.
    def empty_owner_descriptor(entry):
        if not isinstance(entry, dict) or set(entry) != {"entity", "permissions"}:
            return False
        entity = entry["entity"]
        return (identity_valid and entry["permissions"] == [] and isinstance(entity, dict)
                and set(entity) == {"type", "_id", "name"}
                and entity["type"] == "user" and entity["_id"] == owner_id
                and entity["name"] == safe_name)
    resources = ([entry for entry in scoped if not empty_owner_descriptor(entry)]
                 if isinstance(scoped, list) else [])
    target_only = False
    write = False
    content_only = False
    repo_id = dataset.get("id")
    dataset_matches = repo_id == repository
    object_id = dataset.get("_id")
    dataset_identity_valid = (dataset_matches and isinstance(object_id, str)
                              and bool(OBJECT_ID.fullmatch(object_id)))
    if "name" in dataset:
        dataset_identity_valid = (dataset_identity_valid and isinstance(dataset["name"], str)
                                  and dataset["name"] in {repository, repository.split("/", 1)[1]})
    if "author" in dataset:
        dataset_identity_valid = dataset_identity_valid and dataset["author"] == namespace
    dataset_author_id = dataset.get("authorId")
    if "authorId" in dataset:
        dataset_identity_valid = (dataset_identity_valid and isinstance(dataset_author_id, str)
                                  and bool(OBJECT_ID.fullmatch(dataset_author_id))
                                  and (not owner or dataset_author_id == owner_id))
    expected_author_id = dataset_author_id if "authorId" in dataset else owner_id if owner else None
    if (authorization_schema_valid and token.get("role") == "fineGrained" and dataset_identity_valid
            and isinstance(scoped, list) and 1 <= len(scoped) <= 2 and len(resources) == 1
            and not (set(fine) - {"scoped", "global", "canReadGatedRepos"})
            and fine.get("global", []) == [] and fine.get("canReadGatedRepos", False) is False):
        entry = resources[0]
        entry = entry if isinstance(entry, dict) else {}
        entity = entry.get("entity", {})
        entity = entity if isinstance(entity, dict) else {}
        id_matches = (isinstance(object_id, str) and bool(OBJECT_ID.fullmatch(object_id))
                      and entity.get("_id") == object_id)
        permissions = entry.get("permissions", [])
        author_matches = ("authorId" not in entity or
                          (expected_author_id is not None and entity["authorId"] == expected_author_id))
        name_consistent = "name" not in entity or entity["name"] == repository
        if (not (set(entry) - {"entity", "permissions"})
                and not (set(entity) - {"type", "_id", "name", "authorId"})
                and author_matches and name_consistent
                and entity.get("type") == "dataset" and id_matches
                and isinstance(permissions, list) and all(isinstance(item, str) for item in permissions)):
            rights = set(permissions)
            # The current Hub UI automatically includes access-request read
            # with selected-repository write. It is still limited to that repo.
            target_only = bool(rights) and rights <= {"repo.content.read", "repo.content.write", "repo.access.read", "repo.write"}
            write = target_only and bool(rights & {"repo.content.write", "repo.write"})
            content_only = write and rights <= {"repo.content.read", "repo.content.write"}
    return {
        "authenticated_user": safe_name,
        "repository": repository,
        "repository_identity_matches": bool(dataset_identity_valid),
        "namespace_relation": "personal-owner" if owner else "organization-member" if membership else "unconfirmed",
        "namespace_creation_permission_verified": bool(owner and authorization_schema_valid),
        "repository_private": dataset.get("private") if type(dataset.get("private")) is bool else None,
        "fine_grained": token.get("role") == "fineGrained",
        "target_only_scope_evidence": target_only,
        "target_write_scope_evidence": write,
        "content_only_scope_evidence": content_only,
        "remote_write_verified": False,
        "publication_authorized": False,
    }


def _descriptor(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def _open_directory_chain(path, forbidden_identity):
    """Anchor an existing private parent through protected canonical ancestors.

    The operator must trust processes running as this user. Mode checks do not
    protect against a hostile same-user process, root, or filesystem ACL grants.
    """
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in (None, *path.parts[1:]):
            if part is not None:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) == forbidden_identity:
                raise ValueError("Keep local staging outside the scientific source checkout")
            # A root-owned sticky system temporary ancestor is acceptable:
            # its sticky bit protects this user's private child from others.
            sticky_system = opened.st_uid == 0 and bool(opened.st_mode & stat.S_ISVTX)
            if (opened.st_uid not in {0, os.getuid()}
                    or (opened.st_mode & 0o022 and not sticky_system)):
                raise ValueError("Staging ancestors must be protected from other users")
        if opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) != 0o700:
            raise ValueError("Staging parent must already be user-owned with mode 0700")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _same_directory(path, descriptor):
    info = path.lstat()
    opened = os.fstat(descriptor)
    return (info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino)


def _same_entry(directory_fd, name, identity):
    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    return (info.st_dev, info.st_ino) == identity


def _create_private_directory(parent_fd, name):
    """Exclusively create, then reject a changed mkdir/open handoff."""
    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=parent_fd)
    opened = os.fstat(descriptor)
    if ((opened.st_dev, opened.st_ino) != (created.st_dev, created.st_ino)
            or opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) != 0o700):
        os.close(descriptor)
        raise ValueError("Staging directory changed while opening; retained without writing")
    return descriptor


def _write_new_file(directory_fd, name, blob):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
    owned = os.fstat(descriptor)
    # Partial files are deliberately retained on failure. A pathname identity
    # check followed by unlink cannot safely remove a concurrently replaced file.
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    return (owned.st_dev, owned.st_ino)


def stage(source_root, output):
    """Stage under a trusted private parent; retain incomplete trees on failure."""
    source_root = Path(source_root).resolve()
    requested = Path(output).absolute()
    if requested.is_symlink() or requested.exists():
        raise ValueError("Staging destination must be new; existing files are never replaced")
    # Resolve ordinary aliases (e.g. macOS /tmp) before opening no-follow anchors.
    output = requested.resolve(strict=False)
    if output.is_relative_to(source_root):
        raise ValueError("Keep local staging outside the scientific source checkout")
    source_info = source_root.stat()
    parent_fd = _open_directory_chain(output.parent, (source_info.st_dev, source_info.st_ino))
    destination_fd = None
    folders, files = {}, {}
    try:
        sys.path.insert(0, str(source_root / "scripts"))
        from research_report import build_context
        from research_citations import read_prepared_package
        context = build_context(source_root)
        package = context.get("prepared_package")
        if not package:
            raise ValueError("No source-selected frozen package exists")
        frozen = read_prepared_package(context, package)
        prepared = json.loads(frozen["PREPARED.json"])
        metadata = json.loads(frozen["metadata.json"])
        if (requested.resolve(strict=False) != output
                or not _same_directory(output.parent, parent_fd)):
            raise ValueError("Staging parent changed during verification")
        # mkdir is exclusive: a destination that appeared while verifying fails.
        try:
            destination_fd = _create_private_directory(parent_fd, output.name)
        except FileExistsError:
            raise ValueError("Staging destination appeared during verification; it was not replaced") from None
        inventory = {}
        for folder, mapping in (("mirror-staging", MIRROR_FILES),
                                ("citation-projection", {name: name for name in CITATION_FILES})):
            folder_fd = _create_private_directory(destination_fd, folder)
            folders[folder] = folder_fd
            files[folder] = {}
            for destination, source in mapping.items():
                blob = frozen[source]
                files[folder][destination] = _write_new_file(folder_fd, destination, blob)
                inventory[f"{folder}/{destination}"] = {"source_member": source, **_descriptor(blob)}
            os.fsync(folder_fd)
        status = {
            "schema_version": 1,
            "operation": "offline-staging-only",
            "account_connection": "not-checked-by-offline-stager",
            "repository": None,
            "recommended_repository_slug": "sciencetostartup-research",
            "release_id": prepared["release_id"],
            "release_status": metadata["status"],
            "context_contract_version": prepared["context_contract_version"],
            "context_sha256": prepared["context_sha256"],
            "manifest_sha256": prepared["manifest_sha256"],
            "archive_sha256": prepared["archive_sha256"],
            "archive_bytes": prepared["archive_bytes"],
            "frozen_package_verified": True,
            "scientific_gate": context.get("gate", {}),
            "publication_policy_mode": context.get("policy", {}).get("mode"),
            "publication_authorized": False,
            "network_operations": 0,
            "files": inventory,
        }
        files[""] = {"staging-status.json": _write_new_file(destination_fd, "staging-status.json",
                        (json.dumps(status, indent=2, sort_keys=True) + "\n").encode())}
        os.fsync(destination_fd)
        os.fsync(parent_fd)
        current = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        owned = os.fstat(destination_fd)
        if (requested.resolve(strict=False) != output
                or not _same_directory(output.parent, parent_fd)
                or (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino)):
            raise ValueError("Staging destination changed while writing; replacement was not modified")
        for folder, folder_fd in folders.items():
            opened = os.fstat(folder_fd)
            if not _same_entry(destination_fd, folder, (opened.st_dev, opened.st_ino)):
                raise ValueError("Staging child changed while writing; replacement was not modified")
        for folder, entries in files.items():
            directory_fd = folders[folder] if folder else destination_fd
            if not all(_same_entry(directory_fd, name, identity) for name, identity in entries.items()):
                raise ValueError("Staging file changed while writing; replacement was not modified")
        return status
    finally:
        # No automatic unlink/rmdir: retain failed output for operator inspection.
        for descriptor in folders.values():
            os.close(descriptor)
        if destination_fd is not None:
            os.close(destination_fd)
        os.close(parent_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = stage(args.source_root, args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Offline staging stopped: {error}\nAny created staging files were retained; inspect them before deliberate removal.\n")
    print(json.dumps({key: result[key] for key in ("operation", "release_id", "archive_sha256", "archive_bytes", "frozen_package_verified", "publication_authorized", "network_operations")}, indent=2))


if __name__ == "__main__":
    main()
