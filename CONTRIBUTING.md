# Contributing to Vexcalibur Action

This repository contains a composite GitHub Action, two Bash scripts, and their Python test harness. The wrapper should stay thin: Vexcalibur commands and output formats belong in the [Vexcalibur repository](https://github.com/vexcalibur-dev/vexcalibur), while this repository owns installation, argument forwarding, and the GitHub Actions boundary.

## Set up the repository

You need Git, Bash, Python 3.14, and [actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12). If actionlint isn't already installed, you can install the pinned version with Go:

```bash
go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12
export PATH="$(go env GOPATH)/bin:$PATH"
```

Clone the repository, enter its root directory, and create a disposable virtual environment:

```bash
git clone https://github.com/vexcalibur-dev/vexcalibur-action.git
cd vexcalibur-action
python -m venv /tmp/vexcalibur-action-venv
source /tmp/vexcalibur-action-venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The development requirements install ShellCheck, PyYAML, and the secret scanner. A successful install ends without a pip error.

## Run the local checks

Run the same checks from the repository root:

```bash
bash -n scripts/*.sh
shellcheck scripts/*.sh
actionlint
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --
python -m unittest discover -s tests
```

Every command should exit with status `0`. The test command ends with `OK`.

The test suites divide responsibility this way:

- `tests/test_run_vexcalibur.py` covers action inputs, path handling, environment isolation, package installation, and argument forwarding.
- `tests/test_next_release_tag.py` covers automatic and manual release versions.
- `tests/test_fake_osv_server.py` covers the local Open Source Vulnerabilities (OSV) test server.

Hosted continuous integration (CI) also builds a wheel from `vexcalibur-dev/vexcalibur@main`. It exercises the action on Python 3.10 and 3.14 with `--help` and the local fake OSV server. A separate job compares generated Vulnerability Exploitability eXchange (VEX) output with the package repository's golden fixture. None of these checks needs public OSV access.

## Make a focused change

Keep the public contract in `action.yml` small. A new Vexcalibur command-line interface (CLI) command normally needs no action input because `args` already passes commands through.

When you change behavior:

- Update `tests/test_run_vexcalibur.py` for installation, input, environment, or argument changes.
- Update `tests/test_next_release_tag.py` for release classification or version changes.
- Update `docs/reference/action.md` when an input, default, path rule, output, or error changes.
- Update `docs/reference/compatibility.md` and `docs/how-to/release-action.md` when package support or release policy changes.
- Explain any new network access, GitHub permission, credential, or package-installation risk in the pull request.

Use fake package data and reserved domains such as `example.com` in tests and docs. Report a vulnerability through the [private security process](SECURITY.md), not in a pull request or public issue.

## Name the pull request

Release automation reads Conventional Commit-style messages after the latest action tag. In a squash-merge workflow, the pull request title becomes that message.

Use `feat:` for a new user-facing capability, `fix:` for a correction, and `docs:`, `test:`, or `ci:` when no action release is needed. Breaking changes use `type!:` or a `BREAKING CHANGE:` footer. The [release runbook](docs/how-to/release-action.md) lists every recognized release type.

## Open the pull request

Include:

- What changed and which user or maintainer task it affects.
- Tests for the changed contract.
- The exact verification commands you ran and their result.
- Documentation changes for any reader-visible behavior.
- Network, permission, secret, and supply-chain effects, or a statement that none changed.
- The compatibility-table update when the pull request prepares an action release.

CI must pass before merge. If CI finds a secret-like value, remove or rotate a real secret before updating `.secrets.baseline`; use a baseline entry only for reviewed false positives.
