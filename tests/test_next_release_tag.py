from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "next-release-tag.sh"
GIT = shutil.which("git")
BASH = shutil.which("bash")

if GIT is None:
    raise RuntimeError("git is required to test release version calculation")
if BASH is None:
    raise RuntimeError("bash is required to test release version calculation")


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [GIT, *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def commit(repo: Path, message: str, filename: str = "change.txt") -> None:
    path = repo / filename
    path.write_text(f"{message}\n", encoding="utf-8")
    run_git(repo, "add", filename)
    run_git(repo, "commit", "-m", message)


def run_release_script(repo: Path, version: str = "") -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GITHUB_OUTPUT", None)
    result = subprocess.run(
        [BASH, "next-release-tag.sh", version],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def run_release_script_failure(repo: Path, version: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GITHUB_OUTPUT", None)
    return subprocess.run(
        [BASH, "next-release-tag.sh", version],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


class NextReleaseTagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name) / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-b", "main")
        run_git(self.repo, "config", "user.name", "Release Test")
        run_git(self.repo, "config", "user.email", "release-test@example.invalid")
        shutil.copy2(SCRIPT, self.repo / "next-release-tag.sh")
        commit(self.repo, "chore: initialize", "README.md")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_initial_release_defaults_to_0_1_0(self) -> None:
        self.assertEqual(
            run_release_script(self.repo),
            {
                "skip": "false",
                "tag": "v0.1.0",
                "version": "0.1.0",
                "previous_tag": "",
                "bump": "initial",
            },
        )

    def test_feature_after_tag_bumps_minor(self) -> None:
        run_git(self.repo, "tag", "-a", "v0.1.0", "-m", "Release v0.1.0")
        commit(self.repo, "feat: add release automation")

        self.assertEqual(
            run_release_script(self.repo),
            {
                "skip": "false",
                "tag": "v0.2.0",
                "version": "0.2.0",
                "previous_tag": "v0.1.0",
                "bump": "minor",
            },
        )

    def test_docs_only_change_after_tag_skips_release(self) -> None:
        run_git(self.repo, "tag", "-a", "v0.1.0", "-m", "Release v0.1.0")
        commit(self.repo, "docs: update usage notes")

        self.assertEqual(
            run_release_script(self.repo),
            {
                "skip": "true",
                "tag": "",
                "version": "",
                "previous_tag": "v0.1.0",
                "bump": "skip",
            },
        )

    def test_manual_release_must_exceed_latest_tag(self) -> None:
        run_git(self.repo, "tag", "-a", "v0.2.0", "-m", "Release v0.2.0")
        commit(self.repo, "fix: patch after second release")

        result = run_release_script_failure(self.repo, "0.1.9")

        self.assertEqual(result.returncode, 1)
        self.assertIn("manual version 0.1.9 must be greater than base version 0.2.0", result.stderr)


if __name__ == "__main__":
    unittest.main()
