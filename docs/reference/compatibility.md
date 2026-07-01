# Action And Package Compatibility

The Vexcalibur Action installs a Vexcalibur Python package at runtime. Pin the
action and the package separately so workflow reviews can see both trust
boundaries.

## Current Compatibility Table

| Action ref | Vexcalibur package spec | Python versions verified by this repo | Status |
| --- | --- | --- | --- |
| `main` | Development specs only, including a wheel built from `vexcalibur-dev/vexcalibur@main` in CI | `3.10`, `3.14` | Mutable development branch, not a stable release |
| Stable release tags | None published yet | None | Stable action releases have not started |

Do not use `main` for production workflows. Stable workflows should pin a
trusted action release ref and an exact package release, for example
`package-spec: vexcalibur==0.1.0`.

## Release Policy

Before the first stable action release, non-release package specs require
`allow-development-package-spec: "true"`. That includes local wheel paths, Git
URLs, and source checkouts.

For pre-1.0 releases, each action tag supports only the exact Vexcalibur package
versions named in this compatibility table and the release notes. Broader
package ranges must be added explicitly after CI verifies them.

Every stable action release must update this page in the same pull request or
release-preparation pull request. If a release exists but is missing from the
table, treat the release process as incomplete.

The CI release-package lane is guarded by `VEXCALIBUR_RELEASE_PACKAGE_VERSION`.
While PyPI returns 404 for `vexcalibur`, the lane reports that no release exists
and exits successfully. After a PyPI package exists, CI fails until this
environment variable is updated to the expected official release version. This
prevents a third-party PyPI namespace claim from silently becoming trusted test
input.

## CI Compatibility Contract

This repository verifies the action/package boundary with these hosted checks:

- Runs `bash -n`, ShellCheck, `actionlint`, YAML/JSON parsing, and action unit
  tests before building or running package compatibility checks.
- Builds a Vexcalibur wheel from `vexcalibur-dev/vexcalibur@main`.
- Runs the local action with that wheel for `--help` on Python `3.10` and
  Python `3.14`.
- Runs `query-osv` against a local fake OSV-compatible server on Python `3.10`
  and Python `3.14`; this does not send package data to public OSV.
- Runs `generate` with an XML SBOM and local findings, writes a CycloneDX VEX
  JSON file, compares it to the golden fixture from the same Vexcalibur source
  checkout used to build the wheel, and uploads the generated file as a workflow
  artifact named `vexcalibur-sbom-to-vex-output`. The artifact currently contains
  `cyclonedx-vex.xml-input.json`.
- Checks PyPI for the latest expected `vexcalibur` package and runs `--help` and
  `query-osv` against it when an official package release exists. Before the
  first PyPI release, this job reports the missing release and exits
  successfully.
- Runs dependency review on pull requests and OpenSSF Scorecard as part of the
  same CI workflow without requiring pull request comments or SARIF upload side
  effects for the required CI gate.
- Aggregates the required quality, wheel, action E2E, SBOM-to-VEX, and release
  resolution jobs in a single `CI result` job. Dependency review may be skipped
  outside pull requests. Released-package E2E jobs may be skipped only while no
  official package release exists.

The action remains a thin CLI runner. Adding a Vexcalibur command should not
require changing the action runner, but important user workflows can add new E2E
scenarios to this contract.
