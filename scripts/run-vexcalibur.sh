#!/bin/bash -p
set -euo pipefail

package_spec="${VEXCALIBUR_PACKAGE_SPEC:-}"
allow_development_package_spec="${VEXCALIBUR_ALLOW_DEVELOPMENT_PACKAGE_SPEC:-false}"
if [[ -v VEXCALIBUR_ARGS ]]; then
  raw_cli_args="$VEXCALIBUR_ARGS"
else
  raw_cli_args="--help"
fi
runner_temp="${RUNNER_TEMP:-}"
python_bin="${VEXCALIBUR_PYTHON:-}"
cli_args=()
action_work_dir=""
pip_cache_dir=""
venv_dir=""
venv_python=""
vexcalibur_bin=""

export -n package_spec allow_development_package_spec raw_cli_args
export -n runner_temp python_bin action_work_dir pip_cache_dir venv_dir venv_python vexcalibur_bin
unset VEXCALIBUR_ARGS VEXCALIBUR_PURLS args purls

is_true() {
  [[ "$1" == "true" ]]
}

unset_python_tool_env() {
  local env_name
  while IFS= read -r env_name; do
    case "$env_name" in
      PYTHON*|PIP_*|PIPX_*)
        unset "$env_name"
        ;;
    esac
  done < <(compgen -e)
}

validate_package_spec() {
  if [[ -z "$package_spec" ]]; then
    echo "package-spec is required" >&2
    exit 2
  fi

  if is_true "$allow_development_package_spec"; then
    return
  fi

  if [[ "$package_spec" =~ ^vexcalibur==[0-9][0-9A-Za-z.!+_-]*$ ]]; then
    return
  fi

  echo "package-spec must be an exact Vexcalibur release such as vexcalibur==0.1.1" >&2
  echo "set allow-development-package-spec to true only for development workflows" >&2
  exit 2
}

read_cli_args() {
  local arg_line
  cli_args=()
  while IFS= read -r arg_line || [[ -n "$arg_line" ]]; do
    arg_line="${arg_line%$'\r'}"
    if [[ -n "$arg_line" ]]; then
      cli_args+=("$arg_line")
    fi
  done <<<"$raw_cli_args"
}

configure_venv_paths() {
  if [[ -z "$runner_temp" ]]; then
    echo "RUNNER_TEMP is required to isolate the Vexcalibur installation" >&2
    exit 2
  fi

  if [[ -z "$python_bin" ]]; then
    echo "VEXCALIBUR_PYTHON is required from actions/setup-python" >&2
    exit 2
  fi

  if [[ ! -x "$python_bin" ]]; then
    echo "VEXCALIBUR_PYTHON is not executable: $python_bin" >&2
    exit 2
  fi

  action_work_dir="$("$python_bin" -I -c '
from pathlib import Path
import sys
import tempfile

runner_temp = Path(sys.argv[1])
runner_temp.mkdir(parents=True, exist_ok=True)
action_work_dir = Path(tempfile.mkdtemp(prefix="vexcalibur-action.", dir=runner_temp))
(action_work_dir / "pip-cache").mkdir()
print(action_work_dir)
' "$runner_temp")"
  pip_cache_dir="$action_work_dir/pip-cache"
  venv_dir="$action_work_dir/venv"
}

resolve_vexcalibur_bin() {
  if [[ -x "$venv_dir/bin/vexcalibur" ]]; then
    printf '%s\n' "$venv_dir/bin/vexcalibur"
    return
  fi

  echo "vexcalibur executable was not found after installation" >&2
  exit 127
}

validate_package_spec
read_cli_args

unset_python_tool_env
configure_venv_paths
cd "$action_work_dir"
"$python_bin" -I -m venv "$venv_dir"
venv_python="$venv_dir/bin/python"
PIP_CONFIG_FILE=/dev/null PIP_CACHE_DIR="$pip_cache_dir" "$venv_python" -I -m pip --isolated --no-cache-dir install "$package_spec"

vexcalibur_bin="$(resolve_vexcalibur_bin)"
"$vexcalibur_bin" "${cli_args[@]}"
