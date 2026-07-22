from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_metadata import verify_selected_pypi_artifact  # noqa: E402
from release_state import (  # noqa: E402
    ReleaseStateError,
    parse_manifest,
    read_manifest,
    read_manifest_at_commit,
)


MANIFEST = ROOT / "action-compatibility.json"


class ActionCompatibilityTests(unittest.TestCase):
    def test_manifest_is_versionless_and_valid(self) -> None:
        manifest = read_manifest(MANIFEST)
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(set(document), {"python_versions", "vexcalibur_package"})
        self.assertNotIn("action_version", document)
        self.assertEqual(manifest.package_spec, document["vexcalibur_package"])
        self.assertRegex(manifest.sha256, r"^[0-9a-f]{64}$")

    def test_manifest_rejects_unknown_missing_and_duplicate_fields(self) -> None:
        valid = json.loads(MANIFEST.read_text(encoding="utf-8"))
        documents = {
            "unknown": {**valid, "runner": "ubuntu-latest"},
            "missing": {"python_versions": valid["python_versions"]},
        }
        for name, document in documents.items():
            with self.subTest(name=name), self.assertRaises(ReleaseStateError):
                parse_manifest(json.dumps(document).encode())

        duplicate = (
            b'{"python_versions":["3.10"],'
            b'"python_versions":["3.14"],'
            b'"vexcalibur_package":"vexcalibur==1.0"}'
        )
        with self.assertRaisesRegex(ReleaseStateError, "duplicate key"):
            parse_manifest(duplicate)

    def test_manifest_rejects_malformed_values(self) -> None:
        valid = json.loads(MANIFEST.read_text(encoding="utf-8"))
        invalid_values = (
            {**valid, "python_versions": []},
            {**valid, "python_versions": ["3.14", "3.10"]},
            {**valid, "python_versions": ["3.10", "3.10"]},
            {**valid, "python_versions": ["latest"]},
            {**valid, "vexcalibur_package": "vexcalibur>=1"},
            {**valid, "vexcalibur_package": "vexcalibur==1."},
            {**valid, "vexcalibur_package": "vexcalibur==1..2"},
            {**valid, "vexcalibur_package": "vexcalibur==1.2"},
            {**valid, "vexcalibur_package": 1},
        )
        for document in invalid_values:
            with self.subTest(document=document), self.assertRaises(ReleaseStateError):
                parse_manifest(json.dumps(document).encode())

    def test_manifest_rejects_invalid_json_encoding_and_root_types(self) -> None:
        documents = (
            b"{",
            b"\xff",
            b"[]",
            b"null",
            b'"string"',
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(ReleaseStateError):
                parse_manifest(document)

    def test_action_default_python_is_declared_compatible(self) -> None:
        manifest = read_manifest(MANIFEST)
        action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))

        self.assertIn(
            action["inputs"]["python-version"]["default"],
            manifest.python_versions,
        )

    def test_ci_consumes_only_manifest_claims(self) -> None:
        workflow_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        workflow = yaml.safe_load(workflow_text)
        resolve_job = workflow["jobs"]["resolve-released-package"]

        self.assertNotIn("VEXCALIBUR_RELEASE_ACTION_REF", workflow_text)
        self.assertNotIn("VEXCALIBUR_RELEASE_PACKAGE_VERSION", workflow_text)
        self.assertEqual(
            resolve_job["outputs"]["package-spec"],
            "${{ steps.compatibility.outputs.package_spec }}",
        )
        self.assertEqual(
            next(
                step["run"]
                for step in resolve_job["steps"]
                if step["name"] == "Read compatibility declaration"
            ),
            'scripts/release.py manifest --ref "${GITHUB_SHA}" >> "${GITHUB_OUTPUT}"',
        )

    def test_commit_reader_rejects_a_symlinked_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-qb", "main"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repository,
                check=True,
            )
            (repository / "manifest-target.json").write_text(
                MANIFEST.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (repository / "action-compatibility.json").symlink_to(
                "manifest-target.json"
            )
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "test: symlink manifest"],
                cwd=repository,
                check=True,
            )
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            with self.assertRaisesRegex(ReleaseStateError, "must be a regular file"):
                read_manifest_at_commit(commit_sha, cwd=repository)

    def test_selected_pypi_artifact_must_be_exact_and_not_yanked(self) -> None:
        artifact_url = (
            "https://files.pythonhosted.org/vexcalibur-1.2.3-py3-none-any.whl"
        )
        report = {
            "install": [
                {
                    "download_info": {"url": artifact_url},
                    "metadata": {"name": "Vexcalibur", "version": "1.2.3"},
                    "requested": True,
                }
            ]
        }
        release = {
            "info": {"name": "vexcalibur", "version": "1.2.3"},
            "urls": [
                {
                    "digests": {"sha256": "a" * 64},
                    "filename": "vexcalibur-1.2.3-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "url": artifact_url,
                    "yanked": False,
                },
                {"url": "https://files.pythonhosted.org/source.tar.gz", "yanked": True},
            ],
        }

        artifact = verify_selected_pypi_artifact(
            report,
            release,
            package_spec="vexcalibur==1.2.3",
        )
        self.assertEqual(artifact.url, artifact_url)
        self.assertEqual(artifact.filename, "vexcalibur-1.2.3-py3-none-any.whl")
        self.assertEqual(artifact.sha256, "a" * 64)
        release["urls"][0]["yanked"] = True
        with self.assertRaisesRegex(ReleaseStateError, "selected a yanked"):
            verify_selected_pypi_artifact(
                report,
                release,
                package_spec="vexcalibur==1.2.3",
            )

    def test_ci_verifies_the_artifact_pip_selects(self) -> None:
        workflow_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        workflow = yaml.safe_load(workflow_text)
        verify_job = workflow["jobs"]["verify-released-package-artifact"]
        resolve_step = next(
            step
            for step in verify_job["steps"]
            if step["name"] == "Resolve declared package artifact"
        )

        self.assertIn("python -I -m pip", resolve_step["run"])
        self.assertIn("--isolated", resolve_step["run"])
        self.assertIn("--no-cache-dir", resolve_step["run"])
        self.assertIn("--no-deps", resolve_step["run"])
        self.assertIn("--only-binary=:all:", resolve_step["run"])
        self.assertIn("--dry-run", workflow_text)
        self.assertIn("--ignore-installed", workflow_text)
        self.assertIn("--report", workflow_text)
        self.assertIn("scripts/release.py verify-package-artifact", workflow_text)
        self.assertIn("sha256sum --check --strict", workflow_text)
        self.assertIn("Upload verified package artifact", workflow_text)
        upload_step = next(
            step
            for step in verify_job["steps"]
            if step["name"] == "Upload verified package artifact"
        )
        self.assertEqual(upload_step["with"]["overwrite"], True)
        self.assertEqual(
            upload_step["with"]["name"],
            "${{ env.VEXCALIBUR_RELEASE_PACKAGE_ARTIFACT }}-python-"
            "${{ matrix.python-version }}",
        )
        self.assertNotIn("github.run_attempt", workflow_text)
        self.assertNotIn("artifact-attempt", workflow_text)
        for job_name in (
            "released-package-help",
            "released-package-query-osv",
            "released-package-openvex",
            "released-package-csaf",
        ):
            with self.subTest(job=job_name):
                job = workflow["jobs"][job_name]
                self.assertIn("verify-released-package-artifact", job["needs"])
                self.assertIn(
                    "Resolve verified Vexcalibur wheel",
                    [step["name"] for step in job["steps"]],
                )
                wheel_step = next(
                    step
                    for step in job["steps"]
                    if step["name"] == "Resolve verified Vexcalibur wheel"
                )
                self.assertEqual(
                    wheel_step["with"]["artifact-name"],
                    "${{ env.VEXCALIBUR_RELEASE_PACKAGE_ARTIFACT }}-python-"
                    "${{ matrix.python-version }}",
                )


if __name__ == "__main__":
    unittest.main()
