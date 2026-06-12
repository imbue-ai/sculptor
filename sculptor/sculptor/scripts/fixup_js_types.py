"""
Fix the
"""

import re
from pathlib import Path

import typer

# match lines like:
# export type ChecksDefinedRunnerMessageOutput = {
_MATHCHER = re.compile(r"^export (type|interface) (\w+)Output = {$")


def main(file_path: Path = typer.Argument(Path("types.gen.ts"))) -> None:
    typer.echo("Fixing Typescript types for Sculptor web API...")
    lines: list[str] = []
    buffered_line = None
    for line in Path(file_path).read_text().splitlines(keepends=True):
        match = _MATHCHER.match(line.rstrip())
        if match:
            kind = match.group(1)
            type_name = match.group(2)
            buffered_line = f"export {kind} {type_name} = {type_name}Output;\n"
        lines.append(line)
        if lines[-1].rstrip() == "};" and buffered_line is not None:
            lines.append("\n")
            lines.append(buffered_line)
            buffered_line = None
    Path(file_path).write_text("".join(lines), encoding="utf-8")
    typer.echo(f"Finished fixing Typescript types in {file_path.resolve()}")


if __name__ == "__main__":
    typer.run(main)
