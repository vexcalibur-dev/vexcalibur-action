# Vexcalibur Action Reference

The Vexcalibur Action is pre-alpha. Inputs, default values, command support, and
exit behavior can change before the first stable action release.

## Supported Commands

The `command` input currently accepts:

- `help`: install Vexcalibur and run `vexcalibur --help`.
- `query-osv`: install Vexcalibur and run `vexcalibur query-osv --allow-public-osv -- PURL...`.

The action does not currently expose `vexcalibur generate`. SBOM-to-VEX action
support is planned separately from this initial `query-osv` wrapper.

## Inputs

| Input | Required | Default | Contract |
| --- | --- | --- | --- |
| `package-spec` | Yes | None | Package spec passed to isolated `pip install`. Release workflows must use an exact release such as `vexcalibur==0.1.0`. |
| `allow-development-package-spec` | No | `false` | Set to `true` to allow Git URLs, local paths, or other non-release package specs in development workflows. |
| `python-version` | No | `3.14` | Python version passed to `actions/setup-python`. |
| `command` | No | `help` | Supported values are `help` and `query-osv`. |
| `purls` | No | empty | Newline-separated package URLs. Required when `command` is `query-osv`; blank lines are ignored. |
| `allow-public-osv` | No | `false` | Must be `true` when `command` is `query-osv`; the action currently has no private OSV mirror input. |

`package-spec` is validated before installation. Without
`allow-development-package-spec: "true"`, the value must match an exact
Vexcalibur release package spec such as `vexcalibur==0.1.0`.

`purls` is split by line. Each line is trimmed, carriage returns are removed,
and blank lines are ignored. Values that look like command-line options are
passed as data after `--`, not interpreted as action flags.

## Public OSV Boundary

`query-osv` sends package URLs to the public OSV API through the Vexcalibur CLI.
The action therefore fails before installation unless
`allow-public-osv: "true"` is set for `query-osv`.

Do not set `allow-public-osv` for private package inventories unless sending
those package URLs to `https://api.osv.dev` is explicitly approved for the
workflow. Use a later action release with private-provider support when private
SBOM or package inventory data must stay inside your environment.

## Runtime Behavior

The action runs as a composite action and delegates execution to
`scripts/run-vexcalibur.sh`.

Runtime sequence:

1. `actions/setup-python` installs or selects `python-version`.
2. The shell step runs with `/bin/bash --noprofile --norc -e -o pipefail` and
   clears `BASH_ENV` before the script starts.
3. The script validates action inputs before installing Vexcalibur.
4. The script creates a private working directory and virtual environment under
   `RUNNER_TEMP`.
5. The script scrubs inherited `PYTHON*`, `PIP_*`, and `PIPX_*` environment
   variables before Python and pip run.
6. `pip` installs `package-spec` with `PIP_CONFIG_FILE=/dev/null`,
   `PIP_CACHE_DIR` set to the private action cache directory, `python -I`, and
   `pip --isolated --no-cache-dir`.
7. The script runs the `vexcalibur` executable from the private virtual
   environment.

The action does not honor caller-provided executable paths such as
`VEXCALIBUR_BIN`, and it does not resolve `vexcalibur` from the caller's `PATH`.
Package URL input is removed from the environment before installation so
install-time code does not receive `VEXCALIBUR_PURLS`.

## Outputs

The action does not define structured GitHub Actions outputs.

Command output is written to the workflow log:

- `help` writes the installed `vexcalibur --help` output.
- `query-osv` passes through the installed Vexcalibur CLI output.

See the Vexcalibur
[CLI reference](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md)
for the current `query-osv` output shape. Live OSV data changes over time, so
vulnerability IDs, counts, and ordering can change.

## Exit Behavior

| Condition | Exit code | Message shape |
| --- | --- | --- |
| `help` succeeds | `0` | Vexcalibur help appears in the workflow log. |
| `query-osv` succeeds | `0` | One CLI result line appears per package URL. |
| `package-spec` is missing | `2` | `package-spec is required until a stable Vexcalibur release is published`. |
| `package-spec` is not an exact release and development specs are not allowed | `2` | `package-spec must be an exact Vexcalibur release...`. |
| `command` is unsupported | `2` | `unsupported command: VALUE`. |
| `query-osv` has no nonblank `purls` lines | `2` | `purls input is required when command is query-osv`. |
| `query-osv` is missing public OSV opt-in | `2` | `allow-public-osv must be true when command is query-osv`. |
| Runner Python is missing or not executable | `2` | The message names the missing or invalid runner Python value. |
| `RUNNER_TEMP` is missing | `2` | `RUNNER_TEMP is required to isolate the Vexcalibur installation`. |
| Runner temp setup fails after validation | nonzero internal setup exit | Python or shell writes the setup failure to the workflow log. |
| Installed package does not provide a `vexcalibur` executable | `127` | `vexcalibur executable was not found after installation`. |
| `pip install` fails | pip exit code | pip writes the installation error to the workflow log. |
| The Vexcalibur CLI exits nonzero | CLI exit code | The CLI writes its own failure message to the workflow log. |

## Development Verification

From the action repository root, run:

```bash
python -m pip install -r requirements-dev.txt
bash -n scripts/run-vexcalibur.sh
python -m unittest discover -s tests
```

Expected success signal: `unittest` reports all tests passing.

## Workflow Verification

Use the development quick-start workflows in the repository
[README](../../README.md). Expected success signals:

- `help`: the workflow passes and the action logs include Vexcalibur help
  output.
- `query-osv`: the workflow passes and the action logs include Vexcalibur CLI
  output for each submitted package URL.
