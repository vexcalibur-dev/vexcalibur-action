from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})$")
PIN_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)")


def load_workflow(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def step_named(job: dict[str, object], name: str) -> dict[str, object]:
    for step in job["steps"]:  # type: ignore[index]
        if step.get("name") == name:
            return step
    raise AssertionError(f"job does not contain step {name!r}")


def locked_packages(path: Path) -> dict[str, tuple[str, set[str]]]:
    packages: dict[str, tuple[str, set[str]]] = {}
    current_name: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        pin_match = PIN_PATTERN.match(line)
        if pin_match is not None:
            current_name = pin_match.group(1).lower().replace("_", "-")
            packages[current_name] = (pin_match.group(2), set())
            continue

        hash_match = HASH_PATTERN.search(line)
        if hash_match is not None:
            if current_name is None:
                raise AssertionError(f"hash without a package in {path}")
            packages[current_name][1].add(hash_match.group(1))

    return packages


class DependencyLockTests(unittest.TestCase):
    def assert_lock_has_no_alternate_sources(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertNotRegex(
            text,
            r"(?im)^\s*(?:-e\s|--editable\s|--extra-index-url\s|--index-url\s|"
            r"--find-links\s|https?://|file:)",
        )

    def test_release_lock_is_complete_and_hashed(self) -> None:
        path = ROOT / "requirements-release.txt"
        text = path.read_text(encoding="utf-8")
        packages = locked_packages(path)

        self.assert_lock_has_no_alternate_sources(path)
        self.assertIn("--only-binary :all:", text)
        self.assertEqual(
            set(packages),
            {
                "certifi",
                "charset-normalizer",
                "detect-secrets",
                "idna",
                "pyyaml",
                "requests",
                "urllib3",
            },
        )
        for name, (version, hashes) in packages.items():
            with self.subTest(package=name):
                self.assertRegex(version, r"^[A-Za-z0-9][A-Za-z0-9.!+_-]*$")
                self.assertTrue(hashes, f"{name} has no allowed distribution hash")

    def test_development_lock_extends_the_release_lock(self) -> None:
        self.assert_lock_has_no_alternate_sources(ROOT / "requirements-dev.txt")
        release_packages = locked_packages(ROOT / "requirements-release.txt")
        development_packages = locked_packages(ROOT / "requirements-dev.txt")

        self.assertEqual(set(development_packages), set(release_packages) | {"shellcheck-py"})
        for name, release_entry in release_packages.items():
            with self.subTest(package=name):
                self.assertEqual(development_packages[name], release_entry)

    def test_input_requirements_use_exact_direct_pins(self) -> None:
        for filename in ("requirements-release.in", "requirements-dev.in"):
            with self.subTest(filename=filename):
                for raw_line in (ROOT / filename).read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("-r "):
                        continue
                    self.assertIsNotNone(PIN_PATTERN.fullmatch(line))


class ReleaseWorkflowBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = load_workflow(RELEASE_WORKFLOW_PATH)
        cls.jobs = cls.workflow["jobs"]

    def test_notes_use_three_separate_runners(self) -> None:
        generator = self.jobs["generate-release-notes"]
        scanner = self.jobs["scan-release-notes"]
        publisher = self.jobs["publish-release"]

        self.assertEqual(generator["runs-on"], "ubuntu-latest")
        self.assertEqual(scanner["runs-on"], "ubuntu-latest")
        self.assertEqual(publisher["runs-on"], "ubuntu-latest")
        self.assertIn("generate-release-notes", scanner["needs"])
        self.assertIn("scan-release-notes", publisher["needs"])

    def test_scanner_cannot_persist_into_publisher(self) -> None:
        generator_text = yaml.safe_dump(self.jobs["generate-release-notes"])
        scanner_text = yaml.safe_dump(self.jobs["scan-release-notes"])
        publisher_text = yaml.safe_dump(self.jobs["publish-release"])

        self.assertNotIn("pip install", generator_text)
        self.assertNotIn("detect-secrets", generator_text)
        self.assertNotIn("create-github-app-token", scanner_text)
        self.assertNotIn("GH_TOKEN", scanner_text)
        self.assertNotIn("actions/cache", scanner_text)

        for forbidden in (
            "actions/cache",
            "actions/setup-python",
            "detect-secrets",
            "pip install",
            "requirements-release.txt",
            "GITHUB_PATH",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, publisher_text)

    def test_publication_token_is_minted_only_after_digest_verification(self) -> None:
        publisher = self.jobs["publish-release"]
        publisher_steps = publisher["steps"]
        token_indexes = [
            index
            for index, step in enumerate(publisher_steps)
            if step.get("id") == "publication-token"
        ]
        self.assertEqual(token_indexes, [4])
        self.assertEqual(
            publisher_steps[token_indexes[0]]["uses"],
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
        )
        self.assertEqual(
            publisher_steps[token_indexes[0]]["with"]["permission-contents"],
            "write",
        )
        self.assertEqual(
            publisher_steps[token_indexes[0] - 1]["name"],
            "Verify scanned release-note digest",
        )

        for job_name, job in self.jobs.items():
            if job_name == "publish-release":
                continue
            for step in job["steps"]:
                self.assertNotEqual(step.get("id"), "publication-token")

    def test_artifact_digest_is_verified_at_each_boundary(self) -> None:
        generator = self.jobs["generate-release-notes"]
        scanner = self.jobs["scan-release-notes"]
        publisher = self.jobs["publish-release"]

        self.assertEqual(
            generator["outputs"]["notes_sha256"],
            "${{ steps.notes-digest.outputs.sha256 }}",
        )
        self.assertIn("sha256sum", step_named(generator, "Record release-note digest")["run"])
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            step_named(generator, "Upload generated release notes")["uses"],
        )
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            step_named(scanner, "Download generated release notes")["uses"],
        )

        generated_verifier = step_named(scanner, "Verify generated release-note digest")
        self.assertEqual(
            generated_verifier["env"]["EXPECTED_SHA256"],
            "${{ needs.generate-release-notes.outputs.notes_sha256 }}",
        )
        self.assertIn("sha256sum", generated_verifier["run"])
        self.assertEqual(
            scanner["outputs"]["notes_sha256"],
            "${{ steps.scanned-digest.outputs.sha256 }}",
        )
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            step_named(scanner, "Upload scanned release notes")["uses"],
        )

        scanned_verifier = step_named(publisher, "Verify scanned release-note digest")
        self.assertEqual(
            scanned_verifier["env"]["EXPECTED_SHA256"],
            "${{ needs.scan-release-notes.outputs.notes_sha256 }}",
        )
        self.assertIn("sha256sum", scanned_verifier["run"])
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            step_named(publisher, "Download scanned release notes")["uses"],
        )

    def test_requirement_installs_are_hash_checked_and_wheel_only(self) -> None:
        workflows = (load_workflow(CI_WORKFLOW_PATH), self.workflow)
        checked = 0
        for workflow in workflows:
            for job in workflow["jobs"].values():
                for step in job["steps"]:
                    run = step.get("run", "")
                    if "requirements-" not in run or ".txt" not in run:
                        continue
                    checked += 1
                    self.assertIn("--only-binary=:all:", run)
                    self.assertIn("--require-hashes", run)
        self.assertEqual(checked, 2)
        self.assertIn(
            "-r requirements-release.txt",
            step_named(self.jobs["scan-release-notes"], "Install release note scanner")["run"],
        )

        ci_jobs = load_workflow(CI_WORKFLOW_PATH)["jobs"]
        self.assertIn(
            "-r requirements-dev.txt",
            step_named(ci_jobs["quality"], "Install development dependencies")["run"],
        )

    def test_release_actions_are_pinned_to_full_commits(self) -> None:
        for job_name, job in self.jobs.items():
            for step in job["steps"]:
                uses = step.get("uses")
                if uses is None:
                    continue
                with self.subTest(job=job_name, action=uses):
                    self.assertRegex(uses, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
