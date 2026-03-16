"""Generate TypeScript types from agent/models.py Pydantic models.

Usage: uv run python scripts/generate_types.py
Output: frontend/src/types/generated.ts
"""

from __future__ import annotations

from pathlib import Path

from agent.models import (
    Alert,
    HerdSummary,
    OverlayBox,
    OverlayData,
    SceneGraph,
    TrackedEntityModel,
    ZoneOccupancy,
)

HEADER = "// AUTO-GENERATED from agent/models.py — do not edit manually\n\n"

MODELS = [
    HerdSummary,
    ZoneOccupancy,
    TrackedEntityModel,
    Alert,
    SceneGraph,
    OverlayBox,
    OverlayData,
]


def pydantic_to_ts_type(python_type: str) -> str:
    """Map Python/Pydantic types to TypeScript types."""
    mapping: dict[str, str] = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }
    return mapping.get(python_type, "any")


def schema_to_interface(name: str, schema: dict, defs: dict) -> str:
    """Convert a JSON Schema to a TypeScript interface."""
    lines = [f"export interface {name} {{"]
    props = schema.get("properties", {})

    for field_name, field_schema in props.items():
        ts_type = resolve_type(field_schema, defs)
        # All fields are always present in serialized output (defaults are populated),
        # so treat every property as required for the TypeScript consumer.
        lines.append(f"  {field_name}: {ts_type};")

    lines.append("}")
    return "\n".join(lines)


NAME_REMAP = {"TrackedEntityModel": "TrackedEntity"}


def resolve_type(field_schema: dict, defs: dict) -> str:
    """Resolve a JSON Schema field to a TypeScript type."""
    if "$ref" in field_schema:
        ref_name: str = field_schema["$ref"].split("/")[-1]
        return NAME_REMAP.get(ref_name, ref_name)

    if "anyOf" in field_schema:
        types = [resolve_type(t, defs) for t in field_schema["anyOf"]]
        return " | ".join(types)

    if "enum" in field_schema:
        return " | ".join(f"'{v}'" for v in field_schema["enum"])

    json_type = field_schema.get("type", "any")

    if json_type == "array":
        items = field_schema.get("items", {})
        item_type = resolve_type(items, defs)
        return f"{item_type}[]"

    if json_type == "object":
        addl = field_schema.get("additionalProperties", {})
        if addl:
            val_type = resolve_type(addl, defs)
            return f"Record<string, {val_type}>"
        return "Record<string, unknown>"

    return pydantic_to_ts_type(json_type)


def generate() -> str:
    """Generate all TypeScript interfaces."""
    output = [HEADER]

    # Collect all schemas
    for model in MODELS:
        schema = model.model_json_schema()
        defs = schema.get("$defs", {})
        name = model.__name__

        # Rename TrackedEntityModel → TrackedEntity for TS
        ts_name = "TrackedEntity" if name == "TrackedEntityModel" else name

        output.append(schema_to_interface(ts_name, schema, defs))
        output.append("")

    # Add Severity type alias
    output.append("export type Severity = 'info' | 'warning' | 'alert' | 'critical';")
    output.append("")

    return "\n".join(output)


def main():
    out_path = Path("frontend/src/types/generated.ts")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate()
    out_path.write_text(content, encoding="utf-8")
    print(f"Generated {out_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
