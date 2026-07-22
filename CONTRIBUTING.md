# Contributing to Vexcalibur Action

This repository contains a composite GitHub Action, its Bash wrapper, canonical
Python release tooling, and a Python test harness. The wrapper should stay thin:
Vexcalibur commands and output formats belong in the [Vexcalibur
repository](https://github.com/vexcalibur-dev/vexcalibur). This repository owns
installation, argument forwarding, and the GitHub Actions boundary.

## Set up the repository

You need Git, Bash, and a version manager that reads
[`.tool-versions`](.tool-versions), such as mise or asdf. The file pins Python,
uv, pre-commit, actionlint, and ShellCheck for this repository.

Clone the repository, enter its root directory, install the pinned tools, and
create a disposable virtual environment:

```bash
git clone https://github.com/vexcalibur-dev/vexcalibur-action.git
cd vexcalibur-action
mise trust
mise install
pre-commit install
python -m venv /tmp/vexcalibur-action-venv
source /tmp/vexcalibur-action-venv/bin/activate
python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-dev.txt
```

To use asdf instead, install the repository-pinned plugins, then install the
versions in `.tool-versions` before creating the virtual environment:

```bash
bash scripts/install-asdf-plugins.sh
asdf install
pre-commit install
```

The development lock installs Hypothesis, PyYAML, the secret scanner, and their
complete transitive dependency closure. `--only-binary` rejects source
distributions, and `--require-hashes` rejects any distribution that isn't
approved in the lock. A successful install ends without a pip error.

## Update development tools

Keep [`.tool-versions`](.tool-versions) and [`mise.toml`](mise.toml) on the
same exact versions. After changing a tool version, refresh the committed Mise
artifact metadata for the supported developer platforms:

```bash
mise trust
mise lock --platform linux-x64 --platform macos-x64 --platform macos-arm64
```

[`scripts/install-asdf-plugins.sh`](scripts/install-asdf-plugins.sh) pins the
asdf plugin commits separately. Update a plugin reference only after reviewing
the intended upstream revision; do not use `asdf plugin update --all`.

## Refresh dependency locks

`requirements-release.in`, `requirements-dev.in`, and
`requirements-fuzz.in` are the maintainer-edited direct dependencies. Their
corresponding `.txt` files are generated security boundaries. The smaller
release lock supplies PyYAML to the planner and detect-secrets to the scanner.
The development lock adds repository validation tools. The fuzz lock adds
Atheris and the dependency auditor for CPython 3.14 on Linux x86-64.

You need [uv 0.11.28](https://github.com/astral-sh/uv/releases/tag/0.11.28) and network access to the Python Package Index. The refresh script refuses a different uv version. From the repository root, confirm the version and regenerate all three locks:

```bash
uv --version
scripts/refresh-requirements.sh
```

The first command must report `uv 0.11.28`. Review the complete diff before accepting it:

- Every direct dependency change in an `.in` file is intentional.
- Every package in each `.txt` file has an exact version and at least one SHA-256 hash.
- All three generated files retain `--only-binary :all:`.
- `requirements-release.txt` contains only the declared planner and scanner
  dependencies and their transitive dependencies.
- `requirements-dev.txt` contains the same release closure plus the declared development tools.
- `requirements-fuzz.txt` contains the same development closure plus Atheris, the dependency auditor, and their transitive dependencies.
- No editable, local-path, direct-URL, extra-index, or unhashed requirement appears.

Validate all three locks in clean environments rather than reusing the environment that ran the compiler:

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
/tmp/vexcalibur-action-dev-lock/bin/python -c 'import yaml'

python -m venv /tmp/vexcalibur-action-fuzz-lock
/tmp/vexcalibur-action-fuzz-lock/bin/python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-fuzz.txt
/tmp/vexcalibur-action-fuzz-lock/bin/python -c 'import atheris'
/tmp/vexcalibur-action-fuzz-lock/bin/python -m pip_audit \
  --requirement requirements-fuzz.txt \
  --no-deps \
  --disable-pip \
  --cache-dir /tmp/vexcalibur-action-pip-audit-cache
```

Each install must finish without a hash, source-distribution, or resolver error. Remove the three `/tmp/vexcalibur-action-*-lock` environments after review.

## Run the local checks

Run the same checks from the repository root:

```bash
pre-commit run --all-files
ruff format --check scripts tests
ruff check scripts tests
bash -n scripts/*.sh
shellcheck scripts/*.sh
actionlint
git ls-files --cached --others --exclude-standard -z \
  | xargs -0 detect-secrets-hook --baseline .secrets.baseline --
python -m unittest discover -s tests
python -m unittest tests.fuzz.wrapper_properties
python scripts/check-action-contract.py
```

Every command should exit with status `0`. Both test commands end with `OK`.
Run `check-action-contract.py` after creating the candidate commit. It compares
committed Git objects and deliberately ignores staged and unstaged files.

Release tooling has one-way module dependencies. Put shared SemVer and Git
validation in `scripts/release_common.py`, frozen compatibility and note formats
in `scripts/release_metadata.py`, and remote tag operations in
`scripts/release_tags.py`. `scripts/release_state.py` owns planning and exposes
the stable API used by `scripts/release.py` and the contract guard. Don't import
the planner back into a lower layer.

The test suites divide responsibility this way:

- `tests/test_run_vexcalibur.py` covers action inputs, path handling, environment isolation, package installation, and argument forwarding.
- `tests/test_release_state.py` covers automatic planning, final-footer parsing,
  deterministic notes, graph validation, and recovery metadata.
- `tests/test_release_tags.py` covers append-only remote publication, graph
  races, and release CLI integration.
- `tests/test_github_release.py` covers exact GitHub Release projection
  verification.
- `tests/test_action_compatibility.py` validates the versionless compatibility
  declaration and its CI integration.
- `tests/test_action_contract.py` compares the public metadata in `action.yml`
  with the highest release tag and checks the required version bump.
- `tests/test_documentation.py` prevents concrete action release identities from
  becoming tracked documentation state and checks placeholder guidance.
- `tests/test_fake_osv_server.py` covers the local Open Source Vulnerabilities (OSV) test server.
- `tests/test_release_security.py` protects the hash locks and release runner, token, scanner, and artifact-digest boundaries.
- `tests/test_release_policy.py` verifies the no-bypass tag mutation rules and
  App-only tag creation policy.
- `tests/fuzz/wrapper_properties.py` checks decoded environment inputs against the real wrapper and a literal argument-vector model.

Hosted continuous integration (CI) also builds a wheel from `vexcalibur-dev/vexcalibur@main`. It exercises the action on Python 3.10 and 3.14 with `--help` and the local fake OSV server.

Development artifact jobs compare CycloneDX, OpenVEX, and CSAF output with
package-owned golden fixtures. Separate jobs resolve the pinned PyPI artifact,
reject it if PyPI marks the selected file as yanked, verify its published
SHA-256, and pass the downloaded wheel to the released-package E2E jobs. None
of these checks sends inventory to public OSV.

The required wrapper fuzz smoke uses deterministic Hypothesis examples. The weekly Atheris job is bounded and offline after dependency setup. See [Fuzz the Action wrapper](docs/how-to/fuzz-action-wrapper.md) for limits, corpus rules, local reproduction, and private triage.

## Make a focused change

Keep the public contract in `action.yml` small. A new Vexcalibur command-line interface (CLI) command normally needs no action input because `args` already passes commands through.

When you change behavior:

- Update `tests/test_run_vexcalibur.py` for installation, input, environment, or argument changes.
- Update `tests/test_release_state.py` for release classification, planning,
  notes, tag reconciliation, or recovery changes.
- Update `tests/test_action_contract.py` for a public `action.yml` contract
  change. Inputs that remain callable without a new value, and output additions,
  require a minor release. Removals, default changes, inputs newly requiring a
  caller value, output-value changes, and `runs.using` changes require a major
  release.
- Update `action-compatibility.json` only when the full declared combination is
  exercised by CI. A compatibility change requires a new action release.
- Update `docs/reference/action.md` when an input, default, path rule, output, or error changes.
- Update `docs/reference/compatibility.md` and `docs/how-to/release-action.md` when package support or release policy changes.
- Explain any new network access, GitHub permission, credential, or package-installation risk in the pull request.
- Preserve a minimized wrapper crash as an ordinary regression test before adding it to the fuzz corpus.

Use fake package data and reserved domains such as `example.com` in tests and docs. Report a vulnerability through the [private security process](SECURITY.md), not in a pull request or public issue.

## Name the pull request

Release automation reads each Conventional Commit-style message after the
latest action tag. In a squash-merge workflow, the pull request title becomes
that message. A commit containing `[skip release]` or `[release skip]` is
permanently excluded from later bump calculations.

Use `feat:` for a new user-facing capability, `fix:` for a correction, and `docs:`, `test:`, or `ci:` when no action release is needed. Breaking changes use `type!:` or a `BREAKING CHANGE:` footer. The [release runbook](docs/how-to/release-action.md) lists every recognized release type.

Release tags are permanent metadata. Never move, delete, or reuse one. Use a
branch for any alias that must advance over time.

## Open the pull request

Include:

- What changed and which user or maintainer task it affects.
- Tests for the changed contract.
- The exact verification commands you ran and their result.
- Documentation changes for any reader-visible behavior.
- Network, permission, secret, and supply-chain effects, or a statement that none changed.
- Any `action-compatibility.json` change and the CI evidence for every declared
  combination.

CI must pass before merge. If CI finds a secret-like value, remove or rotate a real secret before updating `.secrets.baseline`; use a baseline entry only for reviewed false positives.
