# Generate CycloneDX VEX from an SBOM

Use this guide to turn a checked-out CycloneDX software bill of materials (SBOM) and a local findings file into a CycloneDX 1.6 Vulnerability Exploitability eXchange (VEX) artifact. The vulnerability lookup stays local: Vexcalibur doesn't contact the Open Source Vulnerabilities (OSV) service in this workflow.

The checkout and Python package installation still use the network. If the whole job must run without network access, mirror or pre-stage those dependencies according to your runner policy.

## Before you start

Your repository needs:

- A CycloneDX JSON or XML SBOM.
- A local findings document in [Vexcalibur's findings format](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/local-findings.md).
- A tested action and package pair from the [compatibility table](../reference/compatibility.md).

The workflow below expects these paths:

```text
security/sbom.cdx.json
security/vexcalibur-findings.json
```

Local findings must identify components that exist in the SBOM. A finding can use the component's BOM reference or a package URL that appears exactly once.

## Add the workflow

Create `.github/workflows/generate-vex.yml` with this content:

```yaml
name: Generate VEX

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  vex:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false

      - name: Prepare output directory
        run: mkdir -p "$RUNNER_TEMP/vexcalibur"

      - name: Generate VEX
        uses: vexcalibur-dev/vexcalibur-action@6a028a18b4b7fc15cd5e83056e0013ed0928a483 # v0.2.0
        with:
          package-spec: vexcalibur==0.2.0
          args: |
            generate
            ${{ github.workspace }}/security/sbom.cdx.json
            --offline
            --findings-file
            ${{ github.workspace }}/security/vexcalibur-findings.json
            --output
            ${{ runner.temp }}/vexcalibur/cyclonedx-vex.json

      - name: Validate VEX
        run: |
          python - <<'PY'
          import json
          import os
          from pathlib import Path

          path = Path(os.environ["RUNNER_TEMP"]) / "vexcalibur" / "cyclonedx-vex.json"
          vex = json.loads(path.read_text(encoding="utf-8"))
          assert vex["bomFormat"] == "CycloneDX", vex
          assert vex["specVersion"] == "1.6", vex
          assert isinstance(vex.get("vulnerabilities", []), list), vex
          print(f"validated {path}")
          PY

      - name: Upload VEX
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: cyclonedx-vex
          path: ${{ runner.temp }}/vexcalibur/cyclonedx-vex.json
          if-no-files-found: error
```

The paths passed to Vexcalibur are absolute because the action runs the command-line interface (CLI) from a private temporary directory. Relative paths don't resolve from the checked-out repository.

## Run and verify it

Commit the workflow, SBOM, and findings file to the repository's default branch. Open **Actions**, select **Generate VEX**, and choose **Run workflow**.

The run is successful when:

1. The **Generate VEX** step exits with status `0`.
2. The **Validate VEX** step prints a `validated` message.
3. The run summary contains a `cyclonedx-vex` artifact with `cyclonedx-vex.json`.

Download the artifact and review its findings before using it as a security assertion. Vexcalibur preserves the analysis state and detail supplied by the local findings file.

## Use a private OSV-compatible service

If an approved OSV-compatible service should discover findings, remove `--offline` and `--findings-file`. Pass the service base URL instead:

```yaml
args: |
  generate
  ${{ github.workspace }}/security/sbom.cdx.json
  --osv-url
  https://osv.internal.example
  --output
  ${{ runner.temp }}/vexcalibur/cyclonedx-vex.json
```

The endpoint must use HTTPS unless it is a loopback address. See the [Vexcalibur CLI reference](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/cli.md#vexcalibur-generate) for URL constraints and provider errors.

## Use the public OSV API

The public OSV API receives package URLs and versions derived from the SBOM.

If that disclosure is approved and the inventory is suitable for a public service, replace the local source flags with `--allow-public-osv`:

```yaml
args: |
  generate
  ${{ github.workspace }}/security/sbom.cdx.json
  --allow-public-osv
  --output
  ${{ runner.temp }}/vexcalibur/cyclonedx-vex.json
```

Without the flag, Vexcalibur fails closed instead of sending inventory to `https://api.osv.dev`.

## Make fixture output repeatable

Vexcalibur uses the current time in document metadata unless you pass `--timestamp`. For a golden fixture or a reproducibility check, add a controlled ISO 8601 value as two argument lines:

```yaml
args: |
  generate
  ${{ github.workspace }}/security/sbom.cdx.json
  --offline
  --findings-file
  ${{ github.workspace }}/security/vexcalibur-findings.json
  --timestamp
  2026-06-23T00:00:00Z
  --output
  ${{ runner.temp }}/vexcalibur/cyclonedx-vex.json
```

Don't copy a fixture timestamp into a current production assertion. Use a timestamp that represents the document being generated.

## Troubleshoot the workflow

| Symptom | Check |
| --- | --- |
| Vexcalibur reports that an input file doesn't exist | Confirm the repository was checked out and the argument starts with `${{ github.workspace }}`. |
| Vexcalibur can't write the output | Create the parent directory first and use an absolute `${{ runner.temp }}` path. |
| The action rejects `package-spec` | Use the exact package from the compatibility table, or opt into a trusted development spec explicitly. |
| `--offline` requires a findings file | Pass both `--offline` and `--findings-file`, each value on its own line. |
| A local finding doesn't match an SBOM component | Compare its `component_ref` or package URL with the SBOM. Package URLs used for fallback matching must be unique. |
| Public OSV requires explicit opt-in | Decide whether the inventory can leave the runner. Add `--allow-public-osv` only after approval, or choose a private or local source. |
| The artifact step finds no file | Make the `--output` value and upload path identical. Keep `if-no-files-found: error` so the job doesn't hide the failure. |

The [action reference](../reference/action.md) covers argument conversion, path rules, package installation, and action-level exit codes.
