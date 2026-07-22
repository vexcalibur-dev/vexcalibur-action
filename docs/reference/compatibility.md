# Action and package compatibility

Vexcalibur Action installs a caller-selected Vexcalibur Python package at run
time. The wrapper and package are separate trust boundaries, so reviewed
workflows pin both.

## Source of truth

A strict `vMAJOR.MINOR.PATCH` tag identifies an action release. The tag is
annotated, points to one exact commit, and can never move or be reused.

A current-format tag has canonical annotation metadata, and its commit contains
`action-compatibility.json`:

```text
protected annotated tag
  -> exact action commit
     -> action-compatibility.json
```

The declaration names the Vexcalibur package and Python feature versions that
release-package CI tested. It does not contain an action version, tag, or SHA.
The tag supplies that identity at publication time.

Tags published before the canonical annotation and compatibility declaration
are legacy tags. Their commits contain a historical compatibility table instead
of `action-compatibility.json`. Legacy GitHub Release records may also report
`immutable: false`; the protected annotated Git tag is still the release
identity. When the current workflow was introduced, every previously published
tag fell into this legacy category.

This repository keeps no prospective release version. It also keeps no moving
version tag. If the project ever needs a mutable compatibility alias, that
alias will be a branch.

## Find the latest tested pair

Run these commands in Bash from any working directory. They need Git, curl,
Python 3, and awk. They read public repository data, so they don't need a GitHub
token or an authenticated `gh` session.

```bash
set -euo pipefail

REPOSITORY=vexcalibur-dev/vexcalibur-action
REMOTE="https://github.com/${REPOSITORY}.git"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

ACTION_TAG="$(
  git ls-remote --refs --tags "${REMOTE}" 'refs/tags/v*' |
    awk '{sub("refs/tags/", "", $2); print $2}' |
    python3 -c '
import re
import sys

pattern = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
tags = []
for line in sys.stdin:
    tag = line.strip()
    match = pattern.fullmatch(tag)
    if match and all(len(part) <= 6 and int(part) <= 999999 for part in match.groups()):
        tags.append(tag)
if not tags:
    raise SystemExit("no strict semantic release tag found")
print(max(tags, key=lambda tag: tuple(int(part) for part in tag[1:].split("."))))
'
)"

ACTION_SHA="$(
  git ls-remote --tags "${REMOTE}" "refs/tags/${ACTION_TAG}^{}" |
    awk 'NR == 1 {print $1}'
)"
if [[ ! "${ACTION_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "release tag did not resolve to a full commit SHA" >&2
  exit 1
fi

COMPATIBILITY_FILE="${WORK_DIR}/action-compatibility.json"
if curl --fail --silent --location \
  "https://raw.githubusercontent.com/${REPOSITORY}/${ACTION_SHA}/action-compatibility.json" \
  > "${COMPATIBILITY_FILE}"; then
  PACKAGE_SPEC="$(
    python3 -c '
import json
import re
import sys

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result

with open(sys.argv[1], encoding="utf-8") as stream:
    document = json.load(stream, object_pairs_hook=unique_object)

if set(document) != {"python_versions", "vexcalibur_package"}:
    raise SystemExit("invalid compatibility declaration fields")
package = document["vexcalibur_package"]
package_pattern = re.compile(
    r"^vexcalibur==(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?"
    r"(?:\.dev[0-9]+)?(?:\+[0-9A-Za-z]+(?:[._-][0-9A-Za-z]+)*)?$"
)
if not isinstance(package, str) or package_pattern.fullmatch(package) is None:
    raise SystemExit("invalid Vexcalibur package declaration")
versions = document["python_versions"]
if (
    not isinstance(versions, list)
    or not versions
    or any(not isinstance(value, str) or re.fullmatch(r"3\.(?:[0-9]|[1-9][0-9])", value) is None for value in versions)
    or len(versions) != len(set(versions))
    or versions != sorted(versions, key=lambda value: int(value[2:]))
):
    raise SystemExit("invalid Python compatibility declaration")
print(package)
' "${COMPATIBILITY_FILE}"
  )"
else
  LEGACY_FILE="${WORK_DIR}/compatibility.md"
  curl --fail --silent --show-error --location \
    "https://raw.githubusercontent.com/${REPOSITORY}/${ACTION_SHA}/docs/reference/compatibility.md" \
    > "${LEGACY_FILE}"
  PACKAGE_SPEC="$(
    awk -F '`' -v tag="${ACTION_TAG}" '$2 == tag {print $4; exit}' \
      "${LEGACY_FILE}"
  )"
fi

if ! python3 -c '
import re
import sys

pattern = re.compile(
    r"^vexcalibur==(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?"
    r"(?:\.dev[0-9]+)?(?:\+[0-9A-Za-z]+(?:[._-][0-9A-Za-z]+)*)?$"
)
raise SystemExit(0 if pattern.fullmatch(sys.argv[1]) else 1)
' "${PACKAGE_SPEC}"; then
  echo "release metadata did not contain an exact Vexcalibur package" >&2
  exit 1
