"""Normalize JSON Schema for OpenAI/OpenRouter strict structured outputs."""
from __future__ import annotations

import copy
import re
from typing import Any

# Keywords that make `response_format.json_schema` + `strict: true` return 400.
_UNSUPPORTED = {
    "$id",
    "$schema",
    "contentEncoding",
    "contentMediaType",
    "default",
    "deprecated",
    "discriminator",
    "examples",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "pattern",
    "patternProperties",
    "propertyNames",
    "readOnly",
    "title",
    "uniqueItems",
    "writeOnly",
}


def schema_name(prompt_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", prompt_name or "response")[:64]
    return cleaned or "response"


def openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` that OpenAI strict structured outputs accept.

    Pydantic's ``model_json_schema()`` emits ``default``, optional fields, and
    missing ``additionalProperties: false``. OpenRouter then 400s the request
    and we fall back to unconstrained ``json_object``, which often copies those
    defaults (empty ``requirements``) and silently zeros job fit.
    """
    return _strict(copy.deepcopy(schema))


def _strict(node: Any) -> Any:
    if not isinstance(node, dict):
        return node

    all_of = node.get("allOf")
    if (
        isinstance(all_of, list)
        and len(all_of) == 1
        and isinstance(all_of[0], dict)
        and "$ref" in all_of[0]
    ):
        return {"$ref": all_of[0]["$ref"]}

    if "$ref" in node:
        return {"$ref": node["$ref"]}

    out = {key: value for key, value in node.items() if key not in _UNSUPPORTED}

    if "$defs" in out and isinstance(out["$defs"], dict):
        out["$defs"] = {name: _strict(defn) for name, defn in out["$defs"].items()}
    if "definitions" in out and isinstance(out["definitions"], dict):
        out["definitions"] = {
            name: _strict(defn) for name, defn in out["definitions"].items()
        }

    if "anyOf" in out:
        out["anyOf"] = [_strict(item) for item in out["anyOf"]]
    if "oneOf" in out:
        out["anyOf"] = [_strict(item) for item in out.pop("oneOf")]
    if "allOf" in out:
        merged: dict[str, Any] = {}
        for item in out.pop("allOf"):
            item = _strict(item)
            if isinstance(item, dict) and "$ref" in item:
                return item
            if isinstance(item, dict):
                merged = _merge_objects(merged, item)
        out = _merge_objects(out, merged)

    if "items" in out:
        out["items"] = _strict(out["items"])
    out.pop("prefixItems", None)

    types = out.get("type")
    if isinstance(types, list):
        non_null = [item for item in types if item != "null"]
        if "null" in types and non_null:
            variant = dict(out)
            variant["type"] = non_null[0] if len(non_null) == 1 else non_null
            return {"anyOf": [_strict(variant), {"type": "null"}]}
        out["type"] = non_null[0] if len(non_null) == 1 else types

    if out.get("type") == "object" or "properties" in out:
        out["type"] = "object"
        props = out.get("properties") or {}
        out["properties"] = {name: _strict(prop) for name, prop in props.items()}
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])

    return out


def _merge_objects(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key == "properties" and isinstance(value, dict):
            props = dict(merged.get("properties") or {})
            props.update(value)
            merged["properties"] = props
        elif key == "required" and isinstance(value, list):
            merged["required"] = list(dict.fromkeys([*(merged.get("required") or []), *value]))
        elif key not in merged:
            merged[key] = value
    return merged
