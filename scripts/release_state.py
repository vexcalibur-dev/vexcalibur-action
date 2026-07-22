"""Canonical release planner and stable release-tooling facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal

from release_common import (
    BUMP_RANK,
    Bump,
    CURRENT_NOTES_FORMAT,
    LegacyReleaseError,
    ReleaseStateError,
    SemanticVersion,
    fail,
    git_output,
    read_regular_blob_at_commit,
    require_commit,
    require_notes_format,
    require_sha256,
    run_git_bytes,
)
from release_metadata import (
    CompatibilityChange,
    ReleaseMetadata,
    SelectedPackageArtifact,
    TagMetadata,
    classify_compatibility_change,
    parse_manifest,
    parse_json,
    parse_release_json,
    parse_release_metadata,
    read_manifest,
    read_manifest_at_commit,
    read_tag_metadata,
    render_release_notes,
    verify_tag_reference,
    verify_selected_pypi_artifact,
)
from release_tags import (
    ReleaseTag,
    reconcile_remote_tag,
    release_tags,
    tag_graph_sha256,
)


PlanBump = Literal["skip", "manual", "patch", "minor", "major", "existing"]

__all__ = [
    "ReleaseMetadata",
    "ReleasePlan",
    "SelectedPackageArtifact",
    "ReleaseStateError",
    "TagMetadata",
    "classify_commit",
    "classify_range",
    "classify_release_requirement",
    "parse_manifest",
    "parse_json",
    "parse_release_json",
    "parse_release_metadata",
    "plan_release",
    "read_manifest",
    "read_manifest_at_commit",
    "reconcile_remote_tag",
    "release_tags",
    "render_release_notes",
    "run_git_bytes",
    "verify_github_release",
    "verify_selected_pypi_artifact",
    "verify_tag_reference",
    "write_github_outputs",
]


BREAKING_SUBJECT_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\([^)]+\))?!:", re.IGNORECASE
)
BREAKING_FOOTER_PATTERN = re.compile(
    r"^(?:BREAKING CHANGE|BREAKING-CHANGE):[ \t]+\S.*$",
    re.IGNORECASE | re.MULTILINE,
)
FOOTER_ENTRY_PATTERN = re.compile(
    r"^(?:BREAKING CHANGE|[A-Za-z0-9-]+)(?::[ \t]+|[ \t]+#)\S.*$",
    re.IGNORECASE,
)
FEATURE_PATTERN = re.compile(r"^feat(?:\([^)]+\))?:", re.IGNORECASE)
PATCH_PATTERN = re.compile(
    r"^(?:(?:fix|perf|refactor|deps|revert)(?:\([^)]+\))?:"
    r'|(?:build|chore)\(deps\):|Revert ")',
    re.IGNORECASE,
)
SKIP_PATTERN = re.compile(r"\[(?:skip release|release skip)\]", re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseRequirement:
    """Minimum semantic bump required by the public release metadata."""

    required_bump: Bump
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReleasePlan:
    """The release operation derived from immutable tags and commit history."""

    operation: Literal["skip", "publish", "recover"]
    tag: str
    previous_tag: str
    bump: PlanBump
    commit: str
    notes_format: str
    expected_notes_sha256: str
    expected_tag_graph_sha256: str
    make_latest: bool

    def __post_init__(self) -> None:
        require_commit(self.commit)
        require_notes_format(self.notes_format)
        require_sha256(self.expected_tag_graph_sha256)
        if type(self.make_latest) is not bool:
            fail("make_latest must be a boolean")
        if self.previous_tag:
            SemanticVersion.from_tag(self.previous_tag)

        if self.operation == "skip":
            if (
                self.tag
                or self.bump != "skip"
                or self.expected_notes_sha256
                or self.make_latest
            ):
                fail("a skipped release plan contains publication metadata")
            return

        SemanticVersion.from_tag(self.tag)
        if self.operation == "publish":
            if self.bump not in {"manual", "patch", "minor", "major"}:
                fail("a publication plan has an invalid version bump")
            if self.expected_notes_sha256:
                fail("a new publication cannot have a preexisting notes digest")
            if not self.make_latest:
                fail("a new publication must become the latest release")
            return

        if self.operation != "recover":
            fail(f"unknown release operation {self.operation!r}")
        if self.bump != "existing":
            fail("a recovery plan must describe an existing release")
        require_sha256(self.expected_notes_sha256)

    def github_outputs(self) -> dict[str, str]:
        return {
            "operation": self.operation,
            "tag": self.tag,
            "previous_tag": self.previous_tag,
            "bump": self.bump,
            "sha": self.commit,
            "notes_format": self.notes_format,
            "expected_notes_sha256": self.expected_notes_sha256,
            "expected_tag_graph_sha256": self.expected_tag_graph_sha256,
            "make_latest": str(self.make_latest).lower(),
        }


def final_footer_paragraph(message: str) -> str:
    """Return only the final Conventional Commit footer paragraph."""
    paragraphs = re.split(r"\n[ \t]*\n", message.strip())
    if len(paragraphs) <= 1:
        return ""
    footer = paragraphs[-1]
    first_line = footer.splitlines()[0] if footer.splitlines() else ""
    return footer if FOOTER_ENTRY_PATTERN.fullmatch(first_line) else ""


def classify_commit(message: str) -> Bump:
    if SKIP_PATTERN.search(message):
        return "skip"
    subject = message.splitlines()[0] if message.splitlines() else ""
    footer = final_footer_paragraph(message)
    if BREAKING_SUBJECT_PATTERN.match(subject) or BREAKING_FOOTER_PATTERN.search(
        footer
    ):
        return "major"
    if FEATURE_PATTERN.match(subject):
        return "minor"
    if PATCH_PATTERN.match(subject):
        return "patch"
    return "skip"


def classify_range(revision_range: str, *, cwd: Path | None = None) -> Bump:
    required: Bump = "skip"
    commits = git_output("rev-list", "--reverse", revision_range, cwd=cwd).splitlines()
    for commit in commits:
        message = git_output("show", "-s", "--format=%B", commit, cwd=cwd)
        classification = classify_commit(message)
        if BUMP_RANK[classification] > BUMP_RANK[required]:
            required = classification
        if required == "major":
            break
    return required


def classify_release_requirement(
    released_commit: str,
    current_commit: str,
    *,
    cwd: Path | None = None,
) -> ReleaseRequirement:
    """Compare public contracts against one exact released commit."""
    from action_contract import (
        ActionContractError,
        compare_action_contracts,
        parse_action_contract,
    )

    require_commit(released_commit)
    require_commit(current_commit)
    released_action = read_regular_blob_at_commit(
        released_commit, "action.yml", cwd=cwd
    )
    current_action = read_regular_blob_at_commit(current_commit, "action.yml", cwd=cwd)
    if released_action is None or current_action is None:
        fail("action.yml must be a tracked regular file")
    try:
        action_change = compare_action_contracts(
            parse_action_contract(
                released_action,
                source=f"{released_commit}:action.yml",
            ),
            parse_action_contract(
                current_action,
                source=f"{current_commit}:action.yml",
            ),
        )
    except ActionContractError as exc:
        fail(str(exc))

    released_manifest = None
    released_manifest_bytes = read_regular_blob_at_commit(
        released_commit, "action-compatibility.json", cwd=cwd
    )
    if released_manifest_bytes is not None:
        released_manifest = parse_manifest(
            released_manifest_bytes,
            source=f"{released_commit}:action-compatibility.json",
        )
    current_manifest_bytes = read_regular_blob_at_commit(
        current_commit, "action-compatibility.json", cwd=cwd
    )
    if current_manifest_bytes is None:
        fail("action-compatibility.json must be a tracked regular file")
    compatibility_change: CompatibilityChange = classify_compatibility_change(
        released_manifest,
        parse_manifest(
            current_manifest_bytes,
            source=f"{current_commit}:action-compatibility.json",
        ),
    )

    changes = (action_change, compatibility_change)
    required_bump = max(
        (change.required_bump for change in changes), key=BUMP_RANK.__getitem__
    )
    return ReleaseRequirement(
        required_bump,
        tuple(reason for change in changes for reason in change.reasons),
    )


def recovery_plan(
    tag: ReleaseTag,
    tags: list[ReleaseTag],
    *,
    cwd: Path | None = None,
) -> ReleasePlan:
    try:
        metadata = read_tag_metadata(f"refs/tags/{tag.name}", cwd=cwd)
    except LegacyReleaseError:
        fail(
            f"release tag {tag.name} predates canonical release metadata; "
            "legacy releases cannot be recovered automatically"
        )
    manifest = read_manifest_at_commit(tag.commit, cwd=cwd)
    if metadata.tag != tag.name or metadata.commit != tag.commit:
        fail(f"release tag {tag.name} has conflicting canonical metadata")
    if metadata.compatibility_sha256 != manifest.sha256:
        fail(f"release tag {tag.name} has a conflicting compatibility digest")
    index = tags.index(tag)
    return ReleasePlan(
        "recover",
        tag.name,
        tags[index - 1].name if index else "",
        "existing",
        tag.commit,
        metadata.notes_format,
        metadata.notes_sha256,
        tag_graph_sha256(tags),
        tag == tags[-1],
    )


def plan_release(
    manual_tag: str = "", *, cwd: Path | None = None, head: str = "HEAD"
) -> ReleasePlan:
    """Derive a release without reading or writing any version file."""
    head_commit = git_output("rev-parse", "--verify", f"{head}^{{commit}}", cwd=cwd)
    require_commit(head_commit)
    tags = release_tags(cwd=cwd, head=head)
    by_name = {tag.name: tag for tag in tags}
    by_commit = {tag.commit: tag for tag in tags}

    if manual_tag:
        requested_version = SemanticVersion.from_tag(manual_tag)
        if manual_tag in by_name:
            return recovery_plan(by_name[manual_tag], tags, cwd=cwd)
    else:
        requested_version = None

    if head_commit in by_commit:
        tag = by_commit[head_commit]
        if manual_tag and manual_tag != tag.name:
            fail(
                f"commit {head_commit} already has release tag {tag.name}; "
                f"refusing to add {manual_tag}"
            )
        return recovery_plan(tag, tags, cwd=cwd)

    latest = tags[-1] if tags else None
    if latest is None:
        if requested_version is None:
            fail("the first release requires an explicit vMAJOR.MINOR.PATCH tag")
        required_bump = "skip"
    else:
        history_bump = classify_range(f"{latest.name}..{head}", cwd=cwd)
        metadata_bump = classify_release_requirement(
            latest.commit,
            head_commit,
            cwd=cwd,
        ).required_bump
        required_bump = max((history_bump, metadata_bump), key=BUMP_RANK.__getitem__)

    if requested_version is not None:
        assert manual_tag
        if latest is not None and requested_version <= latest.version:
            fail(
                f"manual tag {manual_tag} must be greater than latest tag {latest.name}"
            )
        if latest is not None and required_bump != "skip":
            minimum = latest.version.bump(required_bump)
            if requested_version < minimum:
                fail(
                    f"manual tag {manual_tag} is lower than required "
                    f"{required_bump} bump {minimum.tag}"
                )
        next_tag = requested_version.tag
        bump = "manual"
    elif required_bump == "skip":
        return ReleasePlan(
            "skip",
            "",
            latest.name if latest else "",
            "skip",
            head_commit,
            CURRENT_NOTES_FORMAT,
            "",
            tag_graph_sha256(tags),
            False,
        )
    else:
        assert latest is not None
        next_tag = latest.version.bump(required_bump).tag
        bump = required_bump

    return ReleasePlan(
        "publish",
        next_tag,
        latest.name if latest else "",
        bump,
        head_commit,
        CURRENT_NOTES_FORMAT,
        "",
        tag_graph_sha256(tags),
        True,
    )


def verify_github_release(
    release: Any,
    *,
    expected_metadata: ReleaseMetadata,
    expected_notes: str,
    expected_author: str,
) -> None:
    """Validate the complete GitHub Release projection at observation time."""
    expected_metadata.validate()
    parsed_metadata = parse_release_metadata(expected_notes)
    if parsed_metadata != expected_metadata:
        fail("scanned release notes contain conflicting release metadata")
    if not isinstance(release, dict):
        fail("GitHub Release API response must be an object")

    problems: list[str] = []
    expected_values: dict[str, object] = {
        "tag_name": expected_metadata.tag,
        "name": expected_metadata.tag,
        "body": expected_notes,
        "assets": [],
    }
    labels = {
        "tag_name": "tag name",
        "name": "title",
        "body": "release notes",
        "assets": "release assets",
    }
    for key, expected_value in expected_values.items():
        if release.get(key) != expected_value:
            problems.append(labels[key])
    for key, expected_value in (
        ("draft", False),
        ("prerelease", False),
        ("immutable", True),
    ):
        if type(release.get(key)) is not bool or release[key] is not expected_value:
            problems.append(f"{key} state")
    author = release.get("author")
    if not isinstance(author, dict) or author.get("login") != expected_author:
        problems.append("release author")
    if problems:
        fail(
            f"GitHub Release {expected_metadata.tag} has conflicting "
            + ", ".join(problems)
        )


def write_github_outputs(path: Path, outputs: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        for key, value in outputs.items():
            if "\n" in key or "\n" in value or "\r" in key or "\r" in value:
                fail(f"GitHub Actions output {key!r} must fit on one line")
            stream.write(f"{key}={value}\n")
