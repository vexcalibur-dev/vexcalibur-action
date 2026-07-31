from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import (
    execution_report,
    managed_install_env,
    read_github_outputs,
    run_script,
)


class RunVexcaliburExecutionReportTests(unittest.TestCase):
    def test_generate_publishes_outputs_when_package_supports_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": (
                        "generate\n"
                        "/tmp/input.json\n"
                        "--offline\n"
                        "--findings-file\n"
                        "/tmp/findings.json\n"
                        "--\n"
                        "--literal-value\n"
                    ),
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": execution_report(),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = calls_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(arguments[0:2], ["generate", "--execution-report"])
            report_path = Path(arguments[2])
            self.assertEqual(report_path.name, "execution-report.json")
            self.assertTrue(report_path.parent.name.startswith("report."))
            self.assertEqual(
                arguments[3:],
                [
                    "/tmp/input.json",
                    "--offline",
                    "--findings-file",
                    "/tmp/findings.json",
                    "--",
                    "--literal-value",
                ],
            )
            outputs = read_github_outputs(github_output)
            self.assertEqual(outputs["execution-report-path"], str(report_path))
            self.assertEqual(outputs["vexcalibur-version"], "0.4.2")
            self.assertEqual(outputs["finding-count"], "2")
            self.assertEqual(outputs["document-sha256"], "a" * 64)

    def test_generate_with_older_package_keeps_original_args_and_empty_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8"),
                "generate\n/tmp/input.json\n--offline\n",
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_generate_help_keeps_original_args_and_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n--help",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8"),
                "generate\n--help\n",
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_literal_help_value_uses_compatibility_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": ("generate\n/tmp/input.json\n--output\n--help"),
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8").splitlines(),
                ["generate", "/tmp/input.json", "--output", "--help"],
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_future_boolean_flag_before_help_uses_compatibility_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": (
                        "generate\n/tmp/input.json\n--future-boolean\n--help"
                    ),
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8").splitlines(),
                ["generate", "/tmp/input.json", "--future-boolean", "--help"],
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_generate_help_after_input_does_not_require_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--help",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8").splitlines()[-2:],
                ["/tmp/input.json", "--help"],
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_generate_help_after_boolean_flag_does_not_require_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": ("generate\n/tmp/input.json\n--offline\n--help"),
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8").splitlines(),
                ["generate", "/tmp/input.json", "--offline", "--help"],
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_eager_help_before_input_keeps_original_arguments(self) -> None:
        cases = (
            "generate\n--help\n/tmp/input.json",
            "--\ngenerate\n--help\n/tmp/input.json",
            "generate\n-\n--help",
            "--\ngenerate\n-\n--help",
        )
        for raw_args in cases:
            with (
                self.subTest(raw_args=raw_args),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root = Path(tmpdir)
                calls_file = root / "calls.txt"
                python_calls = root / "python-calls.txt"
                github_output = root / "github-output"
                github_output.touch()
                env = managed_install_env(root, calls_file, python_calls)
                env.update(
                    {
                        "VEXCALIBUR_ARGS": raw_args,
                        "GITHUB_OUTPUT": str(github_output),
                        "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    }
                )

                result = run_script(env)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    calls_file.read_text(encoding="utf-8").splitlines(),
                    raw_args.splitlines(),
                )
                self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_relative_output_cannot_alias_managed_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": (
                        "generate\n/tmp/input.json\n--output\nexecution-report.json"
                    ),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": execution_report(),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = calls_file.read_text(encoding="utf-8").splitlines()
            report_path = Path(arguments[2])
            self.assertEqual(report_path.name, "execution-report.json")
            self.assertTrue(report_path.parent.name.startswith("report."))
            self.assertEqual(arguments[-2:], ["--output", "execution-report.json"])

    def test_leading_separator_generate_publishes_report_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "--\ngenerate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": execution_report(),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = calls_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                arguments[:3],
                ["--", "generate", "--execution-report"],
            )
            self.assertEqual(
                read_github_outputs(github_output)["vexcalibur-version"],
                "0.4.2",
            )

    def test_non_generate_command_does_not_probe_and_publishes_empty_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "query-osv\n--help",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "broken",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(encoding="utf-8"), "query-osv\n--help\n"
            )
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_supported_generate_missing_report_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot open execution report", result.stderr)
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_supported_generate_malformed_report_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": '{"schema_version":1}',
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid fields", result.stderr)
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_supported_generate_without_github_output_still_validates_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": '{"schema_version":1}',
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("execution report has invalid fields", result.stderr)

    def test_failed_generate_does_not_publish_a_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": execution_report(),
                    "FAKE_VEXCALIBUR_COMMAND_EXIT": "7",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 7)
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_supported_generate_rejects_caller_managed_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": (
                        "generate\n/tmp/input.json\n"
                        "--execution-report=/tmp/caller-report.json"
                    ),
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("action-managed --execution-report", result.stderr)
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_supported_help_rejects_reserved_report_token(self) -> None:
        cases = (
            "generate\n--help\n--execution-report=/tmp/caller-report.json",
            "generate\n--execution-report\n/tmp/caller-report.json\n--help",
        )
        for raw_args in cases:
            with (
                self.subTest(raw_args=raw_args),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root = Path(tmpdir)
                calls_file = root / "calls.txt"
                python_calls = root / "python-calls.txt"
                env = managed_install_env(root, calls_file, python_calls)
                env.update(
                    {
                        "VEXCALIBUR_ARGS": raw_args,
                        "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    }
                )

                result = run_script(env)

                self.assertEqual(result.returncode, 2)
                self.assertIn("action-managed --execution-report", result.stderr)
                self.assertFalse(calls_file.exists())

    def test_supported_generate_rejects_report_argument_after_separator(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": (
                        "generate\n/tmp/input.json\n--\n--execution-report"
                    ),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "1",
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT": execution_report(),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("action-managed --execution-report", result.stderr)
            self.assertFalse(calls_file.exists())

    def test_generate_capability_probe_failure_stops_the_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n/tmp/input.json\n--offline",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "broken",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, "")
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")

    def test_generate_help_capability_probe_failure_stops_the_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            github_output = root / "github-output"
            github_output.touch()
            env = managed_install_env(root, calls_file, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "generate\n--help",
                    "GITHUB_OUTPUT": str(github_output),
                    "FAKE_VEXCALIBUR_EXECUTION_REPORT_SCHEMA": "broken",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertFalse(calls_file.exists())
            self.assertEqual(github_output.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
