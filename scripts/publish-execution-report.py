#!/usr/bin/env python3
"""Validate a Vexcalibur execution report and publish GitHub Action outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any


MAX_REPORT_BYTES = 16 * 1024
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_EXECUTION_REPORT_COUNT = 10_000_000
REPORT_KEYS = {
    "schema_version",
    "command",
    "vexcalibur_version",
    "inventory_source",
    "finding_source",
    "output_format",
    "component_count",
    "finding_count",
    "analysis_state_counts",
    "document",
}
DOCUMENT_KEYS = {"sha256", "bytes"}
ANALYSIS_STATES = (
    "resolved",
    "exploitable",
    "in_triage",
    "false_positive",
    "not_affected",
)
INVENTORY_SOURCES = {"sbom_file", "github_dependency_graph", "custom"}
FINDING_SOURCES = {"local_file", "public_osv", "custom_osv", "custom"}
OUTPUT_FORMATS = {"cyclonedx", "openvex", "csaf", "custom"}
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.!+_-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OUTPUT_NAMES = (
    "execution-report",
    "execution-report-path",
    "vexcalibur-version",
    "component-count",
    "finding-count",
    "analysis-state-counts",
    "output-format",
    "document-sha256",
    "document-bytes",
)


class ReportError(ValueError):
    """Raised when an execution report violates the action contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportError("execution report contains a duplicate JSON key")
        result[key] = value
    return result


