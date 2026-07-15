from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "scripts" / "run-vexcalibur.sh"
MAX_INPUT_BYTES = 64 * 1024
SUBPROCESS_TIMEOUT_SECONDS = 2.0
SEED_MAGIC = b"VAF1\n"
ARGS_MARKER = b"\n<<<ARGS>>>\n"
RELEASE_SPEC = re.compile(r"vexcalibur==[0-9][0-9A-Za-z.!+_-]*", re.ASCII)
PYTHON_TOOL_ENV = (
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PIP_CACHE_DIR",
    "PIP_CONFIG_FILE",
    "PIP_EXTRA_INDEX_URL",
    "PIP_INDEX_URL",
    "PIP_REQUIRE_VIRTUALENV",
    "PIPX_BIN_DIR",
    "PIPX_DEFAULT_BACKEND",
    "PIPX_DEFAULT_PYTHON",
    "PIPX_HOME",
)


@dataclass(frozen=True)
class WrapperCase:
    package_spec: str
    allow_development_package_spec: bool
    constraints_kind: int
    args_present: bool
    raw_args: str


def decode_case(data: bytes) -> WrapperCase:
    """Decode one bounded byte string into environment values for the wrapper."""
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes")

    if data.startswith(SEED_MAGIC):
        flags_bytes, separator, payload = data[len(SEED_MAGIC) :].partition(b"\n")
        try:
            flags = int(flags_bytes, 16) & 0xFF if separator else 0
        except ValueError:
            flags = 0
        package_bytes, marker, args_bytes = payload.partition(ARGS_MARKER)
        if not marker:
            args_bytes = b""
        elif flags & 0x40:
            args_bytes = args_bytes.replace(b"\\r", b"\r")
    else:
        flags = data[0] if data else 0
        package_length = data[1] if len(data) > 1 else 0
        payload = data[2:]
        package_bytes = payload[:package_length]
        args_bytes = payload[package_length:]

    package_spec = _environment_text(package_bytes)
    if flags & 0x10:
        allowed_version_characters = (
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.!+_-"
        )
        version_tail = "".join(
            character if character in allowed_version_characters else "_"
            for character in package_spec
        )
        package_spec = f"vexcalibur==0{version_tail}"

    return WrapperCase(
        package_spec=package_spec,
        allow_development_package_spec=bool(flags & 0x02),
        constraints_kind=(flags >> 2) & 0x03,
        args_present=bool(flags & 0x01),
        raw_args=_environment_text(args_bytes),
    )


def encode_seed(case: WrapperCase) -> bytes:
    """Encode a readable, mutation-friendly seed for the shared decoder."""
    flags = (
        int(case.args_present)
        | (int(case.allow_development_package_spec) << 1)
        | ((case.constraints_kind & 0x03) << 2)
    )
    return (
        SEED_MAGIC
        + f"{flags:02x}\n".encode("ascii")
        + case.package_spec.encode("utf-8")
        + ARGS_MARKER
        + case.raw_args.encode("utf-8")
    )


def expected_cli_args(case: WrapperCase) -> list[str]:
    if not case.args_present:
        return ["--help"]

    args = []
    for line in case.raw_args.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        if line:
            args.append(line)
    return args


def expected_success(case: WrapperCase) -> bool:
    package_is_allowed = bool(case.package_spec) and (
        case.allow_development_package_spec
        or RELEASE_SPEC.fullmatch(case.package_spec) is not None
    )
    constraints_are_allowed = case.constraints_kind in (0, 1)
    return package_is_allowed and constraints_are_allowed


def expected_validation_error(case: WrapperCase) -> str | None:
    if not case.package_spec:
        return "package-spec is required"
    if (
        not case.allow_development_package_spec
        and RELEASE_SPEC.fullmatch(case.package_spec) is None
    ):
        return "package-spec must be an exact Vexcalibur release"
    if case.constraints_kind == 3:
        return "constraints-file must be an absolute path"
    if case.constraints_kind == 2:
        return "constraints-file does not exist or is not readable"
    return None


def exercise_fuzz_input(data: bytes) -> None:
    """Drive the real wrapper and compare all recorded vectors with the model."""
    case = decode_case(data)
    with tempfile.TemporaryDirectory(prefix="vexcalibur-action-fuzz.") as tmpdir:
        _exercise_case(case, Path(tmpdir))


def _environment_text(raw: bytes) -> str:
    # Environment variables cannot represent NUL or surrogate-escaped malformed
    # UTF-8. A one-byte replacement keeps the encoded value within the byte cap.
    decoded = raw.decode("utf-8", errors="surrogateescape")
    return "".join(
        "?" if character == "\x00" or 0xDC80 <= ord(character) <= 0xDCFF else character
        for character in decoded
    )


