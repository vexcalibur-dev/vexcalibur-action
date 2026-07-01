# Vexcalibur Action

[![CI](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml)

![Vexcalibur wordmark and sword logo](docs/assets/vexcalibur-banner.png)

GitHub Action wrapper for [Vexcalibur](https://github.com/vexcalibur-dev/vexcalibur).

The action is usable for development and compatibility testing today. Stable
production workflows should wait for a trusted action release commit and an
exact Vexcalibur package release.

Current workflows:

- Run Vexcalibur help and package URL queries in CI.
- Generate CycloneDX 1.6 VEX JSON from SBOMs with local findings or
  OSV-compatible providers.
- Validate the action/package boundary against a wheel built from
  `vexcalibur-dev/vexcalibur@main`.

## Development Quick Start

This is the runnable pre-release path for development smoke tests. CI validates
the same action/package compatibility path by building a Vexcalibur wheel from
`vexcalibur-dev/vexcalibur@main`; the examples below install that same
development branch directly. If you are testing an unmerged action PR, replace
`@main` with the PR branch or full action commit SHA you are validating.

```yaml
name: Vexcalibur

on:
  workflow_dispatch:

permissions: {}

jobs:
  vexcalibur:
    runs-on: ubuntu-latest
    steps:
      - uses: vexcalibur-dev/vexcalibur-action@main
        with:
          package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
          allow-development-package-spec: "true"
          args: --help
```

Save that as `.github/workflows/vexcalibur.yml` in a test repository. The
successful result is a passing workflow with Vexcalibur help output in the action
logs.

OSV-backed Vexcalibur commands can send package URLs, versions, or
SBOM-derived inventory to the public OSV service. Pass `--allow-public-osv`
only when that data sharing is acceptable for the workflow.

```yaml
name: Vexcalibur OSV Query

on:
  workflow_dispatch:

permissions: {}

jobs:
  vexcalibur:
    runs-on: ubuntu-latest
    steps:
      - uses: vexcalibur-dev/vexcalibur-action@main
        with:
          package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
          allow-development-package-spec: "true"
          args: |
            query-osv
            --allow-public-osv
            --
            pkg:pypi/django@1.2
            pkg:npm/minimist@0.0.8
```

## Release Usage

These examples describe the intended stable interface, but they are not runnable until
Vexcalibur publishes its first PyPI package and this action publishes a release.
Replace `ACTION_RELEASE_COMMIT_SHA` with the full action commit SHA for the release.
Release workflows should pin both the action and the package to trusted versions.
See the [compatibility reference](docs/reference/compatibility.md) for the
current action tag and package version policy.

```yaml
- uses: vexcalibur-dev/vexcalibur-action@ACTION_RELEASE_COMMIT_SHA
  with:
    package-spec: vexcalibur==0.1.0
    args: --help
```

```yaml
- uses: vexcalibur-dev/vexcalibur-action@ACTION_RELEASE_COMMIT_SHA
  with:
    package-spec: vexcalibur==0.1.0
    args: |
      query-osv
      --allow-public-osv
      --
      pkg:pypi/django@1.2
      pkg:npm/minimist@0.0.8
```

## Inputs

See the [action reference](docs/reference/action.md) for inputs, defaults,
argument handling, output behavior, exit behavior, and verification commands.

## SBOM-To-VEX Workflows

Use [Generate VEX from an SBOM](docs/how-to/generate-vex-from-sbom.md) for a
runnable CI workflow that checks out repository fixtures, runs
`vexcalibur generate`, writes a CycloneDX VEX JSON artifact, and uploads it with
`actions/upload-artifact`.

## Runtime Behavior

By default, the action requires an exact `vexcalibur==...` package spec and runs
the binary installed into its private virtual environment. Non-release package
specs require `allow-development-package-spec: "true"`.

The action does not honor caller-provided executable paths. Tests that need a
fake Vexcalibur command should provide a local package spec and let the action
install it through the same managed virtual environment used by normal
workflows. See [action reference](docs/reference/action.md) for the full runtime
contract.

## Development

Run local checks:

```bash
python -m pip install -r requirements-dev.txt
bash -n scripts/run-vexcalibur.sh
shellcheck scripts/run-vexcalibur.sh
ASDF_ACTIONLINT_VERSION=1.7.12 actionlint .github/workflows/*.yml
python -m unittest discover -s tests
```

`requirements-dev.txt` installs ShellCheck. Install actionlint through your local
toolchain before running the full local gate. Hosted CI installs actionlint
before running it.

## Project Links

- [Action reference](docs/reference/action.md)
- [Generate VEX from an SBOM](docs/how-to/generate-vex-from-sbom.md)
- [Compatibility reference](docs/reference/compatibility.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)
