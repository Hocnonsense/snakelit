"""JSON-schema helpers shared by the configuration editor.

Only validation and the small amount of schema introspection that the editor
needs live here; inferring a schema from data stays in SRPtn for now.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

import jsonschema.validators

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


def infer_type(value):
    """Infer a JSON schema type for a single config value."""
    if isinstance(value, Mapping):
        return {"type": "object"}
    if isinstance(value, list):
        schema: dict[str, Any] = {"type": "array"}
        if value:
            schema["items"] = infer_type(value[0])
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


def validate(config, schema: Mapping[str, Any] | None):
    """Yield every problem found in ``config``."""
    yield from validation_errors(config, schema)
    yield from empty_required_errors(config, schema)


def validation_errors(config, schema: Mapping[str, Any] | None):
    """Validate ``config`` against ``schema``; an empty list means valid."""
    if not schema:
        return
    validator = jsonschema.validators.validator_for(schema)(schema)
    for error in sorted(validator.iter_errors(config), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        yield f"{location}: {error.message}"


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
