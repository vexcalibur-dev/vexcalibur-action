from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION = REPO_ROOT / "action.yml"
SCRIPT = REPO_ROOT / "scripts" / "run-vexcalibur.sh"


def run_script(
    extra_env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        check=False,
        cwd=cwd,
        env=extra_env,
        text=True,
        capture_output=True,
    )


def run_action_vexcalibur_step(
    base_env: dict[str, str],
    input_overrides: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    action = _load_action()
    step = next(
        step for step in action["runs"]["steps"] if step["name"] == "Run Vexcalibur"
    )
    inputs = {
        "package-spec": "vexcalibur==0.1.0",
        "allow-development-package-spec": "false",
        "constraints-file": "",
        "args": "--help",
        **input_overrides,
    }
    env = {**base_env, "GITHUB_ACTION_PATH": str(REPO_ROOT)}
    env.update(
        {
            key: _render_action_value(value, env, inputs)
            for key, value in step["env"].items()
        }
    )
    cwd = Path(_render_action_value(step["working-directory"], env, inputs))
    cwd.mkdir(parents=True, exist_ok=True)
    shell_template = step["shell"]
    if "{0}" not in shell_template:
        raise AssertionError(
            f"action shell template does not include script placeholder: {shell_template}"
        )
    step_script = cwd / "vexcalibur-action-step.sh"
    step_script.write_text(f"{step['run']}\n", encoding="utf-8")
    command = shlex.split(shell_template.replace("{0}", shlex.quote(str(step_script))))
    return subprocess.run(
        command,
        check=False,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def managed_install_env(
    root: Path,
    vexcalibur_calls_file: Path,
    python_calls_file: Path,
    package_spec: str = "vexcalibur==0.1.0",
) -> dict[str, str]:
    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    fake_python = write_fake_python(fake_bin, vexcalibur_calls_file, python_calls_file)
    return {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(root / "runner-temp"),
        "VEXCALIBUR_PACKAGE_SPEC": package_spec,
        "VEXCALIBUR_PYTHON": str(fake_python),
    }


def read_venv_path(python_calls_file: Path) -> Path:
    for line in python_calls_file.read_text().splitlines():
        if line.startswith("COMMAND=-I -m venv "):
            return Path(line.removeprefix("COMMAND=-I -m venv "))
    raise AssertionError("venv command was not logged")


def read_commands(python_calls_file: Path) -> list[str]:
    return [
        line.removeprefix("COMMAND=")
        for line in python_calls_file.read_text().splitlines()
        if line.startswith("COMMAND=")
    ]


def read_command_env(python_calls_file: Path, command: str) -> dict[str, str]:
    lines = python_calls_file.read_text().splitlines()
    for index, line in enumerate(lines):
        if line != f"COMMAND={command}":
            continue
        env_values = {}
        for env_line in lines[index + 1 :]:
            if env_line.startswith("COMMAND=") or env_line.startswith("VEXCALIBUR_"):
                break
            key, value = env_line.split("=", 1)
            env_values[key] = value
        return env_values
    raise AssertionError(f"command not logged: {command}")


def write_shadow_modules(directory: Path) -> None:
    (directory / "pip.py").write_text(
        "from pathlib import Path\nPath('shadowed-pip.txt').write_text('ran')\n",
        encoding="utf-8",
    )


def write_fake_vexcalibur(tmpdir: Path, calls_file: Path) -> Path:
    fake_vexcalibur = tmpdir / "vexcalibur"
    fake_vexcalibur.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "from pathlib import Path",
                "import sys",
                f"Path({str(calls_file)!r}).write_text('\\n'.join(sys.argv[1:]) + '\\n')",
            ]
        )
    )
    fake_vexcalibur.chmod(fake_vexcalibur.stat().st_mode | stat.S_IXUSR)
    return fake_vexcalibur


