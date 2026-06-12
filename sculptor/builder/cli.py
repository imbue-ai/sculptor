#!/usr/bin/env python3
"""This build script contains various functions used to assemble the build
artifact of Sculptor.

By only building the wheels we need, we save from having to import all of the
sculptor repo.
"""

import base64
import datetime
import fnmatch
import functools
import hashlib
import json
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Container
from typing import assert_never

import tomlkit
import typer
from builder import darwin
from builder.artifacts import BuildStage
from builder.artifacts import PLATFORM_ARCH_TO_TARGET
from builder.artifacts import artifacts_for_target_and_stage
from packaging.version import InvalidVersion
from packaging.version import Version

import imbue_core.git
from sculptor import posthog_settings
from sculptor import sentry_settings
from sculptor.version import VersionComponent
from sculptor.version import dev_git_sha
from sculptor.version import is_devrelease
from sculptor.version import is_prerelease
from sculptor.version import next_version
from sculptor.version import pep_440_to_semver
from sculptor.version import pyproject_version

app = typer.Typer(pretty_exceptions_enable=False)


# These set convenient defaults on subprocess.run that text-decodes output and raises on non-zero exit status

_run_out = functools.partial(subprocess.run, check=True, stdout=sys.stdout, text=True)  # Writes to standard out
_run_pipe = functools.partial(
    subprocess.run, check=True, stdout=subprocess.PIPE, text=True
)  # Writes to a pipe for checking


