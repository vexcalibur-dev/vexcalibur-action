#!/usr/bin/env python3
"""Command-line interface for Vexcalibur Action release state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from release_policy import (
    create_policy_attestation,
    read_ruleset,
    verify_attested_release_rulesets,
    verify_release_rulesets,
)
from release_state import (
    ReleaseMetadata,
    ReleaseStateError,
    TagMetadata,
    parse_release_json,
    parse_json,
    plan_release,
    read_manifest,
    read_manifest_at_commit,
    reconcile_remote_tag,
    render_release_notes,
    verify_github_release,
    verify_selected_pypi_artifact,
    verify_tag_reference,
    write_github_outputs,
)


def output_path(argument: Path | None) -> Path | None:
    if argument is not None:
        return argument
    value = os.environ.get("GITHUB_OUTPUT")
    return Path(value) if value else None


def command_plan(args: argparse.Namespace) -> None:
    plan = plan_release(args.tag)
    destination = output_path(args.github_output)
    if destination is None:
        for key, value in plan.github_outputs().items():
            print(f"{key}={value}")
    else:
        write_github_outputs(destination, plan.github_outputs())


def command_manifest(args: argparse.Namespace) -> None:
    if args.ref:
        manifest = read_manifest_at_commit(args.ref)
    else:
        manifest = read_manifest(args.path)
    destination = output_path(args.github_output)
    if destination is None:
        print(f"valid action compatibility declaration: {args.ref or args.path}")
    else:
        write_github_outputs(destination, manifest.github_outputs())


def command_render_notes(args: argparse.Namespace) -> None:
    notes = render_release_notes(
        tag=args.tag,
        commit=args.commit,
        previous_tag=args.previous_tag,
        notes_format=args.notes_format,
    )
    args.output.write_text(notes, encoding="utf-8")


def tag_metadata(args: argparse.Namespace) -> TagMetadata:
    return TagMetadata(
        args.tag,
        args.commit,
        args.compatibility_sha256,
        args.notes_format,
        args.notes_sha256,
    )


def command_reconcile_tag(args: argparse.Namespace) -> None:
    operation = reconcile_remote_tag(
        args.remote,
        tag_metadata(args),
        expected_graph_sha256=args.expected_tag_graph_sha256,
    )
    print(f"{operation} immutable release tag {args.tag}")


def command_verify_tag(args: argparse.Namespace) -> None:
    verify_tag_reference(args.ref, tag_metadata(args))
    print(f"verified immutable release tag {args.tag}")


def command_verify_release(args: argparse.Namespace) -> None:
    release = parse_release_json(args.release_json)
    notes = args.notes_file.read_text(encoding="utf-8")
    verify_github_release(
        release,
        expected_metadata=ReleaseMetadata(
            args.tag,
            args.commit,
            args.notes_format,
            args.compatibility_sha256,
        ),
        expected_notes=notes,
        expected_author=args.expected_author,
    )
    print(f"verified current GitHub Release projection for {args.tag}")


def command_verify_rulesets(args: argparse.Namespace) -> None:
    immutable = read_ruleset(args.immutable_json)
    creation = read_ruleset(args.creation_json)
    verify_release_rulesets(
        immutable,
        creation,
        app_id=args.app_id,
    )
    print("verified append-only release tag rules and bypass principals")


def command_attest_rulesets(args: argparse.Namespace) -> None:
    attestation = create_policy_attestation(
        read_ruleset(args.immutable_json),
        read_ruleset(args.creation_json),
        repository=args.repository,
        app_id=args.app_id,
    )
    print(json.dumps(attestation, sort_keys=True, separators=(",", ":")))


def command_verify_attested_rulesets(args: argparse.Namespace) -> None:
    verify_attested_release_rulesets(
        read_ruleset(args.immutable_json),
        read_ruleset(args.creation_json),
        read_ruleset(args.attestation),
        repository=args.repository,
        app_id=args.app_id,
    )
    print("verified live release rules against the owner policy attestation")


def command_verify_package_artifact(args: argparse.Namespace) -> None:
    selected = verify_selected_pypi_artifact(
        parse_json(args.pip_report.read_bytes(), source=str(args.pip_report)),
        parse_json(args.pypi_release.read_bytes(), source=str(args.pypi_release)),
        package_spec=args.package_spec,
    )
    destination = output_path(args.github_output)
    if destination is None:
        print(
            "verified non-yanked Vexcalibur artifact "
            f"{selected.filename} ({selected.sha256})"
        )
    else:
        write_github_outputs(destination, selected.github_outputs())


def add_tag_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--compatibility-sha256", required=True)
    parser.add_argument("--notes-format", required=True)
    parser.add_argument("--notes-sha256", required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(required=True)

    plan = commands.add_parser("plan", help="derive the next tag or recovery state")
    plan.add_argument(
        "--tag", default="", help="explicit tag or existing tag to recover"
    )
    plan.add_argument("--github-output", type=Path)
    plan.set_defaults(function=command_plan)

    manifest = commands.add_parser("manifest", help="validate compatibility metadata")
    source = manifest.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path)
    source.add_argument("--ref", help="full release commit to read")
    manifest.add_argument("--github-output", type=Path)
    manifest.set_defaults(function=command_manifest)

    notes = commands.add_parser(
        "render-notes", help="render deterministic release notes"
    )
    notes.add_argument("--tag", required=True)
    notes.add_argument("--commit", required=True)
    notes.add_argument("--previous-tag", default="")
    notes.add_argument("--notes-format", required=True)
    notes.add_argument("--output", type=Path, required=True)
    notes.set_defaults(function=command_render_notes)

    reconcile = commands.add_parser(
        "reconcile-tag", help="create or verify an append-only remote tag"
    )
    reconcile.add_argument("--remote", default="origin")
    reconcile.add_argument("--expected-tag-graph-sha256", required=True)
    add_tag_metadata_arguments(reconcile)
    reconcile.set_defaults(function=command_reconcile_tag)

    verify_tag = commands.add_parser("verify-tag", help="verify an annotated tag")
    verify_tag.add_argument("--ref", required=True)
    add_tag_metadata_arguments(verify_tag)
    verify_tag.set_defaults(function=command_verify_tag)

    verify_release = commands.add_parser(
        "verify-release", help="verify the current GitHub Release projection"
    )
    verify_release.add_argument("--release-json", type=Path, required=True)
    verify_release.add_argument("--notes-file", type=Path, required=True)
    verify_release.add_argument("--expected-author", required=True)
    verify_release.add_argument("--tag", required=True)
    verify_release.add_argument("--commit", required=True)
    verify_release.add_argument("--notes-format", required=True)
    verify_release.add_argument("--compatibility-sha256", required=True)
    verify_release.set_defaults(function=command_verify_release)

    verify_rulesets = commands.add_parser(
        "verify-rulesets", help="verify append-only release tag rules"
    )
    verify_rulesets.add_argument("--immutable-json", type=Path, required=True)
    verify_rulesets.add_argument("--creation-json", type=Path, required=True)
    verify_rulesets.add_argument("--app-id", type=int, required=True)
    verify_rulesets.set_defaults(function=command_verify_rulesets)

    attest_rulesets = commands.add_parser(
        "attest-rulesets", help="create owner-reviewed release policy evidence"
    )
    attest_rulesets.add_argument("--immutable-json", type=Path, required=True)
    attest_rulesets.add_argument("--creation-json", type=Path, required=True)
    attest_rulesets.add_argument("--repository", required=True)
    attest_rulesets.add_argument("--app-id", type=int, required=True)
    attest_rulesets.set_defaults(function=command_attest_rulesets)

    verify_attested = commands.add_parser(
        "verify-attested-rulesets",
        help="bind live release rules to owner-reviewed evidence",
    )
    verify_attested.add_argument("--immutable-json", type=Path, required=True)
    verify_attested.add_argument("--creation-json", type=Path, required=True)
    verify_attested.add_argument("--attestation", type=Path, required=True)
    verify_attested.add_argument("--repository", required=True)
    verify_attested.add_argument("--app-id", type=int, required=True)
    verify_attested.set_defaults(function=command_verify_attested_rulesets)

    verify_package = commands.add_parser(
        "verify-package-artifact",
        help="verify the Vexcalibur artifact selected by pip",
    )
    verify_package.add_argument("--pip-report", type=Path, required=True)
    verify_package.add_argument("--pypi-release", type=Path, required=True)
    verify_package.add_argument("--package-spec", required=True)
    verify_package.add_argument("--github-output", type=Path)
    verify_package.set_defaults(function=command_verify_package_artifact)

    return root


def main() -> None:
    args = parser().parse_args()
    try:
        args.function(args)
    except (OSError, ReleaseStateError) as exc:
        raise SystemExit(f"release state error: {exc}") from exc


if __name__ == "__main__":
    main()
