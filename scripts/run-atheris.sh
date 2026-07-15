#!/usr/bin/env bash
set -euo pipefail

readonly MAX_SUPPORTED_INPUT_BYTES=65536
readonly DEFAULT_MAX_TOTAL_TIME=30
readonly DEFAULT_UNIT_TIMEOUT=5
readonly DEFAULT_RSS_LIMIT_MB=2048

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
corpus_dir="${FUZZ_CORPUS_DIR:-${repository_root}/.fuzz-corpus/wrapper}"
artifact_dir="${FUZZ_ARTIFACT_DIR:-${repository_root}/fuzz-artifacts/wrapper}"
max_len="${FUZZ_MAX_LEN:-${MAX_SUPPORTED_INPUT_BYTES}}"
max_total_time="${FUZZ_MAX_TOTAL_TIME:-${DEFAULT_MAX_TOTAL_TIME}}"
unit_timeout="${FUZZ_UNIT_TIMEOUT:-${DEFAULT_UNIT_TIMEOUT}}"
rss_limit_mb="${FUZZ_RSS_LIMIT_MB:-${DEFAULT_RSS_LIMIT_MB}}"

require_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${name} must be a positive integer; found ${value}" >&2
    exit 2
  fi
}

require_positive_integer FUZZ_MAX_LEN "${max_len}"
require_positive_integer FUZZ_MAX_TOTAL_TIME "${max_total_time}"
require_positive_integer FUZZ_UNIT_TIMEOUT "${unit_timeout}"
require_positive_integer FUZZ_RSS_LIMIT_MB "${rss_limit_mb}"

if (( max_len > MAX_SUPPORTED_INPUT_BYTES )); then
  echo "FUZZ_MAX_LEN cannot exceed ${MAX_SUPPORTED_INPUT_BYTES}; found ${max_len}" >&2
  exit 2
fi

mkdir -p "${corpus_dir}" "${artifact_dir}"
cd "${repository_root}"

python -m tests.fuzz.fuzz_wrapper \
  "${corpus_dir}" \
  "${repository_root}/tests/fuzz/corpus/wrapper" \
  "-artifact_prefix=${artifact_dir}/" \
  "-max_len=${max_len}" \
  "-max_total_time=${max_total_time}" \
  "-timeout=${unit_timeout}" \
  "-rss_limit_mb=${rss_limit_mb}" \
  -print_final_stats=1
