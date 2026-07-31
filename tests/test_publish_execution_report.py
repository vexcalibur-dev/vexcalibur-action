from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from helpers import execution_report, read_github_outputs


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "scripts" / "publish-execution-report.py"
CHECKER = ROOT / "scripts" / "check-execution-report-support.py"
PUBLISHER_SPEC = importlib.util.spec_from_file_location(
    "vexcalibur_action_execution_report_publisher",
    PUBLISHER,
)
if PUBLISHER_SPEC is None or PUBLISHER_SPEC.loader is None:
    raise RuntimeError("could not load execution-report publisher")
publisher = importlib.util.module_from_spec(PUBLISHER_SPEC)
PUBLISHER_SPEC.loader.exec_module(publisher)
CHECKER_SPEC = importlib.util.spec_from_file_location(
    "vexcalibur_action_execution_report_checker_contract",
    CHECKER,
)
if CHECKER_SPEC is None or CHECKER_SPEC.loader is None:
    raise RuntimeError("could not load execution-report support checker")
checker = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(checker)


def canonical_report(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"


def read_github_outputs_from_text(text: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "github-output"
        path.write_text(text, encoding="utf-8")
        return read_github_outputs(path)


class PublishExecutionReportTests(unittest.TestCase):
    def test_action_outputs_and_schema_match_the_publisher_contract(self) -> None:
        action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
        report = json.loads(execution_report())

        self.assertEqual(tuple(action["outputs"]), publisher.OUTPUT_NAMES)
        self.assertEqual(
            checker.EXPECTED_SCHEMA_VERSION,
            report["schema_version"],
        )
        self.assertEqual(
            publisher.validate_report(execution_report().encode("utf-8"))[
                "schema_version"
            ],
            checker.EXPECTED_SCHEMA_VERSION,
        )

    def test_valid_report_publishes_complete_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            output = root / "github-output"
            report.write_text(execution_report(), encoding="utf-8")
            output.touch()

            result = self._publish(output, report)

            self.assertEqual(result.returncode, 0, result.stderr)
            values = read_github_outputs(output)
            self.assertEqual(
                tuple(values),
                publisher.OUTPUT_NAMES,
            )
            self.assertEqual(
                json.loads(values["execution-report"]),
                json.loads(report.read_text(encoding="utf-8")),
            )
            self.assertEqual(values["execution-report-path"], str(report))
            self.assertEqual(values["vexcalibur-version"], "0.4.2")
            self.assertEqual(values["component-count"], "2")
            self.assertEqual(values["finding-count"], "2")
            self.assertEqual(values["analysis-state-counts"], '{"resolved":2}')
            self.assertEqual(values["output-format"], "cyclonedx")
            self.assertEqual(values["document-sha256"], "a" * 64)
            self.assertEqual(values["document-bytes"], "1234")

    def test_zero_findings_publish_an_empty_state_object(self) -> None:
        report = json.loads(execution_report())
        report["finding_count"] = 0
        report["analysis_state_counts"] = {}

        result, output = self._publish_text(canonical_report(report))

        self.assertEqual(result.returncode, 0, result.stderr)
        values = read_github_outputs_from_text(output)
        self.assertEqual(values["finding-count"], "0")
        self.assertEqual(values["analysis-state-counts"], "{}")

    def test_all_source_and_format_categories_are_preserved(self) -> None:
        base = json.loads(execution_report())
        cases = (
            ("sbom_file", "local_file", "cyclonedx"),
            ("github_dependency_graph", "public_osv", "openvex"),
            ("sbom_file", "custom_osv", "csaf"),
            ("custom", "custom", "custom"),
        )
        for inventory_source, finding_source, output_format in cases:
            with self.subTest(
                inventory_source=inventory_source,
                finding_source=finding_source,
                output_format=output_format,
            ):
                report = {
                    **base,
                    "inventory_source": inventory_source,
                    "finding_source": finding_source,
                    "output_format": output_format,
                }
                result, output = self._publish_text(canonical_report(report))
                self.assertEqual(result.returncode, 0, result.stderr)
                published = json.loads(
                    read_github_outputs_from_text(output)["execution-report"]
                )
                self.assertEqual(published["inventory_source"], inventory_source)
                self.assertEqual(published["finding_source"], finding_source)
                self.assertEqual(published["output_format"], output_format)

    def test_duplicate_or_unknown_fields_fail_closed(self) -> None:
        duplicate = execution_report().replace(
            '"schema_version":1',
            '"schema_version":1,"schema_version":1',
            1,
        )
        unknown = execution_report().replace(
            '"command":"generate"',
            '"command":"generate","components":["pkg:internal/secret@1"]',
            1,
        )
        for report_text in (duplicate, unknown):
            with self.subTest(report_text=report_text):
                result, output = self._publish_text(report_text)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output, "")

    def test_hostile_field_names_are_not_written_to_runner_logs(self) -> None:
        marker = "::warning::attacker-controlled"
        report_text = execution_report().replace(
            '"command":"generate"',
            f'"command":"generate","unknown\\n{marker}":true',
            1,
        )

        result, output = self._publish_text(report_text)

        self.assertEqual(result.returncode, 2)
        self.assertNotIn(marker, result.stderr)
        self.assertNotIn("attacker-controlled", result.stderr)
        self.assertEqual(output, "")

    def test_noncanonical_report_fails_closed(self) -> None:
        noncanonical = json.dumps(json.loads(execution_report()), indent=2)

        result, output = self._publish_text(noncanonical)

        self.assertEqual(result.returncode, 2)
        self.assertIn("not canonical JSON", result.stderr)
        self.assertEqual(output, "")

    def test_malformed_types_and_inconsistent_counts_fail_closed(self) -> None:
        invalid_values = (
            {"schema_version": 1.0},
            {"component_count": True},
            {"component_count": 10_000_001},
            {"finding_count": 3},
            {
                "finding_count": 10_000_001,
                "analysis_state_counts": {"resolved": 10_000_001},
            },
            {"inventory_source": ["sbom_file"]},
            {"output_format": "html"},
            {"analysis_state_counts": {"resolved": 0, "exploitable": 2}},
            {"analysis_state_counts": {"unknown": 2}},
            {"document": {"sha256": "A" * 64, "bytes": 1234}},
            {
                "document": {
                    "sha256": "a" * 64,
                    "bytes": 25 * 1024 * 1024 + 1,
                }
            },
        )
        base = json.loads(execution_report())
        for replacement in invalid_values:
            with self.subTest(replacement=replacement):
                report = {**base, **replacement}
                result, output = self._publish_text(canonical_report(report))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output, "")

    def test_oversized_report_fails_closed(self) -> None:
        report_text = execution_report() + (" " * (16 * 1024))

        result, output = self._publish_text(report_text)

        self.assertEqual(result.returncode, 2)
        self.assertIn("exceeds 16384 bytes", result.stderr)
        self.assertEqual(output, "")

    def test_integer_literal_over_python_limit_fails_with_stable_error(self) -> None:
        report_text = execution_report().replace(
            '"component_count":2',
            '"component_count":' + ("9" * 5_000),
            1,
        )

        result, output = self._publish_text(report_text)

        self.assertEqual(result.returncode, 2)
        self.assertIn("execution report is not valid JSON", result.stderr)
        self.assertEqual(output, "")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_report_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            report = root / "report.json"
            output = root / "github-output"
            target.write_text(execution_report(), encoding="utf-8")
            report.symlink_to(target)
            output.touch()

            result = self._publish(output, report)

            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are unavailable")
    def test_report_fifo_fails_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            output = root / "github-output"
            os.mkfifo(report)
            output.touch()

            result = self._publish(output, report)

            self.assertEqual(result.returncode, 2)
            self.assertIn("not a regular file", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_github_output_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            output_target = root / "github-output-target"
            output = root / "github-output"
            report.write_text(execution_report(), encoding="utf-8")
            output_target.touch()
            output.symlink_to(output_target)

            result = self._publish(output, report)

            self.assertEqual(result.returncode, 2)
            self.assertEqual(output_target.read_text(encoding="utf-8"), "")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are unavailable")
    def test_github_output_fifo_fails_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            output = root / "github-output"
            report.write_text(execution_report(), encoding="utf-8")
            os.mkfifo(output)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUBLISHER),
                    "--github-output",
                    str(output),
                    "--report",
                    str(report),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot open GITHUB_OUTPUT", result.stderr)

    def test_multiline_report_path_uses_safe_github_output_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report\nname.json"
            output = root / "github-output"
            report.write_text(execution_report(), encoding="utf-8")
            output.touch()

            result = self._publish(output, report)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                read_github_outputs(output)["execution-report-path"],
                str(report),
            )

    def test_partial_output_write_is_removed_before_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            output.write_text("existing-output\n", encoding="utf-8")
            real_write = os.write
            calls = 0

            def fail_after_partial_write(
                descriptor: int,
                value: bytes | memoryview,
            ) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return real_write(descriptor, bytes(value[:11]))
                raise OSError("synthetic write failure")

            with patch.object(publisher.os, "write", fail_after_partial_write):
                with self.assertRaisesRegex(
                    publisher.ReportError,
                    "could not write GITHUB_OUTPUT",
                ):
                    report = publisher.validate_report(execution_report().encode())
                    publisher.publish_outputs(
                        output,
                        publisher.report_outputs(report, Path("/tmp/report.json")),
                    )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "existing-output\n",
            )

    def test_partial_output_write_is_removed_before_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            output.write_text("existing-output\n", encoding="utf-8")
            real_write = os.write
            calls = 0

            def interrupt_after_partial_write(
                descriptor: int,
                value: bytes | memoryview,
            ) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    real_write(descriptor, bytes(value[:11]))
                    raise KeyboardInterrupt
                raise AssertionError("write called again after interrupt")

            with patch.object(publisher.os, "write", interrupt_after_partial_write):
                with self.assertRaises(KeyboardInterrupt):
                    report = publisher.validate_report(execution_report().encode())
                    publisher.publish_outputs(
                        output,
                        publisher.report_outputs(report, Path("/tmp/report.json")),
                    )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "existing-output\n",
            )

    def _publish_text(
        self,
        report_text: str,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            output = root / "github-output"
            report.write_text(report_text, encoding="utf-8")
            output.touch()
            result = self._publish(output, report)
            return result, output.read_text(encoding="utf-8")

    def _publish(
        self,
        output: Path,
        report: Path,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            "-I",
            str(PUBLISHER),
            "--github-output",
            str(output),
        ]
        command.extend(["--report", str(report)])
        return subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
