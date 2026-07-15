#!/usr/bin/env bash
set -euo pipefail

readonly UV_VERSION="0.11.28"
REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPOSITORY_ROOT

cd "${REPOSITORY_ROOT}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv ${UV_VERSION} is required to refresh dependency locks." >&2
  exit 1
fi

actual_uv_version="$(uv --version | awk '{print $2}')"
if [[ "${actual_uv_version}" != "${UV_VERSION}" ]]; then
  echo "uv ${UV_VERSION} is required; found ${actual_uv_version}." >&2
  exit 1
fi

compile_lock() {
  local input_path="$1"
  local output_path="$2"

  uv pip compile \
    --quiet \
    --python-version 3.14 \
    --universal \
    --only-binary=:all: \
    --emit-build-options \
    --generate-hashes \
    --upgrade \
    --custom-compile-command "scripts/refresh-requirements.sh" \
    --output-file "${output_path}" \
    "${input_path}"
}

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/vexcalibur-action-locks.XXXXXX")"
trap 'rm -rf "${temporary_directory}"' EXIT

compile_lock requirements-release.in "${temporary_directory}/requirements-release.txt"
compile_lock requirements-dev.in "${temporary_directory}/requirements-dev.txt"

mv "${temporary_directory}/requirements-release.txt" requirements-release.txt
mv "${temporary_directory}/requirements-dev.txt" requirements-dev.txt
