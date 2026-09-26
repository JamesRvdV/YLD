"""Strict validator for the small JSON Schema subset used by model contracts."""
from __future__ import annotations

import math


def validate(schema, value, path="$"):
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        properties = schema["properties"]
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path}: unexpected fields")
        if set(schema.get("required", ())) - set(value):
            raise ValueError(f"{path}: missing fields")
        for name, item in value.items():
            if name in properties:
                validate(properties[name], item, f"{path}.{name}")
    elif kind == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected array")
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf):
            raise ValueError(f"{path}: invalid array length")
        for index, item in enumerate(value):
            validate(schema["items"], item, f"{path}[{index}]")
    elif kind == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected string")
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", math.inf):
            raise ValueError(f"{path}: invalid string length")
    elif kind == "integer":
        if type(value) is not int:
            raise ValueError(f"{path}: expected integer")
    elif kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{path}: expected finite number")
    else:
        raise ValueError(f"{path}: unsupported schema type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if kind in ("integer", "number") and (value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf)):
        raise ValueError(f"{path}: out of range")
    return value
