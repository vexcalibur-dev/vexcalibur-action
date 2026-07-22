from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import unittest

from tests.release_test_support import (
    ROOT,
    GitRepositoryTest,
    annotated_tag,
    canonical_tag,
    commit,
    git,
    raw_tag,
    write_action,
)

from release_metadata import inline_code_v1  # noqa: E402
from release_state import (  # noqa: E402
    ReleaseMetadata,
    ReleasePlan,
    ReleaseStateError,
    TagMetadata,
    classify_commit,
    parse_release_metadata,
    plan_release,
    read_manifest,
    read_manifest_at_commit,
    render_release_notes,
)


class ReleasePlanningTests(GitRepositoryTest):
    def test_release_plan_rejects_impossible_operation_states(self) -> None:
        cases = (
            ("skip", "v0.1.0", "skip", ""),
            ("publish", "v0.1.0", "skip", ""),
            ("publish", "v0.1.0", "patch", "a" * 64),
            ("recover", "v0.1.0", "existing", ""),
            ("unknown", "v0.1.0", "existing", "a" * 64),
        )
        for operation, tag, bump, notes_digest in cases:
            with (
                self.subTest(operation=operation),
                self.assertRaises(ReleaseStateError),
            ):
                ReleasePlan(  # type: ignore[arg-type]
                    operation,
                    tag,
                    "",
                    bump,
                    self.initial_commit,
                    "1",
                    notes_digest,
                    "a" * 64,
                    False,
                )

    def test_first_release_requires_explicit_tag(self) -> None:
        with self.assertRaisesRegex(ReleaseStateError, "first release requires"):
            plan_release(cwd=self.repo)

    def test_explicit_first_release_uses_requested_tag(self) -> None:
        plan = plan_release("v0.4.0", cwd=self.repo)

        self.assertEqual(plan.operation, "publish")
        self.assertEqual(plan.tag, "v0.4.0")
        self.assertEqual(plan.commit, self.initial_commit)

    def test_cli_writes_complete_github_outputs(self) -> None:
        output_path = self.root / "github-output.txt"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/release.py"),
                "plan",
                "--tag",
                "v0.4.0",
            ],
            cwd=self.repo,
            env={**os.environ, "GITHUB_OUTPUT": str(output_path)},
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = dict(
            line.split("=", 1)
            for line in output_path.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(outputs["tag"], "v0.4.0")
        self.assertEqual(outputs["sha"], self.initial_commit)
        self.assertNotIn("skip", outputs)
        self.assertEqual(outputs["notes_format"], "1")
        self.assertEqual(outputs["expected_notes_sha256"], "")
        self.assertRegex(outputs["expected_tag_graph_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(outputs["make_latest"], "true")

    def test_commit_types_choose_highest_required_bump(self) -> None:
        annotated_tag(self.repo, "v0.1.0")
        commit(self.repo, "fix: repair behavior", "fix.txt")
        commit(self.repo, "feat: add behavior", "feature.txt")

        plan = plan_release(cwd=self.repo)

        self.assertEqual((plan.bump, plan.tag), ("minor", "v0.2.0"))

    def test_breaking_footer_must_be_in_final_paragraph(self) -> None:
        self.assertEqual(
            classify_commit(
                "docs: show an example\n\n"
                "BREAKING CHANGE: example only\n\n"
                "This final paragraph is ordinary prose."
            ),
            "skip",
        )
        self.assertEqual(
            classify_commit(
                "fix: change behavior\n\n"
                "Migration details.\n\n"
                "BREAKING CHANGE: replace the old input"
            ),
            "major",
        )
        self.assertEqual(
            classify_commit(
                "docs: quote an example\n\n"
                "This is an ordinary final paragraph.\n"
                "BREAKING CHANGE: quoted, not a footer"
            ),
            "skip",
        )
        self.assertEqual(
            classify_commit("fix: no detail\n\nBREAKING CHANGE:"),
            "patch",
        )
        self.assertEqual(
            classify_commit(
                "fix: replace behavior\n\n"
                "Co-authored-by: Person <person@example.invalid>\n"
                "BREAKING-CHANGE: replace the old input"
            ),
            "major",
        )

    def test_breaking_subject_and_revert_are_classified(self) -> None:
        self.assertEqual(classify_commit("feat!: replace input"), "major")
        self.assertEqual(classify_commit("api-change!: replace input"), "major")
        self.assertEqual(classify_commit("fix2!: replace input"), "major")
        self.assertEqual(classify_commit('Revert "broken behavior"'), "patch")

    def test_documented_patch_types_and_scopes_are_classified(self) -> None:
        subjects = (
            "fix: repair",
            "perf(action): improve",
            "refactor: reorganize",
            "deps(cli): update",
            "revert: undo",
            "build(deps): update",
            "chore(deps): update",
        )
        for subject in subjects:
            with self.subTest(subject=subject):
                self.assertEqual(classify_commit(subject), "patch")

    def test_skip_marker_permanently_excludes_marked_commit(self) -> None:
        annotated_tag(self.repo, "v0.1.0")
        commit(self.repo, "fix: deferred [skip release]", "fix.txt")
        head = commit(self.repo, "docs: explain maintenance", "docs.txt")

        plan = plan_release(cwd=self.repo)

        self.assertEqual(plan.operation, "skip")
        self.assertEqual(plan.commit, head)

    def test_manual_tag_cannot_understate_required_bump(self) -> None:
        annotated_tag(self.repo, "v0.1.0")
        commit(self.repo, "feat: add behavior")

        with self.assertRaisesRegex(ReleaseStateError, "required minor bump"):
            plan_release("v0.1.1", cwd=self.repo)

    def test_planner_reclassifies_contract_against_an_intervening_tag(self) -> None:
        annotated_tag(self.repo, "v1.0.0")
        write_action(
            self.repo,
            inputs="{query: {required: false, default: value}}",
        )
        git(self.repo, "add", "action.yml")
        git(self.repo, "commit", "-m", "feat: add query input")
        intermediate = git(self.repo, "rev-parse", "HEAD")

        write_action(self.repo)
        git(self.repo, "add", "action.yml")
        git(self.repo, "commit", "-m", "fix: remove query input")

        annotated_tag(self.repo, "v1.1.0", intermediate)
        plan = plan_release(cwd=self.repo)

        self.assertEqual((plan.bump, plan.tag), ("major", "v2.0.0"))

    def test_existing_old_tag_can_be_recovered_after_main_advances(self) -> None:
        canonical_tag(self.repo, "v0.1.0")
        old_commit = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, "fix: repair behavior")
        canonical_tag(self.repo, "v0.1.1")
        commit(self.repo, "docs: later documentation")

        plan = plan_release("v0.1.0", cwd=self.repo)

        self.assertEqual(plan.operation, "recover")
        self.assertEqual(plan.commit, old_commit)
        self.assertEqual(plan.notes_format, "1")
        self.assertEqual(plan.expected_notes_sha256, "b" * 64)
        self.assertFalse(plan.make_latest)

    def test_release_graph_rejects_bad_tag_objects(self) -> None:
        with self.subTest("lightweight"):
            git(self.repo, "tag", "v0.1.0")
            with self.assertRaisesRegex(ReleaseStateError, "annotated tag"):
                plan_release(cwd=self.repo)
            git(self.repo, "tag", "-d", "v0.1.0")

        annotated_tag(self.repo, "v0.1.0")
        annotated_tag(self.repo, "v0.1.1")
        with (
            self.subTest("duplicate"),
            self.assertRaisesRegex(ReleaseStateError, "same commit"),
        ):
            plan_release(cwd=self.repo)

    def test_release_graph_rejects_unreachable_and_reordered_tags(self) -> None:
        git(self.repo, "switch", "-c", "side")
        commit(self.repo, "fix: side branch", "side.txt")
        annotated_tag(self.repo, "v0.1.0")
        git(self.repo, "switch", "main")
        with (
            self.subTest("unreachable"),
            self.assertRaisesRegex(ReleaseStateError, "not reachable"),
        ):
            plan_release(cwd=self.repo)

        git(self.repo, "tag", "-d", "v0.1.0")
        annotated_tag(self.repo, "v0.2.0")
        commit(self.repo, "fix: later", "later.txt")
        annotated_tag(self.repo, "v0.1.0")
        with (
            self.subTest("reordered"),
            self.assertRaisesRegex(
                ReleaseStateError, "tag order does not follow commit ancestry"
            ),
        ):
            plan_release(cwd=self.repo)

    def test_release_graph_rejects_nested_legacy_tag(self) -> None:
        annotated_tag(self.repo, "inner", self.initial_commit)
        inner_object = git(self.repo, "rev-parse", "refs/tags/inner")
        raw_tag(
            self.repo,
            ref_name="v0.1.0",
            object_sha=inner_object,
            object_type="tag",
            embedded_tag="v0.1.0",
            message="Release v0.1.0",
        )
        commit(self.repo, "fix: later", "later.txt")

        with self.assertRaisesRegex(ReleaseStateError, "annotated-tag headers"):
            plan_release(cwd=self.repo)

    def test_malformed_and_unbounded_manual_tags_are_rejected(self) -> None:
        for tag in (
            "0.1.0",
            "v01.1.0",
            "v0.0.1000000",
            f"v0.0.{('9' * 5000)}",
        ):
            with self.subTest(tag=tag), self.assertRaises(ReleaseStateError):
                plan_release(tag, cwd=self.repo)

    def test_cli_reports_oversized_tag_without_a_traceback(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/release.py"),
                "plan",
                "--tag",
                f"v0.0.{('9' * 5000)}",
            ],
            cwd=self.repo,
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("release state error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_automatic_bump_cannot_overflow_a_version_component(self) -> None:
        annotated_tag(self.repo, "v0.0.999999")
        commit(self.repo, "fix: overflow the bounded patch")

        with self.assertRaisesRegex(ReleaseStateError, "less than or equal"):
            plan_release(cwd=self.repo)


class ReleaseNotesTests(GitRepositoryTest):
    def test_tag_annotation_format_is_frozen(self) -> None:
        metadata = TagMetadata("v1.2.3", "1" * 40, "a" * 64, "1", "b" * 64)

        self.assertEqual(
            metadata.render(),
            "Release v1.2.3\n\n"
            f"Release-Commit: {'1' * 40}\n"
            "Compatibility-Manifest: action-compatibility.json\n"
            f"Compatibility-SHA256: {'a' * 64}\n"
            "Release-Notes-Format: 1\n"
            f"Release-Notes-SHA256: {'b' * 64}",
        )

    def test_current_release_notes_render_subjects_as_literal_code(self) -> None:
        subject = "fix: avoid @octocat and @example/team with `code`"

        rendered = inline_code_v1(subject)

        self.assertTrue(rendered.startswith("`` "))
        self.assertTrue(rendered.endswith(" ``"))
        self.assertIn(subject, rendered)

    def test_committed_manifest_digest_uses_exact_crlf_bytes(self) -> None:
        raw_manifest = (
            b'{\r\n  "python_versions": ["3.10", "3.14"],\r\n'
            b'  "vexcalibur_package": "vexcalibur==1.2.3"\r\n}\r\n'
        )
        (self.repo / "action-compatibility.json").write_bytes(raw_manifest)
        git(self.repo, "add", "action-compatibility.json")
        git(self.repo, "commit", "-m", "test: preserve manifest bytes")
        target = git(self.repo, "rev-parse", "HEAD")

        manifest = read_manifest_at_commit(target, cwd=self.repo)

        self.assertEqual(manifest.sha256, hashlib.sha256(raw_manifest).hexdigest())

    def test_notes_are_deterministic_and_bind_manifest_and_history(self) -> None:
        annotated_tag(self.repo, "v0.1.0")
        commit(self.repo, "fix: escape [links](https://example.invalid)")
        target = git(self.repo, "rev-parse", "HEAD")
        manifest = read_manifest(self.repo / "action-compatibility.json")

        first = render_release_notes(
            tag="v0.1.1",
            commit=target,
            previous_tag="v0.1.0",
            cwd=self.repo,
        )
        second = render_release_notes(
            tag="v0.1.1",
            commit=target,
            previous_tag="v0.1.0",
            cwd=self.repo,
        )

        self.assertEqual(first, second)
        self.assertIn("` fix: escape [links](https://example.invalid) `", first)
        self.assertIn("vexcalibur==1.2.3", first)
        self.assertEqual(
            parse_release_metadata(first),
            ReleaseMetadata("v0.1.1", target, "1", manifest.sha256),
        )
        release_metadata = (
            "<!-- vexcalibur-action-release-metadata\n"
            "tag=v0.1.1\n"
            f"commit={target}\n"
            "notes_format=1\n"
            f"compatibility_sha256={manifest.sha256}\n"
            "-->"
        )
        expected = (
            "## Changes\n\n"
            f"- `{target[:12]}` ` fix: escape "
            "[links](https://example.invalid) `"
            "\n\n## Tested compatibility\n\n"
            "- Vexcalibur package: `vexcalibur==1.2.3`\n"
            "- Python: `3.10`, `3.14`\n"
            "- Compatibility declaration: `action-compatibility.json` at "
            f"`{target}`\n\n"
            f"{release_metadata}\n"
        )
        self.assertEqual(first, expected, "release-note format 1 must remain stable")

    def test_metadata_like_commit_subject_does_not_shadow_terminal_metadata(
        self,
    ) -> None:
        annotated_tag(self.repo, "v0.1.0")
        commit(self.repo, "fix: <!-- vexcalibur-action-release-metadata")
        target = git(self.repo, "rev-parse", "HEAD")
        manifest = read_manifest(self.repo / "action-compatibility.json")

        notes = render_release_notes(
            tag="v0.1.1",
            commit=target,
            previous_tag="v0.1.0",
            cwd=self.repo,
        )

        self.assertEqual(
            parse_release_metadata(notes),
            ReleaseMetadata("v0.1.1", target, "1", manifest.sha256),
        )

    def test_unknown_notes_format_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ReleaseStateError, "unsupported release-note format"
        ):
            render_release_notes(
                tag="v0.1.0",
                commit=self.initial_commit,
                notes_format="2",
                cwd=self.repo,
            )

    def test_only_terminal_canonical_metadata_is_authoritative(self) -> None:
        metadata = ReleaseMetadata("v1.2.3", "1" * 40, "1", "a" * 64).render()
        self.assertEqual(
            parse_release_metadata(metadata + "\n" + metadata),
            ReleaseMetadata("v1.2.3", "1" * 40, "1", "a" * 64),
        )
        for body in (
            metadata.replace("tag=", "tag ="),
            metadata + "\ncontent after the terminal block",
        ):
            with self.subTest(body=body), self.assertRaises(ReleaseStateError):
                parse_release_metadata(body)

    def test_legacy_release_without_manifest_has_clear_recovery_boundary(self) -> None:
        (self.repo / "action-compatibility.json").unlink()
        git(self.repo, "add", "--update")
        git(self.repo, "commit", "-m", "chore: legacy release")
        target = git(self.repo, "rev-parse", "HEAD")

        with self.assertRaisesRegex(
            ReleaseStateError, "legacy releases cannot be recovered automatically"
        ):
            render_release_notes(tag="v0.1.0", commit=target, cwd=self.repo)

    def test_malformed_canonical_recovery_is_not_reported_as_legacy(self) -> None:
        malformed = (
            "Release v0.1.0\n\n"
            "Compatibility-Manifest: action-compatibility.json\n"
            "Release-Notes-Format: 1"
        )
        raw_tag(
            self.repo,
            ref_name="v0.1.0",
            object_sha=self.initial_commit,
            object_type="commit",
            embedded_tag="v0.1.0",
            message=malformed,
        )

        with self.assertRaisesRegex(ReleaseStateError, "malformed canonical"):
            plan_release("v0.1.0", cwd=self.repo)

    def test_current_tag_recovers_with_a_legacy_predecessor(self) -> None:
        annotated_tag(self.repo, "v0.1.0")
        target = commit(self.repo, "fix: recover this release", "fix.txt")
        manifest = read_manifest(self.repo / "action-compatibility.json")
        notes = render_release_notes(
            tag="v0.1.1",
            commit=target,
            previous_tag="v0.1.0",
            notes_format="1",
            cwd=self.repo,
        )
        notes_digest = hashlib.sha256(notes.encode()).hexdigest()
        tag_message = (
            "Release v0.1.1\n\n"
            f"Release-Commit: {target}\n"
            "Compatibility-Manifest: action-compatibility.json\n"
            f"Compatibility-SHA256: {manifest.sha256}\n"
            "Release-Notes-Format: 1\n"
            f"Release-Notes-SHA256: {notes_digest}"
        )
        raw_tag(
            self.repo,
            ref_name="v0.1.1",
            object_sha=target,
            object_type="commit",
            embedded_tag="v0.1.1",
            message=tag_message,
        )
        commit(self.repo, "docs: main advanced", "later.txt")

        plan = plan_release("v0.1.1", cwd=self.repo)
        recovered_notes = render_release_notes(
            tag=plan.tag,
            commit=plan.commit,
            previous_tag=plan.previous_tag,
            notes_format=plan.notes_format,
            cwd=self.repo,
        )

        self.assertEqual(
            hashlib.sha256(recovered_notes.encode()).hexdigest(),
            notes_digest,
        )
        self.assertTrue(plan.make_latest)


if __name__ == "__main__":
    unittest.main()
