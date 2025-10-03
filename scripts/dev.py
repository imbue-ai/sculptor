#!/usr/bin/env python3
"""This build script contains various functions used to assemble the build
artifact of Sculptor.

By only building the wheels we need, we save from having to import all of the
generally_intelligent repo.
"""

import base64
import enum
import fnmatch
import functools
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from datetime import timezone
from importlib import resources
from pathlib import Path
from typing import Callable
from typing import Container

import pydantic.dataclasses
import tomlkit
import typer
from packaging.version import Version

import imbue_core.git
from sculptor import sentry_settings
from sculptor.cli.dev import CONTROL_PLANE_REQUIRED_SUBPROJECTS
from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_IMAGE_URL,
)
from sculptor.version import VersionComponent
from sculptor.version import dev_git_sha
from sculptor.version import dev_semver
from sculptor.version import next_version
from sculptor.version import pep_440_to_semver

app = typer.Typer(pretty_exceptions_enable=False)


def _run_bash_in_docker_container(container_id, cwd, bash_cmd):
    subprocess.run(
        [
            "docker",
            "exec",
            container_id,
            "bash",
            "-c",
            bash_cmd,
        ],
        check=True,
        cwd=cwd,
    )


@app.command("rebuild_container_for_local_testing")
def rebuild_container_for_local_testing(control_plane_volume_name: str) -> None:
    sub_projects = CONTROL_PLANE_REQUIRED_SUBPROJECTS
    project_root_dir = imbue_core.git.get_git_repo_root()
    # Note that we use zip (instead of git archive) so that we can include uncommitted changes.
    control_plane_src_path = "sculptor/claude-container/build/control-plane-src.zip"
    subprocess.run(["mkdir", "-p", str(Path(control_plane_src_path).parent)], check=True, cwd=project_root_dir)
    subprocess.run(
        [
            "zip",
            "-r",
            "-o",
            control_plane_src_path,
            *sub_projects,
        ],
        check=True,
        cwd=project_root_dir,
    )

    # control-plane-init:
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{control_plane_volume_name}:/imbue", f"{CONTROL_PLANE_IMAGE_URL}", "true"],
        check=True,
    )

    # This container allows us to replace the wheels.
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-v",
            f"{control_plane_volume_name}:/imbue",
            f"{CONTROL_PLANE_IMAGE_URL}",
            "sleep",
            "infinity",
        ],
        check=True,
        capture_output=True,
        cwd=project_root_dir,
    )
    container_id = result.stdout.decode().strip()

    try:
        print(f"Using container id {container_id}")

        subprocess.run(
            [
                "docker",
                "cp",
                control_plane_src_path,
                f"{container_id}:/imbue/workspace/control-plane-src.zip",
            ],
            check=True,
            cwd=project_root_dir,
        )
        _run_bash_in_docker_container(
            container_id, project_root_dir, "cd /imbue/workspace && unzip -o control-plane-src.zip"
        )
        _run_bash_in_docker_container(
            container_id,
            project_root_dir,
            "cd /imbue && . .venv/bin/activate && cd /imbue/workspace && uv sync --only-group control-plane --active --frozen",
        )

        # Mark the volume contents as ready so it doesn't get overwritten.
        _run_bash_in_docker_container(container_id, project_root_dir, "touch /imbue/VOLUME_READY.TXT")
    finally:
        # Clean up the container
        subprocess.run(["docker", "kill", container_id], check=True)
        subprocess.run(["docker", "rm", container_id], check=True)


@app.command("version")
def version() -> None:
    """Print the Sculptor version and Git SHA.

    NOTE: This relays the "dev semver", i.e minus the "-dev" suffix for the semver.
    """
    typer.echo(f"Sculptor v{dev_semver()}")
    typer.echo(f"Git SHA:  {dev_git_sha()}")


# These set convenient defaults on subprocess.run that text-decodes output and raises on non-zero exit status

_run_out = functools.partial(subprocess.run, check=True, stdout=sys.stdout, text=True)  # Writes to standard out
_run_pipe = functools.partial(
    subprocess.run, check=True, stdout=subprocess.PIPE, text=True
)  # Writes to a pipe for checking


@app.command("create-release-artifacts")
def create_release_artifacts() -> None:
    """Creates the release artifacts for Sculptor (tar ball)."""
    _run_out(["just", "clean", "dist"])


