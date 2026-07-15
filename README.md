# Vexcalibur Action

![Vexcalibur wordmark and sword logo](docs/assets/vexcalibur-banner.png)

[![CI](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml/badge.svg)](https://github.com/vexcalibur-dev/vexcalibur-action/actions/workflows/scorecard.yml)

Vexcalibur Action runs the [Vexcalibur command-line interface (CLI)](https://github.com/vexcalibur-dev/vexcalibur) in a GitHub Actions workflow. Use it to generate Vulnerability Exploitability eXchange (VEX) from a software bill of materials (SBOM), query a service that implements the Open Source Vulnerabilities (OSV) API, or run another Vexcalibur command without maintaining a separate installation step.

The action is pre-1.0. Each action release is tested with specific Vexcalibur package versions. The current pair is `vexcalibur-action@v0.2.1` with `vexcalibur==0.3.0`.

Current continuous integration (CI) exercises the wrapper on `ubuntu-latest`. It verifies CycloneDX 1.6, OpenVEX 0.2.0, and CSAF 2.0 VEX output with local fixtures.

## Try the action

This workflow installs the current release pair and prints the Vexcalibur help. It doesn't check out your repository or query a vulnerability service.

```yaml
name: Vexcalibur

on:
  workflow_dispatch:

permissions: {}

jobs:
  help:
    runs-on: ubuntu-latest
    steps:
      - name: Run Vexcalibur
        uses: vexcalibur-dev/vexcalibur-action@v0.2.1
        with:
          package-spec: vexcalibur==0.3.0
          args: --help
```

Save the file as `.github/workflows/vexcalibur.yml` and commit it to the repository's default branch. Run **Vexcalibur** from the **Actions** tab, then open the **Run Vexcalibur** log. A passing job with Vexcalibur's command help is the success signal.

To produce an artifact from an existing SBOM, follow the [CycloneDX](docs/how-to/generate-vex-from-sbom.md), [OpenVEX](docs/how-to/generate-openvex-from-sbom.md), or [CSAF](docs/how-to/generate-csaf-from-sbom.md) guide.

## Choose what to trust

The action and the Python package are separate trust boundaries. Pin both in reviewed workflows:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@f05361ec7308e0ff2cf8b961b7ccca2c001b910b # v0.2.1
  with:
    package-spec: vexcalibur==0.3.0
    args: --help
```

An action release tag is readable, but a full release commit SHA is immutable. The example above uses the commit for `v0.2.1`. The [compatibility reference](docs/reference/compatibility.md) lists tested action and package pairs.

An exact `package-spec` doesn't pin transitive Python dependencies. For repeatable installs, commit a pip constraints file and pass its absolute path:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@v0.2.1
  with:
    package-spec: vexcalibur==0.3.0
    constraints-file: ${{ github.workspace }}/.github/vexcalibur-constraints.txt
    args: --help
```

The action rejects Git URLs, local wheels, and other development package specs unless you set `allow-development-package-spec: "true"`. See the [action reference](docs/reference/action.md) before using a development spec.

## Know when data leaves the runner

Installing a PyPI or Git package uses the network. Vexcalibur commands may also contact GitHub or an Open Source Vulnerabilities (OSV) service, depending on their arguments.

The Vexcalibur CLI refuses to send package URLs, versions, or SBOM inventory to `https://api.osv.dev` unless `--allow-public-osv` is present. Don't add that flag for private inventory without approval. Use local findings or an approved private OSV-compatible endpoint instead.

## How it runs

The action selects Python and creates a private virtual environment under `RUNNER_TEMP`. It installs `package-spec` there, then invokes the installed `vexcalibur` executable. Each nonblank line in `args` becomes one CLI argument.

The CLI runs from the action's private temporary directory, not from your repository. Use absolute paths such as `${{ github.workspace }}/sbom.json` for inputs and `${{ runner.temp }}/vex.json` for outputs.

See the [action reference](docs/reference/action.md) for every input, path and argument rules, installation isolation, output behavior, and failure codes.

## Documentation

| If you want to… | Read… |
| --- | --- |
| Generate and upload CycloneDX VEX from a checked-out SBOM | [Generate CycloneDX VEX from an SBOM](docs/how-to/generate-vex-from-sbom.md) |
| Generate and upload OpenVEX from a checked-out SBOM | [Generate OpenVEX from an SBOM](docs/how-to/generate-openvex-from-sbom.md) |
| Generate and upload CSAF VEX from a checked-out SBOM | [Generate CSAF VEX from an SBOM](docs/how-to/generate-csaf-from-sbom.md) |
| Configure an action input or diagnose a failed run | [Action reference](docs/reference/action.md) |
| Choose an action and package version | [Compatibility reference](docs/reference/compatibility.md) |
| Publish or recover an action release | [Release the action](docs/how-to/release-action.md) |
| Change the wrapper or its tests | [Contributing](CONTRIBUTING.md) |
| Run or triage wrapper fuzzing | [Fuzz the Action wrapper](docs/how-to/fuzz-action-wrapper.md) |
| Report a non-security bug or request a feature | [Vexcalibur Action issues](https://github.com/vexcalibur-dev/vexcalibur-action/issues) |
| Report a vulnerability | [Security policy](SECURITY.md) |
| Understand participation expectations | [Code of conduct](https://github.com/vexcalibur-dev/.github/blob/main/CODE_OF_CONDUCT.md) |

The Vexcalibur repository owns the [CLI reference](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md), input formats, and generated VEX contract.

## Verify a local change

Run these commands from the repository root after installing Python 3.14 and [actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12):

```bash
python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-dev.txt
bash -n scripts/*.sh
shellcheck scripts/*.sh
actionlint
git ls-files --cached --others --exclude-standard -z \
  | xargs -0 detect-secrets-hook --baseline .secrets.baseline --
python -m unittest discover -s tests
python -m unittest tests.fuzz.wrapper_properties
```

Every command should exit with status `0`; the final command reports the test count and `OK`. [Contributing](CONTRIBUTING.md) covers the development setup and pull request checklist.

Vexcalibur Action is available under the [Apache License 2.0](LICENSE).
