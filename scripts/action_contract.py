"""Typed public-contract comparison for Vexcalibur Action metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from release_common import Bump


class ActionContractError(ValueError):
    """Raised when action metadata cannot form a public contract."""


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ActionContractError(
                "YAML mapping keys must be scalar values"
            ) from exc
        if duplicate:
            raise ActionContractError(f"YAML mapping contains duplicate key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_unique_mapping,
)


@dataclass(frozen=True)
class InputContract:
    """Caller-visible behavior for one action input."""

    required: bool
    has_default: bool
    default: str | None
    deprecation_message: str | None


@dataclass(frozen=True)
class OutputContract:
    """Caller-visible behavior for one action output."""

    has_value: bool
    value: str | None


@dataclass(frozen=True)
class ActionContract:
    """The action metadata fields that can affect existing callers."""

    inputs: dict[str, InputContract]
    outputs: dict[str, OutputContract]
    runs_using: str


@dataclass(frozen=True)
class ContractChange:
    """Minimum semantic-version bump and the reasons it is required."""

    required_bump: Bump
    reasons: tuple[str, ...]


def require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not key for key in value
    ):
        raise ActionContractError(f"{field} must be a mapping with string keys")
    return value


def parse_action_contract(raw: bytes, *, source: str) -> ActionContract:
    """Parse only caller-visible fields from an action metadata document."""
    try:
        document = yaml.load(raw, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ActionContractError(f"{source} is not valid YAML: {exc}") from exc
    document = require_mapping(document, field=f"{source} document")

    raw_inputs = require_mapping(document.get("inputs", {}), field="inputs")
    inputs: dict[str, InputContract] = {}
    for name, raw_configuration in raw_inputs.items():
        configuration = require_mapping(
            raw_configuration, field=f"input {name!r} configuration"
        )
        required = configuration.get("required", False)
        if not isinstance(required, bool):
            raise ActionContractError(f"input {name!r} required must be boolean")
        has_default = "default" in configuration
        default = configuration.get("default")
        if has_default and not isinstance(default, str):
            raise ActionContractError(f"input {name!r} default must be a string")
        deprecation_message = configuration.get("deprecationMessage")
        if deprecation_message is not None and (
            not isinstance(deprecation_message, str) or not deprecation_message
        ):
            raise ActionContractError(
                f"input {name!r} deprecationMessage must be a nonempty string"
            )
        inputs[name] = InputContract(
            required=required,
            has_default=has_default,
            default=default,
            deprecation_message=deprecation_message,
        )

    raw_outputs = require_mapping(document.get("outputs", {}), field="outputs")
    outputs: dict[str, OutputContract] = {}
    for name, raw_configuration in raw_outputs.items():
        configuration = require_mapping(
            raw_configuration, field=f"output {name!r} configuration"
        )
        has_value = "value" in configuration
        value = configuration.get("value")
        if has_value and not isinstance(value, str):
            raise ActionContractError(f"output {name!r} value must be a string")
        outputs[name] = OutputContract(
            has_value=has_value,
            value=value,
        )

    runs = require_mapping(document.get("runs"), field="runs")
    runs_using = runs.get("using")
    if not isinstance(runs_using, str) or not runs_using:
        raise ActionContractError("runs.using must be a nonempty string")
    return ActionContract(inputs, outputs, runs_using)


def compare_action_contracts(
    released: ActionContract, current: ActionContract
) -> ContractChange:
    """Return the minimum bump needed for current relative to released."""
    major_reasons: list[str] = []
    minor_reasons: list[str] = []
    patch_reasons: list[str] = []

    if current.runs_using != released.runs_using:
        major_reasons.append(
            f"runs.using changed from {released.runs_using!r} to {current.runs_using!r}"
        )

    for name in sorted(released.inputs.keys() - current.inputs.keys()):
        major_reasons.append(f"input {name!r} was removed")
    for name in sorted(current.inputs.keys() - released.inputs.keys()):
        added = current.inputs[name]
        if added.required and not added.has_default:
            major_reasons.append(f"required input {name!r} was added without a default")
        else:
            minor_reasons.append(f"compatible input {name!r} was added")
    for name in sorted(released.inputs.keys() & current.inputs.keys()):
        old = released.inputs[name]
        new = current.inputs[name]
        if old.has_default != new.has_default or old.default != new.default:
            major_reasons.append(f"input {name!r} default changed")
        if old.required != new.required:
            if new.required:
                major_reasons.append(f"input {name!r} became required")
            else:
                minor_reasons.append(f"input {name!r} became optional")
        if old.deprecation_message != new.deprecation_message:
            if old.deprecation_message is None:
                minor_reasons.append(f"input {name!r} was deprecated")
            else:
                patch_reasons.append(
                    f"input {name!r} deprecation message changed or was removed"
                )

    for name in sorted(released.outputs.keys() - current.outputs.keys()):
        major_reasons.append(f"output {name!r} was removed")
    for name in sorted(current.outputs.keys() - released.outputs.keys()):
        minor_reasons.append(f"output {name!r} was added")
    for name in sorted(released.outputs.keys() & current.outputs.keys()):
        if released.outputs[name] != current.outputs[name]:
            major_reasons.append(f"output {name!r} value changed")

    if major_reasons:
        return ContractChange(
            "major", tuple(major_reasons + minor_reasons + patch_reasons)
        )
    if minor_reasons:
        return ContractChange("minor", tuple(minor_reasons + patch_reasons))
    if patch_reasons:
        return ContractChange("patch", tuple(patch_reasons))
    return ContractChange("skip", ())