@app.command("create-publication-artifacts")
def create_publication_artifacts() -> None:
    """Creates publication artifacts for Sculptor (dmg, deb, rpm) specific to
    the current platform.
    """
    _run_out(["just", "refresh", "pkg"])


@app.command("update-public-repo")
def update_public_repo() -> None:
    """[DEPRECATED] Call this function to update the public version of the repository."""

    raise Exception(
        "This use case is deprecated -- #product-marketing now maintains https://github.com/imbue-ai/sculptor manually."
    )


@app.command("setup-build-vars")
def setup_build_vars(environment: str) -> None:
    """Depending on the build environment, we will set up the build variables."""
    # match environment against the known environments, and export the following variables
    match environment:
        case "dev":
            release_id = dev_semver() + "-dev"
            frontend_dsn = sentry_settings.SCULPTOR_DEV_FRONTEND_SENTRY_DSN
        case "testing":
            release_id = dev_semver() + "-testing"
            frontend_dsn = sentry_settings.SCULPTOR_TESTING_FRONTEND_SENTRY_DSN
        case "production":
            release_id = dev_semver()
            frontend_dsn = sentry_settings.SCULPTOR_PRODUCTION_FRONTEND_SENTRY_DSN
        case _:
            typer.secho("Invalid environment specified. Must be one of: dev, testing, prod.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    typer.echo(f"export SCULPTOR_SENTRY_RELEASE_ID='{release_id}'")
    typer.echo(f"export SCULPTOR_FRONTEND_SENTRY_DSN='{frontend_dsn}'")


# This bucket will contain every single release, keyed by sculptor version.
S3_BUCKET_RELEASES = "imbue-sculptor-releases"

# This bucket contains the "channels" that we release to.
S3_BUCKET_CHANNELS = "imbue-sculptor-latest"


# Create an enum for the types of file extensions we might upload
class FileExtension(enum.Enum):
    TARGZ = ".tar.gz"
    DMG = ".dmg"


@pydantic.dataclasses.dataclass
class ReleaseChannel:
    """A Release Channel is defined by its name, and defines strategies for how it is kept updated."""

    name: str

    # Given a particular version, where should the build artifact be uploaded.
    destination_prefix: Callable[[str], str]

    def upload_version(self, artifact: Path, version: str, file_extension: FileExtension) -> None:
        _run_out(
            [
                "uvx",
                "--from",
                "awscli==1.41.12",
                "--refresh",
                "aws",
                "s3",
                "cp",
                str(artifact),
                self.destination_prefix(version) + file_extension.value,
            ]
        )


RELEASE_CHANNELS = {
    rc.name: rc
    for rc in [
        ReleaseChannel(
            name="latest",
            destination_prefix=lambda version: f"s3://{S3_BUCKET_RELEASES}/sculptor-{version}",
        ),
        ReleaseChannel(name="stable", destination_prefix=lambda _: f"s3://{S3_BUCKET_CHANNELS}/sculptor"),
        ReleaseChannel(name="internal", destination_prefix=lambda _: f"s3://{S3_BUCKET_CHANNELS}/internal/sculptor"),
    ]
}


@app.command("cut-release")
def cut_release(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """Cut a new release branch from main and tag it."""
    if not bypass_checks:
        ensure_on_branch("main")
        ensure_clean_tree()

    target_release_version = dev_semver()
    release_candidate_version = next_version(target_release_version, VersionComponent.PRE_RELEASE)

    typer.echo(f"Begining a release branch for {target_release_version}.")

    # Verify there isn't a release tag and release branch for this.
    _run_out(["git", "fetch", "--tags"])
    _run_out(["git", "fetch"])

    if _run_pipe(["git", "tag", "--list", "sculptor-v{release_candidate_version}"]).stdout:
        typer.echo("A release tag already exists for this version. Did you need to bump the version first?")
        raise typer.Exit(code=1)

    if _run_pipe(["git", "branch", "--list", f"release/{release_candidate_version}"]).stdout:
        typer.echo("A branch already exists for this version, but no release tag.")
        typer.echo("A prior release cut failed. Please delete the branch from origin and try again.")
        raise typer.Exit(code=1)

    # Write the rc version to the pyproject.toml file.
    commit_new_version(f"release/sculptor-v{target_release_version}", release_candidate_version, dry_run=dry_run)

    create_release_artifacts()

    typer.echo(f"Building a new release branch for Sculptor {release_candidate_version} from git sha {dev_git_sha()}")

    tarballs = sorted(dist_dir.glob("sculptor-*.tar.gz"))
    if not tarballs:
        typer.secho("No sculptor-*.tar.gz found in {dist_dir}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if len(tarballs) > 1:
        typer.secho(f"Too many tar files found in {dist_dir} - did you clean first?", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    latest_tgz = tarballs[-1]

    typer.echo(f"  • Found {latest_tgz.name}")

    if not dry_run:
        typer.echo("  • Uploading release artifacts to S3")
        RELEASE_CHANNELS["latest"].upload_version(latest_tgz, release_candidate_version, FileExtension.TARGZ)
        RELEASE_CHANNELS["internal"].upload_version(latest_tgz, release_candidate_version, FileExtension.TARGZ)

        push_tags(release_candidate_version)
        typer.secho("Release complete.", fg=typer.colors.GREEN)
    else:
        typer.echo(f"Would have updated 'latest' and 'internal' to {latest_tgz!r}, but dry-run mode was enabled.")
        typer.secho("Would have released, but dry-run mode was enabled", fg=typer.colors.YELLOW)


@app.command("fixup-release")
def fixup_release(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """Cut a new release branch from main and tag it."""
    if not bypass_checks:
        ensure_on_branch("release/sculptor-v*")
        ensure_clean_tree()

    prior_release_version = dev_semver()
    release_candidate_version = next_version(prior_release_version, VersionComponent.PRE_RELEASE)

    typer.echo(f"Incrementing the release to {release_candidate_version}.")

    # Verify there isn't a release tag and release branch for this.
    _run_out(["git", "fetch", "--tags"])
    _run_out(["git", "fetch"])

    if _run_pipe(["git", "tag", "--list", "sculptor-v{release_candidate_version}"]).stdout:
        typer.echo("A release tag already exists for this version. Did you need to bump the version first?")
        raise typer.Exit(code=1)

    # Write the rc version to the pyproject.toml file.
    commit_new_version(None, release_candidate_version, dry_run=dry_run)

    create_release_artifacts()

    typer.echo(f"Building a new release branch for Sculptor {release_candidate_version} from git sha {dev_git_sha()}")

    tarballs = sorted(dist_dir.glob("sculptor-*.tar.gz"))
    if not tarballs:
        typer.secho(f"No sculptor-*.tar.gz found in {dist_dir}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if len(tarballs) > 1:
        typer.secho(f"Too many tar files found in {dist_dir} - did you clean first?", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    latest_tgz = tarballs[-1]
    typer.echo(f"  • Found {latest_tgz.name}")

    if not dry_run:
        typer.echo("  • Uploading release artifacts to S3")
        RELEASE_CHANNELS["latest"].upload_version(latest_tgz, release_candidate_version, FileExtension.TARGZ)
        RELEASE_CHANNELS["internal"].upload_version(latest_tgz, release_candidate_version, FileExtension.TARGZ)

        push_tags(release_candidate_version)
        typer.secho("Release complete.", fg=typer.colors.GREEN)
    else:
        typer.echo(f"Would have updated 'latest' and 'internal' to {latest_tgz!r}, but dry-run mode was enabled.")
        typer.secho("Would have released, but dry-run mode was enabled", fg=typer.colors.YELLOW)


@app.command("promote")
def promote(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """Publish the latest Sculptor build to all release destinations."""

    release_version = next_version(dev_semver(), VersionComponent.STRIP_PRE_RELEASE)

    if not bypass_checks:
        ensure_on_branch(f"release/sculptor-v{release_version}")
        ensure_clean_tree()

        # Run git fetch, and abort if the release branch is BEHIND its upstream
        _run_out(["git", "fetch", "--prune"])

        status = _run_pipe(["git", "status", "--porcelain=2", "--branch"]).stdout
        for line in status.splitlines():
            if line.startswith("# branch.ab"):
                # The porcelain line looks like:
                # '# branch.ab +<ahead> -<behind>'
                _, _, _, behind_tok = line.split()

                behind = int(behind_tok.lstrip("-"))

                if behind > 0:
                    typer.secho(
                        "Your local release branch is behind the remote release branch. Please pull/rebase before continuing.",
                        fg=typer.colors.RED,
                    )
                    raise typer.Exit(code=1)
                break  # done once we've parsed the branch.ab line

    # Let's commit the new version to the current branch.
    commit_new_version(None, release_version, dry_run=dry_run)
    # Set the version to the full deploy
    create_release_artifacts()

    typer.echo(f"Releasing Sculptor {dev_semver()} from git sha {dev_git_sha()}")

    tarballs = sorted(dist_dir.glob("sculptor-*.tar.gz"))
    if not tarballs:
        typer.secho(f"No sculptor-*.tar.gz found in {dist_dir}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if len(tarballs) > 1:
        typer.secho(f"Too many tar files found in {dist_dir} - did you clean first?", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    latest_tgz = tarballs[-1]

    typer.echo(f"  • Found {latest_tgz.name}")
    typer.echo("  • Uploading release artifacts to S3")

    if not dry_run:
        RELEASE_CHANNELS["latest"].upload_version(latest_tgz, release_version, FileExtension.TARGZ)
        RELEASE_CHANNELS["internal"].upload_version(latest_tgz, release_version, FileExtension.TARGZ)
        RELEASE_CHANNELS["stable"].upload_version(latest_tgz, release_version, FileExtension.TARGZ)

        push_tags(release_version)
        typer.secho("Release complete.", fg=typer.colors.GREEN)
    else:
        typer.secho(
            f"Would have updated 'latest', 'internal' and 'stable' to {latest_tgz!r}, but dry-run mode was enabled."
        )


@app.command("publish")
def publish(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """This will publish the Sculptor artifacts to s3

    This must be run after `cut-release,  `promote` or `fixup-release`.
    This must also be run once on every platform that we support (macOS and Linux).
    """
    # We only publish the specific concrete version that is in the pyproject.toml file.
    release_version = dev_semver()

    # TODO(danver): Check that we run this on the right branch.

    # TODO(danver): Check that we haven't already published this version.

    # TODO(danver): Detect which artifacts we have to upload: for now we will
    # only upload to the latest channel and the internal channel.
    create_publication_artifacts()

    typer.echo(
        f"About to publish for Sculptor {release_version} from git sha {dev_git_sha()} on platform {platform.system()!r}"
    )

    # TODO(danver): DMGs are macOS only, we need to customize this step for the platform.
    latest_dmg = dist_dir / "Sculptor.dmg"
    typer.echo(f"  • Found {latest_dmg.name}")

    if not dry_run:
        typer.echo("  • Publishing artifacts to S3")
        RELEASE_CHANNELS["latest"].upload_version(latest_dmg, release_version, FileExtension.DMG)
        RELEASE_CHANNELS["internal"].upload_version(latest_dmg, release_version, FileExtension.DMG)

    else:
        typer.echo(f"Would have updated 'latest' and 'internal' to {latest_dmg!r}, but dry-run mode was enabled.")


@app.command("bump-version")
def bump_version(
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
) -> None:
    """Bumps the version of Sculptor and creates an MR to Gitlab."""

    if not bypass_checks:
        ensure_on_branch("main")
        ensure_clean_tree()

    old_version = dev_semver()
    typer.echo(f"Current Sculptor version is {old_version}")
    bump_index = "Mmp".index(
        typer.prompt("Are you trying to bump a [M]ajor, [m]inor, or [p]atch version? (default: patch)", default="p")
    )
    new_version = next_version(old_version, VersionComponent(bump_index))
    typer.echo(f"The new Sculptor version will be {new_version}")

    # New Branch for the MR
    branch_name = f"automated/bump-sculptor-v{new_version}"
    commit_new_version(branch_name, new_version)


def commit_new_version(branch_name: str | None, new_version: str, dry_run: bool = False) -> None:
    """Helper method to commit the new version to a new branch.

    Preconditions:
        - The working tree is clean.
    """

    if branch_name:
        # We want to create a new branch.
        _run_out(["git", "checkout", "-b", branch_name])

    write_project_version(new_version)
    repo_root_path = imbue_core.git.get_git_repo_root()

    _run_out(["uv", "lock"])

    _run_out(
        [
            "git",
            "add",
            str(repo_root_path / "sculptor" / "pyproject.toml"),
            str(repo_root_path / "uv.lock"),
        ]
    )

    _run_out(
        [
            "git",
            "commit",
            f"--message=Bumping Sculptor Version to v{new_version}",
        ]
    )

    if not dry_run:
        if branch_name:
            # Commit to the new branch.
            _run_out(["git", "push", "--set-upstream", "origin", branch_name])
        else:
            # Commit to the same branch.
            _run_out(["git", "push", "--set-upstream", "origin"])
    else:
        typer.echo(f"Would have pushed branch {branch_name} to origin, but dry-run mode was enabled.")
        typer.echo("Please remember to delete this branch before trying to take another cut.")


@app.command("generate-release-notes")
def generate_release_notes(
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
) -> None:
    """Uses claude code to generate release notes for the current version."""
    version = Version(dev_semver())

    if not bypass_checks:
        ensure_on_branch(f"release/sculptor-v{version.base_version}", "main")
        ensure_clean_tree()

    with resources.as_file(resources.files("sculptor").joinpath("scripts", "prompt-release-notes.md")) as prompt_path:
        prompt = prompt_path.read_text()

    repo_root = imbue_core.git.get_git_repo_root()

    _run_out(
        ["claude", "-p", prompt, "--max-turns=50", "--allowedTools", "Bash(git log:*)", "Read", "Edit"],
        cwd=repo_root,
    )

    typer.secho("Release notes generated in sculptor/CHANGELOG.sculpted.md", fg=typer.colors.GREEN)
    typer.secho("Done generating release notes.", fg=typer.colors.GREEN)


def write_project_version(new_version: str) -> None:
    """Helper method to write the updated project version to the pyproject.toml file."""
    pyproject = resources.files("sculptor").joinpath("../pyproject.toml")

    with resources.as_file(pyproject) as path, path.open("r") as f:
        config = tomlkit.load(f)

    project = config["project"]
    assert isinstance(project, Container)
    project["version"] = new_version

    with resources.as_file(pyproject) as path, path.open("w") as f:
        tomlkit.dump(config, f)


def push_tags(version: str) -> None:
    """Push a new tag with the given version to origin."""
    # Create a new release tag it and push it to origin.
    tagname = f"sculptor-v{version}"
    _run_out(["git", "tag", tagname])
    # No verify since this is only pushing a tag, and pyre can be finicky.
    _run_out(["git", "push", "origin", tagname, "--no-verify"])


def ensure_clean_tree() -> None:
    """Abort if the working tree has uncommitted changes."""
    if _run_pipe(["git", "status", "--porcelain"]).stdout.strip():
        typer.secho(
            "Working directory is dirty – commit or stash changes first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def ensure_on_branch(*expected_names: str) -> None:
    """Abort unless HEAD is on *expected* branch.

    Supports wildcard expressions such as "release/*"
    """
    if not expected_names:
        expected_names = ("main",)

    current = _run_pipe(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if not any(fnmatch.fnmatch(current, expected_name) for expected_name in expected_names):
        typer.secho(
            f"Your branch must match {expected_names!r}. (current: {current!r}).",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


@app.command("create-version-file")
def create_version_file() -> None:
    """Create a version file with the Sculptor version and Git SHA."""
    sculptor_version = dev_semver()
    sha = dev_git_sha()
    with open("sculptor/_version.py", "w") as f:
        f.write(
            f'"""Sculptor v{sculptor_version} version file, autogenerated by the build process.\nDo not edit."""\n'
        )
        f.write(f"__version__ = '{sculptor_version}'\n")
        f.write(f"__git_sha__ = '{sha}'\n")


@app.command("sync-frontend-version")
def sync_frontend_version(
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Reset frontend package.json version to 0.0.0"),
) -> None:
    """Sync frontend package.json version with sculptor pyproject.toml version, or reset to 0.0.0 with --reverse."""
    frontend_package_json_path = Path("frontend/package.json")

    if not frontend_package_json_path.exists():
        typer.secho(f"Frontend package.json not found at {frontend_package_json_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Read current package.json
    with frontend_package_json_path.open("r") as f:
        package_data = json.load(f)

    # Determine target version
    old_version = package_data.get("version", "unknown")
    if reverse:
        target_version = "0.0.0"
        action = "Reset"
    else:
        target_version = pep_440_to_semver(dev_semver())
        action = "Updated"

    package_data["version"] = target_version

    # Write back to package.json
    with frontend_package_json_path.open("w") as f:
        json.dump(package_data, f, indent=2)
        f.write("\n")  # Add final newline for consistency

    typer.secho(f"{action} frontend package.json version: {old_version} → {target_version}", fg=typer.colors.GREEN)


@app.command("generate-autoupdate-manifest-macos")
def generate_autoupdate_manifest_macos() -> None:
    """Generate the autoupdate manifest for Sculptor's macOS zip packages."""
    _generate_autoupdate_manifest("latest-mac.yml", "zip")


@app.command("generate-autoupdate-manifest-linux")
def generate_autoupdate_manifest_linux() -> None:
    """Generate the autoupdate manifest for Sculptor's Linux AppImage package."""
    _generate_autoupdate_manifest("latest-linux.yml", "AppImage")


def _generate_autoupdate_manifest(out_filename: str, package_extension: str) -> None:
    pkg_artifact_dir = Path.cwd() / "out" / "make"
    if not pkg_artifact_dir.exists():
        typer.secho(
            f"Package artifact directory not found at {pkg_artifact_dir}. Please run just pkg", fg=typer.colors.RED
        )
        raise typer.Exit(code=1)

    # We should search recursively for all the descendant .zip files
    pkg_files = list(pkg_artifact_dir.rglob(f"*.{package_extension}"))
    if not pkg_files:
        typer.secho(f"No .{package_extension} files found in {pkg_artifact_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    app_version = pep_440_to_semver(dev_semver())

    for pkg_file in pkg_files:
        typer.echo(f"Generating {out_filename} for version {app_version} from {pkg_file.name}")

        file_buffer = pkg_file.read_bytes()
        sha512_b64 = base64.b64encode(hashlib.sha512(file_buffer).digest()).decode("ascii")
        file_size = pkg_file.stat().st_size

        release_date = datetime.now(timezone.utc).isoformat()
        yaml_content = f"""version: {app_version}
files:
  - url: {pkg_file.name}
    sha512: {sha512_b64}
    size: {file_size}
releaseDate: {release_date}
"""
        yaml_path = pkg_file.parent / out_filename
        yaml_path.write_text(yaml_content)
        typer.secho(f"Generated {yaml_path} for electron-updater.", fg=typer.colors.GREEN)


@app.command("manual-precommit")
def manual_precommit() -> None:
    """Runs precommit manually on your repository, including all unstaged files."""

    # We don't run every single manual check (yet!) because some are not clean in our repository.
    SELECTED_MANUAL_CHECKS = ["tsc", "eslint-lint"]

    repo_root_path = imbue_core.git.get_git_repo_root()
    _run_out(["uv", "run", "sculptor_npm_run", "generate-api"], cwd=repo_root_path)
    modified_files = _run_pipe(["git", "ls-files", "-m"], cwd=repo_root_path).stdout.splitlines()
    any_failures = False

    if modified_files:
        # Run the checks only on modified files.
        try:
            _run_out(
                [
                    "uv",
                    "run",
                    "--project",
                    "sculptor",
                    "pre-commit",
                    "run",
                    "--hook-stage",
                    "pre-commit",
                    "--files",
                ]
                + modified_files
            )
        except subprocess.CalledProcessError:
            any_failures = True

        for check in SELECTED_MANUAL_CHECKS:
            try:
                _run_out(
                    [
                        "uv",
                        "run",
                        "--project",
                        "sculptor",
                        "pre-commit",
                        "run",
                        "--hook-stage",
                        "manual",
                        check,
                        "--files",
                    ]
                    + modified_files,
                    cwd=repo_root_path,
                )
            except subprocess.CalledProcessError:
                any_failures = True

    # Now also run the check from our last commit diffed against main.
    try:
        _run_out(
            [
                "uv",
                "run",
                "--project",
                "sculptor",
                "pre-commit",
                "run",
                "--hook-stage",
                "pre-commit",
                "--from-ref",
                "main",
                "--to-ref",
                "HEAD",
            ],
            cwd=repo_root_path,
        )
    except subprocess.CalledProcessError:
        any_failures = True

    for check in SELECTED_MANUAL_CHECKS:
        try:
            _run_out(
                [
                    "uv",
                    "run",
                    "--project",
                    "sculptor",
                    "pre-commit",
                    "run",
                    "--hook-stage",
                    "manual",
                    "--from-ref",
                    "main",
                    "--to-ref",
                    "HEAD",
                    check,
                ]
                + ["--files"]
                + modified_files,
                cwd=repo_root_path,
            )
        except subprocess.CalledProcessError:
            any_failures = True

    if any_failures:
        typer.secho("Some checks failed. Please review the output above.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
