"""Frozen compatibility, tag-annotation, and release-note protocols."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from release_common import (
    BUMP_RANK,
    Bump,
    CURRENT_NOTES_FORMAT,
    LegacyReleaseError,
    MANIFEST_PATH,
    SemanticVersion,
    fail,
    git_is_ancestor,
    git_output,
    read_tag_object,
    read_regular_blob_at_commit,
    require_commit,
    require_notes_format,
    require_sha256,
    require_tag_object_identity,
    tag_commit,
)


MANIFEST_PATH_V1 = "action-compatibility.json"
MANIFEST_KEYS_V1 = frozenset({"python_versions", "vexcalibur_package"})
PACKAGE_VERSION_PATTERN_V1 = (
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
    r"(?:\+[0-9A-Za-z]+(?:[._-][0-9A-Za-z]+)*)?"
)
PACKAGE_PATTERN_V1 = re.compile(rf"^vexcalibur==({PACKAGE_VERSION_PATTERN_V1})$")
PYTHON_PATTERN_V1 = re.compile(r"^3\.(?:[0-9]|[1-9][0-9])$")
RELEASE_METADATA_START = "<!-- vexcalibur-action-release-metadata"
RELEASE_METADATA_PATTERN = re.compile(
    rf"^{re.escape(RELEASE_METADATA_START)}\n"
    r"tag=(?P<tag>[^\n]+)\n"
    r"commit=(?P<commit>[^\n]+)\n"
    r"notes_format=(?P<notes_format>[^\n]+)\n"
    r"compatibility_sha256=(?P<compatibility_sha256>[^\n]+)\n"
    r"-->$",
    re.MULTILINE,
)
MARKDOWN_ESCAPE_PATTERN = re.compile(r"([\\`*{}\[\]()<>#+\-.!_|>])")
TAG_METADATA_PATTERN = re.compile(
    r"^Release (?P<tag>[^\n]+)\n\n"
    r"Release-Commit: (?P<commit>[^\n]+)\n"
    rf"Compatibility-Manifest: {re.escape(MANIFEST_PATH_V1)}\n"
    r"Compatibility-SHA256: (?P<compatibility_sha256>[^\n]+)\n"
    r"Release-Notes-Format: (?P<notes_format>[^\n]+)\n"
    r"Release-Notes-SHA256: (?P<notes_sha256>[^\n]+)\n$"
)


@dataclass(frozen=True)
class CompatibilityManifest:
    """Compatibility facts that CI proves for the action wrapper."""

    package_spec: str
    package_version: str
    python_versions: tuple[str, ...]
    sha256: str

    def github_outputs(self) -> dict[str, str]:
        return {
            "manifest_sha256": self.sha256,
            "package_spec": self.package_spec,
            "package_version": self.package_version,
            "python_versions": json.dumps(self.python_versions, separators=(",", ":")),
            "python_versions_markdown": ", ".join(
                f"`{version}`" for version in self.python_versions
            ),
        }


@dataclass(frozen=True)
class CompatibilityChange:
    """Minimum release bump for a semantic compatibility change."""

    required_bump: Bump
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SelectedPackageArtifact:
    """One wheel selected by pip and authenticated by PyPI metadata."""

    url: str
    filename: str
    sha256: str

    def github_outputs(self) -> dict[str, str]:
        return {
            "artifact_url": self.url,
            "artifact_filename": self.filename,
            "artifact_sha256": self.sha256,
        }


@dataclass(frozen=True)
class ReleaseMetadata:
    """Machine-readable identity embedded once in release notes."""

    tag: str
    commit: str
    notes_format: str
    compatibility_sha256: str

    def validate(self) -> None:
        SemanticVersion.from_tag(self.tag)
        require_commit(self.commit)
        require_notes_format(self.notes_format)
        require_sha256(self.compatibility_sha256)

    def render(self) -> str:
        self.validate()
        return "\n".join(
            (
                RELEASE_METADATA_START,
                f"tag={self.tag}",
                f"commit={self.commit}",
                f"notes_format={self.notes_format}",
                f"compatibility_sha256={self.compatibility_sha256}",
                "-->",
            )
        )


@dataclass(frozen=True)
class TagMetadata:
    """Exact annotation stored in every release tag created by this workflow."""

    tag: str
    commit: str
    compatibility_sha256: str
    notes_format: str
    notes_sha256: str

    def validate(self) -> None:
        SemanticVersion.from_tag(self.tag)
        require_commit(self.commit)
        require_sha256(self.compatibility_sha256)
        require_notes_format(self.notes_format)
        require_sha256(self.notes_sha256)

    def render(self) -> str:
        self.validate()
        return "\n".join(
            (
                f"Release {self.tag}",
                "",
                f"Release-Commit: {self.commit}",
                f"Compatibility-Manifest: {MANIFEST_PATH_V1}",
                f"Compatibility-SHA256: {self.compatibility_sha256}",
                f"Release-Notes-Format: {self.notes_format}",
                f"Release-Notes-SHA256: {self.notes_sha256}",
            )
        )


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            fail(f"JSON object contains duplicate key {key!r}")
        document[key] = value
    return document


def parse_json(raw: bytes, *, source: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{source} is not valid JSON: {exc}")


def parse_manifest_v1(
    raw: bytes, *, source: str = MANIFEST_PATH_V1
) -> CompatibilityManifest:
    document = parse_json(raw, source=source)
    if not isinstance(document, dict):
        fail("action compatibility declaration must be a JSON object")
    if set(document) != MANIFEST_KEYS_V1:
        fail(
            "action compatibility keys must be exactly "
            + ", ".join(sorted(MANIFEST_KEYS_V1))
        )

    package_spec = document["vexcalibur_package"]
    if not isinstance(package_spec, str):
        fail("vexcalibur_package must be a string")
    package_match = PACKAGE_PATTERN_V1.fullmatch(package_spec)
    if package_match is None:
        fail("vexcalibur_package must be one exact vexcalibur==VERSION spec")

    python_versions = document["python_versions"]
    if not isinstance(python_versions, list) or not python_versions:
        fail("python_versions must be a nonempty list")
    if any(
        not isinstance(version, str) or PYTHON_PATTERN_V1.fullmatch(version) is None
        for version in python_versions
    ):
        fail("python_versions must contain only Python 3 major.minor strings")
    if len(python_versions) != len(set(python_versions)):
        fail("python_versions must not contain duplicates")
    if python_versions != sorted(python_versions, key=lambda value: int(value[2:])):
        fail("python_versions must be in ascending numeric order")

    return CompatibilityManifest(
        package_spec,
        package_match.group(1),
        tuple(python_versions),
        hashlib.sha256(raw).hexdigest(),
    )


def parse_manifest(raw: bytes, *, source: str = MANIFEST_PATH) -> CompatibilityManifest:
    """Parse the current compatibility protocol."""
    return parse_manifest_v1(raw, source=source)


def verify_selected_pypi_artifact(
    pip_report: Any,
    pypi_release: Any,
    *,
    package_spec: str,
) -> SelectedPackageArtifact:
    """Verify that pip selected the expected non-yanked Vexcalibur artifact."""
    package_match = PACKAGE_PATTERN_V1.fullmatch(package_spec)
    if package_match is None:
        fail("package spec must be one exact vexcalibur==VERSION spec")
    expected_version = package_match.group(1)

    if not isinstance(pip_report, dict) or not isinstance(
        pip_report.get("install"), list
    ):
        fail("pip installation report is malformed")
    selected: list[dict[str, Any]] = []
    for item in pip_report["install"]:
        if not isinstance(item, dict):
            fail("pip installation report contains a malformed install entry")
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            fail("pip installation report contains malformed package metadata")
        normalized_name = re.sub(r"[-_.]+", "-", str(metadata.get("name", ""))).lower()
        if normalized_name == "vexcalibur" and item.get("requested") is True:
            selected.append(item)
    if len(selected) != 1:
        fail("pip installation report must select Vexcalibur exactly once")

    selected_metadata = selected[0]["metadata"]
    if selected_metadata.get("version") != expected_version:
        fail("pip selected a Vexcalibur version that conflicts with the package spec")
    download = selected[0].get("download_info")
    if not isinstance(download, dict) or not isinstance(download.get("url"), str):
        fail("pip installation report has no selected Vexcalibur artifact URL")
    selected_url = download["url"]

    if not isinstance(pypi_release, dict):
        fail("PyPI release response is malformed")
    info = pypi_release.get("info")
    files = pypi_release.get("urls")
    if (
        not isinstance(info, dict)
        or info.get("name") != "vexcalibur"
        or info.get("version") != expected_version
        or not isinstance(files, list)
    ):
        fail("PyPI release response conflicts with the expected Vexcalibur release")
    matches = [
        file
        for file in files
        if isinstance(file, dict) and file.get("url") == selected_url
    ]
    if len(matches) != 1:
        fail("pip selected an artifact that is absent from the PyPI release response")
    if matches[0].get("yanked") is not False:
        fail("pip selected a yanked Vexcalibur artifact")
    selected_file = matches[0]
    filename = selected_file.get("filename")
    digests = selected_file.get("digests")
    if (
        selected_file.get("packagetype") != "bdist_wheel"
        or not isinstance(filename, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.whl", filename) is None
        or not isinstance(digests, dict)
        or not isinstance(digests.get("sha256"), str)
    ):
        fail("PyPI selected artifact is not a verifiable wheel")
    parsed_url = urlsplit(selected_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "files.pythonhosted.org"
        or unquote(parsed_url.path.rsplit("/", 1)[-1]) != filename
        or parsed_url.query
        or parsed_url.fragment
    ):
        fail("PyPI selected artifact URL is not canonical")
    artifact_sha256 = digests["sha256"]
    require_sha256(artifact_sha256)
    return SelectedPackageArtifact(selected_url, filename, artifact_sha256)


def read_manifest(path: Path) -> CompatibilityManifest:
    return parse_manifest(path.read_bytes(), source=str(path))


def read_manifest_v1_at_commit(
    commit: str, *, cwd: Path | None = None
) -> CompatibilityManifest:
    raw = read_regular_blob_at_commit(commit, MANIFEST_PATH_V1, cwd=cwd)
    if raw is None:
        fail(
            f"release commit {commit} has no {MANIFEST_PATH_V1}; "
            "legacy releases cannot be recovered automatically"
        )
    return parse_manifest_v1(raw, source=f"{commit}:{MANIFEST_PATH_V1}")


def read_manifest_at_commit(
    commit: str, *, cwd: Path | None = None
) -> CompatibilityManifest:
    """Read the current compatibility protocol from a commit."""
    return read_manifest_v1_at_commit(commit, cwd=cwd)


def classify_compatibility_change(
    released: CompatibilityManifest | None,
    current: CompatibilityManifest,
) -> CompatibilityChange:
    """Classify semantic compatibility changes without comparing JSON layout."""
    if released is None:
        return CompatibilityChange("patch", ("compatibility declaration was added",))

    major_reasons: list[str] = []
    minor_reasons: list[str] = []
    patch_reasons: list[str] = []
    removed_python = sorted(
        set(released.python_versions) - set(current.python_versions)
    )
    added_python = sorted(set(current.python_versions) - set(released.python_versions))
    if removed_python:
        major_reasons.append("Python support was removed: " + ", ".join(removed_python))
    if added_python:
        minor_reasons.append("Python support was added: " + ", ".join(added_python))
    if released.package_spec != current.package_spec:
        patch_reasons.append(
            f"package changed from {released.package_spec} to {current.package_spec}"
        )

    groups: tuple[tuple[Bump, list[str]], ...] = (
        ("major", major_reasons),
        ("minor", minor_reasons),
        ("patch", patch_reasons),
    )
    required: Bump = "skip"
    reasons: list[str] = []
    for bump, entries in groups:
        reasons.extend(entries)
        if entries and BUMP_RANK[bump] > BUMP_RANK[required]:
            required = bump
    return CompatibilityChange(required, tuple(reasons))


def inline_code_v1(value: str) -> str:
    """Render literal GitHub Markdown without activating mentions or links."""
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", value)),
        default=0,
    )
    delimiter = "`" * (longest_backtick_run + 1)
    return f"{delimiter} {value} {delimiter}"


def release_commits(
    commit: str, previous_tag: str = "", *, cwd: Path | None = None
) -> list[tuple[str, str]]:
    require_commit(commit)
    if previous_tag:
        SemanticVersion.from_tag(previous_tag)
        previous_commit = tag_commit(f"refs/tags/{previous_tag}", cwd=cwd)
        if not git_is_ancestor(previous_commit, commit, cwd=cwd):
            fail(f"previous tag {previous_tag} is not an ancestor of {commit}")
        revision = f"{previous_tag}..{commit}"
    else:
        revision = commit
    commits = git_output("rev-list", "--reverse", revision, cwd=cwd).splitlines()
    return [
        (sha, git_output("show", "-s", "--format=%s", sha, cwd=cwd)) for sha in commits
    ]


def render_release_notes(
    *,
    tag: str,
    commit: str,
    previous_tag: str = "",
    notes_format: str = CURRENT_NOTES_FORMAT,
    cwd: Path | None = None,
) -> str:
    """Render deterministic notes from Git history and compatibility metadata."""
    SemanticVersion.from_tag(tag)
    require_commit(commit)
    require_notes_format(notes_format)
    if notes_format == CURRENT_NOTES_FORMAT:
        notes = render_release_notes_v1(
            tag=tag,
            commit=commit,
            previous_tag=previous_tag,
            cwd=cwd,
        )
        parse_release_metadata(notes)
        return notes
    fail(f"release-note format {notes_format!r} has no renderer")


def render_release_notes_v1(
    *,
    tag: str,
    commit: str,
    previous_tag: str = "",
    cwd: Path | None = None,
) -> str:
    """Render the frozen notes format with inert commit subjects."""
    manifest = read_manifest_v1_at_commit(commit, cwd=cwd)
    commits = release_commits(commit, previous_tag, cwd=cwd)
    lines = ["## Changes", ""]
    if commits:
        lines.extend(
            f"- `{sha[:12]}` {inline_code_v1(subject)}" for sha, subject in commits
        )
    else:
        lines.append("No commits were found in the release range.")
    lines.extend(
        (
            "",
            "## Tested compatibility",
            "",
            f"- Vexcalibur package: `{manifest.package_spec}`",
            "- Python: "
            + ", ".join(f"`{version}`" for version in manifest.python_versions),
            f"- Compatibility declaration: `{MANIFEST_PATH_V1}` at `{commit}`",
            "",
            ReleaseMetadata(tag, commit, "1", manifest.sha256).render(),
            "",
        )
    )
    return "\n".join(lines)


def parse_release_metadata(body: str) -> ReleaseMetadata:
    start = body.rfind(RELEASE_METADATA_START)
    if start < 0:
        fail("release notes contain no release metadata block")
    candidate = body[start:].removesuffix("\n")
    match = RELEASE_METADATA_PATTERN.fullmatch(candidate)
    if match is None:
        fail("release notes contain malformed release metadata")
    metadata = ReleaseMetadata(**match.groupdict())
    metadata.validate()
    if candidate != metadata.render():
        fail("release metadata is not in canonical form")
    return metadata


def notes_sha256(notes: str) -> str:
    return hashlib.sha256(notes.encode()).hexdigest()


def read_tag_metadata(reference: str, *, cwd: Path | None = None) -> TagMetadata:
    headers, message = read_tag_object(reference, cwd=cwd)
    match = TAG_METADATA_PATTERN.fullmatch(message)
    if match is None:
        canonical_markers = (
            f"Compatibility-Manifest: {MANIFEST_PATH_V1}",
            "Release-Notes-Format:",
            "Release-Notes-SHA256:",
        )
        if not any(marker in message for marker in canonical_markers):
            raise LegacyReleaseError(
                f"release reference {reference} has no canonical annotation metadata"
            )
        fail(f"release reference {reference} has malformed canonical metadata")
    metadata = TagMetadata(**match.groupdict())
    metadata.validate()
    if (
        headers["object"] != metadata.commit
        or headers["type"] != "commit"
        or headers["tag"] != metadata.tag
    ):
        fail(f"release reference {reference} conflicts with its annotated-tag headers")
    return metadata


def verify_tag_reference(
    reference: str, expected: TagMetadata, *, cwd: Path | None = None
) -> None:
    expected.validate()
    actual_message = require_tag_object_identity(
        reference,
        expected_tag=expected.tag,
        expected_commit=expected.commit,
        cwd=cwd,
    )
    if actual_message != expected.render() + "\n":
        fail(f"release reference {reference} has conflicting annotation metadata")


def parse_release_json(path: Path) -> Any:
    return parse_json(path.read_bytes(), source=str(path))
