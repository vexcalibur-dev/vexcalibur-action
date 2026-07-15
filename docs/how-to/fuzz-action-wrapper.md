# Fuzz the Action wrapper

Use the wrapper fuzzing harness when you change installation, environment isolation, constraints, or argument forwarding in `scripts/run-vexcalibur.sh`. This maintainer workflow checks the real Bash wrapper with local fake Python, pip, and Vexcalibur executables. It never installs a Vexcalibur package, invokes a package manager, or contacts a network service during a test case.

The deterministic property suite is a required pull-request check. A separate Atheris campaign runs every Wednesday and can be dispatched from GitHub Actions. The scheduled campaign is reliability testing for the wrapper boundary, not a replacement for the ordinary regression suite or fuzzing in the Vexcalibur Python package.

## Understand the boundary

The shared decoder in `tests/fuzz/wrapper_boundary.py` turns at most 65,536 bytes into these inputs:

- `package-spec` and `allow-development-package-spec`;
- an absent, valid, missing, or relative constraints path; and
- an unset or newline-delimited `args` value.

The harness starts `scripts/run-vexcalibur.sh` with an explicit minimal environment. Local fakes record JSON argument arrays at the setup-Python, virtual-environment, pip, and Vexcalibur boundaries.

The setup fake records its argument vector and then replaces itself with the real isolated Python interpreter, which executes the wrapper's exact inline directory-creation program. The virtual-environment, pip, and Vexcalibur fakes simulate only their local side effects.

The reference model then verifies:

- release package policy and validation order;
- one literal pip argument for the package and one for the constraints path;
- one CLI argument per nonblank line, with exactly one trailing carriage return removed;
- literal spaces, quotes, metacharacters, glob characters, redirection characters, and Unicode;
- isolation from caller `PATH`, `BASH_ENV`, `ENV`, `PYTHON*`, `PIP_*`, `PIPX_*`, and Vexcalibur executable overrides; and
- creation of the managed environment directly below `RUNNER_TEMP`.

The subprocess receives no repository token, service credential, or inherited developer environment. Its fake installer performs no network operation.

## Run the deterministic properties

You need Bash, Linux, and Python 3.14. From the repository root, activate a disposable virtual environment and install the development lock:

```bash
python3.14 -m venv /tmp/vexcalibur-action-dev
source /tmp/vexcalibur-action-dev/bin/activate
python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-dev.txt
python -m unittest tests.fuzz.wrapper_properties
```

The command runs 40 deterministic Hypothesis examples plus the fixed corpus checks. A successful run ends with `OK`. Hypothesis keeps no example database, so pull-request runners execute the same deterministic campaign and still shrink a failure within the current run.

Each wrapper subprocess has a two-second timeout. The pull-request job has a five-minute limit.

## Run the Atheris campaign

This repository supports the Atheris 3.1.0 harness on CPython 3.14 on Linux x86-64. Install the separate fuzz lock in a disposable environment:

```bash
python3.14 -m venv /tmp/vexcalibur-action-fuzz
source /tmp/vexcalibur-action-fuzz/bin/activate
python -m pip install \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-fuzz.txt
FUZZ_MAX_TOTAL_TIME=30 scripts/run-atheris.sh
```

The script writes generated corpus entries to `.fuzz-corpus/wrapper/` and crash reproducers to `fuzz-artifacts/wrapper/`; both paths are ignored by Git. A successful 30-second run prints libFuzzer final statistics and exits with status `0`.

Installing the fuzz lock and auditing it require access to the Python Package Index and the vulnerability advisory service. The property cases and Atheris campaign make no network requests after setup.

The runner enforces these limits:

| Limit | Local default | Scheduled value | Hard rule |
| --- | ---: | ---: | --- |
| Input length | 65,536 bytes | 65,536 bytes | `FUZZ_MAX_LEN` cannot exceed 65,536 |
| Wrapper subprocess | 2 seconds | 2 seconds | Set in the shared harness |
| Atheris unit | 5 seconds | 5 seconds | Positive integer only |
| Resident memory | 2,048 MiB | 2,048 MiB | Positive integer only |
| Campaign | 30 seconds | 120 seconds | Positive integer only |
| Workflow job | Not applicable | 20 minutes | GitHub Actions timeout |

You may lower the environment-controlled runner limits for a quick local check. Do not raise the input cap or subprocess timeout without reviewing the environment-size and CI denial-of-service implications.

## Know what coverage means

Atheris instruments the Python decoder, model, and harness. It cannot measure branch coverage inside the Bash subprocess. Repeatedly invoking the real wrapper can still expose crashes, timeouts, and disagreements with the model, but an Atheris coverage increase does not mean Bash branches received equivalent coverage.

The decoder preserves valid UTF-8. Because POSIX environment variables cannot contain NUL or surrogate-escaped malformed UTF-8, each such byte maps to the one-byte question mark (`?`) before process creation. This keeps the encoded environment value within the 65,536-byte input cap. The harness therefore cannot distinguish those bytes from a literal question mark and does not represent a literal NUL in an action input. It also models Linux Bash behavior; run the ordinary tests for the rest of the repository contract.

## Maintain the corpus

Committed seeds live in `tests/fuzz/corpus/wrapper/`. `tests/fuzz/corpus-manifest.json` names every seed and locks its expected success state and CLI argument array. Seeds must remain small, synthetic, and free of private repository names, private package inventory, credentials, and production paths.

Keep a seed only when it represents a distinct boundary such as carriage-return and line-feed handling, blank lines, literal metacharacters, Unicode, package policy, or a constraints state. Do not commit bulk generated corpus entries. The manifest test rejects an undocumented seed and any seed larger than 1,024 bytes or containing NUL.

When a campaign finds a failure:

1. Stop sharing the reproducer if the behavior may have security impact.
2. Reproduce it locally with the same commit and fuzz lock:

   ```bash
   python -m tests.fuzz.fuzz_wrapper -runs=1 PATH_TO_REPRODUCER
   ```

3. Minimize the input with Atheris or Hypothesis while preserving the failure.
4. Add the minimized case as an ordinary regression test before changing the committed corpus.
5. Fix the wrapper, model, or harness according to the documented action contract.
6. Run the deterministic properties, ordinary unit tests, shell checks, and a local Atheris campaign.

`PATH_TO_REPRODUCER` is a local path to the generated crash file. Do not paste an unreviewed reproducer into an issue, pull request, workflow log, or chat.

## Triage failures privately

This repository is public, so assume scheduled Actions logs and uploaded artifacts are public. The workflow uploads a synthetic crash reproducer only when the campaign fails and retains it for seven days. The harness does not derive fuzz bytes from environment variables or repository files, but review the artifact before redistributing it.

Argument execution, installer redirection, isolation escape, or credential exposure may be a security issue. Follow the [private security reporting process](../../SECURITY.md) and keep exploit details out of public issues and pull requests. The repository owner in [CODEOWNERS](../../.github/CODEOWNERS) owns campaign triage, corpus review, dependency refreshes, and conversion of crashes into regression tests.

Delete local state when triage is complete:

```bash
rm -rf .fuzz-corpus fuzz-artifacts \
  /tmp/vexcalibur-action-dev /tmp/vexcalibur-action-fuzz
```
