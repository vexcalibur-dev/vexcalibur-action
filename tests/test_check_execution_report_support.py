from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check-execution-report-support.py"
CHECKER_SPEC = importlib.util.spec_from_file_location(
    "vexcalibur_action_execution_report_checker",
    CHECKER,
)
if CHECKER_SPEC is None or CHECKER_SPEC.loader is None:
    raise RuntimeError("could not load execution-report support checker")
checker = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(checker)


class CheckExecutionReportSupportTests(unittest.TestCase):
    def test_checker_runs_in_an_isolated_interpreter(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(CHECKER)],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertIn(result.returncode, {0, 1})
        self.assertEqual(result.stderr, "")

    def test_schema_one_is_supported(self) -> None:
        module = SimpleNamespace(EXECUTION_REPORT_SCHEMA_VERSION=1)
        stderr = StringIO()
        with (
            patch.object(checker, "_load_api_module", return_value=module),
            redirect_stderr(stderr),
        ):
            result = checker.detect_support()

        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_missing_module_is_an_older_package(self) -> None:
        stderr = StringIO()
        with (
            patch.object(
                checker,
                "_load_api_module",
                return_value=None,
            ),
            redirect_stderr(stderr),
        ):
            result = checker.detect_support()

        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "")

    def test_missing_schema_marker_is_an_older_package(self) -> None:
        stderr = StringIO()
        with (
            patch.object(checker, "_load_api_module", return_value=SimpleNamespace()),
            redirect_stderr(stderr),
        ):
            result = checker.detect_support()

        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "")

    def test_lazy_schema_marker_is_supported(self) -> None:
        module = ModuleType("lazy_vexcalibur_api")

        def resolve_attribute(name: str) -> int:
            if name == checker.SCHEMA_ATTRIBUTE:
                return 1
            raise AttributeError(name)

        module.__getattr__ = resolve_attribute

        stderr = StringIO()
        with (
            patch.object(checker, "_load_api_module", return_value=module),
            redirect_stderr(stderr),
        ):
            result = checker.detect_support()

        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_broken_lazy_schema_marker_is_incompatible(self) -> None:
        failures = (
            AttributeError(checker.SCHEMA_ATTRIBUTE),
            RuntimeError("cannot resolve schema marker"),
        )
        for failure in failures:
            with self.subTest(failure=failure):
                module = ModuleType("broken_lazy_vexcalibur_api")

                def resolve_attribute(name: str) -> int:
                    if name == checker.SCHEMA_ATTRIBUTE:
                        raise failure
                    raise AttributeError(name)

                module.__getattr__ = resolve_attribute
                stderr = StringIO()
                with (
                    patch.object(checker, "_load_api_module", return_value=module),
                    redirect_stderr(stderr),
                ):
                    result = checker.detect_support()

                self.assertEqual(result, 2)
                self.assertIn("could not inspect", stderr.getvalue())

    def test_mistyped_or_unknown_schema_is_incompatible(self) -> None:
        modules = (
            SimpleNamespace(EXECUTION_REPORT_SCHEMA_VERSION=True),
            SimpleNamespace(EXECUTION_REPORT_SCHEMA_VERSION="1"),
            SimpleNamespace(EXECUTION_REPORT_SCHEMA_VERSION=2),
        )
        for module in modules:
            with self.subTest(module=module):
                stderr = StringIO()
                with (
                    patch.object(
                        checker,
                        "_load_api_module",
                        return_value=module,
                    ),
                    redirect_stderr(stderr),
                ):
                    result = checker.detect_support()

                self.assertEqual(result, 2)
                self.assertIn(
                    "unsupported execution-report contract", stderr.getvalue()
                )

    def test_dependency_import_failure_is_incompatible(self) -> None:
        failures = (
            ModuleNotFoundError("missing dependency", name="packageurl"),
            ModuleNotFoundError("failed module import", name="vexcalibur.api"),
            RuntimeError("cannot import API"),
            SystemExit(1),
        )
        for failure in failures:
            with self.subTest(failure=failure):
                stderr = StringIO()
                with (
                    patch.object(
                        checker,
                        "_load_api_module",
                        side_effect=failure,
                    ),
                    redirect_stderr(stderr),
                ):
                    result = checker.detect_support()

                self.assertEqual(result, 2)
                self.assertIn("could not inspect", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
