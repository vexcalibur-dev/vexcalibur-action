from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_tags as release_tag_module  # noqa: E402
from release_state import (  # noqa: E402
    ReleaseStateError,
    TagMetadata,
    read_manifest,
    reconcile_remote_tag,
)
from tests.release_test_support import (  # noqa: E402
    GIT,
    GitRepositoryTest,
    annotated_tag,
    commit,
    configure_git,
    git,
    raw_tag,
)


class RemoteTagIntegrationTests(GitRepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.remote = self.root / "remote.git"
        subprocess.run(
            [GIT, "init", "--bare", "--initial-branch=main", str(self.remote)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        self.expected = TagMetadata(
            "v1.2.3", self.initial_commit, "a" * 64, "1", "b" * 64
        )
        self.empty_graph_sha256 = release_tag_module.tag_graph_sha256([])

    def no_tag_clone(self, name: str) -> Path:
        clone = self.root / name
        subprocess.run(
            [GIT, "clone", "--no-tags", str(self.remote), str(clone)],
            check=True,
            capture_output=True,
            text=True,
        )
        configure_git(clone)
        return clone

    def release_cli(
        self, repo: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/release.py"), *arguments],
            cwd=repo,
            check=False,
            text=True,
            capture_output=True,
        )

    def reconcile(
        self,
        repo: Path,
        expected: TagMetadata | None = None,
        *,
        graph_sha256: str | None = None,
    ) -> str:
        return reconcile_remote_tag(
            "origin",
            expected or self.expected,
            expected_graph_sha256=graph_sha256 or self.empty_graph_sha256,
            cwd=repo,
        )

    def test_cli_publish_and_recovery_round_trip(self) -> None:
        manifest = read_manifest(self.repo / "action-compatibility.json")
        notes = self.root / "release-notes.md"
        render = self.release_cli(
            self.repo,
            "render-notes",
            "--tag",
            "v1.2.3",
            "--commit",
            self.initial_commit,
            "--notes-format",
            "1",
            "--output",
            str(notes),
        )
        self.assertEqual(render.returncode, 0, render.stderr)
        notes_digest = hashlib.sha256(notes.read_bytes()).hexdigest()

        publish = self.release_cli(
            self.repo,
            "reconcile-tag",
            "--remote",
            "origin",
            "--expected-tag-graph-sha256",
            self.empty_graph_sha256,
            "--tag",
            "v1.2.3",
            "--commit",
            self.initial_commit,
            "--compatibility-sha256",
            manifest.sha256,
            "--notes-format",
            "1",
            "--notes-sha256",
            notes_digest,
        )
        self.assertEqual(publish.returncode, 0, publish.stderr)
        self.assertIn("created immutable release tag", publish.stdout)

        recovery = self.root / "cli-recovery"
        subprocess.run(
            [GIT, "clone", str(self.remote), str(recovery)],
            check=True,
            capture_output=True,
            text=True,
        )
        plan = self.release_cli(recovery, "plan", "--tag", "v1.2.3")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn("operation=recover", plan.stdout)

        recovered_notes = self.root / "recovered-notes.md"
        rerender = self.release_cli(
            recovery,
            "render-notes",
            "--tag",
            "v1.2.3",
            "--commit",
            self.initial_commit,
            "--notes-format",
            "1",
            "--output",
            str(recovered_notes),
        )
        self.assertEqual(rerender.returncode, 0, rerender.stderr)
        self.assertEqual(recovered_notes.read_bytes(), notes.read_bytes())

        verify = self.release_cli(
            recovery,
            "verify-tag",
            "--ref",
            "refs/tags/v1.2.3",
            "--tag",
            "v1.2.3",
            "--commit",
            self.initial_commit,
            "--compatibility-sha256",
            manifest.sha256,
            "--notes-format",
            "1",
            "--notes-sha256",
            notes_digest,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn("verified immutable release tag", verify.stdout)

    def test_absent_remote_tag_is_created_once_and_never_moved(self) -> None:
        self.assertEqual(self.reconcile(self.repo), "created")
        self.assertEqual(git(self.repo, "tag", "--list", self.expected.tag), "")
        remote_before = git(
            self.repo, "ls-remote", "origin", f"refs/tags/{self.expected.tag}"
        )
        clone = self.no_tag_clone("consumer")
        self.assertEqual(self.reconcile(clone), "existing")

        conflicting = TagMetadata(
            self.expected.tag,
            self.expected.commit,
            "c" * 64,
            self.expected.notes_format,
            self.expected.notes_sha256,
        )
        with self.assertRaisesRegex(ReleaseStateError, "conflicting annotation"):
            self.reconcile(clone, conflicting)

        remote_after = git(
            self.repo, "ls-remote", "origin", f"refs/tags/{self.expected.tag}"
        )
        self.assertEqual(remote_before, remote_after)

    def test_remote_tag_is_authoritative_over_a_divergent_local_tag(self) -> None:
        self.reconcile(self.repo)
        clone = self.no_tag_clone("divergent-local")
        annotated_tag(clone, self.expected.tag, self.expected.commit, "local conflict")
        local_before = git(clone, "rev-parse", f"refs/tags/{self.expected.tag}")

        result = self.reconcile(clone)

        self.assertEqual(result, "existing")
        self.assertEqual(
            git(clone, "rev-parse", f"refs/tags/{self.expected.tag}"),
            local_before,
        )

    def test_remote_lightweight_tag_is_rejected(self) -> None:
        git(self.repo, "tag", self.expected.tag, self.expected.commit)
        git(self.repo, "push", "origin", f"refs/tags/{self.expected.tag}")
        clone = self.no_tag_clone("lightweight-consumer")

        with self.assertRaisesRegex(ReleaseStateError, "not annotated"):
            self.reconcile(clone)
        self.assertEqual(
            git(
                clone,
                "show-ref",
                "--verify",
                f"refs/vexcalibur-release/verify/{self.expected.tag}",
                check=False,
            ),
            "",
        )

    def test_remote_tag_with_conflicting_target_is_rejected(self) -> None:
        conflicting_target = commit(self.repo, "fix: conflicting target", "later.txt")
        raw_tag(
            self.repo,
            ref_name=self.expected.tag,
            object_sha=conflicting_target,
            object_type="commit",
            embedded_tag=self.expected.tag,
            message=self.expected.render(),
        )
        git(self.repo, "push", "origin", f"refs/tags/{self.expected.tag}")
        clone = self.no_tag_clone("wrong-target-consumer")

        with self.assertRaisesRegex(ReleaseStateError, "annotated-tag headers"):
            self.reconcile(clone)

        self.assertEqual(
            git(
                clone,
                "show-ref",
                "--verify",
                f"refs/vexcalibur-release/verify/{self.expected.tag}",
                check=False,
            ),
            "",
        )

    def test_remote_tag_with_wrong_embedded_name_is_rejected(self) -> None:
        raw_tag(
            self.repo,
            ref_name=self.expected.tag,
            object_sha=self.expected.commit,
            object_type="commit",
            embedded_tag="v9.9.9",
            message=self.expected.render(),
        )
        git(self.repo, "push", "origin", f"refs/tags/{self.expected.tag}")
        clone = self.no_tag_clone("wrong-name-consumer")

        with self.assertRaisesRegex(ReleaseStateError, "annotated-tag headers"):
            self.reconcile(clone)

    def test_remote_tag_that_targets_another_tag_is_rejected(self) -> None:
        annotated_tag(self.repo, "inner", self.expected.commit)
        inner_object = git(self.repo, "rev-parse", "refs/tags/inner")
        raw_tag(
            self.repo,
            ref_name=self.expected.tag,
            object_sha=inner_object,
            object_type="tag",
            embedded_tag=self.expected.tag,
            message=self.expected.render(),
        )
        git(self.repo, "push", "origin", f"refs/tags/{self.expected.tag}")
        clone = self.no_tag_clone("nested-tag-consumer")

        with self.assertRaisesRegex(ReleaseStateError, "annotated-tag headers"):
            self.reconcile(clone)

    def test_local_only_tag_is_rejected_as_ambiguous(self) -> None:
        annotated_tag(self.repo, self.expected.tag, self.expected.commit)

        with self.assertRaisesRegex(ReleaseStateError, "ambiguous state"):
            self.reconcile(self.repo)

    def test_new_tag_must_target_the_checked_out_candidate(self) -> None:
        commit(self.repo, "fix: advance candidate", "next.txt")

        with self.assertRaisesRegex(ReleaseStateError, "checked-out candidate"):
            self.reconcile(self.repo)

    def test_new_tag_must_advance_the_highest_version(self) -> None:
        self.reconcile(self.repo)
        next_commit = commit(self.repo, "fix: prepare lower tag", "next.txt")
        expected = TagMetadata("v1.2.2", next_commit, "a" * 64, "1", "b" * 64)
        graph_sha256 = release_tag_module.tag_graph_sha256(
            release_tag_module.remote_release_tags("origin", cwd=self.repo)
        )

        with self.assertRaisesRegex(ReleaseStateError, "must be greater"):
            self.reconcile(self.repo, expected, graph_sha256=graph_sha256)

    def test_new_tag_must_descend_from_the_highest_release(self) -> None:
        self.reconcile(self.repo)
        git(self.repo, "switch", "--orphan", "unrelated")
        unrelated = commit(self.repo, "fix: unrelated history", "unrelated.txt")
        expected = TagMetadata("v1.2.4", unrelated, "a" * 64, "1", "b" * 64)
        graph_sha256 = release_tag_module.tag_graph_sha256(
            release_tag_module.remote_release_tags("origin", cwd=self.repo)
        )

        with self.assertRaisesRegex(ReleaseStateError, "must descend"):
            self.reconcile(self.repo, expected, graph_sha256=graph_sha256)

    def test_new_remote_predecessor_stops_a_stale_publication_plan(self) -> None:
        annotated_tag(self.repo, "v1.2.2", self.expected.commit)
        git(self.repo, "push", "origin", "refs/tags/v1.2.2")
        next_commit = commit(self.repo, "fix: prepare next release", "next.txt")
        expected = TagMetadata("v1.2.3", next_commit, "a" * 64, "1", "b" * 64)

        with self.assertRaisesRegex(ReleaseStateError, "changed after planning"):
            self.reconcile(self.repo, expected)

        self.assertEqual(
            self.reconcile(
                self.repo,
                expected,
                graph_sha256=release_tag_module.tag_graph_sha256(
                    release_tag_module.release_tags(cwd=self.repo)
                ),
            ),
            "created",
        )

    def test_release_commit_cannot_receive_a_second_strict_tag(self) -> None:
        annotated_tag(self.repo, "v1.2.2", self.expected.commit)
        git(self.repo, "push", "origin", "refs/tags/v1.2.2")
        graph_sha256 = release_tag_module.tag_graph_sha256(
            release_tag_module.release_tags(cwd=self.repo)
        )

        with self.assertRaisesRegex(
            ReleaseStateError, "already has remote release tag"
        ):
            self.reconcile(self.repo, graph_sha256=graph_sha256)

        self.assertEqual(
            git(
                self.repo,
                "ls-remote",
                "--refs",
                "origin",
                f"refs/tags/{self.expected.tag}",
            ),
            "",
        )

    def test_rejected_creation_never_creates_or_rewrites_a_remote_tag(self) -> None:
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)

        with self.assertRaisesRegex(ReleaseStateError, "could not create"):
            self.reconcile(self.repo)

        self.assertEqual(
            git(
                self.repo,
                "ls-remote",
                "--refs",
                "origin",
                f"refs/tags/{self.expected.tag}",
            ),
            "",
        )
        self.assertEqual(git(self.repo, "tag", "--list", self.expected.tag), "")

    def test_interrupted_publish_recovers_from_remote_tag(self) -> None:
        self.reconcile(self.repo)
        recovery = self.no_tag_clone("recovery")

        result = self.reconcile(recovery)

        self.assertEqual(result, "existing")
        self.assertFalse(bool(git(recovery, "tag", "--list", self.expected.tag)))

    def test_coordination_branch_must_match_the_latest_release_tag(self) -> None:
        self.reconcile(self.repo)
        next_commit = commit(self.repo, "fix: uncoordinated branch move", "next.txt")
        git(
            self.repo,
            "push",
            "origin",
            f"{next_commit}:{release_tag_module.RELEASE_COORDINATION_REF}",
        )
        expected = TagMetadata("v1.2.4", next_commit, "a" * 64, "1", "b" * 64)
        graph_sha256 = release_tag_module.tag_graph_sha256(
            release_tag_module.remote_release_tags("origin", cwd=self.repo)
        )

        with self.assertRaisesRegex(ReleaseStateError, "coordination branch conflicts"):
            self.reconcile(self.repo, expected, graph_sha256=graph_sha256)
        self.assertEqual(
            git(
                self.repo,
                "ls-remote",
                "--refs",
                "origin",
                f"refs/tags/{expected.tag}",
            ),
            "",
        )

    def test_existing_tag_rejects_a_stale_recovery_graph(self) -> None:
        self.reconcile(self.repo)
        planned_graph = release_tag_module.tag_graph_sha256(
            release_tag_module.remote_release_tags("origin", cwd=self.repo)
        )
        later = commit(self.repo, "fix: later release", "later-release.txt")
        annotated_tag(self.repo, "v1.2.4", later)
        git(self.repo, "push", "origin", "refs/tags/v1.2.4")

        with self.assertRaisesRegex(ReleaseStateError, "graph changed"):
            self.reconcile(self.repo, graph_sha256=planned_graph)

    def test_concurrent_creators_converge_without_moving_the_tag(self) -> None:
        first = self.no_tag_clone("race-first")
        second = self.no_tag_clone("race-second")
        git(second, "config", "user.name", "Second Release Test")
        barrier = threading.Barrier(2)
        original = release_tag_module.remote_release_tags
        calls = threading.local()

        def synchronized_remote_check(
            remote: str, *, cwd: Path | None = None
        ) -> list[release_tag_module.ReleaseTag]:
            result = original(remote, cwd=cwd)
            count = getattr(calls, "count", 0)
            calls.count = count + 1
            if count == 0:
                barrier.wait(timeout=5)
            return result

        with mock.patch.object(
            release_tag_module, "remote_release_tags", synchronized_remote_check
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda repo: self.reconcile(repo),
                        (first, second),
                    )
                )

        self.assertCountEqual(results, ["created", "existing"])

    def test_atomic_coordination_rejects_distinct_concurrent_tags(self) -> None:
        first = self.no_tag_clone("distinct-race-first")
        second = self.no_tag_clone("distinct-race-second")
        expectations = (
            TagMetadata("v1.2.3", self.initial_commit, "a" * 64, "1", "b" * 64),
            TagMetadata("v1.2.4", self.initial_commit, "a" * 64, "1", "b" * 64),
        )
        barrier = threading.Barrier(2)
        original = release_tag_module.remote_release_tags
        calls = threading.local()

        def synchronized_remote_check(
            remote: str, *, cwd: Path | None = None
        ) -> list[release_tag_module.ReleaseTag]:
            result = original(remote, cwd=cwd)
            count = getattr(calls, "count", 0)
            calls.count = count + 1
            if count == 0:
                barrier.wait(timeout=5)
            return result

        def publish(candidate: tuple[Path, TagMetadata]) -> str:
            repo, expected = candidate
            try:
                return self.reconcile(repo, expected)
            except ReleaseStateError:
                return "rejected"

        with mock.patch.object(
            release_tag_module, "remote_release_tags", synchronized_remote_check
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(publish, zip((first, second), expectations))
                )

        self.assertCountEqual(results, ["created", "rejected"])
        remote_tags = release_tag_module.remote_release_tags("origin", cwd=self.repo)
        self.assertEqual(len(remote_tags), 1)
        self.assertEqual(remote_tags[0].commit, self.initial_commit)
        self.assertEqual(
            release_tag_module.remote_ref_object(
                "origin",
                release_tag_module.RELEASE_COORDINATION_REF,
                cwd=self.repo,
            ),
            self.initial_commit,
        )


if __name__ == "__main__":
    unittest.main()
