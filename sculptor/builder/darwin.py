"""Common utilities for building and validation on MacOS Darwin."""

import os
import re
import subprocess
from shutil import which

import typer


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: command not found"


def _parse_archs_from_lipo(text: str) -> list[str]:
    """Handles both:
    - "Architectures in the fat file ... are: x86_64 arm64"
    - "Non-fat file: ... is architecture: x86_64"
    """
    m = re.search(r"are:\s+(.+)$", text)

    if m:
        return re.findall(r"\b(arm64|x86_64|i386|ppc64|ppc)\b", m.group(1))
    m = re.search(r"architecture:\s+(\S+)", text)
    if m:
        return [m.group(1)]
    return []


def _parse_archs_from_file_output(text: str) -> list[str]:
    """Common patterns from `file -b` output on Mach-O files:

    e.g. "Mach-O 64-bit executable x86_64", "Mach-O universal binary with 2 architectures: [x86_64:...] [arm64:...]"
    """
    found = set(re.findall(r"\b(arm64|x86_64|i386|ppc64|ppc)\b", text))
    return list(found)


def _extract_min_macos(otool_out: str) -> str | None:
    """Prefer LC_BUILD_VERSION -> minos
    Example lines:
      cmd LC_BUILD_VERSION
      minos 12.0
    """
    lines = otool_out.splitlines()
    minos = None
    for i, line in enumerate(lines):
        if line.strip().startswith("cmd ") and "LC_BUILD_VERSION" in line:
            # scan the next few lines for "minos <ver>"
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.search(r"\bminos\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)", lines[j])
                if m:
                    minos = m.group(1)
                    break
        if minos:
            break
    if minos:
        return minos

    # Fallback: LC_VERSION_MIN_MACOSX -> version
    for i, line in enumerate(lines):
        if line.strip().startswith("cmd ") and "LC_VERSION_MIN_MACOSX" in line:
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.search(r"\bversion\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)", lines[j])
                if m:
                    return m.group(1)
    return None


def validate_binary(
    binary_path: str,
    arch: str,  # expected architecture, e.g. "x86_64" or "arm64"
    *,
    lipo: str | None = None,
    file_bin: str | None = None,
    otool: str | None = None,
    codesign_bin: str | None = None,
) -> bool:
    """Returns True if all checks pass, False otherwise.

    This is meant to be called by the build script, it uses typer to print coloured responses. It returns a bool of whether the check was successful.
    """

    # Allow overriding via env like the Bash version
    lipo = lipo or os.environ.get("LIPO") or "lipo"
    file_bin = file_bin or os.environ.get("FILE_BIN") or "file"
    otool = otool or os.environ.get("OTOOL") or "otool"
    codesign_bin = codesign_bin or os.environ.get("CODESIGN") or "codesign"

    ok = True

    # Existence & executability
    if not (os.path.isfile(binary_path) and os.access(binary_path, os.X_OK)):
        typer.secho(f" File not found at {binary_path}")
        return False

    typer.echo(f"- {binary_path}")

    # Architectures (prefer lipo, fallback to file)
    archs: list[str] = []
    if which(lipo):
        rc, out, err = _run([lipo, "-info", binary_path])
        if rc == 0:
            archs = _parse_archs_from_lipo(out or err)

    if not archs and which(file_bin):
        rc, out, err = _run([file_bin, "-b", binary_path])
        if rc == 0:
            desc = out or err
            archs = _parse_archs_from_file_output(desc)
            print(f"   file: {desc.strip()}")
    else:
        if archs:
            print(f"   Archs: {' '.join(archs)}")
        else:
            typer.secho("   Unable to determine architectures.")
            ok = False

    # Policy checks:
    #  - Required slice must be present
    #  - If expected is "x86_64", having "arm64" is flagged as unexpected
    if archs:
        if arch not in archs:
            typer.secho(f"   Missing {arch} slice (required).")
            ok = False
        else:
            typer.secho(f"   {arch} present", fg=typer.colors.GREEN)

        if arch == "x86_64" and "arm64" in archs:
            typer.secho("   Contains arm64 slice (unexpected for Intel-only).")
            ok = False

    # Find min macOS version via otool -l.
    # Informational only at this point.
    if which(otool):
        rc, out, err = _run([otool, "-l", binary_path])
        if rc == 0:
            min_os = _extract_min_macos(out or err)
            if min_os:
                typer.secho(f"   min macOS: {min_os}")
            else:
                typer.secho("   min macOS: not found", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"   otool failed on {binary_path}", fg=typer.colors.YELLOW)

    else:
        typer.secho("   otool not found on PATH", fg=typer.colors.YELLOW)

    # codesign -dv --verbose=2
    if which(codesign_bin):
        rc, out, err = _run([codesign_bin, "-dv", "--verbose=2", binary_path])
        if rc == 0:
            typer.secho("   signature: PRESENT", fg=typer.colors.GREEN)
        else:
            typer.secho("   signature: ABSENT (likely unsigned as expected)", fg=typer.colors.YELLOW)
    else:
        typer.secho("   codesign not found on PATH; failingsignature check", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    return ok