def _exercise_case(case: WrapperCase, root: Path) -> None:
    runner_temp = root / "runner temp [literal]"
    working_directory = root / "caller workspace"
    trusted_bin = root / "trusted bin [literal]"
    hostile_bin = root / "hostile bin [literal]"
    python_log = root / "python-events.jsonl"
    cli_log = root / "cli-events.jsonl"
    hostile_marker = root / "hostile-command-ran"
    bash_env_marker = root / "bash-env-sourced"
    constraints_file = root / "constraints with spaces;literal.txt"

    for directory in (working_directory, trusted_bin, hostile_bin, root / "home"):
        directory.mkdir()
    constraints_file.write_text("synthetic-package==1.0\n", encoding="utf-8")
    trusted_python = _write_fake_python(trusted_bin, python_log, cli_log)
    _write_hostile_commands(hostile_bin, hostile_marker)
    bash_env = root / "bash-env.sh"
    bash_env.write_text(
        f"printf sourced > {shlex.quote(str(bash_env_marker))}\n",
        encoding="utf-8",
    )

    constraints_value = {
        0: "",
        1: str(constraints_file),
        2: str(root / "missing constraints [literal].txt"),
        3: "relative constraints [literal].txt",
    }[case.constraints_kind]
    environment = {
        "BASH_ENV": str(bash_env),
        "ENV": str(bash_env),
        "HOME": str(root / "home"),
        "LANG": "C.UTF-8",
        "PATH": str(hostile_bin),
        "PIP": str(hostile_bin / "pip"),
        "PIP_CACHE_DIR": str(root / "caller-pip-cache"),
        "PIP_CONFIG_FILE": str(root / "caller-pip.conf"),
        "PIP_EXTRA_INDEX_URL": "https://packages.example.test/extra",
        "PIP_INDEX_URL": "https://packages.example.test/simple",
        "PIP_REQUIRE_VIRTUALENV": "true",
        "PIPX": str(hostile_bin / "pipx"),
        "PIPX_BIN_DIR": str(root / "caller-pipx-bin"),
        "PIPX_DEFAULT_BACKEND": "uv",
        "PIPX_DEFAULT_PYTHON": str(hostile_bin / "python"),
        "PIPX_HOME": str(root / "caller-pipx-home"),
        "PYTHON": str(hostile_bin / "python"),
        "PYTHONHOME": str(root / "caller-python-home"),
        "PYTHONINSPECT": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(root / "caller-python-path"),
        "PYTHONSTARTUP": str(root / "caller-startup.py"),
        "PYTHONUSERBASE": str(root / "caller-python-user-base"),
        "RUNNER_TEMP": str(runner_temp),
        "VEXCALIBUR_ALLOW_DEVELOPMENT_PACKAGE_SPEC": (
            "true" if case.allow_development_package_spec else "false"
        ),
        "VEXCALIBUR_BIN": str(hostile_bin / "vexcalibur"),
        "VEXCALIBUR_CONSTRAINTS_FILE": constraints_value,
        "VEXCALIBUR_PACKAGE_SPEC": case.package_spec,
        "VEXCALIBUR_PYTHON": str(trusted_python),
        "VEXCALIBUR_SKIP_INSTALL": "true",
    }
    if case.args_present:
        environment["VEXCALIBUR_ARGS"] = case.raw_args

    completed = subprocess.run(
        [str(WRAPPER)],
        check=False,
        cwd=working_directory,
        env=environment,
        text=True,
        capture_output=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )

    _require(not hostile_marker.exists(), "a caller-controlled executable ran")
    _require(not bash_env_marker.exists(), "BASH_ENV or ENV was sourced")

    if not expected_success(case):
        _require(completed.returncode == 2, _result_message(case, completed))
        expected_error = expected_validation_error(case)
        _require(expected_error is not None, f"missing failure model for {case!r}")
        _require(expected_error in completed.stderr, _result_message(case, completed))
        _require(not python_log.exists(), "validation failure reached the Python boundary")
        _require(not cli_log.exists(), "validation failure reached the CLI boundary")
        return

    _require(completed.returncode == 0, _result_message(case, completed))
    python_events = _read_json_lines(python_log)
    cli_events = _read_json_lines(cli_log)
    _require(len(python_events) == 3, f"unexpected Python calls: {python_events!r}")
    _require(len(cli_events) == 1, f"unexpected CLI calls: {cli_events!r}")

    setup_event, venv_event, pip_event = python_events
    setup_argv = setup_event["argv"]
    _require(
        len(setup_argv) == 4
        and setup_argv[:2] == ["-I", "-c"]
        and setup_argv[-1] == str(runner_temp),
        f"unexpected setup argv: {setup_argv!r}",
    )
    _require(
        Path(setup_event["cwd"]) == working_directory,
        f"setup ran outside caller workspace: {setup_event!r}",
    )

    venv_argv = venv_event["argv"]
    _require(venv_argv[:3] == ["-I", "-m", "venv"], f"unexpected venv argv: {venv_argv!r}")
    _require(len(venv_argv) == 4, f"unexpected venv argv: {venv_argv!r}")
    venv_dir = Path(venv_argv[-1])
    action_work_dir = venv_dir.parent
    _require(
        action_work_dir.parent.resolve() == runner_temp.resolve()
        and action_work_dir.name.startswith("vexcalibur-action."),
        f"temporary environment escaped RUNNER_TEMP: {action_work_dir}",
    )
    _require(
        Path(venv_event["cwd"]) == action_work_dir,
        f"venv creation ran outside action work dir: {venv_event!r}",
    )

    expected_pip_argv = ["-I", "-m", "pip", "--isolated", "--no-cache-dir", "install"]
    if case.constraints_kind == 1:
        expected_pip_argv.extend(["--constraint", str(constraints_file)])
    expected_pip_argv.append(case.package_spec)
    _require(pip_event["argv"] == expected_pip_argv, f"unexpected pip argv: {pip_event['argv']!r}")
    _require(Path(pip_event["cwd"]) == action_work_dir, f"pip ran outside action work dir: {pip_event!r}")
    _require(cli_events[0]["argv"] == expected_cli_args(case), f"unexpected CLI argv: {cli_events!r}")
    _require(
        Path(cli_events[0]["cwd"]) == action_work_dir,
        f"CLI ran outside action work dir: {cli_events!r}",
    )

    for event in (setup_event, venv_event):
        _require(
            all(event["environment"][name] is None for name in PYTHON_TOOL_ENV),
            f"caller Python or installer environment reached setup: {event!r}",
        )
    expected_pip_cache = str(action_work_dir / "pip-cache")
    for name in PYTHON_TOOL_ENV:
        expected_value = None
        if name == "PIP_CACHE_DIR":
            expected_value = expected_pip_cache
        elif name == "PIP_CONFIG_FILE":
            expected_value = "/dev/null"
        _require(
            pip_event["environment"][name] == expected_value,
            f"unexpected pip environment for {name}: {pip_event!r}",
        )


