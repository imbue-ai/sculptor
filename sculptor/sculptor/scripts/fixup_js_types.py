"""
Add backwards-compatible type aliases for generated TypeScript "...Output" types.

openapi-ts emits a separate "...Output" type for each response model; this script
appends an alias (e.g. `export type Foo = FooOutput;`) so the rest of the frontend
can refer to the type by its bare name.
"""

import re
from pathlib import Path

import typer

# match lines like:
# export type ChecksDefinedRunnerMessageOutput = {
_MATCHER = re.compile(r"^export (type|interface) (\w+)Output = {$")


def main(file_path: Path = typer.Argument(Path("types.gen.ts"))) -> None:
    typer.echo("Fixing Typescript types for Sculptor web API...")
    # openapi-ts 0.98+ maps `format: binary` fields to `Blob | File`, but bytes
    # fields are serialized as base64 strings over the JSON wire, so the frontend
    # actually receives strings. The TypeScript backend (which emits the OpenAPI
    # now) already types these as base64 strings, so there is typically nothing
    # to rewrite; we still tolerate the FastAPI-style `Blob | File` encoding for
    # robustness. More than one is unexpected — flag it so a new format:binary
    # field gets a deliberate base64-vs-upload decision rather than silent breakage.
    contents = file_path.read_text(encoding="utf-8")
    binary_data_fields = contents.count("data: Blob | File;")
    assert binary_data_fields <= 1, f"Expected at most one binary 'data' field, found {binary_data_fields}"
    if binary_data_fields == 1:
        contents = contents.replace("data: Blob | File;", "data: string;")
        file_path.write_text(contents, encoding="utf-8")
    lines: list[str] = []
    buffered_line: str | None = None
    for line in file_path.read_text(encoding="utf-8").splitlines(keepends=True):
        match = _MATCHER.match(line.rstrip())
        if match:
            kind = match.group(1)
            type_name = match.group(2)
            buffered_line = f"export {kind} {type_name} = {type_name}Output;\n"
        lines.append(line)
        if lines[-1].rstrip() == "};" and buffered_line is not None:
            lines.append("\n")
            lines.append(buffered_line)
            buffered_line = None
    file_path.write_text("".join(lines), encoding="utf-8")
    typer.echo(f"Finished fixing Typescript types in {file_path.resolve()}")


if __name__ == "__main__":
    typer.run(main)
