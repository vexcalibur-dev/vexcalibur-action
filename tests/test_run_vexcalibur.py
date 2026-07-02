from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import (
    managed_install_env,
    read_command_env,
    read_commands,
    read_venv_path,
    run_action_vexcalibur_step,
    run_script,
    write_fake_command,
    write_fake_vexcalibur,
    write_shadow_modules,
)


class RunVexcaliburScriptTests(unittest.TestCase):
    def test_default_args_pass_help_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls_file.read_text(), "--help\n")

    def test_args_are_passed_one_per_nonblank_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)
            env["VEXCALIBUR_ARGS"] = (
                "query-osv\n"
                "--allow-public-osv\n"
                "--\n"
                "pkg:pypi/django@1.2\n"
                "\n"
                "pkg:npm/minimist@0.0.8\r\n"
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(),
                "query-osv\n--allow-public-osv\n--\npkg:pypi/django@1.2\npkg:npm/minimist@0.0.8\n",
            )

    def test_args_preserve_spaces_quotes_and_option_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calls_file = root / "calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, calls_file, python_calls)
            env["VEXCALIBUR_ARGS"] = (
                "generate\n"
                "--output\n"
                "/tmp/vex output.json\n"
                "--label=\"literal quotes stay literal\"\n"
                " leading-and-trailing-spaces \n"
                "--\n"
                "--option-like-data\n"
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls_file.read_text(),
                (
                    "generate\n"
                    "--output\n"
                    "/tmp/vex output.json\n"
                    "--label=\"literal quotes stay literal\"\n"
                    " leading-and-trailing-spaces \n"
                    "--\n"
                    "--option-like-data\n"
                ),
            )

    def test_package_spec_is_required_when_installing(self) -> None:
        result = run_script({})

        self.assertEqual(result.returncode, 2)
        self.assertIn("package-spec is required", result.stderr)

    def test_script_runner_does_not_inherit_ambient_vexcalibur_inputs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VEXCALIBUR_ALLOW_DEVELOPMENT_PACKAGE_SPEC": "true",
                "VEXCALIBUR_ALLOW_PUBLIC_OSV": "true",
                "VEXCALIBUR_PACKAGE_SPEC": "vexcalibur==9.9.9",
            },
        ):
            result = run_script({})

        self.assertEqual(result.returncode, 2)
        self.assertIn("package-spec is required", result.stderr)

    def test_package_spec_must_be_exact_vexcalibur_release(self) -> None:
        rejected_specs = [
            "vexcalibur",
            "vexcalibur>=0.1.0",
            "other-package==0.1.0",
            "git+https://example.test/repo.git",
        ]

        for rejected_spec in rejected_specs:
            with self.subTest(package_spec=rejected_spec):
                result = run_script(
                    {
                        "VEXCALIBUR_PACKAGE_SPEC": rejected_spec,
                        "VEXCALIBUR_PYTHON": "/bin/true",
                    }
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("exact Vexcalibur release", result.stderr)
                self.assertIn("allow-development-package-spec", result.stderr)

    def test_python_path_is_required_and_must_be_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_python = root / "missing-python"

            missing = run_script(
                {
                    "RUNNER_TEMP": str(root / "runner-temp"),
                    "VEXCALIBUR_PACKAGE_SPEC": "vexcalibur==0.1.0",
                }
            )
            not_executable = run_script(
                {
                    "RUNNER_TEMP": str(root / "runner-temp"),
                    "VEXCALIBUR_PACKAGE_SPEC": "vexcalibur==0.1.0",
                    "VEXCALIBUR_PYTHON": str(missing_python),
                }
            )

            self.assertEqual(missing.returncode, 2)
            self.assertIn("VEXCALIBUR_PYTHON is required", missing.stderr)
            self.assertEqual(not_executable.returncode, 2)
            self.assertIn("VEXCALIBUR_PYTHON is not executable", not_executable.stderr)

    def test_skip_install_env_does_not_bypass_managed_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            env_calls = root / "env-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, managed_calls, python_calls)
            env_dir = root / "env"
            env_dir.mkdir()
            env_override = write_fake_vexcalibur(env_dir, env_calls)
            env.update(
                {
                    "VEXCALIBUR_BIN": str(env_override),
                    "VEXCALIBUR_ARGS": "--help",
                    "VEXCALIBUR_SKIP_INSTALL": "true",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse(env_calls.exists())
            self.assertIn("pip --isolated --no-cache-dir install vexcalibur==0.1.0", python_calls.read_text())

    def test_managed_install_bin_ignores_path_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "fake-bin"
            path_dir = root / "path"
            managed_calls = root / "managed-calls.txt"
            path_calls = root / "path-calls.txt"
            env_calls = root / "env-calls.txt"
            python_calls = root / "python-calls.txt"

            path_dir.mkdir()
            env_dir = root / "env"
            env_dir.mkdir()
            env = managed_install_env(root, managed_calls, python_calls)
            write_fake_vexcalibur(path_dir, path_calls)
            env_override = write_fake_vexcalibur(env_dir, env_calls)
            env.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{path_dir}{os.pathsep}{os.environ['PATH']}",
                    "VEXCALIBUR_BIN": str(env_override),
                    "VEXCALIBUR_ARGS": "--help",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse(path_calls.exists())
            self.assertFalse(env_calls.exists())
            venv_path = read_venv_path(python_calls)
            self.assertEqual(venv_path.parent.parent, root / "runner-temp")
            self.assertTrue(venv_path.parent.name.startswith("vexcalibur-action."))

    def test_caller_path_bootstrap_commands_are_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hostile_bin = root / "hostile-bin"
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            command_calls = {
                name: root / f"hostile-{name}-calls.txt"
                for name in ["env", "mkdir", "mktemp", "python", "uv", "vexcalibur"]
            }

            hostile_bin.mkdir()
            for command_name, calls_file in command_calls.items():
                write_fake_command(hostile_bin, command_name, calls_file)
            env = managed_install_env(root, managed_calls, python_calls)
            env.update(
                {
                    "PATH": f"{hostile_bin}{os.pathsep}{os.environ['PATH']}",
                    "VEXCALIBUR_ARGS": "--help",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            for calls_file in command_calls.values():
                self.assertFalse(calls_file.exists(), str(calls_file))

    def test_cli_args_are_not_visible_to_install_time_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            secret_arg = "pkg:internal/secret-component@1.0"
            env = managed_install_env(root, managed_calls, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": f"query-osv\n--\n{secret_arg}",
                    "args": "caller-exported-lowercase-args",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), f"query-osv\n--\n{secret_arg}\n")
            python_log = python_calls.read_text()
            self.assertNotIn(secret_arg, python_log)
            self.assertNotIn("caller-exported-lowercase-args", python_log)
            self.assertIn("VEXCALIBUR_ACTION_PURLS=\n", python_log)
            self.assertIn("VEXCALIBUR_ACTION_ARGS=\n", python_log)
            self.assertIn("VEXCALIBUR_LOWERCASE_PURLS=\n", python_log)
            self.assertIn("LOWERCASE_PURLS=\n", python_log)
            self.assertIn("VEXCALIBUR_LOWERCASE_ARGS=\n", python_log)
            self.assertIn("LOWERCASE_ARGS=\n", python_log)

    def test_python_module_install_runs_outside_caller_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            caller_workspace = root / "caller-workspace"
            caller_workspace.mkdir()
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, managed_calls, python_calls)
            runner_temp = Path(env["RUNNER_TEMP"])
            runner_temp.mkdir()
            write_shadow_modules(caller_workspace)
            write_shadow_modules(runner_temp)
            env["VEXCALIBUR_ARGS"] = "--help"
            env["PYTHONPATH"] = str(caller_workspace)
            env["PYTHONHOME"] = str(caller_workspace)
            env["PYTHONNOUSERSITE"] = "1"
            env["PYTHONUSERBASE"] = str(caller_workspace)
            env["PIP_CACHE_DIR"] = str(caller_workspace / "pip-cache")
            env["PIP_CONFIG_FILE"] = str(caller_workspace / "pip.conf")
            env["PIP_EXTRA_INDEX_URL"] = "https://evil-extra.example.test/simple"
            env["PIP_INDEX_URL"] = "https://evil.example.test/simple"
            env["PIP_REQUIRE_VIRTUALENV"] = "true"
            env["PIPX_DEFAULT_BACKEND"] = "uv"
            env["PIPX_DEFAULT_PYTHON"] = str(caller_workspace / "evil-python")

            result = run_script(env, cwd=caller_workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse((caller_workspace / "shadowed-pip.txt").exists())
            self.assertFalse((runner_temp / "shadowed-pip.txt").exists())
            venv_path = read_venv_path(python_calls)
            pip_cache_dir = venv_path.parent / "pip-cache"
            setup_commands = [
                command
                for command in read_commands(python_calls)
                if "tempfile.mkdtemp" in command
            ]
            self.assertEqual(len(setup_commands), 1, setup_commands)
            self.assertTrue(setup_commands[0].startswith("-I -c "), setup_commands[0])
            self.assertTrue(setup_commands[0].endswith(f" {runner_temp}"), setup_commands[0])
            self.assertEqual(
                read_command_env(python_calls, f"-I -m venv {venv_path}"),
                _empty_python_tool_env(),
            )
            self.assertEqual(
                read_command_env(python_calls, "-I -m pip --isolated --no-cache-dir install vexcalibur==0.1.0"),
                {
                    **_empty_python_tool_env(),
                    "PIP_CACHE_DIR": str(pip_cache_dir),
                    "PIP_CONFIG_FILE": "/dev/null",
                },
            )
            python_log = python_calls.read_text()
            self.assertIn("VEXCALIBUR_PYTHONHOME=\n", python_log)
            self.assertIn("VEXCALIBUR_PYTHONPATH=\n", python_log)
            self.assertIn("VEXCALIBUR_PIP_CACHE_DIR=\n", python_log)
            self.assertIn("VEXCALIBUR_PIP_CONFIG_FILE=\n", python_log)
            self.assertIn("VEXCALIBUR_PIPX_DEFAULT_BACKEND=\n", python_log)
            self.assertNotIn(str(caller_workspace / "evil-python"), python_log)

    def test_bash_env_is_not_sourced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            marker = root / "bash-env-sourced.txt"
            bash_env_file = root / "bash-env.sh"
            bash_env_file.write_text(
                f"printf sourced > {str(marker)!r}\n",
                encoding="utf-8",
            )
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, managed_calls, python_calls)
            env.update(
                {
                    "BASH_ENV": str(bash_env_file),
                    "VEXCALIBUR_ARGS": "--help",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse(marker.exists())

    def test_action_run_step_clears_bash_env_before_shell_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            marker = root / "action-bash-env-sourced.txt"
            bash_env_file = root / "bash-env.sh"
            bash_env_file.write_text(
                f"printf sourced > {str(marker)!r}\n",
                encoding="utf-8",
            )
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, managed_calls, python_calls)
            env["BASH_ENV"] = str(bash_env_file)

            result = run_action_vexcalibur_step(env, {"args": "--help"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertFalse(marker.exists())

    def test_development_package_spec_can_install_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(
                root,
                managed_calls,
                python_calls,
                package_spec="git+https://github.com/vexcalibur-dev/vexcalibur.git@abc123",
            )
            env.update(
                {
                    "VEXCALIBUR_ARGS": "--help",
                    "VEXCALIBUR_ALLOW_DEVELOPMENT_PACKAGE_SPEC": "true",
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertIn(
                "pip --isolated --no-cache-dir install git+https://github.com/vexcalibur-dev/vexcalibur.git@abc123",
                python_calls.read_text(),
            )

    def test_constraints_file_is_passed_to_pip_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            constraints_file = root / "constraints.txt"
            constraints_file.write_text("httpx==0.28.1\n", encoding="utf-8")
            env = managed_install_env(root, managed_calls, python_calls)
            env.update(
                {
                    "VEXCALIBUR_ARGS": "--help",
                    "VEXCALIBUR_CONSTRAINTS_FILE": str(constraints_file),
                }
            )

            result = run_script(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(managed_calls.read_text(), "--help\n")
            self.assertIn(
                "pip --isolated --no-cache-dir install "
                f"--constraint {constraints_file} vexcalibur==0.1.0",
                python_calls.read_text(),
            )

    def test_missing_constraints_file_fails_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            env = managed_install_env(root, managed_calls, python_calls)
            env["VEXCALIBUR_CONSTRAINTS_FILE"] = str(root / "missing-constraints.txt")

            result = run_script(env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("constraints-file does not exist or is not readable", result.stderr)
            self.assertFalse(python_calls.exists())

    def test_relative_constraints_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            managed_calls = root / "managed-calls.txt"
            python_calls = root / "python-calls.txt"
            (root / "constraints.txt").write_text("httpx==0.28.1\n", encoding="utf-8")
            env = managed_install_env(root, managed_calls, python_calls)
            env["VEXCALIBUR_CONSTRAINTS_FILE"] = "constraints.txt"

            result = run_script(env, cwd=root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("constraints-file must be an absolute path", result.stderr)
            self.assertFalse(python_calls.exists())


def _empty_python_tool_env() -> dict[str, str]:
    return {
        "PYTHONHOME": "",
        "PYTHONNOUSERSITE": "",
        "PYTHONPATH": "",
        "PYTHONUSERBASE": "",
        "PIP_CACHE_DIR": "",
        "PIP_CONFIG_FILE": "",
        "PIP_EXTRA_INDEX_URL": "",
        "PIP_INDEX_URL": "",
        "PIP_REQUIRE_VIRTUALENV": "",
        "PIPX_DEFAULT_BACKEND": "",
        "PIPX_DEFAULT_PYTHON": "",
        "PIPX_HOME": "",
        "PIPX_BIN_DIR": "",
    }


if __name__ == "__main__":
    unittest.main()
