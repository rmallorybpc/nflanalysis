#!/usr/bin/env bash
set -euo pipefail

echo "Running dashboard contract checks..."

python3 - <<'PY'
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path):
    if not path.exists():
        fail(f"missing file: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_ref(schema: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        fail(f"unsupported ref format: {ref}")
    node: object = schema
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            fail(f"invalid ref path: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        fail(f"ref did not resolve to object schema: {ref}")
    return node


def validate_type(expected: str, payload, where: str) -> None:
    mapping = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
    }
    if expected not in mapping:
        return
    py_type = mapping[expected]
    if expected == "integer":
        if isinstance(payload, bool) or not isinstance(payload, int):
            fail(f"{where}: expected integer")
        return
    if expected == "number":
        if isinstance(payload, bool) or not isinstance(payload, (int, float)):
            fail(f"{where}: expected number")
        return
    if not isinstance(payload, py_type):
        fail(f"{where}: expected {expected}")


def validate(schema_root: dict, schema: dict, payload, where: str) -> None:
    if "$ref" in schema:
        target = resolve_ref(schema_root, schema["$ref"])
        validate(schema_root, target, payload, where)
        return

    if "type" in schema:
        validate_type(schema["type"], payload, where)

    if "enum" in schema and payload not in schema["enum"]:
        fail(f"{where}: value {payload!r} not in enum")

    if isinstance(payload, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in payload:
                fail(f"{where}: missing required key {key}")

        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                validate(schema_root, properties[key], value, f"{where}.{key}")

    if isinstance(payload, list) and "items" in schema:
        for index, item in enumerate(payload):
            validate(schema_root, schema["items"], item, f"{where}[{index}]")


pairs = [
    (
        Path("api/schemas/overview-dashboard.schema.json"),
        Path("dashboard/public/overview.sample.json"),
    ),
    (
        Path("api/schemas/team-detail.schema.json"),
        Path("dashboard/public/team-detail.sample.json"),
    ),
    (
        Path("api/schemas/scenario-sandbox.schema.json"),
        Path("dashboard/public/scenario-sandbox.sample.json"),
    ),
]

for schema_path, payload_path in pairs:
    schema = load_json(schema_path)
    payload = load_json(payload_path)
    validate(schema, schema, payload, payload_path.as_posix())

print(f"validated dashboard payload contracts: {len(pairs)}")
PY

echo "Dashboard contract checks passed."
