"""Validated release-tag graphs and create-only remote publication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from release_common import (
    SEMVER_TAG_PATTERN,
    SemanticVersion,
    fail,
    git_is_ancestor,
    git_output,
    read_tag_object,
    require_commit,
    require_sha256,
    run_git,
    tag_commit,
)
from release_metadata import TagMetadata, verify_tag_reference


RELEASE_COORDINATION_REF = "refs/heads/release-coordination"


@dataclass(frozen=True)
class ReleaseTag:
    """A validated release tag and its target commit."""

    name: str
    version: SemanticVersion
    object_id: str
    commit: str


def release_tags(*, cwd: Path | None = None, head: str = "HEAD") -> list[ReleaseTag]:
    """Return the validated, ordered release-tag graph reachable from head."""
    names = git_output("tag", "--list", cwd=cwd).splitlines()
    versions = sorted(
        (
            (SemanticVersion.from_tag(name), name)
            for name in names
            if SEMVER_TAG_PATTERN.fullmatch(name)
        ),
        key=lambda pair: pair[0],
    )
    tags: list[ReleaseTag] = []
    commits: dict[str, str] = {}
    for version, name in versions:
        reference = f"refs/tags/{name}"
        object_id = git_output("rev-parse", "--verify", reference, cwd=cwd)
        require_commit(object_id)
        headers, _ = read_tag_object(reference, cwd=cwd)
        if (
            headers["type"] != "commit"
            or headers["tag"] != name
            or git_output("cat-file", "-t", headers["object"], cwd=cwd) != "commit"
        ):
            fail(f"release tag {name} has conflicting annotated-tag headers")
        commit = headers["object"]
        require_commit(commit)
        if not git_is_ancestor(commit, head, cwd=cwd):
            fail(f"release tag {name} is not reachable from the current branch")
        if commit in commits:
            fail(f"release tags {commits[commit]} and {name} point to the same commit")
        if tags and not git_is_ancestor(tags[-1].commit, commit, cwd=cwd):
            fail(
                "release tag order does not follow commit ancestry: "
                f"{tags[-1].name} then {name}"
            )
        commits[commit] = name
        tags.append(ReleaseTag(name, version, object_id, commit))
    return tags


def tag_graph_sha256(tags: list[ReleaseTag]) -> str:
    """Hash the ordered names, tag objects, and targets in a release graph."""
    payload = bytearray()
    for tag in tags:
        SemanticVersion.from_tag(tag.name)
        require_commit(tag.object_id)
        require_commit(tag.commit)
        payload.extend(f"{tag.name}\t{tag.object_id}\t{tag.commit}\n".encode())
    return hashlib.sha256(payload).hexdigest()


def remote_release_tags(remote: str, *, cwd: Path | None = None) -> list[ReleaseTag]:
    """Read the complete strict SemVer tag graph advertised by a remote."""
    result = run_git(
        "ls-remote",
        "--tags",
        remote,
        "refs/tags/v*",
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        fail(f"could not inspect release tags on remote {remote}: {detail}")

    objects: dict[str, str] = {}
    commits: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t", 1)
        if (
            len(fields) != 2
            or not fields[1].startswith("refs/tags/")
            or len(fields[0]) != 40
            or any(character not in "0123456789abcdef" for character in fields[0])
        ):
            fail(f"remote {remote} returned malformed release-tag state")
        name = fields[1].removeprefix("refs/tags/")
        peeled = name.endswith("^{}")
        if peeled:
            name = name.removesuffix("^{}")
        if SEMVER_TAG_PATTERN.fullmatch(name) is None:
            continue
        destination = commits if peeled else objects
        if name in destination:
            fail(f"remote {remote} returned duplicate state for release tag {name}")
        destination[name] = fields[0]

    if objects.keys() != commits.keys():
        fail(f"remote {remote} contains a strict release tag that is not annotated")
    tags = [
        ReleaseTag(name, SemanticVersion.from_tag(name), object_id, commits[name])
        for name, object_id in objects.items()
    ]
    tags.sort(key=lambda tag: tag.version)
    seen_commits: dict[str, str] = {}
    for tag in tags:
        if tag.commit in seen_commits:
            fail(
                f"remote release tags {seen_commits[tag.commit]} and {tag.name} "
                "point to the same commit"
            )
        seen_commits[tag.commit] = tag.name
    return tags


def remote_ref_object(
    remote: str,
    reference: str,
    *,
    cwd: Path | None = None,
) -> str:
    """Return one exact advertised remote ref, or an empty string when absent."""
    result = run_git(
        "ls-remote",
        "--refs",
        remote,
        reference,
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        fail(f"could not inspect {reference} on remote {remote}: {detail}")
    lines = result.stdout.splitlines()
    if not lines:
        return ""
    if len(lines) != 1:
        fail(f"remote {remote} returned ambiguous state for {reference}")
    fields = lines[0].split("\t", 1)
    if len(fields) != 2 or fields[1] != reference:
        fail(f"remote {remote} returned malformed state for {reference}")
    require_commit(fields[0])
    return fields[0]


def verify_remote_tag(
    remote: str,
    expected: TagMetadata,
    *,
    cwd: Path | None = None,
) -> None:
    """Fetch a remote tag into an isolated ref and verify it exactly."""
    verification_ref = f"refs/vexcalibur-release/verify/{expected.tag}"
    run_git("update-ref", "-d", verification_ref, cwd=cwd)
    try:
        run_git(
            "fetch",
            "--no-tags",
            remote,
            f"refs/tags/{expected.tag}:{verification_ref}",
            cwd=cwd,
        )
        verify_tag_reference(verification_ref, expected, cwd=cwd)
    finally:
        run_git("update-ref", "-d", verification_ref, cwd=cwd)


def reconcile_remote_tag(
    remote: str,
    expected: TagMetadata,
    *,
    expected_graph_sha256: str,
    cwd: Path | None = None,
) -> str:
    """Create an absent remote tag or verify an existing one without mutation."""
    expected.validate()
    target = tag_commit(expected.commit, cwd=cwd)
    if target != expected.commit:
        fail(f"release commit {expected.commit} does not resolve exactly")

    require_sha256(expected_graph_sha256)
    coordination_before = remote_ref_object(
        remote,
        RELEASE_COORDINATION_REF,
        cwd=cwd,
    )
    remote_tags = remote_release_tags(remote, cwd=cwd)
    remote_by_name = {tag.name: tag for tag in remote_tags}
    if expected.tag in remote_by_name:
        verify_remote_tag(remote, expected, cwd=cwd)
        graph_with_expected = tag_graph_sha256(remote_tags)
        graph_without_expected = tag_graph_sha256(
            [tag for tag in remote_tags if tag.name != expected.tag]
        )
        if expected_graph_sha256 not in {
            graph_with_expected,
            graph_without_expected,
        }:
            fail("remote release-tag graph changed before existing-tag verification")
        return "existing"

    if git_output("rev-parse", "--verify", "HEAD", cwd=cwd) != expected.commit:
        fail("a new release tag must target the checked-out candidate commit")
    expected_version = SemanticVersion.from_tag(expected.tag)
    if remote_tags:
        previous = remote_tags[-1]
        if expected_version <= previous.version:
            fail(f"new release tag {expected.tag} must be greater than {previous.name}")
        if not git_is_ancestor(previous.commit, expected.commit, cwd=cwd):
            fail(
                f"new release commit {expected.commit} must descend from "
                f"{previous.name}"
            )

    if coordination_before and (
        not remote_tags or coordination_before != remote_tags[-1].commit
    ):
        fail("release coordination branch conflicts with the latest release tag")

    actual_graph_sha256 = tag_graph_sha256(remote_tags)
    if actual_graph_sha256 != expected_graph_sha256:
        fail(
            "remote release-tag state changed after planning: "
            f"expected graph {expected_graph_sha256}, found {actual_graph_sha256}"
        )
    duplicate = next(
        (tag.name for tag in remote_tags if tag.commit == expected.commit), None
    )
    if duplicate is not None:
        fail(
            f"release commit {expected.commit} already has remote release tag "
            f"{duplicate}"
        )

    local_ref = f"refs/tags/{expected.tag}"
    if (
        run_git(
            "show-ref", "--verify", "--quiet", local_ref, cwd=cwd, check=False
        ).returncode
        == 0
    ):
        fail(
            f"local release tag {expected.tag} exists while remote {remote} does not; "
            "refusing to publish ambiguous state"
        )

    creation_ref = f"refs/vexcalibur-release/create/{expected.tag}"
    run_git("update-ref", "-d", creation_ref, cwd=cwd)
    tagger = git_output("var", "GIT_COMMITTER_IDENT", cwd=cwd)
    tag_object = "\n".join(
        (
            f"object {expected.commit}",
            "type commit",
            f"tag {expected.tag}",
            f"tagger {tagger}",
            "",
            expected.render(),
            "",
        )
    )
    object_id = run_git("mktag", cwd=cwd, input_text=tag_object).stdout.strip()
    run_git("update-ref", creation_ref, object_id, cwd=cwd)
    coordination_lease = (
        f"--force-with-lease={RELEASE_COORDINATION_REF}:{coordination_before}"
    )
    try:
        verify_tag_reference(creation_ref, expected, cwd=cwd)
        push = run_git(
            "push",
            "--atomic",
            coordination_lease,
            remote,
            f"{creation_ref}:{local_ref}",
            f"{expected.commit}:{RELEASE_COORDINATION_REF}",
            cwd=cwd,
            check=False,
        )
    finally:
        run_git("update-ref", "-d", creation_ref, cwd=cwd)
    final_tags = remote_release_tags(remote, cwd=cwd)
    final_by_name = {tag.name: tag for tag in final_tags}
    if expected.tag not in final_by_name:
        detail = push.stderr.strip() or push.stdout.strip() or "unknown error"
        fail(f"could not create immutable release tag {expected.tag}: {detail}")
    verify_remote_tag(remote, expected, cwd=cwd)
    if remote_ref_object(remote, RELEASE_COORDINATION_REF, cwd=cwd) != expected.commit:
        fail("release coordination branch does not match the published tag")
    final_without_expected = [tag for tag in final_tags if tag.name != expected.tag]
    if tag_graph_sha256(final_without_expected) != expected_graph_sha256:
        fail("remote release-tag graph changed during publication")
    return "created" if push.returncode == 0 else "existing"
