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

| Version line | Supported | What to do |
| --- | --- | --- |
| `main` | Yes | Use for development and validation. Security fixes land here first. |
| `v0.2.x` | Yes | Upgrade to the latest `v0.2.x` release and its documented package pair. |
| `v0.1.x` | No | Upgrade to the latest supported action release. |
| Older pre-1.0 lines | No | Upgrade to the latest supported action release. |

Pre-1.0 action releases support only the Vexcalibur package versions in the [compatibility table](docs/reference/compatibility.md). When a fix preserves the `v0.2.x` input contract, maintainers publish a new patch release. An incompatible fix gets a new release line and an explicit upgrade path in the release notes and compatibility table.

Existing release tags aren't moved. Consumers that need an immutable action reference should pin the full release commit SHA.
