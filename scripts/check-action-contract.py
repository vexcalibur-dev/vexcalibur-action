#!/usr/bin/env python3
"""Require commit history to describe public Action contract changes."""

from __future__ import annotations

import argparse

from action_contract import ActionContractError
from release_common import (
    BUMP_RANK,
    git_output,
    require_commit,
)
from release_state import (
    ReleaseStateError,
    classify_range,
    classify_release_requirement,
    release_tags,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--head", default="HEAD")
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        tags = release_tags(head=args.head)
        if not tags:
            print("no released action contract exists yet")
            return
        head_commit = git_output("rev-parse", "--verify", f"{args.head}^{{commit}}")
        require_commit(head_commit)
        latest = tags[-1]
        requirement = classify_release_requirement(
            latest.commit,
            head_commit,
        )
        required_bump = requirement.required_bump
        history_bump = classify_range(f"{latest.name}..{args.head}")
        if BUMP_RANK[history_bump] < BUMP_RANK[required_bump]:
            reason_lines = "\n".join(f"- {reason}" for reason in requirement.reasons)
            raise ActionContractError(
                f"release metadata requires a {required_bump} bump, "
                f"but commit history requires {history_bump}:\n{reason_lines}"
            )
        print(
            f"release metadata requires {required_bump}; "
            f"commit history requires {history_bump}"
        )
    except (ActionContractError, OSError, ReleaseStateError) as exc:
        raise SystemExit(f"action contract error: {exc}") from exc


if __name__ == "__main__":
    main()
