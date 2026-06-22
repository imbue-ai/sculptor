import contextlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from builder.cli import app
from builder.cli import check_release_tag
from builder.cli import s3_uri_to_https
from builder.cli import strip_dev_suffix
from typer.testing import CliRunner

# test_cli.py lives at <repo>/sculptor/builder/test_cli.py; the justfile is at <repo>.
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("version", "tag", "should_pass"),
    [
        # Tag builds: version must be a release (rc/stable) that matches the tag.
        ("0.1.2rc1", "sculptor-v0.1.2rc1", True),
        ("0.1.2", "sculptor-v0.1.2", True),
        ("0.1.2rc1", "sculptor-v0.1.2.rc1", True),  # PEP 440-normalized equality
        ("0.34.0.dev0", "sculptor-v0.0.99rc1", False),  # dev on a tag
        ("0.34.0.dev0", "sculptor-v0.34.0.dev0", False),  # dev version, even if it matches
        ("0.1.3", "sculptor-v0.1.2", False),  # mismatch
        ("0.1.2", "sculptor-vNOTAVERSION", False),  # unparseable tag
        # Non-tag builds: version must be a .dev base (for create-version-file --annotate-dev).
        ("0.34.0.dev0", "", True),
        ("0.1.2", "", False),  # non-dev on a non-tag build
        ("0.1.2rc1", "", False),
    ],
)
def test_check_release_tag(version: str, tag: str, should_pass: bool) -> None:
    error = check_release_tag(version, tag)
    if should_pass:
        assert error is None, f"expected pass, got error: {error}"
    else:
        assert error is not None, "expected an error, got None"


@pytest.mark.parametrize(
    ("version", "args", "expected_exit"),
    [
        # A bare invocation must fall back to the tag="" default. A dev
        # pyproject is consistent with a non-tag build.
        ("0.35.0.dev0", [], 0),
        # An explicit empty --tag value must be treated identically to the
        # default — this is what the justfile recipe sends on a non-tag
        # (main / workflow_dispatch) build, via --tag {{ quote(tag) }}.
        ("0.35.0.dev0", ["--tag", ""], 0),
        # Tag build: a release version that matches the tag passes.
        ("0.35.0rc1", ["--tag", "sculptor-v0.35.0rc1"], 0),
        ("0.35.0", ["--tag", "sculptor-v0.35.0"], 0),
        # Inconsistent contexts still fail with exit 1 (a clean typer.Exit, NOT a
        # usage error) — proving the command reached the version logic.
        ("0.35.0", [], 1),  # non-dev version on a non-tag build
        ("0.35.0.dev0", ["--tag", "sculptor-v0.35.0"], 1),  # dev version on a tag
    ],
)
def test_verify_release_tag_command(version: str, args: list[str], expected_exit: int) -> None:
    """Exercise the verify-release-tag *command* (Typer option parsing + exit codes).

    test_check_release_tag above calls check_release_tag() directly, so it never
    crosses the command boundary where the build-desktop main-push bug lived:
    on a non-tag build the empty --tag token was dropped before any version logic
    ran. These cases pin down that the command accepts a non-tag invocation (no
    --tag, or an explicit empty --tag) and only exits 1 — never a usage error —
    on a genuine version inconsistency.
    """
    runner = CliRunner()
    with patch("builder.cli.pyproject_version", return_value=version):
        result = runner.invoke(app, ["verify-release-tag", *args])
    assert result.exit_code == expected_exit, result.output


def _run_verify_release_tag_recipe(*recipe_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", "verify-release-tag", *recipe_args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_verify_release_tag_recipe_non_tag_smoke() -> None:
    """End-to-end guard for the build-desktop failure on every main push.

    Neither test above crosses the `just` -> shell -> Typer path where the bug
    actually lived. On a main push the workflow ran `just verify-release-tag
    --tag ""`; the old recipe interpolated {{ args }} unquoted, so the shell
    dropped the empty "" token and Typer aborted with "Option '--tag' requires
    an argument" (exit 2) before any version logic ran, skipping the whole build.

    The recipe now quote()s a named tag parameter, so an empty tag survives as
    an empty argument. This runs the recipe exactly as a main push does and
    asserts it reaches the version-check logic rather than the dropped-argument
    usage error, independent of the live pyproject version.
    """
    result = _run_verify_release_tag_recipe()
    combined = result.stdout + result.stderr
    # The exact symptom of the original bug must not reappear.
    assert "requires an argument" not in combined, combined
    # Click usage errors exit 2; reaching the version check exits 0 (consistent)
    # or 1 (inconsistent) — never 2.
    assert result.returncode in (0, 1), f"exit {result.returncode}\n{combined}"


def test_verify_release_tag_recipe_quotes_shell_metacharacters() -> None:
    """The recipe must pass the tag to the builder CLI without shell evaluation.

    CI feeds github.ref_name through this recipe, and git refnames may contain
    shell metacharacters ($, ;, |, ...). With the old unquoted {{ args }}
    interpolation the recipe's shell would have expanded $(...) before the value
    reached the CLI — i.e. command injection. The quoted recipe must deliver the
    tag literally. Whichever consistency error fires (dev-version-on-tag or
    unparseable tag, depending on the live pyproject version), the CLI echoes the
    tag it received: the unexpanded $(...) must appear, and the shell-expanded
    form must not.
    """
    tag = "sculptor-v0$(echo PWNED)"
    result = _run_verify_release_tag_recipe(tag)
    combined = result.stdout + result.stderr
    # An invalid tag is a version-inconsistency (exit 1), never a usage error.
    assert result.returncode == 1, f"exit {result.returncode}\n{combined}"
    assert tag in combined, combined
    assert "sculptor-v0PWNED" not in combined, combined


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.10.0.dev0", "0.10.0"),
        ("1.0.0.dev0", "1.0.0"),
        ("0.10.0.dev20260303001234", "0.10.0"),
        ("0.10.0", "0.10.0"),
        ("0.10.0rc1", "0.10.0rc1"),
        ("1.2.3", "1.2.3"),
    ],
)
def test_strip_dev_suffix(version: str, expected: str) -> None:
    assert strip_dev_suffix(version) == expected


