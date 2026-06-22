#!/usr/bin/env bash
set -euo pipefail

package_spec="${VEXCALIBUR_PACKAGE_SPEC:-vexcalibur}"
command_name="${VEXCALIBUR_COMMAND:-help}"
purls="${VEXCALIBUR_PURLS:-}"
skip_install="${VEXCALIBUR_SKIP_INSTALL:-false}"
purl_args=()

read_purl_args() {
  local purl_line
  purl_args=()
  while IFS= read -r purl_line || [[ -n "$purl_line" ]]; do
    purl_line="${purl_line%$'\r'}"
    if [[ -n "$purl_line" ]]; then
      purl_args+=("$purl_line")
    fi
  done <<<"$purls"
}

resolve_vexcalibur_bin() {
  if [[ -n "${VEXCALIBUR_BIN:-}" ]]; then
    printf '%s\n' "$VEXCALIBUR_BIN"
    return
  fi

  if [[ -x "$HOME/.local/bin/vexcalibur" ]]; then
    printf '%s\n' "$HOME/.local/bin/vexcalibur"
    return
  fi

  if [[ -x "/opt/pipx_bin/vexcalibur" ]]; then
    printf '%s\n' "/opt/pipx_bin/vexcalibur"
    return
  fi

  if command -v vexcalibur >/dev/null 2>&1; then
    command -v vexcalibur
    return
  fi

  echo "vexcalibur executable was not found after installation" >&2
  exit 127
}

if [[ "$skip_install" != "true" ]]; then
  python -m pip install --user pipx
  python -m pipx install --force "$package_spec"
fi

case "$command_name" in
  help)
    ;;
  query-osv)
    read_purl_args
    if [[ ${#purl_args[@]} -eq 0 ]]; then
      echo "purls input is required when command is query-osv" >&2
      exit 2
    fi
    ;;
  *)
    echo "unsupported command: $command_name" >&2
    exit 2
    ;;
esac

vexcalibur_bin="$(resolve_vexcalibur_bin)"

case "$command_name" in
  help)
    "$vexcalibur_bin" --help
    ;;
  query-osv)
    "$vexcalibur_bin" query-osv "${purl_args[@]}"
    ;;
esac
