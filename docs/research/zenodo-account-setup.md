# Zenodo account connection

The account checker is ready. Real production and sandbox tokens must be entered
by the account owner in a local terminal. Connection only establishes authenticated
read access. It does not enable publication or establish a DOI, research readiness,
upload rights, publication rights, or the identity of a published archive.

## Sign in and create separate tokens

Open the appropriate links in your ordinary Chrome profile. Zenodo production and
sandbox are separate accounts and require separate tokens; logging into one does
not connect the other. Sandbox data can be reset, and its `10.5072` DOIs are test
identifiers. Production uses `10.5281`. These requirements and scopes are in the
[official Zenodo REST documentation](https://developers.zenodo.org/#authentication)
and [testing documentation](https://developers.zenodo.org/#testing).

| Environment | Account settings | New token | Suggested label |
| --- | --- | --- | --- |
| Production | [Applications](https://zenodo.org/account/settings/applications/) | [New production token](https://zenodo.org/account/settings/applications/tokens/new/) | ScienceToStartup archive publisher production |
| Sandbox | [Applications](https://sandbox.zenodo.org/account/settings/applications/) | [New sandbox token](https://sandbox.zenodo.org/account/settings/applications/tokens/new/) | ScienceToStartup archive publisher sandbox |

For each token, select **`deposit:write`** and **`deposit:actions`**. The former
allows deposit edits; the latter allows publishing and edit/discard actions. The
local checker performs only GET requests. Its successful read check cannot prove
either scope, so keep the two selected scope names as nonsecret configuration
evidence. The owner should create and copy the token themselves: the one-time
plaintext token must not appear in a chat, screenshot, screen recording, shell
argument, URL, repository file, or publication artifact.

If creating an account, use your actual identity and chosen existing sign-in
provider. The current project publisher metadata names **Musa Ozdem** and website
**https://musaeminozdem.com**; verify the desired full name yourself. Username,
institutional email, affiliation, ORCID and account terms require the account
owner's actual choices. The repository does not establish an institutional
affiliation or an ORCID.

## Enter tokens locally

From the repository checkout containing this tool:

```sh
python3 tools/publishing/configure_accounts.py --service zenodo
```

For the prepared private copy from the 2026-11-10 setup session:

```sh
python3 '/Users/musa.ozdem/Documents/ChatGPT/scienctostartup (new data lab)/site/output/research-next/publishing-account-setup/configure_accounts.py' --service zenodo
```

Paste each token into its hidden prompt, then press Return. Blank inputs preserve
stored values. No credential file or directory is created when every input is
blank and no configuration exists. No secret flags or piped input are supported.

The shared configuration is outside the source checkout:

`~/.config/sciencetostartup/publishing-credentials.json`

It uses `schema_version: 1` and the optional keys `zenodo_production_token`,
`zenodo_sandbox_token`, `hf_token`, and `hf_repository`. The directory is mode
`0700`; credentials, temporary files and the concurrency lock are mode `0600`.
Updates lock and re-read the existing file, preserve the other service's keys,
write and fsync a temporary file, then atomically replace the original. Symlinks,
hardlinks, unexpected JSON fields, duplicate JSON keys, invalid file ownership
and broad file/directory modes fail closed. This is private local storage, not
encryption at rest; normal OS account and disk protections still apply.

These commands print only nonsecret status:

```sh
python3 tools/publishing/configure_accounts.py --service zenodo --status
python3 tools/publishing/configure_accounts.py --service zenodo --check-only
```

`--status` has no network access. `--check-only` performs at most one GET against
each configured Zenodo environment's `/api/deposit/depositions?size=1`, sends the
token only in the HTTPS `Authorization: Bearer` header, and discards deposit
details. Every redirect is blocked and ambient proxy variables are ignored.
Certificate verification remains enabled. No credentials means no request.

Exit status `0` means the selected service checks passed (or presence-only status
completed); `2` means at least one account/repository is unconfigured or its read
check failed; `1` means local setup was refused; `130` means input was cancelled.
An HTTP `401` means authentication failed; `403` means forbidden; `429` means rate
limited. A failed read does not authorize a token replacement or a write probe.

If file modes were changed, inspect locally and restore only these intended paths:

```sh
chmod 700 ~/.config/sciencetostartup
chmod 600 ~/.config/sciencetostartup/publishing-credentials.json
chmod 600 ~/.config/sciencetostartup/publishing-credentials.json.lock
```

Do not run `cat`, `env`, `set -x`, or a shell echo of the credentials. To revoke
a token, use the relevant environment's Applications page. To replace it, rerun
the hidden prompt. The helper never revokes tokens remotely.

## Existing adapter mapping

The adapter remains explicit and does not discover credentials automatically:

| Local key | Adapter arguments | Environment |
| --- | --- | --- |
| `zenodo_production_token` | `Zenodo(plan_or_release, token=credentials["zenodo_production_token"], sandbox=False)` | `https://zenodo.org` |
| `zenodo_sandbox_token` | `Zenodo(plan_or_release, token=credentials["zenodo_sandbox_token"], sandbox=True)` | `https://sandbox.zenodo.org` |

Load the configuration with this tool's `load_credentials()` in the deliberate
operator process and pass only the selected token. Keep reservation and release
journals outside the checkout, under private storage, and separate across
environments. Never reuse a production journal for sandbox or the reverse.

The actual transaction stays defined by
[publication.md](publication.md#explicit-external-adapters): pass the authoritative
research gate and deliberately enable publication policy, then reserve a version
DOI through `PublicationPlan`, prepare/review the exact PDF, freeze and verify
the package, construct `Release`, upload exact bytes, publish and independently
reconcile the production receipt. A read check and a token with action scopes do
not bypass those requirements. Current `prepare_only` policy remains unchanged.
Account setup does not call `draft()`, reserve a DOI, upload files, publish,
create journals, or modify scientific inputs, schemas, the frozen archive or the
website.

## Verification and outstanding proof

Run the synthetic offline tests:

```sh
python3 -m unittest discover -s tests -p test_publishing_account_setup.py -v
```

The tests exercise private modes, symlink/hardlink refusal, a concurrent lock,
preservation after a failed atomic replacement, shared-field merging, hidden
entry refusal, control-character rejection, GET-only bearer requests, blocked
redirects/proxies and sanitized response failures. Fixture tokens and responses
are explicitly synthetic; passing tests is not account or publication evidence.

Real setup is complete only when both environment read checks return
`authenticated_read` and the owner has verified the exact two selected scope
names for each token. Write/action behavior remains untested until the existing
publication gates permit an actual transaction. No production archive receipt,
DOI or mirror state should be claimed from account setup.