@app.command("generate-autoupdate-manifest")
def generate_autoupdate_manifest(platform: str, arch: str) -> None:
    """Generate an electron-updater compatible YAML manifest for auto-updates.

    The manifest includes the artifact filename, version, SHA-512 hash, and file size.
    """
    semver_version = pep_440_to_semver(pyproject_version())
    dist_dir = Path("../dist")

    if platform == "darwin":
        artifact_filename = f"Sculptor-darwin-arm64-{semver_version}.zip"
        manifest_filename = "latest-mac.yml"
        output_dir = dist_dir / "zip" / "darwin" / arch
    elif platform == "linux":
        artifact_filename = "Sculptor.AppImage"
        manifest_filename = "latest-linux-arm64.yml" if arch == "arm64" else "latest-linux.yml"
        output_dir = dist_dir / "AppImage" / arch
    else:
        typer.secho(f"Unsupported platform: {platform}. Must be 'darwin' or 'linux'.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    artifact_path = output_dir / artifact_filename
    if not artifact_path.exists():
        typer.secho(f"Artifact not found: {artifact_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    sha512_hash = hashlib.sha512(artifact_path.read_bytes()).digest()
    sha512_base64 = base64.b64encode(sha512_hash).decode("ascii")
    file_size = artifact_path.stat().st_size
    release_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    manifest_lines = [
        f"version: {semver_version}",
        "files:",
        f"  - url: {artifact_filename}",
        f"    sha512: {sha512_base64}",
        f"    size: {file_size}",
        f"releaseDate: {release_date}",
        "",
    ]
    manifest_content = "\n".join(manifest_lines)

    manifest_path = output_dir / manifest_filename
    manifest_path.write_text(manifest_content)
    typer.secho(f"Generated manifest: {manifest_path}", fg=typer.colors.GREEN)


@app.command("create-publication-artifacts")
def create_publication_artifacts() -> None:
    """Creates publication artifacts for Sculptor (dmg, deb, rpm) specific to
    the current platform.

    This command does the heavy lifting for building artifacts. After this, the artifacts will be available in
    `sculptor/dist`
    """
    _run_out(["just", "refresh", "pkg"])


@app.command("version")
def version() -> None:
    """Print the Sculptor version and Git SHA."""
    typer.echo(f"Sculptor v{pyproject_version()}")
    typer.echo(f"Git SHA:  {dev_git_sha()}")


@app.command("setup-build-vars")
def setup_build_vars(environment: str) -> None:
    """Depending on the build environment, we will set up the build variables."""
    # match environment against the known environments, and export the following variables
    release_id: str
    frontend_dsn: str
    frontend_posthog_token: str
    semver = pep_440_to_semver(pyproject_version())
    match environment:
        case "dev":
            release_id = f"{semver}-dev"
            frontend_dsn = sentry_settings.SCULPTOR_DEV_FRONTEND_SENTRY_DSN
            frontend_posthog_token = posthog_settings.SCULPTOR_DEV_FRONTEND_POSTHOG_TOKEN
        case "testing":
            release_id = f"{semver}-testing"
            frontend_dsn = sentry_settings.SCULPTOR_TESTING_FRONTEND_SENTRY_DSN
            frontend_posthog_token = posthog_settings.SCULPTOR_TESTING_FRONTEND_POSTHOG_TOKEN
        case "production":
            release_id = semver
            frontend_dsn = sentry_settings.SCULPTOR_PRODUCTION_FRONTEND_SENTRY_DSN
            frontend_posthog_token = posthog_settings.SCULPTOR_PRODUCTION_FRONTEND_POSTHOG_TOKEN
        case str():
            typer.secho("Invalid environment specified. Must be one of: dev, testing, prod.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        case _ as never:
            assert_never(never)

    typer.echo(f"export SCULPTOR_SENTRY_RELEASE_ID='{release_id}'")
    typer.echo(f"export SCULPTOR_FRONTEND_SENTRY_DSN='{frontend_dsn}'")
    typer.echo(f"export SCULPTOR_FRONTEND_POSTHOG_TOKEN='{frontend_posthog_token}'")
    typer.echo(f"export SCULPTOR_FRONTEND_POSTHOG_HOST='{posthog_settings.SCULPTOR_FRONTEND_POSTHOG_HOST}'")


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
    """Cut a new release branch from main and tag it.

    This expects main to be on a .dev0 version (e.g. 0.10.0.dev0). The command:
    1. Creates a release branch with the first RC (e.g. 0.10.0rc1)
    2. Bumps main to the next minor .dev0 version (e.g. 0.11.0.dev0)

    Can be run from `main` or from any branch sitting at the tip of `origin/main`
    (e.g. a worktree branch), since git refuses to share a checked-out branch
    across worktrees.
    """
    if not bypass_checks:
        # Fetch before checking so we compare against the latest origin/main.
        _run_out(["git", "fetch", "origin", "main"])
        ensure_at_main_tip()
        ensure_clean_tree()

    # Capture the starting ref so we can return to it after the release branch
    # is created. Used in place of `git checkout main` further down, which
    # would fail in a second worktree where main is held by another checkout.
    start_ref = _run_pipe(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if start_ref == "HEAD":
        typer.secho(
            "Refusing to cut a release from a detached HEAD. Check out a branch at the tip of origin/main first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    current_version = pyproject_version()
    if not bypass_checks and not is_devrelease(current_version):
        typer.secho(
            f"Expected a .dev version on main, got '{current_version}'. Did you forget to bump the version after the last release?",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    # Strip .dev0 to get the target release version (e.g. 0.10.0.dev0 -> 0.10.0)
    target_release_version = strip_dev_suffix(current_version)
    release_candidate_version = next_version(target_release_version, VersionComponent.PRE_RELEASE)

    typer.echo(f"Beginning a release branch for {target_release_version}.")

    # Verify there isn't a release tag and release branch for this.
    _run_out(["git", "fetch", "--tags"])
    _run_out(["git", "fetch"])

    if _run_pipe(["git", "tag", "--list", f"sculptor-v{release_candidate_version}"]).stdout:
        typer.echo("A release tag already exists for this version. Did you need to bump the version first?")
        raise typer.Exit(code=1)

    if _run_pipe(["git", "branch", "--list", f"release/{release_candidate_version}"]).stdout:
        typer.echo("A branch already exists for this version, but no release tag.")
        typer.echo("A prior release cut failed. Please delete the branch from origin and try again.")
        raise typer.Exit(code=1)

    # Write the rc version to the pyproject.toml file on the release branch.
    commit_new_version(f"release/sculptor-v{target_release_version}", release_candidate_version, dry_run=dry_run)

    typer.echo(f"Created a new release branch for Sculptor {release_candidate_version} from git sha {dev_git_sha()}")

    if not dry_run:
        push_tags(release_candidate_version)
        typer.secho("Release branch created.", fg=typer.colors.GREEN)
    else:
        typer.secho("Would have released, but dry-run mode was enabled", fg=typer.colors.YELLOW)

    # Create a branch and MR to bump main to the next minor dev version.
    next_dev_version = next_version(target_release_version, VersionComponent.MINOR) + ".dev0"
    typer.echo(f"\nBumping main to {next_dev_version} for the next development cycle.")

    _run_out(["git", "checkout", start_ref])

    # Capture the branching point before commit_new_version changes HEAD.
    branch_point_sha = _run_pipe(["git", "rev-parse", "HEAD"]).stdout.strip()

    bump_branch = f"automated/bump-sculptor-v{next_dev_version}"
    commit_new_version(bump_branch, next_dev_version, dry_run=dry_run)

    release_branch = f"release/sculptor-v{target_release_version}"
    description = (
        f"Automated version bump after cutting release branch `{release_branch}`"
        + f" (RC `{release_candidate_version}`)."
        + f"\n\nNote: commit {branch_point_sha} is the last commit on main versioned as `{current_version}`."
        + " Any commits merged between that point and this MR will carry the old version."
    )
    create_version_bump_mr(bump_branch, next_dev_version, description, dry_run=dry_run)


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

    prior_release_version = pyproject_version()
    release_candidate_version = next_version(prior_release_version, VersionComponent.PRE_RELEASE)

    typer.echo(f"Incrementing the release to {release_candidate_version}.")

    # Verify there isn't a release tag and release branch for this.
    _run_out(["git", "fetch", "--tags"])
    _run_out(["git", "fetch"])

    if _run_pipe(["git", "tag", "--list", f"sculptor-v{release_candidate_version}"]).stdout:
        typer.echo("A release tag already exists for this version. Did you need to bump the version first?")
        raise typer.Exit(code=1)

    # Write the rc version to the pyproject.toml file.
    commit_new_version(None, release_candidate_version, dry_run=dry_run)

    typer.echo(
        f"About to trigger a new release branch for Sculptor {release_candidate_version} from git sha {dev_git_sha()}"
    )

    if not dry_run:
        push_tags(release_candidate_version)
        typer.secho("Tags have been pushed, and release will be kicked off", fg=typer.colors.GREEN)
    else:
        typer.secho("Would have released, but dry-run mode was enabled", fg=typer.colors.YELLOW)


@app.command("hotfix-release")
def hotfix_release(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """Patches a release that was promoted to production.

    Call this from an up-to-date branch of the most recently released Sculptor version. This will create a new patch
    branch.
    """
    old_version = pyproject_version()

    if not bypass_checks:
        ensure_on_branch(f"release/sculptor-v{old_version}")
        ensure_clean_tree()

        if is_prerelease(old_version):
            typer.secho(
                "You cannot hotfix a pre-release version! Did you forget to release or do you need to git fetch?",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    hotfix_release_version = next_version(old_version, VersionComponent.PATCH)

    typer.echo(f"Begining a hotfix branch for {hotfix_release_version}.")

    # Verify there isn't a release tag and release branch for this.
    _run_out(["git", "fetch", "--tags"])
    _run_out(["git", "fetch"])

    if _run_pipe(["git", "tag", "--list", f"sculptor-v{hotfix_release_version}"]).stdout:
        typer.echo("We already hotfixed this release! Do you need to update your hotfix target?")
        raise typer.Exit(code=1)

    if _run_pipe(["git", "branch", "--list", f"release/sculptor-v{hotfix_release_version}"]).stdout:
        typer.echo("We already attempted to hotfix this release! Do you need to switch your hotfix target?")
        typer.echo("A branch already exists for this version, but no release tag.")
        typer.echo("A prior release cut failed. Please delete the branch from origin and try again.")
        raise typer.Exit(code=1)

    # Write the rc version to the pyproject.toml file and begin a new branch.
    commit_new_version(f"release/sculptor-v{hotfix_release_version}", hotfix_release_version, dry_run=dry_run)

    typer.echo(f"Created a new hotfix branch for Sculptor {hotfix_release_version} from git sha {dev_git_sha()}")
    typer.echo("Now you must go and apply your fixups to that branch.")


@app.command("promote-release")
def promote_release(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """Promotes this release candidate version to a full release, and tags it.

    This initiates the process which will build and publish the release artifacts to all build targets.
    """

    release_version = next_version(pyproject_version(), VersionComponent.STRIP_PRE_RELEASE)

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

    typer.echo(f"Releasing Sculptor {pyproject_version()} from git sha {dev_git_sha()}")

    if not dry_run:
        push_tags(release_version)
        typer.secho("Tags have been pushed, and release will be kicked off.", fg=typer.colors.GREEN)
    else:
        typer.secho("Dry run: No tags were pushed")


@app.command("publish-build-artifacts")
def publish_build_artifacts(
    dry_run: bool = typer.Option(
        False,  # default → real upload
        "--dry-run/--no-dry-run",
        "-n",  # short alias for --dry-run
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
    dist_dir: Path = typer.Option("../dist", help="Directory that holds build artefacts."),
) -> None:
    """This command publishes _already built_ artifacts from s3 to the deployed buckets.

    Calling publish turns the artifacts that were already built live.

    You may only call publish after building has completed for _all_ artifacts, on every platform we support.
    """
    # We only publish the specific concrete version that is in the pyproject.toml file.
    release_version = pyproject_version()

    if not bypass_checks:
        ensure_clean_tree()

    if is_devrelease(release_version):
        stages = [BuildStage.DEV]
    elif is_prerelease(release_version):
        stages = [BuildStage.RC]
    else:
        stages = [BuildStage.RC, BuildStage.STABLE]

    typer.secho(
        f"\nPublish was triggered to {[stage.value for stage in stages]} for Sculptor {release_version} from git sha {dev_git_sha()}",
        fg=typer.colors.YELLOW,
    )

    files_to_copy = []
    for stage in stages:
        for target in PLATFORM_ARCH_TO_TARGET.values():
            artifacts = artifacts_for_target_and_stage(
                target,
                stage,
                pipeline_id=os.environ.get("CI_PIPELINE_ID", ""),
            )
            files_to_copy.extend(artifacts)

    if not bypass_checks:
        typer.echo("  • Verifying source artifacts exist in S3")
        are_artifacts_missing = False
        for artifact in files_to_copy:
            # Run s3 ls to verify the file exists
            try:
                _run_out(
                    [
                        "uv",
                        "tool",
                        "run",
                        "--from",
                        "awscli==1.41.12",
                        "--refresh",
                        "aws",
                        "s3",
                        "ls",
                        artifact.input_path,
                    ]
                )
            except subprocess.CalledProcessError:
                typer.secho(f"Source artifact not found: {artifact.input_path}", fg=typer.colors.RED)
                are_artifacts_missing = True
        if are_artifacts_missing:
            raise typer.Exit(code=1)

    versioned_urls: list[str] = []

    if not dry_run:
        typer.echo("  • Publishing artifacts to release buckets")
        for artifact in files_to_copy:
            for i, output_path in enumerate(artifact.output_paths):
                s3_copy(artifact.input_path, output_path, dry_run=dry_run)
                # output_paths[0] is the mutable path (matches input_path);
                # output_paths[1:] are the versioned (immutable) copies.
                if i > 0:
                    versioned_urls.append(s3_uri_to_https(output_path))

    else:
        typer.secho("Would have made the following copies, but dry-run mode was enabled.", fg=typer.colors.YELLOW)
        for artifact in files_to_copy:
            typer.secho(f"    {artifact!r}")

    if versioned_urls:
        typer.echo("\nVersioned artifact URLs:")
        for url in versioned_urls:
            typer.echo(f"  {url}")


@app.command("snapshot-build-artifacts")
def snapshot_build_artifacts(
    platform: str = typer.Option("linux", "--platform", "-p"),
    arch: str = typer.Option("x86_64", "--arch", "-a"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--no-dry-run",
        "-n",
        help="Pass --dry-run (-n) to skip uploading or --no-dry-run to force the actual upload.",
    ),
) -> None:
    """Puts the release artifacts for the given build in s3.

    Release builds (RC/stable) upload to the BUILT prefix (slim/{sha}/).
    Dev builds upload to the DEV staging prefix (slim-dev/{sha}/{pipeline_id}/).
    """
    typer.echo(f"Staging release artifacts for platform={platform}, arch={arch}")

    target = PLATFORM_ARCH_TO_TARGET[platform, arch]

    if is_devrelease(pyproject_version()):
        # Dev builds go to the dev-specific S3 prefix.
        pipeline_id = os.environ.get("CI_PIPELINE_ID", "")
        if not pipeline_id:
            typer.secho("CI_PIPELINE_ID must be set for dev builds", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        git_sha = dev_git_sha(short=False)
        dev_prefix = f"s3://imbue-sculptor-builds/slim-dev/{git_sha}/{pipeline_id}"
        # Use BUILT stage to resolve local input paths and artifact names.
        files = artifacts_for_target_and_stage(target, BuildStage.BUILT)
        typer.echo(f"Staging dev artifacts to {dev_prefix}:\n  {files!r}")
        for artifact in files:
            for output_path in artifact.output_paths:
                relative_path = output_path.split(git_sha + "/", 1)[-1]
                dev_destination = f"{dev_prefix}/{relative_path}"
                s3_copy(artifact.input_path, dev_destination, dry_run=dry_run)
    else:
        # Release builds (RC/stable) go to the BUILT prefix.
        files = artifacts_for_target_and_stage(target, BuildStage.BUILT)
        typer.echo(f"Found artifacts to stage:\n  {files!r}")
        for artifact in files:
            for output_path in artifact.output_paths:
                s3_copy(artifact.input_path, output_path, dry_run=dry_run)


@app.command("retrieve-build-artifacts")
def retrieve_build_artifacts(
    platform: str = typer.Option("linux", "--platform", "-p"),
    arch: str = typer.Option("x64", "--arch", "-a"),
    version: str | None = typer.Option(None, "--version", "-v", help="The PEP440 Version to retrieve, e.g. v0.3.0"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--no-dry-run",
        "-n",
        help="Pass --dry-run (-n) to skip retrieval or --no-dry-run to force the actual download.",
    ),
) -> None:
    """Pulls down the release artifacts for the current build from s3"""

    if version is not None:
        try:
            version_sha = _run_pipe(
                ["git", "show", "--pretty=%H", "-s", f"sculptor-v{version.lstrip('v')}"]
            ).stdout.strip()
        except subprocess.CalledProcessError:
            typer.secho(f"Could not find git tag for sculptor-v{version.lstrip('v')}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    else:
        version_sha = None

    typer.echo(f"About to retrieve release artifacts for platform={platform}, arch={arch}")

    target = PLATFORM_ARCH_TO_TARGET[platform, arch]
    stage = BuildStage.BUILT
    files = artifacts_for_target_and_stage(target, stage, version_override=version, git_sha_override=version_sha)
    typer.echo(f"Found artifacts to retrieve:\n  {files!r}")

    for artifact in files:
        output_path = artifact.output_paths[0]
        # Reverse the order of this copy--from the output path in s3 to local.
        s3_copy(source=output_path, destination=artifact.input_path, dry_run=dry_run)


@app.command("bump-version")
def bump_version(
    bypass_checks: bool = typer.Option(False, "--bypass-checks", help="Bypass branch protection checks"),
) -> None:
    """Bumps the version of Sculptor and opens a version-bump PR on GitHub.

    The new version will always have a .dev0 suffix, since main must stay on a dev version.
    For example, bumping minor from 0.10.0.dev0 produces 0.11.0.dev0.
    """

    old_version = pyproject_version()
    typer.echo(f"Current Sculptor version is {old_version}")

    if not bypass_checks:
        if not is_devrelease(old_version):
            typer.secho(
                f"Expected a .dev version on main, got '{old_version}'. Is this the right branch?",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    bump_index = "Mmp".index(
        typer.prompt("Are you trying to bump a [M]ajor, [m]inor, or [p]atch version?", default="m")
    )
    # Strip .dev0 before bumping so next_version sees a clean version (e.g. 0.10.0).
    base_version = strip_dev_suffix(old_version)
    new_version = next_version(base_version, VersionComponent(bump_index)) + ".dev0"
    typer.echo(f"The new Sculptor version will be {new_version}")

    if not bypass_checks:
        if bump_index in [0, 1]:
            # We're doing a regular release, from main
            ensure_on_branch("main")
        else:
            typer.secho(
                "You shouldn't bump the patch version, you probably want `just hotfix-release`.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        ensure_clean_tree()

    # New branch + MR for the version bump.
    branch_name = f"automated/bump-sculptor-v{new_version}"
    commit_new_version(branch_name, new_version)

    description = f"Manual version bump from `{old_version}` to `{new_version}`."
    create_version_bump_mr(branch_name, new_version, description)


def commit_new_version(branch_name: str | None, new_version: str, dry_run: bool = False) -> None:
    """Commit a version bump, optionally on a new branch, and push.

    Preconditions:
        - The working tree is clean.
    """

    if branch_name:
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
            _run_out(["git", "push", "--set-upstream", "origin", branch_name])
        else:
            _run_out(["git", "push", "--set-upstream", "origin"])
    else:
        typer.echo(f"Would have pushed branch {branch_name} to origin, but dry-run mode was enabled.")
        typer.echo("Please remember to delete this branch before trying to take another cut.")


def create_version_bump_mr(branch_name: str, new_version: str, description: str, dry_run: bool = False) -> None:
    """Open a GitHub PR for a version-bump branch targeting main, and try to enable auto-merge.

    Auto-merge is a repo-level setting that may be disabled; if gh can't enable it
    we fall back to a message rather than failing the whole release cut — the bump
    PR can be merged by hand once its checks pass.
    """
    if dry_run:
        typer.echo(f"Would have created PR for {branch_name}, but dry-run mode was enabled.")
        return

    _run_out(
        [
            "gh",
            "pr",
            "create",
            "--title",
            f"Bump Sculptor version to v{new_version}",
            "--body",
            description,
            "--base",
            "main",
            "--head",
            branch_name,
        ]
    )

    # Enable auto-merge so the PR lands once required checks pass. Squash keeps the
    # bump to a single commit on main, matching the clean-history convention.
    result = subprocess.run(
        ["gh", "pr", "merge", branch_name, "--auto", "--squash"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        typer.echo("Auto-merge enabled.")
    else:
        typer.secho(
            f"Could not enable auto-merge: {result.stderr.strip()}",
            err=True,
            fg=typer.colors.YELLOW,
        )
        typer.echo("Merge the version-bump PR manually from the GitHub UI once its checks pass.")


def strip_dev_suffix(version: str) -> str:
    """Strip the .devN suffix from a version string, returning the base version.

    For example, '0.10.0.dev0' -> '0.10.0'. Non-dev versions are returned unchanged.
    """
    v = Version(version)
    if v.dev is not None:
        return f"{v.major}.{v.minor}.{v.micro}"
    return version


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
    # No verify since this is only pushing a tag, and pyre can fail here.
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


def ensure_at_main_tip() -> None:
    """Abort unless HEAD is at the same commit as origin/main.

    Looser than `ensure_on_branch("main")`: any branch (e.g. a worktree branch)
    is allowed as long as it points at main's tip. git refuses to share a
    checked-out branch across worktrees, so a second worktree can never be on
    `main` itself even when at main's tip.
    """
    head_sha = _run_pipe(["git", "rev-parse", "HEAD"]).stdout.strip()
    try:
        main_sha = _run_pipe(["git", "rev-parse", "origin/main"]).stdout.strip()
    except subprocess.CalledProcessError:
        typer.secho(
            "Could not resolve origin/main. Run `git fetch origin main` and try again.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    if head_sha != main_sha:
        typer.secho(
            f"HEAD ({head_sha[:8]}) must be at the tip of origin/main ({main_sha[:8]})."
            + " Pull/rebase onto main, or check out a branch at main's tip.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def check_release_tag(version: str, tag: str) -> str | None:
    """Return an error string if the pyproject `version` is inconsistent with the
    build context, or None if it is consistent.

    Encodes the assumptions create-version-file already makes, in one place, so
    they can be checked up front:
    - Tag build (tag given): the version must be a real release — an RC or a
      stable release, never a .dev version — and must equal the tag's version
      (PEP 440-normalized). create-version-file uses pyproject as-is on tags, so
      a mismatch would silently stamp/publish the wrong version.
    - Non-tag build (tag empty): the version must be a .dev version, because
      main / workflow_dispatch builds run create-version-file --annotate-dev,
      which requires a .dev base.
    """
    if tag:
        tag_version = tag.removeprefix("sculptor-v")
        if is_devrelease(version):
            return f"Tag build '{tag}' but pyproject version '{version}' is a .dev version; bump pyproject to the release (rc/stable) version before tagging."
        try:
            tags_match = Version(tag_version) == Version(version)
        except InvalidVersion:
            return f"Tag '{tag}' does not parse as a PEP 440 version after stripping the 'sculptor-v' prefix."
        if not tags_match:
            return f"Tag version '{tag_version}' does not match pyproject version '{version}'; bump pyproject to match the tag before pushing it."
        return None
    if not is_devrelease(version):
        return f"Non-tag build but pyproject version '{version}' is not a .dev version; main / workflow_dispatch builds need a .dev base for create-version-file --annotate-dev."
    return None


@app.command("verify-release-tag")
def verify_release_tag(
    tag: str = typer.Option(
        "",
        "--tag",
        help="Git tag for a tag build (e.g. sculptor-v0.1.2rc1). Leave empty for a non-tag (dev) build.",
    ),
) -> None:
    """Fail fast if pyproject.toml's version is inconsistent with the build context.

    Run before the desktop build so a tag/version or dev/release mismatch stops
    the pipeline in seconds, rather than surfacing 30-60 minutes in or publishing
    to the wrong channel.
    """
    version = pyproject_version()
    error = check_release_tag(version, tag)
    if error is not None:
        typer.secho(error, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    context = f"tag '{tag}'" if tag else "non-tag (dev) build"
    typer.secho(f"Version check OK: pyproject '{version}' is consistent with {context}.", fg=typer.colors.GREEN)


@app.command("create-version-file")
def create_version_file(
    annotate_dev: bool = typer.Option(
        False,
        "--annotate-dev",
        help="Generate a timestamped .dev version instead of using pyproject.toml as-is. Requires CI_PIPELINE_CREATED_AT and CI_PIPELINE_IID env vars.",
    ),
) -> None:
    """Create a version file with the Sculptor version and Git SHA.

    With --annotate-dev, the base .dev0 version from pyproject.toml is replaced
    with a timestamped dev version (e.g. 0.10.0.dev20260305000042) and written
    into both _version.py and pyproject.toml. This is used by CI to produce
    unique dev builds. The pyproject.toml update ensures downstream tools (artifact
    paths, frontend version sync) see the correct version.

    CI_PIPELINE_IID (project-scoped pipeline counter) is used so that every job
    in the same pipeline derives the identical version string, and the number
    stays small enough for 6 digits.
    """
    sculptor_version = pyproject_version()

    if annotate_dev:
        if not is_devrelease(sculptor_version):
            typer.secho(
                f"--annotate-dev requires a .dev version in pyproject.toml, got '{sculptor_version}'",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        pipeline_created_at = os.environ.get("CI_PIPELINE_CREATED_AT", "")
        pipeline_iid = os.environ.get("CI_PIPELINE_IID", "")
        if not pipeline_created_at or not pipeline_iid:
            typer.secho(
                "CI_PIPELINE_CREATED_AT and CI_PIPELINE_IID must be set for --annotate-dev",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        # CI_PIPELINE_CREATED_AT gives a deterministic date across all jobs.
        # CI_PIPELINE_IID is the project-scoped counter, so every job in the
        # same pipeline produces the same version and the number fits in 6 digits.
        date_str = pipeline_created_at[:10].replace("-", "")
        base = sculptor_version.split(".dev")[0]
        sculptor_version = f"{base}.dev{date_str}{int(pipeline_iid):06d}"
        typer.echo(f"Annotated dev version: {sculptor_version}")
        write_project_version(sculptor_version)

    sha = dev_git_sha()
    ci_job_id = os.environ.get("CI_JOB_ID")
    ci_ref = os.environ.get("CI_COMMIT_TAG") or os.environ.get("CI_COMMIT_BRANCH")
    with open("sculptor/_version.py", "w") as f:
        f.write(
            f'"""Sculptor v{sculptor_version} version file, autogenerated by the build process.\nDo not edit."""\n'
        )
        f.write(f"__version__ = '{sculptor_version}'\n")
        f.write(f"__git_sha__ = '{sha}'\n")
        f.write(f"ci_job_id = {repr(ci_job_id) if ci_job_id is not None else 'None'}\n")
        f.write(f"ci_ref = {repr(ci_ref) if ci_ref is not None else 'None'}\n")


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
        target_version = pep_440_to_semver(pyproject_version())
        action = "Updated"

    package_data["version"] = target_version

    # Write back to package.json
    with frontend_package_json_path.open("w") as f:
        json.dump(package_data, f, indent=2)
        f.write("\n")  # Add final newline for consistency

    typer.secho(f"{action} frontend package.json version: {old_version} → {target_version}", fg=typer.colors.GREEN)


def s3_uri_to_https(s3_uri: str) -> str:
    """Convert an S3 URI to an HTTPS URL.

    For example, 's3://imbue-sculptor-releases/slim-rc/Sculptor.dmg'
    becomes 'https://imbue-sculptor-releases.s3.amazonaws.com/slim-rc/Sculptor.dmg'.
    """
    if not s3_uri.startswith("s3://"):
        return s3_uri
    without_scheme = s3_uri[len("s3://") :]
    bucket, _, key = without_scheme.partition("/")
    return f"https://{bucket}.s3.amazonaws.com/{key}"


def s3_copy(source: str, destination: str, dry_run: bool = False) -> None:
    """Uses the s3 CLI cp command to copy a file to s3.

    Either source or destination may be local filepaths or s3 uris
    """
    cmd_base = ["uv", "tool", "run", "--from", "awscli==1.41.12", "--refresh", "aws", "s3", "cp"]
    if dry_run:
        cmd_base.append("--dryrun")

    _run_out([*cmd_base, source, destination])


@app.command("validate-darwin-binary")
def validate_darwin_binary(
    binary_path: Path = typer.Argument(..., help="Path to the macOS binary to validate."),
    arch: str = typer.Argument(..., help="Architecture of the binary (e.g., x86_64, arm64)."),
) -> None:
    """Given a file within the macOs App Bundle, this performs various validations."""

    if not darwin.validate_binary(binary_path=str(binary_path), arch=arch):
        typer.secho(f"Validation failed for binary at {binary_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