@pytest.mark.parametrize(
    ("s3_uri", "expected"),
    [
        (
            "s3://imbue-sculptor-releases/slim-rc/Sculptor.dmg",
            "https://imbue-sculptor-releases.s3.amazonaws.com/slim-rc/Sculptor.dmg",
        ),
        (
            "s3://imbue-sculptor-releases/slim-rc/Sculptor-0.11.0rc1.dmg",
            "https://imbue-sculptor-releases.s3.amazonaws.com/slim-rc/Sculptor-0.11.0rc1.dmg",
        ),
        (
            "s3://imbue-sculptor-releases/slim/AppImage/x64/Sculptor.AppImage",
            "https://imbue-sculptor-releases.s3.amazonaws.com/slim/AppImage/x64/Sculptor.AppImage",
        ),
        ("../dist/Sculptor.dmg", "../dist/Sculptor.dmg"),
    ],
)
def test_s3_uri_to_https(s3_uri: str, expected: str) -> None:
    assert s3_uri_to_https(s3_uri) == expected


# Manually generated: echo -n '<content>' | sha512sum | xxd -r -p | base64
DARWIN_ARTIFACT_CONTENT = b"fake zip content for testing"
DARWIN_ARTIFACT_SHA512 = "fsrMtNj/GpFctAOdNDBU/ItZRUPz2VcPXCP2MTkqy96PbQyIwJE4/IQU+4pM/6FI4bL4sF1eVJ2++99fG7MQhA=="

LINUX_ARTIFACT_CONTENT = b"fake appimage content for testing"
LINUX_ARTIFACT_SHA512 = "MvY5+dd6Z2GNYn7zuzYVBIwBByrmYuSwam/Cz7Gwytp11NMYzh/ndTesGlUVnVp2Gj7A63e8KZ3kZSchJhMhQg=="


def _invoke_generate_manifest(dist_dir: Path, platform: str, arch: str, version: str) -> None:
    """Invoke generate-autoupdate-manifest so its output lands in `dist_dir`.

    The command resolves its output as ``Path("../dist")`` relative to the working
    directory, so run it from a sibling "build" dir whose ``../dist`` is `dist_dir`
    (which must therefore be named "dist"). We deliberately do NOT patch
    ``builder.cli.Path``: that mock would shadow the ``Path``-typed parameter
    annotations on other CLI commands and break typer's app introspection.
    """
    work_dir = dist_dir.parent / "build"
    work_dir.mkdir(exist_ok=True)
    runner = CliRunner()
    with (
        patch("builder.cli.pyproject_version", return_value=version),
        patch("builder.cli.pep_440_to_semver", return_value=version),
        contextlib.chdir(work_dir),
    ):
        result = runner.invoke(app, ["generate-autoupdate-manifest", platform, arch])

    assert result.exit_code == 0, f"CLI failed: {result.output}"


def test_generate_autoupdate_manifest_darwin(tmp_path: Path) -> None:
    """Test that generate_autoupdate_manifest produces a valid manifest for macOS."""
    version = "1.2.3"
    dist_dir = tmp_path / "dist"
    artifact_dir = dist_dir / "zip" / "darwin" / "arm64"
    artifact_dir.mkdir(parents=True)
    artifact_filename = f"Sculptor-darwin-arm64-{version}.zip"
    (artifact_dir / artifact_filename).write_bytes(DARWIN_ARTIFACT_CONTENT)

    _invoke_generate_manifest(dist_dir, "darwin", "arm64", version)

    manifest = yaml.safe_load((artifact_dir / "latest-mac.yml").read_text())
    assert manifest["version"] == "1.2.3"
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["url"] == artifact_filename
    assert manifest["files"][0]["sha512"] == DARWIN_ARTIFACT_SHA512
    assert manifest["files"][0]["size"] == len(DARWIN_ARTIFACT_CONTENT)
    assert "releaseDate" in manifest


def test_generate_autoupdate_manifest_linux(tmp_path: Path) -> None:
    """Test that generate_autoupdate_manifest produces a valid manifest for Linux."""
    dist_dir = tmp_path / "dist"
    artifact_dir = dist_dir / "AppImage" / "x64"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "Sculptor.AppImage").write_bytes(LINUX_ARTIFACT_CONTENT)

    _invoke_generate_manifest(dist_dir, "linux", "x64", "2.0.0")

    manifest = yaml.safe_load((artifact_dir / "latest-linux.yml").read_text())
    assert manifest["version"] == "2.0.0"
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["url"] == "Sculptor.AppImage"
    assert manifest["files"][0]["sha512"] == LINUX_ARTIFACT_SHA512
    assert manifest["files"][0]["size"] == len(LINUX_ARTIFACT_CONTENT)
    assert "releaseDate" in manifest
