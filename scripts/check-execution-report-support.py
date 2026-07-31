#!/usr/bin/env python3
"""Detect the installed Vexcalibur execution-report contract."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType


EXPECTED_SCHEMA_VERSION = 1
PACKAGE_NAME = "vexcalibur"
MODULE_NAME = "vexcalibur.api"
SCHEMA_ATTRIBUTE = "EXECUTION_REPORT_SCHEMA_VERSION"
_MISSING = object()


def _load_api_module() -> ModuleType | None:
    if importlib.util.find_spec(PACKAGE_NAME) is None:
        return None
    if importlib.util.find_spec(MODULE_NAME) is None:
        return None
    return importlib.import_module(MODULE_NAME)


def detect_support() -> int:
    """Return 0 for schema 1, 1 for an older package, or 2 for incompatibility."""
    try:
        module = _load_api_module()
        if module is None:
            return 1
        namespace = vars(module)
        schema_version = namespace.get(SCHEMA_ATTRIBUTE, _MISSING)
        if schema_version is _MISSING and "__getattr__" not in namespace:
            return 1
        if schema_version is _MISSING:
            schema_version = getattr(module, SCHEMA_ATTRIBUTE)
    except KeyboardInterrupt:
        raise
    except BaseException:
        print(
            "could not inspect the installed Vexcalibur execution-report contract",
            file=sys.stderr,
        )
        return 2

    if type(schema_version) is not int or schema_version != EXPECTED_SCHEMA_VERSION:
        print(
            "the installed Vexcalibur package exposes an unsupported "
            "execution-report contract",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(detect_support())
