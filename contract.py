"""Authoritative parameter access and schema projections.

Only track.schema.json owns numeric field limits. Projections visit Schema Objects,
never arbitrary property-name dictionaries (a property may be called 'pattern').
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTRACT_REVISION = "1.2.0"
MAX_EVENTS = 100000
MAX_POLYPHONY = 128
MAX_INPUT_BYTES = 8 * 1024 * 1024
VOICES = dict(zip(
    ("kick", "bass", "closed_hat", "open_hat", "clap", "perc", "stab", "noise"),
    range(1, 9),
))
LEVELS = dict(zip(VOICES, (.48, .20, .16, .12, .22, .18, .15, .10)))
SCHEMA = json.loads((ROOT / "schemas/track.schema.json").read_text())
RAMP_PARAMETERS = SCHEMA["definitions"]["ramp"]["properties"]["parameter"]["enum"]


def ramp_schema(name):
    owner = "clip" if name == "gain_db" else "mix"
    return SCHEMA["definitions"][owner]["properties"][name]


def ramp_bounds(name):
    s = ramp_schema(name)
    return s["minimum"], s["maximum"]


def resolved(node):
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/definitions/"):
            raise ValueError(f"Unsupported contract reference: {ref}")
        return SCHEMA["definitions"][ref.rsplit("/", 1)[-1]]
    return node


def gemini_schema(node=None):
    """Conservative AI Studio profile: no numeric bounds, unions, refs or array caps.

    Limits belong in the generated system instructions and local validation.
    This is a compatibility choice, not a claim all Gemini APIs reject bounds.
    """
    node = resolved(SCHEMA if node is None else node)
    out = {"type": node["type"]}
    if "const" in node:
        out["enum"] = [node["const"]]
    elif "enum" in node:
        out["enum"] = copy.deepcopy(node["enum"])
    if "properties" in node:
        out["properties"] = {k: gemini_schema(v) for k, v in node["properties"].items()}
        out["required"] = list(node.get("required", []))
    if "items" in node:
        out["items"] = gemini_schema(node["items"])
    return out


def openapi_document():
    def convert(node):
        if "$ref" in node:
            return {"$ref": node["$ref"].replace("#/definitions/", "#/components/schemas/")}
        out = {k: copy.deepcopy(v) for k, v in node.items()
               if k not in ("$schema", "definitions", "properties", "items", "const")}
        if "const" in node:
            out["enum"] = [node["const"]]
        if "properties" in node:
            out["properties"] = {k: convert(v) for k, v in node["properties"].items()}
        if "items" in node:
            out["items"] = convert(node["items"])
        return out

    schemas = {k: convert(v) for k, v in SCHEMA["definitions"].items()}
    schemas["TrackPlan"] = convert(SCHEMA)
    # Express parameter-dependent limits in OpenAPI, derived from the same fields.
    schemas["ramp"] = {"type": "object", "oneOf": [
        {"type": "object", "additionalProperties": False,
         "properties": {"parameter": {"type": "string", "enum": [name]},
                        "from": convert(ramp_schema(name)), "to": convert(ramp_schema(name))},
         "required": ["parameter", "from", "to"]} for name in RAMP_PARAMETERS
    ]}
    return {"openapi": "3.0.3", "info": {"title": "Techno Track Plan",
            "version": CONTRACT_REVISION}, "paths": {}, "components": {"schemas": schemas}}


def range_guide():
    rows = []

    def walk(node, path):
        node = resolved(node)
        rules = []
        for low, high, units in (("minimum", "maximum", "value"),
                                 ("minItems", "maxItems", "items"),
                                 ("minLength", "maxLength", "characters")):
            if low in node and high in node:
                rules.append(f'{units} {node[low]}..{node[high]}')
        if "pattern" in node:
            rules.append('ID: lowercase letter followed by letters, digits or underscores; max 32 characters')
        if "enum" in node:
            rules.append("one of " + ", ".join(map(str, node["enum"])))
        if "const" in node:
            rules.append("exactly " + repr(node["const"]))
        if node.get("uniqueItems"):
            rules.append("unique entries")
        if node.get("description"):
            rules.append(node["description"])
        if rules:
            rows.append(f'- {path}: ' + "; ".join(rules))
        for key, child in node.get("properties", {}).items():
            walk(child, f"{path}.{key}" if path else key)
        if "items" in node:
            walk(node["items"], path + "[]")

    walk(SCHEMA, "")
    rows += [f'- clips[].ramps[] {name}: from and to each {ramp_bounds(name)[0]}..{ramp_bounds(name)[1]}'
             for name in RAMP_PARAMETERS]
    return "\n".join(rows)


def audit_gemini(node, path="$", depth=0):
    """Local invariants only; this cannot measure Google's private grammar budget."""
    allowed = {"type", "properties", "items", "required", "enum"}
    if set(node) - allowed:
        raise ValueError(f"{path}: unsupported profile keys {set(node) - allowed}")
    if node.get("type") not in {"object", "array", "string", "number", "integer", "boolean"}:
        raise ValueError(f"{path}: missing or unknown type")
    if node["type"] == "object":
        props = node.get("properties", {})
        required = node.get("required", [])
        if len(required) != len(set(required)) or not set(required) <= props.keys():
            raise ValueError(f"{path}: invalid required list")
        children = [audit_gemini(v, path + "." + k, depth + 1) for k, v in props.items()]
    elif node["type"] == "array":
        children = [audit_gemini(node["items"], path + "[]", depth + 1)]
    else:
        children = []
    return {"nodes": 1 + sum(c["nodes"] for c in children),
            "depth": max([depth] + [c["depth"] for c in children])}
