from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from tests.fuzz.wrapper_boundary import exercise_fuzz_input


def test_one_input(data: bytes) -> None:
    exercise_fuzz_input(data)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input, enable_python_coverage=True)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
