# Contributing

Vexcalibur Action is usable for the workflows documented in the README and
reference docs. Keep action inputs narrow until a compatibility change has
matching CI coverage and documentation.

## Development

Run local checks from the repository root:

```bash
python -m pip install -r requirements-dev.txt
bash -n scripts/*.sh
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --
shellcheck scripts/*.sh
ASDF_ACTIONLINT_VERSION=1.7.12 actionlint .github/workflows/*.yml
python -m unittest discover -s tests
```

Expected success signal: ShellCheck, actionlint, secret scanning, and unit tests
exit successfully. Install actionlint through your local toolchain; hosted CI
installs it before running the same workflow validation gate.

Pull requests should include:

- A short description of the workflow behavior being changed.
- Unit tests for `scripts/run-vexcalibur.sh` when input handling changes.
- Release-version tests for `scripts/next-release-tag.sh` when release behavior
  changes.
- The commands used to verify the change.
- Notes about GitHub Actions permissions, network access, or secret handling when relevant.
- Updates to `docs/reference/compatibility.md` and
  `docs/how-to/release-action.md` when release policy, supported package
  versions, or maintainer steps change.