def _read_report(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReportError(f"cannot open execution report: {error}") from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReportError("execution report is not a regular file")
        if metadata.st_size > MAX_REPORT_BYTES:
            raise ReportError(f"execution report exceeds {MAX_REPORT_BYTES} bytes")
        chunks = []
        remaining = MAX_REPORT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_REPORT_BYTES:
            raise ReportError(f"execution report exceeds {MAX_REPORT_BYTES} bytes")
        return data
    finally:
        os.close(descriptor)


def _require_exact_keys(
    value: object,
    expected: set[str],
    *,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"{field} must be a JSON object")
    actual = set(value)
    if actual != expected:
        details = []
        if expected - actual:
            details.append("missing fields")
        if actual - expected:
            details.append("unexpected fields")
        raise ReportError(f"{field} has invalid fields: {'; '.join(details)}")
    return value


def _require_bounded_integer(
    value: object,
    *,
    field: str,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > maximum
    ):
        raise ReportError(f"{field} must be an integer from 0 through {maximum}")
    return value


def _require_positive_integer(value: object, *, field: str) -> int:
    result = _require_bounded_integer(
        value,
        field=field,
        maximum=MAX_EXECUTION_REPORT_COUNT,
    )
    if result == 0:
        raise ReportError(f"{field} must be a positive integer")
    return result


def validate_report(raw_report: bytes) -> dict[str, Any]:
    try:
        text = raw_report.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReportError("execution report is not valid UTF-8") from error

    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ReportError:
        raise
    except (ValueError, RecursionError) as error:
        raise ReportError(f"execution report is not valid JSON: {error}") from error

    report = _require_exact_keys(value, REPORT_KEYS, field="execution report")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1:
        raise ReportError("schema_version must be the integer 1")
    if report["command"] != "generate":
        raise ReportError("command must be generate")

    version = report["vexcalibur_version"]
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        raise ReportError("vexcalibur_version has an invalid value")
    if (
        not isinstance(report["inventory_source"], str)
        or report["inventory_source"] not in INVENTORY_SOURCES
    ):
        raise ReportError("inventory_source has an invalid value")
    if (
        not isinstance(report["finding_source"], str)
        or report["finding_source"] not in FINDING_SOURCES
    ):
        raise ReportError("finding_source has an invalid value")
    if (
        not isinstance(report["output_format"], str)
        or report["output_format"] not in OUTPUT_FORMATS
    ):
        raise ReportError("output_format has an invalid value")

    _require_bounded_integer(
        report["component_count"],
        field="component_count",
        maximum=MAX_EXECUTION_REPORT_COUNT,
    )
    finding_count = _require_bounded_integer(
        report["finding_count"],
        field="finding_count",
        maximum=MAX_EXECUTION_REPORT_COUNT,
    )

    state_counts = report["analysis_state_counts"]
    if not isinstance(state_counts, dict):
        raise ReportError("analysis_state_counts must be a JSON object")
    unknown_states = set(state_counts) - set(ANALYSIS_STATES)
    if unknown_states:
        raise ReportError("analysis_state_counts has unexpected fields")
    state_total = sum(
        _require_positive_integer(
            count,
            field=f"analysis_state_counts.{state}",
        )
        for state, count in state_counts.items()
    )
    if state_total != finding_count:
        raise ReportError("analysis_state_counts values must sum to finding_count")

    document = _require_exact_keys(report["document"], DOCUMENT_KEYS, field="document")
    digest = document["sha256"]
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise ReportError("document.sha256 must be a lowercase SHA-256 digest")
    _require_bounded_integer(
        document["bytes"],
        field="document.bytes",
        maximum=MAX_DOCUMENT_BYTES,
    )
    if raw_report != _canonical_report_bytes(report):
        raise ReportError("execution report is not canonical JSON")
    return report


def _canonical_report_bytes(report: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            report,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def report_outputs(report: dict[str, Any], path: Path) -> dict[str, str]:
    state_counts = {
        state: report["analysis_state_counts"][state]
        for state in ANALYSIS_STATES
        if state in report["analysis_state_counts"]
    }
    document = report["document"]
    return {
        "execution-report": _canonical_report_bytes(report)
        .decode("ascii")
        .rstrip("\n"),
        "execution-report-path": str(path),
        "vexcalibur-version": report["vexcalibur_version"],
        "component-count": str(report["component_count"]),
        "finding-count": str(report["finding_count"]),
        "analysis-state-counts": json.dumps(
            state_counts,
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        "output-format": report["output_format"],
        "document-sha256": document["sha256"],
        "document-bytes": str(document["bytes"]),
    }


def publish_outputs(path: Path, outputs: dict[str, str]) -> None:
    if set(outputs) != set(OUTPUT_NAMES):
        raise ReportError("internal output set does not match the action contract")

    records = []
    for name in OUTPUT_NAMES:
        value = outputs[name]
        delimiter = f"vexcalibur_{secrets.token_hex(16)}"
        while delimiter in value:
            delimiter = f"vexcalibur_{secrets.token_hex(16)}"
        records.append(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    encoded = "".join(records).encode("utf-8")

    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReportError(f"cannot open GITHUB_OUTPUT: {error}") from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReportError("GITHUB_OUTPUT is not a regular file")
        original_size = metadata.st_size
        view = memoryview(encoded)
        try:
            while view:
                written = os.write(descriptor, view)
                if written <= 0 or written > len(view):
                    raise ReportError("could not write GITHUB_OUTPUT")
                view = view[written:]
        except BaseException as error:
            _rollback_partial_append(
                descriptor,
                original_size=original_size,
                maximum_append=len(encoded),
            )
            if isinstance(error, ReportError):
                raise
            if isinstance(error, OSError):
                raise ReportError(f"could not write GITHUB_OUTPUT: {error}") from error
            raise
    finally:
        os.close(descriptor)


def _rollback_partial_append(
    descriptor: int,
    *,
    original_size: int,
    maximum_append: int,
) -> None:
    try:
        current_size = os.fstat(descriptor).st_size
        if original_size <= current_size <= original_size + maximum_append:
            os.ftruncate(descriptor, original_size)
    except OSError:
        return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = validate_report(_read_report(args.report))
        if args.github_output is not None:
            outputs = report_outputs(report, args.report)
            publish_outputs(args.github_output, outputs)
    except ReportError as error:
        print(f"execution report error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
