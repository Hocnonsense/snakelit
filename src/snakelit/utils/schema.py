"""JSON-schema helpers shared by the configuration and table editors.

Validation uses ``jsonschema`` with one adjustment: the project YAML loader
keeps scientific-notation floats as strings, so the ``number`` type also
accepts strings like ``1e-5``.  Schema inference and the small property
editing helpers are pure: they return new mappings and never mutate their
input.
"""

from __future__ import annotations

import copy
import re
from functools import cache
from typing import Any, Mapping, overload

import jsonschema.exceptions
import jsonschema.validators
from jsonschema.protocols import Validator

from .yaml import SCIENTIFIC_FLOAT

_EMPTY = ("", None)


def get_property_type(schema: Mapping[str, Any]):
    """Return ``"properties"`` or ``"patternProperties"`` for ``schema``."""
    if "properties" in schema:
        return "properties"
    if "patternProperties" in schema:
        return "patternProperties"
    raise ValueError(
        "Wrong schema structure, use either properties or patternProperties"
    )


def is_schema(schema):
    """Whether ``schema`` describes an object with named entries."""
    return isinstance(schema, Mapping) and (
        "properties" in schema or "patternProperties" in schema
    )


def property_schema(
    schema: Mapping[str, Any] | None, name: str
) -> Mapping[str, Any] | None:
    """Return the subschema for ``name``, matching patterns when needed."""
    if schema is None or not is_schema(schema):
        return
    if "properties" in schema:
        return (schema.get("properties") or {}).get(name)
    for pattern, subschema in (schema.get("patternProperties") or {}).items():
        if re.search(pattern, name):
            return subschema
    return


@overload
def sanitize_schema(value: Mapping) -> dict: ...
@overload
def sanitize_schema(value: list) -> list: ...
@overload
def sanitize_schema(value: None) -> None: ...
def sanitize_schema(value):
    """Drop the non-standard ``"missing"`` type so jsonschema accepts it.

    Some producers (including SRPtn's schema inference) use ``"missing"`` for
    values with no known type.  The type carries no validation meaning, so an
    empty schema is the correct translation.
    """
    if isinstance(value, dict):
        result = {key: sanitize_schema(item) for key, item in value.items()}
        if result.get("type") == "missing":
            result.pop("type")
        return result
    if isinstance(value, list):
        return [sanitize_schema(item) for item in value]
    return value


@cache
def _extended_validator(base: type[Validator]):
    """Extend ``base`` so scientific-notation strings count as numbers."""

    def is_number(type_checker, value):
        if isinstance(value, str):
            return bool(SCIENTIFIC_FLOAT.match(value))
        return not isinstance(value, bool) and isinstance(value, (int, float))

    return jsonschema.validators.extend(
        base, type_checker=base.TYPE_CHECKER.redefine("number", is_number)
    )


def _first_present(values):
    """Index of the first value that is not ``None``, ``NaN`` or blank."""
    for index, value in enumerate(values):
        if value is None:
            continue
        if isinstance(value, float) and value != value:
            continue
        if value == "":
            continue
        return index
    return None


def infer_type(value):
    """Infer a JSON schema type for a single config or table value."""
    if isinstance(value, Mapping):
        return {"type": "object"}
    if not isinstance(value, (str, bytes)) and hasattr(value, "to_list"):
        value = value.to_list()
    if isinstance(value, (list, tuple)):
        schema: dict[str, Any] = {"type": "array"}
        index = _first_present(value)
        if index is not None:
            schema["items"] = infer_type(value[index])
        return schema
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {"type": "null"}


def infer_schema(config: Mapping):
    """Infer a JSON schema from a configuration mapping."""
    schema = {"type": "object", "properties": {}}
    for key, value in config.items():
        schema["properties"][key] = (
            infer_schema(value) if isinstance(value, Mapping) else infer_type(value)
        )
    return schema


def update_schema(schema: Mapping, config: Mapping) -> dict:
    """Return ``schema`` extended with properties inferred from ``config``.

    Existing properties keep their schema; missing leaves are inferred.  For
    ``patternProperties``, a key is only described by a matching pattern; an
    unmatched key is left alone instead of becoming a new pattern.
    """
    updated = copy.deepcopy(dict(schema))
    prop_key = get_property_type(updated)
    nested: list[tuple[str, Mapping]] = []
    for key, value in config.items():
        if isinstance(value, Mapping):
            nested.append((key, value))
        elif prop_key == "properties":
            updated[prop_key].setdefault(key, infer_type(value))

    for key, value in nested:
        if prop_key == "patternProperties":
            matched = next(
                (pattern for pattern in updated[prop_key] if re.search(pattern, key)),
                None,
            )
            if matched is None:
                continue
            target = matched
        else:
            target = key
        subschema = updated[prop_key].get(target)
        if subschema is None:
            subschema = infer_schema(value)
            updated[prop_key][target] = subschema
        updated[prop_key][target] = update_schema(subschema, value)
    return updated


def validate(config, schema: Mapping[str, Any] | None):
    """Yield every problem found in ``config``."""
    yield from validation_errors(config, schema)
    yield from empty_required_errors(config, schema)


def validation_errors(config, schema: Mapping[str, Any] | None):
    """Yield jsonschema violations of ``config`` as ``path: message`` strings."""
    if not schema:
        return
    clean = sanitize_schema(schema)
    base = jsonschema.validators.validator_for(clean)
    validator = _extended_validator(base)(clean)
    problems = sorted(
        validator.iter_errors(config),
        key=lambda error: tuple(str(part) for part in error.path),
    )
    for error in problems:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        yield f"{location}: {error.message}"


def schema_errors(schema: Mapping[str, Any] | None):
    """Return meta-schema violations of ``schema`` as strings, ``[]`` if valid.

    A malformed schema (for example a ``required`` list placed inside
    ``properties``) makes jsonschema silently ignore that branch, so nested
    content goes unvalidated; checking the schema itself surfaces the mistake.
    """
    if not schema:
        return []
    clean = sanitize_schema(schema)
    validator = jsonschema.validators.validator_for(clean)
    try:
        validator.check_schema(clean)
    except jsonschema.exceptions.SchemaError as error:
        return [error.message]
    return []


def empty_required_errors(config, schema: Mapping[str, Any] | None):
    """Yield required keys that are present but empty.

    JSON Schema's ``required`` keyword only checks presence, so a blank text
    field passes.  A missing key is already reported by
    :func:`validation_errors`; this only covers the present-but-empty case.
    """
    if not schema or not is_schema(schema):
        return
    if not isinstance(config, Mapping):
        return
    for name in schema.get("required") or ():
        if name in config and config[name] in _EMPTY:
            yield f"{name}: required value is empty"
