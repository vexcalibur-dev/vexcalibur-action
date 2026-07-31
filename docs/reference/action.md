# Action reference

Vexcalibur Action is a composite GitHub Action that installs a selected Vexcalibur Python package and invokes its `vexcalibur` executable. It doesn't add a second command model: commands, flags, input formats, and Vulnerability Exploitability eXchange (VEX) output belong to the [Vexcalibur command-line interface (CLI)](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md).

Input and default changes follow the semantic-version rules in the
[release runbook](../how-to/release-action.md#tag-calculation).

## Runner requirements

This repository verifies the action on GitHub-hosted `ubuntu-latest` runners. The wrapper assumes `/bin/bash`, POSIX paths such as `/dev/null` and `venv/bin`, and a writable, executable `RUNNER_TEMP` directory.

Other runner operating systems aren't part of the current compatibility contract. A self-hosted runner must provide the same shell, path, and filesystem behavior.

## Inputs

The action defines these inputs:

| Input | Required | Default | Value |
| --- | --- | --- | --- |
| `package-spec` | Yes | None | The single package requirement passed to `pip install`. Release workflows use the exact spec published with the selected Action release. |
| `allow-development-package-spec` | No | `false` | The exact string `true` permits Git URLs, local wheels, paths, and other non-release package specs. Any other value leaves release-only validation in place. |
| `constraints-file` | No | Empty | Absolute path to a readable [pip constraints file](https://pip.pypa.io/en/stable/user_guide/#constraints-files). |
| `python-version` | No | `3.14` | Version request passed to `actions/setup-python`. This repository verifies Python 3.10 and 3.14. |
| `args` | No | `--help` | Newline-separated arguments for the installed `vexcalibur` executable. |

### `package-spec`

Without the development opt-in, `package-spec` must start with `vexcalibur==` and name one exact release:

Replace `REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC` with the value published in the
selected Action release notes.

```yaml
with:
  package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
```

The [compatibility reference](compatibility.md) explains how to read the package
and Python versions snapshotted by an action release.

Set `allow-development-package-spec: "true"` only for a package source you trust. This example installs the current development branch:

```yaml
with:
  package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
  allow-development-package-spec: "true"
  args: --help
```

Development specs may be mutable. A package installation can run build code with the job's access to the runner, filesystem, network, and inherited environment.

### `constraints-file`

An exact `package-spec` pins Vexcalibur itself. It doesn't pin packages that Vexcalibur depends on. Pass a complete constraints file when those versions must remain stable:

```yaml
with:
  package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
  constraints-file: ${{ github.workspace }}/.github/vexcalibur-constraints.txt
  args: --help
```

The path must be absolute and name a readable regular file. The action passes it to `pip install --constraint`; it doesn't create or update the file.

### `args`

Each nonblank line becomes one argument. For example:

```yaml
with:
  package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
  args: |
    generate
    ${{ github.workspace }}/security/sbom.json
    --offline
    --findings-file
    ${{ github.workspace }}/security/findings.json
    --output
    ${{ runner.temp }}/vexcalibur/vex.json
```

Argument conversion follows these rules:

- Blank lines are discarded.
- A trailing carriage return is removed from each line.
- Leading and trailing spaces remain part of the argument.
- Quotes, backslashes, and shell operators remain literal text. No shell parses them.
- `--` must appear on its own line when a Vexcalibur command uses it to end option parsing.
- An explicit empty `args` value invokes `vexcalibur` with no arguments. Omitting the input uses `--help`.

Don't wrap a value in shell quotes. Put the complete value on one line, even when it contains spaces.

## File paths and working directory

The CLI runs from a newly created private directory under `RUNNER_TEMP`, not from `github.workspace`. Relative paths therefore point inside that temporary directory.

Use GitHub's absolute path contexts:

- Repository inputs: `${{ github.workspace }}/path/to/file`
- Temporary outputs: `${{ runner.temp }}/path/to/file`

Create an output's parent directory in an earlier workflow step. The action doesn't create caller-selected output directories or upload generated files.

`constraints-file` must also be absolute. Relative constraint paths fail before package installation.

## Network boundaries

Package installation may contact PyPI, a Git server, or another location named by the package spec or constraints file. The action doesn't provide an offline package cache.

Vexcalibur commands decide whether they contact GitHub or a service that implements the Open Source Vulnerabilities (OSV) API. The CLI refuses to send package URLs, versions, or inventory derived from a software bill of materials (SBOM) to the public OSV API unless `--allow-public-osv` appears in `args`. The action never adds that flag.

Use `--osv-url` for an approved private OSV-compatible endpoint, or `--offline --findings-file` for local findings. Don't pass `--allow-public-osv` for private inventory unless the disclosure is approved.

The wrapper adds no timeout or retry policy. Pip and the selected Vexcalibur command own their network behavior; set a job-level `timeout-minutes` when the workflow needs a hard limit.

## GitHub permissions and tokens

The wrapper itself doesn't call the GitHub API and declares no required `GITHUB_TOKEN` permissions. A help-only job can use `permissions: {}`.

Grant permissions for the surrounding workflow and selected CLI command. Checking out a private repository needs `contents: read`. A token-backed `vexcalibur generate --github-repo` request also needs repository contents read permission; the [Vexcalibur CLI reference](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md#vexcalibur-generate) defines its token lookup and GitHub API options.

The installed package and CLI inherit environment variables that the action doesn't scrub, including caller-provided GitHub tokens. Grant the narrowest permissions the command needs.

## Runtime model

The sequence below shows installation and command execution.

```mermaid
sequenceDiagram
    participant Job as Caller job
    participant Action as Vexcalibur Action
    participant Temp as Private runner directory
    participant Package as Installed Vexcalibur package
    participant CLI as Installed Vexcalibur CLI

    Job->>Action: package spec, Python version, constraints, arguments
    Action->>Action: Select Python and validate install inputs
    Action->>Temp: Create virtual environment
    Action->>Temp: Install the selected package
    Action->>Package: Read the report schema marker when applicable
    Action->>CLI: Invoke vexcalibur with one argument per nonblank line
    CLI->>Temp: Write a private execution report when supported
    Action->>Temp: Read and validate the report
    Action->>Action: Publish structured outputs
    Action-->>Job: Return output, report fields, and exit status
```

In text: the action selects Python, validates the installation inputs, creates a
temporary virtual environment, and installs one package spec. For a `generate`
command, it checks the installed package's public report-schema marker. A
compatible package receives a private report path. After the command succeeds,
the Action validates that report and publishes its fields as step outputs.
Other commands run without a report. Standard output, standard error, and the
exit status flow back to the caller job.

The implementation applies these controls:

1. The run step starts `/bin/bash` without profile or startup files and clears `BASH_ENV` before the shell starts.
2. The script validates `package-spec` and `constraints-file`, then converts `args` into an array.
3. It removes action argument variables and inherited environment variables whose names begin with `PYTHON`, `PIP_`, or `PIPX_`.
4. It creates a private work directory and virtual environment under `RUNNER_TEMP` using Python isolated mode.
5. It runs pip with `--isolated --no-cache-dir`, sets `PIP_CONFIG_FILE=/dev/null`, and uses a private cache path.
6. It resolves `vexcalibur` only from the new virtual environment.
7. For `generate`, it imports the public
   `EXECUTION_REPORT_SCHEMA_VERSION` marker from the installed package. Schema
   version 1 receives an Action-managed report path before the caller's
   arguments.
8. After a successful compatible command, it validates the report and appends
   the structured values to `GITHUB_OUTPUT`. Other commands and older packages
   receive their original arguments and leave report outputs unset.

The action ignores caller-provided executable paths such as `VEXCALIBUR_BIN` and doesn't search the caller's `PATH` for Vexcalibur.

The virtual environment isolates Python packages; it isn't a process sandbox. Package build code and the installed CLI retain the job's operating-system permissions, network access, accessible files, and environment variables that the action doesn't scrub. Pin and review the action, package, constraints, and CLI arguments accordingly.

## Outputs

GitHub Actions exposes every value as a string. The two JSON outputs contain
minified JSON text; the counts and byte size contain base-10 digits.

| Output | Value |
| --- | --- |
| `execution-report` | Validated, minified JSON containing the complete schema-versioned report. |
| `execution-report-path` | Absolute path to the validated report under `RUNNER_TEMP`. |
| `vexcalibur-version` | Installed Vexcalibur package version recorded by the report. |
| `component-count` | Decimal count of normalized components sent to the finding source. |
| `finding-count` | Decimal count of normalized findings sent to the renderer. |
| `analysis-state-counts` | Minified JSON object containing positive counts for states that occurred. |
| `output-format` | `cyclonedx`, `openvex`, `csaf`, or `custom`. |
| `document-sha256` | Lowercase SHA-256 digest of the exact generated document bytes. |
| `document-bytes` | Decimal size of the exact generated document in UTF-8 bytes. |

The [core execution-report
reference](https://vexcalibur-dev.github.io/vexcalibur/reference/execution-report.html)
defines the complete JSON schema and field semantics.

Outputs are available only after a successful `generate` command from a
package whose schema marker identifies execution-report version 1. The Action
owns the `--execution-report` option; `args` must not contain that option or
`--execution-report=PATH`. The literal token is reserved in every position,
including as another option's value or after `--`. Other commands and older
packages leave every output empty. `generate --help` also keeps its original
arguments and leaves the outputs empty because it does not generate a document.
Other help forms accepted by the CLI, such as `generate INPUT --offline
--help`, behave the same way.

The wrapper treats any literal `--help` before the `--` option terminator as a
help request. It does not copy the installed package's option grammar to decide
whether another option would consume that token as a value. Use `./--help` or
an absolute path when an option value must name a file called `--help` and the
workflow needs report outputs. The Action checks the package's schema marker
before applying this rule; a broken or unsupported marker fails even when the
invocation requests help.

The Action validates the report's closed field set, types, enum values, state
count total, digest format, and 16 KiB size limit. Duplicate JSON keys and
unknown fields fail. It also rejects a reported document size above the core
schema's 25 MiB limit. Component, finding, and per-state counts must be between
0 and 10,000,000; a state present in the map must have a positive count. The
wrapper does not parse the generated VEX document or recalculate core values.

The complete report preserves the core schema's `custom` inventory, finding,
and output categories. The current CLI emits concrete built-in categories, but
`custom` remains a valid schema-version-1 value and is not treated as a
malformed report.

A missing, malformed, oversized, or inconsistent report from a managed command
makes the step fail. A failed CLI command publishes no report outputs, even if
it left a file behind. This includes `execution-report-path`; files left under
`RUNNER_TEMP` after failure are unsupported forensic residue, not Action
outputs.

The `execution-report` output is the validated report value captured by the
Action. `execution-report-path` points to a job-local file that a later step can
modify. Compare the file with `execution-report` before consuming it, or use
the output value directly. Neither value proves who created the report; use an
attestation or signature when the report needs provenance outside the job.

Counts, source categories, the package version, and a document digest may reveal
operational information. Treat Action outputs as build metadata. Don't print or
export them unless that disclosure is approved.

Use a step `id` to consume an output:

```yaml
- name: Generate VEX
  id: vexcalibur
  uses: vexcalibur-dev/vexcalibur-action@REPLACE_WITH_FULL_COMMIT_SHA
  with:
    package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
    args: |
      generate
      ${{ github.workspace }}/security/sbom.json
      --offline
      --findings-file
      ${{ github.workspace }}/security/findings.json
      --output
      ${{ runner.temp }}/vexcalibur/vex.json

- name: Verify generation metadata
  env:
    DOCUMENT_SHA256: ${{ steps.vexcalibur.outputs.document-sha256 }}
  run: |
    test -n "$DOCUMENT_SHA256"
```

Both placeholders must come from one tested Action release. Create the output
directory before this excerpt. The second step succeeds when the Action
published generation metadata without writing that metadata to the job log.

A zero `finding-count` says only that the selected source returned no
normalized findings. It does not mean `clean`, `safe`, or `passed`. Live OSV
results can also change, so counts aren't stable unless the underlying data is
controlled.

The complete report omits package names, package URLs, vulnerability
identifiers, repository names, filesystem paths, provider URLs, credentials,
and exception text.

The installed CLI continues to write standard output and standard error to the
step log. A command such as `generate --output ABSOLUTE_PATH` can write a file,
but a later step must validate or upload it.

## Exit behavior

The action returns the first failure it encounters:

| Condition | Exit code | Diagnostic |
| --- | --- | --- |
| Vexcalibur succeeds | `0` | CLI output appears in the step log. |
| `package-spec` is empty | `2` | `package-spec is required` |
| A non-release package spec lacks the development opt-in | `2` | The message requires an exact Vexcalibur release and names the opt-in. |
| `constraints-file` is relative | `2` | `constraints-file must be an absolute path: ...` |
| `constraints-file` is missing or unreadable | `2` | `constraints-file does not exist or is not readable: ...` |
| `RUNNER_TEMP` is empty | `2` | The message says `RUNNER_TEMP` is required for isolation. |
| The selected Python path is empty or not executable | `2` | The message names `VEXCALIBUR_PYTHON`. |
| Temporary setup or virtual-environment creation fails | Nonzero setup status | Python or Bash writes the failure to the step log. |
| Package installation fails | pip's exit code | pip writes the installation error to the step log. |
| The installed package has no `vexcalibur` executable | `127` | `vexcalibur executable was not found after installation` |
| Vexcalibur fails | The CLI's exit code | The CLI writes its diagnostic to the step log. |
| The package exposes a broken or unsupported report marker | `2` | The message identifies the execution-report contract. |
| Caller arguments set `--execution-report` for a compatible package | `2` | The message identifies the Action-managed option. |
| A supported command omits or returns an invalid report | `2` | `execution report error: ...` |
| `GITHUB_OUTPUT` cannot be opened or is not a regular file | `2` | The `execution report error` message identifies `GITHUB_OUTPUT`. |

## Related guides

- [Generate CycloneDX VEX from an SBOM](../how-to/generate-vex-from-sbom.md) provides a complete CycloneDX artifact workflow.
- [Generate OpenVEX from an SBOM](../how-to/generate-openvex-from-sbom.md) provides a complete OpenVEX artifact workflow.
- [Generate CSAF VEX from an SBOM](../how-to/generate-csaf-from-sbom.md) provides a complete CSAF artifact workflow.
- [Compatibility reference](compatibility.md) explains release metadata and CI
  coverage.
- [Vexcalibur CLI reference](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md) defines commands and provider-specific failures.
- [Contributing](../../CONTRIBUTING.md) gives the local verification commands for changes to this wrapper.