fi

printf 'Action tag: %s\nAction SHA: %s\nPackage: %s\n' \
  "${ACTION_TAG}" "${ACTION_SHA}" "${PACKAGE_SPEC}"
```

The output supplies the two values needed by a workflow:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@REPLACE_WITH_ACTION_SHA
  with:
    package-spec: REPLACE_WITH_VEXCALIBUR_PACKAGE_SPEC
    args: --help
```

Replace both placeholders. The full action commit is the clearest consumer pin.
The readable release tag is also permanent, but the SHA makes the selected Git
object visible during review.

The fallback handles legacy tags from before `action-compatibility.json`
existed. It reads the matching row from the historical reference stored at the
already resolved commit. Current-format tags must use the JSON declaration.

## Declaration schema

The top-level JSON object contains exactly two fields. Unknown fields fail
validation.

| Field | Type | Constraint | Meaning |
| --- | --- | --- | --- |
| `vexcalibur_package` | String | One exact `vexcalibur==VERSION` requirement with three numeric components and optional PEP 440 pre-release, post-release, development, or local suffixes | Package exercised by released-package CI. |
| `python_versions` | Array of strings | Nonempty, unique, ascending Python 3 `major.minor` values | Python versions used by the released-package help and local OSV-compatible query matrix. |

The file itself contains no action release identity. Its raw SHA-256 digest is
stored in both the annotated tag and the GitHub Release notes. The tag also
stores the release-note protocol and digest so an interrupted release can be
recovered without changing the tag.

## Pinning levels

| Boundary | Readable pin | Stronger repeatability |
| --- | --- | --- |
| Action wrapper | Protected annotated release tag | Dereferenced release commit SHA |
| Vexcalibur package | Exact spec from the tag's declaration | The same exact spec with index and artifact hashes checked by local policy |
| Transitive Python packages | Resolver-selected versions | Complete pip constraints passed through `constraints-file` |

An exact Vexcalibur package spec does not freeze its dependencies. Without
`constraints-file`, pip can select newer compatible transitive releases on a
later run. See the [`constraints-file` reference](action.md#constraints-file).

## Development package specs

The action accepts only an exact `vexcalibur==...` requirement by default. Git
URLs, local wheels, source directories, and other specs require an explicit
development opt-in:

```yaml
- uses: vexcalibur-dev/vexcalibur-action@main
  with:
    package-spec: git+https://github.com/vexcalibur-dev/vexcalibur.git@main
    allow-development-package-spec: "true"
    args: --help
```

Use this form for compatibility development, not for releases. Pin a full
Vexcalibur commit SHA instead of `@main` when a development test must be
repeatable.

## CI coverage

The required `CI result` job aggregates these checks:

1. Bash syntax, ShellCheck, actionlint, YAML and JSON parsing, secret scanning,
   unit tests, and the public Action contract guard.
2. A wheel built from the Vexcalibur repository's `main` branch.
3. The candidate wrapper's help and local OSV-compatible query paths on each
   Python version in `action-compatibility.json`.
4. CycloneDX, OpenVEX, and CSAF generation against controlled local fixtures.
5. The exact PyPI release named by `action-compatibility.json`. On every
   declared Python version, CI resolves the wheel under isolated pip settings,
   rejects it when PyPI marks it as yanked, and verifies its PyPI SHA-256.
   Released-package E2E jobs install that uploaded wheel instead of resolving
   the package a second time.
6. Dependency review on pull requests and OpenSSF Scorecard.

The query jobs use a loopback service. Artifact jobs use offline findings. No
compatibility check sends package URLs or SBOM inventory to the public OSV API.

The contract guard compares `action.yml` with the highest release tag. Adding
an optional input, an input with a default, or an output requires at least a
minor Conventional Commit bump. Removing an input or output, changing a default
or output value, requiring a new caller value, or changing `runs.using` requires
a major bump. Adding an input deprecation warning requires a minor bump;
changing or removing one requires a patch. Description-only changes require no
bump.

Runner and output coverage remain current CI facts rather than immutable
manifest claims. See [Action reference](action.md) for the runner contract.

## Maintenance contract

A compatibility change requires a release even when wrapper behavior stays the
same. Maintainers update `action-compatibility.json` only with a package and
Python versions that the same commit's CI will exercise.

CI compares the declaration with the highest release tag. The release planner
repeats that comparison against the tag graph it uses to calculate the next
version. A tested package change requires a patch, adding a Python version
requires a minor release, and removing one requires a major release. JSON
formatting and key order don't affect the comparison.

The release workflow reads that declaration from the target commit. It stores
the declaration digest in deterministic, scanned release notes and in the
append-only tag annotation. See [Release the action](../how-to/release-action.md)
for publication and recovery.
