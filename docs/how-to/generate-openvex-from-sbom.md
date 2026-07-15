# Generate OpenVEX from an SBOM

Use this guide to turn a checked-out CycloneDX software bill of materials (SBOM) and local findings into OpenVEX 0.2.0 JSON. The generation step does not contact an Open Source Vulnerabilities (OSV) service.

The checkout and package installation still use the network. Mirror those dependencies if your runner must stay offline.

## Before you start

You need:

- A GitHub Actions runner compatible with the [runner requirements](../reference/action.md#runner-requirements).
- A CycloneDX JSON or XML SBOM.
- A local findings document in [Vexcalibur's findings format](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/local-findings.md).
- A reviewed document author name.
- The tested action and package pair from the [compatibility table](../reference/compatibility.md).

The workflow below expects these repository paths:

```text
security/sbom.cdx.json
security/vexcalibur-findings.json
```

Each finding must match one SBOM component. OpenVEX also requires a versioned package URL for every product assertion.

## Add the workflow

Create `.github/workflows/generate-openvex.yml` with this content:

```yaml
name: Generate OpenVEX

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  openvex:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false

      - name: Prepare output directory
        run: mkdir -p "$RUNNER_TEMP/vexcalibur"

      - name: Generate OpenVEX
        uses: vexcalibur-dev/vexcalibur-action@f05361ec7308e0ff2cf8b961b7ccca2c001b910b # v0.2.1
        with:
          package-spec: vexcalibur==0.3.0
          args: |
            generate
            ${{ github.workspace }}/security/sbom.cdx.json
            --offline
            --findings-file
            ${{ github.workspace }}/security/vexcalibur-findings.json
            --format
            openvex
            --author
            Example Security Team
            --author-role
            VEX document producer
            --output
            ${{ runner.temp }}/vexcalibur/openvex.json

      - name: Validate OpenVEX
        run: |
          python - <<'PY'
          import json
          import os
          from pathlib import Path

          path = Path(os.environ["RUNNER_TEMP"]) / "vexcalibur" / "openvex.json"
          document = json.loads(path.read_text(encoding="utf-8"))

          assert document["@context"] == "https://openvex.dev/ns/v0.2.0", document
          assert document["author"] == "Example Security Team", document
          assert document["role"] == "VEX document producer", document
          statements = document.get("statements")
          assert isinstance(statements, list) and statements, document

          allowed_statuses = {
              "affected",
              "fixed",
              "not_affected",
              "under_investigation",
          }
          for statement in statements:
              assert statement["status"] in allowed_statuses, statement
              products = statement.get("products")
              assert isinstance(products, list) and products, statement
              for product in products:
                  assert product["@id"] == product["identifiers"]["purl"], product

              if statement["status"] == "affected":
                  assert statement.get("action_statement", "").strip(), statement
              if statement["status"] == "not_affected":
                  assert statement.get("impact_statement", "").strip(), statement
              if statement["status"] == "fixed":
                  assert "Confirmed fixed product version:" in statement["status_notes"], statement

          print(f"validated {path}")
          PY

      - name: Upload OpenVEX
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: openvex
          path: ${{ runner.temp }}/vexcalibur/openvex.json
          if-no-files-found: error
```

Replace `Example Security Team` and the role with values approved by your organization. The author accepts responsibility for the statements in the document.

The action runs the command-line interface (CLI) from a private temporary directory. That is why every caller-owned input and output uses an absolute path.

## Supply status evidence

OpenVEX needs explicit evidence for several Vexcalibur analysis states:

| Analysis state | OpenVEX status | Local finding requirement |
| --- | --- | --- |
| `resolved` | `fixed` | `fixed_version` must equal the version in the product package URL. |
| `exploitable` | `affected` | `action_statement` must describe remediation or mitigation. |
| `in_triage` | `under_investigation` | No extra evidence field. |
| `false_positive` | `not_affected` | `impact_statement` must explain why the product is not affected. |
| `not_affected` | `not_affected` | `impact_statement` must explain why the product is not affected. |

Vexcalibur rejects evidence fields on other states. Read the [OpenVEX output contract](https://github.com/vexcalibur-dev/vexcalibur/blob/main/docs/reference/openvex-output.md) before publishing an assertion.

## Run and verify it

Commit the workflow, SBOM, and findings file to the repository's default branch. Open **Actions**, select **Generate OpenVEX**, and choose **Run workflow**.

The run is successful when:

1. **Generate OpenVEX** exits with status `0`.
2. **Validate OpenVEX** prints a `validated` message.
3. The run summary contains an `openvex` artifact with `openvex.json`.

Download and review the artifact before using it as a security assertion. If the document is wrong, remove it from downstream systems and correct the SBOM or findings before generating a replacement.

## Troubleshoot the workflow

| Symptom | Check |
| --- | --- |
| `--author is required with --format openvex` | Pass a nonblank author approved to make the assertions. |
| OpenVEX requires at least one finding | Confirm that the findings array is nonempty and the correct file path is in `args`. |
| A finding requires an action or impact statement | Add the state-specific evidence field, or correct the analysis state. |
| `fixed_version` does not match the product | Align the fixed version with the matched SBOM component. Do not weaken the assertion. |
| A product package URL must include a version | Add the component version to the SBOM or its package URL. |
| The action cannot find an input or output | Use `${{ github.workspace }}` for checked-in inputs and `${{ runner.temp }}` for temporary output. |
| The artifact step finds no file | Keep the `--output` value and upload path identical. |

The [action reference](../reference/action.md) covers argument conversion, path rules, installation, and action-level exit codes.
