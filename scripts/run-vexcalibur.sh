#!/usr/bin/env bash
set -euo pipefail

package_spec="${VEXCALIBUR_PACKAGE_SPEC:-vexcalibur}"
command_name="${VEXCALIBUR_COMMAND:-help}"
purls="${VEXCALIBUR_PURLS:-}"
skip_install="${VEXCALIBUR_SKIP_INSTALL:-false}"

if [[ "$skip_install" != "true" ]]; then
  python -m pip install --user pipx
  pipx_bin="${PIPX_BIN:-$HOME/.local/bin/pipx}"
  "$pipx_bin" install --force "$package_spec"
fi

vexcalibur_bin="${VEXCALIBUR_BIN:-$HOME/.local/bin/vexcalibur}"

case "$command_name" in
  help)
    "$vexcalibur_bin" --help
    ;;
  query-osv)
    if [[ -z "$purls" ]]; then
      echo "purls input is required when command is query-osv" >&2
      exit 2
    fi

    mapfile -t purl_args <<<"$purls"
    "$vexcalibur_bin" query-osv "${purl_args[@]}"
    ;;
  *)
    echo "unsupported command: $command_name" >&2
    exit 2
    ;;
esac
