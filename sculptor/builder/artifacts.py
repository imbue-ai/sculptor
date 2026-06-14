"""This module defines where artifact files are uploaded once the build process completes.

This module contains type definitions specifying the Target Platform and Architecture,
the Package type and the locations in S3 where these can be found.

The key function of this module is:

`targets_for_target_and_stage()` which returns the targets as a list of ArtifactFiles.

An ArtifactFile specifies an origin file to a list of destination files. Once
the build process completes, this module can be used to determine which local
files should be copied, and to what destinations.


If you add a new artifact file to the build process, you should add it to the maps below.
"""

import enum
from os import path
from typing import Mapping

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.version import dev_git_sha
from sculptor.version import pep_440_to_semver
from sculptor.version import pyproject_version

DIST_DIR = "../dist"


class FileExtension(enum.Enum):
    DMG = ".dmg"
    ZIP = ".zip"
    APPIMAGE = ".AppImage"
    YML = ".yml"


class Target(enum.StrEnum):
    """We only build for the following platform/architecture combinations."""

    LINUX_X64 = "LINUX_X64"
    LINUX_ARM64 = "LINUX_ARM64"
    MAC_ARM64 = "MAC_ARM64"


TARGET_TO_PLATFORM_ARCH = {
    Target.LINUX_X64: ("linux", "x64"),
    Target.LINUX_ARM64: ("linux", "arm64"),
    Target.MAC_ARM64: ("darwin", "arm64"),
}

PLATFORM_ARCH_TO_TARGET = {v: k for (k, v) in TARGET_TO_PLATFORM_ARCH.items()}


class BuildStage(enum.StrEnum):
    # Built artifacts are keyed by Git SHA, and have not yet been tested.
    BUILT = "BUILT"

    # Release candidate artifacts are published for QA testing.
    RC = "RC"

    # Released artifacts are published for general availability.
    STABLE = "STABLE"

    # Dev build artifacts are published from daily CI builds.
    DEV = "DEV"


class ArtifactFile(SerializableModel):
    """An ArtifactFile represents a single artifact that is built for a given target platform/architecture.

    An ArtifactFile has an input path which is either:
      * the local path to the file produced by the build process (electron) or
      * the object key of the file as uploaded to s3 previously

    The Output paths are the names of the files as stored in S3, which may differ from the input filename. If there
    are mulitple names, it means that the file will be duplicated in S3.
    """

    # The path to the filename, including extension. You may include format string specifiers such as {platform}, {arch} and {version}.
    input_path: str
    # Destination filenames in S3 for each platform/architecture. You may include specifiers such as {platform}, {arch} and {version}.
    output_paths: list[str]

    def interpolate_paths(
        self,
        build_stage: BuildStage,
        target: Target,
        version: str,
        git_sha: str,
        pipeline_id: str = "",
    ) -> "ArtifactFile":
        """Returns a new ArtifactFile with all inputs and outputs interpolated."""

        input_prefix = BUILD_STAGE_TO_INPUT_PREFIX[build_stage].format(
            git_sha=git_sha, pipeline_id=pipeline_id, version=version
        )
        output_prefix = BUILD_STAGE_TO_OUTPUT_PREFIX[build_stage].format(
            git_sha=git_sha, pipeline_id=pipeline_id, version=version
        )
        platform, arch = TARGET_TO_PLATFORM_ARCH[target]

        localized_input_path = path.join(
            input_prefix,
            self.input_path.format(
                platform=platform,
                arch=arch,
                version=version,
                pedantic_version=pep_440_to_semver(version),
            ),
        )

        localized_output_paths = [
            path.join(
                output_prefix,
                output_path.format(
                    platform=platform,
                    arch=arch,
                    version=version,
                    pedantic_version=pep_440_to_semver(version),
                ),
            )
            for output_path in self.output_paths
        ]
        return ArtifactFile(input_path=localized_input_path, output_paths=localized_output_paths)


