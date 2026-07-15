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
python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-dev.txt
```

The development lock installs ShellCheck, PyYAML, the secret scanner, and their complete transitive dependency closure. `--only-binary` rejects source distributions, and `--require-hashes` rejects any distribution that isn't approved in the lock. A successful install ends without a pip error.

## Refresh dependency locks

`requirements-release.in` and `requirements-dev.in` are the maintainer-edited direct dependencies. Their corresponding `.txt` files are generated security boundaries. The smaller release lock is installed only on the release-note scanner runner; the development lock adds repository validation tools.

You need [uv 0.11.28](https://github.com/astral-sh/uv/releases/tag/0.11.28) and network access to the Python Package Index. The refresh script refuses a different uv version. From the repository root, confirm the version and regenerate both locks:

```bash
uv --version
scripts/refresh-requirements.sh
```

The first command must report `uv 0.11.28`. Review the complete diff before accepting it:

- Every direct dependency change in an `.in` file is intentional.
- Every package in each `.txt` file has an exact version and at least one SHA-256 hash.
- Both generated files retain `--only-binary :all:`.
- `requirements-release.txt` contains only the release scanner and its transitive dependencies.
- `requirements-dev.txt` contains the same release closure plus the declared development tools.
- No editable, local-path, direct-URL, extra-index, or unhashed requirement appears.

Validate both locks in clean environments rather than reusing the environment that ran the compiler:

```bash
python -m venv /tmp/vexcalibur-action-release-lock
/tmp/vexcalibur-action-release-lock/bin/python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-release.txt
/tmp/vexcalibur-action-release-lock/bin/detect-secrets --version

python -m venv /tmp/vexcalibur-action-dev-lock
/tmp/vexcalibur-action-dev-lock/bin/python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-dev.txt
/tmp/vexcalibur-action-dev-lock/bin/shellcheck --version
/tmp/vexcalibur-action-dev-lock/bin/python -c 'import yaml'
```

Each install must finish without a hash, source-distribution, or resolver error. Remove the two `/tmp/vexcalibur-action-*-lock` environments after review.

## Run the local checks

Run the same checks from the repository root:

```bash
bash -n scripts/*.sh
shellcheck scripts/*.sh
actionlint
git ls-files --cached --others --exclude-standard -z \
  | xargs -0 detect-secrets-hook --baseline .secrets.baseline --
python -m unittest discover -s tests
```

Every command should exit with status `0`. The test command ends with `OK`.

The test suites divide responsibility this way:

- `tests/test_run_vexcalibur.py` covers action inputs, path handling, environment isolation, package installation, and argument forwarding.
- `tests/test_next_release_tag.py` covers automatic and manual release versions.
- `tests/test_fake_osv_server.py` covers the local Open Source Vulnerabilities (OSV) test server.
- `tests/test_release_security.py` protects the hash locks and release runner, token, scanner, and artifact-digest boundaries.

Hosted continuous integration (CI) also builds a wheel from `vexcalibur-dev/vexcalibur@main`. It exercises the action on Python 3.10 and 3.14 with `--help` and the local fake OSV server.

Development artifact jobs compare CycloneDX, OpenVEX, and CSAF output with package-owned golden fixtures. Separate OpenVEX and CSAF jobs exercise the pinned PyPI release. None of these checks sends inventory to public OSV.

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
