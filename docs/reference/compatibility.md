# Action and package compatibility

Vexcalibur Action installs a Vexcalibur Python package at run time. The action ref controls the wrapper. `package-spec` controls the command-line interface (CLI) and Vulnerability Exploitability eXchange (VEX) implementation. Review and pin them separately.

## Tested pairs

This table records combinations verified by this repository. The current pair is
tested on every continuous integration (CI) run; older rows preserve the coverage
that existed when those versions were current.

| Action ref | Vexcalibur package | Python versions | Status |
| --- | --- | --- | --- |
| `main` | Wheel built from `vexcalibur-dev/vexcalibur@main`; `vexcalibur==0.3.1` in separate release-package jobs | `3.10`, `3.14` | Mutable development branch |
| `v0.2.1` | `vexcalibur==0.3.1` | `3.10`, `3.14` | Current supported pair; actively tested with CycloneDX 1.6, OpenVEX 0.2.0, and CSAF 2.0 VEX output |
| `v0.2.1` | `vexcalibur==0.3.0` | `3.10`, `3.14` | Original release-time pair; previously tested with CycloneDX 1.6, OpenVEX 0.2.0, and CSAF 2.0 VEX output |
| `v0.2.0` | `vexcalibur==0.3.0` | `3.10`, `3.14` | Previously tested pair; includes CycloneDX 1.6, OpenVEX 0.2.0, and CSAF 2.0 VEX output |
| `v0.2.0` | `vexcalibur==0.2.0` | `3.10`, `3.14` | Previously tested pair; includes OpenVEX 0.2.0 output |
| `v0.2.0` | `vexcalibur==0.1.1` | `3.10`, `3.14` | Previously tested pair; CycloneDX output only |
| `v0.1.0` | `vexcalibur==0.1.1` | `3.10`, `3.14` | Historical release; no longer receives security fixes |

The Python column names versions that this repository's continuous integration (CI) exercises. It doesn't claim that every version between them is tested here.

The OpenVEX and CSAF artifact lanes use the default Python 3.14. Help and query lanes exercise Python 3.10 and 3.14.

The `v0.2.1` action was published while `vexcalibur==0.3.0` was current. The
action installs the caller-selected package at run time, and its runtime contract
is unchanged from `v0.2.0`, so the same action release can support a newer tested
package without moving its tag. Current CI verifies `v0.2.1` with
`vexcalibur==0.3.1` and separately verifies the mutable action against a wheel
built from Vexcalibur's `main` branch.

The `v0.2.1` release workflow generates, scans, and publishes release notes on
three separate runners. The scanner installs only a wheel-only, hash-locked
dependency closure and receives no publication credential. The publisher verifies
the scanned artifact's SHA-256 digest before it creates its short-lived
publication credential.

All listed checks run on GitHub-hosted `ubuntu-latest`. Other runner operating systems aren't verified. The action assumes `/bin/bash`, POSIX paths, and a writable, executable `RUNNER_TEMP`; see [Runner requirements](action.md#runner-requirements).

Use a release pair for reviewed workflows:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@v0.2.1
  with:
    package-spec: vexcalibur==0.3.1
    args: --help
```

Don't use `main` as a stable release. It can change whenever either repository merges a change.

## Pinning levels

Choose pins that match the workflow's supply-chain policy:

| Boundary | Readable pin | Immutable or repeatable pin |
| --- | --- | --- |
| Action wrapper | `vexcalibur-dev/vexcalibur-action@v0.2.1` | `vexcalibur-dev/vexcalibur-action@f05361ec7308e0ff2cf8b961b7ccca2c001b910b` (`v0.2.1`) |
| Vexcalibur package | `vexcalibur==0.3.1` | Same exact spec; verify the package index and hashes according to local policy |
| Transitive Python packages | Resolver-selected versions | Checked-in, complete pip constraints passed through `constraints-file` |

This action's release policy forbids moving an existing version tag. A commit SHA still gives the strongest GitHub Actions pin because the workflow itself names the immutable object.

An exact Vexcalibur version doesn't freeze its dependencies. Without `constraints-file`, pip can select newer compatible transitive releases on a later run. See the [`constraints-file` reference](action.md#constraints-file) for the action contract.

## Development package specs

The action accepts only an exact `vexcalibur==...` requirement by default. Git URLs, local wheel paths, source directories, and other specs need an explicit development opt-in:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@main
  with:
    package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
    allow-development-package-spec: "true"
    args: --help
```

Use this form for compatibility testing, not release pinning. Prefer a full Vexcalibur commit SHA over `@main` when a development test must be reproducible.

## What continuous integration verifies

The required `CI result` job aggregates these checks:

1. **Repository quality:** Bash syntax, ShellCheck, actionlint, YAML and JSON parsing, secret scanning, and unit tests.
2. **Development wheel:** a wheel built from `vexcalibur-dev/vexcalibur@main`.
3. **Action boundary:** `--help` and a local fake Open Source Vulnerabilities (OSV) query with that wheel on Python 3.10 and 3.14.
4. **CycloneDX artifact:** an XML CycloneDX software bill of materials (SBOM) plus local findings on the default Python 3.14. CI compares the result with the package repository's golden CycloneDX 1.6 fixture.
5. **Development OpenVEX artifact:** the same local inputs with the development wheel. CI checks the OpenVEX context, author, statuses, products, and status-specific evidence before uploading `openvex-wheel-output`.
6. **Development CSAF artifact:** the development wheel produces CSAF 2.0 from the same controlled inputs. CI compares the document with the package repository's golden fixture except for the independently checked development-version field. It checks publisher and tracking metadata, all product statuses, versioned product identities, remediations, and impact threats before uploading `csaf-wheel-output`.
7. **Released package:** `--help` and the local fake OSV query with `vexcalibur==0.3.1` on Python 3.10 and 3.14.
8. **Released OpenVEX artifact:** `vexcalibur==0.3.1` produces OpenVEX from the controlled local fixtures. CI checks its metadata, statuses, products, and evidence fields. It also confirms that the action inputs, execution steps, and runtime script still match `v0.2.1`, then uploads `openvex-released-package-output`.
9. **Released CSAF artifact:** `vexcalibur==0.3.1` produces CSAF from the controlled local fixtures. CI checks the generator version against the installed release plus the publisher, tracking, product, status, remediation, and impact contracts before uploading `csaf-released-package-output`.
10. **Dependency and repository checks:** dependency review on pull requests and OpenSSF Scorecard without PR comments or SARIF upload in the required CI workflow.

The fake OSV jobs use a loopback server. The artifact jobs use `--offline` with local findings. None of these jobs sends package URLs to the public OSV API.

CI reads the expected released package from `VEXCALIBUR_RELEASE_PACKAGE_VERSION` in `.github/workflows/ci.yml`. It also checks PyPI's latest `vexcalibur` release. A mismatch fails the release-package lane instead of silently testing an unexpected package.

The action remains a generic CLI runner. CI adds end-to-end cases for important user workflows; it doesn't duplicate every Vexcalibur CLI test.

## Release maintenance contract

Before publishing an action version:

1. Set `VEXCALIBUR_RELEASE_PACKAGE_VERSION` to the package version the action release will support.
2. Add the prospective action tag and exact `vexcalibur==...` spec to this table.
3. Run the full CI workflow against that commit.

The release workflow refuses to publish when the computed action tag and expected package spec don't appear together in this file. It waits for CI on the exact release commit, creates an annotated `vX.Y.Z` tag, and publishes a GitHub Release. It doesn't create moving tags such as `v1`.

Maintainers should follow [Release the action](../how-to/release-action.md) for version calculation, permissions, verification, and recovery.
