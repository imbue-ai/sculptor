"""
Generate an OpenAPI schema describing the pydantic types involved in all sculptor web endpoints.

"""

import json
from pathlib import Path
from typing import Any

import typer

from sculptor.web.app import APP


def _widen_http_validation_error_detail(json_schema: dict[str, Any]) -> None:
    """Allow a plain-string `detail` on the 422 error schema, not just a list.

    FastAPI documents every 422 response with `HTTPValidationError`, whose
    `detail` is a list of structured request-validation errors. But a
    hand-raised `HTTPException(422, detail="...")` serializes `detail` as a
    plain string, which does not match that schema. Widening `detail` to
    `string | list[ValidationError]` makes the generated client parse both
    shapes and surface the message instead of crashing on the string.
    """
    schema = json_schema.get("components", {}).get("schemas", {}).get("HTTPValidationError")
    if schema is None:
        return
    detail = schema["properties"]["detail"]
    schema["properties"]["detail"] = {
        "anyOf": [detail, {"type": "string"}],
        "title": detail.get("title", "Detail"),
    }


def main(output_path: Path = typer.Argument(Path("sculptor_schema.json"))) -> None:
    typer.echo("Generating JSON schema for sculptor web API...")
    json_schema = APP.openapi()
    _widen_http_validation_error_detail(json_schema)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(json_schema, f, indent=2)
    typer.echo(f"JSON schema written to {output_path.resolve()}")


if __name__ == "__main__":
    typer.run(main)
