from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

import yaml

from tests.fuzz.wrapper_boundary import MAX_INPUT_BYTES, SUBPROCESS_TIMEOUT_SECONDS


ROOT = Path(__file__).resolve().parents[1]
FUZZ_WORKFLOW = ROOT / ".github" / "workflows" / "fuzz.yml"
FUZZ_RUNNER = ROOT / "scripts" / "run-atheris.sh"
ATHERIS_TARGET = ROOT / "tests" / "fuzz" / "fuzz_wrapper.py"


class FuzzBoundarySecurityTests(unittest.TestCase):
    def test_shared_harness_has_documented_hard_limits(self) -> None:
        self.assertEqual(MAX_INPUT_BYTES, 65_536)
        self.assertEqual(SUBPROCESS_TIMEOUT_SECONDS, 2.0)

    def test_runner_rejects_an_input_limit_over_the_hard_cap(self) -> None:
        environment = {
            "FUZZ_MAX_LEN": "65537",
            "HOME": os.environ.get("HOME", "/tmp"),
            "PATH": "/usr/bin:/bin",
        }

        completed = subprocess.run(
            [str(FUZZ_RUNNER)],
            check=False,
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=2,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("cannot exceed 65536", completed.stderr)

    def test_scheduled_workflow_is_bounded_and_read_only(self) -> None:
        workflow = yaml.safe_load(FUZZ_WORKFLOW.read_text(encoding="utf-8"))
        job = workflow["jobs"]["wrapper-fuzz"]
        campaign = next(step for step in job["steps"] if step["name"] == "Run bounded campaign")
        upload = next(
            step
            for step in job["steps"]
            if step["name"] == "Upload synthetic crash reproducers"
        )

        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(job["timeout-minutes"], 20)
        self.assertEqual(job["env"]["FUZZ_MAX_LEN"], "65536")
        self.assertEqual(job["env"]["FUZZ_MAX_TOTAL_TIME"], "120")
        self.assertEqual(job["env"]["FUZZ_UNIT_TIMEOUT"], "5")
        self.assertEqual(job["env"]["FUZZ_RSS_LIMIT_MB"], "2048")
        self.assertIn("runner.temp", campaign["env"]["FUZZ_ARTIFACT_DIR"])
        self.assertIn("runner.temp", campaign["env"]["FUZZ_CORPUS_DIR"])
        self.assertEqual(upload["if"], "failure() && steps.campaign.outcome == 'failure'")
        self.assertEqual(upload["with"]["retention-days"], 7)

    def test_fuzz_workflow_actions_are_pinned_to_commits(self) -> None:
        workflow = yaml.safe_load(FUZZ_WORKFLOW.read_text(encoding="utf-8"))

        for step in workflow["jobs"]["wrapper-fuzz"]["steps"]:
            uses = step.get("uses")
            if uses is not None:
                with self.subTest(action=uses):
                    self.assertRegex(uses, r"^[^@]+@[0-9a-f]{40}$")

    def test_atheris_target_has_a_literal_import(self) -> None:
        self.assertIn("\nimport atheris\n", ATHERIS_TARGET.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
