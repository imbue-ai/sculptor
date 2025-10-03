"""
Generate an OpenAPI schema describing the pydantic types involved in all sculptor web endpoints.

"""

import json
from pathlib import Path

import typer

from sculptor.web.app import APP


def main(output_path: Path = typer.Argument(Path("sculptor_schema.json"))) -> None:
    typer.echo("Generating JSON schema for sculptor web API...")
    json_schema = APP.openapi()
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(json_schema, f, indent=2)
    typer.echo(f"JSON schema written to {output_path.resolve()}")


if __name__ == "__main__":
    typer.run(main)
