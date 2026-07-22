"""Shared validation and Git primitives for action releases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Literal, NoReturn


MANIFEST_PATH = "action-compatibility.json"
CURRENT_NOTES_FORMAT = "1"
SUPPORTED_NOTES_FORMATS = frozenset({CURRENT_NOTES_FORMAT})
MAX_VERSION_COMPONENT = 999_999
SEMVER_TAG_PATTERN = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
Bump = Literal["skip", "patch", "minor", "major"]
VersionBump = Literal["patch", "minor", "major"]
BUMP_RANK: dict[Bump, int] = {"skip": 0, "patch": 1, "minor": 2, "major": 3}


class ReleaseStateError(ValueError):
    """Raised when release state violates an invariant."""


class LegacyReleaseError(ReleaseStateError):
    """Raised when a release predates canonical recovery metadata."""


def fail(message: str) -> NoReturn:
    """Raise a release-state error with a stable user-facing message."""
    raise ReleaseStateError(message)


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """A bounded semantic version represented by a release tag."""

    major: int
    minor: int
    patch: int

    @classmethod
    def from_tag(cls, tag: str) -> SemanticVersion:
        match = SEMVER_TAG_PATTERN.fullmatch(tag)
        if match is None:
            fail(f"tag {tag!r} must be vMAJOR.MINOR.PATCH without leading zeros")
        if any(len(component) > 6 for component in match.groups()):
            fail(
                f"tag components must be less than or equal to {MAX_VERSION_COMPONENT}"
            )
        components = tuple(int(component) for component in match.groups())
        if any(component > MAX_VERSION_COMPONENT for component in components):
            fail(
                f"tag components must be less than or equal to {MAX_VERSION_COMPONENT}"
            )
        return cls(*components)

    @property
    def tag(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def bump(self, kind: VersionBump) -> SemanticVersion:
        if kind == "major":
            candidate = SemanticVersion(self.major + 1, 0, 0)
        elif kind == "minor":
            candidate = SemanticVersion(self.major, self.minor + 1, 0)
        elif kind == "patch":
            candidate = SemanticVersion(self.major, self.minor, self.patch + 1)
        else:
            fail(f"cannot calculate a tag for bump {kind!r}")
        SemanticVersion.from_tag(candidate.tag)
        return candidate


def require_commit(commit: str) -> None:
    if COMMIT_PATTERN.fullmatch(commit) is None:
        fail(f"commit {commit!r} must be a full lowercase Git SHA")


def require_sha256(digest: str) -> None:
    if SHA256_PATTERN.fullmatch(digest) is None:
        fail(f"digest {digest!r} must be a lowercase SHA-256 value")


def require_notes_format(notes_format: str) -> None:
    if notes_format not in SUPPORTED_NOTES_FORMATS:
        fail(f"unsupported release-note format {notes_format!r}")


def run_git(
    *arguments: str,
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git without invoking a shell."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        fail(f"git {' '.join(arguments)} failed: {detail}")
    return result


def run_git_bytes(
    *arguments: str,
    cwd: Path | None = None,
) -> bytes:
    """Read exact Git output bytes without newline translation."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip() or "unknown error"
        fail(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def read_regular_blob_at_commit(
    commit: str,
    path: str,
    *,
    cwd: Path | None = None,
) -> bytes | None:
    """Read a tracked regular file without following a worktree symlink."""
    require_commit(commit)
    if not path or path.startswith("/") or "\0" in path:
        fail(f"repository path {path!r} is invalid")
    if git_output("cat-file", "-t", commit, cwd=cwd) != "commit":
        fail(f"release object {commit} is not a commit")
    entry = run_git_bytes("ls-tree", "-z", commit, "--", path, cwd=cwd)
    if not entry:
        return None
    if not entry.endswith(b"\0"):
        fail(f"repository path {path!r} has malformed tree metadata")
    try:
        header, entry_path = entry[:-1].split(b"\t", 1)
        mode, object_type, object_id = header.split(b" ")
    except ValueError:
        fail(f"repository path {path!r} has malformed tree metadata")
    if entry_path != path.encode():
        fail(f"repository path {path!r} resolved to an unexpected tree entry")
    if mode not in {b"100644", b"100755"} or object_type != b"blob":
        fail(f"repository path {path!r} must be a regular file")
    try:
        object_sha = object_id.decode("ascii")
    except UnicodeDecodeError:
        fail(f"repository path {path!r} has a malformed blob identity")
    require_commit(object_sha)
    return run_git_bytes("cat-file", "blob", object_sha, cwd=cwd)


def git_output(*arguments: str, cwd: Path | None = None) -> str:
    return run_git(*arguments, cwd=cwd).stdout.strip()


def git_is_ancestor(ancestor: str, descendant: str, *, cwd: Path | None = None) -> bool:
    """Return Git's ancestry predicate while preserving genuine failures."""
    result = run_git(
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
        cwd=cwd,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
    fail(f"git merge-base --is-ancestor failed: {detail}")


def tag_commit(reference: str, *, cwd: Path | None = None) -> str:
    commit = git_output("rev-parse", "--verify", f"{reference}^{{commit}}", cwd=cwd)
    require_commit(commit)
    return commit


def read_tag_object(
    reference: str, *, cwd: Path | None = None
) -> tuple[dict[str, str], str]:
    if git_output("cat-file", "-t", reference, cwd=cwd) != "tag":
        fail(f"release reference {reference} must be an annotated tag")
    tag_object = run_git_bytes("cat-file", "tag", reference, cwd=cwd)
    separator = tag_object.find(b"\n\n")
    if separator < 0:
        fail(f"release reference {reference} has a malformed annotated tag object")
    try:
        header_text = tag_object[:separator].decode("utf-8")
        message = tag_object[separator + 2 :].decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"release reference {reference} is not valid UTF-8: {exc}")

    header_lines = header_text.splitlines()
    if len(header_lines) != 4 or not header_lines[3].startswith("tagger "):
        fail(f"release reference {reference} has noncanonical annotated-tag headers")
    headers: dict[str, str] = {}
    for key, line in zip(("object", "type", "tag"), header_lines[:3], strict=True):
        prefix = f"{key} "
        if not line.startswith(prefix) or not line[len(prefix) :]:
            fail(
                f"release reference {reference} has noncanonical annotated-tag headers"
            )
        headers[key] = line[len(prefix) :]
    return headers, message


def require_tag_object_identity(
    reference: str,
    *,
    expected_tag: str,
    expected_commit: str,
    cwd: Path | None = None,
) -> str:
    headers, message = read_tag_object(reference, cwd=cwd)
    if (
        headers["object"] != expected_commit
        or headers["type"] != "commit"
        or headers["tag"] != expected_tag
    ):
        fail(f"release reference {reference} has conflicting annotated-tag headers")
    if git_output("cat-file", "-t", expected_commit, cwd=cwd) != "commit":
        fail(f"release commit {expected_commit} is not a commit object")
    return message
