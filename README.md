# Vexcalibur Action

GitHub Action wrapper for Vexcalibur.

This repository is pre-alpha. The action currently installs the Vexcalibur Python package and exposes a small command surface for CI workflows. Broader VEX generation and legacy `vexy` compatibility will land in the package first, then this action will expose stable workflow inputs.

## Usage

Show the installed Vexcalibur help:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@v0
  with:
    command: help
```

Query OSV for package URLs:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@v0
  with:
    command: query-osv
    purls: |
      pkg:pypi/django@1.2
      pkg:npm/minimist@0.0.8
```

Until Vexcalibur has published releases, test workflows can install from Git:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@main
  with:
    package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
    command: help
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `package-spec` | `vexcalibur` | Package spec passed to `pipx install`. |
| `python-version` | `3.14` | Python version used to install and run Vexcalibur. |
| `command` | `help` | Supported values: `help`, `query-osv`. |
| `purls` | empty | Newline-separated package URLs for `query-osv`. |

## Development

Run local checks:

```bash
bash -n scripts/run-vexcalibur.sh
python -m unittest discover -s tests
```

## Project Links

- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)
