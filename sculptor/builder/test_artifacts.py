"""Tests for the target module."""

import pytest
from builder.artifacts import ArtifactFile
from builder.artifacts import BuildStage
from builder.artifacts import Target
from builder.artifacts import artifacts_for_target_and_stage

from sculptor import version
from sculptor.version import pep_440_to_semver

GIT_SHA = version.dev_git_sha(is_short=False)
VERSION = version.pyproject_version()
SEMVER_VERSION = pep_440_to_semver(VERSION)

DEV_PIPELINE_ID = "99999"
DEV_VERSION = "0.10.0.dev20260303099999"
DEV_SEMVER_VERSION = pep_440_to_semver(DEV_VERSION)


@pytest.mark.parametrize(
    ["target", "stage", "extra_kwargs", "expected_artifact_files"],
    [
        # ---------------- LINUX X64 ----------------
        (
            Target.LINUX_X64,
            BuildStage.RC,
            {},
            [
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/Sculptor.AppImage",
                    [
                        "s3://imbue-sculptor-releases/slim-rc/AppImage/x64/Sculptor.AppImage",
                        f"s3://imbue-sculptor-releases/slim-rc/AppImage/x64/Sculptor-{VERSION}.AppImage",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/latest-linux.yml",
                    ["s3://imbue-sculptor-releases/slim-rc/AppImage/x64/latest-linux.yml"],
                ),
            ],
        ),
        (
            Target.LINUX_X64,
            BuildStage.STABLE,
            {},
            [
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/Sculptor.AppImage",
                    [
                        "s3://imbue-sculptor-releases/slim/AppImage/x64/Sculptor.AppImage",
                        f"s3://imbue-sculptor-releases/slim/AppImage/x64/Sculptor-{VERSION}.AppImage",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/latest-linux.yml",
                    ["s3://imbue-sculptor-releases/slim/AppImage/x64/latest-linux.yml"],
                ),
            ],
        ),
        (
            Target.LINUX_X64,
            BuildStage.BUILT,
            {},
            [
                (
                    "../dist/AppImage/x64/Sculptor.AppImage",
                    [
                        f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/Sculptor.AppImage",
                        f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/Sculptor-{VERSION}.AppImage",
                    ],
                ),
                (
                    "../dist/AppImage/x64/latest-linux.yml",
                    [f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/AppImage/x64/latest-linux.yml"],
                ),
            ],
        ),
        (
            Target.LINUX_X64,
            BuildStage.DEV,
            {"version_override": DEV_VERSION, "git_sha_override": GIT_SHA, "pipeline_id": DEV_PIPELINE_ID},
            [
                (
                    f"s3://imbue-sculptor-builds/slim-dev/{GIT_SHA}/{DEV_PIPELINE_ID}/AppImage/x64/Sculptor.AppImage",
                    [
                        f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/AppImage/x64/Sculptor.AppImage",
                        f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/AppImage/x64/Sculptor-{DEV_VERSION}.AppImage",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim-dev/{GIT_SHA}/{DEV_PIPELINE_ID}/AppImage/x64/latest-linux.yml",
                    [f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/AppImage/x64/latest-linux.yml"],
                ),
            ],
        ),
        # ---------------- MAC ARM64 ----------------
        (
            Target.MAC_ARM64,
            BuildStage.RC,
            {},
            [
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/Sculptor.dmg",
                    [
                        "s3://imbue-sculptor-releases/slim-rc/Sculptor.dmg",
                        f"s3://imbue-sculptor-releases/slim-rc/Sculptor-{VERSION}.dmg",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip",
                    [
                        f"s3://imbue-sculptor-releases/slim-rc/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip"
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/latest-mac.yml",
                    ["s3://imbue-sculptor-releases/slim-rc/zip/darwin/arm64/latest-mac.yml"],
                ),
            ],
        ),
        (
            Target.MAC_ARM64,
            BuildStage.STABLE,
            {},
            [
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/Sculptor.dmg",
                    [
                        "s3://imbue-sculptor-releases/slim/Sculptor.dmg",
                        f"s3://imbue-sculptor-releases/slim/Sculptor-{VERSION}.dmg",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip",
                    [f"s3://imbue-sculptor-releases/slim/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip"],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/latest-mac.yml",
                    ["s3://imbue-sculptor-releases/slim/zip/darwin/arm64/latest-mac.yml"],
                ),
            ],
        ),
        (
            Target.MAC_ARM64,
            BuildStage.BUILT,
            {},
            [
                (
                    "../dist/Sculptor.dmg",
                    [
                        f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/Sculptor.dmg",
                        f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/Sculptor-{VERSION}.dmg",
                    ],
                ),
                (
                    f"../dist/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip",
                    [
                        f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/Sculptor-darwin-arm64-{SEMVER_VERSION}.zip"
                    ],
                ),
                (
                    "../dist/zip/darwin/arm64/latest-mac.yml",
                    [f"s3://imbue-sculptor-builds/slim/{GIT_SHA}/zip/darwin/arm64/latest-mac.yml"],
                ),
            ],
        ),
        (
            Target.MAC_ARM64,
            BuildStage.DEV,
            {"version_override": DEV_VERSION, "git_sha_override": GIT_SHA, "pipeline_id": DEV_PIPELINE_ID},
            [
                (
                    f"s3://imbue-sculptor-builds/slim-dev/{GIT_SHA}/{DEV_PIPELINE_ID}/Sculptor.dmg",
                    [
                        f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/Sculptor.dmg",
                        f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/Sculptor-{DEV_VERSION}.dmg",
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim-dev/{GIT_SHA}/{DEV_PIPELINE_ID}/zip/darwin/arm64/Sculptor-darwin-arm64-{DEV_SEMVER_VERSION}.zip",
                    [
                        f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/zip/darwin/arm64/Sculptor-darwin-arm64-{DEV_SEMVER_VERSION}.zip"
                    ],
                ),
                (
                    f"s3://imbue-sculptor-builds/slim-dev/{GIT_SHA}/{DEV_PIPELINE_ID}/zip/darwin/arm64/latest-mac.yml",
                    [f"s3://imbue-sculptor-releases/slim-dev/{DEV_VERSION}/zip/darwin/arm64/latest-mac.yml"],
                ),
            ],
        ),
    ],
)
def test_artifacts_for_target_stage(target, stage, extra_kwargs, expected_artifact_files):
    """Verifies that we load the correct files for a particular platform and arch."""

    expected = []
    for input_path, output_paths in expected_artifact_files:
        expected.append(ArtifactFile(input_path=input_path, output_paths=output_paths))

    assert artifacts_for_target_and_stage(target=target, build_stage=stage, **extra_kwargs) == expected
