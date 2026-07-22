"""Shared Git fixtures for release-tooling tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_state import TagMetadata, read_manifest  # noqa: E402


GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("git is required to test release state")


def git(repo: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        [GIT, *arguments],
        cwd=repo,
        check=check,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def configure_git(repo: Path) -> None:
    git(repo, "config", "user.name", "Release Test")
    git(repo, "config", "user.email", "release-test@example.invalid")


def commit(repo: Path, message: str, filename: str = "change.txt") -> str:
    path = repo / filename
    path.write_text(f"{message}\n", encoding="utf-8")
    git(repo, "add", filename)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def annotated_tag(
    repo: Path, name: str, target: str = "HEAD", message: str = ""
) -> None:
    git(repo, "tag", "-a", name, target, "-m", message or f"Release {name}")


def canonical_tag(repo: Path, name: str, target: str = "HEAD") -> None:
    commit_sha = git(repo, "rev-parse", f"{target}^{{commit}}")
    manifest = read_manifest(repo / "action-compatibility.json")
    metadata = TagMetadata(name, commit_sha, manifest.sha256, "1", "b" * 64)
    message_path = repo / "tag-message.txt"
    message_path.write_text(metadata.render() + "\n", encoding="utf-8")
    git(repo, "tag", "-a", name, target, "-F", str(message_path))
    message_path.unlink()


def raw_tag(
    repo: Path,
    *,
    ref_name: str,
    object_sha: str,
    object_type: str,
    embedded_tag: str,
    message: str,
) -> str:
    payload = (
        f"object {object_sha}\n"
        f"type {object_type}\n"
        f"tag {embedded_tag}\n"
        "tagger Release Test <release-test@example.invalid> 0 +0000\n\n"
        f"{message}\n"
    )
    result = subprocess.run(
        [GIT, "hash-object", "-t", "tag", "-w", "--stdin"],
        cwd=repo,
        input=payload,
        check=True,
        text=True,
        capture_output=True,
    )
    object_id = result.stdout.strip()
    git(repo, "update-ref", f"refs/tags/{ref_name}", object_id)
    return object_id


def write_manifest(repo: Path) -> None:
    (repo / "action-compatibility.json").write_text(
        json.dumps(
            {
                "python_versions": ["3.10", "3.14"],
                "vexcalibur_package": "vexcalibur==1.2.3",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_action(repo: Path, *, inputs: str = "{}") -> None:
    (repo / "action.yml").write_text(
        f"inputs: {inputs}\noutputs: {{}}\nruns:\n  using: composite\n  steps: []\n",
        encoding="utf-8",
    )


class GitRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        configure_git(self.repo)
        write_manifest(self.repo)
        write_action(self.repo)
        self.initial_commit = commit(self.repo, "chore: initialize", "README.md")
        git(self.repo, "add", "action-compatibility.json", "action.yml")
        git(self.repo, "commit", "--amend", "--no-edit")
        self.initial_commit = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()
