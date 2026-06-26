# Vexcalibur Action

[![CI](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml)
[![Dependency Review](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/dependency-review.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/dependency-review.yml)

![](docs/assets/vexcalibur-banner.png)

GitHub Action wrapper for [Vexcalibur](https://github.com/vexcalibur-dev/vexcalibur).

This repository is pre-alpha. Use the development workflow below only for testing the
action before the first Vexcalibur package release. Production workflows should wait
for a trusted action release commit and an exact PyPI package release.

## Development Quick Start

This is the runnable pre-release path validated by this repository's CI after these
docs are merged to `main`. If you are testing an unmerged PR, replace `@main` with
the PR branch or full action commit SHA you are validating. This path uses the mutable
action branch and a pinned Vexcalibur Git commit, so it is appropriate for development
smoke tests only.

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
          package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@cc9506fc451bed1a5658a53cee4eaf7174505514
          allow-development-package-spec: "true"
          command: help
```

Save that as `.github/workflows/vexcalibur.yml` in a test repository. The
successful result is a passing workflow with Vexcalibur help output in the action
logs.

Querying public OSV sends package URLs to the public OSV service. Set
`allow-public-osv` only when that data sharing is acceptable for the workflow. This
action requires `allow-public-osv: "true"` for `query-osv` until a private source
input exists.

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
          package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@cc9506fc451bed1a5658a53cee4eaf7174505514
          allow-development-package-spec: "true"
          command: query-osv
          allow-public-osv: "true"
          purls: |
            pkg:pypi/django@1.2
            pkg:npm/minimist@0.0.8
```

## Release Usage

These examples describe the intended stable interface, but they are not runnable until
Vexcalibur publishes its first PyPI package and this action publishes a release.
Replace `ACTION_RELEASE_COMMIT_SHA` with the full action commit SHA for the release.
Release workflows should pin both the action and the package to trusted versions.

```yaml
- uses: vexcalibur-dev/vexcalibur-action@ACTION_RELEASE_COMMIT_SHA
  with:
    package-spec: vexcalibur==0.1.0
    command: help
```

```yaml
- uses: vexcalibur-dev/vexcalibur-action@ACTION_RELEASE_COMMIT_SHA
  with:
    package-spec: vexcalibur==0.1.0
    command: query-osv
    allow-public-osv: "true"
    purls: |
      pkg:pypi/django@1.2
      pkg:npm/minimist@0.0.8
```

## Inputs

See the [action reference](docs/reference/action.md) for inputs, defaults,
supported commands, output behavior, exit behavior, and verification commands.

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
python -m unittest discover -s tests
```

## Project Links

- [Action reference](docs/reference/action.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)
