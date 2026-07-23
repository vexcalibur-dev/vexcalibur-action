from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
FUZZ_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "fuzz.yml"
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
        packages = locked_packages(path)

        self.assert_lock_has_no_alternate_sources(path)
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

        self.assertEqual(
            set(development_packages),
            set(release_packages) | {"hypothesis", "ruff", "sortedcontainers"},
        )
        for name, release_entry in release_packages.items():
            with self.subTest(package=name):
                self.assertEqual(development_packages[name], release_entry)

    def test_fuzz_lock_extends_the_development_lock(self) -> None:
        path = ROOT / "requirements-fuzz.txt"
        self.assert_lock_has_no_alternate_sources(path)
        development_packages = locked_packages(ROOT / "requirements-dev.txt")
        fuzz_packages = locked_packages(path)

        self.assertEqual(
            set(fuzz_packages) - set(development_packages),
            {
                "atheris",
                "boolean-py",
                "cachecontrol",
                "cyclonedx-python-lib",
                "defusedxml",
                "filelock",
                "license-expression",
                "markdown-it-py",
                "mdurl",
                "msgpack",
                "packageurl-python",
                "packaging",
                "pip",
                "pip-api",
                "pip-audit",
                "pip-requirements-parser",
                "platformdirs",
                "py-serializable",
                "pygments",
                "pyparsing",
                "rich",
                "tomli",
                "tomli-w",
            },
        )
        for name, development_entry in development_packages.items():
            with self.subTest(package=name):
                self.assertEqual(fuzz_packages[name], development_entry)
        for name, (version, hashes) in fuzz_packages.items():
            with self.subTest(package=name):
                self.assertRegex(version, r"^[A-Za-z0-9][A-Za-z0-9.!+_-]*$")
                self.assertTrue(hashes, f"{name} has no allowed distribution hash")

    def test_input_requirements_use_exact_direct_pins(self) -> None:
        for filename in (
            "requirements-release.in",
            "requirements-dev.in",
            "requirements-fuzz.in",
        ):
            with self.subTest(filename=filename):
                lines = (ROOT / filename).read_text(encoding="utf-8").splitlines()
                for raw_line in lines:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("-r "):
                        continue
                    self.assertIsNotNone(PIN_PATTERN.fullmatch(line))

    def test_direct_requirements_match_their_generated_locks(self) -> None:
        for input_filename, output_filename in (
            ("requirements-release.in", "requirements-release.txt"),
            ("requirements-dev.in", "requirements-dev.txt"),
            ("requirements-fuzz.in", "requirements-fuzz.txt"),
        ):
            locked = locked_packages(ROOT / output_filename)
            for raw_line in (
                (ROOT / input_filename).read_text(encoding="utf-8").splitlines()
            ):
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith("-r "):
                    continue
                pin_match = PIN_PATTERN.fullmatch(line)
                if pin_match is None:
                    self.fail(f"{input_filename} has a non-pin requirement: {line}")
                name = pin_match.group(1).lower().replace("_", "-")
                with self.subTest(input=input_filename, package=name):
                    self.assertIn(name, locked)
                    self.assertEqual(locked[name][0], pin_match.group(2))

    def test_locks_declare_renovate_compatible_uv_compile_commands(self) -> None:
        for output_filename, input_filename in (
            ("requirements-release.txt", "requirements-release.in"),
            ("requirements-dev.txt", "requirements-dev.in"),
            ("requirements-fuzz.txt", "requirements-fuzz.in"),
        ):
            with self.subTest(output=output_filename):
                header = "\n".join(
                    (ROOT / output_filename)
                    .read_text(encoding="utf-8")
                    .splitlines()[:2]
                )
                self.assertIn("#    uv pip compile", header)
                self.assertIn(
                    "--constraints=requirements-build-constraints.txt",
                    header,
                )
                self.assertIn(
                    f"--output-file={output_filename} {input_filename}",
                    header,
                )

    def test_build_constraint_requires_binary_distributions(self) -> None:
        build_constraints = (ROOT / "requirements-build-constraints.txt").read_text(
            encoding="utf-8"
        )

        self.assertEqual(build_constraints, "--only-binary :all:\n")

    def test_renovate_update_policy_is_explicit(self) -> None:
        configuration = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))

        self.assertEqual(configuration["timezone"], "America/Chicago")
        self.assertEqual(configuration["schedule"], ["* 8-11 * * 1"])
        self.assertEqual(configuration["prHourlyLimit"], 2)
        self.assertEqual(
            configuration["enabledManagers"],
            ["github-actions", "pip-compile"],
        )
        self.assertEqual(
            configuration["pip-compile"],
            {
                "managerFilePatterns": [
                    "/(^|/)requirements-(dev|fuzz|release)\\.txt$/",
                ],
            },
        )
        self.assertEqual(configuration["pip_requirements"], {"enabled": False})
        self.assertEqual(configuration["constraints"], {"uv": "0.11.28"})
        self.assertEqual(configuration["vulnerabilityAlerts"], {"enabled": False})
        self.assertIn("helpers:pinGitHubActionDigests", configuration["extends"])
        self.assertNotIn("automergeType", configuration)
        self.assertNotIn("platformAutomerge", configuration)
        self.assertEqual(
            configuration["packageRules"],
            [
                {
                    "description": "Group reviewable GitHub Actions updates.",
                    "matchManagers": ["github-actions"],
                    "groupName": "GitHub Actions",
                },
                {
                    "description": "Group reviewable compiled Python updates.",
                    "matchManagers": ["pip-compile"],
                    "groupName": "Python requirements",
                },
                {
                    "description": (
                        "Leave coupled runtime versions to manual toolchain updates."
                    ),
                    "matchManagers": ["github-actions"],
                    "matchDepTypes": ["uses-with"],
                    "enabled": False,
                },
            ],
        )

    def test_root_action_pin_has_renovate_version_hint(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")

        self.assertRegex(
            action,
            (
                r"uses: actions/setup-python@[0-9a-f]{40}"
                r"  # v[0-9]+\.[0-9]+\.[0-9]+"
            ),
        )

    def test_clean_runner_release_commands_start_without_site_packages(self) -> None:
        commands = (
            "manifest",
            "render-notes",
            "reconcile-tag",
            "verify-tag",
            "verify-release",
            "verify-rulesets",
            "attest-rulesets",
            "verify-attested-rulesets",
            "verify-package-artifact",
        )
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-S",
                        str(ROOT / "scripts/release.py"),
                        command,
                        "--help",
                    ],
                    cwd=ROOT,
                    check=False,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

        manifest = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "scripts/release.py"),
                "manifest",
                "--path",
                str(ROOT / "action-compatibility.json"),
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(manifest.returncode, 0, manifest.stderr)


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

    def test_partial_reruns_reuse_the_producer_artifact_name(self) -> None:
        generator = self.jobs["generate-release-notes"]
        scanner = self.jobs["scan-release-notes"]
        publisher = self.jobs["publish-release"]

        self.assertEqual(
            generator["outputs"]["artifact_name"],
            "${{ steps.artifact.outputs.name }}",
        )
        self.assertEqual(
            scanner["outputs"]["artifact_name"],
            "${{ steps.artifact.outputs.name }}",
        )
        self.assertEqual(
            step_named(scanner, "Download generated release notes")["with"]["name"],
            "${{ needs.generate-release-notes.outputs.artifact_name }}",
        )
        self.assertEqual(
            step_named(publisher, "Download scanned release notes")["with"]["name"],
            "${{ needs.scan-release-notes.outputs.artifact_name }}",
        )

    def test_publication_token_is_minted_only_after_digest_verification(self) -> None:
        publisher = self.jobs["publish-release"]
        publisher_steps = publisher["steps"]
        token_indexes = [
            index
            for index, step in enumerate(publisher_steps)
            if step.get("id") == "publication-token"
        ]
        self.assertEqual(len(token_indexes), 1)
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

    def test_release_checkouts_use_the_intended_trust_boundary(self) -> None:
        scanner_checkout = step_named(
            self.jobs["scan-release-notes"], "Checkout scanner policy"
        )
        publisher_checkout = step_named(self.jobs["publish-release"], "Checkout")

        self.assertEqual(scanner_checkout["with"]["ref"], "${{ github.sha }}")
        self.assertEqual(publisher_checkout["with"]["ref"], "${{ github.sha }}")

    def test_release_identity_comes_from_tags_not_tracked_versions(self) -> None:
        workflow_text = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
        resolve = self.jobs["resolve"]

        self.assertNotIn("Verify compatibility table", workflow_text)
        self.assertNotIn("RELEASE_VERSION", workflow_text)
        self.assertNotIn("compatibility.md", workflow_text)
        self.assertEqual(resolve["outputs"]["tag"], "${{ steps.release.outputs.tag }}")
        self.assertEqual(resolve["outputs"]["sha"], "${{ steps.release.outputs.sha }}")
        self.assertEqual(
            resolve["outputs"]["operation"],
            "${{ steps.release.outputs.operation }}",
        )
        planner = step_named(resolve, "Determine release tag")
        self.assertEqual(
            planner["env"]["MANUAL_TAG"],
            "${{ github.event.inputs.tag || '' }}",
        )

    def test_compatibility_metadata_is_snapshotted_and_scanned(self) -> None:
        resolve = self.jobs["resolve"]
        generator = self.jobs["generate-release-notes"]
        compatibility = step_named(resolve, "Resolve compatibility metadata")
        notes = step_named(generator, "Generate release notes")["run"]
        release_metadata = (ROOT / "scripts/release_metadata.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts/release.py manifest", compatibility["run"])
        self.assertIn('--ref "${RELEASE_SHA}"', compatibility["run"])
        self.assertEqual(
            resolve["outputs"]["manifest_sha256"],
            "${{ steps.compatibility.outputs.manifest_sha256 }}",
        )
        self.assertIn("scripts/release.py render-notes", notes)
        self.assertIn("vexcalibur-action-release-metadata", release_metadata)
        self.assertIn("compatibility_sha256=", release_metadata)
        self.assertLess(
            next(
                index
                for index, step in enumerate(generator["steps"])
                if step["name"] == "Generate release notes"
            ),
            next(
                index
                for index, step in enumerate(generator["steps"])
                if step["name"] == "Record release-note digest"
            ),
        )

    def test_tag_reconciliation_never_moves_or_deletes_a_tag(self) -> None:
        publisher = self.jobs["publish-release"]
        reconcile = step_named(publisher, "Reconcile immutable release tag")["run"]
        release_tags = (ROOT / "scripts/release_tags.py").read_text(encoding="utf-8")
        release_metadata = (ROOT / "scripts/release_metadata.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts/release.py reconcile-tag", reconcile)
        self.assertIn(
            '--expected-tag-graph-sha256 "${EXPECTED_TAG_GRAPH_SHA256}"',
            reconcile,
        )
        self.assertIn('--notes-sha256 "${NOTES_SHA256}"', reconcile)
        self.assertIn("def reconcile_remote_tag(", release_tags)
        self.assertIn("Compatibility-SHA256:", release_metadata)
        self.assertIn("Release-Notes-SHA256:", release_metadata)
        self.assertNotIn("--force", reconcile)
        self.assertNotIn('"--force"', release_tags)
        self.assertNotIn('"tag", "--delete"', release_tags)
        self.assertNotIn('"push", "--delete"', release_tags)
        self.assertNotIn('"tag", "--force"', release_tags)
        self.assertNotIn('remote set-url origin "https://x-access-token:', reconcile)
        self.assertIn("GIT_CONFIG_VALUE_0", reconcile)
        self.assertIn('"--atomic"', release_tags)
        self.assertIn('"--force-with-lease=', release_tags)
        self.assertIn("refs/heads/release-coordination", release_tags)
        self.assertNotIn("--expected-remote-ref", reconcile)

    def test_release_policy_is_checked_before_tag_publication(self) -> None:
        publisher = self.jobs["publish-release"]
        names = [step["name"] for step in publisher["steps"]]
        token = step_named(publisher, "Generate publication token")
        policy = step_named(publisher, "Require enforced immutable releases")
        rules = step_named(publisher, "Require attested append-only release tag rules")

        self.assertEqual(token["with"]["permission-administration"], "read")
        self.assertIn(".enforced_by_owner", policy["run"])
        self.assertIn("$'true\\ttrue'", policy["run"])
        self.assertEqual(
            rules["env"]["POLICY_ATTESTATION"],
            "${{ vars.RELEASE_POLICY_ATTESTATION }}",
        )
        self.assertIn("scripts/release.py verify-attested-rulesets", rules["run"])
        self.assertIn('--attestation "${policy_dir}/attestation.json"', rules["run"])
        self.assertLess(
            names.index("Require enforced immutable releases"),
            names.index("Reconcile immutable release tag"),
        )
        self.assertLess(
            names.index("Require attested append-only release tag rules"),
            names.index("Reconcile immutable release tag"),
        )

    def test_ci_wait_accepts_any_retained_successful_run(self) -> None:
        step = step_named(self.jobs["wait-for-ci"], "Wait for tooling and release CI")
        wait = step["run"]

        self.assertIn("--limit 1000", wait)
        self.assertIn("if any(", wait)
        self.assertIn('run["conclusion"] == "success"', wait)
        self.assertIn("A retained ${role} CI run passed", wait)
        self.assertEqual(step["env"]["TOOLING_SHA"], "${{ github.sha }}")
        self.assertEqual(
            step["env"]["RELEASE_SHA"],
            "${{ needs.resolve.outputs.sha }}",
        )
        self.assertIn('wait_for_ci "${TOOLING_SHA}" "release-tooling"', wait)
        self.assertIn('wait_for_ci "${RELEASE_SHA}" "release-target"', wait)

    def test_existing_release_is_verified_instead_of_accepted_by_presence(self) -> None:
        publisher = self.jobs["publish-release"]
        create_release = step_named(publisher, "Create GitHub Release")["run"]

        self.assertEqual(create_release.count("scripts/release.py verify-release"), 1)
        self.assertIn("verify_release()", create_release)
        self.assertIn('if ! gh "${args[@]}"', create_release)
        self.assertIn("A concurrent publisher created", create_release)
        self.assertIn('--release-json "${release_json}"', create_release)
        self.assertIn(
            '--notes-file "${RUNNER_TEMP}/scanned-release-notes/release-notes.md"',
            create_release,
        )
        self.assertIn('--expected-author "${EXPECTED_AUTHOR}"', create_release)
        self.assertIn('--tag "${RELEASE_TAG}"', create_release)
        self.assertIn('--commit "${RELEASE_SHA}"', create_release)
        self.assertIn(
            '--compatibility-sha256 "${COMPATIBILITY_SHA256}"', create_release
        )
        self.assertIn('grep -Fq "HTTP 404"', create_release)
        self.assertIn('cat "${release_error}" >&2', create_release)
        self.assertIn(
            'gh api "repos/${GITHUB_REPOSITORY}/releases/tags/${RELEASE_TAG}"',
            create_release,
        )

    def test_latest_release_state_is_explicit_and_verified(self) -> None:
        resolve = self.jobs["resolve"]
        publisher = self.jobs["publish-release"]
        create_release = step_named(publisher, "Create GitHub Release")["run"]
        verify_latest = step_named(publisher, "Verify latest-release projection")["run"]

        self.assertEqual(
            resolve["outputs"]["make_latest"],
            "${{ steps.release.outputs.make_latest }}",
        )
        self.assertIn("args+=(--latest)", create_release)
        self.assertIn("args+=(--latest=false)", create_release)
        self.assertIn("/releases/latest", verify_latest)
        self.assertIn("incorrectly promoted an older release", verify_latest)

    def test_recovery_can_target_an_older_reachable_commit(self) -> None:
        resolve_compatibility = step_named(
            self.jobs["resolve"], "Resolve compatibility metadata"
        )
        self.assertIn(
            'git merge-base --is-ancestor "${RELEASE_SHA}" HEAD',
            resolve_compatibility["run"],
        )

    def test_version_manager_manifests_are_consistent(self) -> None:
        tool_versions = {
            name: version
            for name, version in (
                line.split(maxsplit=1)
                for line in (ROOT / ".tool-versions")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        }
        with (ROOT / "mise.toml").open("rb") as stream:
            mise_configuration = tomllib.load(stream)
        with (ROOT / "mise.lock").open("rb") as stream:
            mise_lock = tomllib.load(stream)

        self.assertTrue(mise_configuration["settings"]["lockfile"])
        self.assertEqual(mise_configuration["tools"], tool_versions)
        self.assertEqual(set(mise_lock["tools"]), set(tool_versions))
        for name, version in tool_versions.items():
            with self.subTest(tool=name):
                lock_entries = mise_lock["tools"][name]
                self.assertEqual(len(lock_entries), 1)
                lock_entry = lock_entries[0]
                self.assertEqual(lock_entry["version"], version)
                for platform in ("linux-x64", "macos-arm64", "macos-x64"):
                    asset = lock_entry[f"platforms.{platform}"]
                    self.assertRegex(asset["checksum"], r"^sha256:[0-9a-f]{64}$")
                    self.assertTrue(asset["url"].startswith("https://"))

        for workflow_path in (
            CI_WORKFLOW_PATH,
            FUZZ_WORKFLOW_PATH,
            RELEASE_WORKFLOW_PATH,
        ):
            workflow = load_workflow(workflow_path)
            for job_name, job in workflow["jobs"].items():
                for step in job.get("steps", []):
                    if not step.get("uses", "").startswith("actions/setup-python@"):
                        continue
                    with self.subTest(workflow=workflow_path, step=step["name"]):
                        expected_version = tool_versions["python"]
                        if (
                            workflow_path == CI_WORKFLOW_PATH
                            and job_name == "verify-released-package-artifact"
                        ):
                            expected_version = "${{ matrix.python-version }}"
                        self.assertEqual(
                            step["with"]["python-version"], expected_version
                        )

        refresh_script = (ROOT / "scripts/refresh-requirements.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"--python-version {tool_versions['python']}", refresh_script)

    def test_artifact_digest_is_verified_at_each_boundary(self) -> None:
        generator = self.jobs["generate-release-notes"]
        scanner = self.jobs["scan-release-notes"]
        publisher = self.jobs["publish-release"]

        self.assertEqual(
            generator["outputs"]["notes_sha256"],
            "${{ steps.notes-digest.outputs.sha256 }}",
        )
        self.assertIn(
            "sha256sum",
            step_named(generator, "Record release-note digest")["run"],
        )
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
        self.assertIn("generate-release-notes", publisher["needs"])
        self.assertEqual(
            scanned_verifier["env"]["GENERATOR_SHA256"],
            "${{ needs.generate-release-notes.outputs.notes_sha256 }}",
        )
        self.assertEqual(
            scanned_verifier["env"]["SCANNER_SHA256"],
            "${{ needs.scan-release-notes.outputs.notes_sha256 }}",
        )
        self.assertIn(
            '"${SCANNER_SHA256}" != "${GENERATOR_SHA256}"',
            scanned_verifier["run"],
        )
        self.assertIn("sha256sum", scanned_verifier["run"])
        reconcile = step_named(publisher, "Reconcile immutable release tag")
        self.assertEqual(
            reconcile["env"]["NOTES_SHA256"],
            "${{ needs.generate-release-notes.outputs.notes_sha256 }}",
        )
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            step_named(publisher, "Download scanned release notes")["uses"],
        )

    def test_requirement_installs_are_hash_checked_and_wheel_only(self) -> None:
        workflows = (
            load_workflow(CI_WORKFLOW_PATH),
            load_workflow(FUZZ_WORKFLOW_PATH),
            self.workflow,
        )
        checked = 0
        for workflow in workflows:
            for job in workflow["jobs"].values():
                for step in job["steps"]:
                    run = step.get("run", "")
                    if (
                        "pip install" not in run
                        or "requirements-" not in run
                        or ".txt" not in run
                    ):
                        continue
                    checked += 1
                    self.assertIn("--only-binary=:all:", run)
                    self.assertIn("--require-hashes", run)
        self.assertEqual(checked, 5)
        self.assertIn(
            "-r requirements-release.txt",
            step_named(
                self.jobs["resolve"],
                "Install release planner dependencies",
            )["run"],
        )
        self.assertIn(
            "-r requirements-release.txt",
            step_named(
                self.jobs["scan-release-notes"],
                "Install release note scanner",
            )["run"],
        )

        ci_jobs = load_workflow(CI_WORKFLOW_PATH)["jobs"]
        self.assertIn(
            "-r requirements-dev.txt",
            step_named(ci_jobs["quality"], "Install development dependencies")["run"],
        )
        self.assertIn(
            "-r requirements-dev.txt",
            step_named(
                ci_jobs["wrapper-fuzz-smoke"],
                "Install development dependencies",
            )["run"],
        )
        fuzz_jobs = load_workflow(FUZZ_WORKFLOW_PATH)["jobs"]
        self.assertIn(
            "-r requirements-fuzz.txt",
            step_named(fuzz_jobs["wrapper-fuzz"], "Install fuzzing dependencies")[
                "run"
            ],
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
