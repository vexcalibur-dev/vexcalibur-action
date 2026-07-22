from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CURRENT_EXAMPLE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "how-to" / "generate-vex-from-sbom.md",
    ROOT / "docs" / "how-to" / "generate-openvex-from-sbom.md",
    ROOT / "docs" / "how-to" / "generate-csaf-from-sbom.md",
)
POLICY_PATHS = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    *sorted((ROOT / "docs").glob("**/*.md")),
)
ACTION_REF_PATTERN = re.compile(
    r"vexcalibur-dev/vexcalibur-action@(?:v[0-9]+\.[0-9]+\.[0-9]+|[0-9a-f]{40})"
)
PACKAGE_SPEC_PATTERN = re.compile(r"^\s*package-spec:\s*([^\s]+)\s*$", re.MULTILINE)
FENCED_BLOCK_PATTERN = re.compile(
    r"```(?P<language>yaml|bash)\n(?P<body>.*?)```", re.DOTALL
)


class DocumentationCompatibilityTests(unittest.TestCase):
    def test_examples_use_runtime_release_placeholders(self) -> None:
        for path in CURRENT_EXAMPLE_PATHS:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    "vexcalibur-dev/vexcalibur-action@REPLACE_WITH_ACTION_SHA",
                    text,
                )
                self.assertEqual(
                    set(PACKAGE_SPEC_PATTERN.findall(text)),
                    {"REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC"},
                )

    def test_docs_do_not_commit_a_concrete_action_release_identity(self) -> None:
        for path in POLICY_PATHS:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(ACTION_REF_PATTERN.search(text))
                self.assertNotIn("VEXCALIBUR_RELEASE_ACTION_REF", text)
                self.assertNotIn("VEXCALIBUR_RELEASE_PACKAGE_VERSION", text)

    def test_compatibility_reference_resolves_metadata_from_a_tag(self) -> None:
        text = (ROOT / "docs" / "reference" / "compatibility.md").read_text(
            encoding="utf-8"
        )
        prose = " ".join(text.split())

        self.assertNotIn("releases/latest", text)
        self.assertIn("git ls-remote --refs --tags", text)
        self.assertIn("no strict semantic release tag found", text)
        self.assertIn('"refs/tags/${ACTION_TAG}^{}"', text)
        self.assertIn(
            "${ACTION_SHA}/action-compatibility.json",
            text,
        )
        self.assertIn("points to one exact commit", prose)
        self.assertIn("don't need a GitHub token", prose)

    def test_release_runbook_forbids_tag_mutation_and_source_versions(self) -> None:
        text = (ROOT / "docs" / "how-to" / "release-action.md").read_text(
            encoding="utf-8"
        )
        prose = " ".join(text.split())

        self.assertIn("Release versions are not\nstored in source files", text)
        self.assertIn("tag refspec is create-only", prose.lower())
        self.assertIn("no force, update, or delete path", prose.lower())
        self.assertIn(
            "Do not add metadata by moving, deleting, or recreating",
            prose,
        )
        self.assertIn("workflow reads the immutable tag target", prose.lower())
        self.assertIn(".enforced_by_owner", prose)
        self.assertIn("Mutable aliases are branches", text)
        self.assertIn("legacy github release", prose.lower())
        self.assertIn("RELEASE_POLICY_ATTESTATION", text)
        self.assertIn("attest-rulesets", text)
        self.assertIn("still permits title and body edits", prose)
        self.assertNotIn("outputs.skip", text)
        self.assertNotRegex(text, r"RELEASE_TAG=v[0-9]+\.[0-9]+\.[0-9]+")

    def test_documented_yaml_and_bash_blocks_parse(self) -> None:
        for path in sorted((ROOT / "docs").glob("**/*.md")):
            text = path.read_text(encoding="utf-8")
            for index, match in enumerate(FENCED_BLOCK_PATTERN.finditer(text), start=1):
                language = match.group("language")
                body = match.group("body")
                with self.subTest(
                    path=path.relative_to(ROOT), block=index, language=language
                ):
                    if language == "yaml":
                        self.assertIsNotNone(yaml.safe_load(body))
                    else:
                        result = subprocess.run(
                            ["bash", "-n"],
                            input=body,
                            text=True,
                            capture_output=True,
                            check=False,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generation_guides_redact_failures_and_limit_artifacts(self) -> None:
        for path in CURRENT_EXAMPLE_PATHS[1:]:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("assert ", text)
                self.assertIn("retention-days: 1", text)
                self.assertIn("Don't commit them to a public repository", text)


if __name__ == "__main__":
    unittest.main()
