# Hugging Face account and mirror setup

The account connection and research publication are separate operations. Connecting
an account does not pass the coverage, source-cutoff, audit, archive or DOI gates.
The current research policy remains `prepare_only`.

## Connect the account

1. Sign in to [Hugging Face](https://huggingface.co/login?next=%2Fsettings%2Ftokens)
   in the Chrome profile used for the setup. Complete password, passkey and MFA
   entry yourself. Do not put credentials into chat.
2. Verify the displayed username. Use the personal namespace, or an organization
   where the account's repository-creation permission is confirmed. A matching
   website name or GitHub handle is not evidence of a Hugging Face namespace.
3. At [New dataset](https://huggingface.co/new-dataset), choose that confirmed
   namespace and `sciencetostartup-research`. Choose **Private** during setup.
   Check whether the repository already exists before creating it. Keep this
   repository empty while the research publication is held.
4. At [Access Tokens](https://huggingface.co/settings/tokens), select **Fine-grained**
   and name it `sciencetostartup-local-publisher`. Select only this dataset in the
   repository permissions. Grant content read/write when available; avoid any
   user-wide, organization-wide, inference, billing, discussion or token-management
   access. Do not choose a broad account `write` token.
   The observed Hub UI labels selected-repository write as “Write contents/settings
   of selected repos” and automatically enables content and access-request reads
   for that same selected repository. The corresponding scope values are
   `repo.write`, `repo.content.read` and `repo.access.read`; this is broader in
   operation than content-only write, but remains limited to the selected dataset.
5. Enter the one-time token directly into the local setup helper's hidden terminal
   prompt, alongside the confirmed `namespace/sciencetostartup-research` value.
   The common helper is `tools/publishing/configure_accounts.py` when integrated.
   It stores credentials outside the checkout at
   `~/.config/sciencetostartup/publishing-credentials.json` with mode `0600`.
   Avoid screenshots or page snapshots while a plaintext token is visible.
6. Run the helper's read-only connection check. Authentication success and dataset
   read access do not establish that a write succeeded. Keep namespace, scope,
   visibility and repository revision evidence separate from publication status.

Hugging Face recommends fine-grained production tokens and supports resource-level
scopes. A token can still depend on organization approval or membership.
[Token documentation](https://huggingface.co/docs/hub/security-tokens) and the
[current API specification](https://huggingface.co/.well-known/openapi.json) are
the authority for current permission fields. `scope_evidence()` interprets the
response conservatively and returns only non-secret status. It accepts a single
matching dataset scope and reports a remote write as unverified. A schema change,
extra resource, extra global access or broad namespace scope cannot silently pass.
The validated response requires coherent authenticated-user and dataset object
identities. Unknown fields in the authorization containers, missing identifiers,
contradictory owner/dataset metadata and duplicate response JSON keys are holds.
The Hub's empty own-user descriptor is metadata only when its exact user ID and
name match the authenticated user and its permission list is empty.

## Prepare inspectable files locally

From the source checkout, run:

```sh
python3 tools/publishing/huggingface_setup.py --output /absolute/private/path/hf-staging
```

The destination must be new and outside the scientific checkout. The tool reads
the source-selected frozen package using the existing scientific verifier; it
does not rebuild, rewrite or recompress any scientific bytes. It makes no network
calls and does not read credentials. Parent aliases are canonically resolved
before no-follow directory descriptors anchor the destination. The final output
is created exclusively after package verification; a path that appears or changes
during staging is refused. Existing directories are never replaced, including
empty ones. Failure cleanup is confined to the newly created anchored objects.

`mirror-staging/` contains exactly the four payload names used by the existing
`HuggingFaceMirror` adapter: `README.md`, `research-archive.zip`,
`clean-dataset.json` and `publication-manifest.json`. The card is the exact
manifest-bound `huggingface-README.md`, with its existing prelaunch statement.
`citation-projection/` contains the frozen CFF, BibTeX, RIS, CSL JSON and metadata
files. These retain the preparation-snapshot status and omit a registered DOI.
`staging-status.json` records the source package digests, gate result and staged
file digests. An offline staging receipt is not a remote mirror receipt.

The Hub renders a dataset repository's `README.md` as its card and accepts YAML
metadata there. The existing card's license and language are preserved without
adding unsupported research claims.
[Dataset card documentation](https://huggingface.co/docs/hub/datasets-cards).

## Finish after the publication gates pass

The optional `huggingface_hub` SDK is needed by the existing publisher, not this
setup tool. Install it in an isolated environment only when the release operator
is ready to execute the publisher. The current adapter requires an existing
**public** dataset and a verified production archival receipt. Review and make
the empty setup repository public only at formal release, after the actual
coverage and audit work, DOI/archive publication, and exact archive verification.

Invoke the existing adapter with the explicit token and repository; keep its
journal outside the checkout. The adapter pins the parent commit, reconciles the
publication manifest, then downloads the archive and dataset at the immutable
resulting commit to compare exact bytes. It records mirror success independently
of the website. Use the release procedure in [publication.md](publication.md).
Do not upload this held prelaunch staging directory manually.
