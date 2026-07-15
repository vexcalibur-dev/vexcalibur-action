from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
CURRENT_EXAMPLE_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "reference" / "action.md",
    ROOT / "docs" / "how-to" / "generate-vex-from-sbom.md",
    ROOT / "docs" / "how-to" / "generate-openvex-from-sbom.md",
    ROOT / "docs" / "how-to" / "generate-csaf-from-sbom.md",
)
PACKAGE_SPEC_PATTERN = re.compile(
    r"^\s*package-spec:\s*(vexcalibur==[^\s]+)\s*$",
    re.MULTILINE,
)


def released_ci_pair() -> tuple[str, str]:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    environment = workflow["env"]
    return (
        environment["VEXCALIBUR_RELEASE_ACTION_REF"],
        environment["VEXCALIBUR_RELEASE_PACKAGE_VERSION"],
    )


class DocumentationCompatibilityTests(unittest.TestCase):
    def test_readme_current_pair_tracks_released_package_ci(self) -> None:
        action_ref, package_version = released_ci_pair()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "The current pair is "
            f"`vexcalibur-action@{action_ref}` with "
            f"`vexcalibur=={package_version}`.",
            readme,
        )

    def test_current_package_examples_track_released_package_ci(self) -> None:
        _, package_version = released_ci_pair()
        expected_spec = f"vexcalibur=={package_version}"

        for path in CURRENT_EXAMPLE_PATHS:
            with self.subTest(path=path.relative_to(ROOT)):
                specs = set(PACKAGE_SPEC_PATTERN.findall(path.read_text(encoding="utf-8")))
                self.assertEqual(specs, {expected_spec})

    def test_compatibility_table_preserves_current_and_release_time_pairs(self) -> None:
        action_ref, package_version = released_ci_pair()
        compatibility = (ROOT / "docs" / "reference" / "compatibility.md").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            compatibility,
            rf"(?m)^\| `{re.escape(action_ref)}` \| "
            rf"`vexcalibur=={re.escape(package_version)}` \| .*"
            r"\| Current supported pair;",
        )
        self.assertRegex(
            compatibility,
            r"(?m)^\| `v0\.2\.1` \| `vexcalibur==0\.3\.0` \| .*"
            r"\| Original release-time pair;",
        )


if __name__ == "__main__":
    unittest.main()
