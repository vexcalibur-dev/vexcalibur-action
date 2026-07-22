"""Repository-policy validation for append-only action releases."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from release_common import fail
from release_metadata import parse_json


STRICT_TAG_PATTERN = "refs/tags/v*"
IMMUTABLE_RULESET_NAME = "immutable release tags"
CREATION_RULESET_NAME = "restricted release tag creation"
ATTESTATION_KEYS = frozenset(
    {"schema", "repository", "app_id", "immutable", "creation"}
)
EVIDENCE_KEYS = frozenset(
    {"id", "name", "source_type", "source", "updated_at", "bypass_actors"}
)


def read_ruleset(path: Path) -> dict[str, Any]:
    document = parse_json(path.read_bytes(), source=str(path))
    if not isinstance(document, dict):
        fail(f"ruleset response {path} must be a JSON object")
    return document


def require_strict_tag_scope(ruleset: dict[str, Any], *, label: str) -> None:
    conditions = ruleset.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if (
        ruleset.get("target") != "tag"
        or ruleset.get("enforcement") != "active"
        or not isinstance(ref_name, dict)
        or ref_name.get("include") != [STRICT_TAG_PATTERN]
        or ref_name.get("exclude") != []
    ):
        fail(
            f"{label} ruleset must actively and exclusively cover {STRICT_TAG_PATTERN}"
        )


def rule_types(ruleset: dict[str, Any], *, label: str) -> set[str]:
    rules = ruleset.get("rules")
    if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
        fail(f"{label} ruleset has malformed rules")
    types: set[str] = set()
    for rule in rules:
        rule_type = rule.get("type")
        if not isinstance(rule_type, str):
            fail(f"{label} ruleset has a malformed rule type")
        types.add(rule_type)
    return types


def verify_release_rulesets(
    immutable_ruleset: dict[str, Any],
    creation_ruleset: dict[str, Any],
    *,
    app_id: int,
) -> None:
    """Require no-bypass mutation blocking and App-only tag creation."""
    if type(app_id) is not int or app_id <= 0:
        fail("automation App ID must be a positive integer")

    require_strict_tag_scope(immutable_ruleset, label="immutable release tag")
    immutable_types = rule_types(immutable_ruleset, label="immutable release tag")
    if not {"update", "deletion"}.issubset(immutable_types):
        fail("immutable release tag ruleset must block updates and deletion")
    if immutable_ruleset.get("bypass_actors") != []:
        fail("immutable release tag ruleset must have no bypass actors")

    require_strict_tag_scope(creation_ruleset, label="release tag creation")
    if "creation" not in rule_types(creation_ruleset, label="release tag creation"):
        fail("release tag creation ruleset must restrict creation")
    expected_actor = {
        "actor_id": app_id,
        "actor_type": "Integration",
        "bypass_mode": "always",
    }
    if creation_ruleset.get("bypass_actors") != [expected_actor]:
        fail("release tag creation ruleset must allow only the automation App")


def ruleset_evidence(
    ruleset: dict[str, Any],
    *,
    repository: str,
    expected_name: str,
) -> dict[str, Any]:
    """Extract revision and principal evidence from one complete ruleset."""
    if (
        type(ruleset.get("id")) is not int
        or ruleset["id"] <= 0
        or ruleset.get("name") != expected_name
        or ruleset.get("source_type") != "Repository"
        or ruleset.get("source") != repository
        or not isinstance(ruleset.get("updated_at"), str)
        or not ruleset["updated_at"]
        or "bypass_actors" not in ruleset
    ):
        fail(f"ruleset {expected_name!r} has invalid repository identity evidence")
    return {
        "id": ruleset["id"],
        "name": ruleset["name"],
        "source_type": ruleset["source_type"],
        "source": ruleset["source"],
        "updated_at": ruleset["updated_at"],
        "bypass_actors": ruleset["bypass_actors"],
    }


def create_policy_attestation(
    immutable_ruleset: dict[str, Any],
    creation_ruleset: dict[str, Any],
    *,
    repository: str,
    app_id: int,
) -> dict[str, Any]:
    """Create owner-reviewed evidence for fields hidden from read-only tokens."""
    if not repository or repository.count("/") != 1:
        fail("repository must use the OWNER/NAME form")
    verify_release_rulesets(
        immutable_ruleset,
        creation_ruleset,
        app_id=app_id,
    )
    return {
        "schema": 1,
        "repository": repository,
        "app_id": app_id,
        "immutable": ruleset_evidence(
            immutable_ruleset,
            repository=repository,
            expected_name=IMMUTABLE_RULESET_NAME,
        ),
        "creation": ruleset_evidence(
            creation_ruleset,
            repository=repository,
            expected_name=CREATION_RULESET_NAME,
        ),
    }


def verify_attested_release_rulesets(
    immutable_ruleset: dict[str, Any],
    creation_ruleset: dict[str, Any],
    attestation: dict[str, Any],
    *,
    repository: str,
    app_id: int,
) -> None:
    """Bind live visible rules to owner-attested bypass principals."""
    if set(attestation) != ATTESTATION_KEYS:
        fail("release policy attestation has unexpected fields")
    if (
        attestation.get("schema") != 1
        or attestation.get("repository") != repository
        or attestation.get("app_id") != app_id
    ):
        fail("release policy attestation has conflicting identity")

    complete_rulesets: list[dict[str, Any]] = []
    for label, live, expected_name in (
        ("immutable", immutable_ruleset, IMMUTABLE_RULESET_NAME),
        ("creation", creation_ruleset, CREATION_RULESET_NAME),
    ):
        evidence = attestation.get(label)
        if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
            fail(f"release policy attestation has malformed {label} evidence")
        live_identity = ruleset_evidence(
            {**live, "bypass_actors": evidence["bypass_actors"]},
            repository=repository,
            expected_name=expected_name,
        )
        for field in EVIDENCE_KEYS - {"bypass_actors"}:
            if live_identity[field] != evidence[field]:
                fail(f"live {label} ruleset differs from the owner attestation")
        complete = deepcopy(live)
        complete["bypass_actors"] = evidence["bypass_actors"]
        complete_rulesets.append(complete)

    verify_release_rulesets(
        complete_rulesets[0],
        complete_rulesets[1],
        app_id=app_id,
    )
