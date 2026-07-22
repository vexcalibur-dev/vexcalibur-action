# Generate CSAF VEX from an SBOM

Use this guide to turn a checked-out CycloneDX software bill of materials
(SBOM) and local findings into a CSAF 2.0 JSON document with the `csaf_vex`
profile. The generation step stays offline and does not contact an Open Source
Vulnerabilities (OSV) service.

The checkout and package installation still use the network. Mirror those
dependencies if your runner must stay offline.

## Before you start

You need:

- A GitHub Actions runner compatible with the [runner
  requirements](../reference/action.md#runner-requirements).
- A CycloneDX JSON or XML SBOM whose asserted products have versioned package
  URLs.
- A local findings document in [Vexcalibur's findings
  format](https://vexcalibur-dev.github.io/vexcalibur/reference/local-findings.html).
- A tracking ID, title, publisher name, publisher category, and absolute
  namespace URL approved by the organization responsible for the document.
- The tested action and package pair resolved through the
  [compatibility reference](../reference/compatibility.md).

The workflow below expects these repository paths:

```text
security/sbom.cdx.json
security/vexcalibur-findings.json
```

Each finding must match one SBOM component. Review the [CSAF output
contract](https://vexcalibur-dev.github.io/vexcalibur/reference/csaf-output.html)
before using the result as a security assertion.

SBOMs, findings, and CSAF documents can expose private inventory and
vulnerability assessments. Don't commit them to a public repository or upload
them from a public workflow unless that disclosure is approved. Anyone who can
read the repository may be able to download its workflow artifacts. The example
retains its result for one day; lower repository-wide retention or skip the
upload if your policy requires less exposure.

## Add the workflow

Replace `REPLACE_WITH_ACTION_SHA` and
`REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC` with the values resolved from the same
release. Then create `.github/workflows/generate-csaf.yml` with this content:

```yaml
name: Generate CSAF VEX

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  csaf:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false

      - name: Prepare output directory
        run: mkdir -p "$RUNNER_TEMP/vexcalibur"

      - name: Generate CSAF VEX
        uses: vexcalibur-dev/vexcalibur-action@REPLACE_WITH_ACTION_SHA
        with:
          package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
          args: |
            generate
            ${{ github.workspace }}/security/sbom.cdx.json
            --offline
            --findings-file
            ${{ github.workspace }}/security/vexcalibur-findings.json
            --format
            csaf
            --csaf-version
            2.0
            --csaf-document-id
            EXAMPLE-VEX-2026-001
            --csaf-document-title
            Example component exploitability assessment
            --csaf-publisher-name
            Example Product Security
            --csaf-publisher-namespace
            https://security.example.com
            --csaf-publisher-category
            vendor
            --csaf-document-status
            draft
            --output
            ${{ runner.temp }}/vexcalibur/example-vex-2026-001.json

      - name: Validate CSAF VEX structure
        run: |
          python - <<'PY'
          import json
          import os
          from pathlib import Path

          path = Path(os.environ["RUNNER_TEMP"]) / "vexcalibur" / "example-vex-2026-001.json"
          document = json.loads(path.read_text(encoding="utf-8"))

          def require(condition, message):
              if not condition:
                  raise SystemExit(message)

          require("$schema" not in document, "CSAF document contains $schema")
          metadata = document["document"]
          require(metadata.get("category") == "csaf_vex", "unexpected CSAF category")
          require(metadata.get("csaf_version") == "2.0", "unexpected CSAF version")
          require(
              metadata.get("publisher", {}).get("name")
              == "Example Product Security",
              "unexpected CSAF publisher",
          )

          tracking = metadata["tracking"]
          require(tracking.get("id") == "EXAMPLE-VEX-2026-001", "unexpected CSAF tracking ID")
          require(tracking.get("status") == "draft", "unexpected CSAF status")
          require(tracking.get("version") == "1", "unexpected CSAF revision")
          require(
              tracking.get("revision_history", [{}])[0].get("number") == "1",
              "unexpected CSAF revision history",
          )

          products = document["product_tree"]["full_product_names"]
          require(
              isinstance(products, list) and bool(products),
              "CSAF products must be a nonempty list",
          )
          for product in products:
              purl = product["product_identification_helper"]["purl"]
              require(
                  purl.startswith("pkg:") and "@" in purl,
                  "CSAF product has no versioned package URL",
              )

          allowed_statuses = {
              "fixed",
              "known_affected",
              "known_not_affected",
              "under_investigation",
          }
          vulnerabilities = document.get("vulnerabilities")
          require(
              isinstance(vulnerabilities, list) and bool(vulnerabilities),
              "CSAF vulnerabilities must be a nonempty list",
          )
          for vulnerability in vulnerabilities:
              product_status = vulnerability.get("product_status")
              require(
                  isinstance(product_status, dict) and bool(product_status),
                  "CSAF vulnerability has no product status",
              )
              require(
                  set(product_status) <= allowed_statuses,
                  "CSAF vulnerability has an unsupported product status",
              )

          print(f"validated {path}")
          PY

      - name: Upload CSAF VEX
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: csaf-vex
          path: ${{ runner.temp }}/vexcalibur/example-vex-2026-001.json
          if-no-files-found: error
          retention-days: 1
```

Replace every `Example` publisher value with an identity approved to issue the
document. Use a namespace URL controlled by that publisher. Change `draft` to
`final` only after the assessment and publisher claims have completed their
review process.

Supported publisher categories are `coordinator`, `discoverer`, `other`,
`user`, and `vendor`. Vexcalibur does not accept `translator` because it creates
a new assessment rather than translating an existing document. Document status
can be `draft`, `interim`, or `final`.

The action runs the command-line interface (CLI) from a private temporary
directory. That is why every caller-owned input and output uses an absolute
path.

## Match the filename to the tracking ID

CSAF file output has a required basename. Vexcalibur lowercases the document
tracking ID, replaces each run outside `+`, `-`, `a-z`, and `0-9` with one
underscore, and appends `.json`.

`EXAMPLE-VEX-2026-001` therefore requires
`example-vex-2026-001.json`. Changing its directory is safe; changing that
basename is not.

## Supply status evidence

CSAF needs explicit evidence for several Vexcalibur analysis states:

| Analysis state | CSAF product status | Local finding requirement |
| --- | --- | --- |
| `resolved` | `fixed` | `fixed_version` must equal the version in the product package URL. |
| `exploitable` | `known_affected` | `action_statement` and `remediation_category` are both required. |
| `in_triage` | `under_investigation` | No extra evidence field. |
| `false_positive` | `known_not_affected` | `impact_statement` must explain why the product is not affected. |
| `not_affected` | `known_not_affected` | `impact_statement` must explain why the product is not affected. |

Accepted remediation categories are `mitigation`, `no_fix_planned`,
`none_available`, `vendor_fix`, and `workaround`. Vexcalibur does not infer one
from prose.

Both `false_positive` and `not_affected` become `known_not_affected`. The CSAF
document preserves the original Vexcalibur state in a note, but consumers that
only inspect product status cannot distinguish the two.

## Run and verify it

Commit the workflow to the repository's default branch. Commit the SBOM and
findings file only when the repository's visibility and access policy permit
it. Otherwise, add a step that retrieves them from an approved private source.
Open **Actions**, select **Generate CSAF VEX**, and choose **Run workflow**.

The run is successful when:

1. **Generate CSAF VEX** exits with status `0`.
2. **Validate CSAF VEX structure** prints a `validated` message.
3. The run summary contains a `csaf-vex` artifact with the expected filename.

The Python step catches a missing, truncated, or wrong-format result. It does
not replace full CSAF conformance validation. Vexcalibur's release tests run
generated output through the pinned OASIS schema and the mandatory CSAF test
suite described in the [CSAF output
reference](https://vexcalibur-dev.github.io/vexcalibur/reference/csaf-output.html#validation).

Download and review the artifact before distributing it. This workflow does
not sign, publish, revise, or convert a VEX document. If an assertion is wrong,
remove the artifact from downstream systems and correct the source assessment
before generating a replacement.

## Troubleshoot the workflow

| Symptom | Check |
| --- | --- |
| CSAF document or publisher options are required | Supply all five publisher-controlled metadata values shown in the workflow. |
| An exploitable finding requires an action or remediation category | Add both structured fields, or correct the analysis state. |
| A finding requires an impact statement | Add explicit impact evidence for `false_positive` or `not_affected`. |
| `fixed_version` does not match the product | Align the fixed version with the matched SBOM component. Do not weaken the assertion. |
| A product package URL must include a version | Add the component version to the SBOM or its package URL. |
| The output basename is rejected | Derive the filename from `--csaf-document-id`; do not choose an unrelated artifact name. |
| The action cannot find an input or output | Use `${{ github.workspace }}` for checked-in inputs and `${{ runner.temp }}` for temporary output. |
| The artifact step finds no file | Keep the `--output` value and upload path identical. |

The [action reference](../reference/action.md) covers argument conversion, path
rules, installation, and action-level exit codes.
