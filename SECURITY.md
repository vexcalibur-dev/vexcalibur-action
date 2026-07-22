# Security policy

## Report a vulnerability

Report Vexcalibur Action vulnerabilities through [GitHub private vulnerability reporting](https://github.com/vexcalibur-dev/vexcalibur-action/security/advisories/new).

Don't put vulnerability details in a public issue, discussion, pull request, workflow log, or screenshot. That includes exploit steps, tokens, private package data, affected package names, and other evidence that could expose a user or repository.

If GitHub won't let you open a private report, submit the [Private disclosure channel request](https://github.com/vexcalibur-dev/vexcalibur-action/issues/new?template=private_disclosure_request.yml). Ask for a private channel and include no security details in that public request.

Send Python package or command-line interface (CLI) vulnerabilities to the [Vexcalibur private reporting page](https://github.com/vexcalibur-dev/vexcalibur/security/advisories/new). Use this repository when the problem lies in the Action wrapper: package installation, argument handling, runner isolation, workflow permissions, or release automation.

In the private report, include the affected action ref or commit, the Vexcalibur package spec, the impact, and enough redacted steps to reproduce the problem. Remove credentials and private inventory first.

Maintainers aim to acknowledge a private report within three business days and send a status update at least every seven calendar days while it remains active. The organization-wide process is documented in the [shared Vexcalibur security policy](https://github.com/vexcalibur-dev/.github/security/policy).

## Supported versions

The following lines currently receive security fixes:

| Release channel | Supported | What to do |
| --- | --- | --- |
| `main` | Yes | Use for development and validation. Security fixes land here first. |
| Highest strict semantic release tag | Yes | Pin its exact commit. Read the current-format declaration when present, or use the documented legacy fallback. |
| Earlier release tags | No | Upgrade to the highest supported action release. |

Releases created by the current workflow support only the Vexcalibur package
and Python versions in the `action-compatibility.json` file at the tag's commit.
These are current-format releases. Tags published before this workflow are
legacy releases: they do not contain that declaration or canonical recovery
metadata. The [compatibility reference](docs/reference/compatibility.md) checks
for the declaration and falls back to the historical compatibility table.

A fix that preserves the input contract receives a patch release. An
incompatible fix receives a major release, and its breaking commit appears in
the deterministic notes.

Release tags are never moved, deleted, or reused. Repository rules enforce that
policy without a bypass, and the publisher checks those rules before creating a
tag. The protected annotated Git tag is the authority for the version, target,
compatibility digest, and release-note digest. Mutable aliases are branches.
Consumers should pin the dereferenced release commit SHA.

GitHub's immutable-release setting protects the associated tag and assets, but
GitHub still permits title and body edits and release deletion. The workflow
verifies the GitHub Release projection when it publishes or recovers a release;
that check is point-in-time. A later verification can detect a body change from
the note digest stored in the tag.

The publisher advances the mutable `release-coordination` branch in the same
atomic push that creates a tag. An exact branch lease serializes independent
publishers before either can create permanent tag state. The branch is not a
release identity and consumers must not pin it.

Repository administrators and organization owners are part of the release
governance trust boundary because they can change repository settings. The
publisher checks the ruleset scope and rule types immediately before
publication. GitHub omits bypass principals from the read-only App response, so
an organization owner records the complete principals in
`RELEASE_POLICY_ATTESTATION`. Publication fails unless the live ruleset IDs and
revision timestamps match that evidence. Owner-enforced immutable Releases
protect a tag after publication. This repository currently uses
repository-owned rulesets, which don't provide independent provenance against
a compromised administrator before a GitHub Release exists.

The automation App and its private key are the protocol-enforcing trust
boundary for tag creation. GitHub rules can restrict creation to that App and
forbid every later tag mutation, but they can't require an annotated object,
canonical metadata, semantic ordering, or the coordination branch. The
publisher enforces those checks. A compromised App could still create malformed
permanent tag state, so revoke its installation and rotate its key during a
release-credential incident.
