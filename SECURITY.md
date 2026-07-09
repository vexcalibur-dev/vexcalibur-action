# Security Policy

## Reporting Vulnerabilities

Vexcalibur Action follows the shared `vexcalibur-dev` security policy:

<https://github.com/vexcalibur-dev/.github/security/policy>

Use GitHub private vulnerability reporting for Vexcalibur Action vulnerabilities:

<https://github.com/vexcalibur-dev/vexcalibur-action/security/advisories/new>

Do not open public issues with vulnerabilities, exploit details, secrets,
tokens, private package data, affected package names, logs, stack traces,
screenshots, reproduction steps, or other sensitive evidence. If GitHub private
vulnerability reporting is unavailable, use the private disclosure channel
request issue form in this repository and include no sensitive details.

## Supported Versions

| Version line | Supported | Notes |
| --- | --- | --- |
| `main` | Yes | Default development branch. Security fixes land here first. |
| `v0.2.x` | Yes | Latest pre-1.0 action release line. |
| `v0.1.x` | No | Upgrade to the latest documented release pair. |
| Older pre-1.0 lines | No | Upgrade to the latest documented release pair. |

Pre-1.0 action releases support only the Vexcalibur package versions listed in
the [compatibility table](docs/reference/compatibility.md). Security fixes that
affect released action behavior are released as a new `v0.2.x` tag when the
fix can be carried without breaking the documented action inputs. If a fix
requires an incompatible action contract, the release notes and compatibility
table document the required upgrade path.