def _write_fake_python(directory: Path, python_log: Path, cli_log: Path) -> Path:
    fake_python = directory / "python"
    cli_program = "\n".join(
        (
            f"#!{sys.executable}",
            "import json",
            "import os",
            "from pathlib import Path",
            "import sys",
            f"log_path = Path({str(cli_log)!r})",
            "with log_path.open('a', encoding='utf-8') as stream:",
            "    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd()}, stream, ensure_ascii=False)",
            "    stream.write('\\n')",
        )
    )
    fake_python.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import json",
                "import os",
                "from pathlib import Path",
                "import stat",
                "import sys",
                f"log_path = Path({str(python_log)!r})",
                f"environment_names = {PYTHON_TOOL_ENV!r}",
                "with log_path.open('a', encoding='utf-8') as stream:",
                "    json.dump(",
                "        {",
                "            'argv': sys.argv[1:],",
                "            'cwd': os.getcwd(),",
                "            'environment': {name: os.environ.get(name) for name in environment_names},",
                "        },",
                "        stream,",
                "        ensure_ascii=False,",
                "    )",
                "    stream.write('\\n')",
                "raw_args = sys.argv[1:]",
                "args = raw_args[1:] if raw_args[:1] == ['-I'] else raw_args",
                "if args[:1] == ['-c']:",
                "    os.execv(sys.executable, [sys.executable, *raw_args])",
                "if args[:2] == ['-m', 'venv']:",
                "    venv_bin = Path(args[2]) / 'bin'",
                "    venv_bin.mkdir(parents=True, exist_ok=True)",
                "    (venv_bin / 'python').symlink_to(Path(sys.argv[0]).resolve())",
                "    raise SystemExit(0)",
                "if args[:2] == ['-m', 'pip'] and 'install' in args:",
                "    vexcalibur = Path(sys.argv[0]).parent / 'vexcalibur'",
                f"    vexcalibur.write_text({cli_program!r}, encoding='utf-8')",
                "    vexcalibur.chmod(vexcalibur.stat().st_mode | stat.S_IXUSR)",
                "    raise SystemExit(0)",
                "raise SystemExit(93)",
            )
        ),
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    return fake_python


def _write_hostile_commands(directory: Path, marker: Path) -> None:
    program = "\n".join(
        (
            f"#!{sys.executable}",
            "from pathlib import Path",
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')",
            "raise SystemExit(91)",
        )
    )
    for command_name in ("mkdir", "mktemp", "pip", "pip3", "pipx", "python", "python3", "uv", "vexcalibur"):
        command = directory / command_name
        command.write_text(program, encoding="utf-8")
        command.chmod(command.stat().st_mode | stat.S_IXUSR)


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _result_message(case: WrapperCase, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"case={case!r} returncode={completed.returncode} "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )
