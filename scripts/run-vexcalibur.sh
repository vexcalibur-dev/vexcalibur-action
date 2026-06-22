#!/usr/bin/env bash
set -euo pipefail

package_spec="${VEXCALIBUR_PACKAGE_SPEC:-vexcalibur}"
command_name="${VEXCALIBUR_COMMAND:-help}"
purls="${VEXCALIBUR_PURLS:-}"
skip_install="${VEXCALIBUR_SKIP_INSTALL:-false}"

if [[ "$skip_install" != "true" ]]; then
  python -m pip install --user pipx
  python -m pipx install --force "$package_spec"
fi

case "$command_name" in
  help)
    ;;
  query-osv)
    if [[ -z "$purls" ]]; then
      echo "purls input is required when command is query-osv" >&2
      exit 2
    fi
    ;;
  *)
    echo "unsupported command: $command_name" >&2
    exit 2
    ;;
esac

vexcalibur_bin="${VEXCALIBUR_BIN:-}"
if [[ -z "$vexcalibur_bin" ]]; then
  if command -v vexcalibur >/dev/null 2>&1; then
    vexcalibur_bin="vexcalibur"
  elif [[ -x "$HOME/.local/bin/vexcalibur" ]]; then
    vexcalibur_bin="$HOME/.local/bin/vexcalibur"
  elif [[ -x "/opt/pipx_bin/vexcalibur" ]]; then
    vexcalibur_bin="/opt/pipx_bin/vexcalibur"
  else
    echo "vexcalibur executable was not found after installation" >&2
    exit 127
  fi
fi

case "$command_name" in
  help)
    "$vexcalibur_bin" --help
    ;;
  query-osv)
    mapfile -t purl_args <<<"$purls"
    "$vexcalibur_bin" query-osv "${purl_args[@]}"
    ;;
esac
