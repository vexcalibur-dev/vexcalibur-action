# Contributing

Vexcalibur Action is pre-alpha. Keep action inputs narrow until the Vexcalibur package exposes stable commands.

## Development

Run local checks from the repository root:

```bash
bash -n scripts/run-vexcalibur.sh
python -m unittest discover -s tests
```

Pull requests should include:

- A short description of the workflow behavior being changed.
- Unit tests for `scripts/run-vexcalibur.sh` when input handling changes.
- The commands used to verify the change.
- Notes about GitHub Actions permissions, network access, or secret handling when relevant.
