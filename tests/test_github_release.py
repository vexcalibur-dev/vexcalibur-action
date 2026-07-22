from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_state import (  # noqa: E402
    ReleaseMetadata,
    ReleaseStateError,
    parse_release_json,
    verify_github_release,
)


class GitHubReleaseVerificationTests(unittest.TestCase):
    tag = "v1.2.3"
    commit = "1" * 40
    digest = "a" * 64
    author = "automation[bot]"

    def setUp(self) -> None:
        self.metadata = ReleaseMetadata(self.tag, self.commit, "1", self.digest)
        self.notes = f"## Changes\n\n- change\n\n{self.metadata.render()}\n"
        self.release = {
            "tag_name": self.tag,
            "target_commitish": "main",
            "name": self.tag,
            "draft": False,
            "prerelease": False,
            "immutable": True,
            "body": self.notes,
            "assets": [],
            "author": {"login": self.author},
        }

    def verify(self, release: object | None = None, notes: str | None = None) -> None:
        verify_github_release(
            self.release if release is None else release,
            expected_metadata=self.metadata,
            expected_notes=self.notes if notes is None else notes,
            expected_author=self.author,
        )

    def test_exact_immutable_release_is_valid(self) -> None:
        self.verify()

    def test_every_release_projection_field_fails_closed(self) -> None:
        replacements = {
            "tag_name": "v9.9.9",
            "name": "Unexpected",
            "draft": True,
            "prerelease": True,
            "immutable": False,
            "body": self.notes + "changed",
            "assets": [{"name": "unexpected"}],
        }
        for field, value in replacements.items():
            with self.subTest(field=field):
                release = deepcopy(self.release)
                release[field] = value
                with self.assertRaises(ReleaseStateError):
                    self.verify(release)

    def test_release_state_booleans_require_actual_boolean_values(self) -> None:
        for field, value in (
            ("draft", 0),
            ("prerelease", 0),
            ("immutable", 1),
            ("draft", "false"),
            ("immutable", "true"),
        ):
            with self.subTest(field=field, value=value):
                release = deepcopy(self.release)
                release[field] = value
                with self.assertRaises(ReleaseStateError):
                    self.verify(release)

    def test_target_commitish_is_not_treated_as_release_identity(self) -> None:
        for value in ("a-field-github-ignores-for-existing-tags", None):
            release = deepcopy(self.release)
            if value is None:
                del release["target_commitish"]
            else:
                release["target_commitish"] = value

            with self.subTest(value=value):
                self.verify(release)

    def test_missing_release_projection_fields_fail_closed(self) -> None:
        for field in self.release.keys() - {"target_commitish"}:
            with self.subTest(field=field):
                release = deepcopy(self.release)
                del release[field]
                with self.assertRaises(ReleaseStateError):
                    self.verify(release)

    def test_wrong_or_missing_author_is_rejected(self) -> None:
        for author in ({"login": "other[bot]"}, {}, None):
            with self.subTest(author=author):
                release = deepcopy(self.release)
                release["author"] = author
                with self.assertRaisesRegex(ReleaseStateError, "release author"):
                    self.verify(release)

    def test_non_object_and_changed_release_body_are_rejected(self) -> None:
        with self.assertRaisesRegex(ReleaseStateError, "must be an object"):
            self.verify([self.release])
        with self.assertRaisesRegex(ReleaseStateError, "conflicting release notes"):
            self.verify(notes=self.notes + self.metadata.render())

    def test_release_json_rejects_malformed_and_duplicate_fields(self) -> None:
        documents = (
            b"{",
            b"\xff",
            b'{"tag_name":"v1.2.3","tag_name":"v9.9.9"}',
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "release.json"
            for document in documents:
                with self.subTest(document=document):
                    path.write_bytes(document)
                    with self.assertRaises(ReleaseStateError):
                        parse_release_json(path)


if __name__ == "__main__":
    unittest.main()
