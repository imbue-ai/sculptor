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
    # openapi-ts 0.98+ maps `format: binary` fields to `Blob | File`, but
    # Pydantic serializes bytes fields as base64 strings over the JSON wire,
    # so the frontend actually receives strings.
    contents = file_path.read_text(encoding="utf-8")
    binary_data_fields = contents.count("data: Blob | File;")
    # If this fails, a new format:binary field was added: decide whether it is
    # base64-over-JSON (rewrite to string) or a real upload body (keep Blob).
    assert binary_data_fields == 1, f"Expected exactly one binary 'data' field, found {binary_data_fields}"
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