TARGET_TO_FILES: Mapping[Target, list[ArtifactFile]] = {
    Target.LINUX_X64: [
        ArtifactFile(
            input_path="AppImage/x64/Sculptor.AppImage",
            output_paths=["AppImage/x64/Sculptor.AppImage", "AppImage/x64/Sculptor-{version}.AppImage"],
        ),
        ArtifactFile(
            input_path="AppImage/x64/latest-linux.yml",
            output_paths=["AppImage/x64/latest-linux.yml"],
        ),
    ],
    Target.LINUX_ARM64: [
        ArtifactFile(
            input_path="AppImage/arm64/Sculptor.AppImage",
            output_paths=["AppImage/arm64/Sculptor.AppImage", "AppImage/arm64/Sculptor-{version}.AppImage"],
        ),
        ArtifactFile(
            input_path="AppImage/arm64/latest-linux-arm64.yml",
            output_paths=["AppImage/arm64/latest-linux-arm64.yml"],
        ),
    ],
    Target.MAC_ARM64: [
        ArtifactFile(
            input_path="Sculptor.dmg",
            output_paths=["Sculptor.dmg", "Sculptor-{version}.dmg"],
        ),
        ArtifactFile(
            input_path="zip/darwin/arm64/Sculptor-darwin-arm64-{pedantic_version}.zip",
            output_paths=["zip/darwin/arm64/Sculptor-darwin-arm64-{pedantic_version}.zip"],
        ),
        ArtifactFile(
            input_path="zip/darwin/arm64/latest-mac.yml",
            output_paths=["zip/darwin/arm64/latest-mac.yml"],
        ),
    ],
}

for artifact_files in TARGET_TO_FILES.values():
    for artifact_file in artifact_files:
        if artifact_file.input_path != artifact_file.output_paths[0]:
            raise ValueError(
                f"Input path and first output path must match for {artifact_file} or publishing will not work"
            )


# This represents where we publish FROM.
BUILD_STAGE_TO_INPUT_PREFIX = {
    # The Built stage always publishes from the local file system
    BuildStage.BUILT: DIST_DIR,
    # RC and STABLE publish from the built stage in s3
    BuildStage.RC: "s3://imbue-sculptor-builds/slim/{git_sha}",
    BuildStage.STABLE: "s3://imbue-sculptor-builds/slim/{git_sha}",
    # DEV builds are stored with pipeline_id for isolation
    BuildStage.DEV: "s3://imbue-sculptor-builds/slim-dev/{git_sha}/{pipeline_id}",
}

BUILD_STAGE_TO_OUTPUT_PREFIX = {
    # The Built stage always publishes to the "build" bucket in s3
    BuildStage.BUILT: "s3://imbue-sculptor-builds/slim/{git_sha}",
    # The remaining stages publish to the relevant folder in the "releases" bucket.
    BuildStage.RC: "s3://imbue-sculptor-releases/slim-rc",
    BuildStage.STABLE: "s3://imbue-sculptor-releases/slim",
    BuildStage.DEV: "s3://imbue-sculptor-releases/slim-dev/{version}",
}


def artifacts_for_target_and_stage(
    target: Target,
    build_stage: BuildStage,
    version_override: str | None = None,
    git_sha_override: str | None = None,
    pipeline_id: str = "",
) -> list[ArtifactFile]:
    """Returns the artifact_files which we need to copy for a given build"""

    if build_stage == BuildStage.DEV and not pipeline_id:
        raise ValueError("pipeline_id is required for DEV stage to avoid clobbering S3 paths")

    artifact_files: list[ArtifactFile] = TARGET_TO_FILES[target]
    if version_override and git_sha_override:
        version = version_override
        git_sha = git_sha_override
    else:
        version = pyproject_version()
        git_sha = dev_git_sha(short=False)

    return [
        artifact_file.interpolate_paths(
            build_stage=build_stage,
            target=target,
            version=version,
            git_sha=git_sha,
            pipeline_id=pipeline_id,
        )
        for artifact_file in artifact_files
    ]
