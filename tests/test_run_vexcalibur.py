from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run-vexcalibur.sh"


class RunVexcaliburScriptTests(unittest.TestCase):
    def test_help_command_passes_help_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            calls_file = Path(tmpdir) / "calls.txt"
            fake_vexcalibur = _write_fake_vexcalibur(Path(tmpdir), calls_file)

            result = _run_script(
                {
                    "VEXCALIBUR_BIN": str(fake_vexcalibur),
                    "VEXCALIBUR_COMMAND": "help",
                    "VEXCALIBUR_SKIP_INSTALL": "true",
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls_file.read_text(), "--help\n")

    def test_query_osv_passes_each_purl_as_an_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            calls_file = Path(tmpdir) / "calls.txt"
            fake_vexcalibur = _write_fake_vexcalibur(Path(tmpdir), calls_file)

            result = _run_script(
                {
                    "VEXCALIBUR_BIN": str(fake_vexcalibur),
                    "VEXCALIBUR_COMMAND": "query-osv",
                    "VEXCALIBUR_PURLS": (
                        "pkg:pypi/django@1.2\n"
                        "\n"
                        "pkg:npm/minimist@0.0.8\r\n"
                    ),
                    "VEXCALIBUR_SKIP_INSTALL": "true",
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(),
                "query-osv\npkg:pypi/django@1.2\npkg:npm/minimist@0.0.8\n",
            )

    def test_query_osv_requires_purls(self) -> None:
        result = _run_script(
            {
                "VEXCALIBUR_COMMAND": "query-osv",
                "VEXCALIBUR_PURLS": "\n\r\n",
                "VEXCALIBUR_SKIP_INSTALL": "true",
            }
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("purls input is required", result.stderr)

    def test_unsupported_command_fails(self) -> None:
        result = _run_script(
            {
                "VEXCALIBUR_COMMAND": "unknown",
                "VEXCALIBUR_SKIP_INSTALL": "true",
            }
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported command: unknown", result.stderr)

    def test_pipx_managed_bin_is_preferred_to_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            path_dir = root / "path"
            managed_calls = root / "managed-calls.txt"
            path_calls = root / "path-calls.txt"
            managed_bin = home / ".local" / "bin"

            managed_bin.mkdir(parents=True)
            path_dir.mkdir()
            _write_fake_vexcalibur(managed_bin, managed_calls)
            _write_fake_vexcalibur(path_dir, path_calls)

            result = _run_script(
                {
                    "HOME": str(home),
                    "PATH": f"{path_dir}{os.pathsep}{os.environ['PATH']}",
                    "VEXCALIBUR_COMMAND": "help",
                    "VEXCALIBUR_SKIP_INSTALL": "true",
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse(path_calls.exists())


def _run_script(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        **extra_env,
    }
    return subprocess.run(
        [str(SCRIPT)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


def _write_fake_vexcalibur(tmpdir: Path, calls_file: Path) -> Path:
    fake_vexcalibur = tmpdir / "vexcalibur"
    fake_vexcalibur.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "import os",
                "import sys",
                f"Path({str(calls_file)!r}).write_text('\\n'.join(sys.argv[1:]) + '\\n')",
            ]
        )
    )
    fake_vexcalibur.chmod(fake_vexcalibur.stat().st_mode | stat.S_IXUSR)
    return fake_vexcalibur


if __name__ == "__main__":
    unittest.main()
