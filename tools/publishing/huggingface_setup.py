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
import shutil
import sys
import tempfile

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
    # Hub includes a zero-permission owner descriptor beside the dataset grant.
    # It is metadata only when both identifiers bind the authenticated owner.
    def empty_owner_descriptor(entry):
        if not isinstance(entry, dict) or set(entry) != {"entity", "permissions"}:
            return False
        entity = entry["entity"]
        return (owner_id_known and entry["permissions"] == [] and isinstance(entity, dict)
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
    if (token.get("role") == "fineGrained" and dataset_matches
            and isinstance(scoped, list) and 1 <= len(scoped) <= 2 and len(resources) == 1
            and not (set(fine) - {"scoped", "global", "canReadGatedRepos"})
            and fine.get("global", []) == [] and fine.get("canReadGatedRepos", False) is False):
        entry = resources[0]
        entry = entry if isinstance(entry, dict) else {}
        entity = entry.get("entity", {})
        entity = entity if isinstance(entity, dict) else {}
        object_id = dataset.get("_id")
        id_matches = (isinstance(object_id, str) and bool(OBJECT_ID.fullmatch(object_id))
                      and entity.get("_id") == object_id)
        name_matches = entity.get("name") == repository and object_id is None
        permissions = entry.get("permissions", [])
        author_matches = ("authorId" not in entity or
                          (owner_id_known and entity["authorId"] == owner_id))
        name_consistent = "name" not in entity or entity["name"] == repository
        if (not (set(entry) - {"entity", "permissions"})
                and not (set(entity) - {"type", "_id", "name", "authorId"})
                and author_matches and name_consistent
                and entity.get("type") == "dataset" and (id_matches or name_matches)
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
        "repository_identity_matches": dataset_matches,
        "namespace_relation": "personal-owner" if owner else "organization-member" if membership else "unconfirmed",
        "namespace_creation_permission_verified": owner,
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


def stage(source_root, output):
    """Verify the current source-selected frozen package and stage exact bytes."""
    source_root, output = Path(source_root).resolve(), Path(output).absolute()
    if output.is_symlink() or output.exists():
        raise ValueError("Staging destination must be new; existing files are never replaced")
    if output.resolve().is_relative_to(source_root):
        raise ValueError("Keep local staging outside the scientific source checkout")
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
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".hf-staging-", dir=output.parent))
    try:
        os.chmod(temporary, 0o700)
        inventory = {}
        for folder, mapping in (("mirror-staging", MIRROR_FILES),
                                ("citation-projection", {name: name for name in CITATION_FILES})):
            directory = temporary / folder
            directory.mkdir(mode=0o700)
            for destination, source in mapping.items():
                blob = frozen[source]
                path = directory / destination
                path.write_bytes(blob)
                path.chmod(0o600)
                inventory[f"{folder}/{destination}"] = {"source_member": source, **_descriptor(blob)}
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
        (temporary / "staging-status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
        (temporary / "staging-status.json").chmod(0o600)
        temporary.rename(output)
        return status
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = stage(args.source_root, args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Offline staging stopped: {error}\n")
    print(json.dumps({key: result[key] for key in ("operation", "release_id", "archive_sha256", "archive_bytes", "frozen_package_verified", "publication_authorized", "network_operations")}, indent=2))


if __name__ == "__main__":
    main()
