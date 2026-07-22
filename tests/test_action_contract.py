from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from action_contract import (  # noqa: E402
    ActionContract,
    ActionContractError,
    compare_action_contracts,
    parse_action_contract,
)
from release_metadata import (  # noqa: E402
    classify_compatibility_change,
    parse_manifest,
)


def contract(
    *,
    inputs: str = "{}",
    outputs: str = "{}",
    runs_using: str = "composite",
) -> ActionContract:
    raw = (
        f"inputs: {inputs}\noutputs: {outputs}\nruns:\n  using: {runs_using}\n"
    ).encode()
    return parse_action_contract(raw, source="test action")


class ActionContractTests(unittest.TestCase):
    def test_compatibility_changes_use_semantic_bumps(self) -> None:
        released = parse_manifest(
            b'{"python_versions":["3.10","3.14"],'
            b'"vexcalibur_package":"vexcalibur==0.3.0"}\n'
        )
        formatting_only = parse_manifest(
            b'{\n  "vexcalibur_package": "vexcalibur==0.3.0",\n'
            b'  "python_versions": ["3.10", "3.14"]\n}\n'
        )
        added_python = parse_manifest(
            b'{"python_versions":["3.10","3.13","3.14"],'
            b'"vexcalibur_package":"vexcalibur==0.3.0"}\n'
        )
        removed_python = parse_manifest(
            b'{"python_versions":["3.14"],"vexcalibur_package":"vexcalibur==0.3.1"}\n'
        )

        self.assertEqual(
            classify_compatibility_change(released, formatting_only).required_bump,
            "skip",
        )
        self.assertEqual(
            classify_compatibility_change(released, added_python).required_bump,
            "minor",
        )
        self.assertEqual(
            classify_compatibility_change(released, removed_python).required_bump,
            "major",
        )

    def test_description_changes_do_not_change_the_contract(self) -> None:
        released = parse_action_contract(
            b"""
inputs:
  query:
    description: Old words
    required: false
    default: value
outputs: {}
runs:
  using: composite
""",
            source="released",
        )
        current = parse_action_contract(
            b"""
inputs:
  query:
    description: Better words
    required: false
    default: value
outputs: {}
runs:
  using: composite
""",
            source="current",
        )

        self.assertEqual(
            compare_action_contracts(released, current).required_bump,
            "skip",
        )

    def test_compatible_additions_require_a_minor_bump(self) -> None:
        released = contract()
        for current in (
            contract(inputs="{query: {required: false, default: value}}"),
            contract(inputs="{query: {required: true, default: value}}"),
            contract(outputs="{result: {value: '${{ steps.run.outputs.value }}'}}"),
        ):
            with self.subTest(current=current):
                self.assertEqual(
                    compare_action_contracts(released, current).required_bump,
                    "minor",
                )

    def test_deprecation_changes_require_a_release(self) -> None:
        released = contract(inputs="{query: {required: false}}")
        deprecated = contract(
            inputs=(
                "{query: {required: false, "
                "deprecationMessage: 'Use replacement instead'}}"
            )
        )
        revised = contract(
            inputs=(
                "{query: {required: false, "
                "deprecationMessage: 'Use the replacement input'}}"
            )
        )

        self.assertEqual(
            compare_action_contracts(released, deprecated).required_bump,
            "minor",
        )
        self.assertEqual(
            compare_action_contracts(deprecated, revised).required_bump,
            "patch",
        )

    def test_breaking_changes_require_a_major_bump(self) -> None:
        base_input = "{query: {required: false, default: old}}"
        released = contract(
            inputs=base_input,
            outputs="{result: {value: old}}",
        )
        breaking_contracts = (
            contract(outputs="{result: {value: old}}"),
            contract(inputs="{query: {required: false, default: new}}"),
            contract(inputs=base_input),
            contract(inputs=base_input, outputs="{result: {value: new}}"),
            contract(
                inputs=base_input,
                outputs="{result: {value: old}}",
                runs_using="node24",
            ),
            contract(
                inputs=(
                    "{query: {required: false, default: old}, token: {required: true}}"
                ),
                outputs="{result: {value: old}}",
            ),
        )
        for current in breaking_contracts:
            with self.subTest(current=current):
                self.assertEqual(
                    compare_action_contracts(released, current).required_bump,
                    "major",
                )

    def test_malformed_and_duplicate_metadata_is_rejected(self) -> None:
        invalid_documents = (
            b"inputs: []\nruns: {using: composite}\n",
            b'inputs: {query: {required: "yes"}}\nruns: {using: composite}\n',
            b"inputs: {}\nruns: {}\n",
            b"inputs: {}\ninputs: {}\nruns: {using: composite}\n",
            b"? [one, two]\n: value\nruns: {using: composite}\n",
            (b"inputs: {query: {deprecationMessage: []}}\nruns: {using: composite}\n"),
            b"inputs: {query: {default: true}}\nruns: {using: composite}\n",
            b"outputs: {result: {value: 1}}\nruns: {using: composite}\n",
        )
        for document in invalid_documents:
            with (
                self.subTest(document=document),
                self.assertRaises(ActionContractError),
            ):
                parse_action_contract(document, source="invalid")

    def test_manifest_change_requires_release_producing_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repository,
                check=True,
            )
            action = b"inputs: {}\noutputs: {}\nruns: {using: composite}\n"
            (repository / "action.yml").write_bytes(action)
            (repository / "action-compatibility.json").write_text(
                '{"python_versions":["3.10"],'
                '"vexcalibur_package":"vexcalibur==0.3.0"}\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "feat: initial contract"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "tag", "-am", "legacy", "v0.1.0"],
                cwd=repository,
                check=True,
            )
            (repository / "action-compatibility.json").write_text(
                '{"python_versions":["3.10"],'
                '"vexcalibur_package":"vexcalibur==0.3.1"}\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "docs: update declaration"],
                cwd=repository,
                check=True,
            )

            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/check-action-contract.py")],
                cwd=repository,
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release metadata requires a patch bump", result.stderr)
        self.assertIn("package changed from", result.stderr)

    def test_ci_runs_the_versionless_contract_guard(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("scripts/check-action-contract.py", workflow)
        self.assertNotIn("VEXCALIBUR_RELEASE_ACTION_REF", workflow)


if __name__ == "__main__":
    unittest.main()