def write_fake_command(tmpdir: Path, command_name: str, calls_file: Path) -> Path:
    fake_command = tmpdir / command_name
    fake_command.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "from pathlib import Path",
                "import sys",
                f"Path({str(calls_file)!r}).write_text('\\n'.join(sys.argv[1:]) + '\\n')",
                "sys.exit(99)",
            ]
        )
    )
    fake_command.chmod(fake_command.stat().st_mode | stat.S_IXUSR)
    return fake_command


def write_fake_python(
    tmpdir: Path, vexcalibur_calls_file: Path, python_calls_file: Path
) -> Path:
    fake_python = tmpdir / "python"
    managed_vexcalibur_script = "\n".join(
        [
            f"#!{sys.executable}",
            "import os",
            "from pathlib import Path",
            "import sys",
            f"calls = Path({str(vexcalibur_calls_file)!r})",
            "calls.write_text('\\n'.join(sys.argv[1:]) + '\\n')",
            f"python_calls = Path({str(python_calls_file)!r})",
            "with python_calls.open('a', encoding='utf-8') as stream:",
            "    stream.write(f\"VEXCALIBUR_PYTHONHOME={os.environ.get('PYTHONHOME', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PYTHONNOUSERSITE={os.environ.get('PYTHONNOUSERSITE', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PYTHONPATH={os.environ.get('PYTHONPATH', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PYTHONUSERBASE={os.environ.get('PYTHONUSERBASE', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIP_CACHE_DIR={os.environ.get('PIP_CACHE_DIR', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIP_CONFIG_FILE={os.environ.get('PIP_CONFIG_FILE', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIP_EXTRA_INDEX_URL={os.environ.get('PIP_EXTRA_INDEX_URL', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIP_INDEX_URL={os.environ.get('PIP_INDEX_URL', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIP_REQUIRE_VIRTUALENV={os.environ.get('PIP_REQUIRE_VIRTUALENV', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIPX_HOME={os.environ.get('PIPX_HOME', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIPX_BIN_DIR={os.environ.get('PIPX_BIN_DIR', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIPX_DEFAULT_BACKEND={os.environ.get('PIPX_DEFAULT_BACKEND', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_PIPX_DEFAULT_PYTHON={os.environ.get('PIPX_DEFAULT_PYTHON', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_ACTION_PURLS={os.environ.get('VEXCALIBUR_PURLS', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_ACTION_ARGS={os.environ.get('VEXCALIBUR_ARGS', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_LOWERCASE_PURLS={os.environ.get('purls', '')}\\n\")",
            "    stream.write(f\"VEXCALIBUR_LOWERCASE_ARGS={os.environ.get('args', '')}\\n\")",
            "",
        ]
    )
    fake_python.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import os",
                "import stat",
                "import sys",
                "import tempfile",
                "from pathlib import Path",
                f"python_calls = Path({str(python_calls_file)!r})",
                "raw_args = sys.argv[1:]",
                "args = raw_args[1:] if raw_args[:1] == ['-I'] else raw_args",
                "logged_command = ' '.join(raw_args).replace('\\n', '\\\\n')",
                "with python_calls.open('a', encoding='utf-8') as stream:",
                '    stream.write(f"COMMAND={logged_command}\\n")',
                "    stream.write(f\"PYTHONHOME={os.environ.get('PYTHONHOME', '')}\\n\")",
                "    stream.write(f\"PYTHONNOUSERSITE={os.environ.get('PYTHONNOUSERSITE', '')}\\n\")",
                "    stream.write(f\"PYTHONPATH={os.environ.get('PYTHONPATH', '')}\\n\")",
                "    stream.write(f\"PYTHONUSERBASE={os.environ.get('PYTHONUSERBASE', '')}\\n\")",
                "    stream.write(f\"PIP_CACHE_DIR={os.environ.get('PIP_CACHE_DIR', '')}\\n\")",
                "    stream.write(f\"PIP_CONFIG_FILE={os.environ.get('PIP_CONFIG_FILE', '')}\\n\")",
                "    stream.write(f\"PIP_EXTRA_INDEX_URL={os.environ.get('PIP_EXTRA_INDEX_URL', '')}\\n\")",
                "    stream.write(f\"PIP_INDEX_URL={os.environ.get('PIP_INDEX_URL', '')}\\n\")",
                "    stream.write(f\"PIP_REQUIRE_VIRTUALENV={os.environ.get('PIP_REQUIRE_VIRTUALENV', '')}\\n\")",
                "    stream.write(f\"PIPX_DEFAULT_BACKEND={os.environ.get('PIPX_DEFAULT_BACKEND', '')}\\n\")",
                "    stream.write(f\"PIPX_DEFAULT_PYTHON={os.environ.get('PIPX_DEFAULT_PYTHON', '')}\\n\")",
                "    stream.write(f\"PIPX_HOME={os.environ.get('PIPX_HOME', '')}\\n\")",
                "    stream.write(f\"PIPX_BIN_DIR={os.environ.get('PIPX_BIN_DIR', '')}\\n\")",
                "    stream.write(f\"VEXCALIBUR_ACTION_PURLS={os.environ.get('VEXCALIBUR_PURLS', '')}\\n\")",
                "    stream.write(f\"VEXCALIBUR_ACTION_ARGS={os.environ.get('VEXCALIBUR_ARGS', '')}\\n\")",
                "    stream.write(f\"LOWERCASE_PURLS={os.environ.get('purls', '')}\\n\")",
                "    stream.write(f\"LOWERCASE_ARGS={os.environ.get('args', '')}\\n\")",
                "if args[:1] == ['-c']:",
                "    runner_temp = Path(raw_args[-1])",
                "    runner_temp.mkdir(parents=True, exist_ok=True)",
                "    action_work_dir = Path(tempfile.mkdtemp(prefix='vexcalibur-action.', dir=runner_temp))",
                "    (action_work_dir / 'pip-cache').mkdir()",
                "    print(action_work_dir)",
                "    sys.exit(0)",
                "if args[:2] == ['-m', 'venv']:",
                "    venv_bin = Path(args[2]) / 'bin'",
                "    venv_bin.mkdir(parents=True, exist_ok=True)",
                "    venv_python = venv_bin / 'python'",
                "    venv_python.symlink_to(Path(sys.argv[0]).resolve())",
                "    sys.exit(0)",
                "pythonpath_entries = [",
                "    Path(raw_path)",
                "    for raw_path in os.environ.get('PYTHONPATH', '').split(os.pathsep)",
                "    if raw_path",
                "]",
                "pip_is_shadowed = Path('pip.py').exists() or any(",
                "    (entry / 'pip.py').exists() for entry in pythonpath_entries",
                ")",
                "if args[:2] == ['-m', 'pip'] and pip_is_shadowed:",
                "    Path('shadowed-pip.txt').write_text('ran', encoding='utf-8')",
                "    sys.exit(97)",
                "if args[:2] == ['-m', 'pip'] and 'install' in args:",
                "    managed_bin = Path(sys.argv[0]).parent",
                "    vexcalibur = managed_bin / 'vexcalibur'",
                f"    vexcalibur.write_text({managed_vexcalibur_script!r}, encoding='utf-8')",
                "    vexcalibur.chmod(vexcalibur.stat().st_mode | stat.S_IXUSR)",
                "",
            ]
        )
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    return fake_python


def _load_action() -> dict:
    with ACTION.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _render_action_value(
    value: str, env: dict[str, str], inputs: dict[str, str]
) -> str:
    rendered = value.replace("${{ runner.temp }}", env["RUNNER_TEMP"])
    rendered = rendered.replace(
        "${{ steps.setup-python.outputs.python-path }}", env["VEXCALIBUR_PYTHON"]
    )
    for input_name, input_value in inputs.items():
        rendered = rendered.replace(f"${{{{ inputs.{input_name} }}}}", input_value)
    if "${{" in rendered:
        raise AssertionError(f"unrendered action expression: {rendered}")
    return rendered
